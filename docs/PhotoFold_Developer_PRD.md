# PhotoFold Developer Product Requirements Document

**Status:** Hackathon MVP  
**Primary owner:** Project team  
**Implementation target:** Web prototype  
**Source document:** PhotoFold Product Requirements Document  
**Tagline:** Keep every shot. Store the scene once.

---

## 1. Product Summary

PhotoFold reduces the storage used by groups of visually similar photos without deleting any frame.

For a set of photos from the same moment, PhotoFold stores:

1. One shared reference scene
2. Alignment data for each frame
3. Frame-specific changed regions
4. Optional residual corrections required for reconstruction
5. A manifest describing how to rebuild every frame

Each uploaded photo must remain individually viewable, reconstructable, and exportable as a standard image.

PhotoFold is not a duplicate cleaner, photo selector, burst picker, cloud gallery, or ordinary single-image compressor. Its core distinction is that it compresses the relationship between similar images.

---

## 2. MVP Objective

Prove the following technical hypothesis:

> A suitable collection of similar photos can be represented as one shared scene plus frame-specific differences, while preserving every frame as an individually reconstructable image and reducing the total encoded size.

The MVP is successful when one complete workflow can:

1. Accept a suitable set of similar photos
2. Validate that the photos belong to the same moment
3. Align the photos to a shared reference
4. Generate a shared-base-plus-differences package
5. Reconstruct every uploaded frame
6. Measure the actual package size
7. Compare each reconstruction with its original
8. Export a reconstructed frame as a standard image

---

## 3. Success Criteria

### Required technical outcomes

- Process at least 5 photos in one moment
- Reconstruct 100% of accepted frames
- Preserve the display-oriented dimensions produced after EXIF normalization for each reconstructed frame
- Calculate storage using actual encoded files, including every asset required for reconstruction
- Report per-frame and aggregate reconstruction-quality metrics
- Allow visual original-versus-reconstruction comparison
- Reject or warn on unsuitable photo sets
- Export at least one reconstructed frame successfully
- Download the reconstructable `.photofold` package

### Target outcomes

These are targets, not guaranteed claims:

- At least 30% storage reduction on at least one curated, suitable photo set
- High visual similarity between originals and reconstructions
- A viewer understands the transformation:

```text
multiple similar photos
→ one shared scene plus differences
→ smaller package
→ every photo remains available
```

### Storage calculation

```text
storage_reduction_percent =
  (original_total_bytes - package_total_bytes)
  / original_total_bytes
  * 100
```

`original_total_bytes` is the sum of the exact uploaded source-file byte counts before normalization or transcoding.

`package_total_bytes` is the file-system byte size of the final downloadable `.photofold` archive. It therefore includes ZIP/container overhead and every file placed in the artifact, including the base image, transforms, masks, changed-region assets, residuals, manifest, and metadata. Original source images and generated inspection artifacts that are not inside the archive must not be included.

The final archive size must be measured after the artifact is closed. An internal `metrics.json` must not claim the final archive size because embedding that value would change the archive being measured. The processor records the final size in the external run/API result; a consumer of a downloaded package can independently measure the archive itself.

The product displays the comparison with the uploaded originals. Gate 1 must additionally compare PhotoFold with independently encoded WebP versions of every frame across a matched-quality rate-distortion sweep. PhotoFold may claim that relationship compression caused a saving only when the package is smaller than the independent-WebP control at equal or better mean and minimum quality. If it only beats the uploaded originals, the result may be described as a storage reduction but not as proof of the shared-scene hypothesis.

---

## 4. Primary User and Use Case

### Primary user

A phone user who:

- Takes several photos of the same moment
- Wants to preserve different poses and expressions
- Hesitates to delete alternatives
- Regularly runs low on phone or cloud storage

### Primary MVP scenario

The user uploads 5 to 20 photos captured within a short period from approximately the same position.

The set may contain:

- The same location and people
- Small pose or expression changes
- Minor camera movement
- Slight lighting differences
- One unique person or object entering a frame

