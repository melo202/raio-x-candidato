"""Configuração central do pipeline Raio-X do Candidato."""
from pathlib import Path

# ── Identidade do projeto ──────────────────────────────────────────────
PROJECT_NAME = "Raio-X do Candidato"
# Troque quando registrar o domínio próprio (GitHub Pages aceita custom domain)
BASE_URL = "https://melo202.github.io/raio-x-candidato"

# ── Eleição-alvo ───────────────────────────────────────────────────────
ANO_ELEICAO = 2026
# Anos usados no histórico e na série patrimonial (CPF é a chave entre eleições)
ANOS_GERAIS = [2014, 2018, 2022, 2026]
ANOS_MUNICIPAIS = [2016, 2020, 2024]
ANOS_PATRIMONIO = sorted(ANOS_GERAIS + ANOS_MUNICIPAIS)
# Receitas de campanha de eleições passadas (camada "doações que o candidato fez")
ANOS_RECEITAS = [2022, 2024]
# UFs a publicar (MVP: Goiás; escala nacional = todas)
UFS_ALVO = ["GO"]
TODAS_UFS = [
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS",
    "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC",
    "SE", "SP", "TO",
]

# ── Fontes oficiais (TSE — Portal de Dados Abertos) ────────────────────
TSE_CDN = "https://cdn.tse.jus.br/estatistica/sead/odsele"
URL_CONSULTA_CAND = TSE_CDN + "/consulta_cand/consulta_cand_{ano}.zip"
URL_BEM_CANDIDATO = TSE_CDN + "/bem_candidato/bem_candidato_{ano}.zip"
URL_FOTOS = (
    "https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes{ano}"
    "/fotos/foto_cand{ano}_{uf}_div.zip"
)
URL_PROPOSTA_GOVERNO = TSE_CDN + "/proposta_governo/proposta_governo_{ano}_{uf}.zip"
URL_REDE_SOCIAL = TSE_CDN + "/consulta_cand/rede_social_candidato_{ano}.zip"
URL_RECEITAS = (TSE_CDN +
                "/prestacao_contas/prestacao_de_contas_eleitorais_candidatos_{ano}.zip")
# Página do dataset (para o link "fonte" nas fichas)
URL_DATASET_CAND = "https://dadosabertos.tse.jus.br/dataset/candidatos-{ano}"
URL_DIVULGACAND = (
    "https://divulgacandcontas.tse.jus.br/divulga/#/candidato"
    "/{ano}/{cd_eleicao}/{sg_ue}/{sq}"
)

# ── TCU — contas julgadas irregulares (camada 6) ───────────────────────
# O portal do TCU bloqueia download automatizado (WAF). Baixe manualmente a
# lista (contasirregulares.tcu.gov.br → exportar CSV/XLSX) e salve em
# data/tcu/. O pipeline detecta qualquer .csv/.xlsx nessa pasta.
# Colunas reconhecidas (nomes flexíveis): CPF, NOME, PROCESSO, ACORDAO/DELIBERACAO,
# TRANSITO_JULGADO/DATA. Cruzamento primário por CPF; fallback nome normalizado.

# ── Caminhos ───────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
TCU_DIR = DATA_DIR / "tcu"
DB_PATH = DATA_DIR / "raiox.duckdb"
DOCS_DIR = ROOT / "docs"           # GitHub Pages serve /docs
OUT_DATA = DOCS_DIR / "data"       # JSONs publicados (1 ficha por candidato)
OUT_CARDS = DOCS_DIR / "c"         # stubs SEO/OG + share cards

# ── Situação da candidatura: rótulos amigáveis ─────────────────────────
SITUACAO_LABEL = {
    "#NE": "Aguardando julgamento",
    "#NULO": "Aguardando julgamento",
    "AGUARDANDO JULGAMENTO": "Aguardando julgamento",
    "APTO": "Apto",
    "DEFERIDO": "Deferido",
    "DEFERIDO COM RECURSO": "Deferido com recurso",
    "INDEFERIDO": "Indeferido",
    "INDEFERIDO COM RECURSO": "Indeferido com recurso",
    "CANCELADO": "Cancelado",
    "CASSADO": "Cassado",
    "FALECIDO": "Falecido",
    "INAPTO": "Inapto",
    "PENDENTE DE JULGAMENTO": "Pendente de julgamento",
    "RENÚNCIA": "Renunciou",
    "SUB JUDICE": "Sub judice (decisão pendente)",
    "IMPUGNADO": "Impugnado",
}

DISCLAIMER_PATRIMONIO = (
    "Valores declarados pelo próprio candidato à Justiça Eleitoral no registro "
    "de cada candidatura. A variação pode refletir herança, venda de empresa, "
    "valorização de imóvel, mudança de critério de declaração etc. Valores "
    "nominais, sem correção pela inflação."
)
DISCLAIMER_TCU = (
    "Constar da lista de contas julgadas irregulares do TCU não significa, por "
    "si só, inelegibilidade: quem decide sobre o registro é a Justiça Eleitoral, "
    "caso a caso, nos termos da LC 64/1990. Consulte o processo na fonte."
)
