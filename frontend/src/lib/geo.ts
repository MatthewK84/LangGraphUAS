// Promise wrapper around the browser geolocation API so callers can use
// async/await with a single typed error path (Principle 9).

import type { ApiResult } from "./types";

export interface Coordinates {
  readonly latitude: number;
  readonly longitude: number;
}

const GEO_TIMEOUT_MS = 10_000;

export async function getCurrentCoordinates(): Promise<ApiResult<Coordinates>> {
  if (typeof navigator === "undefined") {
    return { ok: false, error: "Geolocation is not available in this environment" };
  }
  return new Promise<ApiResult<Coordinates>>((resolve) => {
    navigator.geolocation.getCurrentPosition(
      (position) => {
        resolve({
          ok: true,
          data: {
            latitude: position.coords.latitude,
            longitude: position.coords.longitude,
          },
        });
      },
      (error) => {
        resolve({ ok: false, error: error.message });
      },
      { timeout: GEO_TIMEOUT_MS },
    );
  });
}