PhotoFold evaluates the set, creates a compressed bundle, reconstructs every frame, and displays real storage and quality results.

---

## 5. Scope

### P0: Required for the hackathon MVP

- Upload 5 to 20 photos
- Support JPEG, PNG, and WebP
- Reject HEIC with a clear unsupported-format message unless the optional P2 support has been completed and verified
- Show thumbnail, filename, original size, and dimensions
- Remove files before processing
- Validate whether the photos are suitable for folding
- Select a reference frame automatically
- Align every accepted frame to the reference
- Calculate shared and changed visual regions
- Encode one shared base plus frame-specific differences
- Reconstruct every frame
- Calculate original total size and PhotoFold package size
- Calculate at least one image-quality metric
- Display original-versus-reconstruction comparison
- Display a difference heatmap or equivalent visual difference view
- Export reconstructed frames
- Download the `.photofold` package
- Validate the deterministic pipeline on three curated demo datasets
- Reject or warn when folding is unsafe or ineffective

### P1: Strongly preferred

- GPT-5.6 semantic analysis
- Human-readable explanation of meaningful changes
- Visualization of shared versus changing regions
- Automatic outlier detection
- Animated alignment and folding sequence
- Semantic mode compared with pixel-only mode

### P2: Optional polish

- Manual reference-frame selection
- Multiple quality modes
- Person or subject segmentation
- Moment-title generation
- Multiple reference frames
- Mobile-specific layout polish
- HEIC support
- Advanced optical-flow refinement

### Explicit non-goals

- Replacing the native phone photo library
- Scanning a user's full gallery
- Cloud synchronization
- User accounts or billing
- Shared albums or social features
- Video, Live Photo, or RAW compression
- Production-grade encryption or infrastructure
- Lossless guarantees
- Handling major viewpoint changes
- Defining a globally supported file standard

---

## 6. Core User Flow

### Step 1: Upload

The user uploads 5 to 20 similar photos.

The interface must state:

> Choose photos taken at approximately the same moment and from approximately the same position.

The upload screen displays:

- Thumbnail
- Filename
- File size
- Dimensions
- Total original size
- Remove action

### Step 2: Validate

The system evaluates whether the set is suitable.

Possible results:

- `safe_to_fold`
- `foldable_with_reduced_savings`
- `split_recommended`
- `not_foldable`

`split_recommended` is advisory in P0. The MVP does not need to create multiple moments or automatically cluster the upload.

The system must return at least one clear reason for warnings or rejection.

Examples:

- Camera movement is too large
- Images have insufficient scene overlap
- Several photos appear to show different scenes
- Alignment failed for one or more frames
- Estimated package size is unlikely to beat the originals

### Step 3: Analyze

The system selects a reference frame and reports:

- Number of accepted photos
- An explicit accepted or rejected disposition and reason for every uploaded frame
- Reference-frame index
- Similarity score
- Analysis-resolution estimated shared-region percentage, labeled as an estimate
- Analysis-resolution estimated changing-region percentage, labeled as an estimate
- Camera-motion assessment
- Suitability result
- Optional semantic observations

### Step 4: Fold

The user starts processing.

The pipeline:

1. Normalizes and validates inputs
2. Aligns frames
3. Estimates shared and changing regions
4. Encodes the shared base
5. Encodes frame-specific changes
6. Creates the manifest
7. Reconstructs every frame
8. Evaluates quality
9. Creates the downloadable package

### Step 5: Review

The results screen displays:

- Original total bytes
- PhotoFold package bytes
- Bytes saved
- Percentage saved
- Number of reconstructed frames
- Mean and minimum quality scores
- Processing warnings
- Package contents summary

### Step 6: Inspect and export

The user can:

- Swipe between reconstructed frames
- Toggle between original and reconstruction
- Use a comparison slider
- View a difference heatmap
- Zoom into image details
- Export a reconstructed image
- Download the PhotoFold package

---

## 7. Functional Requirements

### FR-1: Upload and input handling

