"""Camada — Siconfi/Tesouro: finanças do município durante o mandato.

Para candidatos que já foram prefeitos (mesma regra da camada IDEB), busca na
API pública do Siconfi (Tesouro Nacional) as Declarações de Contas Anuais:
    DCA Anexo I-C → receita total realizada (líquida das deduções do FUNDEB)
    DCA Anexo I-D → despesa total empenhada e investimentos empenhados

Salvaguardas (princípio "dado + contexto, não nota"):
    - Série completa do mandato + ano-base (último ano antes do mandato),
      nunca um número isolado.
    - Valores por habitante (população da própria DCA) e corrigidos pela
      inflação (IPCA/IBGE via API do Banco Central) a preços do último ano
      da série — evita a ilusão de "dobrou a receita" que é só inflação.
    - Disclaimer fixo: orçamento municipal depende de transferências,
      economia local e decisões da Câmara — não é mérito/culpa exclusivos
      de uma gestão.

Uso: python pipeline/siconfi.py --ufs GO
Depois: rode fichas.py de novo (ou injetar.py) para injetar nas fichas.
"""
from __future__ import annotations

import argparse
import json
import re
import time
import unicodedata
from datetime import date

import requests

import config

API = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/dca"
URL_IBGE_MUN = "https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf}/municipios"
URL_BCB_IPCA = ("https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados"
                "?formato=json&dataInicial=01/01/2000&dataFinal=31/12/2030")
FONTE_URL = "https://siconfi.tesouro.gov.br/siconfi/pages/public/consulta_finbra/finbra_list.jsf"
ULTIMO_ANO_DCA = 2024  # última DCA entregue (mandatos 2021-2024 fecham completos)

DISCLAIMER = (
    "Receitas e despesas declaradas pelo próprio município ao Tesouro Nacional "
    "(Siconfi/DCA). Valores por habitante e corrigidos pela inflação (IPCA) "
    "para permitir comparação entre anos. Orçamento municipal depende de "
    "transferências federais e estaduais, da economia local e de decisões da "
    "Câmara — a série é contexto, não veredito sobre uma gestão. O ano-base "
    "anterior ao mandato aparece como referência de partida."
)

UA = {"User-Agent": "raio-x-candidato (dados abertos; uso civico)"}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^A-Za-z ]", " ", s)).strip().upper()


def codigos_ibge(uf: str) -> dict[str, int]:
    dest = config.RAW_DIR / f"ibge_municipios_{uf}.json"
    if not dest.exists():
        r = requests.get(URL_IBGE_MUN.format(uf=uf), timeout=60, headers=UA)
        r.raise_for_status()
        dest.write_text(r.text, "utf-8")
    munis = json.loads(dest.read_text("utf-8"))
    return {_norm(m["nome"]): int(m["id"]) for m in munis}


def deflatores_ipca() -> dict[int, float]:
    """Fator multiplicativo p/ trazer valores do ano X a preços de ULTIMO_ANO_DCA.
    Usa o IPCA acumulado (SGS 433, variação mensal %) até dezembro de cada ano."""
    dest = config.RAW_DIR / "ipca_sgs433.json"
    if not dest.exists():
        r = requests.get(URL_BCB_IPCA, timeout=60, headers=UA)
        r.raise_for_status()
        dest.write_text(r.text, "utf-8")
    serie = json.loads(dest.read_text("utf-8"))
    indice: dict[int, float] = {}   # nível do índice em dez/ano
    nivel = 1.0
    for p in serie:
        dd, mm, aa = p["data"].split("/")
        nivel *= 1 + float(p["valor"]) / 100
        if mm == "12":
            indice[int(aa)] = nivel
    base = indice.get(ULTIMO_ANO_DCA) or nivel
    return {ano: base / v for ano, v in indice.items()}


def _fetch_dca(id_ente: int, ano: int, anexo: str) -> list[dict]:
    dest = config.RAW_DIR / "siconfi" / f"dca_{id_ente}_{ano}_{anexo[-3:].replace('-','')}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return json.loads(dest.read_text("utf-8")).get("items", [])
    r = requests.get(API, params={"an_exercicio": ano, "id_ente": id_ente,
                                  "no_anexo": anexo}, timeout=120, headers=UA)
    r.raise_for_status()
    time.sleep(0.6)  # cortesia com a API pública (limite ~1 req/s)
    try:
        items = r.json().get("items", [])
    except ValueError:                       # HTML de erro com HTTP 200
        print(f"  [warn] DCA {id_ente}/{ano}/{anexo}: resposta não-JSON — não cacheada")
        return []
    if items:                                # não cacheia vazio (DCA pode chegar depois)
        dest.write_text(r.text, "utf-8")
    return items


