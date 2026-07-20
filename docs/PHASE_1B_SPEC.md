# PhotoFold Phase 1B Specification

**Status:** Implemented and accepted for the hackathon MVP; final recommendation `CONTINUE COMPRESSION-FIRST`
**Phase:** Phase 1B — multi-dataset validation of the compression hypothesis
**Authority:** `docs/PhotoFold_Developer_PRD.md`, `docs/IMPLEMENTATION_PLAN.md`, and `docs/TECHNICAL_CONTRACTS.md`
**Implementation boundary:** Deterministic CLI benchmark and offline evidence only

## 1. Purpose

Phase 1B determines whether the Gate 1 PhotoFold compression result generalizes beyond the original `hdrplus-static` experiment. It runs the existing deterministic PhotoFold pipeline against three real burst categories, compares each result with two independent-WebP controls, verifies package-only reconstruction, and produces enough generated and visual evidence to choose whether to continue, investigate, or pivot.

This document is an implementation specification. Creating this document does not authorize or constitute Phase 1B implementation.

## 2. Scope boundary

Phase 1B may add only the code, configuration, tests, commands, dataset metadata, generated schemas, documentation, and offline artifacts required for the three-dataset compression experiment.

Phase 1B must not add:

- Phase 2 processing APIs or product routes;
- a product UI, upload flow, background jobs, queues, or databases;
- GPT or other model integration;
- authentication, billing, cloud storage, or cloud infrastructure;
- multiple curated scenarios beyond the three datasets named here;
- codec, transform, metric, package, or error-contract changes that contradict `docs/TECHNICAL_CONTRACTS.md` without a separately documented and measured justification.

The deterministic processor must continue to start and run without network access or model credentials. WebP remains the required codec, and the doctor check must fail when Pillow lacks WebP support.

## 3. Required pre-implementation review

Before changing implementation code, the implementer must:

1. Read `docs/PhotoFold_Developer_PRD.md` in full.
2. Read `docs/IMPLEMENTATION_PLAN.md` in full.
3. Read `docs/TECHNICAL_CONTRACTS.md` and preserve its decisions.
4. Review the completed Gate 0 dataset, health, doctor, OpenAPI, generated-contract, frontend-health, and validation work.
5. Review the completed Gate 1 alignment, package writer, package validator, public decoder, benchmark, WebP control sweep, metrics, reports, tests, configuration, and commands.
6. Run `make verify-gate0` and `make verify-gate1` and record their results before Phase 1B implementation begins.
7. Inspect and validate the three input datasets without modifying any original image bytes or image metadata.

Any pre-existing Gate 0 or Gate 1 failure is a blocker. Phase 1B must not hide, weaken, or bypass an earlier gate.

## 4. Datasets and source integrity

### 4.1 Canonical dataset locations

The Phase 1B implementation must consume exactly these three dataset directories:

```text
data/real-bursts/
├── static-handheld/
├── moving-subject/
└── camera-motion-or-lighting/
```

Repository observation at specification time: the supplied images are currently present under `data/phase 1/real-bursts/`, and no `manifest.json` files are present in the three dataset directories. Before implementation, the path discrepancy must be resolved explicitly and non-destructively, and each canonical dataset must receive a manifest. The benchmark must not silently search alternate paths.

### 4.2 Immutable source rule

Original image files are read-only experiment inputs. Phase 1B must not rewrite, rename, resize, re-encode, rotate, strip metadata from, or otherwise modify them. Normalized decoded arrays and all generated derivatives must live under the Phase 1B artifact directory or an isolated temporary directory.

The implementation must verify source SHA-256 values immediately before and after a benchmark run. A changed checksum fails the run.

### 4.3 Dataset manifest

Each dataset directory must contain a version-controlled `manifest.json` that records at least:

- stable dataset ID and title;
- scenario category;
- provenance and consent/license information;
- capture notes and known limitations;
- expected frame count;
- expected normalized display-oriented width and height;
- an explicit ordered `files` array;
- for every file: relative path and lowercase SHA-256 digest.

The manifest's file order is the normative frame order. Directory iteration order, modification time, EXIF time, and lexicographic discovery must not determine processing order. Filenames must be unique within a dataset, and manifest paths must be relative, traversal-safe, and resolve inside that dataset directory.

### 4.4 Validation requirements

