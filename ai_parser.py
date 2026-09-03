import os
import json
import time
import unicodedata
import google.generativeai as genai

# ── Lista completa de UGRs da UnB (usada para validação e injeção no prompt) ─────
_UGRS_UNB = {
    # Unidades Administrativas
    "ACE": "Arquivo Central",
    "AUD": "Auditoria",
    "BCE": "Biblioteca Central",
    "CCOM": "Centro de Políticas, Direito, Economia e Tecnologias das Comunicações",
    "CDS": "Centro de Desenvolvimento Sustentável",
    "CEAD": "Centro de Educação a Distância",
    "CEAM": "Centro de Estudos Avançados Multidisciplinares",
    "CER": "UNB Cerrado",
    "CET": "Centro de Excelência em Turismo",
    "CIBH": "Centro Internacional de Bioética e Humanidades",
    "CIFMC": "Centro Internacional de Física da Matéria Condensada",
    "CPAB": "Centro de Pesquisa Aplicada em Bambu e Fibras",
    "CPAD": "Assessoria de Acompanhamento e Mediação de Conduta",
    "CRAD": "Centro de Referência em Conservação da Natureza e Recuperação de Áreas Degradadas",
    "DAC": "Decanato de Assuntos Comunitários",
    "DAF": "Decanato de Administração (DAF)",
    "DCA": "Diretoria de Contratos Administrativos",
    "DEG": "Decanato de Ensino de Graduação (DEG)",
    "DEX": "Decanato de Extensão (DEX)",
    "DGP": "Decanato de Gestão de Pessoas (DGP)",
    "DPG": "Decanato de Pós-Graduação (DPG)",
    "DPI": "Decanato de Pesquisa e Inovação",
    "DPO": "Decanato de Planejamento, Orçamento e Avaliação Institucional",
    "EDU": "Editora Universidade de Brasília",
    "FAL": "Fazenda Água Limpa (FAL)",
    "GRE": "Gabinete da Reitora (GRE)",
    "INFRA": "Secretaria de Infraestrutura (INFRA)",
    "INT": "Secretaria de Assuntos Internacionais (INT)",
    "NITCDT": "Núcleo de Inovação Tecnológica e Centro de Apoio ao Desenvolvimento Tecnológico",
    "OUV": "Ouvidoria (OUV)",
    "PCTEC": "Parque Científico e Tecnológico da UnB",
    "PF": "Procuradoria Federal junto à UnB",
    "PRC": "Prefeitura da UnB (PRC)",
    "SAA": "Secretaria de Administração Acadêmica (SAA)",
    "SDH": "Secretaria de Direitos Humanos",
    "SECOM": "Secretaria de Comunicação (SECOM)",
    "SEMA": "Secretaria de Meio Ambiente",
    "SPI": "Secretaria de Patrimônio Imobiliário (SPI)",
    "STI": "Secretaria de Tecnologia da Informação",
    "UnBTV": "Rádio e Televisão Universitárias (UnBTV)",
    "VRT": "Vice-Reitoria (VRT)",
    # Unidades Acadêmicas
    "FAC": "Faculdade de Comunicação",
    "FACE": "Faculdade de Economia, Administração e Contabilidade",
    "FAU": "Faculdade de Arquitetura e Urbanismo",
    "FAV": "Faculdade de Agronomia e Medicina Veterinária",
    "FCE": "Faculdade de Ceilândia (FCE/FCTS)",
    "FCI": "Faculdade de Ciência da Informação",
    "FCE (FCTS)": "Faculdade de Ciências e Tecnologias em Saúde",
    "FD": "Faculdade de Direito",
    "FE": "Faculdade de Educação",
    "FEF": "Faculdade de Educação Física",
    "FGA": "Faculdade UnB Gama (FGA/FCTE)",
    "FGA (FCTE)": "Faculdade de Ciências e Tecnologias em Engenharia – Gama",
    "FM": "Faculdade de Medicina",
    "FS": "Faculdade de Ciências da Saúde",
    "FT": "Faculdade de Tecnologia",
    "FUP": "Faculdade UnB Planaltina",
    "IB": "Instituto de Ciências Biológicas",
    "ICS": "Instituto de Ciências Sociais",
    "ICH": "Instituto de Ciências Humanas",
    "IDA": "Instituto de Artes",
    "IE": "Instituto de Ciências Exatas",
    "IF": "Instituto de Física",
    "IG": "Instituto de Geociências",
    "IL": "Instituto de Letras",
    "IP": "Instituto de Psicologia",
    "IPOL": "Instituto de Ciência Política",
    "IQ": "Instituto de Química",
    "IREL": "Instituto de Relações Internacionais",
}

