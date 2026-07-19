"""Self-contained human experiment report generation and validation."""

from __future__ import annotations

import base64
import html
import io
import json
import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

from photofold.gate1.bundle import verify_package
from photofold.gate1.images import sha256_file


def _format_bytes(value: int) -> str:
    return f"{value:,} bytes ({value / 1024:.1f} KiB)"


def _format_percent(value: float) -> str:
    return f"{value:.2f}%"


def _preview_data_uri(path: Path, max_width: int = 760) -> str:
    with Image.open(path) as image:
        preview = ImageOps.exif_transpose(image).convert("RGB")
        if preview.width > max_width:
            height = round(preview.height * max_width / preview.width)
            preview = preview.resize((max_width, height), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        preview.save(buffer, format="WEBP", quality=88, method=6)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/webp;base64,{encoded}"


def _status(value: bool) -> str:
    return '<span class="pass">PASS</span>' if value else '<span class="fail">FAIL</span>'


def generate_report(benchmark_path: str | Path, dataset_path: str | Path) -> dict[str, Any]:
    benchmark_file = Path(benchmark_path).resolve()
    output_directory = benchmark_file.parent
    result = json.loads(benchmark_file.read_text(encoding="utf-8"))
    package_path = output_directory / "moment.photofold"
    package_check = verify_package(package_path)
    if package_check["package_total_bytes"] != result["package_total_bytes"]:
        raise ValueError("benchmark.json package size does not match the final archive stat")
    if package_check["members"] != result["package_members"]:
        raise ValueError("benchmark.json package listing does not match the final archive")

    dataset = Path(dataset_path).resolve()
    frame_sections: list[str] = []
    for frame in result["per_frame"]:
        original_path = dataset / frame["filename"]
        reconstruction_path = output_directory / frame["artifacts"]["reconstruction"]
        heatmap_path = output_directory / frame["artifacts"]["heatmap"]
        quality_pass = frame["quality_threshold_pass"]
        frame_sections.append(
            f"""
            <article class="frame" data-frame="{frame['index']}">
              <div class="frame-heading">
                <div><p class="eyebrow">Frame {frame['index']:03d}</p><h3>{html.escape(frame['filename'])}</h3></div>
                <div class="frame-facts">
                  <span>{frame['width']} × {frame['height']}</span>
                  <span>Accepted: {_status(frame['accepted'])}</span>
                  <span>Reconstructed: {_status(frame['reconstructed'])}</span>
                  <span>SSIM {frame['ssim']:.6f} · {_status(quality_pass)}</span>
                </div>
              </div>
              <div class="comparison">
                <figure><img src="{_preview_data_uri(original_path)}" alt="Original {html.escape(frame['filename'])}"><figcaption>Original source preview</figcaption></figure>
                <figure><img src="{_preview_data_uri(reconstruction_path)}" alt="Reconstruction {html.escape(frame['filename'])}"><figcaption>Package-only reconstruction preview</figcaption></figure>
              </div>
              <figure class="heatmap"><img src="{_preview_data_uri(heatmap_path)}" alt="Difference heatmap {html.escape(frame['filename'])}"><figcaption>Absolute RGB difference heatmap · changed {frame['changed_region_percent']:.3f}% · shared {frame['shared_region_percent']:.3f}% · {frame['patch_count']} patches</figcaption></figure>
            </article>
            """
        )

    integrity_rows = "".join(
        f"<tr><td>{html.escape(check['label'])}</td><td>{_status(check['pass'])}</td><td>{html.escape(check['detail'])}</td></tr>"
        for check in result["integrity_checks"]
    )
    member_rows = "".join(
        f"<tr><td><code>{html.escape(member['path'])}</code></td><td>{member['bytes']:,}</td><td>{member['compressed_bytes']:,}</td><td><code>{member['sha256']}</code></td></tr>"
        for member in result["package_members"]
    )
    sweep_rows = "".join(
        f"<tr><td>{html.escape(trial['label'])}</td><td>{trial['parameters']['base_quality']}/{trial['parameters']['patch_quality']}</td><td>{trial['parameters']['pixel_threshold']}</td><td>{trial['parameters']['dilation_radius']}/{trial['parameters']['feather_radius']}</td><td>{trial['package_total_bytes']:,}</td><td>{trial['mean_ssim']:.6f}</td><td>{trial['minimum_ssim']:.6f}</td><td>{trial['patch_count']}</td><td>{_status(trial['relational_hypothesis_pass'])}</td></tr>"
        for trial in result["parameter_sweep"]
    )
    transform_rows = "".join(
        f"<tr><td>{item['frame_index']}</td><td>{html.escape(item['chosen'])}</td><td>{item['affine'].get('inlier_ratio', 0):.4f}</td><td>{item['affine'].get('median_reprojection_error', 0):.3f}px</td><td>{html.escape(str(item['homography'].get('median_reprojection_error', item['homography'].get('error', 'n/a'))))}</td><td>{html.escape(item['reason'])}</td></tr>"
        for item in result["alignment"]["model_comparison"]
    )
    failed_checks = "".join(f"<li>{html.escape(item)}</li>" for item in result["failed_checks"])
    failure_block = (
        f'<div class="failure-list"><strong>Failed checks</strong><ul>{failed_checks}</ul></div>'
        if result["failed_checks"]
        else '<p class="all-clear">All required Gate 1 checks passed.</p>'
    )
    overall_pass = result["gate_pass"]
    html_payload = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PhotoFold Gate 1 Compression Experiment</title>
<style>
:root{{--ink:#17211b;--muted:#5f6e64;--paper:#f4f1e9;--card:#fffdf8;--line:#d9d4c8;--green:#1d6b3d;--red:#a13225;--amber:#876310}}*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}main{{width:min(1320px,calc(100% - 32px));margin:40px auto 80px}}h1{{font-size:clamp(2.5rem,7vw,6.8rem);letter-spacing:-.065em;line-height:.9;margin:.25rem 0 1.25rem}}h2{{font-size:2rem;letter-spacing:-.035em;margin:0 0 1rem}}h3{{margin:0;font-size:1.3rem}}.eyebrow{{margin:0;color:var(--muted);font:700 11px/1.4 ui-monospace,SFMono-Regular,monospace;text-transform:uppercase;letter-spacing:.16em}}.hero,.card,.frame{{background:var(--card);border:1px solid var(--line);border-radius:24px;box-shadow:0 22px 70px rgba(23,33,27,.07)}}.hero{{padding:32px}}.verdict{{display:inline-block;border-radius:999px;padding:9px 14px;font:800 13px/1 ui-monospace,SFMono-Regular,monospace;background:{'#dff3e5' if overall_pass else '#fde7e2'};color:{'var(--green)' if overall_pass else 'var(--red)'}}}.lede{{max-width:850px;color:var(--muted);font-size:1.1rem}}.summary{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;margin-top:24px}}.metric{{padding:16px;border-radius:16px;background:#f0ede4}}.metric small{{display:block;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;font-size:10px}}.metric strong{{display:block;margin-top:6px;font-size:1.15rem}}.pass{{color:var(--green);font-weight:800}}.fail{{color:var(--red);font-weight:800}}.storage-status{{display:flex;flex-wrap:wrap;gap:12px;margin:18px 0 0}}.storage-status span{{padding:8px 12px;border-radius:12px;border:1px solid var(--line)}}.all-clear{{color:var(--green);font-weight:700}}.failure-list{{margin-top:16px;padding:16px;border-radius:14px;background:#fde7e2;color:var(--red)}}section{{margin-top:36px}}.frame{{padding:22px;margin-top:16px}}.frame-heading{{display:flex;align-items:end;justify-content:space-between;gap:16px;flex-wrap:wrap}}.frame-facts{{display:flex;flex-wrap:wrap;gap:8px;color:var(--muted);font-size:12px}}.frame-facts span{{padding:5px 8px;background:#f0ede4;border-radius:8px}}.comparison{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:18px}}figure{{margin:0}}img{{display:block;width:100%;height:auto;border-radius:14px;background:#111}}figcaption{{color:var(--muted);font-size:12px;margin-top:7px}}.heatmap{{margin-top:12px}}.heatmap img{{max-height:540px;object-fit:contain}}.card{{padding:24px;margin-top:16px;overflow:auto}}table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{padding:10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}th{{font-size:10px;text-transform:uppercase;letter-spacing:.09em;color:var(--muted)}}code{{font:11px/1.4 ui-monospace,SFMono-Regular,monospace;word-break:break-all}}.meta{{display:grid;grid-template-columns:auto 1fr;gap:7px 14px;margin:16px 0 0}}.meta dt{{color:var(--muted)}}.meta dd{{margin:0}}footer{{margin-top:36px;color:var(--muted);font-size:12px}}@media(max-width:760px){{.comparison{{grid-template-columns:1fr}}.hero{{padding:22px}}}}
</style>
</head>
<body><main>
<header class="hero">
<p class="eyebrow">Deterministic package-only evidence</p>
<h1>PhotoFold Gate 1 Compression Experiment</h1>
<span class="verdict">GATE 1: {'PASS' if overall_pass else 'FAIL'}</span>
<p class="lede">One real curated burst was encoded as a shared WebP base plus target-space patches, closed into a reconstructable archive, decoded using only that archive, and compared with exact sources and a matched-quality independent-WebP control.</p>
<div class="storage-status"><span>STORAGE REDUCTION: {_status(result['storage_reduction_pass'])}</span><span>QUALITY THRESHOLD: {_status(result['quality_threshold_pass'])}</span><span>RELATIONAL HYPOTHESIS: {_status(result['relational_hypothesis_pass'])}</span></div>
<div class="summary">
<div class="metric"><small>Original total</small><strong>{_format_bytes(result['original_total_bytes'])}</strong></div>
<div class="metric"><small>PhotoFold package</small><strong>{_format_bytes(result['package_total_bytes'])}</strong></div>
<div class="metric"><small>Signed byte delta</small><strong>{result['byte_delta']:+,} bytes</strong></div>
<div class="metric"><small>Storage saved</small><strong>{_format_bytes(result['bytes_saved'])} · {_format_percent(result['percent_saved'])}</strong></div>
<div class="metric"><small>Independent WebP control</small><strong>{_format_bytes(result['independent_webp_total_bytes'])} · q{result['independent_webp_quality']}</strong></div>
<div class="metric"><small>Relational gain</small><strong>{result['relational_gain_bytes']:+,} bytes · {_format_percent(result['relational_gain_percent'])}</strong></div>
<div class="metric"><small>Mean SSIM</small><strong>{result['mean_ssim']:.6f}</strong></div>
<div class="metric"><small>Minimum SSIM</small><strong>{result['minimum_ssim']:.6f}</strong></div>
</div>{failure_block}
<dl class="meta"><dt>Dataset</dt><dd>{html.escape(result['dataset_id'])} · {result['accepted_frame_count']} accepted/reconstructed frames</dd><dt>Run timestamp</dt><dd>{html.escape(result['run_at'])}</dd><dt>Config</dt><dd><code>{html.escape(result['config_path'])}</code> · SHA-256 <code>{result['config_sha256']}</code></dd><dt>Reference</dt><dd>Frame {result['reference_frame_index']:03d} · {html.escape(result['per_frame'][result['reference_frame_index']]['filename'])}</dd><dt>Package</dt><dd><code>moment.photofold</code> · SHA-256 <code>{result['package_sha256']}</code></dd></dl>
</header>
<section><p class="eyebrow">Visual evidence</p><h2>Every source and package-only reconstruction</h2><p>Report images are embedded, offline previews derived from the full-resolution artifacts. Inspect the generated PNG files for pixel-level zoom.</p>{''.join(frame_sections)}</section>
<section><p class="eyebrow">Integrity</p><h2>Acceptance checks</h2><div class="card"><table><thead><tr><th>Check</th><th>Verdict</th><th>Evidence</th></tr></thead><tbody>{integrity_rows}</tbody></table></div></section>
<section><p class="eyebrow">Measured selection</p><h2>Parameter sweep</h2><div class="card"><table><thead><tr><th>Trial</th><th>Base/Patch q</th><th>Diff threshold</th><th>Dilate/Feather</th><th>Package bytes</th><th>Mean SSIM</th><th>Min SSIM</th><th>Patches</th><th>Relational</th></tr></thead><tbody>{sweep_rows}</tbody></table></div></section>
<section><p class="eyebrow">Geometry</p><h2>Affine versus homography</h2><div class="card"><table><thead><tr><th>Frame</th><th>Chosen</th><th>Affine inliers</th><th>Affine error</th><th>Homography error/status</th><th>Decision</th></tr></thead><tbody>{transform_rows}</tbody></table></div></section>
<section><p class="eyebrow">Archive accounting</p><h2>Complete package file listing</h2><div class="card"><table><thead><tr><th>Path</th><th>Encoded bytes</th><th>ZIP bytes</th><th>SHA-256</th></tr></thead><tbody>{member_rows}</tbody></table></div></section>
<footer>Generated entirely from <code>benchmark.json</code>, the closed <code>moment.photofold</code> archive, and real image artifacts. No network, model, database, authentication, or source-code inspection is required.</footer>
</main></body></html>"""
    report_path = output_directory / "report.html"
    report_path.write_text(html_payload, encoding="utf-8")
    verification = verify_report(report_path, expected_frames=len(result["per_frame"]))
    return {
        "status": "pass",
        "path": str(report_path),
        "bytes": report_path.stat().st_size,
        "sha256": sha256_file(report_path),
        "verification": verification,
    }


def verify_report(report_path: str | Path, expected_frames: int | None = None) -> dict[str, Any]:
    path = Path(report_path).resolve()
    payload = path.read_text(encoding="utf-8")
    required = [
        "PhotoFold Gate 1 Compression Experiment",
        "GATE 1:",
        "STORAGE REDUCTION:",
        "RELATIONAL HYPOTHESIS:",
        "Complete package file listing",
        "Acceptance checks",
        "Parameter sweep",
    ]
    missing = [item for item in required if item not in payload]
    image_sources = re.findall(r'<img[^>]+src="([^"]+)"', payload)
    external_sources = [source for source in image_sources if not source.startswith("data:image/")]
    frame_count = payload.count('class="frame" data-frame=')
    checks = {
        "required_sections": not missing,
        "embedded_images_present": bool(image_sources),
        "no_external_image_sources": not external_sources,
        "expected_frame_sections": expected_frames is None or frame_count == expected_frames,
        "no_external_stylesheets": "<link" not in payload.lower(),
        "no_external_scripts": "<script" not in payload.lower(),
    }
    return {
        "status": "pass" if all(checks.values()) else "fail",
        "path": str(path),
        "bytes": path.stat().st_size,
        "checks": checks,
        "frame_sections": frame_count,
        "embedded_image_count": len(image_sources),
        "missing_sections": missing,
        "external_image_sources": external_sources,
    }