Before any encoding, validation must prove for each dataset that:

- the directory and manifest exist;
- the manifest is valid and its declared dataset ID is unique;
- the manifest frame count equals the number of ordered entries and is between 5 and 20 inclusive;
- every declared file exists and is a regular file;
- no undeclared supported image file is present;
- each file's SHA-256 equals the manifest value;
- each file decodes successfully through Pillow;
- the decoded format is JPEG, PNG, or WebP;
- EXIF orientation normalization succeeds;
- normalized dimensions are positive and match the manifest;
- all frames in the dataset have compatible normalized dimensions;
- ordering is exactly the manifest order;
- byte totals equal the sum of `stat()` results for the original files.

Validation must emit a machine-readable result containing per-file order, filename, format, byte count, checksum, normalized dimensions, and disposition. Any failure stops that dataset before processing and contributes a visible failed Phase 1B verdict. Validation must never repair an input automatically.

## 5. Reproducibility and experiment controls

### 5.1 Frozen PhotoFold treatment

All three datasets must be processed sequentially with the current Gate 1 PhotoFold pipeline and the same committed configuration. Phase 1B must not tune PhotoFold parameters separately per dataset. The run result must record:

- configuration path and SHA-256;
- all selected parameters;
- Python and dependency versions;
- Pillow WebP capability and encoder version information available at runtime;
- platform and processor information needed to interpret timings;
- dataset manifest and source checksums;
- run timestamp and benchmark schema version.

Phase 1B may fix correctness defects exposed by the datasets, but any such fix must be applied uniformly, covered by tests, and rerun against Gate 1. A material algorithm or parameter change requires rerunning all three Phase 1B datasets and the original Gate 1 dataset.

### 5.2 Fixed-quality independent-WebP control

The fixed-quality control independently encodes every normalized RGB frame with the existing Gate 1 WebP helper at quality 70:

```text
format = WEBP
quality = 70
method = 6
exact = true
```

Each encoded frame must be reopened and measured against its own normalized original. The fixed-control size is the sum of the exact encoded WebP payload lengths. It excludes report assets and filesystem allocation overhead. Per-frame bytes, SSIM, and PSNR must be retained.

### 5.3 Quality-matched independent-WebP baseline

The quality-matched baseline must use the same independent-frame encoder settings as the fixed control and exhaustively test every integer WebP quality from 1 through 100 inclusive. All frames in one candidate point use the same quality value. No interpolation, early exit, binary search, or extrapolation is allowed.

For each candidate quality `q`:

1. Independently encode every normalized original frame.
2. Reopen every encoded payload through the same decoded-RGB path used for quality measurement.
3. Calculate per-frame SSIM and PSNR.
4. Sum the exact payload byte lengths.
5. Calculate mean and minimum SSIM and PSNR.

A candidate qualifies only if, for every accepted frame `i`:

```text
candidate_ssim[i] + 1e-6 >= photofold_ssim[i]
candidate_psnr_db[i] + 1e-4 >= photofold_psnr_db[i]
```

These tolerances exist only for floating-point comparison; they are not quality concessions. The report must print enough precision to audit the comparison. A qualifying candidate must consequently meet or exceed PhotoFold's mean and minimum values within the same tolerances.

The matched baseline is the qualifying candidate with the smallest `total_bytes`. Ties are resolved by lower quality value, then by the lexicographically ordered per-frame byte vector. If no quality from 1 through 100 qualifies, the result is `unmatched`; the implementation must not substitute a lower-quality point, and the affected dataset cannot support a continue recommendation.

The complete 100-point curve and the matching decision must be saved. Matching is performed independently for each dataset only after PhotoFold's final package has been closed, reopened, and measured.

## 6. PhotoFold processing and verification

For every dataset, the benchmark must:

1. Retain an explicit accepted or rejected disposition and reason for every input frame.
2. Run the current automatic reference selection and alignment pipeline.
3. Build a closed `.photofold` archive using only accepted frames.
4. Validate safe paths, schema, inventory, member byte counts, member SHA-256 values, required codecs, transforms, dimensions, and referenced assets.
5. Start package verification from the closed archive, not from in-memory encoder intermediates.
6. Reconstruct every accepted frame using the public package decoder with only the archive and frame index available.
7. Verify that every reconstruction has the expected normalized dimensions.
8. Verify that the accepted count equals the reconstructed count and is at least five.
9. Generate standard reconstruction images and difference heatmaps outside the archive for inspection.
10. Re-stat and checksum the final package after it is closed.

