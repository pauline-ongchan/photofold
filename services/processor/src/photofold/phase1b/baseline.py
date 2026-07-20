"""Independent-WebP controls and per-frame quality matching for Phase 1B."""

from __future__ import annotations

import math
import time
from collections.abc import Iterable
from typing import Any

import numpy as np

from photofold.gate1.images import decode_rgb, encode_webp, rgb_psnr, rgb_ssim
from photofold.phase1b.models import (
    ControlFrameResult,
    ControlTiming,
    IndependentWebPPoint,
    MatchedBaselineResult,
    PsnrValue,
)

FIXED_QUALITY = 70
SSIM_TOLERANCE = 1e-6
PSNR_TOLERANCE_DB = 1e-4
MATCHED_QUALITIES = tuple(range(1, 101))


def serialize_psnr(value: float) -> PsnrValue:
    if math.isinf(value) and value > 0:
        return PsnrValue(value_db=None, is_infinite=True)
    if not math.isfinite(value):
        raise ValueError("PSNR must be finite or positive infinity")
    return PsnrValue(value_db=value, is_infinite=False)


def psnr_float(value: PsnrValue) -> float:
    return float("inf") if value.is_infinite else float(value.value_db)


def _aggregate_psnr(values: list[float]) -> tuple[PsnrValue, PsnrValue]:
    return serialize_psnr(float(np.mean(values))), serialize_psnr(float(np.min(values)))


def encode_control_point(images: list[np.ndarray], quality: int) -> IndependentWebPPoint:
    frames: list[ControlFrameResult] = []
    encoding_ns = 0
    measurement_ns = 0
    total_start = time.perf_counter_ns()
    for index, image in enumerate(images):
        encode_start = time.perf_counter_ns()
        payload = encode_webp(image, quality)
        encoding_ns += time.perf_counter_ns() - encode_start
        measurement_start = time.perf_counter_ns()
        decoded = decode_rgb(payload)
        frames.append(
            ControlFrameResult(
                index=index,
                bytes=len(payload),
                ssim=rgb_ssim(image, decoded),
                psnr_db=serialize_psnr(rgb_psnr(image, decoded)),
            )
        )
        measurement_ns += time.perf_counter_ns() - measurement_start
    total_ns = time.perf_counter_ns() - total_start
    ssim_values = [frame.ssim for frame in frames]
    psnr_values = [psnr_float(frame.psnr_db) for frame in frames]
    mean_psnr, minimum_psnr = _aggregate_psnr(psnr_values)
    return IndependentWebPPoint(
        quality=quality,
        total_bytes=sum(frame.bytes for frame in frames),
        mean_ssim=float(np.mean(ssim_values)),
        minimum_ssim=float(np.min(ssim_values)),
        mean_psnr_db=mean_psnr,
        minimum_psnr_db=minimum_psnr,
        per_frame=frames,
        timing=ControlTiming(
            encoding_ms=encoding_ns / 1_000_000,
            decode_measurement_ms=measurement_ns / 1_000_000,
            total_ms=total_ns / 1_000_000,
        ),
    )


def run_fixed_control(images: list[np.ndarray]) -> IndependentWebPPoint:
    return encode_control_point(images, FIXED_QUALITY)


def point_qualifies(
    point: IndependentWebPPoint,
    photofold_per_frame: list[dict[str, Any]],
) -> bool:
    if len(point.per_frame) != len(photofold_per_frame):
        return False
    for candidate, photofold in zip(point.per_frame, photofold_per_frame, strict=True):
        if candidate.index != int(photofold["index"]):
            return False
        if candidate.ssim + SSIM_TOLERANCE < float(photofold["ssim"]):
            return False
        candidate_psnr = psnr_float(candidate.psnr_db)
        photofold_psnr = float(photofold["psnr_db"])
        if candidate_psnr + PSNR_TOLERANCE_DB < photofold_psnr:
            return False
    return True


def select_matched_point(
    curve: list[IndependentWebPPoint],
    photofold_per_frame: list[dict[str, Any]],
) -> IndependentWebPPoint | None:
    qualifying = [point for point in curve if point_qualifies(point, photofold_per_frame)]
    if not qualifying:
        return None
    return min(
        qualifying,
        key=lambda point: (
            point.total_bytes,
            point.quality,
            tuple(frame.bytes for frame in point.per_frame),
        ),
    )


def run_matched_sweep(
    images: list[np.ndarray],
    photofold_per_frame: list[dict[str, Any]],
    qualities: Iterable[int] = MATCHED_QUALITIES,
) -> MatchedBaselineResult:
    quality_values = list(qualities)
    if quality_values != sorted(quality_values) or len(quality_values) != len(
        set(quality_values)
    ):
        raise ValueError("Matched WebP qualities must be unique and ascending")
    sweep_start = time.perf_counter_ns()
    curve = [encode_control_point(images, quality) for quality in quality_values]
    selected = select_matched_point(curve, photofold_per_frame)
    qualifying_qualities = [
        point.quality for point in curve if point_qualifies(point, photofold_per_frame)
    ]
    return MatchedBaselineResult(
        status="matched" if selected is not None else "unmatched",
        ssim_tolerance=SSIM_TOLERANCE,
        psnr_tolerance_db=PSNR_TOLERANCE_DB,
        selected=selected,
        qualifying_qualities=qualifying_qualities,
        curve=curve,
        sweep_timing_ms=(time.perf_counter_ns() - sweep_start) / 1_000_000,
    )
