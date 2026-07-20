"""Aggregate Phase 1B evidence and apply the ordered decision rules."""

from __future__ import annotations

from datetime import UTC, datetime
from statistics import median
from typing import Any

from photofold.phase1b.datasets import PHASE1B_DATASET_IDS
from photofold.phase1b.models import (
    DatasetAggregateSummary,
    HumanReview,
    Phase1BAggregateResult,
)


def _summary(result: dict[str, Any], expected_id: str) -> DatasetAggregateSummary:
    if result.get("dataset_id") != expected_id:
        raise ValueError(
            f"Expected dataset {expected_id!r}, found {result.get('dataset_id')!r}"
        )
    dataset_status = "pass" if result.get("status") == "pass" else "fail"
    matched = result.get("matched_webp") or {}
    matched_status = matched.get("status", "not-run")
    selected = matched.get("selected")
    package_bytes = int(result.get("photofold_package_bytes", 0))
    matched_bytes = int(selected["total_bytes"]) if selected is not None else None
    relational = (
        (matched_bytes - package_bytes) / matched_bytes * 100
        if matched_bytes is not None and package_bytes > 0
        else None
    )
    fixed = result.get("fixed_webp") or {}
    return DatasetAggregateSummary(
        dataset_id=expected_id,
        dataset_status=dataset_status,
        matched_status=matched_status,
        relational_savings_percent=relational,
        original_total_bytes=int(result.get("original_total_bytes", 0)),
        fixed_webp_total_bytes=int(fixed.get("total_bytes", 0)),
        photofold_package_bytes=package_bytes,
        matched_webp_total_bytes=matched_bytes,
        accepted_frame_count=int(result.get("accepted_frame_count", 0)),
        reconstructed_frame_count=int(result.get("reconstructed_frame_count", 0)),
        machine_pass=bool(result.get("machine_pass", False)),
    )


def _human_review_passes(review: HumanReview | None) -> bool:
    return review is not None and all(
        review.datasets.get(dataset_id) is not None
        and review.datasets[dataset_id].status == "pass"
        for dataset_id in PHASE1B_DATASET_IDS
    )


def _recommendation(
    summaries: list[DatasetAggregateSummary],
    median_savings: float | None,
    wins: int,
    losses: int,
    relational_complete: bool,
    human_review: HumanReview | None,
) -> tuple[str, list[str]]:
    machine_complete = all(
        item.dataset_status == "pass"
        and item.machine_pass
        and item.accepted_frame_count == item.reconstructed_frame_count
        and item.accepted_frame_count >= 5
        for item in summaries
    )
    visual_pass = _human_review_passes(human_review)
    visual_failure = human_review is not None and any(
        item.status == "fail" for item in human_review.datasets.values()
    )
    complexity_veto = bool(
        human_review is not None and human_review.complexity_disproportionate
    )

    pivot_reasons: list[str] = []
    if not machine_complete:
        pivot_reasons.append("reconstruction or package-integrity evidence is incomplete")
    if visual_failure:
        pivot_reasons.append("human review identified a visible quality regression")
    if median_savings is not None and median_savings < 5:
        pivot_reasons.append(
            f"median matched-baseline relational saving is {median_savings:.9f}% (<5%)"
        )
    if losses >= 2:
        pivot_reasons.append(f"PhotoFold loses on {losses} datasets (at least two)")
    if complexity_veto:
        pivot_reasons.append(
            "reviewer judged implementation/runtime complexity disproportionate"
        )
    if pivot_reasons:
        return "PIVOT", pivot_reasons

    complete_quality = relational_complete and visual_pass and machine_complete
    if (
        complete_quality
        and median_savings is not None
        and median_savings >= 10
        and wins >= 2
    ):
        return (
            "CONTINUE COMPRESSION-FIRST",
            [
                f"median matched saving is {median_savings:.9f}% (at least 10%)",
                f"PhotoFold wins on {wins} of 3 datasets",
                "all reconstruction, integrity, matched-quality, and visual checks pass",
            ],
        )
    if (
        complete_quality
        and median_savings is not None
        and 5 <= median_savings < 10
    ):
        return (
            "INVESTIGATE",
            [
                f"median matched saving is {median_savings:.9f}% (5% to below 10%)",
                "all reconstruction, integrity, matched-quality, and visual checks pass",
                "no pivot veto applies",
            ],
        )

    remaining = []
    if not relational_complete:
        remaining.append("at least one dataset lacks a qualifying matched baseline")
    if human_review is None:
        remaining.append("human visual review is pending")
    elif not visual_pass:
        remaining.append("human visual review is incomplete")
    if median_savings is not None and median_savings < 10:
        remaining.append("continue threshold was not met")
    if wins < 2:
        remaining.append(f"only {wins} dataset wins were recorded")
    return "PIVOT", remaining or ["remaining combination satisfies no continue rule"]


