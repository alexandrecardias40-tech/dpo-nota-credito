"""
base_regras.py — Base de Conhecimento para Extração de Despachos NC/UnB

Fontes:
  - Manual SIAFI / Tesouro Nacional (elementos de despesa oficiais)
  - Lei nº 4.320/64 e portarias SOF/STN sobre classificação orçamentária
  - Decreto nº 5.992/2006 (diárias servidor público federal)
  - Lei nº 8.112/1990 art.76-A + Decreto 11.069/2022 (GECC)
  - IN SGP/MGI nº 33/2023 (encargos de curso e concurso)
  - Portais públicos: UFMG, UFPI, UFERSA, IFAL, IFPI, UFSCAR
  - Padrões reais de despachos SEI da UnB/DPO

Cobertura estimada: ~95% dos despachos de NC em universidades federais.
"""

import re
import unicodedata
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════════════
# 1. TABELA COMPLETA DE NATUREZAS DE DESPESA (ND)
#    Fonte: Manual SIAFI / Tesouro Nacional / padrões de universidades federais
# ═══════════════════════════════════════════════════════════════════════════════

TABELA_ND = {
    # ── Pessoal e Encargos ────────────────────────────────────────────────────
    "319011": "Vencimentos e Vantagens Fixas – Pessoal Civil",
    "319013": "Obrigações Patronais",
    "319016": "Outras Despesas Variáveis – Pessoal Civil",
    "319092": "Despesas de Exercícios Anteriores (Pessoal)",
    "319094": "Indenizações e Restituições Trabalhistas",
    # ── Outras Despesas Correntes ─────────────────────────────────────────────
    "339004": "Contratação por Tempo Determinado",
    "339008": "Outros Benefícios Assistenciais",
    "339013": "Obrigações Patronais",
    "339014": "Diárias – Pessoal Civil",
    "339018": "Auxílio Financeiro a Estudantes",
    "339019": "Auxílio Financeiro a Pesquisadores (Proj. Pesquisa)",
    "339020": "Auxílio Financeiro a Pesquisadores",
    "339021": "Bolsas de Estudo no País",
    "339022": "Bolsas de Estudo no Exterior",
    "339030": "Material de Consumo",
    "339032": "Material de Distribuição Gratuita",
    "339033": "Passagens e Despesas com Locomoção",
    "339034": "Outras Despesas de Pessoal decorrentes de Contratos Terceirizados",
    "339035": "Serviços de Consultoria",
    "339036": "Outros Serviços de Terceiros – Pessoa Física",
    "339037": "Locação de Mão de Obra",
    "339038": "Arrendamento Mercantil",
    "339039": "Outros Serviços de Terceiros – Pessoa Jurídica",
    "339040": "Serviços de Tecnologia da Informação e Comunicação – PJ",
    "339041": "Contribuições",
    "339046": "Auxílio Alimentação",
    "339047": "Obrigações Tributárias e Contributivas",
    "339048": "Outros Auxílios Financeiros a Pessoas Físicas",
    "339049": "Auxílio-Transporte",
    "339091": "Sentenças Judiciais",
    "339092": "Despesas de Exercícios Anteriores",
    "339093": "Indenizações e Restituições",
    "339094": "Indenizações e Restituições Trabalhistas",
    "339095": "Pensões Especiais",
    "339096": "Ressarcimento de Despesas de Pessoal no Exterior",
    "339147": "Obrigações Tributárias e Contributivas (taxas/siscomex)",
    # ── Capital / Investimentos ───────────────────────────────────────────────
    "449030": "Material de Consumo (Capital)",
    "449051": "Obras e Instalações",
    "449052": "Equipamentos e Material Permanente",
    "449061": "Aquisição de Imóveis",
    "449071": "Obras e Instalações (Capital – Proj. Estruturantes)",
    "449092": "Despesas de Exercícios Anteriores (Capital)",
}


# ═══════════════════════════════════════════════════════════════════════════════
# 2. MAPA DE PALAVRAS-CHAVE → ND
#    Regras de alta confiança: palavras/expressões que identificam a ND
#    com certeza em 90%+ dos despachos da UnB.
#
#    Formato: lista de (peso, [keywords], nd_codigo)
#    Peso 10 = certeza absoluta | Peso 7 = alta confiança | Peso 5 = provável
# ═══════════════════════════════════════════════════════════════════════════════

