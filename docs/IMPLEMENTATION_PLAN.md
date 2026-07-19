# PhotoFold Implementation Plan

**Status:** Phase 0 and the CLI-only Phase 1 are implemented and verified; Phase 2 and later remain proposed and unimplemented
**Source of truth:** `docs/PhotoFold_Developer_PRD.md`
**Demo context only:** `docs/PhotoFold_Demo_Script.md`
**Planning date:** 2026-07-18
**Last Gate 0 verification:** 2026-07-18
**Last Gate 1 experiment:** 2026-07-18
**Last Gate 1 verification:** 2026-07-18

## 1. Purpose and operating principles

This plan is deliberately compression-first. The team should not build the complete web experience until a real, deterministic, package-only reconstruction experiment demonstrates that PhotoFold can save bytes at an acceptable measured quality.

The implementation should follow these rules:

1. Gate 1 uses a real curated photo set with at least five accepted frames.
2. Every accepted frame is reconstructed from the `.photofold` artifact alone.
3. Every storage number comes from file-system byte counts of real artifacts.
4. Every quality number is calculated from decoded originals and decoded reconstructions.
5. WebP is the initial image codec. AVIF is considered only after a measured experiment shows a material advantage without harming demo reliability.
6. The deterministic pipeline must operate with no model credentials or network access.
7. GPT-5.6 is an optional, bounded P1 enhancement after the deterministic pipeline passes.
8. There is no authentication, billing, database, queue service, cloud storage, or production deployment work in the MVP.
9. Unsupported sets should fail honestly. A narrow reliable success envelope is preferable to misleading universal support.

## 2. Initial repository inspection

Before Gate 0 implementation, the repository contained no commits and no application or tooling files. It contained only:

```text
docs/
├── PhotoFold_Developer_PRD.md
└── PhotoFold_Demo_Script.md
```

There was no `AGENTS.md`, `README.md`, dependency manifest, dataset, test suite, CI configuration, frontend, or processor. The filenames also differed from the shorter names used in the task and from the structure proposed by the PRD. Gate 0 kept the existing source-document names and now references them consistently rather than creating duplicate copies.

The repository now contains the implemented Gate 0 foundation and the CLI-only Gate 1 compression experiment described in their completion records below. Gate 1 adds the deterministic package writer/decoder, reconstruction, real metrics, tests, and offline report. It does not add the upload/product workflow, processing API, job system, extra datasets, or GPT integration reserved for later phases.

## 3. Recommended architecture at a glance

```text
Browser / Next.js
  ├── uploads images with multipart HTTP
  ├── polls typed JSON job state
  └── loads original, reconstruction, difference, and download artifacts by URL
                    │
                    │ HTTP on localhost; no shared runtime imports
                    ▼
Single-process FastAPI service
  ├── Pydantic API contracts and structured errors
  ├── one in-process fold job at a time
  ├── temporary per-moment workspace on local disk
  └── deterministic PhotoFold pipeline
        ├── normalize and validate
        ├── select reference and align
        ├── encode WebP base plus target-space patches
        ├── create and validate `.photofold` ZIP
        ├── reconstruct every accepted frame from that ZIP
        └── calculate real size, SSIM, and difference artifacts
                    │
                    ▼
Optional GPT-5.6 adapter (P1 only)
  └── reduced-resolution contact sheet; schema-validated advice; safe no-op fallback
```

The browser should call FastAPI directly via `NEXT_PUBLIC_PROCESSOR_URL`. A Next.js proxy or server action would duplicate large uploads and add timeout and memory failure modes without helping the local hackathon prototype. FastAPI should allow only the configured local frontend origin through CORS.

The processor should run as one Uvicorn process. An in-process executor with a concurrency limit of one is sufficient for fold jobs. It can return `202 Accepted` and persist job state to a JSON file that the frontend polls. Do not add Celery, Redis, or another queue.

## 4. Technical-assumption review and decisions

| Area | Finding | Decision for the MVP |
|---|---|---|
| Compression claim | Comparing the package only with uploaded JPEG/PNG/WebP bytes can make ordinary WebP transcoding look like relational compression. This does not isolate the core hypothesis. | Keep the PRD's original-byte metric for the product, and add an engineering control: independently encode every frame at every integer WebP quality from 1 through 100. Gate 1 reports both. Claim relational savings only when the PhotoFold package is smaller than the smallest independent-WebP point with equal-or-better mean and minimum SSIM. |
| Package size | The PRD does not say whether size means a directory sum or the downloadable archive. ZIP headers and included metadata are real bytes. | `package_total_bytes` is `stat()` of the final `.photofold` ZIP. Use `ZIP_STORED` initially because image assets are already compressed. Also retain a member-size inventory for debugging. |
| Metrics inside the package | If an internal `metrics.json` contains the final archive size, writing that value changes the archive and creates a circular measurement. | Internal metrics contain quality, source totals, configuration, and member inventory, but not the final archive byte count. The service/benchmark stats the completed archive and records `package_total_bytes` in the external run result returned to the UI. A decoder can independently stat any downloaded archive. |
| Alignment direction | The PRD does not define transform direction, matrix layout, or coordinate space for differences. That can make independent decoding impossible. | The manifest stores a row-major 3x3 `reference_to_target` matrix in oriented pixel coordinates. Reconstruction warps the decoded base into the target's original oriented dimensions, then composites patches and masks stored in target coordinates. |
| Difference assets | A full-canvas `changes.webp` per frame can be a disguised second full-resolution copy even if most pixels are empty. | Store cropped changed-region patches with bounding boxes and lossless alpha masks. Merge nearby components to limit file overhead. A full-canvas representation is allowed only as an experiment and must be reported separately. |
| Masks | Lossy masks can create unstable edges and seams. | Use lossless grayscale PNG masks first. Consider lossless WebP only after codec feature checks and byte measurements. Image patches and the base use lossy WebP. |
| Reference base | A median/consensus scene is more complex and can create ghosting. | Use one automatically selected, encoded WebP reference as the base. A consensus base and multiple bases remain out of scope unless Gate 1 cannot pass on the curated envelope. |
| Transform model | One global homography can distort a mostly planar phone scene and does not solve parallax. | Start with partial affine estimation using RANSAC. Permit a homography only when it materially improves inlier/reprojection metrics and passes geometric sanity checks. Try ECC affine as a small-motion fallback. Reject strong parallax rather than adding optical flow in P0. |
| Dimensions and orientation | “Original dimensions” is ambiguous when EXIF rotation changes displayed width and height. Mixed resolutions add avoidable risk. | Normalize EXIF orientation immediately and define the resulting display-oriented dimensions as `output_width` and `output_height`. P0 accepts sets with identical oriented dimensions; incompatible dimensions fail clearly. Preserve the uploaded byte count separately. |
| Accepted versus uploaded frames | The PRD permits outlier rejection but also requires at least five photos and no silent discard. | Every input gets an explicit accepted/rejected state and reasons. Gate 1 uses at least five inputs and accepts/reconstructs all of them. In the product, folding is disabled if fewer than five frames remain accepted. Rejected frames never vanish from the UI. |
| Shared/change percentages | The denominator and aggregate semantics are unspecified, and a pre-fold estimate could be mistaken for a final metric. | Per frame: `changed_region_percent = changed mask pixels / output pixels`; `shared_region_percent = valid warped-base pixels not marked changed / output pixels`; uncovered pixels count as changed. Aggregate values are pixel-area-weighted. Analysis-resolution values are labeled “estimate”; result values come from full-resolution masks. |
| Quality | Whole-image SSIM can hide a damaged face or a small severe artifact. Color and range settings are unspecified. | P0 reports per-frame RGB SSIM using `data_range=255` and `channel_axis=2`, plus mean, minimum, and a real pixel-difference heatmap. Gate 1 selects and records thresholds after visual review. Add changed-region SSIM or worst-tile error as an engineering diagnostic if whole-image SSIM masks local damage. |
| Failure timing | Savings and final quality are known only after reconstruction, so the pipeline cannot literally stop before creating the package. | Complete reconstruction and evaluation, then mark the result `complete`, `complete_no_savings`, or `failed_quality`. Retain debug artifacts for review and never present a failed fold as saved storage. |
| Analyze versus fold | Separate endpoints risk performing alignment twice. | Analyze at reduced resolution and persist its results. Fold reuses metadata/reference choices and performs full-resolution final work. Any estimate shown before folding is explicitly labeled. |
| Processing model | A long synchronous HTTP request is vulnerable to browser/proxy timeouts; production job infrastructure is overkill. | Use an in-process, single-job executor and polling in Gate 2. Store status and artifacts in the moment's temporary directory so a demo can inspect failures. |
| WebP/AVIF availability | Codec support depends on the Pillow build, and AVIF support is less predictable across machines. | Add a processor “doctor” check for Pillow WebP support. Gate 1 uses WebP only. Run a later AVIF benchmark only if WebP passes and time remains. |
| GPT-5.6 | Requiring model output to change encoding can make deterministic output less reliable and can be decorative if it does not. | Add a narrow `SemanticAdvisor` interface only after Gate 3. Model advice may raise quality or mask dilation in bounded regions; invalid, unavailable, or timed-out advice becomes a no-op. Core acceptance and metrics never depend on it. |
| HEIC | HEIC decoding often needs platform-specific libraries and is already conditional in the PRD. | Defer HEIC until all deterministic gates pass. Do not let HEIC setup consume Gate 1 time. |
| Privacy cleanup | A robust distributed retention system is out of scope, but leaving uploads indefinitely violates the PRD. | Use a configured local workspace, a `DELETE` endpoint, startup cleanup, and best-effort TTL cleanup. State clearly that this is prototype behavior. |

