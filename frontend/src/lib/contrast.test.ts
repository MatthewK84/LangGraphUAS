import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { contrastRatio, over } from "./contrast";

// WCAG 2.x AA for normal-size text: the banner's 12px caption and the 11px
// section labels are well under the 18.66px bold "large text" threshold.
const AA = 4.5;
// tailwind.config.ts mixes each status tint at this percentage.
const TINT = 0.14;

const TOKENS = readFileSync(
  join(__dirname, "..", "styles", "tokens.css"),
  "utf8",
);

/** The token values declared in the block whose selector contains `theme`. */
function palette(theme: string): Map<string, string> {
  const block = TOKENS.split("}").find((part) => part.includes(theme)) ?? "";
  const values = new Map<string, string>();
  for (const match of block.matchAll(/--([\w-]+):\s*(#[0-9a-f]{6});/g)) {
    values.set(match[1] ?? "", match[2] ?? "");
  }
  return values;
}

describe("contrastRatio", () => {
  const dark = palette('[data-theme="dark"]');
  const critical = dark.get("status-critical") ?? "";
  const panel = dark.get("bg-panel") ?? "";

  it("is 1 for a color on itself and symmetric", () => {
    expect(contrastRatio(critical, critical)).toBeCloseTo(1, 5);
    expect(contrastRatio(panel, critical)).toBe(contrastRatio(critical, panel));
  });

  it("matches the WCAG formula worked by hand for the dark tokens", () => {
    // Relative luminances 0.2870 and 0.0078, by the WCAG 2.x definition.
    expect(contrastRatio(critical, panel)).toBeCloseTo(5.83, 2);
  });

  it("composites a tint over its backdrop", () => {
    expect(over(critical, panel, 1)).toBe(critical);
    expect(over(critical, panel, 0)).toBe(panel);
    expect(contrastRatio(critical, over(critical, panel, TINT))).toBeCloseTo(
      4.89,
      2,
    );
  });
});

describe.each([
  ['[data-theme="dark"]', "dark"],
  ['[data-theme="light"]', "light"],
])("the NO-GO treatment in %s (#98)", (selector) => {
  const color = palette(selector);
  const token = (name: string): string => {
    const value = color.get(name);
    if (value === undefined) {
      throw new Error(`no --${name} in ${selector}`);
    }
    return value;
  };
  const tint = over(token("status-critical"), token("bg-panel"), TINT);

  it.each([
    ["the verdict", "status-critical"],
    ["the caption and thread", "text-secondary"],
    ["the thread id", "text-primary"],
  ])("keeps %s at AA on the critical tint", (_part, text) => {
    expect(contrastRatio(token(text), tint)).toBeGreaterThanOrEqual(AA);
  });

  it.each(["bg-panel", "bg-raised"])(
    "keeps the critical Abort and figures at AA on %s",
    (surface) => {
      expect(
        contrastRatio(token("status-critical"), token(surface)),
      ).toBeGreaterThanOrEqual(AA);
    },
  );
});
