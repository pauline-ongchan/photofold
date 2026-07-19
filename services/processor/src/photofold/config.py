"""Local-only Phase 0 configuration."""

from __future__ import annotations

import os
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_DATASET = Path("data/demo/hdrplus-static")


def resolve_repository_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (REPOSITORY_ROOT / path).resolve()


def demo_dataset_path() -> Path:
    return resolve_repository_path(os.getenv("PHOTOFOLD_DEMO_DATASET", str(DEFAULT_DATASET)))


def allowed_origins() -> list[str]:
    configured = os.getenv(
        "PHOTOFOLD_ALLOWED_ORIGINS",
        "http://127.0.0.1:3000,http://localhost:3000",
    )
    return [origin.strip() for origin in configured.split(",") if origin.strip()]

