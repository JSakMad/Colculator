export function buildCalculationPayload(input) {
  const salary = Number(input.nominalSalary);
  if (!Number.isFinite(salary) || salary <= 0) {
    throw new Error("Enter a salary greater than zero.");
  }
  if (!input.destinationRegionId) {
    throw new Error("Choose a destination region.");
  }
  return {
    nominal_salary: salary,
    destination_salary: input.destinationSalary
      ? Number(input.destinationSalary)
      : null,
    origin_region_id: input.originRegionId || null,
    destination_region_id: input.destinationRegionId,
    soc_code: input.socCode || "15-1252",
    include_state_income_tax: true,
    housing_profile: input.housingProfile || "zillow_typical",
    origin_monthly_housing: input.originMonthlyHousing
      ? Number(input.originMonthlyHousing)
      : null,
    destination_monthly_housing: input.destinationMonthlyHousing
      ? Number(input.destinationMonthlyHousing)
      : null,
  };
}

export async function submitAccessibleCalculation(input, request = fetch) {
  const response = await request("/api/calculate", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(buildCalculationPayload(input)),
  });
  const payload = await response.json();
  if (!response.ok) {
    const message = payload?.detail?.message ?? payload?.detail?.code;
    throw new Error(message || "The calculation could not be completed.");
  }
  return payload;
}
