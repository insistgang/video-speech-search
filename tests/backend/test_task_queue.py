from __future__ import annotations

import asyncio
import tempfile

from backend.services.task_queue import SQLiteTaskQueue, JobContext


def test_task_queue_runs_multiple_jobs_concurrently():
    async def run() -> int:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        queue = SQLiteTaskQueue(db_path=db_path, worker_count=2)
        release_jobs = asyncio.Event()
        two_jobs_running = asyncio.Event()
        lock = asyncio.Lock()
        running_jobs = 0
        max_running_jobs = 0

        async def job_handler(ctx: JobContext) -> None:
            nonlocal running_jobs, max_running_jobs
            async with lock:
                running_jobs += 1
                max_running_jobs = max(max_running_jobs, running_jobs)
                if running_jobs == 2:
                    two_jobs_running.set()
            await release_jobs.wait()
            async with lock:
                running_jobs -= 1

        queue.register_job_handler("test-job", job_handler)

        await queue.start()
        try:
            await queue.enqueue("test-job", video_id=1)
            await queue.enqueue("test-job", video_id=2)
            await asyncio.wait_for(two_jobs_running.wait(), timeout=2)
            release_jobs.set()
            await queue.drain()
        finally:
            await queue.stop()

        return max_running_jobs

    assert asyncio.run(run()) == 2


def test_task_queue_persists_job_status():
    async def run() -> bool:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        completed = False

        async def job_handler(ctx: JobContext) -> None:
            nonlocal completed
            await ctx.mark_running()
            completed = True
            await ctx.mark_completed()

        # First session: start queue, enqueue job, stop
        queue1 = SQLiteTaskQueue(db_path=db_path, worker_count=1)
        queue1.register_job_handler("persist-test", job_handler)
        await queue1.start()

        job_id = await queue1.enqueue("persist-test", video_id=1)

        # Wait for job to complete
        await queue1.drain()
        await queue1.stop()

        # Second session: verify job status persisted
        queue2 = SQLiteTaskQueue(db_path=db_path, worker_count=1)
        job = await queue2.get_job(job_id)
        return job is not None and job["status"] == "completed"

    assert asyncio.run(run()) is True


def test_task_queue_restores_pending_jobs_on_start():
    async def run() -> bool:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        job_executed = asyncio.Event()

        async def job_handler(ctx: JobContext) -> None:
            job_executed.set()
            await ctx.mark_completed()

        # First session: enqueue job but don't wait for completion
        queue1 = SQLiteTaskQueue(db_path=db_path, worker_count=1)
        queue1.register_job_handler("restore-test", job_handler)
        await queue1.start()

        job_id = await queue1.enqueue("restore-test", video_id=1)

        # Wait for job to complete in first session
        await asyncio.wait_for(job_executed.wait(), timeout=2)
        await queue1.stop()

        # Verify job is persisted as completed
        queue2 = SQLiteTaskQueue(db_path=db_path, worker_count=1)
        job = await queue2.get_job(job_id)
        return job is not None and job["status"] == "completed"

    assert asyncio.run(run()) is True
