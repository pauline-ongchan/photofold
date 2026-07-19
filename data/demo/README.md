# PhotoFold demo datasets

## `hdrplus-static`

This Gate 0 fixture contains seven JPEG derivatives from one real Google HDR+ mobile-camera burst:

- Burst ID: `0006_20160722_115157_431`
- Source dataset: [HDR+ Burst Photography Dataset](https://www.hdrplusdata.org/dataset.html)
- Authors: Samuel W. Hasinoff, Dillon Sharlet, Ryan Geiss, Andrew Adams, Jonathan T. Barron, Florian Kainz, Jiawen Chen, and Marc Levoy
- License: [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)
- Subject: static tree and mountain scene; no identifiable person is visible

The source dataset states that frames in a burst are captured as a rapid mobile-camera sequence, normally with no more than 33 ms between successive frames. This burst has seven DNG inputs with identical 4048×3036 dimensions.

### Changes made

The checked-in files are derivatives, also distributed under CC BY-SA 4.0:

1. Developed each source DNG with `rawpy==0.27.0`, camera white balance, automatic brightness, and 8-bit RGB output.
2. Resized to 1600×1200 with Pillow 12.3.0 Lanczos resampling.
3. Encoded JPEG at quality 92, optimized, non-progressive, with 4:2:0 subsampling.
4. Renamed frames in source order to `frame-000.jpg` through `frame-006.jpg`.

The exact derivative and source checksums are in `hdrplus-static/manifest.json`. This attribution file and manifest must remain with redistributed copies.

### Reproduce the derivatives

Download `payload_N000.dng` through `payload_N006.dng` from the source URLs in the manifest as `/tmp/photofold-N000.dng` through `/tmp/photofold-N006.dng`. Then run:

```bash
python3 -m venv /tmp/photofold-rawpy-venv
/tmp/photofold-rawpy-venv/bin/python -m pip install rawpy==0.27.0 pillow==12.3.0
/tmp/photofold-rawpy-venv/bin/python scripts/curate_hdrplus.py \
  /tmp data/demo/hdrplus-static
```

Verify with:

```bash
.venv/bin/python -m photofold.cli validate-dataset data/demo/hdrplus-static
```

### Limitations

- This is a static natural scene with only small handheld/capture changes. It is suitable for Phase 0 validation and a later low-motion compression spike.
- It does not satisfy Gate 2's expression-change, pose-change, or unique-entry scenario coverage.
- The checked-in JPEG bytes are derivatives, so Gate 1's user-facing source-byte comparison will use these exact derivative bytes. It must still compare against the independent-WebP control before claiming relational savings.
- The DNG originals are not checked into this repository.

