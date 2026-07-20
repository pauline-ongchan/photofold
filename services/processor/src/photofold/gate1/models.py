"""Strict package models for the Gate 1 PhotoFold artifact."""

from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path, PurePosixPath
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


class NormalizedDimensions(Gate1Model):
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class TransformRecord(Gate1Model):
    type: Literal["identity", "affine", "homography"]
    reference_to_target: list[float] = Field(min_length=9, max_length=9)
    interpolation: Literal["linear"] = "linear"
    border_mode: Literal["constant"] = "constant"
    inlier_count: int = Field(ge=0)
    inlier_ratio: float = Field(ge=0, le=1)
    median_reprojection_error: float = Field(ge=0)
    reprojection_error_units: Literal[
        "analysis_pixels", "legacy_full_resolution_pixels"
    ]
    reprojection_error_threshold: float | None = Field(default=None, gt=0)
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


class IndependentSourceRecord(Gate1Model):
    path: str
    decoded_format: Literal["JPEG", "PNG", "WEBP"]

    _validate_path = field_validator("path")(_safe_member_path)


class FrameRecord(Gate1Model):
    index: int = Field(ge=0)
    original_filename: str = Field(min_length=1)
    output_width: int = Field(gt=0)
    output_height: int = Field(gt=0)
    normalized_dimensions: NormalizedDimensions
    storage_mode: Literal["shared_reference", "shared_delta", "independent_source"]
    transform: TransformRecord | None
    independent_source: IndependentSourceRecord | None = None
    patches: list[PatchRecord]

    @model_validator(mode="after")
    def patches_inside_output(self) -> FrameRecord:
        if (
            self.normalized_dimensions.width != self.output_width
            or self.normalized_dimensions.height != self.output_height
        ):
            raise ValueError("Normalized dimensions must match the output canvas")
        if self.storage_mode == "independent_source":
            if self.independent_source is None or self.transform is not None or self.patches:
                raise ValueError(
                    "Independent frames require one source and no transform or patches"
                )
        elif self.independent_source is not None or self.transform is None:
            raise ValueError(
                "Shared frames require a transform and cannot reference an independent source"
            )
        if self.storage_mode == "shared_reference" and (
            self.transform is None or self.transform.type != "identity" or self.patches
        ):
            raise ValueError(
                "The shared reference requires an identity transform and no patches"
            )
        for patch in self.patches:
            x, y, width, height = patch.bbox
            if x + width > self.output_width or y + height > self.output_height:
                raise ValueError(f"Patch bbox is outside frame {self.index}")
            if x == 0 and y == 0 and width == self.output_width and height == self.output_height:
                raise ValueError("A full-canvas change patch is not allowed")
        return self


class PhotoFoldManifest(Gate1Model):
    format: Literal["photofold"] = "photofold"
    version: Literal["0.2"] = "0.2"
    created_at: datetime
    strategy: Literal["shared_scene", "hybrid", "independent_only"]
    shared_frame_count: int = Field(ge=0, le=20)
    fallback_frame_count: int = Field(ge=0, le=20)
    reference_frame_index: int | None = Field(default=None, ge=0)
    required_codecs: list[Literal["jpeg", "webp", "png"]]
    base: BaseRecord | None
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
        shared_frames = [
            frame for frame in self.frames if frame.storage_mode != "independent_source"
        ]
        fallback_frames = [
            frame for frame in self.frames if frame.storage_mode == "independent_source"
        ]
        if self.shared_frame_count != len(shared_frames) or self.fallback_frame_count != len(
            fallback_frames
        ):
            raise ValueError("Manifest strategy counts disagree with frame storage modes")
        if self.shared_frame_count + self.fallback_frame_count != len(self.frames):
            raise ValueError("Manifest strategy counts do not cover every frame")
        references = [
            frame for frame in self.frames if frame.storage_mode == "shared_reference"
        ]
        if self.strategy == "independent_only":
            if shared_frames or self.base is not None or self.reference_frame_index is not None:
                raise ValueError("Independent-only packages cannot contain a shared base")
        else:
            if len(shared_frames) < 2 or self.base is None or len(references) != 1:
                raise ValueError("Shared and hybrid packages require a useful shared group")
            if self.reference_frame_index != references[0].index:
                raise ValueError("Reference index does not identify the shared reference")
            expected_strategy = "shared_scene" if not fallback_frames else "hybrid"
            if self.strategy != expected_strategy:
                raise ValueError("Manifest strategy disagrees with frame storage modes")
        asset_paths = [asset.path for asset in self.assets]
        if len(asset_paths) != len(set(asset_paths)):
            raise ValueError("Asset inventory contains duplicate paths")
        referenced = {self.analysis_path, self.metrics_path}
        if self.base is not None:
            referenced.add(self.base.path)
        for frame in self.frames:
            frame_root = f"frames/{frame.index:03d}"
            referenced.add(f"{frame_root}/frame.json")
            if frame.independent_source is not None:
                if not frame.independent_source.path.startswith(f"{frame_root}/source."):
                    raise ValueError("Independent source path is outside its frame directory")
                referenced.add(frame.independent_source.path)
            for patch in frame.patches:
                if not patch.image_path.startswith(f"{frame_root}/patches/") or not (
                    patch.mask_path.startswith(f"{frame_root}/patches/")
                ):
                    raise ValueError("Patch path is outside its frame directory")
                referenced.add(patch.image_path)
                referenced.add(patch.mask_path)
        if referenced != set(asset_paths):
            missing = sorted(referenced - set(asset_paths))
            unexpected = sorted(set(asset_paths) - referenced)
            raise ValueError(
                f"Manifest inventory must exactly match referenced assets; "
                f"missing={missing}, unexpected={unexpected}"
            )
        required_codecs: set[str] = set()
        if self.base is not None:
            required_codecs.add("webp")
        for frame in self.frames:
            if frame.patches:
                required_codecs.update(("webp", "png"))
            if frame.independent_source is not None:
                required_codecs.add(frame.independent_source.decoded_format.lower())
        if set(self.required_codecs) != required_codecs:
            raise ValueError("Required codecs do not exactly match package members")
        return self


def export_photofold_schema(output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(PhotoFoldManifest.model_json_schema(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path
