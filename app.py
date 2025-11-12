import os
# ... (outras imports) ...
import streamlit as st
import streamlit.components.v1 as components

# =====================================================
# FUNÇÕES DE FLUXO E AUXILIARES (MANTER AS SUAS)
# =====================================================
# Mantenha suas funções de obter_user_supabase, sincronizar_usuario, etc.

def mover_access_token_do_hash_para_query():
    """Função JS para mover o token da # para a ? e forçar o RERUN."""
    # NÃO USAMOS KEY para evitar o TypeError.
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

# ... (outras funções auxiliares) ...

# =====================================================
# INTERFACE STREAMLIT (Lógica de autenticação FINAL)
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
