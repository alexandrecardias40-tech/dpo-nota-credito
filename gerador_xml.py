"""
gerador_xml.py — Geração do XML de carga para o SIAFIWeb

Suporta os 4 tipos de NC:
  - Detalhamento de Crédito
  - Descentralização de Crédito
  - Devolução de Descentralização
  - Anulação de Descentralização
"""
import os
import tempfile
import zipfile
from datetime import datetime


# ── Mapa de tipos ──────────────────────────────────────────────────────────────
_TIPO_MAP = {
    "detalhamento":   "orcNCDetalhamentoDados",
    "descentralizacao": "orcNCDescentralizacaoDados",
    "devolucao":      "orcNCDevolucaoDescentralizacaoDados",
    "anulacao":       "orcNCAnulacaoDescentralizacaoDados",
}

_NS = "http://services.orcamentario.siafi.tesouro.fazenda.gov.br/"


def gerar_xml_zip(dados: dict) -> str:
    """Gera XML conforme schema SIAFIWeb e empacota em ZIP. Retorna caminho do ZIP."""
    tipo   = dados.get("tipo_nc", "detalhamento")
    elem   = _TIPO_MAP.get(tipo, "orcNCDetalhamentoDados")
    ug     = dados.get("ug_emitente", "154040").strip()
    ano    = dados.get("ano_nc", str(datetime.now().year)).strip()
    data   = _fmt_data(dados.get("data_emissao", ""))
    desc   = _esc(dados.get("descricao", "")[:600])
    itens  = dados.get("itens", [])
    ug_fav = dados.get("ug_favorecida", "").strip()
    cod_tr = dados.get("cod_transf", "").strip()

    tag_item = "itemDetalhamento" if tipo == "detalhamento" else "itemDescentralizacao"

    L = []
    L.append('<?xml version="1.0" encoding="UTF-8"?>')
    L.append(f'<{elem} xmlns="{_NS}">')
    L.append(f"  <ugEmitente>{ug}</ugEmitente>")
    L.append(f"  <anoNotaCredito>{ano}</anoNotaCredito>")
    L.append(f"  <dtEmis>{data}</dtEmis>")
    if cod_tr:
        L.append(f"  <codTransf>{cod_tr}</codTransf>")
    L.append(f"  <txtDescricao>{desc}</txtDescricao>")

    for item in itens:
        L.append(f"  <{tag_item}>")
        if ug_fav and tipo != "detalhamento":
            L.append(f"    <ugFavorecida>{ug_fav}</ugFavorecida>")

        for orig in item.get("origens", []):
            L.append("    <origemCredito>")
            L += _celula_xml(orig, 6)
            L.append("    </origemCredito>")

        if tipo == "detalhamento":
            for dest in item.get("destinos", []):
                L.append("    <destinoCredito>")
                L += _celula_xml(dest, 6)
                L.append("    </destinoCredito>")

        L.append(f"  </{tag_item}>")

    L.append(f"</{elem}>")
    xml_content = "\n".join(L)

    # Empacota em ZIP
    tmp     = tempfile.mkdtemp()
    ts      = datetime.now().strftime("%Y%m%d_%H%M%S")
    nome    = f"NC_{ug}_{ano}_{ts}"
    zip_path = os.path.join(tmp, f"{nome}.zip")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{nome}.xml", xml_content)

    return zip_path


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _celula_xml(cel: dict, indent: int) -> list:
    sp = " " * indent
    lines = [f"{sp}<celulaOrcamentaria>"]
    esfera = cel.get("esfera") or "1"
    lines.append(f"{sp}  <esfera>{esfera}</esfera>")
    if cel.get("ptres"):
        lines.append(f"{sp}  <codPTRES>{cel['ptres']}</codPTRES>")
    if cel.get("fonte"):
        lines.append(f"{sp}  <codFonteRec>{cel['fonte']}</codFonteRec>")
    if cel.get("nd"):
        lines.append(f"{sp}  <codNatDesp>{cel['nd']}</codNatDesp>")
    ugr = cel.get("ugr", "")
    if ugr and ugr not in ("-8", ""):
        lines.append(f"{sp}  <ugResponsavel>{ugr}</ugResponsavel>")
    pi = cel.get("pi", "")
    if pi and pi not in ("-8", ""):
        lines.append(f"{sp}  <codPlanoInterno>{pi}</codPlanoInterno>")
    lines.append(f"{sp}</celulaOrcamentaria>")
    lines.append(f"{sp}<vlrCredito>{_fmt_val(cel.get('valor', '0'))}</vlrCredito>")
    return lines


def _fmt_val(val) -> str:
    """Converte valor BR (1.234,56) → XML (1234.56)."""
    s = str(val).strip().replace("R$", "").replace(" ", "")
    s = s.replace(".", "").replace(",", ".")
    try:
        return f"{float(s):.2f}"
    except ValueError:
        return "0.00"


def _fmt_data(data_str: str) -> str:
    """Converte dd/mm/yyyy → yyyy-mm-dd."""
    if not data_str:
        return datetime.now().strftime("%Y-%m-%d")
    try:
        if "/" in data_str:
            d, m, a = data_str.strip().split("/")
            return f"{a}-{m.zfill(2)}-{d.zfill(2)}"
    except Exception:
        pass
    return datetime.now().strftime("%Y-%m-%d")


def _esc(s: str) -> str:
    """Escapa caracteres especiais XML."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