No original file may be copied into the `.photofold` package. Report previews, heatmaps, logs, and other inspection outputs must not count toward package size.

## 7. Measurement definitions

All values must be derived from real source or generated artifacts. No result, verdict, timing, file size, quality score, or package listing may be hard-coded.

### 7.1 Quality

SSIM uses the existing RGB contract:

```text
structural_similarity(original, decoded, data_range=255, channel_axis=2)
```

PSNR uses all normalized RGB samples:

```text
mse = mean((original.astype(float64) - decoded.astype(float64)) ** 2)
psnr_db = 10 * log10((255 ** 2) / mse)
```

If `mse == 0`, PSNR is positive infinity and must be serialized using an explicit schema-safe representation rather than non-standard JSON. SSIM and PSNR are calculated for every PhotoFold reconstruction and every frame at every independent-WebP point. Each dataset reports per-frame, arithmetic mean, and minimum values for both metrics.

### 7.2 Storage

For each dataset:

```text
original_total_bytes = sum(stat(original source file))
fixed_webp_total_bytes = sum(length(fixed-quality encoded payload))
matched_webp_total_bytes = sum(length(selected matched encoded payload))
photofold_package_bytes = stat(closed .photofold archive)

savings_vs_originals_percent =
  (original_total_bytes - photofold_package_bytes)
  / original_total_bytes * 100

relational_savings_vs_fixed_percent =
  (fixed_webp_total_bytes - photofold_package_bytes)
  / fixed_webp_total_bytes * 100

relational_savings_vs_matched_percent =
  (matched_webp_total_bytes - photofold_package_bytes)
  / matched_webp_total_bytes * 100
```

Signed byte differences must also be reported. Negative savings are losses and must remain negative rather than being clamped to zero.

### 7.3 Package overhead and listing

For each package:

```text
member_payload_bytes = sum(uncompressed member payload sizes)
container_overhead_bytes = photofold_package_bytes - member_payload_bytes
container_overhead_percent = container_overhead_bytes / photofold_package_bytes * 100
```

The report and machine result must list every archive member in deterministic path order with its stored size, uncompressed size, checksum, and role. Member totals must reconcile with the archive inventory and final filesystem size.

### 7.4 Timing

Use a monotonic high-resolution clock around explicitly named stages. Run datasets sequentially in manifest order and controls sequentially by ascending quality. Record at least:

- PhotoFold encoding time, from entry into reference/alignment processing through final archive close;
- package verification time;
- total reconstruction time for all accepted frames from the closed archive;
- per-frame reconstruction time;
- fixed-control encoding and decode/measurement time;
- matched-baseline sweep encoding and decode/measurement time;
- total dataset wall time.

Timings are wall-clock observations, not deterministic byte-for-byte results and not primary correctness gates. Do not include report rendering in PhotoFold encoding or reconstruction time. Record units in milliseconds, clock source, warm/cold-run policy, and runtime environment. The report must avoid implying performance comparability across different machines.

## 8. Per-dataset result contract

Each dataset result must contain at least:

- dataset identity, scenario, manifest checksum, and ordered source inventory;
- validation status and all frame dispositions;
- original total bytes;
- fixed-quality independent-WebP total bytes and quality settings;
- matched independent-WebP total bytes, selected quality, match status, tolerances, and full curve reference;
- PhotoFold package bytes and checksum;
- signed bytes and percentage saved versus originals;
- signed incremental bytes and percentage saved versus fixed WebP;
- signed relational bytes and percentage saved versus matched WebP;
- reference-frame index and recorded alignment evidence;
- per-frame original bytes, baseline bytes, reconstruction status, dimensions, SSIM, and PSNR;
- mean and minimum SSIM and PSNR for PhotoFold and both selected baselines;
- encoding, verification, reconstruction, baseline, and total timings;
- package overhead and complete file listing;
- paths or embedded references for originals, reconstructions, heatmaps, masks, and alignment overlays;
- machine-evaluated pass/fail checks and human visual-review status.

## 9. Aggregate result contract

The primary relational measure is each dataset's signed `relational_savings_vs_matched_percent`. Across the three datasets, report:

