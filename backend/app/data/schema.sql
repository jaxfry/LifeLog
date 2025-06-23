-- EXTENSIONS
INSTALL vss;
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

-- RAW EVENTS TABLE (now immutable regarding processing status)
CREATE TABLE events (
  id UUID PRIMARY KEY,
  source VARCHAR NOT NULL,
  event_type event_kind NOT NULL,
  start_time TIMESTAMPTZ NOT NULL,
  end_time TIMESTAMPTZ,
  payload_hash VARCHAR NOT NULL UNIQUE,
  local_day DATE GENERATED ALWAYS AS (
    (start_time AT TIME ZONE 'America/Vancouver')::date
  )
);

CREATE INDEX events_local_day_idx ON events(local_day);
CREATE INDEX events_start_time_idx ON events(start_time);


-- State tracking for events
CREATE TABLE event_state (
  event_id     UUID PRIMARY KEY,
  processed_at TIMESTAMPTZ DEFAULT NOW()
);


-- PROJECTS
CREATE TABLE projects (
  id UUID PRIMARY KEY,
  name VARCHAR NOT NULL,
  embedding FLOAT[128]
);

CREATE UNIQUE INDEX projects_name_ci_idx ON projects (lower(name));
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
  local_day DATE GENERATED ALWAYS AS (
    (start_time AT TIME ZONE 'America/Vancouver')::date
  ),
  FOREIGN KEY(project_id) REFERENCES projects(id)
);

CREATE INDEX timeline_local_day_idx ON timeline_entries(local_day);

-- Link table for N:M relationship
CREATE TABLE timeline_source_events (
    entry_id UUID NOT NULL,
    event_id UUID NOT NULL,
    PRIMARY KEY (entry_id, event_id),
    --#- REMOVED: ON DELETE CASCADE is not supported.
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
  --#- REMOVED: ON DELETE CASCADE is not supported.
  FOREIGN KEY(event_id) REFERENCES events(id)
);


-- OPTIONAL ALIAS TABLE
CREATE TABLE project_aliases (
  alias VARCHAR PRIMARY KEY,
  project_id UUID NOT NULL,
  --#- REMOVED: ON DELETE CASCADE is not supported.
  FOREIGN KEY(project_id) REFERENCES projects(id)
);
-- USER AUTHENTICATION
CREATE TABLE users (
  id UUID PRIMARY KEY,
  username VARCHAR UNIQUE NOT NULL, -- Should be an email or unique identifier
  hashed_password VARCHAR NOT NULL
  -- Add other user-related fields here if needed, e.g., full_name, is_active, is_superuser
);

-- Optional: Index on username for faster lookups
CREATE INDEX users_username_idx ON users(username);