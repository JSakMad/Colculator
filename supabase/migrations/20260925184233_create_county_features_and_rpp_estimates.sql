create table public.county_features (
  county_fips text not null,
  year smallint not null,
  zhvi numeric,
  zori numeric,
  hud_fmr_studio numeric,
  hud_fmr_1br numeric,
  hud_fmr_2br numeric,
  hud_fmr_3br numeric,
  state_income_tax_rate numeric,
  local_sales_tax_rate numeric,
  population_density numeric,
  source_metadata jsonb not null,
  primary key (county_fips, year),
  constraint county_features_fips_shape check (county_fips ~ '^[0-9]{5}$'),
  constraint county_features_year_range check (year between 2000 and 2100),
  constraint county_features_nonnegative_values check (
    (zhvi is null or zhvi >= 0) and
    (zori is null or zori >= 0) and
    (hud_fmr_studio is null or hud_fmr_studio >= 0) and
    (hud_fmr_1br is null or hud_fmr_1br >= 0) and
    (hud_fmr_2br is null or hud_fmr_2br >= 0) and
    (hud_fmr_3br is null or hud_fmr_3br >= 0) and
    (state_income_tax_rate is null or state_income_tax_rate between 0 and 1) and
    (local_sales_tax_rate is null or local_sales_tax_rate between 0 and 1) and
    (population_density is null or population_density >= 0)
  ),
  constraint county_features_source_metadata check (
    jsonb_typeof(source_metadata) = 'object' and
    source_metadata ? 'field_source_tags' and
    source_metadata ? 'tax_source_url'
  )
);

create table public.county_rpp_estimates (
  county_fips text not null,
  year smallint not null,
  predicted_rpp_all_items numeric not null,
  predicted_rpp_housing numeric not null,
  confidence_interval jsonb not null,
  model_version text not null,
  source text not null default 'modeled',
  primary key (county_fips, year),
  constraint county_rpp_estimates_fips_shape check (county_fips ~ '^[0-9]{5}$'),
  constraint county_rpp_estimates_year_range check (year between 2000 and 2100),
  constraint county_rpp_estimates_positive_values check (
    predicted_rpp_all_items > 0 and predicted_rpp_housing > 0
  ),
  constraint county_rpp_estimates_source check (source = 'modeled'),
  constraint county_rpp_estimates_confidence_interval check (
    jsonb_typeof(confidence_interval) = 'object' and
    confidence_interval ? 'all_items' and
    confidence_interval ? 'housing' and
    confidence_interval ? 'level' and
    confidence_interval ? 'method'
  )
);

create index county_features_year_idx on public.county_features (year);
create index county_rpp_estimates_year_idx on public.county_rpp_estimates (year);

create function public.enforce_county_feature_region()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if not exists (
    select 1
    from public.regions
    where type = 'county' and fips = new.county_fips
  ) then
    raise exception 'county_features county_fips % is not a county region', new.county_fips;
  end if;
  return new;
end;
$$;

create function public.enforce_nonmetro_county_estimate()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if not exists (
    select 1
    from public.regions
    where type = 'county'
      and fips = new.county_fips
      and msa_id is null
  ) then
    raise exception 'county_rpp_estimates only accepts nonmetro county FIPS: %', new.county_fips;
  end if;
  return new;
end;
$$;

create trigger county_features_require_county
before insert or update on public.county_features
for each row execute function public.enforce_county_feature_region();

create trigger county_rpp_estimates_require_nonmetro_county
before insert or update on public.county_rpp_estimates
for each row execute function public.enforce_nonmetro_county_estimate();

alter table public.county_features enable row level security;
alter table public.county_rpp_estimates enable row level security;

revoke all on table public.county_features from anon, authenticated;
revoke all on table public.county_rpp_estimates from anon, authenticated;
grant select on table public.county_features to anon, authenticated;
grant select on table public.county_rpp_estimates to anon, authenticated;
grant all on table public.county_features to service_role;
grant all on table public.county_rpp_estimates to service_role;

create policy "County features are publicly readable"
on public.county_features
for select
to anon, authenticated
using (true);

create policy "Modeled county RPP estimates are publicly readable"
on public.county_rpp_estimates
for select
to anon, authenticated
using (true);
