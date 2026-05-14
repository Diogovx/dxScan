from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.scanner import ScannerPayload
from app.schemas.responses import ComputerListResponse
from app.repositories.inventory import ComputerRepository
from app.services.inventory_service import InventoryService # Ajuste o import conforme o nome do seu arquivo

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
        # 1. Instancia o repositório entregando a conexão com o banco
        repo = ComputerRepository(db)
        
        # 2. Instancia o serviço entregando o repositório
        service = InventoryService(repo)
        
        # 3. Processa o payload mágico
        computer = service.process_inventory_payload(payload)
        
        return {
            "message": "Inventory successfully processed", 
            "computer_serial": computer.serial_num
        }
        
    except Exception as e:
        # Se falhar, devolve um Erro 500 para quem chamou a API
        raise HTTPException(status_code=500, detail=f"Failed to process inventory: {str(e)}")


@router.get("/", response_model=list[ComputerListResponse], status_code=200)
def list_computers(db: Session = Depends(get_db)):
    """Retorna a lista de todos os computadores cadastrados."""
    try:
        repo = ComputerRepository(db)
        computers = repo.get_all()
        return computers
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")
