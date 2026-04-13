from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi import Query
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.api.deps import get_context


router = APIRouter(prefix="/tasks", tags=["tasks"])
limiter = Limiter(key_func=get_remote_address)
VALID_PROCESSING_MODES = {"quick", "two_stage", "deep"}


def resolve_retry_mode(details: dict) -> str:
    requested_mode = str(details.get("requested_mode") or details.get("mode") or "two_stage")
    if requested_mode in VALID_PROCESSING_MODES:
        return requested_mode

    action = str(details.get("action", "process"))
    target_stage = str(details.get("target_stage") or "")
    if action == "rescan":
        return "quick" if target_stage == "coarse" else "two_stage"
    return "two_stage"


@router.get("")
@limiter.limit("60/minute")
def list_tasks(
    request: Request,
    context=Depends(get_context),
    active_only: bool = False,
    limit: Annotated[int | None, Query(ge=1, le=200)] = None,
) -> list[dict]:
    return context.repository.list_tasks(active_only=active_only, limit=limit)


@router.get("/{task_id}/progress")
@limiter.limit("60/minute")
def get_task_progress(request: Request, task_id: int, context=Depends(get_context)) -> dict:
    task = context.repository.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("/{task_id}/retry")
@limiter.limit("60/minute")
async def retry_task(request: Request, task_id: int, context=Depends(get_context)) -> dict:
    task = context.repository.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task["task_type"] != "video_process":
        raise HTTPException(status_code=400, detail="Unsupported task type for retry")
    details = task.get("details", {}) or {}
    scheduled = await context.processing_service.schedule_video_processing(
        task["video_id"],
        mode=resolve_retry_mode(details),
        action=str(details.get("action", "process")),
        target_stage=str(details["target_stage"]) if details.get("target_stage") is not None else None,
    )
    return {"status": "queued", "task": scheduled}
