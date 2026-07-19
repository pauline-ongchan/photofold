"""Gate 1 compression benchmark orchestration."""

from __future__ import annotations

import json
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from photofold.dataset import validate_dataset
from photofold.gate1.alignment import select_reference_and_align, warp_reference
from photofold.gate1.bundle import (
    build_package,
    decode_all_package_frames,
    export_package_frame,
    verify_package,
)
from photofold.gate1.images import (
    decode_rgb,
    difference_heatmap,
    encode_webp,
    load_rgb,
    rgb_ssim,
    sha256_file,
    write_gray_png,
    write_rgb_png,
)
from photofold.gate1.report import generate_report


def _load_config(path: Path) -> tuple[dict[str, Any], str]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Gate 1 config must be a YAML object")
    return payload, sha256_file(path)


def _parameters(config: dict[str, Any]) -> dict[str, int]:
    selected = config.get("selected", {})
    quality_sweep = config["codec"]["quality_sweep"]
    threshold_sweep = config["change_mask"]["pixel_threshold_sweep"]
    dilation_sweep = config["change_mask"]["dilation_radius_sweep"]
    feather_sweep = config["change_mask"]["feather_radius_sweep"]
    return {
        "base_quality": int(selected.get("base_quality", quality_sweep[1])),
        "patch_quality": int(selected.get("patch_quality", quality_sweep[1])),
        "pixel_threshold": int(selected.get("pixel_threshold", threshold_sweep[-1])),
        "dilation_radius": int(selected.get("dilation_radius", dilation_sweep[0])),
        "feather_radius": int(selected.get("feather_radius", feather_sweep[0])),
        "minimum_component_area": int(selected.get("minimum_component_area", 256)),
        "tile_size": int(selected.get("tile_size", 384)),
        "patch_margin": int(selected.get("patch_margin", 2)),
        "maximum_patches_per_frame": int(selected.get("maximum_patches_per_frame", 64)),
    }


def _control_curve(images: list[np.ndarray], qualities: list[int]) -> list[dict[str, Any]]:
    curve = []
    for quality in qualities:
        frame_results = []
        total = 0
        for index, image in enumerate(images):
            payload = encode_webp(image, quality)
            decoded = decode_rgb(payload)
            score = rgb_ssim(image, decoded)
            total += len(payload)
            frame_results.append({"index": index, "bytes": len(payload), "ssim": score})
        scores = [frame["ssim"] for frame in frame_results]
        curve.append(
            {
                "quality": quality,
                "total_bytes": total,
                "mean_ssim": float(np.mean(scores)),
                "minimum_ssim": float(np.min(scores)),
                "per_frame": frame_results,
            }
        )
    return curve


def _control_qualities(config: dict[str, Any]) -> list[int]:
    codec = config["codec"]
    if "independent_quality_range" in codec:
        configured = codec["independent_quality_range"]
        minimum = int(configured["min"])
        maximum = int(configured["max"])
        step = int(configured.get("step", 1))
        if minimum < 1 or maximum > 100 or minimum > maximum or step < 1:
            raise ValueError("Independent WebP quality range must be within 1..100")
        return list(range(minimum, maximum + 1, step))
    return [
        int(value)
        for value in codec.get("independent_quality_sweep", codec["quality_sweep"])
    ]


def _matched_control(
    curve: list[dict[str, Any]], mean_ssim: float, minimum_ssim: float
) -> tuple[dict[str, Any], bool]:
    matching = [
        point
        for point in curve
        if point["mean_ssim"] >= mean_ssim and point["minimum_ssim"] >= minimum_ssim
    ]
    if matching:
        return min(matching, key=lambda point: point["total_bytes"]), True
    return max(curve, key=lambda point: (point["mean_ssim"], point["minimum_ssim"])), False


