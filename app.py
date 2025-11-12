# streamlit_app.py
import os
from datetime import datetime
from urllib.parse import quote

import requests
import streamlit as st
from supabase import create_client, Client
import streamlit.components.v1 as components

# =====================================================
# CONFIGURAÇÕES GERAIS / INTEGRAÇÕES
# =====================================================

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
APP_BASE_URL = os.getenv("APP_BASE_URL")  # ex: https://etp-com-ia.streamlit.app/

if SUPABASE_URL and SUPABASE_KEY:
    supabase: Client | None = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    supabase: Client | None = None

# =====================================================
# UTIL / DEBUG
# =====================================================
def dbg(msg: str):
    """Pequeno helper de debug com timestamp."""
    st.write(f"[{datetime.utcnow().isoformat()}Z] {msg}")

# =====================================================
# FUNÇÕES AUXILIARES DE AUTENTICAÇÃO E USUÁRIOS
# =====================================================

def gerar_google_auth_url():
    """Gera URL do OAuth do Supabase apontando de volta para o APP_BASE_URL."""
    if not SUPABASE_URL:
        return "#"
    redirect = APP_BASE_URL or "http://localhost:8501"
    redirect_enc = quote(redirect, safe="")
    return f"{SUPABASE_URL}/auth/v1/authorize?provider=google&redirect_to={redirect_enc}"

def obter_user_supabase(access_token: str):
    """Consulta o Supabase Auth para obter o usuário a partir do access_token."""
    if not access_token or not SUPABASE_URL or not SUPABASE_KEY:
        st.error("Erro: Parâmetros de Supabase ou token ausentes.")
        return None
    try:
        headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {access_token}"}
        resp = requests.get(f"{SUPABASE_URL}/auth/v1/user", headers=headers, timeout=15)
        if resp.status_code == 200:
            return resp.json()
        st.error(f"Falha na validação do token (Status: {resp.status_code}).")
        try:
            st.code(resp.text[:500], language="json")
        except Exception:
            pass
        return None
    except Exception as e:
        st.error(f"Erro inesperado ao consultar o Supabase Auth API: {e}")
        return None

def sincronizar_usuario(user_json: dict):
    """
    Exemplo simples: espelha o usuário do Auth em uma tabela 'usuarios'.
    Adapte campos conforme seu schema.
    """
    if not supabase:
        return None

    email = (
        user_json.get("email")
        or user_json.get("user_metadata", {}).get("email")
        or user_json.get("identities", [{}])[0].get("identity_data", {}).get("email")
    )
    nome = (
        user_json.get("user_metadata", {}).get("name")
        or user_json.get("user_metadata", {}).get("full_name")
        or (email.split("@")[0] if email else "Usuário")
    )

    payload = {
        "email": email,
        "nome": nome,
        "ultimo_login_utc": datetime.utcnow().isoformat() + "Z",
    }

    try:
        # upsert por email (ajuste 'on_conflict' ao seu schema)
        res = supabase.table("usuarios").upsert(payload, on_conflict="email").execute()
        # Retorna o registro salvo/atualizado
        if res.data and len(res.data) > 0:
            return res.data[0]
        # fallback: retorna payload mínimo
        return payload
    except Exception as e:
        st.error(f"Erro ao sincronizar usuário na tabela 'usuarios': {e}")
        return None

# =====================================================
# INJEÇÕES JS: mover token e limpar URL
# =====================================================

def mover_access_token_do_hash_para_query():
    """
    Se a URL tiver #access_token=..., move para ?access_token=... e recarrega SEM o hash.
    Evita usar localStorage (que causava colisão de keys nos components).
    """
    components.html(
        """
        <script>
        (function () {
          try {
            if (window.location.hash && window.location.hash.includes("access_token=")) {
              const params = new URLSearchParams(window.location.hash.substring(1));
              const access = params.get("access_token");
              if (access) {
                const url = new URL(window.location.href.split("#")[0]);
                if (!url.searchParams.get("access_token")) {
                  url.searchParams.set("access_token", access);
                }
                // opcional: marca dashboard=1 para rota "logada"
                if (!url.searchParams.get("dashboard")) {
                  url.searchParams.set("dashboard", "1");
                }
                window.location.replace(url.toString());
              }
            }
          } catch (e) {
            console.error("Erro ao mover token da hash para query:", e);
          }
        })();
        </script>
        """,
        height=0,
    )

def limpar_access_token_da_url():
    """
    Remove ?access_token=... da URL após a sessão estar estabelecida, mantendo ?dashboard=1.
    """
    components.html(
        """
        <script>
        (function () {
          try {
            const url = new URL(window.location.href);
            if (url.searchParams.has("access_token")) {
              url.searchParams.delete("access_token");
              window.history.replaceState({}, "", url.toString());
            }
          } catch (e) {
            console.error("Erro ao limpar access_token da URL:", e);
          }
        })();
        </script>
        """,
        height=0,
    )

