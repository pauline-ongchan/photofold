import json
import shutil
import zipfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from photofold.config import REPOSITORY_ROOT
from photofold.gate1.bundle import (
    PackageValidationError,
    decode_all_package_frames,
    verify_package,
)
from photofold.prototype.runner import (
    PrototypeRunError,
    analyze_prototype_run,
    evaluated_status,
    fold_prototype_run,
)


def _write_input(run: Path, names: list[str]) -> None:
    run.mkdir(parents=True, exist_ok=True)
    (run / "uploads").mkdir()
    payload = {
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
    (run / "input.json").write_text(json.dumps(payload), encoding="utf-8")


def _prepare_demo(tmp_path: Path) -> Path:
    dataset = REPOSITORY_ROOT / "data/demo/hdrplus-static"
    manifest = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))
    names = [item["path"] for item in manifest["files"]]
    run = tmp_path / "artifacts/gate3/runs/00000000-0000-4000-8000-000000000001"
    _write_input(run, names)
    for index, name in enumerate(names):
        shutil.copy2(dataset / name, run / "uploads" / f"frame-{index:03d}.upload")
    return run


def _prepare_generated(tmp_path: Path, images: list[np.ndarray]) -> Path:
    run = tmp_path / "artifacts/gate3/runs/00000000-0000-4000-8000-000000000001"
    names = [f"frame-{index}.png" for index in range(len(images))]
    _write_input(run, names)
    for index, pixels in enumerate(images):
        Image.fromarray(pixels, mode="RGB").save(
            run / "uploads" / f"frame-{index:03d}.upload", format="PNG"
        )
    return run


def _textured_scene(width: int = 256, height: int = 192) -> np.ndarray:
    return np.random.default_rng(42).integers(0, 256, (height, width, 3), dtype=np.uint8)


