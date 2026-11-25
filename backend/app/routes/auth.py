import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from app.core.access_log import log_auth_event
from app.core.config import settings
from app.core.security import create_access_token, get_current_user
from app.schemas.auth import CurrentUser, TokenResponse
from app.services.auth import AuthenticationError, AuthFailure, LdapAuthenticator

logger = logging.getLogger("dxscan.auth")

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])


def get_authenticator() -> LdapAuthenticator:
    return LdapAuthenticator(settings)


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    authenticator: Annotated[LdapAuthenticator, Depends(get_authenticator)],
):
    """Logs in with Active Directory credentials (sAMAccountName + password).

    Only accounts inside LDAP_ALLOWED_OU_DN (the TI OU) receive a token. The response never says *why*
    a login failed (wrong password vs. outside the OU); the reason goes to the access log only.
    """
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    request.state.principal = form.username[:150] or None
    request.state.principal_type = "user"

    try:
        directory_user = await authenticator.authenticate(form.username, form.password)
    except AuthenticationError as exc:
        request.state.access_detail = exc.reason.value
        await log_auth_event("login_failure", form.username[:150] or None, client_ip, user_agent, exc.reason.value)
        if exc.reason is AuthFailure.DIRECTORY_UNAVAILABLE:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Serviço de diretório indisponível")
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Usuário ou senha inválidos, ou usuário sem permissão",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = CurrentUser(
        username=directory_user.username,
        display_name=directory_user.display_name,
        email=directory_user.email,
    )
    request.state.principal = user.username
    await log_auth_event("login_success", user.username, client_ip, user_agent, directory_user.dn)

    token, expires_in = create_access_token(user)
    return TokenResponse(access_token=token, expires_in=expires_in, user=user)


@router.get("/me", response_model=CurrentUser)
async def me(user: Annotated[CurrentUser, Depends(get_current_user)]):
    """Returns the user identified by the Bearer token."""
    return user
