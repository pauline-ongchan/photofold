from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from photofold.config import REPOSITORY_ROOT
from photofold.gate1.alignment import AlignmentFailure
from photofold.phase1b.benchmark import Phase1BBenchmarkError, run_phase1b_dataset


def _write_feature_dataset(root: Path) -> Path:
    dataset = root / "static-handheld"
    dataset.mkdir(parents=True)
    generator = np.random.default_rng(20260719)
    base = generator.integers(0, 256, (192, 256, 3), dtype=np.uint8)
    files = []
    for index in range(5):
        image = np.roll(base, shift=(index, index * 2), axis=(0, 1))
        path = dataset / f"frame-{index:03d}.png"
        Image.fromarray(image, mode="RGB").save(path)
        files.append(
            {
                "path": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    manifest = {
        "schema_version": "1.0",
        "id": "static-handheld",
        "title": "Synthetic benchmark fixture",
        "scenario_category": "static-handheld",
        "provenance": {
            "source": "test fixture",
            "capture_date": "2026-07-19",
            "device": "fixture",
            "authorization": "test fixture",
        },
        "consent": {
            "basis": "test fixture",
            "identifiable_people_visible": False,
            "notes": "No people.",
        },
        "license": {
            "id": "test-only",
            "redistribution_permitted": False,
            "notes": "Test fixture.",
        },
        "capture_notes": ["Synthetic translated texture."],
        "known_limitations": ["Not scientific evidence."],
        "expected_frame_count": 5,
        "expected_dimensions": {"width": 256, "height": 192},
        "files": files,
    }
    (dataset / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return dataset


def test_dataset_runner_uses_closed_package_and_real_accounting(tmp_path: Path) -> None:
    dataset = _write_feature_dataset(tmp_path / "data")
    output = tmp_path / "artifacts"

    result = run_phase1b_dataset(
        dataset,
        REPOSITORY_ROOT / "configs/gate1.yaml",
        output,
        matched_qualities=[1, 100],
        require_full_curve=False,
    )

    assert result["status"] == "pass"
    assert result["machine_pass"] is True
    assert result["accepted_frame_count"] == 5
    assert result["reconstructed_frame_count"] == 5
    assert result["fixed_webp"]["quality"] == 70
    assert [point["quality"] for point in result["matched_webp"]["curve"]] == [1, 100]
    assert result["photofold_package_bytes"] == (output / "moment.photofold").stat().st_size
    assert result["package_overhead"]["reconciles"] is True
    assert result["source_before"] == result["source_after"]
    assert len(result["package_members"]) > 2
    assert all(
        (output / frame["artifacts"]["reconstruction"]).is_file()
        for frame in result["per_frame"]
    )


def test_alignment_failure_is_visible_and_stops_before_encoding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dataset = _write_feature_dataset(tmp_path / "data")
    output = tmp_path / "artifacts"

    def fail_alignment(_images: list[np.ndarray]) -> dict[str, object]:
        raise AlignmentFailure("fixture alignment failure", [2])

    monkeypatch.setattr(
        "photofold.phase1b.benchmark.select_reference_and_align",
        fail_alignment,
    )

    with pytest.raises(Phase1BBenchmarkError, match="fixture alignment failure"):
        run_phase1b_dataset(
            dataset,
            REPOSITORY_ROOT / "configs/gate1.yaml",
            output,
            matched_qualities=[1],
            require_full_curve=False,
        )

    failure = json.loads((output / "benchmark.json").read_text(encoding="utf-8"))
    assert failure["status"] == "fail"
    assert failure["stage"] == "alignment"
    assert failure["failed_frame_indices"] == [2]
    assert failure["frame_dispositions"][2]["disposition"] == "rejected"
    assert not (output / "moment.photofold").exists()
