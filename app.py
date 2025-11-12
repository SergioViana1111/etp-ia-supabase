# app.py — Login Google via Supabase (hash -> query) para Streamlit (iframe-safe)
# Requisitos: pip install streamlit supabase requests

import os
from urllib.parse import quote
import requests
import streamlit as st
import streamlit.components.v1 as components
from supabase import create_client, Client

# =========================
# CONFIG
# =========================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8501")  # ex.: "https://etp-com-ia.streamlit.app/"

if not SUPABASE_URL or not SUPABASE_KEY:
    supabase: Client | None = None
else:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# =========================
# AUXILIARES
# =========================
def obter_user_supabase(access_token: str):
    if not access_token or not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {access_token}"}
        resp = requests.get(f"{SUPABASE_URL}/auth/v1/user", headers=headers, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        st.error(f"Falha na validação do token (Status: {resp.status_code}). Resposta: {resp.text[:140]}...")
    except Exception as e:
        st.error(f"Erro ao consultar Supabase Auth: {e}")
    return None

def sincronizar_usuario(user_json: dict):
    if user_json:
        return {
            "nome": user_json.get("user_metadata", {}).get("full_name") or user_json.get("email") or "Usuário",
            "email": user_json.get("email"),
        }
    return None

def gerar_google_auth_url():
    """
    Força retorno com #access_token (implicit) e redireciona para APP_BASE_URL.
    IMPORTANTE: APP_BASE_URL deve constar em Auth > URL Configuration > Redirect URLs no Supabase.
    """
    if not SUPABASE_URL:
        return "#"
    redirect_enc = quote(APP_BASE_URL, safe="")
    # response_type=token => retorno com fragment (#access_token)
    return (
        f"{SUPABASE_URL}/auth/v1/authorize"
        f"?provider=google"
        f"&redirect_to={redirect_enc}"
        f"&response_type=token"
    )

# =========================
# JS: mover #access_token -> ?access_token (na janela principal)
# =========================
def mover_access_token_do_hash_para_query():
    components.html(
        """
        <script>
        (function() {
          try {
            // Executa no topo, pois o Streamlit embute isto em um iframe
            var topWin = window.top || window;
            if (topWin.location.hash && topWin.location.hash.includes("access_token=")) {
              const params = new URLSearchParams(topWin.location.hash.substring(1));
              const access = params.get("access_token");
              const base = topWin.location.href.split('#')[0];
              if (access) {
                const url = new URL(base);
                url.searchParams.set("access_token", access);
                topWin.location.replace(url.toString()); // limpa o hash e recarrega o app
              }
            }
          } catch (e) { console.error("Hash->Query mover error:", e); }
        })();
        </script>
        """,
        height=0,
    )

# =========================
# UI
# =========================
def tela_login_google():
    st.title("Ferramenta Inteligente para Elaboração de ETP")
    st.subheader("Acesse com sua conta Google")

    auth_url = gerar_google_auth_url()

    col1, col2 = st.columns([1,1])
    with col1:
        if st.button("🔐 Entrar com Google"):
            # Redireciona a ABA (top window), não o iframe
            components.html(f"<script>window.top.location.href='{auth_url}';</script>", height=0)
            st.stop()

    with col2:
        st.link_button("Abrir login em nova aba", auth_url)

    st.caption("Após autenticar, você será redirecionado de volta para o app.")

# =========================
# MAIN
# =========================
def main():
    st.set_page_config(page_title="Ferramenta IA para ETP", layout="wide")

    # Injeta SEMPRE; só age quando a URL de retorno tiver #access_token
    mover_access_token_do_hash_para_query()

    # DEBUG
    st.write("--- DEBUG INFO ---")
    st.write(f"SUPABASE_URL está configurada: {'Sim' if SUPABASE_URL else 'NÃO'}")
    st.write(f"Sessão atual (usuario): {st.session_state.get('usuario', 'NENHUM')}")
    st.write("--------------------")

    if supabase is None:
        st.error("ERRO CRÍTICO: SUPABASE_URL / SUPABASE_KEY ausentes.")
        return

    # Sem sessão? tenta pegar token da query
    if "usuario" not in st.session_state:
        try:
            qp = st.query_params  # Streamlit novo
            access_token = qp.get("access_token", [None])
            access_token = access_token[0] if isinstance(access_token, list) else access_token
        except Exception:
            params = st.experimental_get_query_params()
            at = params.get("access_token")
            access_token = at[0] if at else None

        if access_token:
            st.write("Token encontrado na query. Validando...")
            user_json = obter_user_supabase(access_token)
            if user_json:
                usuario = sincronizar_usuario(user_json)
                if usuario:
                    st.session_state["usuario"] = usuario
                    st.session_state["access_token"] = access_token
                    # limpa a query pra evitar reprocesso em refresh
                    try:
                        st.query_params.clear()  # novo
                    except Exception:
                        st.experimental_set_query_params()
                    st.rerun()
                else:
                    st.error("Falha ao sincronizar usuário.")
            else:
                st.error("Token inválido/expirado no Supabase.")
        else:
            # sem token → mostrar login
            tela_login_google()
            return

    # Logado
    st.success("AUTENTICAÇÃO COMPLETA. BEM-VINDO!")
    usuario = st.session_state["usuario"]

    st.sidebar.header(f"Olá, {usuario.get('nome', 'Usuário')}")
    st.header("Dashboard de Elaboração de ETP")
    st.write("Conteúdo do seu app aqui…")

    if st.sidebar.button("Sair", help="Encerrar sessão"):
        st.session_state.clear()
        st.rerun()

if __name__ == "__main__":
    main()
