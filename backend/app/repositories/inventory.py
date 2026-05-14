from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models import scanner_data

class ComputerRepository:
    def __init__(self, db: Session):
        """Initializes the repository with a database session.

        Args:
            db (Session): The SQLAlchemy database session.
        """
        self.db = db

    def get_by_serial(self, serial_num: str) -> scanner_data.Computer | None:
        """Fetches a computer from the database by its serial number.

        Args:
            serial_num (str): The unique serial number of the computer.

        Returns:
            scanner_data.Computer | None: The computer model if found, else None.
        """
        stmt = select(scanner_data.Computer).where(scanner_data.Computer.serial_num == serial_num)
        return self.db.execute(stmt).scalar_one_or_none()
    
    def get_all(self) -> list[scanner_data.Computer]:
        """Fetches all computers from the database.

        Returns:
            list[scanner_data.Computer]: A list of all computers.
        """
        stmt = select(scanner_data.Computer)
        return list(self.db.execute(stmt).scalars().all())
    def save(self, computer: scanner_data.Computer, is_new: bool = False) -> scanner_data.Computer:
        """Saves a computer and its relationships to the database.

        Args:
            computer (scanner_data.Computer): The SQLAlchemy model instance.
            is_new (bool): Flag indicating whether to add a new instance or just commit an existing one.

        Returns:
            scanner_data.Computer: The saved and refreshed database model.
        """
        if is_new:
            self.db.add(computer)
            
        self.db.commit()
        self.db.refresh(computer)
        
        return computer