import os
import io
import tempfile
import json
from datetime import datetime
from urllib.parse import quote

import requests
import streamlit as st
from docx import Document
from openai import OpenAI
from supabase import create_client, Client
import pypandoc

# =====================================================
# CONFIGURAÇÕES GERAIS / INTEGRAÇÕES
# =====================================================

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
APP_BASE_URL = os.getenv("APP_BASE_URL")  # ex.: https://seu-app.streamlit.app  

# 🔍 DEBUG: Mostra configurações básicas (sem expor chaves!)
st.write("### 🛠️ Debug: Configurações iniciais")
st.write(f"`SUPABASE_URL` configurada: {'✅ Sim' if SUPABASE_URL else '❌ Não'}")
st.write(f"`SUPABASE_KEY` presente (tamanho): {'✅ ' + str(len(SUPABASE_KEY)) if SUPABASE_KEY else '❌ Não'}")
st.write(f"`APP_BASE_URL`: `{APP_BASE_URL or '❌ Não definida (usando localhost)'}`")
if SUPABASE_KEY and len(SUPABASE_KEY) > 30:
    st.write(f"`SUPABASE_KEY` (primeiros 10 chars): `{SUPABASE_KEY[:10]}...`")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.warning(
        "SUPABASE_URL e/ou SUPABASE_KEY não estão configuradas. "
        "Defina-as nos secrets do Streamlit (ou .streamlit/secrets.toml)."
    )
    supabase: Client | None = None
else:
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        st.success("✅ Cliente Supabase criado com sucesso")
    except Exception as e:
        st.exception("❌ Erro ao criar cliente Supabase")
        supabase = None

# =====================================================
# DEFINIÇÃO DAS ETAPAS
# =====================================================

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
    1: "Explique o problema, a demanda e o contexto que justificam a contratação.",
    2: "Liste os requisitos funcionais e não funcionais, requisitos legais e restrições.",
    3: "Descreva as pesquisas de mercado, fornecedores consultados, tecnologias existentes.",
    4: "Apresente a solução como um todo, de forma clara e compreensível para não técnicos.",
    5: "Estime as quantidades envolvidas (unidades, horas, licenças, etc.).",
    6: "Detalhe a metodologia de estimativa de valor (cotações, bancos de preços, etc.).",
    7: "Mostre como a contratação está alinhada ao PCA / planejamento institucional.",
    8: "Justifique o parcelamento ou a contratação em lote único, com base na legislação.",
    9: "Indique contratações relacionadas, dependências e impactos interdependentes.",
    10: "Identifique os riscos e as medidas de mitigação associadas à contratação.",
    11: "Justifique a escolha da solução em relação a alternativas e critérios adotados.",
    12: "Faça o resumo final e consolide as principais conclusões do ETP.",
}

INFOS_BASICAS_CAMPOS = [
    ("orgao", "Órgão / Entidade"),
    ("unidade", "Unidade Demandante"),
    ("processo", "Número do Processo"),
    ("responsavel", "Responsável pela Demanda"),
    ("objeto", "Objeto da Contratação (resumo)"),
]

# =====================================================
# FUNÇÕES DE BANCO (SUPABASE)
# =====================================================

def _check_db():
    if supabase is None:
        st.set_page_config(page_title="Ferramenta IA para ETP", layout="wide")
        st.error("Banco (Supabase) não configurado. Defina SUPABASE_URL e SUPABASE_KEY.")
        st.stop()

def listar_projetos():
    _check_db()
    resp = (
        supabase.table("projetos")
        .select("id, nome, criado_em")
        .order("criado_em", desc=True)
        .execute()
    )
    return resp.data or []

def obter_projeto(projeto_id: int):
    _check_db()
    resp = (
        supabase.table("projetos")
        .select("*")
        .eq("id", projeto_id)
        .single()
        .execute()
    )
    return resp.data

def criar_projeto(nome: str):
    _check_db()
    resp = supabase.table("projetos").insert({"nome": nome}).execute()
    return resp.data[0]["id"]

def excluir_projeto(projeto_id: int):
    _check_db()
    supabase.table("projetos").delete().eq("id", projeto_id).execute()

