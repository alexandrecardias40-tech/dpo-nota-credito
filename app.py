"""
app.py — Servidor Flask do Sistema de Notas de Crédito UnB/DPO

Novidades:
  - Planilha base embutida em data/planilha_base.xlsx (carregada no boot)
  - /api/processar-pdf já devolve sugestão de células automaticamente
  - Upload de planilha é OPCIONAL (substitui a base embutida)
"""
import os
from flask import Flask, render_template, request, jsonify, send_file

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR  = os.path.join(BASE_DIR, "uploads")
PLANILHA_BASE = os.path.join(BASE_DIR, "data", "planilha_base.xlsx")
os.makedirs(UPLOAD_DIR, exist_ok=True)

_planilha_cache: list = []


# ── Carregar planilha base no boot ────────────────────────────────────────────
def _boot_planilha():
    global _planilha_cache
    if os.path.exists(PLANILHA_BASE):
        from parser_planilha import carregar_planilha
        try:
            _planilha_cache = carregar_planilha(PLANILHA_BASE)
            print(f"  📊 Planilha base carregada: {len(_planilha_cache)} linhas")
        except Exception as e:
            print(f"  ⚠️  Erro ao carregar planilha base: {e}")
    else:
        print("  ℹ️  Planilha base não encontrada em data/planilha_base.xlsx")

_boot_planilha()


# ── Página principal ──────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


# ── Status da planilha ────────────────────────────────────────────────────────
@app.route("/api/status-planilha")
def status_planilha():
    return jsonify({
        "ok": True,
        "carregada": bool(_planilha_cache),
        "total": len(_planilha_cache),
        "fonte": "base embutida" if os.path.exists(PLANILHA_BASE) else "nenhuma",
    })


