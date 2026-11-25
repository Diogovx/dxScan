from dataclasses import dataclass, field

from sqlalchemy import Select, func, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.scanner_data import Computer, Software

# Runtimes and updates that every machine has; they would crowd out the useful entries of the ranking.
RUNTIME_PATTERNS = (
    "Microsoft Visual C++%",
    "Microsoft .NET%",
    "Microsoft ASP.NET%",
    "Microsoft Windows Desktop Runtime%",
    "%Redistributable%",
    "Update for%",
    "Security Update%",
    "%Hotfix%",
)


@dataclass(frozen=True)
class DashboardFilters:
    operating_systems: list[str] = field(default_factory=list)
    manufacturers: list[str] = field(default_factory=list)
    equipment_types: list[str] = field(default_factory=list)


def _apply_filters(stmt: Select, filters: DashboardFilters) -> Select:
    if filters.operating_systems:
        stmt = stmt.where(Computer.operating_system.in_(filters.operating_systems))
    if filters.manufacturers:
        stmt = stmt.where(Computer.manufacturer.in_(filters.manufacturers))
    if filters.equipment_types:
        stmt = stmt.where(Computer.equipment_type.in_(filters.equipment_types))
    return stmt


class DashboardRepository:
    """Read-only queries behind GET /api/v1/dashboard/. Only bound parameters, no raw SQL."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_machines(self, filters: DashboardFilters) -> list[tuple[Computer, int]]:
        """Returns (computer with disks loaded, number of installed softwares) for every matching computer."""
        software_count = (
            select(func.count(Software.id))
            .where(Software.computer_id == Computer.id)
            .correlate(Computer)
            .scalar_subquery()
        )
        stmt = select(Computer, software_count).options(selectinload(Computer.disks)).order_by(Computer.hostname)
        result = await self.db.execute(_apply_filters(stmt, filters))
        return [(computer, count or 0) for computer, count in result.all()]

    async def top_software(self, filters: DashboardFilters, limit: int, hide_runtimes: bool) -> list[tuple[str, int]]:
        """Software names ranked by how many matching computers have them installed."""
        installs = func.count(func.distinct(Software.computer_id))
        stmt = (
            select(Software.software_name, installs)
            .join(Computer, Computer.id == Software.computer_id)
            .group_by(Software.software_name)
            .order_by(installs.desc(), Software.software_name)
            .limit(limit)
        )
        if hide_runtimes:
            stmt = stmt.where(not_(or_(*(Software.software_name.ilike(p) for p in RUNTIME_PATTERNS))))
        result = await self.db.execute(_apply_filters(stmt, filters))
        return [(name, count) for name, count in result.all()]
