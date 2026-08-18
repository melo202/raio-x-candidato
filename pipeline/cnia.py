"""Camada — CNIA/CNJ: condenações cíveis por improbidade administrativa.

DESCOBERTA IMPORTANTE (18/08/2026): a consulta pública do CNIA
(cnj.jus.br/improbidade_adm/consultar_requerido.php) valida reCAPTCHA no
SERVIDOR — o POST sem token volta "Por favor, resolva o recaptcha".
Ou seja: rodar do VPS NÃO resolve (o bloqueio não é de IP de datacenter).
Não há dump oficial em dados abertos.

Caminhos de coleta que funcionam:
    A) Coleta assistida pelo navegador (Claude in Chrome na máquina do Bruno,
       resolvendo o checkbox quando aparecer) — exportar os resultados para CSV.
    B) Consulta manual dirigida: só os ~60 nomes de maior exposição
       (majoritários + ex-gestores) já cobrem o que interessa ao eleitor.

Este módulo consome o(s) CSV(s) soltos em data/cnia/ (mesmo padrão do tcu.py):
    Colunas reconhecidas (nomes flexíveis): NOME, CPF, PROCESSO, TRIBUNAL/ORGAO,
    TRANSITO_JULGADO, PENA/CONDENACAO, URL.
Cruzamento: CPF completo quando houver (certeza); senão nome normalizado
EXATO (marcado criterio="nome" para o aviso de homonímia na ficha).

Princípio do projeto: a ficha diz que o nome consta do cadastro oficial do
CNJ, com processo, tribunal e trânsito em julgado — nunca adjetiva.

Uso: python pipeline/cnia.py --ufs GO
Depois: rode fichas.py de novo (ou injetar.py) para injetar nas fichas.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import unicodedata
from datetime import date

import config

CNIA_DIR = config.DATA_DIR / "cnia"
CONSULTA = "https://www.cnj.jus.br/improbidade_adm/consultar_requerido.php"

DISCLAIMER = (
    "Cadastro Nacional de Condenações Cíveis por Ato de Improbidade "
    "Administrativa e Inelegibilidade, mantido pelo CNJ com registros enviados "
    "pelos tribunais. Improbidade administrativa é matéria CÍVEL, não criminal; "
    "o registro pode estar em recurso e a inelegibilidade só existe nas "
    "hipóteses e prazos da LC 64/1990, decididos pela Justiça Eleitoral. "
    "Confira o processo na consulta oficial do CNJ."
)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^A-Za-z ]", " ", s)).strip().upper()


def _so_digitos(s: str) -> str:
    return re.sub(r"\D", "", str(s or ""))


def _achar_coluna(cols, *padroes):
    for c in cols:
        cn = _norm(c).replace(" ", "_")
        for p in padroes:
            if p in cn:
                return c
    return None


def carregar_listas() -> list[dict]:
    """Concatena todos os CSVs de data/cnia/ num formato canônico."""
    registros = []
    for path in sorted(CNIA_DIR.glob("*.csv")):
        raw = path.read_bytes()
        for enc in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                texto = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        delim = ";" if texto.count(";") > texto.count(",") else ","
        rows = list(csv.DictReader(io.StringIO(texto), delimiter=delim))
        if not rows:
            continue
        cols = list(rows[0].keys())
        c_nome = _achar_coluna(cols, "NOME", "REQUERIDO")
        c_cpf = _achar_coluna(cols, "CPF")
        c_proc = _achar_coluna(cols, "PROCESSO", "NUM_PROC")
        c_trib = _achar_coluna(cols, "TRIBUNAL", "ORGAO", "VARA", "COMARCA")
        c_tran = _achar_coluna(cols, "TRANSITO")
        c_pena = _achar_coluna(cols, "PENA", "CONDENACAO", "SANCAO")
        c_url = _achar_coluna(cols, "URL", "LINK")
        for r in rows:
            registros.append({
                "nome": r.get(c_nome, ""), "cpf": _so_digitos(r.get(c_cpf, "")),
                "processo": r.get(c_proc, ""), "orgao": r.get(c_trib, ""),
                "transito_em_julgado": r.get(c_tran, ""),
                "pena": r.get(c_pena, ""), "url": r.get(c_url, ""),
            })
        print(f"  [ok  ] {path.name}: {len(rows)} linhas")
    return registros


def carregar_candidatos(uf: str) -> list[dict]:
    pasta = config.RAW_DIR / f"consulta_cand_{config.ANO_ELEICAO}"
    path = pasta / f"consulta_cand_{config.ANO_ELEICAO}_{uf}.csv"
    raw = path.read_bytes()
    try:
        texto = raw.decode("utf-8")
    except UnicodeDecodeError:
        texto = raw.decode("latin-1")
    rows = csv.DictReader(io.StringIO(texto), delimiter=";")
    return [{"sq": r["SQ_CANDIDATO"], "nome": r["NM_CANDIDATO"],
             "cpf": _so_digitos(r["NR_CPF_CANDIDATO"])} for r in rows]


def gerar_uf(uf: str, registros: list[dict]) -> int:
    candidatos = carregar_candidatos(uf)
    por_cpf = {c["cpf"]: c for c in candidatos if c["cpf"]}
    por_nome: dict[str, list[dict]] = {}
    for c in candidatos:
        por_nome.setdefault(_norm(c["nome"]), []).append(c)

    hits: dict[str, list[dict]] = {}
    for r in registros:
        alvo, criterio = None, None
        if r["cpf"] and r["cpf"] in por_cpf:
            alvo, criterio = [por_cpf[r["cpf"]]], "cpf"
        elif not r["cpf"]:
            cands = por_nome.get(_norm(r["nome"]), [])
            if len(cands) == 1:
                alvo, criterio = cands, "nome"
        if not alvo:
            continue
        for c in alvo:
            hits.setdefault(c["sq"], []).append({
                "processo": r["processo"], "orgao": r["orgao"],
                "transito_em_julgado": r["transito_em_julgado"],
                "pena": r["pena"], "url": r["url"] or CONSULTA,
                "criterio": criterio,
            })

    out_dir = config.OUT_DATA / "cnia" / uf
    out_dir.mkdir(parents=True, exist_ok=True)
    for antigo in out_dir.glob("*.json"):     # limpa a rodada anterior: quem saiu
        antigo.unlink()                       # da lista não pode continuar na ficha
    for sq, regs in hits.items():
        (out_dir / f"{sq}.json").write_text(json.dumps({
            "registros": regs,
            "fonte": "CNJ — Cadastro Nacional de Condenações por Improbidade (CNIA)",
            "fonte_url": CONSULTA,
            "consulta_oficial": CONSULTA,
            "disclaimer": DISCLAIMER,
            "gerado_em": date.today().isoformat(),
        }, ensure_ascii=False), "utf-8")
    print(f"  {uf}: {len(hits)} candidato(s) com registro no CNIA")
    return len(hits)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ufs", nargs="*", default=None)
    args = ap.parse_args()
    print("-- CNIA/CNJ improbidade")
    CNIA_DIR.mkdir(parents=True, exist_ok=True)
    registros = carregar_listas()
    if not registros:
        print("  [info] nenhum CSV em data/cnia/ — veja o cabeçalho deste "
              "módulo para as duas formas de coleta (captcha impede automação).")
        return
    for uf in (args.ufs or config.UFS_ALVO):
        gerar_uf(uf, registros)
    print("OK — rode fichas.py (ou injetar.py) para injetar nas fichas")


if __name__ == "__main__":
    main()
