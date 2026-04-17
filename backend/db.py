from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS video_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    filepath TEXT NOT NULL UNIQUE,
    duration REAL NOT NULL DEFAULT 0,
    format TEXT NOT NULL DEFAULT '',
    resolution TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS processing_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL,
    task_type TEXT NOT NULL,
    status TEXT NOT NULL,
    progress REAL NOT NULL DEFAULT 0,
    error_message TEXT,
    details TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(video_id) REFERENCES video_assets(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS video_frames (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL,
    frame_index INTEGER NOT NULL,
    timestamp REAL NOT NULL,
    image_path TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(video_id) REFERENCES video_assets(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS frame_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    frame_id INTEGER NOT NULL UNIQUE,
    video_id INTEGER NOT NULL,
    raw_json TEXT NOT NULL,
    screen_text TEXT NOT NULL DEFAULT '',
    application TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    operation TEXT NOT NULL DEFAULT '',
    ai_tool_detected INTEGER NOT NULL DEFAULT 0,
    ai_tool_name TEXT NOT NULL DEFAULT '',
    code_visible INTEGER NOT NULL DEFAULT 0,
    code_content_summary TEXT NOT NULL DEFAULT '',
    risk_indicators TEXT NOT NULL DEFAULT '[]',
    summary TEXT NOT NULL DEFAULT '',
    timestamp REAL NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(frame_id) REFERENCES video_frames(id) ON DELETE CASCADE,
    FOREIGN KEY(video_id) REFERENCES video_assets(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS keyword_sets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    terms TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS search_query_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query TEXT NOT NULL,
    filters TEXT NOT NULL DEFAULT '{}',
    result_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE VIRTUAL TABLE IF NOT EXISTS frame_analysis_fts USING fts5(
    content,
    video_id UNINDEXED,
    frame_id UNINDEXED,
    timestamp UNINDEXED
);

CREATE TABLE IF NOT EXISTS suspicious_segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL,
    start_timestamp REAL NOT NULL,
    end_timestamp REAL NOT NULL,
    severity TEXT NOT NULL DEFAULT 'low',
    reason TEXT NOT NULL DEFAULT '',
    frame_ids TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(video_id) REFERENCES video_assets(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS task_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'two_stage',
    status TEXT NOT NULL DEFAULT 'pending',
    stage TEXT NOT NULL DEFAULT 'coarse',
    progress REAL NOT NULL DEFAULT 0,
    result TEXT NOT NULL DEFAULT '{}',
    error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(video_id) REFERENCES video_assets(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS frame_ocr_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    frame_id INTEGER NOT NULL UNIQUE,
    video_id INTEGER NOT NULL,
    ocr_text TEXT NOT NULL DEFAULT '',
    hash TEXT NOT NULL DEFAULT '',
    language TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(frame_id) REFERENCES video_frames(id) ON DELETE CASCADE,
    FOREIGN KEY(video_id) REFERENCES video_assets(id) ON DELETE CASCADE
);

-- Performance indexes for frequently queried columns
CREATE INDEX IF NOT EXISTS idx_video_assets_status ON video_assets(status);
CREATE INDEX IF NOT EXISTS idx_video_assets_created ON video_assets(created_at);
CREATE INDEX IF NOT EXISTS idx_processing_tasks_status ON processing_tasks(status);
CREATE INDEX IF NOT EXISTS idx_processing_tasks_video_id ON processing_tasks(video_id);
CREATE INDEX IF NOT EXISTS idx_video_frames_video_id ON video_frames(video_id);
CREATE INDEX IF NOT EXISTS idx_video_frames_timestamp ON video_frames(timestamp);
CREATE INDEX IF NOT EXISTS idx_frame_analysis_video_id ON frame_analysis(video_id);
CREATE INDEX IF NOT EXISTS idx_frame_analysis_ai_tool ON frame_analysis(ai_tool_detected);
CREATE INDEX IF NOT EXISTS idx_suspicious_segments_video_id ON suspicious_segments(video_id);
CREATE INDEX IF NOT EXISTS idx_task_queue_status ON task_queue(status);
CREATE INDEX IF NOT EXISTS idx_task_queue_video_id ON task_queue(video_id);

-- Note: FTS sync is managed by application layer (Repository.upsert_fts)
-- rather than triggers, because the search content must be built by
-- build_search_content() which uses jieba tokenization. SQLite triggers
-- cannot replicate this tokenization, leading to mismatched FTS content.
"""


def get_connection(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database(db_path: str) -> None:
    with get_connection(db_path) as connection:
        connection.executescript(SCHEMA_SQL)
        connection.commit()
