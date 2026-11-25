import logging
import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, require_scanner_key
from app.repositories.inventory import ComputerRepository
from app.repositories.logs import ScanLogRepository
from app.schemas import ComputerDetailResponse, ComputerListResponse, ScannerPayload
from app.services.inventory import InventoryService

logger = logging.getLogger("dxscan.inventory")

router = APIRouter(prefix="/api/v1/inventory", tags=["Inventory"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.post("/", status_code=200, dependencies=[Depends(require_scanner_key)])
async def receive_inventory(request: Request, payload: ScannerPayload, db: DbSession):
    """Receives inventory data from the PowerShell scanner and saves it to the database.

    Authenticated by the X-API-Key header (see SCANNER_API_KEY). Every attempt, successful or not,
    is recorded in log_scanners.

    Args:
        payload (ScannerPayload): The JSON payload automatically validated by Pydantic.
        db (AsyncSession): The async database session injected by FastAPI.

    Returns:
        dict: A success message and the serial number of the processed computer.
    """
    hostname = payload.system.hostname
    request.state.access_detail = f"hostname={hostname} serial={payload.system.serial_num}"
    started = time.perf_counter()
    try:
        repo = ComputerRepository(db)
        service = InventoryService(repo)
        serial, computer_id = await service.process_inventory_payload(payload)
    except Exception as e:
        await db.rollback()
        await _record_scan(db, hostname, "error", started, error_msg=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to process inventory: {e!s}") from e

    await _record_scan(db, hostname, "success", started, computer_id=computer_id)
    return {"message": "Inventory successfully processed", "computer_serial": serial}


async def _record_scan(db: AsyncSession, hostname: str, status: str, started: float, **kwargs) -> None:
    # The inventory is already committed (or rolled back) at this point; a logging failure must not change the response.
    try:
        await ScanLogRepository(db).add(hostname, status, time.perf_counter() - started, **kwargs)
    except Exception:
        await db.rollback()
        logger.exception("Falha ao gravar log_scanners para %s", hostname)


@router.get("/", response_model=list[ComputerListResponse], status_code=200, dependencies=[Depends(get_current_user)])
async def list_computers(db: DbSession):
    """Retrieves a summary list of all registered computers. Requires a Bearer token.

    Args:
        db (AsyncSession): The async database session injected by FastAPI.

    Returns:
        list[ComputerListResponse]: A list containing the summary details of all computers.

    Raises:
        HTTPException: If an internal server error occurs during database retrieval.
    """
    try:
        repo = ComputerRepository(db)
        return await repo.get_all()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {e!s}") from e


@router.get("/{serial_num}", response_model=ComputerDetailResponse, status_code=200, dependencies=[Depends(get_current_user)])
async def get_computer_details(serial_num: str, db: DbSession):
    """Retrieves the complete detailed profile of a specific computer by its Serial Number. Requires a Bearer token.

    Args:
        serial_num (str): The unique serial number of the target computer.
        db (AsyncSession): The async database session injected by FastAPI.

    Returns:
        ComputerDetailResponse: An object containing the computer's core details along
        with its nested relationships (disks, monitors, networks, and software).

    Raises:
        HTTPException (404): If no computer is found with the provided serial number.
        HTTPException (500): If an internal server error occurs during database retrieval.
    """
    try:
        repo = ComputerRepository(db)
        computer = await repo.get_by_serial(serial_num)

        if not computer:
            raise HTTPException(status_code=404, detail="Computador não encontrado")

        return computer
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {e!s}") from e
