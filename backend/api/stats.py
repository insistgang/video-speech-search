from fastapi import APIRouter, Depends, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.api.deps import get_context


router = APIRouter(prefix="/stats", tags=["stats"])
limiter = Limiter(key_func=get_remote_address)


@router.get("")
@limiter.limit("60/minute")
def get_stats(request: Request, context=Depends(get_context)) -> dict:
    """Get platform statistics."""
    with context.repository.connection() as conn:
        # Total videos
        video_row = conn.execute("SELECT COUNT(*) as count FROM video_assets").fetchone()
        total_videos = video_row["count"] if video_row else 0

        # Total frames
        frame_row = conn.execute("SELECT COUNT(*) as count FROM video_frames").fetchone()
        total_frames = frame_row["count"] if frame_row else 0

        # Total tasks
        task_row = conn.execute("SELECT COUNT(*) as count FROM processing_tasks").fetchone()
        total_tasks = task_row["count"] if task_row else 0

        # Completed tasks
        completed_row = conn.execute(
            "SELECT COUNT(*) as count FROM processing_tasks WHERE status = 'completed'"
        ).fetchone()
        completed_tasks = completed_row["count"] if completed_row else 0

        # Failed tasks
        failed_row = conn.execute(
            "SELECT COUNT(*) as count FROM processing_tasks WHERE status = 'failed'"
        ).fetchone()
        failed_tasks = failed_row["count"] if failed_row else 0

        return {
            "total_videos": total_videos,
            "total_frames": total_frames,
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "failed_tasks": failed_tasks,
        }
