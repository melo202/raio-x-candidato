"""Camada — desempenho parlamentar (Dados Abertos da Câmara dos Deputados).

Para candidatos de 2026 que são deputados federais na legislatura atual:
    - Projetos apresentados como autor (PL, PEC, PLP...), na legislatura
    - Quantos foram "Transformados em Norma Jurídica" (viraram lei) — na
      CARREIRA inteira, pois lei demora mais que um mandato pra maturar
    - Participação em votações nominais do Plenário, ano a ano
      (votos dados ÷ votações realizadas — proxy oficial de presença)
    - Gastos da cota parlamentar (CEAP), ano a ano

Identificação sem homonímia: o detalhe do deputado na API traz o CPF —
o cruzamento com o candidato 2026 é exato.

Uso: python pipeline/parlamentar.py --ufs GO
Depois: rode fichas.py de novo para injetar nas fichas.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import time
from datetime import date

import duckdb
import requests

import config

API = "https://dadosabertos.camara.leg.br/api/v2"
BULK_VOTOS = ("https://dadosabertos.camara.leg.br/arquivos/votacoesVotos/csv/"
              "votacoesVotos-{ano}.csv")
LEGISLATURA = 57          # 2023-2027
ANOS_MANDATO = [2023, 2024, 2025, 2026]
COD_LEI = 1140            # "Transformado em Norma Jurídica"
H = {"Accept": "application/json",
     "User-Agent": f"{config.PROJECT_NAME} (dados abertos)"}

NOTA = (
    "Fonte: Dados Abertos da Câmara dos Deputados. Participação em votações "
    "nominais do Plenário é um recorte objetivo de atuação — ausências podem "
    "ter justificativa legal (missão oficial, licença saúde). Número de "
    "projetos não mede qualidade. O total de propostas transformadas em lei "
    "conta AUTORIA E COAUTORIA (parlamentares costumam subscrever projetos em "
    "conjunto) e considera a carreira inteira, porque leis levam anos para "
    "maturar. A cota parlamentar (CEAP) é despesa regulamentada do exercício "
    "do mandato, não irregularidade."
)


def _get(url: str, params: dict | None = None) -> dict:
    for tentativa in range(3):
        try:
            r = requests.get(url, params=params, headers=H, timeout=60)
            r.raise_for_status()
            return r.json()
        except Exception:
            if tentativa == 2:
                raise
            time.sleep(2 * (tentativa + 1))
    return {}


def _count_paginado(url: str, params: dict) -> int:
    """Conta itens de um endpoint paginado sem baixar tudo (usa o link 'last')."""
    params = {**params, "itens": 100, "pagina": 1}
    d = _get(url, params)
    total = len(d.get("dados", []))
    last = next((l for l in d.get("links", []) if l["rel"] == "last"), None)
    if not last or total < 100:
        return total
    import urllib.parse as up
    q = up.parse_qs(up.urlparse(last["href"]).query)
    ultima = int(q.get("pagina", ["1"])[0])
    if ultima == 1:
        return total
    d_last = _get(url, {**params, "pagina": ultima})
    return (ultima - 1) * 100 + len(d_last.get("dados", []))


def deputados_da_uf(uf: str) -> list[dict]:
    d = _get(f"{API}/deputados", {"siglaUf": uf, "idLegislatura": LEGISLATURA,
                                  "itens": 100})
    out, vistos = [], set()
    for dep in d.get("dados", []):
        if dep["id"] in vistos:   # a API repete quem mudou de condição
            continue
        vistos.add(dep["id"])
        det = _get(f"{API}/deputados/{dep['id']}").get("dados", {})
        out.append({"id": dep["id"], "nome": dep["nome"],
                    "cpf": det.get("cpf"), "partido": dep.get("siglaPartido")})
        time.sleep(0.3)
    return out


def metricas_deputado(dep_id: int) -> dict:
    # projetos apresentados na legislatura atual (tipos principais)
    tipos = {}
    for sigla in ("PL", "PLP", "PEC", "PDL"):
        n = _count_paginado(f"{API}/proposicoes", {
            "idDeputadoAutor": dep_id, "siglaTipo": sigla,
            "dataApresentacaoInicio": "2023-02-01"})
        if n:
            tipos[sigla] = n
        time.sleep(0.2)
    # projetos de lei da carreira transformados em norma (PL/PLP/PEC apenas —
    # sem esse recorte a API soma requerimentos e coautorias em massa)
    leis = 0
    for sigla in ("PL", "PLP", "PEC"):
        leis += _count_paginado(f"{API}/proposicoes", {
            "idDeputadoAutor": dep_id, "siglaTipo": sigla,
            "codSituacao": COD_LEI})
        time.sleep(0.2)
    return {"projetos_legislatura": tipos,
            "projetos_total_legislatura": sum(tipos.values()),
            "normas_sancionadas_carreira": leis}


URL_CEAP = "https://www.camara.leg.br/cotas/Ano-{ano}.csv.zip"


def ceap_bulk(cpfs: set[str]) -> dict[str, dict]:
    """Cota parlamentar por CPF/ano, dos arquivos consolidados da Câmara
    (a API /deputados/{id}/despesas foi descontinuada — retorna vazio)."""
    import io as _io
    import zipfile as _zip
    out: dict[str, dict] = {c: {} for c in cpfs}
    for ano in ANOS_MANDATO:
        cache = config.RAW_DIR / f"ceap-Ano-{ano}.csv.zip"
        if not cache.exists():
            try:
                r = requests.get(URL_CEAP.format(ano=ano), headers=H, timeout=600)
                r.raise_for_status()
                cache.write_bytes(r.content)
            except Exception as e:
                print(f"  [warn] CEAP {ano}: {e}")
                continue
        with _zip.ZipFile(cache) as z:
            nome = next(n for n in z.namelist() if n.endswith(".csv"))
            texto = z.read(nome).decode("utf-8-sig", errors="replace")
        for row in csv.DictReader(_io.StringIO(texto), delimiter=";"):
            cpf = (row.get("cpf") or "").strip().strip('"')
            if cpf in out:
                try:
                    v = float((row.get("vlrLiquido") or "0").replace(",", "."))
                except ValueError:
                    continue
                out[cpf][str(ano)] = round(out[cpf].get(str(ano), 0) + v, 2)
        print(f"  CEAP {ano}: processado")
    return out


def participacao_votacoes(ids: set[int]) -> dict[int, dict]:
    """Baixa os CSVs anuais de votos nominais e computa participação por ano."""
    part: dict[int, dict] = {i: {} for i in ids}
    for ano in ANOS_MANDATO:
        cache = config.RAW_DIR / f"votacoesVotos-{ano}.csv"
        if cache.exists():
            texto = cache.read_text("utf-8-sig", errors="replace")
        else:
            url = BULK_VOTOS.format(ano=ano)
            try:
                r = requests.get(url, headers=H, timeout=600)
                r.raise_for_status()
            except Exception as e:
                print(f"  [warn] votos {ano}: {e}")
                continue
            cache.write_bytes(r.content)
            texto = r.content.decode("utf-8-sig", errors="replace")
        votacoes_todas, votou = set(), {i: set() for i in ids}
        for row in csv.DictReader(io.StringIO(texto), delimiter=";"):
            vid = row.get("idVotacao")
            votacoes_todas.add(vid)
            try:
                dep = int(row.get("deputado_id") or 0)
            except ValueError:
                continue
            if dep in ids:
                votou[dep].add(vid)
        total = len(votacoes_todas)
        if not total:
            continue
        for i in ids:
            part[i][str(ano)] = {
                "votou": len(votou[i]), "votacoes": total,
                "pct": round(100 * len(votou[i]) / total, 1)}
        print(f"  votações {ano}: {total} nominais no Plenário")
    return part


TOP_VOTACOES = 15
_RE_MATERIA = None  # compilado sob demanda (regex de matérias substantivas)


def votos_chave(ids: set[int]) -> tuple[list[dict], dict[int, dict]]:
    """As TOP_VOTACOES matérias de maior quórum votadas nominalmente no
    Plenário na legislatura, com o voto de cada deputado-alvo na votação
    decisiva de cada uma. Critério 100%% objetivo e declarado na ficha:
        1) votações nominais de Plenário com quórum >= 400;
        2) apenas matérias legislativas (PEC/PL/PLP/MP/PDL — descrições com
           "Proposta de Emenda à Constituição", "Projeto de Lei", "Medida
           Provisória", "Projeto de Decreto"), excluindo requerimentos;
        3) uma linha por PROPOSIÇÃO (destaques e turnos da mesma matéria não
           se repetem): vale a votação decisiva ("Aprovad…"/"Rejeitad…") de
           maior quórum;
        4) as TOP_VOTACOES de maior quórum entram na ficha."""
    import re as _re  # noqa — usado também no agrupamento por matéria
    re_materia = _re.compile(
        r"(Proposta de Emenda à Constituição|Projeto de Lei|"
        r"Medida Provisória|Projeto de Decreto)", _re.I)
    re_decisiva = _re.compile(r"^(Aprovad|Rejeitad)", _re.I)
    grupos: dict[str, dict] = {}
    for ano in ANOS_MANDATO:
        cache = config.RAW_DIR / f"votacoes-{ano}.csv"
        if not cache.exists():
            try:
                r = requests.get(("https://dadosabertos.camara.leg.br/arquivos/"
                                  f"votacoes/csv/votacoes-{ano}.csv"),
                                 headers=H, timeout=600)
                r.raise_for_status()
                cache.write_bytes(r.content)
            except Exception as e:
                print(f"  [warn] votacoes {ano}: {e}")
                continue
        for row in csv.DictReader(
                io.StringIO(cache.read_text("utf-8-sig", errors="replace")),
                delimiter=";"):
            if row.get("siglaOrgao") != "PLEN":
                continue
            try:
                sim = int(row.get("votosSim") or 0)
                nao = int(row.get("votosNao") or 0)
                quorum = sim + nao + int(row.get("votosOutros") or 0)
            except ValueError:
                continue
            desc = (row.get("descricao") or "").strip()
            abert = (row.get("ultimaAberturaVotacao_descricao") or "").strip()
            if quorum < 400 or not (re_materia.search(desc)
                                    or re_materia.search(abert)):
                continue
            # chave da MATÉRIA: número/ano extraído da descrição (turnos e
            # substitutivos da mesma PEC podem ter ids de proposição diferentes)
            m_mat = _re.search(
                r"(Emenda à Constituição|Lei Complementar|Lei|Medida Provisória|"
                r"Decreto Legislativo)[^,]{0,20}n[ºo°]?\s*([\d.]+),?\s*de\s*(\d{4})",
                desc + " " + abert, _re.I)
            prop = (f"{m_mat.group(1)}-{m_mat.group(2)}-{m_mat.group(3)}".upper()
                    if m_mat else row["id"].split("-")[0])
            v = {"id": row["id"], "ano": ano, "data": row.get("data"),
                 "quorum": quorum, "sim": sim, "nao": nao,
                 "decisiva": bool(re_decisiva.match(desc)),
                 "descricao": desc[:260]}
            atual = grupos.get(prop)
            melhor = (v["decisiva"], v["quorum"])
            if atual is None or melhor > (atual["decisiva"], atual["quorum"]):
                grupos[prop] = v
    top = sorted(grupos.values(), key=lambda v: -v["quorum"])[:TOP_VOTACOES]
    top_ids = {v["id"] for v in top}
    votos: dict[int, dict] = {i: {} for i in ids}
    for ano in sorted({v["ano"] for v in top}):
        cache = config.RAW_DIR / f"votacoesVotos-{ano}.csv"
        if not cache.exists():
            continue
        for row in csv.DictReader(
                io.StringIO(cache.read_text("utf-8-sig", errors="replace")),
                delimiter=";"):
            if row.get("idVotacao") not in top_ids:
                continue
            try:
                dep = int(row.get("deputado_id") or 0)
            except ValueError:
                continue
            if dep in ids:
                votos[dep][row["idVotacao"]] = row.get("voto") or ""
    for v in top:
        v.pop("decisiva", None)
    top.sort(key=lambda v: v["data"] or "", reverse=True)
    return top, votos
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ufs", nargs="*", default=None)
    ap.add_argument("--sem-votos", action="store_true",
                    help="pula o cálculo de participação (CSVs grandes)")
    args = ap.parse_args()

    con = duckdb.connect(str(config.DB_PATH), read_only=True)
    ano = config.ANO_ELEICAO
    for uf in (args.ufs or config.UFS_ALVO):
        cands = {r[0]: r[1] for r in con.execute(f"""
            SELECT NR_CPF_CANDIDATO, SQ_CANDIDATO FROM cand_{ano}
            WHERE SG_UF = ? AND NR_CPF_CANDIDATO IS NOT NULL
        """, [uf]).fetchall()}
        print(f"-- {uf}: consultando bancada federal atual")
        deps = deputados_da_uf(uf)
        alvo = [d for d in deps if d.get("cpf") in cands]
        print(f"  {len(deps)} deputados na legislatura · "
              f"{len(alvo)} são candidatos em 2026")

        part = {} if args.sem_votos else participacao_votacoes(
            {d["id"] for d in alvo})
        top_vot, votos_dep = ([], {}) if args.sem_votos else votos_chave(
            {d["id"] for d in alvo})
        ceap = ceap_bulk({d["cpf"] for d in alvo})

        out_dir = config.OUT_DATA / "parlamentar" / uf
        out_dir.mkdir(parents=True, exist_ok=True)
        for antigo in out_dir.glob("*.json"):   # quem saiu da disputa sai da pasta
            antigo.unlink()
        for d in alvo:
            print(f"  [api ] {d['nome']}")
            m = metricas_deputado(d["id"])
            ceap_dep = ceap.get(d["cpf"], {})
            m.update({
                "ceap_por_ano": ceap_dep,
                "ceap_total": round(sum(ceap_dep.values()), 2),
                "dep_id": d["id"], "nome_camara": d["nome"],
                "legislatura": LEGISLATURA,
                "participacao_votacoes": part.get(d["id"], {}),
                "votos_chave": {
                    "criterio": (f"as {TOP_VOTACOES} matérias legislativas "
                                 "(PEC, PL, PLP, MP e PDL) com maior quórum "
                                 "(mínimo de 400 votantes) em votação nominal "
                                 "de Plenário na legislatura — uma votação "
                                 "decisiva (aprovação/rejeição) por matéria, "
                                 "as mesmas para todos os deputados; critério "
                                 "objetivo, sem seleção editorial"),
                    "itens": [{**v, "voto":
                               votos_dep.get(d["id"], {}).get(v["id"])
                               or ("não estava em exercício no período"
                                   if not part.get(d["id"], {}).get(str(v["ano"]), {}).get("votou")
                                   else "não registrou voto")} for v in top_vot],
                },
                "fonte_url": f"https://www.camara.leg.br/deputados/{d['id']}",
                "nota": NOTA,
                "gerado_em": date.today().isoformat(),
            })
            sq = cands[d["cpf"]]
            (out_dir / f"{sq}.json").write_text(
                json.dumps(m, ensure_ascii=False), "utf-8")
        print("  → rode fichas.py de novo para injetar nas fichas")
    con.close()


if __name__ == "__main__":
    main()
