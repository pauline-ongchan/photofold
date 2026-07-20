import { mkdirSync } from "node:fs";
import { spawnSync } from "node:child_process";

mkdirSync("packages/contracts/src", { recursive: true });

const python = spawnSync(
  ".venv/bin/python",
  [
    "-m",
    "photofold.cli",
    "export-openapi",
    "--output",
    "packages/contracts/openapi.json",
  ],
  { stdio: "inherit" },
);

if (python.status !== 0) {
  process.exit(python.status ?? 1);
}

const phase1b = spawnSync(
  ".venv/bin/python",
  [
    "-m",
    "photofold.cli",
    "export-phase1b-schemas",
    "--output-directory",
    "packages/contracts",
  ],
  { stdio: "inherit" },
);

if (phase1b.status !== 0) {
  process.exit(phase1b.status ?? 1);
}

const generator = spawnSync(
  "node_modules/.bin/openapi-typescript",
  [
    "packages/contracts/openapi.json",
    "--output",
    "packages/contracts/src/generated.ts",
  ],
  { stdio: "inherit" },
);

process.exit(generator.status ?? 1);