## 5. Final proposed technology stack

Use conservative, pinned versions in lockfiles after the foundation phase verifies them on the demo machine.

### Runtime and repository tooling

- Git monorepo with npm workspaces for JavaScript packages.
- Node.js 20.9 or newer and npm. Gate 0 pins the verified demo runtime, Node.js 24.13.0 and npm 11.6.2, while retaining Next.js's Node 20.9 minimum in package metadata.
- Python 3.12.11, pinned by `.python-version` and constrained to the Python 3.12 line by `pyproject.toml`.
- Standard `.venv` plus `pip`, `pyproject.toml`, and a resolved `requirements.lock`; do not introduce `uv` because it is not needed for this prototype.
- Root `Makefile` as the human-facing command index, with the underlying commands documented in `README.md`.

### Frontend

- Next.js 16.2.10 App Router, React 19.2.7, and TypeScript 5.9.3, locked after verification on the demo machine.
- Tailwind CSS 4.3.3 for fast, local styling.
- Native `fetch`, `FormData`, file input/drag events, and object URLs; avoid an extra data-fetching framework.
- `<canvas>` for the comparison slider overlay and difference display.
- Generated TypeScript types from FastAPI's OpenAPI document using `openapi-typescript`.
- ESLint 9.39.2 and the TypeScript compiler in Gate 0. Add Vitest/React Testing Library and Playwright only when Gate 2 introduces product behavior worth testing.

Use the current stable Next.js release selected and locked during Gate 0, rather than a floating `latest` dependency. The official installation guide documents the App Router defaults and Node requirement: <https://nextjs.org/docs/app/getting-started/installation>.

### Processor

- FastAPI, Uvicorn, Pydantic, and `python-multipart`.
- OpenCV headless for features, transform estimation, warping, masks, and debug overlays.
- Pillow for decode/encode, EXIF transpose, thumbnails, contact sheets, and codec capability checks.
- NumPy for pixel operations.
- scikit-image for SSIM.
- Pytest, `httpx2`, and Ruff for validation. FastAPI's current test client deprecates the older `httpx` package name, so Gate 0 uses its maintained replacement.
- Standard-library `zipfile`, `hashlib`, `tempfile`, `pathlib`, and `json` for artifact handling; no packaging service.

OpenCV's feature/homography flow explicitly relies on matched points and robust estimation such as RANSAC: <https://docs.opencv.org/master/d1/de0/tutorial_py_feature_homography.html>. Pillow exposes a runtime WebP capability check: <https://pillow.readthedocs.io/en/stable/reference/features.html>. The scikit-image SSIM API exposes the required `data_range` and `channel_axis` parameters: <https://scikit-image.org/docs/stable/api/skimage.metrics.html>.

### Explicit exclusions

- No database or ORM.
- No Docker requirement for the primary local path.
- No Redis, Celery, Kafka, or managed queue.
- No auth or user model.
- No cloud buckets, CDN, or deployment platform work.
- No component system, animation library, or state-management library until the basic flow is reliable.
- No AVIF, HEIC, optical flow, segmentation model, or multiple-reference implementation in the first three gates.

## 6. Recommended repository structure

```text
photofold/
├── apps/
│   └── web/
│       ├── src/
│       │   ├── app/                  # Next.js routes and page composition
│       │   ├── components/           # upload, progress, metrics, viewer
│       │   └── lib/                  # typed API client and browser helpers
│       ├── tests/
│       └── package.json
├── services/
│   └── processor/
│       ├── src/photofold/
│       │   ├── api/                  # FastAPI routes and error mapping
│       │   ├── contracts/            # Pydantic request/response models
│       │   ├── pipeline/             # preprocess, align, mask, encode, evaluate
│       │   ├── package/              # manifest, writer, validator, decoder
│       │   ├── semantic/             # optional adapter; deterministic no-op default
│       │   ├── cli.py                 # Gate 1 benchmark and package verification
│       │   ├── config.py
│       │   └── main.py
│       ├── tests/
│       │   ├── unit/
│       │   ├── integration/
│       │   └── golden/               # small metadata/range expectations, not fake metrics
│       ├── pyproject.toml
│       └── requirements.lock
├── packages/
│   └── contracts/
│       ├── openapi.json              # generated from Pydantic/FastAPI
│       └── src/generated.ts          # generated; never hand-edited
├── configs/
│   ├── gate1.yaml                    # thresholds and codec settings chosen by experiments
│   └── demo.yaml
├── data/
│   └── demo/
│       ├── README.md                 # provenance, consent/license, capture envelope
│       ├── hdrplus-static/           # Gate 0/first Gate 1 real burst
│       ├── expression-static/
│       ├── pose-minor-motion/
│       └── unique-entry/
├── artifacts/                        # ignored; real run output and cached demo fallback
├── scripts/                           # orchestration only; no duplicate pipeline logic
├── docs/
│   ├── PhotoFold_Developer_PRD.md
│   ├── PhotoFold_Demo_Script.md
│   └── IMPLEMENTATION_PLAN.md
├── .env.example
├── .gitignore
├── AGENTS.md
├── Makefile
├── package.json                       # npm workspaces and root commands
├── package-lock.json
└── README.md
```

The curated photos should be committed only if their license/consent and repository size are acceptable. Otherwise, `data/demo/README.md` must provide a reproducible local placement/download procedure and checksums, and the actual images must be present on every demo machine before Gate 1 is considered reproducible. Do not use private personal photos without explicit approval.

## 7. Deterministic package and reconstruction design

### 7.1 Normalized source model

For each upload, record both:

- Source facts: filename, MIME sniff result, uploaded byte count, EXIF timestamp when present, and checksum.
- Normalized facts: display-oriented width/height, RGB/RGBA pixel mode, and analysis-copy dimensions.

`original_total_bytes` is the sum of the exact uploaded files, before orientation normalization or transcoding. Quality is measured against the normalized decoded pixel arrays because those represent the displayed photo.

Reject corrupt images, unsupported decoded modes, decompression bombs, non-opaque alpha if it cannot be preserved correctly, and incompatible oriented dimensions with explicit error codes.

### 7.2 Reference selection and alignment

For every candidate frame, calculate a reference score from:

- average pairwise feature-match/inlier success;
- Laplacian sharpness;
- clipped shadow/highlight penalty;
- valid scene coverage after trial transforms; and
- alignment failure count.

Choose the highest-scoring frame and record all score components. Start with ORB plus Hamming matching and RANSAC partial-affine estimation. Promote a transform to a homography only when its validation score is better and its projected corners remain plausible. Record inlier count, inlier ratio, median reprojection error, valid overlap, transform type, and rejection reason.

During analysis, transforms may be estimated at reduced resolution, but the final transform must be scaled/refined for full-resolution coordinates before it enters the package.

### 7.3 Package coordinate convention

For frame `i`, the manifest stores:

- `reference_to_target`: a row-major 3x3 matrix mapping reference pixels to target pixels;
- `output_width` and `output_height`: normalized, display-oriented target dimensions;
- interpolation and border-mode identifiers;
- zero or more target-space patches, each with `[x, y, width, height]`, image path, lossless mask path, and optional residual path.

Reconstruction is exactly:

1. Decode `base.webp`.
2. Warp it with `reference_to_target` onto the target output canvas.
3. Decode each target-space patch and its lossless mask.
4. Alpha-composite patches in manifest order.
5. Apply an optional residual only if its encoding was validated during a later experiment.
6. Return the normalized target-sized pixel array, then encode a requested standard export format.

Changed masks are derived by comparing the target with the actual decoded-and-warped encoded base, not an unavailable ideal base. Invalid warp borders are always marked changed. Morphological close/dilate and modest feathering reduce seams. Connected components are cropped and nearby crops are merged so a frame is never stored as an accidental second full canvas.

### 7.4 Proposed `.photofold` contents

```text
moment.photofold                  # ZIP_STORED archive with this extension
├── manifest.json
├── base.webp
├── frames/
│   ├── 000/frame.json            # identity transform; normally no patches
│   └── 001/
│       ├── frame.json
│       └── patches/
│           ├── 000.webp
│           └── 000-mask.png
└── metadata/
    ├── analysis.json
    ├── metrics.json              # quality/config; no self-referential archive size
    └── semantic-analysis.json     # absent unless P1 ran successfully
```

`manifest.json` is versioned, schema-validated, and contains byte sizes plus SHA-256 checksums for every referenced non-manifest asset. It cannot checksum itself; the external run result can record the final archive checksum. Package validation rejects missing paths, unsafe ZIP paths, non-finite transforms, checksum mismatches, invalid dimensions, and unknown required codec/features.

Preview images, reconstructed exports, difference heatmaps, and debug overlays live in the temporary run directory, not in the compression package. If the team later chooses to include a preview in the downloadable archive, its bytes automatically count in `package_total_bytes`.

### 7.5 Real measurement rules

The external final result records:

