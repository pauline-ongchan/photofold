# PhotoFold

PhotoFold is a hackathon prototype exploring whether groups of similar photos can be stored as one shared scene plus frame-specific differences while retaining every frame.

## Current status: Phase 4P.1 generalized folding implemented; UI review passed, owner acceptance pending

This repository implements the Gate 0 foundation, the CLI-only Gate 1 compression proof, the accepted Phase 1B multi-dataset validation experiment, and the automated Gate 3P local prototype:

- a FastAPI `/v1/health` endpoint;
- a CLI codec doctor and real-dataset validator;
- a local Next.js upload → analyze → fold → inspect → export → archive workflow;
- generated OpenAPI and TypeScript contracts;
- pinned local dependencies and validation commands; and
- four documented, checksum-verified real bursts: the original Gate 1 set and three canonical Phase 1B scenarios;
- deterministic reference selection and ORB/RANSAC alignment;
- resolution-independent alignment error measured on the fixed analysis canvas;
- deterministic best shared-group selection plus per-frame independent-source fallback;
- a WebP base plus cropped target-space WebP patches and lossless PNG masks for shared frames;
- exact uploaded JPEG/PNG/WebP payloads for independent frames, decoded and EXIF-normalized from the closed package;
- a strict `.photofold` package validator and package-only decoder;
- real archive-byte, RGB SSIM, difference-heatmap, and independent-WebP measurements; and
- fixed-quality and exact quality-matched independent-WebP controls with per-frame RGB SSIM and PSNR;
- deterministic all-dataset aggregation and recommendation rules; and
- self-contained offline HTML experiment reports with artifact-bound human review records;
- strict generated Pydantic/JSON Schema/TypeScript contracts for the private prototype bridge and version 0.2 manifest; and
- run-scoped uploads, fixed shell-free CLI arguments, one active fold, package-only reconstruction artifacts, and focused browser tests.

The Phase 1B automated experiment passes for all three canonical datasets, and the project owner accepts the current reconstruction quality for the hackathon MVP. The final recommendation is `CONTINUE COMPRESSION-FIRST`. Phase 4P now supplies the local product flow without adding a reusable processing service. Runtime and implementation complexity remain documented MVP limitations: the current trade-off can be disproportionate for some datasets, and runtime, encoding efficiency, package overhead, and dataset selection require future optimization.

For the controlled hackathon prototype, Phase 2 / Gate 2A pipeline hardening and Phase 3 / Gate 2B FastAPI processing routes remain explicitly deferred rather than completed. Phase 4P.1 keeps every successfully validated set foldable by selecting `shared_scene`, `hybrid`, or `independent_only` without relaxing measured alignment requirements. The implementation-agent UI visual review passed on the native `static-handheld` workflow; project-owner functional acceptance remains pending because the measured run ends honestly as `failed_quality`. The production-oriented failure matrix, reusable API contract, persistence, concurrency, restart recovery, and TTL lifecycle remain documented future work.

## Prerequisites

- Node.js 20.9 or newer. Gate 0 was verified with Node.js 24.13.0 and npm 11.6.2.
- Python 3.12. Gate 0 was verified with Python 3.12.11.
- macOS or a Unix-like shell for the provided `Makefile` and human-verification runner.

## Install

From the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --constraint services/processor/requirements.lock -e 'services/processor[dev]'
npm ci
```

The project does not need a database, container, cloud account, or model credential.

## Validate Gate 0

Run the individual contract checks:

```bash
.venv/bin/python -m photofold.cli doctor
.venv/bin/python -m photofold.cli validate-dataset data/demo/hdrplus-static
npm run contracts:check
npm run lint --workspaces --if-present
npm run typecheck --workspaces --if-present
npm run build --workspace apps/web
```

Run the complete repeatable gate:

```bash
make verify-gate0
```

It writes human-readable evidence to:

- `artifacts/gate0/doctor.json`
- `artifacts/gate0/dataset-validation.json`
- `packages/contracts/openapi.json`

## Human verification

Run:

```bash
make human-verify-gate0
```

Wait for `Gate 0 services ready`, then open:

- <http://127.0.0.1:3000>
- <http://127.0.0.1:8000/docs>

The original health-only frontend has been superseded by the Gate 3P product page. Pass the retained Gate 0 checkpoint when the product page loads, `curl http://127.0.0.1:8000/v1/health` reports the WebP-capable processor and validated dataset, the API docs show only `/v1/health`, and the command printed `GATE 0: PASS`. Stop both services with `Ctrl-C`.

Fail if a URL does not load, WebP is unavailable, fewer than five compatible dataset frames validate, a generated contract is stale, any automated check fails, or an external service/credential is requested.

## Validate Gate 1

Run the complete real experiment and its package/report checks:

```bash
make verify-gate1 DATASET=data/demo/hdrplus-static
```

