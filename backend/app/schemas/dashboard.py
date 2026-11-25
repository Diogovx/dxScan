from datetime import datetime
from typing import Literal

from pydantic import BaseModel

AntivirusState = Literal["ativo", "parado", "nao_instalado", "desconhecido"]

# Codes the frontend maps to labels; keep them stable (the AI tools will reuse them).
AlertCode = Literal[
    "sem_contato",      # not seen for more than stale_days
    "antivirus",        # antivirus stopped or not installed
    "reboot_pendente",  # Windows reports a pending reboot
    "disco_critico",    # system drive below disk_critical_pct free
    "bateria_fraca",    # battery health below battery_replace_pct
    "admins_extras",    # local Administrators beyond the default ones
]


class DashboardThresholds(BaseModel):
    recent_days: int
    stale_days: int
    disk_critical_pct: float
    battery_replace_pct: int


class MachineHealth(BaseModel):
    serial_num: str
    hostname: str
    manufacturer: str | None = None
    model: str | None = None
    equipment_type: str | None = None
    operating_system: str | None = None
    ram_gb: float | None = None
    last_user: str | None = None
    last_verification: datetime | None = None
    days_since_seen: int | None = None
    system_disk_size_gb: float | None = None
    system_disk_free_gb: float | None = None
    system_disk_free_pct: float | None = None
    battery_health_pct: int | None = None
    antivirus_status: str | None = None
    antivirus_state: AntivirusState = "desconhecido"
    reboot_pending: bool | None = None
    extra_local_admins: int | None = None
    software_count: int = 0
    alerts: list[AlertCode] = []


class SoftwareCount(BaseModel):
    software_name: str
    installs: int


class DashboardResponse(BaseModel):
    generated_at: datetime
    thresholds: DashboardThresholds
    machines: list[MachineHealth]
    top_software: list[SoftwareCount]
