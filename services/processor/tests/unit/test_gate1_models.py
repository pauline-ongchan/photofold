import json
import zipfile
from datetime import UTC, datetime

import numpy as np
import pytest
from pydantic import ValidationError

from photofold.gate1.bundle import (
    PackageValidationError,
    decode_all_package_frames,
    verify_package,
)
from photofold.gate1.images import encode_webp, rgb_ssim, sha256_bytes
from photofold.gate1.models import (
    FrameRecord,
    NormalizedDimensions,
    PatchRecord,
    TransformRecord,
)


def test_rgb_ssim_is_exact_for_identical_decoded_pixels() -> None:
    image = np.arange(16 * 16 * 3, dtype=np.uint8).reshape(16, 16, 3)

    assert rgb_ssim(image, image.copy()) == pytest.approx(1.0)


def test_manifest_model_rejects_a_full_canvas_change_patch() -> None:
    with pytest.raises(ValidationError, match="full-canvas"):
        FrameRecord(
            index=0,
            original_filename="frame.jpg",
            output_width=100,
            output_height=80,
            normalized_dimensions=NormalizedDimensions(width=100, height=80),
            storage_mode="shared_delta",
            transform=TransformRecord(
                type="identity",
                reference_to_target=[1, 0, 0, 0, 1, 0, 0, 0, 1],
                inlier_count=0,
                inlier_ratio=1,
                median_reprojection_error=0,
                reprojection_error_units="analysis_pixels",
                reprojection_error_threshold=2,
                valid_overlap=1,
            ),
            patches=[
                PatchRecord(
                    bbox=[0, 0, 100, 80],
                    image_path="frames/000/patches/000.webp",
                    mask_path="frames/000/patches/000-mask.png",
                )
            ],
        )


def test_transform_model_rejects_a_singular_matrix() -> None:
    with pytest.raises(ValidationError, match="singular"):
        TransformRecord(
            type="homography",
            reference_to_target=[1, 0, 0, 0, 1, 0, 0, 0, 0],
            inlier_count=10,
            inlier_ratio=0.9,
            median_reprojection_error=0.5,
            reprojection_error_units="analysis_pixels",
            reprojection_error_threshold=2,
            valid_overlap=0.95,
        )


def test_patch_model_rejects_an_unbounded_feather_radius() -> None:
    with pytest.raises(ValidationError, match="less than or equal to 64"):
        PatchRecord(
            bbox=[1, 1, 10, 10],
            image_path="frames/000/patches/000.webp",
            mask_path="frames/000/patches/000-mask.png",
            feather_radius=65,
        )


def test_package_validator_rejects_unsafe_zip_paths(tmp_path) -> None:
    package_path = tmp_path / "unsafe.photofold"
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("../escape", b"unsafe")
        archive.writestr("manifest.json", b"{}")

    with pytest.raises(PackageValidationError, match="Unsafe package path"):
        verify_package(package_path)


def test_public_decoder_remains_backward_compatible_with_version_0_1(tmp_path) -> None:
    package_path = tmp_path / "legacy.photofold"
    pixels = np.random.default_rng(12).integers(0, 256, (48, 64, 3), dtype=np.uint8)
    assets: dict[str, bytes] = {"base.webp": encode_webp(pixels, 70)}
    frames = []
    for index in range(5):
        frame = {
            "index": index,
            "original_filename": f"legacy-{index}.jpg",
            "output_width": 64,
            "output_height": 48,
            "transform": {
                "type": "identity",
                "reference_to_target": [1, 0, 0, 0, 1, 0, 0, 0, 1],
                "interpolation": "linear",
                "border_mode": "constant",
                "inlier_count": 0,
                "inlier_ratio": 1,
                "median_reprojection_error": 0,
                "valid_overlap": 1,
            },
            "patches": [],
        }
        frames.append(frame)
        assets[f"frames/{index:03d}/frame.json"] = (
            json.dumps(frame, separators=(",", ":"), sort_keys=True) + "\n"
        ).encode()
    assets["metadata/analysis.json"] = b"{}\n"
    assets["metadata/metrics.json"] = b'{"original_total_bytes":1}\n'
    manifest = {
        "format": "photofold",
        "version": "0.1",
        "created_at": datetime.now(UTC).isoformat(),
        "reference_frame_index": 0,
        "required_codecs": ["webp", "png"],
        "base": {
            "path": "base.webp",
            "width": 64,
            "height": 48,
            "encoding": "webp",
            "quality": 70,
        },
        "frames": frames,
        "assets": [
            {"path": name, "bytes": len(payload), "sha256": sha256_bytes(payload)}
            for name, payload in assets.items()
        ],
        "analysis_path": "metadata/analysis.json",
        "metrics_path": "metadata/metrics.json",
        "semantic_analysis_path": None,
    }
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(manifest, separators=(",", ":"), sort_keys=True) + "\n",
        )
        for name, payload in assets.items():
            archive.writestr(name, payload)

    verification = verify_package(package_path)
    reconstructions = decode_all_package_frames(package_path)

    assert verification["status"] == "pass"
    assert verification["strategy"] == "shared_scene"
    assert len(reconstructions) == 5
    assert all(image.shape == (48, 64, 3) for image in reconstructions)
