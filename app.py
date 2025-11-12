# Streamlit + Supabase Auth (Google) com /dashboard
# ---------------------------------------------------
# Requisitos:
#   pip install streamlit requests supabase
#
# .streamlit/secrets.toml:
#   SUPABASE_URL = "https://SEU-PROJETO.supabase.co"
#   SUPABASE_KEY = "SUA_ANON_KEY"
#   APP_BASE_URL = "https://seu-app.streamlit.app/"  # COM barra no final
#
# Google Cloud:
#   - Consent: External + Em produção
#   - Redirect URI do Client OAuth: https://SEU-PROJETO.supabase.co/auth/v1/callback
# Supabase → Auth → URL Configuration:
#   - Site URL: https://seu-app.streamlit.app/
#   - Additional Redirect URLs: https://seu-app.streamlit.app/ e http://localhost:8501/

import os
import requests
import streamlit as st
import streamlit.components.v1 as components
from urllib.parse import quote

# ------------------------ CONFIG ------------------------
st.set_page_config(page_title="ETP • Login", page_icon="🔐", layout="centered")

SUPABASE_URL = st.secrets.get("SUPABASE_URL", os.getenv("SUPABASE_URL", ""))
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", os.getenv("SUPABASE_KEY", ""))

APP_BASE_URL = st.secrets.get("APP_BASE_URL", os.getenv("APP_BASE_URL", "http://localhost:8501/"))
if not APP_BASE_URL.endswith("/"):
    APP_BASE_URL += "/"

AUTH_AUTHORIZE = f"{SUPABASE_URL}/auth/v1/authorize"
AUTH_USERINFO  = f"{SUPABASE_URL}/auth/v1/user"

# ------------------------ JS HELPERS (executam no navegador) ------------------------
def js_move_hash_to_query():
    """Converte #access_token=... em ?access_token=... (compatível com Streamlit Cloud)."""
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
                url.search = params.toString();   // mantém refresh_token, expires_in etc.
                window.parent.location.replace(url.toString());
                return true;
              }
            } catch (e) { console.error('hash2query error:', e); }
            return false;
          }
          let n=0, iv=setInterval(function(){ if (convert() || ++n>30) clearInterval(iv); }, 100);
          window.addEventListener('load', convert);
        })();
        </script>
        "></iframe>
        """,
        height=150,
    )

def js_force_path(path: str):
    """
    Garante que a URL atual tenha o path desejado (ex.: '/dashboard' ou '/').
    Usa History API sem recarregar a página (o Streamlit se encarrega do rerun).
    """
    components.html(
        f"""
        <script>
        (function() {{
          try {{
            var desired = "{path}";
            var u = new URL(window.location.href);
            if (u.pathname !== desired) {{
              u.pathname = desired;
              // mantém query string limpa
              u.search = "";
              window.history.replaceState(null, "", u.toString());
            }}
          }} catch(e) {{ console.error(e); }}
        }})();
        </script>
        """,
        height=1,
    )

# ------------------------ PY HELPERS ------------------------
def login_url_google():
    """URL de login Supabase/Google com redirect para a raiz do app."""
    if not SUPABASE_URL:
        return "#"
    redirect_to = quote(APP_BASE_URL, safe=":/")
    return f"{AUTH_AUTHORIZE}?provider=google&redirect_to={redirect_to}"

def fetch_supabase_user(access_token: str):
    if not access_token:
        return None
    try:
        r = requests.get(
            AUTH_USERINFO,
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {access_token}"},
            timeout=12,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None

def logout():
    st.session_state.clear()
    st.experimental_set_query_params()
    js_force_path("/")   # volta URL para raiz
    st.rerun()

# ------------------------ UI PAGES ------------------------
def page_login():
    st.title("🔐 Login com Google (Supabase)")
    st.write("Acesse com sua conta Google. O processo é seguro e realizado via Supabase Auth.")
    st.link_button("Entrar com Google", login_url_google())
    st.caption(f"Redirect configurado: `{APP_BASE_URL}`")

def page_dashboard(user: dict):
    name = user.get("user_metadata", {}).get("name") or user.get("email")
    avatar = user.get("user_metadata", {}).get("avatar_url")

    st.set_page_config(page_title="ETP • Dashboard", page_icon="📄", layout="wide")
    st.success(f"Bem-vindo(a), **{name}**")
    if avatar:
        st.image(avatar, width=96)

    st.header("📄 Dashboard")
    st.write("**Mensagem de teste:** você está autenticado e vendo o /dashboard. 🎉")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Atalhos")
        st.button("Sair", on_click=logout)
    with col2:
        st.info("Aqui você pode renderizar o conteúdo real do seu sistema (projetos, etapas, etc.).")

# ------------------------ APP ------------------------
def main():
    # 0) sempre tenta converter o fragmento #access_token
    js_move_hash_to_query()

    # 1) se já está autenticado, garante que a URL seja /dashboard e mostra dashboard
    user = st.session_state.get("user")
    if user:
        js_force_path("/dashboard")
        page_dashboard(user)
        return

    # 2) tratar possível erro do OAuth
    params = st.experimental_get_query_params()
    if "error" in params:
        desc = params.get("error_description", [""])[0]
        st.error(f"Erro de OAuth: {desc or params['error'][0]}")
        st.stop()

    # 3) se veio ?access_token=..., valida no Supabase e vai para /dashboard
    access_token = (params.get("access_token") or [None])[0]
    if access_token:
        u = fetch_supabase_user(access_token)
        if u:
            st.session_state["user"] = u
            st.experimental_set_query_params()  # limpa token da URL
            js_force_path("/dashboard")
            st.rerun()
        else:
            st.error("Não foi possível validar o login. Tente novamente.")
            st.experimental_set_query_params()

    # 4) se não logado, garante que a URL seja raiz e mostra tela de login
    js_force_path("/")
    if not SUPABASE_URL or not SUPABASE_KEY:
        st.error("SUPABASE_URL e/ou SUPABASE_KEY não configurados em secrets.")
        st.stop()
    page_login()

if __name__ == "__main__":
    main()
