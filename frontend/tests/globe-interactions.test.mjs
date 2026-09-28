import assert from "node:assert/strict";
import test from "node:test";

import {
  activateGlobeRegion,
  createInitialGlobeState,
} from "../lib/globe-controller.mjs";

test("a US state activation transitions the camera and reveals its counties", () => {
  const result = activateGlobeRegion(createInitialGlobeState(), {
    id: "US-STATE-06",
    name: "California",
    type: "state",
    interactive: true,
    focus: { lat: 37.2, lng: -119.7 },
  });

  assert.equal(result.state.level, "counties");
  assert.equal(result.state.selectedStateId, "US-STATE-06");
  assert.deepEqual(result.camera, { lat: 37.2, lng: -119.7, altitude: 0.72 });
  assert.equal(result.shouldLoadData, true);
});

test("a county activation populates the calculator destination", () => {
  const result = activateGlobeRegion(createInitialGlobeState(), {
    id: "US-COUNTY-06075",
    name: "San Francisco",
    type: "county",
    parentRegionId: "US-STATE-06",
    interactive: true,
    focus: { lat: 37.76, lng: -122.44 },
  });

  assert.equal(result.state.destinationRegionId, "US-COUNTY-06075");
  assert.equal(result.state.selectedCountyId, "US-COUNTY-06075");
});

test("a non-US country fails gracefully without a data lookup", () => {
  const initial = createInitialGlobeState();
  const result = activateGlobeRegion(initial, {
    id: "COUNTRY-124",
    name: "Canada",
    type: "country",
    interactive: false,
    focus: { lat: 56, lng: -106 },
  });

  assert.equal(result.state, initial);
  assert.equal(result.camera, null);
  assert.equal(result.shouldLoadData, false);
  assert.match(result.notice, /currently supports U\.S\. locations/);
});
