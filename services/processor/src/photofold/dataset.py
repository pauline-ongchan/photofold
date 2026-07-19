"""Checksum and decode validation for curated local datasets."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError

SUPPORTED_FORMATS = {"JPEG", "PNG", "WEBP"}


class DatasetValidationError(ValueError):
    """Raised when a curated dataset violates its manifest."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_manifest(dataset_path: Path) -> dict[str, Any]:
    manifest_path = dataset_path / "manifest.json"
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise DatasetValidationError(f"Missing dataset manifest: {manifest_path}") from error
    except json.JSONDecodeError as error:
        raise DatasetValidationError(f"Invalid dataset manifest JSON: {error}") from error


def validate_dataset(dataset: str | Path) -> dict[str, Any]:
    dataset_path = Path(dataset).expanduser().resolve()
    manifest = _load_manifest(dataset_path)
    files = manifest.get("files")
    if not isinstance(files, list):
        raise DatasetValidationError("manifest.files must be an array")

    expected_count = manifest.get("expected_frame_count")
    if expected_count != len(files):
        raise DatasetValidationError(
            f"expected_frame_count is {expected_count}, but manifest lists {len(files)} files"
        )
    if not 5 <= len(files) <= 20:
        raise DatasetValidationError("A curated PhotoFold set must contain 5 to 20 frames")

    expected_dimensions = manifest.get("expected_dimensions", {})
    expected_size = (
        expected_dimensions.get("width"),
        expected_dimensions.get("height"),
    )
    if not all(isinstance(value, int) and value > 0 for value in expected_size):
        raise DatasetValidationError("expected_dimensions must contain positive width and height")

    seen_paths: set[str] = set()
    frames: list[dict[str, Any]] = []
    total_bytes = 0

    for index, entry in enumerate(files):
        relative_path = entry.get("path")
        expected_sha256 = entry.get("sha256")
        if not isinstance(relative_path, str) or not relative_path:
            raise DatasetValidationError(f"Frame {index} has no path")
        if relative_path in seen_paths:
            raise DatasetValidationError(f"Duplicate frame path: {relative_path}")
        seen_paths.add(relative_path)

        frame_path = (dataset_path / relative_path).resolve()
        try:
            frame_path.relative_to(dataset_path)
        except ValueError as error:
            raise DatasetValidationError(f"Frame path escapes dataset: {relative_path}") from error
        if not frame_path.is_file():
            raise DatasetValidationError(f"Missing frame: {relative_path}")

        actual_sha256 = _sha256(frame_path)
        if actual_sha256 != expected_sha256:
            raise DatasetValidationError(
                f"Checksum mismatch for {relative_path}: {actual_sha256}"
            )

        try:
            with Image.open(frame_path) as image:
                image_format = image.format
                if image_format not in SUPPORTED_FORMATS:
                    raise DatasetValidationError(
                        f"Unsupported decoded format for {relative_path}: {image_format}"
                    )
                normalized = ImageOps.exif_transpose(image)
                normalized.load()
                dimensions = normalized.size
                mode = normalized.mode
        except (Image.DecompressionBombError, UnidentifiedImageError, OSError) as error:
            raise DatasetValidationError(f"Could not decode {relative_path}: {error}") from error

        if dimensions != expected_size:
            raise DatasetValidationError(
                f"Dimension mismatch for {relative_path}: {dimensions}, expected {expected_size}"
            )

        byte_count = frame_path.stat().st_size
        total_bytes += byte_count
        frames.append(
            {
                "index": index,
                "path": relative_path,
                "format": image_format,
                "mode": mode,
                "width": dimensions[0],
                "height": dimensions[1],
                "bytes": byte_count,
                "sha256": actual_sha256,
            }
        )

    return {
        "status": "pass",
        "dataset_id": manifest.get("id"),
        "title": manifest.get("title"),
        "frame_count": len(frames),
        "normalized_dimensions": {
            "width": expected_size[0],
            "height": expected_size[1],
        },
        "total_bytes": total_bytes,
        "license": manifest.get("license"),
        "source": manifest.get("source"),
        "frames": frames,
        "limitations": manifest.get("limitations", []),
    }

