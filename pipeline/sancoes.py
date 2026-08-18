"""Camada — cadastros oficiais de sanção (CGU / Portal da Transparência).

Três cadastros públicos, baixados diariamente do Portal da Transparência:
    CEIS — Empresas Inidôneas e Suspensas (inclui PESSOAS FÍSICAS sancionadas)
    CNEP — Empresas Punidas (Lei Anticorrupção)
    CEAF — Expulsões da Administração Federal (demissão, cassação, destituição)

Cruzamentos com salvaguardas de identidade:
    - CEIS/CNEP pessoa física: CPF COMPLETO → cruzamento direto, certeza total.
    - CEAF: o CPF vem mascarado (***.XXX.XXX-**) → exige dupla coincidência
      (mesmos 6 dígitos centrais E mesmo nome normalizado) para entrar na ficha.
    - Pessoas jurídicas ficam materializadas no banco (tabela sancoes_pj) para
      o cruzamento futuro com o QSA das empresas de candidatos.

Princípio do projeto: a ficha NUNCA diz "fraude" ou "corrupção" — diz que o
nome consta de cadastro oficial X, com processo, órgão, datas e link da fonte.
Sanção administrativa não é condenação criminal; o disclaimer é fixo.

Uso: python pipeline/sancoes.py            (baixa e materializa)
Depois: rode fichas.py de novo para injetar nas fichas.
"""
from __future__ import annotations

import csv
import io
import re
import unicodedata
import zipfile
from datetime import date

import duckdb
import requests

import config

CADASTROS = {
    "ceis": "Cadastro de Empresas Inidôneas e Suspensas (CEIS)",
    "cnep": "Cadastro Nacional de Empresas Punidas (CNEP)",
    "ceaf": "Cadastro de Expulsões da Administração Federal (CEAF)",
}
URL = "https://portaldatransparencia.gov.br/download-de-dados/{cad}/{data}"
CONSULTA = "https://portaldatransparencia.gov.br/sancoes/consulta"

DISCLAIMER = (
    "Registros administrativos publicados pela CGU no Portal da Transparência. "
    "Sanção administrativa não é condenação criminal e pode estar sub judice; "
    "os efeitos têm prazo e escopo definidos no processo indicado. Confira "
    "sempre na consulta oficial."
)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip().upper()


def _meio_cpf(cpf_mascarado_ou_cheio: str) -> str:
    """6 dígitos centrais do CPF (o que o Portal publica no CEAF)."""
    dig = re.sub(r"\D", "", str(cpf_mascarado_ou_cheio or ""))
    if len(dig) == 11:
        return dig[3:9]
    if len(dig) == 6:
        return dig
    return ""


