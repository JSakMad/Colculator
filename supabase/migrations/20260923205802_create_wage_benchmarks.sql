create table public.wage_benchmarks (
  region_id text not null references public.regions (id) on delete cascade,
  soc_code text not null,
  median_wage numeric,
  mean_wage numeric,
  median_wage_status text not null,
  mean_wage_status text not null,
  year smallint not null,
  source text not null default 'bls_oews',
  primary key (region_id, soc_code, year),
  constraint wage_benchmarks_soc_code_format check (soc_code ~ '^[0-9]{2}-[0-9]{4}$'),
  constraint wage_benchmarks_year_range check (year between 2000 and 2100),
  constraint wage_benchmarks_source check (source = 'bls_oews'),
  constraint wage_benchmarks_positive_values check (
    (median_wage is null or median_wage > 0) and
    (mean_wage is null or mean_wage > 0)
  ),
  constraint wage_benchmarks_median_status check (
    median_wage_status in ('published', 'not_available', 'top_coded', 'not_reported') and
    ((median_wage_status = 'published') = (median_wage is not null))
  ),
  constraint wage_benchmarks_mean_status check (
    mean_wage_status in ('published', 'not_available', 'top_coded', 'not_reported') and
    ((mean_wage_status = 'published') = (mean_wage is not null))
  )
);

create index wage_benchmarks_lookup_idx
on public.wage_benchmarks (soc_code, year, region_id);

alter table public.wage_benchmarks enable row level security;

revoke all on table public.wage_benchmarks from anon, authenticated;
grant select on table public.wage_benchmarks to anon, authenticated;
grant all on table public.wage_benchmarks to service_role;

create policy "BLS OEWS wage benchmarks are publicly readable"
on public.wage_benchmarks
for select
to anon, authenticated
using (true);
