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

export type OfferValueResult = {
  region_id: string;
  region_name: string;
  gross_salary: number | string;
  taxes: {
    tax_year: number;
    filing_status: "single";
    federal_income_tax: number | string;
    payroll_tax: number | string;
    state_income_tax: number | string;
    local_income_tax: number | string;
    local_income_tax_status: "included_nyc" | "not_modeled";
    total_estimated_tax: number | string;
    take_home_pay: number | string;
    federal_source: "irs_2026";
    federal_source_url: string;
    payroll_source_url: string;
    state_source: "tax_foundation_2026";
    state_source_url: string;
    local_source: "nyc_tax_2026" | null;
    local_source_url: string | null;
  };
  housing: {
    monthly_cost: number | string;
    annual_cost: number | string;
    profile: "zillow_typical" | "hud_studio" | "hud_1br" | "hud_2br" | "hud_3br" | "user_provided";
    source: "zillow_research" | "hud_fmr" | "user_provided";
    source_year: number | null;
    source_url: string | null;
  };
  spendable_after_housing: number | string;
  comparable_disposable_income: number | string;
};

export type CalculationResponse = {
  nominal_salary: number | string;
  adjusted_salary: number | string;
  origin: {
    requested_region_id: string;
    requested_region_name: string;
    rpp_year: number;
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
    status: "not_requested" | "available" | "unavailable";
    unavailable_reason: string | null;
  };
  offer_comparison: {
    status: "available" | "unavailable";
    origin_offer: OfferValueResult | null;
    destination_offer: OfferValueResult | null;
    destination_break_even_offer: OfferValueResult | null;
    destination_break_even_salary: number | string | null;
    better_offer: "origin" | "destination" | "equivalent" | "not_compared" | null;
    annual_advantage: number | string | null;
    nonhousing_cost_ratio: number | string | null;
    housing_expenditure_weight: number | string;
    methodology: string;
    unavailable_reason: string | null;
    limitations: string[];
  };
};