```text
original_total_bytes       = sum(stat(uploaded source file))
package_total_bytes        = stat(final .photofold archive)
byte_delta                 = original_total_bytes - package_total_bytes
percent_change             = byte_delta / original_total_bytes * 100
bytes_saved                = max(byte_delta, 0)
percent_saved              = max(percent_change, 0)
is_smaller_than_originals  = package_total_bytes < original_total_bytes
```

The engineering benchmark additionally records:

```text
independent_webp_total_bytes
independent_webp_per_frame_ssim
relational_gain_bytes
relational_gain_percent
```

The independent baseline is evaluated as a rate-distortion curve, not a single arbitrary quality number. PhotoFold demonstrates relational compression only when it occupies fewer bytes than the independent encodes at equal or better mean and minimum SSIM. The product UI can keep the simpler PRD metric, while technical documentation discloses both.

SSIM is calculated for every reconstructed normalized frame. The evaluator must reopen the archive through the public decoder and compare the decoder's output, rather than compare an in-memory intermediate. Difference heatmaps are generated from real absolute pixel error. Thresholds and all codec/mask settings are persisted with the result.

## 8. Next.js-to-Python interface

### 8.1 Boundary and contract ownership

- Transport: HTTP/1.1 on localhost for the prototype.
- Upload: `multipart/form-data` with repeated `files` parts.
- Metadata and state: JSON.
- Images and bundle: streamed binary responses with explicit content types and download names.
- Contract owner: FastAPI/Pydantic OpenAPI schema.
- TypeScript client types: generated from the checked-in OpenAPI file.
- Contract check: regeneration must produce no Git diff.
- No Python imports in Next.js and no hand-maintained duplicate TypeScript DTOs.

### 8.2 Proposed endpoints

| Method and path | Behavior | Success |
|---|---|---|
| `GET /v1/health` | Process and codec capability check. | `200` with version and WebP support. |
| `POST /v1/moments` | Validate count/types, persist uploads temporarily, return thumbnails/metadata. | `201 Moment`. |
| `POST /v1/moments/{id}/analysis` | Queue/reuse reduced-resolution suitability and reference analysis. | `202 Moment` or `200` if cached. |
| `POST /v1/moments/{id}/fold` | Queue the deterministic full-resolution fold. Reject if analysis is not foldable. | `202 Moment`. |
| `GET /v1/moments/{id}` | Return state, stage progress, warnings, analysis, and real results when available. | `200 Moment`. |
| `GET /v1/moments/{id}/frames/{index}/original` | Stream the temporary normalized original for comparison. | `200 image/*`. |
| `GET /v1/moments/{id}/frames/{index}/reconstruction` | Stream a reconstruction created through the package decoder. | `200 image/*`. |
| `GET /v1/moments/{id}/frames/{index}/difference` | Stream the actual difference heatmap. | `200 image/png`. |
| `GET /v1/moments/{id}/frames/{index}/export?format=webp` | Export a standard image; allow `jpeg`, `png`, or `webp`. | Download response. |
| `GET /v1/moments/{id}/bundle` | Stream the final `.photofold` artifact. | Download response. |
| `DELETE /v1/moments/{id}` | Delete temporary originals, artifacts, and state. | `204`. |

Do not add automatic set splitting in P0. `split_recommended` is an analysis result with reasons, not a promise that the service creates multiple moments.

### 8.3 State model

```text
uploaded
  → analyzing → analyzed_foldable ─┐
              → analyzed_rejected  │
                                   └→ folding
                                        → complete
                                        → complete_no_savings
                                        → failed_quality
                                        → failed
any terminal/transient state → expired after cleanup
```

The moment response contains:

- `moment_id`, `status`, `created_at`, and `expires_at`;
- ordered frame metadata and per-frame acceptance state;
- `progress.stage`, `progress.completed`, `progress.total`, and a user-safe message;
- suitability status, score, reasons, outlier indices, reference index, estimates, and thresholds;
- when final, storage metrics, per-frame/aggregate quality, measured region percentages, warnings, and artifact URLs.

Frame indices are assigned once at upload and never renumbered after rejection.

### 8.4 Error contract

All non-success responses use one shape:

```json
{
  "error": {
    "code": "ALIGNMENT_FAILED",
    "message": "Frame 4 could not be aligned with enough confidence.",
    "stage": "align",
    "frame_indices": [4],
    "retryable": false,
    "debug": null
  }
}
```

`debug` is populated only in development and must not expose arbitrary local paths in the normal UI. Initial error codes include invalid count, unsupported type, decode failure, incompatible dimensions, insufficient overlap, insufficient features, implausible transform, alignment failure, quality below threshold, no savings, package validation failure, job busy, missing moment, expired moment, and semantic-provider failure. Model failure is a warning/no-op when deterministic processing remains possible.

### 8.5 Progress and concurrency

The frontend polls `GET /v1/moments/{id}` every 750–1000 ms while work is active and stops in a terminal state. One fold job runs at a time; a second request receives a structured `JOB_BUSY` response or remains queued in the single in-memory queue. Progress is stage-level and based on actual completed work units, not a fake timer.

FastAPI supports returning a response before background work, but its own documentation notes that heavier computation can call for larger queue systems. For this constrained single-machine prototype, the in-process single-job design is the intentional middle ground: <https://fastapi.tiangolo.com/tutorial/background-tasks/>.

## 9. Smallest end-to-end demoable vertical slice

The smallest useful slice is a CLI-driven technical demo, not a web mockup:

1. Use the real, licensed, checksum-verified seven-frame burst in `data/demo/hdrplus-static/`.
2. Run one command that selects a reference, aligns every frame, creates a WebP base and cropped target-space patches, writes a `.photofold` archive, and closes access to its internal workspace.
3. Launch the package decoder in a separate process with only the archive path and reconstruct every accepted frame.
4. Report the exact uploaded byte total, archive byte total, independently encoded WebP control, per-frame/mean/minimum SSIM, dimensions, and pass/fail gates.
5. Produce the required self-contained HTML experiment report with embedded originals, reconstructions, heatmaps, metrics, integrity results, and package file listing.
6. Export one reconstructed frame as a normal WebP or JPEG.

This is demoable end to end and tests the unique product claim. It intentionally has no polished upload UI, GPT call, animation, cloud component, or database. If this slice does not show honest relational benefit on at least one curated set, stop and tune/narrow the pipeline before building the complete frontend.

## 10. Phase-by-phase implementation plan

All validation targets below are deliverables of the named phase. `make verify-gateN` should run the listed checks without hidden manual setup beyond the documented environment and datasets.

Every gate also has a **Human verification** procedure. Its command, URL/file, visible evidence, checklist, and failure signals are part of the gate deliverable and must remain current in the root `README.md`. A reviewer must be able to pass or fail a gate from generated reports, rendered UI, downloaded artifacts, and visible file metadata. Source-code inspection is never a human-verification step.

### Phase 0 / Gate 0 — Foundation and measurement contract

**Goal:** Make the empty repository reproducible and freeze the experimental rules before implementing compression.

**Deliverables**

- Recommended directory structure, root workspace files, lockfiles, `.gitignore`, `.env.example`, `README.md`, `AGENTS.md`, and `Makefile`.
- Python package skeleton with CLI/help, API health endpoint, and codec “doctor”; Next.js shell that starts and displays processor health only.
- Pinned dependencies verified on the demo machine.
- At least one real curated Gate 1 dataset with five or more frames, provenance/consent, checksums, and a dataset manifest containing expected frame count and normalized dimensions.
- Written metric definitions, transform convention, package schema draft, error taxonomy, and experimental configuration file.
- Independent-WebP benchmark design and output schema.

**Acceptance criteria**

- A new developer can install and start both processes from the README.
- Pillow reports WebP encode/decode support.
- Dataset integrity checks pass and all Gate 1 inputs decode to compatible oriented dimensions.
- The processor's OpenAPI schema generates TypeScript types without hand edits.
- Lint, typecheck, import smoke tests, and the frontend production build pass.
- No compression result or product metric is hard-coded.

