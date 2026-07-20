// @vitest-environment node

import { EventEmitter } from "node:events";
import { PassThrough } from "node:stream";
import { beforeEach, expect, it, vi } from "vitest";

const spawnMock = vi.fn();

vi.mock("node:child_process", () => ({ spawn: spawnMock }));

beforeEach(() => {
  spawnMock.mockReset();
  process.env.PHOTOFOLD_REPOSITORY_ROOT = "/tmp/photofold-command-test";
});

it("uses a fixed argument vector with shell execution disabled", async () => {
  const child = new EventEmitter() as EventEmitter & {
    stdout: PassThrough;
    stderr: PassThrough;
  };
  child.stdout = new PassThrough();
  child.stderr = new PassThrough();
  spawnMock.mockReturnValue(child);
  const { runProcessor } = await import("./prototype-server");

  const pending = runProcessor(["prototype-fold", "--run", "/safe/run"]);
  child.emit("close", 0);
  await expect(pending).resolves.toMatchObject({ code: 0 });

  expect(spawnMock).toHaveBeenCalledWith(
    "/tmp/photofold-command-test/.venv/bin/python",
    ["-m", "photofold.cli", "prototype-fold", "--run", "/safe/run"],
    expect.objectContaining({
      cwd: "/tmp/photofold-command-test",
      shell: false,
      stdio: ["ignore", "pipe", "pipe"],
    }),
  );
});
