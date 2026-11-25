import os
import streamlit as st
import requests
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="dxScan", page_icon="🛡️", layout="wide")

API_URL = os.getenv("API_URL","http://localhost:8000/api/v1/inventory/")
AUTH_URL = os.getenv("AUTH_URL", "http://localhost:8000/api/v1/auth/")


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


def _get(url, token):
    response = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
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
    
    f_os = st.sidebar.multiselect("Sistema Operacional", df_raw["operating_system"].unique())
    f_man = st.sidebar.multiselect("Fabricante", df_raw["manufacturer"].unique())

    df_filtered = df_raw.copy()
    if f_os:
        df_filtered = df_filtered[df_filtered["operating_system"].isin(f_os)]
    if f_man:
        df_filtered = df_filtered[df_filtered["manufacturer"].isin(f_man)]
else:
    df_filtered = df_raw

if page == "Dashboard Geral":
    st.title("Fleet Analytics")
    
    if df_filtered.empty:
        st.info("Aguardando dados...")
    else:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Máquinas", len(df_filtered))
        m2.metric("Fabricantes", df_filtered["manufacturer"].nunique())
        m3.metric("Média RAM", f"{df_filtered['ram_gb'].mean():.1f} GB")
        m4.metric("S.O. Diferentes", df_filtered["operating_system"].nunique())

        st.divider()

        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Sistemas Operacionais")
            fig_os = px.pie(df_filtered, names="operating_system", hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
            st.plotly_chart(fig_os, use_container_width=True)
        
        with c2:
            st.subheader("Distribuição por Fabricante")
            fig_man = px.bar(df_filtered.groupby("manufacturer").size().reset_index(name='count'), 
                            x="manufacturer", y="count", color="manufacturer")
            st.plotly_chart(fig_man, use_container_width=True)

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