def atualizar_infos_basicas(projeto_id: int, dados: dict):
    _check_db()
    supabase.table("projetos").update(
        {
            "orgao": dados.get("orgao"),
            "unidade": dados.get("unidade"),
            "processo": dados.get("processo"),
            "responsavel": dados.get("responsavel"),
            "objeto": dados.get("objeto"),
        }
    ).eq("id", projeto_id).execute()

def carregar_etapa(projeto_id: int, numero: int):
    _check_db()
    resp = (
        supabase.table("etapas")
        .select("texto_final, sugestao_ia, titulo")
        .eq("projeto_id", projeto_id)
        .eq("numero", numero)
        .execute()
    )
    data = resp.data
    if data:
        row = data[0]
        return {
            "texto_final": row.get("texto_final") or "",
            "sugestao_ia": row.get("sugestao_ia") or "",
            "titulo": row.get("titulo") or dict(ETAPAS)[numero],
        }
    return {
        "texto_final": "",
        "sugestao_ia": "",
        "titulo": dict(ETAPAS)[numero],
    }

def salvar_etapa(projeto_id: int, numero: int, titulo: str, texto_final: str, sugestao_ia: str):
    _check_db()
    payload = {
        "projeto_id": projeto_id,
        "numero": numero,
        "titulo": titulo,
        "texto_final": texto_final,
        "sugestao_ia": sugestao_ia,
        "atualizado_em": datetime.utcnow().isoformat(),
    }
    resp = (
        supabase.table("etapas")
        .select("id")
        .eq("projeto_id", projeto_id)
        .eq("numero", numero)
        .execute()
    )
    if resp.data:
        supabase.table("etapas").update(payload).eq("projeto_id", projeto_id).eq("numero", numero).execute()
    else:
        supabase.table("etapas").insert(payload).execute()

def salvar_arquivo(projeto_id: int, numero_etapa: int, file):
    _check_db()
    supabase.table("arquivos").insert(
        {
            "projeto_id": projeto_id,
            "numero_etapa": numero_etapa,
            "nome_original": file.name,
            "storage_path": "",
            "upload_em": datetime.utcnow().isoformat(),
        }
    ).execute()

def listar_arquivos(projeto_id: int, numero_etapa: int):
    _check_db()
    resp = (
        supabase.table("arquivos")
        .select("id, nome_original")
        .eq("projeto_id", projeto_id)
        .eq("numero_etapa", numero_etapa)
        .order("upload_em", desc=True)
        .execute()
    )
    return resp.data or []

def carregar_textos_todas_etapas(projeto_id: int):
    _check_db()
    resp = (
        supabase.table("etapas")
        .select("numero, titulo, texto_final")
        .eq("projeto_id", projeto_id)
        .order("numero")
        .execute()
    )
    return resp.data or []

# =====================================================
# USUÁRIOS (LOGIN REAL COM GOOGLE via SUPABASE AUTH)
# =====================================================

def obter_usuario_por_email(email: str):
    _check_db()
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
    _check_db()
    resp = supabase.table("usuarios").insert(
        {
            "nome": nome,
            "sobrenome": sobrenome,
            "cpf": cpf,
            "email": email,
        }
    ).execute()
    return resp.data[0]

def gerar_google_auth_url():
    """Monta a URL de login do Supabase com Google."""
    if not SUPABASE_URL:
        return "#"

    redirect = APP_BASE_URL or "http://localhost:8501"
    redirect_enc = quote(redirect, safe="")
    url = f"{SUPABASE_URL}/auth/v1/authorize?provider=google&redirect_to={redirect_enc}"
    st.write(f"🔗 URL de autenticação gerada: `{url}`")
    return url