def test_analyze_and_fold_reuse_real_alignment_and_write_package_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _prepare_demo(tmp_path)
    config = REPOSITORY_ROOT / "configs/gate1.yaml"

    analysis = analyze_prototype_run(run, config)
    assert analysis.status == "analyzed_foldable"
    assert analysis.strategy == "shared_scene"
    assert analysis.shared_frame_count == 7
    assert analysis.fallback_frame_count == 0
    assert analysis.alignment_measurement.units == "analysis_pixels"
    assert analysis.original_total_bytes == sum(frame.bytes for frame in analysis.source_frames)
    assert len(analysis.alignment) == 7

    def fail_if_alignment_repeats(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("fold repeated reference selection")

    monkeypatch.setattr(
        "photofold.prototype.runner.select_shared_scene_group", fail_if_alignment_repeats
    )
    result = fold_prototype_run(run, config)

    assert result.status == "complete"
    assert result.strategy == "shared_scene"
    assert result.reconstructed_frame_count == 7
    assert result.storage is not None
    assert result.storage.package_total_bytes == (run / "moment.photofold").stat().st_size
    assert result.quality is not None and result.quality.threshold_pass is True
    assert all(frame.reconstructed and frame.ssim is not None for frame in result.frames)
    assert all((run / frame.artifacts.reconstruction).is_file() for frame in result.frames)
    assert all((run / frame.artifacts.difference).is_file() for frame in result.frames)
    assert (run.parents[1] / "latest/result.json").is_file()
    assert (run.parents[1] / "latest/moment.photofold").is_file()
    with zipfile.ZipFile(run / "moment.photofold") as archive:
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["reference_frame_index"] == analysis.reference_frame_index
    assert manifest["version"] == "0.2"
    assert manifest["strategy"] == "shared_scene"
    assert [
        frame["transform"]["reference_to_target"] for frame in manifest["frames"]
    ] == [item.reference_to_target for item in analysis.alignment]


def test_mixed_normalized_dimensions_use_independent_fallback(tmp_path: Path) -> None:
    scene = _textured_scene()
    images = [scene.copy() for _ in range(4)]
    images.append(_textured_scene(width=288))
    run = _prepare_generated(tmp_path, images)

    analysis = analyze_prototype_run(run, REPOSITORY_ROOT / "configs/gate1.yaml")
    result = fold_prototype_run(run, REPOSITORY_ROOT / "configs/gate1.yaml")

    assert analysis.strategy == "hybrid"
    assert analysis.normalized_dimensions is None
    assert analysis.frame_dispositions[4].storage_mode == "independent_source"
    assert "dimensions differ" in analysis.frame_dispositions[4].fallback_reason.lower()
    assert result.strategy == "hybrid"
    assert [(frame.width, frame.height) for frame in result.frames] == [
        (256, 192),
        (256, 192),
        (256, 192),
        (256, 192),
        (288, 192),
    ]
    decoded = decode_all_package_frames(run / "moment.photofold")
    assert np.array_equal(decoded[4], images[4])


def test_analyze_rejects_invalid_file_count(tmp_path: Path) -> None:
    run = tmp_path / "run"
    _write_input(run, [f"frame-{index}.png" for index in range(4)])

    with pytest.raises(PrototypeRunError) as raised:
        analyze_prototype_run(run, REPOSITORY_ROOT / "configs/gate1.yaml")

    assert raised.value.detail.code == "INVALID_FILE_COUNT"


def test_fold_rejects_a_source_changed_after_analysis(tmp_path: Path) -> None:
    run = _prepare_demo(tmp_path)
    config = REPOSITORY_ROOT / "configs/gate1.yaml"
    analyze_prototype_run(run, config)
    with (run / "uploads/frame-000.upload").open("ab") as handle:
        handle.write(b"changed-after-analysis")

    with pytest.raises(PrototypeRunError) as raised:
        fold_prototype_run(run, config)

    assert raised.value.detail.code == "CHECKSUM_MISMATCH"


def test_failed_alignment_frame_becomes_exact_independent_fallback(tmp_path: Path) -> None:
    scene = _textured_scene()
    unrelated = np.zeros_like(scene)
    images = [scene.copy(), scene.copy(), unrelated, scene.copy(), scene.copy()]
    run = _prepare_generated(tmp_path, images)

    analysis = analyze_prototype_run(run, REPOSITORY_ROOT / "configs/gate1.yaml")
    result = fold_prototype_run(run, REPOSITORY_ROOT / "configs/gate1.yaml")
    verification = verify_package(run / "moment.photofold")
    decoded = decode_all_package_frames(run / "moment.photofold")

    assert analysis.strategy == "hybrid"
    assert analysis.shared_frame_count == 4
    assert analysis.fallback_frame_count == 1
    assert [item.storage_mode for item in analysis.frame_dispositions] == [
        "shared_reference",
        "shared_delta",
        "independent_source",
        "shared_delta",
        "shared_delta",
    ]
    assert result.strategy == "hybrid"
    assert result.frames[2].storage_mode == "independent_source"
    assert result.frames[2].ssim == pytest.approx(1.0)
    assert np.array_equal(decoded[2], unrelated)
    assert verification["strategy"] == "hybrid"
    assert verification["fallback_frame_count"] == 1


def test_every_frame_can_use_independent_storage_in_source_order(tmp_path: Path) -> None:
    images = [
        np.full((96 + index, 128 + index, 3), index * 40, dtype=np.uint8)
        for index in range(5)
    ]
    run = _prepare_generated(tmp_path, images)

    analysis = analyze_prototype_run(run, REPOSITORY_ROOT / "configs/gate1.yaml")
    result = fold_prototype_run(run, REPOSITORY_ROOT / "configs/gate1.yaml")
    decoded = decode_all_package_frames(run / "moment.photofold")
    verification = verify_package(run / "moment.photofold")

    assert analysis.strategy == "independent_only"
    assert analysis.reference_frame_index is None
    assert analysis.shared_frame_count == 0
    assert analysis.fallback_frame_count == 5
    assert result.status == "complete_no_savings"
    assert result.strategy == "independent_only"
    assert [frame.original_filename for frame in result.frames] == [
        f"frame-{index}.png" for index in range(5)
    ]
    assert all(frame.storage_mode == "independent_source" for frame in result.frames)
    assert all(frame.ssim == pytest.approx(1.0) for frame in result.frames)
    assert all(
        np.array_equal(actual, expected)
        for actual, expected in zip(decoded, images, strict=True)
    )
    assert verification["strategy"] == "independent_only"
    assert verification["reference_frame_index"] is None

    corrupted = run / "corrupted.photofold"
    with zipfile.ZipFile(run / "moment.photofold") as source:
        members = {name: source.read(name) for name in source.namelist()}
    members["metadata/metrics.json"] += b" "
    with zipfile.ZipFile(corrupted, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    with pytest.raises(PackageValidationError, match="integrity check failed"):
        verify_package(corrupted)


@pytest.mark.parametrize(
    ("quality_pass", "is_smaller", "expected"),
    [
        (True, True, "complete"),
        (True, False, "complete_no_savings"),
        (False, True, "failed_quality"),
        (False, False, "failed_quality"),
    ],
)
def test_evaluated_terminal_statuses(
    quality_pass: bool, is_smaller: bool, expected: str
) -> None:
    assert evaluated_status(quality_pass=quality_pass, is_smaller=is_smaller) == expected