def remover_dashboard_da_url():
    """
    Usado no logout: remove ?dashboard=1 (e também access_token se sobrou).
    """
    components.html(
        """
        <script>
        (function () {
          try {
            const url = new URL(window.location.href);
            if (url.searchParams.has("dashboard")) {
              url.searchParams.delete("dashboard");
            }
            if (url.searchParams.has("access_token")) {
              url.searchParams.delete("access_token");
            }
            window.history.replaceState({}, "", url.toString());
          } catch (e) {
            console.error("Erro ao limpar params da URL:", e);
          }
        })();
        </script>
        """,
        height=0,
    )

# =====================================================
# UI BÁSICA
# =====================================================

def tela_login_google():
    st.title("Ferramenta Inteligente para Elaboração de ETP")
    st.subheader("Acesse com sua conta Google")
    auth_url = gerar_google_auth_url()
    st.markdown(
        f'<a href="{auth_url}" target="_self"><button style="background-color:#4285F4; color:white; border:none; padding: 10px 20px; text-align: center; text-decoration: none; display: inline-block; font-size: 16px; margin: 4px 2px; cursor: pointer; border-radius: 4px;">🔐 Entrar com Google</button></a>',
        unsafe_allow_html=True
    )

def dashboard(usuario: dict):
    st.header("Dashboard de Elaboração de ETP")
    st.success("AUTENTICAÇÃO COMPLETA. BEM-VINDO!")
    st.write("Dados do usuário (resumo):")
    st.json({
        "nome": usuario.get("nome"),
        "email": usuario.get("email"),
        "ultimo_login_utc": usuario.get("ultimo_login_utc"),
    })

# =====================================================
# APP
# =====================================================

def main():
    # Configuração da página (chamar apenas uma vez)
    st.set_page_config(page_title="Ferramenta IA para ETP", layout="wide")

    # DEBUG HEADER
    st.write("--- DEBUG INFO ---")
    st.write(f"SUPABASE_URL está configurada: {'Sim' if os.getenv('SUPABASE_URL') else 'NÃO'}")
    st.write(f"APP_BASE_URL está configurada: {os.getenv('APP_BASE_URL')}")
    st.write(f"Sessão atual (usuario): {st.session_state.get('usuario', 'NENHUM')}")
    st.write("--------------------")

    if supabase is None:
        st.error("ERRO CRÍTICO: Configurações de Supabase ausentes.")
        return

    # 1) Converter #access_token=... -> ?access_token=...
    dbg("PASSO 1: Movendo token da hash (#) para a query (se houver).")
    mover_access_token_do_hash_para_query()

    # 2) Leitura dos parâmetros da query
    dbg("PASSO 2: Lendo parâmetros de query.")
    params = st.experimental_get_query_params()
    access_token = None
    if "access_token" in params and len(params["access_token"]) > 0:
        access_token = params["access_token"][0]
        dbg("PASSO 2.1: access_token presente na query.")
    else:
        dbg("PASSO 2.1: nenhum access_token na query.")

    # 3) Autenticação / Sessão
    if "usuario" not in st.session_state:
        dbg("PASSO 3: Usuário não está na sessão. Iniciando checagem de login.")
        if access_token:
            dbg("PASSO 3.1: Validando token no Supabase Auth API...")
            user_json = obter_user_supabase(access_token)
            if user_json:
                dbg("PASSO 3.2: Token válido. Sincronizando usuário na tabela 'usuarios'...")
                usuario = sincronizar_usuario(user_json)
                if usuario:
                    st.session_state["usuario"] = usuario
                    st.session_state["autenticado_em"] = datetime.utcnow().isoformat() + "Z"
                    dbg("PASSO 3.3: Sessão criada. Limpando access_token da URL e marcando dashboard=1.")
                    # marca dashboard=1 caso ainda não esteja
                    if params.get("dashboard", ["0"])[0] != "1":
                        st.experimental_set_query_params(dashboard="1")
                    # remove access_token da URL
                    limpar_access_token_da_url()
                else:
                    st.error("ERRO: Falha ao sincronizar/criar registro na tabela 'usuarios'.")
                    tela_login_google()
                    return
            else:
                st.error("ERRO: Falha na validação do token com a API Auth do Supabase.")
                tela_login_google()
                return
        else:
            dbg("PASSO 3.1: Sem token. Exibindo tela de login.")
            tela_login_google()
            return

    # 4) Usuário em sessão -> Dashboard
    dbg("PASSO 4: Usuário está na sessão. Exibindo Dashboard.")
    usuario = st.session_state["usuario"]

    # Sidebar com info e logout
    with st.sidebar:
        st.header(f"Olá, {usuario.get('nome','Usuário')}")
        st.caption(usuario.get("email", ""))
        st.divider()
        if st.button("Sair", help="Encerrar sessão"):
            dbg("Logout solicitado. Limpando sessão e parâmetros.")
            st.session_state.clear()
            remover_dashboard_da_url()
            st.experimental_rerun()

    # Conteúdo principal
    dashboard(usuario)

if __name__ == "__main__":
    main()
