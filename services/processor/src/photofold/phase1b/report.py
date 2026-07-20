"""Self-contained Phase 1B report generation and structural verification."""

# ruff: noqa: E501

from __future__ import annotations

import base64
import hashlib
import html
import io
import json
import math
import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError

from photofold.gate1.bundle import PackageValidationError, verify_package
from photofold.gate1.images import sha256_file
from photofold.phase1b.aggregate import build_aggregate
from photofold.phase1b.baseline import MATCHED_QUALITIES, point_qualifies, select_matched_point
from photofold.phase1b.datasets import (
    PHASE1B_DATASET_IDS,
    source_snapshot,
    validate_phase1b_dataset,
)
from photofold.phase1b.models import (
    HumanDatasetReview,
    HumanReview,
    IndependentWebPPoint,
    Phase1BAggregateResult,
    Phase1BDatasetResult,
    PsnrValue,
)

REPORT_IMAGE_ROLES = (
    "original",
    "reconstruction",
    "heatmap",
    "mask",
    "alignment_overlay",
)


def _escape(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "PASS" if value else "FAIL"
    if isinstance(value, float):
        return f"{value:.9f}"
    if isinstance(value, (dict, list)):
        return html.escape(json.dumps(value, sort_keys=True))
    return html.escape(str(value))


def _table(headers: list[str], rows: list[list[Any]], css_class: str = "") -> str:
    head = "".join(f"<th>{html.escape(header)}</th>" for header in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{_escape(value)}</td>" for value in row) + "</tr>"
        for row in rows
    )
    return f'<table class="{css_class}"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def _preview_data_url(path: Path, max_dimension: int = 800) -> str:
    try:
        with Image.open(path) as image:
            normalized = ImageOps.exif_transpose(image).convert("RGB")
            normalized.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            normalized.save(
                buffer,
                format="WEBP",
                quality=75,
                method=4,
                exact=True,
            )
    except (FileNotFoundError, UnidentifiedImageError, OSError) as error:
        raise ValueError(f"Cannot embed report image {path}: {error}") from error
    return "data:image/webp;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def _psnr(value: dict[str, Any]) -> str:
    return "+∞" if value["is_infinite"] else f"{value['value_db']:.6f}"


def _status_badge(passed: bool, label: str) -> str:
    css = "pass" if passed else "fail"
    return f'<span class="badge {css}">{html.escape(label)}</span>'


def _psnr_float(value: PsnrValue | dict[str, Any]) -> float:
    if isinstance(value, PsnrValue):
        return float("inf") if value.is_infinite else float(value.value_db)
    return float("inf") if value["is_infinite"] else float(value["value_db"])


def _lowest_frame_indices(dataset: Phase1BDatasetResult) -> tuple[int, int]:
    lowest_ssim = min(
        dataset.per_frame,
        key=lambda frame: (float(frame["ssim"]), int(frame["index"])),
    )
    lowest_psnr = min(
        dataset.per_frame,
        key=lambda frame: (_psnr_float(frame["psnr_db"]), int(frame["index"])),
    )
    return int(lowest_ssim["index"]), int(lowest_psnr["index"])


def _dataset_section(
    root: Path,
    dataset_id: str,
    result: dict[str, Any],
    human_review: HumanDatasetReview | None,
) -> str:
    try:
        dataset = Phase1BDatasetResult.model_validate(result)
    except ValueError:
        if result.get("status") == "pass":
            raise
        failure = html.escape(json.dumps(result, indent=2, sort_keys=True))
        return (
            f'<section id="dataset-{dataset_id}" data-dataset-id="{dataset_id}" '
            'data-status="fail" data-frame-count="0" data-member-count="0">'
            f"<h2>{html.escape(dataset_id)}</h2>"
            f"{_status_badge(False, 'DATASET FAILED')}<pre>{failure}</pre></section>"
        )

    lowest_ssim, lowest_psnr = _lowest_frame_indices(dataset)
    if human_review is None:
        review_html = (
            "<p>Pending. Deliberately inspect lowest-SSIM frame "
            f"{lowest_ssim} and lowest-PSNR frame {lowest_psnr}.</p>"
        )
    else:
        review_html = (
            f"<p>Status: <strong>{html.escape(human_review.status.upper())}</strong>; "
            f"lowest-SSIM frame inspected: {human_review.lowest_ssim_frame_inspected}; "
            f"lowest-PSNR frame inspected: {human_review.lowest_psnr_frame_inspected}; "
            f"notes: {html.escape(human_review.notes)}</p>"
        )
    benchmark_sha256 = sha256_file(root / dataset_id / "benchmark.json")
    storage = dataset.storage
    matched = dataset.matched_webp.selected
    storage_rows = [
        ["Original source files", dataset.original_total_bytes, "baseline", "baseline"],
        [
            "Independent WebP q70",
            dataset.fixed_webp.total_bytes,
            storage["versus_fixed_webp"]["signed_bytes_saved"],
            storage["versus_fixed_webp"]["signed_savings_percent"],
        ],
        [
            f"Matched WebP q{matched.quality}" if matched else "Matched WebP (unmatched)",
            matched.total_bytes if matched else None,
            (
                storage["versus_matched_webp"]["signed_bytes_saved"]
                if storage["versus_matched_webp"]
                else None
            ),
            (
                storage["versus_matched_webp"]["signed_savings_percent"]
                if storage["versus_matched_webp"]
                else None
            ),
        ],
        [
            "PhotoFold closed package",
            dataset.photofold_package_bytes,
            storage["versus_originals"]["signed_bytes_saved"],
            storage["versus_originals"]["signed_savings_percent"],
        ],
    ]
    quality_rows = []
    for label, quality in (
        ("PhotoFold", dataset.quality["photofold"]),
        (
            "Fixed WebP q70",
            {
                "mean_ssim": dataset.fixed_webp.mean_ssim,
                "minimum_ssim": dataset.fixed_webp.minimum_ssim,
                "mean_psnr_db": dataset.fixed_webp.mean_psnr_db.model_dump(mode="json"),
                "minimum_psnr_db": dataset.fixed_webp.minimum_psnr_db.model_dump(
                    mode="json"
                ),
            },
        ),
    ):
        quality_rows.append(
            [
                label,
                quality["mean_ssim"],
                quality["minimum_ssim"],
                _psnr(quality["mean_psnr_db"]),
                _psnr(quality["minimum_psnr_db"]),
            ]
        )
    if matched:
        quality_rows.append(
            [
                f"Matched WebP q{matched.quality}",
                matched.mean_ssim,
                matched.minimum_ssim,
                _psnr(matched.mean_psnr_db.model_dump(mode="json")),
                _psnr(matched.minimum_psnr_db.model_dump(mode="json")),
            ]
        )

    validation_rows = [
        [
            item["index"],
            item["path"],
            item["disposition"],
            ", ".join(item.get("reasons", [])) or "validated",
            item["bytes"],
            item["sha256"],
        ]
        for item in dataset.validation["frames"]
    ]
    frame_cards = []
    dataset_directory = root / dataset_id
    for frame in dataset.per_frame:
        artifact_paths = {
            "original": Path(frame["artifacts"]["original"]),
            "reconstruction": dataset_directory / frame["artifacts"]["reconstruction"],
            "heatmap": dataset_directory / frame["artifacts"]["heatmap"],
            "mask": dataset_directory / frame["artifacts"]["mask"],
            "alignment_overlay": dataset_directory
            / frame["artifacts"]["alignment_overlay"],
        }
        figures = []
        for role in REPORT_IMAGE_ROLES:
            label = role.replace("_", " ").title()
            figures.append(
                f'<figure data-image-role="{role}"><img alt="{html.escape(dataset_id)} '
                f'frame {frame["index"]} {label}" src="{_preview_data_url(artifact_paths[role])}">'
                f"<figcaption>{label}</figcaption></figure>"
            )
        matched_frame = frame.get("matched_webp")
        metrics = (
            f'{frame["width"]}×{frame["height"]}; '
            f'PhotoFold SSIM {frame["ssim"]:.9f}, PSNR {_psnr(frame["psnr_db"])} dB; '
            f'fixed q70 {frame["fixed_webp"]["bytes"]:,} B, '
            f'SSIM {frame["fixed_webp"]["ssim"]:.9f}, '
            f'PSNR {_psnr(frame["fixed_webp"]["psnr_db"])} dB; '
            + (
                f'matched q{matched.quality} {matched_frame["bytes"]:,} B, '
                f'SSIM {matched_frame["ssim"]:.9f}, '
                f'PSNR {_psnr(matched_frame["psnr_db"])} dB'
                if matched_frame is not None
                else "matched control unavailable"
            )
        )
        figure_html = "".join(figures)
        frame_cards.append(
            f'<article class="frame" data-frame-index="{frame["index"]}">'
            f'<h3>Frame {frame["index"]}: {html.escape(frame["filename"])}</h3>'
            f'<p>{metrics}</p><div class="images">{figure_html}</div></article>'
        )

    check_rows = [
        [
            check.id,
            check.label,
            "PASS" if check.passed else "FAIL",
            "required" if check.required_for_machine_pass else "scientific indicator",
            check.detail,
        ]
        for check in dataset.checks
    ]
    timing_rows = [[key, dataset.timings[key]] for key in sorted(dataset.timings)]
    curve_rows = [
        [
            point.quality,
            point.total_bytes,
            point.mean_ssim,
            point.minimum_ssim,
            _psnr(point.mean_psnr_db.model_dump(mode="json")),
            _psnr(point.minimum_psnr_db.model_dump(mode="json")),
            "YES" if point.quality in dataset.matched_webp.qualifying_qualities else "NO",
        ]
        for point in dataset.matched_webp.curve
    ]
    member_rows = [
        [
            member.path,
            member.role,
            member.stored_bytes,
            member.uncompressed_bytes,
            member.sha256,
        ]
        for member in dataset.package_members
    ]
    environment_rows = [
        [key, dataset.environment[key]] for key in sorted(dataset.environment)
    ]
    return f"""
<section id="dataset-{dataset_id}" data-dataset-id="{dataset_id}" data-status="{dataset.status}"
 data-benchmark-sha256="{benchmark_sha256}" data-frame-count="{len(dataset.per_frame)}"
 data-member-count="{len(dataset.package_members)}">
  <h2>{html.escape(dataset.validation['title'])} <small>{dataset_id}</small></h2>
  <p>{_status_badge(dataset.machine_pass, 'MACHINE PASS' if dataset.machine_pass else 'MACHINE FAIL')}
  {_status_badge(dataset.source_immutability_pass, 'SOURCE IMMUTABLE' if dataset.source_immutability_pass else 'SOURCE CHANGED')}
  {_status_badge(matched is not None, 'MATCHED BASELINE' if matched else 'UNMATCHED BASELINE')}
  {_status_badge(dataset.human_visual_review_status == 'pass', 'VISUAL PASS' if dataset.human_visual_review_status == 'pass' else dataset.human_visual_review_status.upper())}</p>
  <p>Manifest SHA-256: <code>{dataset.manifest_sha256}</code><br>
  Config: <code>{html.escape(dataset.config_path)}</code> · <code>{dataset.config_sha256}</code><br>
  Package: <code>{dataset.photofold_package_sha256}</code> · reference frame {dataset.reference_frame_index}</p>
  <h3>Frozen treatment parameters</h3>
  {_table(['Parameter', 'Value'], [[key, dataset.parameters[key]] for key in sorted(dataset.parameters)])}
  <h3>Independent-WebP encoder settings</h3>
  {_table(['Setting', 'Value'], [[key, value] for key, value in dataset.webp_control_settings.model_dump(mode='json').items()])}
  <h3>Storage</h3>
  {_table(['Treatment', 'Bytes', 'Signed bytes saved', 'Signed savings %'], storage_rows)}
  <h3>Quality</h3>
  {_table(['Treatment', 'Mean SSIM', 'Minimum SSIM', 'Mean PSNR dB', 'Minimum PSNR dB'], quality_rows)}
  <h3>Source validation and dispositions</h3>
  {_table(['Index', 'Path', 'Disposition', 'Reason', 'Bytes', 'SHA-256'], validation_rows)}
  <h3>Frame evidence</h3>
  {''.join(frame_cards)}
  <h3>Integrity and scientific checks</h3>
  {_table(['ID', 'Check', 'Result', 'Role', 'Detail'], check_rows)}
  <h3>Timing</h3>
  {_table(['Stage', 'Observation'], timing_rows)}
  <h3>Runtime environment</h3>
  {_table(['Field', 'Value'], environment_rows)}
  <h3>Human visual review</h3>
  {review_html}
  <details><summary>Alignment evidence</summary><pre>{html.escape(json.dumps(dataset.alignment, indent=2, sort_keys=True))}</pre></details>
  <details><summary>Complete independent-WebP q1–q100 curve</summary>
  {_table(['q', 'Bytes', 'Mean SSIM', 'Min SSIM', 'Mean PSNR', 'Min PSNR', 'Qualifies'], curve_rows)}
  </details>
  <h3>Package overhead</h3>
  {_table(['Field', 'Value'], [[key, dataset.package_overhead[key]] for key in sorted(dataset.package_overhead)])}
  <details><summary>Complete package listing ({len(member_rows)} members)</summary>
  {_table(['Path', 'Role', 'Stored bytes', 'Payload bytes', 'SHA-256'], member_rows)}
  </details>
</section>
"""


def _render_phase1b_report(
    artifact_root: str | Path,
    results: dict[str, dict[str, Any]],
    aggregate: Phase1BAggregateResult,
) -> str:
    root = Path(artifact_root).expanduser().resolve()
    aggregate_rows = [
        [
            item.dataset_id,
            item.dataset_status,
            item.original_total_bytes,
            item.fixed_webp_total_bytes,
            item.matched_webp_total_bytes,
            item.photofold_package_bytes,
            item.relational_savings_percent,
            item.matched_status,
        ]
        for item in aggregate.datasets
    ]
    review = aggregate.human_review
    review_text = (
        "Human visual review is pending; use the generated review template."
        if review is None
        else (
            f"Reviewed by {html.escape(review.reviewer)} at {review.reviewed_at.isoformat()}; "
            f"complexity veto: {'YES' if review.complexity_disproportionate else 'NO'}; "
            f"notes: {html.escape(review.complexity_notes)}"
        )
    )
    dataset_sections = "".join(
        _dataset_section(
            root,
            dataset_id,
            results[dataset_id],
            review.datasets.get(dataset_id) if review is not None else None,
        )
        for dataset_id in PHASE1B_DATASET_IDS
    )
    phase_label = "PHASE PASS" if aggregate.phase_pass else "PHASE INCOMPLETE/FAIL"
    reasons = "".join(f"<li>{html.escape(reason)}</li>" for reason in aggregate.recommendation_reasons)
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PhotoFold Phase 1B validation report</title>
<style>
:root {{ color-scheme: light dark; font-family: ui-sans-serif, system-ui, sans-serif; }}
body {{ margin: 0 auto; max-width: 1500px; padding: 1.5rem; line-height: 1.45; }}
h1,h2 {{ letter-spacing: -.025em; }} section {{ border-top: 3px solid #667; margin-top: 2rem; padding-top: 1rem; }}
.hero {{ border: 2px solid #667; border-radius: 12px; padding: 1rem 1.25rem; }}
.badge {{ border-radius: 999px; display: inline-block; font-weight: 700; margin: .2rem; padding: .3rem .7rem; }}
.pass {{ background: #0b6; color: white; }} .fail {{ background: #b32; color: white; }}
table {{ border-collapse: collapse; display: block; font-size: .86rem; max-width: 100%; overflow-x: auto; }}
th,td {{ border: 1px solid #7788; padding: .35rem .5rem; text-align: left; vertical-align: top; }}
.frame {{ border: 1px solid #7788; border-radius: 8px; margin: 1rem 0; padding: .75rem; }}
.images {{ display: grid; gap: .65rem; grid-template-columns: repeat(auto-fit,minmax(210px,1fr)); }}
figure {{ margin: 0; }} img {{ background: #222; display: block; height: auto; max-height: 520px; object-fit: contain; width: 100%; }}
figcaption {{ font-weight: 650; padding-top: .25rem; }} code,pre {{ overflow-wrap: anywhere; white-space: pre-wrap; }}
small {{ font-weight: normal; }} details {{ margin: 1rem 0; }} summary {{ cursor: pointer; font-weight: 700; }}
</style></head>
<body data-report-version="1.0" data-recommendation="{html.escape(aggregate.recommendation, quote=True)}"
 data-phase-pass="{str(aggregate.phase_pass).lower()}" data-dataset-count="3">
<header class="hero"><h1>PhotoFold Phase 1B multi-dataset validation</h1>
<p>{_status_badge(aggregate.phase_pass, phase_label)} <strong>Recommendation: {html.escape(aggregate.recommendation)}</strong></p>
<ul>{reasons}</ul><p>{review_text}</p></header>
<section id="methodology"><h2>Methodology and fixed thresholds</h2>
<p>One frozen Gate 1 PhotoFold treatment is applied sequentially to all three manifest-ordered datasets. The fixed control independently encodes every normalized RGB frame as WebP q70, method 6, exact true. The quality-matched baseline exhaustively evaluates every integer q1 through q100 in ascending order, with one common quality per dataset. A point qualifies only when every frame has candidate SSIM + 0.000001 ≥ PhotoFold SSIM and candidate PSNR + 0.0001 dB ≥ PhotoFold PSNR. Selection minimizes total payload bytes, then quality, then the lexicographic per-frame byte vector. Infinite PSNR is represented explicitly. Timings use time.perf_counter_ns, exclude report rendering, and are not comparable across machines.</p></section>
<section id="decision-criteria"><h2>Ordered decision criteria</h2>
<ol><li><strong>PIVOT</strong> for any reconstruction/package-integrity failure, any human-visible quality regression, median matched saving below 5%, at least two dataset losses, or a documented disproportionate-complexity veto.</li>
<li><strong>CONTINUE COMPRESSION-FIRST</strong> for median matched saving at least 10%, at least two dataset wins, complete reconstruction/package/matched-quality evidence, and a clean human review.</li>
<li><strong>INVESTIGATE</strong> for median matched saving from 5% inclusive to below 10%, with complete machine and visual evidence and no pivot veto.</li>
<li><strong>PIVOT</strong> for every remaining combination.</li></ol></section>
<section id="aggregate"><h2>Aggregate result</h2>
{_table(['Dataset', 'Status', 'Original B', 'Fixed B', 'Matched B', 'PhotoFold B', 'Matched saving %', 'Match'], aggregate_rows)}
{_table(['Metric', 'Value'], [
['Aggregate original bytes', aggregate.aggregate_original_bytes],
['Aggregate fixed WebP bytes', aggregate.aggregate_fixed_webp_bytes],
['Aggregate matched WebP bytes', aggregate.aggregate_matched_webp_bytes],
['Aggregate PhotoFold bytes', aggregate.aggregate_photofold_bytes],
['Median matched saving %', aggregate.median_relational_savings_percent],
['Weighted matched saving %', aggregate.weighted_mean_relational_savings_percent],
['Best dataset', f'{aggregate.best_dataset_id}: {aggregate.best_relational_savings_percent}'],
['Worst dataset', f'{aggregate.worst_dataset_id}: {aggregate.worst_relational_savings_percent}'],
['Wins / losses / ties', f'{aggregate.win_count} / {aggregate.loss_count} / {aggregate.tie_count}'],
['Accepted / reconstructed frames', f'{aggregate.total_accepted_frames} / {aggregate.total_reconstructed_frames}'],
])}</section>
{dataset_sections}
</body></html>"""
    return document


def generate_phase1b_report(
    artifact_root: str | Path,
    results: dict[str, dict[str, Any]],
    aggregate: Phase1BAggregateResult,
) -> dict[str, Any]:
    root = Path(artifact_root).expanduser().resolve()
    report_path = root / "report.html"
    document = _render_phase1b_report(root, results, aggregate)
    root.mkdir(parents=True, exist_ok=True)
    report_path.write_text(document, encoding="utf-8")
    return {
        "status": "pass",
        "report": str(report_path),
        "bytes": report_path.stat().st_size,
        "sha256": sha256_file(report_path),
        "embedded_image_count": document.count("data:image/webp;base64,"),
    }


def _load_results(root: Path) -> dict[str, dict[str, Any]]:
    return {
        dataset_id: json.loads(
            (root / dataset_id / "benchmark.json").read_text(encoding="utf-8")
        )
        for dataset_id in PHASE1B_DATASET_IDS
    }


def _decode_embedded_images(document: str) -> tuple[int, list[str]]:
    errors: list[str] = []
    sources = re.findall(r'<img[^>]+src="([^"]+)"', document)
    for index, source in enumerate(sources):
        if not source.startswith("data:image/") or ";base64," not in source:
            errors.append(f"image {index} is not an embedded base64 data URL")
            continue
        try:
            payload = base64.b64decode(source.split(",", 1)[1], validate=True)
            with Image.open(io.BytesIO(payload)) as image:
                image.verify()
        except (ValueError, UnidentifiedImageError, OSError) as error:
            errors.append(f"image {index} cannot be decoded: {error}")
    return len(sources), errors


def _contains_placeholder(document: str) -> bool:
    scrubbed = re.sub(
        r"data:image/[^;\"']+;base64,[A-Za-z0-9+/=]+",
        "data:image/embedded;base64,REDACTED",
        document,
    )
    return bool(
        re.search(
            r"\b(?:TODO|TBD|PLACEHOLDER|REPLACE_WITH)\b",
            scrubbed,
            flags=re.IGNORECASE,
        )
    )


def _float_matches(actual: float, expected: float, tolerance: float = 1e-12) -> bool:
    return math.isclose(float(actual), float(expected), rel_tol=tolerance, abs_tol=tolerance)


def _psnr_matches(actual: PsnrValue | dict[str, Any], expected: float) -> bool:
    value = actual if isinstance(actual, PsnrValue) else PsnrValue.model_validate(actual)
    if math.isinf(expected):
        return value.is_infinite and value.value_db is None
    return (
        not value.is_infinite
        and value.value_db is not None
        and _float_matches(value.value_db, expected)
    )


def _point_consistency_errors(
    point: IndependentWebPPoint,
    label: str,
    expected_frame_count: int,
) -> list[str]:
    errors: list[str] = []
    indices = [frame.index for frame in point.per_frame]
    if indices != list(range(expected_frame_count)):
        errors.append(f"{label} frame indices are not complete and ordered")
    if point.total_bytes != sum(frame.bytes for frame in point.per_frame):
        errors.append(f"{label} byte total does not equal its frame payloads")
    ssim_values = [frame.ssim for frame in point.per_frame]
    psnr_values = [_psnr_float(frame.psnr_db) for frame in point.per_frame]
    if ssim_values:
        if not _float_matches(point.mean_ssim, sum(ssim_values) / len(ssim_values)):
            errors.append(f"{label} mean SSIM does not recompute")
        if not _float_matches(point.minimum_ssim, min(ssim_values)):
            errors.append(f"{label} minimum SSIM does not recompute")
        expected_mean_psnr = sum(psnr_values) / len(psnr_values)
        if not _psnr_matches(point.mean_psnr_db, expected_mean_psnr):
            errors.append(f"{label} mean PSNR does not recompute")
        if not _psnr_matches(point.minimum_psnr_db, min(psnr_values)):
            errors.append(f"{label} minimum PSNR does not recompute")
    return errors


def _quality_summary_errors(
    summary: dict[str, Any],
    frames: list[dict[str, Any]],
    label: str,
) -> list[str]:
    errors: list[str] = []
    ssim_values = [float(frame["ssim"]) for frame in frames]
    psnr_values = [_psnr_float(frame["psnr_db"]) for frame in frames]
    expected = {
        "mean_ssim": sum(ssim_values) / len(ssim_values),
        "minimum_ssim": min(ssim_values),
        "mean_psnr_db": sum(psnr_values) / len(psnr_values),
        "minimum_psnr_db": min(psnr_values),
    }
    if not _float_matches(summary["mean_ssim"], expected["mean_ssim"]):
        errors.append(f"{label} mean SSIM does not recompute")
    if not _float_matches(summary["minimum_ssim"], expected["minimum_ssim"]):
        errors.append(f"{label} minimum SSIM does not recompute")
    if not _psnr_matches(summary["mean_psnr_db"], expected["mean_psnr_db"]):
        errors.append(f"{label} mean PSNR does not recompute")
    if not _psnr_matches(summary["minimum_psnr_db"], expected["minimum_psnr_db"]):
        errors.append(f"{label} minimum PSNR does not recompute")
    return errors


def _signed_comparison(reference_bytes: int, package_bytes: int) -> dict[str, Any]:
    saved = reference_bytes - package_bytes
    return {
        "reference_bytes": reference_bytes,
        "photofold_bytes": package_bytes,
        "signed_bytes_saved": saved,
        "signed_savings_percent": saved / reference_bytes * 100,
        "result": "win" if saved > 0 else "loss" if saved < 0 else "tie",
    }


def _comparison_matches(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    return all(
        _float_matches(actual[key], value) if isinstance(value, float) else actual[key] == value
        for key, value in expected.items()
    )


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


def _dataset_consistency_errors(
    dataset_id: str,
    dataset: Phase1BDatasetResult,
    verification: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    validation = dataset.validation
    expected_sources = [
        {"path": frame["path"], "bytes": frame["bytes"], "sha256": frame["sha256"]}
        for frame in validation["frames"]
    ]
    source_before = [item.model_dump(mode="json") for item in dataset.source_before]
    source_after = [item.model_dump(mode="json") for item in dataset.source_after]
    if source_before != expected_sources or source_after != expected_sources:
        errors.append(f"{dataset_id} source inventories do not match validation")
    current_validation = validate_phase1b_dataset(dataset.dataset_path)
    if (
        current_validation.get("status") != "pass"
        or source_snapshot(current_validation) != expected_sources
        or not dataset.source_immutability_pass
    ):
        errors.append(f"{dataset_id} current sources do not match the bound snapshot")
    expected_original_bytes = sum(int(frame["bytes"]) for frame in validation["frames"])
    if (
        dataset.original_total_bytes != expected_original_bytes
        or validation["total_bytes"] != expected_original_bytes
    ):
        errors.append(f"{dataset_id} original byte total does not reconcile")

    frame_count = len(dataset.per_frame)
    errors.extend(_point_consistency_errors(dataset.fixed_webp, f"{dataset_id} fixed q70", frame_count))
    if dataset.fixed_webp.quality != 70:
        errors.append(f"{dataset_id} fixed control is not WebP q70")
    qualities = [point.quality for point in dataset.matched_webp.curve]
    if qualities != sorted(set(qualities)):
        errors.append(f"{dataset_id} matched curve is not unique and ascending")
    if dataset.full_curve_required and qualities != list(MATCHED_QUALITIES):
        errors.append(f"{dataset_id} matched curve is not exhaustive q1 through q100")
    for point in dataset.matched_webp.curve:
        errors.extend(
            _point_consistency_errors(
                point,
                f"{dataset_id} matched q{point.quality}",
                frame_count,
            )
        )
    matching_input = [
        {
            "index": int(frame["index"]),
            "ssim": float(frame["ssim"]),
            "psnr_db": _psnr_float(frame["psnr_db"]),
        }
        for frame in dataset.per_frame
    ]
    recalculated_selected = select_matched_point(dataset.matched_webp.curve, matching_input)
    recalculated_qualities = [
        point.quality
        for point in dataset.matched_webp.curve
        if point_qualifies(point, matching_input)
    ]
    recorded_selected = dataset.matched_webp.selected
    if (recalculated_selected is None) != (recorded_selected is None):
        errors.append(f"{dataset_id} matched-control status does not recompute")
    elif (
        recalculated_selected is not None
        and recorded_selected is not None
        and recalculated_selected.model_dump(mode="json")
        != recorded_selected.model_dump(mode="json")
    ):
        errors.append(f"{dataset_id} selected matched point is not the minimum qualifier")
    if recalculated_qualities != dataset.matched_webp.qualifying_qualities:
        errors.append(f"{dataset_id} qualifying quality list does not recompute")
    q70 = next((point for point in dataset.matched_webp.curve if point.quality == 70), None)
    if q70 is not None and q70.model_dump(
        mode="json", exclude={"timing"}
    ) != dataset.fixed_webp.model_dump(mode="json", exclude={"timing"}):
        errors.append(f"{dataset_id} fixed q70 content differs from matched-curve q70")

    if frame_count != len(validation["frames"]):
        errors.append(f"{dataset_id} frame evidence count differs from validation")
    expected_width = int(validation["normalized_dimensions"]["width"])
    expected_height = int(validation["normalized_dimensions"]["height"])
    for index, frame in enumerate(dataset.per_frame):
        if int(frame["index"]) != index:
            errors.append(f"{dataset_id} frame evidence is not ordered")
            continue
        if (
            frame["filename"] != validation["frames"][index]["path"]
            or int(frame["original_bytes"]) != int(validation["frames"][index]["bytes"])
            or not frame["accepted"]
            or not frame["reconstructed"]
            or int(frame["width"]) != expected_width
            or int(frame["height"]) != expected_height
        ):
            errors.append(f"{dataset_id} frame {index} evidence differs from validation")
        fixed = dataset.fixed_webp.per_frame[index]
        if (
            int(frame["fixed_webp"]["bytes"]) != fixed.bytes
            or not _float_matches(frame["fixed_webp"]["ssim"], fixed.ssim)
            or not _psnr_matches(frame["fixed_webp"]["psnr_db"], _psnr_float(fixed.psnr_db))
        ):
            errors.append(f"{dataset_id} frame {index} fixed-control evidence differs")
        matched = recorded_selected.per_frame[index] if recorded_selected is not None else None
        recorded_matched = frame.get("matched_webp")
        matched_mismatch = (matched is None) != (recorded_matched is None) or (
            matched is not None
            and recorded_matched is not None
            and (
                int(recorded_matched["bytes"]) != matched.bytes
                or not _float_matches(recorded_matched["ssim"], matched.ssim)
                or not _psnr_matches(
                    recorded_matched["psnr_db"], _psnr_float(matched.psnr_db)
                )
            )
        )
        if matched_mismatch:
            errors.append(f"{dataset_id} frame {index} matched-control evidence differs")

    errors.extend(
        _quality_summary_errors(dataset.quality["photofold"], dataset.per_frame, f"{dataset_id} PhotoFold")
    )
    fixed_frames = [frame.model_dump(mode="json") for frame in dataset.fixed_webp.per_frame]
    errors.extend(
        _quality_summary_errors(dataset.quality["fixed_webp"], fixed_frames, f"{dataset_id} fixed q70")
    )
    if recorded_selected is not None:
        matched_frames = [frame.model_dump(mode="json") for frame in recorded_selected.per_frame]
        errors.extend(
            _quality_summary_errors(
                dataset.quality["matched_webp"],
                matched_frames,
                f"{dataset_id} matched WebP",
            )
        )

    package_bytes = int(verification["package_total_bytes"])
    if (
        dataset.photofold_package_bytes != package_bytes
        or dataset.photofold_package_sha256 != verification["package_sha256"]
    ):
        errors.append(f"{dataset_id} package stat/checksum differs from result")
    actual_members = [
        {
            "path": member["path"],
            "role": _member_role(member["path"]),
            "stored_bytes": member["compressed_bytes"],
            "uncompressed_bytes": member["bytes"],
            "sha256": member["sha256"],
        }
        for member in sorted(verification["members"], key=lambda item: item["path"])
    ]
    recorded_members = [member.model_dump(mode="json") for member in dataset.package_members]
    if recorded_members != actual_members:
        errors.append(f"{dataset_id} package listing differs from the closed archive")
    payload_bytes = sum(member["uncompressed_bytes"] for member in actual_members)
    stored_bytes = sum(member["stored_bytes"] for member in actual_members)
    expected_overhead = {
        "member_count": len(actual_members),
        "member_payload_bytes": payload_bytes,
        "member_stored_bytes": stored_bytes,
        "container_overhead_bytes": package_bytes - payload_bytes,
        "container_overhead_percent": (package_bytes - payload_bytes) / package_bytes * 100,
        "reconciles": True,
    }
    if any(
        not _float_matches(dataset.package_overhead[key], value)
        if isinstance(value, float)
        else dataset.package_overhead[key] != value
        for key, value in expected_overhead.items()
    ):
        errors.append(f"{dataset_id} package overhead does not reconcile")

    expected_storage = {
        "versus_originals": _signed_comparison(dataset.original_total_bytes, package_bytes),
        "versus_fixed_webp": _signed_comparison(dataset.fixed_webp.total_bytes, package_bytes),
        "versus_matched_webp": (
            _signed_comparison(recorded_selected.total_bytes, package_bytes)
            if recorded_selected is not None
            else None
        ),
    }
    for key, expected in expected_storage.items():
        actual = dataset.storage[key]
        if (expected is None) != (actual is None) or (
            expected is not None and actual is not None and not _comparison_matches(actual, expected)
        ):
            errors.append(f"{dataset_id} storage comparison {key} does not recompute")

    failed_required = [
        check.id
        for check in dataset.checks
        if check.required_for_machine_pass and not check.passed
    ]
    if dataset.failed_checks != failed_required or dataset.machine_pass != (not failed_required):
        errors.append(f"{dataset_id} machine verdict does not match required checks")
    if (
        dataset.accepted_frame_count != frame_count
        or dataset.reconstructed_frame_count != frame_count
        or verification["frame_count"] != frame_count
        or not verification["package_only_decode"]
    ):
        errors.append(f"{dataset_id} accepted/reconstructed/package counts do not reconcile")
    return errors


def verify_phase1b_report(report: str | Path) -> dict[str, Any]:
    report_path = Path(report).expanduser().resolve()
    root = report_path.parent
    errors: list[str] = []
    try:
        document = report_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"status": "fail", "report": str(report_path), "errors": ["report missing"]}
    try:
        aggregate_payload = json.loads((root / "aggregate.json").read_text(encoding="utf-8"))
        aggregate = Phase1BAggregateResult.model_validate(aggregate_payload)
        results = _load_results(root)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as error:
        return {
            "status": "fail",
            "report": str(report_path),
            "errors": [f"machine evidence cannot be loaded: {error}"],
        }

    human_review = (
        HumanReview.model_validate(aggregate.human_review)
        if aggregate.human_review is not None
        else None
    )
    recalculated = build_aggregate(results, human_review)
    comparison_fields = (
        "dataset_order",
        "datasets",
        "aggregate_original_bytes",
        "aggregate_fixed_webp_bytes",
        "aggregate_matched_webp_bytes",
        "aggregate_photofold_bytes",
        "median_relational_savings_percent",
        "weighted_mean_relational_savings_percent",
        "best_dataset_id",
        "best_relational_savings_percent",
        "worst_dataset_id",
        "worst_relational_savings_percent",
        "win_count",
        "loss_count",
        "tie_count",
        "total_accepted_frames",
        "total_reconstructed_frames",
        "relational_evidence_complete",
        "recommendation",
        "recommendation_reasons",
        "phase_pass",
        "failed_checks",
    )
    for field in comparison_fields:
        if getattr(aggregate, field) != getattr(recalculated, field):
            errors.append(f"aggregate field {field} does not recompute")

    try:
        expected_document = _render_phase1b_report(root, results, aggregate)
        if document != expected_document:
            errors.append("report content differs from current machine evidence")
    except (FileNotFoundError, UnidentifiedImageError, OSError, ValueError) as error:
        errors.append(f"report cannot be regenerated from current evidence: {error}")

    expected_images = 0
    expected_frames = 0
    for dataset_id in PHASE1B_DATASET_IDS:
        result = results[dataset_id]
        section_marker = f'id="dataset-{dataset_id}"'
        if section_marker not in document:
            errors.append(f"missing dataset section: {dataset_id}")
        try:
            dataset = Phase1BDatasetResult.model_validate(result)
        except ValueError as error:
            if result.get("status") == "pass":
                errors.append(f"{dataset_id} passing result is invalid: {error}")
            continue
        try:
            verification = verify_package(root / dataset_id / "moment.photofold")
            errors.extend(
                _dataset_consistency_errors(dataset_id, dataset, verification)
            )
        except (
            FileNotFoundError,
            IndexError,
            KeyError,
            OSError,
            TypeError,
            ValueError,
            PackageValidationError,
        ) as error:
            errors.append(f"{dataset_id} package/result verification failed: {error}")
            continue
        if verification["package_total_bytes"] != dataset.photofold_package_bytes:
            errors.append(f"{dataset_id} package byte count differs")
        if verification["package_sha256"] != dataset.photofold_package_sha256:
            errors.append(f"{dataset_id} package checksum differs")
        if len(verification["members"]) != len(dataset.package_members):
            errors.append(f"{dataset_id} package member count differs")
        expected_frames += len(dataset.per_frame)
        expected_images += len(dataset.per_frame) * len(REPORT_IMAGE_ROLES)

    if document.count('data-frame-index="') != expected_frames:
        errors.append(
            f"expected {expected_frames} frame evidence cards, "
            f"found {document.count('data-frame-index=') }"
        )

    image_count, image_errors = _decode_embedded_images(document)
    errors.extend(image_errors)
    if image_count != expected_images:
        errors.append(f"expected {expected_images} embedded images, found {image_count}")
    if re.search(r'<(?:img|script|link)[^>]+(?:src|href)="(?!data:|#)', document):
        errors.append("report contains an external dependency")
    if _contains_placeholder(document):
        errors.append("report contains a blank or hard-coded placeholder")
    recommendation_marker = f'data-recommendation="{html.escape(aggregate.recommendation, quote=True)}"'
    if recommendation_marker not in document:
        errors.append("displayed recommendation differs from aggregate.json")
    if 'data-dataset-count="3"' not in document:
        errors.append("report dataset count is not three")
    return {
        "status": "pass" if not errors else "fail",
        "report": str(report_path),
        "report_sha256": sha256_file(report_path),
        "aggregate_sha256": sha256_file(root / "aggregate.json"),
        "dataset_count": 3,
        "embedded_image_count": image_count,
        "expected_embedded_image_count": expected_images,
        "recommendation": aggregate.recommendation,
        "errors": errors,
    }


def review_basis_sha256(results: dict[str, dict[str, Any]], root: Path) -> str:
    evidence: dict[str, Any] = {"schema_version": "1.0", "datasets": {}}
    for dataset_id in PHASE1B_DATASET_IDS:
        result = results[dataset_id]
        if result.get("status") != "pass":
            evidence["datasets"][dataset_id] = result
            continue
        artifacts = []
        for frame in result["per_frame"]:
            for role in ("reconstruction", "heatmap"):
                path = root / dataset_id / frame["artifacts"][role]
                artifacts.append(
                    {
                        "frame": frame["index"],
                        "role": role,
                        "sha256": sha256_file(path),
                    }
                )
        evidence["datasets"][dataset_id] = {
            "manifest_sha256": result["manifest_sha256"],
            "config_sha256": result["config_sha256"],
            "source_before": result["source_before"],
            "package_sha256": result["photofold_package_sha256"],
            "artifacts": artifacts,
        }
    encoded = json.dumps(evidence, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()
