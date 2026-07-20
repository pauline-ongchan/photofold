# Phase 1B Multi-Dataset Validation Execution Plan

## Summary and fixed assumptions

Phase 1B will extend the deterministic CLI experiment across exactly three canonical datasets, reuse one frozen Gate 1 treatment, add per-frame SSIM/PSNR quality-matched WebP controls, and generate auditable machine results plus one offline report. No API, frontend, upload, job, GPT, cloud, or Phase 2 work is included.

Repository inspection found:

- Canonical `data/real-bursts/` does not yet exist; supplied files are under `data/phase 1/real-bursts/`.
- `static-handheld`: 15 JPEGs, normalized 3024×4032, 46,659,071 bytes.
- `moving-subject`: use 13 JPEGs from `IMG_8419.jpg` through `IMG_8431.jpg`, normalized 3024×4032, 25,331,644 bytes. Exclude incompatible 4284×5712 `IMG_8418.jpg`.
- `camera-motion-or-lighting`: use 14 JPEGs, normalized 4284×5712, 26,301,637 bytes. Exclude incompatible 3024×4032 `IMG_8480.jpg`.
- Canonical files will be byte-identical copies; the supplied staging files remain untouched.
- Source photos are assumed owner-authorized but local-only because they retain EXIF/GPS metadata. Commit manifests and placement documentation, not the approximately 98 MB of image bytes.
- Manifest order is ascending capture filename order. The benchmark never searches the staging path.
- Any rejected canonical frame makes that dataset non-comparable and failed; Phase 1B will not improve savings by silently dropping difficult frames.

## Implementation changes

### 1. Dataset validation

- Add strict Phase 1B manifest models covering ID, title, scenario, provenance/consent, capture notes, limitations, expected count/dimensions, and ordered file paths/checksums.
- Add an explicit preparation command that copies only manifest-listed files from the staging location to `data/real-bursts/`, refuses overwrites, and verifies byte-identical SHA-256 values. This is separate from the benchmark.
- Validate the exact three directory names and unique IDs as a collection. For every file, check traversal safety, uniqueness, regular-file status, checksum format/value, supported decoded format, EXIF transpose, normalized dimensions, and exact stat bytes.
- Detect undeclared JPEG/PNG/WebP files, accumulate per-file dispositions, and never repair an input.
- Snapshot source checksums immediately before processing and verify them again afterward. Any mutation fails the dataset and Phase 1B evidence.
- Preserve Gate 0 compatibility: `data/demo/hdrplus-static` continues passing its existing validator and health path.

### 2. Frozen PhotoFold treatment and benchmark architecture

- Extract the reusable selected-treatment path from Gate 1 into a small shared treatment module: load the committed `configs/gate1.yaml`, select the same parameters, align, build and close the archive, verify it, and reconstruct via the public decoder.
- Keep Gate 1’s sweep/report behavior unchanged; Phase 1B disables the PhotoFold parameter sweep and applies the same selected treatment to all datasets.
- Make alignment failures structured per-frame dispositions instead of uncaught lookup errors. All canonical frames must align for a dataset to remain comparable.
- Run datasets sequentially in this fixed order: `static-handheld`, `moving-subject`, `camera-motion-or-lighting`.
- Measure stages with `time.perf_counter_ns`: PhotoFold encode through archive close, verification, per-frame and total reconstruction, fixed control encode/decode, matched sweep encode/decode, and total dataset wall time. Report milliseconds and the cold-process/no-deliberate-warm-up policy.
- Record configuration checksum and parameters, manifest/source checksums, Python/package/Pillow-WebP versions, OS/machine information, clock source, timestamp, and result schema version.
- Keep all output under `artifacts/phase1b/`; never write into Gate 1 artifacts.

### 3. WebP baselines and quality metrics

- Add RGB PSNR beside the existing SSIM helper. Represent infinity as `{ "value_db": null, "is_infinite": true }`; finite values use a numeric `value_db`.
- Run the fixed control independently at WebP q70, method 6, exact true, reopening every payload before SSIM/PSNR measurement.
- Run a separate exhaustive matched sweep for q1–q100, ascending, with the same quality for every frame at a candidate point. No interpolation, early exit, or binary search.
- A point qualifies only when every frame satisfies:
  - `candidate_ssim + 1e-6 >= photofold_ssim`
  - `candidate_psnr_db + 1e-4 >= photofold_psnr_db`
