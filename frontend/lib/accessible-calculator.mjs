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
    origin_region_id: input.originRegionId || null,
    destination_region_id: input.destinationRegionId,
    soc_code: input.socCode || "15-1252",
    include_state_income_tax: Boolean(input.includeStateIncomeTax),
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
