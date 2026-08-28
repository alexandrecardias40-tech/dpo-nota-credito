"""
parser_planilha.py — Leitura, busca e cruzamento automático com planilha orçamentária.

Padrão de cruzamento para Detalhamento de Crédito:
  - Linha com ND genérico (ex: 339000) e saldo > 0 → ORIGEM
  - Linhas com ND específico (ex: 339039) → candidatos para DESTINO
  - O usuário escolhe qual ND específico usar; os demais campos (PTRES, Fonte, UGR, PI) são iguais.
"""
import openpyxl


def carregar_planilha(path: str) -> list:
    """Carrega planilha orçamentária (padrão DPO ou exportada do Tesouro Gerencial) e retorna lista de dicts."""
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb.active
    todas = list(ws.iter_rows(values_only=True))
    wb.close()

    if not todas:
        return []

    # Detectar linha de cabeçalho (primeiras 10 linhas)
    header_idx = -1
    col_map = {}

    for i, row in enumerate(todas[:10]):
        cells = [str(c or "").upper().strip() for c in row]
        has_ptres = any("PTRES" in c for c in cells)
        has_fonte = any("FONTE" in c for c in cells)
        has_acao  = any("AÇÃO" in c or "ACAO" in c for c in cells)
        has_saldo = any(k in c for k in ("SALDO", "VALOR", "DISPONIVEL", "DISPONÍVEL", "CREDITO", "CRÉDITO") for c in cells)

        if sum([has_ptres, has_fonte, has_acao, has_saldo]) >= 2:
            header_idx = i
            for c_idx, cell in enumerate(cells):
                if not cell: continue
                if ("AÇÃO" in cell or "ACAO" in cell) and "NOME" not in cell and "acao" not in col_map:
                    col_map["acao"] = c_idx
                elif ("AÇÃO" in cell or "ACAO" in cell) and ("NOME" in cell or "DESCR" in cell or "TITULO" in cell):
                    col_map["acao_nome"] = c_idx
                elif "PTRES" in cell and "ptres" not in col_map:
                    col_map["ptres"] = c_idx
                elif "FONTE" in cell and "fonte" not in col_map:
                    col_map["fonte"] = c_idx
                elif "UGR" in cell and ("CÓD" in cell or "COD" in cell or "ugr_cod" not in col_map):
                    col_map["ugr_cod"] = c_idx
                elif ("UGR" in cell or "UNIDADE" in cell) and ("NOME" in cell or "DESCR" in cell or "ugr_nome" not in col_map):
                    col_map["ugr_nome"] = c_idx
                elif ("PI" in cell or "PLANO" in cell) and ("CÓD" in cell or "COD" in cell or "pi_cod" not in col_map):
                    col_map["pi_cod"] = c_idx
                elif ("PI" in cell or "PLANO" in cell) and ("NOME" in cell or "DESCR" in cell or "pi_nome" not in col_map):
                    col_map["pi_nome"] = c_idx
                elif ("ND" in cell or "NATUREZA" in cell or "ELEMENTO" in cell) and ("CÓD" in cell or "COD" in cell or "nd_cod" not in col_map):
                    col_map["nd_cod"] = c_idx
                elif ("ND" in cell or "NATUREZA" in cell or "ELEMENTO" in cell) and ("NOME" in cell or "DESCR" in cell or "nd_nome" not in col_map):
                    col_map["nd_nome"] = c_idx
                elif any(k in cell for k in ("SALDO", "DISPONIVEL", "DISPONÍVEL", "VALOR", "ORÇAMENTO")) and "saldo" not in col_map:
                    col_map["saldo"] = c_idx
            break

    # Posicionamento de colunas padrão (fallback para 11 colunas)
    idx_acao      = col_map.get("acao", 0)
    idx_acao_nome = col_map.get("acao_nome", 1 if idx_acao != 1 else 0)
    idx_ptres     = col_map.get("ptres", 2)
    idx_fonte     = col_map.get("fonte", 3)
    idx_ugr_cod   = col_map.get("ugr_cod", 4)
    idx_ugr_nome  = col_map.get("ugr_nome", 5)
    idx_pi_cod    = col_map.get("pi_cod", 6)
    idx_pi_nome   = col_map.get("pi_nome", 7)
    idx_nd_cod    = col_map.get("nd_cod", 8)
    idx_nd_nome   = col_map.get("nd_nome", 9)
    idx_saldo     = col_map.get("saldo", 10)

    registros = []
    start_row = (header_idx + 1) if header_idx >= 0 else 0
    for row in todas[start_row:]:
        if not any(c for c in row if c is not None and str(c).strip()):
            continue
        try:
            r = {
                "acao":      _s(row, idx_acao),
                "acao_nome": _s(row, idx_acao_nome),
                "ptres":     _s(row, idx_ptres),
                "fonte":     _s(row, idx_fonte),
                "ugr_cod":   _cod(_s(row, idx_ugr_cod)),
                "ugr_nome":  _s(row, idx_ugr_nome),
                "pi_cod":    _cod(_s(row, idx_pi_cod)),
                "pi_nome":   _s(row, idx_pi_nome),
                "nd_cod":    _s(row, idx_nd_cod),
                "nd_nome":   _s(row, idx_nd_nome),
                "saldo":     _n(row, idx_saldo),
            }
            if r["acao"] in ("Ação Governo", "AÇÃO GOVERNO", "acao", "AÇÃO", ""):
                continue
            registros.append(r)
        except Exception:
            continue

    return registros


