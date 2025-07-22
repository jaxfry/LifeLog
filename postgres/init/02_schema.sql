/* =========================================================
   LifeLog Database Schema for PostgreSQL
   ========================================================= */

/* Create enum type for event kinds */
CREATE TYPE eventkind AS ENUM (
  'digital_activity',
  'health_metric', 
  'location_visit',
  'media_note',
  'photo'
);

/* =========================================================
   Core "spine" table: events
   ========================================================= */
CREATE TABLE events (
  id           UUID PRIMARY KEY,
  user_id      UUID NULL,                -- omit if single-user
  event_type   eventkind NOT NULL,       -- typed enum for event kinds
  source       TEXT      NOT NULL,       -- e.g. activitywatch, iphone
  start_time   TIMESTAMPTZ NOT NULL,
  end_time     TIMESTAMPTZ,
  payload_hash TEXT UNIQUE NOT NULL,
  details      JSONB,                    -- flexible payload
  local_day    DATE GENERATED ALWAYS AS
               ((start_time AT TIME ZONE 'America/Vancouver')::date) STORED
);

CREATE INDEX events_start_time_idx ON events(start_time);
CREATE INDEX events_local_day_idx  ON events(local_day);

/* =========================================================
   Projects & embeddings
   ========================================================= */
CREATE TABLE projects (
  id        UUID PRIMARY KEY,
  name      CITEXT UNIQUE NOT NULL,      -- case-insensitive
  embedding VECTOR(128)
);

CREATE INDEX project_embedding_idx
  ON projects USING hnsw (embedding vector_cosine_ops);

/* Optional aliases (alternate names) */
CREATE TABLE project_aliases (
  alias      CITEXT PRIMARY KEY,
  project_id UUID REFERENCES projects(id) ON DELETE CASCADE
);

/* =========================================================
   Timeline & linking
   ========================================================= */
CREATE TABLE timeline_entries (
  id          UUID PRIMARY KEY,
  start_time  TIMESTAMPTZ NOT NULL,
  end_time    TIMESTAMPTZ NOT NULL,
  title       TEXT NOT NULL,
  summary     TEXT,
  project_id  UUID REFERENCES projects(id) ON DELETE SET NULL,
  local_day   DATE GENERATED ALWAYS AS
              ((start_time AT TIME ZONE 'America/Vancouver')::date) STORED
);

CREATE INDEX timeline_time_idx ON timeline_entries(start_time, end_time);
CREATE INDEX timeline_day_idx  ON timeline_entries(local_day);

CREATE TABLE timeline_source_events (
  entry_id UUID REFERENCES timeline_entries(id) ON DELETE CASCADE,
  event_id UUID REFERENCES events(id)          ON DELETE CASCADE,
  PRIMARY KEY (entry_id, event_id)
);

/* =========================================================
   Typed payload tables ("organs")
   ========================================================= */

/* Digital Activity Data from ActivityWatch */
CREATE TABLE digital_activity_data (
  event_id  UUID PRIMARY KEY REFERENCES events(id) ON DELETE CASCADE,
  hostname  TEXT NOT NULL,
  app       TEXT,                       -- nullable: can be null for web-only events
  title     TEXT,                       -- nullable: can be null for some events
  url       TEXT                        -- nullable: can be null for non-web events
);

/* Event State Tracking - FIXED: UUID type with FK */
CREATE TABLE event_state (
  event_id UUID PRIMARY KEY REFERENCES events(id) ON DELETE CASCADE
);

/* Photos */
CREATE TABLE photo_data (
  event_id  UUID PRIMARY KEY REFERENCES events(id) ON DELETE CASCADE,
  file_path TEXT  NOT NULL,          -- filesystem or S3/GS URI
  embedding VECTOR(512),
  caption   TEXT,
  metadata  JSONB
  -- location  GEOGRAPHY(Point,4326) NULL   -- enable later when PostGIS is installed
);

CREATE INDEX photo_embedding_idx
  ON photo_data USING hnsw (embedding vector_cosine_ops);

/* GPS / Location visits */
CREATE TABLE location_data (
  event_id    UUID PRIMARY KEY REFERENCES events(id) ON DELETE CASCADE,
  latitude    DOUBLE PRECISION NOT NULL,
  longitude   DOUBLE PRECISION NOT NULL,
  accuracy_m  DOUBLE PRECISION,
  place_name  TEXT,
  source      TEXT
);

/* =========================================================
   Users (optional multi-tenant)
   ========================================================= */
CREATE TABLE users (
  id              UUID PRIMARY KEY,
  username        CITEXT UNIQUE NOT NULL,
  hashed_password TEXT  NOT NULL
);

/* =========================================================
   Meta key-value store
   ========================================================= */
CREATE TABLE meta (
  key   TEXT PRIMARY KEY,
  value TEXT
);

/* =========================================================
   Daily Reflections (LLM Summaries)
   ========================================================= */
CREATE TABLE daily_reflections (
  id         UUID PRIMARY KEY,
  local_day  DATE NOT NULL UNIQUE,
  summary    TEXT NOT NULL, -- The <summary>...</summary> extracted from the LLM
  reflection TEXT NOT NULL, -- The full LLM tag-formatted reflection
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX daily_reflections_day_idx ON daily_reflections(local_day);
