"use client";

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useMemo, useState, useTransition } from "react";

import { submitAccessibleCalculation } from "@/lib/accessible-calculator.mjs";
import type { CalculationResponse, OfferValueResult, RegionCatalogEntry } from "@/lib/types";

const currency = new Intl.NumberFormat("en-US", {
  style: "currency", currency: "USD", maximumFractionDigits: 0,
});
const formatCurrency = (value: number | string) => currency.format(Number(value));
const formatSignedCurrency = (value: number) =>
  `${value >= 0 ? "+" : "−"}${currency.format(Math.abs(value))}`;

const occupations = [
  ["15-1252", "Software developers"],
  ["15-1251", "Computer programmers"],
  ["15-1253", "Software QA analysts & testers"],
  ["15-1254", "Web developers"],
  ["15-1255", "Web & digital interface designers"],
] as const;
const housingProfiles = [
  ["zillow_typical", "Typical market rent · Zillow"],
  ["hud_studio", "Studio · HUD fair market rent"],
  ["hud_1br", "1 bedroom · HUD fair market rent"],
  ["hud_2br", "2 bedrooms · HUD fair market rent"],
  ["hud_3br", "3 bedrooms · HUD fair market rent"],
] as const;
const categoryLabels: Record<string, string> = {
  housing: "Housing", goods: "Goods", utilities: "Utilities", other_services: "Other services",
};
const sourceLabel = (source: "official_bea" | "modeled") =>
  source === "official_bea" ? "Official BEA" : "Modeled";

function OfferCard({ offer, reference }: { offer: OfferValueResult; reference: boolean }) {
  const housingSource = offer.housing.source === "zillow_research"
    ? "Zillow Research"
    : offer.housing.source === "hud_fmr" ? "HUD FMR" : "Your housing cost";
  return (
    <article className="offer-card">
      <div className="offer-card-heading">
        <div><span>{reference ? "Offer A · reference" : "Offer B · destination"}</span><h3>{offer.region_name}</h3></div>
        <strong>{formatCurrency(offer.gross_salary)}</strong>
      </div>
      <dl>
        <div><dt>Federal income tax</dt><dd>−{formatCurrency(offer.taxes.federal_income_tax)}</dd></div>
        <div><dt>Social Security + Medicare</dt><dd>−{formatCurrency(offer.taxes.payroll_tax)}</dd></div>
        <div><dt>State income tax</dt><dd>−{formatCurrency(offer.taxes.state_income_tax)}</dd></div>
        <div>
          <dt>Local income tax · {offer.taxes.local_income_tax_status === "not_modeled" ? "not modeled" : "NYC"}</dt>
          <dd>−{formatCurrency(offer.taxes.local_income_tax)}</dd>
        </div>
        <div className="offer-subtotal"><dt>Estimated take-home</dt><dd>{formatCurrency(offer.taxes.take_home_pay)}</dd></div>
        <div><dt>Housing · {housingSource}</dt><dd>−{formatCurrency(offer.housing.annual_cost)}</dd></div>
        <div className="offer-total">
          <dt>{reference ? "Spendable after housing" : "Comparable purchasing power"}</dt>
          <dd>{formatCurrency(offer.comparable_disposable_income)}</dd>
        </div>
      </dl>
      <p className="offer-sources">
        Sources: <a href={offer.taxes.federal_source_url} target="_blank" rel="noreferrer">IRS federal</a>
        {" · "}<a href={offer.taxes.payroll_source_url} target="_blank" rel="noreferrer">IRS payroll</a>
        {" · "}<a href={offer.taxes.state_source_url} target="_blank" rel="noreferrer">Tax Foundation state</a>
        {offer.taxes.local_source_url ? <>{" · "}<a href={offer.taxes.local_source_url} target="_blank" rel="noreferrer">NYC local</a></> : null}
        {offer.housing.source_url ? <>{" · "}<a href={offer.housing.source_url} target="_blank" rel="noreferrer">{housingSource}</a></> : null}
      </p>
    </article>
  );
}

