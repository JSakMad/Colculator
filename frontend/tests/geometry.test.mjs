import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { feature } from "topojson-client";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const dataDirectory = path.join(root, "frontend/public/data");

async function readJSON(relativePath) {
  return JSON.parse(await readFile(path.join(dataDirectory, relativePath), "utf8"));
}

test("committed geometry resolves every interactive state and county", async () => {
  const [catalog, states, counties] = await Promise.all([
    readJSON("regions.json"),
    readJSON("geometry/us-states.topo.json"),
    readJSON("geometry/us-counties.topo.json"),
  ]);

  const stateIds = new Set(
    states.objects.states.geometries.map((geometry) => `US-STATE-${geometry.id}`),
  );
  const countyIds = new Set(
    counties.objects.counties.geometries.map((geometry) => `US-COUNTY-${geometry.id}`),
  );

  for (const region of catalog.regions) {
    if (region.type === "state") assert.ok(stateIds.has(region.id), region.id);
    if (region.type === "county") assert.ok(countyIds.has(region.id), region.id);
  }
  assert.equal(stateIds.size, 51);
  assert.equal(countyIds.size, 3_144);

  const decodedStates = feature(states, states.objects.states);
  const decodedCounties = feature(counties, counties.objects.counties);
  assert.equal(decodedStates.features.length, 51);
  assert.equal(decodedCounties.features.length, 3_144);
  for (const decoded of [...decodedStates.features, ...decodedCounties.features]) {
    assert.match(decoded.geometry.type, /^(Multi)?Polygon$/);
    assert.ok(decoded.geometry.coordinates.length > 0, decoded.id);
  }
});

test("TopoJSON assets stay below the uncompressed delivery budget", async () => {
  const [states, counties] = await Promise.all([
    readFile(path.join(dataDirectory, "geometry/us-states.topo.json")),
    readFile(path.join(dataDirectory, "geometry/us-counties.topo.json")),
  ]);
  assert.ok(states.byteLength < 3_000_000, `states: ${states.byteLength} bytes`);
  assert.ok(counties.byteLength < 3_000_000, `counties: ${counties.byteLength} bytes`);
});
