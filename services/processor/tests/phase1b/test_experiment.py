from __future__ import annotations

import hashlib
import json
import shutil
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
    report = (artifacts / "report.html").read_text(encoding="utf-8")
    assert "Ordered decision criteria" in report
    assert "Original, reconstruction, heatmap, mask, and overlay inspected." in report
    assert "lowest-SSIM frame inspected" in report
    assert "Alignment evidence" in report


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


def test_collection_failure_stops_before_any_encoding(tmp_path: Path) -> None:
    datasets = _write_collection(tmp_path / "data")
    manifest_path = datasets / "moving-subject/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["id"] = "static-handheld"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    artifacts = tmp_path / "artifacts"

    experiment = run_phase1b_experiment(
        datasets,
        REPOSITORY_ROOT / "configs/gate1.yaml",
        artifacts,
        matched_qualities=[1, 100],
        require_full_curve=False,
    )

    assert experiment["status"] == "fail"
    assert experiment["automated_pass"] is False
    assert any("unique" in error.lower() for error in experiment["errors"])
    assert not any(artifacts.glob("*/moment.photofold"))
    assert experiment["report_verification"]["status"] == "pass"


def test_report_verifier_recomputes_content_totals_and_package_listing(
    tmp_path: Path,
) -> None:
    datasets = _write_collection(tmp_path / "data")
    base_artifacts = tmp_path / "base-artifacts"
    run_phase1b_experiment(
        datasets,
        REPOSITORY_ROOT / "configs/gate1.yaml",
        base_artifacts,
        matched_qualities=[1, 100],
        require_full_curve=False,
    )

    missing_section = tmp_path / "missing-section"
    shutil.copytree(base_artifacts, missing_section)
    report_path = missing_section / "report.html"
    report_path.write_text(
        report_path.read_text(encoding="utf-8").replace(
            'id="dataset-static-handheld"',
            'id="removed-static-handheld"',
            1,
        ),
        encoding="utf-8",
    )
    missing_result = verify_phase1b_report(report_path)
    assert any("missing dataset section" in error for error in missing_result["errors"])

    broken_image = tmp_path / "broken-image"
    shutil.copytree(base_artifacts, broken_image)
    report_path = broken_image / "report.html"
    report_path.write_text(
        report_path.read_text(encoding="utf-8").replace(
            "data:image/webp;base64,",
            "data:image/webp;base64,!!!!",
            1,
        ),
        encoding="utf-8",
    )
    broken_result = verify_phase1b_report(report_path)
    assert any("cannot be decoded" in error for error in broken_result["errors"])

    missing_image = tmp_path / "missing-image"
    shutil.copytree(base_artifacts, missing_image)
    report_path = missing_image / "report.html"
    report = report_path.read_text(encoding="utf-8")
    image_start = report.index("<img ")
    image_end = report.index(">", image_start) + 1
    report_path.write_text(report[:image_start] + report[image_end:], encoding="utf-8")
    missing_image_result = verify_phase1b_report(report_path)
    assert any(
        "embedded images" in error for error in missing_image_result["errors"]
    )

    inconsistent_storage = tmp_path / "inconsistent-storage"
    shutil.copytree(base_artifacts, inconsistent_storage)
    benchmark_path = inconsistent_storage / "static-handheld/benchmark.json"
    benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
    benchmark["storage"]["versus_originals"]["signed_bytes_saved"] += 1
    benchmark_path.write_text(json.dumps(benchmark), encoding="utf-8")
    storage_result = verify_phase1b_report(inconsistent_storage / "report.html")
    assert any("storage comparison" in error for error in storage_result["errors"])

    inconsistent_total = tmp_path / "inconsistent-total"
    shutil.copytree(base_artifacts, inconsistent_total)
    aggregate_path = inconsistent_total / "aggregate.json"
    aggregate = json.loads(aggregate_path.read_text(encoding="utf-8"))
    aggregate["aggregate_original_bytes"] += 1
    aggregate_path.write_text(json.dumps(aggregate), encoding="utf-8")
    total_result = verify_phase1b_report(inconsistent_total / "report.html")
    assert any("aggregate field" in error for error in total_result["errors"])

    absent_member = tmp_path / "absent-member"
    shutil.copytree(base_artifacts, absent_member)
    benchmark_path = absent_member / "static-handheld/benchmark.json"
    benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
    benchmark["package_members"].pop()
    benchmark_path.write_text(json.dumps(benchmark), encoding="utf-8")
    member_result = verify_phase1b_report(absent_member / "report.html")
    assert any("package listing" in error for error in member_result["errors"])

    wrong_recommendation = tmp_path / "wrong-recommendation"
    shutil.copytree(base_artifacts, wrong_recommendation)
    report_path = wrong_recommendation / "report.html"
    report_path.write_text(
        report_path.read_text(encoding="utf-8").replace(
            'data-recommendation="PIVOT"',
            'data-recommendation="INVESTIGATE"',
            1,
        ),
        encoding="utf-8",
    )
    recommendation_result = verify_phase1b_report(report_path)
    assert any(
        "displayed recommendation" in error
        for error in recommendation_result["errors"]
    )


def test_placeholder_scan_ignores_embedded_base64_payloads() -> None:
    assert _contains_placeholder(
        '<img src="data:image/webp;base64,QUJDVEJERUY=">'
    ) is False
    assert _contains_placeholder("<p>TODO</p>") is True
    assert _contains_placeholder("<p>REPLACE_WITH reviewer</p>") is True
