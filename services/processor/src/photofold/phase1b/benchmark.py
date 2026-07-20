"""Sequential per-dataset Phase 1B compression experiment."""

from __future__ import annotations

import json
import os
import platform
import shutil
import sys
import time
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

import numpy as np
from PIL import features

from photofold.doctor import run_doctor
from photofold.gate1.alignment import AlignmentFailure, select_reference_and_align
from photofold.gate1.bundle import decode_package_frame, verify_package
from photofold.gate1.images import (
    difference_heatmap,
    load_rgb,
    rgb_psnr,
    rgb_ssim,
    sha256_file,
    write_gray_png,
    write_rgb_png,
)
from photofold.gate1.treatment import (
    build_treatment_package,
    load_gate1_config,
    selected_parameters,
    write_alignment_overlays,
)
from photofold.phase1b.baseline import (
    MATCHED_QUALITIES,
    run_fixed_control,
    run_matched_sweep,
    serialize_psnr,
)
from photofold.phase1b.datasets import (
    source_snapshot,
    source_snapshot_matches,
    validate_phase1b_dataset,
)
from photofold.phase1b.models import (
    IndependentWebPPoint,
    IntegrityCheck,
    PackageMemberResult,
    Phase1BDatasetResult,
    PsnrValue,
)


class Phase1BBenchmarkError(RuntimeError):
    """Raised when a dataset cannot produce complete Phase 1B evidence."""


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _prepare_output(output_directory: Path) -> None:
    output_directory.mkdir(parents=True, exist_ok=True)
    for directory_name in (
        "reconstructions",
        "heatmaps",
        "masks",
        "alignment-overlays",
    ):
        directory = output_directory / directory_name
        if directory.exists():
            shutil.rmtree(directory)
        directory.mkdir(parents=True)
    for filename in (
        "benchmark.json",
        "dataset-validation.json",
        "independent-webp-curve.json",
        "moment.photofold",
        "package-inventory.json",
        "package-verification.json",
    ):
        path = output_directory / filename
        if path.exists():
            path.unlink()


def _runtime_environment() -> dict[str, Any]:
    doctor = run_doctor()
    return {
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "executable": sys.executable,
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "packages": doctor["packages"],
        "webp_available": doctor["checks"]["webp_available"],
        "webp_roundtrip": doctor["checks"]["webp_roundtrip"],
        "webp_encoder_version": features.version_module("webp"),
        "clock": "time.perf_counter_ns",
        "timing_units": "milliseconds",
        "warmup_policy": "cold process; no deliberate warm-up",
        "dataset_execution": "sequential",
        "control_execution": "sequential ascending quality",
        "timing_comparability_note": (
            "Wall-clock observations are machine-specific and are not correctness gates."
        ),
        "photofold_package_version": version("photofold-processor"),
    }


def _psnr_aggregates(values: list[float]) -> tuple[PsnrValue, PsnrValue]:
    return serialize_psnr(float(np.mean(values))), serialize_psnr(float(np.min(values)))


def _quality_summary(per_frame: list[dict[str, Any]]) -> dict[str, Any]:
    ssim_values = [float(frame["ssim"]) for frame in per_frame]
    psnr_values = [float(frame["psnr_db_float"]) for frame in per_frame]
    mean_psnr, minimum_psnr = _psnr_aggregates(psnr_values)
    return {
        "mean_ssim": float(np.mean(ssim_values)),
        "minimum_ssim": float(np.min(ssim_values)),
        "mean_psnr_db": mean_psnr.model_dump(mode="json"),
        "minimum_psnr_db": minimum_psnr.model_dump(mode="json"),
    }


def _alignment_evidence(alignment: dict[str, Any]) -> dict[str, Any]:
    return {
        "reference_candidates": alignment["reference_candidates"],
        "model_comparison": alignment["model_comparison"],
        "transforms": [
            {
                **{key: value for key, value in transform.items() if key != "matrix"},
                "reference_to_target": np.asarray(transform["matrix"])
                .reshape(-1)
                .tolist(),
            }
            for transform in alignment["transforms"]
        ],
    }


def _member_role(path: str) -> str:
    if path == "manifest.json":
        return "manifest"
    if path == "base.webp":
        return "shared-base"
    if path == "metadata/analysis.json":
        return "alignment-analysis"
    if path == "metadata/metrics.json":
        return "treatment-metrics"
    if path.endswith("/frame.json"):
        return "frame-metadata"
    if path.endswith("-mask.png"):
        return "patch-mask"
    if "/patches/" in path and path.endswith(".webp"):
        return "patch-image"
    return "other"