- unweighted median;
- weighted mean, calculated as `(sum(matched_webp_total_bytes) - sum(photofold_package_bytes)) / sum(matched_webp_total_bytes) * 100`;
- best dataset and value, using the maximum signed relational saving;
- worst dataset and value, using the minimum signed relational saving;
- win count, where a win means `photofold_package_bytes < matched_webp_total_bytes` at a qualifying matched quality;
- loss/tie count, with exact byte ties reported as ties;
- total accepted and reconstructed frame counts;
- aggregate original, fixed-control, matched-control, and PhotoFold bytes.

Do not average per-dataset percentages to produce the weighted mean. If any dataset lacks a qualifying matched baseline, aggregate relational evidence is incomplete and cannot yield `CONTINUE COMPRESSION-FIRST`.

## 10. Self-contained HTML report

Generate one report at:

```text
artifacts/phase1b/report.html
```

It must open with networking disabled and contain no external images, stylesheets, scripts, fonts, or service dependencies. Images must be embedded as data URLs or otherwise fully contained in the HTML.

The report must visibly include:

- a top-level Phase 1B pass/fail state and recommendation;
- the exact decision thresholds and quality-matching algorithm, including tolerances;
- environment, configuration, and source-integrity identifiers;
- one dataset section for each of the three required scenarios;
- original and reconstructed images side by side for every accepted frame;
- a difference heatmap for every accepted frame;
- clear rejected-frame evidence and reasons, if any;
- dataset-by-dataset storage, quality, timing, and integrity tables;
- fixed and quality-matched WebP comparison tables;
- aggregate median, weighted mean, best, worst, and win-count results;
- complete package listings and overhead reconciliation;
- visible pass/fail indicators for validation, reconstruction, dimensions, package integrity, quality matching, source savings, both baseline comparisons, and visual review;
- an explicit `CONTINUE COMPRESSION-FIRST`, `INVESTIGATE`, or `PIVOT` recommendation with the exact criteria that passed or failed.

The report verifier must reject missing dataset sections, missing or broken embedded images, external dependencies, blank/hard-coded placeholders, inconsistent totals, absent package members, or a recommendation inconsistent with the machine-readable results.

## 11. Decision criteria

Quality and reconstruction pass only when every accepted frame reconstructs at the expected dimensions, all package integrity checks pass, a qualifying matched baseline exists for every dataset, and human review records no visible quality regression in originals versus reconstructions and heatmaps.

Apply the following rules in order:

1. **PIVOT** if any reconstruction or package-integrity requirement fails; human review identifies any visible quality regression; the median matched-baseline relational saving is below 5%; PhotoFold loses on at least two datasets; or the recorded reviewer determination says implementation/runtime complexity is disproportionate to the storage benefit and states the evidence.
2. **CONTINUE COMPRESSION-FIRST** when the median matched-baseline relational saving is at least 10%, PhotoFold wins on at least two of three datasets, every accepted frame reconstructs, every package and quality check passes, and human review finds no visible quality regression.
3. **INVESTIGATE** when the median matched-baseline relational saving is at least 5% but below 10%, while reconstruction, integrity, matched-quality comparison, and visual quality all pass and no pivot veto applies.
4. **PIVOT** for any remaining combination that does not satisfy the complete continue or investigate criteria.

The recommendation is an experiment result, never a configuration constant. Runtime/complexity disproportionality is a documented human judgment because this phase does not establish a universal hardware threshold; the report must identify the measured timings and specific complexity concern when that veto is used.

## 12. Artifacts and separation from Gate 1

All Phase 1B generated output must remain under `artifacts/phase1b/`. It must not overwrite, reuse as writable workspace, or mix with `artifacts/gate1/`.

Required layout:

```text
artifacts/phase1b/
├── report.html
├── aggregate.json
├── report-verification.json
├── static-handheld/
│   ├── benchmark.json
│   ├── dataset-validation.json
│   ├── moment.photofold
│   ├── package-verification.json
│   ├── package-inventory.json
│   ├── independent-webp-curve.json
│   ├── reconstructions/
│   ├── heatmaps/
│   ├── masks/
│   └── alignment-overlays/
├── moving-subject/
│   └── ...
└── camera-motion-or-lighting/
    └── ...
```

Artifacts remain generated evidence and must not be used as hard-coded application inputs.

