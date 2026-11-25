from pydantic import BaseModel


class CurrentUser(BaseModel):
    username: str
    display_name: str | None = None
    email: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: CurrentUser
