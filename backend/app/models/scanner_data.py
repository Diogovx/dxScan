from datetime import datetime
from typing import List, Optional

from sqlalchemy import String, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

class Computer(Base):
    __tablename__ = "computers"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    serial_num: Mapped[str] = mapped_column(String, unique=True, index=True) # nullable=False is default for Mapped[str]
    hostname: Mapped[str]
    manufacturer: Mapped[Optional[str]]
    model: Mapped[Optional[str]]
    equipment_type: Mapped[Optional[str]]
    bios_version: Mapped[Optional[str]]
    cpu: Mapped[Optional[str]]
    ram_gb: Mapped[Optional[float]]
    operating_system: Mapped[Optional[str]]
    os_installation_date: Mapped[Optional[datetime]]
    activity_time: Mapped[Optional[str]]
    last_user: Mapped[Optional[str]]
    battery_health: Mapped[Optional[str]]
    antivirus: Mapped[Optional[str]]
    local_admins: Mapped[Optional[str]]
    reboot_pending: Mapped[Optional[str]] 
    last_verification: Mapped[datetime]

    # Relationships (Explicit back_populates is the 2.x standard over backref)
    monitors: Mapped[List["Monitor"]] = relationship(back_populates="computer", cascade="all, delete-orphan")
    networks: Mapped[List["Network"]] = relationship(back_populates="computer", cascade="all, delete-orphan")
    disks: Mapped[List["Disk"]] = relationship(back_populates="computer", cascade="all, delete-orphan")
    softwares: Mapped[List["Software"]] = relationship(back_populates="computer", cascade="all, delete-orphan")
    printers: Mapped[List["Printer"]] = relationship(back_populates="computer", cascade="all, delete-orphan")

class Monitor(Base):
    __tablename__ = "monitors"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    computer_id: Mapped[int] = mapped_column(ForeignKey("computers.id"))
    serial_num: Mapped[Optional[str]] 
    manufacturer: Mapped[Optional[str]]
    model: Mapped[Optional[str]]

    computer: Mapped["Computer"] = relationship(back_populates="monitors")

class Network(Base):
    __tablename__ = "networks"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    computer_id: Mapped[int] = mapped_column(ForeignKey("computers.id"))
    adapter_name: Mapped[Optional[str]]
    mac_address: Mapped[Optional[str]] = mapped_column(String(20))
    ip_address: Mapped[Optional[str]]

    computer: Mapped["Computer"] = relationship(back_populates="networks")

class Disk(Base):
    __tablename__ = "disks"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    computer_id: Mapped[int] = mapped_column(ForeignKey("computers.id"))
    drive: Mapped[Optional[str]] = mapped_column(String(5))
    size_gb: Mapped[Optional[float]]
    free_gb: Mapped[Optional[float]]

    computer: Mapped["Computer"] = relationship(back_populates="disks")

class Software(Base):
    __tablename__ = "softwares"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    computer_id: Mapped[int] = mapped_column(ForeignKey("computers.id"))
    software_name: Mapped[str]
    version: Mapped[Optional[str]]

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
    computer_id: Mapped[Optional[int]] 
    hostname: Mapped[str]
    execution_date: Mapped[datetime]
    status: Mapped[str] = mapped_column(String(20))
    error_msg: Mapped[Optional[str]] = mapped_column(Text)
    duration: Mapped[Optional[float]]