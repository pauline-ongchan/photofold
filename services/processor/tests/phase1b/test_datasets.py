from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image
from pydantic import ValidationError

from photofold.config import REPOSITORY_ROOT
from photofold.phase1b.datasets import (
    PHASE1B_DATASET_IDS,
    Phase1BDatasetError,
    prepare_phase1b_datasets,
    source_snapshot,
    source_snapshot_matches,
    validate_phase1b_collection,
    validate_phase1b_dataset,
)
from photofold.phase1b.models import ManifestFile


def _write_dataset(root: Path, dataset_id: str = "static-handheld") -> Path:
    dataset = root / dataset_id
    dataset.mkdir(parents=True)
    files = []
    for index in range(5):
        path = dataset / f"frame-{index:03d}.png"
        Image.new("RGB", (8, 6), color=(index, 20, 40)).save(path)
        files.append(
            {
                "path": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    manifest = {
        "schema_version": "1.0",
        "id": dataset_id,
        "title": "Test burst",
        "scenario_category": dataset_id,
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
        "capture_notes": ["Synthetic validator fixture."],
        "known_limitations": ["Not benchmark evidence."],
        "expected_frame_count": 5,
        "expected_dimensions": {"width": 8, "height": 6},
        "files": files,
    }
    (dataset / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return dataset


def test_real_phase1b_collection_is_canonical_and_checksum_valid() -> None:
    result = validate_phase1b_collection(REPOSITORY_ROOT / "data/real-bursts")

    assert result["status"] == "pass"
    assert result["dataset_order"] == list(PHASE1B_DATASET_IDS)
    assert [item["frame_count"] for item in result["datasets"]] == [15, 13, 14]
    assert [item["total_bytes"] for item in result["datasets"]] == [
        46_659_071,
        25_331_644,
        26_301_637,
    ]
    assert [item["normalized_dimensions"] for item in result["datasets"]] == [
        {"width": 3024, "height": 4032},
        {"width": 3024, "height": 4032},
        {"width": 4284, "height": 5712},
    ]
    assert all(
        frame["disposition"] == "accepted"
        for dataset in result["datasets"]
        for frame in dataset["frames"]
    )


def test_validator_rejects_undeclared_supported_image(tmp_path: Path) -> None:
    dataset = _write_dataset(tmp_path)
    Image.new("RGB", (8, 6)).save(dataset / "undeclared.webp")

    result = validate_phase1b_dataset(dataset)

    assert result["status"] == "fail"
    assert "Undeclared supported image files" in result["errors"][0]


def test_validator_detects_source_mutation(tmp_path: Path) -> None:
    dataset = _write_dataset(tmp_path)
    before = validate_phase1b_dataset(dataset)
    snapshot = source_snapshot(before)
    (dataset / "frame-004.png").write_bytes(b"changed")

    after = validate_phase1b_dataset(dataset)

    assert after["status"] == "fail"
    assert source_snapshot_matches(after, snapshot) is False


def test_manifest_file_rejects_traversal() -> None:
    with pytest.raises(ValidationError, match="Unsafe dataset path"):
        ManifestFile(path="../outside.jpg", sha256="0" * 64)


def test_preparation_refuses_differing_destination(tmp_path: Path) -> None:
    destination = tmp_path / "destination"
    source = tmp_path / "source"
    for dataset_id in PHASE1B_DATASET_IDS:
        destination_dataset = _write_dataset(destination, dataset_id)
        source_dataset = source / dataset_id
        source_dataset.mkdir(parents=True)
        manifest = json.loads(
            (destination_dataset / "manifest.json").read_text(encoding="utf-8")
        )
        for item in manifest["files"]:
            source_file = source_dataset / item["path"]
            source_file.write_bytes((destination_dataset / item["path"]).read_bytes())
    (destination / "static-handheld/frame-000.png").write_bytes(b"different")

    with pytest.raises(Phase1BDatasetError, match="Refusing to overwrite"):
        prepare_phase1b_datasets(source, destination)
