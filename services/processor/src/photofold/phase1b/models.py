"""Strict machine contracts for Phase 1B datasets and results."""

from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Phase1BModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Dimensions(Phase1BModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class ManifestFile(Phase1BModel):
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("path")
    @classmethod
    def safe_relative_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or "\\" in value:
            raise ValueError(f"Unsafe dataset path: {value!r}")
        return value


class Provenance(Phase1BModel):
    source: str = Field(min_length=1)
    capture_date: str = Field(min_length=1)
    device: str = Field(min_length=1)
    authorization: str = Field(min_length=1)


class Consent(Phase1BModel):
    basis: str = Field(min_length=1)
    identifiable_people_visible: bool
    notes: str = Field(min_length=1)


class License(Phase1BModel):
    id: str = Field(min_length=1)
    redistribution_permitted: bool
    notes: str = Field(min_length=1)


class Phase1BDatasetManifest(Phase1BModel):
    schema_version: Literal["1.0"]
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    scenario_category: str = Field(min_length=1)
    provenance: Provenance
    consent: Consent
    license: License
    capture_notes: list[str] = Field(min_length=1)
    known_limitations: list[str] = Field(min_length=1)
    expected_frame_count: int = Field(ge=5, le=20)
    expected_dimensions: Dimensions
    files: list[ManifestFile] = Field(min_length=5, max_length=20)

    @model_validator(mode="after")
    def consistent_files(self) -> Phase1BDatasetManifest:
        if self.expected_frame_count != len(self.files):
            raise ValueError(
                "expected_frame_count does not equal the ordered files array length"
            )
        paths = [item.path for item in self.files]
        if len(paths) != len(set(paths)):
            raise ValueError("Dataset manifest contains duplicate file paths")
        return self


class PsnrValue(Phase1BModel):
    value_db: float | None
    is_infinite: bool

    @model_validator(mode="after")
    def valid_representation(self) -> PsnrValue:
        if self.is_infinite and self.value_db is not None:
            raise ValueError("Infinite PSNR must use a null value_db")
        if not self.is_infinite and (
            self.value_db is None or not math.isfinite(self.value_db)
        ):
            raise ValueError("Finite PSNR must use a finite numeric value_db")
        return self


class ControlFrameResult(Phase1BModel):
    index: int = Field(ge=0)
    bytes: int = Field(gt=0)
    ssim: float = Field(ge=0, le=1)
    psnr_db: PsnrValue


class ControlTiming(Phase1BModel):
    encoding_ms: float = Field(ge=0)
    decode_measurement_ms: float = Field(ge=0)
    total_ms: float = Field(ge=0)


class IndependentWebPPoint(Phase1BModel):
    quality: int = Field(ge=1, le=100)
    total_bytes: int = Field(gt=0)
    mean_ssim: float = Field(ge=0, le=1)
    minimum_ssim: float = Field(ge=0, le=1)
    mean_psnr_db: PsnrValue
    minimum_psnr_db: PsnrValue
    per_frame: list[ControlFrameResult] = Field(min_length=1)
    timing: ControlTiming


class MatchedBaselineResult(Phase1BModel):
    status: Literal["matched", "unmatched"]
    ssim_tolerance: float = Field(ge=0)
    psnr_tolerance_db: float = Field(ge=0)
    selected: IndependentWebPPoint | None
    qualifying_qualities: list[int]
    curve: list[IndependentWebPPoint] = Field(min_length=1)
    sweep_timing_ms: float = Field(ge=0)

    @model_validator(mode="after")
    def selected_matches_status(self) -> MatchedBaselineResult:
        if (self.status == "matched") != (self.selected is not None):
            raise ValueError("Matched status and selected point disagree")
        return self


class SourceRecord(Phase1BModel):
    path: str
    bytes: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class IntegrityCheck(Phase1BModel):
    id: str
    label: str
    passed: bool
    detail: str


class PackageMemberResult(Phase1BModel):
    path: str
    role: str
    stored_bytes: int = Field(ge=0)
    uncompressed_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class Phase1BDatasetResult(Phase1BModel):
    schema_version: Literal["1.0"]
    run_at: datetime
    dataset_id: str
    scenario_category: str
    dataset_path: str
    manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    validation: dict[str, Any]
    source_before: list[SourceRecord]
    source_after: list[SourceRecord]
    source_immutability_pass: bool
    config_path: str
    config_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    parameters: dict[str, int]
    environment: dict[str, Any]
    frame_dispositions: list[dict[str, Any]]
    accepted_frame_count: int = Field(ge=0, le=20)
    reconstructed_frame_count: int = Field(ge=0, le=20)
    original_total_bytes: int = Field(gt=0)
    fixed_webp: IndependentWebPPoint
    matched_webp: MatchedBaselineResult
    photofold_package_bytes: int = Field(gt=0)
    photofold_package_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    storage: dict[str, Any]
    reference_frame_index: int = Field(ge=0)
    alignment: dict[str, Any]
    per_frame: list[dict[str, Any]]
    quality: dict[str, Any]
    timings: dict[str, Any]
    package_overhead: dict[str, Any]
    package_members: list[PackageMemberResult]
    artifacts: dict[str, Any]
    checks: list[IntegrityCheck]
    machine_pass: bool
    human_visual_review_status: Literal["pending", "pass", "fail"]
    failed_checks: list[str]


class DatasetAggregateSummary(Phase1BModel):
    dataset_id: str
    matched_status: Literal["matched", "unmatched"]
    relational_savings_percent: float | None
    photofold_package_bytes: int = Field(gt=0)
    matched_webp_total_bytes: int | None = Field(default=None, gt=0)
    accepted_frame_count: int = Field(ge=0)
    reconstructed_frame_count: int = Field(ge=0)
    machine_pass: bool


class HumanDatasetReview(Phase1BModel):
    status: Literal["pass", "fail"]
    notes: str = Field(min_length=1)
    lowest_ssim_frame_inspected: int = Field(ge=0)
    lowest_psnr_frame_inspected: int = Field(ge=0)


class HumanReview(Phase1BModel):
    schema_version: Literal["1.0"]
    review_basis_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reviewer: str = Field(min_length=1)
    reviewed_at: datetime
    datasets: dict[str, HumanDatasetReview]
    complexity_disproportionate: bool
    complexity_notes: str

    @model_validator(mode="after")
    def complexity_has_evidence(self) -> HumanReview:
        if self.complexity_disproportionate and not self.complexity_notes.strip():
            raise ValueError("A complexity veto requires written evidence")
        return self


class Phase1BAggregateResult(Phase1BModel):
    schema_version: Literal["1.0"]
    generated_at: datetime
    dataset_order: list[str] = Field(min_length=3, max_length=3)
    datasets: list[DatasetAggregateSummary] = Field(min_length=3, max_length=3)
    aggregate_original_bytes: int = Field(gt=0)
    aggregate_fixed_webp_bytes: int = Field(gt=0)
    aggregate_matched_webp_bytes: int | None = Field(default=None, gt=0)
    aggregate_photofold_bytes: int = Field(gt=0)
    median_relational_savings_percent: float | None
    weighted_mean_relational_savings_percent: float | None
    best_dataset_id: str | None
    best_relational_savings_percent: float | None
    worst_dataset_id: str | None
    worst_relational_savings_percent: float | None
    win_count: int = Field(ge=0, le=3)
    loss_count: int = Field(ge=0, le=3)
    tie_count: int = Field(ge=0, le=3)
    total_accepted_frames: int = Field(ge=0)
    total_reconstructed_frames: int = Field(ge=0)
    relational_evidence_complete: bool
    human_review: HumanReview | None
    recommendation: Literal[
        "CONTINUE COMPRESSION-FIRST",
        "INVESTIGATE",
        "PIVOT",
    ]
    recommendation_reasons: list[str]
    phase_pass: bool
    failed_checks: list[str]


PHASE1B_SCHEMA_MODELS: dict[str, type[Phase1BModel]] = {
    "phase1b-dataset-manifest.schema.json": Phase1BDatasetManifest,
    "phase1b-dataset-result.schema.json": Phase1BDatasetResult,
    "phase1b-aggregate-result.schema.json": Phase1BAggregateResult,
    "phase1b-human-review.schema.json": HumanReview,
}


def export_phase1b_schemas(output_directory: str | Path) -> list[Path]:
    destination = Path(output_directory)
    destination.mkdir(parents=True, exist_ok=True)
    written = []
    for filename, model in PHASE1B_SCHEMA_MODELS.items():
        path = destination / filename
        path.write_text(
            json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        written.append(path)
    return written
