# Generated tax-rate input

Run `npm run build:taxes` to generate `county_tax_rates.csv` and the committed
`frontend/public/data/state_income_tax_rules.json`. The importer reads
Tax Foundation's 2026 workbooks, computes values once per state, and applies the
same pair to every FR1 county in that state. D.C. is included because it is a
state-level region in the catalog.

Rates use decimal proportions (`0.093` means 9.3%), never whole percentages.
Every value has its own HTTPS source URL. The build rejects blank rates, missing
counties, malformed FIPS codes, and unsourced rows instead of inventing or
silently imputing tax data.

`state_income_tax_rate` is the effective rate at $100,000 gross income for a
single filer. The importer subtracts the published single-filer standard
deduction and personal exemption, applies the published brackets sequentially,
and applies items explicitly labeled as credits against tax owed. AK, FL, NV,
NH, SD, TN, TX, WA, and WY are explicit `0.0` wage-income-tax values.

The rules artifact preserves those same single-filer deductions, exemptions,
credits, and progressive brackets so the offer-value calculator can estimate
state tax at the salary actually entered instead of reusing the $100,000 rate.

`local_sales_tax_rate` is Tax Foundation's published combined state plus
population-weighted-average-local rate, used as-is. Local income taxes (notably
New York City and some municipalities in Ohio and Pennsylvania) are outside v1;
the state-level income rate is applied uniformly for consistency.
