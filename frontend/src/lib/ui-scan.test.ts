// `npm run lint:ui`: the banned-pattern scan from the operator-grade UI
// standard. Each rule is proven on a probe, then the real tree must be clean.
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { RULES, scanText, scanTree } from "./ui-scan";

const EMOJI = String.fromCodePoint(0x1f680);

const PROBES: Readonly<Record<string, string>> = {
  gradient: 'className="bg-gradient-to-r"',
  blur: 'className="backdrop-blur-sm"',
  radius: 'className="rounded-xl"',
  shadow: 'className="shadow-lg"',
  purple: 'className="text-violet-500"',
  "big-text": 'className="text-3xl"',
  motion: 'className="animate-pulse"',
  palette: 'className="bg-slate-800"',
  "arbitrary-px": 'className="w-[317px]"',
  hex: "color: #1e293b;",
  emoji: `<span>${EMOJI}</span>`,
  suppression: "const x = y as any;",
};

function rulesHit(text: string, file = "app/probe.tsx"): readonly string[] {
  return scanText(file, text).map((hit) => hit.rule);
}

describe("ui scan rules", () => {
  it("has a probe for every rule", () => {
    expect(Object.keys(PROBES).sort()).toEqual(RULES.map((r) => r.id).sort());
  });

  it.each(Object.entries(PROBES))("%s catches its probe", (rule, probe) => {
    expect(rulesHit(probe)).toContain(rule);
  });

  it("passes token-backed utilities", () => {
    const line =
      'className="bg-panel text-fg-muted border-line rounded-sm text-2xl"';
    expect(rulesHit(line)).toEqual([]);
  });

  it("lets only tokens.css hold literal colors", () => {
    expect(rulesHit("--bg-app: #0b0e12;", "styles/tokens.css")).toEqual([]);
    expect(rulesHit("--bg-app: #0b0e12;", "app/globals.css")).toEqual(["hex"]);
  });
});

describe("source tree", () => {
  it("has no banned pattern anywhere under src", () => {
    const hits = scanTree(join(process.cwd(), "src")).map(
      (hit) => `${hit.file}:${String(hit.line)} [${hit.rule}] ${hit.text}`,
    );
    expect(hits).toEqual([]);
  });
});
