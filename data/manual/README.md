# Manual official-source inputs

Phase 5 expects `county_tax_rates.csv` in this directory. Start from
`county_tax_rates.template.csv`; include one row for every FR1 county and the
2024 model year.

Rates use decimal proportions (`0.093` means 9.3%), never whole percentages.
Every row must carry an HTTPS source URL. The build intentionally rejects blank
rates, missing counties, malformed FIPS codes, and unsourced rows instead of
inventing or silently imputing tax data.

The requirements do not define whether `state_income_tax_rate` is a top
marginal, flat, or effective rate, nor how a county-level local sales-tax rate
should represent municipalities with different rates. Record the approved
project-wide definition here before adding the production CSV.