- Accept 5 to 20 files
- Accept JPEG, PNG, and WebP
- Preserve original files for comparison during the active processing session
- Normalize EXIF orientation before analysis
- Define the normalized display-oriented dimensions as the reconstruction output dimensions
- For P0, reject a set whose normalized display-oriented dimensions are not identical
- Generate lower-resolution analysis copies
- Display validation errors without starting the pipeline
- Do not silently discard unsupported or corrupted files
- Return an accepted or rejected disposition and reason for every input while preserving its original upload index

### FR-2: Set suitability

Suitability should use a practical combination of:

- Image dimensions and aspect ratio
- Perceptual hashes
- Feature-match count and quality
- Estimated homography or affine-transform confidence
- Shared scene overlap
- Capture timestamps when available
- Outlier detection

Embeddings are optional for P0.

The suitability response must include:

```json
{
  "status": "safe_to_fold",
  "score": 0.0,
  "reasons": [],
  "outlier_frame_indices": []
}
```

Thresholds must be configurable and recorded in the results. The initial values should be selected during the compression spike rather than treated as permanent product constants.

Folding must not start if fewer than five frames remain accepted. Rejected frames must remain visible to the user with their original upload indices and reasons. Automatic splitting is not required for P0.

### FR-3: Reference-frame selection

The system selects one reference frame using practical signals such as:

- Sharpness
- Exposure
- Scene coverage
- Motion blur
- Average similarity to the other frames
- Alignment success rate

For the MVP, one reference frame is sufficient.

Manual override is P2.

### FR-4: Alignment

For each non-reference frame, the pipeline must:

1. Detect and describe visual features
2. Match features to the reference
3. Estimate an affine transform or homography
4. Warp images into a common coordinate system
5. Calculate alignment confidence
6. Store the transform and confidence

The package transform convention is mandatory:

- Serialize a row-major 3x3 `reference_to_target` matrix
- Interpret the matrix in normalized, display-oriented pixel coordinates
- Map pixels from the decoded reference base into the target output canvas
- Record the transform type, interpolation mode, border mode, output width, and output height
- Store changed-region patches and masks in target-frame coordinates

Optional optical-flow refinement must not block the P0 implementation.

If alignment confidence is below the configured threshold, the frame must be rejected, marked as an outlier, or cause the set to fail.

### FR-5: Shared and changed regions

The pipeline must produce:

- A shared-scene estimate
- A changed-region mask for every frame
- A confidence or uncertainty representation
- A difference visualization suitable for debugging

A median or consensus image may be tested, but the default MVP implementation should use one selected reference image as the base unless experiments show a clear advantage.

Changed-region masks should be expanded or softened where necessary to reduce boundary artifacts.

For each frame:

```text
changed_region_percent = changed_mask_pixels / output_pixels * 100
shared_region_percent = valid_warped_base_pixels_not_changed / output_pixels * 100
```

Pixels outside the valid warped-base region count as changed. Aggregate percentages must be weighted by output pixel count. Analysis-resolution values are estimates; final displayed result values must be recalculated from full-resolution masks.

### FR-6: Difference encoding

Each frame representation may contain:

- Transform metadata
- Changed-region image or patches
- Alpha or binary mask
- Optional residual image
- Frame metadata
- Encoding parameters

The system must avoid storing a second full-resolution copy of each frame inside the PhotoFold package.

The P0 default must store cropped changed-region patches with target-space bounding boxes and lossless alpha or grayscale masks. Nearby components may be merged to control file overhead. A full-canvas changed image is an experiment only and must not be the default representation.

The first implementation should prefer WebP because it is easier to support consistently. AVIF can be tested as an optimization after the end-to-end pipeline works.

### FR-7: Reconstruction

The reconstruction function must accept only the PhotoFold package and a frame index.

It must:

1. Load the shared base
2. Warp the base into the target canvas using the stored `reference_to_target` transform
3. Composite target-space changed-region patches using their stored bounding boxes and lossless masks
4. Apply residual corrections when present
5. Produce an image with the target frame's normalized display-oriented dimensions
6. Export the result as JPEG, PNG, or WebP

