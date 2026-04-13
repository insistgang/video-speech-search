import asyncio
import importlib
import logging
from unittest.mock import Mock

import pytest

from backend.config import get_settings


def test_development_mode_generates_ephemeral_key_when_api_key_missing(monkeypatch):
    import backend.auth as auth_module

    logger = Mock()

    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.setattr(logging, "getLogger", lambda _name: logger)
    get_settings.cache_clear()

    auth_module = importlib.reload(auth_module)
    try:
        # In dev mode, a non-empty ephemeral key is generated
        key = auth_module.get_api_key()
        assert key != ""
        assert key == auth_module.get_api_key()  # stable across calls

        # verify_api_key rejects missing header
        with pytest.raises(auth_module.HTTPException) as exc_info:
            asyncio.run(auth_module.verify_api_key(None))
        assert exc_info.value.status_code == 401

        # verify_api_key rejects wrong key
        with pytest.raises(auth_module.HTTPException) as exc_info:
            asyncio.run(auth_module.verify_api_key("wrong_key"))
        assert exc_info.value.status_code == 401

        # verify_api_key accepts the correct key
        assert asyncio.run(auth_module.verify_api_key(key)) == key
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
        importlib.reload(auth_module)


def test_production_requires_api_key(monkeypatch):
    import backend.auth as auth_module

    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.setenv("ENV", "production")
    get_settings.cache_clear()

    auth_module = importlib.reload(auth_module)

    with pytest.raises(RuntimeError, match="API_KEY must be set in production environment"):
        auth_module.get_api_key()
