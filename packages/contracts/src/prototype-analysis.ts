/* Generated from the processor-owned Pydantic schema. Do not edit. */

export type Decision = "shared" | "fallback";
export type FallbackReason = string | null;
export type FrameIndex = number;
export type InlierCount = number | null;
export type InlierRatio = number | null;
export type MatchCount = number | null;
export type MedianReprojectionError = number | null;
export type ReferenceToTarget = [number, number, number, number, number, number, number, number, number] | null;
export type ReprojectionErrorUnits = "analysis_pixels";
export type Type = ("identity" | "affine" | "homography") | null;
export type ValidOverlap = number | null;
export type Alignment = AlignmentRecord[];
export type AnalysisMaxDimension = number;
export type Description = string;
export type MaxMedianReprojectionError = number;
export type MinInlierRatio = number;
export type Units = "analysis_pixels";
export type AnalyzedAt = string;
export type ConfigSha256 = string;
export type DeferredFields = string[];
export type FallbackFrameCount = number;
/**
 * @minItems 5
 * @maxItems 20
 */
export type FrameDispositions =
  | [FrameDisposition, FrameDisposition, FrameDisposition, FrameDisposition, FrameDisposition]
  | [FrameDisposition, FrameDisposition, FrameDisposition, FrameDisposition, FrameDisposition, FrameDisposition]
  | [
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition
    ]
  | [
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition
    ]
  | [
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition
    ]
  | [
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition
    ]
  | [
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition
    ]
  | [
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition
    ]
  | [
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition
    ]
  | [
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition
    ]
  | [
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition
    ]
  | [
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition
    ]
  | [
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition
    ]
  | [
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition
    ]
  | [
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition
    ]
  | [
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition,
      FrameDisposition
    ];
export type FallbackReason1 = string | null;
export type FrameIndex1 = number;
export type StorageMode = "shared_reference" | "shared_delta" | "independent_source";
export type Height = number;
export type Width = number;
export type OriginalTotalBytes = number;
export type Reasons = string[];
export type AlignmentFailureIndices = number[];
export type AlignmentSuccessCount = number;
export type ClippedPixelFraction = number;
export type Index = number;
export type MeanInlierRatio = number;
export type MeanValidOverlap = number;
export type Score = number;
export type Sharpness = number;
export type SharpnessScore = number;
export type ReferenceCandidates = ReferenceCandidate[];
export type ReferenceFrameIndex = number | null;
export type ReferenceScore = number | null;
export type SchemaVersion = "1.1";
export type SharedFrameCount = number;
/**
 * @minItems 5
 * @maxItems 20
 */
export type SourceFrames =
  | [SourceSnapshot, SourceSnapshot, SourceSnapshot, SourceSnapshot, SourceSnapshot]
  | [SourceSnapshot, SourceSnapshot, SourceSnapshot, SourceSnapshot, SourceSnapshot, SourceSnapshot]
  | [SourceSnapshot, SourceSnapshot, SourceSnapshot, SourceSnapshot, SourceSnapshot, SourceSnapshot, SourceSnapshot]
  | [
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot
    ]
  | [
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot
    ]
  | [
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot
    ]
  | [
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot
    ]
  | [
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot
    ]
  | [
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot
    ]
  | [
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot
    ]
  | [
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot
    ]
  | [
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot
    ]
  | [
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot
    ]
  | [
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot
    ]
  | [
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot
    ]
  | [
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot,
      SourceSnapshot
    ];
export type Bytes = number;
export type DecodedFormat = "JPEG" | "PNG" | "WEBP";
export type Disposition = "accepted";
export type Height1 = number;
export type Index1 = number;
export type MimeType = "image/jpeg" | "image/png" | "image/webp";
export type Mode = string;
export type OriginalArtifact = string;
export type OriginalFilename = string;
export type Reasons1 = string[];
export type Sha256 = string;
export type StoredFilename = string;
export type Width1 = number;
export type Status = "analyzed_foldable";
export type Strategy = "shared_scene" | "hybrid" | "independent_only";
export type Suitability = "safe_to_fold" | "foldable_with_reduced_savings";
export type Warnings = string[];

export interface PrototypeAnalysis {
  alignment: Alignment;
  alignment_measurement: AlignmentMeasurement;
  analyzed_at: AnalyzedAt;
  config_sha256: ConfigSha256;
  deferred_fields: DeferredFields;
  fallback_frame_count: FallbackFrameCount;
  frame_dispositions: FrameDispositions;
  normalized_dimensions: Dimensions | null;
  original_total_bytes: OriginalTotalBytes;
  reasons: Reasons;
  reference_candidates: ReferenceCandidates;
  reference_frame_index: ReferenceFrameIndex;
  reference_score: ReferenceScore;
  schema_version?: SchemaVersion;
  shared_frame_count: SharedFrameCount;
  source_frames: SourceFrames;
  status?: Status;
  strategy: Strategy;
  suitability: Suitability;
  warnings: Warnings;
}
export interface AlignmentRecord {
  decision: Decision;
  fallback_reason?: FallbackReason;
  frame_index: FrameIndex;
  inlier_count?: InlierCount;
  inlier_ratio?: InlierRatio;
  match_count?: MatchCount;
  median_reprojection_error?: MedianReprojectionError;
  reference_to_target?: ReferenceToTarget;
  reprojection_error_units?: ReprojectionErrorUnits;
  type: Type;
  valid_overlap?: ValidOverlap;
}
export interface AlignmentMeasurement {
  analysis_max_dimension: AnalysisMaxDimension;
  description: Description;
  max_median_reprojection_error: MaxMedianReprojectionError;
  min_inlier_ratio: MinInlierRatio;
  units?: Units;
}
export interface FrameDisposition {
  fallback_reason?: FallbackReason1;
  frame_index: FrameIndex1;
  storage_mode: StorageMode;
}
export interface Dimensions {
  height: Height;
  width: Width;
}
export interface ReferenceCandidate {
  alignment_failure_indices: AlignmentFailureIndices;
  alignment_success_count: AlignmentSuccessCount;
  clipped_pixel_fraction: ClippedPixelFraction;
  index: Index;
  mean_inlier_ratio: MeanInlierRatio;
  mean_valid_overlap: MeanValidOverlap;
  score: Score;
  sharpness: Sharpness;
  sharpness_score: SharpnessScore;
}
export interface SourceSnapshot {
  bytes: Bytes;
  decoded_format: DecodedFormat;
  disposition?: Disposition;
  height: Height1;
  index: Index1;
  mime_type: MimeType;
  mode: Mode;
  original_artifact: OriginalArtifact;
  original_filename: OriginalFilename;
  reasons?: Reasons1;
  sha256: Sha256;
  stored_filename: StoredFilename;
  width: Width1;
}
