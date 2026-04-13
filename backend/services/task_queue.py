from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from backend.db import get_connection, initialize_database


JobCallable = Callable[[], Awaitable[None]]


@dataclass
class QueuedJob:
    id: int
    name: str
    status: str
    stage: str
    video_id: int = 0
    mode: str = "two_stage"
    progress: float = 0.0
    skipped_frames: int = 0


@dataclass
class JobContext:
    """Context passed to job executor for status updates."""

    job_id: int
    video_id: int
    queue: SQLiteTaskQueue = field(repr=False)

    async def update_progress(self, progress: float, stage: str = "") -> None:
        """Update job progress in database."""
        await self.queue.update_job_status(self.job_id, progress=progress, stage=stage)

    async def mark_running(self, stage: str = "") -> None:
        """Mark job as running."""
        await self.queue.update_job_status(self.job_id, status="running", stage=stage)

    async def mark_completed(self, result: dict[str, Any] | None = None) -> None:
        """Mark job as completed."""
        await self.queue.update_job_status(
            self.job_id, status="completed", progress=1.0, result=result or {}
        )

    async def mark_failed(self, error: str) -> None:
        """Mark job as failed."""
        await self.queue.update_job_status(self.job_id, status="failed", error=error)


class SQLiteTaskQueue:
    """
    Persistent task queue backed by SQLite.

    Features:
    - Task state persisted to SQLite (pending/running/completed/failed)
    - Automatic recovery of pending tasks on startup
    - Progress tracking via JobContext
    - Concurrent worker processing
    """

    def __init__(self, db_path: str, worker_count: int = 1):
        self.db_path = db_path
        self.worker_count = max(1, worker_count)
        self._queue: asyncio.Queue[tuple[int, str, str]] = asyncio.Queue()
        self._worker_tasks: list[asyncio.Task] = []
        self._stop_event = asyncio.Event()
        self._job_registry: dict[str, Callable[[JobContext], Awaitable[None]]] = {}

    def register_job_handler(
        self, name: str, handler: Callable[[JobContext], Awaitable[None]]
    ) -> None:
        """Register a handler for a specific job type."""
        self._job_registry[name] = handler

    async def start(self) -> None:
        """Initialize database and start workers, restoring pending jobs."""
        initialize_database(self.db_path)

        # Clean up zombie running jobs from previous session
        self._reset_stale_jobs()

        # Restore pending jobs from database
        await self._restore_pending_jobs()

        # Start worker tasks
        self._worker_tasks = [task for task in self._worker_tasks if not task.done()]
        if len(self._worker_tasks) >= self.worker_count:
            return

        self._stop_event.clear()
        for _ in range(self.worker_count - len(self._worker_tasks)):
            self._worker_tasks.append(asyncio.create_task(self._worker()))

    async def stop(self) -> None:
        """Gracefully stop all workers."""
        if not self._worker_tasks:
            return

        self._stop_event.set()
        for _ in self._worker_tasks:
            await self._queue.put((-1, "__stop__", ""))
        await asyncio.gather(*self._worker_tasks, return_exceptions=True)
        self._worker_tasks = []

    async def enqueue(
        self,
        name: str,
        video_id: int,
        mode: str = "two_stage",
        stage: str = "coarse",
    ) -> int:
        """
        Add a job to the queue.

        Returns:
            The job ID from the database.
        """
        conn = get_connection(self.db_path)
        try:
            cursor = conn.execute(
                """
                INSERT INTO task_queue (video_id, name, mode, status, stage, progress, result)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (video_id, name, mode, "pending", stage, 0.0, "{}"),
            )
            conn.commit()
            job_id = cursor.lastrowid
        finally:
            conn.close()

        await self._queue.put((job_id, name, stage))
        return job_id

    async def update_job_status(
        self,
        job_id: int,
        status: str | None = None,
        progress: float | None = None,
        stage: str | None = None,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        """Update job status in database."""
        updates: list[str] = []
        params: list[Any] = []

        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if progress is not None:
            updates.append("progress = ?")
            params.append(progress)
        if stage is not None:
            updates.append("stage = ?")
            params.append(stage)
        if result is not None:
            updates.append("result = ?")
            params.append(json.dumps(result, ensure_ascii=False))
        if error is not None:
            updates.append("error = ?")
            params.append(error)

        if not updates:
            return

        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(job_id)

        conn = get_connection(self.db_path)
        try:
            conn.execute(
                f"UPDATE task_queue SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            conn.commit()
        finally:
            conn.close()

    async def get_job(self, job_id: int) -> dict[str, Any] | None:
        """Get job details from database."""
        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT * FROM task_queue WHERE id = ?",
                (job_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    async def list_jobs(
        self,
        status: str | None = None,
        video_id: int | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """List jobs with optional filtering."""
        conn = get_connection(self.db_path)
        try:
            conditions: list[str] = []
            params: list[Any] = []

            if status is not None:
                conditions.append("status = ?")
                params.append(status)
            if video_id is not None:
                conditions.append("video_id = ?")
                params.append(video_id)

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            order_clause = "ORDER BY created_at DESC"
            limit_clause = f" LIMIT {int(limit)}" if limit and limit > 0 else ""

            rows = conn.execute(
                f"SELECT * FROM task_queue {where_clause} {order_clause}{limit_clause}",
                params,
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    async def drain(self) -> None:
        """Wait for all queued jobs to complete."""
        await self._queue.join()

    def _reset_stale_jobs(self) -> None:
        """Reset any 'running' jobs from previous session to 'pending'."""
        conn = get_connection(self.db_path)
        try:
            conn.execute(
                """
                UPDATE task_queue
                SET status = 'pending', progress = 0, updated_at = CURRENT_TIMESTAMP
                WHERE status = 'running'
                """
            )
            conn.commit()
        finally:
            conn.close()

    async def _restore_pending_jobs(self) -> None:
        """Restore pending jobs from database to memory queue."""
        conn = get_connection(self.db_path)
        try:
            rows = conn.execute(
                """
                SELECT id, name, stage FROM task_queue
                WHERE status = 'pending'
                ORDER BY created_at ASC
                """
            ).fetchall()

            for row in rows:
                await self._queue.put((row["id"], row["name"], row["stage"]))
        finally:
            conn.close()

    async def _worker(self) -> None:
        """Worker loop that processes jobs from the queue."""
        while True:
            job_id, name, stage = await self._queue.get()
            try:
                if job_id == -1 and name == "__stop__":
                    return

                # Get job details
                job = await self.get_job(job_id)
                if job is None:
                    continue

                # Skip if job is already completed or failed
                if job.get("status") in ("completed", "failed"):
                    continue

                # Get handler for this job type
                handler = self._job_registry.get(name)
                if handler is None:
                    # Re-queue for later processing when handler is registered
                    # This allows recovery after restart
                    await self._queue.put((job_id, name, stage))
                    # Small delay to prevent busy-loop
                    await asyncio.sleep(0.1)
                    continue

                # Create context and execute job
                ctx = JobContext(
                    job_id=job_id,
                    video_id=job.get("video_id", 0),
                    queue=self,
                )

                await ctx.mark_running(stage=stage)
                await handler(ctx)

            except Exception as exc:
                await self.update_job_status(
                    job_id,
                    status="failed",
                    error=str(exc),
                )
            finally:
                self._queue.task_done()

    @staticmethod
    async def _noop() -> None:
        """No-op handler for stop signals."""
        return None
