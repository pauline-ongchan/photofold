from __future__ import annotations

from datetime import UTC, datetime

import pytest

from photofold.phase1b.aggregate import build_aggregate
from photofold.phase1b.datasets import PHASE1B_DATASET_IDS
from photofold.phase1b.models import HumanDatasetReview, HumanReview


def _result(dataset_id: str, matched_bytes: int, package_bytes: int) -> dict[str, object]:
    return {
        "status": "pass",
        "dataset_id": dataset_id,
        "machine_pass": True,
        "accepted_frame_count": 5,
        "reconstructed_frame_count": 5,
        "original_total_bytes": 2_000,
        "fixed_webp": {"total_bytes": 1_200},
        "matched_webp": {
            "status": "matched",
            "selected": {"total_bytes": matched_bytes},
        },
        "photofold_package_bytes": package_bytes,
    }


def _results(savings: tuple[float, float, float]) -> dict[str, dict[str, object]]:
    return {
        dataset_id: _result(
            dataset_id,
            1_000_000,
            round(1_000_000 * (1 - saving / 100)),
        )
        for dataset_id, saving in zip(PHASE1B_DATASET_IDS, savings, strict=True)
    }


def _review(*, complexity: bool = False, failed_dataset: str | None = None) -> HumanReview:
    return HumanReview(
        schema_version="1.0",
        review_basis_sha256="a" * 64,
        reviewer="Test reviewer",
        reviewed_at=datetime.now(UTC),
        datasets={
            dataset_id: HumanDatasetReview(
                status="fail" if dataset_id == failed_dataset else "pass",
                notes="Fixture review evidence.",
                lowest_ssim_frame_inspected=0,
                lowest_psnr_frame_inspected=0,
            )
            for dataset_id in PHASE1B_DATASET_IDS
        },
        complexity_disproportionate=complexity,
        complexity_notes="Measured runtime is disproportionate." if complexity else "No veto.",
    )


def test_aggregate_uses_median_and_weighted_byte_formula() -> None:
    results = {
        PHASE1B_DATASET_IDS[0]: _result(PHASE1B_DATASET_IDS[0], 1_000, 900),
        PHASE1B_DATASET_IDS[1]: _result(PHASE1B_DATASET_IDS[1], 2_000, 1_600),
        PHASE1B_DATASET_IDS[2]: _result(PHASE1B_DATASET_IDS[2], 7_000, 6_650),
    }

    aggregate = build_aggregate(results, _review())

    assert aggregate.median_relational_savings_percent == pytest.approx(10.0)
    assert aggregate.weighted_mean_relational_savings_percent == pytest.approx(8.5)
    assert aggregate.best_dataset_id == PHASE1B_DATASET_IDS[1]
    assert aggregate.worst_dataset_id == PHASE1B_DATASET_IDS[2]
    assert aggregate.win_count == 3
    assert aggregate.recommendation == "CONTINUE COMPRESSION-FIRST"
    assert aggregate.phase_pass is True


@pytest.mark.parametrize("median_saving", [5.0, 9.999])
def test_investigate_boundaries(median_saving: float) -> None:
    aggregate = build_aggregate(
        _results((median_saving, median_saving, median_saving)), _review()
    )

    assert aggregate.recommendation == "INVESTIGATE"


def test_continue_starts_at_ten_percent_and_two_wins() -> None:
    aggregate = build_aggregate(_results((0.0, 10.0, 20.0)), _review())

    assert aggregate.median_relational_savings_percent == pytest.approx(10.0)
    assert aggregate.win_count == 2
    assert aggregate.tie_count == 1
    assert aggregate.recommendation == "CONTINUE COMPRESSION-FIRST"


def test_best_and_worst_ties_use_dataset_id_order() -> None:
    aggregate = build_aggregate(_results((10.0, 10.0, 10.0)), _review())

    assert aggregate.best_dataset_id == "camera-motion-or-lighting"
    assert aggregate.worst_dataset_id == "camera-motion-or-lighting"


def test_below_five_and_two_losses_trigger_ordered_pivot_vetoes() -> None:
    aggregate = build_aggregate(_results((20.0, -1.0, -2.0)), _review())

    assert aggregate.recommendation == "PIVOT"
    assert aggregate.loss_count == 2
    assert any("(<5%)" in reason for reason in aggregate.recommendation_reasons)
    assert any("at least two" in reason for reason in aggregate.recommendation_reasons)


def test_unmatched_or_pending_human_evidence_cannot_continue() -> None:
    results = _results((20.0, 20.0, 20.0))
    results[PHASE1B_DATASET_IDS[1]]["matched_webp"] = {
        "status": "unmatched",
        "selected": None,
    }

    unmatched = build_aggregate(results, _review())
    pending = build_aggregate(_results((20.0, 20.0, 20.0)))

    assert unmatched.relational_evidence_complete is False
    assert unmatched.recommendation == "PIVOT"
    assert pending.recommendation == "PIVOT"
    assert "human visual review" in pending.failed_checks


def test_visual_failure_and_documented_complexity_are_pivot_vetoes() -> None:
    visual = build_aggregate(
        _results((20.0, 20.0, 20.0)),
        _review(failed_dataset=PHASE1B_DATASET_IDS[0]),
    )
    complexity = build_aggregate(
        _results((20.0, 20.0, 20.0)),
        _review(complexity=True),
    )

    assert visual.recommendation == "PIVOT"
    assert any("visible quality" in reason for reason in visual.recommendation_reasons)
    assert complexity.recommendation == "PIVOT"
    assert any("complexity" in reason for reason in complexity.recommendation_reasons)
