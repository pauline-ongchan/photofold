"""Reusable frozen Gate 1 treatment configuration and package construction."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import yaml

from photofold.gate1.alignment import warp_reference
from photofold.gate1.bundle import build_package
from photofold.gate1.images import sha256_file, write_rgb_png


def load_gate1_config(path: str | Path) -> tuple[dict[str, Any], str]:
    config_path = Path(path)
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Gate 1 config must be a YAML object")
    return payload, sha256_file(config_path)


def selected_parameters(config: dict[str, Any]) -> dict[str, int]:
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


def build_treatment_package(
    *,
    images: list[np.ndarray],
    filenames: list[str],
    alignment: dict[str, Any],
    parameters: dict[str, int],
    original_total_bytes: int,
    output_path: Path,
) -> dict[str, Any]:
    return build_package(
        images=images,
        filenames=filenames,
        reference_index=alignment["reference_frame_index"],
        transforms=alignment["transforms"],
        parameters=parameters,
        analysis={key: value for key, value in alignment.items() if key != "transforms"},
        original_total_bytes=original_total_bytes,
        output_path=output_path,
    )


def write_alignment_overlays(
    output_directory: Path,
    images: list[np.ndarray],
    reference_index: int,
    transforms: list[dict[str, Any]],
) -> None:
    """Write the shared red/green alignment diagnostic for every frame."""
    reference = images[reference_index]
    height, width = reference.shape[:2]
    for index, target in enumerate(images):
        warped, _ = warp_reference(reference, transforms[index]["matrix"], width, height)
        overlay = np.empty_like(target)
        overlay[..., 0] = target[..., 0]
        overlay[..., 1] = warped[..., 1]
        overlay[..., 2] = (
            (target[..., 2].astype(np.uint16) + warped[..., 2]) // 2
        ).astype(np.uint8)
        write_rgb_png(
            output_directory / "alignment-overlays" / f"frame-{index:03d}.png",
            overlay,
        )
