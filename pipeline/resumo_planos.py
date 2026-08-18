"""Resume os planos de governo (governador/senador) com a Claude API — em batch,
no pipeline, nunca no site (roda 1x por candidato, não por visita).

Requisitos:
    pip install anthropic pypdf
    export ANTHROPIC_API_KEY=...

Saída: docs/data/planos/{UF}/{SQ}.json  →  injetado na ficha na próxima
rodada de fichas.py (campo "resumo_plano").

Uso: python pipeline/resumo_planos.py --ufs GO
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import zipfile

import requests

import config

MODEL = os.environ.get("RAIOX_CLAUDE_MODEL", "claude-sonnet-4-5")

PROMPT = """Você resume planos de governo para eleitores comuns, com neutralidade absoluta.

Regras inegociáveis:
- Zero adjetivo valorativo, zero opinião, zero previsão de viabilidade.
- Apenas o que está escrito no documento; se algo é vago, diga "o plano não detalha".
- Linguagem de gente: frases curtas, sem juridiquês nem economês.

Responda SOMENTE com JSON válido neste formato:
{"resumo": "3 a 5 frases neutras sobre o que o plano propõe",
 "temas": [{"tema": "Saúde", "propostas": ["...", "..."]}, ...],
 "omissoes_notaveis": ["temas comuns que o plano não aborda"]}

PLANO DE GOVERNO:
"""


def _extrair_pdfs(uf: str) -> dict[str, str]:
    """Baixa o zip de propostas da UF e retorna {SQ_CANDIDATO: texto}."""
    from pypdf import PdfReader

    url = config.URL_PROPOSTA_GOVERNO.format(ano=config.ANO_ELEICAO, uf=uf)
    r = requests.get(url, timeout=600)
    r.raise_for_status()
    out = {}
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        for nome in z.namelist():
            if not nome.lower().endswith(".pdf"):
                continue
            # padrão TSE: proposta_governo_{ano}_{SQ}.pdf (tolerante a variações)
            digitos = [t for t in nome.replace(".pdf", "").split("_") if t.isdigit()]
            sq = max(digitos, key=len) if digitos else None
            if not sq or len(sq) < 8:
                continue
            try:
                reader = PdfReader(io.BytesIO(z.read(nome)))
                texto = "\n".join((p.extract_text() or "") for p in reader.pages)
                if texto.strip():
                    out[sq] = texto[:150_000]
            except Exception as e:
                print(f"  [warn] {nome}: {e}", file=sys.stderr)
    return out


def resumir(texto: str) -> dict:
    import anthropic

    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        messages=[{"role": "user", "content": PROMPT + texto}],
    )
    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`").removeprefix("json").strip()
    return json.loads(raw)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ufs", nargs="*", default=None)
    args = ap.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Defina ANTHROPIC_API_KEY antes de rodar.")

    for uf in (args.ufs or config.UFS_ALVO):
        print(f"-- {uf}: baixando propostas de governo")
        try:
            pdfs = _extrair_pdfs(uf)
        except requests.HTTPError as e:
            print(f"  [warn] {uf}: {e}", file=sys.stderr)
            continue
        out_dir = config.OUT_DATA / "planos" / uf
        out_dir.mkdir(parents=True, exist_ok=True)
        for sq, texto in pdfs.items():
            dest = out_dir / f"{sq}.json"
            if dest.exists():
                print(f"  [skip] {sq}")
                continue
            print(f"  [ia  ] {sq} ({len(texto)//1000}k chars)")
            try:
                resumo = resumir(texto)
                resumo["fonte"] = config.URL_PROPOSTA_GOVERNO.format(
                    ano=config.ANO_ELEICAO, uf=uf)
                resumo["gerado_por"] = f"Claude ({MODEL}) — resumo automatizado do PDF oficial"
                dest.write_text(json.dumps(resumo, ensure_ascii=False), "utf-8")
            except Exception as e:
                print(f"  [erro] {sq}: {e}", file=sys.stderr)
        print(f"  {uf}: {len(pdfs)} planos processados — rode fichas.py de novo p/ injetar")


if __name__ == "__main__":
    main()
