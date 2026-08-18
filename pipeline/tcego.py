"""Camada — TCE-GO: responsáveis com contas julgadas irregulares (âmbito ESTADUAL).

Complementa o TCM-GO (municipal): o TCE-GO julga contas de gestores ESTADUAIS
(secretários, dirigentes de autarquias, ordenadores de despesa do estado).

Fonte: "Relação de Responsáveis com Contas Julgadas Irregulares" que o TCE-GO
publica por eleição (LC 64/1990, art. 11, §5º) em portal.tce.go.gov.br —
o painel Qlik da página é só um índice; os dados vivem em PDFs por ano com
CPF COMPLETO, o que permite cruzamento por CPF (certeza total, sem homônimo).

Uso: python pipeline/tcego.py --ufs GO
Depois: rode fichas.py de novo (ou injetar.py) para injetar nas fichas.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
from datetime import date

import requests

import config

# Lista atualizada publicada para as eleições 2026 (índice exportado do painel
# em portal.tce.go.gov.br/contas-irregulares, 18/08/2026)
URL_PDF_2026 = ("https://portal.tce.go.gov.br/documents/20181/835290/"
                "Lista de Responsáveis com Contas Julgadas Irregulares - Atualizada.pdf")
URL_PAGINA = "https://portal.tce.go.gov.br/contas-irregulares"

DISCLAIMER = (
    "Relação oficial publicada pelo TCE-GO (contas de gestores estaduais "
    "julgadas irregulares, enviada à Justiça Eleitoral nos termos da "
    "LC 64/1990). Constar da lista não significa, por si só, inelegibilidade "
    "nem condenação criminal: a decisão pode estar sub judice e quem decide "
    "sobre o registro de candidatura é a Justiça Eleitoral, caso a caso. "
    "Consulte o processo na fonte."
)


def _so_digitos(s: str) -> str:
    return re.sub(r"\D", "", str(s or ""))


def baixar_lista(force: bool = False) -> list[dict]:
    """Baixa o PDF 2026 e extrai a tabela → lista canônica (cache em CSV)."""
    cache = config.RAW_DIR / "tcego_contas_irregulares_2026.csv"
    if cache.exists() and not force:
        return list(csv.DictReader(io.StringIO(cache.read_text("utf-8"))))
    import urllib.parse
    import pdfplumber
    pdf_path = config.RAW_DIR / "tcego_2026.pdf"
    if force or not pdf_path.exists():
        print("  [get ] relação de contas irregulares (PDF TCE-GO)")
        r = requests.get(urllib.parse.quote(URL_PDF_2026, safe=":/"),
                         timeout=300, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(r.content)
    registros = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                for row in table:
                    if not row or len(row) < 6:
                        continue
                    cpf = _so_digitos(row[1])
                    if len(cpf) != 11:      # cabeçalhos, títulos, linhas vazias
                        continue
                    def limpar(s):
                        s = re.sub(r"\s+", " ", (s or "")).strip()
                        # artefatos do PDF: "09 07 2024" → "09/07/2024", "4136 2022" → "4136/2022"
                        s = re.sub(r"^(\d{2}) (\d{2}) (\d{4})$", r"\1/\2/\3", s)
                        s = re.sub(r"^(\d+) (\d{4})$", r"\1/\2", s)
                        return s
                    registros.append({
                        "nome": limpar(row[0]), "cpf": cpf,
                        "natureza": limpar(row[2]), "processo": limpar(row[3]),
                        "acordao": limpar(row[4]),
                        "transito_em_julgado": limpar(row[5]),
                    })
    with open(cache, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(registros[0].keys()))
        w.writeheader()
        w.writerows(registros)
    print(f"  lista TCE-GO 2026: {len(registros)} responsáveis")
    return registros


def carregar_candidatos(uf: str) -> dict[str, dict]:
    pasta = config.RAW_DIR / f"consulta_cand_{config.ANO_ELEICAO}"
    path = pasta / f"consulta_cand_{config.ANO_ELEICAO}_{uf}.csv"
    raw = path.read_bytes()
    try:
        texto = raw.decode("utf-8")
    except UnicodeDecodeError:
        texto = raw.decode("latin-1")
    rows = csv.DictReader(io.StringIO(texto), delimiter=";")
    return {_so_digitos(r["NR_CPF_CANDIDATO"]):
            {"sq": r["SQ_CANDIDATO"], "nome": r["NM_CANDIDATO"]} for r in rows}


def gerar_uf(uf: str, lista: list[dict]) -> int:
    por_cpf = carregar_candidatos(uf)
    hits: dict[str, list[dict]] = {}
    for r in lista:
        c = por_cpf.get(r["cpf"])
        if not c:
            continue
        hits.setdefault(c["sq"], []).append({
            "natureza": r["natureza"], "processo": r["processo"],
            # não há deep link público por processo (a busca exige captcha);
            # o link abre a consulta oficial, onde se cola o número
            "processo_url": "https://www.tce.go.gov.br/ConsultaProcesso",
            "acordao": r["acordao"],
            "transito_em_julgado": r["transito_em_julgado"],
            "criterio": "cpf",
        })
    out_dir = config.OUT_DATA / "tcego" / uf
    out_dir.mkdir(parents=True, exist_ok=True)
    for antigo in out_dir.glob("*.json"):     # limpa a rodada anterior: quem saiu
        antigo.unlink()                       # da lista não pode continuar na ficha
    for sq, regs in hits.items():
        (out_dir / f"{sq}.json").write_text(json.dumps({
            "registros": regs,
            "fonte": "TCE-GO — relação de responsáveis com contas julgadas irregulares (2026)",
            "fonte_url": URL_PAGINA,
            "consulta_oficial": URL_PAGINA,
            "disclaimer": DISCLAIMER,
            "gerado_em": date.today().isoformat(),
        }, ensure_ascii=False), "utf-8")
    print(f"  {uf}: {len(hits)} candidato(s) na lista do TCE-GO "
          f"({sum(len(v) for v in hits.values())} registros)")
    return len(hits)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ufs", nargs="*", default=None)
    ap.add_argument("--force", action="store_true", help="re-baixa o PDF")
    args = ap.parse_args()
    print("-- TCE-GO contas julgadas irregulares (estadual)")
    lista = baixar_lista(force=args.force)
    for uf in (args.ufs or config.UFS_ALVO):
        if uf != "GO":
            continue
        gerar_uf(uf, lista)
    print("OK — rode fichas.py (ou injetar.py) para injetar nas fichas")


if __name__ == "__main__":
    main()