**Validation commands**

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --constraint services/processor/requirements.lock -e 'services/processor[dev]'
npm ci
.venv/bin/python -m photofold.cli doctor
.venv/bin/python -m photofold.cli validate-dataset data/demo/hdrplus-static
npm run contracts:check
npm run lint --workspaces --if-present
npm run typecheck --workspaces --if-present
npm run build --workspace apps/web
make verify-gate0
```

#### Human verification

1. **Run:** From the repository root, run `make human-verify-gate0`. The target must run the automated Gate 0 checks, write the artifacts below, start the processor on port 8000 and frontend on port 3000, print `Gate 0 services ready`, and remain running until `Ctrl-C`.
2. **Open:** Open <http://127.0.0.1:3000> and <http://127.0.0.1:8000/docs>.
3. **Expect to see:** The frontend shows a plain foundation status page with a `Processor connected` pill, a `WebP codec` card whose value is `Available`, processor `v0.1.0`, Python `3.12.11`, dataset `hdrplus-static`, `7` frames, and `1600px × 1200px` dimensions. FastAPI's rendered API page shows `/v1/health` and no authentication endpoints.
4. **Pass/fail checklist:**
   - [ ] Both URLs load without a stack trace or browser console-visible failure.
   - [ ] The frontend visibly says the processor is connected and WebP is available.
   - [ ] The displayed curated dataset has at least five decodable, compatible frames.
   - [ ] The command output ends its checks with `GATE 0: PASS` before starting the services.
   - [ ] No login, database, cloud, billing, or model credential is requested.
5. **Inspect these generated artifacts:** `artifacts/gate0/doctor.json`, `artifacts/gate0/dataset-validation.json`, and `packages/contracts/openapi.json`. Each must be valid human-readable JSON and the first two must contain a top-level `"status": "pass"` field.
6. **Gate failure is indicated by:** Either URL not loading; WebP reported unavailable; fewer than five compatible dataset frames; generated contracts missing; a visible error/traceback; any automated check marked failed; or any undocumented external service being required.

#### Gate 0 implementation record — 2026-07-18

**Status:** Complete and verified on the demo machine. No later-phase behavior was implemented.

**Completed deliverables**

- Created the npm-workspace monorepo foundation, root environment files, `AGENTS.md`, `README.md`, `Makefile`, JavaScript lockfile, Python direct pins, and resolved Python constraints.
- Added a Phase 0-only FastAPI processor with `/v1/health`, CLI help, codec doctor, dataset validator, OpenAPI export, and focused tests. The test suite asserts that no future product routes exist yet.
- Added a health-only Next.js page using generated OpenAPI TypeScript contracts. It displays real processor and dataset readiness and explicitly states that compression, reconstruction, storage, and quality metrics do not exist yet.
- Added the real `hdrplus-static` dataset: seven 1600×1200 JPEG derivatives from HDR+ burst `0006_20160722_115157_431`, with source URLs, attribution, CC BY-SA 4.0 license, source and derivative SHA-256 checksums, conversion recipe, and limitations.
- Froze the draft source/package byte definitions, RGB SSIM settings, `reference_to_target` convention, target-space patch model, package schema, suitability/error taxonomy, independent-WebP control, and experiment result schema. Gate 1 thresholds remain intentionally unset.
- Added `make verify-gate0` and `make human-verify-gate0`. The latter runs the automated gate, starts both local services, prints their URLs, and shuts down both cleanly on `Ctrl-C`.

**Decisions made during implementation**

- Use the actual verified runtimes—Node.js 24.13.0/npm 11.6.2 and Python 3.12.11—instead of the older machine assumptions in the original draft.
- Pin Next.js 16.2.10, React 19.2.7, TypeScript 5.9.3, and ESLint 9.39.2. ESLint 10.7.0 was rejected because Next's current React lint plugin crashes with it.
- Use FastAPI 0.139.2 with `httpx2` 2.7.0 for tests; FastAPI/Starlette emits a deprecation warning with the older `httpx` package.
- Keep the frontend-to-processor boundary as direct typed HTTP. Gate 0 generates TypeScript from the processor OpenAPI document and checks generated-file drift without relying on Git history.
- Use the static HDR+ burst as the first low-motion technical dataset. It is suitable for plumbing and initial compression experimentation, but it does not replace the expression, pose, and unique-entry datasets required in Gate 2.
- Keep every quality/alignment pass threshold `null` until Gate 1 produces a real parameter sweep and human visual review.

**Validation evidence**

| Command | Result |
|---|---|
| `.venv/bin/python -m pip install --constraint services/processor/requirements.lock -e 'services/processor[dev]'` | Passed; the pinned editable processor environment resolved successfully. |
| `npm ci` | Passed from `package-lock.json`; 400 packages installed. |
| `.venv/bin/python -m photofold.cli doctor` | Passed; WebP compile support and a real encode/decode round trip succeeded. |
| `.venv/bin/python -m photofold.cli validate-dataset data/demo/hdrplus-static` | Passed; 7/7 JPEGs decoded at 1600×1200, every SHA-256 matched, and the exact total was 4,408,395 bytes. |
| `.venv/bin/python -m ruff check services/processor` | Passed. |
| `.venv/bin/python -m pytest -q services/processor/tests` | Passed: 4 tests. |
| `npm run contracts:check` | Passed; regenerated OpenAPI and TypeScript contracts matched the checked-in artifacts. |
| `npm run lint --workspaces --if-present` | Passed. |
| `npm run typecheck --workspaces --if-present` | Passed for the frontend and contracts package. |
| `npm run build --workspace apps/web` | Passed; Next.js produced the static `/` route. |
| `make verify-gate0` | Passed and printed `GATE 0: PASS`. |
| `make human-verify-gate0` | Passed automated checks; both documented URLs returned HTTP 200, `/v1/health` returned the real dataset/codec facts, and `Ctrl-C` left ports 3000 and 8000 clear. |

The production build needs permission to create Turbopack's local CSS worker in a restricted sandbox. Its first sandboxed attempt failed with `binding to a port: Operation not permitted`; the unchanged build passed outside that restriction. This is an execution-environment constraint, not an application dependency.

**Remaining limitations**

- Phase 0 does not align, compress, package, decode, reconstruct, score, or report savings for any image. There are no product upload/job routes and no GPT integration.
- `hdrplus-static` is one low-motion natural scene. Whether it produces relational savings at acceptable quality remains completely unproven until Gate 1; it does not exercise faces, expressions, pose, or unique entry.
- `npm audit --omit=dev` reports two moderate entries because Next.js 16.2.10 bundles PostCSS 8.4.31, affected by `GHSA-qx2v-qp2m-jg93`. The root PostCSS is already 8.5.19, npm proposes only an invalid major downgrade of Next as a “fix,” and the Gate 0 page does not accept or stringify untrusted CSS. Re-check for a patched stable Next release before the demo and do not suppress the advisory.
- The install and human-verification scripts target the documented macOS/Unix-like hackathon environment; Windows support and CI are not part of Gate 0.

### Phase 1 / Gate 1 — Compression hypothesis proof

**Goal:** Prove or falsify the deterministic shared-scene hypothesis on real images before building the product UI.

**Deliverables**

- CLI benchmark for the Gate 1 dataset.
- Automatic reference selection with recorded score components.
- ORB/affine alignment, confidence data, valid overlap masks, and alignment overlays.
- Encoded WebP reference base, cropped target-space change patches, and lossless masks.
- Versioned manifest, archive writer, package validator, and package-only decoder.
- Reconstruction of every accepted frame at its normalized original dimensions.
- Actual final archive byte count and independently encoded WebP rate-distortion control.
- Per-frame, mean, and minimum SSIM plus pixel-difference heatmaps.
- Parameter sweep report for base/patch WebP quality, difference threshold, mask dilation/feathering, and affine versus homography where warranted.
- One standard-image export generated from a package reconstruction.
- `artifacts/gate1/hdrplus-static/report.html`, a self-contained experiment report generated from the real run result. All CSS, JavaScript, originals, reconstructions, and heatmaps must be embedded so the file renders offline with no server or sibling assets. It must visibly contain:
  - an explicit `GATE 1: PASS` or `GATE 1: FAIL` verdict and failed checks;
  - original and reconstructed images side by side for every frame;
  - a difference heatmap for every frame;
  - exact original total size, `.photofold` archive size, signed byte delta, bytes/percentage saved, and independent-WebP control size;
  - every frame's filename, dimensions, accepted state, SSIM, and quality-threshold result;
  - mean and minimum SSIM;
  - a complete package-member listing with path and encoded bytes;
  - visible integrity checks for accepted/reconstructed counts, dimensions, package-only decoding, archive stat, member checksums, quality threshold, original-savings result, and matched-quality independent-WebP result.

**Acceptance criteria**

- One real curated set has at least five accepted frames; all uploaded frames in this Gate 1 set are accepted and reconstructed.
- A clean decoder process receives only the `.photofold` archive and reconstructs all frames successfully.
- Every reconstruction has the expected normalized dimensions.
- The archive passes schema, path, asset, checksum, and transform validation.
- `package_total_bytes` equals the final artifact's actual file-system size; source totals equal the sum of exact uploaded files.
- Per-frame, mean, and minimum SSIM are present and are calculated from decoded package reconstructions.
- The configured quality threshold is chosen from the sweep, visually reviewed, committed, and passed. It is not invented in the UI.
- The archive is smaller than the original uploaded collection for at least one curated set, satisfying the PRD gate.
- To claim the compression hypothesis is proven, the archive also beats the independent-WebP control at equal or better mean and minimum SSIM. If it does not, the team reports that ordinary transcoding—not PhotoFold's relationship model—explains the saving and does not proceed to the complete UI.
- Debug output makes seams, rejected alignment regions, and patch coverage inspectable.
- `report.html` opens with networking disabled, has no external asset dependencies, and contains no broken images.
- Every metric and package-listing value in the report is generated from `benchmark.json` and the final archive, and visible integrity checks confirm that they match.

**Validation commands**

```bash
.venv/bin/python -m photofold.cli benchmark \
  --dataset data/demo/hdrplus-static \
  --config configs/gate1.yaml \
  --output artifacts/gate1/hdrplus-static
.venv/bin/python -m photofold.cli verify-package \
  artifacts/gate1/hdrplus-static/moment.photofold
.venv/bin/python -m photofold.cli export \
  artifacts/gate1/hdrplus-static/moment.photofold \
  --frame 0 --format webp --output artifacts/gate1/exported-000.webp
