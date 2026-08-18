"""Gera um demo auto-contido (1 arquivo HTML) do site, com dados embutidos.

Serve pra mostrar o produto antes do deploy: busca funciona pros 888 do índice;
fichas completas embutidas pros majoritários + maiores patrimônios + quem tem
radar de imprensa (fotos em base64). O restante mostra aviso de demo.

Uso: python pipeline/build_demo.py --ufs GO --top 30
Saída: demo-raio-x.html (na raiz do repo)
"""
from __future__ import annotations

import argparse
import base64
import json
import re

import config


def montar(ufs: list[str], top: int) -> str:
    files, fotos = {}, {}
    for uf in ufs:
        idx = json.loads((config.OUT_DATA / uf / "index.json").read_text("utf-8"))
        files[f"data/{uf}/index.json"] = idx
        cands = idx["candidatos"]
        maj = [c for c in cands if c["cg"].upper() in ("GOVERNADOR", "SENADOR")]
        top_pat = sorted(cands, key=lambda c: c.get("pat") or 0, reverse=True)[:top]
        # + quem tem camada especial (TCM-GO, Siconfi/ex-gestores, QSA c/ sanção):
        # são as fichas que melhor mostram o produto
        com_camada = []
        for c in cands:
            for pasta in ("tcmgo", "tcego", "siconfi", "cnia", "alego"):
                if (config.OUT_DATA / pasta / uf / f"{c['sq']}.json").exists():
                    com_camada.append(c)
                    break
            else:
                q = config.OUT_DATA / "qsa" / uf / f"{c['sq']}.json"
                if q.exists() and any(e.get("sancoes_da_empresa")
                                      for e in json.loads(q.read_text("utf-8"))["empresas"]):
                    com_camada.append(c)
        escolhidos = {c["sq"]: c for c in maj + top_pat + com_camada}
        for sq in escolhidos:
            ficha = json.loads((config.OUT_DATA / uf / f"{sq}.json").read_text("utf-8"))
            files[f"data/{uf}/{sq}.json"] = ficha
            fjpg = config.OUT_DATA / uf / "fotos" / f"{sq}.jpg"
            if fjpg.exists():
                fotos[sq] = ("data:image/jpeg;base64,"
                             + base64.b64encode(fjpg.read_bytes()).decode())

    html = (config.DOCS_DIR / "index.html").read_text("utf-8")
    css = (config.DOCS_DIR / "style.css").read_text("utf-8")
    js = (config.DOCS_DIR / "app.js").read_text("utf-8")

    html = html.replace('<link rel="stylesheet" href="style.css">',
                        f"<style>\n{css}\n</style>")
    html = html.replace('<link rel="manifest" href="manifest.json">', "")
    html = re.sub(r'<link rel="(icon|apple-touch-icon)"[^>]*>', "", html)
    dados = json.dumps({"files": files, "fotos": fotos},
                       ensure_ascii=False, separators=(",", ":"))
    aviso = ('<div style="background:#f5b301;color:#0c1626;text-align:center;'
             'padding:8px 12px;font:600 14px system-ui">DEMO — dados reais do TSE de '
             'GO (18/08/2026). Fichas completas embutidas pros principais candidatos; '
             'na versão publicada, todos os 888 têm ficha.</div>')
    html = html.replace("<body>", "<body>\n" + aviso)
    html = html.replace('<script src="app.js"></script>',
                        f"<script>window.__DEMO_DATA__={dados};</script>\n"
                        f"<script>\n{js}\n</script>")
    html = html.replace('if ("serviceWorker" in navigator', 'if (false && ("serviceWorker" in navigator)')
    return html


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ufs", nargs="*", default=None)
    ap.add_argument("--top", type=int, default=30)
    args = ap.parse_args()
    out = config.ROOT / "demo-raio-x.html"
    out.write_text(montar(args.ufs or config.UFS_ALVO, args.top), "utf-8")
    print(f"OK — {out} ({out.stat().st_size/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
