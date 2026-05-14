from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime

class ComputerListResponse(BaseModel):
    """Molde que define quais dados do computador vamos devolver na listagem."""
    serial_num: str
    hostname: str
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    operating_system: Optional[str] = None
    ram_gb: Optional[float] = None
    last_verification: Optional[datetime] = None

    # Isso avisa ao Pydantic para ler os dados do SQLAlchemy sem reclamar
    model_config = ConfigDict(from_attributes=True)