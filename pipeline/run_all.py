"""Orquestrador: download → DuckDB → fichas → share cards → páginas SEO.

Uso:
    python pipeline/run_all.py                     # UFs de config.UFS_ALVO
    python pipeline/run_all.py --ufs GO            # UFs específicas
    python pipeline/run_all.py --ufs GO --force    # re-baixa dados de 2026
    python pipeline/run_all.py --skip-cards        # sem share cards (mais rápido)
"""
from __future__ import annotations

import argparse
import sys
import time

import config


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ufs", nargs="*", default=None)
    ap.add_argument("--force", action="store_true",
                    help="re-baixa os dados de 2026 (situação muda todo dia)")
    ap.add_argument("--skip-cards", action="store_true")
    ap.add_argument("--top-cards", type=int, default=None)
    args = ap.parse_args()
    ufs = args.ufs or config.UFS_ALVO
    t0 = time.time()

    print("### 1/4 download")
    import download
    for ano in config.ANOS_PATRIMONIO:
        download.baixar_ano(ano, force=(args.force and ano == config.ANO_ELEICAO))
    for uf in ufs:
        try:
            download.baixar_fotos(uf, force=args.force)
        except Exception as e:
            print(f"  [warn] fotos {uf}: {e}", file=sys.stderr)

    print("### 2/4 duckdb")
    import build_db
    build_db.build()

    print("### 2.5 camadas de fontes externas (cada uma isolada — falha não derruba o resto)")
    import subprocess
    from pathlib import Path
    pasta_pipe = Path(__file__).resolve().parent
    forca = ["--force"] if args.force else []
    etapas = [
        ("sancoes", []),                          # CEIS/CNEP/CEAF (muda todo dia)
        ("tcmgo", ["--ufs", *ufs] + forca),       # lista TCM-GO (muda todo dia)
        ("tcego", ["--ufs", *ufs] + forca),       # PDF TCE-GO (por eleição)
        ("gestao_numeros", ["--ufs", *ufs]),      # IDEB/INEP
        ("siconfi", ["--ufs", *ufs]),             # finanças municipais (anual)
        ("qsa", ["--ufs", *ufs]),                 # QSA RFB (zips mensais já baixados)
        ("cnia", ["--ufs", *ufs]),                # improbidade (drop-in manual)
        ("doacoes_feitas", []),                   # receitas 2022/2024 (estático)
        ("financiamento", ["--ufs", *ufs] + forca),  # quem financia 2026 (parcial 09/09→)
        ("alego", ["--ufs", *ufs]),               # ALEGO (dump da coleta assistida)
        ("radar_noticias", ["--ufs", *ufs]),      # imprensa (muda todo dia)
        ("parlamentar", ["--ufs", *ufs]),         # Câmara (semanal na prática)
        ("emendas", ["--ufs", *ufs] + forca),     # DEPOIS do parlamentar (lê os sidecars dele)
    ]
    falhas = []
    for mod, argv in etapas:
        r = subprocess.run([sys.executable, str(pasta_pipe / f"{mod}.py"), *argv])
        if r.returncode:
            falhas.append(mod)
            print(f"  [warn] camada {mod} falhou (rc={r.returncode}) — "
                  f"fichas seguirão com o dado anterior", file=sys.stderr)
    if falhas:
        print(f"### camadas com falha nesta rodada: {', '.join(falhas)}", file=sys.stderr)

    print("### 3/4 fichas")
    import duckdb
    import fichas
    from tcu import CruzadorTCU
    con = duckdb.connect(str(config.DB_PATH), read_only=True)
    cruzador = CruzadorTCU()
    for uf in ufs:
        fichas.gerar_uf(con, uf, cruzador)
    con.close()
    # regrava ufs.json
    sys.argv = ["fichas.py", "--ufs"]  # nada a regerar; só o meta
    import json
    from datetime import date
    config.OUT_DATA.mkdir(parents=True, exist_ok=True)
    publicadas = sorted({p.name for p in config.OUT_DATA.iterdir()
                         if p.is_dir() and len(p.name) == 2})
    (config.OUT_DATA / "ufs.json").write_text(
        json.dumps({"ano": config.ANO_ELEICAO,
                    "atualizado_em": date.today().isoformat(),
                    "ufs": publicadas}, ensure_ascii=False), "utf-8")

    print("### 4/4 share cards + páginas SEO")
    if not args.skip_cards:
        import sharecards
        for uf in ufs:
            idx = json.loads((config.OUT_DATA / uf / "index.json").read_text("utf-8"))
            cands = idx["candidatos"]
            if args.top_cards:
                cands = sorted(cands, key=lambda c: c.get("pat") or 0,
                               reverse=True)[: args.top_cards]
            for c in cands:
                f = json.loads((config.OUT_DATA / uf / f"{c['sq']}.json").read_text("utf-8"))
                sharecards.gerar_card(f, config.OUT_CARDS / uf.lower() / f"{c['sq']}.png")
            print(f"  {uf}: {len(cands)} cards")
    import stubs
    for uf in ufs:
        stubs.gerar_uf(uf)
    stubs.gerar_sitemap_index()

    # bump do service worker: troca a VERSAO por data — sem isso, quem já visitou
    # o site nunca recebe app.js/style.css novos (cache-first do shell)
    from datetime import date as _d
    import re as _re
    sw = config.DOCS_DIR / "sw.js"
    if sw.exists():
        from datetime import datetime as _dt
        novo_sw = _re.sub(r'const VERSAO = "[^"]+"',
                          f'const VERSAO = "raiox-{_dt.now().strftime("%Y%m%d%H%M")}"',
                          sw.read_text("utf-8"))
        sw.write_text(novo_sw, "utf-8")
        print("  sw.js: VERSAO ← raiox-" + _d.today().strftime("%Y%m%d"))

    print(f"### concluído em {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
