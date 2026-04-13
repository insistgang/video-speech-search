from fastapi import APIRouter, Depends, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.api.deps import get_context


router = APIRouter(tags=["health"])
limiter = Limiter(key_func=get_remote_address)


@router.get("/health")
@limiter.limit("10/minute")
def healthcheck(request: Request, context=Depends(get_context)) -> dict[str, str]:
    return {"status": "ok", "vision_analyzer_mode": context.settings.vision_analyzer_mode}
