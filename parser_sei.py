"""
parser_sei.py — Extração flexível e profissional de dados do Despacho SEI (PDF, HTML e ZIP)

Design: tenta múltiplos padrões por campo com busca multicamadas.
Suporta:
  - Arquivo PDF individual
  - Arquivo HTML individual de despacho
  - Arquivo ZIP do processo SEI completo (lê e consolida todos os despachos)
"""
import re
import os
import zipfile
import pdfplumber
from bs4 import BeautifulSoup


def _extrair_texto_pdf(file_path: str) -> str:
    """
    Extrai texto de PDF usando múltiplas estratégias.
    Fallback automático para PDFs do SEI com layout de colunas ou texto fragmentado.
    """
    with pdfplumber.open(file_path) as pdf:
        paginas = pdf.pages[:10]  # limita para evitar timeout
        
        # Estratégia 1: extract_text simples (funciona na maioria dos PDFs)
        textos_simples = []
        for page in paginas:
            t = page.extract_text() or ""
            textos_simples.append(t)
        texto_simples = "\n".join(textos_simples).strip()
        
        # Se o texto simples for razoável (>200 chars), usa direto
        if len(texto_simples) > 200:
            return texto_simples
        
        # Estratégia 2: extract_words — reconstrói o texto palavra a palavra
        # (mais robusto para PDFs com layout de coluna ou caixas de texto fragmentadas)
        print("⚠️ Texto simples muito curto, tentando extract_words...", flush=True)
        palavras_all = []
        for page in paginas:
            try:
                words = page.extract_words(x_tolerance=3, y_tolerance=3)
                if words:
                    # Ordena por posição Y depois X para reconstruir a ordem de leitura
                    words_sorted = sorted(words, key=lambda w: (round(w['top'] / 10), w['x0']))
                    linha_atual = []
                    y_anterior = None
                    for w in words_sorted:
                        y = round(w['top'] / 10)
                        if y_anterior is not None and y != y_anterior:
                            palavras_all.append(" ".join(linha_atual))
                            linha_atual = []
                        linha_atual.append(w['text'])
                        y_anterior = y
                    if linha_atual:
                        palavras_all.append(" ".join(linha_atual))
            except Exception as e:
                print(f"  extract_words falhou na página: {e}", flush=True)
        
        texto_words = "\n".join(palavras_all).strip()
        if len(texto_words) > len(texto_simples):
            return texto_words
        
        # Retorna o melhor resultado entre as duas estratégias
        return texto_simples or texto_words


def parsear_despacho(file_path: str) -> dict:
    """Função principal: aceita PDF, HTML ou ZIP de processo SEI."""
    ext = os.path.splitext(file_path)[1].lower()
    texto = ""

    try:
        if ext == ".zip":
            texto = _extrair_texto_zip(file_path)
        elif ext in (".html", ".htm"):
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                soup = BeautifulSoup(f.read(), "html.parser")
                texto = soup.get_text(" ")
        elif ext == ".pdf":
            texto = _extrair_texto_pdf(file_path)
        else:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                texto = f.read()
    except Exception as e:
        return {"texto": f"[Erro ao ler arquivo: {e}]", "campos": _campos_vazios()}

    # Normalizar espaços e caracteres invisíveis
    texto_norm = re.sub(r"\s+", " ", texto.replace("\xa0", " "))
    return _parsear_texto(texto_norm)


def _extrair_texto_zip(zip_path: str) -> str:
    """Extrai e consolida o texto de todos os despachos dentro de um arquivo ZIP do SEI."""
    textos = []
    with zipfile.ZipFile(zip_path, "r") as z:
        # Ordenar arquivos invertidos para que despachos mais recentes/finais venham primeiro
        names = sorted([n for n in z.namelist() if n.endswith((".html", ".htm", ".pdf"))], reverse=True)
        for n in names:
            try:
                data = z.read(n)
                if n.endswith((".html", ".htm")):
                    soup = BeautifulSoup(data, "html.parser")
                    t = soup.get_text(" ")
                    textos.append(t)
                elif n.endswith(".pdf"):
                    with pdfplumber.open(data) as pdf:
                        t = "\n".join(p.extract_text() or "" for p in pdf.pages)
                        textos.append(t)
            except Exception:
                continue
    return " \n ".join(textos)


