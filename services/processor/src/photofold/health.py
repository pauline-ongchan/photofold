"""Health response composed from real local capability checks."""

from __future__ import annotations

import platform

from photofold import __version__
from photofold.config import demo_dataset_path
from photofold.contracts import DatasetSummary, HealthResponse
from photofold.dataset import DatasetValidationError, validate_dataset
from photofold.doctor import run_doctor


def health_response() -> HealthResponse:
    doctor = run_doctor()
    dataset_summary: DatasetSummary | None = None
    limitations = [
        "Phase 0 foundation only; compression and reconstruction are not implemented.",
        "Storage and quality metrics do not exist until Gate 1 processes real outputs.",
    ]

    try:
        dataset = validate_dataset(demo_dataset_path())
        dimensions = dataset["normalized_dimensions"]
        dataset_summary = DatasetSummary(
            id=dataset["dataset_id"],
            frame_count=dataset["frame_count"],
            width=dimensions["width"],
            height=dimensions["height"],
            total_bytes=dataset["total_bytes"],
        )
    except DatasetValidationError as error:
        limitations.append(f"Curated dataset unavailable: {error}")

    webp_available = bool(doctor["checks"]["webp_available"])
    webp_roundtrip = bool(doctor["checks"]["webp_roundtrip"])
    status = "ok" if doctor["status"] == "pass" and dataset_summary is not None else "degraded"
    return HealthResponse(
        status=status,
        version=__version__,
        python_version=platform.python_version(),
        webp_available=webp_available,
        webp_roundtrip=webp_roundtrip,
        dataset=dataset_summary,
        limitations=limitations,
    )

