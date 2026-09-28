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

export type RegionCatalogEntry = {
  id: string;
  country_code: string;
  type: "state" | "metro" | "county";
  fips: string;
  name: string;
  parent_region_id: string | null;
  msa_id: string | null;
  is_interactive: boolean;
  abbreviation?: string;
};

export type SearchCandidate = {
  id: string;
  label: string;
  kind: "state" | "county" | "city";
  regionId: string;
  stateRegionId: string;
  source: "census_catalog" | "census_tigerweb_geocoder";
  lat?: number;
  lng?: number;
};

export type CategoryResult = {
  category: "housing" | "goods" | "utilities" | "other_services";
  category_group: "housing" | "goods" | "services";
  status: "available" | "unavailable";
  origin_rpp: number | string | null;
  destination_rpp: number | string | null;
  equivalent_salary: number | string | null;
  origin_source: "official_bea" | "modeled";
  destination_source: "official_bea" | "modeled";
  unavailable_reason?: string | null;
};

export type CalculationResponse = {
  nominal_salary: number | string;
  adjusted_salary: number | string;
  origin: {
    requested_region_id: string;
    requested_region_name: string;
    rpp_all_items: number | string;
    rpp_source: "official_bea" | "modeled";
    confidence_interval: [number | string, number | string] | null;
  };
  destination: {
    requested_region_id: string;
    requested_region_name: string;
    effective_rpp_region_name: string;
    rpp_year: number;
    rpp_all_items: number | string;
    rpp_source: "official_bea" | "modeled";
    confidence_interval: [number | string, number | string] | null;
    model_version: string | null;
  };
  category_breakdown: CategoryResult[];
  category_breakdown_note: string;
  destination_wage_benchmark: {
    median_wage: number | string | null;
    year: number | null;
    publication_status: string;
    source: "bls_oews" | null;
    unavailable_reason: string | null;
  };
  state_income_tax_adjustment: {
    requested: boolean;
    status: "not_requested" | "unavailable";
    unavailable_reason: string | null;
  };
};
