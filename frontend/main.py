import os

import pandas as pd
import requests
import streamlit as st

import dashboard

st.set_page_config(page_title="dxScan", page_icon="🛡️", layout="wide")

API_URL = os.getenv("API_URL","http://localhost:8000/api/v1/inventory/")
AUTH_URL = os.getenv("AUTH_URL", "http://localhost:8000/api/v1/auth/")
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://localhost:8000/api/v1/dashboard/")


class SessionExpired(Exception):
    pass


def logout():
    st.session_state.pop("auth", None)
    st.cache_data.clear()


def login_screen():
    st.title("dxScan")
    st.caption("Entre com seu usuário do Active Directory (OU TI).")
    with st.form("login"):
        username = st.text_input("Usuário", placeholder="nome.sobrenome")
        password = st.text_input("Senha", type="password")
        submitted = st.form_submit_button("Entrar", use_container_width=True)
    if submitted:
        try:
            response = requests.post(f"{AUTH_URL}login", data={"username": username, "password": password}, timeout=15)
        except requests.RequestException:
            st.error("Não foi possível contatar a API.")
            return
        if response.status_code == 200:
            st.session_state["auth"] = response.json()
            st.rerun()
        elif response.status_code == 503:
            st.error("Active Directory indisponível no momento. Tente novamente.")
        else:
            st.error("Usuário ou senha inválidos, ou usuário sem permissão de acesso.")


def _get(url, token, params=None):
    response = requests.get(url, headers={"Authorization": f"Bearer {token}"}, params=params, timeout=30)
    if response.status_code == 401:
        raise SessionExpired()
    return response

# The token is a parameter so the cache is per user session (and dropped on logout).
@st.cache_data(ttl=60)
def fetch_all_computers(token):
    try:
        response = _get(API_URL, token)
        return response.json() if response.status_code == 200 else []
    except requests.RequestException:
        return []

@st.cache_data(ttl=60)
def fetch_computer_detail(serial, token):
    try:
        response = _get(f"{API_URL}{serial}", token)
        return response.json() if response.status_code == 200 else None
    except requests.RequestException:
        return None

@st.cache_data(ttl=60)
def fetch_dashboard(token, operating_systems, manufacturers, equipment_types, hide_runtimes):
    """Filters are tuples so the cache key is hashable; the backend applies them in SQL."""
    params = {
        "operating_system": list(operating_systems),
        "manufacturer": list(manufacturers),
        "equipment_type": list(equipment_types),
        "hide_runtimes": str(hide_runtimes).lower(),
    }
    try:
        response = _get(DASHBOARD_URL, token, params=params)
        return response.json() if response.status_code == 200 else None
    except requests.RequestException:
        return None


if "auth" not in st.session_state:
    login_screen()
    st.stop()

TOKEN = st.session_state["auth"]["access_token"]
CURRENT_USER = st.session_state["auth"]["user"]


def get_detail(serial):
    try:
        return fetch_computer_detail(serial, TOKEN)
    except SessionExpired:
        logout()
        st.rerun()

st.sidebar.title("Controle dxScan")
st.sidebar.caption(f"👤 {CURRENT_USER.get('display_name') or CURRENT_USER['username']}")
if st.sidebar.button("Sair"):
    logout()
    st.rerun()
page = st.sidebar.radio("Ir para:", ["Dashboard Geral", "Inventário Detalhado", "Gestão de Software"])

try:
    data = fetch_all_computers(TOKEN)
except SessionExpired:
    logout()
    st.warning("Sua sessão expirou. Entre novamente.")
    st.rerun()
df_raw = pd.DataFrame(data)

