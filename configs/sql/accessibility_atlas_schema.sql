create table if not exists origins (
  origin_id text primary key,
  name text not null,
  municipality text not null,
  neighborhood text not null,
  geom geometry(point, 4326) not null,
  population_weight double precision default 1.0,
  is_active boolean default true
);

create table if not exists pois (
  poi_id text primary key,
  name text not null,
  category text not null check (category in ('campus', 'hospital', 'job_hub')),
  geom geometry(point, 4326) not null,
  weight double precision not null,
  nearest_stop_id text,
  candidate_stop_ids text[] default '{}'
);

create table if not exists scenarios (
  scenario_id text primary key,
  label text not null,
  depart_at_local timestamp without time zone not null,
  description text,
  default_max_changes integer not null default 2
);

create table if not exists reachability_results (
  origin_id text not null references origins(origin_id),
  scenario_id text not null references scenarios(scenario_id),
  max_changes integer not null,
  duration_minutes integer not null,
  reachable_stop_ids text[] not null,
  source_mode text not null,
  request_url text,
  computed_at_utc timestamptz not null default now(),
  primary key (origin_id, scenario_id, max_changes, duration_minutes)
);

create table if not exists accessibility_metrics (
  origin_id text not null references origins(origin_id),
  scenario_id text not null references scenarios(scenario_id),
  max_changes integer not null,
  duration_minutes integer not null,
  campus_count integer not null default 0,
  hospital_count integer not null default 0,
  job_hub_count integer not null default 0,
  weighted_access_score double precision not null default 0,
  nearest_campus_time_min integer,
  nearest_hospital_time_min integer,
  nearest_job_hub_time_min integer,
  computed_at_utc timestamptz not null default now(),
  primary key (origin_id, scenario_id, max_changes, duration_minutes)
);

create table if not exists exemplar_trips (
  origin_id text not null references origins(origin_id),
  poi_id text not null references pois(poi_id),
  scenario_id text not null references scenarios(scenario_id),
  max_changes integer not null,
  trip_json jsonb not null,
  fetched_at_utc timestamptz not null default now(),
  primary key (origin_id, poi_id, scenario_id, max_changes)
);
