import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import Home from "./page";

function files(count = 5): File[] {
  return Array.from(
    { length: count },
    (_, index) => new File(["x".repeat(100 + index)], `frame-${index}.jpg`, { type: "image/jpeg" }),
  );
}

function choose(inputFiles = files()) {
  const input = document.querySelector<HTMLInputElement>('input[type="file"]');
  if (!input) throw new Error("file input missing");
  fireEvent.change(input, { target: { files: inputFiles } });
}

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const sourceFrames = Array.from({ length: 5 }, (_, index) => ({
  index,
  original_filename: `frame-${index}.jpg`,
  stored_filename: `frame-${String(index).padStart(3, "0")}.upload`,
  decoded_format: "JPEG",
  mime_type: "image/jpeg",
  mode: "RGB",
  bytes: 200,
  sha256: "a".repeat(64),
  width: 1600,
  height: 1200,
  disposition: "accepted",
  reasons: [],
  original_artifact: `uploads/frame-${String(index).padStart(3, "0")}.upload`,
}));

const analysis = {
  schema_version: "1.1",
  analyzed_at: "2026-07-19T12:00:00Z",
  status: "analyzed_foldable",
  suitability: "foldable_with_reduced_savings",
  strategy: "hybrid",
  reasons: ["4 frames can share scene data; 1 will be stored independently."],
  source_frames: sourceFrames,
  original_total_bytes: 1000,
  normalized_dimensions: { width: 1600, height: 1200 },
  shared_frame_count: 4,
  fallback_frame_count: 1,
  frame_dispositions: Array.from({ length: 5 }, (_, index) => ({
    frame_index: index,
    storage_mode: index === 2 ? "shared_reference" : index === 4 ? "independent_source" : "shared_delta",
    fallback_reason: index === 4 ? "Alignment evidence did not pass the threshold." : null,
  })),
  reference_frame_index: 2,
  reference_score: 0.91,
  reference_candidates: [
    {
      index: 2,
      score: 0.91,
      mean_inlier_ratio: 0.94,
      mean_valid_overlap: 0.97,
      sharpness: 42,
      sharpness_score: 1,
      clipped_pixel_fraction: 0.01,
      alignment_success_count: 4,
      alignment_failure_indices: [],
    },
  ],
  alignment: Array.from({ length: 5 }, (_, index) => ({
    frame_index: index,
    decision: index === 4 ? "fallback" : "shared",
    type: index === 2 ? "identity" : index === 4 ? null : "affine",
    reference_to_target: index === 4 ? null : [1, 0, 0, 0, 1, 0, 0, 0, 1],
    inlier_count: index === 4 ? null : index === 2 ? 0 : 42,
    match_count: index === 4 ? null : index === 2 ? 0 : 44,
    inlier_ratio: index === 4 ? null : 0.95,
    median_reprojection_error: index === 4 ? null : 0.5,
    reprojection_error_units: "analysis_pixels",
    valid_overlap: index === 4 ? null : 0.98,
    fallback_reason: index === 4 ? "Alignment evidence did not pass the threshold." : null,
  })),
  alignment_measurement: {
    units: "analysis_pixels",
    analysis_max_dimension: 800,
    max_median_reprojection_error: 2,
    min_inlier_ratio: 0.8,
    description: "Measured on the fixed analysis canvas.",
  },
  config_sha256: "b".repeat(64),
  warnings: ["Local prototype warning."],
  deferred_fields: ["suitability_score", "automatic_set_splitting"],
};

const result = {
  schema_version: "1.1",
  completed_at: "2026-07-19T12:01:00Z",
  status: "complete_no_savings",
  strategy: "hybrid",
  shared_frame_count: 4,
  fallback_frame_count: 1,
  reference_frame_index: 2,
  reconstructed_frame_count: 5,
  storage: {
    original_total_bytes: 1000,
    package_total_bytes: 1500,
    package_sha256: "c".repeat(64),
    byte_delta: -500,
    percent_change: -50,
    bytes_saved: 0,
    percent_saved: 0,
    is_smaller_than_originals: false,
  },
  quality: {
    mean_ssim: 0.9,
    minimum_ssim: 0.86,
    min_mean_threshold: 0.85,
    min_per_frame_threshold: 0.82,
    threshold_pass: true,
  },
  frames: sourceFrames.map((frame) => ({
    index: frame.index,
    original_filename: frame.original_filename,
    width: frame.width,
    height: frame.height,
    original_bytes: frame.bytes,
    storage_mode: analysis.frame_dispositions[frame.index].storage_mode,
    fallback_reason: analysis.frame_dispositions[frame.index].fallback_reason,
    reconstructed: true,
    ssim: 0.9 - frame.index / 100,
    quality_threshold_pass: true,
    patch_count: frame.index,
    changed_region_percent: 4,
    shared_region_percent: 94,
    artifacts: {
      original: frame.original_artifact,
      reconstruction: `reconstructions/frame-${String(frame.index).padStart(3, "0")}.png`,
      difference: `differences/frame-${String(frame.index).padStart(3, "0")}.png`,
    },
  })),
  package_contents: {
    member_count: 18,
    frame_count: 5,
    patch_count: 4,
    mask_count: 4,
    metadata_count: 2,
    independent_source_count: 1,
    member_payload_bytes: 1200,
  },
  package_artifact: "moment.photofold",
  warnings: ["Storage is compared with exact uploaded source bytes."],
  error: null,
};

