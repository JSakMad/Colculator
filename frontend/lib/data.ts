import { geoBounds, geoCentroid } from "d3-geo";
import type { FeatureCollection } from "geojson";
import { feature } from "topojson-client";
import type { GeometryCollection, Topology } from "topojson-specification";

import type {
  CountyEstimate,
  RegionFeature,
  RegionProperties,
  RegionCatalogEntry,
  RppRecord,
  WageRecord,
} from "./types";

type SourceProperties = {
  id: string;
  name: string;
  type: "state" | "county";
  fips: string;
  abbreviation?: string;
  country_code: string;
  is_interactive: boolean;
  parent_region_id?: string;
  msa_id?: string | null;
};

type DataEnvelope<T> = { year: number; records: T[] };
type RegionEnvelope = { regions: RegionCatalogEntry[] };

const fetchJson = async <T,>(path: string): Promise<T> => {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`Could not load ${path}`);
  return response.json() as Promise<T>;
};

let countyResourcesPromise: Promise<{
  features: FeatureCollection["features"];
  estimates: Map<string, CountyEstimate>;
}> | null = null;

function loadCountyResources() {
  if (!countyResourcesPromise) {
    countyResourcesPromise = Promise.all([
      fetchJson<Topology<{ counties: GeometryCollection<SourceProperties> }>>(
        "/data/geometry/us-counties.topo.json",
      ),
      fetchJson<DataEnvelope<CountyEstimate>>("/data/county_rpp_estimates.json"),
    ]).then(([countyTopology, estimateEnvelope]) => ({
      features: (
        feature(countyTopology, countyTopology.objects.counties) as FeatureCollection
      ).features,
      estimates: new Map(
        estimateEnvelope.records.map((record) => [record.county_fips, record]),
      ),
    }));
  }
  return countyResourcesPromise;
}

function sourceProperties(raw: SourceProperties, geometry: RegionFeature["geometry"]): RegionProperties {
  const geographicFeature = { type: "Feature" as const, properties: {}, geometry };
  const [lng, lat] = geoCentroid(geographicFeature);
  const [[west, south], [east, north]] = geoBounds(geographicFeature);
  const longitudeSpan = east >= west ? east - west : 360 - west + east;
  const span = Math.max(longitudeSpan, north - south);
  const altitude = raw.type === "state"
    ? Math.max(0.34, Math.min(0.82, span / 18))
    : Math.max(0.1, Math.min(0.28, span / 8));
  return {
    id: raw.id,
    name: raw.name,
    type: raw.type,
    fips: raw.fips,
    abbreviation: raw.abbreviation,
    countryCode: raw.country_code,
    interactive: raw.is_interactive,
    parentRegionId: raw.parent_region_id,
    msaId: raw.msa_id,
    focus: { lat, lng, altitude },
    rpp: null,
    rppHousing: null,
    medianWage: null,
    source: "unavailable",
  };
}

export async function loadStateData(): Promise<{
  states: RegionFeature[];
  rpp: Map<string, RppRecord>;
  wages: Map<string, WageRecord>;
  rppYear: number;
  wageYear: number;
}> {
  const [stateTopology, rppEnvelope, wageEnvelope] = await Promise.all([
    fetchJson<Topology<{ states: GeometryCollection<SourceProperties> }>>(
      "/data/geometry/us-states.topo.json",
    ),
    fetchJson<DataEnvelope<RppRecord>>("/data/rpp.json"),
    fetchJson<DataEnvelope<WageRecord>>("/data/wages.json"),
  ]);
  const rpp = new Map(rppEnvelope.records.map((record) => [record.region_id, record]));
  const wages = new Map(
    wageEnvelope.records
      .filter((record) => record.soc_code === "15-1252")
      .map((record) => [record.region_id, record]),
  );
  const decoded = feature(
    stateTopology,
    stateTopology.objects.states,
  ) as FeatureCollection;
  const states = decoded.features.map((item) => {
    const raw = item.properties as SourceProperties;
    const price = rpp.get(raw.id);
    const wage = wages.get(raw.id);
    return {
      ...item,
      properties: {
        ...sourceProperties(raw, item.geometry as RegionFeature["geometry"]),
        rpp: price ? Number(price.rpp_all_items) : null,
        rppHousing: price ? Number(price.rpp_housing) : null,
        medianWage: wage?.median_wage ?? null,
        source: price ? "official_bea" : "unavailable",
      },
    } as RegionFeature;
  });

  return { states, rpp, wages, rppYear: rppEnvelope.year, wageYear: wageEnvelope.year };
}

export async function loadCountiesForState(
  stateId: string,
  rpp: Map<string, RppRecord>,
  wages: Map<string, WageRecord>,
): Promise<RegionFeature[]> {
  const { features, estimates } = await loadCountyResources();

  return features
    .filter((item) => (item.properties as SourceProperties).parent_region_id === stateId)
    .map((item) => {
      const raw = item.properties as SourceProperties;
      const official = raw.msa_id ? rpp.get(raw.msa_id) : undefined;
      const estimate = official ? undefined : estimates.get(raw.fips);
      const wage = (raw.msa_id && wages.get(raw.msa_id)) || wages.get(stateId);
      return {
        ...item,
        properties: {
          ...sourceProperties(raw, item.geometry as RegionFeature["geometry"]),
          rpp: official
            ? Number(official.rpp_all_items)
            : estimate?.predicted_rpp_all_items ?? null,
          rppHousing: official
            ? Number(official.rpp_housing)
            : estimate?.predicted_rpp_housing ?? null,
          medianWage: wage?.median_wage ?? null,
          source: official ? "official_bea" : estimate ? "modeled" : "unavailable",
          confidenceInterval: estimate?.confidence_interval.all_items ?? null,
        },
      } as RegionFeature;
    });
}

export function metricValue(feature: RegionFeature, metric: "cost" | "wage") {
  return metric === "cost" ? feature.properties.rpp : feature.properties.medianWage;
}

let regionCatalogPromise: Promise<RegionCatalogEntry[]> | null = null;

export function loadRegionCatalog() {
  if (!regionCatalogPromise) {
    regionCatalogPromise = fetchJson<RegionEnvelope>("/data/regions.json").then(
      (payload) => payload.regions.filter(
        (region) => region.type === "state" || region.type === "county",
      ),
    );
  }
  return regionCatalogPromise;
}
