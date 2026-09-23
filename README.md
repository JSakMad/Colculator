# Colculator

A US cost-of-living-adjusted salary calculator for software engineering roles,
centered on an interactive 3D globe. Work is intentionally delivered in the
phases defined by [`docs/colculator_requirements.md`](docs/colculator_requirements.md).

## Current phase

Phase 3 implements FR4 on top of the region and RPP foundations:

- official BLS OEWS state and metropolitan-area annual wage ingestion
- all five detailed occupations in the 15-1250 software broad group
- explicit statuses for suppressed values, which remain null rather than estimated
- source-tagged static data plus a read-only, RLS-protected Supabase table
- exact May 2025 published-value spot checks for California, Mississippi, and Texas
- an annual GitHub Actions refresh after the expected spring OEWS release

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
npm run build:regions
npm run build:rpp
npm run build:wages
npm test
npm run lint
npm audit --audit-level=moderate
```

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

## Repository layout

- `backend/src/colculator/regions`: official-data ingestion and hierarchy logic
- `backend/src/colculator/rpp`: official BEA RPP API ingestion
- `backend/src/colculator/wages`: official BLS OEWS wage ingestion
- `frontend/public/data`: generated region catalog, provenance, and geometry
- `supabase/migrations`: database schema with public read-only RLS policy
- `supabase/seed.sql` and `supabase/seeds`: deterministic official-data rows
- `backend/tests` and `frontend/tests`: FR1, FR2, and FR4 acceptance coverage

No taxes or modeled values are introduced in Phase 3.
