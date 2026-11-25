"""Página "Visão Geral" do dashboard: indicadores, máquinas que precisam de atenção e gráficos da frota.

Os dados vêm prontos de GET /api/v1/dashboard/ (valores já normalizados e alertas já calculados no
backend); aqui só há apresentação.
"""
import pandas as pd
import plotly.express as px
import streamlit as st

OK = "#2E7D32"
INFO = "#0288D1"
WARN = "#F9A825"
CRIT = "#C62828"
MUTED = "#9E9E9E"
EQUIPMENT_COLORS = {"Notebook": "#5E35B1", "Desktop": "#00897B", "Desconhecido": MUTED}

ALERT_LABELS = {
    "sem_contato": "Sem contato",
    "antivirus": "Antivírus com problema",
    "reboot_pendente": "Reboot pendente",
    "disco_critico": "Disco crítico",
    "bateria_fraca": "Bateria fraca",
    "admins_extras": "Admins extras",
}

FRESHNESS_ORDER = ["Hoje", "1–7 dias", "8–30 dias", "> 30 dias", "Nunca"]
FRESHNESS_COLORS = dict(zip(FRESHNESS_ORDER, [OK, INFO, WARN, CRIT, MUTED], strict=True))
RAM_ORDER = ["< 8 GB", "8 GB", "16 GB", "32 GB+"]


def controls() -> tuple[list[str], bool]:
    """Filtros próprios desta página (o tipo de equipamento não existe na rota de lista)."""
    c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
    with c1:
        equipment = st.segmented_control(
            "Tipo de equipamento", ["Notebook", "Desktop"], selection_mode="multi", key="dash_equipment",
        )
    with c2:
        hide_runtimes = st.toggle("Ocultar runtimes no ranking", value=True, key="dash_hide_runtimes",
                                  help="Esconde Visual C++, .NET e atualizações do ranking de softwares.")
    return list(equipment or []), hide_runtimes


def render(data: dict) -> None:
    machines = pd.DataFrame(data.get("machines", []))
    if machines.empty:
        st.info("Nenhuma máquina encontrada com os filtros atuais.")
        return

    th = data["thresholds"]
    df = _prepare(machines)
    generated = pd.to_datetime(data["generated_at"]).strftime("%d/%m/%Y %H:%M")
    st.caption(f"Dados de {len(df)} máquinas • gerado em {generated}")

    _kpis(df, th)
    st.divider()
    _attention_table(df)
    st.divider()

    c1, c2 = st.columns(2)
    with c1:
        _chart_freshness(df, th)
    with c2:
        _chart_os(df)

    c3, c4 = st.columns(2)
    with c3:
        _chart_disk(df, th)
    with c4:
        _chart_battery(df, th)

    c5, c6 = st.columns(2)
    with c5:
        _chart_ram(df)
    with c6:
        _chart_models(df)

    _chart_software(pd.DataFrame(data.get("top_software", [])), total=len(df))


# --- preparação ---

def _prepare(machines: pd.DataFrame) -> pd.DataFrame:
    df = machines.copy()
    df["equipment_type"] = df["equipment_type"].fillna("Desconhecido")
    df["os_label"] = df["operating_system"].fillna("Desconhecido").str.replace("Microsoft ", "", regex=False)
    df["freshness"] = df["days_since_seen"].apply(_freshness_bucket)
    df["ram_bucket"] = df["ram_gb"].apply(_ram_bucket)
    df["n_alerts"] = df["alerts"].apply(len)
    df["alert_labels"] = df["alerts"].apply(lambda codes: ", ".join(ALERT_LABELS.get(c, c) for c in codes))
    df["last_verification"] = pd.to_datetime(df["last_verification"], errors="coerce")
    return df


def _freshness_bucket(days) -> str:
    if days is None or pd.isna(days):
        return "Nunca"
    if days == 0:
        return "Hoje"
    if days <= 7:
        return "1–7 dias"
    if days <= 30:
        return "8–30 dias"
    return "> 30 dias"


def _ram_bucket(gb) -> str | None:
    if gb is None or pd.isna(gb):
        return None
    if gb < 7.5:
        return "< 8 GB"
    if gb < 15:
        return "8 GB"
    if gb < 31:
        return "16 GB"
    return "32 GB+"


def _count_alert(df: pd.DataFrame, code: str) -> int:
    return int(df["alerts"].apply(lambda codes: code in codes).sum())


def _style(fig, height: int = 330):
    fig.update_layout(
        height=height,
        margin={"l": 10, "r": 10, "t": 10, "b": 10},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0, "title": None},
        bargap=0.15,
    )
    return fig


# --- seções ---

