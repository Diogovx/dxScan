from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scanner_data import LogScanner


class ScanLogRepository:
    """Persists one LogScanner row per ingestion attempt made by a PowerShell agent."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def add(
        self,
        hostname: str,
        status: str,
        duration: float,
        computer_id: int | None = None,
        error_msg: str | None = None,
    ) -> None:
        self.db.add(LogScanner(
            computer_id=computer_id,
            hostname=hostname[:255],
            # log_scanners.execution_date is TIMESTAMP WITHOUT TIME ZONE: store naive UTC.
            execution_date=datetime.now(UTC).replace(tzinfo=None),
            status=status[:20],
            error_msg=error_msg,
            duration=round(duration, 3),
        ))
        await self.db.commit()