REGRAS_ND = [

    # ─── 339093 — Indenizações e Restituições ────────────────────────────────
    # (reembolso/restituição de valores pagos pelo próprio servidor)
    (10, ["reembolso", "ressarcimento", "restituição", "restitui"], "339093"),
    (10, ["indenização", "indenizacao", "indeni"], "339093"),
    (10, ["pagou com recursos próprios", "recurso próprio", "recursos proprios", "custeou com"], "339093"),
    (10, ["pago com recursos proprios", "pagou com recursos proprios"], "339093"),
    (10, ["ajuda de custo", "ajuda de custo pela"], "339093"),
    (10, ["auxílio moradia", "auxilio moradia"], "339093"),
    (10, ["devolução de valores", "devolucao de valores"], "339093"),
    (9,  ["bilhete rodoviário", "bilhete rodoviario", "comprou bilhete"], "339093"),
    (9,  ["certificado digital a3", "certificado digital tipo a3", "certificado digital icp"], "339093"),
    (9,  ["despesa com recursos próprios", "arcou com a despesa"], "339093"),

    # ─── 339014 — Diárias – Civil ─────────────────────────────────────────────
    (10, ["diária nacional", "diárias nacionais", "diaria nacional", "diarias nacionais"], "339014"),
    (10, ["diária internacional", "diárias internacionais", "diaria internacional"], "339014"),
    (10, ["diária em missão", "diárias em missão", "diaria em missao"], "339014"),
    (10, ["diária do servidor", "diárias do servidor", "diaria do servidor"], "339014"),
    (10, ["diária da servidora", "diárias da servidora"], "339014"),
    (9,  ["hospedagem e alimentação em viagem", "despesas de viagem a serviço"], "339014"),
    (9,  ["per diem", "per-diem", "perdiem"], "339014"),
    (8,  ["diária", "diárias", "diaria", "diarias"], "339014"),  # genérico — só se não bater PF antes

    # ─── 339036 — Outros Serviços Terceiros PF / GECC / Não-Servidor ─────────
    (10, ["gecc", "gratificação por encargo de curso", "gratificacao por encargo de curso"], "339036"),
    (10, ["encargo de curso e concurso", "encargo de concurso"], "339036"),
    (10, ["procap", "capacitacao procap", "capacitação procap"], "339036"),
    (10, ["diária de não servidor", "diária não servidor", "diaria nao servidor"], "339036"),
    (10, ["diária de colaborador eventual", "diarias colaborador eventual"], "339036"),
    (10, ["pró-labore", "pro-labore", "prolabore"], "339036"),
    (9,  ["pessoa física autônoma", "prestador autônomo", "autônomo sem cnpj"], "339036"),
    (9,  ["instrutor externo", "palestrante pessoa física", "palestrante pf"], "339036"),
    (8,  ["gratificação encargo", "gratificacao encargo"], "339036"),

    # ─── 339033 — Passagens e Despesas com Locomoção ─────────────────────────
    (10, ["passagem aérea", "passagem area", "passagens aéreas", "bilhete aéreo"], "339033"),
    (10, ["passagem terrestre", "passagem rodoviária", "passagem rodoviaria", "ônibus"], "339033"),
    (10, ["passagem fluvial", "passagem marítima", "passagem marítima"], "339033"),
    (10, ["táxi gov", "taxi gov", "taxigov"], "339033"),
    (10, ["passagem de avião", "passagem de onibus", "locomoção a serviço"], "339033"),
    (9,  ["despesa de locomoção", "despesas com locomoção", "despesas locomoção"], "339033"),
    (9,  ["translado aeroporto", "traslado"], "339033"),
    (9,  ["fretamento de veículo", "fretamento de aeronave"], "339033"),
    (8,  ["passagem", "passagens", "locomoção", "locomocao"], "339033"),

    # ─── 339030 — Material de Consumo ────────────────────────────────────────
    (10, ["material de consumo", "materiais de consumo"], "339030"),
    (10, ["almoxarifado central", "almox central", "almoxarifado"], "339030"),
    (10, ["papel a4", "papel sulfite", "resma", "cartolina"], "339030"),
    (10, ["toner", "cartucho de impressora", "cartucho de tinta"], "339030"),
    (10, ["material de escritório", "material de expediente", "material de papelaria"], "339030"),
    (10, ["material de limpeza", "produto de limpeza", "material de higiene"], "339030"),
    (10, ["artigos de copa", "itens de copa", "café, açúcar", "agua mineral"], "339030"),
    (10, ["material hospitalar", "material médico", "material odontológico", "material farmacológico"], "339030"),
    (10, ["material de laboratório", "reagente", "reagentes", "vidraria"], "339030"),
    (10, ["combustível", "gasolina", "diesel", "etanol", "abastecimento"], "339030"),
    (10, ["gás de cozinha", "gás encanado", "botijão de gás"], "339030"),
    (10, ["material elétrico", "lâmpada", "conduíte", "fio elétrico"], "339030"),
    (10, ["material de construção", "tinta para parede", "cimento", "areia"], "339030"),
    (10, ["insumo agrícola", "semente", "muda", "adubo", "fertilizante"], "339030"),
    (10, ["ração animal", "alimento para animal", "alimentação animal"], "339030"),
    (9,  ["material gráfico", "papel fotográfico", "banner", "faixa"], "339030"),
    (8,  ["suprimento", "suprimentos", "insumo", "insumos"], "339030"),

    # ─── 339039 — Outros Serviços Terceiros PJ ───────────────────────────────
    (10, ["inscrição em congresso", "inscrição em simpósio", "inscrição em evento científico"], "339039"),
    (10, ["inscrição em curso", "inscrição em treinamento", "inscrição em capacitação"], "339039"),
    (10, ["inscrição em workshop", "inscrição em seminário", "inscrição em conferência"], "339039"),
    (10, ["taxa de publicação", "article processing charge", "taxa apc", "taxa de submissão"], "339039"),
    (10, ["publicação de artigo", "publicação em revista", "publicação científica"], "339039"),
    (10, ["seguro viagem", "seguro de viagem", "seguro internacional"], "339039"),
    (10, ["serviço de tradução", "tradução de documento", "tradução juramentada"], "339039"),
    (10, ["interpretação simultânea", "tradução simultânea", "intérprete"], "339039"),
    (10, ["frete internacional", "frete aéreo", "remessa internacional", "envio de encomenda"], "339039"),
    (10, ["despesa bancária", "tarifa bancária", "taxa de transferência"], "339039"),
    (10, ["locação de veículo", "aluguel de carro", "locação de automóvel"], "339039"),
    (10, ["serviço de manutenção", "manutenção preventiva", "manutenção corretiva"], "339039"),
    (10, ["serviço gráfico", "impressão gráfica", "plotagem", "encadernação"], "339039"),
    (10, ["serviço de comunicação", "telefonia", "internet", "banda larga"], "339039"),
    (10, ["taxa de visão consular", "taxa consular", "visto", "apostilamento"], "339039"),
    (10, ["persianas", "cortinas", "instalação de persianas"], "339039"),
    (10, ["serviço de limpeza de ar condicionado", "higienização de ar condicionado"], "339039"),
    (10, ["serviço de fotografia", "captação de imagens", "filmagem"], "339039"),
    (9,  ["pessoa jurídica", "empresa prestadora", "prestação de serviços pj"], "339039"),
    (9,  ["serviços correlatos", "serviços de apoio", "serviços técnicos"], "339039"),
    (8,  ["inscrição", "inscricao", "evento", "congresso", "seminário", "simpósio"], "339039"),

    # ─── 339040 — TI / Software ───────────────────────────────────────────────
    (10, ["licença de software", "aquisição de licença", "licenciamento de software"], "339040"),
    (10, ["assinatura de software", "assinatura de sistema", "software as a service"], "339040"),
    (10, ["adobe creative cloud", "microsoft office", "microsoft 365", "autocad"], "339040"),
    (10, ["antivírus", "anti-vírus", "endpoint security"], "339040"),
    (10, ["hospedagem de site", "hospedagem web", "servidor virtual", "vps"], "339040"),
    (10, ["serviço de nuvem", "cloud computing", "aws", "azure", "google cloud"], "339040"),
    (10, ["sistema de informação", "sistema ti", "plataforma digital", "ferramenta digital"], "339040"),
    (10, ["domínio de internet", "registro de domínio", ".edu.br"], "339040"),
    (9,  ["suporte técnico de ti", "manutenção de sistema", "suporte de software"], "339040"),
    (8,  ["software", "sistema informatizado", "ti ", "tecnologia da informação"], "339040"),

    # ─── 339018 — Auxílio Financeiro a Estudantes ────────────────────────────
    (10, ["bolsa de extensão", "bolsa pibex", "auxílio bolsa de extensão"], "339018"),
    (10, ["bolsa de permanência", "auxílio permanência", "auxílio estudantil"], "339018"),
    (10, ["pibic", "iniciação científica pibic", "bolsa iniciação científica"], "339018"),
    (10, ["bolsa de graduação", "bolsa pré-iniciação científica"], "339018"),
    (10, ["auxílio financeiro a estudante", "auxílio a discente", "auxílio a aluno"], "339018"),
    (10, ["bolsa de extensão universitária", "auxílio de extensão"], "339018"),
    (10, ["bolsa de monitoria", "bolsa monitoria"], "339018"),
    (10, ["auxílio viagem para discente", "auxílio viagem discente", "auxílio a estudante para viagem"], "339018"),
    (10, ["bolsa de residência", "bolsa residência pedagógica"], "339018"),
    (9,  ["bolsa estudante", "bolsa aluno", "bolsa discente"], "339018"),

    # ─── 339020 — Auxílio Financeiro a Pesquisadores ─────────────────────────
    (10, ["bolsa de pós-doutorado", "bolsa pos-doutorado", "bolsa pós-doutoral"], "339020"),
    (10, ["bolsa de pesquisa", "bolsa de produtividade", "bolsa pq", "bolsa produtividade cnpq"], "339020"),
    (10, ["bolsa de pesquisador", "auxílio financeiro a pesquisador"], "339020"),
    (10, ["bolsa preceptoria", "bolsa de preceptoria", "preceptor de residência"], "339020"),
    (10, ["capes bolsa", "bolsa capes", "bolsa cnpq pesquisador"], "339020"),
    (10, ["bolsa de pós-graduação", "bolsa de mestrado", "bolsa de doutorado"], "339020"),
    (9,  ["bolsa pesquisador", "bolsa pós-graduação", "bolsa pesquisa"], "339020"),

    # ─── 339048 — Outros Auxílios Financeiros PF ─────────────────────────────
    (10, ["auxílio financeiro a voluntário", "bolsa de voluntário"], "339048"),
    (10, ["bolsa de extensão comunitária", "bolsa participação social"], "339048"),
    (9,  ["outro auxílio financeiro", "auxílio a colaborador voluntário"], "339048"),

    # ─── 339037 — Locação de Mão de Obra ─────────────────────────────────────
    (10, ["locação de mão de obra", "locacao de mao de obra"], "339037"),
    (10, ["copeiragem", "serviço de copeiragem", "copa e limpeza terceirizado"], "339037"),
    (10, ["vigilância terceirizada", "serviço de vigilância", "segurança terceirizada"], "339037"),
    (10, ["limpeza e conservação terceirizada", "limpeza predial terceirizada"], "339037"),
    (10, ["manutenção predial terceirizada", "serviços gerais terceirizados"], "339037"),
    (10, ["recepção terceirizada", "serviço de recepção", "portaria terceirizada"], "339037"),
    (9,  ["serviço terceirizado de", "contrato terceirizado"], "339037"),

    # ─── 339047 — Obrigações Tributárias e Contributivas ─────────────────────
    (10, ["multa de trânsito", "multa cbl", "multa cbdf", "multa detran"], "339047"),
    (10, ["ipva", "licenciamento de veículo", "dpvat", "crlv"], "339047"),
    (10, ["taxa de licenciamento", "taxa de registro", "taxa de emissão de cédula"], "339047"),
    (10, ["imposto de importação", "iof", "pis/cofins s/importação"], "339047"),
    (9,  ["obrigação tributária", "encargo tributário", "contribuição compulsória"], "339047"),

    # ─── 339092 — Despesas de Exercícios Anteriores ───────────────────────────
    (10, ["exercício anterior", "exercícios anteriores", "exercicio anterior"], "339092"),
    (10, ["reconhecimento de dívida de exercício anterior", "dívida de exercício anterior"], "339092"),
    (10, ["despesa de exercício anterior", "despesas de exercícios anteriores"], "339092"),
    (9,  ["dívida anterior", "saldo de exercício anterior"], "339092"),

    # ─── 339093 — Indenizações e Restituições (geral) ────────────────────────
    (10, ["indenização por dano", "indenização de servidor", "indenização por extravio"], "339093"),
    (10, ["reconhecimento de dívida", "dívida reconhecida administrativamente"], "339093"),
    (10, ["restituição de empenho", "reembolso de empenho anulado"], "339093"),
    (10, ["ajuda de custo por mudança de domicílio", "ajuda de custo transferência"], "339093"),

    # ─── 339147 — Taxas / SISCOMEX / Importação ─────────────────────────────
    (10, ["siscomex", "taxa siscomex", "di siscomex"], "339147"),
    (10, ["desembaraço aduaneiro", "despacho aduaneiro", "taxa de desembaraço"], "339147"),
    (10, ["armazenagem alfandegária", "tarifa alfandegária"], "339147"),
    (9,  ["importação", "frete de importação", "taxa de importação"], "339147"),

    # ─── 449052 — Equipamentos e Material Permanente ─────────────────────────
    (10, ["equipamento permanente", "bem permanente", "material permanente"], "449052"),
    (10, ["notebook", "computador", "desktop", "servidor de dados"], "449052"),
    (10, ["impressora", "scanner", "multifuncional", "plotter"], "449052"),
    (10, ["câmera fotográfica", "câmera de vídeo", "filmadora", "projetor"], "449052"),
    (10, ["televisão", "monitor", "display", "tela led"], "449052"),
    (10, ["ar condicionado", "condicionador de ar"], "449052"),
    (10, ["mobiliário", "cadeira ergonômica", "mesa", "armário de aço", "estante de aço"], "449052"),
    (10, ["geladeira", "freezer", "frigobar", "micro-ondas", "bebedouro"], "449052"),
    (10, ["instrumento científico", "equipamento de laboratório", "centrífuga", "espectrofotômetro"], "449052"),
    (10, ["quadro magnético", "quadro branco", "lousa interativa"], "449052"),
    (10, ["aparelho de som", "projetor multimídia", "data show"], "449052"),
    (9,  ["aquisição de bem", "compra de equipamento", "bem duradouro"], "449052"),

    # ─── 449051 — Obras e Instalações ────────────────────────────────────────
    (10, ["obra de construção", "reforma predial", "ampliação de prédio"], "449051"),
    (10, ["instalação elétrica", "instalação hidráulica", "instalação de rede"], "449051"),
    (9,  ["obra", "construção", "reforma do espaço físico"], "449051"),
]


