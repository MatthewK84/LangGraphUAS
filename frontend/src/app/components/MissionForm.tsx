"use client";

import { useState } from "react";
import type { JSX } from "react";

import { getCurrentCoordinates } from "@/lib/geo";
import type { MissionRequest } from "@/lib/types";

import { LocationFields } from "./LocationFields";
import { NumberField } from "./NumberField";
import { SelectField } from "./SelectField";
import type { SelectOption } from "./SelectField";

interface MissionFormProps {
  readonly loading: boolean;
  readonly onAnalyze: (request: MissionRequest) => void;
}

const AIRCRAFT_OPTIONS: readonly SelectOption[] = [
  { value: "DJI_M350", label: "DJI Matrice 350 RTK" },
  { value: "Mavic_3_Ent", label: "DJI Mavic 3 Enterprise" },
];
const PAYLOAD_OPTIONS: readonly SelectOption[] = [
  { value: "Zenmuse_H30T", label: "Zenmuse H30T (Sensor)" },
  { value: "L1_LiDAR", label: "Zenmuse L1 (LiDAR)" },
  { value: "None", label: "No External Payload" },
];

function parseParam(value: string): number | null {
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function MissionForm(props: MissionFormProps): JSX.Element {
  const { loading, onAnalyze } = props;
  const [aircraftId, setAircraftId] = useState("DJI_M350");
  const [payloadId, setPayloadId] = useState("Zenmuse_H30T");
  const [distanceM, setDistanceM] = useState("5000");
  const [hoverTimeS, setHoverTimeS] = useState("600");
  const [targetAltitudeM, setTargetAltitudeM] = useState("120");
  const [elevationM, setElevationM] = useState("0");
  const [latitude, setLatitude] = useState("");
  const [longitude, setLongitude] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

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
    const distance = parseParam(distanceM);
    const hover = parseParam(hoverTimeS);
    const altitude = parseParam(targetAltitudeM);
    const elevation = parseParam(elevationM);
    const lat = parseParam(latitude);
    const lon = parseParam(longitude);
    if (
      distance === null ||
      hover === null ||
      altitude === null ||
      elevation === null ||
      lat === null ||
      lon === null
    ) {
      setFormError("All numeric fields, including latitude and longitude, are required.");
      return;
    }
    onAnalyze({
      aircraft_id: aircraftId,
      payload_id: payloadId,
      mission_params: {
        distance_m: distance,
        hover_time_s: hover,
        target_altitude_m: altitude,
        elevation_m: elevation,
        latitude: lat,
        longitude: lon,
      },
      thread_id: null,
    });
  }

  return (
    <div className="lg:col-span-1 bg-slate-800 p-6 rounded-xl border border-slate-700 shadow-xl h-fit">
      <h2 className="text-xl font-semibold mb-4 text-white">Mission Configuration</h2>
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
          options={AIRCRAFT_OPTIONS}
          onChange={setAircraftId}
        />
        <SelectField
          id="payload"
          label="Payload System"
          value={payloadId}
          options={PAYLOAD_OPTIONS}
          onChange={setPayloadId}
        />
        <div className="grid grid-cols-2 gap-3">
          <NumberField id="distance" label="Distance (m)" value={distanceM} onChange={setDistanceM} />
          <NumberField id="hover" label="Hover Time (s)" value={hoverTimeS} onChange={setHoverTimeS} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <NumberField
            id="altitude"
            label="Target Alt (m)"
            value={targetAltitudeM}
            onChange={setTargetAltitudeM}
          />
          <NumberField
            id="elevation"
            label="Elevation (m)"
            value={elevationM}
            onChange={setElevationM}
          />
        </div>
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
          disabled={loading}
          className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 text-white font-semibold py-3 rounded-lg text-sm mt-4 transition-colors shadow-lg"
        >
          {loading ? "Processing environment and metrics..." : "Analyze flight feasibility"}
        </button>
      </form>
    </div>
  );
}
