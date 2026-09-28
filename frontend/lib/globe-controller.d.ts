export type GlobeSelectionState = {
  level: "states" | "counties";
  selectedStateId: string | null;
  selectedCountyId: string | null;
  destinationRegionId: string | null;
};

export type Focus = { lat: number; lng: number; altitude?: number };

export type GlobeRegion = {
  id: string;
  name: string;
  type: "country" | "state" | "county";
  interactive: boolean;
  parentRegionId?: string;
  focus: Focus;
};

export const INITIAL_CAMERA: Readonly<Required<Focus>>;
export function createInitialGlobeState(): GlobeSelectionState;
export function activateGlobeRegion(
  current: GlobeSelectionState,
  region: GlobeRegion | null,
): {
  state: GlobeSelectionState;
  camera: Focus | null;
  shouldLoadData: boolean;
  notice: string | null;
};
export function returnToNationalView(current: GlobeSelectionState): {
  state: GlobeSelectionState;
  camera: Readonly<Required<Focus>>;
};