describe("PhotoFold Gate 3 workflow", () => {
  it("shows exact browser file totals and updates them when a frame is removed", async () => {
    render(<Home />);
    choose();

    expect(await screen.findByText("5 / 20 frames")).toBeInTheDocument();
    expect(screen.getByText("510 B")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Remove frame-0.jpg" }));

    expect(screen.getByText("4 / 20 frames")).toBeInTheDocument();
    expect(screen.getByText("410 B")).toBeInTheDocument();
    expect(screen.getByText("1 more photo needed")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Analyze this moment" })).toBeDisabled();
  });

  it("renders structured processor errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          {
            error: {
              code: "DIMENSIONS_INCOMPATIBLE",
              message: "All photos must have identical normalized dimensions.",
              stage: "preprocess",
              frame_indices: [4],
              retryable: false,
              debug: null,
            },
          },
          422,
        ),
      ),
    );
    render(<Home />);
    choose();
    await waitFor(() => expect(screen.getByRole("button", { name: "Analyze this moment" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Analyze this moment" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("DIMENSIONS_INCOMPATIBLE · preprocess");
    expect(screen.getByRole("alert")).toHaveTextContent("Affected frames: 5");
  });

  it("labels deferred analysis and never calls a no-savings outcome successful", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ runId: "00000000-0000-4000-8000-000000000001", analysis }))
      .mockResolvedValueOnce(jsonResponse({ runId: "00000000-0000-4000-8000-000000000001", result }));
    vi.stubGlobal("fetch", fetchMock);
    render(<Home />);
    choose();
    await waitFor(() => expect(screen.getByRole("button", { name: "Analyze this moment" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Analyze this moment" }));

    expect(await screen.findByText("Processor analysis")).toBeInTheDocument();
    expect(screen.getByText("Ready to fold")).toBeInTheDocument();
    expect(screen.getByText("4 frames can share scene data; 1 will be stored independently.")).toBeInTheDocument();
    expect(screen.getAllByText("Fallback").length).toBeGreaterThan(0);
    expect(screen.getByText(/suitability score/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Fold this moment" }));

    expect(await screen.findByText("Fold complete — no storage reduction")).toBeInTheDocument();
    expect(screen.getByText("Difference vs uploads")).toBeInTheDocument();
    expect(screen.queryByText("Saved vs uploads")).not.toBeInTheDocument();
    expect(screen.queryByText("Moment folded successfully")).not.toBeInTheDocument();
    expect(screen.getByText("Download PhotoFold archive")).toBeInTheDocument();
    expect(screen.getByText("Requires PhotoFold to reconstruct the complete set.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Heatmap" }));
    expect(screen.getByRole("img", { name: /difference for frame-2.jpg/i })).toBeInTheDocument();
  });

  it("uses neutral independent-only strategy language", async () => {
    const independentAnalysis = {
      ...analysis,
      suitability: "foldable_with_reduced_savings",
      strategy: "independent_only",
      reasons: ["These photos will use independent storage."],
      normalized_dimensions: null,
      shared_frame_count: 0,
      fallback_frame_count: 5,
      reference_frame_index: null,
      reference_score: null,
      frame_dispositions: sourceFrames.map((frame) => ({
        frame_index: frame.index,
        storage_mode: "independent_source",
        fallback_reason: "No useful shared-scene group passed alignment.",
      })),
      alignment: sourceFrames.map((frame) => ({
        frame_index: frame.index,
        decision: "fallback",
        type: null,
        reference_to_target: null,
        inlier_count: null,
        match_count: null,
        inlier_ratio: null,
        median_reprojection_error: null,
        reprojection_error_units: "analysis_pixels",
        valid_overlap: null,
        fallback_reason: "No useful shared-scene group passed alignment.",
      })),
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          runId: "00000000-0000-4000-8000-000000000001",
          analysis: independentAnalysis,
        }),
      ),
    );
    render(<Home />);
    choose();
    await waitFor(() => expect(screen.getByRole("button", { name: "Analyze this moment" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Analyze this moment" }));

    expect(await screen.findByText("These photos will use independent storage.")).toBeInTheDocument();
    expect(screen.getByText("No shared base")).toBeInTheDocument();
    expect(screen.getAllByText("Fallback")).toHaveLength(5);
    expect(screen.getByRole("button", { name: "Fold this moment" })).toBeEnabled();
  });
});