def _parsear_texto(texto: str) -> dict:
    c = {}

    # ── Processo SEI ──────────────────────────────────────────────────────────
    m = re.search(r"\d{5}\.\d{6}/\d{4}-\d{2}", texto)
    c["processo_sei"] = _f("Processo SEI", m.group() if m else "", "alta" if m else "baixa")

    # ── NC(s) de referência ──────────────────────────────────────────────────
    ncs = list(dict.fromkeys(re.findall(r"\b\d{4}NC\d{5,6}\b", texto)))
    if not ncs:
        ncs_sei = list(dict.fromkeys(re.findall(r"(?:Nota de crédito|Despacho)\s*\((147\d{5,6})\)", texto, re.I)))
        if ncs_sei:
            ncs = [f"SEI-{n}" for n in ncs_sei]
    c["nc_referencia"] = {
        **_f("NC de Referência", ncs[0] if ncs else "", "alta" if ncs else "baixa"),
        "todas": ncs,
    }

    # ── Valor (R$) ────────────────────────────────────────────────────────────
    todos_vals = list(dict.fromkeys(re.findall(r"(?:R\s*)?\$\s*[\d\.]+(?:,\d{2})?", texto)))
    val = _extrair(texto, [
        r"(?:o\s+)?débito\s+de\s+(?:R\s*)?\$\s*([\d\.]+(?:,\d{2})?)",
        r"(?:o\s+)?crédito\s+de\s+(?:R\s*)?\$\s*([\d\.]+(?:,\d{2})?)",
        r"valor\s+de\s+(?:R\s*)?\$\s*([\d\.]+(?:,\d{2})?)",
        r"montante\s+de\s+(?:R\s*)?\$\s*([\d\.]+(?:,\d{2})?)",
        r"importância\s+de\s+(?:R\s*)?\$\s*([\d\.]+(?:,\d{2})?)",
        r"crédito.{0,30}?\$\s*([\d\.]+(?:,\d{2})?)",
    ])
    if not val and todos_vals:
        val = re.sub(r"(?:R\s*)?\$\s*", "", todos_vals[0])
    c["valor"] = {
        **_f("Valor (R$)", val, "alta" if _extrair(texto, [r"valor de (?:R\s*)?\$"]) else ("media" if val else "baixa")),
        "todos": [re.sub(r"(?:R\s*)?\$\s*", "", v) for v in todos_vals],
    }

    # ── Ação orçamentária ────────────────────────────────────────────────────
    acao_cod, acao_nome = "", ""
    for pat in [
        r"[Aa]ção\s+[Oo]rçament[aá]ria\s+([0-9A-Z]{4})\s*[-–]?\s*([^\n,\.]{0,100})",
        r"[Aa]ção\s+([0-9A-Z]{4})\s*[-–]\s*([^\n,\.]{3,100})",
        r"[Pp]rojeto/[Aa]tividade\s+([0-9A-Z]{4})",
        r"[Aa]ção\s+([0-9A-Z]{4})\b",
    ]:
        m = re.search(pat, texto)
        if m:
            acao_cod = m.group(1).strip()
            try:
                acao_nome = m.group(2).strip()
            except IndexError:
                acao_nome = ""
            break

    if acao_nome:
        # Remove sufixos como "- Nota de Crédito 2026NC...", "- Capacitação/PROCAP - Nota..."
        acao_nome = re.sub(r"\s*[-–]\s*(?:Nota|NC|SEI|Processo|Despacho|Empenho|Crédito|conforme).*", "", acao_nome, flags=re.I).strip()
        # Se o nome veio com "/" (ex: "Capacitação/PROCAP") e existe um padrão completo antes, limpa
        acao_nome = re.sub(r"^(\w+)/\w+$", r"\1", acao_nome).strip()
        # Remove texto após "(" que não faz parte do nome
        acao_nome = re.sub(r"\s*\(.*$", "", acao_nome).strip()

    c["acao_cod"] = _f("Código da Ação", acao_cod, "alta" if acao_cod else "baixa")
    c["acao_nome"] = _f("Nome da Ação", acao_nome.strip(), "media" if acao_nome else "baixa")

    # ── CNPJ / CPF ────────────────────────────────────────────────────────────
    cnpjs = list(dict.fromkeys(re.findall(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", texto)))
    cpfs  = list(dict.fromkeys(re.findall(r"\d{3}\.\d{3}\.\d{3}-\d{2}", texto)))
    c["cnpj"] = {
        **_f("CNPJ/CPF do Favorecido",
             cnpjs[0] if cnpjs else (cpfs[0] if cpfs else ""),
             "alta" if (cnpjs or cpfs) else "baixa"),
        "tipo": "CNPJ" if cnpjs else ("CPF" if cpfs else ""),
        "todos_cnpj": cnpjs,
    }

    # ── Favorecido ────────────────────────────────────────────────────────────
    fav = _extrair(texto, [
        r"(?:Lista\s+de\s+Credores|LC)\s*(?:no\s+SIAFI)?\s*([0-9A-Z]{12})",
        r"emissão\s+de\s+empenho\s+(?:em\s+favor\s+da?o?|ao?|à)\s+([A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ0-9\.\-\/ ]{5,120}?)(?=\s*\(|\s*,|\s*\.\s|\s*CNPJ|\s*CPF|$)",
        r"empenho\s+(?:em\s+favor\s+da?o?|ao?|à)\s+([A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ0-9\.\-\/ ]{5,120}?)(?=\s*\(|\s*,|\s*\.\s|\s*CNPJ|\s*CPF|$)",
        r"(?:contratad[ao]|fornecedor|empresa|pessoa|favorecido)\s*[:\-]?\s*([A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ0-9\.\-\/ ]{5,100}?)(?=\s*\(|\s*,|\s*\.\s|\s*CNPJ|\s*CPF|$)",
        r"para\s+a\s+UGR\s+d[ao]\s+([A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ0-9\.\-\/ ]{4,80})",
        r"para\s+o\s+Decanato\s+de\s+([A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ0-9\.\-\/ ]{4,80})",
    ])
    if re.match(r"20\d{2}LC\d{6}", fav, re.I):
        fav = f"LISTA DE CREDORES SIAFI {fav}"
    fav = re.sub(r"\s+(?:Nota|NC|SEI|Processo|conforme|atender|para|de|do|da)\s*$", "", fav, flags=re.I).strip()
    c["favorecido_nome"] = _f("Nome do Favorecido", fav.rstrip(". "), "media" if fav else "baixa")

    # ── Objeto ────────────────────────────────────────────────────────────
    # Prioridade: padrões que capturam o real propósito/finalidade da NC
    obj = _extrair(texto, [
        # 1. "com vistas à inscrição/participação/aquisição/..." (conteúdo real do objeto)
        r"com\s+vistas?\s+[àa]\s+((?:inscri(?:ção|cão)|participa(?:ção|cao)|aquisi(?:ção|cao)|contrata(?:ção|cao)|pagamento|execu(?:ção|cao)|realiza(?:ção|cao)|apoio|atendimento).{10,400}?)(?=\.\s|\.\n|,\s+(?:a\s+ser|conforme|instrução|Despacho)|$)",
        # 2. "com vistas a qualquer coisa" mais genérico
        r"com\s+vistas?\s+[àa]\s+(.{15,400}?)(?=\.\s|\.\n|,\s+(?:a\s+ser|conforme|instrução|Despacho)|$)",
        # 3. "visando a emissão de empenho" → captura o propósito após "para"
        r"visando\s+a\s+emissão\s+de\s+empenho.{0,100}?para\s+(.{15,300}?)(?=\.\s|\.\n|,\s+(?:a\s+ser|conforme)|$)",
        # 4. "visando o pagamento de..."
        r"visando\s+o\s+pagamento\s+d[ao]s?\s+(.{15,300}?)(?=\.\s|\.\n|,\s+conforme|assim,)",
        # 5. "visando a ..." genérico (excluindo "emissão de empenho")
        r"visando\s+(?!a\s+emiss)(.{15,300}?)(?=\.\s|\.\n|,\s+conforme|assim,)",
        # 6. "referente à/ao ..."
        r"referente\s+[àa]o?\s+(.{15,300}?)(?=\.\s|\.\n|conforme)",
        # 7. "solicito o detalhamento/remanejamento/... de crédito" → resto da frase
        r"solicito\s+(?:o\s+)?(?:detalhamento|remanejamento|transferência|descentralização)\s+de\s+crédito.{0,100}?(?:,|\s+da\s+Ação)\s+.{0,200}?(?:,\s+visando\s+|com\s+vistas)\s*(.{15,300}?)(?=\.\s|\.\n|,\s+conforme|$)",
        # 8. "objeto: ..."
        r"objeto\s*[:\-]\s*(.{15,400}?)(?=\.\s|\.\n)",
        # 9. "inscrição/participação/aquisição/contratação de ..."
        r"(?:inscrição|participação|aquisição|contratação)\s+de\s+(.{15,300}?)(?=\.\s|\.\n|conforme)",
        # 10. "finalidade: ..."
        r"finalidade\s*[:\-]\s*(.{15,300})",
        # 11. "autorizo/solicito ..." genérico
        r"(?:autorizo|solicito)\s+(.{15,400}?)(?=\.\s|\.\n)",
    ])
    obj = re.sub(r"\s+(?:Nota|NC|SEI|Processo|conforme|a\s+fim\s+de|para|-)\s*$", "", obj, flags=re.I).strip()
    c["objeto"] = _f("Objeto/Descrição", re.sub(r"\s+", " ", obj).strip()[:500] if obj else "", "media" if obj else "baixa")

    # ── Datas ─────────────────────────────────────────────────────────────────
    datas = list(dict.fromkeys(re.findall(r"\b\d{2}/\d{2}/\d{4}\b", texto)))
    c["data_despacho"] = {
        **_f("Data do Despacho", datas[-1] if datas else "", "alta" if datas else "baixa"),
        "todas": datas,
    }

    # ── Tipo NC (inferido) ────────────────────────────────────────────────────
    tipo = "detalhamento"
    if re.search(r"descentraliza", texto, re.I):
        if re.search(r"devolu", texto, re.I):
            tipo = "devolucao"
        elif re.search(r"anula", texto, re.I):
            tipo = "anulacao"
        elif not re.search(r"detalhamento", texto, re.I):
            tipo = "descentralizacao"
    c["tipo_nc"] = _f("Tipo de NC", tipo, "media")

    # ── Centro de Custo / Unidade Emissora ─────────────────────────────────────────────
    # Extrai o nome da unidade emissora ("Centro de custo: NOME") para apoiar o cruzamento de UGR
    centro_custo = _extrair(texto, [
        r"[Cc]entro\s+de\s+custo\s*:\s*([A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇa-záéíóúàâêîôûãõç \-,\.]{5,150}?)(?:\s*Para:|\s*\n|$)",
        r"[Dd]ecanato\s+de\s+([A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇa-z \-]{5,80}?)(?:\s*\-|\s*\n|$)",
    ])
    centro_custo = re.sub(r"\s*\-\s*$", "", centro_custo.strip()).strip()
    c["centro_custo"] = _f("Centro de Custo / Unidade", centro_custo, "media" if centro_custo else "baixa")

    # ── Fonte / Tipo de Crédito ────────────────────────────────────────────────────────────
    # Extrai o tipo de crédito mencionado ("Crédito para Unidades Administrativas/PF", etc.)
    fonte_credito = _extrair(texto, [
        r"(?:com\s+recursos\s+d[oa]|recursos\s+d[oa])\s+([A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇa-záéíóúàâêîôûãõç /\-,\.]{5,120}?)(?=,|\.|\s+autorizado|$)",
        r"[Cc]rédito\s+para\s+([A-Za-záéíóúàâêîôûãõç /\-]{5,80}?)(?=,|\.|\s+autorizado|$)",
    ])
    c["fonte_credito"] = _f("Tipo de Crédito", fonte_credito.strip(), "media" if fonte_credito else "baixa")

    return {"texto": texto[:5000], "campos": c}


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _f(label: str, valor: str, confianca: str) -> dict:
    return {"label": label, "valor": valor, "confianca": confianca}


def _extrair(texto: str, patterns: list) -> str:
    for pat in patterns:
        m = re.search(pat, texto, re.I | re.DOTALL)
        if m:
            try:
                return m.group(1).strip()
            except IndexError:
                return m.group(0).strip()
    return ""


def _campos_vazios() -> dict:
    return {
        k: _f(l, "", "baixa")
        for k, l in [
            ("processo_sei", "Processo SEI"),
            ("nc_referencia", "NC de Referência"),
            ("valor", "Valor (R$)"),
            ("acao_cod", "Código da Ação"),
            ("acao_nome", "Nome da Ação"),
            ("cnpj", "CNPJ/CPF do Favorecido"),
            ("favorecido_nome", "Nome do Favorecido"),
            ("objeto", "Objeto/Descrição"),
            ("data_despacho", "Data do Despacho"),
            ("tipo_nc", "Tipo de NC"),
        ]
    }
