------------------------------------------------------------------------
-- EXTENSIONS
------------------------------------------------------------------------
LOAD icu;
LOAD vss;

-- Allow HNSW indexes to live in a disk-backed DB
SET hnsw_enable_experimental_persistence = true;

------------------------------------------------------------------------
-- ENUM TYPES
------------------------------------------------------------------------
CREATE TYPE event_kind AS ENUM (
  'digital_activity',
  'health_metric',
  'location_visit',
  'media_note',
  'photo'
);
CREATE TYPE processing_status_enum AS ENUM ('pending','processed','error');

------------------------------------------------------------------------
-- RAW EVENTS TABLE (must come first for FK references)
------------------------------------------------------------------------
CREATE TABLE events (
  id UUID PRIMARY KEY,
  source         VARCHAR NOT NULL,
  event_type     event_kind NOT NULL,
  start_time     TIMESTAMPTZ NOT NULL,
  end_time       TIMESTAMPTZ,
  payload_hash   VARCHAR NOT NULL UNIQUE,
  processing_status processing_status_enum DEFAULT 'pending' NOT NULL,

  -- virtual generated column (DuckDB supports only VIRTUAL) :contentReference[oaicite:0]{index=0}
  local_day DATE GENERATED ALWAYS AS (
    start_time AT TIME ZONE 'America/Vancouver'
  )
);
CREATE INDEX events_local_day_idx ON events(local_day);

------------------------------------------------------------------------
-- PROJECTS (must precede tables that reference it)
------------------------------------------------------------------------
CREATE TABLE projects (
  id        UUID PRIMARY KEY,
  name      VARCHAR NOT NULL,
  embedding FLOAT[128]                      -- fixed-size ARRAY syntax :contentReference[oaicite:1]{index=1}
);

-- case-insensitive uniqueness
CREATE UNIQUE INDEX projects_name_ci_idx ON projects (lower(name));

CREATE INDEX project_embedding_idx
  ON projects USING HNSW (embedding)
  WITH (metric = 'cosine');                 -- option name = metric :contentReference[oaicite:2]{index=2}

------------------------------------------------------------------------
-- TABLES THAT REFERENCE projects OR events
------------------------------------------------------------------------
CREATE TABLE timeline_entries (
  id UUID PRIMARY KEY,
  start_time TIMESTAMPTZ NOT NULL,
  end_time   TIMESTAMPTZ NOT NULL,
  title      VARCHAR NOT NULL,
  summary    VARCHAR,
  project_id UUID,
  source_event_ids UUID[],

  FOREIGN KEY(project_id) REFERENCES projects(id)
);

CREATE INDEX timeline_time_idx
  ON timeline_entries(start_time,end_time);

CREATE TABLE digital_activity_data (
  event_id UUID PRIMARY KEY,
  hostname VARCHAR NOT NULL,
  app      VARCHAR,
  title    VARCHAR,
  url      VARCHAR,

  FOREIGN KEY(event_id) REFERENCES events(id)
);

------------------------------------------------------------------------
-- OPTIONAL ALIAS TABLE
------------------------------------------------------------------------
CREATE TABLE project_aliases (
  alias      VARCHAR PRIMARY KEY,
  project_id UUID NOT NULL,
  FOREIGN KEY(project_id) REFERENCES projects(id)
);

------------------------------------------------------------------------
-- END SCHEMA
------------------------------------------------------------------------
