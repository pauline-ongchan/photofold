import json
import shutil
import zipfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from photofold.config import REPOSITORY_ROOT
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


def test_analyze_and_fold_reuse_real_alignment_and_write_package_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _prepare_demo(tmp_path)
    config = REPOSITORY_ROOT / "configs/gate1.yaml"

    analysis = analyze_prototype_run(run, config)
    assert analysis.status == "analyzed_foldable"
    assert analysis.original_total_bytes == sum(frame.bytes for frame in analysis.source_frames)
    assert len(analysis.alignment) == 7

    def fail_if_alignment_repeats(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("fold repeated reference selection")

    monkeypatch.setattr(
        "photofold.prototype.runner.select_reference_and_align", fail_if_alignment_repeats
    )
    result = fold_prototype_run(run, config)

    assert result.status == "complete"
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
    assert [
        frame["transform"]["reference_to_target"] for frame in manifest["frames"]
    ] == [item.reference_to_target for item in analysis.alignment]


def test_analyze_rejects_a_source_with_different_normalized_dimensions(tmp_path: Path) -> None:
    run = tmp_path / "run"
    _write_input(run, [f"frame-{index}.png" for index in range(5)])
    for index in range(5):
        size = (16, 12) if index < 4 else (18, 12)
        pixels = np.full((size[1], size[0], 3), index * 20, dtype=np.uint8)
        Image.fromarray(pixels, mode="RGB").save(
            run / "uploads" / f"frame-{index:03d}.upload", format="PNG"
        )

    with pytest.raises(PrototypeRunError) as raised:
        analyze_prototype_run(run, REPOSITORY_ROOT / "configs/gate1.yaml")

    assert raised.value.detail.code == "DIMENSIONS_INCOMPATIBLE"
    assert raised.value.detail.frame_indices == [4]


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