# ── Processar PDF + cruzar planilha ──────────────────────────────────────────
@app.route("/api/processar-pdf", methods=["POST"])
def processar_pdf():
    if "pdf" not in request.files:
        return jsonify({"ok": False, "erro": "Arquivo não enviado"}), 400

    f = request.files["pdf"]
    ext = os.path.splitext(f.filename)[1].lower() or ".pdf"
    path = os.path.join(UPLOAD_DIR, f"despacho_temp{ext}")
    f.save(path)

    from parser_sei import parsear_despacho
    try:
        resultado = parsear_despacho(path)
    except Exception as e:
        return jsonify({"ok": False, "erro": str(e)}), 500

    # ── Cruzamento automático com planilha ────────────────────────────────────
    sugestao = None
    if _planilha_cache:
        acao  = resultado["campos"].get("acao_cod", {}).get("valor", "")
        valor = resultado["campos"].get("valor", {}).get("valor", "")
        fav   = resultado["campos"].get("favorecido_nome", {}).get("valor", "")
        obj   = resultado["campos"].get("objeto", {}).get("valor", "")

        # Fallback 1: Se GECC, PROCAP ou Crédito para Unidades Administrativas → força Ação 20RK (Funcionamento IFEs)
        # Esses despachos raramente mencionam o código da ação explicitamente
        if not acao:
            obj_up  = obj.upper()
            fav_up  = fav.upper()
            fc_up   = resultado["campos"].get("fonte_credito", {}).get("valor", "").upper()
            if any(k in obj_up for k in ("GECC", "GRATIFICAC", "ENCARGO DE CURSO", "ENCARGO DE CONCURSO",
                                          "UNIDADES ADMINISTRATIVAS", "CREDITOS DISTRIBUIDOS")):
                acao = "20RK"
                resultado["campos"]["acao_cod"]  = {"label": "Código da Ação", "valor": acao, "confianca": "media"}
                resultado["campos"]["acao_nome"] = {"label": "Nome da Ação", "valor": "FUNCIONAMENTO DE INSTITUICOES FEDERAIS DE ENSINO SUPERIOR", "confianca": "media"}
            elif "UNIDADES ADMINISTRATIVAS" in fc_up or "CREDITO PARA UNIDADES" in fc_up:
                acao = "20RK"
                resultado["campos"]["acao_cod"]  = {"label": "Código da Ação", "valor": acao, "confianca": "media"}
                resultado["campos"]["acao_nome"] = {"label": "Nome da Ação", "valor": "FUNCIONAMENTO DE INSTITUICOES FEDERAIS DE ENSINO SUPERIOR", "confianca": "media"}

        # Fallback 2: busca textual genérica na planilha por Favorecido/PI/UGR
        if not acao:
            for term in (fav, obj):
                if not term or len(term) < 3:
                    continue
                words = [w for w in term.upper().replace("/", " ").replace("-", " ").split()
                         if len(w) >= 4 and w not in ("PARA", "DECANATO", "REMANEJAMENTO", "RECURSOS",
                                                        "NOTA", "CREDITO", "VALOR", "REAIS", "DEBITO",
                                                        "UNIDADES", "ADMINISTRATIVAS", "PAGAMENTO",
                                                        "EMISSAO", "EMISSÃO", "EMPENHO", "CURSO")]
                for w in words:
                    match_row = next((r for r in _planilha_cache
                                      if w in r.get("ugr_nome", "").upper()
                                      or w in r.get("pi_nome", "").upper()
                                      or w in r.get("acao_nome", "").upper()), None)
                    if match_row:
                        acao = match_row["acao"]
                        resultado["campos"]["acao_cod"]  = {"label": "Código da Ação", "valor": acao, "confianca": "media"}
                        resultado["campos"]["acao_nome"] = {"label": "Nome da Ação", "valor": match_row["acao_nome"], "confianca": "media"}
                        break
                if acao:
                    break

        # Identificar dicas semânticas do despacho para escolha precisa da linha
        nd_hint, ugr_hint, pi_hint = "", "", ""
        txt_full = (str(obj) + " " + str(fav)).lower()

        # Extrai centro de custo e tipo de crédito detectados pelo parser
        centro = resultado["campos"].get("centro_custo", {}).get("valor", "").upper()
        fonte_cred = resultado["campos"].get("fonte_credito", {}).get("valor", "").upper()

        # ── Mapeamento Semântico de PI/UGR por tipo de despesa ───────────────────
        if any(k in txt_full for k in ("estagiár", "estagiar", "estágio", "estagio")):
            # Estagiários: crédito centralizado na DOR para redistribuição por demanda
            nd_hint  = "339000"
            ugr_hint = "152371"
            pi_hint  = "VGY01N0118N"

        elif any(k in txt_full for k in ("bolsa", "auxílio financeiro", "auxiliar financeiro", "estudante", "cuc")):
            # Bolsas/auxílios DEX
            nd_hint  = "339018"
            ugr_hint = "154153"
            pi_hint  = "MXX01G21C4N"

        elif any(k in txt_full for k in ("gecc", "gratificaç", "gratificac", "encargo de curso", "encargo de concurso")):
            # GECC - Gratificação por Encargo de Curso ou Concurso
            # Origem: 230639 / 1050A000AP / PI VGY01N0105N / ND 339000 — na UGR da unidade solicitante
            nd_hint  = "339000"
            pi_hint  = "VGY01N0105N"
            # Tenta identificar a UGR pela unidade emissora (centro de custo)
            if "DPO" in centro or "PLANEJAMENTO" in centro or "ORCAMENTO" in centro:
                ugr_hint = "152387"
            elif "DAF" in centro or "ADMINISTRACAO" in centro or "ADMINISTRAÇÃO" in centro:
                ugr_hint = "154040"

        elif "unbtv" in txt_full:
            # UnBTV: Rádio e Televisão Universitárias
            nd_hint      = "339000"
            pi_hint      = "VGY01N0105N"
            ugr_hint     = "154190"

        elif any(k in txt_full for k in ("capacitaç", "capacitac", "curso", "treinamento", "procap")) and \
             any(k in txt_full for k in ("empenho", "empresa", "fornecedor", "cnpj")):
            # Capacitação com empresa fornecedora externa (PROCAP/empresa)
            nd_hint = "339039"

        elif any(k in txt_full for k in ("diária", "diaria")):
            nd_hint = "339014"

        elif any(k in txt_full for k in ("passagem",)):
            nd_hint = "339033"

        elif any(k in fonte_cred for k in ("UNIDADES ADMINISTRATIVAS", "CREDITO PARA UNIDADES")):
            # Crédito para Unidades Administrativas genérico → PI VGY01N0105N
            nd_hint = "339000"
            pi_hint = "VGY01N0105N"
            # Tenta refinar UGR pelo centro de custo do despacho
            if "DPO" in centro or "PLANEJAMENTO" in centro:
                ugr_hint = "152387"

        orig_ugr_hint = ""
        if "unbtv" in txt_full:
            orig_ugr_hint = "154190"

        if acao:
            from parser_planilha import sugerir_celulas
            sugestao = sugerir_celulas(_planilha_cache, acao, valor, nd_hint=nd_hint, ugr_hint=ugr_hint, pi_hint=pi_hint, orig_ugr_hint=orig_ugr_hint)
            # Buscar nome oficial da Ação na planilha para garantir precisão
            row_acao = next((r for r in _planilha_cache if str(r.get("acao")).strip().upper() == str(acao).strip().upper() and r.get("acao_nome")), None)
            if row_acao and row_acao["acao_nome"]:
                resultado["campos"]["acao_nome"] = {"label": "Nome da Ação", "valor": row_acao["acao_nome"], "confianca": "alta"}

    return jsonify({"ok": True, "dados": resultado, "sugestao": sugestao})


