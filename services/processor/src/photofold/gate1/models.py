"""Strict package models for the Gate 1 PhotoFold artifact."""

from __future__ import annotations

import math
from datetime import datetime
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Gate1Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _safe_member_path(value: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\\" in value:
        raise ValueError(f"Unsafe package member path: {value!r}")
    return value


class AssetRecord(Gate1Model):
    path: str
    bytes: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    _validate_path = field_validator("path")(_safe_member_path)


class BaseRecord(Gate1Model):
    path: Literal["base.webp"] = "base.webp"
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    encoding: Literal["webp"] = "webp"
    quality: int = Field(ge=1, le=100)


class TransformRecord(Gate1Model):
    type: Literal["identity", "affine", "homography"]
    reference_to_target: list[float] = Field(min_length=9, max_length=9)
    interpolation: Literal["linear"] = "linear"
    border_mode: Literal["constant"] = "constant"
    inlier_count: int = Field(ge=0)
    inlier_ratio: float = Field(ge=0, le=1)
    median_reprojection_error: float = Field(ge=0)
    valid_overlap: float = Field(ge=0, le=1)

    @field_validator("reference_to_target")
    @classmethod
    def finite_matrix(cls, value: list[float]) -> list[float]:
        if not all(math.isfinite(item) for item in value):
            raise ValueError("Transform contains a non-finite value")
        matrix = [value[0:3], value[3:6], value[6:9]]
        determinant = (
            matrix[0][0] * (matrix[1][1] * matrix[2][2] - matrix[1][2] * matrix[2][1])
            - matrix[0][1] * (matrix[1][0] * matrix[2][2] - matrix[1][2] * matrix[2][0])
            + matrix[0][2] * (matrix[1][0] * matrix[2][1] - matrix[1][1] * matrix[2][0])
        )
        if abs(determinant) < 1e-10:
            raise ValueError("Transform matrix is singular")
        return value


class PatchRecord(Gate1Model):
    bbox: list[int] = Field(min_length=4, max_length=4)
    image_path: str
    mask_path: str
    feather_radius: int = Field(default=0, ge=0, le=64)
    residual_path: str | None = None

    _validate_image_path = field_validator("image_path")(_safe_member_path)
    _validate_mask_path = field_validator("mask_path")(_safe_member_path)

    @field_validator("bbox")
    @classmethod
    def valid_bbox(cls, value: list[int]) -> list[int]:
        if value[0] < 0 or value[1] < 0 or value[2] <= 0 or value[3] <= 0:
            raise ValueError("Patch bbox must be [x>=0, y>=0, width>0, height>0]")
        return value


class FrameRecord(Gate1Model):
    index: int = Field(ge=0)
    original_filename: str = Field(min_length=1)
    output_width: int = Field(gt=0)
    output_height: int = Field(gt=0)
    transform: TransformRecord
    patches: list[PatchRecord]

    @model_validator(mode="after")
    def patches_inside_output(self) -> FrameRecord:
        for patch in self.patches:
            x, y, width, height = patch.bbox
            if x + width > self.output_width or y + height > self.output_height:
                raise ValueError(f"Patch bbox is outside frame {self.index}")
            if x == 0 and y == 0 and width == self.output_width and height == self.output_height:
                raise ValueError("A full-canvas change patch is not allowed")
        return self


class PhotoFoldManifest(Gate1Model):
    format: Literal["photofold"] = "photofold"
    version: Literal["0.1"] = "0.1"
    created_at: datetime
    reference_frame_index: int = Field(ge=0)
    required_codecs: list[Literal["webp", "png"]]
    base: BaseRecord
    frames: list[FrameRecord] = Field(min_length=5, max_length=20)
    assets: list[AssetRecord]
    analysis_path: str
    metrics_path: str
    semantic_analysis_path: None = None

    _validate_analysis_path = field_validator("analysis_path")(_safe_member_path)
    _validate_metrics_path = field_validator("metrics_path")(_safe_member_path)

    @model_validator(mode="after")
    def internally_consistent(self) -> PhotoFoldManifest:
        indices = [frame.index for frame in self.frames]
        if indices != list(range(len(self.frames))):
            raise ValueError("Frame indices must be ordered and contiguous from zero")
        if self.reference_frame_index not in indices:
            raise ValueError("Reference frame index is outside the frame list")
        asset_paths = [asset.path for asset in self.assets]
        if len(asset_paths) != len(set(asset_paths)):
            raise ValueError("Asset inventory contains duplicate paths")
        referenced = {self.base.path, self.analysis_path, self.metrics_path}
        for frame in self.frames:
            referenced.add(f"frames/{frame.index:03d}/frame.json")
            for patch in frame.patches:
                referenced.add(patch.image_path)
                referenced.add(patch.mask_path)
        missing = referenced - set(asset_paths)
        if missing:
            raise ValueError(f"Manifest inventory omits referenced assets: {sorted(missing)}")
        return self
