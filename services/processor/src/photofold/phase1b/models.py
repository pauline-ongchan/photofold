"""Strict machine contracts for Phase 1B datasets and results."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Literal

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