# ── Substituir planilha (upload manual) ──────────────────────────────────────
@app.route("/api/carregar-planilha", methods=["POST"])
def carregar_planilha():
    global _planilha_cache
    if "excel" not in request.files:
        return jsonify({"ok": False, "erro": "Arquivo Excel não enviado"}), 400

    f = request.files["excel"]
    path = os.path.join(UPLOAD_DIR, "planilha_temp.xlsx")
    f.save(path)

    from parser_planilha import carregar_planilha as _load
    try:
        _planilha_cache = _load(path)
        return jsonify({"ok": True, "total": len(_planilha_cache), "fonte": "upload manual"})
    except Exception as e:
        return jsonify({"ok": False, "erro": str(e)}), 500


# ── Buscar células ────────────────────────────────────────────────────────────
@app.route("/api/buscar-celulas", methods=["POST"])
def buscar_celulas():
    if not _planilha_cache:
        return jsonify({"ok": False, "erro": "Planilha não carregada"}), 400
    filtros = request.get_json() or {}
    from parser_planilha import buscar_celulas as _buscar
    return jsonify({"ok": True, "resultados": _buscar(_planilha_cache, filtros)})


# ── Gerar XML ─────────────────────────────────────────────────────────────────
@app.route("/api/gerar-xml", methods=["POST"])
def gerar_xml():
    dados = request.get_json()
    if not dados:
        return jsonify({"ok": False, "erro": "Dados não enviados"}), 400

    def is_bad(val):
        if not val: return True
        s = str(val).strip().upper()
        if s in ("", "0", "0,00", "R$ 0,00", "-8"): return True
        if "XXXX" in s or "X.XXX" in s or "NOME DA EMPRESA" in s or "PESSOA FÍSICA" in s or "PESSOA FISICA" in s: return True
        return False

    erros = []
    if is_bad(dados.get("ug_emitente")): erros.append("UG Emitente em branco")
    if is_bad(dados.get("ano_nc")): erros.append("Ano NC em branco")
    if is_bad(dados.get("data_emissao")): erros.append("Data de Emissão em branco")
    if is_bad(dados.get("processo_sei")): erros.append("Número do Processo SEI está incompleto (XXXX)")
    if is_bad(dados.get("favorecido_nome")): erros.append("Nome do Favorecido está fictício ou em branco")
    if is_bad(dados.get("cnpj")): erros.append("CNPJ/CPF do Favorecido está fictício ou em branco (XX.XXX...)")

    if erros:
        return jsonify({"ok": False, "erro": "Não foi possível gerar o XML SIAFIWeb. Dados incompletos:\n• " + "\n• ".join(erros)}), 400

    from gerador_xml import gerar_xml_zip
    try:
        zip_path = gerar_xml_zip(dados)
        ug  = dados.get("ug_emitente", "154040")
        ano = dados.get("ano_nc", "2026")
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return send_file(
            zip_path,
            as_attachment=True,
            download_name=f"NC_{ug}_{ano}_{ts}.zip",
            mimetype="application/zip",
        )
    except Exception as e:
        return jsonify({"ok": False, "erro": str(e)}), 500


# ── Iniciar ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "=" * 55)
    print("  🏛  UnB/DPO — Sistema de Notas de Crédito")
    print("  📌  Acesse: http://localhost:5000")
    print("=" * 55)
    app.run(debug=True, port=5000)
