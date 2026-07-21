import { expect, test } from "@playwright/test";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { readFile, stat } from "node:fs/promises";
import { resolve } from "node:path";

const repositoryRoot = resolve(__dirname, "../../..");
const dataset = resolve(repositoryRoot, "data/demo/hdrplus-static");
const files = Array.from({ length: 7 }, (_, index) =>
  resolve(dataset, `frame-${String(index).padStart(3, "0")}.jpg`),
);
const fallbackDataset = resolve(repositoryRoot, "data/real-bursts/static-handheld");
const fallbackManifest = JSON.parse(
  readFileSync(resolve(fallbackDataset, "manifest.json"), "utf8"),
) as { files: Array<{ path: string }> };
const fallbackFiles = fallbackManifest.files.map((item) => resolve(fallbackDataset, item.path));

test("curated upload → analyze → fold → inspect → export → bundle", async ({ page }, testInfo) => {
  await page.goto("/");
  const input = page.locator('input[type="file"]');
  await input.setInputFiles(files);
  await expect(page.getByText("7 / 20 photos")).toBeVisible();
  await expect(page.getByText("1600×1200")).toHaveCount(7);

  await page.getByRole("button", { name: "Remove frame-006.jpg" }).click();
  await expect(page.getByText("6 / 20 photos")).toBeVisible();
  await input.setInputFiles(files[6]);
  await expect(page.getByText("7 / 20 photos")).toBeVisible();

  await page.getByRole("button", { name: "Check these photos" }).click();
  await expect(page.getByRole("heading", { name: "These photos are a strong match" })).toBeVisible();
  const analysisRegion = page.getByRole("region", { name: "These photos are a strong match" });
  await expect(analysisRegion.getByText("Ready to create", { exact: true })).toBeVisible();
  await expect(analysisRegion.getByText("All 7 photos can share space.", { exact: true })).toBeVisible();
  await analysisRegion.getByText("See how PhotoFold made this decision").click();
  await expect(analysisRegion.getByText("Matching-detail confidence", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Create PhotoFold collection" }).click();
  await expect(page.getByRole("heading", { name: "Your smaller photo collection is ready" })).toBeVisible({
    timeout: 120_000,
  });
  await expect(page.getByText("Quality passed", { exact: true })).toBeVisible();
  await page.getByText("Size, quality & collection details", { exact: true }).click();
  await expect(page.getByText("What does SSIM mean?")).toBeVisible();

  const resultPath = resolve(repositoryRoot, "artifacts/gate3/latest/result.json");
  const result = JSON.parse(await readFile(resultPath, "utf8"));
  expect(result.status).toBe("complete");
  expect(result.reconstructed_frame_count).toBe(7);
  expect(result.storage.package_total_bytes).toBeGreaterThan(0);
  expect(result.storage.package_total_bytes).toBeLessThan(result.storage.original_total_bytes);
  await expect(page.getByText("Space saved")).toBeVisible();
  await expect(page.getByText(`${result.quality.mean_ssim.toFixed(4)} avg · ${result.quality.minimum_ssim.toFixed(4)} lowest`)).toBeVisible();

  const viewer = page.getByTestId("frame-viewer");
  const zoom = page.getByLabel("Zoom");
  const viewerCanvas = viewer.locator(".viewer-canvas");
  const viewerFitsWithoutScroll = () => viewer.evaluate((element) =>
    element.scrollWidth <= element.clientWidth && element.scrollHeight <= element.clientHeight,
  );
  const viewerFrame = () => viewer.evaluate((element) => ({
    height: element.clientHeight,
    width: element.clientWidth,
  }));
  const viewerOverflowIsHidden = () => viewer.evaluate((element) => {
    const style = getComputedStyle(element);
    return style.overflowX === "hidden" && style.overflowY === "hidden";
  });
  await expect(zoom).toHaveValue("1");
  await expect.poll(viewerFitsWithoutScroll).toBe(true);
  const fittedFrame = await viewerFrame();
  await zoom.press("ArrowRight");
  await expect(zoom).toHaveValue("1.25");
  await expect.poll(viewerFrame).toEqual(fittedFrame);
  await expect.poll(viewerOverflowIsHidden).toBe(true);
  await expect.poll(() => viewerCanvas.evaluate((element) =>
    getComputedStyle(element).transform !== "none" && !getComputedStyle(element).transform.startsWith("matrix(1,"),
  )).toBe(true);
  await zoom.press("End");
  await expect(zoom).toHaveValue("3");
  const transformBeforePan = await viewerCanvas.evaluate((element) => element.getAttribute("style"));
  await viewer.scrollIntoViewIfNeeded();
  const box = await viewer.boundingBox();
  if (!box) throw new Error("Viewer bounds are unavailable");
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 80, box.y + box.height / 2 + 45, { steps: 4 });
  await page.mouse.up();
  await expect.poll(() => viewerCanvas.evaluate((element) => element.getAttribute("style"))).not.toBe(transformBeforePan);
  await expect.poll(viewerFrame).toEqual(fittedFrame);
  await expect.poll(viewerOverflowIsHidden).toBe(true);
  await page.getByRole("button", { name: "Fit" }).click();
  await expect(zoom).toHaveValue("1");

  await page.getByRole("button", { name: "Change heatmap" }).click();
  await expect(page.getByText("How to read the change heatmap")).toBeVisible();
  const difference = page.getByRole("img", { name: "difference for frame-000.jpg" });
  await expect(difference).toBeVisible();
  await expect.poll(() => difference.evaluate((image: HTMLImageElement) => image.naturalWidth)).toBeGreaterThan(0);
  await expect.poll(viewerOverflowIsHidden).toBe(true);
  await expect(page.getByLabel("Frame browser").getByRole("button")).toHaveCount(7);

  const frameSeven = page.getByRole("button", {
    name: `Photo 7 Shares space · match ${result.frames[6].ssim.toFixed(4)}`,
  });
  await frameSeven.click();
  await expect(page.getByRole("heading", { name: "frame-006.jpg" })).toBeVisible();

  const exportDownloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: "Save this rebuilt photo" }).click();
  const exportDownload = await exportDownloadPromise;
  const exportPath = testInfo.outputPath("PhotoFold-frame-006.webp");
  await exportDownload.saveAs(exportPath);
  const exported = await readFile(exportPath);
  expect(exported.subarray(0, 4).toString("ascii")).toBe("RIFF");
  expect(exported.subarray(8, 12).toString("ascii")).toBe("WEBP");

  const bundleDownloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download collection" }).click();
  const bundleDownload = await bundleDownloadPromise;
  const bundlePath = testInfo.outputPath("moment.photofold");
  await bundleDownload.saveAs(bundlePath);
  const downloadedBundle = await readFile(bundlePath);
  expect((await stat(bundlePath)).size).toBe(result.storage.package_total_bytes);
  expect(createHash("sha256").update(downloadedBundle).digest("hex")).toBe(
    result.storage.package_sha256,
  );
});

