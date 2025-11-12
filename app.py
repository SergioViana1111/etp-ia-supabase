import os
import io
# Importações omitidas...
from urllib.parse import quote

import requests
import streamlit as st
import streamlit.components.v1 as components
from supabase import create_client, Client
# from openai import OpenAI # Importe suas bibliotecas necessárias

# =====================================================
# CONFIGURAÇÕES GERAIS / INTEGRAÇÕES
# =====================================================

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
APP_BASE_URL = os.getenv("APP_BASE_URL") 

if not SUPABASE_URL or not SUPABASE_KEY:
    supabase: Client | None = None
else:
    # A variável 'supabase' deve estar configurada para uso nas funções auxiliares
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) 

# =====================================================
# FUNÇÕES AUXILIARES DE AUTENTICAÇÃO (Mantenha as suas)
# =====================================================

def obter_user_supabase(access_token: str):
    """Consulta a API Auth do Supabase."""
    if not access_token or not SUPABASE_URL or not SUPABASE_KEY: return None
    try:
        headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {access_token}"}
        resp = requests.get(f"{SUPABASE_URL}/auth/v1/user", headers=headers, timeout=15)
        if resp.status_code == 200:
            return resp.json()
        st.error(f"Falha na validação do token (Status: {resp.status_code}). Resposta: {resp.text[:50]}...") 
    except Exception as e:
        st.error(f"Erro ao consultar Supabase Auth: {e}")
    return None

def sincronizar_usuario(user_json: dict):
    # CRÍTICO: Sua lógica de SELECT/INSERT na tabela 'usuarios'
    # Esta função deve retornar o objeto do usuário do seu BD
    if user_json:
        # st.write(f"Sincronizando: {user_json.get('email')}")
        return {"nome": user_json.get("user_metadata", {}).get("full_name"), "email": user_json.get("email")}
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
    auth_url = gerar_google_auth_url()
    st.markdown(
        f'<a href="{auth_url}" target="_self"><button style="background-color:#4285F4; color:white; border:none; padding: 10px 20px; text-align: center; text-decoration: none; display: inline-block; font-size: 16px; margin: 4px 2px; cursor: pointer; border-radius: 4px;">🔐 Entrar com Google</button></a>', 
        unsafe_allow_html=True
    )

# =====================================================
# FUNÇÕES DE FLUXO JS (Simplificada)
# =====================================================

def mover_access_token_do_hash_para_query():
    """Lê o token da hash e o move para a query string, forçando o Streamlit a ler."""
    # Removemos o 'key' e qualquer complexidade para evitar o TypeError/Tela Branca.
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
                    // CRÍTICO: replace() força o Streamlit a iniciar um ciclo limpo
                    window.location.replace(url.toString()); 
                }
            }
        })();
        </script>
        """,
        height=0, 
    )

# =====================================================
# FUNÇÃO PRINCIPAL (MAIN)
# =====================================================

def main():
    st.set_page_config(page_title="Ferramenta IA para ETP", layout="wide")

    # ----------------------------------------------------
    # DEBUG INFO
    # ----------------------------------------------------
    st.write("--- DEBUG INFO ---")
    st.write(f"SUPABASE_URL está configurada: {'Sim' if os.getenv('SUPABASE_URL') else 'NÃO'}")
    st.write(f"Sessão atual (usuario): {st.session_state.get('usuario', 'NENHUM')}")
    st.write("--------------------")

    if supabase is None:
        st.error("ERRO CRÍTICO: Configurações de Supabase ausentes.")
        return

    # 1) Executa o JS para ler o token da # e movê-lo para a ?
    st.write("PASSO 1: Rodando script JS para mover o token da # para a ? (Rerun será forçado).")
    mover_access_token_do_hash_para_query()

    # 2) Bloco de Autenticação
    if "usuario" not in st.session_state:
        st.write("PASSO 2: Usuário não está na sessão. Iniciando checagem de login.")
        
        # Leitura da QUERY STRING, que deve ter o token após o PASSO 1
        params = st.experimental_get_query_params()
        access_tokens = params.get("access_token")

        if access_tokens:
            st.write("PASSO 3: Token encontrado na URL query string (?access_token=...).")
            access_token = access_tokens[0]
            
            # Garante que o processamento do token ocorra apenas uma vez
            if "login_processado" not in st.session_state:
                st.session_state["login_processado"] = True 
                st.write("PASSO 3.1: Iniciando processamento do token (1ª vez).")

                # Ponto de Falha 1: Validação do Token
                st.write("PASSO 4: Chamando obter_user_supabase (API Auth)...")
                user_json = obter_user_supabase(access_token)
                
                if user_json:
                    st.write("PASSO 4.1: SUCESSO! Token validado.")
                    
                    # Ponto de Falha 2: Sincronização
                    st.write("PASSO 5: Sincronizando usuário com a tabela 'usuarios'...")
                    usuario = sincronizar_usuario(user_json)
                    
                    if usuario:
                        st.write("PASSO 5.1: SUCESSO! Usuário salvo na sessão. Preparando para RERUN.")
                        st.session_state["usuario"] = usuario
                        st.session_state["access_token"] = access_token 

                        # CRÍTICO: Limpa a URL e força o Streamlit a recarregar no dashboard limpo
                        st.experimental_set_query_params() 
                        st.experimental_rerun()
                    else:
                        st.error("ERRO 5.2: Falha ao sincronizar/criar registro na tabela 'usuarios'.")
                else:
                    st.error("ERRO 4.2: Falha na validação do token com a API Auth do Supabase.")
            
            # Se o processo falhou (chegou aqui sem rerun), exibe a tela de login
            if "usuario" not in st.session_state:
                st.write("PASSO 6: Processamento falhou. Exibindo tela de login.")
                # Limpa a query param se falhou, para evitar que o loop continue
                st.experimental_set_query_params() 
                tela_login_google()
                return
        
        else:
            st.write("PASSO 3: Nenhum token encontrado na URL. Exibindo tela de login.")
            tela_login_google()
            return
    
    # 3) Daqui pra baixo SÓ RODA SE O USUÁRIO ESTIVER LOGADO
    st.write("PASSO 7: Usuário na sessão. Exibindo Dashboard.")
    st.success("AUTENTICAÇÃO COMPLETA. BEM-VINDO!")

    # Limpa a flag de processamento, pois o login foi bem-sucedido
    if "login_processado" in st.session_state:
        del st.session_state["login_processado"]
        
    usuario = st.session_state["usuario"]
    
    # --- INÍCIO DO DASHBOARD ---
    st.sidebar.header(f"Olá, {usuario.get('nome', 'Usuário')}")
    st.header("Dashboard de Elaboração de ETP")
    
    if st.sidebar.button("Sair", help="Encerrar sessão"):
        st.session_state.clear()
        st.experimental_rerun()


if __name__ == "__main__":
    main()
