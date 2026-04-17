from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.api.deps import get_context
from backend.auth import verify_api_key, verify_media_api_key
from backend.models import ImportFolderRequest, ImportVideoRequest, resolve_path_input


router = APIRouter(prefix="/videos", tags=["videos"])
limiter = Limiter(key_func=get_remote_address)


class ProcessVideoRequest(BaseModel):
    mode: str = "two_stage"


class RescanRequest(BaseModel):
    stage: str = "coarse"


@router.post("/import")
@limiter.limit("60/minute")
async def import_video(
    request: Request,
    payload: ImportVideoRequest,
    context=Depends(get_context),
    _: str = Depends(verify_api_key),
) -> dict:
    try:
        video_path = resolve_path_input(payload.path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not video_path.exists():
        raise HTTPException(status_code=400, detail=f"Video file does not exist: {video_path}")
    if not video_path.is_file():
        raise HTTPException(status_code=400, detail=f"Video path is not a file: {video_path}")

    try:
        video = context.video_import_service.import_one(str(video_path))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    task = await context.processing_service.schedule_video_processing(video["id"], mode=payload.mode)
    return {
        "video": video,
        "task": task,
        "estimate": context.video_import_service.estimate_cost(
            video["duration"], context.settings.frame_interval
        ),
    }


@router.post("/import-folder")
@limiter.limit("60/minute")
async def import_folder(
    request: Request,
    payload: ImportFolderRequest,
    context=Depends(get_context),
    _: str = Depends(verify_api_key),
) -> dict:
    try:
        videos = context.video_import_service.import_folder(payload.folder_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    tasks = []
    for video in videos:
        tasks.append(await context.processing_service.schedule_video_processing(video["id"]))
    return {"videos": videos, "tasks": tasks, "count": len(videos)}


@router.get("")
@limiter.limit("60/minute")
def list_videos(
    request: Request,
    context=Depends(get_context),
    _: str = Depends(verify_api_key),
) -> list[dict]:
    return context.repository.list_videos()


@router.get("/{video_id}")
@limiter.limit("60/minute")
def get_video(
    request: Request,
    video_id: int,
    context=Depends(get_context),
    _: str = Depends(verify_api_key),
) -> dict:
    video = context.repository.get_video(video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    video["frames"] = context.repository.get_frames_for_video(video_id)
    return video


@router.get("/{video_id}/file")
@limiter.limit("60/minute")
def get_video_file(
    request: Request,
    video_id: int,
    context=Depends(get_context),
    _: str = Depends(verify_media_api_key),
):
    video = context.repository.get_video(video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    video_path = Path(video["filepath"])
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video file missing")
    return FileResponse(video_path)


@router.post("/{video_id}/process", status_code=202)
@limiter.limit("60/minute")
async def process_video(
    request: Request,
    video_id: int,
    payload: ProcessVideoRequest,
    context=Depends(get_context),
    _: str = Depends(verify_api_key),
) -> dict:
    """Queue a full video processing job with the specified mode."""
    video = context.repository.get_video(video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")

    if payload.mode not in ("quick", "two_stage", "deep"):
        raise HTTPException(
            status_code=400,
            detail="Invalid mode. Use 'quick' (coarse only), 'two_stage' (coarse+fine), or 'deep' (full fine scan)"
        )

    task = await context.processing_service.schedule_video_processing(
        video_id,
        mode=payload.mode,
        action="process",
    )
    return {"status": "queued", "task": task}


@router.get("/{video_id}/segments")
@limiter.limit("60/minute")
def get_suspicious_segments(
    request: Request,
    video_id: int,
    context=Depends(get_context),
    _: str = Depends(verify_api_key),
) -> list[dict]:
    """Get all suspicious segments for a video."""
    video = context.repository.get_video(video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")

    with context.repository.connection() as conn:
        rows = conn.execute(
            "SELECT * FROM suspicious_segments WHERE video_id = ? ORDER BY start_timestamp",
            (video_id,),
        ).fetchall()
        segments = []
        for row in rows:
            segment = dict(row)
            segment["frame_ids"] = __import__("json").loads(segment.get("frame_ids", "[]"))
            segments.append(segment)
        return segments


@router.post("/{video_id}/rescan", status_code=202)
@limiter.limit("60/minute")
async def rescan_video(
    request: Request,
    video_id: int,
    payload: RescanRequest,
    context=Depends(get_context),
    _: str = Depends(verify_api_key),
) -> dict:
    """Queue a rescan job for a specific stage."""
    video = context.repository.get_video(video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")

    if payload.stage not in ("coarse", "fine"):
        raise HTTPException(status_code=400, detail="Invalid stage. Use 'coarse' or 'fine'")

    task = await context.processing_service.schedule_video_processing(
        video_id,
        mode="quick" if payload.stage == "coarse" else "two_stage",
        action="rescan",
        target_stage=payload.stage,
    )
    return {"status": "queued", "task": task}
