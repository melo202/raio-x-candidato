"""Camada — ALEGO: atuação na Assembleia Legislativa de Goiás.

Para candidatos que são (ou foram) deputados estaduais em Goiás, mostra o que
o sistema legislativo oficial da ALEGO (SPL — alegodigital.al.go.leg.br/spl)
registra sobre eles: proposições apresentadas por tipo, leis de sua autoria e
frequência em Plenário ano a ano da legislatura atual (presenças, faltas
justificadas e não justificadas).

COLETA: o servidor do SPL bloqueia acesso de datacenter (TLS legado + filtro),
então a coleta é feita via navegador (sessão assistida — ver
data/raw/alego/README). O módulo consome o dump JSON mais recente em
data/raw/alego/spl_parlamentares_*.json. Re-coletar ~1×/mês na campanha.

IDENTIFICAÇÃO: o perfil do SPL publica o NOME CIVIL COMPLETO do parlamentar —
o cruzamento com o candidato exige nome civil idêntico (normalizado). Sem
CPF na fonte; homonímia de nome completo é improvável mas o critério é
declarado na ficha.

Uso: python pipeline/alego.py --ufs GO
Depois: rode fichas.py de novo (ou injetar.py) para injetar nas fichas.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import unicodedata
from datetime import date

import config

FONTE = "ALEGO — Sistema de Proposições Legislativas (SPL)"
FONTE_URL = "https://alegodigital.al.go.leg.br/spl/parlamentares.aspx"

DISCLAIMER = (
    "Números registrados pelo sistema legislativo oficial da ALEGO (SPL). "
    "Proposições e leis consideram o que o sistema registra para o "
    "parlamentar em todas as legislaturas que ele exerceu; a frequência em "
    "Plenário refere-se à legislatura atual (2023–2027). Quantidade de "
    "projetos não mede qualidade, e ausências podem ter justificativa legal "
    "(licença, missão oficial) — as faltas justificadas aparecem separadas "
    "das não justificadas por isso. Requerimentos e comunicados são atos "
    "ordinários do mandato. Confira o perfil completo na fonte."
)

# tipos exibidos com destaque (o resto é agregado em "outros atos")
TIPOS_PRINCIPAIS = [
    "Projeto de Lei Ordinária",
    "Projeto de Lei Complementar",
    "Proposta de Emenda Constitucional",
    "Projeto de Lei Ordinária - Título de Cidadão",
    "Projeto de Resolução",
    "Requerimento",
]


_PARTICULAS = {"DE", "DA", "DO", "DAS", "DOS", "E"}

# grafias divergentes VERIFICADAS manualmente entre SPL e TSE (mesma pessoa)
# (chaves e valores em forma normalizada SEM partículas)
_ALIASES = {
    "BRUNO REGIANY PEIXOTO PIMENTA": "BRUNNO REGIANY PEIXOTO PIMENTA",
    "ANDERSON TEODORO CUNHA": "ANDERSON TEODORO CUNHA DOURADO",
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\s+", " ", re.sub(r"[^A-Za-z ]", " ", s)).strip().upper()
    return " ".join(w for w in s.split() if w not in _PARTICULAS)


def _casar(civil_norm: str, cands: dict[str, str]) -> str | None:
    """Match seguro: exato → alias verificado → subconjunto de nomes
    (≥3 nomes em comum, mesmo primeiro nome, match ÚNICO)."""
    if civil_norm in cands:
        return cands[civil_norm]
    alias = _norm(_ALIASES.get(civil_norm, ""))
    if alias and alias in cands:
        return cands[alias]
    return None   # sem match automático por semelhança: divergência de grafia
                  # só entra via _ALIASES, após verificação manual (auditoria 2)


def carregar_dump() -> tuple[dict, str]:
    pasta = config.RAW_DIR / "alego"
    arquivos = sorted(pasta.glob("spl_parlamentares_*.json"))
    if not arquivos:
        raise SystemExit("alego.py: nenhum dump em data/raw/alego/ — "
                         "faça a coleta assistida (ver docstring)")
    path = arquivos[-1]
    data_coleta = re.search(r"(\d{8})", path.name)
    dc = data_coleta.group(1) if data_coleta else ""
    dc_fmt = f"{dc[6:8]}/{dc[4:6]}/{dc[0:4]}" if len(dc) == 8 else ""
    return json.loads(path.read_text("utf-8")), dc_fmt


def carregar_candidatos(uf: str) -> dict[str, str]:
    pasta = config.RAW_DIR / f"consulta_cand_{config.ANO_ELEICAO}"
    path = pasta / f"consulta_cand_{config.ANO_ELEICAO}_{uf}.csv"
    raw = path.read_bytes()
    try:
        texto = raw.decode("utf-8")
    except UnicodeDecodeError:
        texto = raw.decode("latin-1")
    return {_norm(r["NM_CANDIDATO"]): r["SQ_CANDIDATO"]
            for r in csv.DictReader(io.StringIO(texto), delimiter=";")}


def gerar_uf(uf: str) -> int:
    dump, data_coleta = carregar_dump()
    cands = carregar_candidatos(uf)
    out_dir = config.OUT_DATA / "alego" / uf
    out_dir.mkdir(parents=True, exist_ok=True)
    for antigo in out_dir.glob("*.json"):
        antigo.unlink()

    n = 0
    for spl_id, d in dump.items():
        sq = _casar(_norm(d.get("civil")), cands)
        if not sq:
            continue
        prop = d.get("prop", {})
        principais = [{"tipo": t, "n": prop[t]} for t in TIPOS_PRINCIPAIS
                      if prop.get(t)]
        outros = sum(v for k, v in prop.items() if k not in TIPOS_PRINCIPAIS)
        freq = d.get("freq", {})
        anos = sorted({a for st in freq.values() for a in st})
        freq_anos = []
        for a in anos:
            pres = freq.get("Presente", {}).get(a, 0)
            fj = freq.get("Falta Justificada", {}).get(a, 0)
            fnj = freq.get("Falta não Justificada", {}).get(a, 0)
            base = pres + fj + fnj
            freq_anos.append({
                "ano": a, "presente": pres, "falta_justificada": fj,
                "falta_nao_justificada": fnj,
                "pct_presenca": round(100 * pres / base, 1) if base else None,
            })
        legs = sorted(d.get("legislaturas", []), key=lambda x: int(x))
        (out_dir / f"{sq}.json").write_text(json.dumps({
            "nome_alego": d.get("urna_alego"),
            "spl_id": spl_id,
            "perfil_url": f"https://alegodigital.al.go.leg.br/spl/parlamentar.aspx?id={spl_id}",
            "legislaturas": legs,
            "proposicoes_principais": principais,
            "proposicoes_outros_atos": outros,
            "leis_de_sua_autoria": [{"tipo": k, "n": v}
                                    for k, v in d.get("leis", {}).items()],
            "frequencia_plenario": freq_anos,
            "criterio": "nome civil completo, normalizado sem partículas "
                        "(de/da/dos); divergências de grafia só entram após "
                        "verificação manual documentada no código",
            "coletado_em": data_coleta,
            "fonte": FONTE, "fonte_url": FONTE_URL,
            "disclaimer": DISCLAIMER,
            "gerado_em": date.today().isoformat(),
        }, ensure_ascii=False), "utf-8")
        n += 1
    print(f"  {uf}: atuação na ALEGO gerada para {n} candidato(s) "
          f"(dump de {data_coleta} com {len(dump)} parlamentares)")
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ufs", nargs="*", default=None)
    args = ap.parse_args()
    print("-- ALEGO (SPL, coleta assistida)")
    for uf in (args.ufs or config.UFS_ALVO):
        if uf != "GO":
            continue
        gerar_uf(uf)
    print("OK — rode fichas.py (ou injetar.py) para injetar nas fichas")


if __name__ == "__main__":
    main()
