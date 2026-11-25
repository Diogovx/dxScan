import asyncio
import logging
import re
import ssl
import time
from dataclasses import dataclass
from enum import Enum

from ldap3 import NONE, SIMPLE, SUBTREE, Connection, Server, Tls
from ldap3.core.exceptions import LDAPException
from ldap3.utils.conv import escape_filter_chars

from app.core.config import Settings

logger = logging.getLogger("dxscan.auth")

# sAMAccountName-style logins only: blocks UPN/DN tricks and LDAP filter metacharacters up front.
_USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

# AD puts the real reason for a failed bind in the diagnostic message: "... data 52e, v4563".
_AD_DATA_CODE_RE = re.compile(r"\bdata ([0-9a-f]{3,4})\b", re.IGNORECASE)
AD_BIND_REASONS = {
    "525": "usuário não encontrado",
    "52e": "senha incorreta",
    "530": "login fora do horário permitido",
    "531": "login não permitido nesta estação",
    "532": "senha expirada",
    "533": "conta desabilitada",
    "701": "conta expirada",
    "773": "usuário precisa trocar a senha",
    "775": "conta bloqueada",
}


def describe_bind_failure(result: dict | None) -> str:
    """Turns ldap3's ``conn.result`` after a failed bind into a short reason for the server log."""
    result = result or {}
    description = result.get("description") or "desconhecido"
    match = _AD_DATA_CODE_RE.search(result.get("message") or "")
    if not match:
        return description
    code = match.group(1).lower()
    return f"{description} (AD data {code}: {AD_BIND_REASONS.get(code, 'código não mapeado')})"


@dataclass(frozen=True)
class ConnectionCheck:
    ok: bool
    detail: str
    elapsed_ms: int


class AuthFailure(str, Enum):
    INVALID_INPUT = "invalid_input"
    INVALID_CREDENTIALS = "invalid_credentials"
    NOT_IN_ALLOWED_OU = "not_in_allowed_ou"
    DIRECTORY_UNAVAILABLE = "directory_unavailable"


@dataclass(frozen=True)
class DirectoryUser:
    username: str
    display_name: str | None
    email: str | None
    dn: str


class AuthenticationError(Exception):
    def __init__(self, reason: AuthFailure):
        super().__init__(reason.value)
        self.reason = reason


