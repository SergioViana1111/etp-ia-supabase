# streamlit_app.py
import os
from datetime import datetime
from urllib.parse import quote
import requests
import streamlit as st
from supabase import create_client, Client
import streamlit.components.v1 as components

# ================================
# CONFIG
# ================================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
APP_BASE_URL = os.getenv("APP_BASE_URL")  # ex.: https://etp-com-ia.streamlit.app

if SUPABASE_URL and SUPABASE_KEY:
    supabase: Client | None = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    supabase = None

def dbg(msg: str):
    st.write(f"[{datetime.utcnow().isoformat()}Z] {msg}")

# ================================
# AUTH HELPERS
# ================================
def gerar_google_auth_url():
    """
    Força fluxo implícito (hash com access_token) para evitar troca de código (PKCE).
    IMPORTANTE: nas Redirect URLs do Supabase, cadastre COM e SEM barra final.
    """
    if not SUPABASE_URL:
        return "#"
    redirect = (APP_BASE_URL or "http://localhost:8501").rstrip("/")
    redirect_enc = quote(redirect, safe="")
    # flow_type=implicit é o ponto crítico aqui
    return (
        f"{SUPABASE_URL}/auth/v1/authorize"
        f"?provider=google"
        f"&redirect_to={redirect_enc}"
        f"&flow_type=implicit"
    )

def obter_user_supabase(access_token: str):
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
            st.code(resp.text[:800], language="json")
        except Exception:
            pass
        return None
    except Exception as e:
        st.error(f"Erro inesperado ao consultar Supabase Auth API: {e}")
        return None

def sincronizar_usuario(user_json: dict):
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
        res = supabase.table("usuarios").upsert(payload, on_conflict="email").execute()
        if res.data and len(res.data) > 0:
            return res.data[0]
        return payload
    except Exception as e:
        st.error(f"Erro ao sincronizar usuário na tabela 'usuarios': {e}")
        return None

# ================================
# JS HELPERS (OAuth Hash -> Query)
# ================================
def banner_debug_oauth():
    components.html(
        """
        <div id="oauth-debug-banner"
             style="position:fixed;z-index:9999;top:8px;right:8px;padding:8px 12px;
                    border-radius:8px;background:#111;color:#fff;font:12px monospace;">
          Checando OAuth hash...
        </div>
        <script>
          (function () {
            try {
              var el = document.getElementById("oauth-debug-banner");
              var has = !!(window.location.hash && window.location.hash.includes("access_token="));
              el.textContent = has ? "OAuth: hash COM access_token" : "OAuth: hash SEM access_token";
            } catch (e) { console.error("Erro banner OAuth:", e); }
          })();
        </script>
        """,
        height=0,
    )

def mover_access_token_do_hash_para_query():
    components.html(
        """
        <script>
        (function () {
          try {
            var el = document.getElementById("oauth-debug-banner");
            if (window.location.hash && window.location.hash.includes("access_token=")) {
              const params = new URLSearchParams(window.location.hash.substring(1));
              const access = params.get("access_token");
              if (access) {
                if (el) el.textContent = "OAuth: hash COM token — movendo para query...";
                const url = new URL(window.location.href.split("#")[0]);
                if (!url.searchParams.get("access_token")) {
                  url.searchParams.set("access_token", access);
                }
                if (!url.searchParams.get("dashboard")) {
                  url.searchParams.set("dashboard", "1");
                }
                window.location.replace(url.toString());
              }
            } else {
              if (el) el.textContent = "OAuth: hash SEM access_token";
            }
          } catch (e) { console.error("Erro mover hash->query:", e); }
        })();
        </script>
        """,
        height=0,
    )

