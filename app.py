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

# ==========================
# CONFIG
# ==========================
SUPABASE_URL = os.getenv("SUPABASE_URL") or st.secrets.get("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or st.secrets.get("SUPABASE_KEY")
APP_BASE_URL = os.getenv("APP_BASE_URL") or st.secrets.get("APP_BASE_URL") or "https://etp-com-ia.streamlit.app"

if not SUPABASE_URL or not SUPABASE_KEY:
    st.set_page_config(page_title="Ferramenta ETP", layout="wide")
    st.error("SUPABASE_URL e/ou SUPABASE_KEY não configuradas.")
    st.stop()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================
# ETAPAS
# ==========================
ETAPAS = [
    (1, "Ajuste da Descrição da Necessidade de Contratação"),
    (2, "Requisitos da Contratação"),
    (3, "Levantamento de Mercado"),
    (4, "Descrição da solução como um todo"),
    (5, "Estimativa das quantidades"),
    (6, "Estimativa do valor da contratação"),
    (7, "Alinhamento da contratação com PCA"),
    (8, "Justificativa para o parcelamento ou não da contratação"),
    (9, "Contratações correlatas e/ou interdependentes"),
    (10, "Gestão de riscos / riscos envolvidos"),
    (11, "Justificativa da escolha da solução"),
    (12, "Providências finais / conclusão"),
]
ORIENTACOES = {
    1: "Explique o problema e o contexto que justificam a contratação.",
    2: "Liste os requisitos funcionais e não funcionais.",
    3: "Descreva as pesquisas de mercado e fornecedores consultados.",
    4: "Apresente a solução de forma clara para não técnicos.",
    5: "Estime quantidades envolvidas.",
    6: "Detalhe a metodologia de estimativa de valor.",
    7: "Mostre o alinhamento ao PCA.",
    8: "Justifique parcelamento ou contratação em lote.",
    9: "Indique contratações relacionadas e impactos.",
    10: "Identifique riscos e medidas de mitigação.",
    11: "Justifique a escolha da solução.",
    12: "Resumo final e conclusões do ETP.",
}
INFOS_BASICAS_CAMPOS = [
    ("orgao", "Órgão / Entidade"),
    ("unidade", "Unidade Demandante"),
    ("processo", "Número do Processo"),
    ("responsavel", "Responsável pela Demanda"),
    ("objeto", "Objeto da Contratação (resumo)"),
]

# ==========================
# DB (Supabase)
# ==========================
def listar_projetos():
    user_id = st.session_state.get("auth_user_id")
    if not user_id:
        return []
    return (
        supabase.table("projetos")
        .select("id, nome, criado_em")
        .eq("user_id", user_id)
        .order("criado_em", desc=True)
        .execute()
    ).data or []

def criar_projeto(nome: str):
    # Recupera o ID do usuário autenticado
    user_id = st.session_state.get("auth_user_id")
    if not user_id:
        # Tentativa de restaurar do token
        token = st.session_state.get("access_token")
        if token:
            user_json = obter_user_supabase(token)
            if user_json:
                user_id = user_json.get("id")
                st.session_state["auth_user_id"] = user_id
    if not user_id:
        st.error("Usuário não autenticado. Faça login novamente.")
        st.stop()

    # Inserção com user_id (RLS requer auth_token ativo)
    return (
        supabase.table("projetos")
        .insert({"nome": nome, "user_id": user_id})
        .execute()
    ).data[0]["id"]

def obter_projeto(projeto_id: int):
    return (
        supabase.table("projetos")
        .select("*")
        .eq("id", projeto_id)
        .single()
        .execute()
    ).data

def excluir_projeto(projeto_id: int):
    supabase.table("projetos").delete().eq("id", projeto_id).execute()

def atualizar_infos_basicas(projeto_id: int, dados: dict):
    supabase.table("projetos").update(dados).eq("id", projeto_id).execute()

def carregar_etapa(projeto_id: int, numero: int):
    resp = (
        supabase.table("etapas")
        .select("texto_final, sugestao_ia, titulo")
        .eq("projeto_id", projeto_id)
        .eq("numero", numero)
        .execute()
    ).data
    if resp:
        return resp[0]
    return {"texto_final": "", "sugestao_ia": "", "titulo": dict(ETAPAS)[numero]}

def salvar_etapa(projeto_id: int, numero: int, titulo: str, texto_final: str, sugestao_ia: str):
    payload = {
        "projeto_id": projeto_id,
        "numero": numero,
        "titulo": titulo,
        "texto_final": texto_final,
        "sugestao_ia": sugestao_ia,
        "atualizado_em": datetime.utcnow().isoformat(),
    }
    existe = (
        supabase.table("etapas")
        .select("id")
        .eq("projeto_id", projeto_id)
        .eq("numero", numero)
        .execute()
    ).data
    if existe:
        supabase.table("etapas").update(payload).eq("projeto_id", projeto_id).eq("numero", numero).execute()
    else:
        supabase.table("etapas").insert(payload).execute()

def salvar_arquivo(projeto_id: int, numero_etapa: int, file):
    supabase.table("arquivos").insert(
        {
            "projeto_id": projeto_id,
            "numero_etapa": numero_etapa,
            "nome_original": file.name,
            "upload_em": datetime.utcnow().isoformat(),
        }
    ).execute()

def listar_arquivos(projeto_id: int, numero_etapa: int):
    return (
        supabase.table("arquivos")
        .select("id, nome_original")
        .eq("projeto_id", projeto_id)
        .eq("numero_etapa", numero_etapa)
        .order("upload_em", desc=True)
        .execute()
    ).data or []

# ==========================
# AUTH HELPERS
# ==========================
def gerar_google_auth_url():
    redirect_enc = quote(APP_BASE_URL, safe="")
    return f"{SUPABASE_URL}/auth/v1/authorize?provider=google&redirect_to={redirect_enc}"

def obter_user_supabase(access_token: str):
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {access_token}"}
    r = requests.get(f"{SUPABASE_URL}/auth/v1/user", headers=headers, timeout=10)
    return r.json() if r.status_code == 200 else None

def tela_login_ou_cadastro():
    st.set_page_config(page_title="Login – Ferramenta ETP", layout="wide")
    st.title("Ferramenta Inteligente para Elaboração de ETP")

    components.html("""
    <script>
    (function(){
      var h = window.location.hash;
      if(h && h.indexOf("access_token=")>=0){
        var qs = h.substring(1);
        var base = window.location.origin + window.location.pathname;
        window.history.replaceState({}, "", base + "?" + qs);
        window.location.reload();
      }
    })();
    </script>
    """, height=0)

    tabs = st.tabs(["🔑 Entrar", "🆕 Cadastrar", "🔗 Google"])

    with tabs[0]:
        st.subheader("Entrar com e-mail e senha")
        email = st.text_input("E-mail", key="login_email")
        senha = st.text_input("Senha", type="password", key="login_senha")
        if st.button("Entrar"):
            try:
                res = supabase.auth.sign_in_with_password({"email": email, "password": senha})
                if res and res.session and res.session.access_token:
                    token = res.session.access_token
                    user_json = obter_user_supabase(token)
                    st.session_state["usuario"] = user_json
                    st.session_state["auth_user_id"] = user_json.get("id")
                    st.session_state["access_token"] = token
                    st.success("Login realizado!")
                    st.rerun()
                else:
                    st.error("E-mail, senha incorretos ou e-mail não confirmado.")
            except Exception as e:
                st.error(f"Erro: {e}")

    with tabs[1]:
        st.subheader("Criar nova conta")
        nome = st.text_input("Nome")
        email_cad = st.text_input("E-mail", key="cad_email")
        senha_cad = st.text_input("Senha", type="password", key="cad_senha")
        if st.button("Cadastrar"):
            try:
                supabase.auth.sign_up({
                    "email": email_cad,
                    "password": senha_cad,
                    "options": {"emailRedirectTo": APP_BASE_URL}
                })
                st.success("Conta criada! Confirme o e-mail antes de entrar.")
            except Exception as e:
                st.error(f"Erro ao cadastrar: {e}")

    with tabs[2]:
        st.subheader("Entrar com Google")
        st.link_button("🔐 Entrar com Google", gerar_google_auth_url())

# ==========================
# IA (OpenAI)
# ==========================
def gerar_texto_ia(numero_etapa, nome_etapa, orientacao, texto_existente, infos_basicas, arquivos_etapa):
    api_key = os.getenv("OPENAI_API_KEY") or st.secrets.get("OPENAI_API_KEY")
    if not api_key:
        return "⚠️ OPENAI_API_KEY não configurada."
    client = OpenAI(api_key=api_key)
    user_prompt = f"""
Etapa {numero_etapa} – {nome_etapa}
Orientações: {orientacao}
Texto atual: {texto_existente or '[vazio]'}
Arquivos: {', '.join(a['nome_original'] for a in arquivos_etapa) if arquivos_etapa else 'nenhum'}
"""
    r = client.responses.create(
        model="gpt-5",
        input=[{"role": "user", "content": user_prompt}]
    )
    out = r.output_text or ""
    return out.strip()

# ==========================
# EXPORT DOCX/PDF
# ==========================
def gerar_docx_etp(projeto, etapas_rows):
    doc = Document()
    doc.add_heading("Estudo Técnico Preliminar – ETP", level=0)
    for k, label in INFOS_BASICAS_CAMPOS:
        doc.add_paragraph(f"{label}: {projeto.get(k,'')}")
    for row in etapas_rows:
        doc.add_heading(f"Etapa {row['numero']} – {row['titulo']}", level=1)
        doc.add_paragraph(row.get("texto_final") or "")
    buf = io.BytesIO()
    doc.save(buf); buf.seek(0)
    return buf

# ==========================
# MAIN
# ==========================
def main():
    # Recupera token de query (callback Google)
    params = st.experimental_get_query_params()
    access_tokens = params.get("access_token")
    if "usuario" not in st.session_state and access_tokens:
        token = access_tokens[0]
        user_json = obter_user_supabase(token)
        if user_json:
            st.session_state["usuario"] = user_json
            st.session_state["auth_user_id"] = user_json.get("id")
            st.session_state["access_token"] = token
            st.experimental_set_query_params()

    # Se ainda não logou, mostra tela de login
    if "usuario" not in st.session_state:
        tela_login_ou_cadastro()
        return

    # 🔐 Garante que o token está ativo para RLS
    token = st.session_state.get("access_token")
    if token:
        supabase.postgrest.auth(token)
    else:
        st.warning("Sessão expirada. Faça login novamente.")
        st.session_state.clear()
        st.rerun()

    usuario = st.session_state["usuario"]
    user_id = st.session_state.get("auth_user_id")

    st.set_page_config(page_title="Ferramenta ETP", layout="wide")
    st.title("Ferramenta Inteligente para Elaboração de ETP")

    # Sidebar: usuário e logout
    st.sidebar.markdown(f"**Usuário:** {usuario.get('email','')}")
    if st.sidebar.button("Sair"):
        st.session_state.clear()
        st.experimental_set_query_params()
        st.rerun()

    # Sidebar: projetos
    st.sidebar.header("Projetos de ETP")
    projetos = listar_projetos()
    options = ["(Novo projeto)"] + [f"{p['id']} - {p['nome']}" for p in projetos]
    escolha = st.sidebar.selectbox("Selecione o projeto", options)

    projeto_id = None
    if escolha == "(Novo projeto)":
        nome_novo = st.sidebar.text_input("Nome do novo projeto")
        if st.sidebar.button("Criar projeto"):
            if not nome_novo.strip():
                st.warning("Informe o nome do projeto.")
            else:
                projeto_id = criar_projeto(nome_novo.strip())
                st.success("Projeto criado com sucesso!")
                st.rerun()
    else:
        projeto_id = int(escolha.split(" - ")[0])

    if not projeto_id:
        st.info("Crie ou selecione um projeto para começar.")
        return

    projeto = obter_projeto(projeto_id)

    # Etapas e conteúdos
    numero_etapa = st.sidebar.selectbox(
        "Etapa", [n for n, _ in ETAPAS],
        format_func=lambda n: f"{n} - {dict(ETAPAS)[n]}"
    )
    orientacao = ORIENTACOES.get(numero_etapa, "")
    dados_etapa = carregar_etapa(projeto_id, numero_etapa)

    # Layout principal
    col1, col2 = st.columns([1, 2])
    with col1:
        st.subheader("Informações básicas")
        dados_infos = {}
        for key, label in INFOS_BASICAS_CAMPOS:
            valor = projeto.get(key) or ""
            dados_infos[key] = st.text_input(label, value=valor, key=f"info_{key}")
        if st.button("Salvar informações básicas"):
            atualizar_infos_basicas(projeto_id, dados_infos)
            st.success("Informações salvas!")

    with col2:
        st.subheader(f"Etapa {numero_etapa}")
        st.caption(orientacao)
        st.text_area("Sugestão IA", key="sug", value=dados_etapa.get("sugestao_ia") or "", height=200)
        st.text_area("Texto Final", key="txt", value=dados_etapa.get("texto_final") or "", height=300)
        if st.button("Salvar Etapa"):
            salvar_etapa(projeto_id, numero_etapa, dict(ETAPAS)[numero_etapa],
                         st.session_state["txt"], st.session_state["sug"])
            st.success("Etapa salva!")

if __name__ == "__main__":
    main()
