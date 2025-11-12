# app.py — Login Google via Supabase (hash -> query) estável no Streamlit
# Autor: Sérgio Viana (ajustes finais)
# Requisitos:
#   pip install streamlit supabase requests

import os
from urllib.parse import quote

import requests
import streamlit as st
import streamlit.components.v1 as components
from supabase import create_client, Client

# =====================================================
# CONFIGURAÇÕES GERAIS / INTEGRAÇÕES
# =====================================================

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8501")

if not SUPABASE_URL or not SUPABASE_KEY:
    supabase: Client | None = None
else:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# =====================================================
# FUNÇÕES AUXILIARES DE AUTENTICAÇÃO
# =====================================================

def obter_user_supabase(access_token: str):
    """
    Valida o access_token no endpoint /auth/v1/user do Supabase.
    Retorna o JSON do usuário em caso de sucesso, ou None.
    """
    if not access_token or not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {access_token}"}
        resp = requests.get(f"{SUPABASE_URL}/auth/v1/user", headers=headers, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        st.error(f"Falha na validação do token (Status: {resp.status_code}). Resposta: {resp.text[:120]}...")
    except Exception as e:
        st.error(f"Erro ao consultar Supabase Auth: {e}")
    return None


def sincronizar_usuario(user_json: dict):
    """
    Sincroniza dados mínimos do usuário.
    (Adapte para gravar em sua tabela 'usuarios' no Supabase, se necessário.)
    """
    if user_json:
        return {
            "nome": user_json.get("user_metadata", {}).get("full_name") or user_json.get("email") or "Usuário",
            "email": user_json.get("email"),
        }
    return None


def gerar_google_auth_url():
    """
    Gera a URL de autorização do Supabase Google com redirect para APP_BASE_URL.
    """
    if not SUPABASE_URL:
        return "#"
    redirect_enc = quote(APP_BASE_URL, safe="")
    return f"{SUPABASE_URL}/auth/v1/authorize?provider=google&redirect_to={redirect_enc}"

# =====================================================
# FLUXO JS: MOVER TOKEN DO HASH PARA A QUERY STRING
# =====================================================

def mover_access_token_do_hash_para_query():
    """
    Se a URL tiver #access_token=..., transforma em ?access_token=... e faz replace.
    Evita sessionStorage e evita tentar retornar valor do JS para o Python.
    """
    st.session_state["movimento_js_executado"] = True  # apenas para debug
    components.html(
        """
        <script>
        (function() {
          try {
            if (window.location.hash && window.location.hash.includes("access_token=")) {
              const params = new URLSearchParams(window.location.hash.substring(1));
              const access = params.get("access_token");
              const base = window.location.href.split('#')[0];
              if (access) {
                const url = new URL(base);
                url.searchParams.set("access_token", access);
                window.location.replace(url.toString()); // limpa o hash e reroda o app
              }
            }
          } catch (e) {
            console.error("Hash->Query mover error:", e);
          }
        })();
        </script>
        """,
        height=0,
    )

# =====================================================
# UI: TELA DE LOGIN
# =====================================================

def tela_login_google():
    st.title("Ferramenta Inteligente para Elaboração de ETP")
    st.subheader("Acesse com sua conta Google")

    auth_url = gerar_google_auth_url()

    if st.button("🔐 Entrar com Google"):
        # Sinaliza que no próximo ciclo vamos mover o token do hash pra query
        st.session_state["pronto_para_mover_hash"] = True
        # Redireciona para o Supabase Auth
        components.html(f"<script>window.location.href = '{auth_url}';</script>", height=0)
        st.rerun()

    st.caption("Ao clicar, você será redirecionado para o Google/Supabase para autenticação.")

# =====================================================
# MAIN
# =====================================================

def main():
    st.set_page_config(page_title="Ferramenta IA para ETP", layout="wide")

    # Flags default
    st.session_state.setdefault("pronto_para_mover_hash", False)

    # ----------------------------------------------------
    # DEBUG INFO
    # ----------------------------------------------------
    st.write("--- DEBUG INFO ---")
    st.write(f"SUPABASE_URL está configurada: {'Sim' if SUPABASE_URL else 'NÃO'}")
    st.write(f"Sessão atual (usuario): {st.session_state.get('usuario', 'NENHUM')}")
    st.write(f"Flag 'pronto_para_mover_hash': {st.session_state.get('pronto_para_mover_hash')}")
    st.write(f"Flag 'movimento_js_executado': {st.session_state.get('movimento_js_executado')}")
    st.write("--------------------")

    if supabase is None:
        st.error("ERRO CRÍTICO: Configurações de Supabase ausentes. Verifique SUPABASE_URL e SUPABASE_KEY.")
        return

    # 1) Se acabou de clicar em "Entrar", injeta JS que move #token -> ?token
    if st.session_state["pronto_para_mover_hash"] and "usuario" not in st.session_state:
        st.write("PASSO 1: Movendo token do hash para a query...")
        mover_access_token_do_hash_para_query()
        # O JS fará replace; não chamamos st.rerun() aqui.

    # 2) Autenticação (somente se ainda não há usuário na sessão)
    if "usuario" not in st.session_state:
        st.write("PASSO 2: Usuário não está na sessão. Checando query string...")

        # Preferir API nova se disponível; fallback na experimental
        try:
            # Streamlit >= 1.30 tem st.query_params (Mapping)
            params_map = st.query_params  # type: ignore[attr-defined]
            access_token = params_map.get("access_token", [None])
            access_token = access_token[0] if isinstance(access_token, list) else access_token
        except Exception:
            params = st.experimental_get_query_params()
            access_tokens_query = params.get("access_token")
            access_token = access_tokens_query[0] if access_tokens_query else None

        if access_token:
            st.write("PASSO 3: Token encontrado na QUERY STRING.")
            if not st.session_state.get("login_processado"):
                st.session_state["login_processado"] = True

                user_json = obter_user_supabase(access_token)
                if user_json:
                    usuario = sincronizar_usuario(user_json)
                    if usuario:
                        st.session_state["usuario"] = usuario
                        st.session_state["access_token"] = access_token

                        # Limpa a query string para evitar reprocessar token em refresh
                        try:
                            # API nova
                            st.query_params.clear()  # type: ignore[attr-defined]
                        except Exception:
                            st.experimental_set_query_params()

                        # Zera flags de forma segura
                        st.session_state.pop("pronto_para_mover_hash", None)
                        st.session_state.pop("movimento_js_executado", None)

                        st.rerun()
                    else:
                        st.error("ERRO 5.2: Falha ao sincronizar/criar registro na tabela 'usuarios'.")
                else:
                    st.error("ERRO 4.2: Falha na validação do token com a API Auth do Supabase.")
        else:
            st.write("PASSO 3: Nenhum token na query. Exibindo tela de login.")
            # Limpa resquícios de query, se houver
            try:
                st.query_params.clear()  # type: ignore[attr-defined]
            except Exception:
                st.experimental_set_query_params()

            tela_login_google()
            return

    # 3) Usuário logado → Dashboard
    st.write("PASSO 5: Usuário na sessão. Exibindo Dashboard.")
    st.success("AUTENTICAÇÃO COMPLETA. BEM-VINDO!")
    st.session_state.pop("login_processado", None)

    usuario = st.session_state["usuario"]

    # === DASHBOARD EXEMPLO ===
    st.sidebar.header(f"Olá, {usuario.get('nome', 'Usuário')}")
    st.header("Dashboard de Elaboração de ETP")

    st.write("Conteúdo do seu app aqui…")

    if st.sidebar.button("Sair", help="Encerrar sessão"):
        st.session_state.clear()
        st.rerun()


if __name__ == "__main__":
    main()
