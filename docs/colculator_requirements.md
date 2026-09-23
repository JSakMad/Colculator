# Colculator
## Requirements Document (for implementation via an AI coding agent)

---

## 1. Vision

A US cost-of-living-adjusted salary calculator for software engineering roles, built around an interactive 3D map: click into a state, then a county, enter a salary, and get back a normalized figure — backed by official government price data where it exists, and a validated machine-learning estimate where it doesn't (most nonmetro/rural counties).

---

## 2. Existing Data & Solutions (research summary — this is a real, established methodology, not something to invent from scratch)

- **BEA Regional Price Parities (RPP)** — the actual U.S. government measure of geographic price-level differences, published annually and free, covering every state and ~400 metro areas. Expressed as a percentage of the national price level: California was 110.7, Hawaii 110.0, Mississippi 87.0 in 2024. This is the real number to build on, not a proprietary index you'd need to derive from nothing.
- **Existing tools already do the RPP-only version:** PlainCost, CompareLiving.us, and Calcipedia all present BEA RPP data directly. Worth noting PlainCost's stated design philosophy specifically: present the breakdown by spending category transparently rather than blending it into one opaque score — that's a good principle to borrow (Section 8).
- **BLS OEWS (Occupational Employment and Wage Statistics)** — free, no-key-required, publishes real observed wage data by occupation and metro area. It directly covers Software Developers (SOC 15-1252): median annual wage was $135,980 in May 2025, broken out across ~600 metro/nonmetro areas. **SalariesByCity and USWages already combine BLS wages with BEA RPP** — validating that this exact combination (which you independently arrived at) is the right one.
- **The real gap: county-level.** RPP is only officially published at state/metro level. The Commerce Department published an actual working paper attempting county-level estimates from public data, finding Manhattan the most expensive county nationally (32.6% above the national average). This is a legitimate, citable research gap — you're extending published federal research, not guessing.
- **Free county-level feature data to build the estimator on:** Zillow Research publishes home-value (ZHVI) and rent (ZORI) indexes at the county level as free downloadable data (attribution to Zillow required per their Terms of Use — build this into the UI, Section 7). HUD Fair Market Rents are free at the county level, no key required.
- **3D map library:** `react-globe.gl` (MIT license, Three.js/WebGL) directly supports an "Elevated Polygons" pattern — extruded, color-coded regions with click handling — which is exactly the visual this project wants, without hand-building a Three.js scene from nothing.
- **Design reference:** Hack the North's own design write-ups describe building each year's site around one strong narrative/visual concept rather than generic dashboard chrome — and notably, a past Hack the North application portal used the *exact* interaction you asked for: a map that zooms into a city once a user types it in. That's a validated precedent, not a novel UX risk.

---

## 3. Your Decisions (from our discussion — locked in, not open questions)

- **Map scope:** full 3D rotating world globe (reverting the earlier US-locked decision) — but only US regions are clickable and populated with data for v1. Other countries render as visible landmass (for the immersive globe feel) but are non-interactive, with the data model built to make adding a country later a matter of adding data, not rearchitecting (Section 4).
- **County-level ML estimator:** in scope for v1, as a core differentiator.
- **Salary calibration:** specifically tuned to software engineering roles (BLS SOC 15-1252, Software Developers, plus closely related software SOC codes) rather than general/any-occupation.

---

## 4. Data Model

**Region** — id, country_code (default `US` — included now specifically so adding a second country later is a data change, not a schema migration), type (`state`/`metro`/`county`), FIPS code, name, parent_region_id (county→state), msa_id (nullable — which MSA a county belongs to, if any), geometry_ref (pointer to the simplified TopoJSON boundary), is_interactive (bool — false for any non-US region rendered for globe completeness but not yet backed by data).

