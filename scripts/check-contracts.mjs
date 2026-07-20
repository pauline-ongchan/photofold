import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";

const directory = mkdtempSync(join(tmpdir(), "photofold-contracts-"));
const openapi = join(directory, "openapi.json");
const generated = join(directory, "generated.ts");
const phase1bSchemas = join(directory, "phase1b-schemas");

try {
  const python = spawnSync(
    ".venv/bin/python",
    ["-m", "photofold.cli", "export-openapi", "--output", openapi],
    { stdio: "inherit" },
  );
  if (python.status !== 0) process.exit(python.status ?? 1);

  const phase1b = spawnSync(
    ".venv/bin/python",
    [
      "-m",
      "photofold.cli",
      "export-phase1b-schemas",
      "--output-directory",
      phase1bSchemas,
    ],
    { stdio: "inherit" },
  );
  if (phase1b.status !== 0) process.exit(phase1b.status ?? 1);

  const generator = spawnSync(
    "node_modules/.bin/openapi-typescript",
    [openapi, "--output", generated],
    { stdio: "inherit" },
  );
  if (generator.status !== 0) process.exit(generator.status ?? 1);

  const comparisons = [
    [openapi, "packages/contracts/openapi.json"],
    [generated, "packages/contracts/src/generated.ts"],
    [
      join(phase1bSchemas, "phase1b-dataset-manifest.schema.json"),
      "packages/contracts/phase1b-dataset-manifest.schema.json",
    ],
    [
      join(phase1bSchemas, "phase1b-dataset-result.schema.json"),
      "packages/contracts/phase1b-dataset-result.schema.json",
    ],
    [
      join(phase1bSchemas, "phase1b-aggregate-result.schema.json"),
      "packages/contracts/phase1b-aggregate-result.schema.json",
    ],
    [
      join(phase1bSchemas, "phase1b-human-review.schema.json"),
      "packages/contracts/phase1b-human-review.schema.json",
    ],
  ];

  const stale = comparisons.filter(
    ([actual, expected]) =>
      readFileSync(actual, "utf8") !== readFileSync(expected, "utf8"),
  );

  if (stale.length > 0) {
    for (const [, expected] of stale) {
      console.error(`Generated contract is stale: ${expected}`);
    }
    console.error("Run: npm run contracts:generate");
    process.exit(1);
  }

  console.log("Generated contracts are current.");
} finally {
  rmSync(directory, { recursive: true, force: true });
}