def _trial(
    images: list[np.ndarray],
    filenames: list[str],
    alignment: dict[str, Any],
    parameters: dict[str, int],
    original_total_bytes: int,
    control_curve: list[dict[str, Any]],
    package_path: Path,
) -> dict[str, Any]:
    package = build_package(
        images=images,
        filenames=filenames,
        reference_index=alignment["reference_frame_index"],
        transforms=alignment["transforms"],
        parameters=parameters,
        analysis={key: value for key, value in alignment.items() if key != "transforms"},
        original_total_bytes=original_total_bytes,
        output_path=package_path,
    )
    package_check = verify_package(package_path)
    reconstructions = decode_all_package_frames(package_path)
    scores = [
        rgb_ssim(original, reconstruction)
        for original, reconstruction in zip(images, reconstructions, strict=True)
    ]
    mean_ssim = float(np.mean(scores))
    minimum_ssim = float(np.min(scores))
    matched_control, control_matched = _matched_control(control_curve, mean_ssim, minimum_ssim)
    package_bytes = package_path.stat().st_size
    return {
        "parameters": parameters,
        "package": package,
        "package_check": package_check,
        "reconstructions": reconstructions,
        "scores": scores,
        "mean_ssim": mean_ssim,
        "minimum_ssim": minimum_ssim,
        "matched_control": matched_control,
        "control_matched": control_matched,
        "storage_reduction_pass": package_bytes < original_total_bytes,
        "relational_hypothesis_pass": control_matched
        and package_bytes < matched_control["total_bytes"],
    }


def _sweep_variants(
    config: dict[str, Any], selected: dict[str, int]
) -> list[tuple[str, dict[str, int]]]:
    variants: list[tuple[str, dict[str, int]]] = []

    def add(label: str, **changes: int) -> None:
        parameters = {**selected, **changes}
        signature = tuple(sorted(parameters.items()))
        if not any(tuple(sorted(existing.items())) == signature for _, existing in variants):
            variants.append((label, parameters))

    for quality in config["codec"]["quality_sweep"]:
        add(f"codec q{quality}", base_quality=quality, patch_quality=quality)
    for threshold in config["change_mask"]["pixel_threshold_sweep"]:
        add(f"difference threshold {threshold}", pixel_threshold=threshold)
    for radius in config["change_mask"]["dilation_radius_sweep"]:
        add(f"dilation radius {radius}", dilation_radius=radius)
    for radius in config["change_mask"]["feather_radius_sweep"]:
        add(f"feather radius {radius}", feather_radius=radius)
    for area in config["change_mask"].get("minimum_component_area_sweep", []):
        add(f"minimum component area {area}", minimum_component_area=area)
    add("selected configuration")
    return variants


def _write_alignment_overlays(
    output_directory: Path,
    images: list[np.ndarray],
    reference_index: int,
    transforms: list[dict[str, Any]],
) -> None:
    reference = images[reference_index]
    height, width = reference.shape[:2]
    for index, target in enumerate(images):
        warped, _ = warp_reference(reference, transforms[index]["matrix"], width, height)
        overlay = np.empty_like(target)
        overlay[..., 0] = target[..., 0]
        overlay[..., 1] = warped[..., 1]
        overlay[..., 2] = ((target[..., 2].astype(np.uint16) + warped[..., 2]) // 2).astype(
            np.uint8
        )
        write_rgb_png(output_directory / "alignment-overlays" / f"frame-{index:03d}.png", overlay)


def _prepare_output(output_directory: Path) -> None:
    output_directory.mkdir(parents=True, exist_ok=True)
    for directory in ["reconstructions", "heatmaps", "masks", "alignment-overlays"]:
        path = output_directory / directory
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True)
    for filename in [
        "moment.photofold",
        "benchmark.json",
        "package-inventory.json",
        "sweep.json",
        "report.html",
        "exported-000.webp",
    ]:
        path = output_directory / filename
        if path.exists():
            path.unlink()


