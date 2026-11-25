"""Dashboard normalization (pure functions) and GET /api/v1/dashboard/. All data is fictitious."""
from datetime import datetime

import pytest

from app.core.security import create_access_token
from app.models.scanner_data import Computer, Disk
from app.repositories.dashboard import DashboardFilters, DashboardRepository
from app.schemas.auth import CurrentUser
from app.services import dashboard as svc

NOW = datetime(2026, 6, 15, 12, 0, 0)
DASHBOARD = "/api/v1/dashboard/"


def _mojibake(text: str) -> str:
    """Reproduces what Windows PowerShell 5.1 does to a UTF-8 (no BOM) script literal."""
    return text.encode("utf-8").decode("cp1252")


def _computer(**overrides) -> Computer:
    data = {
        "serial_num": "FAKE-SN-0001",
        "hostname": "PC-FICTICIO-01",
        "manufacturer": "Fabricante Exemplo",
        "model": "Modelo X",
        "equipment_type": "Notebook",
        "operating_system": "Microsoft Windows 11 Pro",
        "ram_gb": 16.0,
        "last_user": "usuario.ficticio",
        "battery_health": "85%",
        "antivirus": "Ativo",
        "local_admins": "Apenas Padrão",
        "reboot_pending": "Não",
        "last_verification": datetime(2026, 6, 14, 9, 0, 0),
    }
    data.update(overrides)
    disks = data.pop("disks", [Disk(drive="C:", size_gb=200.0, free_gb=100.0)])
    computer = Computer(**data)
    computer.disks = disks
    return computer


# --- repair_text ---

@pytest.mark.parametrize("original", ["Não", "Apenas Padrão", "Não Instalado", "Modelo Genérico"])
def test_repair_text_undoes_powershell_mojibake(original):
    assert svc.repair_text(_mojibake(original)) == original


@pytest.mark.parametrize("value", ["Não", "SÃO PAULO", "Ativo", "", None])
def test_repair_text_keeps_text_that_is_not_mojibake(value):
    assert svc.repair_text(value) == value


# --- parsers ---

@pytest.mark.parametrize("value,expected", [
    ("Ativo", "ativo"),
    ("Instalado, mas Parado!", "parado"),
    ("Não Instalado", "nao_instalado"),
    (_mojibake("Não Instalado"), "nao_instalado"),
    ("Instalado (Status oculto)", "desconhecido"),
    ("Erro ao verificar", "desconhecido"),
    (None, "desconhecido"),
])
def test_parse_antivirus(value, expected):
    assert svc.parse_antivirus(value) == expected


@pytest.mark.parametrize("value,expected", [
    ("Sim", True), ("Não", False), (_mojibake("Não"), False), ("", None), (None, None), ("talvez", None),
])
def test_parse_reboot_pending(value, expected):
    assert svc.parse_reboot_pending(value) is expected


@pytest.mark.parametrize("value,expected", [
    ("85%", 85), (" 59 % ", 59), ("130%", 100),
    ("40% (Carga Atual)", None),  # current charge, not health
    ("N/A (Desktop)", None), ("Falha ao ler dados ACPI", None), (None, None),
])
def test_parse_battery_pct(value, expected):
    assert svc.parse_battery_pct(value) == expected


@pytest.mark.parametrize("value,expected", [
    ("Apenas Padrão", 0), (_mojibake("Apenas Padrão"), 0),
    ("EXEMPLO\\usuario.a", 1), ("EXEMPLO\\usuario.a; EXEMPLO\\usuario.b", 2),
    ("Erro ao ler", None), (None, None),
])
def test_count_extra_admins(value, expected):
    assert svc.count_extra_admins(value) == expected


def test_system_disk_and_free_pct():
    disks = [Disk(drive="D:", size_gb=500.0, free_gb=10.0), Disk(drive="c:", size_gb=200.0, free_gb=15.0)]
    assert svc.free_pct(svc.system_disk(disks)) == 7.5
    assert svc.system_disk([Disk(drive="D:", size_gb=1.0, free_gb=1.0)]) is None
    assert svc.free_pct(Disk(drive="C:", size_gb=0.0, free_gb=0.0)) is None


