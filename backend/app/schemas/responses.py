from pydantic import BaseModel, ConfigDict
from datetime import datetime

class ComputerListResponse(BaseModel):
    serial_num: str
    hostname: str
    manufacturer: str | None = None
    model: str | None = None
    operating_system: str | None = None
    ram_gb: float | None = None
    last_verification: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
    
class DiskResponse(BaseModel):
    drive: str
    size_gb: float
    free_gb: float
    model_config = ConfigDict(from_attributes=True)

class MonitorResponse(BaseModel):
    manufacturer: str
    model: str
    serial_num: str
    model_config = ConfigDict(from_attributes=True)

class NetworkResponse(BaseModel):
    adapter_name: str
    mac_address: str
    ip_address: str
    model_config = ConfigDict(from_attributes=True)

class SoftwareResponse(BaseModel):
    software_name: str
    version: str
    model_config = ConfigDict(from_attributes=True)

class ComputerDetailResponse(ComputerListResponse):
    equipment_type: str | None = None
    bios_version: str | None = None
    cpu: str | None = None
    os_installation_date: datetime | None = None
    activity_time: str | None = None
    last_user: str | None = None
    battery_health: str | None = None
    antivirus: str | None = None
    local_admins: str | None = None
    reboot_pending: str | None = None
    
    disks: list[DiskResponse] = []
    monitors: list[MonitorResponse] = []
    networks: list[NetworkResponse] = []
    softwares: list[SoftwareResponse] = []