- Select with the deterministic key `(total_bytes, quality, per_frame_byte_vector)`. If nothing qualifies, serialize `unmatched`; relational fields are null and aggregate evidence is incomplete.
- Save all 100 points with per-frame bytes, SSIM, and PSNR. Print SSIM to at least nine decimal places and PSNR to six.
- Record Gate 1’s 0.85/0.82 thresholds for context only; they are dataset-specific and will not be presented as universal Phase 1B quality gates. Per-frame matching plus human visual review governs Phase 1B quality.

### 4. Per-dataset and aggregate results

Each `benchmark.json` will contain:

- Validation inventory and dispositions; source/config/manifest integrity identifiers.
- Original, fixed-WebP, matched-WebP, and PhotoFold bytes with signed byte and percentage differences.
- Per-frame original/fixed/matched bytes; reconstruction status/dimensions; PhotoFold and baseline SSIM/PSNR.
- Mean and minimum SSIM/PSNR for all treatments.
- Reference/alignment evidence, timing breakdowns, artifact references, and integrity checks.
- Package checksum, deterministic member listing with role/stored/uncompressed bytes/checksum, and payload/container-overhead reconciliation.

`aggregate.json` will calculate directly from the three dataset results:

- Median signed matched-baseline saving.
- Weighted mean from summed matched and PhotoFold bytes, never the average of percentages.
- Best/worst dataset with deterministic ID tie-breaking.
- Strict win, loss, and exact-byte-tie counts.
- Total accepted/reconstructed frames and summed original/fixed/matched/PhotoFold bytes.
- Evidence validity and the ordered recommendation rules from the specification: pivot vetoes first, then continue at ≥10% median and two wins, investigate at 5–10%, otherwise pivot.
- A matched-baseline failure makes aggregate relational evidence incomplete. A human complexity veto requires written evidence.

### 5. Offline HTML report and review

Generate `artifacts/phase1b/report.html` with:

- Phase validity, recommendation, failed criteria, exact thresholds, environment/config/source identifiers.
- Aggregate byte totals, median, weighted mean, best/worst, wins/losses/ties, and decision-rule audit.
- A methodology section explaining fixed q70, exhaustive q1–q100 matching, per-frame tolerances, PSNR infinity handling, and timing limitations.
- One section per dataset with validation/dispositions, storage and quality tables, timing, alignment evidence, integrity checks, fixed/matched controls, and the full curve in a collapsible table or inline SVG.
- Embedded original/reconstruction/heatmap previews for every frame; embedded masks and alignment overlays in collapsible diagnostics.
- Complete package listings and overhead reconciliation.
- Human-review status and notes, including deliberate inspection of the lowest-SSIM and lowest-PSNR frames.

The verifier will reopen the JSON and archives, recompute totals and recommendation, decode every embedded data URL, reject external dependencies/placeholders, and verify dataset/frame/member counts. Human review starts as pending; a validated review-record command binds pass/fail notes and any complexity veto to the current source/config/reconstruction hashes, then regenerates and re-verifies the final report.

## Commands, files, and tests

### Validation commands

Fast developer validation:

```bash
make verify-phase1b-fast
```

This runs strict dataset validation/checksums, Ruff, Phase 1B unit/fixture integration tests, schema drift checks, and report-verifier fixtures without native-resolution compression.

Authoritative full validation:

```bash
make verify-gate0
make verify-gate1
make verify-phase1b
```

`verify-phase1b` processes all three native-resolution datasets sequentially, executes both controls, verifies pre/post source checksums and every package, writes aggregate/report artifacts, and runs structural consistency verification.

Human review:

```bash
make human-verify-phase1b
open artifacts/phase1b/report.html
```

The target prints the exact validated review-record command. Recording the review regenerates the recommendation/report without rerunning compression.

### Expected tracked changes