A successful reconstruction must not depend on the original input image.

### FR-8: Storage measurement

The backend must report:

```json
{
  "original_total_bytes": 0,
  "package_total_bytes": 0,
  "byte_delta": 0,
  "percent_change": 0.0,
  "bytes_saved": 0,
  "percent_saved": 0.0,
  "is_smaller_than_originals": true
}
```

The values are defined as:

```text
original_total_bytes = sum of exact uploaded source-file sizes
package_total_bytes = exact final `.photofold` archive size
byte_delta = original_total_bytes - package_total_bytes
percent_change = byte_delta / original_total_bytes * 100
bytes_saved = max(byte_delta, 0)
percent_saved = max(percent_change, 0)
```

The completed archive must be measured after it is closed. The external run/API result owns `package_total_bytes`; metrics stored inside the archive must omit that self-referential value. Gate 1 engineering output must also report the independent-WebP control, its per-frame quality, and the resulting relational gain or loss.

If the package is not smaller than the original collection:

- Do not report a positive saving
- Display `No meaningful savings found`
- Retain quality results for debugging
- Mark the fold as unsuccessful or experimental

Because size is known only after packaging and quality is known only after reconstruction, no-savings and below-threshold results are terminal evaluated outcomes. The pipeline must finish reconstruction and measurement, retain the evidence, and then mark the fold `complete_no_savings` or `failed_quality`; it must not discard the measured result.

### FR-9: Quality evaluation

P0 must calculate SSIM for every reconstructed frame.

SSIM must be calculated between the normalized decoded original and the decoded reconstruction reopened through the public package decoder. For opaque photos, calculate RGB SSIM with `data_range=255` and `channel_axis=2`. If alpha is supported, the implementation must define and record consistent alpha handling rather than silently dropping it.

The results must include:

- Per-frame SSIM
- Mean SSIM
- Minimum SSIM
- Pixel-difference visualization

PSNR or LPIPS may be added later.

Quality thresholds must be configurable. The system must warn or fail when the selected threshold is not met.

Whole-image SSIM can hide a small severe artifact. Gate 1 must therefore include visible per-frame heatmaps and visual review. A changed-region score or worst-tile error may be retained as an engineering diagnostic without replacing the required SSIM result.

### FR-10: Package generation

The system must create a reconstructable downloadable P0 package such as:

```text
moment.photofold                  # ZIP archive with this extension
├── manifest.json
├── base.webp
├── frames/
│   ├── 000/
│   │   └── frame.json            # identity transform; normally no patches
│   └── 001/
│       ├── frame.json
│       └── patches/
│           ├── 000.webp
│           ├── 000-mask.png
│           └── 000-residual.webp # optional
└── metadata/
    ├── analysis.json
    ├── metrics.json              # quality/config; no final archive byte count
    └── semantic-analysis.json   # optional
```

The downloadable artifact is a ZIP archive with a `.photofold` extension for the MVP. `ZIP_STORED` is the initial default because the image members are already compressed; another ZIP mode may be adopted only after measurement. Every file placed in the archive counts toward `package_total_bytes`.

Preview images, reconstructions, difference heatmaps, alignment overlays, and experiment reports are external inspection artifacts unless deliberately placed in the archive. If included, their bytes count. The manifest must include member sizes and SHA-256 checksums, and the package validator must reject unsafe paths, missing assets, checksum failures, invalid dimensions, non-finite transforms, or unsupported required codecs.

### FR-11: Failure handling

The pipeline must stop, reject, warn, or produce an evaluated terminal failure when:

- The set has fewer than 5 or more than 20 images
- Image decoding fails
- Dimensions or aspect ratios are incompatible
- Scene overlap is too low
- Camera motion is excessive
- Feature matching is insufficient
- Alignment fails
- Reconstruction cannot be completed
- Quality falls below the configured threshold
- The package is not smaller than the original set

Decode, compatibility, scene, feature, alignment, and reconstruction failures may stop processing. Quality and savings failures occur only after reconstruction and measurement and must preserve their real artifacts and metrics for inspection.

