from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AccessLog(Base):
    """One row per HTTP request handled by the API, plus explicit auth events (login success/failure).

    Request bodies are never stored (they carry passwords and full inventories).
    """

    __tablename__ = "access_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    # http_request | login_success | login_failure
    event: Mapped[str] = mapped_column(String(30), index=True)
    # user | scanner | anonymous
    principal_type: Mapped[str] = mapped_column(String(20))
    principal: Mapped[str | None] = mapped_column(String(150), index=True)
    method: Mapped[str | None] = mapped_column(String(10))
    path: Mapped[str | None] = mapped_column(String(500))
    status_code: Mapped[int | None]
    duration_ms: Mapped[float | None]
    client_ip: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    detail: Mapped[str | None] = mapped_column(Text)
