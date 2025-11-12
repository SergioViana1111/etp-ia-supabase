import os
import io
import tempfile
from datetime import datetime
from urllib.parse import quote

import requests
import streamlit as st
from docx import Document
from openai import OpenAI
from supabase import create_client, Client
import pypandoc
import streamlit.components.v1 as components

# =====================================================
# CONFIGURAÇÕES GERAIS / INTEGRAÇÕES
# =====================================================

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
APP_BASE_URL = os.getenv("APP_BASE_URL")  # ex.: https://seu-app.streamlit.app

if not SUPABASE_URL or not SUPABASE_KEY:
    st.warning(
        "SUPABASE_URL e/ou SUPABASE_KEY não estão configuradas. "
        "Defina-as nos secrets do Streamlit (ou .streamlit/secrets.toml)."
    )
    supabase: Client | None = None
else:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# =====================================================
# FUNÇÕES DE USUÁRIOS (Apenas as relevantes para login)
# =====================================================

# ... (Funções obter_usuario_por_email, criar_usuario, sincronizar_usuario permanecem inalteradas)
def obter_usuario_por_email(email: str):
    if supabase is None: return None
    # ... (Resto da função)
    resp = (
        supabase.table("usuarios")
        .select("*")
        .eq("email", email)
        .limit(1)
        .execute()
    )
    data = resp.data or []
    return data[0] if data else None

def criar_usuario(nome: str, sobrenome: str, cpf: str, email: str):
    if supabase is None: return None
    # ... (Resto da função)
    resp = supabase.table("usuarios").insert(
        {
            "nome": nome,
            "sobrenome": sobrenome,
            "cpf": cpf,
            "email": email,
        }
    ).execute()
    return resp.data[0]

def obter_user_supabase(access_token: str):
    """Consulta a API Auth do Supabase para pegar dados do usuário logado."""
    if not access_token or not SUPABASE_URL or not SUPABASE_KEY:
        st.error("Erro: Parâmetros de Supabase (URL/KEY) ou token ausentes.")
        return None
    try:
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {access_token}",
        }
        resp = requests.get(f"{SUPABASE_URL}/auth/v1/user", headers=headers, timeout=15)
        
        if resp.status_code == 200:
            return resp.json()
        
        st.error(f"Falha na validação do token (Status: {resp.status_code}).")
        st.error(f"Resposta bruta do Supabase: {resp.text[:200]}...") 
        
    except requests.exceptions.Timeout:
        st.error("Erro de Timeout: Não foi possível conectar ao Supabase Auth API.")
    except requests.exceptions.ConnectionError:
        st.error("Erro de Conexão: Verifique as configurações de rede ou se a URL do Supabase está correta.")
    except Exception as e:
        st.error(f"Erro inesperado ao consultar o Supabase Auth API: {e}")
    return None

def sincronizar_usuario(user_json: dict):
    if not user_json: return None
    try:
        email = user_json.get("email")
        meta = user_json.get("user_metadata") or {}
        nome_completo = meta.get("full_name") or meta.get("name") or ""
        partes = nome_completo.split(" ", 1)
        nome = partes[0] if partes else ""
        sobrenome = partes[1] if len(partes) > 1 else ""
        cpf = "" 

        existente = obter_usuario_por_email(email) if email else None
        if existente:
            return existente
        return criar_usuario(nome, sobrenome, cpf, email)
    except Exception as e:
        st.error(f"Erro ao sincronizar usuário: {e}")
        return None


def gerar_google_auth_url():
    if not SUPABASE_URL: return "#"
    redirect = APP_BASE_URL if APP_BASE_URL else "http://localhost:8501" 
    redirect_enc = quote(redirect, safe="")
    return f"{SUPABASE_URL}/auth/v1/authorize?provider=google&redirect_to={redirect_enc}"

