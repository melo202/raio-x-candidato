"""Gera as páginas estáticas por candidato (SEO + OG) e o sitemap.

GitHub Pages é estático, então o preview no WhatsApp e a indexação no Google
precisam de 1 HTML real por candidato: docs/c/{uf}/{SQ}.html
— com meta OG apontando pro share card e redirect imediato pra SPA.

~20 mil páginas na escala nacional = a jogada de busca orgânica
("candidato X é ficha limpa" explode em setembro).

Uso: python pipeline/stubs.py --ufs GO
"""
from __future__ import annotations

import argparse
import html
import json

import config

TPL = """<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>{titulo}</title>
<meta name="description" content="{desc}">
<meta property="og:type" content="profile">
<meta property="og:title" content="{titulo}">
<meta property="og:description" content="{desc}">
<meta property="og:image" content="{og_img}">
<meta property="og:url" content="{url}">
<meta name="twitter:card" content="summary_large_image">
<link rel="canonical" href="{url}">
<meta name="viewport" content="width=device-width,initial-scale=1">
<script>location.replace("{spa}");</script>
</head>
<body>
<noscript>
  <h1>{titulo}</h1>
  <p>{desc}</p>
  <p><a href="{spa}">Ver a ficha completa</a></p>
</noscript>
</body>
</html>
"""


def _brl(v):
    if v is None:
        return "não declarado"
    return "R$ " + f"{v:,.0f}".replace(",", ".")


def gerar_uf(uf: str) -> int:
    idx = json.loads((config.OUT_DATA / uf / "index.json").read_text("utf-8"))
    out_dir = config.OUT_CARDS / uf.lower()
    out_dir.mkdir(parents=True, exist_ok=True)
    urls = []
    for c in idx["candidatos"]:
        sq = c["sq"]
        titulo = f"{c['nu'] or c['nm']} ({c['pt']}) — {c['cg']} · {uf} 2026 | {config.PROJECT_NAME}"
        # resumo textual das camadas presentes na ficha (indexável — é o que o
        # eleitor busca: "candidato X contas irregulares")
        try:
            ficha = json.loads((config.OUT_DATA / uf / f"{sq}.json").read_text("utf-8"))
        except Exception:
            ficha = {}
        extras = []
        if ficha.get("tcmgo"):
            extras.append("registro na lista de contas do TCM-GO")
        if ficha.get("tcego"):
            extras.append("registro na relação de contas do TCE-GO")
        if (ficha.get("sancoes") or {}).get("registros"):
            extras.append("registro em cadastro de sanção da CGU")
        if (ficha.get("tcu") or {}).get("listado"):
            extras.append("registro na lista de contas do TCU")
        if ficha.get("qsa"):
            extras.append(f"{len(ficha['qsa'].get('empresas', []))} participação(ões) "
                          "societária(s) na Receita Federal")
        if ficha.get("siconfi"):
            extras.append("finanças do município no mandato (Tesouro/Siconfi)")
        if ficha.get("gestao"):
            extras.append("IDEB do município no mandato (INEP)")
        extras_txt = ("Registros públicos na ficha: " + "; ".join(extras) + ". "
                      if extras else "")
        desc = (f"Quem é {c['nm']}? Situação do registro: {c['st']}. Patrimônio "
                f"declarado ao TSE: {_brl(c.get('pat'))}. {extras_txt}"
                "Ficha completa com fonte oficial em cada dado — patrimônio desde 2014, "
                "histórico eleitoral, contas nos tribunais (TCU/TCE-GO/TCM-GO), sanções, "
                "empresas e finanças públicas. Sem nota, sem ranking.")
        url = f"{config.BASE_URL}/c/{uf.lower()}/{sq}.html"
        card = out_dir / f"{sq}.png"
        og_img = (f"{config.BASE_URL}/c/{uf.lower()}/{sq}.png" if card.exists()
                  else f"{config.BASE_URL}/assets/og-default.png")
        page = TPL.format(
            titulo=html.escape(titulo), desc=html.escape(desc),
            og_img=og_img, url=url,
            spa=f"{config.BASE_URL}/#/{uf.lower()}/{sq}",
        )
        (out_dir / f"{sq}.html").write_text(page, "utf-8")
        urls.append(url)

    # sitemap incremental por UF + índice
    sm = ["<?xml version='1.0' encoding='UTF-8'?>",
          "<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"]
    for u in urls:
        sm.append(f"<url><loc>{html.escape(u)}</loc><changefreq>daily</changefreq></url>")
    sm.append("</urlset>")
    (config.DOCS_DIR / f"sitemap-{uf.lower()}.xml").write_text("\n".join(sm), "utf-8")
    return len(urls)


def gerar_sitemap_index() -> None:
    partes = sorted(config.DOCS_DIR.glob("sitemap-*.xml"))
    xml = ["<?xml version='1.0' encoding='UTF-8'?>",
           "<sitemapindex xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"]
    for p in partes:
        xml.append(f"<sitemap><loc>{config.BASE_URL}/{p.name}</loc></sitemap>")
    xml.append("</sitemapindex>")
    (config.DOCS_DIR / "sitemap.xml").write_text("\n".join(xml), "utf-8")
    (config.DOCS_DIR / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {config.BASE_URL}/sitemap.xml\n", "utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ufs", nargs="*", default=None)
    args = ap.parse_args()
    for uf in (args.ufs or config.UFS_ALVO):
        n = gerar_uf(uf)
        print(f"  {uf}: {n} páginas SEO/OG")
    gerar_sitemap_index()
    print("  sitemap.xml + robots.txt ok")


if __name__ == "__main__":
    main()
