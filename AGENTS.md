# AGENTS.md — Colculator

Persistent rules for any Codex task in this repo. Read this before starting any task, even if the task description doesn't repeat it.

## What this project is
A US cost-of-living-adjusted salary calculator for software engineering roles, centered on an interactive 3D globe. Full spec: `docs/colculator_requirements.md` (attach/reference it in every task — it is the source of truth, this file is just standing conventions).

## Stack (do not substitute without asking)
- Frontend: Next.js + Tailwind + `react-globe.gl`, deployed to Vercel (free tier)
- Backend: Python + FastAPI, deployed to Render (free tier)
- Database: PostgreSQL via Supabase (free tier)
- ML: scikit-learn, trained via a scheduled GitHub Actions workflow, not an always-on service
- All data sources must be the free ones named in the spec (BEA, BLS, Census, Zillow Research, HUD) — no substituting a paid data vendor to save build time.

## Non-negotiable rules
1. **Never invent a number.** If a value can't be confidently sourced or modeled, mark it missing/unavailable in the data model — never fill it with a guess. This applies to salary figures, RPP estimates, and geocoding matches alike.
2. **Never present a `modeled` value with the same visual/data confidence as an `official_bea` value.** Every UI surface and every API response must carry the source tag through, not just the backend.
3. **Zillow Research data requires visible attribution** wherever it's used — this is a real term of their data license, not a style choice.
4. **The county-level ML estimator (spec Section 6) must never run on a county that already has official metro-level coverage.** Check this before generating a prediction, not after.
5. Every functional requirement in the spec has a "Test —" line. Treat that as the actual acceptance criteria for the corresponding task — write and pass that test before considering the task done, not after.

## Working style
- Follow the build order in spec Section 10 as separate phases/sessions, not one giant task — each phase should end in its own PR with its own passing tests, per that section's ordering.
- If a phase's task is ambiguous against the spec, stop and ask rather than guessing on anything touching the rules above.
- Run the full test suite before opening a PR, and include the test output in the PR description.

## Commands
- Install: `npm ci`
- Build region data: `npm run build:regions`
- Build official RPP data: `npm run build:rpp` (requires `BEA_API_KEY` in the environment or root `.env`)
- Test (frontend): `npm run test:frontend`
- Test (backend): `npm run test:backend`
- Test (full): `npm test`
- Lint: `npm run lint`
- Dependency audit: `npm audit --audit-level=moderate`
