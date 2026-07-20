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
  schema_version: "1.0",
  analyzed_at: "2026-07-19T12:00:00Z",
  status: "analyzed_foldable",
  suitability: "safe_to_fold",
  reasons: ["All frames passed deterministic validation and alignment thresholds."],
  source_frames: sourceFrames,
  original_total_bytes: 1000,
  normalized_dimensions: { width: 1600, height: 1200 },
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
    type: index === 2 ? "identity" : "affine",
    reference_to_target: [1, 0, 0, 0, 1, 0, 0, 0, 1],
    inlier_count: index === 2 ? 0 : 42,
    match_count: index === 2 ? 0 : 44,
    inlier_ratio: 0.95,
    median_reprojection_error: 0.5,
    valid_overlap: 0.98,
  })),
  config_sha256: "b".repeat(64),
  warnings: ["Local prototype warning."],
  deferred_fields: ["suitability_score", "automatic_set_splitting"],
};

const result = {
  schema_version: "1.0",
  completed_at: "2026-07-19T12:01:00Z",
  status: "complete_no_savings",
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
    expect(screen.getByText(/suitability score/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Fold this moment" }));

    expect(await screen.findByText("Fold complete — no storage reduction")).toBeInTheDocument();
    expect(screen.getByText("Difference vs uploads")).toBeInTheDocument();
    expect(screen.queryByText("Saved vs uploads")).not.toBeInTheDocument();
    expect(screen.queryByText("Moment folded successfully")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Heatmap" }));
    expect(screen.getByRole("img", { name: /difference for frame-2.jpg/i })).toBeInTheDocument();
  });
});
