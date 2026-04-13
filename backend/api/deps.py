from __future__ import annotations

from fastapi import Request


def get_context(request: Request):
    return request.app.state.context