def buscar_celulas(registros: list, filtros: dict) -> list:
    """Filtra registros conforme critérios enviados pelo frontend."""
    acao      = filtros.get("acao", "").strip().upper()
    ptres     = filtros.get("ptres", "").strip()
    ugr       = filtros.get("ugr", "").strip()
    nd        = filtros.get("nd", "").strip()
    pi        = filtros.get("pi", "").strip()
    texto     = filtros.get("texto", "").strip().upper()
    s_saldo   = filtros.get("apenas_saldo", True)

    resultado = []
    for r in registros:
        if acao  and acao  not in r["acao"].upper():
            continue
        if ptres and ptres not in r["ptres"]:
            continue
        if ugr   and ugr   not in r["ugr_cod"] and ugr.upper() not in r["ugr_nome"].upper():
            continue
        if nd    and nd    not in r["nd_cod"]:
            continue
        if pi    and pi.upper() not in r["pi_cod"].upper() and pi.upper() not in r["pi_nome"].upper():
            continue
        if texto:
            hay = f"{r['acao_nome']} {r['ugr_nome']} {r['pi_nome']} {r['nd_nome']}".upper()
            if texto not in hay:
                continue
        if s_saldo and r["saldo"] <= 0:
            continue
        resultado.append(r)
        if len(resultado) >= 200:
            break

    return resultado


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _s(row, idx: int) -> str:
    if idx >= len(row) or row[idx] is None:
        return ""
    return str(row[idx]).strip()


def _cod(val: str) -> str:
    """Remove prefixo ' que o Excel às vezes adiciona a códigos numéricos."""
    return val.lstrip("'")


def _n(row, idx: int) -> float:
    if idx >= len(row) or row[idx] is None:
        return 0.0
    try:
        return float(row[idx])
    except (ValueError, TypeError):
        try:
            return float(str(row[idx]).replace(".", "").replace(",", "."))
        except Exception:
            return 0.0


