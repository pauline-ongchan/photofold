from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from photofold.config import REPOSITORY_ROOT
from photofold.phase1b.datasets import PHASE1B_DATASET_IDS
from photofold.phase1b.experiment import (
    Phase1BReviewError,
    finalize_human_review,
    run_phase1b_experiment,
)
from photofold.phase1b.report import _contains_placeholder, verify_phase1b_report


def _write_collection(root: Path) -> Path:
    generator = np.random.default_rng(20260719)
    for dataset_offset, dataset_id in enumerate(PHASE1B_DATASET_IDS):
        dataset = root / dataset_id
        dataset.mkdir(parents=True)
        base = generator.integers(0, 256, (192, 256, 3), dtype=np.uint8)
        files = []
        for index in range(5):
            image = np.roll(
                base,
                shift=(index + dataset_offset, index * 2),
                axis=(0, 1),
            )
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
            "id": dataset_id,
            "title": f"Synthetic {dataset_id} fixture",
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
            "capture_notes": ["Synthetic translated texture."],
            "known_limitations": ["Not scientific evidence."],
            "expected_frame_count": 5,
            "expected_dimensions": {"width": 256, "height": 192},
            "files": files,
        }
        (dataset / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def _complete_review(template_path: Path, output: Path) -> Path:
    review = json.loads(template_path.read_text(encoding="utf-8"))
    review["reviewer"] = "Fixture reviewer"
    review["reviewed_at"] = datetime.now(UTC).isoformat()
    review["complexity_notes"] = "Fixture timings were reviewed; no complexity veto."
    for dataset_id in PHASE1B_DATASET_IDS:
        review["datasets"][dataset_id]["status"] = "pass"
        review["datasets"][dataset_id]["notes"] = (
            "Original, reconstruction, heatmap, mask, and overlay inspected."
        )
    output.write_text(json.dumps(review), encoding="utf-8")
    return output


def test_collection_report_and_evidence_bound_review(tmp_path: Path) -> None:
    datasets = _write_collection(tmp_path / "data")
    artifacts = tmp_path / "artifacts"

    experiment = run_phase1b_experiment(
        datasets,
        REPOSITORY_ROOT / "configs/gate1.yaml",
        artifacts,
        matched_qualities=[1, 100],
        require_full_curve=False,
    )

    assert experiment["status"] == "pass"
    assert experiment["human_review_status"] == "pending"
    assert experiment["recommendation_before_human_review"] == "PIVOT"
    assert experiment["report_verification"]["status"] == "pass"
    assert experiment["report_verification"]["embedded_image_count"] == 75

    review_path = _complete_review(
        artifacts / "human-review-template.json",
        artifacts / "human-review.json",
    )
    finalized = finalize_human_review(artifacts, review_path)

    assert finalized["status"] == "pass"
    assert finalized["phase_pass"] is True
    assert finalized["report_verification"]["status"] == "pass"
    assert verify_phase1b_report(artifacts / "report.html")["status"] == "pass"


def test_report_verifier_rejects_external_image_and_stale_review(tmp_path: Path) -> None:
    datasets = _write_collection(tmp_path / "data")
    artifacts = tmp_path / "artifacts"
    run_phase1b_experiment(
        datasets,
        REPOSITORY_ROOT / "configs/gate1.yaml",
        artifacts,
        matched_qualities=[1, 100],
        require_full_curve=False,
    )
    report_path = artifacts / "report.html"
    report_path.write_text(
        report_path.read_text(encoding="utf-8") + '<img src="https://example.invalid/x.png">',
        encoding="utf-8",
    )

    verification = verify_phase1b_report(report_path)

    assert verification["status"] == "fail"
    assert any("external dependency" in error for error in verification["errors"])

    review_path = _complete_review(
        artifacts / "human-review-template.json",
        artifacts / "human-review.json",
    )
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["review_basis_sha256"] = "0" * 64
    review_path.write_text(json.dumps(review), encoding="utf-8")
    with pytest.raises(Phase1BReviewError, match="stale"):
        finalize_human_review(artifacts, review_path)


def test_placeholder_scan_ignores_embedded_base64_payloads() -> None:
    assert _contains_placeholder(
        '<img src="data:image/webp;base64,QUJDVEJERUY=">'
    ) is False
    assert _contains_placeholder("<p>TODO</p>") is True
