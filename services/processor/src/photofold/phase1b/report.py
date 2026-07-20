"""Self-contained Phase 1B report generation and structural verification."""

# ruff: noqa: E501

from __future__ import annotations

import base64
import hashlib
import html
import io
import json
import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError

from photofold.gate1.bundle import PackageValidationError, verify_package
from photofold.gate1.images import sha256_file
from photofold.phase1b.aggregate import build_aggregate
from photofold.phase1b.datasets import PHASE1B_DATASET_IDS
from photofold.phase1b.models import (
    HumanReview,
    Phase1BAggregateResult,
    Phase1BDatasetResult,
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


def _dataset_section(
    root: Path,
    dataset_id: str,
    result: dict[str, Any],
) -> str:
    if result.get("status") != "pass":
        failure = html.escape(json.dumps(result, indent=2, sort_keys=True))
        return (
            f'<section id="dataset-{dataset_id}" data-dataset-id="{dataset_id}" '
            'data-status="fail" data-frame-count="0" data-member-count="0">'
            f"<h2>{html.escape(dataset_id)}</h2>"
            f"{_status_badge(False, 'DATASET FAILED')}<pre>{failure}</pre></section>"
        )

    dataset = Phase1BDatasetResult.model_validate(result)
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
            f'SSIM {frame["ssim"]:.9f}; PSNR {_psnr(frame["psnr_db"])} dB; '
            f'fixed {frame["fixed_webp"]["bytes"]:,} B; '
            + (
                f'matched {matched_frame["bytes"]:,} B'
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
    timing_rows = [[key, value] for key, value in dataset.timings.items()]
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
    environment_rows = [[key, value] for key, value in dataset.environment.items()]
    return f"""
<section id="dataset-{dataset_id}" data-dataset-id="{dataset_id}" data-status="pass"
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
  <details><summary>Complete independent-WebP q1–q100 curve</summary>
  {_table(['q', 'Bytes', 'Mean SSIM', 'Min SSIM', 'Mean PSNR', 'Min PSNR', 'Qualifies'], curve_rows)}
  </details>
  <h3>Package overhead</h3>
  {_table(['Field', 'Value'], [[key, value] for key, value in dataset.package_overhead.items()])}
  <details><summary>Complete package listing ({len(member_rows)} members)</summary>
  {_table(['Path', 'Role', 'Stored bytes', 'Payload bytes', 'SHA-256'], member_rows)}
  </details>
</section>
"""


def generate_phase1b_report(
    artifact_root: str | Path,
    results: dict[str, dict[str, Any]],
    aggregate: Phase1BAggregateResult,
) -> dict[str, Any]:
    root = Path(artifact_root).expanduser().resolve()
    report_path = root / "report.html"
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
        _dataset_section(root, dataset_id, results[dataset_id])
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

    expected_images = 0
    expected_frames = 0
    for dataset_id in PHASE1B_DATASET_IDS:
        result = results[dataset_id]
        section_marker = f'id="dataset-{dataset_id}"'
        if section_marker not in document:
            errors.append(f"missing dataset section: {dataset_id}")
        if result.get("status") != "pass":
            continue
        try:
            dataset = Phase1BDatasetResult.model_validate(result)
            verification = verify_package(root / dataset_id / "moment.photofold")
        except (ValueError, PackageValidationError) as error:
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
    if re.search(r"\b(?:TODO|TBD|PLACEHOLDER)\b", document, flags=re.IGNORECASE):
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