- Dataset metadata: `.gitignore`, `data/real-bursts/README.md`, and three `manifest.json` files.
- Dataset/runtime foundation: `photofold/dataset.py`, `photofold/cli.py`, and a preparation script.
- Shared Gate 1 extraction: `gate1/treatment.py`, with focused compatibility edits to `gate1/benchmark.py`, `gate1/alignment.py`, and `gate1/images.py`.
- New Phase 1B package: `phase1b/models.py`, `baseline.py`, `benchmark.py`, and `report.py`.
- Generated contracts: Phase 1B manifest, dataset-result, aggregate-result, and human-review JSON schemas; extend contract generation/check scripts accordingly.
- Tests: dedicated Phase 1B validation, baseline, aggregate/recommendation, report, and orchestration tests.
- Commands/docs: `Makefile`, root `README.md`, and the Phase 1B implementation/completion section in `docs/IMPLEMENTATION_PLAN.md`.

Expected unchanged interfaces include FastAPI/OpenAPI, generated TypeScript API types, the health-only frontend, package schema/version, `configs/gate1.yaml`, and all Phase 2 surfaces. Canonical photo bytes and `artifacts/phase1b/**` remain local/ignored.

### Required tests

- Missing/invalid manifest, duplicate/traversal path, undeclared image, checksum mismatch, unsupported/corrupt decode, dimension mismatch, duplicate dataset ID, and simulated source mutation.
- Exact q1–q100 coverage, separate q70 control, dual-metric per-frame qualification, tolerances, deterministic tie-breaking, unmatched result, and infinite PSNR serialization.
- Median/weighted formulas, signed losses/ties, incomplete evidence, 5%/10% boundaries, two-loss veto, visual-review veto, and complexity veto.
- Closed-package reconstruction/dimensions, package listing and overhead reconciliation, and unchanged Gate 1 output behavior.
- Missing dataset sections/images, invalid data URLs, external assets, inconsistent totals, absent members, stale human review, and incorrect recommendation in report verification.
- Assert the API still exposes only `/v1/health`.

## Risks, checkpoints, and acceptance

### Risks and fallbacks

- Native-resolution workloads may take hours or exceed memory. Default remains sequential and authoritative; if memory fails, stream full-resolution frames while retaining only analysis copies and current-frame reconstruction. Any such refactor applies uniformly and reruns Gate 1.
- Alignment, patch-count, or quality failures are experiment findings—not permission for dataset-specific tuning. Only correctness fixes may be applied uniformly; material changes require rerunning Gate 1 and all three datasets.
- Interrupted 100-point sweeps may checkpoint by quality, keyed to manifest/config/runtime checksums, but the authoritative target rejects stale or incomplete curves.
- Large PNG evidence and embedded reports may consume substantial disk. Use bounded WebP report previews while retaining full-resolution PNG inspection artifacts outside the archive.
- Missing source authorization blocks dataset-manifest acceptance. The fallback is local-only placement with non-redistributable owner authorization, not metadata stripping or source rewriting.
- Replacement same-dimension frames may be substituted only by updating their manifests/checksums and rerunning the complete experiment; the two current outliers are never normalized in place.

### Checkpoints

1. Create `codex/phase-1b-validation` from the approved spec baseline, preserve existing user changes, snapshot source hashes, and run Gate 0/Gate 1. Any failure blocks implementation.
2. Commit canonical manifests/preparation/strict validation; pass observed counts, dimensions, totals, and source immutability checks.
3. Commit schemas, PSNR, fixed control, and exhaustive matched baseline; pass fast negative/boundary tests.
4. Commit shared treatment and Phase 1B orchestration; run one untuned dataset vertically and rerun Gate 1 to prove compatibility.
5. Run all three datasets, verify packages and complete curves, then generate and structurally verify aggregate/report evidence.
6. Complete human review, bind notes to the generated evidence, and confirm the recommendation follows the specification exactly.
7. Run Gate 0, Gate 1, fast Phase 1B, and full Phase 1B again; update README/implementation completion evidence, push the feature branch, and open a draft PR against `main`. Stop without starting Phase 2 or merging.

Phase 1B is accepted when earlier gates remain green; all three canonical datasets validate without source mutation; all canonical frames have explicit dispositions; every accepted frame reconstructs from its closed archive at the expected dimensions; both WebP controls are complete and auditable; all storage, quality, timing, and package values reconcile to real artifacts; aggregate formulas and recommendation are exact; the offline report passes structural and human review; and no API/product/Phase 2 work appears.
