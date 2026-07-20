"""Immutable-source preparation and validation for the Phase 1B collection."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import ValidationError

from photofold.gate1.images import sha256_file
from photofold.phase1b.models import Phase1BDatasetManifest

PHASE1B_DATASET_IDS = (
    "static-handheld",
    "moving-subject",
    "camera-motion-or-lighting",
)
SUPPORTED_FORMATS = {"JPEG", "PNG", "WEBP"}
SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


class Phase1BDatasetError(ValueError):
    """Raised when Phase 1B source preparation cannot proceed safely."""


def _manifest_result(dataset_path: Path, errors: list[str]) -> dict[str, Any]:
    return {
        "status": "fail",
        "dataset_path": str(dataset_path),
        "manifest_path": str(dataset_path / "manifest.json"),
        "errors": errors,
        "frames": [],
    }


def load_phase1b_manifest(dataset_path: Path) -> tuple[Phase1BDatasetManifest, str]:
    manifest_path = dataset_path / "manifest.json"
    try:
        payload = manifest_path.read_bytes()
    except FileNotFoundError as error:
        raise Phase1BDatasetError(f"Missing dataset manifest: {manifest_path}") from error
    try:
        manifest = Phase1BDatasetManifest.model_validate_json(payload)
    except ValidationError as error:
        raise Phase1BDatasetError(f"Invalid Phase 1B manifest: {error}") from error
    return manifest, sha256_file(manifest_path)


def validate_phase1b_dataset(dataset: str | Path) -> dict[str, Any]:
    dataset_path = Path(dataset).expanduser().resolve()
    if not dataset_path.is_dir():
        return _manifest_result(dataset_path, [f"Dataset directory does not exist: {dataset_path}"])

    try:
        manifest, manifest_sha256 = load_phase1b_manifest(dataset_path)
    except Phase1BDatasetError as error:
        return _manifest_result(dataset_path, [str(error)])

    declared_paths = {item.path for item in manifest.files}
    discovered_paths = {
        path.relative_to(dataset_path).as_posix()
        for path in dataset_path.rglob("*")
        if path.is_file()
        and path.name != "manifest.json"
        and path.suffix.lower() in SUPPORTED_SUFFIXES
    }
    undeclared = sorted(discovered_paths - declared_paths)
    missing_declared = sorted(declared_paths - discovered_paths)
    dataset_errors: list[str] = []
    if undeclared:
        dataset_errors.append(f"Undeclared supported image files: {undeclared}")
    if missing_declared:
        dataset_errors.append(f"Manifest-declared image files are missing: {missing_declared}")

    frames: list[dict[str, Any]] = []
    total_bytes = 0
    for index, item in enumerate(manifest.files):
        reasons: list[str] = []
        frame_path = dataset_path / item.path
        try:
            resolved = frame_path.resolve(strict=True)
            resolved.relative_to(dataset_path)
        except (FileNotFoundError, ValueError):
            reasons.append("path_missing_or_outside_dataset")
            resolved = frame_path

        byte_count = 0
        actual_sha256: str | None = None
        image_format: str | None = None
        mode: str | None = None
        dimensions: tuple[int, int] | None = None
        if not reasons:
            if frame_path.is_symlink() or not frame_path.is_file():
                reasons.append("not_a_regular_file")
            else:
                byte_count = frame_path.stat().st_size
                total_bytes += byte_count
                actual_sha256 = sha256_file(frame_path)
                if actual_sha256 != item.sha256:
                    reasons.append("checksum_mismatch")
                try:
                    with Image.open(frame_path) as image:
                        image_format = image.format
                        if image_format not in SUPPORTED_FORMATS:
                            reasons.append("unsupported_decoded_format")
                        normalized = ImageOps.exif_transpose(image)
                        normalized.load()
                        dimensions = normalized.size
                        mode = normalized.mode
                except (Image.DecompressionBombError, UnidentifiedImageError, OSError):
                    reasons.append("decode_failed")
                expected_dimensions = (
                    manifest.expected_dimensions.width,
                    manifest.expected_dimensions.height,
                )
                if dimensions is not None and dimensions != expected_dimensions:
                    reasons.append("normalized_dimensions_mismatch")

        frames.append(
            {
                "index": index,
                "path": item.path,
                "format": image_format,
                "mode": mode,
                "bytes": byte_count,
                "sha256": actual_sha256,
                "expected_sha256": item.sha256,
                "width": dimensions[0] if dimensions else None,
                "height": dimensions[1] if dimensions else None,
                "disposition": "accepted" if not reasons else "rejected",
                "reasons": reasons,
            }
        )

    rejected = [frame for frame in frames if frame["disposition"] == "rejected"]
    if rejected:
        dataset_errors.append(f"{len(rejected)} manifest frames failed validation")
    status = "pass" if not dataset_errors else "fail"
    return {
        "status": status,
        "dataset_id": manifest.id,
        "title": manifest.title,
        "scenario_category": manifest.scenario_category,
        "dataset_path": str(dataset_path),
        "manifest_path": str(dataset_path / "manifest.json"),
        "manifest_sha256": manifest_sha256,
        "frame_count": len(frames),
        "normalized_dimensions": manifest.expected_dimensions.model_dump(),
        "total_bytes": total_bytes,
        "provenance": manifest.provenance.model_dump(),
        "consent": manifest.consent.model_dump(),
        "license": manifest.license.model_dump(),
        "capture_notes": manifest.capture_notes,
        "known_limitations": manifest.known_limitations,
        "frames": frames,
        "errors": dataset_errors,
    }


def validate_phase1b_collection(root: str | Path) -> dict[str, Any]:
    root_path = Path(root).expanduser().resolve()
    results = [validate_phase1b_dataset(root_path / name) for name in PHASE1B_DATASET_IDS]
    ids = [result.get("dataset_id") for result in results if result.get("dataset_id")]
    collection_errors: list[str] = []
    if root_path.is_dir():
        unexpected_directories = sorted(
            path.name
            for path in root_path.iterdir()
            if path.is_dir() and path.name not in PHASE1B_DATASET_IDS
        )
        if unexpected_directories:
            collection_errors.append(
                f"Unexpected Phase 1B dataset directories: {unexpected_directories}"
            )
    if len(ids) != len(set(ids)):
        collection_errors.append("Dataset IDs are not unique")
    for expected_id, result in zip(PHASE1B_DATASET_IDS, results, strict=True):
        if result.get("dataset_id") != expected_id:
            collection_errors.append(
                f"Directory {expected_id} declares dataset ID {result.get('dataset_id')!r}"
            )
        if result.get("scenario_category") != expected_id:
            collection_errors.append(
                f"Dataset {expected_id} declares scenario {result.get('scenario_category')!r}"
            )
    status = (
        "pass"
        if not collection_errors and all(result["status"] == "pass" for result in results)
        else "fail"
    )
    return {
        "schema_version": "1.0",
        "status": status,
        "root": str(root_path),
        "dataset_order": list(PHASE1B_DATASET_IDS),
        "dataset_count": len(results),
        "total_frames": sum(int(result.get("frame_count", 0)) for result in results),
        "total_bytes": sum(int(result.get("total_bytes", 0)) for result in results),
        "datasets": results,
        "errors": collection_errors,
    }


def source_snapshot(validation: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "path": frame["path"],
            "bytes": frame["bytes"],
            "sha256": frame["sha256"],
        }
        for frame in validation["frames"]
    ]


def source_snapshot_matches(validation: dict[str, Any], snapshot: list[dict[str, Any]]) -> bool:
    return validation["status"] == "pass" and source_snapshot(validation) == snapshot


def prepare_phase1b_datasets(source: str | Path, destination: str | Path) -> dict[str, Any]:
    source_root = Path(source).expanduser().resolve()
    destination_root = Path(destination).expanduser().resolve()
    copied = 0
    existing = 0
    datasets: list[dict[str, Any]] = []
    for dataset_id in PHASE1B_DATASET_IDS:
        destination_dataset = destination_root / dataset_id
        manifest, _ = load_phase1b_manifest(destination_dataset)
        source_dataset = source_root / dataset_id
        dataset_copied = 0
        for item in manifest.files:
            source_path = source_dataset / item.path
            destination_path = destination_dataset / item.path
            if not source_path.is_file() or source_path.is_symlink():
                raise Phase1BDatasetError(f"Missing regular staging file: {source_path}")
            if sha256_file(source_path) != item.sha256:
                raise Phase1BDatasetError(f"Staging checksum mismatch: {source_path}")
            if destination_path.exists():
                if not destination_path.is_file() or sha256_file(destination_path) != item.sha256:
                    raise Phase1BDatasetError(
                        f"Refusing to overwrite differing destination: {destination_path}"
                    )
                existing += 1
                continue
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_path, destination_path)
            if sha256_file(destination_path) != item.sha256:
                raise Phase1BDatasetError(f"Copied checksum mismatch: {destination_path}")
            copied += 1
            dataset_copied += 1
        datasets.append(
            {
                "dataset_id": dataset_id,
                "frame_count": len(manifest.files),
                "copied": dataset_copied,
            }
        )
    return {
        "status": "pass",
        "source": str(source_root),
        "destination": str(destination_root),
        "copied": copied,
        "already_present": existing,
        "datasets": datasets,
    }
