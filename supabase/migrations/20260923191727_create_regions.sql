create type public.region_type as enum ('state', 'metro', 'county');

create table public.regions (
  id text primary key,
  country_code text not null default 'US',
  type public.region_type not null,
  fips text not null,
  name text not null,
  parent_region_id text references public.regions (id),
  msa_id text references public.regions (id),
  geometry_ref text,
  is_interactive boolean not null default false,
  constraint regions_country_code_iso_shape check (country_code ~ '^[A-Z]{2}$'),
  constraint regions_fips_shape check (
    (type = 'state' and fips ~ '^[0-9]{2}$') or
    (type in ('metro', 'county') and fips ~ '^[0-9]{5}$')
  ),
  constraint regions_parent_shape check (
    (type = 'county' and parent_region_id is not null) or
    (type in ('state', 'metro') and parent_region_id is null)
  ),
  constraint regions_msa_shape check (type = 'county' or msa_id is null),
  constraint regions_geometry_shape check (
    (type in ('state', 'county') and geometry_ref is not null) or
    (type = 'metro' and geometry_ref is null)
  ),
  unique (country_code, type, fips)
);

create index regions_parent_region_id_idx on public.regions (parent_region_id);
create index regions_msa_id_idx on public.regions (msa_id);
create index regions_type_name_idx on public.regions (type, name);

alter table public.regions enable row level security;

revoke all on table public.regions from anon, authenticated;
grant select on table public.regions to anon, authenticated;

create policy "Regions are publicly readable"
on public.regions
for select
to anon, authenticated
using (true);
