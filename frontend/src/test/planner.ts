// Drive the whole planner page in jsdom: a stubbed backend and the operator's
// steps to an assessment. Used where a behaviour lives in how the page wires
// its panels together, not in any one component.
import { screen } from "@testing-library/react";
import type { UserEvent } from "@testing-library/user-event";
import { vi } from "vitest";

import type { AircraftSummary, PayloadSummary, PlanResult } from "@/lib/types";

const AIRCRAFT: readonly AircraftSummary[] = [
  {
    id: "dji_matrice_350_rtk",
    name: "DJI Matrice 350 RTK",
    max_payload_kg: 2.7,
    battery_wh: 263.2,
    max_wind_mps: 12,
    max_temp_c: 50,
  },
];

const PAYLOADS: readonly PayloadSummary[] = [
  {
    id: "zenmuse_h20t",
    name: "Zenmuse H20T",
    weight_kg: 0.828,
    power_draw_w: 26.4,
  },
];

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

/** Answer the catalog and every plan or ack call with the given plan. */
export function stubBackend(plan: PlanResult): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = input instanceof Request ? input.url : String(input);
      if (url.endsWith("/api/aircraft")) {
        return Promise.resolve(json(AIRCRAFT));
      }
      if (url.endsWith("/api/payloads")) {
        return Promise.resolve(json(PAYLOADS));
      }
      return Promise.resolve(json(plan));
    }),
  );
}

/** Fill the location and analyze, as an operator would. */
export async function analyzeMission(user: UserEvent): Promise<void> {
  await screen.findByRole("option", { name: AIRCRAFT[0]?.name ?? "" });
  await user.type(screen.getByLabelText(/Latitude/), "38.87114");
  await user.type(screen.getByLabelText(/Longitude/), "-77.05581");
  await user.click(
    screen.getByRole("button", { name: "Analyze flight feasibility" }),
  );
}
