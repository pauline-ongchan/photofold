// @vitest-environment node

import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  acquireFoldLock,
  BridgeError,
  createRun,
  runArtifact,
  runDirectory,
  validateRunId,
} from "./prototype-server";

let root: string;

beforeEach(async () => {
  root = await mkdtemp(join(tmpdir(), "photofold-web-test-"));
  process.env.PHOTOFOLD_REPOSITORY_ROOT = root;
});

afterEach(async () => {
  delete process.env.PHOTOFOLD_REPOSITORY_ROOT;
  await rm(root, { recursive: true, force: true });
});

describe("prototype workspace safety", () => {
  it("rejects invalid and traversal-shaped run identifiers", () => {
    expect(() => validateRunId("../../outside")).toThrow(BridgeError);
    expect(() => runDirectory("00000000-0000-0000-0000-000000000000")).toThrow(
      BridgeError,
    );
  });

  it("stores hostile original names only as JSON metadata", async () => {
    const files = Array.from(
      { length: 5 },
      (_, index) => new File([`payload-${index}`], index === 0 ? "../../face.jpg" : `face-${index}.jpg`, {
        type: "image/jpeg",
      }),
    );

    const runId = await createRun(files);
    const input = JSON.parse(await readFile(runArtifact(runId, "input.json"), "utf8"));

    expect(input.frames[0].original_filename).toBe("../../face.jpg");
    expect(input.frames.map((frame: { stored_filename: string }) => frame.stored_filename)).toEqual([
      "frame-000.upload",
      "frame-001.upload",
      "frame-002.upload",
      "frame-003.upload",
      "frame-004.upload",
    ]);
    expect(() => runArtifact(runId, "../../outside")).toThrow(BridgeError);
  });

  it("allows exactly one active fold lock and releases it explicitly", async () => {
    const release = await acquireFoldLock();
    await expect(acquireFoldLock()).rejects.toMatchObject({
      status: 409,
      envelope: { error: { code: "JOB_BUSY" } },
    });
    await release();
    const releaseAgain = await acquireFoldLock();
    await releaseAgain();
  });
});