export function AccessibleCalculator({
  regions, destinationRegionId, onDestinationChange,
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
  const regionById = useMemo(() => new Map(regions.map((region) => [region.id, region])), [regions]);

  const [salary, setSalary] = useState("");
  const [destinationSalary, setDestinationSalary] = useState("");
  const [originState, setOriginState] = useState("");
  const [originCounty, setOriginCounty] = useState("");
  const [destinationState, setDestinationState] = useState("");
  const [destinationCounty, setDestinationCounty] = useState("");
  const [socCode, setSocCode] = useState("15-1252");
  const [housingProfile, setHousingProfile] = useState<(typeof housingProfiles)[number][0]>("zillow_typical");
  const [originHousing, setOriginHousing] = useState("");
  const [destinationHousing, setDestinationHousing] = useState("");
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

  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    startTransition(async () => {
      try {
        const nextResult = await submitAccessibleCalculation({
          nominalSalary: salary,
          destinationSalary,
          originRegionId: originCounty,
          destinationRegionId: destinationCounty,
          socCode,
          includeStateIncomeTax: true,
          housingProfile,
          originMonthlyHousing: originHousing,
          destinationMonthlyHousing: destinationHousing,
        }) as CalculationResponse;
        setResult(nextResult);
      } catch (caught) {
        setResult(null);
        setError(caught instanceof Error ? caught.message : "The calculation could not be completed.");
      }
    });
  }

  const comparison = result?.offer_comparison;
  const actualDestination = comparison?.status === "available" ? comparison.destination_offer : null;
  const actualComparison = actualDestination !== null;
  const advantage = actualComparison ? Number(comparison?.annual_advantage) : 0;
  const winningOffer = actualDestination
    ? comparison?.better_offer === "destination"
      ? actualDestination.region_name
      : comparison?.better_offer === "origin" ? comparison.origin_offer?.region_name : "Effectively tied"
    : null;

  return (
    <section id="calculator" className="calculator-section" aria-labelledby="calculator-heading">
      <div className="calculator-intro">
        <span className="section-number">03</span>
        <p className="eyebrow">Offer value, not salary theater</p>
        <h2 id="calculator-heading">Which offer leaves more life after the bills?</h2>
        <p>Compare after-tax pay, local housing, and the purchasing power of what remains. Both locations must be counties so the calculator never invents a statewide rent.</p>
      </div>

      <form className="calculator-form" onSubmit={submit}>
        <div className="offer-salary-grid">
          <div className="salary-field">
            <label htmlFor="salary">Offer A annual salary</label><span>$</span>
            <input id="salary" inputMode="decimal" type="number" min="1" step="1" value={salary}
              onChange={(event) => setSalary(event.target.value)} placeholder="100,000" required />
          </div>
          <div className="salary-field">
            <label htmlFor="destination-salary">Offer B salary · optional</label><span>$</span>
            <input id="destination-salary" inputMode="decimal" type="number" min="1" step="1"
              value={destinationSalary} onChange={(event) => setDestinationSalary(event.target.value)} placeholder="Find break-even" />
          </div>
        </div>

        <fieldset>
          <legend>Offer A location</legend>
          <div className="location-field">
            <label htmlFor="origin-state">State</label>
            <select id="origin-state" value={originState} required onChange={(event) => {
              setOriginState(event.target.value); setOriginCounty("");
            }}>
              <option value="">Choose a state</option>
              {states.map((state) => <option key={state.id} value={state.id}>{state.name}</option>)}
            </select>
          </div>
          <div className="location-field">
            <label htmlFor="origin-county">County</label>
            <select id="origin-county" value={originCounty} required disabled={!originState}
              onChange={(event) => setOriginCounty(event.target.value)}>
              <option value="">Choose a county</option>
              {(countiesByState.get(originState) ?? []).map((county) => <option key={county.id} value={county.id}>{county.name} County</option>)}
            </select>
          </div>
        </fieldset>

        <fieldset>
          <legend>Offer B location</legend>
          <div className="location-field">
            <label htmlFor="destination-state">State</label>
            <select id="destination-state" value={destinationState} required onChange={(event) => {
              const value = event.target.value; setDestinationState(value); setDestinationCounty("");
              if (value) onDestinationChange(value);
            }}>
              <option value="">Choose a state</option>
              {states.map((state) => <option key={state.id} value={state.id}>{state.name}</option>)}
            </select>
          </div>
          <div className="location-field">
            <label htmlFor="destination-county">County</label>
            <select id="destination-county" value={destinationCounty} required disabled={!destinationState}
              onChange={(event) => {
                const value = event.target.value; setDestinationCounty(value); if (value) onDestinationChange(value);
              }}>
              <option value="">Choose a county</option>
              {(countiesByState.get(destinationState) ?? []).map((county) => <option key={county.id} value={county.id}>{county.name} County</option>)}
            </select>
          </div>
        </fieldset>

        <div className="housing-controls">
          <div>
            <label htmlFor="housing-profile">Housing benchmark</label>
            <select id="housing-profile" value={housingProfile}
              onChange={(event) => setHousingProfile(event.target.value as typeof housingProfile)}>
              {housingProfiles.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="origin-housing">Offer A monthly housing · optional</label>
            <input id="origin-housing" type="number" min="0" step="1" inputMode="decimal" value={originHousing}
              onChange={(event) => setOriginHousing(event.target.value)} placeholder="Use benchmark" />
          </div>
          <div>
            <label htmlFor="destination-housing">Offer B monthly housing · optional</label>
            <input id="destination-housing" type="number" min="0" step="1" inputMode="decimal" value={destinationHousing}
              onChange={(event) => setDestinationHousing(event.target.value)} placeholder="Use benchmark" />
          </div>
        </div>

        <div className="role-field">
          <label htmlFor="occupation">Destination wage benchmark</label>
          <select id="occupation" value={socCode} onChange={(event) => setSocCode(event.target.value)}>
            {occupations.map(([code, label]) => <option key={code} value={code}>{label}</option>)}
          </select>
        </div>
        <p className="assumption-note">2026 single filer · standard deductions · taxes always included</p>
        <button className="calculate-button" type="submit" disabled={pending || !originCounty || !destinationCounty}>
          <span>{pending ? "Calculating…" : destinationSalary ? "Compare offers" : "Find break-even offer"}</span><span aria-hidden="true">→</span>
        </button>
        {error ? <p className="calculator-error" role="alert">{error}</p> : null}
      </form>

      <AnimatePresence mode="wait">
        {result ? (
          <motion.div key={`${result.destination.requested_region_id}-${result.adjusted_salary}`} className="calculation-result"
            initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -16 }}
            transition={{ duration: .5, ease: [0.22, 1, 0.36, 1] }} aria-live="polite">
            {comparison?.status === "available" && comparison.origin_offer ? (
              <>
                <div className="result-heading offer-verdict">
                  <div><p className="eyebrow">{actualComparison ? "Stronger offer" : "Offer B break-even salary"}</p>
                    <strong>{actualComparison ? winningOffer : formatCurrency(comparison.destination_break_even_salary ?? 0)}</strong></div>
                  <span className="result-source">Estimated offer value</span>
                </div>
                <p className="result-equation">
                  {actualComparison
                    ? `${formatSignedCurrency(Math.abs(advantage))} per year in comparable income after taxes and housing`
                    : `Gross salary needed in ${result.destination.requested_region_name} to match Offer A`}
                </p>
                <div className="offer-card-grid">
                  <OfferCard offer={comparison.origin_offer} reference />
                  {comparison.destination_offer || comparison.destination_break_even_offer ? (
                    <OfferCard offer={(comparison.destination_offer ?? comparison.destination_break_even_offer)!} reference={false} />
                  ) : null}
                </div>
                {actualComparison ? <p className="result-equation">Offer B break-even salary: {formatCurrency(comparison.destination_break_even_salary ?? 0)}</p> : null}
                <div className="method-ledger">
                  <p>{comparison.methodology}</p>
                  <p>Nonhousing price ratio: {Number(comparison.nonhousing_cost_ratio).toFixed(3)} · housing weight removed: {Number(comparison.housing_expenditure_weight) * 100}%</p>
                  {[result.origin, result.destination].map((region) => <p key={region.requested_region_id}>
                    {region.requested_region_name}: {region.rpp_source === "modeled" ? "Modeled estimate" : "Official BEA"} RPP · {region.rpp_year}
                    {region.confidence_interval ? ` · RPP confidence interval ${region.confidence_interval.join("–")}` : ""}
                  </p>)}
                  {comparison.limitations.map((limitation) => <p key={limitation}>{limitation}</p>)}
                </div>
                {[comparison.origin_offer, comparison.destination_offer ?? comparison.destination_break_even_offer].some((offer) => offer?.housing.source === "zillow_research") ? (
                  <p className="zillow-attribution">Housing data provided by <a href="https://www.zillow.com/research/data/" target="_blank" rel="noreferrer">Zillow Research</a>. Zillow is a registered trademark of Zillow, Inc.</p>
                ) : null}
              </>
            ) : <p className="calculator-error">{comparison?.unavailable_reason}</p>}

            <div className="official-baseline">
              <div><span>Official purchasing-power baseline</span><strong>{formatCurrency(result.adjusted_salary)}</strong></div>
              <p>The original FR5 result remains intact: {formatCurrency(result.nominal_salary)} × destination BEA RPP ÷ origin BEA RPP. It describes average-economy buying power, not take-home offer value.</p>
              <span className={`result-source source-${result.origin.rpp_source === "modeled" || result.destination.rpp_source === "modeled" ? "modeled" : "official_bea"}`}>
                {result.origin.rpp_source === "modeled" || result.destination.rpp_source === "modeled" ? "Includes modeled estimate" : "Official BEA"}
              </span>
            </div>
            <div className="wage-benchmark">
              <span>Observed destination wage</span>
              <strong>{result.destination_wage_benchmark.median_wage === null ? "Not published" : formatCurrency(result.destination_wage_benchmark.median_wage)}</strong>
              <small>BLS OEWS · {result.destination_wage_benchmark.year ?? "unavailable"}</small>
            </div>
            <details className="technical-breakdown">
              <summary>Inspect official category RPPs</summary>
              <div className="breakdown-table-wrap"><table>
                <caption>Independent category equivalents—not contribution weights</caption>
                <thead><tr><th>Category</th><th>Origin</th><th>Destination</th><th>Sources</th><th>Equivalent</th></tr></thead>
                <tbody>{result.category_breakdown.map((category) => <tr key={category.category}>
                  <th scope="row">{categoryLabels[category.category]}</th><td>{category.origin_rpp ?? "Unavailable"}</td>
                  <td>{category.destination_rpp ?? "Unavailable"}</td><td>{sourceLabel(category.origin_source)} → {sourceLabel(category.destination_source)}</td>
                  <td>{category.equivalent_salary === null ? "Unavailable" : formatCurrency(category.equivalent_salary)}</td>
                </tr>)}</tbody>
              </table></div>
              <p className="breakdown-note">{result.category_breakdown_note}</p>
            </details>
          </motion.div>
        ) : (
          <motion.div key="awaiting-input" className="result-placeholder" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} aria-hidden="true">
            <div className="placeholder-heading"><span>Offer field</span><i /></div>
            <div className="placeholder-orbit"><span /><span /><strong>?</strong></div>
            <div className="placeholder-copy"><p>Awaiting two locations</p><h3>Your stronger offer resolves here.</h3></div>
            <div className="formula-strip"><span>Take-home</span><b>−</b><span>Housing</span><b>÷</b><span>Local prices</span></div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}
