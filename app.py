import os
import io
from datetime import datetime
from urllib.parse import quote, urlparse, parse_qs

import requests
import streamlit as st
import streamlit.components.v1 as components
from supabase import create_client, Client
# Importe suas bibliotecas restantes

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
# FUNÇÕES AUXILIARES DE AUTENTICAÇÃO (Mantenha)
# =====================================================

def obter_user_supabase(access_token: str):
    # Sua lógica de consulta Supabase Auth
    if not access_token or not SUPABASE_URL or not SUPABASE_KEY: return None
    try:
        headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {access_token}"}
        resp = requests.get(f"{SUPABASE_URL}/auth/v1/user", headers=headers, timeout=10) 
        if resp.status_code == 200:
            return resp.json()
        st.error(f"Falha na validação do token (Status: {resp.status_code}). Resposta: {resp.text[:80]}...") 
    except Exception as e:
        st.error(f"Erro ao consultar Supabase Auth: {e}")
    return None

def sincronizar_usuario(user_json: dict):
    # Sua lógica de sincronização com a tabela 'usuarios'
    if user_json:
        # Simplificado para o debug, use sua lógica de DB aqui.
        return {"nome": user_json.get("user_metadata", {}).get("full_name"), "email": user_json.get("email")}
    return None

def gerar_google_auth_url():
    if not SUPABASE_URL: return "#"
    redirect_enc = quote(APP_BASE_URL, safe="")
    return f"{SUPABASE_URL}/auth/v1/authorize?provider=google&redirect_to={redirect_enc}"

def tela_login_google():
    st.set_page_config(page_title="Ferramenta IA para ETP", layout="wide")
    st.title("Ferramenta Inteligente para Elaboração de ETP")
    st.subheader("Acesse com sua conta Google")
    
    auth_url = gerar_google_auth_url()
    
    if st.button("🔐 Entrar com Google"):
        # Define a flag para mover o token no próximo rerun
        st.session_state["pronto_para_mover_hash"] = True 
        
        # Redireciona via JS para o Supabase
        components.html(
            f"""<script>window.location.href = '{auth_url}';</script>""",
            height=0
        )
        st.rerun() 
    
    st.caption("Ao clicar, você será redirecionado para o Google/Supabase para autenticação.")

# =====================================================
# FUNÇÕES DE FLUXO JS (AGORA COM FLAGGING DE EXECUÇÃO)
# =====================================================

def mover_access_token_do_hash_para_session():
    """Lê a hash, salva no sessionStorage e força o Streamlit a recarregar com URL limpa."""
    
    st.session_state["movimento_js_executado"] = True # Sinaliza que o JS foi injetado
    
    components.html(
        """
        <script>
        (function() {
            if (window.location.hash && window.location.hash.includes("access_token=")) {
                const params = new URLSearchParams(window.location.hash.substring(1));
                const access = params.get("access_token");
                const url = new URL(window.location.href.split('#')[0]);
                
                if (access) {
                    sessionStorage.setItem('supabase_access_token', access); 
                    window.location.replace(url.toString()); 
                }
            }
        })();
        </script>
        """,
        height=0, 
    )
    
def obter_token_do_session_storage():
    """Lê o token salvo no sessionStorage e limpa em um único script JS."""
    
    st.session_state["leitor_js_executado"] = True # Sinaliza que o JS foi injetado
    
    token = components.html(
        """
        <script>
            const token = sessionStorage.getItem('supabase_access_token');
            if (token) {
                sessionStorage.removeItem('supabase_access_token');
            }
            return token; 
        </script>
        """,
        height=0,
        width=0,
        key="session_storage_reader_cleaner_final" # Chave ÚNICA
    )
    
    return token if token else None

# =====================================================
# FUNÇÃO PRINCIPAL (MAIN) - ISOLAMENTO DE ERRO
# =====================================================