# ── Lista de NDs com palavras-chave para matching ────────────────────────────
_NDS = {
    "339014": ["diária", "diarias", "diárias", "diária nacional", "diária internacional"],
    "339018": ["bolsa estudante", "auxílio financeiro a estudante", "auxílio viagem discente",
               "auxílio financeiro a aluno", "bolsa extensão"],
    "339020": ["bolsa pesquisador", "auxílio financeiro a pesquisador", "bolsa preceptoria",
               "bolsa de pesquisa", "bolsa pos-doutor"],
    "339030": ["material de consumo", "almox", "material de expediente", "itens de copa",
               "copa e cozinha", "material gráfico", "material hospitalar", "insumos"],
    "339033": ["passagem", "passagens", "bilhete aéreo", "bilhete rodoviário", "locomoção",
               "taxi gov", "táxi gov", "passagem aérea", "passagem terrestre"],
    "339036": ["gecc", "gratificação", "encargo de curso", "encargo concurso",
               "diária não servidor", "diária colaborador eventual", "pró-labore"],
    "339039": ["inscrição", "inscrição em congresso", "inscrição em curso", "inscrição em evento",
               "capacitação", "treinamento", "publicação de artigo", "serviço de terceiros",
               "pessoa jurídica", "seguro viagem", "tradução", "frete", "jardinagem",
               "serviços correlatos", "despesas bancárias", "persianas", "serviço gráfico"],
    "339040": ["software", "licença de software", "ti ", "tecnologia da informação",
               "adobe", "microsoft", "antivírus"],
    "339047": ["multa", "licenciamento veículo", "taxa", "obrigações contributivas"],
    "339092": ["reconhecimento de dívida exercícios anteriores", "despesas exercícios anteriores"],
    "339093": ["reembolso", "restituição", "indenização", "ajuda de custo",
               "ressarcimento", "reconhecimento de dívida", "bilhete rodoviário restituição"],
    "339147": ["siscomex", "taxa siscomex", "desembaraço aduaneiro"],
    "449052": ["equipamento", "material permanente", "bem permanente", "mobiliário",
               "quadro magnético", "persiana", "computador", "impressora", "servidor físico"],
}


def _norm(txt: str) -> str:
    """Normaliza texto removendo acentos e convertendo para minúsculas."""
    return ''.join(c for c in unicodedata.normalize('NFD', str(txt).lower())
                   if unicodedata.category(c) != 'Mn')


def _detectar_nd_local(texto: str) -> str:
    """Detecta código de ND a partir de palavras-chave no texto."""
    txt = _norm(texto)
    for cod, keywords in _NDS.items():
        for kw in keywords:
            if _norm(kw) in txt:
                return cod
    return ""


def _validar_ugr(ugr_ia: str) -> str:
    """Retorna a sigla canônica se a UGR identificada pela IA bater com uma conhecida."""
    if not ugr_ia:
        return ""
    ugr_upper = ugr_ia.strip().upper()
    # Match exato
    for sigla in _UGRS_UNB:
        if sigla.upper() == ugr_upper:
            return sigla
    # Match parcial (ex: "Matriz/DGP" → "DGP")
    for sigla in _UGRS_UNB:
        if sigla.upper() in ugr_upper or _norm(sigla) in _norm(ugr_ia):
            return sigla
    # Retorna como veio se não encontrar (a IA pode ter acertado mesmo assim)
    return ugr_ia.strip()


