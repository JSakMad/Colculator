"use client";

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useMemo, useState, useTransition } from "react";

import {
  submitAccessibleCalculation,
} from "@/lib/accessible-calculator.mjs";
import type { CalculationResponse, RegionCatalogEntry } from "@/lib/types";

const currency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

const formatCurrency = (value: number | string) => currency.format(Number(value));

const occupations = [
  ["15-1252", "Software developers"],
  ["15-1251", "Computer programmers"],
  ["15-1253", "Software QA analysts & testers"],
  ["15-1254", "Web developers"],
  ["15-1255", "Web & digital interface designers"],
] as const;

const categoryLabels: Record<string, string> = {
  housing: "Housing",
  goods: "Goods",
  utilities: "Utilities",
  other_services: "Other services",
};

const sourceLabel = (source: "official_bea" | "modeled") =>
  source === "official_bea" ? "Official BEA" : "Modeled";

const formatSignedCurrency = (value: number) =>
  `${value >= 0 ? "+" : "−"}${currency.format(Math.abs(value))}`;

export function AccessibleCalculator({
  regions,
  destinationRegionId,
  onDestinationChange,
}: {
  regions: RegionCatalogEntry[];
  destinationRegionId: string | null;
  onDestinationChange: (regionId: string) => void;
}) {
  const states = useMemo(
    () => regions.filter((region) => region.type === "state").toSorted((a, b) => a.name.localeCompare(b.name)),
    [regions],
  );
  const countiesByState = useMemo(() => {
    const grouped = new Map<string, RegionCatalogEntry[]>();
    for (const region of regions) {
      if (region.type !== "county" || !region.parent_region_id) continue;
      const group = grouped.get(region.parent_region_id) ?? [];
      group.push(region);
      grouped.set(region.parent_region_id, group);
    }
    for (const group of grouped.values()) group.sort((a, b) => a.name.localeCompare(b.name));
    return grouped;
  }, [regions]);
  const regionById = useMemo(
    () => new Map(regions.map((region) => [region.id, region])),
    [regions],
  );

  const [salary, setSalary] = useState("");
  const [originState, setOriginState] = useState("");
  const [originCounty, setOriginCounty] = useState("");
  const [destinationState, setDestinationState] = useState("");
  const [destinationCounty, setDestinationCounty] = useState("");
  const [socCode, setSocCode] = useState("15-1252");
  const [includeTax, setIncludeTax] = useState(false);
  const [result, setResult] = useState<CalculationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  useEffect(() => {
    if (!destinationRegionId) return;
    const region = regionById.get(destinationRegionId);
    if (!region) return;
    if (region.type === "state") {
      setDestinationState(region.id);
      setDestinationCounty("");
    } else if (region.type === "county" && region.parent_region_id) {
      setDestinationState(region.parent_region_id);
      setDestinationCounty(region.id);
    }
  }, [destinationRegionId, regionById]);

  const destinationId = destinationCounty || destinationState;
  const originId = originCounty || originState;
  const nominalValue = result ? Number(result.nominal_salary) : 0;
  const adjustedValue = result ? Number(result.adjusted_salary) : 0;
  const difference = adjustedValue - nominalValue;
  const differencePercent = nominalValue ? (difference / nominalValue) * 100 : 0;

  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    startTransition(async () => {
      try {
        const nextResult = await submitAccessibleCalculation({
          nominalSalary: salary,
          originRegionId: originId,
          destinationRegionId: destinationId,
          socCode,
          includeStateIncomeTax: includeTax,
        }) as CalculationResponse;
        setResult(nextResult);
      } catch (caught) {
        setResult(null);
        setError(caught instanceof Error ? caught.message : "The calculation could not be completed.");
      }
    });
  }

  return (
    <section id="calculator" className="calculator-section" aria-labelledby="calculator-heading">
      <div className="calculator-intro">
        <span className="section-number">03</span>
        <p className="eyebrow">No globe required</p>
        <h2 id="calculator-heading">Run the comparison in plain coordinates.</h2>
        <p>
          Every map destination is available here as standard form controls. Start at
          the national average or name an origin, then choose where you are going.
        </p>
      </div>

      <form className="calculator-form" onSubmit={submit}>
        <div className="salary-field">
          <label htmlFor="salary">Current annual salary</label>
          <span>$</span>
          <input
            id="salary"
            inputMode="decimal"
            type="number"
            min="1"
            step="1"
            value={salary}
            onChange={(event) => setSalary(event.target.value)}
            placeholder="Enter your salary"
            required
          />
        </div>

        <fieldset>
          <legend>Origin</legend>
          <label htmlFor="origin-state">State or national baseline</label>
          <select
            id="origin-state"
            value={originState}
            onChange={(event) => {
              setOriginState(event.target.value);
              setOriginCounty("");
            }}
          >
            <option value="">U.S. national average</option>
            {states.map((state) => <option key={state.id} value={state.id}>{state.name}</option>)}
          </select>
          <label htmlFor="origin-county">County (optional)</label>
          <select
            id="origin-county"
            value={originCounty}
            onChange={(event) => setOriginCounty(event.target.value)}
            disabled={!originState}
          >
            <option value="">Use the state value</option>
            {(countiesByState.get(originState) ?? []).map((county) => (
              <option key={county.id} value={county.id}>{county.name} County</option>
            ))}
          </select>
        </fieldset>

        <fieldset>
          <legend>Destination</legend>
          <label htmlFor="destination-state">State</label>
          <select
            id="destination-state"
            value={destinationState}
            onChange={(event) => {
              const value = event.target.value;
              setDestinationState(value);
              setDestinationCounty("");
              if (value) onDestinationChange(value);
            }}
            required
          >
            <option value="">Choose a state</option>
            {states.map((state) => <option key={state.id} value={state.id}>{state.name}</option>)}
          </select>
          <label htmlFor="destination-county">County (optional)</label>
          <select
            id="destination-county"
            value={destinationCounty}
            onChange={(event) => {
              const value = event.target.value;
              setDestinationCounty(value);
              if (value) onDestinationChange(value);
            }}
            disabled={!destinationState}
          >
            <option value="">Use the state value</option>
            {(countiesByState.get(destinationState) ?? []).map((county) => (
              <option key={county.id} value={county.id}>{county.name} County</option>
            ))}
          </select>
        </fieldset>

        <div className="role-field">
          <label htmlFor="occupation">Role benchmark</label>
          <select id="occupation" value={socCode} onChange={(event) => setSocCode(event.target.value)}>
            {occupations.map(([code, label]) => <option key={code} value={code}>{label}</option>)}
          </select>
        </div>

        <label className="tax-toggle">
          <input
            type="checkbox"
            checked={includeTax}
            onChange={(event) => setIncludeTax(event.target.checked)}
          />
          <span>Request state-income-tax adjustment as a separate line item</span>
        </label>

        <button className="calculate-button" type="submit" disabled={pending || !destinationId}>
          <span>{pending ? "Calculating…" : "Calculate equivalent salary"}</span>
          <span aria-hidden="true">→</span>
        </button>
        {error ? <p className="calculator-error" role="alert">{error}</p> : null}
      </form>

      <AnimatePresence mode="wait">
        {result ? (
          <motion.div
            key={`${result.destination.requested_region_id}-${result.adjusted_salary}`}
            className="calculation-result"
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -16 }}
            transition={{ duration: .5, ease: [0.22, 1, 0.36, 1] }}
            aria-live="polite"
          >
            <div className="result-heading">
              <div>
                <p className="eyebrow">Equivalent in {result.destination.requested_region_name}</p>
                <strong>{formatCurrency(result.adjusted_salary)}</strong>
              </div>
              <span className={`result-source source-${result.destination.rpp_source}`}>
                {result.destination.rpp_source === "official_bea" ? "Official BEA" : "Modeled estimate"}
              </span>
            </div>
            <p className="result-equation">
              {formatCurrency(result.nominal_salary)} in {result.origin.requested_region_name}
              <span aria-hidden="true"> → </span>
              {result.destination.requested_region_name} · RPP {result.destination.rpp_all_items}
            </p>
            <p className="result-provenance">
              Origin: {sourceLabel(result.origin.rpp_source)} · Destination: {sourceLabel(result.destination.rpp_source)}
            </p>
            <div className="result-difference" aria-label="Difference from current salary">
              <span>Difference from nominal</span>
              <strong>{formatSignedCurrency(difference)}</strong>
              <small>{differencePercent >= 0 ? "+" : ""}{differencePercent.toFixed(1)}%</small>
            </div>
            {result.destination.confidence_interval ? (
              <p className="result-confidence">
                95% confidence interval: {Number(result.destination.confidence_interval[0]).toFixed(1)}–
                {Number(result.destination.confidence_interval[1]).toFixed(1)} · {result.destination.model_version}
              </p>
            ) : null}

            <div className="wage-benchmark">
              <span>Observed destination wage</span>
              <strong>
                {result.destination_wage_benchmark.median_wage === null
                  ? "Not published"
                  : formatCurrency(result.destination_wage_benchmark.median_wage)}
              </strong>
              <small>BLS OEWS · {result.destination_wage_benchmark.year ?? "unavailable"}</small>
            </div>

            <div className="breakdown-table-wrap">
              <table>
                <caption>Category-by-category equivalent salary</caption>
                <thead>
                  <tr><th>Category</th><th>Origin RPP</th><th>Destination RPP</th><th>Sources</th><th>Equivalent</th></tr>
                </thead>
                <tbody>
                  {result.category_breakdown.map((category) => (
                    <tr key={category.category}>
                      <th scope="row">{categoryLabels[category.category]}</th>
                      <td>{category.origin_rpp ?? "Unavailable"}</td>
                      <td>{category.destination_rpp ?? "Unavailable"}</td>
                      <td>{sourceLabel(category.origin_source)} → {sourceLabel(category.destination_source)}</td>
                      <td>{category.equivalent_salary === null ? "Unavailable" : formatCurrency(category.equivalent_salary)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="breakdown-note">{result.category_breakdown_note}</p>
            {result.state_income_tax_adjustment.requested ? (
              <p className="tax-note">
                <strong>Tax adjustment:</strong> {result.state_income_tax_adjustment.unavailable_reason}
              </p>
            ) : null}
          </motion.div>
        ) : (
          <motion.div
            key="awaiting-input"
            className="result-placeholder"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            aria-hidden="true"
          >
            <div className="placeholder-heading">
              <span>Output field</span>
              <i />
            </div>
            <div className="placeholder-orbit">
              <span />
              <span />
              <strong>?</strong>
            </div>
            <div className="placeholder-copy">
              <p>Awaiting coordinates</p>
              <h3>Your equivalent salary resolves here.</h3>
            </div>
            <div className="formula-strip">
              <span>Nominal salary</span>
              <b>×</b>
              <span>Destination RPP</span>
              <b>÷</b>
              <span>Origin RPP</span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}
