from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.api.deps import get_context
from backend.auth import verify_api_key, verify_media_api_key


router = APIRouter(prefix="/frames", tags=["frames"])
limiter = Limiter(key_func=get_remote_address)


@router.get("/video/{video_id}")
@limiter.limit("60/minute")
def list_frames(
    request: Request,
    video_id: int,
    context=Depends(get_context),
    _: str = Depends(verify_api_key),
) -> list[dict]:
    """获取视频的所有帧列表。"""
    return context.repository.get_frames_for_video(video_id)


@router.get("/{frame_id}/image")
@limiter.limit("60/minute")
def get_frame_image(
    request: Request,
    frame_id: int,
    context=Depends(get_context),
    _: str = Depends(verify_media_api_key),
):
    frame = context.repository.get_frame(frame_id)
    if frame is None:
        raise HTTPException(status_code=404, detail="Frame not found")
    image_path = Path(frame["image_path"])
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Frame image missing")
    return FileResponse(image_path)


@router.get("/{frame_id}/analysis")
@limiter.limit("60/minute")
def get_frame_analysis(
    request: Request,
    frame_id: int,
    context=Depends(get_context),
    _: str = Depends(verify_api_key),
) -> dict:
    analysis = context.repository.get_frame_analysis(frame_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return analysis
