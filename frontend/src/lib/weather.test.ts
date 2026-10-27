import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { SOURCE_TREATMENT, sourceClass } from "./weather";

const SCHEMA = resolve(__dirname, "../../../backend/suas/schemas/responses.py");

/** The values of the backend's `WeatherSource` StrEnum, read from its source. */
function backendSources(): readonly string[] {
  const text = readFileSync(SCHEMA, "utf-8");
  const body = /class WeatherSource\(StrEnum\):([\s\S]*?)\n\S/.exec(text)?.[1];
  return [...(body ?? "").matchAll(/^ {4}[A-Z_]+ = "([a-z_]+)"$/gm)].map(
    (match) => match[1] ?? "",
  );
}

const sources = Object.keys(SOURCE_TREATMENT);

describe("weather source treatment (#93)", () => {
  it("has a rendering for every state the backend can send", () => {
    expect(backendSources().length).toBeGreaterThanOrEqual(6);
    expect([...sources].sort()).toEqual([...backendSources()].sort());
  });

  it("renders no two states alike", () => {
    const looks = sources.map(
      (source) =>
        `${SOURCE_TREATMENT[source as keyof typeof SOURCE_TREATMENT].label}|${sourceClass(source as keyof typeof SOURCE_TREATMENT)}`,
    );
    expect(new Set(looks).size).toBe(sources.length);
  });

  it("cannot style fallback as live", () => {
    expect(SOURCE_TREATMENT.fallback.tone).not.toBe(SOURCE_TREATMENT.live.tone);
    expect(sourceClass("fallback")).not.toBe(sourceClass("live"));
  });

  it("marks only live and cached_fresh as operational, like the backend", () => {
    const operational = sources.filter(
      (source) =>
        SOURCE_TREATMENT[source as keyof typeof SOURCE_TREATMENT].operational,
    );
    expect(operational.sort()).toEqual(["cached_fresh", "live"]);
  });

  it("gives the ok tone only to operational states", () => {
    for (const treatment of Object.values(SOURCE_TREATMENT)) {
      expect(treatment.tone === "ok").toBe(treatment.operational);
    }
  });
});
