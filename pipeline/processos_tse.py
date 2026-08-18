"""Camada — processos da candidatura no TSE (impugnações, AIJE, AIME, recursos).

Fonte: API não-oficial do DivulgaCandContas, a mesma que alimenta o site público
    https://divulgacandcontas.tse.jus.br/divulga/rest/v1/candidatura/buscar
        /{ano}/{UF}/{cd_eleicao}/candidato/{sq}

ATENÇÃO: essa API devolve resposta vazia para IPs de datacenter (WAF).
Rode este módulo do VPS ou de uma máquina residencial. Se a resposta vier
vazia, o módulo pula sem quebrar o pipeline — a ficha continua com o link
"Ver no TSE", que sempre funciona no navegador do eleitor.

O payload traz, entre outros: situação detalhada do registro, motivos de
indeferimento/cassação e a lista de processos da candidatura com número de
protocolo. Salvamos só o necessário (dado público de processo eleitoral).

Uso:
    python pipeline/processos_tse.py --ufs GO
    python pipeline/processos_tse.py --ufs GO --so-com-processo   # grava só quem tem
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import date

import duckdb
import requests

import config

API = ("https://divulgacandcontas.tse.jus.br/divulga/rest/v1/candidatura/buscar"
       "/{ano}/{ue}/{cd_eleicao}/candidato/{sq}")

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://divulgacandcontas.tse.jus.br/divulga/",
    "Accept-Language": "pt-BR,pt;q=0.9",
}


def extrair(payload: dict) -> dict:
    """Reduz o payload ao que interessa (defensivo: campos podem variar)."""
    processos = []
    for p in (payload.get("processos") or payload.get("processosJudiciais") or []):
        if isinstance(p, dict):
            processos.append({
                "protocolo": p.get("numeroProtocolo") or p.get("protocolo"),
                "processo": p.get("numeroProcesso") or p.get("processo"),
                "tipo": p.get("tipo") or p.get("descricaoTipo"),
                "data": p.get("dataProtocolo") or p.get("data"),
            })
    return {
        "situacao_detalhe": (payload.get("descricaoSituacao")
                             or payload.get("situacaoCandidato")),
        "motivos": [m.get("descricao") if isinstance(m, dict) else str(m)
                    for m in (payload.get("motivos")
                              or payload.get("motivosIndeferimento") or [])],
        "processos": processos,
        "coletado_em": date.today().isoformat(),
        "fonte": "DivulgaCandContas/TSE",
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ufs", nargs="*", default=None)
    ap.add_argument("--so-com-processo", action="store_true")
    ap.add_argument("--pausa", type=float, default=0.8,
                    help="segundos entre requisições (rate limit educado)")
    args = ap.parse_args()

    con = duckdb.connect(str(config.DB_PATH), read_only=True)
    ano = config.ANO_ELEICAO
    vazias = 0
    for uf in (args.ufs or config.UFS_ALVO):
        rows = con.execute(f"""
            SELECT SQ_CANDIDATO, SG_UE, CD_ELEICAO, NM_URNA_CANDIDATO
            FROM cand_{ano} WHERE SG_UF = ?
        """, [uf]).fetchall()
        out_dir = config.OUT_DATA / "processos_tse" / uf
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"-- {uf}: {len(rows)} candidatos")
        for sq, ue, cd_eleicao, nome in rows:
            url = API.format(ano=ano, ue=ue, cd_eleicao=cd_eleicao, sq=sq)
            try:
                r = requests.get(url, headers=HEADERS, timeout=30)
                if not r.content:
                    vazias += 1
                    if vazias >= 5:
                        print("  [stop] API devolvendo vazio — provável bloqueio de IP "
                              "(rode do VPS ou de rede residencial)")
                        return
                    continue
                dados = extrair(r.json())
            except Exception as e:
                print(f"  [warn] {nome}: {e}")
                continue
            vazias = 0
            if args.so_com_processo and not (dados["processos"] or dados["motivos"]):
                continue
            (out_dir / f"{sq}.json").write_text(
                json.dumps(dados, ensure_ascii=False), "utf-8")
            if dados["processos"]:
                print(f"  {nome}: {len(dados['processos'])} processo(s)")
            time.sleep(args.pausa)
        print("  → rode fichas.py de novo para injetar nas fichas")
    con.close()


if __name__ == "__main__":
    main()
