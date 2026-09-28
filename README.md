# Colculator

A US cost-of-living-adjusted salary calculator for software engineering roles,
centered on an interactive 3D globe. Work is intentionally delivered in the
phases defined by [`docs/colculator_requirements.md`](docs/colculator_requirements.md).

## Current phase

Phase 5 implements FR3 and Section 6 on top of the official-data calculator:

- county Zillow ZHVI/ZORI ingestion with missing observations preserved as null
- county HUD FMR and Census population-density ingestion
- source-tagged, strict tax-rate input with no guessed or unsourced values
- population-weighted state/metro training rows with local wages explicitly excluded
- an ElasticNet baseline with five-fold cross-validation RMSE logged on every run
- 95% residual-based confidence intervals on every modeled county estimate
- hard pipeline and database guards that prevent prediction for metro-covered counties
- a separately labeled comparison to Commerce's experimental research estimates

Phase 4 already provides:

- FastAPI salary normalization using the exact FR5 RPP ratio
- national-average origin default and official metro inheritance for covered counties
- separate housing, goods, utilities, and other-services comparisons without invented weights
- destination BLS median wage alongside the normalized result
- source, confidence interval, and model version propagation for future modeled counties
- an explicit unavailable tax result until sourced tax inputs and assumptions exist

The committed source manifest at
[`frontend/public/data/regions.sources.json`](frontend/public/data/regions.sources.json)
contains every official geometry input URL, vintage, checksum, and transformation.
RPP provenance and the lossless BEA line-code mapping are in
[`frontend/public/data/rpp.sources.json`](frontend/public/data/rpp.sources.json).
BLS archive URLs, checksums, suppression semantics, and the complete SOC scope are
in [`frontend/public/data/wages.sources.json`](frontend/public/data/wages.sources.json).

## Commands

```bash
npm ci
python3 -m venv .venv
.venv/bin/python -m pip install -e 'backend[test]'
npm run build:regions
npm run build:rpp
npm run build:wages
npm run build:taxes
npm run build:county-features
npm run train:county-rpp -- --commerce-csv data/reference/commerce_experimental_county_rpp.csv
npm test
npm run lint
npm audit --audit-level=moderate
```

In a separate terminal, run `npm run start:backend` to start the API.

`npm run build:regions` downloads only the checksum-pinned official Census/OMB
inputs and regenerates the region catalog, TopoJSON, and `supabase/seed.sql`.
The first build requires network access; subsequent builds reuse `.cache/regions`.

Copy `.env.example` to `.env`, add the free BEA API key, and run
`npm run build:rpp` to select the latest year available in both SARPP and MARPP.
The key is used only for API requests and is never written to generated files.

`npm run build:wages` uses the latest paired release in `.cache/wages`, or the
preceding year's official state and metro archive URLs during the annual
late-May refresh. The workbook vintage is validated before output. It requires
no API key; `-- --year YYYY` can select a different published vintage.

`npm run build:taxes` generates county-expanded 2026 Tax Foundation income and
sales-tax features using the uniform state-level convention documented in
[`data/manual/README.md`](data/manual/README.md).

`npm run build:county-features` uses the December 2024 Zillow county ZHVI/ZORI
observations, FY 2024 HUD FMRs, and Census 2024 population and land area. HUD's
free dataset API token must be set as `HUD_API_TOKEN` in `.env` and as the same
repository secret for scheduled GitHub Actions. Run `npm run build:taxes` first
to generate the approved tax input. The feature build rejects missing tax rows
and population-weights HUD's conflicting New England town values with official
2020 Census PL county-subdivision populations. The 2024 Census subdivision
Gazetteer maps Connecticut's legacy HUD town codes to its current planning
regions.

`npm run train:county-rpp` aggregates county inputs to official BEA state and
metro labels, logs cross-validation metrics, trains the ElasticNet baseline,
and predicts only counties whose FR1 `msa_id` is null. The optional Commerce
file location and its required research-only interpretation are documented in
[`data/reference/README.md`](data/reference/README.md).

`npm run start:backend` serves the API at `http://localhost:8000`. POST
`/v1/calculate` with a nominal salary and destination region; omit the origin
to use BEA's national-average index of 100. The optional tax request is clearly
reported as unavailable and never changes the RPP result until sourced tax data
and calculation assumptions are added in a later phase.

## Repository layout

- `backend/src/colculator/regions`: official-data ingestion and hierarchy logic
- `backend/src/colculator/rpp`: official BEA RPP API ingestion
- `backend/src/colculator/wages`: official BLS OEWS wage ingestion
- `backend/src/colculator/calculator`: FR5 calculation and response contract
- `frontend/public/data`: generated region catalog, provenance, and geometry
- `supabase/migrations`: database schema with public read-only RLS policy
- `supabase/seed.sql` and `supabase/seeds`: deterministic official-data rows
- `backend/tests` and `frontend/tests`: FR1, FR2, FR4, and FR5 acceptance coverage

The calculator repository automatically resolves a nonmetro county to a
source-tagged modeled estimate when the generated Phase 5 artifact is present.
Official metro inheritance always takes priority and modeled values can never
replace an `official_bea` result.
