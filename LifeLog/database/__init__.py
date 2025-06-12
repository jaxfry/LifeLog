# Database schema and utilities for LifeLog v3

import os
import duckdb
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / 'storage' / 'lifelog.db'

SCHEMA_QUERIES = [
    '''
    CREATE TABLE IF NOT EXISTS timeline_events (
        event_id UUID PRIMARY KEY,
        start_time TIMESTAMP,
        end_time TIMESTAMP,
        date DATE GENERATED ALWAYS AS (DATE(start_time)) VIRTUAL,
        duration_s INTEGER,
        source VARCHAR,
        app_name VARCHAR,
        window_title VARCHAR,
        category VARCHAR,
        project VARCHAR,
        notes TEXT,
        last_modified TIMESTAMP
    );
    ''',
    'CREATE INDEX IF NOT EXISTS idx_timeline_events_start_time ON timeline_events(start_time);',
    'CREATE INDEX IF NOT EXISTS idx_timeline_events_date ON timeline_events(date);',
    '''
    CREATE TABLE IF NOT EXISTS daily_summaries (
        date DATE PRIMARY KEY,
        summary_text TEXT,
        key_events JSON,
        version VARCHAR,
        generated_at TIMESTAMP
    );
    ''',
    '''
    CREATE TABLE IF NOT EXISTS metadata (
        key VARCHAR PRIMARY KEY,
        value VARCHAR
    );
    ''',
    '''
    CREATE TABLE IF NOT EXISTS project_memory (
        project_name VARCHAR PRIMARY KEY,
        embedding JSON,
        count INTEGER,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    '''
]

def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(DB_PATH))

def migrate_database():
    """Apply any necessary database migrations."""
    with get_connection() as conn:
        # Check if project column exists, if not add it
        try:
            conn.execute("SELECT project FROM timeline_events LIMIT 1")
        except:
            # Column doesn't exist, add it
            conn.execute("ALTER TABLE timeline_events ADD COLUMN project VARCHAR")
            print("Added project column to timeline_events table")

def init_database():
    with get_connection() as conn:
        for query in SCHEMA_QUERIES:
            conn.execute(query)
    migrate_database()
