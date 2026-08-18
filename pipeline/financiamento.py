"""Camada — QUEM FINANCIA: receitas e fornecedores da campanha 2026.

Pronta para a prestação parcial de contas (TSE publica entre 09 e 13/09/2026)
e para as prestações finais. Responde, por candidato:
    - quanto entrou e DE ONDE (fundo eleitoral, fundo partidário, pessoas
      físicas, recursos próprios, financiamento coletivo...);
    - quem são os maiores doadores (CPF de pessoa física sempre mascarado);
    - quem são os maiores fornecedores contratados — cruzados com os
      cadastros de sanção CEIS/CNEP (tabela sancoes_pj) já materializados.

Fonte: prestação de contas eleitorais — dados abertos do TSE
(receitas_candidatos_{ano}_{UF}.csv e despesas_contratadas_candidatos_{ano}_{UF}.csv).
Lição da auditoria: NUNCA carregar o consolidado _BRASIL junto com os por-UF
(duplica); aqui usamos só o arquivo da UF do candidato.

Uso:
    python pipeline/financiamento.py --ufs GO                # ano da eleição
    python pipeline/financiamento.py --ano 2022 --saida-teste /tmp/fin22
                                                             # dry-run estrutural
Depois: rode fichas.py de novo (ou injetar.py) para injetar nas fichas.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import zipfile
from datetime import date
from pathlib import Path

import requests

import config

UA = {"User-Agent": f"{config.PROJECT_NAME} (dados abertos; uso civico)"}
TOP_N = 10

DISCLAIMER = (
    "Valores declarados pelos próprios candidatos e partidos à Justiça "
    "Eleitoral (prestação de contas). Durante a campanha os números são "
    "PARCIAIS — doações e gastos novos entram a cada atualização, e a análise "
    "definitiva é a da prestação final julgada pelo TSE. Doar é legal e "
    "regulamentado; CPFs de doadores pessoas físicas são exibidos mascarados. "
    "Quando um fornecedor consta de cadastro de sanção (CEIS/CNEP), a sanção "
    "é da empresa, com processo e prazo próprios, e pode não ter relação com "
    "o serviço prestado à campanha. Confira sempre a consulta oficial."
)


def _num(v: str) -> float:
    try:
        return float(str(v).replace(",", "."))
    except ValueError:
        return 0.0


def _mask_pf(doc: str) -> str:
    d = re.sub(r"\D", "", str(doc or ""))
    if len(d) == 11:
        return f"***.{d[3:6]}.{d[6:9]}-**"
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    return ""


def baixar(ano: int) -> Path:
    url = config.URL_RECEITAS.format(ano=ano)
    dest = config.RAW_DIR / f"prestacao_candidatos_{ano}.zip"
    if not dest.exists():
        print(f"  [get ] {url} (grande — pode demorar)")
        with requests.get(url, headers=UA, stream=True, timeout=3600) as r:
            r.raise_for_status()
            tmp = dest.with_suffix(".part")
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(1 << 22):
                    f.write(chunk)
            tmp.rename(dest)
    return dest


def _ler_csv_do_zip(zip_path: Path, nome: str):
    """Itera dicts do CSV dentro do zip (latin-1, ';'), sem extrair pro disco."""
    with zipfile.ZipFile(zip_path) as z:
        if nome not in z.namelist():
            print(f"  [warn] {nome} ainda não existe no zip do TSE")
            return
        with z.open(nome) as f:
            wrapper = io.TextIOWrapper(f, encoding="latin-1", newline="")
            for row in csv.DictReader(wrapper, delimiter=";"):
                yield row


def _sancoes_por_cnpj() -> dict[str, list[dict]]:
    """cnpj completo → sanções CEIS/CNEP (para o cruzamento de fornecedores)."""
    try:
        import duckdb
        con = duckdb.connect(str(config.DB_PATH), read_only=True)
        out: dict[str, list[dict]] = {}
        for r in con.execute("""SELECT cnpj, cadastro, categoria, processo,
                                       orgao, inicio, fim FROM sancoes_pj""").fetchall():
            out.setdefault(r[0], []).append({
                "cadastro": r[1].upper(), "categoria": r[2], "processo": r[3],
                "orgao": r[4], "inicio": r[5], "fim": r[6]})
        con.close()
        return out
    except Exception as e:
        print(f"  [warn] sancoes_pj indisponível ({e}) — fornecedores sem cruzamento")
        return {}


def gerar_uf(uf: str, ano: int, zip_path: Path, sancoes: dict,
             saida: Path | None = None) -> int:
    # ── receitas ──
    receitas: dict[str, dict] = {}
    for r in _ler_csv_do_zip(zip_path, f"receitas_candidatos_{ano}_{uf}.csv"):
        sq = r["SQ_CANDIDATO"]
        v = _num(r["VR_RECEITA"])
        c = receitas.setdefault(sq, {"total": 0.0, "origens": {}, "doadores": {}})
        c["total"] += v
        origem = (r.get("DS_ORIGEM_RECEITA") or "Outros").strip().title()
        c["origens"][origem] = c["origens"].get(origem, 0.0) + v
        doc = re.sub(r"\D", "", r.get("NR_CPF_CNPJ_DOADOR") or "")
        nome = (r.get("NM_DOADOR_RFB") or r.get("NM_DOADOR") or "").strip().title()
        if nome:
            chave = doc or nome
            d = c["doadores"].setdefault(chave, {"nome": nome, "doc": doc, "valor": 0.0})
            d["valor"] += v

    # ── despesas contratadas ──
    despesas: dict[str, dict] = {}
    for r in _ler_csv_do_zip(zip_path, f"despesas_contratadas_candidatos_{ano}_{uf}.csv"):
        sq = r["SQ_CANDIDATO"]
        v = _num(r["VR_DESPESA_CONTRATADA"])
        c = despesas.setdefault(sq, {"total": 0.0, "fornecedores": {}})
        c["total"] += v
        doc = re.sub(r"\D", "", r.get("NR_CPF_CNPJ_FORNECEDOR") or "")
        nome = (r.get("NM_FORNECEDOR_RFB") or r.get("NM_FORNECEDOR") or "").strip().title()
        if nome:
            chave = doc or nome
            f_ = c["fornecedores"].setdefault(chave, {"nome": nome, "doc": doc, "valor": 0.0})
            f_["valor"] += v

    out_dir = saida or (config.OUT_DATA / "financiamento" / uf)
    out_dir.mkdir(parents=True, exist_ok=True)
    if saida is None:
        for antigo in Path(out_dir).glob("*.json"):
            antigo.unlink()

    n = 0
    for sq in set(receitas) | set(despesas):
        rec = receitas.get(sq, {"total": 0.0, "origens": {}, "doadores": {}})
        dep = despesas.get(sq, {"total": 0.0, "fornecedores": {}})
        top_doadores = sorted(rec["doadores"].values(),
                              key=lambda d: -d["valor"])[:TOP_N]
        top_forn = sorted(dep["fornecedores"].values(),
                          key=lambda d: -d["valor"])[:TOP_N]
        ficha = {
            "ano": ano,
            "receita_total": round(rec["total"], 2),
            "despesa_contratada_total": round(dep["total"], 2),
            "origens": [{"origem": k, "valor": round(v, 2)}
                        for k, v in sorted(rec["origens"].items(),
                                           key=lambda kv: -kv[1])],
            "top_doadores": [{
                "nome": d["nome"], "doc": _mask_pf(d["doc"]),
                "tipo": "PF" if len(d["doc"]) == 11 else
                        ("PJ" if len(d["doc"]) == 14 else ""),
                "valor": round(d["valor"], 2),
            } for d in top_doadores],
            "top_fornecedores": [{
                "nome": f_["nome"], "doc": _mask_pf(f_["doc"]),
                "tipo": "PF" if len(f_["doc"]) == 11 else
                        ("PJ" if len(f_["doc"]) == 14 else ""),
                "valor": round(f_["valor"], 2),
                "sancoes_da_empresa": sancoes.get(f_["doc"], []) if len(f_["doc"]) == 14 else [],
            } for f_ in top_forn],
            "fonte": f"TSE — prestação de contas eleitorais {ano} (dados abertos)",
            "fonte_url": f"https://dadosabertos.tse.jus.br/dataset/prestacao-de-contas-eleitorais-{ano}",
            "disclaimer": DISCLAIMER,
            "gerado_em": date.today().isoformat(),
        }
        (Path(out_dir) / f"{sq}.json").write_text(
            json.dumps(ficha, ensure_ascii=False), "utf-8")
        n += 1
    forn_sanc = sum(1 for sq in despesas
                    for f_ in despesas[sq]["fornecedores"].values()
                    if len(f_["doc"]) == 14 and f_["doc"] in sancoes)
    print(f"  {uf}: financiamento gerado para {n} candidatos "
          f"({forn_sanc} contratações de fornecedor em cadastro de sanção)")
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ufs", nargs="*", default=None)
    ap.add_argument("--ano", type=int, default=config.ANO_ELEICAO)
    ap.add_argument("--saida-teste", default=None,
                    help="dry-run: grava sidecars neste diretório em vez de docs/data")
    args = ap.parse_args()
    print(f"-- quem financia (prestação de contas {args.ano})")
    try:
        zip_path = baixar(args.ano)
    except requests.HTTPError as e:
        print(f"  [info] prestação de {args.ano} ainda não publicada pelo TSE ({e}) — "
              "a camada entra no ar automaticamente quando o arquivo existir.")
        return
    sancoes = _sancoes_por_cnpj()
    saida = Path(args.saida_teste) if args.saida_teste else None
    for uf in (args.ufs or config.UFS_ALVO):
        gerar_uf(uf, args.ano, zip_path, sancoes, saida)
    if saida:
        print(f"OK (dry-run) — sidecars em {saida}, nada publicado")
    else:
        print("OK — rode fichas.py (ou injetar.py) para injetar nas fichas")


if __name__ == "__main__":
    main()
