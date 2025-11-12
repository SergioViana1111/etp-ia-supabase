import os
from urllib.parse import quote
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
# FUNÇÕES AUXILIARES DE AUTENTICAÇÃO
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
        # Placeholder para o debug
        return {"nome": user_json.get("user_metadata", {}).get("full_name"), "email": user_json.get("email")}
    return None

def gerar_google_auth_url():
    if not SUPABASE_URL: return "#"
    # A URL de redirecionamento deve ser a URL base da aplicação
    redirect_enc = quote(APP_BASE_URL, safe="")
    return f"{SUPABASE_URL}/auth/v1/authorize?provider=google&redirect_to={redirect_enc}"

def tela_login_google():
    st.set_page_config(page_title="Ferramenta IA para ETP", layout="wide")
    st.title("Ferramenta Inteligente para Elaboração de ETP")
    st.subheader("Acesse com sua conta Google")
    st.write("Para usar a ferramenta, faça login com sua conta Google. O processo é seguro e realizado via Supabase Auth.")
    
    auth_url = gerar_google_auth_url()
    
    # CORREÇÃO: Usar st.link_button para redirecionamento estável
    st.link_button(
        label="🔐 Entrar com Google", 
        url=auth_url, 
        type="primary"
    )

    st.caption("Ao clicar, você será redirecionado para o Google/Supabase para autenticação.")

# =====================================================
# FUNÇÕES DE FLUXO JS E LEITURA (MANTIDAS)
# =====================================================

def mover_access_token_do_hash_para_session():
    """Lê a hash, salva no sessionStorage e força o Streamlit a recarregar com URL limpa."""
    components.html(
        """
        <script>
        (function() {
            // Verifica se a URL de retorno tem o token na hash
            if (window.location.hash && window.location.hash.includes("access_token=")) {
                const params = new URLSearchParams(window.location.hash.substring(1));
                const access = params.get("access_token");
                const url = new URL(window.location.href.split('#')[0]);
                
                if (access) {
                    // Salva o token para ser lido no próximo rerun do Python
                    sessionStorage.setItem('supabase_access_token', access); 
                    // Limpa a URL e força o navegador a recarregar (CRÍTICO)
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
    
    # Esta função é a causa do TypeError, mas é necessária no arquivo único.
    token = components.html(
        """
        <script>
            const token = sessionStorage.getItem('supabase_access_token');
            // Remove imediatamente para evitar loops
            if (token) {
                sessionStorage.removeItem('supabase_access_token');
            }
            return token; 
        </script>
        """,
        height=0,
        width=0,
        key="session_storage_reader_cleaner_final" 
    )
    
    return token if token else None

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

    # 1) MOVIMENTO DA HASH: Roda sempre para capturar o redirecionamento do Supabase
    st.write("PASSO 1: Rodando script JS de MOVIMENTO/SALVAMENTO (Verifica se há hash na URL).")
    mover_access_token_do_hash_para_session() 
    
    # 2) Bloco de Autenticação
    if "usuario" not in st.session_state:
        st.write("PASSO 2: Usuário não está na sessão. Iniciando checagem de login.")
        
        access_token = None
        
        # 2.1) LEITURA DO SESSION STORAGE (PRIMEIRA TENTATIVA)
        st.write("PASSO 2.1: Tentando ler o SESSION STORAGE.")
        access_token = obter_token_do_session_storage() 
            
        # 2.2) Leitura da QUERY STRING (Fallback)
        if not access_token:
            params = st.experimental_get_query_params()
            access_tokens_query = params.get("access_token")
            if access_tokens_query:
                access_token = access_tokens_query[0]

        
        # 3) Tenta obter o token
        if access_token:
            st.write(f"PASSO 3: Token encontrado. Iniciando validação.")
            
            if "login_processado" not in st.session_state:
                st.session_state["login_processado"] = True 
                
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
