import type { JSX } from "react";

import { NumberField } from "./NumberField";

interface LocationFieldsProps {
  readonly latitude: string;
  readonly longitude: string;
  readonly onLatitudeChange: (value: string) => void;
  readonly onLongitudeChange: (value: string) => void;
  readonly onLocate: () => void;
}

export function LocationFields(props: LocationFieldsProps): JSX.Element {
  const { latitude, longitude, onLatitudeChange, onLongitudeChange, onLocate } = props;
  return (
    <div className="pt-2 border-t border-slate-700 space-y-3">
      <button
        type="button"
        onClick={onLocate}
        className="w-full bg-slate-700 hover:bg-slate-600 text-slate-200 text-xs font-medium py-2 rounded-lg transition-colors tracking-wide"
      >
        Use my current location
      </button>
      <div className="grid grid-cols-2 gap-3">
        <NumberField
          id="latitude"
          label="Latitude"
          value={latitude}
          placeholder="0.0000"
          onChange={onLatitudeChange}
        />
        <NumberField
          id="longitude"
          label="Longitude"
          value={longitude}
          placeholder="0.0000"
          onChange={onLongitudeChange}
        />
      </div>
    </div>
  );
}
