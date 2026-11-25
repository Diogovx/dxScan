import asyncio
import logging
import re
import ssl
from dataclasses import dataclass
from enum import Enum

from ldap3 import NONE, SIMPLE, SUBTREE, Connection, Server, Tls
from ldap3.core.exceptions import LDAPException
from ldap3.utils.conv import escape_filter_chars

from app.core.config import Settings

logger = logging.getLogger("dxscan.auth")

# sAMAccountName-style logins only: blocks UPN/DN tricks and LDAP filter metacharacters up front.
_USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


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

    # --- internals (sync, run in a thread) ---

    def _authenticate_sync(self, username: str, password: str) -> DirectoryUser:
        username = (username or "").strip()
        # An empty password on a simple bind is an "unauthenticated bind" that many DCs accept as success.
        if not password or not _USERNAME_RE.fullmatch(username):
            raise AuthenticationError(AuthFailure.INVALID_INPUT)

        conn = self._open_connection(f"{username}@{self.settings.LDAP_DOMAIN}", password)
        try:
            try:
                if not conn.bind():
                    raise AuthenticationError(AuthFailure.INVALID_CREDENTIALS)
            except LDAPException as exc:
                logger.warning("LDAP bind error: %s", type(exc).__name__)
                raise AuthenticationError(AuthFailure.DIRECTORY_UNAVAILABLE) from exc

            account_name = self._bound_account_name(conn)
            if not account_name:
                # Fail closed: without a server-confirmed identity we cannot safely check the OU.
                raise AuthenticationError(AuthFailure.DIRECTORY_UNAVAILABLE)

            return self._find_in_allowed_ou(conn, account_name)
        finally:
            conn.unbind()

    def _open_connection(self, user: str, password: str) -> Connection:
        tls = Tls(validate=ssl.CERT_REQUIRED if self.settings.LDAP_VALIDATE_CERT else ssl.CERT_NONE)
        server = Server(
            self.settings.LDAP_SERVER_URI,
            get_info=NONE,
            tls=tls,
            connect_timeout=self.settings.LDAP_TIMEOUT_SECONDS,
        )
        return Connection(
            server,
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
            logger.warning("LDAP search error: %s", type(exc).__name__)
            raise AuthenticationError(AuthFailure.DIRECTORY_UNAVAILABLE) from exc

        if not found or len(conn.entries) != 1:
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
