import type { JSX } from "react";

import { NumberField } from "./NumberField";

interface MissionParamFieldsProps {
  readonly distanceM: string;
  readonly hoverTimeS: string;
  readonly targetAltitudeM: string;
  readonly elevationM: string;
  readonly onDistanceChange: (value: string) => void;
  readonly onHoverTimeChange: (value: string) => void;
  readonly onTargetAltitudeChange: (value: string) => void;
  readonly onElevationChange: (value: string) => void;
}

export function MissionParamFields(
  props: MissionParamFieldsProps,
): JSX.Element {
  const {
    distanceM,
    hoverTimeS,
    targetAltitudeM,
    elevationM,
    onDistanceChange,
    onHoverTimeChange,
    onTargetAltitudeChange,
    onElevationChange,
  } = props;
  return (
    <>
      <div className="grid grid-cols-2 gap-2">
        <NumberField
          id="distance"
          label="Distance (m)"
          value={distanceM}
          onChange={onDistanceChange}
        />
        <NumberField
          id="hover"
          label="Hover time (s)"
          value={hoverTimeS}
          onChange={onHoverTimeChange}
        />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <NumberField
          id="altitude"
          label="Target alt (m AGL)"
          value={targetAltitudeM}
          onChange={onTargetAltitudeChange}
        />
        <NumberField
          id="elevation"
          label="Elevation (m MSL)"
          value={elevationM}
          onChange={onElevationChange}
        />
      </div>
    </>
  );
}
