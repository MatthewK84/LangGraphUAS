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

export function MissionForm(props: MissionFormProps): JSX.Element {
  const { loading, aircraft, payloads, catalogLoading, catalogError, onAnalyze } = props;
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
    if (aircraftId === "" || payloadId === "") {
      setFormError("Select an aircraft and payload before analyzing.");
      return;
    }
    const missionParams = buildMissionParams({
      distanceM,
      hoverTimeS,
      targetAltitudeM,
      elevationM,
      latitude,
      longitude,
    });
    if (missionParams === null) {
      setFormError("All numeric fields, including latitude and longitude, are required.");
      return;
    }
    onAnalyze({
      aircraft_id: aircraftId,
      payload_id: payloadId,
      mission_params: missionParams,
      thread_id: null,
    });
  }

  return (
    <div className="lg:col-span-1 bg-slate-800 p-6 rounded-xl border border-slate-700 shadow-xl h-fit">
      <h2 className="text-xl font-semibold mb-4 text-white">Mission Configuration</h2>
      <CatalogStatus loading={catalogLoading} error={catalogError} />
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <SelectField
          id="aircraft"
          label="Aircraft Platform"
          value={aircraftId}
          options={toOptions(aircraft)}
          onChange={setAircraftId}
        />
        <SelectField
          id="payload"
          label="Payload System"
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
        {formError !== null && (
          <p className="text-rose-400 text-xs" role="alert">
            {formError}
          </p>
        )}
        <button
          type="submit"
          disabled={loading || catalogLoading || aircraft.length === 0}
          className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 text-white font-semibold py-3 rounded-lg text-sm mt-4 transition-colors shadow-lg"
        >
          {loading ? "Processing environment and metrics..." : "Analyze flight feasibility"}
        </button>
      </form>
    </div>
  );
}