Every failure response must include:

- A machine-readable error code
- A user-readable explanation
- The processing stage that failed
- Debug information in development mode

---

## 8. Recommended Technical Architecture

### Repository structure

```text
photofold/
├── apps/
│   └── web/                    # Next.js frontend
├── services/
│   └── processor/              # FastAPI and image pipeline
├── packages/
│   └── contracts/              # Shared schemas or generated types
├── data/
│   └── demo/                   # Curated local datasets
├── docs/
│   ├── PhotoFold_Developer_PRD.md
│   ├── IMPLEMENTATION_PLAN.md
│   └── PhotoFold_Demo_Script.md
├── AGENTS.md
└── README.md
```

A simpler repository structure is acceptable if it reduces setup time. The frontend and processor should still have a clear interface boundary.

### Frontend

Recommended:

- Next.js
- TypeScript
- Tailwind CSS
- React Dropzone or native file input
- Canvas for comparison and heatmap views

Frontend responsibilities:

- Upload and thumbnail management
- Analysis and suitability display
- Processing progress
- Results dashboard
- Frame viewer
- Original-versus-reconstruction comparison
- Package and image download

Framer Motion is optional and should be added only after the core pipeline works.

### Backend and processing

Recommended:

- Python
- FastAPI
- OpenCV
- Pillow
- NumPy
- scikit-image

Backend responsibilities:

- Input validation
- Metadata extraction
- Temporary file management
- Suitability analysis
- Reference selection
- Alignment
- Shared-region and change detection
- Encoding
- Reconstruction
- Metrics
- Package generation
- Optional model calls

For the hackathon MVP:

- Use temporary local storage
- Do not add a database unless a concrete requirement appears
- Process one active job at a time if necessary
- Use synchronous requests for short operations
- Add status polling only if processing exceeds normal request limits

### Prototype execution profile

The accepted Phase 1B multi-dataset experiment is sufficient evidence to proceed to a controlled local web prototype without first completing the stable processing-service gate. Under this profile:

- Gate 2 is deferred, not passed.
- The Gate 3P prototype may use a local-only Next.js route handler or server action as a narrow bridge to the existing processor CLI instead of adding FastAPI product routes.
- The bridge must use a fixed argument vector without shell interpolation, isolate each run in a temporary workspace, permit only one active fold, and expose only real processor results and artifacts.
- Progress may be coarse, but it must represent actual execution and must never be timer-only or fabricated.
- Manual/startup cleanup is sufficient for the controlled demo. Durable state, restart recovery, concurrent jobs, generated product-route OpenAPI types, delete endpoints, and TTL cleanup remain Gate 2 work.
- This exception applies only to a local single-machine prototype. Remote deployment, multi-user use, or a separately supported processor boundary requires returning to Gate 2.

### Deferred processing API surface

This is the target surface when Gate 2 resumes. Exact route names may change. The Gate 3P local bridge does not need to reproduce these HTTP routes.

```text
POST /moments
  Upload files and create a temporary moment.

POST /moments/{moment_id}/analyze
  Validate the set, select a reference, and return analysis.

POST /moments/{moment_id}/fold
  Run encoding, reconstruction, and evaluation.

GET /moments/{moment_id}
  Return current status and results.

GET /moments/{moment_id}/frames/{frame_index}/original
GET /moments/{moment_id}/frames/{frame_index}/reconstruction
GET /moments/{moment_id}/frames/{frame_index}/difference

GET /moments/{moment_id}/bundle
  Download the generated PhotoFold package.
```

All API responses must use structured error objects.

---

## 9. Processing Pipeline

### Stage A: Preprocess

Inputs:

- Original uploaded files

Outputs:

- Normalized originals
- Analysis-resolution copies
- Metadata records

Tasks:

- Decode images
- Normalize orientation
- Extract timestamps, source byte counts, and normalized display-oriented dimensions
- Preserve originals for evaluation
- Generate analysis copies

### Stage B: Validate similarity

Inputs:

- Analysis copies
- Metadata

