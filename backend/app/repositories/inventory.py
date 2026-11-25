from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert  # Importe o INSERT nativo do Postgres
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import scanner_data


class ComputerRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_serial(self, serial_num: str):
        stmt = select(scanner_data.Computer).where(scanner_data.Computer.serial_num == serial_num).options(
            selectinload(scanner_data.Computer.softwares),
            selectinload(scanner_data.Computer.disks),
            selectinload(scanner_data.Computer.monitors),
            selectinload(scanner_data.Computer.networks)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all(self):
        stmt = select(scanner_data.Computer)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def upsert_inventory(self, computer_data: dict, relations: dict) -> int:
        """Faz o Upsert Atômico e atualiza as relações rapidamente."""
        

        insert_stmt = insert(scanner_data.Computer).values(**computer_data)

        update_dict = {c.name: c for c in insert_stmt.excluded if c.name not in ['id', 'serial_num']}
        
        upsert_stmt = insert_stmt.on_conflict_do_update(
            index_elements=['serial_num'],
            set_=update_dict
        ).returning(scanner_data.Computer.id)

        result = await self.db.execute(upsert_stmt)
        computer_id = result.scalar_one()

        relation_mappings = [
            (scanner_data.Disk, relations.get("disks", [])),
            (scanner_data.Monitor, relations.get("monitors", [])),
            (scanner_data.Network, relations.get("networks", [])),
            (scanner_data.Software, relations.get("softwares", []))
        ]

        for table_model, rel_data in relation_mappings:
            await self.db.execute(delete(table_model).where(table_model.computer_id == computer_id))
            
            if rel_data:

                for item in rel_data:
                    item["computer_id"] = computer_id
                await self.db.execute(insert(table_model), rel_data)

        await self.db.commit()
        return computer_id