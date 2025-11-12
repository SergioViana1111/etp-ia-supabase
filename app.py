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


# Converte o hash (#access_token=...) da PÁGINA PRINCIPAL para query (?access_token=...)
components.html('''
<script>
(function() {
  try {
    var w = window.parent || window.top || window; // <- pega a janela "de fora", não o iframe
    var h = w.location.hash || "";
    if (h && h.indexOf("access_token=") >= 0) {
      var qs = h.substring(1); // remove '#'
      // Reconstrói usando origin+pathname para não perder o host completo
      var base = w.location.origin + w.location.pathname;
      w.history.replaceState({}, "", base + "?" + qs);
      w.location.reload();
    }
  } catch (e) {
    console.warn("hash->query (parent) error", e);
  }
})();
</script>
''', height=0)

# ==========================
# CONFIG
# ==========================
SUPABASE_URL = os.getenv("SUPABASE_URL") or st.secrets.get("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or st.secrets.get("SUPABASE_KEY")
APP_BASE_URL = os.getenv("APP_BASE_URL") or st.secrets.get("APP_BASE_URL") or "http://localhost:8501"

if not SUPABASE_URL or not SUPABASE_KEY:
    st.set_page_config(page_title="Ferramenta ETP", layout="wide")
    st.error("SUPABASE_URL e/ou SUPABASE_KEY não configuradas.")
    st.stop()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================
# CONSTANTES: ETAPAS
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
    1: "Explique o problema, a demanda e o contexto que justificam a contratação.",
    2: "Liste os requisitos funcionais e não funcionais, requisitos legais e restrições.",
    3: "Descreva as pesquisas de mercado, fornecedores consultados, tecnologias existentes.",
    4: "Apresente a solução como um todo, de forma clara e compreensível para não técnicos.",
    5: "Estime as quantidades envolvidas (unidades, horas, licenças, etc.).",
    6: "Detalhe a metodologia de estimativa de valor (cotações, bancos de preços, etc.).",
    7: "Mostre como a contratação está alinhada ao PCA / planejamento institucional.",
    8: "Justifique o parcelamento ou a contratação em lote único, com base na legislação.",
    9: "Indique contratações relacionadas, dependências e impactos interdependentes.",
    10: "Identifique os riscos e as medidas de mitigação associados à contratação.",
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

# ==========================
# DB (Supabase)
# ==========================
def listar_projetos():
    return (
        supabase.table("projetos")
        .select("id, nome, criado_em")
        .order("criado_em", desc=True)
        .execute()
    ).data or []

def obter_projeto(projeto_id: int):
    return (
        supabase.table("projetos")
        .select("*")
        .eq("id", projeto_id)
        .single()
        .execute()
    ).data

def criar_projeto(nome: str):
    return supabase.table("projetos").insert({"nome": nome}).execute().data[0]["id"]

def excluir_projeto(projeto_id: int):
    supabase.table("projetos").delete().eq("id", projeto_id).execute()

def atualizar_infos_basicas(projeto_id: int, dados: dict):
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
    resp = (
        supabase.table("etapas")
        .select("texto_final, sugestao_ia, titulo")
        .eq("projeto_id", projeto_id)
        .eq("numero", numero)
        .execute()
    ).data
    if resp:
        row = resp[0]
        return {
            "texto_final": row.get("texto_final") or "",
            "sugestao_ia": row.get("sugestao_ia") or "",
            "titulo": row.get("titulo") or dict(ETAPAS)[numero],
        }
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
        .eq("projeto_id", projeto_id).eq("numero", numero)
        .execute()
    ).data
    if existe:
        supabase.table("etapas").update(payload).eq("projeto_id", projeto_id).eq("numero", numero).execute()
    else:
        supabase.table("etapas").insert(payload).execute()

def salvar_arquivo(projeto_id: int, numero_etapa: int, file):
    supabase.table("arquivos").insert(
        {"projeto_id": projeto_id, "numero_etapa": numero_etapa, "nome_original": file.name, "storage_path": "", "upload_em": datetime.utcnow().isoformat()}
    ).execute()

def listar_arquivos(projeto_id: int, numero_etapa: int):
    return (
        supabase.table("arquivos")
        .select("id, nome_original")
        .eq("projeto_id", projeto_id).eq("numero_etapa", numero_etapa)
        .order("upload_em", desc=True)
        .execute()
    ).data or []

def obter_usuario_por_email(email: str):
    data = (
        supabase.table("usuarios")
        .select("*")
        .eq("email", email)
        .limit(1)
        .execute()
    ).data or []
    return data[0] if data else None

