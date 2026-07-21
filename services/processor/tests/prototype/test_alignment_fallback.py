import json
import shutil
from pathlib import Path

import cv2
import numpy as np

from photofold.config import REPOSITORY_ROOT
from photofold.gate1.alignment import select_shared_scene_group
from photofold.prototype.runner import analyze_prototype_run


def _translated_scene(width: int, height: int, offsets: list[int]) -> list[np.ndarray]:
    scene = np.random.default_rng(84).integers(0, 256, (height, width, 3), dtype=np.uint8)
    return [
        cv2.warpAffine(
            scene,
            np.asarray([[1, 0, offset], [0, 1, offset / 2]], dtype=np.float32),
            (width, height),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REFLECT,
        )
        for offset in offsets
    ]


def test_alignment_decisions_are_invariant_across_source_resolutions() -> None:
    standard = _translated_scene(1600, 1200, [-8, -4, 0, 4, 8])
    high_resolution = [
        cv2.resize(image, (3200, 2400), interpolation=cv2.INTER_CUBIC) for image in standard
    ]

    standard_result = select_shared_scene_group(
        standard,
        min_inlier_ratio=0.8,
        max_median_reprojection_error=2.0,
    )
    high_result = select_shared_scene_group(
        high_resolution,
        min_inlier_ratio=0.8,
        max_median_reprojection_error=2.0,
    )

    assert standard_result["strategy"] == high_result["strategy"] == "shared_scene"
    assert [item["storage_mode"] for item in standard_result["dispositions"]] == [
        item["storage_mode"] for item in high_result["dispositions"]
    ]
    assert standard_result["alignment_error_units"] == "analysis_pixels"
    assert high_result["alignment_error_units"] == "analysis_pixels"
    standard_errors = sorted(
        transform["median_reprojection_error"]
        for transform in standard_result["transforms"]
        if transform is not None and transform["type"] != "identity"
    )
    high_errors = sorted(
        transform["median_reprojection_error"]
        for transform in high_result["transforms"]
        if transform is not None and transform["type"] != "identity"
    )
    assert np.allclose(standard_errors, high_errors, atol=0.35)


def test_static_handheld_3024_by_4032_alignment_regression(tmp_path: Path) -> None:
    dataset = REPOSITORY_ROOT / "data/real-bursts/static-handheld"
    manifest = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))
    names = [item["path"] for item in manifest["files"]]
    run = tmp_path / "artifacts/gate3/runs/00000000-0000-4000-8000-000000000001"
    uploads = run / "uploads"
    uploads.mkdir(parents=True)
    (run / "input.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "frames": [
                    {
                        "index": index,
                        "original_filename": name,
                        "stored_filename": f"frame-{index:03d}.upload",
                    }
                    for index, name in enumerate(names)
                ],
            }
        ),
        encoding="utf-8",
    )
    for index, name in enumerate(names):
        shutil.copy2(dataset / name, uploads / f"frame-{index:03d}.upload")

    analysis = analyze_prototype_run(run, REPOSITORY_ROOT / "configs/gate1.yaml")

    assert analysis.strategy == "hybrid"
    assert analysis.shared_frame_count == 13
    assert analysis.fallback_frame_count == 2
    assert analysis.normalized_dimensions is not None
    assert (
        analysis.normalized_dimensions.width,
        analysis.normalized_dimensions.height,
    ) == (3024, 4032)
    assert analysis.alignment_measurement.units == "analysis_pixels"
    measured = [
        item.median_reprojection_error
        for item in analysis.alignment
        if item.type != "identity"
    ]
    assert measured
    assert max(error for error in measured if error is not None) <= 2.0
    assert all(
        item.median_reprojection_error is None
        or item.median_reprojection_error <= 2.0
        for item in analysis.alignment
    )
