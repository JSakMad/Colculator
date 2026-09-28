export const INITIAL_CAMERA = Object.freeze({ lat: 34.5, lng: -98.5, altitude: 2.15 });

export function createInitialGlobeState() {
  return {
    level: "states",
    selectedStateId: null,
    selectedCountyId: null,
    destinationRegionId: null,
  };
}

export function activateGlobeRegion(current, region) {
  if (!region || region.interactive !== true) {
    return {
      state: current,
      camera: null,
      shouldLoadData: false,
      notice: region?.name
        ? `${region.name} is visible for context. Colculator currently supports U.S. locations.`
        : "Colculator currently supports U.S. locations.",
    };
  }

  if (region.type === "state") {
    return {
      state: {
        ...current,
        level: "counties",
        selectedStateId: region.id,
        selectedCountyId: null,
      },
      camera: { ...region.focus, altitude: region.focus.altitude ?? 0.72 },
      shouldLoadData: true,
      notice: null,
    };
  }

  if (region.type === "county") {
    return {
      state: {
        ...current,
        level: "counties",
        selectedStateId: region.parentRegionId,
        selectedCountyId: region.id,
        destinationRegionId: region.id,
      },
      camera: { ...region.focus, altitude: region.focus.altitude ?? 0.34 },
      shouldLoadData: true,
      notice: null,
    };
  }

  return { state: current, camera: null, shouldLoadData: false, notice: null };
}

export function returnToNationalView(current) {
  return {
    state: {
      ...current,
      level: "states",
      selectedStateId: null,
      selectedCountyId: null,
    },
    camera: INITIAL_CAMERA,
  };
}
