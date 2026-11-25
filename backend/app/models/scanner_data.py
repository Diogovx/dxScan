from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Computer(Base):
    __tablename__ = "computers"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    serial_num: Mapped[str] = mapped_column(String, unique=True, index=True) # nullable=False is default for Mapped[str]
    hostname: Mapped[str]
    manufacturer: Mapped[str | None]
    model: Mapped[str | None]
    equipment_type: Mapped[str | None]
    bios_version: Mapped[str | None]
    cpu: Mapped[str | None]
    ram_gb: Mapped[float | None]
    operating_system: Mapped[str | None]
    os_installation_date: Mapped[datetime | None]
    activity_time: Mapped[str | None]
    last_user: Mapped[str | None]
    battery_health: Mapped[str | None]
    antivirus: Mapped[str | None]
    local_admins: Mapped[str | None]
    reboot_pending: Mapped[str | None] 
    last_verification: Mapped[datetime]

    # Relationships (Explicit back_populates is the 2.x standard over backref)
    monitors: Mapped[list["Monitor"]] = relationship(back_populates="computer", cascade="all, delete-orphan")
    networks: Mapped[list["Network"]] = relationship(back_populates="computer", cascade="all, delete-orphan")
    disks: Mapped[list["Disk"]] = relationship(back_populates="computer", cascade="all, delete-orphan")
    softwares: Mapped[list["Software"]] = relationship(back_populates="computer", cascade="all, delete-orphan")
    printers: Mapped[list["Printer"]] = relationship(back_populates="computer", cascade="all, delete-orphan")

class Monitor(Base):
    __tablename__ = "monitors"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    computer_id: Mapped[int] = mapped_column(ForeignKey("computers.id"))
    serial_num: Mapped[str | None] 
    manufacturer: Mapped[str | None]
    model: Mapped[str | None]

    computer: Mapped["Computer"] = relationship(back_populates="monitors")

class Network(Base):
    __tablename__ = "networks"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    computer_id: Mapped[int] = mapped_column(ForeignKey("computers.id"))
    adapter_name: Mapped[str | None]
    mac_address: Mapped[str | None] = mapped_column(String(20))
    ip_address: Mapped[str | None]

    computer: Mapped["Computer"] = relationship(back_populates="networks")

class Disk(Base):
    __tablename__ = "disks"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    computer_id: Mapped[int] = mapped_column(ForeignKey("computers.id"))
    drive: Mapped[str | None] = mapped_column(String(5))
    size_gb: Mapped[float | None]
    free_gb: Mapped[float | None]

    computer: Mapped["Computer"] = relationship(back_populates="disks")

class Software(Base):
    __tablename__ = "softwares"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    computer_id: Mapped[int] = mapped_column(ForeignKey("computers.id"))
    software_name: Mapped[str]
    version: Mapped[str | None]

    computer: Mapped["Computer"] = relationship(back_populates="softwares")

class Printer(Base):
    __tablename__ = "printers"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    computer_id: Mapped[int] = mapped_column(ForeignKey("computers.id"))
    printer_name: Mapped[str]

    computer: Mapped["Computer"] = relationship(back_populates="printers")

class LogScanner(Base):
    __tablename__ = "log_scanners"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    # No ForeignKey here, as the computer might not exist in the DB when an error log is generated
    computer_id: Mapped[int | None] 
    hostname: Mapped[str]
    execution_date: Mapped[datetime]
    status: Mapped[str] = mapped_column(String(20))
    error_msg: Mapped[str | None] = mapped_column(Text)
    duration: Mapped[float | None]