**RPPRecord** — region_id, year, rpp_all_items, rpp_housing, rpp_goods, rpp_services (BEA publishes these sub-components officially at state/metro — pull all of them, not just the headline number, per PlainCost's transparency principle), source (`official_bea`).

**CountyFeature** — county_fips, year, zhvi (Zillow home value), zori (Zillow rent index), hud_fmr_studio/1br/2br/3br, state_income_tax_rate, local_sales_tax_rate, population_density. This is the ML model's input feature set (Section 6).

**CountyRPPEstimate** — county_fips, year, predicted_rpp_all_items, predicted_rpp_housing, confidence_interval, model_version, source (`modeled`) — only populated for counties **not** covered by an official metro RPP (see Section 6 — most populous counties already have an official number via their MSA; this table exists for the nonmetro gap).

**WageBenchmark** — region_id, soc_code, median_wage, mean_wage, year, source (`bls_oews`).

---

## 5. Legal & Data-Compliance Notes

- All core data sources here (BEA, BLS, Census, HUD) are official U.S. government data — public domain, no licensing restriction.
- **Zillow Research data is free for public use but requires visible attribution to Zillow** — this is a real term of their published data, not optional. Build a persistent, visible credit line into the footer/data-sources page (Section 8).
- No scraping is required anywhere in this pipeline — every source here is a direct free download or a free (if registration-gated) public API. BEA's API requires a free account signup for an API key; it is not literally keyless, but it costs nothing.

---

## 6. The ML County Estimator — Methodology

This needs a precise spec, since "add ML" is meaningless without one.

- **What's actually being estimated:** most populous US counties already have a usable number, because they sit inside an officially-covered BEA metro area — for those, **use the official metro RPP directly, tagged `official_bea`, no modeling needed.** The model's actual job is estimating RPP for counties **outside** any officially-covered metro (mostly rural/nonmetro counties) — this mirrors the actual motivation behind the Commerce Department's own experimental county paper.
- **Training labels:** official state and metro-level RPP values (all-items and housing sub-component) — a few hundred labeled rows.
- **Features (county level, all free):** Zillow ZHVI, Zillow ZORI, HUD Fair Market Rents by bedroom count, state + local tax rates, population density. **Deliberately exclude local wage/salary level as a feature** — using wages to predict a metric that will then be used to adjust wages is circular and would quietly bias the whole product toward "high-paying places are expensive because they're high-paying," which isn't the causal story you want.
- **Model choice — flag this explicitly rather than defaulting to something fancy:** the labeled training set (roughly 50 states + ~400 metros) is small. A complex gradient-boosted model risks overfitting on a dataset this size. Start with a regularized linear model (ElasticNet) with the housing-cost features as the dominant signal (housing is the largest driver of regional price differences per BEA's own methodology), and only move to a small Random Forest if cross-validation shows it actually generalizes better — don't reach for complexity by default.
- **Validation — two distinct checks, and be honest about what each one proves:**
  1. **K-fold cross-validation** on the official labeled state/metro data — this measures whether the model can recover a *known* RPP from the features alone.
  2. **Comparison against the Commerce Department's experimental county-level estimates**, wherever both exist — this is the "compared to actual values" check you asked for, but label it accurately in the UI and docs: Commerce's own dataset is explicitly experimental, not an official government product, so a match against it is "consistent with the best existing research estimate," not "verified correct." Never present a modeled county figure with the same visual confidence as an official one — the frontend must distinguish `official_bea` from `modeled` (Section 8).
- **Test — ML Model:** Assert cross-validation RMSE is computed and logged for every retrain, not just eyeballed once. Assert every `CountyRPPEstimate` row carries a `confidence_interval` — no bare point estimate without one. Assert the pipeline never overwrites an `official_bea` county with a modeled value, even if a modeled prediction exists for it.

---

## 7. Functional Requirements

### FR1 — Region Hierarchy & Geometry
- Ingest Census TIGER/Line state and county boundaries, simplified to a web-performant TopoJSON (3,143 counties at full detail is too heavy to ship raw).
- Tag each county with its parent state and, where applicable, its containing MSA (free Census/OMB crosswalk).
- **Test:** every county resolves to exactly one parent state; MSA membership matches the official OMB delineation file for a spot-checked sample.

### FR2 — Official RPP Ingestion
- Pull state and metro RPP (all-items + housing/goods/services sub-components) from BEA's API annually.
- **Test:** ingested values match BEA's published table for a spot-checked sample of states.

### FR3 — County Feature & ML Pipeline
- Ingest Zillow ZHVI/ZORI, HUD FMR, and tax rate data per county; run the estimator from Section 6 for nonmetro counties only.
- **Test:** see Section 6's test. Additionally, confirm a county that IS covered by an official metro never gets a `CountyRPPEstimate` row generated for it — the model shouldn't even run on data it has no business estimating.

### FR4 — BLS SWE Wage Ingestion
- Pull BLS OEWS wage data for SOC 15-1252 (Software Developers) and closely related software SOC codes, by state/metro, annually.
- **Test:** ingested median wage matches BLS's published table for a spot-checked state.

### FR5 — Salary Normalization Calculation
- Input: nominal salary, origin region (defaults to US national average if unspecified), destination region.
- Core calculation: `adjusted_salary = nominal_salary × (RPP_destination / RPP_origin)`.
- **Show the category breakdown** (housing vs. goods vs. services contribution to the adjustment), not just the final number — this is the PlainCost-style transparency principle from Section 2.
- **Optional toggle: include state income tax difference** — this is a materially different adjustment from cost-of-goods (RPP) and must be shown as a clearly separate line item, never blended into the RPP-based figure, so a user can tell which part of the change is "things cost more here" versus "the state taxes more."
- **Also show the real BLS median SWE wage for the destination** alongside the calculated figure — this is the genuinely differentiated insight: a user sees not just "your salary adjusts to $X" but "and by the way, the actual median software developer salary there is $Y," letting them judge whether an offer is actually competitive for that market, not just cost-adjusted.
- **Test:** known-value check — feed in a same-region query (origin = destination) and confirm the adjusted salary equals the input exactly. Feed in a query where destination RPP is a `modeled` county value and confirm the UI-facing response carries the `modeled` flag through to display, not just the backend.

### FR6 — Interactive 3D Globe
- `react-globe.gl`, full free-rotating world globe (not camera-locked) — this is the library's native mode, so no fighting the tool to constrain it.
- Render basic world landmass/country boundaries (free, public-domain Natural Earth boundary data is sufficient for non-interactive countries) for visual completeness, but **only US regions are clickable and carry data** — non-US countries should read as visibly present but clearly non-interactive (muted color, no hover response), not broken or half-built.
- Elevated-polygon choropleth on US states/counties: height and color driven by the selected metric (COL index or BLS wage). Click a state → camera transitions in, reveals its counties. Click a county → side panel shows its data and feeds the FR5 calculator.
- **Built for extension, not just US-shaped:** adding a second country later should mean adding `Region` rows with that country's code and `is_interactive: true`, plus that country's own price-data ingestion — not a rewrite of the globe component itself.
- **Test:** clicking a US state programmatically in a test harness triggers the expected camera transition and county reveal; clicking a county populates the calculator's destination field correctly; clicking a non-US country triggers no data lookup and no error — confirm it fails gracefully (e.g., a "not yet supported" tooltip) rather than throwing.

### FR7 — Search-to-Zoom
- Text search (city/county/state name) → geocode via the free US Census Geocoding API → animate the camera to that location, auto-select the matching region.
- **Test:** a fixture set of ambiguous names (e.g. "Washington" — state vs. county vs. multiple cities) resolves to a disambiguation prompt rather than a silent wrong guess.

### FR8 — Accessible Non-Map Path
- Every piece of functionality reachable via the 3D map must also be reachable through a plain search/dropdown + results table, for anyone not using a mouse or not wanting 3D interaction.
- **Test:** the full calculate flow (pick origin, pick destination, enter salary, get result) completes with zero interaction with the map component.

---

## 8. Frontend & Design Requirements

This is explicitly meant to look like a distinctive, professional, "could win a design award" site — not a generic finance dashboard. Direction for whoever builds it:

- **Reference points:** Hack the North's approach of building the whole site around one strong idea rather than templated sections, and their validated "search zooms into the place" interaction (Section 2). The 3D globe is the one moment to spend real design boldness on — per general design discipline, everything else on the page should stay quiet and disciplined around it, not compete with it.
- **Avoid the generic tells:** identical rounded cards with the same soft shadow, gradient-wash decoration, ALL-CAPS tracked-out labels, em-dash-joined meta text. Pick a deliberate typographic and color system specific to *this* subject — a geographic/economic data tool — rather than a default startup palette.
- **Transparency as a design principle, not just a data principle:** since Section 7 requires showing the category breakdown and the `official` vs `modeled` distinction, design these as a visible, legible part of the result — not a tooltip buried behind a hover.
- **Zillow attribution (Section 5)** — visible in the footer or a dedicated data-sources page, not hidden in fine print nobody reads.
- **Accessibility:** FR8's non-map path is a real requirement, not a checkbox — the 3D map must respect `prefers-reduced-motion` (fall back to a static, still-interactive flat choropleth) and the whole flow must be keyboard-navigable.

---

## 9. Free-Tier Full-Stack Deployment

| Layer | Tool | Why |
|---|---|---|
| Frontend | Next.js + `react-globe.gl` + Tailwind, on Vercel (free) | Matches your existing stack; `react-globe.gl`'s Elevated Polygons pattern gets the 3D visual without a from-scratch Three.js build |
| Backend API | Python (FastAPI), on Render free web service | Python's ML ecosystem (scikit-learn) is the natural fit for Section 6's estimator |
| Database | PostgreSQL via Supabase (free) | Consistent with your other projects |
| ML training + data refresh | Scheduled GitHub Actions workflow (free for public repos) | BEA RPP updates annually, Zillow/HUD monthly — a scheduled batch job matches BOTH cadences without needing an always-on worker |
| Geometry | Pre-simplified TopoJSON committed as a static asset, served via Vercel | Avoids needing a live geometry/tile service just to draw county borders |
| Data sources | BEA API (free, registration required), BLS OEWS (free, no key), Census TIGER/Line + Geocoding API (free, no key), Zillow Research CSV (free, attribution required), HUD FMR (free, no key) | Every source here is genuinely free; none require scraping |

---

## 10. Suggested Build Order

1. Region hierarchy + geometry (FR1) — nothing else works without a place to attach data to.
2. Official RPP ingestion (FR2) — get the state/metro baseline solid before touching the harder county estimation problem.
3. BLS wage ingestion (FR4) — independent of the RPP pipeline, can be built in parallel with step 2.
4. Salary normalization calculation (FR5) — build and test this against official-only data first, before the ML layer exists, so you have a working core product early.
5. County feature ingestion + ML estimator (FR3/Section 6) — the most technically involved piece; build it once FR5 already proves out the calculation logic it feeds into.
6. 3D map (FR6) — once there's real data to visualize, not before.
7. Search-to-zoom (FR7) and the accessible non-map path (FR8) together, since FR8 is effectively "everything FR6/FR7 do, without the map."
8. Design pass (Section 8) once every page has real data flowing through it.
