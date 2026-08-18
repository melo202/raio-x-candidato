"""Baixa e extrai os datasets oficiais do TSE.

Uso:
    python pipeline/download.py                # baixa o que faltar
    python pipeline/download.py --force-2026   # força re-download do ano corrente
    python pipeline/download.py --fotos GO SP  # fotos das UFs indicadas
"""
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

import requests

import config

UA = {"User-Agent": f"{config.PROJECT_NAME} (dados abertos; uso civico)"}


def _download(url: str, dest: Path, force: bool = False) -> bool:
    """Baixa `url` para `dest`. Retorna True se baixou (False = já existia)."""
    if dest.exists() and not force:
        print(f"  [skip] {dest.name} já existe")
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  [get ] {url}")
    with requests.get(url, headers=UA, stream=True, timeout=600) as r:
        r.raise_for_status()
        tmp = dest.with_suffix(dest.suffix + ".part")
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
        tmp.rename(dest)
    print(f"  [ok  ] {dest.name} ({dest.stat().st_size/1e6:.1f} MB)")
    return True


def _extract(zip_path: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    marcador = out_dir / ".utf8_ok"          # criado por build_db após converter
    if marcador.exists():
        marcador.unlink()                     # CSVs novos chegam em latin-1 de novo
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(out_dir)


def baixar_ano(ano: int, force: bool = False) -> None:
    raw = config.RAW_DIR
    fontes = [
        (f"consulta_cand_{ano}", config.URL_CONSULTA_CAND.format(ano=ano)),
        (f"bem_candidato_{ano}", config.URL_BEM_CANDIDATO.format(ano=ano)),
    ]
    if ano == config.ANO_ELEICAO:
        fontes.append((f"rede_social_candidato_{ano}",
                       config.URL_REDE_SOCIAL.format(ano=ano)))
    for nome, url in fontes:
        z = raw / f"{nome}.zip"
        baixou = _download(url, z, force=force)
        pasta = raw / nome
        if baixou or not pasta.exists():
            print(f"  [unz ] {nome}")
            _extract(z, pasta)


def baixar_fotos(uf: str, ano: int | None = None, force: bool = False) -> None:
    ano = ano or config.ANO_ELEICAO
    url = config.URL_FOTOS.format(ano=ano, uf=uf)
    z = config.RAW_DIR / f"foto_cand{ano}_{uf}_div.zip"
    baixou = _download(url, z, force=force)
    pasta = config.RAW_DIR / f"fotos_{ano}_{uf}"
    if baixou or not pasta.exists():
        _extract(z, pasta)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force-2026", action="store_true",
                    help="re-baixa os arquivos do ano corrente (situação muda todo dia)")
    ap.add_argument("--fotos", nargs="*", metavar="UF", default=None,
                    help="baixa fotos das UFs (default: UFS_ALVO)")
    args = ap.parse_args()

    print("== Datasets TSE ==")
    for ano in config.ANOS_PATRIMONIO:
        force = args.force_2026 and ano == config.ANO_ELEICAO
        print(f"-- {ano}")
        baixar_ano(ano, force=force)

    ufs = args.fotos if args.fotos else config.UFS_ALVO
    print("== Fotos ==")
    for uf in ufs:
        print(f"-- {uf}")
        try:
            baixar_fotos(uf, force=args.force_2026)
        except requests.HTTPError as e:
            print(f"  [warn] fotos {uf}: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
