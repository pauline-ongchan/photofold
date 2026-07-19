"""ORB reference selection and reference-to-target transform estimation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np


@dataclass(frozen=True)
class FeatureSet:
    keypoints: tuple[cv2.KeyPoint, ...]
    descriptors: np.ndarray | None


def analysis_copy(image: np.ndarray, max_dimension: int = 800) -> tuple[np.ndarray, float, float]:
    height, width = image.shape[:2]
    scale = min(1.0, max_dimension / max(width, height))
    target = (max(1, round(width * scale)), max(1, round(height * scale)))
    resized = cv2.resize(image, target, interpolation=cv2.INTER_AREA) if scale < 1 else image.copy()
    return resized, target[0] / width, target[1] / height


def _features(image: np.ndarray) -> FeatureSet:
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    detector = cv2.ORB_create(nfeatures=5000, fastThreshold=8)
    keypoints, descriptors = detector.detectAndCompute(gray, None)
    return FeatureSet(tuple(keypoints or ()), descriptors)


def _matched_points(
    source: FeatureSet,
    target: FeatureSet,
) -> tuple[np.ndarray, np.ndarray]:
    if source.descriptors is None or target.descriptors is None:
        raise ValueError("No ORB descriptors were found")
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    pairs = matcher.knnMatch(source.descriptors, target.descriptors, k=2)
    good = [first for first, second in pairs if first.distance < 0.76 * second.distance]
    if len(good) < 8:
        raise ValueError(f"Only {len(good)} reliable ORB matches were found")
    source_points = np.float32([source.keypoints[item.queryIdx].pt for item in good])
    target_points = np.float32([target.keypoints[item.trainIdx].pt for item in good])
    return source_points, target_points


def _full_matrix(matrix: np.ndarray, scale_x: float, scale_y: float) -> np.ndarray:
    scale = np.array([[scale_x, 0, 0], [0, scale_y, 0], [0, 0, 1]], dtype=np.float64)
    return np.linalg.inv(scale) @ matrix.astype(np.float64) @ scale


def _overlap(matrix: np.ndarray, width: int, height: int) -> float:
    source = np.full((height, width), 255, dtype=np.uint8)
    warped = cv2.warpPerspective(
        source,
        matrix,
        (width, height),
        flags=cv2.INTER_NEAREST,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )
    return float(np.count_nonzero(warped) / warped.size)


def _reprojection_error(
    source_points: np.ndarray,
    target_points: np.ndarray,
    matrix: np.ndarray,
    inliers: np.ndarray,
) -> float:
    projected = cv2.perspectiveTransform(source_points.reshape(-1, 1, 2), matrix).reshape(-1, 2)
    errors = np.linalg.norm(projected - target_points, axis=1)
    selected = errors[inliers.astype(bool).ravel()]
    return float(np.median(selected)) if selected.size else float("inf")


def _plausible_homography(matrix: np.ndarray, width: int, height: int) -> bool:
    corners = np.float32([[[0, 0], [width, 0], [width, height], [0, height]]])
    projected = cv2.perspectiveTransform(corners, matrix)[0]
    if not np.isfinite(projected).all():
        return False
    margin_x, margin_y = width * 0.3, height * 0.3
    if (
        projected[:, 0].min() < -margin_x
        or projected[:, 0].max() > width + margin_x
        or projected[:, 1].min() < -margin_y
        or projected[:, 1].max() > height + margin_y
    ):
        return False
    area = abs(cv2.contourArea(projected.astype(np.float32)))
    return 0.55 <= area / (width * height) <= 1.45


def estimate_transform(
    source: FeatureSet,
    target: FeatureSet,
    width: int,
    height: int,
    scale_x: float,
    scale_y: float,
    model: str,
) -> dict[str, Any]:
    source_points, target_points = _matched_points(source, target)
    if model == "affine":
        affine, inliers = cv2.estimateAffinePartial2D(
            source_points,
            target_points,
            method=cv2.RANSAC,
            ransacReprojThreshold=2.5,
            maxIters=5000,
            confidence=0.999,
            refineIters=20,
        )
        if affine is None or inliers is None:
            raise ValueError("RANSAC partial-affine estimation failed")
        small_matrix = np.vstack([affine, [0, 0, 1]]).astype(np.float64)
        transform_type = "affine"
    elif model == "homography":
        small_matrix, inliers = cv2.findHomography(
            source_points,
            target_points,
            cv2.RANSAC,
            2.5,
            maxIters=5000,
            confidence=0.999,
        )
        if small_matrix is None or inliers is None:
            raise ValueError("RANSAC homography estimation failed")
        if not _plausible_homography(small_matrix, width, height):
            raise ValueError("Homography failed projected-corner sanity checks")
        transform_type = "homography"
    else:
        raise ValueError(f"Unsupported transform model: {model}")

    inlier_count = int(np.count_nonzero(inliers))
    inlier_ratio = float(inlier_count / len(source_points))
    small_error = _reprojection_error(source_points, target_points, small_matrix, inliers)
    full_matrix = _full_matrix(small_matrix, scale_x, scale_y)
    return {
        "type": transform_type,
        "matrix": full_matrix,
        "inlier_count": inlier_count,
        "match_count": len(source_points),
        "inlier_ratio": inlier_ratio,
        "median_reprojection_error": float(small_error / min(scale_x, scale_y)),
        "valid_overlap": _overlap(small_matrix, width, height),
    }


def select_reference_and_align(images: list[np.ndarray]) -> dict[str, Any]:
    copies: list[np.ndarray] = []
    scales: list[tuple[float, float]] = []
    features: list[FeatureSet] = []
    sharpness: list[float] = []
    exposure_penalty: list[float] = []
    for image in images:
        resized, scale_x, scale_y = analysis_copy(image)
        copies.append(resized)
        scales.append((scale_x, scale_y))
        features.append(_features(resized))
        gray = cv2.cvtColor(resized, cv2.COLOR_RGB2GRAY)
        sharpness.append(float(cv2.Laplacian(gray, cv2.CV_64F).var()))
        exposure_penalty.append(float(np.mean((gray <= 3) | (gray >= 252))))

    min_sharpness, max_sharpness = min(sharpness), max(sharpness)
    sharpness_range = max(max_sharpness - min_sharpness, 1e-9)
    candidate_records: list[dict[str, Any]] = []
    pair_cache: dict[tuple[int, int], dict[str, Any]] = {}
    for source_index in range(len(images)):
        pair_metrics: list[dict[str, Any]] = []
        failures: list[int] = []
        for target_index in range(len(images)):
            if source_index == target_index:
                continue
            try:
                height, width = copies[target_index].shape[:2]
                result = estimate_transform(
                    features[source_index],
                    features[target_index],
                    width,
                    height,
                    scales[source_index][0],
                    scales[source_index][1],
                    "affine",
                )
                pair_cache[(source_index, target_index)] = result
                pair_metrics.append(result)
            except ValueError:
                failures.append(target_index)
        mean_inlier = (
            float(np.mean([item["inlier_ratio"] for item in pair_metrics]))
            if pair_metrics
            else 0
        )
        mean_overlap = (
            float(np.mean([item["valid_overlap"] for item in pair_metrics]))
            if pair_metrics
            else 0
        )
        sharpness_score = (sharpness[source_index] - min_sharpness) / sharpness_range
        success_ratio = len(pair_metrics) / max(1, len(images) - 1)
        score = (
            0.4 * mean_inlier
            + 0.3 * mean_overlap
            + 0.15 * sharpness_score
            + 0.15 * success_ratio
            - 0.1 * exposure_penalty[source_index]
        )
        candidate_records.append(
            {
                "index": source_index,
                "score": score,
                "mean_inlier_ratio": mean_inlier,
                "mean_valid_overlap": mean_overlap,
                "sharpness": sharpness[source_index],
                "sharpness_score": sharpness_score,
                "clipped_pixel_fraction": exposure_penalty[source_index],
                "alignment_success_count": len(pair_metrics),
                "alignment_failure_indices": failures,
            }
        )

    reference_index = max(candidate_records, key=lambda item: item["score"])["index"]
    height, width = images[0].shape[:2]
    transforms: list[dict[str, Any]] = []
    model_comparison: list[dict[str, Any]] = []
    for target_index in range(len(images)):
        if target_index == reference_index:
            transforms.append(
                {
                    "type": "identity",
                    "matrix": np.eye(3, dtype=np.float64),
                    "inlier_count": 0,
                    "match_count": 0,
                    "inlier_ratio": 1.0,
                    "median_reprojection_error": 0.0,
                    "valid_overlap": 1.0,
                }
            )
            continue
        affine = pair_cache[(reference_index, target_index)]
        try:
            homography = estimate_transform(
                features[reference_index],
                features[target_index],
                copies[target_index].shape[1],
                copies[target_index].shape[0],
                scales[reference_index][0],
                scales[reference_index][1],
                "homography",
            )
        except ValueError as error:
            homography = {"error": str(error)}
        chosen = affine
        reason = "partial affine is the conservative default"
        if "error" not in homography:
            materially_better = (
                homography["median_reprojection_error"]
                < affine["median_reprojection_error"] * 0.8
                and homography["inlier_ratio"] >= affine["inlier_ratio"] * 0.95
            )
            if materially_better:
                chosen = homography
                reason = "homography materially reduced reprojection error and passed sanity checks"
        transforms.append(chosen)
        model_comparison.append(
            {
                "frame_index": target_index,
                "affine": {key: value for key, value in affine.items() if key != "matrix"},
                "homography": {
                    key: value for key, value in homography.items() if key != "matrix"
                },
                "chosen": chosen["type"],
                "reason": reason,
            }
        )

    return {
        "reference_frame_index": reference_index,
        "reference_candidates": candidate_records,
        "transforms": transforms,
        "model_comparison": model_comparison,
        "width": width,
        "height": height,
    }


def warp_reference(
    reference: np.ndarray,
    matrix: np.ndarray,
    width: int,
    height: int,
) -> tuple[np.ndarray, np.ndarray]:
    warped = cv2.warpPerspective(
        reference,
        matrix,
        (width, height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0),
    )
    valid = cv2.warpPerspective(
        np.full(reference.shape[:2], 255, dtype=np.uint8),
        matrix,
        (width, height),
        flags=cv2.INTER_NEAREST,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )
    return warped, valid
