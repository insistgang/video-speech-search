from __future__ import annotations

from backend.main import LOCALHOST_CORS_REGEX, get_cors_configuration


def test_cors_defaults_to_localhost_regex_when_env_is_unset(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)

    origins, origin_regex = get_cors_configuration()

    assert origins == []
    assert origin_regex == LOCALHOST_CORS_REGEX


def test_cors_uses_explicit_origins_when_configured(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173, http://localhost:4173")
    monkeypatch.delenv("ENV", raising=False)

    origins, origin_regex = get_cors_configuration()

    assert origins == ["http://localhost:5173", "http://localhost:4173"]
    assert origin_regex == LOCALHOST_CORS_REGEX


def test_cors_disables_loopback_regex_in_production_when_origins_are_configured(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://console.example.com")
    monkeypatch.setenv("ENV", "production")

    origins, origin_regex = get_cors_configuration()

    assert origins == ["https://console.example.com"]
    assert origin_regex is None
