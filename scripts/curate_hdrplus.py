"""Create the checked-in JPEG derivatives from one downloaded HDR+ burst.

This is a dataset-curation utility, not part of the PhotoFold runtime. Install the
documented pinned rawpy/Pillow versions in a temporary environment before use.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import rawpy
from PIL import Image


FRAME_COUNT = 7
OUTPUT_SIZE = (1600, 1200)


def curate(source: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for index in range(FRAME_COUNT):
        source_path = source / f"photofold-N{index:03d}.dng"
        output_path = output / f"frame-{index:03d}.jpg"
        with rawpy.imread(str(source_path)) as raw:
            rgb = raw.postprocess(
                use_camera_wb=True,
                no_auto_bright=False,
                output_bps=8,
            )
        image = Image.fromarray(rgb, mode="RGB")
        image = image.resize(OUTPUT_SIZE, Image.Resampling.LANCZOS)
        image.save(
            output_path,
            format="JPEG",
            quality=92,
            optimize=True,
            progressive=False,
            subsampling="4:2:0",
        )
        print(f"wrote {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="Directory containing photofold-N000.dng … N006")
    parser.add_argument("output", type=Path, help="Destination dataset directory")
    args = parser.parse_args()
    curate(args.source, args.output)


if __name__ == "__main__":
    main()

