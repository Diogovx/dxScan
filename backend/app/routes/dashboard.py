from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.repositories.dashboard import DashboardFilters, DashboardRepository
from app.schemas.dashboard import DashboardResponse
from app.services.dashboard import DashboardService

router = APIRouter(prefix="/api/v1/dashboard", tags=["Dashboard"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("/", response_model=DashboardResponse, dependencies=[Depends(get_current_user)])
async def get_dashboard(
    db: DbSession,
    operating_system: Annotated[list[str] | None, Query(description="Filtra por sistema operacional (repetível)")] = None,
    manufacturer: Annotated[list[str] | None, Query(description="Filtra por fabricante (repetível)")] = None,
    equipment_type: Annotated[list[str] | None, Query(description="Filtra por tipo: Notebook, Desktop (repetível)")] = None,
    top: Annotated[int, Query(ge=1, le=50, description="Tamanho do ranking de softwares")] = 15,
    hide_runtimes: Annotated[bool, Query(description="Oculta runtimes e updates do ranking de softwares")] = True,
):
    """Fleet health for the main dashboard: one normalized row per machine (with alerts) plus the
    software ranking, both restricted by the same filters. Requires a Bearer token.
    """
    filters = DashboardFilters(
        operating_systems=operating_system or [],
        manufacturers=manufacturer or [],
        equipment_types=equipment_type or [],
    )
    try:
        service = DashboardService(DashboardRepository(db))
        return await service.build(filters, now=datetime.now(), top=top, hide_runtimes=hide_runtimes)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {e!s}") from e
