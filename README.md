# Colculator

A US cost-of-living-adjusted salary calculator for software engineering roles,
centered on an interactive 3D globe. Work is intentionally delivered in the
phases defined by [`docs/colculator_requirements.md`](docs/colculator_requirements.md).

## Current phase

Phase 2 implements FR2 on top of the Phase 1 region foundation:

- official BEA state and metropolitan-area RPP ingestion through the Regional API
- all five published series: all items, goods, housing, utilities, and other services
- source-tagged static data plus a read-only, RLS-protected Supabase table
- exact 2024 published-value spot checks for California, Mississippi, and Texas
- an annual GitHub Actions refresh after BEA's scheduled December release

The committed source manifest at
[`frontend/public/data/regions.sources.json`](frontend/public/data/regions.sources.json)
contains every official geometry input URL, vintage, checksum, and transformation.
RPP provenance and the lossless BEA line-code mapping are in
[`frontend/public/data/rpp.sources.json`](frontend/public/data/rpp.sources.json).

## Commands

```bash
npm ci
npm run build:regions
npm run build:rpp
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

## Repository layout

- `backend/src/colculator/regions`: official-data ingestion and hierarchy logic
- `backend/src/colculator/rpp`: official BEA RPP API ingestion
- `frontend/public/data`: generated region catalog, provenance, and geometry
- `supabase/migrations`: database schema with public read-only RLS policy
- `supabase/seed.sql` and `supabase/seeds`: deterministic official-data rows
- `backend/tests` and `frontend/tests`: FR1 and FR2 acceptance coverage

No salary, wage, tax, or modeled values are introduced in Phase 2.