.venv/bin/pytest -q services/processor/tests/unit services/processor/tests/integration/test_gate1.py
make verify-gate1 DATASET=data/demo/hdrplus-static
```

#### Human verification

1. **Run:** From the repository root, run `make human-verify-gate1 DATASET=data/demo/hdrplus-static`, then run `open artifacts/gate1/hdrplus-static/report.html`.
2. **Open:** Open the exact file `artifacts/gate1/hdrplus-static/report.html`. It must work with networking disabled and must not require a local server.
3. **Expect to see:** A single rendered experiment report headed `PhotoFold Gate 1 Compression Experiment` and an explicit gate verdict. The top summary shows exact uploaded bytes, final archive bytes, signed delta, saved bytes/percentage, independent-WebP control, mean SSIM, and minimum SSIM. Below it, every accepted frame has its original and reconstruction side by side, a difference heatmap, dimensions, and SSIM. The bottom contains the full package file listing and an integrity-check table. No image should be a broken link.
4. **Pass/fail checklist:** Gate 1 passes only when every item below passes. A report that beats originals but not independent WebP must show `STORAGE REDUCTION: PASS`, `RELATIONAL HYPOTHESIS: FAIL`, and an overall Gate 1 `FAIL`.
   - [ ] The report says `GATE 1: PASS` and identifies the dataset/config/run timestamp.
   - [ ] At least five input frames are shown, all are accepted, and every one has a reconstruction.
   - [ ] Every original/reconstruction pair has matching visible dimensions and a per-frame SSIM at or above the committed threshold.
   - [ ] Mean and minimum SSIM are present and the minimum equals the lowest visible per-frame score.
   - [ ] A real heatmap is visible for every frame and obvious seams or subject damage are absent at normal size and zoom.
   - [ ] The exact final archive size is smaller than the original total and storage saved is calculated from those two numbers.
   - [ ] The relationship-proof row says the package beats the matched-quality independent-WebP control; otherwise the PRD storage gate may pass, but the compression hypothesis does not.
   - [ ] The integrity table says package-only reconstruction, member checksums, file-size accounting, dimensions, and manifest validation all passed.
   - [ ] The package listing includes `manifest.json`, `base.webp`, frame metadata, and every referenced patch/mask; its listed members agree with the visible member count/total.
5. **Inspect these generated artifacts:** Within `artifacts/gate1/hdrplus-static/`, inspect `report.html`, `moment.photofold`, `benchmark.json`, `package-inventory.json`, `reconstructions/`, `heatmaps/`, `masks/`, `alignment-overlays/`, and `exported-000.webp`. The HTML report is the primary evidence; the directories permit optional full-resolution visual inspection without reading code.
6. **Gate failure is indicated by:** Any broken/missing image; fewer than five accepted or reconstructed frames; dimension mismatch; checksum/manifest/package-only decoder failure; missing or below-threshold SSIM; visible unacceptable artifacts; archive bytes not matching the measured file; package not smaller than originals; package not beating independent WebP at matched quality; missing package members; hard-coded/blank values; or an overall `FAIL` verdict.

**Gate response if it fails**

Inspect the rate-distortion and patch-coverage reports. In order: narrow the supported dataset envelope; fix transform/mask defects; merge/crop patches more effectively; sweep WebP settings; try plausible affine/homography selection; add selective residual patches. Do not add GPT, optical flow, multiple bases, AVIF, or the complete UI as a substitute for a failed proof.

#### Phase 1 completion record — 2026-07-18

**Status:** Implemented and verified within the CLI-only Gate 1 boundary. Phase 2 routes, product UI, job processing, additional datasets, GPT, AVIF, databases, queues, authentication, billing, and cloud infrastructure were not started.

**Implemented deliverables**

- Added a deterministic Gate 1 module for EXIF-aware RGB loading, automatic reference selection, ORB feature matching, RANSAC partial-affine/homography comparison, geometric sanity checks, full-resolution warping, change-mask extraction, WebP encoding, package writing, package-only decoding, verification, SSIM, heatmaps, alignment overlays, and standard-image export.
- Added a strict Pydantic manifest and matching JSON contracts. Validation covers safe ZIP paths, exact inventory, SHA-256 and byte counts, required codecs, contiguous frames, finite/non-singular transforms, plausible projected geometry, in-bounds non-full-canvas patches, package-only dimensions, and the absence of a circular internal archive-size value.
- Added `benchmark`, `verify-package`, `export`, and `verify-report` CLI commands plus repeatable `verify-gate1` and `human-verify-gate1` Make targets.
- Added a real parameter sweep for WebP quality, difference threshold, dilation, feathering, minimum component area, and affine/homography evidence. The independent control exhaustively encodes all seven frames at every integer WebP quality from 1 through 100.
- Added unit and integration coverage that runs the real dataset, reopens the closed package, reconstructs all seven frames, checks the exhaustive control, verifies the report, and asserts that the API still exposes only `/v1/health`.
- Generated `artifacts/gate1/hdrplus-static/report.html` with all 21 original/reconstruction/heatmap previews embedded, an explicit verdict, exact storage and quality metrics, per-frame results, sweep evidence, integrity checks, and the complete package-member listing. Full-resolution inspection artifacts remain beside it.

**Decisions made from the real experiment**

- Keep WebP. AVIF was not needed to establish Gate 1 and was not tested.
- Use automatically selected frame 0 as the single base and partial affine as the selected transform model; homography comparisons are retained as evidence and are used only when materially and geometrically better.
- Use WebP quality 70 for base and patches, difference threshold 24, dilation radius 8, decoder-side feather radius 2, minimum component area 1,152 pixels, 384-pixel patch tiles, and at most 64 patches per frame.
- Store compact machine-only package JSON because the archive is `ZIP_STORED`. Patch crops retain real target pixels outside the binary mask, which prevents lossy WebP from bleeding zero-fill into the composited edge. The binary mask alone determines application, and its recorded feather radius is applied by the decoder.
- Commit dataset-specific thresholds of mean RGB SSIM ≥ 0.85 and every frame RGB SSIM ≥ 0.82 after the sweep and full-resolution visual review. These are experiment thresholds, not product guarantees.

**Authoritative measured result**

| Metric | Measured value |
|---|---:|
| Accepted / reconstructed frames | 7 / 7 |
| Dimensions | 1600×1200 for every frame |
| Exact uploaded source total | 4,408,395 bytes |
| Closed `.photofold` archive | 677,744 bytes |
| Saved versus uploaded sources | 3,730,651 bytes (84.6261%) |
| Smallest equal-or-better independent control | WebP q31, 725,126 bytes |
| Relational gain versus control | 47,382 bytes (6.5343%) |
| PhotoFold mean / minimum SSIM | 0.851131 / 0.826471 |
| Control mean / minimum SSIM | 0.853045 / 0.852371 |
| Package members | 157 |
| Overall generated verdict | `GATE 1: PASS` with no failed integrity checks |

The independent q31 set has equal-or-better mean and minimum SSIM, so the comparison is conservative: the PhotoFold package is 6.5343% smaller even though the matched control scores higher on both reported quality aggregates.

**Acceptance-criteria comparison**

| Criterion | Result | Evidence |
|---|---|---|
| At least five real frames; all accepted/reconstructed | Pass | 7/7 real HDR+ frames accepted and package-only reconstructed. |
| Decoder receives only the archive | Pass | `verify-package` reopened `moment.photofold` and decoded every frame without source paths. |
| Expected dimensions | Pass | Every decoded frame is 1600×1200. |
| Schema/path/asset/checksum/transform validation | Pass | All package verifier rows passed across 157 members. |
| Exact source and final archive accounting | Pass | Source stats sum to 4,408,395 bytes; benchmark and file stat both report 677,744 archive bytes. |
| Real per-frame/mean/minimum quality | Pass | Scores were calculated from decoded package reconstructions; mean 0.851131 and minimum 0.826471 pass the committed 0.85/0.82 thresholds. |
| Smaller than uploaded collection | Pass | The package saves 3,730,651 bytes (84.6261%). |
| Beats equal-or-better independent WebP | Pass | 677,744 package bytes versus exhaustive-control q31 at 725,126 bytes. |
| Debug artifacts inspect seams and coverage | Pass | Full-resolution reconstructions, heatmaps, masks, and alignment overlays exist for every frame. |
| Self-contained report and generated values | Pass with final manual browser check documented | Structural verification found 21 embedded images, seven frame sections, all required sections, and no external image, script, or stylesheet dependencies. The exact OS/browser open remains the human command below. |

**Validation record**

| Command | Result |
|---|---|
| `.venv/bin/python -m photofold.cli benchmark --dataset data/demo/hdrplus-static --config configs/gate1.yaml --output artifacts/gate1/hdrplus-static` | Passed; generated the authoritative package, metrics, inspection artifacts, export, and 2,302,736-byte self-contained report. |
| `.venv/bin/python -m photofold.cli verify-package artifacts/gate1/hdrplus-static/moment.photofold` | Passed; 7/7 package-only decodes and every validation/checksum row passed. |
| `.venv/bin/python -m photofold.cli export artifacts/gate1/hdrplus-static/moment.photofold --frame 0 --format webp --output artifacts/gate1/exported-000.webp` | Passed; wrote a real 1600×1200, 376,396-byte WebP export. |
| `.venv/bin/pytest -q services/processor/tests/unit services/processor/tests/integration/test_gate1.py` | Passed; 7 tests in 303.42 seconds. |
| `make verify-gate1 DATASET=data/demo/hdrplus-static` | Passed; reproduced the exact metrics, 7 tests passed again in 313.47 seconds, and printed `GATE 1: PASS`. |
| `make human-verify-gate1 DATASET=data/demo/hdrplus-static` | Passed; reproduced the exact metrics again, 7 tests passed in 307.18 seconds, verified the report, printed `GATE 1: PASS`, and printed the exact local report/open command. |
| `make verify-gate0` | Passed after granting the production build permission to bind Turbopack's local helper port; 4 foundation tests, contracts, lint, typecheck, and build passed, ending with `GATE 0: PASS`. |

**Human verification performed and remaining**

- Full-resolution originals, every reconstruction, the minimum-score frame, its heatmap, mask, and alignment overlay were visually inspected. The scene remains complete; retaining real target pixels outside masks removed the visible dark patch contours found during tuning. Remaining differences are concentrated in fine foliage, high-contrast edges, and burst noise.
- The report's embedded assets and required sections passed automated self-containment checks. A local-file browser policy prevented automated navigation to a `file://` URL, so the final human browser-render check remains: run `make human-verify-gate1 DATASET=data/demo/hdrplus-static`, open `artifacts/gate1/hdrplus-static/report.html`, and complete the checklist above without reading source code.