def tela_login_google():
    st.set_page_config(page_title="Ferramenta IA para ETP", layout="wide")
    st.title("Ferramenta Inteligente para Elaboração de ETP")
    st.subheader("Acesse com sua conta Google")
    st.write("Para usar a ferramenta, faça login com sua conta Google. O processo é seguro e realizado via Supabase Auth.")
    auth_url = gerar_google_auth_url()
    st.markdown(
        f'<a href="{auth_url}" target="_self"><button style="background-color:#4285F4; color:white; border:none; padding: 10px 20px; text-align: center; text-decoration: none; display: inline-block; font-size: 16px; margin: 4px 2px; cursor: pointer; border-radius: 4px;">🔐 Entrar com Google</button></a>', 
        unsafe_allow_html=True
    )
    st.caption("Ao clicar em \"Entrar com Google\", você será redirecionado para a página oficial do Google para login/autorização e, em seguida, voltará para esta aplicação.")


def mover_access_token_do_hash_para_query():
    """Script para forçar a leitura do token da hash (#) pelo Streamlit."""
    components.html(
        """
        <script>
        (function() {
            if (window.location.hash && window.location.hash.includes("access_token=")) {
                const params = new URLSearchParams(window.location.hash.substring(1));
                const access = params.get("access_token");
                const url = new URL(window.location.href.split('#')[0]);
                
                if (access) {
                    url.searchParams.set("access_token", access);
                    // Usa replace para evitar que o Streamlit recarregue 
                    // no mesmo passo de execução, garantindo um novo ciclo limpo.
                    window.location.replace(url.toString()); 
                }
            }
        })();
        </script>
        """,
        height=0, 
    )

# ... (O resto das funções de banco, IA e exportação foram omitidas por brevidade, 
# mas devem estar no seu código final) ...
# =====================================================
# INTERFACE STREAMLIT (Lógica de autenticação FINAL)
# =====================================================

def main():
    st.set_page_config(page_title="Ferramenta IA para ETP", layout="wide")

    if supabase is None:
        st.error("SUPABASE_URL e SUPABASE_KEY não estão configuradas.")
        return

    # 1) Tenta converter #access_token em ?access_token
    mover_access_token_do_hash_para_query()

    # 2) Bloco de Autenticação
    if "usuario" not in st.session_state:
        params = st.experimental_get_query_params()
        access_tokens = params.get("access_token")

        if access_tokens:
            access_token = access_tokens[0]
            
            # Garante que o processo de login só ocorra uma vez por token
            if "login_processado" not in st.session_state:
                st.session_state["login_processado"] = True # Marca o início do processo

                user_json = obter_user_supabase(access_token)
                
                if user_json:
                    usuario = sincronizar_usuario(user_json)
                    
                    if usuario:
                        st.session_state["usuario"] = usuario
                        st.session_state["access_token"] = access_token 

                        # CRÍTICO: Limpa a query string e força o rerun
                        st.experimental_set_query_params() 
                        st.experimental_rerun()
                        # O Streamlit irá recarregar no topo do script com o usuário em sessão.
                    else:
                        st.error("Falha ao criar o registro do usuário no BD (tabela 'usuarios').")
                        st.experimental_set_query_params() 
                else:
                    st.warning("Falha na validação do token (veja os logs de erro acima).")
                    st.experimental_set_query_params() 
            
            # Se o processo falhou e o usuário não foi logado, exibe a tela de login
            if "usuario" not in st.session_state:
                tela_login_google()
                return
        
        else:
            # Não tem token na URL e não tem usuário em sessão → tela de login
            tela_login_google()
            return
    
    # --- 3) DAQUI PRA BAIXO SÓ RODA SE O USUÁRIO ESTIVER LOGADO ---
    # Limpa a flag de processamento para futuros logouts/re-logins
    if "login_processado" in st.session_state:
        del st.session_state["login_processado"]
        
    usuario = st.session_state["usuario"]
    # ... (Resto da aplicação) ...


if __name__ == "__main__":
    # Certifique-se de que todas as funções de helper (etapas, projetos, etc.) 
    # estão definidas antes de chamar main().
    main()
