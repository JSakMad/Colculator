export type CalculationInput = {
  nominalSalary: string | number;
  destinationSalary?: string | number;
  originRegionId: string;
  destinationRegionId: string;
  socCode: string;
  includeStateIncomeTax: boolean;
  housingProfile?: "zillow_typical" | "hud_studio" | "hud_1br" | "hud_2br" | "hud_3br";
  originMonthlyHousing?: string | number;
  destinationMonthlyHousing?: string | number;
};

import type { CalculationResponse } from "./types";

export function buildCalculationPayload(input: CalculationInput): {
  nominal_salary: number;
  destination_salary: number | null;
  origin_region_id: string | null;
  destination_region_id: string;
  soc_code: string;
  include_state_income_tax: boolean;
  housing_profile: string;
  origin_monthly_housing: number | null;
  destination_monthly_housing: number | null;
};
export function submitAccessibleCalculation(
  input: CalculationInput,
  request?: typeof fetch,
): Promise<CalculationResponse>;
