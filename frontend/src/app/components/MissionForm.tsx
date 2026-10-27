"use client";

import { useEffect, useState } from "react";
import type { JSX } from "react";

import { getCurrentCoordinates } from "@/lib/geo";
import type {
  AircraftSummary,
  MissionParams,
  MissionRequest,
  PayloadSummary,
} from "@/lib/types";

import { CatalogStatus } from "./CatalogStatus";
import { LocationFields } from "./LocationFields";
import { MissionParamFields } from "./MissionParamFields";
import { SelectField } from "./SelectField";
import type { SelectOption } from "./SelectField";

interface MissionFormProps {
  readonly loading: boolean;
  readonly aircraft: readonly AircraftSummary[];
  readonly payloads: readonly PayloadSummary[];
  readonly catalogLoading: boolean;
  readonly catalogError: string | null;
  readonly onAnalyze: (request: MissionRequest) => void;
}

function toOptions(
  items: readonly { readonly id: string; readonly name: string }[],
): readonly SelectOption[] {
  return items.map((item) => ({ value: item.id, label: item.name }));
}

function parseParam(value: string): number | null {
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : null;
}

interface RawParams {
  readonly distanceM: string;
  readonly hoverTimeS: string;
  readonly targetAltitudeM: string;
  readonly elevationM: string;
  readonly latitude: string;
  readonly longitude: string;
}

function buildMissionParams(raw: RawParams): MissionParams | null {
  const distance = parseParam(raw.distanceM);
  const hover = parseParam(raw.hoverTimeS);
  const altitude = parseParam(raw.targetAltitudeM);
  const elevation = parseParam(raw.elevationM);
  const lat = parseParam(raw.latitude);
  const lon = parseParam(raw.longitude);
  if (
    distance === null ||
    hover === null ||
    altitude === null ||
    elevation === null ||
    lat === null ||
    lon === null
  ) {
    return null;
  }
  return {
    distance_m: distance,
    hover_time_s: hover,
    target_altitude_m: altitude,
    elevation_m: elevation,
    latitude: lat,
    longitude: lon,
  };
}

type FormResult =
  | { readonly ok: true; readonly request: MissionRequest }
  | { readonly ok: false; readonly error: string };

/** Validate the raw form state into a request, or explain why it cannot be. */
function buildMissionRequest(
  aircraftId: string,
  payloadId: string,
  raw: RawParams,
): FormResult {
  if (aircraftId === "" || payloadId === "") {
    return {
      ok: false,
      error: "Select an aircraft and payload before analyzing.",
    };
  }
  const missionParams = buildMissionParams(raw);
  if (missionParams === null) {
    return {
      ok: false,
      error:
        "All numeric fields, including latitude and longitude, are required.",
    };
  }
  return {
    ok: true,
    request: {
      aircraft_id: aircraftId,
      payload_id: payloadId,
      mission_params: missionParams,
      thread_id: null,
    },
  };
}

function FormFooter({
  error,
  loading,
  disabled,
}: {
  readonly error: string | null;
  readonly loading: boolean;
  readonly disabled: boolean;
}): JSX.Element {
  return (
    <>
      {error !== null && (
        <p
          className="border-l-2 border-critical bg-critical-tint px-2 py-1 text-sm text-fg"
          role="alert"
        >
          {error}
        </p>
      )}
      <button
        type="submit"
        disabled={disabled}
        className="btn btn-primary w-full"
      >
        {loading
          ? "Processing environment and metrics..."
          : "Analyze flight feasibility"}
      </button>
    </>
  );
}

export function MissionForm(props: MissionFormProps): JSX.Element {
  const {
    loading,
    aircraft,
    payloads,
    catalogLoading,
    catalogError,
    onAnalyze,
  } = props;
  const [aircraftId, setAircraftId] = useState("");
  const [payloadId, setPayloadId] = useState("");
  const [distanceM, setDistanceM] = useState("5000");
  const [hoverTimeS, setHoverTimeS] = useState("600");
  const [targetAltitudeM, setTargetAltitudeM] = useState("120");
  const [elevationM, setElevationM] = useState("0");
  const [latitude, setLatitude] = useState("");
  const [longitude, setLongitude] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  // Default the selection to the first catalog entry once it loads.
  useEffect(() => {
    if (aircraftId === "" && aircraft.length > 0) {
      setAircraftId(aircraft[0]?.id ?? "");
    }
    if (payloadId === "" && payloads.length > 0) {
      setPayloadId(payloads[0]?.id ?? "");
    }
  }, [aircraft, payloads, aircraftId, payloadId]);

  function locate(): void {
    setFormError(null);
    void getCurrentCoordinates().then((result) => {
      if (!result.ok) {
        setFormError(`Location acquisition failed: ${result.error}`);
        return;
      }
      setLatitude(result.data.latitude.toFixed(4));
      setLongitude(result.data.longitude.toFixed(4));
    });
  }

  function submit(): void {
    setFormError(null);
    const result = buildMissionRequest(aircraftId, payloadId, {
      distanceM,
      hoverTimeS,
      targetAltitudeM,
      elevationM,
      latitude,
      longitude,
    });
    if (!result.ok) {
      setFormError(result.error);
      return;
    }
    onAnalyze(result.request);
  }

  return (
    <section
      className="flex w-form shrink-0 flex-col border-r border-line bg-panel"
      aria-labelledby="mission-heading"
    >
      <div className="panel-header">
        <h2 id="mission-heading" className="section-label">
          Mission configuration
        </h2>
      </div>
      <form
        className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3"
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <CatalogStatus loading={catalogLoading} error={catalogError} />
        <SelectField
          id="aircraft"
          label="Aircraft platform"
          value={aircraftId}
          options={toOptions(aircraft)}
          onChange={setAircraftId}
        />
        <SelectField
          id="payload"
          label="Payload system"
          value={payloadId}
          options={toOptions(payloads)}
          onChange={setPayloadId}
        />
        <MissionParamFields
          distanceM={distanceM}
          hoverTimeS={hoverTimeS}
          targetAltitudeM={targetAltitudeM}
          elevationM={elevationM}
          onDistanceChange={setDistanceM}
          onHoverTimeChange={setHoverTimeS}
          onTargetAltitudeChange={setTargetAltitudeM}
          onElevationChange={setElevationM}
        />
        <LocationFields
          latitude={latitude}
          longitude={longitude}
          onLatitudeChange={setLatitude}
          onLongitudeChange={setLongitude}
          onLocate={locate}
        />
        <FormFooter
          error={formError}
          loading={loading}
          disabled={loading || catalogLoading || aircraft.length === 0}
        />
      </form>
    </section>
  );
}
