"""Camada — QSA/Receita Federal: participações societárias dos candidatos,
cruzadas com os cadastros de sanção (CEIS/CNEP) já materializados no banco.

Fonte: dados abertos do CNPJ da Receita Federal (arquivos mensais Socios*.zip
e Empresas*.zip no Nextcloud público da RFB — a URL antiga dadosabertos.rfb
morreu; o acesso atual é via WebDAV público, ver RFB_SHARE abaixo).

Identidade com salvaguarda (mesmo padrão do CEAF em sancoes.py):
o CPF do sócio vem mascarado (***NNNNNN** = 6 dígitos centrais), então um
vínculo só entra na ficha com DUPLA coincidência:
    nome do sócio idêntico (normalizado)  E  mesmos 6 dígitos centrais do CPF.

O que a ficha mostra — e o que ela NÃO diz:
    - Ser sócio de empresa é lícito e comum; a ficha apenas lista os vínculos
      declarados à Receita, com a data de entrada e a qualificação.
    - Se uma empresa do candidato consta do CEIS/CNEP, a ficha registra a
      sanção DA EMPRESA (processo, órgão, período), nunca atribui ao sócio.
    - Disclaimer fixo cobre os dois pontos.

Uso: python pipeline/qsa.py --ufs GO          (usa zips já baixados)
     python pipeline/qsa.py --ufs GO --baixar (baixa Socios/Empresas se faltar)
Depois: rode fichas.py de novo (ou injetar.py) para injetar nas fichas.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import unicodedata
import zipfile
from datetime import date

import duckdb
import requests

import config

# Nextcloud público da Receita (descoberto 18/08/2026; índice em
# https://dados.gov.br/dados/conjuntos-dados/cadastro-nacional-da-pessoa-juridica---cnpj)
RFB_SHARE = "YggdBLfdninEJX9"
RFB_WEBDAV = "https://arquivos.receitafederal.gov.br/public.php/webdav/{mes}/{arq}"
RFB_MES = "2026-08"
RFB_DIR = config.RAW_DIR / "rfb"

FONTE = "Receita Federal — dados abertos do CNPJ (QSA)"
FONTE_URL = ("https://dados.gov.br/dados/conjuntos-dados/"
             "cadastro-nacional-da-pessoa-juridica---cnpj")

DISCLAIMER = (
    "Vínculos societários declarados à Receita Federal (dados abertos do "
    "CNPJ). Ter ou ter tido empresa é lícito e comum — a lista é informação "
    "de transparência, não acusação. Quando uma empresa consta de cadastro "
    "de sanção (CEIS/CNEP), a sanção é da PESSOA JURÍDICA, com processo, "
    "órgão e prazo próprios; ela não se transfere ao sócio, pode ser "
    "anterior ou posterior à participação dele e pode estar sub judice. "
    "Confira sempre a consulta oficial."
)

QUALIF_FALLBACK = {"49": "Sócio-Administrador", "22": "Sócio", "16": "Presidente",
                   "05": "Administrador", "10": "Diretor"}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^A-Za-z ]", " ", s)).strip().upper()


def _baixar(arq: str) -> None:
    dest = RFB_DIR / arq
    if dest.exists():
        return
    print(f"  [get ] RFB {arq}")
    RFB_DIR.mkdir(parents=True, exist_ok=True)
    url = RFB_WEBDAV.format(mes=RFB_MES, arq=arq)
    with requests.get(url, auth=(RFB_SHARE, ""), stream=True, timeout=1800) as r:
        r.raise_for_status()
        tmp = dest.with_suffix(".part")
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
        tmp.rename(dest)


def _linhas_zip(path):
    """Itera linhas do CSV dentro de um zip da RFB (latin-1, ';', sem header)."""
    with zipfile.ZipFile(path) as z:
        for nome in z.namelist():
            with z.open(nome) as f:
                for ln in io.TextIOWrapper(f, encoding="latin-1", newline=""):
                    yield next(csv.reader([ln], delimiter=";", quotechar='"'))


def qualificacoes() -> dict[str, str]:
    path = RFB_DIR / "Qualificacoes.zip"
    try:
        _baixar("Qualificacoes.zip")
        return {r[0]: r[1] for r in _linhas_zip(path) if len(r) >= 2}
    except Exception:
        return QUALIF_FALLBACK


def candidatos_por_meio(con) -> dict[str, list[tuple]]:
    """meio6 do CPF → [(cpf, nome_norm, sq, uf, nome)] — todos os candidatos 2026."""
    rows = con.execute("""
        SELECT NR_CPF_CANDIDATO, NM_CANDIDATO, SQ_CANDIDATO, SG_UF
        FROM cand_2026 WHERE LENGTH(NR_CPF_CANDIDATO) = 11
    """).fetchall()
    por_meio: dict[str, list[tuple]] = {}
    for cpf, nome, sq, uf in rows:
        por_meio.setdefault(cpf[3:9], []).append((cpf, _norm(nome), sq, uf, nome))
    return por_meio


def casar_socios(por_meio) -> list[dict]:
    """Streaming dos Socios*.zip → vínculos com dupla coincidência."""
    vinculos = []
    for i in range(10):
        path = RFB_DIR / f"Socios{i}.zip"
        if not path.exists():
            print(f"  [warn] {path.name} ausente — rode com --baixar")
            continue
        n = 0
        for r in _linhas_zip(path):
            if len(r) < 6 or r[1] != "2":          # só pessoa física
                continue
            m = re.search(r"\*{3}(\d{6})\*{2}", r[3])
            if not m:
                continue
            for cpf, nome_norm, sq, uf, _ in por_meio.get(m.group(1), []):
                if _norm(r[2]) == nome_norm:        # dupla coincidência
                    vinculos.append({
                        "cnpj_basico": r[0], "cpf": cpf, "sq": sq, "uf": uf,
                        "nome_socio": r[2], "qualificacao_cod": r[4],
                        "desde": r[5],
                    })
            n += 1
        print(f"  [ok  ] {path.name}: {n:,} sócios PF varridos "
              f"(acum. {len(vinculos)} vínculos de candidatos)")
    return vinculos


def enriquecer_empresas(cnpjs: set[str]) -> dict[str, dict]:
    """Razão social/porte dos CNPJs casados, varrendo Empresas*.zip."""
    info: dict[str, dict] = {}
    for i in range(10):
        path = RFB_DIR / f"Empresas{i}.zip"
        if not path.exists():
            print(f"  [warn] {path.name} ausente — razão social ficará vazia")
            continue
        for r in _linhas_zip(path):
            if r and r[0] in cnpjs:
                info[r[0]] = {"razao_social": r[1] if len(r) > 1 else "",
                              "porte": r[5] if len(r) > 5 else ""}
        print(f"  [ok  ] {path.name} varrido ({len(info)}/{len(cnpjs)} CNPJs resolvidos)")
        if len(info) == len(cnpjs):
            break
    return info


def cruzar_sancoes(con, cnpjs: set[str]) -> dict[str, list[dict]]:
    """cnpj_basico → sanções (CEIS/CNEP) da tabela sancoes_pj."""
    out: dict[str, list[dict]] = {}
    for r in con.execute("""
        SELECT SUBSTR(cnpj,1,8), cadastro, categoria, processo, orgao,
               uf_orgao, inicio, fim FROM sancoes_pj
    """).fetchall():
        if r[0] in cnpjs:
            out.setdefault(r[0], []).append({
                "cadastro": r[1].upper(), "categoria": r[2], "processo": r[3],
                "orgao": r[4], "uf_orgao": r[5], "inicio": r[6], "fim": r[7],
            })
    return out


def materializar(con, vinculos: list[dict]) -> None:
    con.execute("""CREATE OR REPLACE TABLE qsa_candidatos (
        cnpj_basico VARCHAR, cpf VARCHAR, sq VARCHAR, uf VARCHAR,
        nome_socio VARCHAR, qualificacao_cod VARCHAR, desde VARCHAR)""")
    if vinculos:
        con.executemany("INSERT INTO qsa_candidatos VALUES (?,?,?,?,?,?,?)",
                        [[v["cnpj_basico"], v["cpf"], v["sq"], v["uf"],
                          v["nome_socio"], v["qualificacao_cod"], v["desde"]]
                         for v in vinculos])


def gerar_uf(uf: str, vinculos, empresas, sancoes, qualif) -> tuple[int, int]:
    out_dir = config.OUT_DATA / "qsa" / uf
    out_dir.mkdir(parents=True, exist_ok=True)
    for antigo in out_dir.glob("*.json"):     # limpa a rodada anterior: quem saiu
        antigo.unlink()                       # da lista não pode continuar na ficha
    por_sq: dict[str, list[dict]] = {}
    for v in vinculos:
        if v["uf"] != uf:
            continue
        cnpj = v["cnpj_basico"]
        emp = empresas.get(cnpj, {})
        desde = v["desde"]
        por_sq.setdefault(v["sq"], []).append({
            "cnpj_basico": cnpj,
            "razao_social": emp.get("razao_social", ""),
            "qualificacao": qualif.get(v["qualificacao_cod"],
                                       v["qualificacao_cod"]),
            "desde": f"{desde[:4]}-{desde[4:6]}" if len(desde) == 8 else desde,
            "criterio": "nome + 6 dígitos centrais do CPF",
            "sancoes_da_empresa": sancoes.get(cnpj, []),
        })
    com_sancao = 0
    for sq, emps in por_sq.items():
        if any(e["sancoes_da_empresa"] for e in emps):
            com_sancao += 1
        (out_dir / f"{sq}.json").write_text(json.dumps({
            "empresas": sorted(emps, key=lambda e: e["desde"]),
            "fonte": FONTE, "fonte_url": FONTE_URL,
            "consulta_oficial":
                "https://solucoes.receita.fazenda.gov.br/Servicos/cnpjreva/Cnpjreva_Solicitacao.asp",
            "sancoes_consulta_oficial":
                "https://portaldatransparencia.gov.br/sancoes/consulta",
            "referencia_dados": RFB_MES,
            "disclaimer": DISCLAIMER,
            "gerado_em": date.today().isoformat(),
        }, ensure_ascii=False), "utf-8")
    print(f"  {uf}: QSA gerado para {len(por_sq)} candidatos "
          f"({com_sancao} com empresa em cadastro de sanção)")
    return len(por_sq), com_sancao


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ufs", nargs="*", default=None)
    ap.add_argument("--baixar", action="store_true",
                    help="baixa Socios*/Empresas*/Qualificacoes da RFB se faltar")
    args = ap.parse_args()
    print("-- QSA / dados abertos do CNPJ (RFB)")
    if args.baixar:
        for i in range(10):
            _baixar(f"Socios{i}.zip")
    con = duckdb.connect(str(config.DB_PATH))
    por_meio = candidatos_por_meio(con)
    vinculos = casar_socios(por_meio)
    materializar(con, vinculos)
    cnpjs = {v["cnpj_basico"] for v in vinculos}
    print(f"  vínculos: {len(vinculos)} | empresas distintas: {len(cnpjs)}")
    if args.baixar:
        for i in range(10):
            _baixar(f"Empresas{i}.zip")
    empresas = enriquecer_empresas(cnpjs)
    sancoes = cruzar_sancoes(con, cnpjs)
    qualif = qualificacoes()
    for uf in (args.ufs or config.UFS_ALVO):
        gerar_uf(uf, vinculos, empresas, sancoes, qualif)
    con.close()
    print("OK — rode fichas.py (ou injetar.py) para injetar nas fichas")


if __name__ == "__main__":
    main()