def main():
    st.set_page_config(page_title="Ferramenta IA para ETP", layout="wide")

    # Inicializa flags se não existirem
    if "pronto_para_mover_hash" not in st.session_state:
        st.session_state["pronto_para_mover_hash"] = False
    
    # ----------------------------------------------------
    # DEBUG INFO
    # ----------------------------------------------------
    st.write("--- DEBUG INFO ---")
    st.write(f"SUPABASE_URL está configurada: {'Sim' if os.getenv('SUPABASE_URL') else 'NÃO'}")
    st.write(f"Sessão atual (usuario): {st.session_state.get('usuario', 'NENHUM')}")
    st.write(f"Flag 'pronto_para_mover_hash': {st.session_state.get('pronto_para_mover_hash')}")
    st.write(f"Flag 'movimento_js_executado': {st.session_state.get('movimento_js_executado')}")
    st.write(f"Flag 'leitor_js_executado': {st.session_state.get('leitor_js_executado')}")
    st.write("--------------------")

    if supabase is None:
        st.error("ERRO CRÍTICO: Configurações de Supabase ausentes.")
        return

    # 1) MOVIMENTO DA HASH (SÓ RODA SE A SESSÃO SINALIZAR)
    if st.session_state["pronto_para_mover_hash"] and "usuario" not in st.session_state:
        st.write("PASSO 1: Flag 'pronto_para_mover_hash' ATIVA. Rodando script JS de MOVIMENTO/SALVAMENTO.")
        mover_access_token_do_hash_para_session()
        # O script JS acima fará o window.location.replace, resultando em um novo rerun.
        # Não precisamos de st.rerun() aqui, pois o JS já faz isso.
    else:
        st.write("PASSO 1: Script de MOVIMENTO SKIPPADO ou Usuário logado.")


    # 2) Bloco de Autenticação
    if "usuario" not in st.session_state:
        st.write("PASSO 2: Usuário não está na sessão. Iniciando checagem de login.")
        
        access_token = None
        
        # 2.1) LEITURA DO SESSION STORAGE (SÓ TENTA SE O MOVIMENTO JÁ FOI FEITO)
        # Tenta ler o token se a flag de movimento foi ativada em algum momento
        if st.session_state.get("movimento_js_executado", False):
            st.write("PASSO 2.1: Flag 'movimento_js_executado' ATIVA. Tentando ler o SESSION STORAGE.")
            
            # CRÍTICO: Esta chamada é a causa do TypeError. 
            # Se der erro aqui, é a colisão do leitor com o ciclo de vida.
            access_token = obter_token_do_session_storage() 
            
            # Limpa as flags após a tentativa de leitura
            del st.session_state["movimento_js_executado"]
            del st.session_state["pronto_para_mover_hash"]
        else:
            st.write("PASSO 2.1: Leitura do SESSION STORAGE SKIPPADA (Nenhum redirecionamento detectado).")
            
        # 2.2) Leitura da QUERY STRING (Fallback)
        if not access_token:
            params = st.experimental_get_query_params()
            access_tokens_query = params.get("access_token")
            if access_tokens_query:
                access_token = access_tokens_query[0]

        
        # 3) Tenta obter o token
        if access_token:
            st.write(f"PASSO 3: Token encontrado (Fonte: {'SESSION STORAGE' if st.session_state.get('leitor_js_executado') else 'QUERY STRING/FALLBACK'}).")
            
            if "login_processado" not in st.session_state:
                st.session_state["login_processado"] = True 
                st.write("PASSO 3.1: Iniciando processamento do token (1ª vez).")

                user_json = obter_user_supabase(access_token)
                
                if user_json:
                    usuario = sincronizar_usuario(user_json)
                    
                    if usuario:
                        st.session_state["usuario"] = usuario
                        st.session_state["access_token"] = access_token 
                        st.experimental_set_query_params() 
                        st.rerun() 
                    else:
                        st.error("ERRO 5.2: Falha ao sincronizar/criar registro na tabela 'usuarios'.")
                else:
                    st.error("ERRO 4.2: Falha na validação do token com a API Auth do Supabase.")
            
        else:
            st.write("PASSO 3: Nenhum token encontrado. Exibindo tela de login.")
        
        # 4) Se o processo falhou ou não houve token, exibe a tela de login
        if "usuario" not in st.session_state:
            st.write("PASSO 4: Processamento falhou ou token ausente. Exibindo tela de login.")
            st.experimental_set_query_params() 
            tela_login_google()
            return
        
    # 5) Daqui pra baixo SÓ RODA SE O USUÁRIO ESTIVER LOGADO
    st.write("PASSO 5: Usuário na sessão. Exibindo Dashboard.")
    st.success("AUTENTICAÇÃO COMPLETA. BEM-VINDO!")

    if "login_processado" in st.session_state:
        del st.session_state["login_processado"]
        
    usuario = st.session_state["usuario"]
    
    # --- INÍCIO DO DASHBOARD ---
    st.sidebar.header(f"Olá, {usuario.get('nome', 'Usuário')}")
    st.header("Dashboard de Elaboração de ETP")
    
    if st.sidebar.button("Sair", help="Encerrar sessão"):
        st.session_state.clear()
        st.rerun() 


if __name__ == "__main__":
    main()
