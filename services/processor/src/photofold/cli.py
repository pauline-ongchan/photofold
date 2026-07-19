"""Phase 0 command-line entrypoints."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from photofold.dataset import DatasetValidationError, validate_dataset
from photofold.doctor import run_doctor


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="photofold",
        description="PhotoFold Phase 0 capability and contract tools",
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

    openapi = commands.add_parser(
        "export-openapi",
        help="Write the canonical FastAPI OpenAPI document",
    )
    openapi.add_argument("--output", required=True, help="Destination JSON file")
    openapi.set_defaults(handler=_export_openapi)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(args.handler(args))


if __name__ == "__main__":
    main()