def test_days_since_never_negative():
    assert svc.days_since(datetime(2026, 6, 1), NOW) == 14
    assert svc.days_since(datetime(2026, 7, 1), NOW) == 0  # scanner clock ahead of the server
    assert svc.days_since(None, NOW) is None


# --- alerts ---

def test_healthy_machine_has_no_alerts():
    assert svc.build_machine_health(_computer(), 10, NOW).alerts == []


@pytest.mark.parametrize("overrides,alert", [
    ({"last_verification": datetime(2026, 5, 1)}, "sem_contato"),
    ({"antivirus": "Instalado, mas Parado!"}, "antivirus"),
    ({"antivirus": "Não Instalado"}, "antivirus"),
    ({"reboot_pending": "Sim"}, "reboot_pendente"),
    ({"disks": [Disk(drive="C:", size_gb=200.0, free_gb=10.0)]}, "disco_critico"),
    ({"battery_health": "55%"}, "bateria_fraca"),
    ({"local_admins": "EXEMPLO\\usuario.a"}, "admins_extras"),
])
def test_each_problem_raises_its_alert(overrides, alert):
    assert svc.build_machine_health(_computer(**overrides), 10, NOW).alerts == [alert]


def test_boundaries_do_not_alert():
    machine = svc.build_machine_health(
        _computer(
            last_verification=datetime(2026, 5, 16, 12, 0, 0),           # exactly 30 days
            disks=[Disk(drive="C:", size_gb=100.0, free_gb=10.0)],       # exactly 10%
            battery_health="60%",                                        # exactly 60%
        ),
        0,
        NOW,
    )
    assert machine.alerts == []


def test_mojibake_fields_are_repaired_for_display():
    machine = svc.build_machine_health(_computer(model=_mojibake("Modelo Genérico")), 0, NOW)
    assert machine.model == "Modelo Genérico"


# --- route ---

@pytest.fixture
def token():
    return create_access_token(CurrentUser(username="ana.ti"))[0]


@pytest.fixture
def fake_repo(monkeypatch):
    calls = {}

    async def get_machines(self, filters):
        calls["filters"] = filters
        seen = datetime.now()  # the route uses the real clock
        return [
            (_computer(last_verification=seen), 42),
            (_computer(serial_num="FAKE-SN-0002", hostname="PC-FICTICIO-02", reboot_pending="Sim", last_verification=seen), 7),
        ]

    async def top_software(self, filters, limit, hide_runtimes):
        calls["top"] = (limit, hide_runtimes)
        return [("Programa Exemplo", 2)]

    monkeypatch.setattr(DashboardRepository, "get_machines", get_machines)
    monkeypatch.setattr(DashboardRepository, "top_software", top_software)
    return calls


def test_dashboard_requires_token(client):
    assert client.get(DASHBOARD).status_code == 401


def test_dashboard_returns_machines_alerts_and_ranking(client, token, fake_repo):
    response = client.get(DASHBOARD, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    body = response.json()
    assert body["thresholds"]["stale_days"] == svc.THRESHOLDS.stale_days
    assert [m["software_count"] for m in body["machines"]] == [42, 7]
    assert body["machines"][1]["alerts"] == ["reboot_pendente"]
    assert body["top_software"] == [{"software_name": "Programa Exemplo", "installs": 2}]
    assert fake_repo["filters"] == DashboardFilters()
    assert fake_repo["top"] == (15, True)


def test_dashboard_passes_filters(client, token, fake_repo):
    client.get(
        DASHBOARD,
        params={"operating_system": ["Windows 10", "Windows 11"], "equipment_type": "Notebook", "top": 5, "hide_runtimes": "false"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert fake_repo["filters"] == DashboardFilters(
        operating_systems=["Windows 10", "Windows 11"], equipment_types=["Notebook"],
    )
    assert fake_repo["top"] == (5, False)


def test_dashboard_rejects_invalid_top(client, token, fake_repo):
    assert client.get(DASHBOARD, params={"top": 0}, headers={"Authorization": f"Bearer {token}"}).status_code == 422
