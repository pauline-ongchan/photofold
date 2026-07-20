"""Copy manifest-listed Phase 1B source bytes into the canonical directories."""

from __future__ import annotations

import argparse
import json

from photofold.phase1b.datasets import prepare_phase1b_datasets


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="Supplied staging dataset root")
    parser.add_argument("--destination", required=True, help="Canonical dataset root")
    args = parser.parse_args()
    result = prepare_phase1b_datasets(args.source, args.destination)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