The selected run processes all seven real frames, reconstructs every frame from the package alone, measures the closed archive, evaluates per-frame RGB SSIM, and compares PhotoFold with a matched-quality independent-WebP curve. It does not use the network or model credentials.

The authoritative Gate 1 run measured 4,408,395 source bytes, a 677,744-byte `.photofold` archive, and 725,126 bytes for the smallest equal-or-better independent-WebP point (quality 31). PhotoFold saved 3,730,651 bytes versus the sources and 47,382 bytes versus the matched control. Mean SSIM was 0.851131 and minimum per-frame SSIM was 0.826471. These values are generated by the experiment and reproduced in the report; the application does not hard-code them.

### Gate 1 human verification

1. Run `make human-verify-gate1 DATASET=data/demo/hdrplus-static`.
2. Open the exact file `artifacts/gate1/hdrplus-static/report.html`:

   ```bash
   open artifacts/gate1/hdrplus-static/report.html
   ```

3. Expect a page headed `PhotoFold Gate 1 Compression Experiment` with `GATE 1: PASS`, `STORAGE REDUCTION: PASS`, `QUALITY THRESHOLD: PASS`, and `RELATIONAL HYPOTHESIS: PASS`. It must show the exact source/package/control bytes, mean/minimum SSIM, seven original/reconstruction/heatmap rows, the parameter sweep, integrity checks, and the complete package listing.
4. Pass only when every frame is accepted and reconstructed at 1600×1200, every per-frame SSIM passes, images and heatmaps render without broken links, the package is smaller than both sources and the matched control, and every integrity row passes.
5. Inspect `benchmark.json`, `moment.photofold`, `package-inventory.json`, `package-verification.json`, `report-verification.json`, `sweep.json`, `reconstructions/`, `heatmaps/`, `masks/`, `alignment-overlays/`, and `exported-000.webp` under `artifacts/gate1/hdrplus-static/`. The explicit export command also writes `artifacts/gate1/exported-000.webp`.
6. Fail the gate for any overall `FAIL`, broken image, missing frame, dimension/checksum/manifest/stat mismatch, below-threshold SSIM, package-size mismatch, non-matched control, or source-code inspection requirement.

## Validate Phase 1B

Run the fast deterministic checks during development:

```bash
make verify-phase1b-fast
```

Run the authoritative native-resolution experiment only for release/checkpoint evidence. It validates and processes all 42 frames, exhaustively searches WebP qualities 1 through 100 for every frame, verifies every closed package through the public decoder, and regenerates the self-contained report:

```bash
make verify-phase1b
```

The current authoritative automated run produced:

| Dataset | Frames | Original | PhotoFold | Saved vs original | Matched-WebP result | Processing time |
|---|---:|---:|---:|---:|---:|---:|
| `static-handheld` | 15 | 46,659,071 bytes | 8,722,761 bytes | 81.3053% | 10.6301% win | 3,913,459.509 ms |
| `moving-subject` | 13 | 25,331,644 bytes | 12,376,638 bytes | 51.1416% | 4.5292% loss | 3,387,811.496 ms |
| `camera-motion-or-lighting` | 14 | 26,301,637 bytes | 5,198,284 bytes | 80.2359% | 31.3488% win | 6,192,228.432 ms |

Across the three datasets, PhotoFold reduced 98,292,352 original bytes to 26,297,683 bytes, saving 71,994,669 bytes or 73.2454%. The exact matched-quality controls used 29,172,680 bytes; median relational savings were 10.6301%, the weighted mean was 9.8551%, and the win/loss/tie count was 2/1/0. The summed per-dataset wall-clock observations were 13,493,499.437 ms (3.748 hours), of which 12,588,648.657 ms were spent in exhaustive q1–q100 WebP sweeps. These values are generated from real artifacts and are not hard-coded into the application.

The self-contained [Phase 1B report](artifacts/phase1b/report.html) records the completed project-owner visual review, measured runtime and storage, known computational bottlenecks, and final `CONTINUE COMPRESSION-FIRST` decision. Its detailed automated body preserves the previously verified pre-review snapshot, in which the generated aggregate correctly remained provisional until human review. The project owner directed that a final multi-hour recompression rerun be skipped; the completed native measurements above remain the authoritative experiment evidence.

To reproduce and bind a fresh review after a future full run:

1. Open `artifacts/phase1b/report.html` with networking disabled and inspect every dataset, especially the preselected lowest-SSIM and lowest-PSNR frames.
2. Copy `artifacts/phase1b/human-review-template.json` to `artifacts/phase1b/human-review.json`, record the reviewer, timestamp, per-dataset pass/fail decisions, notes, and complexity observations without changing the embedded evidence basis.
3. Finalize the bound review:

   ```bash
   .venv/bin/python -m photofold.cli finalize-phase1b-review \
     --artifacts artifacts/phase1b \
     --review artifacts/phase1b/human-review.json
   ```

