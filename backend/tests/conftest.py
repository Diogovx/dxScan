"""Shared fixtures. Everything here is fictitious: no real AD, no real database, no real secrets."""
import pytest
from fastapi.testclient import TestClient

from app.core import access_log
from app.core.config import settings
from app.core.database import get_db
from app.main import app

TEST_JWT_SECRET = "test-secret-only-for-pytest-0123456789abcdef"
TEST_SCANNER_KEY = "test-scanner-key"


@pytest.fixture(autouse=True)
def auth_settings(monkeypatch):
    monkeypatch.setattr(settings, "LDAP_SERVER_URI", "ldaps://dc.exemplo.test")
    monkeypatch.setattr(settings, "LDAP_DOMAIN", "exemplo.test")
    monkeypatch.setattr(settings, "LDAP_ALLOWED_OU_DN", "OU=TI,DC=exemplo,DC=test")
    monkeypatch.setattr(settings, "JWT_SECRET", TEST_JWT_SECRET)
    monkeypatch.setattr(settings, "JWT_EXPIRE_MINUTES", 60)
    monkeypatch.setattr(settings, "SCANNER_API_KEY", TEST_SCANNER_KEY)
    return settings


@pytest.fixture
def access_events(monkeypatch):
    """Captures access-log rows instead of writing them to PostgreSQL."""
    events: list[dict] = []

    async def fake_persist(entry):
        events.append(entry)

    monkeypatch.setattr(access_log, "persist", fake_persist)
    return events


class _DummySession:
    async def rollback(self):
        pass

    async def commit(self):
        pass

    def add(self, _obj):
        pass


@pytest.fixture
def client(access_events):
    async def fake_db():
        yield _DummySession()

    app.dependency_overrides[get_db] = fake_db
    # Not used as a context manager on purpose: the lifespan (which touches the real DB) does not run.
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def scanner_payload() -> dict:
    return {
        "Verification_Date": "2026-01-15 10:30:00",
        "System": {"Hostname": "PC-FICTICIO-01", "Serial_Number": "FAKE-SN-0001", "Operating_System": "Windows 11 Pro"},
        "Security": {"Antivirus_Status": "Ativo"},
        "Disks": {"Drive": "C:", "Size_GB": 237.5, "Free_GB": 120.1},
        "Softwares": [{"Name": "Programa Exemplo", "Version": "1.0"}],
    }
