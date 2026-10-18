import pytest
from fastapi.testclient import TestClient

from devfolio.config import Settings, database_url, required
from health import app


def test_missing_configuration_and_tls(monkeypatch):
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    with pytest.raises(ValueError, match="SUPABASE_DB_URL is required"):
        required("SUPABASE_DB_URL")
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://reader:secret@external.example/postgres")
    with pytest.raises(ValueError, match="TLS"):
        database_url("SUPABASE_DB_URL")
    with pytest.raises(ValueError):
        Settings("owner", dimensions=384)
    with pytest.raises(ValueError):
        Settings("bad/path")


def test_health_and_safe_readiness(monkeypatch):
    import devfolio.runtime

    def fail():
        raise RuntimeError("secret database details")

    monkeypatch.setattr(devfolio.runtime, "get_runtime", fail)
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.json() == {"status": "ok"}
        assert health.headers["X-Request-ID"] and health.headers["Cache-Control"] == "no-store"
        ready = client.get("/ready")
        assert ready.status_code == 503 and "secret" not in ready.text


def test_successful_readiness(monkeypatch):
    from types import SimpleNamespace

    import devfolio.runtime

    monkeypatch.setattr(
        devfolio.runtime, "get_runtime", lambda: SimpleNamespace(reader=SimpleNamespace(ready=lambda: True))
    )
    assert TestClient(app).get("/ready").json() == {"status": "ready"}
