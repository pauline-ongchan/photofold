import type { PrototypeAnalysis } from "@photofold/contracts/prototype-analysis";
import type { ErrorEnvelope } from "@photofold/contracts/prototype-error";
import type { PrototypeResult } from "@photofold/contracts/prototype-result";
import analysisSchema from "@photofold/contracts/schemas/prototype-analysis";
import errorSchema from "@photofold/contracts/schemas/prototype-error";
import resultSchema from "@photofold/contracts/schemas/prototype-result";
import Ajv, { type ValidateFunction } from "ajv";
import { createHash, randomUUID } from "node:crypto";
import { spawn } from "node:child_process";
import {
  copyFile,
  mkdir,
  readFile,
  rm,
  stat,
  writeFile,
} from "node:fs/promises";
import { basename, dirname, relative, resolve, sep } from "node:path";

const RUN_ID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const ALLOWED_UPLOAD_TYPES = new Set(["", "image/jpeg", "image/png", "image/webp"]);
const ajv = new Ajv({ allErrors: true, strict: false, validateFormats: false });
const validateAnalysis = ajv.compile(analysisSchema) as ValidateFunction<PrototypeAnalysis>;
const validateResult = ajv.compile(resultSchema) as ValidateFunction<PrototypeResult>;
const validateError = ajv.compile(errorSchema) as ValidateFunction<ErrorEnvelope>;

export type FrameAssetKind = "original" | "reconstruction" | "difference";

export class BridgeError extends Error {
  readonly envelope: ErrorEnvelope;
  readonly status: number;

  constructor(
    code: string,
    message: string,
    stage: string,
    status: number,
    frameIndices: number[] = [],
    debug: string | null = null,
  ) {
    super(message);
    this.status = status;
    this.envelope = {
      error: {
        code,
        message,
        stage,
        frame_indices: frameIndices,
        retryable: code === "JOB_BUSY",
        debug: process.env.NODE_ENV === "development" ? debug : null,
      },
    };
  }
}

function repositoryRoot(): string {
  if (process.env.PHOTOFOLD_REPOSITORY_ROOT) {
    return resolve(process.env.PHOTOFOLD_REPOSITORY_ROOT);
  }
  const cwd = resolve(/* turbopackIgnore: true */ process.cwd());
  return basename(cwd) === "web" && basename(dirname(cwd)) === "apps" ? resolve(cwd, "../..") : cwd;
}

export function gate3Root(): string {
  return resolve(repositoryRoot(), "artifacts/gate3");
}

function runsRoot(): string {
  return resolve(gate3Root(), "runs");
}

function assertInside(parent: string, child: string): string {
  const resolvedParent = resolve(parent);
  const resolvedChild = resolve(child);
  const relation = relative(resolvedParent, resolvedChild);
  if (relation === ".." || relation.startsWith(`..${sep}`) || resolve(resolvedChild) === resolve("/")) {
    throw new BridgeError(
      "UNSAFE_RUN_PATH",
      "The requested local artifact is outside its isolated run workspace.",
      "service",
      400,
    );
  }
  return resolvedChild;
}

export function validateRunId(runId: string): string {
  if (!RUN_ID_PATTERN.test(runId)) {
    throw new BridgeError("MOMENT_NOT_FOUND", "This local prototype run was not found.", "service", 404);
  }
  return runId;
}

export function runDirectory(runId: string): string {
  return assertInside(runsRoot(), resolve(runsRoot(), validateRunId(runId)));
}

export function runArtifact(runId: string, artifact: string): string {
  return assertInside(runDirectory(runId), resolve(runDirectory(runId), artifact));
}

export async function createRun(files: File[]): Promise<string> {
  if (files.length < 5 || files.length > 20) {
    throw new BridgeError(
      "INVALID_FILE_COUNT",
      "Choose between 5 and 20 photos before analyzing this moment.",
      "upload",
      422,
    );
  }
  const invalidType = files.findIndex((file) => !ALLOWED_UPLOAD_TYPES.has(file.type.toLowerCase()));
  if (invalidType >= 0) {
    throw new BridgeError(
      "UNSUPPORTED_FILE_TYPE",
      `${files[invalidType].name} is not a JPEG, PNG, or WebP image.`,
      "upload",
      422,
      [invalidType],
    );
  }
  const invalidName = files.findIndex((file) => file.name.length === 0 || file.name.length > 255);
  if (invalidName >= 0) {
    throw new BridgeError(
      "INVALID_FILENAME",
      "Every upload must have a filename no longer than 255 characters.",
      "upload",
      422,
      [invalidName],
    );
  }
  const runId = randomUUID();
  const directory = runDirectory(runId);
  const uploads = runArtifact(runId, "uploads");
  await mkdir(uploads, { recursive: true });
  const frames = [];
  for (const [index, file] of files.entries()) {
    const storedFilename = `frame-${String(index).padStart(3, "0")}.upload`;
    await writeFile(runArtifact(runId, `uploads/${storedFilename}`), Buffer.from(await file.arrayBuffer()), {
      flag: "wx",
    });
    frames.push({
      index,
      original_filename: file.name,
      stored_filename: storedFilename,
    });
  }
  await writeFile(
    resolve(directory, "input.json"),
    `${JSON.stringify({ schema_version: "1.0", frames }, null, 2)}\n`,
    { flag: "wx" },
  );
  return runId;
}