def obter_user_supabase(access_token: str):
    """Consulta a API Auth do Supabase para pegar dados do usuário logado."""
    if not access_token or not SUPABASE_URL or not SUPABASE_KEY:
        st.write("❌ obter_user_supabase: token ou credenciais ausentes")
        return None

    try:
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {access_token}",
        }
        st.write("📡 Chamando Supabase Auth API `/auth/v1/user`...")
        resp = requests.get(f"{SUPABASE_URL}/auth/v1/user", headers=headers, timeout=10)
        st.write(f"➡️ Status code: `{resp.status_code}`")
        st.write(f"➡️ Headers enviados (parcial): `Authorization: Bearer {access_token[:10]}...`")
        
        if resp.status_code == 200:
            user_json = resp.json()
            st.write("✅ Resposta 200: usuário recebido com sucesso")
            st.json({k: v for k, v in user_json.items() if k != "user_metadata"})  # oculta metadata longa
            if "user_metadata" in user_json:
                st.write(f"user_metadata keys: {list(user_json['user_metadata'].keys())}")
            return user_json
        else:
            st.error(f"❌ Erro na API Auth: `{resp.status_code}` — `{resp.text}`")
            return None
    except Exception as e:
        st.exception("💥 Exceção em `obter_user_supabase`")
        return None

def sincronizar_usuario(user_json: dict):
    if not user_json:
        st.write("❌ sincronizar_usuario: user_json vazio")
        return None

    email = user_json.get("email")
    meta = user_json.get("user_metadata") or {}
    nome_completo = meta.get("full_name") or meta.get("name") or ""
    partes = nome_completo.split(" ", 1)
    nome = partes[0] if partes else ""
    sobrenome = partes[1] if len(partes) > 1 else ""
    cpf = ""

    st.write(f"👤 Dados extraídos: nome=`{nome}`, sobrenome=`{sobrenome}`, email=`{email}`")

    existente = obter_usuario_por_email(email) if email else None
    if existente:
        st.write("✅ Usuário já existe no DB")
        return existente
    
    st.write("🆕 Criando novo usuário no banco...")
    novo = criar_usuario(nome, sobrenome, cpf, email)
    st.write("✅ Usuário criado com sucesso no banco")
    return novo

def tela_login_google():
    st.set_page_config(page_title="Ferramenta IA para ETP", layout="wide")

    st.title("Ferramenta Inteligente para Elaboração de ETP")
    st.subheader("Acesse com sua conta Google")

    st.write(
        "Para usar a ferramenta, faça login com sua conta Google. "
        "O processo é seguro e realizado via Supabase Auth."
    )

    # ✅ JavaScript para capturar #access_token e mover para ?access_token
    st.markdown(
        """
        <script>
        // Verifica se há token no fragment (ex: #access_token=abc)
        if (window.location.hash && window.location.hash.includes('access_token')) {
            const hash = window.location.hash.substring(1); // remove '#'
            const urlParams = new URLSearchParams(hash);
            const token = urlParams.get('access_token');
            if (token) {
                // Move para query params e recarrega
                const url = new URL(window.location);
                url.searchParams.set('access_token', token);
                url.hash = ''; // limpa o fragment
                window.history.replaceState(null, '', url);
                window.location.reload();
            }
        }
        </script>
        <button onclick="window.location.reload()">🔄 Forçar reload (depuração)</button>
        """,
        unsafe_allow_html=True,
    )

    auth_url = gerar_google_auth_url()
    st.link_button("🔐 Entrar com Google", auth_url)

    st.caption(
        "Ao clicar em \"Entrar com Google\", você será redirecionado para a página oficial "
        "do Google para login/autorização e, em seguida, voltará para esta aplicação."
    )

    # Mostra os query params atuais
    st.write("### 🔍 Query Params atuais:")
    st.json(dict(st.query_params))


# =====================================================
# [OUTRAS FUNÇÕES: IA, DOCX, PDF — mantidas sem debug pesado por brevidade]
# (Você pode reativar debug nelas se necessário)
# =====================================================