def baixar(cad: str) -> list[dict]:
    from datetime import timedelta
    r = None
    for delta in (0, 1, 2, 3):                # CGU publica com atraso às vezes
        data = (date.today() - timedelta(days=delta)).strftime("%Y%m%d")
        url = URL.format(cad=cad, data=data)
        r = requests.get(url, timeout=300, allow_redirects=True,
                         headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200 and r.content[:2] == b"PK":   # zip válido
            if delta:
                print(f"  [info] {cad}: usando dump de {data} (D-{delta})")
            break
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        nome = next(n for n in z.namelist() if n.endswith(".csv"))
        texto = z.read(nome).decode("latin-1")
    return list(csv.DictReader(io.StringIO(texto), delimiter=";"))


def _campo(row: dict, *padroes: str) -> str:
    """Busca a coluna por nome, preferindo igualdade > prefixo > contém
    (evita p.ex. casar 'ÓRGÃO SANCIONADOR' com
    'NOME INFORMADO PELO ÓRGÃO SANCIONADOR')."""
    chaves = {_norm(k): k for k in row}
    for p in padroes:
        if p in chaves:
            return (row[chaves[p]] or "").strip()
    for p in padroes:
        for kn, k in chaves.items():
            if kn.startswith(p):
                return (row[k] or "").strip()
    for p in padroes:
        for kn, k in chaves.items():
            if p in kn:
                return (row[k] or "").strip()
    return ""


def materializar(con: duckdb.DuckDBPyConnection) -> None:
    ano = config.ANO_ELEICAO
    cands = {r[0]: r[1] for r in con.execute(f"""
        SELECT NR_CPF_CANDIDATO, NM_CANDIDATO FROM cand_{ano}
        WHERE NR_CPF_CANDIDATO IS NOT NULL AND LENGTH(NR_CPF_CANDIDATO) = 11
    """).fetchall()}
    por_meio = {}
    for cpf, nome in cands.items():
        por_meio.setdefault(cpf[3:9], []).append((cpf, _norm(nome)))

    hits, pj = [], []
    for cad in CADASTROS:
        print(f"  [get ] {cad.upper()}")
        for row in baixar(cad):
            tipo = _campo(row, "TIPO DE PESSOA")
            doc = _campo(row, "CPF OU CNPJ")
            nome = _campo(row, "NOME DO SANCIONADO") or _campo(row, "NOME")
            base = {
                "cadastro": cad,
                "categoria": _campo(row, "CATEGORIA DA SANCAO") or _campo(row, "TIPO DA SANCAO"),
                "processo": _campo(row, "NUMERO DO PROCESSO"),
                "orgao": _campo(row, "ORGAO SANCIONADOR"),
                "uf_orgao": _campo(row, "UF ORGAO"),
                "inicio": _campo(row, "DATA INICIO"),
                "fim": _campo(row, "DATA FINAL"),
                "publicacao": _campo(row, "DATA PUBLICACAO"),
            }
            dig = re.sub(r"\D", "", doc)
            if tipo.upper().startswith("J") or len(dig) == 14:
                pj.append({**base, "cnpj": dig, "nome": nome})
                continue
            if len(dig) == 11:                       # CPF completo (CEIS/CNEP PF)
                if dig in cands:
                    hits.append({**base, "cpf": dig, "nome": nome,
                                 "criterio": "cpf"})
            else:                                     # CPF mascarado (CEAF)
                meio = _meio_cpf(doc)
                for cpf, nome_cand in por_meio.get(meio, []):
                    if _norm(nome) == nome_cand:      # dupla coincidência
                        hits.append({**base, "cpf": cpf, "nome": nome,
                                     "criterio": "cpf_parcial+nome"})

    con.execute("""CREATE OR REPLACE TABLE sancoes_pf (
        cadastro VARCHAR, categoria VARCHAR, processo VARCHAR, orgao VARCHAR,
        uf_orgao VARCHAR, inicio VARCHAR, fim VARCHAR, publicacao VARCHAR,
        cpf VARCHAR, nome VARCHAR, criterio VARCHAR)""")
    con.execute("""CREATE OR REPLACE TABLE sancoes_pj (
        cadastro VARCHAR, categoria VARCHAR, processo VARCHAR, orgao VARCHAR,
        uf_orgao VARCHAR, inicio VARCHAR, fim VARCHAR, publicacao VARCHAR,
        cnpj VARCHAR, nome VARCHAR)""")
    if hits:
        con.executemany("INSERT INTO sancoes_pf VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        [[h["cadastro"], h["categoria"], h["processo"], h["orgao"],
                          h["uf_orgao"], h["inicio"], h["fim"], h["publicacao"],
                          h["cpf"], h["nome"], h["criterio"]] for h in hits])
    if pj:
        con.executemany("INSERT INTO sancoes_pj VALUES (?,?,?,?,?,?,?,?,?,?)",
                        [[p["cadastro"], p["categoria"], p["processo"], p["orgao"],
                          p["uf_orgao"], p["inicio"], p["fim"], p["publicacao"],
                          p["cnpj"], p["nome"]] for p in pj])
    print(f"  sanções PF cruzadas com candidatos 2026: {len(hits)} "
          f"| PJs materializadas p/ QSA futuro: {len(pj):,}")


def main() -> None:
    con = duckdb.connect(str(config.DB_PATH))
    materializar(con)
    con.close()
    print("OK — rode fichas.py de novo para injetar nas fichas")


if __name__ == "__main__":
    main()
