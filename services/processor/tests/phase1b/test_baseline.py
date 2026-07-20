from __future__ import annotations

import math

import numpy as np
import pytest

from photofold.gate1.images import rgb_psnr
from photofold.phase1b.baseline import (
    MATCHED_QUALITIES,
    encode_control_point,
    point_qualifies,
    run_fixed_control,
    run_matched_sweep,
    select_matched_point,
    serialize_psnr,
)
from photofold.phase1b.models import (
    ControlFrameResult,
    ControlTiming,
    IndependentWebPPoint,
)


def _images() -> list[np.ndarray]:
    generator = np.random.default_rng(1234)
    return [generator.integers(0, 256, (16, 16, 3), dtype=np.uint8) for _ in range(5)]


def _point(quality: int, total_bytes: int, per_frame_bytes: list[int]) -> IndependentWebPPoint:
    frames = [
        ControlFrameResult(
            index=index,
            bytes=byte_count,
            ssim=0.9,
            psnr_db=serialize_psnr(35.0),
        )
        for index, byte_count in enumerate(per_frame_bytes)
    ]
    return IndependentWebPPoint(
        quality=quality,
        total_bytes=total_bytes,
        mean_ssim=0.9,
        minimum_ssim=0.9,
        mean_psnr_db=serialize_psnr(35.0),
        minimum_psnr_db=serialize_psnr(35.0),
        per_frame=frames,
        timing=ControlTiming(encoding_ms=0, decode_measurement_ms=0, total_ms=0),
    )


def test_rgb_psnr_uses_schema_safe_positive_infinity() -> None:
    image = np.zeros((8, 8, 3), dtype=np.uint8)

    score = rgb_psnr(image, image.copy())
    serialized = serialize_psnr(score)

    assert math.isinf(score)
    assert serialized.model_dump() == {"value_db": None, "is_infinite": True}


def test_fixed_control_is_independent_webp_q70() -> None:
    result = run_fixed_control(_images())

    assert result.quality == 70
    assert len(result.per_frame) == 5
    assert result.total_bytes == sum(frame.bytes for frame in result.per_frame)
    assert result.timing.encoding_ms > 0
    assert result.timing.decode_measurement_ms > 0


def test_matching_requires_every_frame_to_meet_both_metrics() -> None:
    point = _point(40, 100, [20] * 5)
    photofold = [
        {"index": index, "ssim": 0.9, "psnr_db": 35.0} for index in range(5)
    ]
    assert point_qualifies(point, photofold) is True
    photofold[3]["psnr_db"] = 35.1

    assert point_qualifies(point, photofold) is False


def test_selection_uses_total_quality_then_byte_vector() -> None:
    photofold = [
        {"index": index, "ssim": 0.8, "psnr_db": 30.0} for index in range(5)
    ]
    points = [
        _point(50, 100, [21, 20, 20, 20, 19]),
        _point(40, 100, [22, 20, 20, 20, 18]),
        _point(30, 110, [22, 22, 22, 22, 22]),
    ]

    assert select_matched_point(points, photofold).quality == 40


def test_exhaustive_sweep_covers_every_integer_quality() -> None:
    images = _images()
    reference = encode_control_point(images, 1)
    photofold = [
        {
            "index": frame.index,
            "ssim": frame.ssim,
            "psnr_db": frame.psnr_db.value_db,
        }
        for frame in reference.per_frame
    ]

    result = run_matched_sweep(images, photofold)

    assert [point.quality for point in result.curve] == list(MATCHED_QUALITIES)
    assert result.status == "matched"
    assert result.selected is not None


def test_unmatched_sweep_does_not_substitute_a_lower_quality_point() -> None:
    images = _images()
    photofold = [
        {"index": index, "ssim": 1.0, "psnr_db": float("inf")} for index in range(5)
    ]

    result = run_matched_sweep(images, photofold, qualities=[1, 2])

    assert result.status == "unmatched"
    assert result.selected is None
    assert result.qualifying_qualities == []


def test_qualities_must_be_unique_and_ascending() -> None:
    with pytest.raises(ValueError, match="unique and ascending"):
        run_matched_sweep(_images(), [], qualities=[2, 1])
