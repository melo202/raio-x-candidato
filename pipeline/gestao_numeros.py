"""Camada — "gestão em números": indicadores oficiais do município durante o
mandato de candidatos que já foram prefeitos.

Primeiro indicador: IDEB da rede municipal (anos iniciais), INEP — a régua
pública mais consolidada de educação municipal. A planilha de divulgação traz
a série completa 2005-2023 por município/rede.

Salvaguardas (princípio "dado + contexto, não nota"):
    - A ficha mostra a SÉRIE no período do mandato, lado a lado com a média
      das redes municipais do estado — nunca um número isolado.
    - Disclaimer fixo: indicador é contexto; resultado educacional tem muitos
      fatores e maturação lenta — não é mérito nem culpa exclusivos da gestão.

Uso: python pipeline/gestao_numeros.py --ufs GO
Depois: rode fichas.py de novo para injetar nas fichas.
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
import zipfile
from datetime import date

import pandas as pd
import requests

import config

URL_IDEB = ("https://download.inep.gov.br/ideb/resultados/"
            "divulgacao_anos_iniciais_municipios_2023.zip")
EDICOES = [2005, 2007, 2009, 2011, 2013, 2015, 2017, 2019, 2021, 2023]

DISCLAIMER = (
    "O IDEB é da rede municipal de ensino (anos iniciais), medido pelo INEP a "
    "cada dois anos. Indicador é contexto, não veredito: resultados educacionais "
    "dependem de muitos fatores (orçamento, continuidade de políticas, condições "
    "socioeconômicas) e mudam devagar — não são mérito nem culpa exclusivos de "
    "uma gestão. A média estadual das redes municipais aparece ao lado para "
    "comparação."
)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9 ]", "", s.upper()).strip()


def baixar_ideb() -> pd.DataFrame:
    dest = config.RAW_DIR / "ideb_anos_iniciais_municipios.zip"
    if not dest.exists():
        print("  [get ] planilha IDEB municípios (INEP)")
        # a cadeia TLS do INEP falha em alguns ambientes; cai pra verify=False
        try:
            r = requests.get(URL_IDEB, timeout=600,
                             headers={"User-Agent": "Mozilla/5.0"})
        except requests.exceptions.SSLError:
            import urllib3
            urllib3.disable_warnings()
            r = requests.get(URL_IDEB, timeout=600, verify=False,
                             headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        dest.write_bytes(r.content)
    with zipfile.ZipFile(dest) as z:
        xlsx = next(n for n in z.namelist() if n.endswith(".xlsx"))
        with z.open(xlsx) as f:
            df = pd.read_excel(f, header=9)
    df = df[df["REDE"].isin(["Municipal", "Pública"])]
    return df


def montar_lookup(df: pd.DataFrame):
    """(UF, município normalizado) → {edicao: ideb} e média estadual por edição."""
    cols = {e: f"VL_OBSERVADO_{e}" for e in EDICOES if f"VL_OBSERVADO_{e}" in df.columns}

    def valores(row) -> dict:
        out = {}
        for e, c in cols.items():
            v = pd.to_numeric(pd.Series([row[c]]), errors="coerce").iloc[0]
            if pd.notna(v):
                out[e] = float(v)
        return out

    lookup: dict = {}
    for _, row in df.iterrows():
        chave = (row["SG_UF"], _norm(row["NO_MUNICIPIO"]))
        vals = valores(row)
        # preferência: rede Municipal; usa Pública só se não houver Municipal
        if row["REDE"] == "Municipal" or chave not in lookup:
            if row["REDE"] == "Municipal" or not lookup.get(chave):
                lookup[chave] = vals

    medias: dict = {}
    dfm = df[df["REDE"] == "Municipal"]
    for uf, grupo in dfm.groupby("SG_UF"):
        medias[uf] = {}
        for e, c in cols.items():
            serie = pd.to_numeric(grupo[c], errors="coerce").dropna()
            if len(serie):
                medias[uf][e] = round(float(serie.mean()), 1)
    return lookup, medias


def gerar_uf(uf: str, lookup, medias) -> int:
    out_dir = config.OUT_DATA / "gestao" / uf
    out_dir.mkdir(parents=True, exist_ok=True)
    for antigo in out_dir.glob("*.json"):     # limpa a rodada anterior: quem saiu
        antigo.unlink()                       # da lista não pode continuar na ficha
    idx = json.loads((config.OUT_DATA / uf / "index.json").read_text("utf-8"))
    n = 0
    for c in idx["candidatos"]:
        ficha = json.loads((config.OUT_DATA / uf / f"{c['sq']}.json").read_text("utf-8"))
        blocos = []
        for m in ficha.get("historico", {}).get("mandatos", []):
            if not m.get("executivo") or "Prefeito" not in (m.get("cargo") or ""):
                continue
            uf_m = ficha["uf"]
            serie_mun = lookup.get((uf_m, _norm(m["onde"])), {})
            # edições relevantes: da linha de base (última antes do início) ao fim
            base = max((e for e in EDICOES if e < m["inicio"]), default=None)
            eds = [e for e in EDICOES if (base or 0) <= e <= m["fim"]]
            pontos = [{
                "edicao": e,
                "municipio": serie_mun.get(e),
                "media_estado": medias.get(uf_m, {}).get(e),
            } for e in eds]
            if any(p["municipio"] is not None for p in pontos):
                blocos.append({
                    "indicador": "IDEB — rede municipal, anos iniciais",
                    "cargo": m["cargo"], "onde": m["onde"],
                    "mandato": f"{m['inicio']}–{m['fim']}",
                    "baseline": base,
                    "pontos": pontos,
                })
        if blocos:
            (out_dir / f"{c['sq']}.json").write_text(json.dumps({
                "blocos": blocos,
                "fonte": "INEP — resultados do IDEB (dados abertos)",
                "fonte_url": "https://www.gov.br/inep/pt-br/areas-de-atuacao/"
                             "pesquisas-estatisticas-e-indicadores/ideb/resultados",
                "disclaimer": DISCLAIMER,
                "gerado_em": date.today().isoformat(),
            }, ensure_ascii=False), "utf-8")
            n += 1
    print(f"  {uf}: gestão em números gerada para {n} ex-prefeitos")
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ufs", nargs="*", default=None)
    args = ap.parse_args()
    print("-- IDEB/INEP")
    df = baixar_ideb()
    lookup, medias = montar_lookup(df)
    for uf in (args.ufs or config.UFS_ALVO):
        gerar_uf(uf, lookup, medias)
    print("OK — rode fichas.py de novo para injetar nas fichas")


if __name__ == "__main__":
    main()
