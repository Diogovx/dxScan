from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class MonitorSchema(BaseModel):
    manufacturer: str | None = Field(default=None, alias="Manufacturer")
    model: str | None = Field(default=None, alias="Model")
    serial_num: str | None = Field(default=None, alias="Serial")

class DiskSchema(BaseModel):
    drive: str | None = Field(default=None, alias="Drive")
    size_gb: float | None = Field(default=None, alias="Size_GB")
    free_gb: float | None = Field(default=None, alias="Free_GB")

class NetworkSchema(BaseModel):
    adapter_name: str | None = Field(default=None, alias="Name")
    mac_address: str | None = Field(default=None, alias="MAC")
    ip_address: str | None = Field(default=None, alias="IP")

class SoftwareSchema(BaseModel):
    software_name: str = Field(alias="Name")
    version: str | None = Field(default=None, alias="Version")

class SystemSchema(BaseModel):
    hostname: str = Field(alias="Hostname")
    serial_num: str = Field(alias="Serial_Number")
    manufacturer: str | None = Field(default=None, alias="Manufacturer")
    model: str | None = Field(default=None, alias="Model")
    equipment_type: str | None = Field(default=None, alias="Equipment_Type")
    bios_version: str | None = Field(default=None, alias="BIOS_Version")
    cpu: str | None = Field(default=None, alias="Processor")
    ram_gb: float | None = Field(default=None, alias="RAM_GB")
    operating_system: str | None = Field(default=None, alias="Operating_System")
    
    os_installation_date: str | None = Field(default=None, alias="OS_Installation_Date")
    
    activity_time: str | None = Field(default=None, alias="Uptime")
    last_user: str | None = Field(default=None, alias="Last_Logged_User")
    battery_health: str | None = Field(default=None, alias="Battery_Health")

class SecuritySchema(BaseModel):
    antivirus: str | None = Field(default=None, alias="Antivirus_Status")
    local_admins: str | None = Field(default=None, alias="Local_Admins")
    reboot_pending: str | None = Field(default=None, alias="Reboot_Pending")



class ScannerPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    verification_date: datetime = Field(alias="Verification_Date")
    
    system: SystemSchema = Field(alias="System")
    security: SecuritySchema = Field(alias="Security")
    
    monitors: list[MonitorSchema] | MonitorSchema | None = Field(default=[], alias="Monitors")
    disks: list[DiskSchema] | DiskSchema | None = Field(default=[], alias="Disks")
    networks: list[NetworkSchema] | NetworkSchema | None = Field(default=[], alias="Network")
    softwares: list[SoftwareSchema] | SoftwareSchema | None = Field(default=[], alias="Softwares")