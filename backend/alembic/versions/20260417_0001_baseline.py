"""baseline schema

Revision ID: 20260417_0001
Revises:
Create Date: 2026-04-17 19:20:00
"""

from __future__ import annotations

from alembic import op

from backend.db import SCHEMA_SQL


# revision identifiers, used by Alembic.
revision = "20260417_0001"
down_revision = None
branch_labels = None
depends_on = None


DROP_SCHEMA_SQL = """
DROP TABLE IF EXISTS frame_analysis_fts;
DROP TABLE IF EXISTS frame_ocr_cache;
DROP TABLE IF EXISTS task_queue;
DROP TABLE IF EXISTS suspicious_segments;
DROP TABLE IF EXISTS search_query_logs;
DROP TABLE IF EXISTS keyword_sets;
DROP TABLE IF EXISTS frame_analysis;
DROP TABLE IF EXISTS video_frames;
DROP TABLE IF EXISTS processing_tasks;
DROP TABLE IF EXISTS video_assets;
"""


def upgrade() -> None:
    bind = op.get_bind()
    bind.connection.executescript(SCHEMA_SQL)


def downgrade() -> None:
    bind = op.get_bind()
    bind.connection.executescript(DROP_SCHEMA_SQL)
