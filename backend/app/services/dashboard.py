"""Turns the free-text values the PowerShell scanner sends into numbers, states and alerts.

Everything here is deterministic and pure (no DB, no clock unless passed in) so it is easy to test
and can be reused by the AI tools later.
"""
import re
from datetime import datetime

from app.models.scanner_data import Computer, Disk
from app.repositories.dashboard import DashboardFilters, DashboardRepository
from app.schemas.dashboard import (
    AlertCode,
    AntivirusState,
    DashboardResponse,
    DashboardThresholds,
    MachineHealth,
    SoftwareCount,
)

THRESHOLDS = DashboardThresholds(
    recent_days=7,
    stale_days=30,
    disk_critical_pct=10.0,
    battery_replace_pct=60,
)

SYSTEM_DRIVE = "C:"

# scanner.ps1 -> Get-SecurityInformation
_ANTIVIRUS_STATES: dict[str, AntivirusState] = {
    "ativo": "ativo",
    "instalado, mas parado!": "parado",
    "não instalado": "nao_instalado",
}
# scanner.ps1 -> Battery_Health is "87%" when the ACPI capacity could be read; anything else is not a health value.
_BATTERY_RE = re.compile(r"^\s*(\d{1,3})\s*%\s*$")
_NO_EXTRA_ADMINS = "apenas padrão"
_ADMINS_READ_ERROR = "erro ao ler"


def repair_text(value: str | None) -> str | None:
    """Undoes UTF-8 text that was decoded as Windows-1252 ("NÃ£o" -> "Não").

    scanner.ps1 saved as UTF-8 *without* BOM is read by Windows PowerShell 5.1 as ANSI, so every
    accented literal in the script reaches the API already garbled. Rows stored that way stay in the
    database until the machine is scanned again with a fixed script. Text that is not mojibake
    (it fails the round trip) is returned unchanged.
    """
    if not value or ("Ã" not in value and "Â" not in value):
        return value
    try:
        return value.encode("cp1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value


def parse_antivirus(value: str | None) -> AntivirusState:
    value = repair_text(value)
    if not value:
        return "desconhecido"
    return _ANTIVIRUS_STATES.get(value.strip().lower(), "desconhecido")


def parse_reboot_pending(value: str | None) -> bool | None:
    normalized = (repair_text(value) or "").strip().lower()
    if normalized == "sim":
        return True
    if normalized in ("não", "nao"):
        return False
    return None


def parse_battery_pct(value: str | None) -> int | None:
    match = _BATTERY_RE.match(value or "")
    if not match:
        return None
    return min(int(match.group(1)), 100)


def count_extra_admins(value: str | None) -> int | None:
    value = repair_text(value)
    if not value:
        return None
    normalized = value.strip().lower()
    if normalized == _NO_EXTRA_ADMINS:
        return 0
    if normalized == _ADMINS_READ_ERROR:
        return None
    return len([name for name in value.split(";") if name.strip()])


def system_disk(disks: list[Disk]) -> Disk | None:
    for disk in disks:
        if (disk.drive or "").strip().upper() == SYSTEM_DRIVE:
            return disk
    return None


def free_pct(disk: Disk | None) -> float | None:
    if disk is None or not disk.size_gb or disk.free_gb is None:
        return None
    return round(disk.free_gb / disk.size_gb * 100, 1)


def days_since(moment: datetime | None, now: datetime) -> int | None:
    if moment is None:
        return None
    # last_verification is the scanner's local time without a timezone; compare it as naive.
    return max((now.replace(tzinfo=None) - moment.replace(tzinfo=None)).days, 0)


def compute_alerts(machine: MachineHealth, thresholds: DashboardThresholds = THRESHOLDS) -> list[AlertCode]:
    alerts: list[AlertCode] = []
    if machine.days_since_seen is not None and machine.days_since_seen > thresholds.stale_days:
        alerts.append("sem_contato")
    if machine.antivirus_state in ("parado", "nao_instalado"):
        alerts.append("antivirus")
    if machine.reboot_pending:
        alerts.append("reboot_pendente")
    if machine.system_disk_free_pct is not None and machine.system_disk_free_pct < thresholds.disk_critical_pct:
        alerts.append("disco_critico")
    if machine.battery_health_pct is not None and machine.battery_health_pct < thresholds.battery_replace_pct:
        alerts.append("bateria_fraca")
    if machine.extra_local_admins:
        alerts.append("admins_extras")
    return alerts


def build_machine_health(computer: Computer, software_count: int, now: datetime) -> MachineHealth:
    disk = system_disk(computer.disks)
    machine = MachineHealth(
        serial_num=computer.serial_num,
        hostname=computer.hostname,
        manufacturer=repair_text(computer.manufacturer),
        model=repair_text(computer.model),
        equipment_type=repair_text(computer.equipment_type),
        operating_system=repair_text(computer.operating_system),
        ram_gb=computer.ram_gb,
        last_user=repair_text(computer.last_user),
        last_verification=computer.last_verification,
        days_since_seen=days_since(computer.last_verification, now),
        system_disk_size_gb=disk.size_gb if disk else None,
        system_disk_free_gb=disk.free_gb if disk else None,
        system_disk_free_pct=free_pct(disk),
        battery_health_pct=parse_battery_pct(computer.battery_health),
        antivirus_status=repair_text(computer.antivirus),
        antivirus_state=parse_antivirus(computer.antivirus),
        reboot_pending=parse_reboot_pending(computer.reboot_pending),
        extra_local_admins=count_extra_admins(computer.local_admins),
        software_count=software_count,
    )
    machine.alerts = compute_alerts(machine)
    return machine


class DashboardService:
    def __init__(self, repository: DashboardRepository):
        self.repository = repository

    async def build(
        self,
        filters: DashboardFilters,
        now: datetime,
        top: int = 15,
        hide_runtimes: bool = True,
    ) -> DashboardResponse:
        rows = await self.repository.get_machines(filters)
        software = await self.repository.top_software(filters, top, hide_runtimes)
        return DashboardResponse(
            generated_at=now,
            thresholds=THRESHOLDS,
            machines=[build_machine_health(computer, count, now) for computer, count in rows],
            top_software=[SoftwareCount(software_name=name, installs=installs) for name, installs in software],
        )
