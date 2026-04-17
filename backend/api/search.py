from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.api.deps import get_context
from backend.models import SearchRequest


router = APIRouter(prefix="/search", tags=["search"])
limiter = Limiter(key_func=get_remote_address)
DETAIL_FRAME_WINDOW = 60


@router.post("")
@limiter.limit("60/minute")
def search(request: Request, payload: SearchRequest, context=Depends(get_context)) -> dict:
    results = context.search_service.search(
        payload.query,
        filters={
            "video_id": payload.video_id,
            "time_start": payload.time_start,
            "time_end": payload.time_end,
            "ai_tool_detected": payload.ai_tool_detected,
        },
    )
    segments = context.search_service.build_segments(
        results,
        max_gap_seconds=float(context.settings.frame_interval),
    )
    return {
        "query": payload.query,
        "count": len(results),
        "segment_count": len(segments),
        "results": results,
        "segments": segments,
    }


@router.get("/results/{frame_id}")
@limiter.limit("60/minute")
def get_search_result_detail(request: Request, frame_id: int, context=Depends(get_context)) -> dict:
    frame = context.repository.get_frame(frame_id)
    if frame is None:
        raise HTTPException(status_code=404, detail="Frame not found")
    analysis = context.repository.get_frame_analysis(frame_id)
    video = context.repository.get_video(frame["video_id"])
    frames = context.repository.get_frames_for_video_window(
        frame["video_id"],
        frame_id,
        before=DETAIL_FRAME_WINDOW,
        after=DETAIL_FRAME_WINDOW,
    )
    total_frames = context.repository.count_frames_for_video(frame["video_id"])
    return {
        "video": video,
        "frame": frame,
        "analysis": analysis,
        "frames": frames,
        "total_frames": total_frames,
    }