type CommandResult = { code: number; stdout: string; stderr: string };

export async function runProcessor(arguments_: string[]): Promise<CommandResult> {
  const root = repositoryRoot();
  const python = resolve(root, ".venv/bin/python");
  return new Promise((resolveCommand, reject) => {
    const child = spawn(python, ["-m", "photofold.cli", ...arguments_], {
      cwd: root,
      env: process.env,
      shell: false,
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk: string) => {
      stdout = `${stdout}${chunk}`.slice(-1_000_000);
    });
    child.stderr.on("data", (chunk: string) => {
      stderr = `${stderr}${chunk}`.slice(-1_000_000);
    });
    child.once("error", reject);
    child.once("close", (code) => resolveCommand({ code: code ?? 1, stdout, stderr }));
  });
}

function schemaFailure(label: string, validator: ValidateFunction): BridgeError {
  return new BridgeError(
    "PROCESSOR_CONTRACT_INVALID",
    `The processor returned an invalid ${label} contract.`,
    "service",
    500,
    [],
    ajv.errorsText(validator.errors),
  );
}

async function readValidated<T>(
  path: string,
  validator: ValidateFunction<T>,
  label: string,
): Promise<T> {
  let value: unknown;
  try {
    value = JSON.parse(await readFile(path, "utf8"));
  } catch (error) {
    throw new BridgeError(
      "PROCESSOR_CONTRACT_INVALID",
      `The processor did not write a readable ${label} result.`,
      "service",
      500,
      [],
      error instanceof Error ? error.message : String(error),
    );
  }
  if (!validator(value)) throw schemaFailure(label, validator);
  return value;
}

export async function readAnalysis(runId: string): Promise<PrototypeAnalysis> {
  return readValidated(runArtifact(runId, "analysis.json"), validateAnalysis, "analysis");
}

export async function readResult(runId: string): Promise<PrototypeResult> {
  return readValidated(runArtifact(runId, "result.json"), validateResult, "result");
}

async function processorError(runId: string, command: CommandResult): Promise<BridgeError> {
  try {
    const envelope = await readValidated(runArtifact(runId, "error.json"), validateError, "error");
    const clientStatus = new Set([
      "INVALID_FILE_COUNT",
      "UNSUPPORTED_FILE_TYPE",
      "IMAGE_DECODE_FAILED",
      "DIMENSIONS_INCOMPATIBLE",
      "CHECKSUM_MISMATCH",
      "INVALID_RUN_STATE",
    ]).has(envelope.error.code)
      ? 422
      : 500;
    return new BridgeError(
      envelope.error.code,
      envelope.error.message,
      envelope.error.stage,
      clientStatus,
      envelope.error.frame_indices,
      envelope.error.debug,
    );
  } catch (error) {
    if (error instanceof BridgeError && error.envelope.error.code !== "PROCESSOR_CONTRACT_INVALID") {
      return error;
    }
    return new BridgeError(
      "PROCESSOR_FAILED",
      "The deterministic processor could not complete this request.",
      "service",
      500,
      [],
      command.stderr || command.stdout,
    );
  }
}

export async function analyzeRun(runId: string): Promise<PrototypeAnalysis> {
  const command = await runProcessor([
    "prototype-analyze",
    "--run",
    runDirectory(runId),
    "--config",
    resolve(repositoryRoot(), "configs/gate1.yaml"),
  ]);
  if (command.code !== 0) throw await processorError(runId, command);
  return readAnalysis(runId);
}

export async function acquireFoldLock(): Promise<() => Promise<void>> {
  await mkdir(gate3Root(), { recursive: true });
  const lock = resolve(gate3Root(), "fold.lock");
  try {
    await mkdir(lock);
  } catch (error) {
    const code = error && typeof error === "object" && "code" in error ? error.code : undefined;
    if (code === "EEXIST") {
      throw new BridgeError(
        "JOB_BUSY",
        "Another local PhotoFold run is already folding. Try again when it finishes.",
        "service",
        409,
      );
    }
    throw error;
  }
  return () => rm(lock, { recursive: true, force: true });
}