def limpar_access_token_da_url():
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
          } catch (e) { console.error("Erro limpar access_token:", e); }
        })();
        </script>
        """,
        height=0,
    )

def remover_params_da_url_no_logout():
    components.html(
        """
        <script>
        (function () {
          try {
            const url = new URL(window.location.href);
            ["dashboard","access_token"].forEach(p => url.searchParams.delete(p));
            window.history.replaceState({}, "", url.toString());
          } catch (e) { console.error("Erro logout URL clean:", e); }
        })();
        </script>
        """,
        height=0,
    )

# ================================
# UI
# ================================
def tela_login_google():
    st.title("Ferramenta Inteligente para Elaboração de ETP")
    st.subheader("Acesse com sua conta Google")

    auth_url = gerar_google_auth_url()

    # 1) Botão nativo (fora de iframe)
    try:
        st.link_button("🔐 Entrar com Google (link nativo)", auth_url, help="Fluxo Supabase/Google (implícito)")
    except Exception:
        pass

    # 2) Link de texto (clicável e copiável)
    st.write("Se o botão não navegar, use o link abaixo ou copie/cole no navegador:")
    st.write(f"[Abrir login Google (Supabase)]({auth_url})")

    # 3) URL crua para debug
    st.caption("URL de autenticação (debug):")
    st.code(auth_url, language="text")

def dashboard(usuario: dict):
    st.header("Dashboard de Elaboração de ETP")
    st.success("AUTENTICAÇÃO COMPLETA. BEM-VINDO!")
    st.json({
        "nome": usuario.get("nome"),
        "email": usuario.get("email"),
        "ultimo_login_utc": usuario.get("ultimo_login_utc"),
    })

# ================================
# APP
# ================================
def main():
    st.set_page_config(page_title="Ferramenta IA para ETP", layout="wide")

    st.write("-- DEBUG INFO ---")
    st.write(f"SUPABASE_URL está configurada: {'Sim' if os.getenv('SUPABASE_URL') else 'NÃO'}")
    st.write(f"APP_BASE_URL está configurada: {os.getenv('APP_BASE_URL')}")
    st.write(f"Sessão atual (usuario): {st.session_state.get('usuario', 'NENHUM')}")
    st.write("")

    if supabase is None:
        st.error("ERRO CRÍTICO: Configurações de Supabase ausentes.")
        return

    # 1) Banner e mover hash->query
    dbg("PASSO 1: Checando/movendo token da hash (#) para a query (se houver).")
    banner_debug_oauth()
    mover_access_token_do_hash_para_query()

    # 2) Ler query params
    dbg("PASSO 2: Lendo parâmetros de query.")
    params = st.experimental_get_query_params()
    access_token = params.get("access_token", [None])[0]
    if access_token:
        dbg("PASSO 2.1: access_token presente na query.")
    else:
        dbg("PASSO 2.1: nenhum access_token na query.")

    # 3) Se não tem sessão, tenta logar
    if "usuario" not in st.session_state:
        dbg("PASSO 3: Usuário não está na sessão. Iniciando checagem de login.")
        if access_token:
            dbg("PASSO 3.1: Validando token no Supabase.")
            user_json = obter_user_supabase(access_token)
            if user_json:
                dbg("PASSO 3.2: Token válido. Sincronizando usuário…")
                usuario = sincronizar_usuario(user_json)
                if usuario:
                    st.session_state["usuario"] = usuario
                    st.session_state["autenticado_em"] = datetime.utcnow().isoformat() + "Z"
                    dbg("PASSO 3.3: Sessão criada. Limpando access_token da URL.")
                    limpar_access_token_da_url()
                else:
                    st.error("ERRO: Falha ao sincronizar/criar registro em 'usuarios'.")
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

    # 4) Já está logado
    dbg("PASSO 4: Usuário está na sessão. Exibindo Dashboard.")
    usuario = st.session_state["usuario"]

    with st.sidebar:
        st.header(f"Olá, {usuario.get('nome','Usuário')}")
        st.caption(usuario.get("email", ""))
        st.divider()
        if st.button("Sair"):
            dbg("Logout solicitado. Limpando sessão e parâmetros.")
            st.session_state.clear()
            remover_params_da_url_no_logout()
            st.experimental_rerun()

    dashboard(usuario)

if __name__ == "__main__":
    main()