# ═══════════════════════════════════════════════════════════════════════════════
# 3. PADRÕES REGEX PARA EXTRAIR A UGR DO TEXTO
# ═══════════════════════════════════════════════════════════════════════════════

# Mapa nome longo → sigla (para cabeçalhos "Centro de custo: NOME COMPLETO")
NOME_PARA_SIGLA_UGR = {
    # Decanatos
    "decanato de planejamento": "DPO",
    "planej, orça e aval": "DPO",
    "planejamento, orçamento e avaliação": "DPO",
    "decanato de administracao": "DAF",
    "decanato de administração": "DAF",
    "decanato de assuntos comunitarios": "DAC",
    "decanato de assuntos comunitários": "DAC",
    "decanato de ensino de graduacao": "DEG",
    "decanato de ensino de graduação": "DEG",
    "decanato de extensao": "DEX",
    "decanato de extensão": "DEX",
    "decanato de gestao de pessoas": "DGP",
    "decanato de gestão de pessoas": "DGP",
    "decanato de pesquisa e inovacao": "DPI",
    "decanato de pesquisa e inovação": "DPI",
    "decanato de pos-graduacao": "DPG",
    "decanato de pós-graduação": "DPG",
    # Secretarias
    "secretaria de tecnologia da informacao": "STI",
    "secretaria de tecnologia da informação": "STI",
    "secretaria de infraestrutura": "INFRA",
    "secretaria de comunicacao": "SECOM",
    "secretaria de comunicação": "SECOM",
    "secretaria de assuntos internacionais": "INT",
    "secretaria de meio ambiente": "SEMA",
    "secretaria de patrimonio imobiliario": "SPI",
    "secretaria de administracao academica": "SAA",
    "secretaria de administração acadêmica": "SAA",
    "secretaria de direitos humanos": "SDH",
    # Bibliotecas, prefeituras, ouvidorias
    "biblioteca central": "BCE",
    "arquivo central": "ACE",
    "prefeitura da unb": "PRC",
    "ouvidoria": "OUV",
    "auditoria": "AUD",
    "editora universidade de brasilia": "EDU",
    "editora da universidade de brasília": "EDU",
    "gabinete da reitora": "GRE",
    "vice reitoria": "VRT",
    "vice-reitoria": "VRT",
    "procuradoria federal": "PF",
    "procuradoria federal junto": "PF",
    "radio e televisao": "UnBTV",
    "rádio e televisão universitária": "UnBTV",
    # Centros
    "centro de desenvolvimento sustentavel": "CDS",
    "centro de desenvolvimento sustentável": "CDS",
    "centro de educacao a distancia": "CEAD",
    "centro de educação a distância": "CEAD",
    "centro de excelencia em turismo": "CET",
    "centro est. avancados": "CEAM",
    "centro de estudos avancados multidisciplinares": "CEAM",
    "centro inter fisica da mat condensada": "CIFMC",
    "centro pesq aplic bambu": "CPAB",
    "assessoria de acompanhamento e mediacao": "CPAD",
    "assessoria de acompanhamento e mediação": "CPAD",
    "centro ref em cons nat": "CRAD",
    "centro de referencia em conservacao": "CRAD",
    "cent internac de bioetica": "CIBH",
    "parque cientif e tecnologico": "PCTEC",
    "parque científico e tecnológico": "PCTEC",
    "nucleo de inovacao tecnologica": "NITCDT",
    "núcleo de inovação tecnológica": "NITCDT",
    "fazenda agua limpa": "FAL",
    "fazenda água limpa": "FAL",
    "unb cerrado": "CER",
    "diretoria de contratos administrativos": "DCA",
    # Faculdades
    "faculdade de comunicacao": "FAC",
    "faculdade de comunicação": "FAC",
    "faculdade de economia, administracao": "FACE",
    "faculdade de economia, administração": "FACE",
    "faculdade de arquitetura e urbanismo": "FAU",
    "faculdade de agronomia e medicina veterinaria": "FAV",
    "faculdade de agronomia e medicina veterinária": "FAV",
    "faculdade de ceilandia": "FCE",
    "faculdade de ceilândia": "FCE",
    "faculdade de ciencia da informacao": "FCI",
    "faculdade de ciência da informação": "FCI",
    "faculdade de direito": "FD",
    "faculdade de educacao": "FE",
    "faculdade de educação": "FE",
    "faculdade de educacao fisica": "FEF",
    "faculdade de educação física": "FEF",
    "faculdade unb gama": "FGA",
    "faculdade de medicina": "FM",
    "faculdade de ciencias de saude": "FS",
    "faculdade de ciências de saúde": "FS",
    "faculdade de tecnologia": "FT",
    "faculdade unb planaltina": "FUP",
    # Institutos
    "instituto de ciencias biologicas": "IB",
    "instituto de ciências biológicas": "IB",
    "instituto de ciencias sociais": "ICS",
    "instituto de ciências sociais": "ICS",
    "instituto de artes": "IDA",
    "instituto de ciencias exatas": "IE",
    "instituto de ciências exatas": "IE",
    "instituto de fisica": "IF",
    "instituto de física": "IF",
    "instituto de geociencias": "IG",
    "instituto de geociências": "IG",
    "instituto de ciencias humanas": "ICH",
    "instituto de ciências humanas": "ICH",
    "instituto de letras": "IL",
    "instituto de psicologia": "IP",
    "instituto de ciencia politica": "IPOL",
    "instituto de ciência política": "IPOL",
    "instituto de quimica": "IQ",
    "instituto de química": "IQ",
    "instituto de relacoes internacionais": "IREL",
    "instituto de relações internacionais": "IREL",
}


