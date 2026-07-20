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
  await expect(page.getByText("7 / 20 frames")).toBeVisible();
  await expect(page.getByText("1600×1200")).toHaveCount(7);

  await page.getByRole("button", { name: "Remove frame-006.jpg" }).click();
  await expect(page.getByText("6 / 20 frames")).toBeVisible();
  await input.setInputFiles(files[6]);
  await expect(page.getByText("7 / 20 frames")).toBeVisible();

  await page.getByRole("button", { name: "Analyze this moment" }).click();
  await expect(page.getByRole("heading", { name: "Processor analysis" })).toBeVisible();
  const analysisRegion = page.getByRole("region", { name: "Processor analysis" });
  await expect(analysisRegion.getByText("Ready to fold", { exact: true })).toBeVisible();
  await expect(analysisRegion.getByText("7 frames can share scene data.", { exact: true })).toBeVisible();
  await expect(analysisRegion.getByText(/estimated shared region percent/)).toBeVisible();

  await page.getByRole("button", { name: "Fold this moment" }).click();
  await expect(page.getByRole("heading", { name: "Moment folded successfully" })).toBeVisible({
    timeout: 120_000,
  });
  await expect(page.getByText("7 reconstructions")).toBeVisible();

  const resultPath = resolve(repositoryRoot, "artifacts/gate3/latest/result.json");
  const result = JSON.parse(await readFile(resultPath, "utf8"));
  expect(result.status).toBe("complete");
  expect(result.reconstructed_frame_count).toBe(7);
  expect(result.storage.package_total_bytes).toBeGreaterThan(0);
  expect(result.storage.package_total_bytes).toBeLessThan(result.storage.original_total_bytes);
  await expect(page.getByText("Saved vs uploads")).toBeVisible();
  await expect(page.getByText(`${result.quality.mean_ssim.toFixed(4)} / ${result.quality.minimum_ssim.toFixed(4)}`)).toBeVisible();

  await page.getByRole("button", { name: "Heatmap" }).click();
  const difference = page.getByRole("img", { name: "difference for frame-000.jpg" });
  await expect(difference).toBeVisible();
  await expect.poll(() => difference.evaluate((image: HTMLImageElement) => image.naturalWidth)).toBeGreaterThan(0);
  await expect(page.getByLabel("Frame browser").getByRole("button")).toHaveCount(7);

  const frameSeven = page.getByRole("button", {
    name: `Frame 7 Shared · ${result.frames[6].ssim.toFixed(4)}`,
  });
  await frameSeven.click();
  await expect(page.getByRole("heading", { name: "Frame 7 · frame-006.jpg" })).toBeVisible();

  const exportDownloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: "Export selected photo" }).click();
  const exportDownload = await exportDownloadPromise;
  const exportPath = testInfo.outputPath("PhotoFold-frame-006.webp");
  await exportDownload.saveAs(exportPath);
  const exported = await readFile(exportPath);
  expect(exported.subarray(0, 4).toString("ascii")).toBe("RIFF");
  expect(exported.subarray(8, 12).toString("ascii")).toBe("WEBP");

  const bundleDownloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download PhotoFold archive" }).click();
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
  await expect(page.getByText("15 / 20 frames")).toBeVisible();

  await page.getByRole("button", { name: "Analyze this moment" }).click();
  const analysisRegion = page.getByRole("region", { name: "Processor analysis" });
  await expect(analysisRegion.getByText("Ready to fold", { exact: true })).toBeVisible();
  await expect(
    analysisRegion.getByText("13 frames can share scene data; 2 will be stored independently.", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(analysisRegion.getByText("Fallback", { exact: true })).toHaveCount(2);

  await page.getByRole("button", { name: "Fold this moment" }).click();
  await expect(page.getByRole("heading", { name: "Fold measured — quality threshold missed" })).toBeVisible({
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
    name: `Frame ${fallback.index + 1} Fallback · ${fallback.ssim.toFixed(4)}`,
  }).click();
  await expect(page.getByText(/Fallback: Alignment fallback/)).toBeVisible();
  await expect(page.getByText("Requires PhotoFold to reconstruct the complete set.")).toBeVisible();
});
