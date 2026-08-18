"""Gera as fichas JSON (1 por candidato) e o índice de busca de cada UF.

Saída (servida pelo GitHub Pages):
    docs/data/{UF}/index.json       — índice compacto p/ busca client-side
    docs/data/{UF}/{SQ}.json        — ficha completa do candidato
    docs/data/{UF}/fotos/{SQ}.jpg   — foto oficial (divulgação TSE)
    docs/data/ufs.json              — UFs publicadas + metadados

Uso: python pipeline/fichas.py [--ufs GO SP ...]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import date, datetime

import duckdb

import config
from tcu import CruzadorTCU


# ── LGPD: as descrições de bens do TSE às vezes trazem CPF de terceiros
# (co-titular de conta), agência/conta bancária e placa de veículo em texto
# livre. Publicar isso verbatim viola a minimização (LGPD art. 6º, III) e
# expõe vetor de fraude. Mascaramos ANTES de publicar. ──────────────────
_RE_CPF_DESC = re.compile(r"\b\d{3}[.\s]?\d{3}[.\s]?\d{3}\s?[-–]\s?\d{2}\b")
_RE_CPF_NU = re.compile(r"\b\d{11}\b")
_RE_PLACA = re.compile(r"\b[A-Z]{3}[- ]?\d(?:[A-Z]\d{2}|\d{3})\b")
_RE_CONTA = re.compile(
    r"(?i)\b(AG(?:[EÊ]NCIA)?|CONTA(?:\s+CORRENTE)?|C/?C|POUPAN[CÇ]A|OPERA[CÇ][AÃ]O|BANCO)"
    r"(\s*(?:N[ºO°.]?|:|\.|-)?\s*)([\d.\-/xX*]{2,})")


def _anonimizar_descricao(s: str | None) -> str | None:
    if not s:
        return s
    s = _RE_CPF_DESC.sub("***.***.***-**", s)
    s = _RE_CPF_NU.sub("***********", s)
    s = _RE_PLACA.sub("***-****", s)
    s = _RE_CONTA.sub(lambda m: m.group(1) + m.group(2) + "\u2022\u2022\u2022", s)
    return s


def _mask_cpf(cpf: str) -> str | None:
    cpf = "".join(ch for ch in str(cpf or "") if ch.isdigit())
    if len(cpf) != 11:
        return None
    return f"***.{cpf[3:6]}.{cpf[6:9]}-**"


def _idade(dt_nasc: str) -> int | None:
    try:
        d = datetime.strptime(dt_nasc.strip(), "%d/%m/%Y").date()
        hoje = date.today()
        return hoje.year - d.year - ((hoje.month, hoje.day) < (d.month, d.day))
    except Exception:
        return None


def _limpo(v) -> str | None:
    """Normaliza os pseudo-nulos do TSE (#NULO#, #NE, -1, etc.)."""
    if v is None:
        return None
    s = str(v).strip()
    if s in ("", "#NULO#", "#NULO", "#NE#", "-1", "-3"):
        return None
    return s


def _situacao(ds: str | None) -> dict:
    ds = (ds or "").strip()
    label = config.SITUACAO_LABEL.get(ds.upper(), ds.title() if ds else "Aguardando julgamento")
    return {"ds": ds or None, "label": label}


def _resultado_label(ds: str | None) -> str | None:
    """Rótulo amigável do resultado da eleição (DS_SIT_TOT_TURNO)."""
    s = (ds or "").strip().upper()
    if not s or s in ("#NULO#", "#NULO", "#NE", "#NE#", "-1", "-3"):
        return None
    mapa = {
        "ELEITO": "Eleito",
        "ELEITO POR QP": "Eleito (quociente partidário)",
        "ELEITO POR MÉDIA": "Eleito (média)",
        "NÃO ELEITO": "Não eleito",
        "SUPLENTE": "Suplente",
        "2º TURNO": "Foi ao 2º turno",
        "CONCORRENDO": "Concorrendo",
        "RENÚNCIA": "Renunciou",
        "CASSADO": "Cassado",
        "REGISTRO NEGADO ANTES DA ELEIÇÃO": "Registro negado",
        "REGISTRO NEGADO APÓS A ELEIÇÃO": "Registro negado",
        "SUBSTITUÍDO": "Substituído",
        "INDEFERIDO COM RECURSO": "Indeferido com recurso",
    }
    return mapa.get(s, s.title())


# Renomeações e fusões partidárias (2014→2026): mesma linhagem ≠ troca de partido
_LINHAGEM_PARTIDO = {
    "PMDB": "MDB",
    "PFL": "UNIÃO", "DEM": "UNIÃO", "PSL": "UNIÃO",     # fusão DEM+PSL (2022)
    "PR": "PL",
    "PRB": "REPUBLICANOS",
    "PPS": "CIDADANIA",
    "PTN": "PODEMOS", "PSC": "PODEMOS",                  # incorporação (2023)
    "PP": "PROGRESSISTAS",
    "PSDC": "DC",
    "PEN": "PATRIOTA", "PATRIOTA": "PRD", "PTB": "PRD",  # fusão (2023)
    "PROS": "SOLIDARIEDADE",                             # incorporação (2022)
    "PPL": "PC DO B",
    "PTC": "AGIR",
    "PMN": "MOBILIZA",
    "PHS": "PODE",
}


def _linhagem(sigla: str | None) -> str | None:
    s = (sigla or "").strip().upper()
    return _LINHAGEM_PARTIDO.get(s, s) or None


_REDES_DOMINIOS = [
    ("instagram.com", "Instagram"), ("facebook.com", "Facebook"),
    ("fb.com", "Facebook"), ("twitter.com", "X (Twitter)"), ("x.com", "X (Twitter)"),
    ("tiktok.com", "TikTok"), ("youtube.com", "YouTube"), ("youtu.be", "YouTube"),
    ("kwai", "Kwai"), ("threads.net", "Threads"), ("linkedin.com", "LinkedIn"),
    ("t.me", "Telegram"), ("telegram", "Telegram"), ("wa.me", "WhatsApp"),
    ("whatsapp.com", "WhatsApp"), ("spotify.com", "Spotify"),
]


def _classificar_rede(url: str) -> dict | None:
    u = (url or "").strip()
    if not u:
        return None
    if u.lower().startswith("www."):
        u = "https://" + u
    if not u.lower().startswith("http"):
        return None
    low = u.lower()
    plataforma = next((nome for dom, nome in _REDES_DOMINIOS if dom in low), "Site")
    return {"plataforma": plataforma, "url": u}


def _variacoes(serie: list[dict]) -> list[dict]:
    """Variação % entre anos consecutivos DECLARADOS da série."""
    decl = [p for p in serie if p["declarou"] and p["total"] is not None]
    out = []
    for a, b in zip(decl, decl[1:]):
        if a["total"] and a["total"] > 0:
            out.append({
                "de": a["ano"], "para": b["ano"],
                "pct": round(100.0 * (b["total"] - a["total"]) / a["total"], 1),
            })
        else:
            out.append({"de": a["ano"], "para": b["ano"], "pct": None})
    return out


def gerar_uf(con: duckdb.DuckDBPyConnection, uf: str, tcu: CruzadorTCU) -> dict:
    ano = config.ANO_ELEICAO
    out_dir = config.OUT_DATA / uf
    fotos_out = out_dir / "fotos"
    out_dir.mkdir(parents=True, exist_ok=True)
    fotos_out.mkdir(exist_ok=True)

    cands = con.execute(f"""
        SELECT * FROM cand_{ano} WHERE SG_UF = ? ORDER BY NM_URNA_CANDIDATO
    """, [uf]).fetch_df().to_dict("records")

    # bens detalhados do ano corrente, por SQ
    bens = {}
    for r in con.execute(f"""
        SELECT b.SQ_CANDIDATO sq, b.DS_TIPO_BEM_CANDIDATO tipo,
               b.DS_BEM_CANDIDATO descricao,
               TRY_CAST(REPLACE(b.VR_BEM_CANDIDATO, ',', '.') AS DOUBLE) valor
        FROM bem_{ano} b
        JOIN cand_{ano} c ON c.SQ_CANDIDATO = b.SQ_CANDIDATO
        WHERE c.SG_UF = ?
        ORDER BY valor DESC
    """, [uf]).fetchall():
        bens.setdefault(r[0], []).append(
            {"tipo": r[1], "descricao": _anonimizar_descricao(r[2]),
             "valor": round(r[3], 2) if r[3] is not None else None})

    # série patrimonial nacional por CPF (o candidato pode ter concorrido em outra UF)
    series = {}
    for r in con.execute(f"""
        SELECT s.cpf, s.ano, s.uf, s.cargo, s.partido, s.total, s.n_bens, s.declarou,
               s.resultado, s.ue, s.municipal
        FROM serie_cpf s
        WHERE s.cpf IN (SELECT NR_CPF_CANDIDATO FROM cand_{ano} WHERE SG_UF = ?)
        ORDER BY s.ano
    """, [uf]).fetchall():
        series.setdefault(r[0], []).append({
            "ano": int(r[1]), "uf": r[2], "cargo": (r[3] or "").title(),
            "partido": r[4], "total": round(r[5], 2) if r[5] is not None else None,
            "n_bens": int(r[6] or 0), "declarou": bool(r[7]),
            "resultado": _resultado_label(r[8]),
            "municipio": (r[9] or "").title() if r[10] else None,
        })

    # doações eleitorais que o candidato FEZ (cruzamento por CPF do doador)
    doacoes = {}
    doacoes_disp = True
    try:
        for r in con.execute(f"""
            SELECT d.cpf, d.ano, d.beneficiado, d.partido, d.cargo, d.uf,
                   d.municipio, d.valor, d.origem, d.propria_campanha, d.data
            FROM doacoes_feitas d
            WHERE d.cpf IN (SELECT NR_CPF_CANDIDATO FROM cand_{ano} WHERE SG_UF = ?)
            ORDER BY d.ano DESC, d.valor DESC
        """, [uf]).fetchall():
            doacoes.setdefault(r[0], []).append({
                "ano": int(r[1]), "beneficiado": (r[2] or "").title(),
                "partido": r[3], "cargo": (r[4] or "").title(), "uf": r[5],
                "municipio": (r[6] or "").title() or None,
                "valor": round(r[7], 2), "origem": r[8],
                "propria": bool(r[9]), "data": r[10],
            })
    except duckdb.CatalogException:
        doacoes_disp = False  # tabela ainda não materializada (rode doacoes_feitas.py)

    # sanções em cadastros oficiais (CEIS/CNEP/CEAF — pessoa física)
    sancoes = {}
    sancoes_disp = True
    try:
        for r in con.execute("""
            SELECT cpf, cadastro, categoria, processo, orgao, uf_orgao,
                   inicio, fim, publicacao, criterio
            FROM sancoes_pf
        """).fetchall():
            sancoes.setdefault(r[0], []).append({
                "cadastro": r[1].upper(), "categoria": r[2], "processo": r[3],
                "orgao": r[4], "uf_orgao": r[5], "inicio": r[6], "fim": r[7],
                "publicacao": r[8], "criterio": r[9],
            })
    except duckdb.CatalogException:
        sancoes_disp = False  # rode sancoes.py

    # redes sociais declaradas ao TSE (ano corrente)
    redes = {}
    for r in con.execute(f"""
        SELECT rs.SQ_CANDIDATO, rs.url FROM rede_social rs
        JOIN cand_{ano} c ON c.SQ_CANDIDATO = rs.SQ_CANDIDATO
        WHERE c.SG_UF = ?
    """, [uf]).fetchall():
        item = _classificar_rede(r[1])
        if item:
            redes.setdefault(str(r[0]), []).append(item)

    fotos_raw = config.RAW_DIR / f"fotos_{ano}_{uf}"
    dt_geracao = _limpo(cands[0].get("DT_GERACAO")) if cands else None

    indice = []
    for c in cands:
        sq = str(c["SQ_CANDIDATO"])
        cpf = str(c.get("NR_CPF_CANDIDATO") or "")
        nome = _limpo(c.get("NM_CANDIDATO")) or ""

        # foto (padrão do zip TSE: F{UF}{SQ}_div.jpg)
        foto_rel = None
        src = fotos_raw / f"F{uf}{sq}_div.jpg"
        if src.exists():
            dst = fotos_out / f"{sq}.jpg"
            if not dst.exists():
                shutil.copyfile(src, dst)
            foto_rel = f"data/{uf}/fotos/{sq}.jpg"

        serie = [dict(p) for p in series.get(cpf, [])]

        # histórico eleitoral: só as candidaturas reais (antes do preenchimento)
        historico = [{
            "ano": p["ano"], "uf": p["uf"], "cargo": p["cargo"],
            "partido": p["partido"], "resultado": p["resultado"],
            "municipio": p.get("municipio"),
        } for p in serie]
        partidos_seq = [_linhagem(p["partido"]) for p in historico if p["partido"]]
        trocas = sum(1 for a, b in zip(partidos_seq, partidos_seq[1:]) if a != b)
        eleicoes_ant = [h for h in historico if h["ano"] != ano]

        # mandatos exercidos (derivados do resultado oficial)
        mandatos = []
        for h in eleicoes_ant:
            if not (h["resultado"] or "").startswith("Eleito"):
                continue
            cargo_up = (h["cargo"] or "").upper()
            dur = 8 if "SENADOR" in cargo_up else 4
            mandatos.append({
                "cargo": h["cargo"],
                "onde": h["municipio"] or h["uf"],
                "inicio": h["ano"] + 1, "fim": h["ano"] + dur,
                "executivo": any(k in cargo_up for k in ("PREFEITO", "GOVERNADOR")),
            })

        # garante os anos de eleições GERAIS na série (não declarado = ponto vazio);
        # anos municipais só aparecem se a pessoa de fato concorreu
        anos_pres = {p["ano"] for p in serie}
        for a in config.ANOS_GERAIS:
            if a not in anos_pres:
                serie.append({"ano": a, "uf": None, "cargo": None, "partido": None,
                              "total": None, "n_bens": 0, "declarou": False,
                              "resultado": None, "municipio": None})
        serie.sort(key=lambda p: p["ano"])

        situ = _situacao(_limpo(c.get("DS_SITUACAO_CANDIDATURA")))
        cd_eleicao = _limpo(c.get("CD_ELEICAO")) or ""
        sg_ue = _limpo(c.get("SG_UE")) or uf

        ficha = {
            "v": 1,
            "ano": ano,
            "sq": sq,
            "uf": uf,
            "nome": nome.title(),
            "nome_urna": _limpo(c.get("NM_URNA_CANDIDATO")),
            "nome_social": (_limpo(c.get("NM_SOCIAL_CANDIDATO")) or "").title() or None,
            "numero": _limpo(c.get("NR_CANDIDATO")),
            "cpf_mascarado": _mask_cpf(cpf),
            "cargo": (_limpo(c.get("DS_CARGO")) or "").title(),
            "situacao": situ,
            "partido": {
                "nr": _limpo(c.get("NR_PARTIDO")),
                "sigla": _limpo(c.get("SG_PARTIDO")),
                "nome": _limpo(c.get("NM_PARTIDO")),
            },
            "federacao": _limpo(c.get("NM_FEDERACAO")),
            "coligacao": _limpo(c.get("NM_COLIGACAO")),
            "nascimento": _limpo(c.get("DT_NASCIMENTO")),
            "idade": _idade(str(c.get("DT_NASCIMENTO") or "")),
            "uf_nascimento": _limpo(c.get("SG_UF_NASCIMENTO")),
            "genero": (_limpo(c.get("DS_GENERO")) or "").title() or None,
            "cor_raca": (_limpo(c.get("DS_COR_RACA")) or "").title() or None,
            "instrucao": (_limpo(c.get("DS_GRAU_INSTRUCAO")) or "").title() or None,
            "ocupacao": (_limpo(c.get("DS_OCUPACAO")) or "").title() or None,
            "foto": foto_rel,
            "patrimonio": {
                "serie": serie,
                "variacoes": _variacoes(serie),
                "bens": bens.get(sq, []),
                "disclaimer": config.DISCLAIMER_PATRIMONIO,
            },
            "historico": {
                "eleicoes": historico,
                "ja_concorreu": len(eleicoes_ant) > 0,
                "vezes_candidato": len(eleicoes_ant),
                "vezes_eleito": sum(1 for h in eleicoes_ant
                                    if h["resultado"] and h["resultado"].startswith("Eleito")),
                "trocas_partido": trocas,
                "mandatos": mandatos,
                "nota": "Candidaturas em eleições gerais (2014, 2018, 2022) e municipais "
                        "(2016, 2020, 2024), cruzadas por CPF nos dados abertos do TSE. "
                        "Renomeações e fusões de partido (ex.: PMDB→MDB, DEM/PSL→UNIÃO) "
                        "não contam como troca de partido. Período de mandato estimado "
                        "pelo calendário eleitoral; afastamentos e sucessões não estão na base.",
            },
            "redes_sociais": redes.get(sq, []),
            "doacoes_feitas": (lambda ds: {
                "disponivel": doacoes_disp,
                "itens": ds[:30],
                "truncado": max(0, len(ds) - 30),
                "total_terceiros": round(sum(d["valor"] for d in ds
                                             if not d["propria"]), 2),
                "total_propria": round(sum(d["valor"] for d in ds
                                           if d["propria"]), 2),
                "anos_cobertos": config.ANOS_RECEITAS,
                "nota": "Doações registradas na prestação de contas eleitoral (TSE), "
                        "cruzadas pelo CPF do doador. Doar para campanhas é legal e "
                        "regulamentado; o dado mostra alinhamentos, não irregularidade.",
            })(doacoes.get(cpf, [])),
            "tcu": {**tcu.consultar(cpf, nome),
                    "disclaimer": config.DISCLAIMER_TCU},
            "sancoes": {
                "disponivel": sancoes_disp,
                "registros": sancoes.get(cpf, []),
                "consulta_oficial": "https://portaldatransparencia.gov.br/sancoes/consulta",
                "disclaimer": "Registros administrativos publicados pela CGU no Portal "
                              "da Transparência. Sanção administrativa não é condenação "
                              "criminal e pode estar sub judice; os efeitos têm prazo e "
                              "escopo definidos no processo indicado. Confira na fonte.",
            },
            # camadas com gancho de dados futuro (prestação de contas: 09-13/09)
            "financiamento": {"disponivel": False,
                              "previsao": "após a prestação parcial de contas (set/2026)"},
            "votacoes": {"disponivel": False},
            "mandato": {"disponivel": False},
            "processos": {"disponivel": False},
            "resumo_plano": None,
            "fontes": {
                "divulgacand": config.URL_DIVULGACAND.format(
                    ano=ano, cd_eleicao=cd_eleicao, sg_ue=sg_ue, sq=sq),
                "dataset_candidatos": config.URL_DATASET_CAND.format(ano=ano),
                "dataset_bens": config.URL_DATASET_CAND.format(ano=ano),
            },
            "dados_tse_de": dt_geracao,
            "gerado_em": date.today().isoformat(),
        }

        # injeta camadas geradas por módulos opcionais (rodam em separado)
        plano_path = config.OUT_DATA / "planos" / uf / f"{sq}.json"
        if plano_path.exists():
            ficha["resumo_plano"] = json.loads(plano_path.read_text("utf-8"))
        noticias_path = config.OUT_DATA / "noticias" / uf / f"{sq}.json"
        if noticias_path.exists():
            ficha["noticias"] = json.loads(noticias_path.read_text("utf-8"))
        proc_path = config.OUT_DATA / "processos_tse" / uf / f"{sq}.json"
        if proc_path.exists():
            ficha["processos_tse"] = json.loads(proc_path.read_text("utf-8"))
        gestao_path = config.OUT_DATA / "gestao" / uf / f"{sq}.json"
        if gestao_path.exists():
            ficha["gestao"] = json.loads(gestao_path.read_text("utf-8"))
        parl_path = config.OUT_DATA / "parlamentar" / uf / f"{sq}.json"
        if parl_path.exists():
            ficha["parlamentar"] = json.loads(parl_path.read_text("utf-8"))
        for camada in ("tcmgo", "tcego", "siconfi", "cnia", "qsa", "financiamento"):
            p = config.OUT_DATA / camada / uf / f"{sq}.json"
            if p.exists():
                ficha[camada] = json.loads(p.read_text("utf-8"))

        (out_dir / f"{sq}.json").write_text(
            json.dumps(ficha, ensure_ascii=False, separators=(",", ":")), "utf-8")

        tot26 = next((p["total"] for p in serie if p["ano"] == ano and p["declarou"]), None)
        indice.append({
            "sq": sq,
            "nu": ficha["nome_urna"],
            "nm": ficha["nome"],
            "nr": ficha["numero"],
            "pt": ficha["partido"]["sigla"],
            "cg": ficha["cargo"],
            "st": situ["label"],
            "ft": 1 if foto_rel else 0,
            "pat": tot26,
            "vc": len(eleicoes_ant),
            "ve": ficha["historico"]["vezes_eleito"],
        })

    (out_dir / "index.json").write_text(
        json.dumps({"uf": uf, "ano": ano, "dados_tse_de": dt_geracao,
                    "gerado_em": date.today().isoformat(),
                    "candidatos": indice},
                   ensure_ascii=False, separators=(",", ":")), "utf-8")
    print(f"  {uf}: {len(indice)} fichas geradas")
    return {"uf": uf, "n": len(indice)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ufs", nargs="*", default=None)
    args = ap.parse_args()
    ufs = args.ufs or config.UFS_ALVO

    con = duckdb.connect(str(config.DB_PATH), read_only=True)
    tcu = CruzadorTCU()
    if not tcu.disponivel:
        print("  [aviso] lista TCU ausente em data/tcu/ — camada 6 marcada como indisponível")

    resumo = [gerar_uf(con, uf, tcu) for uf in ufs]
    con.close()

    config.OUT_DATA.mkdir(parents=True, exist_ok=True)
    ufs_meta = {"ano": config.ANO_ELEICAO,
                "atualizado_em": date.today().isoformat(),
                "ufs": sorted({r["uf"] for r in resumo} |
                              {p.name for p in config.OUT_DATA.iterdir()
                               if p.is_dir() and len(p.name) == 2})}
    (config.OUT_DATA / "ufs.json").write_text(
        json.dumps(ufs_meta, ensure_ascii=False), "utf-8")
    print("OK —", ", ".join(f"{r['uf']}={r['n']}" for r in resumo))


if __name__ == "__main__":
    main()
