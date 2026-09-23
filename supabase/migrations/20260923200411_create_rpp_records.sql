create table public.rpp_records (
  region_id text not null references public.regions (id) on delete cascade,
  year smallint not null,
  rpp_all_items numeric,
  rpp_goods numeric,
  rpp_housing numeric,
  rpp_utilities numeric,
  rpp_other_services numeric,
  source text not null default 'official_bea',
  primary key (region_id, year),
  constraint rpp_records_year_range check (year between 2000 and 2100),
  constraint rpp_records_source check (source = 'official_bea'),
  constraint rpp_records_positive_values check (
    (rpp_all_items is null or rpp_all_items > 0) and
    (rpp_goods is null or rpp_goods > 0) and
    (rpp_housing is null or rpp_housing > 0) and
    (rpp_utilities is null or rpp_utilities > 0) and
    (rpp_other_services is null or rpp_other_services > 0)
  ),
  constraint rpp_records_has_value check (
    num_nonnulls(
      rpp_all_items,
      rpp_goods,
      rpp_housing,
      rpp_utilities,
      rpp_other_services
    ) > 0
  )
);

create index rpp_records_year_idx on public.rpp_records (year);

alter table public.rpp_records enable row level security;

revoke all on table public.rpp_records from anon, authenticated;
grant select on table public.rpp_records to anon, authenticated;
grant all on table public.rpp_records to service_role;

create policy "Official RPP records are publicly readable"
on public.rpp_records
for select
to anon, authenticated
using (true);
