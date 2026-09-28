import type { Feature, MultiPolygon, Polygon } from "geojson";

export type Metric = "cost" | "wage";
export type RegionLevel = "country" | "state" | "county";
export type PriceSource = "official_bea" | "modeled" | "unavailable";
export type Focus = { lat: number; lng: number; altitude?: number };
export type GlobeSelectionState = {
  level: "states" | "counties";
  selectedStateId: string | null;
  selectedCountyId: string | null;
  destinationRegionId: string | null;
};

export type RegionProperties = {
  id: string;
  name: string;
  type: RegionLevel;
  fips?: string;
  abbreviation?: string;
  countryCode: string;
  interactive: boolean;
  parentRegionId?: string;
  msaId?: string | null;
  focus: Focus;
  rpp: number | null;
  rppHousing: number | null;
  medianWage: number | null;
  source: PriceSource;
  confidenceInterval?: { lower: number; upper: number } | null;
};

export type RegionFeature = Feature<Polygon | MultiPolygon, RegionProperties>;

export type RppRecord = {
  region_id: string;
  year: number;
  rpp_all_items: string;
  rpp_housing: string;
  source: "official_bea";
};

export type WageRecord = {
  region_id: string;
  soc_code: string;
  median_wage: number | null;
  median_wage_status: string;
  year: number;
  source: "bls_oews";
};

export type CountyEstimate = {
  county_fips: string;
  predicted_rpp_all_items: number;
  predicted_rpp_housing: number;
  confidence_interval: {
    all_items: { lower: number; upper: number };
  };
  source: "modeled";
};

export type GlobeData = {
  states: RegionFeature[];
  counties: RegionFeature[];
  rppYear: number;
  wageYear: number;
};
