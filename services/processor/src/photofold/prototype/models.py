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
    decision: Literal["shared", "fallback"]
    type: Literal["identity", "affine", "homography"] | None
    reference_to_target: list[float] | None = Field(default=None, min_length=9, max_length=9)
    inlier_count: int | None = Field(default=None, ge=0)
    match_count: int | None = Field(default=None, ge=0)
    inlier_ratio: float | None = Field(default=None, ge=0, le=1)
    median_reprojection_error: float | None = Field(default=None, ge=0)
    reprojection_error_units: Literal["analysis_pixels"] = "analysis_pixels"
    valid_overlap: float | None = Field(default=None, ge=0, le=1)
    fallback_reason: str | None = None

    @field_validator("reference_to_target")
    @classmethod
    def finite_matrix(cls, value: list[float] | None) -> list[float] | None:
        if value is None:
            return value
        if not all(math.isfinite(item) for item in value):
            raise ValueError("Alignment matrix contains a non-finite value")
        return value

    @model_validator(mode="after")
    def evidence_matches_decision(self) -> AlignmentRecord:
        if self.type is None and self.reference_to_target is not None:
            raise ValueError("Alignment without a transform type cannot contain a matrix")
        if self.type is not None and self.reference_to_target is None:
            raise ValueError("Measured alignment requires a transform matrix")
        if self.decision == "shared" and self.type is None:
            raise ValueError("Shared alignment requires measured transform evidence")
        if self.decision == "fallback" and not self.fallback_reason:
            raise ValueError("Fallback alignment requires an explicit reason")
        return self


class AlignmentMeasurement(PrototypeModel):
    units: Literal["analysis_pixels"] = "analysis_pixels"
    analysis_max_dimension: int = Field(gt=0)
    max_median_reprojection_error: float = Field(gt=0)
    min_inlier_ratio: float = Field(ge=0, le=1)
    description: str = Field(min_length=1)


class FrameDisposition(PrototypeModel):
    frame_index: int = Field(ge=0, le=19)
    storage_mode: Literal["shared_reference", "shared_delta", "independent_source"]
    fallback_reason: str | None = None

    @model_validator(mode="after")
    def fallback_has_reason(self) -> FrameDisposition:
        if self.storage_mode == "independent_source" and not self.fallback_reason:
            raise ValueError("Independent fallback requires a reason")
        if self.storage_mode != "independent_source" and self.fallback_reason is not None:
            raise ValueError("Shared frames cannot contain a fallback reason")
        return self


class PrototypeAnalysis(PrototypeModel):
    schema_version: Literal["1.1"] = "1.1"
    analyzed_at: datetime
    status: Literal["analyzed_foldable"] = "analyzed_foldable"
    suitability: Literal["safe_to_fold", "foldable_with_reduced_savings"]
    strategy: Literal["shared_scene", "hybrid", "independent_only"]
    reasons: list[str]
    source_frames: list[SourceSnapshot] = Field(min_length=5, max_length=20)
    original_total_bytes: int = Field(gt=0)
    normalized_dimensions: Dimensions | None
    shared_frame_count: int = Field(ge=0, le=20)
    fallback_frame_count: int = Field(ge=0, le=20)
    frame_dispositions: list[FrameDisposition] = Field(min_length=5, max_length=20)
    reference_frame_index: int | None
    reference_score: float | None
    reference_candidates: list[ReferenceCandidate]
    alignment: list[AlignmentRecord]
    alignment_measurement: AlignmentMeasurement
    config_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    warnings: list[str]
    deferred_fields: list[str]

    @model_validator(mode="after")
    def consistent_analysis(self) -> PrototypeAnalysis:
        frame_count = len(self.source_frames)
        if len(self.alignment) != frame_count or len(self.frame_dispositions) != frame_count:
            raise ValueError("Analysis requires alignment and storage evidence for every frame")
        indices = list(range(frame_count))
        if [item.frame_index for item in self.alignment] != indices or [
            item.frame_index for item in self.frame_dispositions
        ] != indices:
            raise ValueError("Analysis evidence must preserve source order")
        shared = [
            item for item in self.frame_dispositions if item.storage_mode != "independent_source"
        ]
        fallback = [
            item for item in self.frame_dispositions if item.storage_mode == "independent_source"
        ]
        if self.shared_frame_count != len(shared) or self.fallback_frame_count != len(fallback):
            raise ValueError("Analysis strategy counts disagree with frame dispositions")
        if self.strategy == "independent_only":
            if shared or self.reference_frame_index is not None:
                raise ValueError("Independent-only analysis cannot select a shared reference")
        else:
            references = [item for item in shared if item.storage_mode == "shared_reference"]
            if len(shared) < 2 or len(references) != 1:
                raise ValueError("Shared analysis requires one reference and at least one delta")
            if references[0].frame_index != self.reference_frame_index:
                raise ValueError("Reference index disagrees with the storage disposition")
        expected_suitability = (
            "safe_to_fold" if self.strategy == "shared_scene" else "foldable_with_reduced_savings"
        )
        if self.suitability != expected_suitability:
            raise ValueError("Suitability does not match the selected strategy")
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
    storage_mode: Literal["shared_reference", "shared_delta", "independent_source"]
    fallback_reason: str | None = None
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
    independent_source_count: int = Field(ge=0, le=20)
    member_payload_bytes: int = Field(gt=0)


class PrototypeResult(PrototypeModel):
    schema_version: Literal["1.1"] = "1.1"
    completed_at: datetime
    status: Literal["complete", "complete_no_savings", "failed_quality", "failed"]
    strategy: Literal["shared_scene", "hybrid", "independent_only"]
    shared_frame_count: int = Field(ge=0, le=20)
    fallback_frame_count: int = Field(ge=0, le=20)
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