Outputs:

- Suitability score
- Outlier list
- Reference recommendation

Tasks:

- Calculate perceptual hashes
- Calculate pairwise similarity
- Estimate feature overlap
- Reject major outliers
- Select a reference candidate

### Stage C: Align

Inputs:

- Reference frame
- Other frames

Outputs:

- Transform per frame
- Aligned images
- Confidence score
- Valid-overlap masks

Tasks:

- Detect features
- Match features
- Estimate transform
- Warp into the common coordinate system
- Measure confidence
- Convert and serialize the final transform as row-major `reference_to_target` in normalized full-resolution pixel coordinates

### Stage D: Estimate shared scene and changes

Inputs:

- Aligned frames

Outputs:

- Shared base
- Per-frame changed-region masks
- Optional uncertainty maps
- Debug visualizations

Tasks:

- Compare aligned pixels
- Estimate stable regions
- Detect changed regions
- Clean and expand masks
- Preserve uncertain boundaries
- Calculate full-resolution shared and changed percentages using the defined pixel-count formulas

### Stage E: Encode

Inputs:

- Shared base
- Transforms
- Changed regions
- Optional residuals

Outputs:

- Encoded assets
- Manifest
- Initial package

Tasks:

- Encode the base
- Encode cropped target-space patches with lossless masks
- Write transform and target-space bounding-box metadata
- Write manifest and metadata
- Write and close the final `.photofold` archive
- Calculate archive bytes from the closed file

### Stage F: Reconstruct

Inputs:

- PhotoFold package

Outputs:

- Reconstructed frames

Tasks:

- Rebuild every frame from package assets
- Ensure the reconstruction process is given only the package and target frame index
- Export standard images
- Verify expected dimensions

### Stage G: Evaluate

Inputs:

- Originals
- Reconstructions
- Package

Outputs:

- Quality metrics
- Storage metrics
- Difference views
- Final success or failure state

Tasks:

- Reopen reconstructions through the package decoder and calculate per-frame RGB SSIM
- Calculate byte totals
- Compare the Gate 1 package with the matched-quality independent-WebP control
- Generate difference heatmaps
- Apply quality and savings gates

---

## 10. Manifest Contract

The exact schema may evolve, but it must contain enough information to reconstruct every frame without the originals.

Example:

```json
{
  "format": "photofold",
  "version": "0.1",
  "created_at": "ISO-8601 timestamp",
  "reference_frame_index": 0,
  "base": {
    "path": "base.webp",
    "width": 0,
    "height": 0,
    "encoding": "webp"
  },
  "frames": [
    {
      "index": 0,
      "original_filename": "IMG_0001.jpg",
      "output_width": 0,
      "output_height": 0,
      "transform": {
        "type": "affine",
        "reference_to_target": [
          1.0, 0.0, 0.0,
          0.0, 1.0, 0.0,
          0.0, 0.0, 1.0
        ],
        "interpolation": "linear",
        "border_mode": "constant"
      },
      "patches": [
        {
          "bbox": [0, 0, 0, 0],
          "image_path": "frames/000/patches/000.webp",
          "mask_path": "frames/000/patches/000-mask.png",
          "residual_path": null
        }
      ]
    }
  ],
  "metrics_path": "metadata/metrics.json",
  "analysis_path": "metadata/analysis.json",
  "semantic_analysis_path": null
}
```

The manifest must also contain an inventory with encoded byte sizes and SHA-256 checksums for every referenced non-manifest asset. The manifest cannot checksum itself; its validity is covered by schema validation, while the external run result may record the final archive checksum. The processor must validate the schema, transform convention, paths, asset inventory, checksums, dimensions, and codec requirements before declaring the package complete.

---

## 11. GPT-5.6 Integration

### Purpose

GPT-5.6 provides semantic understanding, not pixel-level reconstruction.

It may:

- Determine whether frames appear to belong to one moment
- Identify pose and expression changes
- Identify unique people, objects, or background events
- Explain why a set is suitable or unsafe
- Recommend regions or frames for higher-quality preservation
- Generate a human-readable moment summary