def _kpis(df: pd.DataFrame, th: dict) -> None:
    total = len(df)
    recent = int((df["days_since_seen"].fillna(10**6) <= th["recent_days"]).sum())
    stale = _count_alert(df, "sem_contato")
    with_alerts = int((df["n_alerts"] > 0).sum())

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Máquinas", total, border=True)
    k2.metric(f"Vistas em {th['recent_days']} dias", f"{recent / total:.0%}", border=True,
              help=f"{recent} de {total} máquinas enviaram inventário recentemente. "
                   "É a confiabilidade do inventário automático na conferência com o Snipe-IT.")
    k3.metric(f"Sem contato > {th['stale_days']} dias", stale, border=True,
              help="Desligadas, fora da rede, formatadas ou desaparecidas: conferir no Snipe-IT.")
    k4.metric("Com algum alerta", with_alerts, border=True)

    a1, a2, a3, a4, a5 = st.columns(5)
    a1.metric("Antivírus com problema", _count_alert(df, "antivirus"), border=True,
              help="Antivírus parado ou não instalado.")
    a2.metric("Reboot pendente", _count_alert(df, "reboot_pendente"), border=True,
              help="Atualizações aguardando reinicialização.")
    a3.metric("Disco C: crítico", _count_alert(df, "disco_critico"), border=True,
              help=f"Menos de {th['disk_critical_pct']:.0f}% livre no disco do sistema.")
    a4.metric("Bateria fraca", _count_alert(df, "bateria_fraca"), border=True,
              help=f"Saúde abaixo de {th['battery_replace_pct']}% da capacidade original: candidata a troca.")
    a5.metric("Admins extras", _count_alert(df, "admins_extras"), border=True,
              help="Contas além das padrão no grupo Administradores local.")


def _attention_table(df: pd.DataFrame) -> None:
    st.subheader("Precisa de atenção")
    flagged = df[df["n_alerts"] > 0]
    if flagged.empty:
        st.success("Nenhuma máquina com alerta nos filtros atuais.")
        return

    present = [code for code in ALERT_LABELS if _count_alert(flagged, code)]
    chosen = st.multiselect("Filtrar por alerta", present, format_func=ALERT_LABELS.get, key="dash_alert_filter")
    if chosen:
        flagged = flagged[flagged["alerts"].apply(lambda codes: any(c in codes for c in chosen))]

    flagged = flagged.sort_values(["n_alerts", "days_since_seen"], ascending=[False, False])
    st.dataframe(
        flagged,
        hide_index=True,
        column_order=["hostname", "serial_num", "last_user", "alert_labels", "days_since_seen",
                      "system_disk_free_pct", "battery_health_pct", "antivirus_status", "last_verification"],
        column_config={
            "hostname": "Hostname",
            "serial_num": "Serial",
            "last_user": "Último usuário",
            "alert_labels": st.column_config.TextColumn("Alertas", width="large"),
            "days_since_seen": st.column_config.NumberColumn("Visto há (dias)"),
            "system_disk_free_pct": st.column_config.ProgressColumn(
                "Disco C: livre", format="%.0f%%", min_value=0, max_value=100),
            "battery_health_pct": st.column_config.ProgressColumn(
                "Bateria", format="%d%%", min_value=0, max_value=100),
            "antivirus_status": "Antivírus",
            "last_verification": st.column_config.DatetimeColumn("Última coleta", format="DD/MM/YYYY HH:mm"),
        },
    )


def _chart_freshness(df: pd.DataFrame, th: dict) -> None:
    st.subheader("Última comunicação")
    st.caption("Há quanto tempo cada máquina enviou inventário. Muitas em vermelho = inventário desatualizado.")
    counts = df["freshness"].value_counts().reindex(FRESHNESS_ORDER, fill_value=0).reset_index()
    counts.columns = ["faixa", "maquinas"]
    fig = px.bar(counts, x="faixa", y="maquinas", color="faixa", color_discrete_map=FRESHNESS_COLORS,
                 text="maquinas", labels={"faixa": "", "maquinas": "Máquinas"})
    fig.update_traces(textposition="outside", hovertemplate="%{x}: %{y} máquinas<extra></extra>")
    st.plotly_chart(_style(fig).update_layout(showlegend=False), key="chart_freshness")


def _chart_os(df: pd.DataFrame) -> None:
    st.subheader("Sistemas operacionais")
    st.caption("Edições do Windows na frota, por tipo de equipamento.")
    counts = df.groupby(["os_label", "equipment_type"]).size().reset_index(name="maquinas")
    fig = px.bar(counts, x="maquinas", y="os_label", color="equipment_type", orientation="h",
                 color_discrete_map=EQUIPMENT_COLORS, labels={"os_label": "", "maquinas": "Máquinas"})
    fig.update_yaxes(categoryorder="total ascending")
    fig.update_traces(hovertemplate="%{y}: %{x} máquinas<extra>%{fullData.name}</extra>")
    st.plotly_chart(_style(fig), key="chart_os")


