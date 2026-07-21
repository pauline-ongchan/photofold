"""PhotoFold archive writer, validator, and package-only decoder."""

from __future__ import annotations

import json
import zipfile
from collections import OrderedDict
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import ValidationError

from photofold.gate1.alignment import warp_reference
from photofold.gate1.images import (
    decode_gray,
    decode_rgb,
    encode_png_gray,
    encode_webp,
    sha256_bytes,
    sha256_file,
)
from photofold.gate1.models import (
    AssetRecord,
    BaseRecord,
    FrameRecord,
    IndependentSourceRecord,
    NormalizedDimensions,
    PatchRecord,
    PhotoFoldManifest,
    TransformRecord,
)


class PackageValidationError(ValueError):
    """Raised when a `.photofold` package violates its contract."""


def _json_bytes(value: Any) -> bytes:
    # Package metadata is machine-consumed and ZIP_STORED does not remove JSON
    # whitespace. Compact encoding therefore avoids paying archive bytes for
    # presentation formatting without changing any image quality.
    return (json.dumps(value, separators=(",", ":"), sort_keys=True) + "\n").encode()


def _json_safe(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _remove_small_components(mask: np.ndarray, minimum_area: int) -> np.ndarray:
    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    filtered = np.zeros_like(mask)
    for label in range(1, component_count):
        if int(stats[label, cv2.CC_STAT_AREA]) >= minimum_area:
            filtered[labels == label] = 255
    return filtered


def _changed_mask(
    target: np.ndarray,
    warped_base: np.ndarray,
    valid: np.ndarray,
    parameters: dict[str, int],
) -> np.ndarray:
    difference = np.max(
        np.abs(target.astype(np.int16) - warped_base.astype(np.int16)),
        axis=2,
    )
    binary = np.where(difference > parameters["pixel_threshold"], 255, 0).astype(np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    binary = _remove_small_components(binary, parameters["minimum_component_area"])
    binary[valid == 0] = 255
    dilation_radius = parameters["dilation_radius"]
    if dilation_radius > 0:
        size = dilation_radius * 2 + 1
        binary = cv2.dilate(binary, np.ones((size, size), np.uint8))
    return binary


def _component_boxes(mask: np.ndarray, tile_size: int, margin: int) -> list[list[int]]:
    height, width = mask.shape
    binary = np.where(mask > 0, 255, 0).astype(np.uint8)
    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    boxes: list[list[int]] = []
    for label in range(1, component_count):
        x = max(0, int(stats[label, cv2.CC_STAT_LEFT]) - margin)
        y = max(0, int(stats[label, cv2.CC_STAT_TOP]) - margin)
        component_width = int(stats[label, cv2.CC_STAT_WIDTH]) + margin * 2
        component_height = int(stats[label, cv2.CC_STAT_HEIGHT]) + margin * 2
        right = min(width, x + component_width)
        bottom = min(height, y + component_height)
        component_width = right - x
        component_height = bottom - y
        if component_width <= tile_size and component_height <= tile_size:
            boxes.append([x, y, component_width, component_height])
            continue
        for tile_y in range(y, bottom, tile_size):
            for tile_x in range(x, right, tile_size):
                tile_right = min(right, tile_x + tile_size)
                tile_bottom = min(bottom, tile_y + tile_size)
                tile_mask = labels[tile_y:tile_bottom, tile_x:tile_right] == label
                if np.any(tile_mask):
                    boxes.append([tile_x, tile_y, tile_right - tile_x, tile_bottom - tile_y])

    unique: list[list[int]] = []
    seen: set[tuple[int, int, int, int]] = set()
    for box in boxes:
        key = tuple(box)
        if key not in seen and key != (0, 0, width, height):
            seen.add(key)
            unique.append(box)
    return unique


def _encode_patches(
    frame_index: int,
    target: np.ndarray,
    mask: np.ndarray,
    parameters: dict[str, int],
) -> tuple[list[PatchRecord], OrderedDict[str, bytes], np.ndarray]:
    feather_radius = parameters["feather_radius"]
    boxes = _component_boxes(
        mask,
        parameters["tile_size"],
        max(parameters["patch_margin"], feather_radius),
    )
    ranked = sorted(
        boxes,
        key=lambda box: int(
            np.count_nonzero(mask[box[1] : box[1] + box[3], box[0] : box[0] + box[2]])
        ),
        reverse=True,
    )[: parameters["maximum_patches_per_frame"]]

    assets: OrderedDict[str, bytes] = OrderedDict()
    patches: list[PatchRecord] = []
    applied_mask = np.zeros_like(mask)
    for patch_index, (x, y, width, height) in enumerate(ranked):
        crop_mask = mask[y : y + height, x : x + width].copy()
        if not np.any(crop_mask):
            continue
        crop_target = target[y : y + height, x : x + width].copy()
        image_path = f"frames/{frame_index:03d}/patches/{patch_index:03d}.webp"
        mask_path = f"frames/{frame_index:03d}/patches/{patch_index:03d}-mask.png"
        assets[image_path] = encode_webp(crop_target, parameters["patch_quality"])
        assets[mask_path] = encode_png_gray(crop_mask)
        patches.append(
            PatchRecord(
                bbox=[x, y, width, height],
                image_path=image_path,
                mask_path=mask_path,
                feather_radius=feather_radius,
            )
        )
        applied_mask[y : y + height, x : x + width] = np.maximum(
            applied_mask[y : y + height, x : x + width], crop_mask
        )
    return patches, assets, applied_mask


def build_package(
    images: list[np.ndarray],
    filenames: list[str],
    reference_index: int | None,
    transforms: list[dict[str, Any] | None],
    parameters: dict[str, int],
    analysis: dict[str, Any],
    original_total_bytes: int,
    output_path: Path,
    storage_dispositions: list[dict[str, Any]] | None = None,
    source_payloads: list[bytes | None] | None = None,
    source_formats: list[str | None] | None = None,
    alignment_error_threshold: float | None = None,
) -> dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if storage_dispositions is None:
        storage_dispositions = [
            {
                "frame_index": index,
                "storage_mode": (
                    "shared_reference" if index == reference_index else "shared_delta"
                ),
                "fallback_reason": None,
            }
            for index in range(len(images))
        ]
    if [item["frame_index"] for item in storage_dispositions] != list(range(len(images))):
        raise ValueError("Storage dispositions must preserve contiguous source order")
    storage_modes = [item["storage_mode"] for item in storage_dispositions]
    shared_indices = [
        index for index, mode in enumerate(storage_modes) if mode != "independent_source"
    ]
    if bool(shared_indices) != (reference_index is not None):
        raise ValueError("Shared storage and reference selection disagree")
    if shared_indices and reference_index not in shared_indices:
        raise ValueError("The selected reference is not in the shared group")
    if not shared_indices and any(mode != "independent_source" for mode in storage_modes):
        raise ValueError("Independent-only packages cannot contain shared storage modes")
    fallback_indices = [
        index for index, mode in enumerate(storage_modes) if mode == "independent_source"
    ]
    if fallback_indices and (
        source_payloads is None
        or source_formats is None
        or len(source_payloads) != len(images)
        or len(source_formats) != len(images)
    ):
        raise ValueError("Independent fallback requires every exact source payload and format")

    assets: OrderedDict[str, bytes] = OrderedDict()
    decoded_base: np.ndarray | None = None
    base_record: BaseRecord | None = None
    if reference_index is not None:
        base_height, base_width = images[reference_index].shape[:2]
        base_payload = encode_webp(images[reference_index], parameters["base_quality"])
        assets["base.webp"] = base_payload
        decoded_base = decode_rgb(base_payload)
        base_record = BaseRecord(
            width=base_width,
            height=base_height,
            quality=parameters["base_quality"],
        )

    frame_records: list[FrameRecord] = []
    debug_masks: list[np.ndarray] = []
    region_metrics: list[dict[str, float | int]] = []
    for frame_index, target in enumerate(images):
        height, width = target.shape[:2]
        storage_mode = storage_modes[frame_index]
        transform = transforms[frame_index] if frame_index < len(transforms) else None
        transform_record: TransformRecord | None = None
        source_record: IndependentSourceRecord | None = None
        if storage_mode == "independent_source":
            if source_payloads is None or source_formats is None:
                raise ValueError("Independent fallback source payloads are unavailable")
            source_payload = source_payloads[frame_index]
            source_format = source_formats[frame_index]
            if source_payload is None or source_format not in {"JPEG", "PNG", "WEBP"}:
                raise ValueError(f"Independent fallback source {frame_index} is invalid")
            extension = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}[source_format]
            source_path = f"frames/{frame_index:03d}/source.{extension}"
            assets[source_path] = source_payload
            source_record = IndependentSourceRecord(
                path=source_path,
                decoded_format=source_format,
            )
            patches: list[PatchRecord] = []
            applied_mask = np.zeros((height, width), dtype=np.uint8)
            valid = np.zeros((height, width), dtype=np.uint8)
        else:
            if transform is None or decoded_base is None:
                raise ValueError(f"Shared frame {frame_index} has no usable transform or base")
            matrix = np.asarray(transform["matrix"], dtype=np.float64)
            transform_record = TransformRecord(
                type=transform["type"],
                reference_to_target=matrix.reshape(-1).tolist(),
                inlier_count=transform["inlier_count"],
                inlier_ratio=transform["inlier_ratio"],
                median_reprojection_error=transform["median_reprojection_error"],
                reprojection_error_units=transform.get(
                    "reprojection_error_units", "analysis_pixels"
                ),
                reprojection_error_threshold=alignment_error_threshold,
                valid_overlap=transform["valid_overlap"],
            )
            if storage_mode == "shared_reference":
                patches = []
                applied_mask = np.zeros((height, width), dtype=np.uint8)
                valid = np.full((height, width), 255, dtype=np.uint8)
            else:
                warped_base, valid = warp_reference(decoded_base, matrix, width, height)
                candidate_mask = _changed_mask(target, warped_base, valid, parameters)
                patches, patch_assets, applied_mask = _encode_patches(
                    frame_index,
                    target,
                    candidate_mask,
                    parameters,
                )
                assets.update(patch_assets)
        debug_masks.append(applied_mask)
        changed_pixels = int(np.count_nonzero(applied_mask))
        shared_pixels = int(np.count_nonzero((valid > 0) & (applied_mask == 0)))
        region_metrics.append(
            {
                "frame_index": frame_index,
                "storage_mode": storage_mode,
                "patch_count": len(patches),
                "changed_region_percent": (
                    changed_pixels / applied_mask.size * 100
                    if storage_mode != "independent_source"
                    else None
                ),
                "shared_region_percent": shared_pixels / applied_mask.size * 100,
            }
        )
        frame = FrameRecord(
            index=frame_index,
            original_filename=filenames[frame_index],
            output_width=width,
            output_height=height,
            normalized_dimensions=NormalizedDimensions(width=width, height=height),
            storage_mode=storage_mode,
            transform=transform_record,
            independent_source=source_record,
            patches=patches,
        )
        frame_records.append(frame)
        assets[f"frames/{frame_index:03d}/frame.json"] = _json_bytes(
            frame.model_dump(mode="json")
        )

    analysis_payload = _json_bytes(_json_safe(analysis))
    metrics_payload = _json_bytes(
        {
            "schema_version": "0.1",
            "original_total_bytes": original_total_bytes,
            "parameters": parameters,
            "strategy": analysis.get("strategy"),
            "storage_dispositions": storage_dispositions,
            "region_metrics": region_metrics,
            "notes": [
                "The closed archive size is intentionally external to avoid circular measurement.",
                "Final quality is calculated by reopening this package through the public decoder.",
            ],
        }
    )
    assets["metadata/analysis.json"] = analysis_payload
    assets["metadata/metrics.json"] = metrics_payload

    inventory = [
        AssetRecord(path=path, bytes=len(payload), sha256=sha256_bytes(payload))
        for path, payload in assets.items()
    ]
    shared_count = len(shared_indices)
    fallback_count = len(fallback_indices)
    strategy = (
        "independent_only"
        if shared_count == 0
        else "shared_scene"
        if fallback_count == 0
        else "hybrid"
    )
    required_codecs: set[str] = set()
    if base_record is not None:
        required_codecs.add("webp")
    for frame in frame_records:
        if frame.patches:
            required_codecs.update(("webp", "png"))
        if frame.independent_source is not None:
            required_codecs.add(frame.independent_source.decoded_format.lower())
    manifest = PhotoFoldManifest(
        created_at=datetime.now(UTC).isoformat(),
        strategy=strategy,
        shared_frame_count=shared_count,
        fallback_frame_count=fallback_count,
        reference_frame_index=reference_index,
        required_codecs=sorted(required_codecs),
        base=base_record,
        frames=frame_records,
        assets=inventory,
        analysis_path="metadata/analysis.json",
        metrics_path="metadata/metrics.json",
    )
    manifest_payload = _json_bytes(manifest.model_dump(mode="json"))
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("manifest.json", manifest_payload)
        for path, payload in assets.items():
            archive.writestr(path, payload)

    return {
        "path": str(output_path),
        "bytes": output_path.stat().st_size,
        "sha256": sha256_file(output_path),
        "manifest": manifest.model_dump(mode="json"),
        "debug_masks": debug_masks,
        "region_metrics": region_metrics,
    }


def _legacy_frame_data(value: dict[str, Any], reference_index: int) -> dict[str, Any]:
    migrated = dict(value)
    migrated["normalized_dimensions"] = {
        "width": migrated["output_width"],
        "height": migrated["output_height"],
    }
    migrated["storage_mode"] = (
        "shared_reference" if migrated["index"] == reference_index else "shared_delta"
    )
    migrated["independent_source"] = None
    transform = dict(migrated["transform"])
    transform["reprojection_error_units"] = "legacy_full_resolution_pixels"
    transform["reprojection_error_threshold"] = None
    migrated["transform"] = transform
    return migrated


def _migrate_legacy_manifest(value: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    if value.get("version") != "0.1":
        return value, False
    migrated = dict(value)
    reference_index = int(migrated["reference_frame_index"])
    frames = [
        _legacy_frame_data(dict(frame), reference_index) for frame in migrated["frames"]
    ]
    required_codecs = {"webp"}
    if any(frame["patches"] for frame in frames):
        required_codecs.add("png")
    migrated.update(
        {
            "version": "0.2",
            "strategy": "shared_scene",
            "shared_frame_count": len(frames),
            "fallback_frame_count": 0,
            "required_codecs": sorted(required_codecs),
            "frames": frames,
        }
    )
    return migrated, True


def _decode_independent_source(
    frame: FrameRecord,
    payloads: dict[str, bytes],
) -> np.ndarray:
    source = frame.independent_source
    if source is None:
        raise PackageValidationError(f"Independent frame {frame.index} has no source member")
    if (
        Image.MAX_IMAGE_PIXELS is not None
        and frame.output_width * frame.output_height > Image.MAX_IMAGE_PIXELS
    ):
        raise PackageValidationError(
            f"Independent source exceeds the safe decoded pixel limit: frame {frame.index}"
        )
    try:
        with Image.open(BytesIO(payloads[source.path])) as image:
            if image.format != source.decoded_format:
                raise PackageValidationError(
                    f"Independent source format disagrees with frame {frame.index}"
                )
            normalized = ImageOps.exif_transpose(image)
            normalized.load()
            if (
                "A" in normalized.getbands() or "transparency" in normalized.info
            ) and normalized.convert("RGBA").getchannel("A").getextrema()[0] < 255:
                raise PackageValidationError(
                    f"Independent source transparency is unsupported: frame {frame.index}"
                )
            reconstruction = np.asarray(normalized.convert("RGB"), dtype=np.uint8).copy()
    except PackageValidationError:
        raise
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError) as error:
        raise PackageValidationError(
            f"Independent source could not be decoded safely: frame {frame.index}"
        ) from error
    if reconstruction.shape[:2] != (frame.output_height, frame.output_width):
        raise PackageValidationError(
            f"Independent source dimensions disagree with frame {frame.index}"
        )
    return reconstruction


def _read_package(
    package_path: Path,
) -> tuple[PhotoFoldManifest, dict[str, bytes], list[dict[str, Any]]]:
    if not package_path.is_file():
        raise PackageValidationError(f"Package does not exist: {package_path}")
    try:
        with zipfile.ZipFile(package_path, "r") as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise PackageValidationError("Package contains duplicate member paths")
            for info in infos:
                path = PurePosixPath(info.filename)
                if path.is_absolute() or ".." in path.parts or "\\" in info.filename:
                    raise PackageValidationError(f"Unsafe package path: {info.filename}")
                if info.flag_bits & 0x1:
                    raise PackageValidationError("Encrypted package members are unsupported")
                if info.compress_type != zipfile.ZIP_STORED:
                    raise PackageValidationError("Gate 1 packages must use ZIP_STORED")
            if "manifest.json" not in names:
                raise PackageValidationError("Package has no manifest.json")
            payloads = {name: archive.read(name) for name in names}
            member_listing = [
                {
                    "path": info.filename,
                    "bytes": info.file_size,
                    "compressed_bytes": info.compress_size,
                    "sha256": sha256_bytes(payloads[info.filename]),
                }
                for info in infos
            ]
    except zipfile.BadZipFile as error:
        raise PackageValidationError(f"Invalid ZIP container: {error}") from error

    try:
        raw_manifest = json.loads(payloads["manifest.json"])
        manifest_data, legacy = _migrate_legacy_manifest(raw_manifest)
        manifest = PhotoFoldManifest.model_validate(manifest_data)
    except (json.JSONDecodeError, ValidationError) as error:
        raise PackageValidationError(f"Invalid package manifest: {error}") from error
    for frame in manifest.frames:
        frame_path = f"frames/{frame.index:03d}/frame.json"
        try:
            raw_frame = json.loads(payloads[frame_path])
            if legacy:
                raw_frame = _legacy_frame_data(raw_frame, manifest.reference_frame_index or 0)
            frame_member = FrameRecord.model_validate(raw_frame)
        except (KeyError, json.JSONDecodeError, ValidationError) as error:
            raise PackageValidationError(
                f"Invalid frame metadata member: {frame_path}: {error}"
            ) from error
        if frame_member != frame:
            raise PackageValidationError(
                f"Frame metadata member disagrees with manifest: {frame_path}"
            )
        if frame.storage_mode == "independent_source":
            _decode_independent_source(frame, payloads)
            continue
        if frame.transform is None or manifest.base is None:
            raise PackageValidationError(f"Shared frame {frame.index} is missing its base data")
        matrix = np.asarray(frame.transform.reference_to_target, dtype=np.float64).reshape(3, 3)
        corners = np.asarray(
            [
                [0.0, 0.0, 1.0],
                [manifest.base.width, 0.0, 1.0],
                [manifest.base.width, manifest.base.height, 1.0],
                [0.0, manifest.base.height, 1.0],
            ]
        ).T
        projected = matrix @ corners
        denominators = projected[2]
        if np.any(np.abs(denominators) < 1e-8):
            raise PackageValidationError(f"Transform projects frame {frame.index} to infinity")
        points = (projected[:2] / denominators).T
        if not np.all(np.isfinite(points)):
            raise PackageValidationError(f"Transform has invalid projected corners: {frame.index}")
        projected_area = abs(float(cv2.contourArea(points.astype(np.float32))))
        canvas_area = float(frame.output_width * frame.output_height)
        if not 0.1 * canvas_area <= projected_area <= 10.0 * canvas_area:
            raise PackageValidationError(f"Transform has implausible projected area: {frame.index}")
        if np.max(np.abs(points)) > 4 * max(frame.output_width, frame.output_height):
            raise PackageValidationError(f"Transform projects frame implausibly far: {frame.index}")
    expected_members = {"manifest.json", *(asset.path for asset in manifest.assets)}
    if expected_members != set(payloads):
        missing = sorted(expected_members - set(payloads))
        unexpected = sorted(set(payloads) - expected_members)
        raise PackageValidationError(
            f"Package inventory mismatch; missing={missing}, unexpected={unexpected}"
        )
    for asset in manifest.assets:
        payload = payloads[asset.path]
        if len(payload) != asset.bytes or sha256_bytes(payload) != asset.sha256:
            raise PackageValidationError(f"Asset integrity check failed: {asset.path}")
    metrics = json.loads(payloads[manifest.metrics_path])
    if "package_total_bytes" in metrics:
        raise PackageValidationError("Internal metrics contain circular package_total_bytes")
    return manifest, payloads, member_listing


def _decode_frame_from_payloads(
    manifest: PhotoFoldManifest,
    payloads: dict[str, bytes],
    frame_index: int,
) -> np.ndarray:
    if not 0 <= frame_index < len(manifest.frames):
        raise PackageValidationError(f"Frame index is outside the package: {frame_index}")
    frame = manifest.frames[frame_index]
    if frame.storage_mode == "independent_source":
        return _decode_independent_source(frame, payloads)
    if manifest.base is None or frame.transform is None:
        raise PackageValidationError(f"Shared frame {frame.index} has no shared base")
    base = decode_rgb(payloads[manifest.base.path])
    if base.shape[:2] != (manifest.base.height, manifest.base.width):
        raise PackageValidationError("Decoded base dimensions disagree with the manifest")
    matrix = np.asarray(frame.transform.reference_to_target, dtype=np.float64).reshape(3, 3)
    reconstruction, _ = warp_reference(
        base,
        matrix,
        frame.output_width,
        frame.output_height,
    )
    for patch in frame.patches:
        x, y, width, height = patch.bbox
        patch_rgb = decode_rgb(payloads[patch.image_path])
        patch_mask = decode_gray(payloads[patch.mask_path])
        if patch_rgb.shape[:2] != (height, width) or patch_mask.shape != (height, width):
            raise PackageValidationError(
                f"Patch dimensions disagree with bbox: {patch.image_path}"
            )
        if patch.feather_radius > 0:
            size = patch.feather_radius * 2 + 1
            patch_mask = cv2.GaussianBlur(
                patch_mask,
                (size, size),
                sigmaX=max(0.5, patch.feather_radius / 2),
            )
        alpha = patch_mask.astype(np.float32)[..., None] / 255.0
        target = reconstruction[y : y + height, x : x + width].astype(np.float32)
        composited = patch_rgb.astype(np.float32) * alpha + target * (1.0 - alpha)
        reconstruction[y : y + height, x : x + width] = np.clip(
            np.rint(composited), 0, 255
        ).astype(np.uint8)
    return reconstruction


def decode_package_frame(package_path: str | Path, frame_index: int) -> np.ndarray:
    manifest, payloads, _ = _read_package(Path(package_path))
    return _decode_frame_from_payloads(manifest, payloads, frame_index)


def decode_all_package_frames(package_path: str | Path) -> list[np.ndarray]:
    manifest, payloads, _ = _read_package(Path(package_path))
    return [
        _decode_frame_from_payloads(manifest, payloads, frame.index)
        for frame in manifest.frames
    ]


def verify_package(package_path: str | Path) -> dict[str, Any]:
    path = Path(package_path).resolve()
    manifest, payloads, member_listing = _read_package(path)
    frames = []
    for frame in manifest.frames:
        reconstruction = _decode_frame_from_payloads(manifest, payloads, frame.index)
        frames.append(
            {
                "index": frame.index,
                "storage_mode": frame.storage_mode,
                "width": int(reconstruction.shape[1]),
                "height": int(reconstruction.shape[0]),
                "patch_count": len(frame.patches),
                "dimensions_match": reconstruction.shape[:2]
                == (frame.output_height, frame.output_width),
            }
        )
    return {
        "status": "pass" if all(frame["dimensions_match"] for frame in frames) else "fail",
        "package": str(path),
        "package_total_bytes": path.stat().st_size,
        "package_sha256": sha256_file(path),
        "format": manifest.format,
        "version": manifest.version,
        "strategy": manifest.strategy,
        "shared_frame_count": manifest.shared_frame_count,
        "fallback_frame_count": manifest.fallback_frame_count,
        "reference_frame_index": manifest.reference_frame_index,
        "frame_count": len(manifest.frames),
        "reconstructed_frame_count": len(frames),
        "package_only_decode": True,
        "checks": {
            "zip_paths_safe": True,
            "zip_stored": True,
            "manifest_valid": True,
            "inventory_exact": True,
            "member_checksums": True,
            "transforms_valid": True,
            "dimensions_match": all(frame["dimensions_match"] for frame in frames),
            "no_circular_archive_size": True,
        },
        "frames": frames,
        "members": member_listing,
    }


def export_package_frame(
    package_path: str | Path,
    frame_index: int,
    output_path: str | Path,
    image_format: str,
) -> dict[str, Any]:
    normalized_format = image_format.lower()
    format_map = {"webp": "WEBP", "jpeg": "JPEG", "jpg": "JPEG", "png": "PNG"}
    if normalized_format not in format_map:
        raise ValueError("Export format must be webp, jpeg, or png")
    reconstruction = decode_package_frame(package_path, frame_index)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    options: dict[str, Any] = {}
    if normalized_format in {"webp", "jpeg", "jpg"}:
        options["quality"] = 95
    Image.fromarray(reconstruction, mode="RGB").save(
        destination,
        format=format_map[normalized_format],
        **options,
    )
    return {
        "status": "pass",
        "package": str(Path(package_path).resolve()),
        "frame_index": frame_index,
        "format": normalized_format,
        "output": str(destination.resolve()),
        "bytes": destination.stat().st_size,
        "sha256": sha256_file(destination),
        "width": reconstruction.shape[1],
        "height": reconstruction.shape[0],
    }
