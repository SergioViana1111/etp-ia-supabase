# app.py — Streamlit + Supabase Auth (Google) • arquivo único
# Requisitos:
#   pip install streamlit requests supabase
#
# Coloque no .streamlit/secrets.toml:
#   SUPABASE_URL = "https://SEU-PROJETO.supabase.co"
#   SUPABASE_KEY = "SUA_ANON_KEY"
#   APP_BASE_URL = "https://seu-app.streamlit.app/"
#
# No Google Cloud:
#   - OAuth consent: Externo + Em produção
#   - Domínios autorizados: seu subdomínio do Streamlit e o do Supabase
#   - Redirect URI do cliente OAuth: https://SEU-PROJETO.supabase.co/auth/v1/callback
# No Supabase → Auth → URL Configuration:
#   - Site URL: https://seu-app.streamlit.app/
#   - Additional Redirect URLs: https://seu-app.streamlit.app/ e http://localhost:8501/

import os
import requests
import streamlit as st
import streamlit.components.v1 as components
from urllib.parse import quote

# ------------------------ CONFIG ------------------------
st.set_page_config(page_title="Login Google • Supabase", page_icon="🔐", layout="centered")

SUPABASE_URL = st.secrets.get("SUPABASE_URL", os.getenv("SUPABASE_URL", ""))
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", os.getenv("SUPABASE_KEY", ""))

APP_BASE_URL = st.secrets.get("APP_BASE_URL", os.getenv("APP_BASE_URL", "http://localhost:8501/"))
if not APP_BASE_URL.endswith("/"):
    APP_BASE_URL += "/"

AUTH_AUTHORIZE = f"{SUPABASE_URL}/auth/v1/authorize"
AUTH_USERINFO  = f"{SUPABASE_URL}/auth/v1/user"

# ------------------------ HELPERS ------------------------
def login_url_google():
    """Monta a URL de login do Supabase com Google e redirect para o app."""
    if not SUPABASE_URL:
        return "#"
    # evitar double-encode; manter :/ seguros
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

def mover_access_token_do_hash_para_query():
    """
    Converte #access_token=... (fragment) para ?access_token=...
    Compatível com Streamlit Cloud — executa com retries.
    """
    components.html(
        """
        <html><body></body>
        <script>
        (function () {
          function tryConvert() {
            try {
              if (location.hash && location.hash.indexOf("access_token=") !== -1) {
                const params = new URLSearchParams(location.hash.substring(1));
                const access = params.get("access_token");
                if (access) {
                  const url = new URL(location.href);
                  url.hash = "";
                  // mantém todos os parâmetros que vieram no fragment
                  url.search = params.toString();
                  location.replace(url.toString());
                  return true;
                }
              }
            } catch (e) { console.error(e); }
            return false;
          }
          if (!tryConvert()) {
            window.addEventListener("load", tryConvert);
            let n=0, t=setInterval(function(){ if (tryConvert() || ++n>30) clearInterval(t); }, 100);
          }
        })();
        </script>
        </html>
        """,
        height=110,  # precisa ser >0 para o JS executar no Cloud
    )

def logout():
    st.session_state.clear()
    st.experimental_set_query_params()
    st.rerun()

# ------------------------ APP ------------------------
def main():
    # 1) mover hash->query (precisa acontecer antes de ler os params)
    mover_access_token_do_hash_para_query()

    # 2) se já autenticado, mostra “segunda página”
    if st.session_state.get("user"):
        u = st.session_state["user"]
        st.success(f"Autenticado como **{u.get('user_metadata',{}).get('name') or u.get('email')}**")
        if u.get("user_metadata", {}).get("avatar_url"):
            st.image(u["user_metadata"]["avatar_url"], width=96)
        st.header("📄 Página pós-login")
        st.write("**Mensagem de teste:** Login OK! Bem-vindo à área autenticada. 🎉")
        st.button("Sair", on_click=logout)
        return

    # 3) tratar possível erro vindo do OAuth
    params = st.experimental_get_query_params()
    if "error" in params:
        desc = params.get("error_description", [""])[0]
        st.error(f"Erro de OAuth: {desc or params['error'][0]}")
        st.stop()

    # 4) tentar autenticar se já veio ?access_token=...
    access_token = (params.get("access_token") or [None])[0]
    if access_token:
        user = fetch_supabase_user(access_token)
        if user:
            st.session_state["user"] = user
            # limpa a query pra não deixar token na barra
            st.experimental_set_query_params()
            st.rerun()
        else:
            st.error("Não foi possível validar o login. Tente novamente.")
            st.experimental_set_query_params()

    # 5) tela de login
    st.title("🔐 Login com Google (Supabase)")
    if not SUPABASE_URL or not SUPABASE_KEY:
        st.error("SUPABASE_URL e/ou SUPABASE_KEY não configurados em secrets.")
        st.stop()

    st.write("Acesse com sua conta Google. O processo é seguro e realizado via Supabase Auth.")
    st.link_button("Entrar com Google", login_url_google())
    st.caption(f"Redirect configurado: `{APP_BASE_URL}`")

if __name__ == "__main__":
    main()