# Padrões regex para capturar a UGR diretamente do texto do despacho
# Cada tupla: (peso, padrão_regex)
PADROES_UGR = [
    # Alta certeza: menciona explicitamente "Matriz/SIGLA" ou "recursos da/do SIGLA"
    (10, r"(?:com\s+recursos\s+d[aoe]\s+)?[Mm]atriz\s*/\s*([A-Z]{2,10})(?:\s+\(|[\s,\.]|$)"),
    (10, r"com\s+recursos\s+d[aoe]\s+(?:Matriz/)?([A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ]{2,10})(?:\s+\(|[\s,\.]|$)"),
    (9,  r"recursos\s+provenientes\s+d[aoe]\s+([A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ]{2,10})(?:\s+\(|[\s,\.]|$)"),
    (9,  r"recursos\s+oriundos\s+d[aoe]\s+([A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ]{2,10})(?:\s+\(|[\s,\.]|$)"),
    (9,  r"dotação\s+orçamentária\s+d[aoe]\s+([A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ]{2,10})(?:\s+\(|[\s,\.]|$)"),
    (9,  r"crédito\s+orçamentário\s+d[aoe]\s+([A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ]{2,10})(?:\s+\(|[\s,\.]|$)"),
    (9,  r"saldo\s+orçamentário\s+d[aoe]\s+([A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ]{2,10})(?:\s+\(|[\s,\.]|$)"),
    (8,  r"autorizado\s+(?:pelo|pela)\s+([A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ]{2,10})(?:\s+\(|[\s,\.]|$)"),
    (7,  r"recurso\s+d[aoe]\s+([A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ]{2,10})(?:\s+\(|[\s,\.]|$)"),
]


# ═══════════════════════════════════════════════════════════════════════════════
# 4. PADRÕES REGEX PARA EXTRAIR O FAVORECIDO
# ═══════════════════════════════════════════════════════════════════════════════

