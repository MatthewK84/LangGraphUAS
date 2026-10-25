// The lint config is a gate, so its rules get tests like any other gate:
// each test lints a small probe through the real eslint.config.mjs, using the
// same CLI that `npm run lint` runs.
import { spawnSync } from "node:child_process";
import path from "node:path";

import { describe, expect, it } from "vitest";

// An existing source file, so the type-aware project service accepts the path;
// --stdin lints the probe text, not the file's contents.
const PROBE_PATH = "src/lib/geo.ts";
const ESLINT_BIN = path.join(process.cwd(), "node_modules", ".bin", "eslint");

interface LintMessage {
  ruleId: string | null;
  message: string;
  fatal?: boolean;
}

interface LintResult {
  messages: LintMessage[];
}

function branchyFunction(branches: number): string {
  const cases = Array.from(
    { length: branches },
    (_, i) => `  if (n === ${String(i)}) {\n    return ${String(i)};\n  }\n`,
  ).join("");
  return `export function probe(n: number): number {\n${cases}  return -1;\n}\n`;
}

function lint(code: string): LintMessage[] {
  const run = spawnSync(
    ESLINT_BIN,
    ["--stdin", "--stdin-filename", PROBE_PATH, "--format", "json"],
    { input: code, encoding: "utf-8" },
  );
  const results = JSON.parse(run.stdout) as LintResult[];
  const messages = results.flatMap((result) => result.messages);
  // A parse or config failure must not pass as "no complexity message".
  expect(messages.filter((message) => message.fatal === true)).toEqual([]);
  return messages;
}

function complexityMessages(code: string): string[] {
  return lint(code)
    .filter((message) => message.ruleId === "complexity")
    .map((message) => message.message);
}

describe("complexity rule", () => {
  it("fails a function with cyclomatic complexity 11", () => {
    expect(complexityMessages(branchyFunction(10))).toHaveLength(1);
  }, 60_000);

  it("allows a function with cyclomatic complexity 10", () => {
    expect(complexityMessages(branchyFunction(9))).toEqual([]);
  }, 60_000);
});
