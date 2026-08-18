"""Injeta as camadas-sidecar (tcmgo, siconfi, cnia, qsa, gestao, noticias,
parlamentar, processos_tse, planos) nas fichas JÁ GERADAS em docs/data/<UF>/,
sem precisar do banco DuckDB nem de re-rodar fichas.py.

Útil quando um módulo de camada roda sozinho (ex.: atualização diária só do
TCM-GO) e você quer refletir o resultado nas fichas publicadas.

Uso: python pipeline/injetar.py --ufs GO
"""
from __future__ import annotations

import argparse
import json

import config

CAMADAS = {
    "planos": "resumo_plano",
    "noticias": "noticias",
    "processos_tse": "processos_tse",
    "gestao": "gestao",
    "parlamentar": "parlamentar",
    "tcmgo": "tcmgo",
    "tcego": "tcego",
    "siconfi": "siconfi",
    "cnia": "cnia",
    "qsa": "qsa",
    "financiamento": "financiamento",
    "emendas": "emendas",
    "alego": "alego",
}


def injetar_uf(uf: str) -> int:
    idx_path = config.OUT_DATA / uf / "index.json"
    idx = json.loads(idx_path.read_text("utf-8"))
    n = 0
    for c in idx["candidatos"]:
        sq = c["sq"]
        path = config.OUT_DATA / uf / f"{sq}.json"
        ficha = json.loads(path.read_text("utf-8"))
        mudou = False
        for pasta, chave in CAMADAS.items():
            side = config.OUT_DATA / pasta / uf / f"{sq}.json"
            if side.exists():
                novo = json.loads(side.read_text("utf-8"))
                if ficha.get(chave) != novo:
                    ficha[chave] = novo
                    mudou = True
            elif ficha.get(chave) is not None and (config.OUT_DATA / pasta).exists():
                # sidecar removido (saiu da lista na rodada atual) → tira da ficha
                del ficha[chave]
                mudou = True
        if mudou:
            path.write_text(json.dumps(ficha, ensure_ascii=False,
                                       separators=(",", ":")), "utf-8")
            n += 1
    print(f"  {uf}: {n} fichas atualizadas")
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ufs", nargs="*", default=None)
    args = ap.parse_args()
    print("-- injeção de camadas nas fichas publicadas")
    for uf in (args.ufs or config.UFS_ALVO):
        injetar_uf(uf)


if __name__ == "__main__":
    main()