def build_aggregate(
    results: dict[str, dict[str, Any]],
    human_review: HumanReview | None = None,
) -> Phase1BAggregateResult:
    if set(results) != set(PHASE1B_DATASET_IDS):
        raise ValueError(
            "Aggregate inputs must contain exactly the three canonical Phase 1B datasets"
        )
    summaries = [_summary(results[dataset_id], dataset_id) for dataset_id in PHASE1B_DATASET_IDS]
    complete = all(
        item.matched_status == "matched"
        and item.matched_webp_total_bytes is not None
        and item.photofold_package_bytes > 0
        for item in summaries
    )
    relational_values = [
        item.relational_savings_percent
        for item in summaries
        if item.relational_savings_percent is not None
    ]
    median_savings = float(median(relational_values)) if complete else None
    aggregate_matched = (
        sum(int(item.matched_webp_total_bytes) for item in summaries) if complete else None
    )
    aggregate_photofold = sum(item.photofold_package_bytes for item in summaries)
    weighted = (
        (aggregate_matched - aggregate_photofold) / aggregate_matched * 100
        if aggregate_matched is not None
        else None
    )
    ordered_by_best = sorted(
        (item for item in summaries if item.relational_savings_percent is not None),
        key=lambda item: (-float(item.relational_savings_percent), item.dataset_id),
    )
    ordered_by_worst = sorted(
        (item for item in summaries if item.relational_savings_percent is not None),
        key=lambda item: (float(item.relational_savings_percent), item.dataset_id),
    )
    wins = sum(
        item.matched_webp_total_bytes is not None
        and item.photofold_package_bytes < item.matched_webp_total_bytes
        for item in summaries
    )
    losses = sum(
        item.matched_webp_total_bytes is not None
        and item.photofold_package_bytes > item.matched_webp_total_bytes
        for item in summaries
    )
    ties = sum(
        item.matched_webp_total_bytes is not None
        and item.photofold_package_bytes == item.matched_webp_total_bytes
        for item in summaries
    )
    recommendation, reasons = _recommendation(
        summaries,
        median_savings,
        wins,
        losses,
        complete,
        human_review,
    )
    machine_complete = all(
        item.dataset_status == "pass" and item.machine_pass for item in summaries
    )
    human_complete = _human_review_passes(human_review)
    failed_checks = []
    if not machine_complete:
        failed_checks.append("dataset machine verification")
    if not complete:
        failed_checks.append("complete matched-baseline evidence")
    if not human_complete:
        failed_checks.append("human visual review")
    return Phase1BAggregateResult(
        schema_version="1.0",
        generated_at=datetime.now(UTC),
        dataset_order=list(PHASE1B_DATASET_IDS),
        datasets=summaries,
        aggregate_original_bytes=sum(item.original_total_bytes for item in summaries),
        aggregate_fixed_webp_bytes=sum(item.fixed_webp_total_bytes for item in summaries),
        aggregate_matched_webp_bytes=aggregate_matched,
        aggregate_photofold_bytes=aggregate_photofold,
        median_relational_savings_percent=median_savings,
        weighted_mean_relational_savings_percent=weighted,
        best_dataset_id=ordered_by_best[0].dataset_id if ordered_by_best else None,
        best_relational_savings_percent=(
            ordered_by_best[0].relational_savings_percent if ordered_by_best else None
        ),
        worst_dataset_id=ordered_by_worst[0].dataset_id if ordered_by_worst else None,
        worst_relational_savings_percent=(
            ordered_by_worst[0].relational_savings_percent if ordered_by_worst else None
        ),
        win_count=wins,
        loss_count=losses,
        tie_count=ties,
        total_accepted_frames=sum(item.accepted_frame_count for item in summaries),
        total_reconstructed_frames=sum(item.reconstructed_frame_count for item in summaries),
        relational_evidence_complete=complete,
        human_review=human_review,
        recommendation=recommendation,
        recommendation_reasons=reasons,
        phase_pass=machine_complete and complete and human_complete,
        failed_checks=failed_checks,
    )