def extrair_dados_com_ia(texto_despacho: str, api_key: str) -> dict:
    """
    Usa o modelo Gemini (Google) para extrair UGR, ND e Favorecido
    de despachos SEI de Nota de Crédito da UnB.
    Inclui lista de UGRs e NDs conhecidas no prompt para máxima precisão.
    Possui retry automático contra erros temporários (504 Deadline Exceeded).
    """
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-flash-lite-latest')

    # ── Monta lista de UGRs para injetar no prompt ─────────────────────────
    ugrs_lista = "\n".join(f"  - {sig}: {nome}" for sig, nome in _UGRS_UNB.items())

    # ── Monta lista de NDs para injetar no prompt ──────────────────────────
    nds_lista = (
        "  339014 – Diárias (servidor civil)\n"
        "  339018 – Auxílio Financeiro a Estudantes (bolsa de graduação/extensão)\n"
        "  339020 – Auxílio Financeiro a Pesquisador (bolsa pós-grad/pesquisa)\n"
        "  339030 – Material de Consumo (almoxarifado, expediente)\n"
        "  339033 – Passagens e Locomoção (aérea, terrestre, Táxi Gov)\n"
        "  339036 – Outros Serv. Terceiros – PF / GECC / Gratificação não servidor\n"
        "  339039 – Outros Serv. Terceiros – PJ (inscrições, publicações, traduções, seguros)\n"
        "  339040 – Material de TI (software, licença, antivírus)\n"
        "  339047 – Obrigações Tributárias (multa, licenciamento veículo, taxas)\n"
        "  339092 – Despesas de Exercícios Anteriores (reconhecimento de dívida anterior)\n"
        "  339093 – Reembolso / Restituição / Indenização / Ajuda de Custo\n"
        "  339147 – Taxa SISCOMEX / Desembaraço Aduaneiro\n"
        "  449052 – Equipamentos e Material Permanente (bem duradouro, mobiliário)"
    )

    prompt = f"""Você é especialista em orçamento público da Universidade de Brasília (UnB).
Analise o DESPACHO SEI abaixo (pedido de Nota de Crédito) e extraia exatamente os campos solicitados.

═══════════════════════════════════════
UNIDADES GESTORAS RESPONSÁVEIS (UGRs) CONHECIDAS DA UnB:
{ugrs_lista}
═══════════════════════════════════════
NATUREZAS DE DESPESA (NDs) MAIS COMUNS:
{nds_lista}
═══════════════════════════════════════

REGRAS DE EXTRAÇÃO:
1. "ugr": Identifique QUAL unidade é DONA dos recursos (não quem encaminhou).
   • Procure por expressões como: "com recursos da/do/de [SIGLA]", "Matriz/[SIGLA]",
     "recursos de [UNIDADE]", "recursos [SIGLA]", "dotação de [UNIDADE]".
   • Use APENAS siglas da lista acima. Se não encontrar com clareza, retorne "".
   • NUNCA confunda o encaminhador/destinatário ("Encaminhe-se para DOR/DGP") com o dono do recurso.

2. "nd_codigo": Retorne SOMENTE o código numérico da ND (ex: "339033").
   • Se o texto mencionar "passagem", use 339033.
   • Se mencionar "diária", use 339014.
   • Se mencionar "reembolso", "restituição" ou "indenização", use 339093.
   • Se mencionar "bolsa" ou "auxílio financeiro a estudante", use 339018.
   • Se mencionar "material de consumo" ou "almox", use 339030.
   • Se mencionar "inscrição", "capacitação", "treinamento" ou "publicação de artigo", use 339039.
   • Se não souber com certeza, retorne "".

3. "nd_descricao": Nome curto da despesa (ex: "Passagens", "Diárias", "Reembolso").
   Se não souber, retorne "".

4. "favorecido": Nome completo da PESSOA FÍSICA ou JURÍDICA que vai receber o recurso.
   • Se for um servidor, extraia o nome do texto.
   • Se não houver nome explícito, retorne "".

5. "descricao_nc": Frase direta e objetiva (máximo 120 caracteres) para o campo
   "Descrição da NC" no SIAFI. Ex: "Reembolso certificado digital A3 – [Nome]",
   "Inscrição no congresso SBPC 2026 – [Nome]". Não invente dados.

6. "resumo": 1-2 frases descrevendo o que está sendo solicitado.

RETORNE APENAS O JSON (sem markdown, sem explicações):
{{
  "ugr": "sigla da lista ou vazio",
  "nd_codigo": "código numérico ou vazio",
  "nd_descricao": "nome da despesa ou vazio",
  "favorecido": "nome completo ou vazio",
  "descricao_nc": "frase objetiva ou vazio",
  "resumo": "1-2 frases"
}}

DESPACHO:
\"\"\"
{texto_despacho[:2500]}
\"\"\"
"""

    ultimo_erro = ""
    for tentativa in range(2):
        try:
            response = model.generate_content(prompt, request_options={"timeout": 30})
            texto_resposta = response.text.strip()

            # Limpar markdown se vier com crases
            if texto_resposta.startswith("```json"):
                texto_resposta = texto_resposta[7:]
            if texto_resposta.startswith("```"):
                texto_resposta = texto_resposta[3:]
            if texto_resposta.endswith("```"):
                texto_resposta = texto_resposta[:-3]

            print(f"RESPOSTA BRUTA DA IA (tentativa {tentativa+1}):\n{texto_resposta}", flush=True)

            try:
                dados = json.loads(texto_resposta.strip())
            except Exception as json_err:
                print(f"Erro ao parsear JSON: {json_err}", flush=True)
                return {"raw": texto_resposta, "erro": "A IA não retornou um JSON válido."}

            # ── Pós-processamento: validar e normalizar campos ──────────────
            # 1. Validar UGR contra lista conhecida
            ugr_original = dados.get("ugr", "")
            dados["ugr"] = _validar_ugr(ugr_original)

            # 2. Consolidar nd / nd_codigo / nd_descricao no formato esperado pelo app.py
            # O campo "nd" era o que o app.py usava antes — mantemos compatibilidade
            nd_codigo = str(dados.get("nd_codigo", "") or dados.get("nd", "") or "").strip()
            nd_descricao = str(dados.get("nd_descricao", "") or "").strip()

            # 3. Fallback: detectar ND localmente se a IA não identificou
            if not nd_codigo:
                nd_codigo_local = _detectar_nd_local(texto_despacho)
                if nd_codigo_local:
                    nd_codigo = nd_codigo_local
                    print(f"ND detectada localmente: {nd_codigo}", flush=True)

            # Reescrever campo "nd" como a descrição (para compatibilidade com app.py)
            if not nd_descricao and nd_codigo:
                # Mapa reverso simples para obter o nome do código
                _cod_nome = {
                    "339014": "Diárias", "339018": "Bolsa/Auxílio a Estudantes",
                    "339020": "Auxílio a Pesquisador", "339030": "Material de Consumo",
                    "339033": "Passagens", "339036": "Serv. Terceiros PF / GECC",
                    "339039": "Serv. Terceiros PJ / Inscrições", "339040": "Material TI",
                    "339047": "Obrigações Tributárias", "339092": "Desp. Exerc. Anteriores",
                    "339093": "Reembolso / Restituição", "339147": "Taxa SISCOMEX",
                    "449052": "Equipamentos/Material Permanente",
                }
                nd_descricao = _cod_nome.get(nd_codigo, "")

            dados["nd"] = nd_descricao        # Descrição textual (compatibilidade)
            dados["nd_codigo"] = nd_codigo    # Código numérico explícito
            dados["raw"] = texto_resposta
            return dados

        except Exception as e:
            ultimo_erro = str(e)
            print(f"Tentativa {tentativa+1} falhou: {e}", flush=True)
            if tentativa < 1:
                time.sleep(1)

    return {"erro": f"Servidor Google temporariamente indisponível: {ultimo_erro}"}
