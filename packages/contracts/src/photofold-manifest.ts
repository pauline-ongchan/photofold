/* Generated from the processor-owned Pydantic schema. Do not edit. */

export type AnalysisPath = string;
export type Bytes = number;
export type Path = string;
export type Sha256 = string;
export type Assets = AssetRecord[];
export type Encoding = "webp";
export type Height = number;
export type Path1 = "base.webp";
export type Quality = number;
export type Width = number;
export type CreatedAt = string;
export type FallbackFrameCount = number;
export type Format = "photofold";
/**
 * @minItems 5
 * @maxItems 20
 */
export type Frames =
  | [FrameRecord, FrameRecord, FrameRecord, FrameRecord, FrameRecord]
  | [FrameRecord, FrameRecord, FrameRecord, FrameRecord, FrameRecord, FrameRecord]
  | [FrameRecord, FrameRecord, FrameRecord, FrameRecord, FrameRecord, FrameRecord, FrameRecord]
  | [FrameRecord, FrameRecord, FrameRecord, FrameRecord, FrameRecord, FrameRecord, FrameRecord, FrameRecord]
  | [
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord
    ]
  | [
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord
    ]
  | [
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord
    ]
  | [
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord
    ]
  | [
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord
    ]
  | [
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord
    ]
  | [
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord
    ]
  | [
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord
    ]
  | [
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord
    ]
  | [
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord
    ]
  | [
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord
    ]
  | [
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord,
      FrameRecord
    ];
export type DecodedFormat = "JPEG" | "PNG" | "WEBP";
export type Path2 = string;
export type Index = number;
export type Height1 = number;
export type Width1 = number;
export type OriginalFilename = string;
export type OutputHeight = number;
export type OutputWidth = number;
/**
 * @minItems 4
 * @maxItems 4
 */
export type Bbox = [number, number, number, number];
export type FeatherRadius = number;
export type ImagePath = string;
export type MaskPath = string;
export type ResidualPath = string | null;
export type Patches = PatchRecord[];
export type StorageMode = "shared_reference" | "shared_delta" | "independent_source";
export type BorderMode = "constant";
export type InlierCount = number;
export type InlierRatio = number;
export type Interpolation = "linear";
export type MedianReprojectionError = number;
/**
 * @minItems 9
 * @maxItems 9
 */
export type ReferenceToTarget = [number, number, number, number, number, number, number, number, number];
export type ReprojectionErrorThreshold = number | null;
export type ReprojectionErrorUnits = "analysis_pixels" | "legacy_full_resolution_pixels";
export type Type = "identity" | "affine" | "homography";
export type ValidOverlap = number;
export type MetricsPath = string;
export type ReferenceFrameIndex = number | null;
export type RequiredCodecs = ("jpeg" | "webp" | "png")[];
export type SemanticAnalysisPath = null;
export type SharedFrameCount = number;
export type Strategy = "shared_scene" | "hybrid" | "independent_only";
export type Version = "0.2";

export interface PhotoFoldManifest {
  analysis_path: AnalysisPath;
  assets: Assets;
  base: BaseRecord | null;
  created_at: CreatedAt;
  fallback_frame_count: FallbackFrameCount;
  format?: Format;
  frames: Frames;
  metrics_path: MetricsPath;
  reference_frame_index?: ReferenceFrameIndex;
  required_codecs: RequiredCodecs;
  semantic_analysis_path?: SemanticAnalysisPath;
  shared_frame_count: SharedFrameCount;
  strategy: Strategy;
  version?: Version;
}
export interface AssetRecord {
  bytes: Bytes;
  path: Path;
  sha256: Sha256;
}
export interface BaseRecord {
  encoding?: Encoding;
  height: Height;
  path?: Path1;
  quality: Quality;
  width: Width;
}
export interface FrameRecord {
  independent_source?: IndependentSourceRecord | null;
  index: Index;
  normalized_dimensions: NormalizedDimensions;
  original_filename: OriginalFilename;
  output_height: OutputHeight;
  output_width: OutputWidth;
  patches: Patches;
  storage_mode: StorageMode;
  transform: TransformRecord | null;
}
export interface IndependentSourceRecord {
  decoded_format: DecodedFormat;
  path: Path2;
}
export interface NormalizedDimensions {
  height: Height1;
  width: Width1;
}
export interface PatchRecord {
  bbox: Bbox;
  feather_radius?: FeatherRadius;
  image_path: ImagePath;
  mask_path: MaskPath;
  residual_path?: ResidualPath;
}
export interface TransformRecord {
  border_mode?: BorderMode;
  inlier_count: InlierCount;
  inlier_ratio: InlierRatio;
  interpolation?: Interpolation;
  median_reprojection_error: MedianReprojectionError;
  reference_to_target: ReferenceToTarget;
  reprojection_error_threshold?: ReprojectionErrorThreshold;
  reprojection_error_units: ReprojectionErrorUnits;
  type: Type;
  valid_overlap: ValidOverlap;
}
