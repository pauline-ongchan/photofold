"""Single-pass deterministic runner for the local Phase 4P prototype."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import ValidationError

from photofold.gate1.alignment import AlignmentFailure, select_reference_and_align
from photofold.gate1.bundle import (
    PackageValidationError,
    decode_all_package_frames,
    verify_package,
)
from photofold.gate1.images import (
    difference_heatmap,
    rgb_ssim,
    sha256_file,
    write_rgb_png,
)
from photofold.gate1.treatment import (
    build_treatment_package,
    load_gate1_config,
    selected_parameters,
)
from photofold.prototype.models import (
    AlignmentRecord,
    Dimensions,
    FrameArtifacts,
    PackageContents,
    PrototypeAnalysis,
    PrototypeError,
    PrototypeFrameResult,
    PrototypeInput,
    PrototypeResult,
    QualityResult,
    ReferenceCandidate,
    SourceSnapshot,
    StorageResult,
)

SUPPORTED_FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
DEFERRED_FIELDS = [
    "suitability_score",
    "estimated_shared_region_percent",
    "estimated_changing_region_percent",
    "camera_motion_assessment",
    "automatic_set_splitting",
    "alignment_based_per_frame_rejection",
]


class PrototypeRunError(ValueError):
    """User-safe workflow failure with a stable prototype error contract."""

    def __init__(
        self,
        code: str,
        message: str,
        stage: str,
        *,
        frame_indices: list[int] | None = None,
        retryable: bool = False,
        debug: str | None = None,
    ) -> None:
        super().__init__(message)
        self.detail = PrototypeError(
            code=code,
            message=message,
            stage=stage,
            frame_indices=frame_indices or [],
            retryable=retryable,
            debug=debug,
        )


def _inside_run(run_directory: Path, relative: str) -> Path:
    path = (run_directory / relative).resolve()
    try:
        path.relative_to(run_directory)
    except ValueError as error:
        raise PrototypeRunError(
            "UNSAFE_RUN_PATH",
            "A prototype artifact path escaped its isolated run workspace.",
            "validation",
        ) from error
    return path


def _load_input(run_directory: Path) -> PrototypeInput:
    try:
        return PrototypeInput.model_validate_json(
            _inside_run(run_directory, "input.json").read_bytes()
        )
    except FileNotFoundError as error:
        raise PrototypeRunError(
            "MOMENT_NOT_FOUND", "The local prototype run does not exist.", "service"
        ) from error
    except ValidationError as error:
        raise PrototypeRunError(
            "INVALID_FILE_COUNT",
            "Choose between 5 and 20 photos before analyzing this moment.",
            "upload",
            debug=str(error),
        ) from error


def _decode_sources(
    run_directory: Path, prototype_input: PrototypeInput
) -> tuple[list[SourceSnapshot], list[np.ndarray]]:
    frames: list[SourceSnapshot] = []
    images: list[np.ndarray] = []
    expected_dimensions: tuple[int, int] | None = None
    for frame in prototype_input.frames:
        path = _inside_run(run_directory, f"uploads/{frame.stored_filename}")
        try:
            path.relative_to(_inside_run(run_directory, "uploads"))
        except ValueError as error:
            raise PrototypeRunError(
                "UNSAFE_RUN_PATH",
                "An upload path escaped its isolated run workspace.",
                "upload",
                frame_indices=[frame.index],
            ) from error
        if not path.is_file() or path.is_symlink() or path.stat().st_size <= 0:
            raise PrototypeRunError(
                "IMAGE_DECODE_FAILED",
                f"{frame.original_filename} is missing or empty.",
                "preprocess",
                frame_indices=[frame.index],
            )
        try:
            with Image.open(path) as image:
                image_format = image.format
                if image_format not in SUPPORTED_FORMATS:
                    raise PrototypeRunError(
                        "UNSUPPORTED_FILE_TYPE",
                        f"{frame.original_filename} is not a decoded JPEG, PNG, or WebP image.",
                        "upload",
                        frame_indices=[frame.index],
                    )
                normalized = ImageOps.exif_transpose(image)
                normalized.load()
                if "A" in normalized.getbands():
                    alpha = normalized.getchannel("A")
                    if alpha.getextrema()[0] < 255:
                        raise PrototypeRunError(
                            "UNSUPPORTED_FILE_TYPE",
                            f"{frame.original_filename} has transparency that the P0 "
                            "package cannot preserve.",
                            "preprocess",
                            frame_indices=[frame.index],
                        )
                dimensions = normalized.size
                mode = normalized.mode
                rgb = np.asarray(normalized.convert("RGB"), dtype=np.uint8).copy()
        except PrototypeRunError:
            raise
        except (Image.DecompressionBombError, UnidentifiedImageError, OSError) as error:
            raise PrototypeRunError(
                "IMAGE_DECODE_FAILED",
                f"{frame.original_filename} could not be decoded safely.",
                "preprocess",
                frame_indices=[frame.index],
                debug=str(error),
            ) from error
        if expected_dimensions is None:
            expected_dimensions = dimensions
        elif dimensions != expected_dimensions:
            raise PrototypeRunError(
                "DIMENSIONS_INCOMPATIBLE",
                "All photos must have identical dimensions after orientation is normalized.",
                "preprocess",
                frame_indices=[frame.index],
                debug=f"expected={expected_dimensions}, actual={dimensions}",
            )
        frames.append(
            SourceSnapshot(
                index=frame.index,
                original_filename=frame.original_filename,
                stored_filename=frame.stored_filename,
                decoded_format=image_format,
                mime_type=SUPPORTED_FORMATS[image_format],
                mode=mode,
                bytes=path.stat().st_size,
                sha256=sha256_file(path),
                width=dimensions[0],
                height=dimensions[1],
                original_artifact=f"uploads/{frame.stored_filename}",
            )
        )
        images.append(rgb)
    return frames, images


def _alignment_records(alignment: dict[str, Any]) -> list[AlignmentRecord]:
    return [
        AlignmentRecord(
            frame_index=index,
            type=transform["type"],
            reference_to_target=np.asarray(transform["matrix"]).reshape(-1).tolist(),
            inlier_count=transform["inlier_count"],
            match_count=transform["match_count"],
            inlier_ratio=transform["inlier_ratio"],
            median_reprojection_error=transform["median_reprojection_error"],
            valid_overlap=transform["valid_overlap"],
        )
        for index, transform in enumerate(alignment["transforms"])
    ]


def analyze_prototype_run(
    run_path: str | Path, config_path: str | Path
) -> PrototypeAnalysis:
    run_directory = Path(run_path).resolve()
    prototype_input = _load_input(run_directory)
    sources, images = _decode_sources(run_directory, prototype_input)
    config, config_sha256 = load_gate1_config(config_path)
    reasons: list[str] = []
    reference_index: int | None = None
    reference_score: float | None = None
    candidates: list[ReferenceCandidate] = []
    records: list[AlignmentRecord] = []
    try:
        alignment = select_reference_and_align(images)
        reference_index = alignment["reference_frame_index"]
        candidates = [
            ReferenceCandidate.model_validate(item)
            for item in alignment["reference_candidates"]
        ]
        reference_score = next(item.score for item in candidates if item.index == reference_index)
        records = _alignment_records(alignment)
        minimum_inlier = float(config["alignment"]["min_inlier_ratio"])
        maximum_error = float(config["alignment"]["max_median_reprojection_error"])
        below_threshold = [
            item.frame_index
            for item in records
            if item.inlier_ratio < minimum_inlier
            or item.median_reprojection_error > maximum_error
        ]
        if below_threshold:
            reasons.append(
                "Frames "
                + ", ".join(str(index + 1) for index in below_threshold)
                + " did not meet the committed alignment thresholds."
            )
    except AlignmentFailure as error:
        reasons.append(str(error))
    except ValueError as error:
        reasons.append(f"Reference analysis could not establish a reliable alignment: {error}")
    foldable = not reasons and reference_index is not None and len(records) == len(sources)
    analysis = PrototypeAnalysis(
        analyzed_at=datetime.now(UTC),
        status="analyzed_foldable" if foldable else "analyzed_rejected",
        suitability="safe_to_fold" if foldable else "not_foldable",
        reasons=reasons or ["All frames passed deterministic validation and alignment thresholds."],
        source_frames=sources,
        original_total_bytes=sum(frame.bytes for frame in sources),
        normalized_dimensions=Dimensions(width=sources[0].width, height=sources[0].height),
        reference_frame_index=reference_index,
        reference_score=reference_score,
        reference_candidates=candidates,
        alignment=records,
        config_sha256=config_sha256,
        warnings=[
            "This local prototype evaluates one set at a time and does not persist restart state.",
            "Matched-quality relational savings remain evidenced by the accepted offline "
            "experiment, not this interactive run.",
        ],
        deferred_fields=DEFERRED_FIELDS,
    )
    _inside_run(run_directory, "analysis.json").write_text(
        analysis.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    return analysis


def _load_analysis(run_directory: Path) -> PrototypeAnalysis:
    try:
        return PrototypeAnalysis.model_validate_json(
            _inside_run(run_directory, "analysis.json").read_bytes()
        )
    except FileNotFoundError as error:
        raise PrototypeRunError(
            "INVALID_RUN_STATE", "Analyze this moment before folding it.", "service"
        ) from error
    except ValidationError as error:
        raise PrototypeRunError(
            "INVALID_RUN_STATE",
            "The saved analysis is invalid and cannot be folded.",
            "service",
            debug=str(error),
        ) from error


def _source_snapshot_matches(before: list[SourceSnapshot], after: list[SourceSnapshot]) -> bool:
    fields = ("index", "stored_filename", "bytes", "sha256", "width", "height", "decoded_format")
    return len(before) == len(after) and all(
        all(getattr(left, field) == getattr(right, field) for field in fields)
        for left, right in zip(before, after, strict=True)
    )


def _classification(path: str) -> str:
    if path.endswith("-mask.png"):
        return "mask"
    if "/patches/" in path and path.endswith(".webp"):
        return "patch"
    if path.startswith("metadata/"):
        return "metadata"
    return "other"


def _publish_latest(run_directory: Path) -> None:
    latest = run_directory.parents[1] / "latest"
    latest.mkdir(parents=True, exist_ok=True)
    for name in ["result.json", "moment.photofold"]:
        source = run_directory / name
        if source.is_file():
            shutil.copy2(source, latest / name)


def evaluated_status(*, quality_pass: bool, is_smaller: bool) -> str:
    if not quality_pass:
        return "failed_quality"
    if not is_smaller:
        return "complete_no_savings"
    return "complete"


def fold_prototype_run(
    run_path: str | Path, config_path: str | Path
) -> PrototypeResult:
    run_directory = Path(run_path).resolve()
    analysis = _load_analysis(run_directory)
    if analysis.status != "analyzed_foldable":
        raise PrototypeRunError(
            "INVALID_RUN_STATE",
            "This photo set did not pass analysis and cannot be folded.",
            "service",
        )
    prototype_input = _load_input(run_directory)
    current_sources, images = _decode_sources(run_directory, prototype_input)
    if not _source_snapshot_matches(analysis.source_frames, current_sources):
        raise PrototypeRunError(
            "CHECKSUM_MISMATCH",
            "One or more uploaded files changed after analysis. Analyze the set again.",
            "validation",
        )
    config, config_sha256 = load_gate1_config(config_path)
    if config_sha256 != analysis.config_sha256:
        raise PrototypeRunError(
            "INVALID_RUN_STATE",
            "The deterministic configuration changed after analysis. Analyze the set again.",
            "validation",
        )
    parameters = selected_parameters(config)
    transforms = [
        {
            "type": item.type,
            "matrix": np.asarray(item.reference_to_target, dtype=np.float64).reshape(3, 3),
            "inlier_count": item.inlier_count,
            "match_count": item.match_count,
            "inlier_ratio": item.inlier_ratio,
            "median_reprojection_error": item.median_reprojection_error,
            "valid_overlap": item.valid_overlap,
        }
        for item in analysis.alignment
    ]
    alignment = {
        "reference_frame_index": analysis.reference_frame_index,
        "reference_candidates": [item.model_dump() for item in analysis.reference_candidates],
        "model_comparison": [],
        "transforms": transforms,
        "width": analysis.normalized_dimensions.width,
        "height": analysis.normalized_dimensions.height,
    }
    package_path = _inside_run(run_directory, "moment.photofold")
    package = build_treatment_package(
        images=images,
        filenames=[frame.original_filename for frame in analysis.source_frames],
        alignment=alignment,
        parameters=parameters,
        original_total_bytes=analysis.original_total_bytes,
        output_path=package_path,
    )
    try:
        verification = verify_package(package_path)
        reconstructions = decode_all_package_frames(package_path)
    except PackageValidationError as error:
        raise PrototypeRunError(
            "PACKAGE_VALIDATION_FAILED",
            "The generated PhotoFold package did not pass integrity validation.",
            "package",
            debug=str(error),
        ) from error
    scores = [
        rgb_ssim(original, reconstruction)
        for original, reconstruction in zip(images, reconstructions, strict=True)
    ]
    minimum_threshold = float(config["quality"]["min_per_frame"])
    mean_threshold = float(config["quality"]["min_mean"])
    mean_ssim = float(np.mean(scores))
    minimum_ssim = float(np.min(scores))
    quality_pass = mean_ssim >= mean_threshold and minimum_ssim >= minimum_threshold
    frame_results: list[PrototypeFrameResult] = []
    for index, (source, original, reconstruction, score) in enumerate(
        zip(analysis.source_frames, images, reconstructions, scores, strict=True)
    ):
        reconstruction_relative = f"reconstructions/frame-{index:03d}.png"
        difference_relative = f"differences/frame-{index:03d}.png"
        write_rgb_png(_inside_run(run_directory, reconstruction_relative), reconstruction)
        write_rgb_png(
            _inside_run(run_directory, difference_relative),
            difference_heatmap(original, reconstruction),
        )
        region = package["region_metrics"][index]
        frame_results.append(
            PrototypeFrameResult(
                index=index,
                original_filename=source.original_filename,
                width=source.width,
                height=source.height,
                original_bytes=source.bytes,
                reconstructed=True,
                ssim=score,
                quality_threshold_pass=score >= minimum_threshold,
                patch_count=region["patch_count"],
                changed_region_percent=region["changed_region_percent"],
                shared_region_percent=region["shared_region_percent"],
                artifacts=FrameArtifacts(
                    original=source.original_artifact,
                    reconstruction=reconstruction_relative,
                    difference=difference_relative,
                ),
            )
        )
    package_bytes = package_path.stat().st_size
    byte_delta = analysis.original_total_bytes - package_bytes
    percent_change = byte_delta / analysis.original_total_bytes * 100
    smaller = byte_delta > 0
    status = evaluated_status(quality_pass=quality_pass, is_smaller=smaller)
    members = verification["members"]
    roles = [_classification(member["path"]) for member in members]
    result = PrototypeResult(
        completed_at=datetime.now(UTC),
        status=status,
        reference_frame_index=analysis.reference_frame_index,
        reconstructed_frame_count=len(reconstructions),
        storage=StorageResult(
            original_total_bytes=analysis.original_total_bytes,
            package_total_bytes=package_bytes,
            package_sha256=sha256_file(package_path),
            byte_delta=byte_delta,
            percent_change=percent_change,
            bytes_saved=max(byte_delta, 0),
            percent_saved=max(percent_change, 0),
            is_smaller_than_originals=smaller,
        ),
        quality=QualityResult(
            mean_ssim=mean_ssim,
            minimum_ssim=minimum_ssim,
            min_mean_threshold=mean_threshold,
            min_per_frame_threshold=minimum_threshold,
            threshold_pass=quality_pass,
        ),
        frames=frame_results,
        package_contents=PackageContents(
            member_count=len(members),
            frame_count=len(frame_results),
            patch_count=roles.count("patch"),
            mask_count=roles.count("mask"),
            metadata_count=roles.count("metadata"),
            member_payload_bytes=sum(member["bytes"] for member in members),
        ),
        package_artifact="moment.photofold",
        warnings=[
            *analysis.warnings,
            "Storage is compared with exact uploaded source bytes.",
            "This interactive run does not rerun the independent-WebP rate-distortion sweep.",
        ],
    )
    _inside_run(run_directory, "package-inventory.json").write_text(
        json.dumps(verification, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _inside_run(run_directory, "result.json").write_text(
        result.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    _publish_latest(run_directory)
    return result


def failed_result(run_path: str | Path, error: PrototypeError) -> PrototypeResult:
    run_directory = Path(run_path).resolve()
    analysis = _load_analysis(run_directory)
    frames = [
        PrototypeFrameResult(
            index=frame.index,
            original_filename=frame.original_filename,
            width=frame.width,
            height=frame.height,
            original_bytes=frame.bytes,
            reconstructed=False,
            artifacts=FrameArtifacts(original=frame.original_artifact),
        )
        for frame in analysis.source_frames
    ]
    result = PrototypeResult(
        completed_at=datetime.now(UTC),
        status="failed",
        reference_frame_index=analysis.reference_frame_index,
        reconstructed_frame_count=0,
        storage=None,
        quality=None,
        frames=frames,
        package_contents=None,
        package_artifact=None,
        warnings=analysis.warnings,
        error=error,
    )
    _inside_run(run_directory, "result.json").write_text(
        result.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    _publish_latest(run_directory)
    return result
