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
APP_BASE_URL = os.getenv("APP_BASE_URL") 

if not SUPABASE_URL or not SUPABASE_KEY:
    supabase: Client | None = None
else:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# =====================================================
# FUNÇÕES AUXILIARES DE AUTENTICAÇÃO
# =====================================================
# (Mantenha suas implementações completas aqui)

def obter_usuario_por_email(email: str):
    # ... (sua implementação) ...
    pass
def criar_usuario(nome: str, sobrenome: str, cpf: str, email: str):
    # ... (sua implementação) ...
    pass

def obter_user_supabase(access_token: str):
    # Sua implementação robusta com try/except
    if not access_token or not SUPABASE_URL or not SUPABASE_KEY:
        st.error("Erro: Parâmetros de Supabase ou token ausentes.")
        return None
    try:
        headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {access_token}"}
        resp = requests.get(f"{SUPABASE_URL}/auth/v1/user", headers=headers, timeout=15)
        if resp.status_code == 200:
            return resp.json()
        st.error(f"Falha na validação do token (Status: {resp.status_code}).")
        return None
    except Exception as e:
        st.error(f"Erro inesperado ao consultar o Supabase Auth API: {e}")
        return None

def sincronizar_usuario(user_json: dict):
    # ... (sua implementação) ...
    pass

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
# FUNÇÕES CRÍTICAS DE FLUXO (Local Storage)
# =====================================================

def mover_access_token_do_hash_para_query():
    """Lê o token da hash, salva no localStorage e limpa a URL. (Sem 'key' para evitar TypeError)"""
    components.html(
        """
        <script>
        (function() {
            if (window.location.hash && window.location.hash.includes("access_token=")) {
                const params = new URLSearchParams(window.location.hash.substring(1));
                const access = params.get("access_token");
                
                if (access) {
                    localStorage.setItem('supabase_access_token', access);
                    const url = new URL(window.location.href.split('#')[0]);
                    window.location.replace(url.toString()); 
                }
            }
        })();
        </script>
        """,
        height=0, 
    )

def obter_token_do_local_storage():
    """Usa JS para ler o token salvo no localStorage e o retorna ao Python.
    USA CHAVES DISTINTAS E FIXAS PARA EVITAR TypeError."""
    
    # 1. Leitor do Token
    token = components.html(
        """
        <script>
            return localStorage.getItem('supabase_access_token');
        </script>
        """,
        height=0,
        width=0,
        key="local_storage_reader_return" # Chave ÚNICA
    )
    
    # 2. Removedor do Token (só roda se tiver lido o token)
    if token:
        components.html(
            """<script>localStorage.removeItem('supabase_access_token');</script>""",
            height=0,
            width=0,
            key="local_storage_remover_final" # Chave ÚNICA e DIFERENTE da anterior
        )
    return token

# =====================================================
# FUNÇÕES DO APP (ETAPAS / IA / EXPORTAÇÃO) - Mantenha as suas aqui
# =====================================================
# Funções placeholder para compilação
def listar_projetos(): return [] 
def obter_projeto(projeto_id: int): return {}
# ... (outras funções) ...

# =====================================================
# INTERFACE STREAMLIT (Lógica de autenticação FINAL)
# =====================================================

def main():
    # ... (Seu código e DEBUG INFO aqui) ...

    mover_access_token_do_hash_para_query() # PASSO 1

    # 2) Bloco de Autenticação
    if "usuario" not in st.session_state:
        st.write("PASSO 2: Usuário não está na sessão. Iniciando checagem de login.")
        
        # ----------------------------------------------------------------------
        # CENTRALIZAÇÃO DA LEITURA DE TOKEN
        # O token é lido apenas se a flag 'token_lido' não estiver na sessão
        # ----------------------------------------------------------------------
        
        access_token = None
        
        if "token_lido" not in st.session_state:
            st.session_state["token_lido"] = True # Marca que tentaremos ler nesta execução
            
            st.write("PASSO 2.1: Tentando ler o token do Local Storage (Primeira tentativa de leitura).")
            # Esta chamada é o ponto de falha. Ela é feita apenas uma vez por ciclo de lógica.
            try:
                access_token = obter_token_do_local_storage()
            except Exception as e:
                # Se falhar aqui, mostra a tela de login.
                st.error(f"ERRO CRÍTICO no PASSO 2.1 (Componente JS): {type(e).__name__}. Verifique se as chaves 'local_storage_reader_return' são únicas.")
                tela_login_google()
                return

        if access_token:
            st.write("PASSO 3: Token encontrado no Local Storage.")
            
            # ... (Restante da lógica PASSO 3.1 até PASSO 5.1 permanece igual) ...
            
            if "login_processado" not in st.session_state:
                st.session_state["login_processado"] = True 

                st.write("PASSO 4: Chamando obter_user_supabase (API Auth)...")
                user_json = obter_user_supabase(access_token)
                
                if user_json:
                    # ... (SUCESSO: Sincronização, salvamento em session_state) ...
                    st.write("PASSO 5.1: SUCESSO! Usuário salvo na sessão. Preparando para RERUN.")
                    
                    # Salva o usuário e força o rerun
                    # ...
                    st.experimental_rerun()
                else:
                    st.error("ERRO 4.2: Falha na validação do token com a API Auth do Supabase.")
            
            # Se falhou, limpa o token_lido para tentar novamente no próximo ciclo
            if "usuario" not in st.session_state and "token_lido" in st.session_state:
                del st.session_state["token_lido"] 
            
            if "usuario" not in st.session_state:
                st.write("PASSO 6: Processamento falhou. Exibindo tela de login.")
                tela_login_google()
                return
        
        else:
            st.write("PASSO 3: Nenhum token encontrado. Exibindo tela de login.")
            tela_login_google()
            return
    
    # 3) Daqui pra baixo SÓ RODA SE O USUÁRIO ESTIVER LOGADO
    st.write("PASSO 7: Usuário na sessão. Exibindo Dashboard.")
    st.success("AUTENTICAÇÃO COMPLETA. BEM-VINDO!")

    # ... (Restante do seu código) ...
if __name__ == "__main__":
    main()
