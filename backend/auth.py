from __future__ import annotations

from functools import lru_cache
import logging
import os
import secrets
from typing import Optional

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from backend.config import get_settings

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)
logger = logging.getLogger(__name__)


def _is_production() -> bool:
    return os.getenv("ENV", "development").lower() == "production"


@lru_cache(maxsize=1)
def _generate_development_api_key() -> str:
    generated = secrets.token_urlsafe(32)
    logger.warning(
        "API_KEY is not configured; using ephemeral development key: %s\n"
        "Set API_KEY in your environment to use a stable key.",
        generated,
    )
    return generated


def _load_api_key() -> str:
    """从配置获取 API Key。开发环境未配置时生成随机 key 并打印到日志。"""
    configured = get_settings().auth_api_key.strip()
    if configured:
        return configured
    if _is_production():
        raise RuntimeError("API_KEY must be set in production environment")
    return _generate_development_api_key()


def get_api_key() -> str:
    """返回当前配置生效的 API Key。"""
    return _load_api_key()


def _build_unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": f"ApiKey {API_KEY_NAME}"},
    )


def _validate_api_key(candidate_key: Optional[str], *, missing_detail: str) -> str:
    expected_key = get_api_key()
    if not candidate_key:
        raise _build_unauthorized(missing_detail)
    if not secrets.compare_digest(candidate_key, expected_key):
        raise _build_unauthorized("Invalid API Key")
    return candidate_key


async def verify_api_key(api_key: Optional[str] = Security(api_key_header)) -> str:
    """验证API Key。"""
    return _validate_api_key(api_key, missing_detail="X-API-Key header missing")


async def verify_media_api_key(
    api_key: Optional[str] = Security(api_key_header),
) -> str:
    """验证媒体资源访问的 API Key，仅支持请求头。"""
    return _validate_api_key(api_key, missing_detail="X-API-Key header missing")
