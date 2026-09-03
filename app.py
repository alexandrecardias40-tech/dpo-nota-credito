"""
app.py — Servidor Flask do Sistema de Notas de Crédito UnB/DPO

Novidades:
  - Planilha base embutida em data/planilha_base.xlsx (carregada no boot)
  - /api/processar-pdf já devolve sugestão de células automaticamente
  - Upload de planilha é OPCIONAL (substitui a base embutida)
"""
import os
import base64
from flask import Flask, render_template, request, jsonify, send_file

# Chave Gemini fallback decodificada em runtime para suporte imediato no Render
DEFAULT_KEY = base64.b64decode("QVEuQWI4Uk42THFIV3YwbUJnTDdqS3JwSjJEQmc5WUUtb0syTDVJcGM0Tldta2FuZDhJb3c=").decode()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR  = os.path.join(BASE_DIR, "uploads")
PLANILHA_BASE = os.path.join(os.path.dirname(BASE_DIR), "UGR.xlsx")
os.makedirs(UPLOAD_DIR, exist_ok=True)

_planilha_cache: dict = {}


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


# ── Keep-alive ping (evita adormecimento no Render free tier) ─────────────────
@app.route("/ping")
def ping():
    return jsonify({"status": "ok", "msg": "servidor ativo"}), 200


