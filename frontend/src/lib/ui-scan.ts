// The operator-grade UI scan (`npm run lint:ui`). Each rule is a pattern that
// marks the generic template look or an escape hatch; zero hits is the pass.
// This file and its test hold the patterns themselves, so they are excluded
// from the scan, as is the one file allowed to hold literal colors.
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";

export interface ScanRule {
  readonly id: string;
  readonly why: string;
  readonly pattern: RegExp;
}

export interface ScanHit {
  readonly file: string;
  readonly line: number;
  readonly rule: string;
  readonly text: string;
}

const PALETTE =
  "slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose|white|black";

export const RULES: readonly ScanRule[] = [
  { id: "gradient", why: "no gradients", pattern: /gradient/ },
  { id: "blur", why: "no glass or blur", pattern: /backdrop-blur/ },
  {
    id: "radius",
    why: "radius above 4px",
    pattern: /rounded-(md|lg|xl|2xl|3xl)/,
  },
  {
    id: "shadow",
    why: "shadow on a static panel",
    pattern: /shadow-(sm|md|lg|xl|2xl)/,
  },
  {
    id: "purple",
    why: "indigo, violet or purple accent",
    pattern: /(indigo|violet|purple|fuchsia)-[0-9]{2,3}/,
  },
  { id: "big-text", why: "text above 20px", pattern: /text-([3-9]xl)/ },
  {
    id: "motion",
    why: "bounce or pulse animation",
    pattern: /animate-(bounce|pulse)/,
  },
  {
    id: "palette",
    why: "a Tailwind palette color instead of a token",
    pattern: new RegExp(`\\b[a-z]+-(${PALETTE})(-[0-9]{2,3})?\\b`),
  },
  {
    id: "arbitrary-px",
    why: "an arbitrary pixel value off the token scale",
    pattern: /\b[a-z-]+-\[-?[0-9.]+px\]/,
  },
  {
    id: "hex",
    why: "a literal color outside tokens.css",
    pattern: /#[0-9a-fA-F]{3,8}\b|rgba?\(/,
  },
  {
    id: "emoji",
    why: "emoji in the UI",
    pattern: /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u,
  },
  {
    id: "suppression",
    why: "a compiler or linter suppression",
    pattern: /@ts-ignore|@ts-expect-error|eslint-disable|: any\b|as any\b/,
  },
];

const SCANNED = /\.(tsx?|css|mjs)$/;
const EXCLUDED = new Set(["lib/ui-scan.ts", "lib/ui-scan.test.ts"]);
const COLOR_HOME = "styles/tokens.css";

function rulesFor(file: string): readonly ScanRule[] {
  return file === COLOR_HOME ? RULES.filter((r) => r.id !== "hex") : RULES;
}

/** Every rule hit in one file's text, one per rule per line. */
export function scanText(file: string, text: string): readonly ScanHit[] {
  const rules = rulesFor(file);
  return text.split("\n").flatMap((line, index) =>
    rules
      .filter((rule) => rule.pattern.test(line))
      .map((rule) => ({
        file,
        line: index + 1,
        rule: rule.id,
        text: line.trim(),
      })),
  );
}

function listFiles(root: string): readonly string[] {
  const pending = [root];
  const found: string[] = [];
  for (let dir = pending.pop(); dir !== undefined; dir = pending.pop()) {
    for (const entry of readdirSync(dir)) {
      const path = join(dir, entry);
      if (statSync(path).isDirectory()) {
        pending.push(path);
      } else if (SCANNED.test(entry)) {
        found.push(path);
      }
    }
  }
  return found;
}

/** Scan a source tree; paths in hits are relative to `root`, with `/`. */
export function scanTree(root: string): readonly ScanHit[] {
  return listFiles(root)
    .map((path) => relative(root, path).split(sep).join("/"))
    .filter((file) => !EXCLUDED.has(file))
    .flatMap((file) => scanText(file, readFileSync(join(root, file), "utf8")));
}
