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

    if not APP_BASE_URL:
        redirect = "http://localhost:8501"
    else:
        redirect = APP_BASE_URL

    redirect_enc = quote(redirect, safe="")
    return f"{SUPABASE_URL}/auth/v1/authorize?provider=google&redirect_to={redirect_enc}"

def obter_user_supabase(access_token: str):
    """Consulta a API Auth do Supabase para pegar dados do usuário logado."""
    if not access_token or not SUPABASE_URL:
        return None

    try:
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {access_token}",
        }
        resp = requests.get(f"{SUPABASE_URL}/auth/v1/user", headers=headers, timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        return None

    return None

def sincronizar_usuario(user_json: dict):
    """
    Recebe o JSON retornado pelo /auth/v1/user,
    extrai nome/email e garante um registro em 'usuarios'.
    """
    if not user_json:
        return None

    email = user_json.get("email")
    meta = user_json.get("user_metadata") or {}
    nome_completo = meta.get("full_name") or meta.get("name") or ""
    partes = nome_completo.split(" ", 1)
    nome = partes[0] if partes else ""
    sobrenome = partes[1] if len(partes) > 1 else ""

    cpf = ""  # pode ser preenchido depois, se quiser

    existente = obter_usuario_por_email(email) if email else None
    if existente:
        return existente
    return criar_usuario(nome, sobrenome, cpf, email)

def tela_login_google():
    st.set_page_config(page_title="Ferramenta IA para ETP", layout="wide")

    st.title("Ferramenta Inteligente para Elaboração de ETP")
    st.subheader("Acesse com sua conta Google")

    st.write(
        "Para usar a ferramenta, faça login com sua conta Google. "
        "O processo é seguro e realizado via Supabase Auth."
    )

    auth_url = gerar_google_auth_url()
    st.link_button("🔐 Entrar com Google", auth_url)

    st.caption(
        "Ao clicar em \"Entrar com Google\", você será redirecionado para a página oficial "
        "do Google para login/autorização e, em seguida, voltará para esta aplicação."
    )


def mover_access_token_do_hash_para_query():
    """
    Se o Supabase retornar #access_token=..., este JS roda no browser,
    converte para ?access_token=... e recarrega a página.
    """
    components.html(
        """
        <script>
        (function() {
            try {
                if (window.location.hash && window.location.hash.includes("access_token=")) {
                    const params = new URLSearchParams(window.location.hash.substring(1));
                    const access = params.get("access_token");
                    if (access) {
                        const url = new URL(window.location.href);
                        // limpa o hash e adiciona o token como query param
                        url.hash = "";
                        url.searchParams.set("access_token", access);
                        window.location.replace(url.toString());
                    }
                }
            } catch (e) {
                console.error("Erro ao mover access_token do hash para query:", e);
            }
        })();
        </script>
        """,
        height=0,
    )



# =====================================================
# IA (GPT-5 via Responses API)
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

# =====================================================
# EXPORTAÇÃO DOCX / PDF
# =====================================================

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
    """Gera PDF a partir de um DOCX usando pandoc + wkhtmltopdf.
    Retorna (buffer_pdf, erro_str)."""
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
# INTERFACE STREAMLIT
# =====================================================

def main():
    # Supabase precisa estar configurado
    if supabase is None:
        st.set_page_config(page_title="Ferramenta IA para ETP", layout="wide")
        st.error("SUPABASE_URL e SUPABASE_KEY não estão configuradas.")
        return

    # >>> NOVO: converte #access_token=... para ?access_token=...
    mover_access_token_do_hash_para_query()

    # Autenticação com Google via Supabase
    if "usuario" not in st.session_state:
        params = st.experimental_get_query_params()
        access_tokens = params.get("access_token")

        if access_tokens:
            access_token = access_tokens[0]
            user_json = obter_user_supabase(access_token)
            usuario = sincronizar_usuario(user_json)

            if usuario:
                st.session_state["usuario"] = usuario
                # limpa a query string pra não ficar mostrando o token
                st.experimental_set_query_params()
            else:
                st.warning("Não foi possível validar o login. Tente novamente.")
                st.experimental_set_query_params()
                tela_login_google()
                return
        else:
            # não tem token na URL e não há usuário em sessão → mostra tela de login
            tela_login_google()
            return

    # daqui pra baixo você já TEM usuário logado
    usuario = st.session_state["usuario"]

    st.set_page_config(page_title="Ferramenta IA para ETP", layout="wide")

    st.title("Ferramenta Inteligente para Elaboração de ETP")

    # Info do usuário logado na sidebar
    st.sidebar.markdown(
        f"**Usuário:** {usuario.get('nome','')} {usuario.get('sobrenome','')}"
    )
    st.sidebar.markdown(f"*E-mail:* {usuario.get('email','')}")
    if st.sidebar.button("Sair"):
        st.session_state.clear()
        st.experimental_set_query_params()
        st.rerun()

    st.sidebar.header("Projetos de ETP")


    # Seleção / criação de projeto
    projetos = listar_projetos()
    options = ["(Novo projeto)"] + [f"{p['id']} - {p['nome']}" for p in projetos]
    escolha = st.sidebar.selectbox("Selecione o projeto", options)

    projeto_id = None
    if escolha == "(Novo projeto)":
        nome_novo = st.sidebar.text_input("Nome do novo projeto")
        if st.sidebar.button("Criar projeto") and nome_novo.strip():
            projeto_id = criar_projeto(nome_novo.strip())
            st.rerun()
    else:
        projeto_id = int(escolha.split(" - ")[0])

    if not projeto_id:
        st.info("Crie ou selecione um projeto de ETP na barra lateral para começar.")
        return

    projeto = obter_projeto(projeto_id)

    # Gerenciar projeto (excluir)
    if escolha != "(Novo projeto)":
        st.sidebar.markdown("### Gerenciar projeto")
        confirmar = st.sidebar.checkbox("Confirmar exclusão permanente", key="confirmar_exclusao")
        if st.sidebar.button("🗑️ Excluir projeto selecionado"):
            if confirmar:
                excluir_projeto(projeto_id)
                st.sidebar.success("Projeto removido com sucesso.")
                st.rerun()
            else:
                st.sidebar.warning("Marque a caixa de confirmação antes de excluir.")

    # Seleção de etapa
    st.sidebar.markdown("---")
    numero_etapa = st.sidebar.selectbox(
        "Etapa",
        [num for num, _ in ETAPAS],
        format_func=lambda n: f"{n} - {dict(ETAPAS)[n]}",
    )
    nome_etapa = dict(ETAPAS)[numero_etapa]
    orientacao = ORIENTACOES.get(numero_etapa, "")

    # Status da IA
    st.sidebar.markdown("---")
    st.sidebar.caption("Status da IA:")
    if os.getenv("OPENAI_API_KEY"):
        st.sidebar.success("OPENAI_API_KEY configurada")
    else:
        st.sidebar.error("OPENAI_API_KEY não configurada")

    col1, col2 = st.columns([1.2, 2.0])

    # COLUNA ESQUERDA: INFOS BÁSICAS + ARQUIVOS
    with col1:
        st.subheader("Informações básicas do projeto")

        dados_infos = {}
        for key, label in INFOS_BASICAS_CAMPOS:
            valor_atual = projeto.get(key) if projeto and projeto.get(key) is not None else ""
            dados_infos[key] = st.text_input(label, value=valor_atual, key=f"info_{key}")

        if st.button("Salvar informações básicas"):
            atualizar_infos_basicas(projeto_id, dados_infos)
            st.success("Informações básicas atualizadas com sucesso!")

        st.markdown("---")
        st.subheader(f"Arquivos da etapa {numero_etapa}")
        uploads = st.file_uploader(
            "Envie arquivos de orientações gerais ou ETPs de referência (PDF, DOCX, etc.)",
            accept_multiple_files=True,
            key=f"uploader_{numero_etapa}",
        )
        if uploads:
            for f in uploads:
                salvar_arquivo(projeto_id, numero_etapa, f)
            st.success("Arquivo(s) salvo(s) para esta etapa.")

        lista_arquivos = listar_arquivos(projeto_id, numero_etapa)
        if lista_arquivos:
            st.caption("Arquivos já cadastrados para esta etapa:")
            for arq in lista_arquivos:
                st.write(f"- {arq['nome_original']}")
        else:
            st.caption("Nenhum arquivo cadastrado ainda para esta etapa.")

    # COLUNA DIREITA: IA + TEXTO FINAL DA ETAPA
    with col2:
        st.subheader(f"Etapa {numero_etapa} de {len(ETAPAS)} – {nome_etapa}")

        with st.expander("Orientações gerais desta etapa", expanded=True):
            st.write(orientacao)

        dados_etapa = carregar_etapa(projeto_id, numero_etapa)

        key_sug = f"sugestao_ia_{projeto_id}_{numero_etapa}"
        key_txt = f"texto_final_{projeto_id}_{numero_etapa}"

        if key_sug not in st.session_state:
            st.session_state[key_sug] = dados_etapa.get("sugestao_ia", "") or ""
        if key_txt not in st.session_state:
            st.session_state[key_txt] = dados_etapa.get("texto_final", "") or ""

        st.markdown("#### Sugestão de texto pela IA")
        if st.button("Gerar sugestão com IA", key=f"btn_ia_{projeto_id}_{numero_etapa}"):
            arquivos_etapa = [
                {"nome_original": a["nome_original"]}
                for a in listar_arquivos(projeto_id, numero_etapa)
            ]
            sugestao = gerar_texto_ia(
                numero_etapa=numero_etapa,
                nome_etapa=nome_etapa,
                orientacao=orientacao,
                texto_existente=st.session_state[key_txt],
                infos_basicas={
                    "orgao": projeto.get("orgao"),
                    "unidade": projeto.get("unidade"),
                    "processo": projeto.get("processo"),
                    "responsavel": projeto.get("responsavel"),
                    "objeto": projeto.get("objeto"),
                }
                if projeto
                else {},
                arquivos_etapa=arquivos_etapa,
            )
            st.session_state[key_sug] = sugestao

        st.text_area(
            "Sugestão da IA (você pode editar ou aproveitar partes)",
            height=200,
            key=key_sug,
        )

        st.markdown("#### Texto final da etapa")
        st.text_area(
            "Texto final que será usado no documento do ETP",
            height=300,
            key=key_txt,
        )

        if st.button("Salvar etapa", key=f"btn_salvar_{projeto_id}_{numero_etapa}"):
            salvar_etapa(
                projeto_id=projeto_id,
                numero=numero_etapa,
                titulo=nome_etapa,
                texto_final=st.session_state[key_txt],
                sugestao_ia=st.session_state[key_sug],
            )
            st.success("Etapa salva com sucesso!")

    # EXPORTAÇÃO DOCX + PDF
    st.markdown("---")
    st.subheader("Exportar ETP completo")

    etapas_rows = carregar_textos_todas_etapas(projeto_id)
    if not etapas_rows:
        st.info("Preencha e salve pelo menos uma etapa para habilitar a exportação.")
        return

    col_docx, col_pdf = st.columns(2)

    with col_docx:
        if st.button("Gerar DOCX do ETP"):
            docx_buffer = gerar_docx_etp(projeto, etapas_rows)
            st.download_button(
                label="Baixar ETP em DOCX",
                data=docx_buffer,
                file_name=f"etp_projeto_{projeto_id}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

    with col_pdf:
        if st.button("Gerar PDF do ETP"):
            pdf_buffer, erro = gerar_pdf_etp(projeto, etapas_rows)
            if erro or pdf_buffer is None:
                st.error(
                    "Erro ao converter DOCX para PDF no servidor. "
                    "Baixe o DOCX e converta para PDF localmente no Word/LibreOffice.\n"
                    f"Detalhes técnicos: {erro}"
                )
            else:
                st.download_button(
                    label="Baixar ETP em PDF",
                    data=pdf_buffer,
                    file_name=f"etp_projeto_{projeto_id}.pdf",
                    mime="application/pdf",
                )

if __name__ == "__main__":
    main()
