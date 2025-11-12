# app.py — Streamlit + Supabase Auth (Google) com DEBUG detalhado
# ----------------------------------------------------------------
# Requisitos:
#   pip install streamlit requests supabase
#
# .streamlit/secrets.toml:
#   SUPABASE_URL = "https://SEU-PROJETO.supabase.co"
#   SUPABASE_KEY = "SUA_ANON_KEY"
#   APP_BASE_URL = "https://seu-app.streamlit.app/"  # com barra no final
#
# Google Cloud:
#   - Consent: Externo + Em produção
#   - Redirect URI do Client OAuth: https://SEU-PROJETO.supabase.co/auth/v1/callback
# Supabase → Auth → URL Configuration:
#   - Site URL: https://seu-app.streamlit.app/
#   - Additional Redirect URLs: https://seu-app.streamlit.app/ e http://localhost:8501/

import os
import json
import time
import requests
import streamlit as st
import streamlit.components.v1 as components
from urllib.parse import quote

# ------------------------ CONFIG BÁSICA ------------------------
st.set_page_config(page_title="Login Google • Supabase (DEBUG)", page_icon="🛠️", layout="wide")

SUPABASE_URL = st.secrets.get("SUPABASE_URL", os.getenv("SUPABASE_URL", ""))
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", os.getenv("SUPABASE_KEY", ""))

APP_BASE_URL = st.secrets.get("APP_BASE_URL", os.getenv("APP_BASE_URL", "http://localhost:8501/"))
if not APP_BASE_URL.endswith("/"):
    APP_BASE_URL += "/"

AUTH_AUTHORIZE = f"{SUPABASE_URL}/auth/v1/authorize" if SUPABASE_URL else ""
AUTH_USERINFO  = f"{SUPABASE_URL}/auth/v1/user"      if SUPABASE_URL else ""

# ------------------------ DEBUG HELPERS ------------------------
if "debug_log" not in st.session_state:
    st.session_state["debug_log"] = []

def log(msg, data=None):
    """Adiciona uma linha ao painel de debug."""
    ts = time.strftime("%H:%M:%S")
    item = {"t": ts, "msg": str(msg)}
    if data is not None:
        try:
            item["data"] = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False, indent=2)
        except Exception:
            item["data"] = str(data)
    st.session_state["debug_log"].append(item)

def debug_panel():
    with st.expander("🛠️ Painel de Depuração (passo a passo)", expanded=True):
        cols = st.columns(3)
        with cols[0]:
            st.caption("• Variáveis de ambiente")
            st.code(
                f"SUPABASE_URL: {SUPABASE_URL or '(vazio)'}\n"
                f"SUPABASE_KEY: {'(definida)' if SUPABASE_KEY else '(vazia)'}\n"
                f"APP_BASE_URL: {APP_BASE_URL}"
            )
        with cols[1]:
            st.caption("• Query params atuais")
            st.code(st.experimental_get_query_params())
        with cols[2]:
            st.caption("• Chaves da sessão")
            st.code(list(st.session_state.keys()))

        st.markdown("---")
        for i, row in enumerate(st.session_state["debug_log"], 1):
            st.write(f"**{i:02d}. [{row['t']}]** {row['msg']}")
            if "data" in row:
                st.code(row["data"])

# Mostra a URL atual (lado do cliente) e converte hash→query fora do iframe
def show_current_url_client():
    components.html(
        """
        <div id="__cururl__" style="font-family: monospace; font-size: 12px;"></div>
        <script>
          (function() {
            const el = document.getElementById("__cururl__");
            if (el) {
              el.textContent = "URL (navegador): " + window.location.href;
            }

            // 🔄 Se a URL contém #access_token=..., converte e abre fora do iframe
            if (window.location.href.includes('#access_token=')) {
              const params = new URLSearchParams(window.location.hash.substring(1));
              const url = window.location.origin + "?" + params.toString();
              console.log("Recarregando fora do iframe:", url);
              window.open(url, "_top");  // força abrir fora do sandbox
            }
          })();
        </script>
        """,
        height=30,
    )


# ------------------------ JS HELPERS ------------------------
def js_move_hash_to_query():
    """Converte #access_token=... em ?access_token=... (robusto no Streamlit Cloud via iframe)."""
    log("Executando js_move_hash_to_query()")
    components.html(
        """
        <iframe style="display:none" srcdoc="
        <script>
        (function() {
          function convert() {
            try {
              const hash = window.parent.location.hash;
              if (hash && hash.indexOf('access_token=') !== -1) {
                const params = new URLSearchParams(hash.substring(1));
                const url = new URL(window.parent.location.href);
                url.hash = '';
                url.search = params.toString();   // mantém todos os campos
                window.parent.location.replace(url.toString());
                return true;
              }
            } catch (e) { console.error('hash2query error:', e); }
            return false;
          }
          // tenta por 3s (30 tentativas) + no load
          var tries = 0;
          var iv = setInterval(function(){ if (convert() || ++tries > 30) clearInterval(iv); }, 100);
          window.addEventListener('load', convert);
        })();
        </script>
        "></iframe>
        """,
        height=150,
    )