def _threshold_histogram(df: pd.DataFrame, column: str, threshold: float, label: str, key: str) -> None:
    values = df[[column]].dropna()
    if values.empty:
        st.info("Sem leituras nos filtros atuais.")
        return
    values["faixa"] = values[column].apply(lambda v: "Abaixo do limite" if v < threshold else "OK")
    fig = px.histogram(values, x=column, color="faixa", nbins=20, range_x=[0, 100],
                       color_discrete_map={"OK": OK, "Abaixo do limite": CRIT},
                       category_orders={"faixa": ["Abaixo do limite", "OK"]},
                       labels={column: label, "count": "Máquinas"})
    fig.add_vline(x=threshold, line_dash="dash", line_color=CRIT,
                  annotation_text=f"limite {threshold:.0f}%", annotation_position="top")
    fig.update_layout(yaxis_title="Máquinas")
    st.plotly_chart(_style(fig), key=key)


def _chart_disk(df: pd.DataFrame, th: dict) -> None:
    st.subheader("Espaço livre no disco do sistema")
    st.caption("Distribuição do % livre no C:. À esquerda da linha, risco de falha em atualizações.")
    _threshold_histogram(df, "system_disk_free_pct", th["disk_critical_pct"], "% livre no C:", "chart_disk")


def _chart_battery(df: pd.DataFrame, th: dict) -> None:
    st.subheader("Saúde da bateria (notebooks)")
    notebooks = df[df["equipment_type"] == "Notebook"]
    missing = int(notebooks["battery_health_pct"].isna().sum())
    caption = "Capacidade atual em relação à original. À esquerda da linha, candidata a troca."
    if missing:
        caption += f" {missing} notebook(s) sem leitura de saúde."
    st.caption(caption)
    _threshold_histogram(notebooks, "battery_health_pct", th["battery_replace_pct"], "% da capacidade original",
                         "chart_battery")


def _chart_ram(df: pd.DataFrame) -> None:
    st.subheader("Memória RAM")
    st.caption("Faixas de RAM por tipo de equipamento. Abaixo de 8 GB costuma limitar o Windows 11.")
    counts = df.dropna(subset=["ram_bucket"]).groupby(["ram_bucket", "equipment_type"]).size().reset_index(name="maquinas")
    fig = px.bar(counts, x="ram_bucket", y="maquinas", color="equipment_type", color_discrete_map=EQUIPMENT_COLORS,
                 category_orders={"ram_bucket": RAM_ORDER}, labels={"ram_bucket": "", "maquinas": "Máquinas"})
    fig.update_traces(hovertemplate="%{x}: %{y} máquinas<extra>%{fullData.name}</extra>")
    st.plotly_chart(_style(fig), key="chart_ram")


def _chart_models(df: pd.DataFrame) -> None:
    st.subheader("Fabricantes e modelos")
    st.caption("Clique num fabricante para abrir os modelos; clique no topo para voltar.")
    tree = df[["manufacturer", "model"]].fillna("Desconhecido")
    fig = px.treemap(tree, path=[px.Constant("Frota"), "manufacturer", "model"], color="manufacturer",
                     color_discrete_sequence=px.colors.qualitative.Set2)
    fig.update_traces(root_color="rgba(0,0,0,0)", textinfo="label+value",
                      hovertemplate="%{label}<br>%{value} máquinas<extra></extra>")
    st.plotly_chart(_style(fig), key="chart_models")


def _chart_software(top: pd.DataFrame, total: int) -> None:
    st.subheader("Softwares mais instalados")
    if top.empty:
        st.info("Nenhum software catalogado nos filtros atuais.")
        return
    st.caption("Em quantas máquinas cada software aparece. Útil para licenças e padronização.")
    top = top.assign(pct=top["installs"] / total * 100)
    fig = px.bar(top, x="installs", y="software_name", orientation="h", custom_data=["pct"],
                 labels={"software_name": "", "installs": "Máquinas"}, color_discrete_sequence=[INFO])
    fig.update_yaxes(categoryorder="total ascending")
    fig.update_traces(hovertemplate="%{y}<br>%{x} máquinas (%{customdata[0]:.0f}% da frota)<extra></extra>")
    st.plotly_chart(_style(fig, height=max(330, 26 * len(top))), key="chart_software")