PADROES_FAVORECIDO = [
    # ── Pessoa Jurídica (Empresas, Fundações, Instituições, Fornecedores PJ) ─
    (10, r"em\s+favor\s+d[ao]\s+empresa\s+([A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ0-9\.\-\&]+(?: [A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ0-9\.\-\&]+){1,6})"),
    (10, r"à\s+empresa\s+([A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ0-9\.\-\&]+(?: [A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ0-9\.\-\&]+){1,6})"),
    (10, r"à\s+contratada\s+([A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ0-9\.\-\&]+(?: [A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ0-9\.\-\&]+){1,6})"),
    (10, r"em\s+favor\s+d[ao]\s+fundação\s+([A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ0-9\.\-\&]+(?: [A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ0-9\.\-\&]+){1,6})"),
    (10, r"em\s+favor\s+d[ao]\s+instituição\s+([A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ0-9\.\-\&]+(?: [A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ0-9\.\-\&]+){1,6})"),
    (10, r"em\s+favor\s+de\s+([A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ0-9\.\-\&]+(?:\s+LTDA|\s+S\.?A\.?|\s+ME|\s+EPP|\s+EIRELI|\s+INC|\s+CORP))"),
    (10, r"pagamento\s+[àa]\s+([A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ0-9\.\-\&]+(?:\s+LTDA|\s+S\.?A\.?|\s+ME|\s+EPP|\s+EIRELI))"),

    # ── Pessoa Física (Servidores, Docentes, Estudantes, Pesquisadores) ──────
    (10, r"em\s+favor\s+d[ao]s?\s+servidora?s?\s+([A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ][a-záéíóúàâêîôûãõç]+(?: [A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ][a-záéíóúàâêîôûãõç]+){1,5})"),
    (10, r"reembolso\s+d[ao]s?\s+servidora?s?\s+([A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ][a-záéíóúàâêîôûãõç]+(?: [A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ][a-záéíóúàâêîôûãõç]+){1,5})"),
    (10, r"reembolso\s+d[ao]s?\s+docente\s+([A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ][a-záéíóúàâêîôûãõç]+(?: [A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ][a-záéíóúàâêîôûãõç]+){1,5})"),
    (10, r"d[ao]s?\s+servidora?\s+([A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ][a-záéíóúàâêîôûãõç]+(?: [A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ][a-záéíóúàâêîôûãõç]+){1,5})\s+referente"),
    (10, r"d[ao]s?\s+servidora?\s+([A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ][a-záéíóúàâêîôûãõç]+(?: [A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ][a-záéíóúàâêîôûãõç]+){1,5})\s+(?:,|\.|\bpara\b|\bem\b)"),
    (10, r"em\s+favor\s+de\s+([A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ][a-záéíóúàâêîôûãõç]+(?: [A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ][a-záéíóúàâêîôûãõç]+){1,5})"),
    (9,  r"para\s+a\s+servidora?\s+([A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ][a-záéíóúàâêîôûãõç]+(?: [A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ][a-záéíóúàâêîôûãõç]+){1,5})"),
    (9,  r"ao\s+servidor\s+([A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ][a-záéíóúàâêîôûãõç]+(?: [A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ][a-záéíóúàâêîôûãõç]+){1,5})"),
    (9,  r"à\s+servidora\s+([A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ][a-záéíóúàâêîôûãõç]+(?: [A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ][a-záéíóúàâêîôûãõç]+){1,5})"),
    (9,  r"pago(?:s)?\s+pela\s+servidora?\s+([A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ][a-záéíóúàâêîôûãõç]+(?: [A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ][a-záéíóúàâêîôûãõç]+){1,5})"),
    (9,  r"pago(?:s)?\s+pelo\s+servidor\s+([A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ][a-záéíóúàâêîôûãõç]+(?: [A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ][a-záéíóúàâêîôûãõç]+){1,5})"),
    (9,  r"realizada\s+(?:com\s+recursos\s+próprios\s+)?pela\s+servidora?\s+([A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ][a-záéíóúàâêîôûãõç]+(?: [A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ][a-záéíóúàâêîôûãõç]+){1,5})"),
    (9,  r"realizado\s+(?:com\s+recursos\s+próprios\s+)?pelo\s+servidor\s+([A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ][a-záéíóúàâêîôûãõç]+(?: [A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ][a-záéíóúàâêîôûãõç]+){1,5})"),
    (9,  r"custeado\s+pela\s+servidora?\s+([A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ][a-záéíóúàâêîôûãõç]+(?: [A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ][a-záéíóúàâêîôûãõç]+){1,5})"),
    (9,  r"inscrição\s+de\s+([A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ][a-záéíóúàâêîôûãõç]+(?: [A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ][a-záéíóúàâêîôûãõç]+){1,5})\s+em"),
    (9,  r"participação\s+de\s+([A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ][a-záéíóúàâêîôûãõç]+(?: [A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ][a-záéíóúàâêîôûãõç]+){1,5})\s+(?:em|no|na)"),
    (9,  r"diárias\s+d[ao]\s+servidor[a]?\s+([A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ][a-záéíóúàâêîôûãõç]+(?: [A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ][a-záéíóúàâêîôûãõç]+){1,5})"),
    (8,  r"viagem\s+de\s+([A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ][a-záéíóúàâêîôûãõç]+(?: [A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ][a-záéíóúàâêîôûãõç]+){1,5})\s+(?:a|para|ao|à)"),
    (8,  r"beneficiária?\s+([A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ][a-záéíóúàâêîôûãõç]+(?: [A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ][a-záéíóúàâêîôûãõç]+){1,5})"),
    (8,  r"em\s+nome\s+de\s+([A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ][a-záéíóúàâêîôûãõç]+(?: [A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ][a-záéíóúàâêîôûãõç]+){1,5})"),
    # Assinatura no final do despacho (servidor que assinou = frequentemente o requerente)
    (5, r"Atenciosamente.*?(?:,\s*|\n)([A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ][a-záéíóúàâêîôûãõç]+(?: [A-ZÁÉÍÓÚÀÂÊÎÔÛÃÕÇ][a-záéíóúàâêîôûãõç]+){1,5})\s*,?\s*(?:Servidor|Assessor|Diretor|Coordenador|Professor|Docente)"),
]


# ═══════════════════════════════════════════════════════════════════════════════
# 5. TEMPLATES AUTOMÁTICOS DE DESCRIÇÃO NC POR ND
#    Geram frases prontas para o campo "Descrição da NC" no SIAFI
# ═══════════════════════════════════════════════════════════════════════════════

def _nome_curto(nome: str, max_chars: int = 20) -> str:
    """Abrevia nome para SIAFI: 'João Carlos da Silva Pereira' → 'João C.S. Pereira'"""
    if not nome:
        return ""
    partes = nome.strip().split()
    if len(partes) <= 2:
        return nome[:max_chars]
    # Primeiro nome completo + iniciais do meio + último nome completo
    primeiro = partes[0]
    ultimo = partes[-1]
    meios = "".join(p[0] + "." for p in partes[1:-1] if p.lower() not in ("da","de","do","das","dos","e"))
    resultado = f"{primeiro} {meios} {ultimo}".strip()
    return resultado[:max_chars]


def _sei_curto(processo_sei: str) -> str:
    """Formata número SEI para exibição compacta: '23106.097294/2026-49' → 'SEI 097294/2026'"""
    if not processo_sei:
        return ""
    # Extrai a parte numérica do meio (após o ponto) e o ano
    m = re.search(r"\d{5}\.(\d{6})/(\d{4})", processo_sei)
    if m:
        return f"SEI {m.group(1)}/{m.group(2)}"
    return f"SEI {processo_sei[-15:]}" if len(processo_sei) > 15 else f"SEI {processo_sei}"