**Remaining limitations**

- The result proves the hypothesis only for one static, low-motion natural-scene burst. It says nothing yet about faces, expressions, pose changes, unique entries, parallax, or mixed dimensions.
- The 0.85 mean and 0.82 minimum SSIM thresholds are visually reviewed for this dataset only and are lower than the independent control's scores. Whole-image SSIM can still hide local perceptual defects.
- Relational savings are real but modest at 47,382 bytes (6.5343%) versus the matched control. Later codec/library versions or more difficult data can reverse the result, so Phase 2 must use regression ranges and additional curated sets.
- The archive has 157 members. Component filtering and compact JSON make it viable for this experiment, but package overhead and patch grouping still need hardening.
- Gate 1 remains a deterministic CLI experiment. There is no processing API, upload/product UI, persistence, job runner, or semantic provider.

### Phase 2 / Gate 2A — Deterministic pipeline hardening

**Goal:** Turn the successful spike into a testable pipeline that handles all three curated scenarios and fails unsuitable inputs clearly.

**Deliverables**

- Modular preprocess, suitability, alignment, change, encode, reconstruct, and evaluate stages.
- Three real curated datasets: expression/static, pose/minor motion, and unique-entry.
- Configurable thresholds with every selected value written into analysis/results.
- Per-frame accepted/rejected records and stable machine-readable errors.
- Full package and manifest test suite, including malicious/missing path checks.
- Unit, integration, failure, and regression-range tests.
- Regression expectations for reference choice, confidence range, package-byte range, SSIM range, and patch coverage; no byte-for-byte codec requirement.
- Best-effort cleanup utilities and TTL configuration.

**Acceptance criteria**

- All three curated success sets accept and reconstruct every expected frame or the dataset documentation explicitly changes the expected outcome before the test is written.
- Unrelated scenes, excessive motion, corrupt images, invalid count, incompatible dimensions, low quality, and no-savings fixtures produce the expected status and reasons.
- The decoder never accesses source images.
- Byte inventories match actual archive members and the final archive stat.
- Repeated runs stay inside recorded metric ranges.
- No GPT credential is configured or required.

**Validation commands**

```bash
.venv/bin/ruff check services/processor
.venv/bin/pytest -q services/processor/tests/unit
.venv/bin/pytest -q services/processor/tests/integration
.venv/bin/python -m photofold.cli benchmark-all \
  --datasets data/demo --config configs/demo.yaml --output artifacts/gate2
.venv/bin/python -m photofold.cli regression-check artifacts/gate2
make verify-gate2a
```

#### Human verification

1. **Run:** From the repository root, run `make human-verify-gate2a` and then `open artifacts/gate2a/report.html`.
2. **Open:** Open the exact file `artifacts/gate2a/report.html`.
3. **Expect to see:** A rendered matrix headed `PhotoFold Gate 2A Deterministic Pipeline Report`. It shows the three curated success datasets in separate rows with frame counts, reference thumbnails, accepted/reconstructed counts, package/original bytes, mean/minimum SSIM, runtime, and verdict. A second table shows every required rejection fixture with its expected and actual error code/reason. Links open full-resolution Gate 1-style reports for each successful dataset.
4. **Pass/fail checklist:**
   - [ ] The top-level report says `GATE 2A: PASS`.
   - [ ] `expression-static`, `pose-minor-motion`, and `unique-entry` each show the documented expected outcome and no unexplained rejected frame.
   - [ ] Every successful dataset shows equal accepted and reconstructed counts, package-only decode passed, and quality/size values derived from a named run.
   - [ ] Every negative fixture shows the expected user-readable explanation and machine-readable code.
   - [ ] Repeated-run values remain within the visible stored ranges; the report does not require byte-for-byte identity.
   - [ ] The report says `Semantic provider: disabled` and still passes.
5. **Inspect these generated artifacts:** `artifacts/gate2a/report.html`; the per-dataset `report.html`, `moment.photofold`, `benchmark.json`, and `regression.json` under `artifacts/gate2a/datasets/`; and `artifacts/gate2a/failure-cases.json`.
6. **Gate failure is indicated by:** A missing curated scenario; an unexpected accepted/rejected frame; any package-only, checksum, dimension, quality, or regression-range failure; a rejection fixture with the wrong code/reason; a metric shown without a run artifact; model/network dependency; broken report links; or an overall `FAIL` verdict.

### Phase 3 / Gate 2B — Stable local processing service

**Goal:** Expose the proven deterministic pipeline through the typed FastAPI boundary without adding infrastructure.

**Deliverables**

- Proposed `/v1` endpoints, generated OpenAPI contract, and generated TypeScript types.
- Multipart upload validation and safe temporary moment directories.
- Single-job in-process execution, real stage progress, JSON state persistence, and polling.
- Original, reconstruction, difference, export, bundle, and delete responses.
- Structured errors and development-only debug details.
- Startup/TTL/manual cleanup.
- API tests proving all metrics and artifacts originate from processor outputs.

**Acceptance criteria**

- API processing of every curated dataset matches CLI results within documented ranges.
- A service restart never converts incomplete work into fake success; it marks/reloads state predictably.
- A second concurrent fold is queued or rejected honestly.
- Bundle bytes served over HTTP exactly match the completed artifact on disk.
- Generated TypeScript contracts are current.
- The API works with GPT disabled and no network access.

**Validation commands**

```bash
.venv/bin/pytest -q services/processor/tests/api
npm run contracts:generate
git diff --exit-code -- packages/contracts
.venv/bin/uvicorn photofold.main:app --host 127.0.0.1 --port 8000
# In a second terminal:
.venv/bin/python -m photofold.cli api-smoke \
  --base-url http://127.0.0.1:8000 --dataset data/demo/expression-static
make verify-gate2b
```

The manual two-terminal smoke command should also be wrapped by `make verify-gate2b` so CI/local validation can start and stop the server safely.

#### Human verification

1. **Run:** From the repository root, run `make human-verify-gate2b`. The target must start FastAPI on port 8000, execute the API smoke workflow against the real `expression-static` dataset, write the artifacts below, print `GATE 2B: PASS` or `FAIL`, and remain running until `Ctrl-C`. In another terminal, run `open artifacts/gate2b/api-smoke-report.html`.
2. **Open:** Open `artifacts/gate2b/api-smoke-report.html` and <http://127.0.0.1:8000/docs>.
3. **Expect to see:** The report shows the exact sequence `upload → analyze → fold → poll → original → reconstruction → difference → export → bundle → delete`, with HTTP status, elapsed time, returned state, and pass/fail for each step. The rendered FastAPI page lists the `/v1` routes and their structured response schemas. The report links to the actual downloaded image, heatmap, export, and bundle.
4. **Pass/fail checklist:**
   - [ ] The report says `GATE 2B: PASS` and every workflow step is green.
   - [ ] Polling visibly advances through real named processor stages and reaches a documented terminal state.
   - [ ] Original, reconstruction, difference, export, and bundle links open successfully.
   - [ ] The downloaded bundle byte count and checksum match the values shown in the API report.
   - [ ] A deliberate second concurrent fold produces the documented `JOB_BUSY` or queued behavior rather than corrupting either job.
   - [ ] A deliberate invalid upload produces a structured visible error with code, stage, and user-readable message.
   - [ ] Deleting the moment changes its subsequent lookup to the documented missing/expired response.
5. **Inspect these generated artifacts:** Within `artifacts/gate2b/`, inspect `api-smoke-report.html`, `request-log.json`, `state-transitions.json`, `downloaded.photofold`, `downloaded-bundle.sha256`, `original.webp`, `reconstruction.webp`, `difference.png`, and `exported.webp`.
6. **Gate failure is indicated by:** Any unexpected HTTP status; fake/timer-only progress; missing route/schema; inaccessible artifact; bundle byte/checksum mismatch; malformed error; concurrency corruption; delete/cleanup failure; GPT/network requirement; traceback; or overall `FAIL`.

### Phase 4 / Gate 3 — End-to-end web product flow

**Goal:** Build only the UI required to exercise and prove the real processor.

