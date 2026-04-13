from __future__ import annotations

import json
from typing import Any

from backend.repositories import Repository
from backend.services.indexer import tokenize_fts_text


class SearchService:
    def __init__(self, repository: Repository):
        self.repository = repository

    def search(self, query: str, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        filters = filters or {}
        content_results = self._search_by_indexed_content(query, filters)
        metadata_results = self._search_by_video_metadata(query, filters)
        results = self._merge_results(content_results, metadata_results)
        self.repository.log_search(query, filters, len(results))
        return results

    @staticmethod
    def build_segments(results: list[dict[str, Any]], max_gap_seconds: float) -> list[dict[str, Any]]:
        if not results:
            return []

        sorted_results = sorted(
            results,
            key=lambda item: (int(item["video_id"]), float(item["timestamp"]), int(item["frame_id"])),
        )
        segments: list[dict[str, Any]] = []
        current_segment: dict[str, Any] | None = None

        for result in sorted_results:
            if current_segment is None or SearchService._should_start_new_segment(
                current_segment, result, max_gap_seconds
            ):
                if current_segment is not None:
                    SearchService._finalize_segment(current_segment)
                    segments.append(current_segment)
                current_segment = SearchService._create_segment(result)
                continue

            current_segment["end_timestamp"] = float(result["timestamp"])
            current_segment["frame_ids"].append(int(result["frame_id"]))
            current_segment["hit_count"] += 1
            current_segment["ai_tool_detected"] = current_segment["ai_tool_detected"] or bool(
                result["ai_tool_detected"]
            )
            SearchService._append_unique(current_segment["ai_tool_names"], result["ai_tool_name"])
            SearchService._append_unique(
                current_segment["matched_sources"],
                str(result.get("matched_source", "")),
            )
            for indicator in result["risk_indicators"]:
                SearchService._append_unique(current_segment["risk_indicators"], indicator)

        if current_segment is not None:
            SearchService._finalize_segment(current_segment)
            segments.append(current_segment)

        return segments

    def _search_by_indexed_content(self, query: str, filters: dict[str, Any]) -> list[dict[str, Any]]:
        query_tokens = tokenize_fts_text(query)
        params: list[Any] = [self._build_match_query(query)]
        clauses = ["frame_analysis_fts MATCH ?"]
        filter_clauses, filter_params = self._build_filter_clauses(filters)
        params.extend(filter_params)
        sql = f"""
            SELECT
                vf.id AS frame_id,
                v.id AS video_id,
                v.filename AS video_name,
                v.filepath AS video_path,
                vf.timestamp AS timestamp,
                vf.image_path AS frame_image_path,
                fa.screen_text AS screen_text,
                fa.application AS application,
                fa.url AS url,
                fa.operation AS operation,
                fa.ai_tool_detected AS ai_tool_detected,
                fa.ai_tool_name AS ai_tool_name,
                fa.code_content_summary AS code_content_summary,
                fa.summary AS summary,
                fa.risk_indicators AS risk_indicators
            FROM frame_analysis_fts
            JOIN video_frames vf ON vf.id = frame_analysis_fts.frame_id
            JOIN video_assets v ON v.id = vf.video_id
            JOIN frame_analysis fa ON fa.frame_id = vf.id
            WHERE {' AND '.join(clauses + filter_clauses)}
            ORDER BY bm25(frame_analysis_fts), vf.timestamp ASC
        """
        with self.repository.connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_payload(row, query_tokens=query_tokens) for row in rows]

    def _search_by_video_metadata(self, query: str, filters: dict[str, Any]) -> list[dict[str, Any]]:
        normalized_query = query.strip()
        if not normalized_query:
            return []
        params: list[Any] = [f"%{normalized_query}%", f"%{normalized_query}%"]
        filter_clauses, filter_params = self._build_filter_clauses(filters)
        params.extend(filter_params)
        sql = f"""
            SELECT
                vf.id AS frame_id,
                v.id AS video_id,
                v.filename AS video_name,
                v.filepath AS video_path,
                vf.timestamp AS timestamp,
                vf.image_path AS frame_image_path,
                fa.screen_text AS screen_text,
                fa.application AS application,
                fa.url AS url,
                fa.operation AS operation,
                fa.ai_tool_detected AS ai_tool_detected,
                fa.ai_tool_name AS ai_tool_name,
                fa.code_content_summary AS code_content_summary,
                fa.summary AS summary,
                fa.risk_indicators AS risk_indicators
            FROM video_frames vf
            JOIN video_assets v ON v.id = vf.video_id
            JOIN frame_analysis fa ON fa.frame_id = vf.id
            WHERE (v.filename LIKE ? OR v.filepath LIKE ?)
              AND {' AND '.join(filter_clauses) if filter_clauses else '1 = 1'}
            ORDER BY v.filename ASC, vf.timestamp ASC
        """
        with self.repository.connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            self._row_to_payload(row, query_tokens=tokenize_fts_text(normalized_query), metadata_query=normalized_query)
            for row in rows
        ]

    @staticmethod
    def _merge_results(*result_sets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen_frame_ids: set[int] = set()
        for result_set in result_sets:
            for item in result_set:
                frame_id = int(item["frame_id"])
                if frame_id in seen_frame_ids:
                    continue
                seen_frame_ids.add(frame_id)
                merged.append(item)
        return merged

    @staticmethod
    def _build_filter_clauses(filters: dict[str, Any]) -> tuple[list[str], list[Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if filters.get("video_id") is not None:
            clauses.append("vf.video_id = ?")
            params.append(filters["video_id"])
        if filters.get("time_start") is not None:
            clauses.append("vf.timestamp >= ?")
            params.append(filters["time_start"])
        if filters.get("time_end") is not None:
            clauses.append("vf.timestamp <= ?")
            params.append(filters["time_end"])
        if filters.get("ai_tool_detected") is not None:
            clauses.append("fa.ai_tool_detected = ?")
            params.append(int(bool(filters["ai_tool_detected"])))
        return clauses, params

    @staticmethod
    def _row_to_payload(
        row: Any,
        *,
        query_tokens: list[str],
        metadata_query: str | None = None,
    ) -> dict[str, Any]:
        payload = dict(row)
        payload["ai_tool_detected"] = bool(payload["ai_tool_detected"])
        payload["risk_indicators"] = json.loads(payload.get("risk_indicators") or "[]")
        if metadata_query:
            matched_source = "metadata"
            matched_text = SearchService._pick_metadata_match(
                metadata_query,
                str(payload.get("video_name", "")),
                str(payload.get("video_path", "")),
            )
        else:
            matched_source, matched_text = SearchService._resolve_content_match(
                payload,
                query_tokens=query_tokens,
            )

        return {
            "frame_id": payload["frame_id"],
            "video_id": payload["video_id"],
            "video_name": payload["video_name"],
            "video_path": payload["video_path"],
            "timestamp": payload["timestamp"],
            "matched_text": matched_text,
            "matched_source": matched_source,
            "analysis_summary": payload.get("summary", ""),
            "frame_image_path": payload["frame_image_path"],
            "application": payload.get("application", ""),
            "ai_tool_detected": payload["ai_tool_detected"],
            "ai_tool_name": payload.get("ai_tool_name", ""),
            "risk_indicators": payload["risk_indicators"],
        }

    @staticmethod
    def _create_segment(result: dict[str, Any]) -> dict[str, Any]:
        return {
            "video_id": int(result["video_id"]),
            "video_name": result["video_name"],
            "video_path": result["video_path"],
            "start_timestamp": float(result["timestamp"]),
            "end_timestamp": float(result["timestamp"]),
            "first_frame_id": int(result["frame_id"]),
            "last_frame_id": int(result["frame_id"]),
            "frame_ids": [int(result["frame_id"])],
            "hit_count": 1,
            "ai_tool_detected": bool(result["ai_tool_detected"]),
            "ai_tool_names": [result["ai_tool_name"]] if result["ai_tool_name"] else [],
            "matched_sources": [result["matched_source"]] if result.get("matched_source") else [],
            "risk_indicators": list(result["risk_indicators"]),
            "summary": result["analysis_summary"] or result["matched_text"],
        }

    @staticmethod
    def _finalize_segment(segment: dict[str, Any]) -> None:
        segment["last_frame_id"] = segment["frame_ids"][-1]
        segment["duration_seconds"] = round(
            float(segment["end_timestamp"]) - float(segment["start_timestamp"]),
            1,
        )

    @staticmethod
    def _should_start_new_segment(
        segment: dict[str, Any], result: dict[str, Any], max_gap_seconds: float
    ) -> bool:
        if int(segment["video_id"]) != int(result["video_id"]):
            return True
        return float(result["timestamp"]) - float(segment["end_timestamp"]) > max_gap_seconds

    @staticmethod
    def _append_unique(items: list[str], value: str) -> None:
        normalized = value.strip()
        if normalized and normalized not in items:
            items.append(normalized)

    @staticmethod
    def _resolve_content_match(payload: dict[str, Any], *, query_tokens: list[str]) -> tuple[str, str]:
        fields_to_check = [
            ("ocr", str(payload.get("screen_text", ""))),
            ("ai_tool_name", str(payload.get("ai_tool_name", ""))),
            (
                "summary",
                " ".join(
                    [
                        str(payload.get("summary", "")),
                        str(payload.get("operation", "")),
                        str(payload.get("code_content_summary", "")),
                    ]
                ).strip(),
            ),
            (
                "metadata",
                " ".join(
                    [
                        str(payload.get("application", "")),
                        str(payload.get("url", "")),
                        str(payload.get("video_name", "")),
                        str(payload.get("video_path", "")),
                    ]
                ).strip(),
            ),
        ]

        for source, text in fields_to_check:
            if SearchService._field_matches_tokens(text, query_tokens):
                return source, text

        fallback_text = (
            str(payload.get("summary", "")).strip()
            or str(payload.get("screen_text", "")).strip()
            or str(payload.get("ai_tool_name", "")).strip()
            or str(payload.get("application", "")).strip()
            or str(payload.get("video_name", "")).strip()
        )
        return "summary", fallback_text

    @staticmethod
    def _field_matches_tokens(text: str, query_tokens: list[str]) -> bool:
        if not query_tokens:
            return bool(text.strip())
        field_tokens = set(tokenize_fts_text(text))
        return all(token in field_tokens for token in query_tokens)

    @staticmethod
    def _pick_metadata_match(query: str, video_name: str, video_path: str) -> str:
        normalized_query = query.strip().lower()
        if normalized_query and normalized_query in video_name.lower():
            return video_name
        if normalized_query and normalized_query in video_path.lower():
            return video_path
        return video_name or video_path

    @staticmethod
    def _build_match_query(query: str) -> str:
        tokens = tokenize_fts_text(query)
        if not tokens:
            return '""'
        escaped_tokens = [token.replace('"', '""') for token in tokens]
        return " AND ".join(f'"{token}"' for token in escaped_tokens)