It must not:

- Calculate exact pixel differences
- Perform geometric alignment
- Calculate storage size
- Replace deterministic reconstruction
- Be the only reason a frame is accepted or rejected

### Input strategy

Use a reduced-resolution contact sheet or selected frames rather than full-resolution uploads where possible.

### Required structured output

```json
{
  "same_moment": true,
  "summary": "",
  "meaningful_changes": [
    {
      "frame_indices": [0],
      "type": "expression",
      "description": "",
      "preservation_priority": "high"
    }
  ],
  "unique_events": [],
  "unsafe_reasons": []
}
```

### Integration gate

GPT-5.6 is P1.

Do not integrate it until the deterministic pipeline can:

- Align
- Encode
- Reconstruct
- Measure quality
- Measure storage

To demonstrate that the model is not decorative, semantic output should visibly alter at least one preservation decision or quality setting.

---

## 12. Non-Functional Requirements

### Performance

For curated demo datasets:

- Support 5 to 15 medium-resolution images
- Complete processing quickly enough for a live or recorded demonstration
- Display stage-level progress
- Permit cached results only as a fallback

Cached results must originate from genuine prior processing and must not display invented measurements.

### Reliability

The pipeline should successfully process at least three curated sets:

1. Expression changes with minimal camera movement
2. Pose changes with minor camera movement
3. One unique person or object entering the scene

### Privacy

The prototype must:

- Clearly state that images are processed by the prototype backend
- Use temporary storage
- Delete temporary uploads after a configurable retention period or manual cleanup
- Avoid retaining images unnecessarily
- Send reduced-resolution model inputs when sufficient
- Avoid claims of production-level privacy guarantees

### Explainability

The interface must explain:

- Why the images were grouped
- Why a reference frame was selected
- Which regions were stored separately
- Why a set or frame was rejected
- Why measured savings may be low

---

## 13. Development Plan and Gates

### Gate 0: Repository foundation

Deliverables:

- Project structure
- Frontend and processor start locally
- Shared environment documentation
- Lint, typecheck, test, and build commands
- One curated dataset checked into or documented for local use
- `AGENTS.md`
- `IMPLEMENTATION_PLAN.md`

Exit criteria:

- A new developer can run the frontend and processor from the README
- Validation commands pass

### Gate 1: Compression proof

Do not build the full interface before this gate passes.

Deliverables:

- CLI or test script for one curated dataset
- A real curated dataset with at least five input frames, all accepted for the primary Gate 1 run
- Reference-frame selection
- Alignment
- Shared base
- Frame-specific differences
- Reconstructed frames
- Real final-archive package-size calculation
- Matched-quality independent-WebP rate-distortion control
- SSIM report
- Debug images
- A self-contained `report.html` with embedded originals, reconstructions, difference heatmaps, original/package/saved byte totals, per-frame/mean/minimum quality, package file listing, integrity checks, and an explicit gate verdict

Exit criteria:

- At least 5 images are processed
- Every input frame in the primary Gate 1 set is accepted and reconstructed
- The package can be reconstructed without original files
- The package is smaller than the original set for at least one curated dataset
- The package beats independently encoded WebP at equal or better mean and minimum SSIM before the shared-scene hypothesis is claimed as proven
- Quality metrics are recorded
- The self-contained HTML report is reviewed by the team without requiring source-code inspection

If this gate fails, optimize the encoding strategy or narrow the supported dataset before continuing.

### Gate 2: Stable processing service — deferred for the local prototype

Gate 2 remains required for a reusable or remotely deployed processing service. It is not a prerequisite for the constrained Gate 3P prototype execution profile above and must not be marked complete merely because that prototype works.

Deliverables:

- FastAPI wrapper
- Structured status and errors
- Package generation
- Automated tests
- Three curated datasets

Exit criteria:

- All three curated success datasets complete and reconstruct every expected frame
- Separate unsuitable/corrupt fixtures fail with the expected reasons
- No hard-coded savings values
- Package and quality metrics are reproducible within reasonable encoding variation

