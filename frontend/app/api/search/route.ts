import { NextRequest, NextResponse } from "next/server";

import regionPayload from "../../../public/data/regions.json";
import {
  mergeSearchCandidates,
  rankCatalogCandidates,
  searchOutcome,
} from "@/lib/search-controller.mjs";
import type { RegionCatalogEntry, SearchCandidate } from "@/lib/types";

const TIGER_BASE =
  "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_Current/MapServer";
const GEOCODER_BASE =
  "https://geocoding.geo.census.gov/geocoder/geographies/coordinates";
const PLACE_LAYERS = [28, 30] as const;

type TigerPlace = {
  GEOID: string;
  STATE: string;
  BASENAME: string;
  NAME: string;
  INTPTLAT: string;
  INTPTLON: string;
};

const regions = regionPayload.regions as RegionCatalogEntry[];
const states = regions.filter((region) => region.type === "state");
const stateNames = new Map(states.map((state) => [state.id, state.name]));
const stateByFips = new Map(states.map((state) => [state.fips, state]));

function safePlaceQuery(query: string) {
  return query
    .replace(/[^\p{L}\p{N}\s'.,-]/gu, "")
    .replaceAll("'", "''")
    .trim()
    .toUpperCase();
}

async function queryPlaceLayer(layer: number, query: string): Promise<TigerPlace[]> {
  const params = new URLSearchParams({
    where: `UPPER(BASENAME) LIKE '${safePlaceQuery(query)}%'`,
    outFields: "GEOID,STATE,BASENAME,NAME,INTPTLAT,INTPTLON",
    returnGeometry: "false",
    resultRecordCount: "6",
    orderByFields: "BASENAME ASC",
    f: "json",
  });
  const response = await fetch(`${TIGER_BASE}/${layer}/query?${params}`, {
    next: { revalidate: 86_400 },
    signal: AbortSignal.timeout(12_000),
  });
  if (!response.ok) return [];
  const payload = (await response.json()) as {
    features?: Array<{ attributes: TigerPlace }>;
  };
  return payload.features?.map((feature) => feature.attributes) ?? [];
}

async function countyForCoordinates(lng: number, lat: number) {
  const params = new URLSearchParams({
    x: String(lng),
    y: String(lat),
    benchmark: "Public_AR_Current",
    vintage: "Current_Current",
    format: "json",
  });
  const response = await fetch(`${GEOCODER_BASE}?${params}`, {
    next: { revalidate: 86_400 },
    signal: AbortSignal.timeout(12_000),
  });
  if (!response.ok) return null;
  const payload = (await response.json()) as {
    result?: { geographies?: { Counties?: Array<{ STATE: string; COUNTY: string }> } };
  };
  const county = payload.result?.geographies?.Counties?.[0];
  return county ? `${county.STATE}${county.COUNTY}` : null;
}

async function cityCandidates(query: string): Promise<SearchCandidate[]> {
  try {
    const placeGroups = await Promise.all(
      PLACE_LAYERS.map((layer) => queryPlaceLayer(layer, query)),
    );
    const places = placeGroups
      .flat()
      .filter((place) => stateByFips.has(place.STATE))
      .slice(0, 8);
    const candidates: Array<SearchCandidate | null> = await Promise.all(
      places.map(async (place) => {
        const lat = Number(place.INTPTLAT);
        const lng = Number(place.INTPTLON);
        if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
        const countyFips = await countyForCoordinates(lng, lat);
        const state = stateByFips.get(place.STATE);
        if (!countyFips || !state) return null;
        return {
          id: `US-PLACE-${place.GEOID}`,
          label: `${place.BASENAME}, ${state.abbreviation ?? state.name}`,
          kind: "city" as const,
          regionId: `US-COUNTY-${countyFips}`,
          stateRegionId: state.id,
          source: "census_tigerweb_geocoder" as const,
          lat,
          lng,
        };
      }),
    );
    return candidates.filter((candidate): candidate is SearchCandidate => candidate !== null);
  } catch {
    return [];
  }
}

export async function GET(request: NextRequest) {
  const query = request.nextUrl.searchParams.get("q")?.trim() ?? "";
  if (query.length < 2 || query.length > 100) {
    return NextResponse.json(
      { query, outcome: "empty", candidates: [], message: "Enter at least two characters." },
      { status: 400 },
    );
  }

  const [cities, local] = await Promise.all([
    cityCandidates(query),
    Promise.resolve(rankCatalogCandidates(query, regions, stateNames)),
  ]);
  const candidates = mergeSearchCandidates(local, cities);
  return NextResponse.json({
    query,
    outcome: searchOutcome(candidates),
    candidates,
    source: "U.S. Census Bureau TIGERweb and Geocoding Services",
  });
}