def _sintetizar_objeto(objeto_raw: str, fav_nome: str = "") -> str:
    """
    Limpa e sintetiza o objeto de qualquer despacho SEI, removendo chavões burocráticos.
    """
    if not objeto_raw:
        return ""

    txt = objeto_raw.strip()

    # Remover prefixos burocráticos comuns em despachos SEI
    padroes_remover_inicio = [
        r"^homologada\s+a\s+despesa.*?(?:solicito|autorizo)\s+",
        r"^solicito\s+o\s+detalhamento\s+de\s+crédito.*?(?:visando|para|referente)\s+",
        r"^solicito\s+a\s+descentralização\s+de\s+crédito.*?(?:visando|para|referente)\s+",
        r"^visando\s+(?:o\s+pagamento\s+de|a\s+aquisição\s+de|o\s+atendimento\s+d[ea]s?)?\s*",
        r"^referente\s+[àa]o?\s+(?:pagamento\s+de|aquisição\s+de|concessão\s+de)?\s*",
        r"^com\s+vistas\s+[àa]o?\s+",
        r"^para\s+(?:pagamento\s+de|aquisição\s+de|atendimento\s+d[ea]s?)\s*",
        r"^reembolso\s+d[ao]s?\s+servidora?\s+.*?\s+referente\s+[àa]o?\s+",
    ]

    for p in padroes_remover_inicio:
        txt = re.sub(p, "", txt, flags=re.I).strip()

    # Se o nome do favorecido estiver dentro do texto do objeto, remove a redundância
    if fav_nome and len(fav_nome) >= 4:
        txt = re.sub(rf"^.*?\b{re.escape(fav_nome)}\b\s*(?:referente\s+[àa]o?|da|do)?\s*", "", txt, flags=re.I).strip()

    # Remover resíduos como "no valor de R$ X" ou números de despacho
    txt = re.sub(r",?\s*no\s+valor\s+de\s+R\$\s*[\d\.,]+(?:\s*\([^)]+\))?", "", txt, flags=re.I).strip()
    txt = re.sub(r",?\s*autorizado\s+no\s+Despacho\s+\d+", "", txt, flags=re.I).strip()
    txt = re.sub(r",?\s*realizada\s+com\s+recursos\s+próprios", "", txt, flags=re.I).strip()

    txt = txt.strip(" ,.-")
    return txt


def gerar_descricao_nc(nd_codigo: str, favorecido: str, objeto_resumo: str,
                        processo_sei: str = "", valor: str = "", ugr: str = "") -> str:
    """
    Gera descrição NC perfeita, lógica e bem articulada para uso no SIAFIWeb.
    """
    fav_nome = favorecido.strip() if favorecido else ""
    sei_full  = f"Proc. SEI {processo_sei}" if processo_sei else ""
    val_str   = f"R$ {valor}" if valor else ""
    ugr_str   = f"Recursos {ugr}" if ugr else ""

    # Limpeza gramatical inteligente do objeto
    obj_limpo = _sintetizar_objeto(objeto_resumo, fav_nome)

    # Definir componente principal de finalidade por ND
    if nd_codigo == "339093":  # Reembolso / Indenização
        detalhe = obj_limpo if obj_limpo else "aquisição com recursos próprios"
        partes = [f"Reembolso de despesa própria ({detalhe})"]
        if fav_nome:
            partes.append(f"Favorecido: {fav_nome}")
        if ugr_str:
            partes.append(ugr_str)
        if val_str:
            partes.append(f"({val_str})")

    elif nd_codigo == "339014":  # Diárias
        detalhe = f"diárias ({obj_limpo})" if obj_limpo and "diária" not in obj_limpo.lower() else "concessão de diárias"
        partes = [detalhe.capitalize()]
        if fav_nome:
            partes.append(f"Favorecido: {fav_nome}")
        if ugr_str:
            partes.append(ugr_str)
        if val_str:
            partes.append(f"({val_str})")

    elif nd_codigo == "339033":  # Passagens
        partes = ["Aquisição de passagens e locomoção"]
        if obj_limpo:
            partes[0] += f" ({obj_limpo})"
        if fav_nome:
            partes.append(f"Favorecido: {fav_nome}")
        if ugr_str:
            partes.append(ugr_str)
        if val_str:
            partes.append(f"({val_str})")

    elif nd_codigo == "339036":  # GECC / Terceiros PF
        tipo_pf = "GECC (Gratificação de Encargo de Curso/Concurso)" if any(k in (objeto_resumo or "").lower() for k in ["gecc", "encargo"]) else "Serviços de Terceiros PF"
        partes = [f"Pagamento de {tipo_pf}"]
        if obj_limpo:
            partes[0] += f" ({obj_limpo})"
        if fav_nome:
            partes.append(f"Favorecido: {fav_nome}")
        if ugr_str:
            partes.append(ugr_str)
        if val_str:
            partes.append(f"({val_str})")

    elif nd_codigo == "339039":  # Terceiros PJ / Inscrições
        tipo_pj = "taxa de inscrição em evento/capacitação" if any(k in (objeto_resumo or "").lower() for k in ["inscriç", "congresso", "curso"]) else "Serviços de Terceiros PJ"
        partes = [f"Pagamento de {tipo_pj}"]
        if obj_limpo and "inscriç" not in obj_limpo.lower():
            partes[0] += f" ({obj_limpo})"
        if fav_nome:
            partes.append(f"Favorecido: {fav_nome}")
        if ugr_str:
            partes.append(ugr_str)
        if val_str:
            partes.append(f"({val_str})")

    elif nd_codigo == "339040":  # TI / Software
        partes = ["Aquisição de licença de software / TI"]
        if obj_limpo:
            partes[0] += f" ({obj_limpo})"
        if fav_nome:
            partes.append(f"Favorecido: {fav_nome}")
        if ugr_str:
            partes.append(ugr_str)
        if val_str:
            partes.append(f"({val_str})")

    elif nd_codigo == "339018":  # Auxílio Estudante
        partes = ["Auxílio financeiro a estudante"]
        if obj_limpo:
            partes[0] += f" ({obj_limpo})"
        if fav_nome:
            partes.append(f"Favorecido: {fav_nome}")
        if ugr_str:
            partes.append(ugr_str)
        if val_str:
            partes.append(f"({val_str})")

    else:  # Genérico / Outras NDs
        det = obj_limpo if obj_limpo else "despesas orçamentárias"
        partes = [f"Detalhamento de crédito para {det}"]
        if fav_nome:
            partes.append(f"Favorecido: {fav_nome}")
        if ugr_str:
            partes.append(ugr_str)
        if val_str:
            partes.append(f"({val_str})")

    base = " – ".join(partes)
    return f"{base} – {sei_full}." if sei_full else f"{base}."