The finalizer rejects stale or edited evidence by checking the recorded artifact hashes before applying the ordered Phase 1B decision rules. The dominant current bottleneck is the sequential native-resolution q1–q100 control sweep; alignment, warping, change analysis, patch encoding, archive verification, and package-only reconstruction add further work. The current implementation may be disproportionate to the storage benefit for some datasets, especially the measured moving-subject relational loss. See `docs/PHASE_1B_SPEC.md` and `docs/PHASE_1B_EXECUTION_PLAN.md` for the experiment contract and execution checkpoints.

## Validate Gate 3P

Install the locked Chromium runtime once, then run the repeatable local-prototype gate:

```bash
npm exec --workspace apps/web playwright install chromium
make verify-gate3
```

The command checks the processor, generated contracts, bridge and UI tests, production build, and two real Chromium workflows: the normal seven-frame shared burst and the native-resolution fallback burst. It does not rerun the multi-hour q1–q100 research sweeps.

The Phase 4P.1 selected-treatment re-evaluation measured:

| Dataset | Strategy | Shared / fallback | Alignment error range | Package / originals | Mean / minimum SSIM | Terminal status |
|---|---|---:|---:|---:|---:|---|
| `static-handheld` | `hybrid` | 13 / 2 | 0.692620–1.027088 analysis px | 13,663,060 / 46,659,071 bytes | 0.783225 / 0.715211 | `failed_quality` |
| `moving-subject` | `hybrid` | 10 / 3 | 0.862348–1.407737 analysis px | 15,901,130 / 25,331,644 bytes | 0.887196 / 0.824598 | `complete` |
| `camera-motion-or-lighting` | `hybrid` | 10 / 4 | 0.638211–0.922210 analysis px | 11,001,509 / 26,301,637 bytes | 0.850882 / 0.675281 | `failed_quality` |

Every listed archive passed closed-package validation and reconstructed every frame. Independent members scored exactly 1.0 SSIM against their normalized source pixels. The two `failed_quality` outcomes are intentionally retained because the current 0.85 mean/0.82 per-frame thresholds were selected for `hdrplus-static`, not generalized or bypassed for these native datasets. Storage is still reported from real closed archives, and no positive savings claim is made for a non-`complete` terminal result.

Expected evidence under `artifacts/gate3/latest/` is:

- `result.json` and the exact `moment.photofold` it measures;
- `exported-frame.webp` from the package-only decoder;
- `ui-e2e-report/index.html`; and
- `gate1-report.html`, copied from the accepted offline Gate 1 evidence when present.

For the project-owner walkthrough:

```bash
make human-verify-gate3 DATASET=data/real-bursts/static-handheld
```

Open <http://127.0.0.1:3000>, upload the dataset files, and complete upload → analyze → fold → inspect → **Export selected photo** → **Download PhotoFold archive**. `static-handheld` must show `13` shared and `2` fallback frames with their measured low-inlier reasons, then reconstruct all 15 frames and retain its honest `failed_quality` result. Because that native run does not pass the currently recorded quality gate, functional project-owner acceptance must remain pending unless a later measured and reviewed quality decision changes the outcome. Run `make clean-gate3` to remove all local Gate 3P runs and published evidence.

## Manual development servers

Processor:

```bash
.venv/bin/uvicorn photofold.main:app --host 127.0.0.1 --port 8000 --reload
```

Frontend, in a second terminal:

```bash
npm run dev --workspace apps/web
```

The frontend invokes the deterministic CLI directly through its private localhost-only bridge. The FastAPI process is not required for Gate 3P.

## Curated dataset

`data/demo/hdrplus-static` contains seven 1600×1200 JPEG derivatives from one real Google HDR+ mobile-camera burst. The originals were captured within one burst and are licensed CC BY-SA. Exact provenance, attribution, source object URLs, conversion settings, derivative checksums, and limitations are in `data/demo/README.md` and the dataset's `manifest.json`.

This static natural scene is appropriate for validating repository plumbing and later low-motion experiments. It does not cover the expression, pose, or unique-entry scenarios required by Gate 2.

`data/real-bursts/` contains the three canonical Phase 1B scenarios: `static-handheld`, `moving-subject`, and `camera-motion-or-lighting`. Their versioned manifests pin ordered source files, SHA-256 checksums, formats, dimensions, frame counts, provenance, and preparation metadata. The validator fails on any mismatch; it does not silently skip or normalize unexpected inputs during the benchmark.

## Technical contracts

Gate 0 froze the measurement, transform, package, error, and independent-WebP benchmark contracts in [docs/TECHNICAL_CONTRACTS.md](docs/TECHNICAL_CONTRACTS.md). Gate 1 selected dataset-specific thresholds from the real sweep and records them in `configs/gate1.yaml` and every run result.
