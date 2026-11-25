"""HTTP-level tests: route protection, login endpoint, scanner API key and access logging."""
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.security import create_access_token
from app.main import app
from app.repositories.inventory import ComputerRepository
from app.repositories.logs import ScanLogRepository
from app.routes.auth import get_authenticator
from app.schemas.auth import CurrentUser
from app.services.auth import AuthenticationError, AuthFailure, DirectoryUser
from app.services.inventory import InventoryService
from tests.conftest import TEST_JWT_SECRET, TEST_SCANNER_KEY

INVENTORY = "/api/v1/inventory/"


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def valid_token():
    return create_access_token(CurrentUser(username="ana.ti", display_name="Ana TI"))[0]


@pytest.fixture
def no_computers(monkeypatch):
    async def get_all(self):
        return []
    monkeypatch.setattr(ComputerRepository, "get_all", get_all)


@pytest.fixture
def fake_authenticator():
    class Fake:
        result: DirectoryUser | AuthFailure = DirectoryUser("ana.ti", "Ana TI", "ana.ti@exemplo.test", "CN=Ana TI,OU=TI,DC=exemplo,DC=test")
        def __init__(self):
            self.calls: list[str] = []

        async def authenticate(self, username, password):
            self.calls.append(username)
            if isinstance(self.result, AuthFailure):
                raise AuthenticationError(self.result)
            return self.result

    fake = Fake()
    app.dependency_overrides[get_authenticator] = lambda: fake
    return fake


# --- dashboard routes (Bearer token) ---

def test_inventory_list_requires_token(client):
    assert client.get(INVENTORY).status_code == 401


def test_inventory_detail_requires_token(client):
    assert client.get(INVENTORY + "FAKE-SN-0001").status_code == 401


def test_inventory_list_with_valid_token(client, valid_token, no_computers):
    response = client.get(INVENTORY, headers=_bearer(valid_token))
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize("token", [
    "nao-e-um-jwt",
    jwt.encode({"sub": "ana.ti", "exp": datetime.now(UTC) - timedelta(minutes=1)}, TEST_JWT_SECRET, "HS256"),
    jwt.encode({"sub": "ana.ti", "exp": datetime.now(UTC) + timedelta(hours=1)}, "outro-segredo-qualquer-com-32-chars!!", "HS256"),
    jwt.encode({"sub": "ana.ti", "exp": datetime.now(UTC) + timedelta(hours=1)}, None, "none"),
    jwt.encode({"exp": datetime.now(UTC) + timedelta(hours=1)}, TEST_JWT_SECRET, "HS256"),
], ids=["garbage", "expired", "wrong-secret", "alg-none", "no-sub"])
def test_invalid_tokens_are_rejected(client, token, no_computers):
    assert client.get(INVENTORY, headers=_bearer(token)).status_code == 401


# --- login ---

def test_login_success_returns_usable_token(client, fake_authenticator, access_events):
    response = client.post("/api/v1/auth/login", data={"username": "ana.ti", "password": "senha-ficticia"})
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["username"] == "ana.ti"

    me = client.get("/api/v1/auth/me", headers=_bearer(body["access_token"]))
    assert me.json()["username"] == "ana.ti"

    assert any(e["event"] == "login_success" and e["principal"] == "ana.ti" for e in access_events)


@pytest.mark.parametrize("reason", [AuthFailure.INVALID_CREDENTIALS, AuthFailure.NOT_IN_ALLOWED_OU, AuthFailure.INVALID_INPUT])
def test_login_failure_is_generic_for_client_but_detailed_in_log(client, fake_authenticator, access_events, reason):
    fake_authenticator.result = reason
    response = client.post("/api/v1/auth/login", data={"username": "carla.fin", "password": "senha-ficticia"})
    assert response.status_code == 401
    assert reason.value not in response.text  # never reveal *why* to the caller
    failure = next(e for e in access_events if e["event"] == "login_failure")
    assert failure["principal"] == "carla.fin"
    assert failure["detail"] == reason.value


def test_login_directory_down_returns_503(client, fake_authenticator):
    fake_authenticator.result = AuthFailure.DIRECTORY_UNAVAILABLE
    response = client.post("/api/v1/auth/login", data={"username": "ana.ti", "password": "x"})
    assert response.status_code == 503


def test_password_never_reaches_access_log(client, fake_authenticator, access_events):
    client.post("/api/v1/auth/login", data={"username": "ana.ti", "password": "SENHA-SECRETA-123"})
    assert access_events
    assert "SENHA-SECRETA-123" not in repr(access_events)


# --- scanner ingestion (X-API-Key) ---

@pytest.fixture
def fake_ingestion(monkeypatch):
    scans: list[tuple] = []

    async def process(self, payload):
        return payload.system.serial_num, 42

    async def add(self, hostname, status, duration, **kwargs):
        scans.append((hostname, status, kwargs))

    monkeypatch.setattr(InventoryService, "process_inventory_payload", process)
    monkeypatch.setattr(ScanLogRepository, "add", add)
    return scans


def test_scanner_post_requires_key(client, scanner_payload, fake_ingestion):
    assert client.post(INVENTORY, json=scanner_payload).status_code == 401
    assert client.post(INVENTORY, json=scanner_payload, headers={"X-API-Key": "errada"}).status_code == 401
    assert fake_ingestion == []


def test_scanner_post_with_key_is_processed_and_logged(client, scanner_payload, fake_ingestion, access_events):
    response = client.post(INVENTORY, json=scanner_payload, headers={"X-API-Key": TEST_SCANNER_KEY})
    assert response.status_code == 200
    assert response.json() == {"message": "Inventory successfully processed", "computer_serial": "FAKE-SN-0001"}
    assert fake_ingestion == [("PC-FICTICIO-01", "success", {"computer_id": 42})]

    request_log = next(e for e in access_events if e["event"] == "http_request")
    assert request_log["principal_type"] == "scanner"
    assert request_log["status_code"] == 200
    assert "FAKE-SN-0001" in request_log["detail"]


def test_scanner_failure_is_logged_as_error(client, scanner_payload, fake_ingestion, monkeypatch):
    async def boom(self, payload):
        raise ValueError("falha simulada")
    monkeypatch.setattr(InventoryService, "process_inventory_payload", boom)

    response = client.post(INVENTORY, json=scanner_payload, headers={"X-API-Key": TEST_SCANNER_KEY})
    assert response.status_code == 500
    assert fake_ingestion == [("PC-FICTICIO-01", "error", {"error_msg": "falha simulada"})]


def test_scanner_post_open_in_legacy_mode(client, scanner_payload, fake_ingestion, auth_settings, monkeypatch):
    monkeypatch.setattr(auth_settings, "SCANNER_API_KEY", "")
    assert client.post(INVENTORY, json=scanner_payload).status_code == 200


def test_scanner_key_does_not_grant_dashboard_access(client, no_computers):
    assert client.get(INVENTORY, headers={"X-API-Key": TEST_SCANNER_KEY}).status_code == 401


# --- access log middleware ---

def test_every_request_is_logged_with_principal(client, valid_token, no_computers, access_events):
    client.get(INVENTORY, headers=_bearer(valid_token))
    client.get(INVENTORY)
    logs = [e for e in access_events if e["event"] == "http_request"]
    assert [(e["principal"], e["principal_type"], e["status_code"]) for e in logs] == [
        ("ana.ti", "user", 200),
        (None, "anonymous", 401),
    ]
    assert logs[0]["method"] == "GET" and logs[0]["path"] == INVENTORY


def test_docs_are_not_logged(client, access_events):
    client.get("/openapi.json")
    assert access_events == []
