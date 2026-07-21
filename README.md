# PhotoFold

**Keep every shot. Store the shared scene once.**

PhotoFold is a local-first prototype that compresses a burst of similar photos into one reconstructable `.photofold` collection. It preserves every frame instead of choosing a “best shot” or deleting duplicates.

## What it does

1. Accepts 5–20 JPEG, PNG, or WebP photos from the same moment.
2. Selects a reference frame and aligns compatible photos with ORB features and RANSAC.
3. Stores one shared WebP scene plus frame-specific patches and lossless masks.
4. Keeps low-confidence frames whole rather than forcing an unsafe fold.
5. Reconstructs every photo from the closed archive and reports real archive size and per-frame visual similarity.

The web demo supports the complete local workflow: upload, analyze, fold, compare, export an individual photo, and download the `.photofold` archive. It does not require an account, database, cloud service, model credential, or network connection at runtime.

## Run the demo

### Requirements

- Python 3.12
- Node.js 20.9 or newer
- npm 10 or newer
- macOS or another Unix-like environment

### Install

From the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install \
  --constraint services/processor/requirements.lock \
  -e 'services/processor[dev]'
npm ci
```

### Start

```bash
make human-verify-gate3 DATASET=data/demo/hdrplus-static
```

Wait for the local services to start, then open <http://127.0.0.1:3000>. Upload the seven images from `data/demo/hdrplus-static/` and follow the four on-screen steps. Stop the demo with `Ctrl-C`.

## Sample data

`data/demo/hdrplus-static/` contains seven checksum-verified 1600×1200 JPEG frames derived from one Google HDR+ mobile-camera burst. The images are licensed CC BY-SA 4.0; provenance, attribution, source URLs, conversion settings, and checksums are documented in [`data/demo/README.md`](data/demo/README.md).

Three additional real bursts covering handheld capture, moving subjects, and camera motion or lighting changes are available under `data/real-bursts/`. Their manifests pin frame order, checksums, formats, dimensions, provenance, and preparation metadata.

## How Codex and GPT-5.6 were used

Codex with GPT-5.6 accelerated the Build Week engineering workflow by helping to:

- turn the product requirements into explicit implementation gates;
- implement and review the Python and TypeScript code;
- generate and synchronize OpenAPI-derived contracts;
- design package invariants and failure handling;
- write unit, integration, and browser tests;
- analyze measured compression and quality evidence; and
- iterate on the plain-language product experience.

The key decisions were evidence-driven: keep the codec deterministic and offline, measure the final closed archive instead of estimating it, compare against quality-matched independent WebP, preserve low-confidence frames independently, and display failed quality checks honestly.

GPT-5.6 was used through Codex during development. It is not a hidden runtime dependency: the submitted compression workflow remains fully functional without an API key or network connection.