export async function foldRun(runId: string): Promise<PrototypeResult> {
  await readAnalysis(runId);
  const release = await acquireFoldLock();
  try {
    const command = await runProcessor([
      "prototype-fold",
      "--run",
      runDirectory(runId),
      "--config",
      resolve(repositoryRoot(), "configs/gate1.yaml"),
    ]);
    if (command.code !== 0) {
      try {
        return await readResult(runId);
      } catch {
        throw await processorError(runId, command);
      }
    }
    return await readResult(runId);
  } finally {
    await release();
  }
}

export async function frameAsset(
  runId: string,
  index: number,
  kind: FrameAssetKind,
): Promise<{ path: string; contentType: string }> {
  if (!Number.isInteger(index) || index < 0 || index > 19) {
    throw new BridgeError("MOMENT_NOT_FOUND", "This frame was not found.", "service", 404);
  }
  if (kind === "original") {
    const analysis = await readAnalysis(runId);
    const frame = analysis.source_frames[index];
    if (!frame || frame.index !== index) {
      throw new BridgeError("MOMENT_NOT_FOUND", "This frame was not found.", "service", 404);
    }
    return { path: runArtifact(runId, frame.original_artifact), contentType: frame.mime_type };
  }
  const result = await readResult(runId);
  const frame = result.frames[index];
  const relativePath = kind === "reconstruction" ? frame?.artifacts.reconstruction : frame?.artifacts.difference;
  if (!frame || frame.index !== index || !relativePath) {
    throw new BridgeError("INVALID_RUN_STATE", "This generated frame is not available.", "service", 409);
  }
  return { path: runArtifact(runId, relativePath), contentType: "image/png" };
}

export async function readBinary(path: string): Promise<Buffer> {
  const fileStat = await stat(path);
  if (!fileStat.isFile()) {
    throw new BridgeError("MOMENT_NOT_FOUND", "This local artifact was not found.", "service", 404);
  }
  return readFile(path);
}

export function responseBody(payload: Buffer): ArrayBuffer {
  const copy = new Uint8Array(payload.byteLength);
  copy.set(payload);
  return copy.buffer;
}

export async function exportFrame(
  runId: string,
  index: number,
): Promise<{ payload: Buffer; filename: string }> {
  const result = await readResult(runId);
  const frame = result.frames[index];
  if (!frame || !frame.reconstructed || !result.package_artifact) {
    throw new BridgeError("INVALID_RUN_STATE", "This frame is not ready to export.", "service", 409);
  }
  const output = runArtifact(runId, "exported-frame.webp");
  const command = await runProcessor([
    "export",
    runArtifact(runId, result.package_artifact),
    "--frame",
    String(index),
    "--format",
    "webp",
    "--output",
    output,
  ]);
  if (command.code !== 0) throw await processorError(runId, command);
  await mkdir(resolve(gate3Root(), "latest"), { recursive: true });
  await copyFile(output, resolve(gate3Root(), "latest/exported-frame.webp"));
  return { payload: await readBinary(output), filename: `PhotoFold-frame-${String(index).padStart(3, "0")}.webp` };
}

export async function bundle(runId: string): Promise<Buffer> {
  const result = await readResult(runId);
  if (!result.storage || !result.package_artifact) {
    throw new BridgeError("INVALID_RUN_STATE", "This PhotoFold bundle is not available.", "service", 409);
  }
  const payload = await readBinary(runArtifact(runId, result.package_artifact));
  const digest = createHash("sha256").update(payload).digest("hex");
  if (payload.byteLength !== result.storage.package_total_bytes || digest !== result.storage.package_sha256) {
    throw new BridgeError(
      "PACKAGE_VALIDATION_FAILED",
      "The downloadable bundle no longer matches the measured result.",
      "package",
      500,
    );
  }
  return payload;
}

export async function removeRun(runId: string): Promise<void> {
  await rm(runDirectory(runId), { recursive: true, force: true });
}

export function downloadHeaders(contentType: string, filename?: string, length?: number): Headers {
  const headers = new Headers({
    "Cache-Control": "no-store",
    "Content-Type": contentType,
  });
  if (filename) headers.set("Content-Disposition", `attachment; filename="${basename(filename)}"`);
  if (length !== undefined) headers.set("Content-Length", String(length));
  return headers;
}
