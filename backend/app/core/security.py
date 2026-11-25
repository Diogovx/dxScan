import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer

from app.core.config import settings
from app.schemas.auth import CurrentUser

# tokenUrl makes the "Authorize" button in Swagger UI (/docs) log in through the AD endpoint.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)
scanner_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

_CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Não autenticado ou sessão expirada",
    headers={"WWW-Authenticate": "Bearer"},
)


def create_access_token(user: CurrentUser) -> tuple[str, int]:
    """Issues a signed JWT for a user that passed the AD check. Returns (token, expires_in_seconds)."""
    expires_in = settings.JWT_EXPIRE_MINUTES * 60
    now = datetime.now(UTC)
    claims = {
        "sub": user.username,
        "name": user.display_name,
        "email": user.email,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    token = jwt.encode(claims, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return token, expires_in


def decode_access_token(token: str) -> CurrentUser:
    try:
        claims = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],  # pinned: never trust the alg in the token header
            options={"require": ["sub", "exp"]},
        )
    except jwt.PyJWTError:
        raise _CREDENTIALS_EXCEPTION
    return CurrentUser(username=claims["sub"], display_name=claims.get("name"), email=claims.get("email"))


async def get_current_user(request: Request, token: Annotated[str | None, Depends(oauth2_scheme)]) -> CurrentUser:
    """Dependency for routes used by people (dashboard, Swagger). Requires a valid Bearer token."""
    if not token:
        raise _CREDENTIALS_EXCEPTION
    user = decode_access_token(token)
    request.state.principal = user.username
    request.state.principal_type = "user"
    return user


async def require_scanner_key(request: Request, api_key: Annotated[str | None, Security(scanner_key_header)]) -> None:
    """Dependency for the ingestion endpoint used by the PowerShell agents.

    When SCANNER_API_KEY is empty the endpoint stays open (legacy mode, a warning is logged at startup),
    so already-deployed scanners keep working until their config.json gets the key.
    """
    request.state.principal_type = "scanner"
    expected = settings.SCANNER_API_KEY
    if not expected:
        request.state.principal = "scanner:sem-chave"
        return
    if not api_key or not secrets.compare_digest(api_key.encode(), expected.encode()):
        request.state.principal = "scanner:chave-invalida"
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key do scanner inválida")
    request.state.principal = "scanner"
