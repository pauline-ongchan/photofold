"""Runtime capability checks for the deterministic processor."""

from __future__ import annotations

import io
import platform
from importlib.metadata import version
from typing import Any

import cv2
import numpy as np
import skimage
from PIL import Image, features

from photofold import __version__


def _webp_roundtrip() -> bool:
    buffer = io.BytesIO()
    source = Image.new("RGB", (2, 2), color=(20, 40, 60))
    try:
        source.save(buffer, format="WEBP", lossless=True)
        buffer.seek(0)
        with Image.open(buffer) as decoded:
            decoded.load()
            return decoded.format == "WEBP" and decoded.size == source.size
    except (OSError, ValueError):
        return False


def run_doctor() -> dict[str, Any]:
    webp_available = features.check_module("webp")
    webp_roundtrip = _webp_roundtrip() if webp_available else False
    checks = {
        "webp_available": webp_available,
        "webp_roundtrip": webp_roundtrip,
        "opencv_import": bool(cv2.__version__),
        "numpy_import": bool(np.__version__),
        "scikit_image_import": bool(skimage.__version__),
    }
    return {
        "status": "pass" if all(checks.values()) else "fail",
        "service_version": __version__,
        "python_version": platform.python_version(),
        "checks": checks,
        "packages": {
            "fastapi": version("fastapi"),
            "numpy": np.__version__,
            "opencv-python-headless": version("opencv-python-headless"),
            "pillow": version("pillow"),
            "pydantic": version("pydantic"),
            "scikit-image": skimage.__version__,
            "uvicorn": version("uvicorn"),
        },
        "notes": [
            "Phase 0 checks capabilities only.",
            "No compression, reconstruction, storage, or quality result is produced.",
        ],
    }