def criar_usuario(nome: str, sobrenome: str, cpf: str, email: str):
    return supabase.table("usuarios").insert(
        {"nome": nome, "sobrenome": sobrenome, "cpf": cpf, "email": email}
    ).execute().data[0]

def sincronizar_usuario_google(user_json: dict):
    if not user_json:
        return None
    email = user_json.get("email")
    meta = user_json.get("user_metadata") or {}
    nome_completo = meta.get("full_name") or meta.get("name") or ""
    partes = nome_completo.split(" ", 1)
    nome = partes[0] if partes else ""
    sobrenome = partes[1] if len(partes) > 1 else ""
    existente = obter_usuario_por_email(email) if email else None
    return existente or criar_usuario(nome, sobrenome, "", email)

# ==========================
# AUTH HELPERS
# ==========================
def gerar_google_auth_url():
    redirect_enc = quote(APP_BASE_URL, safe="")
    return f"{SUPABASE_URL}/auth/v1/authorize?provider=google&redirect_to={redirect_enc}"

def obter_user_supabase(access_token: str):
    try:
        headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {access_token}"}
        r = requests.get(f"{SUPABASE_URL}/auth/v1/user", headers=headers, timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception:
        return None
    return None

def script_converter_hash_para_query():
    st.markdown(
        """
        <script>
        (function() {
            if (window.location.hash && window.location.hash.includes("access_token=")) {
                const params = new URLSearchParams(window.location.hash.substring(1));
                const access = params.get("access_token");
                if (access) {
                    const newUrl = window.location.origin + window.location.pathname + "?access_token=" + encodeURIComponent(access);
                    window.location.replace(newUrl);
                }
            }
        })();
        </script>
        """,
        unsafe_allow_html=True,
    )

# ==========================
# IA (GPT-5 Responses API)
# ==========================
def gerar_texto_ia(numero_etapa, nome_etapa, orientacao, texto_existente, infos_basicas, arquivos_etapa):
    api_key = os.getenv("OPENAI_API_KEY") or st.secrets.get("OPENAI_API_KEY")
    if not api_key:
        return "⚠️ OPENAI_API_KEY não definida."
    client = OpenAI(api_key=api_key)

    arquivos_lista = ", ".join(a["nome_original"] for a in arquivos_etapa) if arquivos_etapa else "nenhum arquivo enviado"

    system_prompt = (
        "Você é uma IA especialista em elaboração de ETP para a Administração Pública brasileira. "
        "Gere textos claros, objetivos e alinhados à legislação de contratações públicas."
    )
    user_prompt = f"""
Informações básicas:
- Órgão: {infos_basicas.get('orgao') or '-'}
- Unidade: {infos_basicas.get('unidade') or '-'}
- Processo: {infos_basicas.get('processo') or '-'}
- Responsável: {infos_basicas.get('responsavel') or '-'}
- Objeto: {infos_basicas.get('objeto') or '-'}

Etapa: {numero_etapa} – {nome_etapa}
Orientações: {orientacao}

Arquivos de referência: {arquivos_lista}

Texto atual do usuário (se houver):
{texto_existente or '[vazio]'}

Tarefa: gere o texto final desta etapa, pronto para uso no ETP.
"""
    try:
        r = client.responses.create(
            model="gpt-5",
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        outs = getattr(r, "output", None) or getattr(r, "outputs", None)
        if not outs:
            return f"⚠️ A IA não retornou output.\nResposta bruta: {r}"
        partes = []
        for o in outs:
            for c in getattr(o, "content", []) or []:
                t = getattr(c, "text", None)
                if hasattr(t, "value") and t.value:
                    partes.append(t.value)
                elif isinstance(t, str):
                    partes.append(t)
                elif isinstance(t, dict):
                    partes.append(t.get("value") or t.get("text") or "")
        texto = "\n".join([p for p in partes if p]).strip()
        return texto or f"⚠️ A IA não retornou texto.\nResposta bruta: {r}"
    except Exception as e:
        return f"⚠️ Erro ao chamar a IA: {e}"

# ==========================
# EXPORT DOCX / PDF
# ==========================
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
    buf = io.BytesIO()
    doc.save(buf); buf.seek(0)
    return buf

def gerar_pdf_etp(projeto, etapas_rows):
    try:
        with tempfile.TemporaryDirectory() as tmp:
            docx_path = os.path.join(tmp, "etp.docx")
            pdf_path = os.path.join(tmp, "etp.pdf")
            with open(docx_path, "wb") as f:
                f.write(gerar_docx_etp(projeto, etapas_rows).getbuffer())
            pypandoc.convert_file(docx_path, "pdf", outputfile=pdf_path, extra_args=["--pdf-engine=wkhtmltopdf"])
            with open(pdf_path, "rb") as f:
                b = f.read()
            out = io.BytesIO(b); out.seek(0)
            return out, None
    except Exception as e:
        return None, str(e)

# ==========================
# TELAS DE AUTENTICAÇÃO
# ==========================
def tela_login_ou_cadastro():
    st.set_page_config(page_title="Login – Ferramenta ETP", layout="wide")
    st.title("Ferramenta Inteligente para Elaboração de ETP")
    st.subheader("Acesse sua conta")

    # Converte #access_token -> ?access_token
    script_converter_hash_para_query()

    tabs = st.tabs(["🔑 Entrar", "🆕 Cadastrar", "🔗 Entrar com Google"])

    # --------- ENTRAR (email/senha)
    with tabs[0]:
        st.write("Entre com e-mail e senha (Supabase Auth).")
        email = st.text_input("E-mail", key="login_email")
        senha = st.text_input("Senha", type="password", key="login_senha")
        if st.button("Entrar"):
            try:
                res = supabase.auth.sign_in_with_password({"email": email, "password": senha})
                if res and res.session and res.session.access_token:
                    token = res.session.access_token
                    user_json = obter_user_supabase(token)
                    usuario = sincronizar_usuario_google(user_json)  # reaproveitamos a mesma normalização
                    if usuario:
                        st.session_state["usuario"] = usuario
                        st.experimental_set_query_params()
                        st.success("Login realizado!")
                        st.rerun()
                    else:
                        st.error("Não foi possível obter os dados do usuário.")
                else:
                    st.error("Falha no login. Verifique as credenciais.")
            except Exception as e:
                st.error(f"Erro ao autenticar: {e}")

    # --------- CADASTRAR (email/senha)
    with tabs[1]:
        st.write("Crie sua conta com e-mail e senha.")
        nome = st.text_input("Nome")
        sobrenome = st.text_input("Sobrenome")
        email_cad = st.text_input("E-mail", key="cad_email")
        senha_cad = st.text_input("Senha", type="password", key="cad_senha")
        if st.button("Cadastrar"):
            try:
                res = supabase.auth.sign_up({"email": email_cad, "password": senha_cad,
                                             "options": {"data": {"full_name": f"{nome} {sobrenome}".strip()}}})
                if res and res.user:
                    # cria/atualiza nosso registro local
                    existente = obter_usuario_por_email(email_cad)
                    if not existente:
                        criar_usuario(nome, sobrenome, "", email_cad)
                    st.success("Cadastro criado! Verifique seu e-mail se a confirmação estiver habilitada.")
                else:
                    st.error("Não foi possível criar a conta. Verifique os dados.")
            except Exception as e:
                st.error(f"Erro ao cadastrar: {e}")

    # --------- GOOGLE
    with tabs[2]:
        st.write("Ou entre com sua conta Google.")
        auth_url = gerar_google_auth_url()
        st.link_button("🔐 Entrar com Google", auth_url)
        with st.expander("Ver URL de autenticação (debug)"):
            st.code(auth_url)

# ==========================
# APP
# ==========================
def main():
    # Autenticação
    if "usuario" not in st.session_state:
        # Se voltou com ?access_token=..., autentica via token
        params = st.experimental_get_query_params()
        access_tokens = params.get("access_token")
        if access_tokens:
            token = access_tokens[0]
            user_json = obter_user_supabase(token)
            usuario = sincronizar_usuario_google(user_json)
            if usuario:
                st.session_state["usuario"] = usuario
                st.experimental_set_query_params()  # limpa token
            else:
                st.warning("Não foi possível validar o login. Tente novamente.")
                st.experimental_set_query_params()
                tela_login_ou_cadastro()
                return
        else:
            tela_login_ou_cadastro()
            return

    usuario = st.session_state["usuario"]

    st.set_page_config(page_title="Ferramenta ETP", layout="wide")
    st.title("Ferramenta Inteligente para Elaboração de ETP")

    # Sidebar: usuário
    st.sidebar.markdown(f"**Usuário:** {usuario.get('nome','')} {usuario.get('sobrenome','')}")
    st.sidebar.caption(usuario.get("email",""))
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
        if st.sidebar.button("Criar projeto") and nome_novo.strip():
            projeto_id = criar_projeto(nome_novo.strip())
            st.rerun()
    else:
        projeto_id = int(escolha.split(" - ")[0])

    if not projeto_id:
        st.info("Crie ou selecione um projeto de ETP na barra lateral para começar.")
        return

    projeto = obter_projeto(projeto_id)

    # Excluir projeto
    if escolha != "(Novo projeto)":
        st.sidebar.markdown("### Gerenciar projeto")
        confirmar = st.sidebar.checkbox("Confirmar exclusão permanente", key="confirmar_exclusao")
        if st.sidebar.button("🗑️ Excluir projeto selecionado"):
            if confirmar:
                excluir_projeto(projeto_id)
                st.sidebar.success("Projeto removido.")
                st.rerun()
            else:
                st.sidebar.warning("Marque a caixa de confirmação antes de excluir.")

    # Seleção de etapa
    st.sidebar.markdown("---")
    numero_etapa = st.sidebar.selectbox(
        "Etapa", [num for num, _ in ETAPAS],
        format_func=lambda n: f"{n} - {dict(ETAPAS)[n]}",
    )
    nome_etapa = dict(ETAPAS)[numero_etapa]
    orientacao = ORIENTACOES.get(numero_etapa, "")

    # Status da IA
    st.sidebar.markdown("---")
    st.sidebar.caption("Status da IA:")
    if os.getenv("OPENAI_API_KEY") or st.secrets.get("OPENAI_API_KEY"):
        st.sidebar.success("OPENAI_API_KEY configurada")
    else:
        st.sidebar.error("OPENAI_API_KEY não configurada")

    col1, col2 = st.columns([1.2, 2.0])

    # Coluna esquerda: infos + arquivos
    with col1:
        st.subheader("Informações básicas do projeto")
        dados_infos = {}
        for key, label in INFOS_BASICAS_CAMPOS:
            valor_atual = projeto.get(key) if projeto and projeto.get(key) is not None else ""
            dados_infos[key] = st.text_input(label, value=valor_atual, key=f"info_{key}")
        if st.button("Salvar informações básicas"):
            atualizar_infos_basicas(projeto_id, dados_infos)
            st.success("Informações atualizadas!")

        st.markdown("---")
        st.subheader(f"Arquivos da etapa {numero_etapa}")
        uploads = st.file_uploader("Envie arquivos (PDF, DOCX, etc.)", accept_multiple_files=True, key=f"uploader_{numero_etapa}")
        if uploads:
            for f in uploads:
                salvar_arquivo(projeto_id, numero_etapa, f)
            st.success("Arquivo(s) salvo(s).")

        lista_arquivos = listar_arquivos(projeto_id, numero_etapa)
        if lista_arquivos:
            st.caption("Arquivos cadastrados:")
            for arq in lista_arquivos:
                st.write(f"- {arq['nome_original']}")
        else:
            st.caption("Nenhum arquivo cadastrado ainda.")

    # Coluna direita: IA + texto final
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
            arquivos_etapa = [{"nome_original": a["nome_original"]} for a in listar_arquivos(projeto_id, numero_etapa)]
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
                } if projeto else {},
                arquivos_etapa=arquivos_etapa,
            )
            st.session_state[key_sug] = sugestao

        st.text_area("Sugestão da IA (edite se quiser)", height=200, key=key_sug)

        st.markdown("#### Texto final da etapa")
        st.text_area("Texto final que será usado no documento do ETP", height=300, key=key_txt)

        if st.button("Salvar etapa", key=f"btn_salvar_{projeto_id}_{numero_etapa}"):
            salvar_etapa(projeto_id, numero_etapa, nome_etapa, st.session_state[key_txt], st.session_state[key_sug])
            st.success("Etapa salva com sucesso!")

    # Exportação
    st.markdown("---")
    st.subheader("Exportar ETP completo")
    etapas_rows = (
        supabase.table("etapas")
        .select("numero, titulo, texto_final")
        .eq("projeto_id", projeto_id)
        .order("numero")
        .execute()
    ).data or []
    if not etapas_rows:
        st.info("Preencha e salve pelo menos uma etapa para habilitar a exportação.")
        return

    col_docx, col_pdf = st.columns(2)
    with col_docx:
        if st.button("Gerar DOCX do ETP"):
            buf = gerar_docx_etp(projeto, etapas_rows)
            st.download_button("Baixar ETP em DOCX", data=buf, file_name=f"etp_projeto_{projeto_id}.docx",
                               mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    with col_pdf:
        if st.button("Gerar PDF do ETP"):
            pdf_buf, err = gerar_pdf_etp(projeto, etapas_rows)
            if err or pdf_buf is None:
                st.error("Erro ao converter DOCX para PDF no servidor. Baixe o DOCX e converta localmente.\n" + str(err))
            else:
                st.download_button("Baixar ETP em PDF", data=pdf_buf, file_name=f"etp_projeto_{projeto_id}.pdf", mime="application/pdf")

if __name__ == "__main__":
    main()
