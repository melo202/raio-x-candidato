"""Camada — TCM-GO: contas com parecer pela rejeição ou julgadas irregulares.

Fonte oficial: API de dados abertos do Tribunal de Contas dos Municípios do
Estado de Goiás (ws.tcm.go.gov.br), a mesma que alimenta a página
"Contas com parecer prévio pela rejeição ou julgamentos irregulares".
A lista traz três recortes (coluna TipoLista):
    - Contas de Prefeitos e Ex-Prefeitos (parecer prévio pela rejeição)
    - Contas de Gestão de Demais Autoridades
    - Contas Julgadas Irregulares com Débito

Cruzamento com salvaguarda de identidade (mesmo padrão do CEAF em sancoes.py):
o CPF publicado pelo TCM vem mascarado (só os 2 primeiros dígitos visíveis),
então um registro só entra na ficha com DUPLA coincidência:
    nome normalizado idêntico  E  mesmos dígitos iniciais do CPF.
Como sinal adicional (exibido, não eliminatório), marcamos se o município do
registro aparece no histórico do candidato (mandato ou candidatura).

Princípio do projeto: a ficha NUNCA diz "condenado"/"irregularidade" como
juízo — diz que o nome consta da lista oficial X, com processo, acórdão,
datas e link direto ao processo eletrônico do TCM-GO.

Uso: python pipeline/tcmgo.py --ufs GO
Depois: rode fichas.py de novo para injetar nas fichas (ou injetar.py).
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import unicodedata
from datetime import date

import requests

import config

URL_API = "https://ws.tcm.go.gov.br/api/rest/dados/contas-irregulares"
URL_PAGINA = ("https://www.tcmgo.tc.br/site/"
              "contas-com-parecer-previo-pela-rejeicao-ou-julgamentos-irregulares/")

DISCLAIMER = (
    "Lista oficial publicada pelo TCM-GO (contas com parecer prévio pela "
    "rejeição, contas de gestão julgadas irregulares e contas com débito). "
    "Parecer ou julgamento do Tribunal de Contas não significa, por si só, "
    "inelegibilidade nem condenação criminal: contas de prefeito são julgadas "
    "em definitivo pela Câmara Municipal, a decisão pode estar sub judice e "
    "quem decide sobre registro de candidatura é a Justiça Eleitoral, caso a "
    "caso (LC 64/1990). Consulte o processo no link da fonte."
)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^A-Za-z ]", " ", s)).strip().upper()


def _fix_encoding(texto: str) -> str:
    """A API devolve UTF-8 com linhas re-codificadas (mojibake misto).
    Conserta linha a linha; onde o roundtrip falha, mantém o original."""
    linhas = []
    for ln in texto.splitlines():
        try:
            linhas.append(ln.encode("latin-1").decode("utf-8"))
        except (UnicodeEncodeError, UnicodeDecodeError):
            linhas.append(ln)
    return "\n".join(linhas)


def baixar_lista(force: bool = False) -> list[dict]:
    dest = config.RAW_DIR / "tcmgo_contas_irregulares.csv"
    if force or not dest.exists():
        print("  [get ] lista de contas irregulares (API TCM-GO)")
        r = requests.get(URL_API, timeout=300,
                         headers={"User-Agent": "Mozilla/5.0 (dados abertos; uso civico)"})
        r.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(_fix_encoding(r.content.decode("utf-8", "replace")), "utf-8")
    rows = list(csv.DictReader(io.StringIO(dest.read_text("utf-8"))))
    print(f"  lista TCM-GO: {len(rows)} registros")
    return rows


def _iniciais_cpf_mascarado(cpf_mascarado: str) -> str:
    """'76***.***-**' → '76' (dígitos antes do primeiro asterisco)."""
    m = re.match(r"\s*(\d+)", str(cpf_mascarado or ""))
    return m.group(1) if m else ""


def carregar_candidatos(uf: str) -> list[dict]:
    """Lê SQ/nome/CPF do consulta_cand bruto (latin-1 ou já convertido)."""
    pasta = config.RAW_DIR / f"consulta_cand_{config.ANO_ELEICAO}"
    path = pasta / f"consulta_cand_{config.ANO_ELEICAO}_{uf}.csv"
    raw = path.read_bytes()
    try:
        texto = raw.decode("utf-8")
    except UnicodeDecodeError:
        texto = raw.decode("latin-1")
    rows = csv.DictReader(io.StringIO(texto), delimiter=";")
    return [{"sq": r["SQ_CANDIDATO"], "nome": r["NM_CANDIDATO"],
             "cpf": re.sub(r"\D", "", r["NR_CPF_CANDIDATO"])} for r in rows]


def _municipios_do_historico(uf: str, sq: str) -> set[str]:
    """Municípios em que o candidato teve mandato ou disputou (da ficha já gerada)."""
    path = config.OUT_DATA / uf / f"{sq}.json"
    if not path.exists():
        return set()
    ficha = json.loads(path.read_text("utf-8"))
    hist = ficha.get("historico", {})
    locais = {m.get("onde") for m in hist.get("mandatos", [])}
    for e in hist.get("eleicoes", []):
        locais.add(e.get("onde") or e.get("municipio"))
    return {_norm(x) for x in locais if x}


def gerar_uf(uf: str, lista: list[dict]) -> int:
    candidatos = carregar_candidatos(uf)
    por_nome: dict[str, list[dict]] = {}
    for c in candidatos:
        por_nome.setdefault(_norm(c["nome"]), []).append(c)

    hits: dict[str, list[dict]] = {}
    for row in lista:
        nome_n = _norm(row.get("Nome"))
        iniciais = _iniciais_cpf_mascarado(row.get("CPF"))
        for c in por_nome.get(nome_n, []):
            if not iniciais or not c["cpf"].startswith(iniciais):
                continue  # dupla coincidência obrigatória
            municipio = (row.get("Município") or "").strip()
            hits.setdefault(c["sq"], []).append({
                "municipio": municipio.title(),
                "tipo_lista": row.get("TipoLista"),
                "assunto": row.get("Assunto"),
                "periodo": row.get("Mês/Ano"),
                "processo": row.get("Processo/Fase"),
                "acordao": row.get("Acórdão/Resolução"),
                "data_julgamento": row.get("Data Julgamento"),
                "transito_em_julgado": row.get("Dt. Trânsito Julgado"),
                "processo_url": row.get("Url"),
                "criterio": "nome + iniciais do CPF",
                "municipio_no_historico":
                    _norm(municipio.split(" - ")[0])
                    in _municipios_do_historico(uf, c["sq"]),
            })

    out_dir = config.OUT_DATA / "tcmgo" / uf
    out_dir.mkdir(parents=True, exist_ok=True)
    for antigo in out_dir.glob("*.json"):     # limpa a rodada anterior: quem saiu
        antigo.unlink()                       # da lista não pode continuar na ficha
    for sq, registros in hits.items():
        (out_dir / f"{sq}.json").write_text(json.dumps({
            "registros": registros,
            "fonte": "TCM-GO — contas com parecer pela rejeição ou julgadas irregulares",
            "fonte_url": URL_PAGINA,
            "consulta_oficial": URL_PAGINA,
            "disclaimer": DISCLAIMER,
            "gerado_em": date.today().isoformat(),
        }, ensure_ascii=False), "utf-8")
    print(f"  {uf}: {len(hits)} candidato(s) com registro no TCM-GO "
          f"({sum(len(v) for v in hits.values())} registros)")
    return len(hits)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ufs", nargs="*", default=None)
    ap.add_argument("--force", action="store_true", help="re-baixa a lista")
    args = ap.parse_args()
    print("-- TCM-GO contas irregulares")
    lista = baixar_lista(force=args.force)
    for uf in (args.ufs or config.UFS_ALVO):
        if uf != "GO":
            continue  # lista é do tribunal de contas DOS MUNICÍPIOS goianos
        gerar_uf(uf, lista)
    print("OK — rode fichas.py (ou injetar.py) para injetar nas fichas")


if __name__ == "__main__":
    main()
