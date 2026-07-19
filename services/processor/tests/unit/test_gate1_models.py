import zipfile

import numpy as np
import pytest
from pydantic import ValidationError

from photofold.gate1.bundle import PackageValidationError, verify_package
from photofold.gate1.images import rgb_ssim
from photofold.gate1.models import FrameRecord, PatchRecord, TransformRecord


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
            transform=TransformRecord(
                type="identity",
                reference_to_target=[1, 0, 0, 0, 1, 0, 0, 0, 1],
                inlier_count=0,
                inlier_ratio=1,
                median_reprojection_error=0,
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