test("native burst completes with explicit per-frame fallback", async ({ page }) => {
  await page.goto("/");
  await page.locator('input[type="file"]').setInputFiles(fallbackFiles);
  await expect(page.getByText("15 / 20 photos")).toBeVisible();

  await page.getByRole("button", { name: "Check these photos" }).click();
  const analysisRegion = page.getByRole("region", { name: "Most of these photos can share space" });
  await expect(analysisRegion.getByText("Ready to create", { exact: true })).toBeVisible();
  await expect(
    analysisRegion.getByText("13 photos can share space; 2 will stay whole.", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(analysisRegion.getByText("Kept whole", { exact: true })).toHaveCount(2);

  await page.getByRole("button", { name: "Create PhotoFold collection" }).click();
  await expect(page.getByRole("heading", { name: "Your photos were rebuilt, but quality was below our target" })).toBeVisible({
    timeout: 180_000,
  });

  const result = JSON.parse(
    await readFile(resolve(repositoryRoot, "artifacts/gate3/latest/result.json"), "utf8"),
  );
  expect(result.strategy).toBe("hybrid");
  expect(result.status).toBe("failed_quality");
  expect(result.shared_frame_count).toBe(13);
  expect(result.fallback_frame_count).toBe(2);
  const fallback = result.frames.find((frame: { storage_mode: string }) => frame.storage_mode === "independent_source");
  expect(fallback).toBeTruthy();
  await page.getByRole("button", {
    name: `Photo ${fallback.index + 1} Kept whole · match ${fallback.ssim.toFixed(4)}`,
  }).click();
  await expect(page.getByText(/did not line up closely enough with the others/)).toBeVisible();
  await expect(page.getByText(/inlier ratio/i)).toHaveCount(0);
  await expect(page.getByText(/needs PhotoFold to export photos/)).toBeVisible();
});
