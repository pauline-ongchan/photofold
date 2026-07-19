"""Pydantic contracts that own the Phase 0 OpenAPI surface."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DatasetSummary(StrictModel):
    id: str
    frame_count: int = Field(ge=5, le=20)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    total_bytes: int = Field(gt=0)


class HealthResponse(StrictModel):
    status: Literal["ok", "degraded"]
    service: Literal["photofold-processor"] = "photofold-processor"
    version: str
    python_version: str
    webp_available: bool
    webp_roundtrip: bool
    dataset: DatasetSummary | None = None
    limitations: list[str]