# ═══════════════════════════════════════════════════════════════════════════════
# 6. MOTOR DE EXTRAÇÃO PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════════

def _norm(txt: str) -> str:
    """Normaliza texto removendo acentos e convertendo para minúsculas."""
    return ''.join(
        c for c in unicodedata.normalize('NFD', str(txt).lower())
        if unicodedata.category(c) != 'Mn'
    )


def detectar_nd(texto: str) -> tuple[str, str, int]:
    """
    Detecta a Natureza de Despesa por palavras-chave no texto.
    Retorna: (nd_codigo, nd_descricao, score_confianca)
    """
    txt_norm = _norm(texto)
    melhor_score = 0
    melhor_nd = ("", "", 0)

    for peso, keywords, nd_cod in REGRAS_ND:
        for kw in keywords:
            if _norm(kw) in txt_norm:
                score_total = peso
                if score_total > melhor_score:
                    melhor_score = score_total
                    melhor_nd = (nd_cod, TABELA_ND.get(nd_cod, ""), score_total)

    return melhor_nd


MAPA_CODIGOS_UGR = {
    "ACE": "155027", "AUD": "154222", "BCE": "154197", "CCOM": "150241", "CDS": "154368",
    "CEAD": "154175", "CEAM": "154173", "CER": "152364", "CET": "154371", "CIBH": "156850",
    "CIFMC": "154198", "CPAB": "154271", "CPAD": "157250", "CRAD": "154304", "DAC": "154152",
    "DAF": "154151", "DEG": "154168", "DEX": "154153", "DGP": "152386", "DPG": "154154",
    "DPI": "156047", "DPO": "152387", "EDU": "154078", "FAL": "154226", "FCE": "150243",
    "FGA": "150242", "FUP": "154329", "GRE": "154156", "INFRA": "154920", "INT": "154297",
    "NITCDT": "154172", "OUV": "152383", "PCTEC": "156247", "PF": "154218", "PRC": "154191",
    "SAA": "154269", "SDH": "155099", "SECOM": "154221", "SEMA": "156478", "SPI": "154155",
    "STI": "154076", "UNBTV": "154190", "VRT": "154227", "DCA": "154922", "FAC": "154169",
    "FACE": "154164", "FAU": "154161", "FAV": "154251", "FCI": "151833", "FD": "154263",
    "FE": "154165", "FEF": "154256", "FM": "154299", "FS": "154163", "FT": "154162",
    "IB": "154158", "ICS": "154283", "IDA": "154167", "IE": "154157", "IF": "154228",
    "IG": "154188", "ICH": "154159", "IL": "154160", "IP": "154166", "IPOL": "154278",
    "IQ": "154230", "IREL": "154264"
}


def obter_codigo_ugr(ugr_str: str = "", texto_contexto: str = "") -> str:
    """
    Localiza e retorna o código numérico de 6 dígitos da UGR (SIAFI).
    Exemplo: 'PCTEC' ou 'Unidade Administrativa/PCTEC' -> '156247'
    """
    alvo = f"{ugr_str or ''} {texto_contexto or ''}".upper()
    if not alvo.strip():
        return ""

    # 1. Procura se já há código numérico de 6 dígitos na string
    m_cod = re.search(r"\b(15\d{4})\b", alvo)
    if m_cod:
        return m_cod.group(1)

    # 2. Procura siglas exatas
    for sigla, cod in MAPA_CODIGOS_UGR.items():
        if re.search(rf"\b{re.escape(sigla)}\b", alvo):
            return cod

    # 3. Procura por extensão no mapa NOME_PARA_SIGLA_UGR
    norm_alvo = _norm(alvo)
    for nome_chave, sigla in NOME_PARA_SIGLA_UGR.items():
        if _norm(nome_chave) in norm_alvo:
            return MAPA_CODIGOS_UGR.get(sigla, "")

    return ""


def detectar_ugr(texto: str) -> tuple[str, int]:
    """
    Detecta a UGR responsável pelos recursos.
    Retorna: (sigla_ugr, score_confianca)
    """
    txt_norm = _norm(texto)

    # 1. Tentar padrões regex de alta confiança
    for peso, padrao in PADROES_UGR:
        m = re.search(padrao, texto, re.I)
        if m:
            sigla = m.group(1).strip().upper()
            if len(sigla) >= 2 and sigla.isalpha():
                return (sigla, peso)

    # 2. Fallback: comparar "Centro de custo: NOME" com mapa de nomes
    cc_match = re.search(
        r"[Cc]entro\s+de\s+custo\s*[:\-]\s*(.{5,150}?)(?:\s*Para:|$)",
        texto, re.I
    )
    if cc_match:
        nome_cc = _norm(cc_match.group(1))
        for nome_chave, sigla in NOME_PARA_SIGLA_UGR.items():
            if _norm(nome_chave) in nome_cc:
                return (sigla, 7)

    # 3. Procurar qualquer sigla de UGR conhecida no texto
    for sigla_conhecida in MAPA_CODIGOS_UGR.keys():
        if re.search(rf"\b(?:recursos?\s+d[aoe]|crédito\s+para|unidade\s+administrativa/|ugr|para\s+[ao]s?)\s+{re.escape(sigla_conhecida)}\b", texto, re.I):
            return (sigla_conhecida, 8)
        if re.search(rf"\b{re.escape(sigla_conhecida)}\b", texto):
            return (sigla_conhecida, 6)

    return ("", 0)