### Gate 3P: Local end-to-end prototype flow

Deliverables:

- Upload screen
- Analysis screen
- Fold action
- Honest processing state
- Results screen
- Frame viewer
- Comparison view
- Export and bundle download

Exit criteria:

- A user can complete the full workflow without command-line steps
- Results are produced by the real processor
- Error states are understandable
- The local bridge uses fixed arguments, run-scoped paths, one active fold, and real generated artifacts
- UI values match processor result files and downloaded artifact sizes without requiring FastAPI product routes

### Gate 4: Semantic preservation

Deliverables:

- Contact-sheet generation
- GPT-5.6 structured analysis
- Semantic observations in the interface
- At least one semantic output influences preservation behavior

Exit criteria:

- Semantic analysis changes an observable processing decision
- The deterministic pipeline still works if the model call fails

### Gate 5: Demo hardening

Deliverables:

- Folding animation
- Final curated datasets
- Stable recorded-demo path
- Cached fallback results generated from real runs
- Architecture diagram
- Demo script
- Final README and hackathon documentation

Exit criteria:

- The complete demo can be run repeatedly
- Every displayed metric is traceable to real output
- A fallback exists for network or model failure

---

## 14. Test Plan

### Unit tests

- File validation
- Metadata extraction
- Orientation normalization
- Reference scoring
- Transform serialization
- Manifest validation
- Storage calculation
- Quality calculation
- Reconstruction dimensions
- Error-code mapping

### Integration tests

For each curated dataset:

- Run preprocessing
- Run suitability analysis
- Align frames
- Generate package
- Reconstruct all frames
- Verify manifest references exist
- Verify output dimensions
- Verify quality metrics exist
- Verify byte totals match files on disk

### End-to-end tests

- Upload valid set
- Remove a file
- Analyze
- Fold
- Review results
- Compare a frame
- Export a frame
- Download package

### Failure tests

- Too few files
- Unsupported file
- Corrupted image
- Unrelated scenes
- Excessive camera movement
- Failed alignment
- Package larger than originals
- Quality below threshold
- Model timeout or invalid model output

### Regression outputs

For curated datasets, retain:

- Selected reference frame
- Alignment confidence range
- Package byte range
- Mean and minimum SSIM range
- Representative difference images
- Self-contained human-verification HTML reports where required by the implementation plan

Do not require byte-for-byte identical compressed output across library versions.

---

## 15. Default Implementation Decisions

Codex should use these defaults unless a concrete experiment justifies changing them:

1. Build the deterministic compression proof before the full UI.
2. Use one selected reference frame for the MVP.
3. Use WebP first. Treat AVIF as an optimization.
4. Use local temporary storage. Do not add authentication or a database.
5. Preserve normalized display-oriented output dimensions after EXIF orientation.
6. Use SSIM as the required P0 quality metric.
7. Use a curated dataset before supporting arbitrary uploads.
8. Reject unsupported photo sets rather than producing misleading results.
9. Keep GPT-5.6 behind a clear interface so the core pipeline works without it.
10. Optimize for a reliable hackathon demonstration, not production scale.
11. Measure `package_total_bytes` from the closed downloadable archive.
12. Use a matched-quality independent-WebP control before claiming relationship-compression benefit.
13. Store cropped target-space patches with lossless masks by default.

---

## 16. Definition of Done

The MVP is done when:

- A user uploads a valid photo set through the web interface
- PhotoFold explains whether the set is suitable
- The real image pipeline generates a reconstructable package
- All accepted photos can be rebuilt without their source files
- The results show real original and package byte counts
- The results show measured quality
- A user can visually compare original and reconstruction
- A user can export a reconstructed frame
- A user can download the PhotoFold package
- Unsuitable sets fail honestly with a useful explanation
- The demo works reliably on at least three curated datasets
- All displayed metrics come from real processing
- The primary Gate 1 result is human-verifiable from its self-contained HTML report
- The product does not claim that relational compression caused savings unless it beats the matched-quality independent-WebP control
