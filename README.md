# Colculator

A US cost-of-living-adjusted salary calculator for software engineering roles,
centered on an interactive 3D globe. Work is intentionally delivered in the
phases defined by [`docs/colculator_requirements.md`](docs/colculator_requirements.md).

## Current phase

Phase 4 implements FR5 on top of the official region, RPP, and wage data:

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

No tax rate or modeled RPP is introduced in Phase 4. The response contract is
tested with a modeled fixture so Phase 5 cannot lose its source/confidence tags.
