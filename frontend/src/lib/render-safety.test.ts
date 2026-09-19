/**
 * The brief reaches the page as text, never as markup.
 *
 * docs/backlog/13-brief-output-allowlist.md asks that an `<img src>` in chunk
 * text cannot reach the rendered page. The guarantee here is structural rather
 * than a sanitizer: the brief is interpolated as a JSX text child, and React
 * escapes those. A sanitizer is a thing that can have a bypass; escaping by
 * construction is not.
 *
 * These assertions are over the source, because the invariant IS a property of
 * the source. Adding jsdom and a rendering harness to assert it would test
 * React's escaping, which is not ours to test.
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const SRC_ROOT = join(process.cwd(), "src");

function sourceFiles(directory: string): readonly string[] {
  const found: string[] = [];
  for (const entry of readdirSync(directory)) {
    const path = join(directory, entry);
    if (statSync(path).isDirectory()) {
      found.push(...sourceFiles(path));
      continue;
    }
    if (/\.tsx?$/.test(entry) && !/\.test\.tsx?$/.test(entry)) {
      found.push(path);
    }
  }
  return found;
}

describe("brief rendering", () => {
  it("never uses dangerouslySetInnerHTML anywhere in the app", () => {
    const offenders = sourceFiles(SRC_ROOT).filter((path) =>
      readFileSync(path, "utf8").includes("dangerouslySetInnerHTML"),
    );

    expect(offenders).toEqual([]);
  });

  it("renders the report as a JSX text child", () => {
    const panel = readFileSync(
      join(SRC_ROOT, "app", "components", "ResultsPanel.tsx"),
      "utf8",
    );

    expect(panel).toContain("{result.report}");
  });

  it("pulls in no markdown-to-HTML renderer", () => {
    // JSON.parse returns `any`; narrow it rather than assert it, since `any`
    // here would switch off the checking this file exists to perform.
    const parsed: unknown = JSON.parse(
      readFileSync(join(process.cwd(), "package.json"), "utf8"),
    );
    const dependencies: unknown =
      typeof parsed === "object" && parsed !== null
        ? (parsed as Record<string, unknown>).dependencies
        : undefined;
    const names: readonly string[] =
      typeof dependencies === "object" && dependencies !== null
        ? Object.keys(dependencies)
        : [];

    // A renderer added later is where an <img> would find its way in, so the
    // failure should land on whoever adds it, not on whoever ships after them.
    expect(
      names.filter((name) =>
        /markdown|remark|rehype|marked|sanitize/i.test(name),
      ),
    ).toEqual([]);
  });
});