def run_benchmark(
    dataset_path: str | Path,
    config_path: str | Path,
    output_path: str | Path,
    *,
    include_sweep: bool = True,
) -> dict[str, Any]:
    dataset_directory = Path(dataset_path).resolve()
    config_file = Path(config_path).resolve()
    output_directory = Path(output_path).resolve()
    _prepare_output(output_directory)
    dataset = validate_dataset(dataset_directory)
    config, config_sha256 = _load_config(config_file)
    selected = _parameters(config)
    filenames = [frame["path"] for frame in dataset["frames"]]
    images = [load_rgb(dataset_directory / filename) for filename in filenames]
    alignment = select_reference_and_align(images)
    qualities = _control_qualities(config)
    control_curve = _control_curve(images, qualities)

    sweep_results: list[dict[str, Any]] = []
    variants = _sweep_variants(config, selected) if include_sweep else [("selected", selected)]
    with tempfile.TemporaryDirectory(prefix="photofold-gate1-sweep-") as temp_directory:
        for trial_index, (label, parameters) in enumerate(variants):
            trial_path = Path(temp_directory) / f"trial-{trial_index:03d}.photofold"
            trial = _trial(
                images,
                filenames,
                alignment,
                parameters,
                dataset["total_bytes"],
                control_curve,
                trial_path,
            )
            sweep_results.append(
                {
                    "label": label,
                    "parameters": parameters,
                    "package_total_bytes": trial["package_path"].stat().st_size
                    if "package_path" in trial
                    else trial_path.stat().st_size,
                    "mean_ssim": trial["mean_ssim"],
                    "minimum_ssim": trial["minimum_ssim"],
                    "patch_count": sum(
                        item["patch_count"] for item in trial["package"]["region_metrics"]
                    ),
                    "changed_region_percent": float(
                        np.mean(
                            [
                                item["changed_region_percent"]
                                for item in trial["package"]["region_metrics"]
                            ]
                        )
                    ),
                    "matched_control_quality": trial["matched_control"]["quality"],
                    "matched_control_bytes": trial["matched_control"]["total_bytes"],
                    "control_matched": trial["control_matched"],
                    "storage_reduction_pass": trial["storage_reduction_pass"],
                    "relational_hypothesis_pass": trial["relational_hypothesis_pass"],
                }
            )

    final_package = output_directory / "moment.photofold"
    selected_trial = _trial(
        images,
        filenames,
        alignment,
        selected,
        dataset["total_bytes"],
        control_curve,
        final_package,
    )
    verification = selected_trial["package_check"]
    package_total_bytes = final_package.stat().st_size
    scores = selected_trial["scores"]
    mean_ssim = selected_trial["mean_ssim"]
    minimum_ssim = selected_trial["minimum_ssim"]
    min_per_frame = config["quality"].get("min_per_frame")
    min_mean = config["quality"].get("min_mean")
    thresholds_committed = min_per_frame is not None and min_mean is not None
    quality_threshold_pass = thresholds_committed and minimum_ssim >= float(
        min_per_frame
    ) and mean_ssim >= float(min_mean)
    matched_control = selected_trial["matched_control"]
    relational_gain_bytes = matched_control["total_bytes"] - package_total_bytes
    relational_gain_percent = relational_gain_bytes / matched_control["total_bytes"] * 100
    byte_delta = dataset["total_bytes"] - package_total_bytes
    percent_change = byte_delta / dataset["total_bytes"] * 100
    storage_reduction_pass = package_total_bytes < dataset["total_bytes"]
    relational_hypothesis_pass = selected_trial["control_matched"] and relational_gain_bytes > 0

    _write_alignment_overlays(
        output_directory,
        images,
        alignment["reference_frame_index"],
        alignment["transforms"],
    )
    per_frame = []
    for index, (original, reconstruction, score) in enumerate(
        zip(images, selected_trial["reconstructions"], scores, strict=True)
    ):
        reconstruction_relative = f"reconstructions/frame-{index:03d}.png"
        heatmap_relative = f"heatmaps/frame-{index:03d}.png"
        mask_relative = f"masks/frame-{index:03d}.png"
        write_rgb_png(output_directory / reconstruction_relative, reconstruction)
        write_rgb_png(
            output_directory / heatmap_relative,
            difference_heatmap(original, reconstruction),
        )
        write_gray_png(
            output_directory / mask_relative,
            selected_trial["package"]["debug_masks"][index],
        )
        region = selected_trial["package"]["region_metrics"][index]
        per_frame.append(
            {
                "index": index,
                "filename": filenames[index],
                "width": original.shape[1],
                "height": original.shape[0],
                "original_bytes": dataset["frames"][index]["bytes"],
                "accepted": True,
                "reconstructed": True,
                "ssim": score,
                "quality_threshold_pass": thresholds_committed
                and score >= float(min_per_frame),
                "patch_count": region["patch_count"],
                "changed_region_percent": region["changed_region_percent"],
                "shared_region_percent": region["shared_region_percent"],
                "artifacts": {
                    "reconstruction": reconstruction_relative,
                    "heatmap": heatmap_relative,
                    "mask": mask_relative,
                    "alignment_overlay": f"alignment-overlays/frame-{index:03d}.png",
                },
            }
        )

    source_total_check = (
        sum(frame["original_bytes"] for frame in per_frame) == dataset["total_bytes"]
    )
    package_stat_check = package_total_bytes == verification["package_total_bytes"]
    dimensions_check = all(
        frame["width"] == dataset["normalized_dimensions"]["width"]
        and frame["height"] == dataset["normalized_dimensions"]["height"]
        for frame in per_frame
    )
    alignment_threshold_pass = all(
        transform["inlier_ratio"] >= float(config["alignment"]["min_inlier_ratio"])
        and transform["median_reprojection_error"]
        <= float(config["alignment"]["max_median_reprojection_error"])
        for transform in alignment["transforms"]
    )
    integrity_checks = [
        {
            "id": "accepted_count",
            "label": "All input frames accepted",
            "pass": len(per_frame) >= 5 and all(frame["accepted"] for frame in per_frame),
            "detail": f"{len(per_frame)} of {len(dataset['frames'])} frames accepted",
        },
        {
            "id": "reconstructed_count",
            "label": "All accepted frames reconstructed",
            "pass": all(frame["reconstructed"] for frame in per_frame),
            "detail": f"{len(per_frame)} package-only reconstructions",
        },
        {
            "id": "dimensions",
            "label": "Reconstruction dimensions",
            "pass": dimensions_check and verification["checks"]["dimensions_match"],
            "detail": (
                f"All frames are {dataset['normalized_dimensions']['width']}×"
                f"{dataset['normalized_dimensions']['height']}"
            ),
        },
        {
            "id": "alignment_thresholds",
            "label": "Committed alignment thresholds",
            "pass": alignment_threshold_pass,
            "detail": (
                f"every transform has inlier ratio ≥ "
                f"{config['alignment']['min_inlier_ratio']} and median reprojection "
                f"error ≤ {config['alignment']['max_median_reprojection_error']} px"
            ),
        },
        {
            "id": "package_only_decode",
            "label": "Package-only decoder",
            "pass": verification["package_only_decode"],
            "detail": "The public decoder received only moment.photofold and frame index",
        },
        {
            "id": "manifest",
            "label": "Manifest, paths, transforms, and inventory",
            "pass": all(
                verification["checks"][key]
                for key in [
                    "zip_paths_safe",
                    "manifest_valid",
                    "inventory_exact",
                    "transforms_valid",
                ]
            ),
            "detail": "Strict Pydantic schema and safe ZIP-member validation passed",
        },
        {
            "id": "member_checksums",
            "label": "Package member checksums",
            "pass": verification["checks"]["member_checksums"],
            "detail": f"{len(verification['members'])} members matched encoded bytes and SHA-256",
        },
        {
            "id": "archive_stat",
            "label": "Closed archive byte count",
            "pass": package_stat_check,
            "detail": f"benchmark and stat both report {package_total_bytes:,} bytes",
        },
        {
            "id": "source_stat",
            "label": "Exact source byte count",
            "pass": source_total_check,
            "detail": f"source file stats sum to {dataset['total_bytes']:,} bytes",
        },
        {
            "id": "quality",
            "label": "Committed quality threshold",
            "pass": quality_threshold_pass,
            "detail": (
                f"mean {mean_ssim:.6f} ≥ {min_mean}; minimum {minimum_ssim:.6f} ≥ {min_per_frame}"
                if thresholds_committed
                else "quality thresholds are still null in configs/gate1.yaml"
            ),
        },
        {
            "id": "original_savings",
            "label": "Smaller than exact uploaded sources",
            "pass": storage_reduction_pass,
            "detail": (
                f"{package_total_bytes:,} package bytes versus "
                f"{dataset['total_bytes']:,} source bytes"
            ),
        },
        {
            "id": "matched_control",
            "label": "Matched-quality independent-WebP control",
            "pass": relational_hypothesis_pass,
            "detail": (
                f"PhotoFold is {relational_gain_bytes:,} bytes smaller than "
                f"q{matched_control['quality']} independent WebP at equal/better "
                "mean and minimum SSIM"
                if selected_trial["control_matched"]
                else "No independent-WebP point matched both PhotoFold quality values"
            ),
        },
    ]
    failed_checks = [check["label"] for check in integrity_checks if not check["pass"]]
    result = {
        "schema_version": "0.1",
        "run_at": datetime.now(UTC).isoformat(),
        "dataset_id": dataset["dataset_id"],
        "dataset_path": str(dataset_directory),
        "config_path": str(config_file),
        "config_sha256": config_sha256,
        "parameters": selected,
        "reference_frame_index": alignment["reference_frame_index"],
        "accepted_frame_count": len(per_frame),
        "reconstructed_frame_count": len(per_frame),
        "original_total_bytes": dataset["total_bytes"],
        "package_total_bytes": package_total_bytes,
        "package_sha256": sha256_file(final_package),
        "byte_delta": byte_delta,
        "percent_change": percent_change,
        "bytes_saved": max(byte_delta, 0),
        "percent_saved": max(percent_change, 0),
        "independent_webp_total_bytes": matched_control["total_bytes"],
        "independent_webp_quality": matched_control["quality"],
        "independent_webp_mean_ssim": matched_control["mean_ssim"],
        "independent_webp_minimum_ssim": matched_control["minimum_ssim"],
        "independent_webp_control_matched": selected_trial["control_matched"],
        "relational_gain_bytes": relational_gain_bytes,
        "relational_gain_percent": relational_gain_percent,
        "mean_ssim": mean_ssim,
        "minimum_ssim": minimum_ssim,
        "quality_thresholds": {
            "min_per_frame": min_per_frame,
            "min_mean": min_mean,
        },
        "quality_threshold_pass": quality_threshold_pass,
        "alignment_threshold_pass": alignment_threshold_pass,
        "storage_reduction_pass": storage_reduction_pass,
        "relational_hypothesis_pass": relational_hypothesis_pass,
        "gate_pass": not failed_checks,
        "per_frame": per_frame,
        "alignment": {
            "reference_candidates": alignment["reference_candidates"],
            "model_comparison": alignment["model_comparison"],
            "transforms": [
                {
                    **{key: value for key, value in transform.items() if key != "matrix"},
                    "reference_to_target": np.asarray(transform["matrix"]).reshape(-1).tolist(),
                }
                for transform in alignment["transforms"]
            ],
        },
        "independent_webp_curve": control_curve,
        "parameter_sweep": sweep_results,
        "integrity_checks": integrity_checks,
        "package_members": verification["members"],
        "failed_checks": failed_checks,
        "limitations": [
            "This proves or falsifies the hypothesis only for one static, low-motion HDR+ burst.",
            "Whole-image RGB SSIM and heatmaps do not establish perceptual quality "
            "for faces or larger motion.",
            "The Gate 1 CLI is not exposed through the API or product interface.",
        ],
    }
    benchmark_path = output_directory / "benchmark.json"
    benchmark_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_directory / "package-inventory.json").write_text(
        json.dumps(verification, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_directory / "sweep.json").write_text(
        json.dumps(
            {"selected": selected, "trials": sweep_results, "control_curve": control_curve},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    export_package_frame(final_package, 0, output_directory / "exported-000.webp", "webp")
    report = generate_report(benchmark_path, dataset_directory)
    result["report"] = report
    benchmark_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result
