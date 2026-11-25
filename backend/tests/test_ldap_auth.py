"""LdapAuthenticator against an in-memory fake directory (ldap3 MOCK_SYNC)."""
import asyncio
from types import SimpleNamespace

import pytest
from ldap3 import MOCK_SYNC, Connection, Server

from app.services.auth import AuthenticationError, AuthFailure, LdapAuthenticator

BASE = "DC=exemplo,DC=test"
USERS = {
    # sAMAccountName: (dn, password)
    "ana.ti": (f"CN=Ana TI,OU=TI,{BASE}", "senha-ana"),
    "bruno.suporte": (f"CN=Bruno Suporte,OU=Suporte,OU=TI,{BASE}", "senha-bruno"),
    "carla.fin": (f"CN=Carla Fin,OU=Financeiro,{BASE}", "senha-carla"),
}


class FakeDirectoryAuthenticator(LdapAuthenticator):
    """Real authentication logic; only the transport is swapped for ldap3's mock strategy.

    The mock binds by DN and does not implement "Who am I?", so those two pieces are emulated
    the way AD behaves (UPN bind; whoami answers u:DOMAIN\\sam).
    """

    def __init__(self, settings, whoami_works: bool = True):
        super().__init__(settings)
        self.whoami_works = whoami_works
        self.server = Server("fake-dc")
        setup = Connection(self.server, client_strategy=MOCK_SYNC)
        for sam, (dn, password) in USERS.items():
            setup.strategy.add_entry(dn, {
                "objectClass": ["top", "person", "user"],
                "objectCategory": "person",
                "sAMAccountName": sam,
                "displayName": dn.split(",")[0].removeprefix("CN="),
                "mail": f"{sam}@exemplo.test",
                "userPassword": password,
            })
        self._bound_sam: str | None = None

    def _open_connection(self, user, password):
        sam = user.split("@", 1)[0]
        dn = USERS.get(sam, (f"CN={sam},{BASE}", None))[0]
        self._bound_sam = sam
        return Connection(self.server, user=dn, password=password, client_strategy=MOCK_SYNC)

    def _bound_account_name(self, conn):
        return self._bound_sam if self.whoami_works else None


def _login(authenticator, username, password):
    return asyncio.run(authenticator.authenticate(username, password))


@pytest.fixture
def authenticator(auth_settings):
    return FakeDirectoryAuthenticator(auth_settings)


def test_user_directly_in_ti_ou_is_accepted(authenticator):
    user = _login(authenticator, "ana.ti", "senha-ana")
    assert user.username == "ana.ti"
    assert user.display_name == "Ana TI"
    assert user.dn.endswith(f"OU=TI,{BASE}")


def test_user_in_sub_ou_of_ti_is_accepted(authenticator):
    assert _login(authenticator, "bruno.suporte", "senha-bruno").username == "bruno.suporte"


def test_valid_user_outside_ti_ou_is_refused(authenticator):
    with pytest.raises(AuthenticationError) as exc:
        _login(authenticator, "carla.fin", "senha-carla")
    assert exc.value.reason is AuthFailure.NOT_IN_ALLOWED_OU


def test_wrong_password_is_refused(authenticator):
    with pytest.raises(AuthenticationError) as exc:
        _login(authenticator, "ana.ti", "senha-errada")
    assert exc.value.reason is AuthFailure.INVALID_CREDENTIALS


@pytest.mark.parametrize("username,password", [
    ("ana.ti", ""),                      # unauthenticated bind would "succeed" on many DCs
    ("", "qualquer"),
    ("*)(sAMAccountName=*", "x"),        # LDAP filter injection
    ("ana.ti@outro.dominio", "x"),       # UPN of another domain
    ("CN=Ana TI,OU=TI,DC=exemplo", "x"), # raw DN
])
def test_malformed_input_is_rejected_before_contacting_ad(authenticator, username, password):
    with pytest.raises(AuthenticationError) as exc:
        _login(authenticator, username, password)
    assert exc.value.reason is AuthFailure.INVALID_INPUT


def test_fails_closed_when_identity_cannot_be_confirmed(auth_settings):
    authenticator = FakeDirectoryAuthenticator(auth_settings, whoami_works=False)
    with pytest.raises(AuthenticationError) as exc:
        _login(authenticator, "ana.ti", "senha-ana")
    assert exc.value.reason is AuthFailure.DIRECTORY_UNAVAILABLE


@pytest.mark.parametrize("whoami,expected", [
    ("u:EXEMPLO\\ana.ti", "ana.ti"),
    ("", None),
    (None, None),
])
def test_bound_account_name_parses_ad_whoami(auth_settings, whoami, expected):
    conn = SimpleNamespace(extend=SimpleNamespace(standard=SimpleNamespace(who_am_i=lambda: whoami)))
    assert LdapAuthenticator(auth_settings)._bound_account_name(conn) == expected
