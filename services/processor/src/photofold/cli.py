"""Deterministic PhotoFold command-line entrypoints."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from photofold.dataset import DatasetValidationError, validate_dataset
from photofold.doctor import run_doctor
from photofold.gate1.benchmark import run_benchmark
from photofold.gate1.bundle import (
    PackageValidationError,
    export_package_frame,
    verify_package,
)
from photofold.gate1.report import verify_report
from photofold.phase1b.datasets import validate_phase1b_collection


def _write_json(payload: dict[str, Any], output: str | None) -> None:
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    print(serialized, end="")
    if output is not None:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(serialized, encoding="utf-8")


def _doctor(args: argparse.Namespace) -> int:
    result = run_doctor()
    _write_json(result, args.output)
    return 0 if result["status"] == "pass" else 1


def _validate_dataset(args: argparse.Namespace) -> int:
    try:
        result = validate_dataset(args.dataset)
    except DatasetValidationError as error:
        result = {
            "status": "fail",
            "dataset": str(Path(args.dataset).resolve()),
            "error": str(error),
        }
        _write_json(result, args.output)
        return 1
    _write_json(result, args.output)
    return 0


def _validate_phase1b_datasets(args: argparse.Namespace) -> int:
    result = validate_phase1b_collection(args.root)
    _write_json(result, args.output)
    return 0 if result["status"] == "pass" else 1


def _export_openapi(args: argparse.Namespace) -> int:
    from photofold.main import app

    schema = app.openapi()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(schema, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {output_path}")
    return 0


def _benchmark(args: argparse.Namespace) -> int:
    result = run_benchmark(
        dataset_path=args.dataset,
        config_path=args.config,
        output_path=args.output,
    )
    summary = {
        "status": "pass" if result["gate_pass"] else "fail",
        "gate_pass": result["gate_pass"],
        "dataset_id": result["dataset_id"],
        "accepted_frame_count": result["accepted_frame_count"],
        "reconstructed_frame_count": result["reconstructed_frame_count"],
        "original_total_bytes": result["original_total_bytes"],
        "package_total_bytes": result["package_total_bytes"],
        "independent_webp_total_bytes": result["independent_webp_total_bytes"],
        "percent_saved": result["percent_saved"],
        "mean_ssim": result["mean_ssim"],
        "minimum_ssim": result["minimum_ssim"],
        "storage_reduction_pass": result["storage_reduction_pass"],
        "relational_hypothesis_pass": result["relational_hypothesis_pass"],
        "failed_checks": result["failed_checks"],
        "report": result["report"],
    }
    _write_json(summary, None)
    return 0 if result["gate_pass"] else 1


def _verify_package(args: argparse.Namespace) -> int:
    try:
        result = verify_package(args.package)
    except PackageValidationError as error:
        result = {
            "status": "fail",
            "package": str(Path(args.package).resolve()),
            "error": str(error),
        }
    _write_json(result, args.output)
    return 0 if result["status"] == "pass" else 1


def _export_frame(args: argparse.Namespace) -> int:
    try:
        result = export_package_frame(
            package_path=args.package,
            frame_index=args.frame,
            output_path=args.output,
            image_format=args.format,
        )
    except (PackageValidationError, ValueError) as error:
        result = {
            "status": "fail",
            "package": str(Path(args.package).resolve()),
            "error": str(error),
        }
    _write_json(result, None)
    return 0 if result["status"] == "pass" else 1


def _verify_report(args: argparse.Namespace) -> int:
    result = verify_report(args.report, expected_frames=args.expected_frames)
    _write_json(result, args.output)
    return 0 if result["status"] == "pass" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="photofold",
        description="PhotoFold deterministic capability, package, and experiment tools",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    doctor = commands.add_parser("doctor", help="Check deterministic runtime and WebP support")
    doctor.add_argument("--output", help="Also write the JSON result to this file")
    doctor.set_defaults(handler=_doctor)

    dataset = commands.add_parser(
        "validate-dataset",
        help="Verify a curated dataset manifest, checksums, formats, and dimensions",
    )
    dataset.add_argument("dataset", help="Path to the curated dataset directory")
    dataset.add_argument("--output", help="Also write the JSON result to this file")
    dataset.set_defaults(handler=_validate_dataset)

    phase1b_datasets = commands.add_parser(
        "validate-phase1b-datasets",
        help="Verify the complete canonical Phase 1B dataset collection",
    )
    phase1b_datasets.add_argument("root", help="Canonical Phase 1B dataset root")
    phase1b_datasets.add_argument("--output", help="Also write the JSON result to this file")
    phase1b_datasets.set_defaults(handler=_validate_phase1b_datasets)

    openapi = commands.add_parser(
        "export-openapi",
        help="Write the canonical FastAPI OpenAPI document",
    )
    openapi.add_argument("--output", required=True, help="Destination JSON file")
    openapi.set_defaults(handler=_export_openapi)

    benchmark = commands.add_parser(
        "benchmark",
        help="Run the real Gate 1 compression experiment and generate its report",
    )
    benchmark.add_argument("--dataset", required=True, help="Curated dataset directory")
    benchmark.add_argument("--config", required=True, help="Gate 1 YAML configuration")
    benchmark.add_argument("--output", required=True, help="Experiment artifact directory")
    benchmark.set_defaults(handler=_benchmark)

    package = commands.add_parser(
        "verify-package",
        help="Validate and reconstruct every frame using only a .photofold package",
    )
    package.add_argument("package", help="Path to the .photofold archive")
    package.add_argument("--output", help="Also write the JSON result to this file")
    package.set_defaults(handler=_verify_package)

    export = commands.add_parser(
        "export",
        help="Decode one package frame and export a standard image",
    )
    export.add_argument("package", help="Path to the .photofold archive")
    export.add_argument("--frame", required=True, type=int, help="Zero-based frame index")
    export.add_argument("--format", required=True, choices=["webp", "jpeg", "png"])
    export.add_argument("--output", required=True, help="Export destination")
    export.set_defaults(handler=_export_frame)

    report = commands.add_parser(
        "verify-report",
        help="Check that a Gate 1 report is self-contained and complete",
    )
    report.add_argument("report", help="Path to report.html")
    report.add_argument("--expected-frames", type=int, default=7)
    report.add_argument("--output", help="Also write the JSON result to this file")
    report.set_defaults(handler=_verify_report)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(args.handler(args))


if __name__ == "__main__":
    main()
