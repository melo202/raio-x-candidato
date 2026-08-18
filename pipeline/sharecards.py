"""Gera share cards OG (1200×630 PNG) — a imagem que aparece quando a ficha
é compartilhada no WhatsApp/Instagram. Feature de crescimento do produto.

Saída: docs/c/{uf}/{SQ}.png

Uso:
    python pipeline/sharecards.py --ufs GO            # todos os candidatos
    python pipeline/sharecards.py --ufs GO --top 50   # só os N com maior patrimônio
"""
from __future__ import annotations

import argparse
import json

from PIL import Image, ImageDraw, ImageFont, ImageOps

import config

W, H = 1200, 630
BG = (12, 22, 38)          # azul-noite
BG2 = (17, 32, 55)
ACCENT = (245, 179, 1)     # âmbar
FG = (240, 244, 250)
MUT = (148, 163, 184)
FONT_DIR = "/usr/share/fonts/truetype/dejavu"


def _font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return ImageFont.truetype(f"{FONT_DIR}/{name}", size)


def _brl(v: float | None) -> str:
    if v is None:
        return "não declarado"
    s = f"{v:,.0f}".replace(",", ".")
    return f"R$ {s}"


def _fit_text(draw, text, max_w, size, bold=True, min_size=28):
    while size > min_size:
        f = _font(size, bold)
        if draw.textlength(text, font=f) <= max_w:
            return f
        size -= 4
    return _font(min_size, bold)


def gerar_card(ficha: dict, out_path) -> None:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # faixa diagonal sutil
    d.polygon([(W - 420, 0), (W, 0), (W, H), (W - 260, H)], fill=BG2)
    # barra de topo
    d.rectangle([0, 0, W, 10], fill=ACCENT)

    # foto (à direita)
    x_txt_max = W - 90
    foto = ficha.get("foto")
    if foto:
        src = config.DOCS_DIR / foto
        if src.exists():
            ph = 400
            p = Image.open(src).convert("RGB")
            p = ImageOps.fit(p, (int(ph * 0.78), ph))
            mask = Image.new("L", p.size, 0)
            ImageDraw.Draw(mask).rounded_rectangle([0, 0, *p.size], 28, fill=255)
            px, py = W - p.size[0] - 70, 115
            img.paste(p, (px, py), mask)
            d.rounded_rectangle([px - 3, py - 3, px + p.size[0] + 3, py + p.size[1] + 3],
                                30, outline=ACCENT, width=3)
            x_txt_max = px - 50

    # marca
    d.text((70, 42), "RAIO-X DO CANDIDATO", font=_font(30), fill=ACCENT)
    d.text((70, 84), "dados oficiais · TSE · sem nota, sem ranking",
           font=_font(21, bold=False), fill=MUT)

    y = 160
    nome = ficha.get("nome_urna") or ficha.get("nome") or "?"
    f = _fit_text(d, nome, x_txt_max - 70, 74)
    d.text((70, y), nome, font=f, fill=FG)
    y += f.size + 22

    linha2 = " · ".join(x for x in [
        ficha.get("cargo"),
        (ficha.get("partido") or {}).get("sigla"),
        f"nº {ficha['numero']}" if ficha.get("numero") else None,
    ] if x)
    d.text((70, y), linha2, font=_font(33, bold=False), fill=MUT)
    y += 62

    situ = (ficha.get("situacao") or {}).get("label") or ""
    if situ:
        f_s = _font(25)
        wpill = d.textlength(situ, font=f_s) + 44
        d.rounded_rectangle([70, y, 70 + wpill, y + 46], 23, outline=ACCENT, width=2)
        d.text((92, y + 9), situ, font=f_s, fill=ACCENT)
        y += 78

    serie = (ficha.get("patrimonio") or {}).get("serie") or []
    tot = next((p["total"] for p in serie
                if p["ano"] == ficha.get("ano") and p.get("declarou")), None)
    d.text((70, y), "Patrimônio declarado ao TSE (2026)",
           font=_font(24, bold=False), fill=MUT)
    d.text((70, y + 34), _brl(tot), font=_font(52), fill=FG)
    y += 34 + 66

    var = [v for v in (ficha.get("patrimonio") or {}).get("variacoes", [])
           if v.get("pct") is not None and v.get("para") == ficha.get("ano")]
    if var:
        pct = var[-1]["pct"]
        d.text((70, y), f"{'+' if pct >= 0 else ''}{pct:.0f}% desde {var[-1]['de']} "
               "(valores declarados pelo próprio candidato)",
               font=_font(23, bold=False), fill=MUT)

    d.rectangle([0, H - 70, W, H], fill=BG2)
    d.text((70, H - 51), "ficha completa, com fonte oficial em cada dado →  "
           + config.BASE_URL.replace("https://", ""),
           font=_font(24, bold=False), fill=FG)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG", optimize=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ufs", nargs="*", default=None)
    ap.add_argument("--top", type=int, default=None,
                    help="gera só os N candidatos de maior patrimônio (mais rápido)")
    args = ap.parse_args()

    for uf in (args.ufs or config.UFS_ALVO):
        idx = json.loads((config.OUT_DATA / uf / "index.json").read_text("utf-8"))
        cands = idx["candidatos"]
        if args.top:
            cands = sorted(cands, key=lambda c: c.get("pat") or 0,
                           reverse=True)[: args.top]
        n = 0
        for c in cands:
            ficha = json.loads(
                (config.OUT_DATA / uf / f"{c['sq']}.json").read_text("utf-8"))
            gerar_card(ficha, config.OUT_CARDS / uf.lower() / f"{c['sq']}.png")
            n += 1
        print(f"  {uf}: {n} share cards")


if __name__ == "__main__":
    main()
