import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { ALERT_CODES, SEVERITY } from "./alerts";

const SCHEMA = resolve(__dirname, "../../../backend/suas/schemas/alerts.py");

/** The values of one backend StrEnum, read from its source. */
function backendEnum(name: string): readonly string[] {
  const text = readFileSync(SCHEMA, "utf-8");
  const pattern = new RegExp(`class ${name}\\(StrEnum\\):([\\s\\S]*?)\\n\\S`);
  const body = pattern.exec(text)?.[1] ?? "";
  return [...body.matchAll(/^ {4}[A-Z_]+ = "([A-Za-z_]+)"$/gm)].map(
    (match) => match[1] ?? "",
  );
}

describe("replan alert configuration (#94)", () => {
  it("describes every alert code the backend can raise", () => {
    expect(backendEnum("AlertCode").length).toBeGreaterThanOrEqual(6);
    expect(Object.keys(ALERT_CODES).sort()).toEqual(
      [...backendEnum("AlertCode")].sort(),
    );
  });

  it("gives every severity a treatment", () => {
    expect(Object.keys(SEVERITY).sort()).toEqual(
      [...backendEnum("Severity")].sort(),
    );
  });

  it("never paints a replan finding green", () => {
    for (const severity of Object.values(SEVERITY)) {
      expect(severity.tone).not.toBe("ok");
    }
  });
});
