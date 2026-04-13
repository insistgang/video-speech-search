from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from backend.db import get_connection
from backend.models import FrameAnalysisRecord


class Repository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    @contextmanager
    def connection(self) -> Iterator[Any]:
        with get_connection(self.db_path) as conn:
            yield conn

    def create_video_asset(self, record: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "filename": record["filename"],
            "filepath": record["filepath"],
            "duration": record["duration"],
            "format": record["format"],
            "resolution": record["resolution"],
            "status": record.get("status", "pending"),
        }
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO video_assets (filename, filepath, duration, format, resolution, status)
                VALUES (:filename, :filepath, :duration, :format, :resolution, :status)
                ON CONFLICT(filepath) DO UPDATE SET
                    filename=excluded.filename,
                    duration=excluded.duration,
                    format=excluded.format,
                    resolution=excluded.resolution,
                    updated_at=CURRENT_TIMESTAMP
                """,
                payload,
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM video_assets WHERE filepath = ?",
                (record["filepath"],),
            ).fetchone()
        return dict(row)

    def list_videos(self) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM video_assets ORDER BY created_at DESC, id DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_video(self, video_id: int) -> dict[str, Any] | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM video_assets WHERE id = ?", (video_id,)).fetchone()
        return dict(row) if row else None

    def update_video_status(self, video_id: int, status: str) -> None:
        with self.connection() as conn:
            conn.execute(
                "UPDATE video_assets SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (status, video_id),
            )
            conn.commit()

    def create_task(
        self,
        video_id: int,
        task_type: str,
        status: str = "pending",
        progress: float = 0.0,
        error_message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO processing_tasks (video_id, task_type, status, progress, error_message, details)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    video_id,
                    task_type,
                    status,
                    progress,
                    error_message,
                    json.dumps(details or {}, ensure_ascii=False),
                ),
            )
            conn.commit()
            row = conn.execute(self._task_select_sql(where_clause="pt.id = ?"), (cursor.lastrowid,)).fetchone()
        return self._task_row_to_dict(row)

    def list_tasks(self, *, active_only: bool = False, limit: int | None = None) -> list[dict[str, Any]]:
        where_clause = "WHERE pt.status IN ('pending', 'running')" if active_only else ""
        limit_clause = f" LIMIT {int(limit)}" if limit and limit > 0 else ""
        with self.connection() as conn:
            rows = conn.execute(
                f"{self._task_select_sql()} {where_clause} ORDER BY pt.created_at DESC, pt.id DESC{limit_clause}"
            ).fetchall()
        return [self._task_row_to_dict(row) for row in rows]

    def get_task(self, task_id: int) -> dict[str, Any] | None:
        with self.connection() as conn:
            row = conn.execute(self._task_select_sql(where_clause="pt.id = ?"), (task_id,)).fetchone()
        return self._task_row_to_dict(row) if row else None

    def update_task(
        self,
        task_id: int,
        *,
        status: str | None = None,
        progress: float | None = None,
        error_message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        updates: list[str] = []
        params: list[Any] = []
        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if progress is not None:
            updates.append("progress = ?")
            params.append(progress)
        if error_message is not None:
            updates.append("error_message = ?")
            params.append(error_message)
        if details is not None:
            updates.append("details = ?")
            params.append(json.dumps(details, ensure_ascii=False))
        if not updates:
            return self.get_task(task_id)
        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(task_id)
        with self.connection() as conn:
            conn.execute(
                f"UPDATE processing_tasks SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            conn.commit()
            row = conn.execute(self._task_select_sql(where_clause="pt.id = ?"), (task_id,)).fetchone()
        return self._task_row_to_dict(row) if row else None

    def delete_frames_for_video(self, video_id: int) -> None:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT image_path FROM video_frames WHERE video_id = ?",
                (video_id,),
            ).fetchall()
            for row in rows:
                image_path = Path(row["image_path"])
                if image_path.exists():
                    image_path.unlink()
            conn.execute("DELETE FROM video_frames WHERE video_id = ?", (video_id,))
            conn.execute("DELETE FROM frame_analysis WHERE video_id = ?", (video_id,))
            conn.execute("DELETE FROM frame_analysis_fts WHERE video_id = ?", (video_id,))
            conn.commit()

    def create_frames(self, video_id: int, frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
        with self.connection() as conn:
            for frame in frames:
                conn.execute(
                    """
                    INSERT INTO video_frames (video_id, frame_index, timestamp, image_path)
                    VALUES (?, ?, ?, ?)
                    """,
                    (video_id, frame["frame_index"], frame["timestamp"], frame["image_path"]),
                )
            conn.commit()
            rows = conn.execute(
                "SELECT * FROM video_frames WHERE video_id = ? ORDER BY frame_index ASC",
                (video_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_frames_for_video(self, video_id: int) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM video_frames WHERE video_id = ? ORDER BY timestamp ASC, id ASC",
                (video_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_frame(self, frame_id: int) -> dict[str, Any] | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM video_frames WHERE id = ?", (frame_id,)).fetchone()
        return dict(row) if row else None

    def save_frame_analysis(self, record: FrameAnalysisRecord) -> dict[str, Any]:
        payload = record.model_dump()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO frame_analysis (
                    frame_id, video_id, raw_json, screen_text, application, url,
                    operation, ai_tool_detected, ai_tool_name, code_visible,
                    code_content_summary, risk_indicators, summary, timestamp
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(frame_id) DO UPDATE SET
                    raw_json=excluded.raw_json,
                    screen_text=excluded.screen_text,
                    application=excluded.application,
                    url=excluded.url,
                    operation=excluded.operation,
                    ai_tool_detected=excluded.ai_tool_detected,
                    ai_tool_name=excluded.ai_tool_name,
                    code_visible=excluded.code_visible,
                    code_content_summary=excluded.code_content_summary,
                    risk_indicators=excluded.risk_indicators,
                    summary=excluded.summary,
                    timestamp=excluded.timestamp
                """,
                (
                    payload["frame_id"],
                    payload["video_id"],
                    json.dumps(payload["raw_json"], ensure_ascii=False),
                    payload["screen_text"],
                    payload["application"],
                    payload["url"],
                    payload["operation"],
                    int(payload["ai_tool_detected"]),
                    payload["ai_tool_name"],
                    int(payload["code_visible"]),
                    payload["code_content_summary"],
                    json.dumps(payload["risk_indicators"], ensure_ascii=False),
                    payload["summary"],
                    payload["timestamp"],
                ),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM frame_analysis WHERE frame_id = ?",
                (payload["frame_id"],),
            ).fetchone()
        return self._analysis_row_to_dict(row)

    def get_frame_analysis(self, frame_id: int) -> dict[str, Any] | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM frame_analysis WHERE frame_id = ?",
                (frame_id,),
            ).fetchone()
        return self._analysis_row_to_dict(row) if row else None

    def upsert_keyword_set(
        self,
        *,
        name: str,
        category: str,
        terms: list[str],
        keyword_set_id: int | None = None,
    ) -> dict[str, Any]:
        with self.connection() as conn:
            if keyword_set_id is None:
                cursor = conn.execute(
                    "INSERT INTO keyword_sets (name, category, terms) VALUES (?, ?, ?)",
                    (name, category, json.dumps(terms, ensure_ascii=False)),
                )
                keyword_set_id = cursor.lastrowid
            else:
                conn.execute(
                    """
                    UPDATE keyword_sets
                    SET name = ?, category = ?, terms = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (name, category, json.dumps(terms, ensure_ascii=False), keyword_set_id),
                )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM keyword_sets WHERE id = ?",
                (keyword_set_id,),
            ).fetchone()
        return self._keyword_row_to_dict(row)

    def list_keyword_sets(self) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM keyword_sets ORDER BY id DESC").fetchall()
        return [self._keyword_row_to_dict(row) for row in rows]

    def get_keyword_set(self, keyword_set_id: int) -> dict[str, Any] | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM keyword_sets WHERE id = ?",
                (keyword_set_id,),
            ).fetchone()
        return self._keyword_row_to_dict(row) if row else None

    def delete_keyword_set(self, keyword_set_id: int) -> None:
        with self.connection() as conn:
            conn.execute("DELETE FROM keyword_sets WHERE id = ?", (keyword_set_id,))
            conn.commit()

    def upsert_fts(self, *, frame_id: int, video_id: int, timestamp: float, content: str) -> None:
        """
        Upsert FTS record. Note: FTS triggers auto-sync on frame_analysis changes,
        but this method provides a manual fallback for bulk operations.
        """
        with self.connection() as conn:
            # Use REPLACE INTO to handle both insert and update
            conn.execute(
                """
                INSERT OR REPLACE INTO frame_analysis_fts (content, video_id, frame_id, timestamp)
                VALUES (?, ?, ?, ?)
                """,
                (content, video_id, frame_id, timestamp),
            )
            conn.commit()

    def log_search(self, query: str, filters: dict[str, Any], result_count: int) -> None:
        with self.connection() as conn:
            conn.execute(
                "INSERT INTO search_query_logs (query, filters, result_count) VALUES (?, ?, ?)",
                (query, json.dumps(filters, ensure_ascii=False), result_count),
            )
            conn.commit()

    @staticmethod
    def _task_row_to_dict(row: Any) -> dict[str, Any]:
        payload = dict(row)
        payload["details"] = json.loads(payload.get("details") or "{}")
        return payload

    @staticmethod
    def _task_select_sql(where_clause: str | None = None) -> str:
        sql = """
            SELECT
                pt.*,
                v.filename AS video_filename,
                v.filepath AS video_filepath,
                v.status AS video_status
            FROM processing_tasks pt
            LEFT JOIN video_assets v ON v.id = pt.video_id
        """
        if where_clause:
            sql += f" WHERE {where_clause}"
        return sql

    @staticmethod
    def _analysis_row_to_dict(row: Any) -> dict[str, Any]:
        payload = dict(row)
        payload["raw_json"] = json.loads(payload.get("raw_json") or "{}")
        payload["risk_indicators"] = json.loads(payload.get("risk_indicators") or "[]")
        payload["ai_tool_detected"] = bool(payload.get("ai_tool_detected"))
        payload["code_visible"] = bool(payload.get("code_visible"))
        return payload

    @staticmethod
    def _keyword_row_to_dict(row: Any) -> dict[str, Any]:
        payload = dict(row)
        payload["terms"] = json.loads(payload.get("terms") or "[]")
        return payload