def _package_members(verification: dict[str, Any]) -> list[PackageMemberResult]:
    return [
        PackageMemberResult(
            path=member["path"],
            role=_member_role(member["path"]),
            stored_bytes=member["compressed_bytes"],
            uncompressed_bytes=member["bytes"],
            sha256=member["sha256"],
        )
        for member in sorted(verification["members"], key=lambda item: item["path"])
    ]


def _signed_comparison(reference_bytes: int, package_bytes: int) -> dict[str, Any]:
    saved_bytes = reference_bytes - package_bytes
    return {
        "reference_bytes": reference_bytes,
        "photofold_bytes": package_bytes,
        "signed_bytes_saved": saved_bytes,
        "signed_savings_percent": saved_bytes / reference_bytes * 100,
        "result": "win" if saved_bytes > 0 else "loss" if saved_bytes < 0 else "tie",
    }


def _check(
    identifier: str,
    label: str,
    passed: bool,
    detail: str,
    *,
    required: bool = True,
) -> IntegrityCheck:
    return IntegrityCheck(
        id=identifier,
        label=label,
        passed=passed,
        required_for_machine_pass=required,
        detail=detail,
    )


def _baseline_frame(point: IndependentWebPPoint, index: int) -> dict[str, Any]:
    frame = point.per_frame[index]
    return {
        "bytes": frame.bytes,
        "ssim": frame.ssim,
        "psnr_db": frame.psnr_db.model_dump(mode="json"),
    }