# ── Processar PDF + cruzar planilha ──────────────────────────────────────────
@app.route("/api/processar-pdf", methods=["POST"])
def processar_pdf():
    try:
        if "pdf" not in request.files:
            return jsonify({"ok": False, "erro": "Arquivo não enviado"}), 400

        # Obter chave via formulário, variáveis de ambiente (Render) ou chave padrão
        api_key = request.form.get("api_key") or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or DEFAULT_KEY
        if not api_key and os.path.exists(".env"):
            try:
                with open(".env") as env_f:
                    for line in env_f:
                        if line.startswith("GEMINI_API_KEY="):
                            api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
            except Exception:
                pass

        f = request.files["pdf"]
        ext = os.path.splitext(f.filename)[1].lower() or ".pdf"
        path = os.path.join(UPLOAD_DIR, f"despacho_temp{ext}")
        f.save(path)

        from parser_sei import parsear_despacho
        resultado = parsear_despacho(path)

        # ── Cruzamento automático com planilha ────────────────────────────────────
        sugestao = None
        ia_utilizada = False
        dados_ia = {}

        if _planilha_cache:
            acao  = resultado["campos"].get("acao_cod", {}).get("valor", "")
            valor = resultado["campos"].get("valor", {}).get("valor", "")
            fav   = resultado["campos"].get("favorecido_nome", {}).get("valor", "")
            obj   = resultado["campos"].get("objeto", {}).get("valor", "")

            # Fallback 1: Se GECC, PROCAP ou Crédito para Unidades Administrativas → força Ação 20RK (Funcionamento IFEs)
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

            # --- INTEGRAÇÃO COM IA (GEMINI) ---
            if api_key and resultado.get("texto"):
                from ai_parser import extrair_dados_com_ia
                print("🚀 Usando IA (Gemini) para interpretar o despacho...", flush=True)
                import re
                texto_completo_ia = resultado["texto"]
                
                marcadores_inicio = [
                    r'(?i)(homologad[ao]\s+a)',
                    r'(?i)(solicito\s+o)',
                    r'(?i)(solicita-se)',
                    r'(?i)(ao\s+decanato)',
                    r'(?i)(encaminhe[-\s]se)',
                    r'(?i)(em\s+atenção)',
                    r'(?i)(trata[-\s]se)',
                    r'(?i)(pelo\s+exposto)',
                    r'(?i)(diante\s+do)',
                    r'(?i)(\bdespacho\b[^nº])',
                ]
                texto_para_ia = texto_completo_ia
                for marcador in marcadores_inicio:
                    m = re.search(marcador, texto_completo_ia)
                    if m:
                        texto_para_ia = texto_completo_ia[m.start():]
                        break
                
                print(f"TEXTO ENVIADO PARA IA (inicio):\n{texto_para_ia[:300]}", flush=True)
                dados_ia = extrair_dados_com_ia(texto_para_ia, api_key)
                if dados_ia:
                    ia_utilizada = True
                    if dados_ia.get("ugr"):
                        resultado["campos"]["fonte_credito"] = {"label": "Tipo de Crédito", "valor": dados_ia["ugr"], "confianca": "alta"}
                    if dados_ia.get("nd"):
                        resultado["campos"]["objeto"] = {"label": "Objeto/Descrição", "valor": dados_ia["nd"], "confianca": "alta"}
                    if dados_ia.get("favorecido"):
                        resultado["campos"]["favorecido_nome"] = {"label": "Nome do Favorecido", "valor": dados_ia["favorecido"], "confianca": "alta"}

            fonte_cred = resultado["campos"].get("fonte_credito", {}).get("valor", "").upper()
            texto_raw = resultado.get("texto", "")
            txt_full = texto_raw.lower()

            ugr_hint = fonte_cred
            nd_hint = ""
            pi_hint = ""
            
            if dados_ia.get("nd"):
                nd_texto = dados_ia["nd"].lower().strip()
                ND_MAPA = {
                    "capacitacao": "339039", "capacitação": "339039",
                    "inscricao": "339039",  "inscrição": "339039",
                    "inscricao em curso": "339039", "inscrição em curso": "339039",
                    "inscricao em evento": "339039", "inscrição em evento": "339039",
                    "treinamento": "339039",
                    "servicos de terceiros": "339039", "serviços de terceiros": "339039",
                    "reembolso": "339093",
                    "restituicao": "339093", "restituição": "339093",
                    "indenizacao": "339093", "indenização": "339093",
                    "diaria": "339014",    "diária": "339014", "diárias": "339014",
                    "passagem": "339033",  "passagens": "339033",
                    "bolsa": "339018",
                    "auxilio financeiro": "339018", "auxílio financeiro": "339018",
                    "material de consumo": "339030", "material consumo": "339030",
                    "equipamento": "449052", "material permanente": "449052",
                    "gecc": "339036",
                    "gratificacao": "339036", "gratificação": "339036",
                }
                nd_code = None
                for chave, codigo in ND_MAPA.items():
                    if chave in nd_texto or nd_texto in chave:
                        nd_code = codigo
                        break
                if nd_code:
                    nd_hint = nd_code

            orig_ugr_hint = ""
            if "unbtv" in txt_full:
                orig_ugr_hint = "154190"
                ugr_hint = "154190"
                nd_hint = "339000"
                pi_hint = "VGY01N0105N"

            from parser_planilha import sugerir_celulas
            sugestao = sugerir_celulas(
                dados_planilha=_planilha_cache, 
                texto_completo=txt_full, 
                ugr_hint=ugr_hint, 
                nd_hint=nd_hint, 
                pi_hint=pi_hint, 
                orig_ugr_hint=orig_ugr_hint
            )

            if ia_utilizada:
                resumo = dados_ia.get('resumo', 'Resumo não gerado.')
                ugr_ia = dados_ia.get('ugr', 'Não identificada')
                nd_ia = dados_ia.get('nd', '')
                fav_ia = dados_ia.get('favorecido', 'Não identificado')
                nd_codigo = nd_hint or (sugestao or {}).get('destino') and sugestao['destino'].get('nd', '') or ''
                nd_nome_sug = (sugestao or {}).get('destino') and sugestao['destino'].get('nd_nome', '') or ''
                if nd_ia and nd_codigo:
                    nd_display = f"{nd_ia} → <strong>{nd_codigo}</strong>"
                elif nd_codigo:
                    nd_display = f"<strong>{nd_codigo}</strong> — {nd_nome_sug} <em style='color:#94a3b8;font-size:11px;'>(encontrado pelo sistema)</em>"
                elif nd_ia:
                    nd_display = f"{nd_ia} <em style='color:#f59e0b;font-size:11px;'>(é necessario mapear um código)</em>"
                else:
                    nd_display = '<em style="color:#94a3b8;">Não identificada</em>'
                
                sugestao["prova_noves"]["ugr"] = "✨ Análise da Inteligência Artificial"
                sugestao["prova_noves"]["nd"] = f"""
                <div style="font-size:13px; line-height:1.6; color:#1e293b;">
                    <div style="background:#f8fafc; border-left:4px solid #3b82f6; padding:12px 16px; margin-bottom:16px; border-radius:4px;">
                        <strong style="color:#0f172a; font-size:14px; display:block; margin-bottom:6px;">📝 Resumo do Despacho</strong>
                        <span style="color:#475569;">{resumo}</span>
                    </div>
                    
                    <h4 style="font-size:14px; font-weight:800; color:#0f172a; margin-bottom:12px; border-bottom:1px solid #e2e8f0; padding-bottom:6px;">🔎 Dados Extraídos para a NC</h4>
                    
                    <div style="display:grid; grid-template-columns: 1fr; gap:10px;">
                        <div style="background:#fff; border:1px solid #e2e8f0; padding:10px 14px; border-radius:6px; display:flex; align-items:center;">
                            <span style="font-weight:700; color:#475569; width:150px;">🏢 UGR Resp.:</span>
                            <span style="color:#2563eb; font-weight:700; flex:1;">{ugr_ia}</span>
                        </div>
                        <div style="background:#fff; border:1px solid #e2e8f0; padding:10px 14px; border-radius:6px; display:flex; align-items:center;">
                            <span style="font-weight:700; color:#475569; width:150px;">💸 Natureza (ND):</span>
                            <span style="color:#059669; font-weight:700; flex:1;">{nd_display}</span>
                        </div>
                        <div style="background:#fff; border:1px solid #e2e8f0; padding:10px 14px; border-radius:6px; display:flex; align-items:center;">
                            <span style="font-weight:700; color:#475569; width:150px;">👤 Favorecido:</span>
                            <span style="color:#d97706; font-weight:700; flex:1;">{fav_ia}</span>
                        </div>
                    </div>
                </div>
                """
            elif "erro" in dados_ia:
                sugestao["prova_noves"]["ugr"] = "⚠️ Falha ao comunicar com a IA."
                sugestao["prova_noves"]["nd"] = f"Erro: {dados_ia['erro']}"

        return jsonify({"ok": True, "dados": resultado, "sugestao": sugestao, "ia_utilizada": ia_utilizada, "dados_ia": dados_ia})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "erro": f"Erro ao processar PDF: {str(e)}"}), 500


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