def sugerir_celulas(registros: list, acao: str, valor_str: str = "", nd_hint: str = "", ugr_hint: str = "", pi_hint: str = "", orig_ugr_hint: str = "") -> dict:
    """
    Cruza automaticamente a ação extraída do despacho com a planilha.
    Retorna sugestão de células de origem e destino, com alternativas.
    """
    acao = str(acao).strip().upper()
    if not acao:
        return _sem_sugestao("Código da ação não extraído do despacho.")

    # ── 1. Filtrar por ação ────────────────────────────────────────────────────
    por_acao = [r for r in registros if r["acao"].upper() == acao]
    if not por_acao:
        return _sem_sugestao(f"Ação {acao} não encontrada na planilha.")

    # ── 2. Separar genéricos (ND *000) dos específicos ────────────────────────
    def is_gen(nd: str) -> bool:
        nd = nd.strip()
        return len(nd) >= 3 and nd.endswith("00")

    ND_gen = [r for r in por_acao if is_gen(r["nd_cod"])]
    ND_esp = [r for r in por_acao if not is_gen(r["nd_cod"])]

    # ── 3. Escolher melhor origem ──────────────────────────────────────────────
    def rank_orig(r):
        score = 0
        if r["saldo"] > 0:        score += 10
        if orig_ugr_hint and (r["ugr_cod"] == orig_ugr_hint or orig_ugr_hint in r["ugr_nome"].upper()): score += 40
        elif ugr_hint and (r["ugr_cod"] == ugr_hint or ugr_hint in r["ugr_nome"].upper()): score += 15
        if r["ugr_cod"] != "-8":  score += 5
        if is_gen(r["nd_cod"]):   score += 3
        return score

    candidatos_orig = sorted(ND_gen or por_acao, key=rank_orig, reverse=True)
    origem = candidatos_orig[0] if candidatos_orig else None

    # ── 4. Encontrar melhor destino compatível ──────────────────────────────────
    def rank_dest(r):
        score = 0
        if r["saldo"] > 0: score += 5
        if nd_hint and r["nd_cod"] == nd_hint: score += 50
        if ugr_hint and (r["ugr_cod"] == ugr_hint or ugr_hint in r["ugr_nome"].upper()): score += 30
        if pi_hint and (r["pi_cod"] == pi_hint or pi_hint in r["pi_nome"].upper()): score += 20
        if origem and r["ptres"] == origem["ptres"]: score += 10
        return score

    cand_dest = por_acao if nd_hint == "339000" else (ND_esp or por_acao)
    destinos_compat = sorted(cand_dest, key=rank_dest, reverse=True)
    destino_sug = destinos_compat[0] if destinos_compat else None

    # ── 5. Se origem não tem UGR específica mas destino tem, ajustar ──────────
    if origem and destino_sug and origem["ugr_cod"] == "-8" and destino_sug["ugr_cod"] != "-8":
        # Criar origem "derivada" com a UGR específica do destino
        origem = {
            **origem,
            "ugr_cod":  destino_sug["ugr_cod"],
            "ugr_nome": destino_sug["ugr_nome"],
            "pi_cod":   destino_sug["pi_cod"],
            "pi_nome":  destino_sug["pi_nome"],
        }

    # ── 6. Se não há destino, derivar ND do pai ───────────────────────────────
    if origem and not destino_sug:
        destino_sug = {**origem, "nd_cod": "", "nd_nome": "(preencha o ND específico)"}

    com_saldo = [r for r in por_acao if r["saldo"] > 0]
    # ── 7. Avisos ──────────────────────────────────────────────────────────────
    avisos = []
    if not com_saldo:
        avisos.append(f"Ação {acao} encontrada ({len(por_acao)} linhas), mas nenhuma com saldo > 0.")
    if origem and origem["saldo"] <= 0:
        avisos.append("Saldo zero na linha de origem — verifique se o crédito já foi utilizado.")
    if len(destinos_compat) > 1:
        avisos.append(f"{len(destinos_compat)} subelementos disponíveis para o DESTINO — verifique qual usar.")

    return {
        "origem":       _cell_to_dict(origem) if origem else None,
        "destino":      _cell_to_dict(destino_sug) if destino_sug else None,
        "alternativas": [_cell_to_dict(r) for r in destinos_compat[:10]],
        "total_acao":   len(por_acao),
        "avisos":       avisos,
        "encontrou":    origem is not None,
    }


def _sem_sugestao(msg: str) -> dict:
    return {"origem": None, "destino": None, "alternativas": [],
            "total_acao": 0, "avisos": [msg], "encontrou": False}


def _cell_to_dict(r: dict) -> dict:
    return {
        "esfera": "1",
        "ptres":  r.get("ptres", ""),
        "fonte":  r.get("fonte", ""),
        "nd":     r.get("nd_cod", ""),
        "nd_nome":r.get("nd_nome", ""),
        "ugr":    r.get("ugr_cod", ""),
        "ugr_nome":r.get("ugr_nome",""),
        "pi":     r.get("pi_cod", ""),
        "pi_nome":r.get("pi_nome", ""),
        "saldo":  r.get("saldo", 0),
        "valor":  "",
    }
