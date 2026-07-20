/* Generated from the processor-owned Pydantic schema. Do not edit. */

export type FrameIndex = number;
export type InlierCount = number;
export type InlierRatio = number;
export type MatchCount = number;
export type MedianReprojectionError = number;
/**
 * @minItems 9
 * @maxItems 9
 */
export type ReferenceToTarget = [number, number, number, number, number, number, number, number, number];
export type Type = "identity" | "affine" | "homography";
export type ValidOverlap = number;
export type Alignment = AlignmentRecord[];
export type AnalyzedAt = string;
export type ConfigSha256 = string;
export type DeferredFields = string[];
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
export type SchemaVersion = "1.0";
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
export type Status = "analyzed_foldable" | "analyzed_rejected";
export type Suitability = "safe_to_fold" | "not_foldable";
export type Warnings = string[];

export interface PrototypeAnalysis {
  alignment: Alignment;
  analyzed_at: AnalyzedAt;
  config_sha256: ConfigSha256;
  deferred_fields: DeferredFields;
  normalized_dimensions: Dimensions;
  original_total_bytes: OriginalTotalBytes;
  reasons: Reasons;
  reference_candidates: ReferenceCandidates;
  reference_frame_index: ReferenceFrameIndex;
  reference_score: ReferenceScore;
  schema_version?: SchemaVersion;
  source_frames: SourceFrames;
  status: Status;
  suitability: Suitability;
  warnings: Warnings;
}
export interface AlignmentRecord {
  frame_index: FrameIndex;
  inlier_count: InlierCount;
  inlier_ratio: InlierRatio;
  match_count: MatchCount;
  median_reprojection_error: MedianReprojectionError;
  reference_to_target: ReferenceToTarget;
  type: Type;
  valid_overlap: ValidOverlap;
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