## 13. Implementation deliverables

Phase 1B implementation must provide:

- manifests and immutable-source validation for all three datasets;
- deterministic orchestration that runs the existing pipeline across all three datasets;
- PSNR calculation alongside the existing SSIM calculation;
- fixed-quality and exact matched-quality independent-WebP comparisons;
- package-only reconstruction and verification of every accepted frame;
- timing and package-overhead measurement;
- per-dataset and aggregate machine-readable results;
- the self-contained report and structural report verifier;
- focused unit and integration tests, including negative validation and recommendation-boundary cases;
- isolated Phase 1B commands and artifacts;
- a Phase 1B section in `docs/IMPLEMENTATION_PLAN.md` with the final commands, exit criteria, completion record, and complete human-verification procedure;
- corresponding command documentation in the root `README.md` after implementation.

FastAPI/Pydantic remains the owner of any API contracts. If Phase 1B changes a generated contract, run `npm run contracts:generate` and keep generated TypeScript synchronized. Phase 1B should not add product API endpoints.

## 14. Required validation commands

Implementation must add stable Make targets so the complete validation sequence is:

```bash
make verify-gate0
make verify-gate1
make verify-phase1b
make human-verify-phase1b
```

`make verify-phase1b` must validate all three datasets, run all Phase 1B unit and integration tests, process all three datasets, verify every package, verify source immutability, generate aggregate results and the HTML report, and structurally verify that report. It must exit nonzero for a validation, reconstruction, integrity, accounting, report-consistency, or acceptance failure.

`make human-verify-phase1b` must run the automated Phase 1B verification, print the exact report path, and print the manual open command. It must not start the Phase 2 service or product UI.

## 15. Human verification

From the repository root, run:

```bash
make human-verify-phase1b
open artifacts/phase1b/report.html
```

Open exactly `artifacts/phase1b/report.html` with networking disabled. A reviewer must verify:

- all three named dataset sections are present;
- every input frame has an explicit disposition;
- every accepted frame has an original, reconstruction, and heatmap with no broken image;
- original and reconstructed dimensions match;
- no visible seam, subject damage, color shift, missing content, or other quality regression appears at normal size or full-resolution zoom;
- the lowest-SSIM and lowest-PSNR frames receive deliberate visual inspection;
- original, fixed-WebP, matched-WebP, and PhotoFold byte totals reconcile with their detailed rows;
- the matching quality and tolerances are visible and the selected point is the smallest qualifying encoded total;
- mean and minimum metrics match the visible per-frame values;
- all accepted frames reconstruct and all integrity checks pass;
- each package listing is complete and overhead totals reconcile;
- aggregate median, weighted mean, best, worst, and win count are present and correctly signed;
- the displayed recommendation follows Section 11 exactly;
- the report opens and remains complete without a server or network connection.

The reviewer must record pass/fail and notes in the generated verification evidence. Source-code inspection is not a substitute for this review.

## 16. Completion report requirements

At Phase 1B completion, report:

- every file changed;
- exact commands run and their exit results;
- validation results for each dataset, including frame count, dimensions, total bytes, and checksum status;
- original, fixed-control, matched-control, and PhotoFold sizes for each dataset;
- per-dataset savings, quality aggregates, timing, package overhead, and reconstruction status;
- aggregate median, weighted mean, best, worst, and win/loss/tie results;
- an explicit comparison with every acceptance criterion;
- the generated continue/investigate/pivot recommendation and rationale;
- known limitations and any runtime/complexity concern;
- the exact manual inspection command and report file;
- anything requiring manual review.

Stop after Phase 1B. Do not begin Phase 2.

## 17. Definition of done

Phase 1B is done only when:

- Gate 0 and Gate 1 pass unchanged;
- all three canonical datasets pass immutable-source validation;
- the same committed PhotoFold treatment processes all three datasets;
- every accepted frame reconstructs from its closed package and passes integrity and dimension checks;
- real artifacts provide every storage, quality, timing, and inventory value;
- fixed-quality and per-frame quality-matched WebP baselines are complete and auditable;
- the aggregate result and recommendation follow this specification;
- the self-contained report passes structural verification and human visual review;
- Phase 1B output is isolated from Gate 1 output;
- implementation-plan and README human-verification instructions are current;
- no Phase 2, product UI, upload, job, or GPT work has started.
