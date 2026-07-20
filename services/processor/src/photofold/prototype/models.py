"""Strict contracts for the local-only Phase 4P bridge."""

from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PrototypeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Dimensions(PrototypeModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class PrototypeInputFrame(PrototypeModel):
    index: int = Field(ge=0, le=19)
    original_filename: str = Field(min_length=1, max_length=255)
    stored_filename: str = Field(pattern=r"^frame-[0-9]{3}\.upload$")

    @field_validator("stored_filename")
    @classmethod
    def controlled_filename(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.name != value or path.is_absolute() or ".." in path.parts or "\\" in value:
            raise ValueError("Upload storage names must be controlled basenames")
        return value


class PrototypeInput(PrototypeModel):
    schema_version: Literal["1.0"] = "1.0"
    frames: list[PrototypeInputFrame] = Field(min_length=5, max_length=20)

    @model_validator(mode="after")
    def ordered_unique_frames(self) -> PrototypeInput:
        indices = [frame.index for frame in self.frames]
        if indices != list(range(len(self.frames))):
            raise ValueError("Input frame indices must be ordered and contiguous from zero")
        names = [frame.stored_filename for frame in self.frames]
        if len(names) != len(set(names)):
            raise ValueError("Input storage names must be unique")
        return self


class SourceSnapshot(PrototypeModel):
    index: int = Field(ge=0, le=19)
    original_filename: str
    stored_filename: str
    decoded_format: Literal["JPEG", "PNG", "WEBP"]
    mime_type: Literal["image/jpeg", "image/png", "image/webp"]
    mode: str
    bytes: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    disposition: Literal["accepted"] = "accepted"
    reasons: list[str] = Field(default_factory=list)
    original_artifact: str


class ReferenceCandidate(PrototypeModel):
    index: int = Field(ge=0)
    score: float
    mean_inlier_ratio: float = Field(ge=0, le=1)
    mean_valid_overlap: float = Field(ge=0, le=1)
    sharpness: float = Field(ge=0)
    sharpness_score: float = Field(ge=0, le=1)
    clipped_pixel_fraction: float = Field(ge=0, le=1)
    alignment_success_count: int = Field(ge=0)
    alignment_failure_indices: list[int]


class AlignmentRecord(PrototypeModel):
    frame_index: int = Field(ge=0)
    type: Literal["identity", "affine", "homography"]
    reference_to_target: list[float] = Field(min_length=9, max_length=9)
    inlier_count: int = Field(ge=0)
    match_count: int = Field(ge=0)
    inlier_ratio: float = Field(ge=0, le=1)
    median_reprojection_error: float = Field(ge=0)
    valid_overlap: float = Field(ge=0, le=1)

    @field_validator("reference_to_target")
    @classmethod
    def finite_matrix(cls, value: list[float]) -> list[float]:
        if not all(math.isfinite(item) for item in value):
            raise ValueError("Alignment matrix contains a non-finite value")
        return value


class PrototypeAnalysis(PrototypeModel):
    schema_version: Literal["1.0"] = "1.0"
    analyzed_at: datetime
    status: Literal["analyzed_foldable", "analyzed_rejected"]
    suitability: Literal["safe_to_fold", "not_foldable"]
    reasons: list[str]
    source_frames: list[SourceSnapshot] = Field(min_length=5, max_length=20)
    original_total_bytes: int = Field(gt=0)
    normalized_dimensions: Dimensions
    reference_frame_index: int | None
    reference_score: float | None
    reference_candidates: list[ReferenceCandidate]
    alignment: list[AlignmentRecord]
    config_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    warnings: list[str]
    deferred_fields: list[str]

    @model_validator(mode="after")
    def consistent_analysis(self) -> PrototypeAnalysis:
        if self.status == "analyzed_foldable":
            if self.suitability != "safe_to_fold" or self.reference_frame_index is None:
                raise ValueError("Foldable analysis requires a safe suitability and reference")
            if len(self.alignment) != len(self.source_frames):
                raise ValueError("Foldable analysis requires one transform per frame")
        return self


class PrototypeError(PrototypeModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    stage: str = Field(min_length=1)
    frame_indices: list[int] = Field(default_factory=list)
    retryable: bool = False
    debug: str | None = None


class ErrorEnvelope(PrototypeModel):
    error: PrototypeError


class FrameArtifacts(PrototypeModel):
    original: str
    reconstruction: str | None = None
    difference: str | None = None


class PrototypeFrameResult(PrototypeModel):
    index: int = Field(ge=0, le=19)
    original_filename: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    original_bytes: int = Field(gt=0)
    reconstructed: bool
    ssim: float | None = Field(default=None, ge=-1, le=1)
    quality_threshold_pass: bool | None = None
    patch_count: int | None = Field(default=None, ge=0)
    changed_region_percent: float | None = Field(default=None, ge=0, le=100)
    shared_region_percent: float | None = Field(default=None, ge=0, le=100)
    artifacts: FrameArtifacts


class StorageResult(PrototypeModel):
    original_total_bytes: int = Field(gt=0)
    package_total_bytes: int = Field(gt=0)
    package_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    byte_delta: int
    percent_change: float
    bytes_saved: int = Field(ge=0)
    percent_saved: float = Field(ge=0)
    is_smaller_than_originals: bool


class QualityResult(PrototypeModel):
    mean_ssim: float = Field(ge=-1, le=1)
    minimum_ssim: float = Field(ge=-1, le=1)
    min_mean_threshold: float = Field(ge=-1, le=1)
    min_per_frame_threshold: float = Field(ge=-1, le=1)
    threshold_pass: bool


class PackageContents(PrototypeModel):
    member_count: int = Field(gt=0)
    frame_count: int = Field(ge=5, le=20)
    patch_count: int = Field(ge=0)
    mask_count: int = Field(ge=0)
    metadata_count: int = Field(ge=0)
    member_payload_bytes: int = Field(gt=0)


class PrototypeResult(PrototypeModel):
    schema_version: Literal["1.0"] = "1.0"
    completed_at: datetime
    status: Literal["complete", "complete_no_savings", "failed_quality", "failed"]
    reference_frame_index: int | None
    reconstructed_frame_count: int = Field(ge=0, le=20)
    storage: StorageResult | None
    quality: QualityResult | None
    frames: list[PrototypeFrameResult] = Field(min_length=5, max_length=20)
    package_contents: PackageContents | None
    package_artifact: str | None
    warnings: list[str]
    error: PrototypeError | None = None

    @model_validator(mode="after")
    def terminal_payload_matches_status(self) -> PrototypeResult:
        measured = self.status != "failed"
        if measured and any(
            value is None
            for value in (self.storage, self.quality, self.package_contents, self.package_artifact)
        ):
            raise ValueError(
                "Evaluated terminal results require storage, quality, and package data"
            )
        if measured and self.error is not None:
            raise ValueError("Evaluated terminal results cannot include a processing error")
        if not measured and self.error is None:
            raise ValueError("Failed results require a structured error")
        return self


def export_prototype_schemas(output_directory: str | Path) -> list[Path]:
    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=True)
    schemas = {
        "prototype-input.schema.json": PrototypeInput.model_json_schema(),
        "prototype-analysis.schema.json": PrototypeAnalysis.model_json_schema(),
        "prototype-result.schema.json": PrototypeResult.model_json_schema(),
        "prototype-error.schema.json": ErrorEnvelope.model_json_schema(),
    }
    paths: list[Path] = []
    for filename, schema in schemas.items():
        path = directory / filename
        path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        paths.append(path)
    return paths