class LdapAuthenticator:
    """Authenticates a user against Active Directory and checks that the account lives in the allowed OU.

    Flow:
      1. Bind as the user (UPN ``username@LDAP_DOMAIN``) - this is the password check. No service account needed.
      2. Ask the server who we are bound as (RFC 4532 "Who am I?") so the identity comes from AD, not from user input.
      3. Search for that account *inside* ``LDAP_ALLOWED_OU_DN`` (subtree, so sub-OUs count).
         If it is not there, the login is refused even though the password was correct.
    """

    def __init__(self, settings: Settings):
        self.settings = settings

    async def authenticate(self, username: str, password: str) -> DirectoryUser:
        # ldap3 is a blocking library; run it in a worker thread to keep the event loop free.
        return await asyncio.to_thread(self._authenticate_sync, username, password)

    async def check_connection(self) -> ConnectionCheck:
        """Opens a connection to the DC (TCP, plus the TLS handshake for ldaps://) without binding.

        Proves the server is reachable and its certificate is accepted; it does not test any password.
        """
        return await asyncio.to_thread(self._check_connection_sync)

    # --- internals (sync, run in a thread) ---

    def _check_connection_sync(self) -> ConnectionCheck:
        started = time.perf_counter()
        conn = self._probe_connection()
        try:
            conn.open()
            ok, detail = True, "conectado"
        except LDAPException as exc:
            ok, detail = False, f"{type(exc).__name__}: {exc}"
        finally:
            conn.unbind()
        return ConnectionCheck(ok=ok, detail=detail, elapsed_ms=round((time.perf_counter() - started) * 1000))

    def _authenticate_sync(self, username: str, password: str) -> DirectoryUser:
        username = (username or "").strip()
        # An empty password on a simple bind is an "unauthenticated bind" that many DCs accept as success.
        if not password or not _USERNAME_RE.fullmatch(username):
            raise AuthenticationError(AuthFailure.INVALID_INPUT)

        conn = self._open_connection(f"{username}@{self.settings.LDAP_DOMAIN}", password)
        try:
            try:
                bound = conn.bind()
            except LDAPException as exc:
                logger.warning(
                    "AD: falha de conexão com %s ao autenticar '%s': %s: %s",
                    self.settings.LDAP_SERVER_URI, username, type(exc).__name__, exc,
                )
                raise AuthenticationError(AuthFailure.DIRECTORY_UNAVAILABLE) from exc
            if not bound:
                logger.info("AD: bind recusado para '%s': %s", username, describe_bind_failure(conn.result))
                raise AuthenticationError(AuthFailure.INVALID_CREDENTIALS)

            account_name = self._bound_account_name(conn)
            if not account_name:
                # Fail closed: without a server-confirmed identity we cannot safely check the OU.
                logger.warning("AD: 'Who am I?' não confirmou a identidade de '%s'; login recusado", username)
                raise AuthenticationError(AuthFailure.DIRECTORY_UNAVAILABLE)

            user = self._find_in_allowed_ou(conn, account_name)
            logger.info("AD: login ok para '%s' (%s)", user.username, user.dn)
            return user
        finally:
            conn.unbind()

    def _server(self) -> Server:
        tls = Tls(validate=ssl.CERT_REQUIRED if self.settings.LDAP_VALIDATE_CERT else ssl.CERT_NONE)
        return Server(
            self.settings.LDAP_SERVER_URI,
            get_info=NONE,
            tls=tls,
            connect_timeout=self.settings.LDAP_TIMEOUT_SECONDS,
        )

    def _probe_connection(self) -> Connection:
        """Anonymous connection used only to open the socket in check_connection; it never binds."""
        return Connection(self._server(), receive_timeout=self.settings.LDAP_TIMEOUT_SECONDS, raise_exceptions=False)

    def _open_connection(self, user: str, password: str) -> Connection:
        return Connection(
            self._server(),
            user=user,
            password=password,
            authentication=SIMPLE,
            receive_timeout=self.settings.LDAP_TIMEOUT_SECONDS,
            raise_exceptions=False,
        )

    def _bound_account_name(self, conn: Connection) -> str | None:
        """Returns the sAMAccountName of the bound account. AD answers 'u:DOMAIN\\sam'."""
        try:
            identity = conn.extend.standard.who_am_i()
        except LDAPException:
            return None
        if not identity:
            return None
        identity = identity.removeprefix("u:")
        return identity.split("\\", 1)[-1] or None

    def _find_in_allowed_ou(self, conn: Connection, account_name: str) -> DirectoryUser:
        search_filter = (
            "(&(objectClass=user)(objectCategory=person)"
            f"(sAMAccountName={escape_filter_chars(account_name)}))"
        )
        try:
            found = conn.search(
                search_base=self.settings.LDAP_ALLOWED_OU_DN,
                search_filter=search_filter,
                search_scope=SUBTREE,
                attributes=["sAMAccountName", "displayName", "mail"],
                size_limit=2,
            )
        except LDAPException as exc:
            logger.warning("AD: erro na busca em %s: %s: %s", self.settings.LDAP_ALLOWED_OU_DN, type(exc).__name__, exc)
            raise AuthenticationError(AuthFailure.DIRECTORY_UNAVAILABLE) from exc

        if not found or len(conn.entries) != 1:
            logger.info(
                "AD: '%s' autenticou, mas não está em %s; login recusado",
                account_name, self.settings.LDAP_ALLOWED_OU_DN,
            )
            raise AuthenticationError(AuthFailure.NOT_IN_ALLOWED_OU)

        entry = conn.entries[0]
        return DirectoryUser(
            username=str(entry.sAMAccountName.value),
            display_name=_attr(entry, "displayName"),
            email=_attr(entry, "mail"),
            dn=entry.entry_dn,
        )


def _attr(entry, name: str) -> str | None:
    if name in entry.entry_attributes and entry[name].value:
        return str(entry[name].value)
    return None
