from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.api.deps import get_context
from backend.models import KeywordSetCreate, KeywordSetUpdate


router = APIRouter(prefix="/keywords", tags=["keywords"])
limiter = Limiter(key_func=get_remote_address)


@router.get("")
@limiter.limit("60/minute")
def list_keyword_sets(request: Request, context=Depends(get_context)) -> list[dict]:
    return context.repository.list_keyword_sets()


@router.post("", status_code=201)
@limiter.limit("60/minute")
def create_keyword_set(request: Request, payload: KeywordSetCreate, context=Depends(get_context)) -> dict:
    return context.repository.upsert_keyword_set(
        name=payload.name,
        category=payload.category,
        terms=payload.terms,
    )


@router.put("/{keyword_set_id}")
@limiter.limit("60/minute")
def update_keyword_set(
    request: Request,
    keyword_set_id: int,
    payload: KeywordSetUpdate,
    context=Depends(get_context),
) -> dict:
    if context.repository.get_keyword_set(keyword_set_id) is None:
        raise HTTPException(status_code=404, detail="Keyword set not found")
    return context.repository.upsert_keyword_set(
        keyword_set_id=keyword_set_id,
        name=payload.name,
        category=payload.category,
        terms=payload.terms,
    )


@router.delete("/{keyword_set_id}", status_code=204)
@limiter.limit("60/minute")
def delete_keyword_set(request: Request, keyword_set_id: int, context=Depends(get_context)) -> Response:
    if context.repository.get_keyword_set(keyword_set_id) is None:
        raise HTTPException(status_code=404, detail="Keyword set not found")
    context.repository.delete_keyword_set(keyword_set_id)
    return Response(status_code=204)


@router.post("/{keyword_set_id}/scan")
@limiter.limit("60/minute")
def scan_with_keyword_set(request: Request, keyword_set_id: int, context=Depends(get_context)) -> dict:
    keyword_set = context.repository.get_keyword_set(keyword_set_id)
    if keyword_set is None:
        raise HTTPException(status_code=404, detail="Keyword set not found")
    aggregated: dict[int, dict] = {}
    for term in keyword_set["terms"]:
        for result in context.search_service.search(term, filters={}):
            frame_id = result["frame_id"]
            if frame_id not in aggregated:
                aggregated[frame_id] = {**result, "matched_terms": [term]}
            else:
                aggregated[frame_id]["matched_terms"].append(term)
    results = sorted(
        aggregated.values(),
        key=lambda item: (item["video_name"], item["timestamp"]),
    )
    return {
        "keyword_set_id": keyword_set_id,
        "total_terms": len(keyword_set["terms"]),
        "total_hits": len(results),
        "results": results,
    }
