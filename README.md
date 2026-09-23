# Colculator

A US cost-of-living-adjusted salary calculator for software engineering roles,
centered on an interactive 3D globe. Work is intentionally delivered in the
phases defined by [`docs/colculator_requirements.md`](docs/colculator_requirements.md).

## Current phase

Phase 1 implements FR1, the region hierarchy and geometry foundation:

- 2025 Census TIGER/Line state and county boundaries for the 50 states and D.C.
- July 2023 OMB metropolitan delineations, including explicit null membership
  for counties that are nonmetro or only micropolitan
- browser-ready, topology-preserving TopoJSON static assets
- a read-only, RLS-protected Supabase `regions` migration and deterministic seed
- acceptance tests for every county parent and official MSA spot checks

The committed source manifest at
[`frontend/public/data/regions.sources.json`](frontend/public/data/regions.sources.json)
contains every official input URL, vintage, checksum, and transformation.

## Commands

```bash
npm ci
npm run build:regions
npm test
npm run lint
npm audit --audit-level=moderate
```

`npm run build:regions` downloads only the checksum-pinned official Census/OMB
inputs and regenerates the region catalog, TopoJSON, and `supabase/seed.sql`.
The first build requires network access; subsequent builds reuse `.cache/regions`.

## Repository layout

- `backend/src/colculator/regions`: official-data ingestion and hierarchy logic
- `frontend/public/data`: generated region catalog, provenance, and geometry
- `supabase/migrations`: database schema with public read-only RLS policy
- `supabase/seed.sql`: deterministic Region rows generated from official inputs
- `backend/tests` and `frontend/tests`: FR1 acceptance coverage

No salary, RPP, wage, tax, or modeled values are introduced in Phase 1.
