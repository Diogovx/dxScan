from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas import ScannerPayload,ComputerDetailResponse, ComputerListResponse
from app.repositories.inventory import ComputerRepository
from app.services.inventory_service import InventoryService

router = APIRouter(prefix="/api/v1/inventory", tags=["Inventory"])

@router.post("/", status_code=200)
def receive_inventory(payload: ScannerPayload, db: Session = Depends(get_db)):
    """Receives inventory data from the PowerShell scanner and saves it to the database.

    Args:
        payload (ScannerPayload): The JSON payload automatically validated by Pydantic.
        db (Session): The database session injected by FastAPI.

    Returns:
        dict: A success message and the serial number of the processed computer.
    """
    try:
        repo = ComputerRepository(db)
        
        service = InventoryService(repo)
        
        computer = service.process_inventory_payload(payload)
        
        return {
            "message": "Inventory successfully processed", 
            "computer_serial": computer.serial_num
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process inventory: {str(e)}")


@router.get("/", response_model=list[ComputerListResponse], status_code=200)
def list_computers(db: Session = Depends(get_db)):
    """Retrieves a summary list of all registered computers.

    Args:
        db (Session): The database session injected by FastAPI.

    Returns:
        list[ComputerListResponse]: A list containing the summary details of all computers.
    
    Raises:
        HTTPException: If an internal server error occurs during database retrieval.
    """
    try:
        repo = ComputerRepository(db)
        computers = repo.get_all()
        return computers
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")

@router.get("/{serial_num}", response_model=ComputerDetailResponse, status_code=200)
def get_computer_details(serial_num: str, db: Session = Depends(get_db)):
    """Retrieves the complete detailed profile of a specific computer by its Serial Number.

    Args:
        serial_num (str): The unique serial number of the target computer.
        db (Session): The database session injected by FastAPI.

    Returns:
        ComputerDetailResponse: An object containing the computer's core details along 
        with its nested relationships (disks, monitors, networks, and software).

    Raises:
        HTTPException (404): If no computer is found with the provided serial number.
        HTTPException (500): If an internal server error occurs during database retrieval.
    """
    try:
        repo = ComputerRepository(db)
        computer = repo.get_by_serial(serial_num)
        
        if not computer:
            raise HTTPException(status_code=404, detail="Computador não encontrado")
            
        return computer
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")