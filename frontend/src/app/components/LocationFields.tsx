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
  const { latitude, longitude, onLatitudeChange, onLongitudeChange, onLocate } =
    props;
  return (
    <fieldset className="space-y-2 border-t border-line-subtle pt-3">
      <legend className="section-label float-left mb-2 w-full">Location</legend>
      <button type="button" onClick={onLocate} className="btn w-full">
        Use my current location
      </button>
      <div className="grid grid-cols-2 gap-2">
        <NumberField
          id="latitude"
          label="Latitude"
          value={latitude}
          placeholder="decimal deg"
          onChange={onLatitudeChange}
        />
        <NumberField
          id="longitude"
          label="Longitude"
          value={longitude}
          placeholder="decimal deg"
          onChange={onLongitudeChange}
        />
      </div>
    </fieldset>
  );
}