**Deliverables**

- Upload/drop screen with instruction text, ordered thumbnails, filename, exact source size, normalized dimensions, remove action, and total.
- Analysis screen with labeled estimates, reference rationale, suitability, reasons, outliers, and explicit Fold action.
- Real polling progress tied to processor stages.
- Results screen with actual storage/result state, mean/minimum/per-frame SSIM, warnings, and contents summary.
- Frame browser with original/reconstruction toggle or slider and difference heatmap.
- One-frame standard export and `.photofold` bundle download.
- Understandable failure/no-savings/quality-failure states.
- Focused responsive layout sufficient for a laptop demo; no elaborate mobile polish.

**Acceptance criteria**

- A user completes upload → analyze → fold → inspect → export → bundle download with no CLI step.
- UI values match the API response and downloaded file stat; no number is computed from a mock or animation.
- Removing a file before analysis changes the uploaded total and processor input.
- Rejected frames remain visible with reasons.
- The viewer uses actual per-frame artifacts and can zoom via normal browser/canvas behavior.
- No-savings and failed-quality results never display positive-savings language.
- One Playwright test covers the curated happy path; focused tests cover error-state rendering.

**Validation commands**

```bash
npm run lint --workspaces --if-present
npm run typecheck --workspaces --if-present
npm run test --workspace apps/web
npm run build --workspace apps/web
npm run test:e2e --workspace apps/web -- --project=chromium
make verify-gate3
```

#### Human verification

1. **Run:** From the repository root, run `make human-verify-gate3 DATASET=data/demo/expression-static`. The target must clear only its Gate 3 temporary state, start the real processor and frontend, print `Gate 3 app ready at http://127.0.0.1:3000`, and remain running until `Ctrl-C`.
2. **Open:** Open <http://127.0.0.1:3000>.
3. **Expect to see:** A usable PhotoFold flow. Uploading the files in `data/demo/expression-static/` shows ordered thumbnails and real source totals. Analyze shows suitability, labeled estimates, reference rationale, and per-frame disposition. Fold shows real stage progress. Results show real archive/original/saved bytes, mean/minimum SSIM, every reconstructed frame, comparison view, heatmap, export, and bundle download. A no-savings fixture visibly uses neutral/failure language rather than a positive claim.
4. **Pass/fail checklist:**
   - [ ] All uploaded thumbnails, names, sizes, dimensions, and source total are visible and correct; removing one file updates the total before analysis.
   - [ ] Analysis clearly labels estimates, retains original frame indices, and explains suitability/reference selection.
   - [ ] Fold progress follows actual processor stages and reaches a terminal result without reloading the page.
   - [ ] Results match the processor values shown in `artifacts/gate3/latest/result.json`.
   - [ ] Every frame can switch/slide between original and reconstruction, zoom, and show a real heatmap.
   - [ ] One exported standard image opens in the browser/Preview and the `.photofold` bundle downloads with the displayed byte size.
   - [ ] Invalid, rejected, failed-quality, and no-savings cases are understandable and never show invented positive savings.
   - [ ] No login, database, cloud service, GPT credential, or source-code inspection is needed.
5. **Inspect these generated artifacts:** Within `artifacts/gate3/latest/`, inspect `result.json`, `moment.photofold`, `exported-frame.webp`, `ui-e2e-report/index.html`, and `gate1-report.html`; also open the browser-downloaded `PhotoFold-frame-000.webp` and `moment.photofold` files. The Gate 1 report is the processor-evidence cross-check if a displayed value is in doubt.
6. **Gate failure is indicated by:** A broken workflow; stale/mock/hard-coded metric; UI/API value mismatch; fake progress; missing/rejected frame without explanation; inaccessible compare/heatmap/export/bundle; downloaded byte mismatch; misleading savings language; unreadable error state; external-service requirement; or automated/human verdict `FAIL`.

### Phase 5 / Gate 4 — Optional semantic preservation

**Goal:** Add GPT-5.6 only if the deterministic demo is already complete and stable.

**Deliverables**

- `SemanticAdvisor` interface with deterministic no-op implementation as the default.
- Reduced-resolution contact sheet with frame indices and no full-resolution model upload.
- GPT-5.6 adapter with timeout, retry limit, schema validation, and recorded model/config metadata.
- Human-readable observations in the UI.
- One bounded policy that can alter processing, such as increasing patch quality/mask dilation inside a model-identified high-priority region, with hard limits.
- A/B output showing the observable decision and its real byte/quality effect.

**Acceptance criteria**

- The same deterministic workflow passes with model credentials absent, a timeout, invalid JSON, or provider failure.
- Model output never changes geometry, byte accounting, SSIM calculation, or final acceptance by itself.
- One curated semantic case causes a traceable bounded decision; the UI labels it accurately.
- All semantic-mode metrics are recalculated from the resulting real package.

**Validation commands**

```bash
.venv/bin/pytest -q services/processor/tests/semantic
PHOTOFOLD_SEMANTIC_PROVIDER=none make verify-gate4
PHOTOFOLD_SEMANTIC_PROVIDER=gpt make verify-semantic-demo \
  DATASET=data/demo/unique-entry
```

The provider-backed validation is optional for the deterministic build but required before showing semantic behavior in the final demo.

#### Human verification

1. **Run:** With the documented model credential available, run `PHOTOFOLD_SEMANTIC_PROVIDER=gpt make human-verify-gate4 DATASET=data/demo/unique-entry`, then run `open artifacts/gate4/semantic-comparison.html`. This target must also execute the same dataset once with `PHOTOFOLD_SEMANTIC_PROVIDER=none` and one forced provider-failure run.
2. **Open:** Open the exact file `artifacts/gate4/semantic-comparison.html`.
3. **Expect to see:** An A/B report headed `PhotoFold Gate 4 Semantic Preservation`. It shows the reduced contact sheet sent for analysis, schema-valid semantic observations, the precise bounded preservation decision they caused, and deterministic-versus-semantic package bytes/SSIM/patch overlays. A separate fallback panel shows that a forced timeout/invalid response produced a warning and a successful deterministic result.
4. **Pass/fail checklist:**
   - [ ] The report says `GATE 4: PASS` and names the provider/model/config used.
   - [ ] The contact sheet is reduced-resolution and visibly frame-indexed.
   - [ ] A human-readable observation maps to one visible, bounded encoding decision; before/after masks or patch settings make the change inspectable.
   - [ ] Both modes show newly measured package and quality metrics rather than copied values.
   - [ ] Geometry, byte accounting, SSIM, and deterministic acceptance remain processor-owned.
   - [ ] The forced model failure visibly falls back to deterministic processing and still reconstructs every expected frame.
   - [ ] Running with provider `none` remains a complete Gate 3-quality workflow.
5. **Inspect these generated artifacts:** Within `artifacts/gate4/`, inspect `semantic-comparison.html`, `contact-sheet.webp`, `semantic-analysis.json`, `decision-log.json`, `deterministic/moment.photofold`, `deterministic/result.json`, `semantic/moment.photofold`, `semantic/result.json`, `overlays/`, and `fallback-result.json`.
6. **Gate failure is indicated by:** No observable bounded decision; full-resolution source upload without justification; invalid/unrecorded model output; semantic mode using fabricated/stale metrics; model advice controlling geometry or measurement; forced failure breaking deterministic processing; missing A/B evidence; or overall `FAIL`. If credentials are unavailable, Gate 4 is `SKIPPED`, not passed; Gates 0–3 remain unaffected.

### Phase 6 / Gate 5 — Demo hardening and optional codec experiment

**Goal:** Make the proven path repeatable under hackathon conditions and spend remaining time only on visible, low-risk polish.

**Deliverables**

- Final selected demo set and rehearsal checklist.
- Real precomputed fallback artifacts generated by the current pipeline, with checksums, configuration, timestamp, and source-dataset identity.
- Stage visualization/folding animation driven by real job state.
- Final architecture diagram, README, limitations, and metric methodology.
- Cleanup command and offline deterministic demo mode.
- Optional WebP-versus-AVIF benchmark run on all curated datasets; no AVIF product switch without a recorded decision.

**Acceptance criteria**

- The full demo succeeds repeatedly from a clean start on the demo machine.
- Live, offline deterministic, and cached-fallback paths never display fabricated values.
- Cached results are visibly associated with the same dataset and genuine prior run.
- Network/model failure leaves the deterministic demo intact.
- AVIF is adopted only if it is materially smaller at matched quality, supported by the chosen Pillow build and browser/export path, and does not measurably reduce reliability. Otherwise WebP remains final.

**Validation commands**

```bash
make clean-demo-state
make verify-all
make demo-smoke DATASET=data/demo/expression-static
make demo-offline DATASET=data/demo/expression-static
make verify-cached-demo DATASET=data/demo/expression-static
.venv/bin/python -m photofold.cli codec-benchmark \
  --datasets data/demo --codecs webp,avif --output artifacts/codec-benchmark
```

The AVIF command is exploratory and should be skipped if the doctor check reports no reliable AVIF support.

#### Human verification

