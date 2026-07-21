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
    fallback_reason: index === 4 ? "Alignment fallback: inlier ratio 0.7967 is below 0.8000." : null,
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
    fallback_reason: index === 4 ? "Alignment fallback: inlier ratio 0.7967 is below 0.8000." : null,
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

    expect(await screen.findByText("5 / 20 photos")).toBeInTheDocument();
    expect(screen.getByText("510 B")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Remove frame-0.jpg" }));

    expect(screen.getByText("4 / 20 photos")).toBeInTheDocument();
    expect(screen.getByText("410 B")).toBeInTheDocument();
    expect(screen.getByText("1 more photo needed")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Check these photos" })).toBeDisabled();
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
    await waitFor(() => expect(screen.getByRole("button", { name: "Check these photos" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Check these photos" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("We could not complete this step");
    expect(screen.getByRole("alert")).toHaveTextContent("DIMENSIONS_INCOMPATIBLE · preprocess");
    expect(screen.getByRole("alert")).toHaveTextContent("Photos to check: 5");
  });

  it("labels deferred analysis and never calls a no-savings outcome successful", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ runId: "00000000-0000-4000-8000-000000000001", analysis }))
      .mockResolvedValueOnce(jsonResponse({ runId: "00000000-0000-4000-8000-000000000001", result }));
    vi.stubGlobal("fetch", fetchMock);
    render(<Home />);
    choose();
    await waitFor(() => expect(screen.getByRole("button", { name: "Check these photos" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Check these photos" }));

    expect(await screen.findByText("Most of these photos can share space")).toBeInTheDocument();
    expect(screen.getByText("Ready to create")).toBeInTheDocument();
    expect(screen.getByText("4 photos can share space; 1 will stay whole.")).toBeInTheDocument();
    expect(screen.getAllByText("Kept whole").length).toBeGreaterThan(0);
    expect(screen.getByText(/did not line up closely enough with the others/)).toBeInTheDocument();
    expect(screen.queryByText(/inlier ratio/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Not included in this preview/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Create PhotoFold collection" }));

    expect(await screen.findByText("Your collection is ready, but it is not smaller")).toBeInTheDocument();
    expect(screen.queryByText("Space saved")).not.toBeInTheDocument();
    expect(screen.queryByText("Your smaller photo collection is ready")).not.toBeInTheDocument();
    expect(screen.getByText("Download collection")).toBeInTheDocument();
    expect(screen.getByText(/Contains everything needed to rebuild and export all photos/)).toBeInTheDocument();
    const storageResult = screen.getByRole("region", { name: "Storage result" });
    expect(storageResult).toBeInTheDocument();
    expect(screen.getByText("5 photos preserved")).toBeInTheDocument();
    expect(screen.getByText("4 using shared storage · 1 stored whole")).toBeInTheDocument();
    expect(screen.getByText("500 B larger than the uploaded files")).toBeInTheDocument();
    expect(screen.queryByText("Quality passed")).not.toBeInTheDocument();

    const photoSelector = screen.getByLabelText("Photo selector");
    expect(photoSelector).toContainElement(screen.getByRole("button", { name: "Photo 1 · Shared storage · 90.0% match" }));
    const storedWholeButton = screen.getByRole("button", { name: "Photo 5 · Stored whole · 86.0% match" });
    expect(photoSelector).toContainElement(storedWholeButton);
    expect(document.querySelector(".selected-photo-summary")).not.toBeInTheDocument();

    const advancedDetails = screen.getByText("Advanced details").closest("details");
    expect(advancedDetails).not.toHaveAttribute("open");
    fireEvent.click(screen.getByText("Advanced details"));
    expect(screen.getByText(/SSIM compares structure, contrast, and detail/)).toBeInTheDocument();
    expect(screen.getByText("About these results")).toBeInTheDocument();
    expect(advancedDetails?.querySelectorAll("li")).toHaveLength(3);
    expect(screen.getByText(/1× fits the whole photo/)).toBeInTheDocument();
    const zoom = screen.getByRole("slider", { name: "Zoom" });
    expect(zoom).toHaveValue("1");
    fireEvent.change(zoom, { target: { value: "2" } });
    expect(zoom).toHaveValue("2");

    const viewer = screen.getByTestId("frame-viewer");
    const canvas = viewer.querySelector<HTMLElement>(".viewer-canvas");
    if (!canvas) throw new Error("viewer canvas missing");
    Object.defineProperty(canvas, "clientWidth", { configurable: true, value: 800 });
    Object.defineProperty(canvas, "clientHeight", { configurable: true, value: 450 });
    fireEvent.pointerDown(viewer, { pointerId: 1, clientX: 100, clientY: 100 });
    fireEvent.pointerMove(viewer, { pointerId: 1, clientX: 160, clientY: 140 });
    expect(canvas.style.transform).toContain("translate3d(60px, 40px, 0) scale(2)");
    fireEvent.pointerUp(viewer, { pointerId: 1, clientX: 160, clientY: 140 });
    fireEvent.change(zoom, { target: { value: "2.25" } });
    expect(canvas.style.transform).toContain("translate3d(60px, 40px, 0) scale(2.25)");
    fireEvent.click(screen.getByRole("button", { name: "Fit" }));
    expect(zoom).toHaveValue("1");

    fireEvent.click(screen.getByRole("button", { name: "Change heatmap" }));
    expect(screen.getByText("What the change heatmap compares")).toBeInTheDocument();
    expect(screen.getByText(/compares the rebuilt photo with the original, pixel by pixel/)).toBeInTheDocument();
    expect(screen.getByText(/does not show what moved between burst photos/)).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /difference for frame-2.jpg/i })).toBeInTheDocument();

    fireEvent.click(storedWholeButton);
    expect(storedWholeButton).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText(/Stored whole · SSIM 0.8600/)).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Viewer mode" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Original" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Rebuilt photo" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Change heatmap" })).not.toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Stored photo frame-4.jpg" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Save this photo" })).toBeInTheDocument();
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
    await waitFor(() => expect(screen.getByRole("button", { name: "Check these photos" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Check these photos" }));

    expect(await screen.findByText(/These photos are too different to share safely/)).toBeInTheDocument();
    expect(screen.getByText("None needed")).toBeInTheDocument();
    expect(screen.getAllByText("Kept whole")).toHaveLength(5);
    expect(screen.getByRole("button", { name: "Create PhotoFold collection" })).toBeEnabled();
  });

  it("shows exactly one active workflow step while processing", async () => {
    let finishAnalysis: ((response: Response) => void) | undefined;
    let finishFold: ((response: Response) => void) | undefined;
    const fetchMock = vi.fn()
      .mockImplementationOnce(() => new Promise<Response>((resolve) => { finishAnalysis = resolve; }))
      .mockImplementationOnce(() => new Promise<Response>((resolve) => { finishFold = resolve; }));
    vi.stubGlobal("fetch", fetchMock);
    render(<Home />);
    choose();
    await waitFor(() => expect(screen.getByRole("button", { name: "Check these photos" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Check these photos" }));

    await screen.findByText("Checking now");
    expect(document.querySelectorAll(".step-number-active")).toHaveLength(1);
    expect(document.querySelector(".step-number-active")).toHaveTextContent("2");
    expect(document.querySelectorAll(".step-number-complete")).toHaveLength(1);

    finishAnalysis?.(jsonResponse({ runId: "00000000-0000-4000-8000-000000000001", analysis }));
    await screen.findByText("Most of these photos can share space");
    fireEvent.click(screen.getByRole("button", { name: "Create PhotoFold collection" }));

    await screen.findByText("Folding now");
    expect(screen.getByRole("button", { name: "Folding.." })).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent("Rebuilding and checking every photo");
    expect(screen.getByRole("region", { name: "Most of these photos can share space" })).toHaveAttribute("aria-busy", "true");
    expect(document.querySelectorAll(".step-number-active")).toHaveLength(1);
    expect(document.querySelector(".step-number-active")).toHaveTextContent("3");
    expect(document.querySelectorAll(".step-number-complete")).toHaveLength(2);

    finishFold?.(jsonResponse({ runId: "00000000-0000-4000-8000-000000000001", result }));
    await screen.findByText("Your collection is ready, but it is not smaller");
  });
});
