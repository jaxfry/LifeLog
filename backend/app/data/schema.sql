-- EXTENSIONS
LOAD icu;
LOAD vss;

-- Allow HNSW indexes to live in a disk-backed DB
SET hnsw_enable_experimental_persistence = true;

-- ENUM TYPES
CREATE TYPE event_kind AS ENUM (
  'digital_activity',
  'health_metric',
  'location_visit',
  'media_note',
  'photo'
);

CREATE TYPE processing_status_enum AS ENUM (
  'pending',
  'processed',
  'error'
);

-- RAW EVENTS TABLE
CREATE TABLE events (
  id UUID PRIMARY KEY,
  source VARCHAR NOT NULL,
  event_type event_kind NOT NULL,
  start_time TIMESTAMPTZ NOT NULL,
  end_time TIMESTAMPTZ,
  payload_hash VARCHAR NOT NULL UNIQUE,
  -- A BIGINT prefix of the hash can be faster for indexed lookups at scale.
  -- payload_hash_prefix BIGINT GENERATED ALWAYS AS (hashtext(payload_hash) & 9223372036854775807),
  processing_status processing_status_enum DEFAULT 'pending' NOT NULL,
  -- local_day is now using America/Vancouver timezone
  local_day DATE GENERATED ALWAYS AS (
    (start_time AT TIME ZONE 'America/Vancouver')::date
  )
);

CREATE INDEX events_local_day_idx ON events(local_day);
-- Partial index for the batch processor's main query. Critical for performance.
CREATE INDEX events_status_time_idx ON events(processing_status, start_time);


-- PROJECTS
CREATE TABLE projects (
  id UUID PRIMARY KEY,
  name VARCHAR NOT NULL,
  embedding FLOAT[128]
);

CREATE UNIQUE INDEX projects_name_ci_idx ON projects (lower(name));
-- VSS index for fast similarity search.
CREATE INDEX project_embedding_idx
  ON projects USING HNSW (embedding)
  WITH (metric = 'cosine');


-- TABLES THAT REFERENCE projects OR events
CREATE TABLE timeline_entries (
  id UUID PRIMARY KEY,
  start_time TIMESTAMPTZ NOT NULL,
  end_time TIMESTAMPTZ NOT NULL,
  title VARCHAR NOT NULL,
  summary VARCHAR,
  project_id UUID,
  FOREIGN KEY(project_id) REFERENCES projects(id)
);

-- Link table for N:M relationship between timeline entries and source events.
-- More flexible and performant than a UUID array for updates.
CREATE TABLE timeline_source_events (
    entry_id UUID NOT NULL,
    event_id UUID NOT NULL,
    PRIMARY KEY (entry_id, event_id),
    FOREIGN KEY(entry_id) REFERENCES timeline_entries(id),
    FOREIGN KEY(event_id) REFERENCES events(id)
);

CREATE INDEX timeline_time_idx
  ON timeline_entries(start_time, end_time);


CREATE TABLE digital_activity_data (
  event_id UUID PRIMARY KEY,
  hostname VARCHAR NOT NULL,
  app VARCHAR,
  title VARCHAR,
  url VARCHAR,
  FOREIGN KEY(event_id) REFERENCES events(id)
);


-- OPTIONAL ALIAS TABLE
CREATE TABLE project_aliases (
  alias VARCHAR PRIMARY KEY,
  project_id UUID NOT NULL,
  FOREIGN KEY(project_id) REFERENCES projects(id)
);