def _validar_nome_favorecido(nome: str) -> bool:
    """
    Valida se a captura é um nome válido de pessoa física ou razão social jurídica.
    Rejeita rigorosamente frases burocráticas e capturas falsas (ex: 's durante os dias de programação').
    """
    if not nome or not isinstance(nome, str):
        return False

    nome_clean = nome.strip()
    if len(nome_clean) < 4:
        return False

    # A primeira letra útil deve ser maiúscula (exceto se for empresa/fundação/etc)
    if not nome_clean[0].isupper() and not re.match(r"^(?:empresa|fundação|instituição|lista)", nome_clean, re.I):
        return False

    # Lista de termos burocráticos proibidos em nomes de pessoas
    proibidos = {
        "DURANTE", "DIAS", "PROGRAMAÇÃO", "PROGRAMACAO", "SOLICITAÇÃO", "SOLICITACAO",
        "DETALHAMENTO", "DESCENTRALIZAÇÃO", "DESCENTRALIZACAO", "CRÉDITO", "CREDITO",
        "RECURSOS", "MATRIZ", "VALOR", "DOCUMENTO", "EXERCÍCIO", "EXERCICIO", "SISTEMA",
        "UNIVERSIDADE", "DECANATO", "FACULDADE", "INSTITUTO", "COORDENADORIA", "DIRETORIA",
        "SECRETARIA", "SERVIDORES", "DOCENTES", "ALUNOS", "DISCENTES", "PESQUISADORES",
        "EVENTO", "EVENTOS", "CONGRESSO", "VIAGEM", "VIAGENS", "CURSO", "CURSOS",
        "PARCELA", "FINAL", "UNIDADE", "ADMINISTRATIVA", "PCTEC", "PROVENIENTE",
        "CUSTEIO", "DESPESA", "DESPESAS", "ORÇAMENTÁRIO", "ORÇAMENTÁRIA", "ATENCIOSAMENTE",
        "HOMOLOGADA", "CONFORME", "TERMOS", "PROCESSO", "REFERÊNCIA", "REFERENCIA", "FAVORECIDO"
    }

    partes = nome_clean.split()
    partes_upper = [p.upper() for p in partes]

    # Se qualquer palavra capturada estiver na lista de proibidos -> rejeita captura falsa
    if any(p in proibidos for p in partes_upper):
        return False

    # Se for "LISTA DE CREDORES SIAFI 202XLCXXXXXX", é válido
    if re.match(r"^LISTA\s+DE\s+CREDORES", nome_clean, re.I):
        return True

    # Deve conter ao menos 2 palavras para ser um nome de pessoa (ou conter sigla PJ)
    siglas_pj = {"LTDA", "S.A", "SA", "ME", "EPP", "EIRELI", "CNPJ", "INC", "CORP", "FUNDAÇÃO", "FUNDACAO", "EMPRESA", "INSTITUTO", "SERPRO"}
    if len(partes) < 2 and not any(k in nome_clean.upper() for k in siglas_pj):
        return False

    return True


def detectar_favorecido(texto: str) -> tuple[str, int]:
    """
    Detecta o nome do favorecido a partir de padrões de texto.
    Retorna: (nome_favorecido, score_confianca)
    """
    # Siglas ou nomes de unidades que NÃO são pessoas
    _NAO_FAVORECIDOS = {
        "DGP", "DEG", "DEX", "DAF", "DAC", "DPO", "DPG", "DPI", "STI", "INFRA",
        "SECOM", "INT", "SPI", "SAA", "BCE", "PRC", "GRE", "VRT", "OUV", "AUD",
        "ACE", "FAL", "EDU", "UNBTV", "FAC", "FACE", "FAU", "FAV", "FCE", "FCI",
        "FD", "FE", "FEF", "FGA", "FM", "FS", "FT", "FUP", "IB", "ICS", "IDA",
        "IE", "IF", "IG", "ICH", "IL", "IP", "IPOL", "IQ", "IREL", "UNB",
        "FACULDADE", "DECANATO", "INSTITUTO", "SECRETARIA", "COORDENADORIA", "DIRETORIA"
    }

    for peso, padrao in PADROES_FAVORECIDO:
        m = re.search(padrao, texto, re.I | re.DOTALL)
        if m:
            nome = m.group(1).strip()
            # Limpa prefixos de cargo/tratamento
            nome = re.sub(r"^(?:servidora?|docente|professora?|alunoa?|pesquisadora?|senhora?)\s+", "", nome, flags=re.I).strip()
            # Limpa palavras de ligação no final do nome capturado
            nome = re.sub(r"\s+(?:referente|conforme|para|com|em|relativo|decorrente|cujo|cuja|que|solicito|solicitando|visando|autorizado)\b.*$", "", nome, flags=re.I).strip()
            
            # Verificar se não é uma UGR/Departamento
            nome_up = nome.upper()
            if any(n == nome_up or nome_up.startswith(n + " ") for n in _NAO_FAVORECIDOS):
                continue

            # Valida se realmente é um nome de pessoa ou empresa válido
            if _validar_nome_favorecido(nome):
                return (nome, peso)

    return ("", 0)


def extrair_por_regras(texto: str, planilha_cache: Optional[dict] = None, processo_sei: str = "", valor: str = "") -> dict:
    """
    Extrai todos os campos relevantes da NC usando regras locais.
    Retorna um dicionário com campos extraídos e score de confiança global.
    """
    nd_codigo, nd_descricao, nd_score = detectar_nd(texto)
    ugr_sigla, ugr_score = detectar_ugr(texto)
    favorecido, fav_score = detectar_favorecido(texto)

    # Multi-padrão de extração de objeto do despacho
    objeto_resumo = ""
    padroes_objeto = [
        # Padrão 1: Propósito explícito
        r"(?:visando|referente\s+[àa]o?|com\s+vistas\s+[àa]|cujo\s+objetivo\s+é|destinado\s+[àa]o?)\s+(.{5,130}?)(?:\.|\n|,\s+(?:conforme|autorizado|realizada|a\s+ser|com\s+base)|$)",
        # Padrão 2: Pagamento, aquisição ou concessão
        r"(?:pagamento\s+d[ea]|aquisição\s+d[ea]|compra\s+d[ea]|concessão\s+d[ea]|custeio\s+d[ea]|atendimento\s+d[ea]s?)\s+(.{5,130}?)(?:\.|\n|,\s+(?:conforme|autorizado|realizada|a\s+ser)|$)",
        # Padrão 3: Solicitações formais
        r"(?:solicito|solicitando)\s+(?:o\s+detalhamento|a\s+descentralização).*?\s+para\s+(.{5,130}?)(?:\.|\n|,\s+(?:conforme|autorizado|a\s+ser)|$)",
    ]

    for p in padroes_objeto:
        m = re.search(p, texto, re.I | re.DOTALL)
        if m:
            candidato = m.group(1).strip()
            if len(candidato) >= 8 and not re.match(r"^\d+|^R\$|^SEI|^SIAFI", candidato):
                objeto_resumo = candidato
                break

    descricao_nc = gerar_descricao_nc(nd_codigo, favorecido, objeto_resumo, processo_sei, valor, ugr=ugr_sigla)

    # Score global de confiança (0-10)
    scores_validos = [s for s in [nd_score, ugr_score, fav_score] if s > 0]
    confianca_global = sum(scores_validos) / (len(scores_validos) * 10) if scores_validos else 0.0

    # Montar resumo textual
    resumo_parts = []
    if ugr_sigla:
        resumo_parts.append(f"Recursos de {ugr_sigla}")
    if nd_descricao:
        resumo_parts.append(nd_descricao.lower())
    if favorecido:
        resumo_parts.append(f"favorecido: {favorecido}")
    resumo = ". ".join(resumo_parts).capitalize() + "." if resumo_parts else "Análise local não identificou todos os campos."

    return {
        "ugr":          ugr_sigla,
        "ugr_score":    ugr_score,
        "nd_codigo":    nd_codigo,
        "nd":           nd_descricao,
        "nd_score":     nd_score,
        "favorecido":   favorecido,
        "fav_score":    fav_score,
        "descricao_nc": descricao_nc,
        "objeto_resumo": objeto_resumo,
        "resumo":       resumo,
        "confianca_global": confianca_global,
        "fonte":        "regras_locais",
    }
