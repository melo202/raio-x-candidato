"""Radar de imprensa — menções ao candidato em veículos jornalísticos estabelecidos.

Salvaguardas contra fake news e homonímia (princípios do projeto):
    1. WHITELIST: só entram links de veículos da lista abaixo (edite com critério
       público — a lista aparece na página de Metodologia).
    2. LINK, NÃO CONTEÚDO: o radar publica título + veículo + data + link.
       Nada de resumo, recorte ou juízo — quem fala é o veículo, na fonte.
    3. BUSCA RESTRITIVA: nome de urna entre aspas + nome do estado, para reduzir
       homônimos. Ainda assim a ficha exibe aviso de possível homonímia.
    4. ESCOPO: por padrão só majoritários (governador/senador), onde a cobertura
       é densa e o risco de homônimo é menor. --todos expande por sua conta.

Fonte dos links: Google News RSS (agregador; os links apontam pro veículo).

Uso:
    python pipeline/radar_noticias.py --ufs GO
    python pipeline/radar_noticias.py --ufs GO --todos --max 5
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import date

import requests

import config

# Veículos aceitos (domínio → nome). Critério: redações profissionais com
# responsabilidade editorial identificável, nacionais + locais de GO.
WHITELIST = {
    "opopular.com.br": "O Popular",
    "maisgoias.com.br": "Mais Goiás",
    "jornalopcao.com.br": "Jornal Opção",
    "aredacao.com.br": "A Redação",
    "diariodegoias.com.br": "Diário de Goiás",
    "g1.globo.com": "g1",
    "oglobo.globo.com": "O Globo",
    "folha.uol.com.br": "Folha de S.Paulo",
    "www1.folha.uol.com.br": "Folha de S.Paulo",
    "estadao.com.br": "Estadão",
    "uol.com.br": "UOL",
    "noticias.uol.com.br": "UOL",
    "cnnbrasil.com.br": "CNN Brasil",
    "metropoles.com": "Metrópoles",
    "poder360.com.br": "Poder360",
    "agenciabrasil.ebc.com.br": "Agência Brasil",
    "bbc.com": "BBC News Brasil",
    "gazetadopovo.com.br": "Gazeta do Povo",
    "correiobraziliense.com.br": "Correio Braziliense",
    "valor.globo.com": "Valor Econômico",
    "gauchazh.clicrbs.com.br": "GZH",
    "nexojornal.com.br": "Nexo",
    "apublica.org": "Agência Pública",
    "piaui.folha.uol.com.br": "piauí",
}

UF_NOME = {
    "AC": "Acre", "AL": "Alagoas", "AM": "Amazonas", "AP": "Amapá", "BA": "Bahia",
    "CE": "Ceará", "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás",
    "MA": "Maranhão", "MG": "Minas Gerais", "MS": "Mato Grosso do Sul",
    "MT": "Mato Grosso", "PA": "Pará", "PB": "Paraíba", "PE": "Pernambuco",
    "PI": "Piauí", "PR": "Paraná", "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte",
    "RO": "Rondônia", "RR": "Roraima", "RS": "Rio Grande do Sul",
    "SC": "Santa Catarina", "SE": "Sergipe", "SP": "São Paulo", "TO": "Tocantins",
}

DISCLAIMER = (
    "Menções em veículos jornalísticos estabelecidos (lista aberta na Metodologia), "
    "coletadas automaticamente por nome de urna. O conteúdo é dos veículos — o "
    "Raio-X não produz, resume nem verifica as matérias, e pode haver homônimos. "
    "Leia sempre na fonte."
)


def _dominio(url: str) -> str:
    try:
        host = urllib.parse.urlparse(url).netloc.lower()
        return host.removeprefix("www.")
    except Exception:
        return ""


def _veiculo(url: str, source_texto: str) -> str | None:
    d = _dominio(url)
    for dom, nome in WHITELIST.items():
        chave = dom.removeprefix("www.")
        if d == chave or d.endswith("." + chave):
            return nome
    # o RSS do Google News usa link intermediário; caia pro <source>
    if source_texto:
        for nome in WHITELIST.values():
            if source_texto.strip().lower() == nome.lower():
                return nome
    return None


def buscar(nome_urna: str, uf: str, max_itens: int = 8) -> list[dict]:
    q = urllib.parse.quote(f'"{nome_urna}" {UF_NOME.get(uf, uf)}')
    url = (f"https://news.google.com/rss/search?q={q}"
           "&hl=pt-BR&gl=BR&ceid=BR:pt-419")
    r = requests.get(url, timeout=30,
                     headers={"User-Agent": f"{config.PROJECT_NAME} radar"})
    r.raise_for_status()
    root = ET.fromstring(r.content)
    itens = []
    for item in root.iter("item"):
        titulo = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        data_pub = (item.findtext("pubDate") or "").strip()
        source = item.find("source")
        source_txt = (source.text or "").strip() if source is not None else ""
        veiculo = _veiculo(link, source_txt)
        if not veiculo or not titulo:
            continue
        # o título do Google News costuma terminar com " - Veículo": limpa
        if titulo.lower().endswith(" - " + source_txt.lower()):
            titulo = titulo[: -(len(source_txt) + 3)].strip()
        itens.append({"titulo": titulo, "veiculo": veiculo,
                      "data": data_pub, "url": link})
        if len(itens) >= max_itens:
            break
    return itens


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ufs", nargs="*", default=None)
    ap.add_argument("--todos", action="store_true",
                    help="todos os candidatos (padrão: só governador/senador)")
    ap.add_argument("--max", type=int, default=8)
    args = ap.parse_args()

    for uf in (args.ufs or config.UFS_ALVO):
        idx = json.loads((config.OUT_DATA / uf / "index.json").read_text("utf-8"))
        cands = idx["candidatos"]
        if not args.todos:
            cands = [c for c in cands
                     if c["cg"].upper() in ("GOVERNADOR", "SENADOR")]
        out_dir = config.OUT_DATA / "noticias" / uf
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"-- {uf}: radar para {len(cands)} candidatos")
        for c in cands:
            try:
                itens = buscar(c["nu"] or c["nm"], uf, args.max)
            except Exception as e:
                print(f"  [warn] {c['nu']}: {e}")
                continue
            (out_dir / f"{c['sq']}.json").write_text(json.dumps({
                "itens": itens,
                "consulta": f'"{c["nu"] or c["nm"]}" {UF_NOME.get(uf, uf)}',
                "disclaimer": DISCLAIMER,
                "coletado_em": date.today().isoformat(),
            }, ensure_ascii=False), "utf-8")
            print(f"  {c['nu']}: {len(itens)} menções")
            time.sleep(1.5)  # rate limit educado
        print("  → rode fichas.py de novo para injetar nas fichas")


if __name__ == "__main__":
    main()
