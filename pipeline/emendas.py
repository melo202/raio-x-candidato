"""Camada — EMENDAS PARLAMENTARES: para onde o deputado mandou o dinheiro.

Para candidatos que são deputados federais na legislatura atual, mostra as
emendas de sua autoria no orçamento federal — total por ano do mandato e os
municípios mais beneficiados, com valores empenhados e pagos.

Fonte: Portal da Transparência (CGU) — base "Emendas Parlamentares"
(portaldatransparencia.gov.br/download-de-dados/emendas-parlamentares).

Identificação: o autor da emenda é registrado pelo NOME PARLAMENTAR — o
cruzamento usa o nome parlamentar obtido dos Dados Abertos da Câmara para o
deputado já identificado por CPF (parlamentar.py). O nome parlamentar é o
identificador orçamentário oficial do autor; ainda assim, a ficha declara o
critério.

Princípio do projeto: emenda parlamentar é instrumento LEGAL do orçamento —
a camada é transparência ("quanto e para onde"), não acusação. O disclaimer
é fixo.

Uso: python pipeline/emendas.py --ufs GO
Depois: rode fichas.py de novo (ou injetar.py) para injetar nas fichas.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import unicodedata
import zipfile
from datetime import date

import requests

import config

URL = "https://portaldatransparencia.gov.br/download-de-dados/emendas-parlamentares/UNICO"
URL_PAGINA = "https://portaldatransparencia.gov.br/emendas"
ANOS_MANDATO = [2023, 2024, 2025, 2026]   # legislatura 57
TOP_MUNICIPIOS = 10

DISCLAIMER = (
    "Emendas parlamentares são instrumento legal do orçamento federal: todo "
    "deputado tem direito a indicá-las, e parte delas é de execução "
    "obrigatória. Os valores são os registrados pelo Portal da Transparência "
    "(CGU) para o autor, nos anos da legislatura atual; 'empenhado' é o valor "
    "reservado e 'pago' o efetivamente desembolsado até a data da consulta — "
    "execução orçamentária leva anos. Para onde o recurso vai é decisão "
    "documentada e pública; esta seção é transparência, não juízo."
)


_PARTICULAS = {"DE", "DA", "DO", "DAS", "DOS", "E"}


def _norm(s: str) -> str:
    """Normaliza e REMOVE partículas: a base orçamentária grafa 'SAMUEL SANTOS'
    para o deputado 'Samuel dos Santos' (caso real, GO/leg. 57)."""
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\s+", " ", re.sub(r"[^A-Za-z ]", " ", s)).strip().upper()
    return " ".join(w for w in s.split() if w not in _PARTICULAS)


def _num(v: str) -> float:
    try:
        return float(str(v).replace(".", "").replace(",", "."))
    except ValueError:
        return 0.0


def baixar() -> "config.Path":
    dest = config.RAW_DIR / "emendas_parlamentares.zip"
    if not dest.exists():
        print("  [get ] base de emendas (Portal da Transparência)")
        r = requests.get(URL, timeout=1800, allow_redirects=True,
                         headers={"User-Agent": "Mozilla/5.0 (dados abertos; uso civico)"})
        r.raise_for_status()
        dest.write_bytes(r.content)
    return dest


def carregar_alvos(uf: str) -> dict[str, dict]:
    """nome parlamentar normalizado → {sq, nome_camara} (dos sidecars do
    parlamentar.py, que já fizeram o cruzamento por CPF)."""
    alvos = {}
    pasta = config.OUT_DATA / "parlamentar" / uf
    for p in sorted(pasta.glob("*.json")):
        d = json.loads(p.read_text("utf-8"))
        nome = d.get("nome_camara")
        if nome:
            alvos[_norm(nome)] = {"sq": p.stem, "nome_camara": nome}
    return alvos


def gerar_uf(uf: str, zip_path) -> int:
    alvos = carregar_alvos(uf)
    if not alvos:
        print(f"  [warn] {uf}: nenhum sidecar em parlamentar/ — rode parlamentar.py antes")
        return 0
    dados: dict[str, dict] = {}   # sq → agregado
    _codigos_vistos: dict[str, str] = {}
    with zipfile.ZipFile(zip_path) as z:
        with z.open("EmendasParlamentares.csv") as f:
            for row in csv.DictReader(
                    io.TextIOWrapper(f, encoding="latin-1", newline=""),
                    delimiter=";"):
                try:
                    ano = int(row["Ano da Emenda"])
                except (ValueError, KeyError):
                    continue
                if ano not in ANOS_MANDATO:
                    continue
                autor = _norm(row.get("Nome do Autor da Emenda"))
                alvo = alvos.get(autor)
                if not alvo:
                    continue
                # guarda de homonímia: 1 nome-alvo deve mapear 1 código de autor
                cod = (row.get("Código do Autor da Emenda") or "").strip()
                if cod and cod not in ("S/I",):
                    visto = _codigos_vistos.setdefault(autor, cod)
                    if visto != cod:
                        print(f"  [ERRO] nome '{autor}' casa 2 códigos de autor "
                              f"({visto} e {cod}) — registros do 2º ignorados")
                        continue
                emp = _num(row.get("Valor Empenhado"))
                # "pago" = pago no exercício + restos a pagar pagos depois
                # (emenda é majoritariamente paga em RP nos anos seguintes)
                pag = (_num(row.get("Valor Pago"))
                       + _num(row.get("Valor Restos A Pagar Pagos")))
                d = dados.setdefault(alvo["sq"], {
                    "por_ano": {}, "municipios": {}, "funcoes": {}, "n": 0})
                d["n"] += 1
                a = d["por_ano"].setdefault(str(ano), {"empenhado": 0.0, "pago": 0.0})
                a["empenhado"] += emp
                a["pago"] += pag
                mun = (row.get("Município") or "").strip().title()
                loc = (row.get("Localidade de aplicação do recurso") or "").strip().title()
                chave_mun = mun or loc or "Sem Localidade Definida"
                uf_mun = (row.get("UF") or "").strip().title()
                m = d["municipios"].setdefault(chave_mun, {"uf": uf_mun, "empenhado": 0.0})
                m["empenhado"] += emp
                fun = (row.get("Nome Função") or "Outros").strip().title()
                d["funcoes"][fun] = d["funcoes"].get(fun, 0.0) + emp

    out_dir = config.OUT_DATA / "emendas" / uf
    out_dir.mkdir(parents=True, exist_ok=True)
    for antigo in out_dir.glob("*.json"):
        antigo.unlink()
    for sq, d in dados.items():
        top_mun = sorted(d["municipios"].items(),
                         key=lambda kv: -kv[1]["empenhado"])[:TOP_MUNICIPIOS]
        top_fun = sorted(d["funcoes"].items(), key=lambda kv: -kv[1])[:6]
        (out_dir / f"{sq}.json").write_text(json.dumps({
            "anos_cobertos": ANOS_MANDATO,
            "n_registros": d["n"],
            "total_empenhado": round(sum(a["empenhado"] for a in d["por_ano"].values()), 2),
            "total_pago": round(sum(a["pago"] for a in d["por_ano"].values()), 2),
            "por_ano": {a: {"empenhado": round(v["empenhado"], 2),
                            "pago": round(v["pago"], 2)}
                        for a, v in sorted(d["por_ano"].items())},
            "top_municipios": [{"municipio": m, "uf": v["uf"],
                                "empenhado": round(v["empenhado"], 2)}
                               for m, v in top_mun],
            "top_funcoes": [{"funcao": f_, "empenhado": round(v, 2)}
                            for f_, v in top_fun],
            "criterio": "autoria pelo nome parlamentar (identificador orçamentário oficial)",
            "fonte": "Portal da Transparência (CGU) — emendas parlamentares",
            "fonte_url": URL_PAGINA,
            "disclaimer": DISCLAIMER,
            "gerado_em": date.today().isoformat(),
        }, ensure_ascii=False), "utf-8")
    print(f"  {uf}: emendas geradas para {len(dados)} deputado(s) federais")
    return len(dados)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ufs", nargs="*", default=None)
    ap.add_argument("--force", action="store_true", help="re-baixa a base")
    args = ap.parse_args()
    print("-- emendas parlamentares (Portal da Transparência)")
    if args.force:
        (config.RAW_DIR / "emendas_parlamentares.zip").unlink(missing_ok=True)
    zip_path = baixar()
    for uf in (args.ufs or config.UFS_ALVO):
        gerar_uf(uf, zip_path)
    print("OK — rode fichas.py (ou injetar.py) para injetar nas fichas")


if __name__ == "__main__":
    main()
