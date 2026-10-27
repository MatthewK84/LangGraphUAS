import { describe, expect, it } from "vitest";

import {
  ADVISORY_PLAN,
  OPERATIONAL_PLAN,
  REPLAN,
  REPLAN_SNAPSHOT,
} from "@/test/fixtures";

import {
  briefsPayload,
  buildSnapshot,
  replanVerdict,
  residualRows,
} from "./replan";

const PARAMS = {
  distance_m: 5000,
  hover_time_s: 600,
  target_altitude_m: 120,
  elevation_m: 0,
  latitude: 38.87114,
  longitude: -77.05581,
};

const INPUT = {
  socPercent: "42",
  remainingLegM: "1800",
  remainingHoverS: "60",
  oatC: "4",
  windMps: "6.1",
  payloadAttached: true,
};

const NOW = new Date("2026-10-27T14:03:11.000Z");

describe("telemetry snapshot (#94)", () => {
  it("sends state of charge as a fraction, from a percent typed", () => {
    const built = buildSnapshot("msn-3d90e6a4", PARAMS, INPUT, NOW);
    expect(built).toEqual({
      ok: true,
      snapshot: {
        thread_id: "msn-3d90e6a4",
        ts: "2026-10-27T14:03:11.000Z",
        latitude: 38.87114,
        longitude: -77.05581,
        alt_m: 120,
        soc_fraction: 0.42,
        remaining_leg_m: 1800,
        remaining_hover_s: 60,
        oat_c: 4,
        wind_mps: 6.1,
        payload_attached: true,
      },
    });
  });

  it("sends no wind when none is reported, rather than zero", () => {
    const built = buildSnapshot("t", PARAMS, { ...INPUT, windMps: "" }, NOW);
    expect(built.ok && built.snapshot.wind_mps).toBeNull();
  });

  it.each(["", "101", "-1", "abc"])(
    "refuses a state of charge of %j",
    (soc) => {
      const built = buildSnapshot(
        "t",
        PARAMS,
        { ...INPUT, socPercent: soc },
        NOW,
      );
      expect(built).toEqual({
        ok: false,
        error: "State of charge must be a number from 0 to 100.",
      });
    },
  );

  it("requires the remaining leg and outside air temperature", () => {
    const built = buildSnapshot("t", PARAMS, { ...INPUT, oatC: "" }, NOW);
    expect(built).toEqual({
      ok: false,
      error:
        "Remaining leg, hover time and outside air temperature are required.",
    });
  });
});

describe("residual comparison (#94)", () => {
  it("keeps the briefed figure beside the live one, with the delta", () => {
    const rows = residualRows(OPERATIONAL_PLAN, REPLAN_SNAPSHOT, REPLAN);
    expect(rows.find((row) => row.label === "Margin after mission")).toEqual({
      label: "Margin after mission",
      unit: "Wh",
      briefed: 41.7,
      live: 44.54,
      delta: 2.84,
    });
    expect(rows.find((row) => row.label === "Wind")).toEqual({
      label: "Wind",
      unit: "m/s",
      briefed: 3.9,
      live: 6.1,
      delta: 2.2,
    });
    expect(rows.find((row) => row.label === "State of charge")).toEqual({
      label: "State of charge",
      unit: "%",
      briefed: 100,
      live: 42,
      delta: -58,
    });
  });

  it("shows no wind delta when the snapshot reported none", () => {
    const calm = { ...REPLAN_SNAPSHOT, wind_mps: null };
    const wind = residualRows(ADVISORY_PLAN, calm, REPLAN).find(
      (row) => row.label === "Wind",
    );
    expect(wind).toMatchObject({ live: null, delta: null });
  });
});

describe("replan verdict (#94)", () => {
  it("makes one watch alert advisory, whatever the plan was", () => {
    expect(replanVerdict(OPERATIONAL_PLAN, REPLAN)).toEqual({
      mode: "advisory",
      action: "Advisory only",
      tone: "caution",
    });
  });

  it("keeps a clean replan of an operational plan operational", () => {
    const clean = {
      ...REPLAN,
      operational_ok: true,
      severity: "info",
      alerts: [],
    } as const;
    expect(replanVerdict(OPERATIONAL_PLAN, clean).mode).toBe("operational");
  });

  it("never upgrades an advisory plan on a clean replan", () => {
    const clean = {
      ...REPLAN,
      operational_ok: true,
      severity: "info",
      alerts: [],
    } as const;
    expect(replanVerdict(ADVISORY_PLAN, clean).mode).toBe("advisory");
  });

  it("marks a land-now finding critical", () => {
    const abort = {
      ...REPLAN,
      severity: "abort",
      recommended_action: "land_now",
    } as const;
    expect(replanVerdict(OPERATIONAL_PLAN, abort)).toMatchObject({
      action: "Land now",
      tone: "critical",
    });
  });
});

describe("briefed payload (#94)", () => {
  const payloads = [
    { id: "None", name: "No Payload", weight_kg: 0, power_draw_w: 0 },
    { id: "FLIR", name: "FLIR", weight_kg: 0.037, power_draw_w: 3 },
  ];

  // The backend raises PAYLOAD_MISMATCH against a weighted payload, so the
  // form starts from what was briefed rather than from "attached".
  it("starts attached only when the brief carried a payload with weight", () => {
    expect(briefsPayload(payloads, "FLIR")).toBe(true);
    expect(briefsPayload(payloads, "None")).toBe(false);
    expect(briefsPayload(payloads, "unknown")).toBe(false);
  });
});