1. **Run:** From the repository root, run `make human-verify-gate5 DATASET=data/demo/expression-static`. The target must perform preflight checks, run the live deterministic workflow three times, verify the genuine cached fallback, start the final demo app, write the rehearsal report, print `Gate 5 demo ready at http://127.0.0.1:3000`, and remain running until `Ctrl-C`.
2. **Open:** Open <http://127.0.0.1:3000> and `artifacts/gate5/rehearsal-report.html` (run `open artifacts/gate5/rehearsal-report.html`).
3. **Expect to see:** The final rehearsable product flow with real upload/analysis/fold/reconstruction evidence, stage-driven animation, comparison/heatmap, export, and bundle download. The rehearsal report shows three successful live deterministic runs with durations and metric ranges, an offline run, cached-fallback provenance/checksums, model/network failure results, and the exact demo configuration. Cached mode is visibly labeled and uses values tied to a genuine prior run.
4. **Pass/fail checklist:**
   - [ ] The rehearsal report says `GATE 5: PASS`; all three live runs complete and their metrics remain within documented ranges.
   - [ ] The final UI completes the scripted workflow without a restart, code edit, terminal workaround, or fabricated value.
   - [ ] Every visible metric can be followed to the named run result and artifact in the rehearsal report.
   - [ ] Export and bundle files open, and the downloaded bundle's bytes/checksum match the displayed result.
   - [ ] Offline deterministic mode works with network/model access disabled.
   - [ ] Cached fallback is clearly labeled, matches the selected dataset/config, and passes provenance/checksum checks.
   - [ ] Failure of GPT or network access does not block deterministic processing.
   - [ ] Any AVIF result is labeled experimental unless its adoption criteria visibly pass; WebP remains the default otherwise.
5. **Inspect these generated artifacts:** Within `artifacts/gate5/`, inspect `rehearsal-report.html`, `runs/01/`, `runs/02/`, `runs/03/`, `offline/`, `cached-fallback/manifest.json`, `cached-fallback/moment.photofold`, `cached-fallback/checksums.json`, `demo-config.json`, `exported-frame.webp`, `downloaded.photofold`, `architecture.svg`, and `gate1-report.html`.
6. **Gate failure is indicated by:** Any failed or materially inconsistent rehearsal; demo-only hard-coded metric; terminal/source-code intervention; broken export/package; checksum or provenance mismatch; unlabeled cached data; deterministic failure when GPT/network is absent; animation detached from actual stage state; an unreliable codec switch; or overall `FAIL`.

## 11. Work that can safely run in parallel

Parallel work must not bypass Gate 1. In particular, building the full UI in parallel with an unproven compression approach creates expensive rework and encourages mock metrics.

| After prerequisite | Safe parallel tracks | Shared dependency / integration rule |
|---|---|---|
| Plan approved | Repository/tooling setup; licensing/curation of dataset 1; transform/manifest contract review. | Freeze metric and transform conventions before implementation merges. |
| Gate 0 structure exists | Alignment/reference experiment; independent-WebP/SSIM benchmark harness; package schema/validator tests. | Use fixed fixture contracts. One owner integrates encoder/decoder so coordinate assumptions cannot diverge. |
| First Gate 1 package reconstructs | Mask/patch parameter sweeps; package-only decoder tests; debug-report generation. | All tracks use the same package version and rate-distortion report. |
| Gate 1 passes | Dataset 2/3 preparation and expected outcomes; deterministic failure tests; FastAPI contract implementation; low-fidelity UI layout/design only. | Do not bind the UI to hand-written responses. Wait for generated OpenAPI types before real data integration. |
| API contract is frozen | Upload/analysis frontend; results/viewer frontend; API/job-state tests; cleanup/hardening. | Integrate daily against the same real local processor and never add fixture-only metrics to product code. |
| Gate 3 passes | Semantic adapter; semantic UI panel; demo animation; cached-output verification; optional AVIF experiment. | Each enhancement must be removable without changing the deterministic path. |

Tasks that should not run independently are: defining transform direction versus implementing the decoder, changing package contents versus byte accounting, changing masks versus quality gates, and changing API result fields versus generated contracts.

## 12. Technical risks and fallback approaches

| Risk | Early signal | Primary mitigation | Hackathon fallback |
|---|---|---|---|
| No true relational savings | Package beats uploads but not independent WebP; patches cover most pixels. | Use the rate-distortion control from the first experiment; crop/merge patches; narrow motion envelope; tune masks/codecs. | Demonstrate only the curated static-expression set. If it still does not beat the control, report the hypothesis as unproven rather than build a misleading UI. |
| Alignment/parallax failure | Low inlier ratio, implausible projected corners, large invalid borders, widespread false changes. | Partial affine first, transform sanity checks, strong reference selection, ECC small-motion fallback. | Reject the frame/set and use tripod-like or minimally moving datasets. Do not add optical flow under demo pressure. |
| Visible seams or face-detail damage | Heatmaps cluster at patch boundaries/faces despite high whole-image SSIM. | Lossless masks, component dilation/feathering, patch-quality sweep, decoded-base-aware masks, local diagnostics. | Increase patch quality/dilation for the demo config, accept lower savings honestly, or add selective residual crops. |
| Baseline/byte-accounting credibility | UI total differs from archive stat; included files are omitted from reporting. | Stat exact sources and final archive; checksum/member inventory; integration assertion on served bundle bytes. | Show a terminal/file-inspector verification in the demo and remove any metric whose provenance cannot be traced. |
| Codec inconsistency | WebP tests pass on one machine but fail or change materially elsewhere. | Pin Pillow, run doctor, lock demo machine, record versions/settings, allow byte ranges. | Use the verified demo environment and WebP only; skip AVIF/HEIC. |
| CPU/memory/time exceeds live-demo budget | Full-resolution runs stall or OS memory spikes. | Downscale analysis, decode/process frames sequentially, single worker, cap pixel count, pre-measure stage duration. | Use a documented medium-resolution curated set and genuine cached prior output as fallback. |
| SSIM hides local failures | High mean SSIM with an obviously damaged small subject. | Minimum per-frame SSIM, heatmaps, worst-tile/changed-region diagnostics, visual Gate 1 review. | Raise patch preservation around the affected region and disclose the chosen quality/savings tradeoff. |
| Temporary job loss or stale uploads | Restart strands active state; disk fills across rehearsals. | JSON state per moment, explicit incomplete-on-restart behavior, DELETE/startup/TTL cleanup. | Run a cleanup command before each demo and process one known set. |
| GPT latency/variance/failure | Timeout, invalid schema, inconsistent regions, no observable value. | P1-only adapter, reduced input, strict schema, hard timeout, bounded advice, no-op fallback. | Disable GPT and use deterministic output. The core demo remains complete. |
| Scope creep from presentation features | Animation/HEIC/segmentation consumes time before pipeline evidence exists. | Gate order and acceptance criteria are explicit; no full UI before Gate 1. | Cut animation, semantic mode, HEIC, AVIF, zoom polish, and multiple quality modes in that order. |

## 13. PRD clarifications applied

`docs/PhotoFold_Developer_PRD.md` has been revised to incorporate these decisions:

1. **Independent-codec control:** The user-facing original-byte formula remains, while Gate 1 now requires a matched-quality independent-WebP rate-distortion comparison before claiming relationship-compression benefit.
2. **Final-artifact size:** `package_total_bytes` is the closed `.photofold` archive size, and internal metrics omit the circular final-archive-size field.
3. **Transform and patch coordinates:** Matrix direction/layout, oriented-pixel coordinates, interpolation/border metadata, and target-space patch bounding boxes are specified.
4. **Normalized dimensions:** “Original output dimensions” now means display-oriented dimensions after EXIF normalization, and P0 may reject mixed normalized dimensions.
5. **Accepted-frame semantics:** Every upload retains its index and explicit disposition, at least five accepted frames are required, and the primary Gate 1 set accepts/reconstructs every input.
6. **Package-download priority:** Package creation and download are P0 rather than P1.
7. **Measured region percentages:** Denominators/aggregation are defined, and analysis estimates are distinguished from full-resolution results.
8. **Post-evaluation failures:** Low quality and no savings preserve their measured evidence and become terminal evaluated outcomes.
9. **SSIM inputs:** Normalized decoded inputs, RGB parameters, package-decoder reopening, heatmaps, and alpha-handling expectations are specified.
10. **P0 difference storage:** Cropped target-space patches plus lossless masks are the default, not full-canvas changed images.
11. **Automatic splitting:** `split_recommended` is advisory in P0.
12. **Document names:** The PRD repository tree now uses the existing `PhotoFold_Developer_PRD.md` and `PhotoFold_Demo_Script.md` filenames.
13. **Human evidence:** Gate 1 now requires the self-contained HTML experiment report defined by this plan.

## 14. Final go/no-go sequence

```text
Real dataset and measurement contract ready?
  no  → remain at Gate 0
  yes → run Gate 1 rate-distortion experiment

Every accepted frame reconstructed from package only,
quality threshold passed, archive bytes real,
and package smaller than original?
  no  → tune/narrow; do not build full UI
  yes → does it beat independent WebP at matched quality?
          no  → do not claim relational proof; tune or reconsider hypothesis
          yes → harden deterministic pipeline and add API

Three curated sets reliable through API?
  no  → harden/reduce supported envelope
  yes → build complete web flow

Deterministic web demo reliable with time remaining?
  no  → harden and rehearse
  yes → optionally add GPT-5.6, animation, and AVIF experiment
```

The first experiment therefore determines whether the project should proceed as designed. That is the intended behavior of the plan, not a delay to product work.