def gerar_texto_ia(
    numero_etapa: int,
    nome_etapa: str,
    orientacao: str,
    texto_existente: str,
    infos_basicas: dict,
    arquivos_etapa: list,
):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "⚠️ OPENAI_API_KEY não definida no ambiente. Configure a variável para usar a IA."

    client = OpenAI(api_key=api_key)

    arquivos_lista = (
        ", ".join(a["nome_original"] for a in arquivos_etapa)
        if arquivos_etapa
        else "nenhum arquivo enviado"
    )

    system_prompt = (
        "Você é uma IA especialista em elaboração de Estudos Técnicos Preliminares (ETP) "
        "para a Administração Pública brasileira. Gere textos claros, objetivos e alinhados "
        "à legislação de contratações públicas, com linguagem formal, mas compreensível.\n\n"
        "Siga sempre a estrutura solicitada para cada etapa e evite juridiquês excessivo."
    )

    user_prompt = f"""
Informações básicas do projeto:
- Órgão / Entidade: {infos_basicas.get('orgao') or '-'}
- Unidade Demandante: {infos_basicas.get('unidade') or '-'}
- Número do Processo: {infos_basicas.get('processo') or '-'}
- Responsável pela Demanda: {infos_basicas.get('responsavel') or '-'}
- Objeto da Contratação (resumo): {infos_basicas.get('objeto') or '-'}

Etapa do ETP que deve ser produzida:
- Número da etapa: {numero_etapa}
- Nome da etapa: {nome_etapa}

Orientações gerais desta etapa:
{orientacao}

Arquivos de referência enviados para esta etapa:
{arquivos_lista}

Texto atual (se houver) que o usuário já começou a escrever:
{texto_existente or '[sem texto prévio]'}

Tarefa:
Gere um texto completo para esta etapa do ETP, de forma estruturada, podendo usar parágrafos e listas se fizer sentido.
Não repita os títulos das seções da lei, apenas produza o texto final pronto para ser colado no documento.
    """.strip()

    try:
        response = client.responses.create(
            model="gpt-5",
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

        outputs = getattr(response, "output", None) or getattr(response, "outputs", None)
        if not outputs:
            return f"⚠️ A IA não retornou output.\nResposta bruta: {response}"

        partes = []
        for out in outputs:
            content_list = getattr(out, "content", None) or []
            for c in content_list:
                text_obj = getattr(c, "text", None)
                if not text_obj:
                    continue
                if hasattr(text_obj, "value") and text_obj.value:
                    partes.append(text_obj.value)
                elif isinstance(text_obj, str):
                    partes.append(text_obj)
                elif isinstance(text_obj, dict):
                    partes.append(text_obj.get("value") or text_obj.get("text") or "")

        texto = "\n".join([p for p in partes if p]).strip()
        if not texto:
            return f"⚠️ A IA não retornou texto.\nResposta bruta: {response}"
        return texto

    except Exception as e:
        return f"⚠️ Erro ao chamar a IA: {e}"

def gerar_docx_etp(projeto, etapas_rows):
    doc = Document()
    doc.add_heading("Estudo Técnico Preliminar – ETP", level=0)

    doc.add_heading("Informações Básicas", level=1)
    doc.add_paragraph(f"Órgão / Entidade: {projeto.get('orgao') or ''}")
    doc.add_paragraph(f"Unidade Demandante: {projeto.get('unidade') or ''}")
    doc.add_paragraph(f"Número do Processo: {projeto.get('processo') or ''}")
    doc.add_paragraph(f"Responsável pela Demanda: {projeto.get('responsavel') or ''}")
    doc.add_paragraph(f"Objeto da Contratação: {projeto.get('objeto') or ''}")

    for row in etapas_rows:
        numero = row["numero"]
        titulo = row["titulo"]
        texto_final = row.get("texto_final") or "[Texto ainda não preenchido]"
        doc.add_heading(f"Etapa {numero} – {titulo}", level=1)
        for par in texto_final.split("\n\n"):
            doc.add_paragraph(par)

    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer

def gerar_pdf_etp(projeto, etapas_rows):
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            docx_path = os.path.join(tmpdir, "etp_temp.docx")
            pdf_path = os.path.join(tmpdir, "etp_temp.pdf")

            docx_buffer = gerar_docx_etp(projeto, etapas_rows)
            with open(docx_path, "wb") as f:
                f.write(docx_buffer.getbuffer())

            pypandoc.convert_file(
                docx_path,
                "pdf",
                outputfile=pdf_path,
                extra_args=["--pdf-engine=wkhtmltopdf"],
            )

            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()

            buffer = io.BytesIO(pdf_bytes)
            buffer.seek(0)
            return buffer, None
    except Exception as e:
        return None, str(e)


# =====================================================
# INTERFACE STREAMLIT — COM DEBUG COMPLETO
# =====================================================

def main():
    st.set_page_config(page_title="🛠️ Debug Mode — Ferramenta IA para ETP", layout="wide")
    
    with st.expander("🔍 Estado da Sessão (st.session_state)", expanded=False):
        st.write(st.session_state)

    if supabase is None:
        st.error("SUPABASE_URL e SUPABASE_KEY não estão configuradas.")
        return

    st.title("🛠️ Modo Depuração: Login com Google")

    # 🔎 ETAPA 1: Verificar query params — agora procuramos por `code` OU `access_token`
    code = st.query_params.get("code")
    access_token = st.session_state.get("access_token")  # Podemos guardar na sessão

    # Normaliza
    if isinstance(code, list) and code:
        code = code[0]
    elif not isinstance(code, str):
        code = None

    st.write("### 🔎 ETAPA 1: Verificando parâmetros")
    st.write(f"`code` recebido: `{code[:20]}...`" if code else "❌ `code` não encontrado")
    st.write(f"`access_token` em sessão: `{'✅ Sim' if access_token else '❌ Não'}`")

    # 🔁 Se temos `code`, trocamos por `access_token`
    if code and not access_token:
        st.write("### 🔄 ETAPA 2: Trocando `code` por `access_token` via `/token`")
        
        redirect_uri = APP_BASE_URL or "http://localhost:8501"
        token_url = f"{SUPABASE_URL}/auth/v1/token?grant_type=authorization_code"

        payload = {
            "code": code,
            "redirect_uri": redirect_uri,
        }
        headers = {
            "apikey": SUPABASE_KEY,
            "Content-Type": "application/json",
        }

        try:
            st.write(f"📡 POST para: `{token_url}`")
            st.write(f"📦 Payload: `{{'code': '{code[:10]}...', 'redirect_uri': '{redirect_uri}'}}`")

            resp = requests.post(token_url, json=payload, headers=headers, timeout=10)
            st.write(f"➡️ Status: `{resp.status_code}`")
            if resp.status_code == 200:
                tokens = resp.json()
                new_access_token = tokens.get("access_token")
                st.write(f"✅ `access_token` obtido (primeiros 10 chars): `{new_access_token[:10]}...`")
                st.session_state["access_token"] = new_access_token
                st.session_state["refresh_token"] = tokens.get("refresh_token")
                st.toast("🔑 Token obtido com sucesso!", icon="✅")
                
                # Limpa o `code` da URL
                st.query_params.clear()
                st.rerun()
            else:
                st.error(f"❌ Erro ao trocar code por token: `{resp.status_code}`")
                st.code(resp.text)
                st.query_params.clear()  # evita loop
                return
        except Exception as e:
            st.exception("💥 Erro na chamada para `/token`")

    # ✅ Agora, com `access_token` na sessão, validamos o usuário
    access_token = st.session_state.get("access_token")
    if access_token:
        st.write("### ✅ ETAPA 3: Validando usuário com `access_token`")
        user_json = obter_user_supabase(access_token)
        if user_json:
            st.write("### ✅ ETAPA 4: Sincronizando usuário com banco")
            usuario = sincronizar_usuario(user_json)
            if usuario:
                st.session_state["usuario"] = usuario
                # Remove token da sessão (opcional, por segurança)
                # del st.session_state["access_token"]
                st.toast("🎉 Login bem-sucedido!", icon="✅")
                st.rerun()
            else:
                st.error("❌ Falha ao sincronizar usuário")
        else:
            st.error("❌ Falha ao obter usuário — token pode estar inválido")
            if "access_token" in st.session_state:
                del st.session_state["access_token"]
            st.rerun()

    # ❌ Nenhum token → exibe login
    st.write("### ❌ Nenhum token ativo → exibindo tela de login")
    tela_login_google()

if __name__ == "__main__":
    main()