def indicadores_ano(id_ente: int, ano: int) -> dict | None:
    ic = _fetch_dca(id_ente, ano, "DCA-Anexo I-C")
    idd = _fetch_dca(id_ente, ano, "DCA-Anexo I-D")
    if not ic and not idd:
        return None
    receita = deducoes = None
    populacao = None
    for i in ic:
        populacao = populacao or i.get("populacao")
        if i["cod_conta"] == "TotalReceitas":
            if i["coluna"] == "Receitas Brutas Realizadas":
                receita = i["valor"]
            elif i["coluna"].startswith("Dedu"):
                deducoes = (deducoes or 0) + i["valor"]
    despesa = invest = None
    for i in idd:
        populacao = populacao or i.get("populacao")
        if i["coluna"] != "Despesas Empenhadas":
            continue
        if i["cod_conta"] == "TotalDespesas":
            despesa = i["valor"]
        elif i["cod_conta"] == "DO4.4.00.00.00.00":  # 4.4 Investimentos (só o total,
            invest = i["valor"]                       # subcontas duplicariam a soma)
    if receita is None and despesa is None:
        return None
    return {
        "ano": ano,
        "receita_total": round(receita - (deducoes or 0), 2) if receita is not None else None,
        "despesa_total": despesa,
        "investimentos": invest,
        "populacao": populacao,
    }


def gerar_uf(uf: str, deflator: dict[int, float]) -> int:
    ibge = codigos_ibge(uf)
    idx = json.loads((config.OUT_DATA / uf / "index.json").read_text("utf-8"))
    out_dir = config.OUT_DATA / "siconfi" / uf
    out_dir.mkdir(parents=True, exist_ok=True)
    for antigo in out_dir.glob("*.json"):     # limpa a rodada anterior: quem saiu
        antigo.unlink()                       # da lista não pode continuar na ficha
    cache_series: dict[tuple, list] = {}
    n = 0
    for c in idx["candidatos"]:
        ficha = json.loads((config.OUT_DATA / uf / f"{c['sq']}.json").read_text("utf-8"))
        blocos = []
        for m in ficha.get("historico", {}).get("mandatos", []):
            if not m.get("executivo") or "Prefeito" not in (m.get("cargo") or ""):
                continue
            id_ente = ibge.get(_norm(m["onde"]))
            if not id_ente:
                print(f"  [warn] município sem código IBGE: {m['onde']}")
                continue
            base = m["inicio"] - 1
            anos = [a for a in range(base, min(m["fim"], ULTIMO_ANO_DCA) + 1)]
            chave = (id_ente, anos[0], anos[-1])
            if chave not in cache_series:
                serie = []
                for ano in anos:
                    ind = indicadores_ano(id_ente, ano)
                    if ind:
                        f = deflator.get(ind["ano"])
                        pop = ind["populacao"] or None
                        for campo in ("receita_total", "despesa_total", "investimentos"):
                            v = ind[campo]
                            ind[f"{campo}_pc_corrigido"] = (
                                round(v * f / pop, 2) if (v is not None and f and pop) else None)
                        serie.append(ind)
                cache_series[chave] = serie
            serie = cache_series[chave]
            if serie:
                blocos.append({
                    "indicador": "Finanças do município (Siconfi/Tesouro)",
                    "cargo": m["cargo"], "onde": m["onde"], "id_ente": id_ente,
                    "mandato": f"{m['inicio']}–{m['fim']}",
                    "baseline": base,
                    "ano_precos": ULTIMO_ANO_DCA,
                    "pontos": serie,
                })
        if blocos:
            (out_dir / f"{c['sq']}.json").write_text(json.dumps({
                "blocos": blocos,
                "fonte": "Tesouro Nacional — Siconfi, Declarações de Contas Anuais (DCA)",
                "fonte_url": FONTE_URL,
                "disclaimer": DISCLAIMER,
                "gerado_em": date.today().isoformat(),
            }, ensure_ascii=False), "utf-8")
            n += 1
    print(f"  {uf}: finanças municipais geradas para {n} ex-gestores")
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ufs", nargs="*", default=None)
    args = ap.parse_args()
    print("-- Siconfi/DCA (Tesouro Nacional)")
    deflator = deflatores_ipca()
    for uf in (args.ufs or config.UFS_ALVO):
        gerar_uf(uf, deflator)
    print("OK — rode fichas.py (ou injetar.py) para injetar nas fichas")


if __name__ == "__main__":
    main()
