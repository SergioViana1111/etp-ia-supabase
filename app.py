import os
import io
import tempfile
from datetime import datetime

import streamlit as st
from docx import Document
from openai import OpenAI
from supabase import create_client, Client
import pypandoc

# -----------------------
# CONFIGURAÇÕES GERAIS
# -----------------------

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# No Streamlit Cloud, defina em secrets.toml
if not SUPABASE_URL or not SUPABASE_KEY:
    # No desenvolvimento local, evitamos quebrar o app de cara
    st.warning("SUPABASE_URL e SUPABASE_KEY não estão configuradas. Defina-as em secrets ou variáveis de ambiente.")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

# -----------------------
# DEFINIÇÃO DAS ETAPAS
# -----------------------

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

# -----------------------
# FUNÇÕES DE BANCO (SUPABASE)
# -----------------------

def _check_db():
    if supabase is None:
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

# -----------------------
# IA (GPT-5 via Responses API)
# -----------------------

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

# -----------------------
# EXPORTAÇÃO DOCX / PDF
# -----------------------

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
    """Gera PDF a partir de um DOCX usando pypandoc.
    Se não for possível, retorna (None, mensagem_erro).
    """
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            docx_path = os.path.join(tmpdir, "etp_temp.docx")
            pdf_path = os.path.join(tmpdir, "etp_temp.pdf")

            docx_buffer = gerar_docx_etp(projeto, etapas_rows)
            with open(docx_path, "wb") as f:
                f.write(docx_buffer.getbuffer())

            try:
                pypandoc.convert_file(
                    docx_path,
                    "pdf",
                    outputfile=pdf_path,
                    extra_args=["--pdf-engine=wkhtmltopdf"],
                )
            except Exception:
                pypandoc.convert_file(
                    docx_path,
                    "pdf",
                    outputfile=pdf_path,
                )

            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()

            buffer = io.BytesIO(pdf_bytes)
            buffer.seek(0)
            return buffer, None
    except Exception as e:
        return None, str(e)

# -----------------------
# INTERFACE STREAMLIT
# -----------------------

def main():
    st.set_page_config(page_title="Ferramenta IA para ETP", layout="wide")

    st.title("Ferramenta Inteligente para Elaboração de ETP")

    st.sidebar.header("Projetos de ETP")

    # ----- Seleção / criação de projeto -----
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

    # ----- Gerenciar projeto (excluir) -----
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

    # ----- Seleção de etapa -----
    st.sidebar.markdown("---")
    numero_etapa = st.sidebar.selectbox(
        "Etapa",
        [num for num, _ in ETAPAS],
        format_func=lambda n: f"{n} - {dict(ETAPAS)[n]}",
    )
    nome_etapa = dict(ETAPAS)[numero_etapa]
    orientacao = ORIENTACOES.get(numero_etapa, "")

    # ----- Status da IA -----
    st.sidebar.markdown("---")
    st.sidebar.caption("Status da IA:")
    if os.getenv("OPENAI_API_KEY"):
        st.sidebar.success("OPENAI_API_KEY configurada")
    else:
        st.sidebar.error("OPENAI_API_KEY não configurada")

    col1, col2 = st.columns([1.2, 2.0])

    # =====================================================================
    # COLUNA ESQUERDA: INFOS BÁSICAS + ARQUIVOS
    # =====================================================================
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

    # =====================================================================
    # COLUNA DIREITA: IA + TEXTO FINAL DA ETAPA
    # =====================================================================
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

        sugestao_ia = st.text_area(
            "Sugestão da IA (você pode editar ou aproveitar partes)",
            height=200,
            key=key_sug,
        )

        st.markdown("#### Texto final da etapa")
        texto_final = st.text_area(
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

    # =====================================================================
    # EXPORTAÇÃO DOCX + PDF
    # =====================================================================
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
