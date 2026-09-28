export type CalculationInput = {
  nominalSalary: string | number;
  originRegionId: string;
  destinationRegionId: string;
  socCode: string;
  includeStateIncomeTax: boolean;
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

export function buildCalculationPayload(input: CalculationInput): {
  nominal_salary: number;
  origin_region_id: string | null;
  destination_region_id: string;
  soc_code: string;
  include_state_income_tax: boolean;
};
export function submitAccessibleCalculation(
  input: CalculationInput,
  request?: typeof fetch,
): Promise<CalculationResponse>;