def run_phase1b_dataset(
    dataset_path: str | Path,
    config_path: str | Path,
    output_path: str | Path,
    *,
    matched_qualities: tuple[int, ...] | list[int] = MATCHED_QUALITIES,
    require_full_curve: bool = True,
) -> dict[str, Any]:
    """Run one dataset without tuning or reusing encoder intermediates."""
    dataset_start = time.perf_counter_ns()
    dataset_directory = Path(dataset_path).expanduser().resolve()
    config_file = Path(config_path).expanduser().resolve()
    output_directory = Path(output_path).expanduser().resolve()
    _prepare_output(output_directory)

    validation = validate_phase1b_dataset(dataset_directory)
    _write_json(output_directory / "dataset-validation.json", validation)
    if validation["status"] != "pass":
        _write_json(
            output_directory / "benchmark.json",
            {
                "schema_version": "1.0",
                "status": "fail",
                "dataset_id": validation.get("dataset_id", dataset_directory.name),
                "stage": "dataset_validation",
                "error": "strict dataset validation failed",
                "validation": validation,
                "frame_dispositions": validation.get("frames", []),
            },
        )
        raise Phase1BBenchmarkError(
            f"Dataset validation failed for {dataset_directory}: {validation['errors']}"
        )
    source_before = source_snapshot(validation)
    config, config_sha256 = load_gate1_config(config_file)
    parameters = selected_parameters(config)
    filenames = [frame["path"] for frame in validation["frames"]]
    images = [load_rgb(dataset_directory / filename) for filename in filenames]

    encode_start = time.perf_counter_ns()
    try:
        alignment = select_reference_and_align(images)
    except AlignmentFailure as error:
        failure = {
            "schema_version": "1.0",
            "status": "fail",
            "dataset_id": validation["dataset_id"],
            "stage": "alignment",
            "error": str(error),
            "failed_frame_indices": error.frame_indices,
            "frame_dispositions": [
                {
                    "index": frame["index"],
                    "path": frame["path"],
                    "disposition": (
                        "rejected" if frame["index"] in error.frame_indices else "accepted"
                    ),
                    "reason": (
                        "selected_reference_alignment_failed"
                        if frame["index"] in error.frame_indices
                        else "validated_before_alignment_failure"
                    ),
                }
                for frame in validation["frames"]
            ],
        }
        _write_json(output_directory / "benchmark.json", failure)
        raise Phase1BBenchmarkError(str(error)) from error

    package_path = output_directory / "moment.photofold"
    package = build_treatment_package(
        images=images,
        filenames=filenames,
        alignment=alignment,
        parameters=parameters,
        original_total_bytes=validation["total_bytes"],
        output_path=package_path,
    )
    photofold_encoding_ms = (time.perf_counter_ns() - encode_start) / 1_000_000

    verification_start = time.perf_counter_ns()
    verification = verify_package(package_path)
    verification_ms = (time.perf_counter_ns() - verification_start) / 1_000_000
    _write_json(output_directory / "package-verification.json", verification)

    reconstructions: list[np.ndarray] = []
    reconstruction_frame_ms: list[float] = []
    reconstruction_start = time.perf_counter_ns()
    for index in range(len(images)):
        frame_start = time.perf_counter_ns()
        reconstructions.append(decode_package_frame(package_path, index))
        reconstruction_frame_ms.append(
            (time.perf_counter_ns() - frame_start) / 1_000_000
        )
    reconstruction_ms = (time.perf_counter_ns() - reconstruction_start) / 1_000_000

    photofold_metrics: list[dict[str, Any]] = []
    for index, (original, reconstruction) in enumerate(
        zip(images, reconstructions, strict=True)
    ):
        psnr = rgb_psnr(original, reconstruction)
        photofold_metrics.append(
            {
                "index": index,
                "ssim": rgb_ssim(original, reconstruction),
                "psnr_db": serialize_psnr(psnr).model_dump(mode="json"),
                "psnr_db_float": psnr,
            }
        )
    photofold_quality = _quality_summary(photofold_metrics)

    fixed_webp = run_fixed_control(images)
    matching_input = [
        {
            "index": frame["index"],
            "ssim": frame["ssim"],
            "psnr_db": frame["psnr_db_float"],
        }
        for frame in photofold_metrics
    ]
    matched_webp = run_matched_sweep(images, matching_input, qualities=matched_qualities)
    _write_json(
        output_directory / "independent-webp-curve.json",
        matched_webp.model_dump(mode="json"),
    )

    write_alignment_overlays(
        output_directory,
        images,
        alignment["reference_frame_index"],
        alignment["transforms"],
    )
    per_frame: list[dict[str, Any]] = []
    for index, (original, reconstruction, metric) in enumerate(
        zip(images, reconstructions, photofold_metrics, strict=True)
    ):
        reconstruction_relative = f"reconstructions/frame-{index:03d}.png"
        heatmap_relative = f"heatmaps/frame-{index:03d}.png"
        mask_relative = f"masks/frame-{index:03d}.png"
        write_rgb_png(output_directory / reconstruction_relative, reconstruction)
        write_rgb_png(
            output_directory / heatmap_relative,
            difference_heatmap(original, reconstruction),
        )
        write_gray_png(output_directory / mask_relative, package["debug_masks"][index])
        region = package["region_metrics"][index]
        matched_frame = (
            _baseline_frame(matched_webp.selected, index)
            if matched_webp.selected is not None
            else None
        )
        per_frame.append(
            {
                "index": index,
                "filename": filenames[index],
                "original_bytes": validation["frames"][index]["bytes"],
                "accepted": True,
                "reconstructed": True,
                "width": int(reconstruction.shape[1]),
                "height": int(reconstruction.shape[0]),
                "ssim": metric["ssim"],
                "psnr_db": metric["psnr_db"],
                "fixed_webp": _baseline_frame(fixed_webp, index),
                "matched_webp": matched_frame,
                "reconstruction_ms": reconstruction_frame_ms[index],
                "patch_count": region["patch_count"],
                "changed_region_percent": region["changed_region_percent"],
                "shared_region_percent": region["shared_region_percent"],
                "artifacts": {
                    "original": str(dataset_directory / filenames[index]),
                    "reconstruction": reconstruction_relative,
                    "heatmap": heatmap_relative,
                    "mask": mask_relative,
                    "alignment_overlay": (
                        f"alignment-overlays/frame-{index:03d}.png"
                    ),
                },
            }
        )

    source_after_validation = validate_phase1b_dataset(dataset_directory)
    source_after = source_snapshot(source_after_validation)
    source_immutability_pass = source_snapshot_matches(
        source_after_validation, source_before
    )
    package_bytes = package_path.stat().st_size
    package_sha256 = sha256_file(package_path)
    members = _package_members(verification)
    member_payload_bytes = sum(member.uncompressed_bytes for member in members)
    member_stored_bytes = sum(member.stored_bytes for member in members)
    container_overhead_bytes = package_bytes - member_payload_bytes
    package_overhead = {
        "member_count": len(members),
        "member_payload_bytes": member_payload_bytes,
        "member_stored_bytes": member_stored_bytes,
        "container_overhead_bytes": container_overhead_bytes,
        "container_overhead_percent": container_overhead_bytes / package_bytes * 100,
        "reconciles": member_payload_bytes + container_overhead_bytes == package_bytes,
    }
    _write_json(
        output_directory / "package-inventory.json",
        {
            "package_bytes": package_bytes,
            "package_sha256": package_sha256,
            "overhead": package_overhead,
            "members": [member.model_dump(mode="json") for member in members],
        },
    )

    expected_width = validation["normalized_dimensions"]["width"]
    expected_height = validation["normalized_dimensions"]["height"]
    alignment_threshold_pass = all(
        transform["inlier_ratio"] >= float(config["alignment"]["min_inlier_ratio"])
        and transform["median_reprojection_error"]
        <= float(config["alignment"]["max_median_reprojection_error"])
        for transform in alignment["transforms"]
    )
    full_curve_pass = list(matched_qualities) == list(MATCHED_QUALITIES)
    checks = [
        _check(
            "dataset_validation",
            "Strict dataset validation",
            validation["status"] == "pass",
            f"{validation['frame_count']} manifest-ordered frames validated",
        ),
        _check(
            "accepted_count",
            "All canonical frames accepted",
            len(per_frame) == validation["frame_count"] and len(per_frame) >= 5,
            f"{len(per_frame)} of {validation['frame_count']} frames accepted",
        ),
        _check(
            "closed_package_verification",
            "Closed package integrity",
            verification["status"] == "pass"
            and all(verification["checks"].values()),
            "Safe paths, schema, inventory, checksums, transforms, and codecs verified",
        ),
        _check(
            "package_only_reconstruction",
            "Package-only reconstruction",
            len(reconstructions) == len(images)
            and verification["package_only_decode"],
            f"{len(reconstructions)} frames decoded with archive and frame index only",
        ),
        _check(
            "dimensions",
            "Expected reconstruction dimensions",
            all(
                frame["width"] == expected_width and frame["height"] == expected_height
                for frame in per_frame
            ),
            f"Every reconstruction is {expected_width}x{expected_height}",
        ),
        _check(
            "source_immutability",
            "Source checksums unchanged",
            source_immutability_pass,
            "Pre/post source byte counts and SHA-256 values are identical",
        ),
        _check(
            "fixed_webp_q70",
            "Fixed independent-WebP control",
            fixed_webp.quality == 70 and len(fixed_webp.per_frame) == len(images),
            "Every normalized frame was independently encoded and reopened at q70",
        ),
        _check(
            "matched_curve",
            "Exhaustive quality-matched WebP curve",
            full_curve_pass or not require_full_curve,
            (
                "All integer qualities 1 through 100 are present"
                if full_curve_pass
                else f"Fixture-only qualities were {list(matched_qualities)}"
            ),
        ),
        _check(
            "matched_quality",
            "Per-frame SSIM and PSNR match",
            matched_webp.status == "matched",
            (
                f"Selected q{matched_webp.selected.quality} after per-frame matching"
                if matched_webp.selected is not None
                else "No q1-q100 point matched every PhotoFold frame"
            ),
        ),
        _check(
            "package_accounting",
            "Package size and member accounting",
            package_bytes == verification["package_total_bytes"]
            and package_sha256 == verification["package_sha256"]
            and package_overhead["reconciles"],
            f"{len(members)} members reconcile to {package_bytes} closed-archive bytes",
        ),
        _check(
            "alignment_thresholds",
            "Gate 1 alignment threshold context",
            alignment_threshold_pass,
            "Recorded against the committed Gate 1 alignment thresholds",
            required=False,
        ),
        _check(
            "source_savings",
            "Smaller than original sources",
            package_bytes < validation["total_bytes"],
            "Scientific storage outcome; not an integrity prerequisite",
            required=False,
        ),
        _check(
            "fixed_webp_comparison",
            "Smaller than fixed q70 WebP",
            package_bytes < fixed_webp.total_bytes,
            "Scientific storage outcome; not an integrity prerequisite",
            required=False,
        ),
        _check(
            "matched_webp_comparison",
            "Smaller than quality-matched WebP",
            matched_webp.selected is not None
            and package_bytes < matched_webp.selected.total_bytes,
            "Scientific relational outcome; evaluated again by aggregate decision rules",
            required=False,
        ),
    ]
    failed_required_checks = [
        check.id for check in checks if check.required_for_machine_pass and not check.passed
    ]
    machine_pass = not failed_required_checks
    matched_comparison = (
        _signed_comparison(matched_webp.selected.total_bytes, package_bytes)
        if matched_webp.selected is not None
        else None
    )
    storage = {
        "versus_originals": _signed_comparison(validation["total_bytes"], package_bytes),
        "versus_fixed_webp": _signed_comparison(fixed_webp.total_bytes, package_bytes),
        "versus_matched_webp": matched_comparison,
    }
    timings = {
        "clock": "time.perf_counter_ns",
        "units": "milliseconds",
        "photofold_encoding_ms": photofold_encoding_ms,
        "package_verification_ms": verification_ms,
        "reconstruction_total_ms": reconstruction_ms,
        "reconstruction_per_frame_ms": reconstruction_frame_ms,
        "fixed_webp": fixed_webp.timing.model_dump(mode="json"),
        "matched_webp_sweep_ms": matched_webp.sweep_timing_ms,
        "matched_webp_encoding_ms": sum(
            point.timing.encoding_ms for point in matched_webp.curve
        ),
        "matched_webp_decode_measurement_ms": sum(
            point.timing.decode_measurement_ms for point in matched_webp.curve
        ),
        "dataset_wall_ms": (time.perf_counter_ns() - dataset_start) / 1_000_000,
        "excludes": ["aggregate calculation", "HTML report rendering"],
    }
    frame_dispositions = [
        {
            "index": frame["index"],
            "path": frame["path"],
            "disposition": "accepted",
            "reason": "validated_and_aligned",
        }
        for frame in validation["frames"]
    ]
    result = Phase1BDatasetResult(
        schema_version="1.0",
        status="pass" if machine_pass else "fail",
        run_at=datetime.now(UTC),
        dataset_id=validation["dataset_id"],
        scenario_category=validation["scenario_category"],
        dataset_path=str(dataset_directory),
        manifest_sha256=validation["manifest_sha256"],
        validation=validation,
        source_before=source_before,
        source_after=source_after,
        source_immutability_pass=source_immutability_pass,
        config_path=str(config_file),
        config_sha256=config_sha256,
        parameters=parameters,
        environment=_runtime_environment(),
        frame_dispositions=frame_dispositions,
        accepted_frame_count=len(per_frame),
        reconstructed_frame_count=len(reconstructions),
        original_total_bytes=validation["total_bytes"],
        fixed_webp=fixed_webp,
        matched_webp=matched_webp,
        photofold_package_bytes=package_bytes,
        photofold_package_sha256=package_sha256,
        storage=storage,
        reference_frame_index=alignment["reference_frame_index"],
        alignment=_alignment_evidence(alignment),
        per_frame=per_frame,
        quality={
            "photofold": photofold_quality,
            "fixed_webp": {
                "mean_ssim": fixed_webp.mean_ssim,
                "minimum_ssim": fixed_webp.minimum_ssim,
                "mean_psnr_db": fixed_webp.mean_psnr_db.model_dump(mode="json"),
                "minimum_psnr_db": fixed_webp.minimum_psnr_db.model_dump(mode="json"),
            },
            "matched_webp": (
                {
                    "mean_ssim": matched_webp.selected.mean_ssim,
                    "minimum_ssim": matched_webp.selected.minimum_ssim,
                    "mean_psnr_db": matched_webp.selected.mean_psnr_db.model_dump(
                        mode="json"
                    ),
                    "minimum_psnr_db": (
                        matched_webp.selected.minimum_psnr_db.model_dump(mode="json")
                    ),
                }
                if matched_webp.selected is not None
                else None
            ),
            "gate1_ssim_thresholds_context_only": config["quality"],
        },
        timings=timings,
        package_overhead=package_overhead,
        package_members=members,
        artifacts={
            "package": "moment.photofold",
            "validation": "dataset-validation.json",
            "package_verification": "package-verification.json",
            "package_inventory": "package-inventory.json",
            "independent_webp_curve": "independent-webp-curve.json",
        },
        checks=checks,
        machine_pass=machine_pass,
        human_visual_review_status="pending",
        failed_checks=failed_required_checks,
    )
    payload = result.model_dump(mode="json")
    _write_json(output_directory / "benchmark.json", payload)
    return payload