if not df_raw.empty:
    st.sidebar.divider()
    st.sidebar.subheader("🔍 Filtros Globais")
    
    f_os = st.sidebar.multiselect("Sistema Operacional", df_raw["operating_system"].dropna().unique())
    f_man = st.sidebar.multiselect("Fabricante", df_raw["manufacturer"].dropna().unique())

    df_filtered = df_raw.copy()
    if f_os:
        df_filtered = df_filtered[df_filtered["operating_system"].isin(f_os)]
    if f_man:
        df_filtered = df_filtered[df_filtered["manufacturer"].isin(f_man)]
else:
    df_filtered = df_raw
    f_os, f_man = [], []

if page == "Dashboard Geral":
    st.title("Visão Geral da Frota")
    equipment_types, hide_runtimes = dashboard.controls()
    try:
        dash_data = fetch_dashboard(TOKEN, tuple(f_os), tuple(f_man), tuple(equipment_types), hide_runtimes)
    except SessionExpired:
        logout()
        st.rerun()
    if dash_data is None:
        st.error("Não foi possível carregar os dados do dashboard.")
    else:
        dashboard.render(dash_data)

elif page == "Inventário Detalhado":
    st.title("Gerenciamento de Ativos")
    
    tab_simple, tab_full = st.tabs(["Visualização Simples", "Raio-X da Máquina"])

    with tab_simple:
        st.subheader("Lista de Dispositivos")
        view_cols = ["hostname", "serial_num", "operating_system", "ram_gb", "last_verification"]
        st.dataframe(df_filtered[view_cols], use_container_width=True, hide_index=True)

    with tab_full:
        selected_serial = st.selectbox("Selecione um computador para ver o Raio-X:", 
                                     options=df_filtered["serial_num"].tolist(),
                                     format_func=lambda x: f"{df_filtered[df_filtered['serial_num']==x]['hostname'].values[0]} ({x})")
        
        if selected_serial:
            detail = get_detail(selected_serial)
            if detail:
                d1, d2, d3 = st.columns(3)
                with d1:
                    st.info("**Hardware**")
                    st.write(f"**Modelo:** {detail['model']}")
                    st.write(f"**BIOS:** {detail['bios_version']}")
                    st.write(f"**CPU:** {detail['cpu']}")
                with d2:
                    st.success("**Segurança**")
                    st.write(f"**Antivírus:** {detail['antivirus']}")
                    st.write(f"**Reboot Pendente:** {detail['reboot_pending']}")
                    st.write(f"**Admins:** {detail['local_admins']}")
                with d3:
                    st.warning("**Status**")
                    st.write(f"**Uptime:** {detail['activity_time']}")
                    st.write(f"**Bateria:** {detail['battery_health']}")
                    st.write(f"**Último Usuário:** {detail['last_user']}")

                st.subheader("Armazenamento & Redes")
                r1, r2 = st.columns(2)
                with r1:
                    st.write("**Discos Lógicos**")
                    st.table(detail['disks'])
                with r2:
                    st.write("**Interfaces de Rede**")
                    st.table(detail['networks'])

elif page == "Gestão de Software":
    st.title("Inventário de Softwares")
    
    selected_pc = st.selectbox("Ver softwares instalados em:", 
                               options=df_filtered["serial_num"].tolist(),
                               format_func=lambda x: f"{df_filtered[df_filtered['serial_num']==x]['hostname'].values[0]} ({x})")
    
    if selected_pc:
        detail = get_detail(selected_pc)
        if detail and detail['softwares']:
            df_sw = pd.DataFrame(detail['softwares'])
            
            search_sw = st.text_input("Buscar software específico nesta máquina:")
            if search_sw:
                df_sw = df_sw[df_sw["software_name"].str.contains(search_sw, case=False)]
            
            st.write(f"Encontrados **{len(df_sw)}** programas instalados.")
            
            # Toggle Simples/Completo
            
            
            st.dataframe(df_sw, use_container_width=True, hide_index=True)
            
        else:
            st.warning("Nenhum software catalogado para esta máquina.")

st.sidebar.markdown("---")
st.sidebar.caption("dxScan v2.1 • Diogo Xavier")