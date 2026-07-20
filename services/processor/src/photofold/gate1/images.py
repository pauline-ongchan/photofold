"""Image encoding and measurement helpers used by Gate 1."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps
from skimage.metrics import structural_similarity


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_rgb(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        normalized = ImageOps.exif_transpose(image).convert("RGB")
        return np.asarray(normalized, dtype=np.uint8).copy()


def encode_webp(image: np.ndarray, quality: int) -> bytes:
    buffer = io.BytesIO()
    Image.fromarray(image, mode="RGB").save(
        buffer,
        format="WEBP",
        quality=quality,
        method=6,
        exact=True,
    )
    return buffer.getvalue()


def encode_png_gray(mask: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    Image.fromarray(mask, mode="L").save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def decode_rgb(payload: bytes) -> np.ndarray:
    with Image.open(io.BytesIO(payload)) as image:
        return np.asarray(image.convert("RGB"), dtype=np.uint8).copy()


def decode_gray(payload: bytes) -> np.ndarray:
    with Image.open(io.BytesIO(payload)) as image:
        return np.asarray(image.convert("L"), dtype=np.uint8).copy()


def rgb_ssim(original: np.ndarray, reconstruction: np.ndarray) -> float:
    return float(
        structural_similarity(
            original,
            reconstruction,
            data_range=255,
            channel_axis=2,
        )
    )


def rgb_psnr(original: np.ndarray, reconstruction: np.ndarray) -> float:
    difference = original.astype(np.float64) - reconstruction.astype(np.float64)
    mean_squared_error = float(np.mean(difference * difference))
    if mean_squared_error == 0:
        return float("inf")
    return float(10 * np.log10((255**2) / mean_squared_error))


def difference_heatmap(original: np.ndarray, reconstruction: np.ndarray) -> np.ndarray:
    difference = np.max(
        np.abs(original.astype(np.int16) - reconstruction.astype(np.int16)),
        axis=2,
    ).astype(np.uint8)
    return cv2.cvtColor(cv2.applyColorMap(difference, cv2.COLORMAP_INFERNO), cv2.COLOR_BGR2RGB)


def write_rgb_png(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(image, mode="RGB").save(path, format="PNG", optimize=True)


def write_gray_png(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(image, mode="L").save(path, format="PNG", optimize=True)
