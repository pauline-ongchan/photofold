"""Collection orchestration and evidence-bound human review for Phase 1B."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from photofold.phase1b.aggregate import build_aggregate
from photofold.phase1b.baseline import MATCHED_QUALITIES
from photofold.phase1b.benchmark import Phase1BBenchmarkError, run_phase1b_dataset
from photofold.phase1b.datasets import PHASE1B_DATASET_IDS, validate_phase1b_collection
from photofold.phase1b.models import HumanReview, Phase1BDatasetResult
from photofold.phase1b.report import (
    generate_phase1b_report,
    review_basis_sha256,
    verify_phase1b_report,
)


class Phase1BReviewError(ValueError):
    """Raised when human-review evidence is invalid or stale."""


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load_results(root: Path) -> dict[str, dict[str, Any]]:
    return {
        dataset_id: json.loads(
            (root / dataset_id / "benchmark.json").read_text(encoding="utf-8")
        )
        for dataset_id in PHASE1B_DATASET_IDS
    }


def _lowest_frame_indices(result: dict[str, Any]) -> tuple[int, int]:
    frames = result["per_frame"]
    lowest_ssim = min(frames, key=lambda frame: (float(frame["ssim"]), frame["index"]))

    def psnr_value(frame: dict[str, Any]) -> float:
        value = frame["psnr_db"]
        return float("inf") if value["is_infinite"] else float(value["value_db"])

    lowest_psnr = min(frames, key=lambda frame: (psnr_value(frame), frame["index"]))
    return int(lowest_ssim["index"]), int(lowest_psnr["index"])


def write_human_review_template(
    artifact_root: Path,
    results: dict[str, dict[str, Any]],
) -> Path:
    basis = review_basis_sha256(results, artifact_root)
    datasets: dict[str, Any] = {}
    for dataset_id in PHASE1B_DATASET_IDS:
        result = results[dataset_id]
        if result.get("status") == "pass":
            lowest_ssim, lowest_psnr = _lowest_frame_indices(result)
        else:
            lowest_ssim = lowest_psnr = 0
        datasets[dataset_id] = {
            "status": "REPLACE_WITH_pass_OR_fail",
            "notes": "REPLACE_WITH_visual_inspection_notes",
            "lowest_ssim_frame_inspected": lowest_ssim,
            "lowest_psnr_frame_inspected": lowest_psnr,
        }
    template = {
        "schema_version": "1.0",
        "review_basis_sha256": basis,
        "reviewer": "REPLACE_WITH_reviewer_name",
        "reviewed_at": "REPLACE_WITH_ISO_8601_timestamp",
        "datasets": datasets,
        "complexity_disproportionate": False,
        "complexity_notes": "REPLACE_WITH_complexity_assessment_and_timing_evidence",
    }
    path = artifact_root / "human-review-template.json"
    _write_json(path, template)
    return path


def _write_aggregate_and_report(
    artifact_root: Path,
    results: dict[str, dict[str, Any]],
    human_review: HumanReview | None,
) -> dict[str, Any]:
    aggregate = build_aggregate(results, human_review)
    _write_json(artifact_root / "aggregate.json", aggregate.model_dump(mode="json"))
    generated = generate_phase1b_report(artifact_root, results, aggregate)
    verification = verify_phase1b_report(artifact_root / "report.html")
    _write_json(artifact_root / "report-verification.json", verification)
    return {
        "aggregate": aggregate.model_dump(mode="json"),
        "report": generated,
        "report_verification": verification,
    }


def run_phase1b_experiment(
    dataset_root: str | Path,
    config_path: str | Path,
    artifact_root: str | Path,
    *,
    matched_qualities: tuple[int, ...] | list[int] = MATCHED_QUALITIES,
    require_full_curve: bool = True,
) -> dict[str, Any]:
    datasets = Path(dataset_root).expanduser().resolve()
    artifacts = Path(artifact_root).expanduser().resolve()
    artifacts.mkdir(parents=True, exist_ok=True)
    collection_validation = validate_phase1b_collection(datasets)
    _write_json(artifacts / "dataset-collection-validation.json", collection_validation)
    if collection_validation["status"] != "pass":
        results = {}
        errors = list(collection_validation["errors"])
        for dataset_id, validation in zip(
            PHASE1B_DATASET_IDS,
            collection_validation["datasets"],
            strict=True,
        ):
            dataset_errors = list(validation.get("errors", []))
            errors.extend(f"{dataset_id}: {error}" for error in dataset_errors)
            result = {
                "schema_version": "1.0",
                "status": "fail",
                "dataset_id": dataset_id,
                "stage": "collection_validation",
                "error": "strict Phase 1B collection validation failed",
                "validation": validation,
                "frame_dispositions": validation.get("frames", []),
            }
            results[dataset_id] = result
            output = artifacts / dataset_id
            output.mkdir(parents=True, exist_ok=True)
            _write_json(output / "benchmark.json", result)

        template_path = write_human_review_template(artifacts, results)
        evidence = _write_aggregate_and_report(artifacts, results, None)
        return {
            "status": "fail",
            "automated_pass": False,
            "dataset_order": list(PHASE1B_DATASET_IDS),
            "datasets": {
                dataset_id: {
                    "status": "fail",
                    "machine_pass": False,
                    "accepted_frame_count": 0,
                    "reconstructed_frame_count": 0,
                }
                for dataset_id in PHASE1B_DATASET_IDS
            },
            "recommendation_before_human_review": evidence["aggregate"][
                "recommendation"
            ],
            "human_review_status": "pending",
            "human_review_template": str(template_path),
            "report": evidence["report"],
            "report_verification": evidence["report_verification"],
            "errors": errors or ["strict Phase 1B collection validation failed"],
        }
    results: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for dataset_id in PHASE1B_DATASET_IDS:
        try:
            result = run_phase1b_dataset(
                datasets / dataset_id,
                config_path,
                artifacts / dataset_id,
                matched_qualities=matched_qualities,
                require_full_curve=require_full_curve,
            )
        except Phase1BBenchmarkError as error:
            errors.append(f"{dataset_id}: {error}")
            result = json.loads(
                (artifacts / dataset_id / "benchmark.json").read_text(encoding="utf-8")
            )
        results[dataset_id] = result

    template_path = write_human_review_template(artifacts, results)
    evidence = _write_aggregate_and_report(artifacts, results, None)
    aggregate = evidence["aggregate"]
    automated_pass = (
        collection_validation["status"] == "pass"
        and not errors
        and all(result.get("machine_pass", False) for result in results.values())
        and aggregate["relational_evidence_complete"]
        and evidence["report_verification"]["status"] == "pass"
    )
    return {
        "status": "pass" if automated_pass else "fail",
        "automated_pass": automated_pass,
        "dataset_order": list(PHASE1B_DATASET_IDS),
        "datasets": {
            dataset_id: {
                "status": result.get("status", "fail"),
                "machine_pass": result.get("machine_pass", False),
                "accepted_frame_count": result.get("accepted_frame_count", 0),
                "reconstructed_frame_count": result.get("reconstructed_frame_count", 0),
            }
            for dataset_id, result in results.items()
        },
        "recommendation_before_human_review": aggregate["recommendation"],
        "human_review_status": "pending",
        "human_review_template": str(template_path),
        "report": evidence["report"],
        "report_verification": evidence["report_verification"],
        "errors": errors,
    }


def finalize_human_review(
    artifact_root: str | Path,
    review_path: str | Path,
) -> dict[str, Any]:
    artifacts = Path(artifact_root).expanduser().resolve()
    review_file = Path(review_path).expanduser().resolve()
    results = _load_results(artifacts)
    try:
        review = HumanReview.model_validate_json(review_file.read_bytes())
    except (FileNotFoundError, ValidationError) as error:
        raise Phase1BReviewError(f"Invalid human-review file: {error}") from error
    expected_basis = review_basis_sha256(results, artifacts)
    if review.review_basis_sha256 != expected_basis:
        raise Phase1BReviewError(
            "Human review is stale: review_basis_sha256 does not match current evidence"
        )
    if set(review.datasets) != set(PHASE1B_DATASET_IDS):
        raise Phase1BReviewError("Human review must cover exactly the three canonical datasets")
    for dataset_id in PHASE1B_DATASET_IDS:
        result = results[dataset_id]
        if result.get("status") != "pass":
            continue
        expected_ssim, expected_psnr = _lowest_frame_indices(result)
        dataset_review = review.datasets[dataset_id]
        if dataset_review.lowest_ssim_frame_inspected != expected_ssim:
            raise Phase1BReviewError(
                f"{dataset_id} review did not identify lowest-SSIM frame {expected_ssim}"
            )
        if dataset_review.lowest_psnr_frame_inspected != expected_psnr:
            raise Phase1BReviewError(
                f"{dataset_id} review did not identify lowest-PSNR frame {expected_psnr}"
            )

    for dataset_id in PHASE1B_DATASET_IDS:
        result = results[dataset_id]
        if result.get("status") != "pass":
            continue
        result["human_visual_review_status"] = review.datasets[dataset_id].status
        validated = Phase1BDatasetResult.model_validate(result)
        payload = validated.model_dump(mode="json")
        results[dataset_id] = payload
        _write_json(artifacts / dataset_id / "benchmark.json", payload)

    evidence = _write_aggregate_and_report(artifacts, results, review)
    aggregate = evidence["aggregate"]
    complete = aggregate["phase_pass"] and evidence["report_verification"]["status"] == "pass"
    return {
        "status": "pass" if complete else "fail",
        "phase_pass": aggregate["phase_pass"],
        "recommendation": aggregate["recommendation"],
        "recommendation_reasons": aggregate["recommendation_reasons"],
        "report": evidence["report"],
        "report_verification": evidence["report_verification"],
    }
