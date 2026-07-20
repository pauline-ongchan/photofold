# Phase 1B real burst inputs

These three directories are the only canonical Phase 1B dataset locations:

```text
data/real-bursts/
├── static-handheld/
├── moving-subject/
└── camera-motion-or-lighting/
```

The original photos are owner-authorized local experiment inputs. They retain
private EXIF/GPS metadata and are intentionally ignored by Git. The checked-in
`manifest.json` files are authoritative for filenames, ordering, dimensions,
and SHA-256 checksums.

Prepare the canonical directories from the supplied staging copy without
rewriting either source or destination bytes:

```bash
.venv/bin/python scripts/prepare_phase1b_datasets.py \
  --source "data/phase 1/real-bursts" \
  --destination data/real-bursts
```

The preparation command refuses to overwrite a differing destination and does
not make the benchmark search the staging path. After preparation, validate the
canonical collection with:

```bash
.venv/bin/python -m photofold.cli validate-phase1b-datasets \
  data/real-bursts \
  --output artifacts/phase1b/dataset-validation.json
```

Two supplied staging frames are deliberately not part of the canonical sets:

- `moving-subject/IMG_8418.jpg` normalizes to 4284×5712 while the canonical
  sequence is 3024×4032.
- `camera-motion-or-lighting/IMG_8480.jpg` normalizes to 3024×4032 while the
  canonical sequence is 4284×5712.

They remain unchanged in the local staging directory and are not silently
resized, transcoded, renamed, or processed.