def js_force_path(path: str):
    """Força o path (ex.: '/dashboard' ou '/'), sem reload (History API)."""
    log(f"Forçando path no navegador para: {path}")
    components.html(
        f"""
        <script>
        (function(){{
          try {{
            var desired = "{path}";
            var u = new URL(window.location.href);
            if (u.pathname !== desired) {{
              u.pathname = desired;
              u.search = "";
              window.history.replaceState(null, "", u.toString());
            }}
          }} catch(e) {{ console.error(e); }}
        }})();
        </script>
        """,
        height=1,
    )

# ------------------------ FUNÇÕES AUTH ------------------------
def login_url_google():
    """URL de login do Supabase/Google com redirect na RAIZ do app."""
    if not SUPABASE_URL:
        log("SUPABASE_URL não definido — não é possível gerar login_url")
        return "#"
    redirect_to = quote(APP_BASE_URL, safe=":/")
    url = f"{AUTH_AUTHORIZE}?provider=google&redirect_to={redirect_to}"
    log("Gerada login_url_google()", {"url": url})
    return url

def fetch_supabase_user(access_token: str):
    if not access_token:
        log("fetch_supabase_user(): access_token vazio")
        return None
    try:
        log("Chamando /auth/v1/user no Supabase", {"endpoint": AUTH_USERINFO})
        r = requests.get(
            AUTH_USERINFO,
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
        log("Resposta do /user", {"status_code": r.status_code, "text": safe_text(r.text)})
        if r.status_code == 200:
            return r.json()
        return None
    except requests.exceptions.RequestException as e:
        log("Erro de rede ao chamar /user", {"error": str(e)})
        return None
    except Exception as e:
        log("Erro inesperado ao chamar /user", {"error": str(e)})
        return None

def safe_text(text: str, limit: int = 500):
    if text is None:
        return ""
    return text if len(text) <= limit else text[:limit] + "... [truncado]"

def logout():
    log("Logout solicitado: limpando sessão e voltando para /")
    st.session_state.clear()
    st.experimental_set_query_params()
    js_force_path("/")
    st.rerun()

# ------------------------ UI PAGES ------------------------
def page_login():
    st.title("🔐 Login com Google (Supabase)")
    if not SUPABASE_URL or not SUPABASE_KEY:
        st.error("SUPABASE_URL e/ou SUPABASE_KEY não configurados em secrets.")
    st.link_button("Entrar com Google", login_url_google())
    st.caption(f"Redirect configurado: `{APP_BASE_URL}`")

def page_dashboard(user: dict):
    name = user.get("user_metadata", {}).get("name") or user.get("email")
    avatar = user.get("user_metadata", {}).get("avatar_url")

    st.success(f"Autenticado como **{name}**")
    if avatar:
        st.image(avatar, width=96)

    st.header("📄 Dashboard (área autenticada)")
    st.write("**Mensagem de teste:** você está autenticado. 🎉")
    st.button("Sair", on_click=logout)

# ------------------------ APP (FLUXO) ------------------------
def main():
    show_current_url_client()
    debug_panel()
    log("Iniciando main()")

    # 0) Converter #access_token → ?access_token
    js_move_hash_to_query()

    # 1) Se já autenticado, força path /dashboard e mostra dashboard
    if st.session_state.get("user"):
        log("Sessão já contém 'user' — exibindo dashboard")
        js_force_path("/dashboard")
        page_dashboard(st.session_state["user"])
        return

    # 2) Ler params e tratar erro de OAuth
    params = st.experimental_get_query_params()
    log("Query params lidos", dict(params))
    if "error" in params:
        desc = params.get("error_description", [""])[0]
        msg = desc or params["error"][0]
        log("Erro de OAuth detectado", {"error": msg})
        st.error(f"Erro de OAuth: {msg}")
        st.stop()

    # 3) Tentar autenticar se veio ?access_token=...
    access_token = (params.get("access_token") or [None])[0]
    if access_token:
        log("Detectado access_token na query", {"has_token": bool(access_token)})
        user = fetch_supabase_user(access_token)
        if user:
            log("Validação OK — salvando usuário na sessão", user)
            st.session_state["user"] = user
            st.experimental_set_query_params()  # limpa token da URL
            js_force_path("/dashboard")
            st.rerun()
        else:
            log("Validação FALHOU — usuário não retornado")
            st.error("Não foi possível validar o login. Tente novamente.")
            st.experimental_set_query_params()

    # 4) Se não logado, garantir path raiz e mostrar tela de login
    log("Usuário não autenticado — exibindo tela de login")
    js_force_path("/")
    page_login()

if __name__ == "__main__":
    main()
