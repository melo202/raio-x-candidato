"""Camada 6 — contas julgadas irregulares (TCU).

O portal do TCU bloqueia download automatizado (WAF), então esta camada
consome um arquivo baixado manualmente:

    1. Acesse contasirregulares.tcu.gov.br e exporte a lista (CSV ou XLSX).
    2. Salve o arquivo em data/tcu/ (qualquer nome).
    3. Rode o pipeline — o cruzamento por CPF (primário) e nome (fallback)
       acontece automaticamente na geração das fichas.

Colunas reconhecidas (busca por nome aproximado, caixa/acentos ignorados):
    CPF        → "cpf", "nr_cpf", "cpf_responsavel" …
    NOME       → "nome", "nm_responsavel", "responsavel" …
    PROCESSO   → "processo", "num_processo" …
    DELIBERAÇÃO→ "acordao", "deliberacao", "decisao" …
    TRÂNSITO   → "transito", "data_transito", "transito_julgado" …
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pandas as pd

import config


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip().upper()


def _so_digitos(s: str) -> str:
    return re.sub(r"\D", "", str(s or ""))


def _achar_coluna(cols: list[str], *padroes: str) -> str | None:
    for c in cols:
        cn = _norm(c).replace(" ", "_")
        for p in padroes:
            if p in cn:
                return c
    return None


def carregar_lista() -> pd.DataFrame | None:
    """Lê o primeiro CSV/XLSX em data/tcu/. None se não houver arquivo."""
    arquivos = sorted(
        [p for p in config.TCU_DIR.glob("*")
         if p.suffix.lower() in (".csv", ".xlsx", ".xls")],
        key=lambda p: p.stat().st_mtime, reverse=True,   # mais recente primeiro
    )
    if not arquivos:
        return None
    path = arquivos[0]
    if path.suffix.lower() == ".csv":
        # tenta ; depois , — e latin-1 depois utf-8
        for kw in ({"sep": ";"}, {"sep": ","}):
            for enc in ("utf-8", "latin-1"):
                try:
                    df = pd.read_csv(path, encoding=enc, dtype=str, **kw)
                    if len(df.columns) > 1:
                        raise StopIteration
                except StopIteration:
                    break
                except Exception:
                    df = None
            else:
                continue
            break
    else:
        df = pd.read_excel(path, dtype=str)
    if df is None or df.empty:
        return None

    cols = list(df.columns)
    c_cpf = _achar_coluna(cols, "CPF")
    c_nome = _achar_coluna(cols, "NOME", "RESPONSAVEL")
    if c_cpf is None and c_nome is None:
        raise SystemExit(f"tcu.py: nenhuma coluna CPF/NOME reconhecida em "
                         f"{path.name} — colunas: {cols}")
    c_proc = _achar_coluna(cols, "PROCESSO")
    c_delib = _achar_coluna(cols, "ACORDAO", "DELIBERACAO", "DECISAO")
    c_trans = _achar_coluna(cols, "TRANSITO")

    out = pd.DataFrame({
        "cpf": df[c_cpf].map(_so_digitos) if c_cpf else "",
        "nome_norm": df[c_nome].map(_norm) if c_nome else "",
        "processo": df[c_proc] if c_proc else "",
        "deliberacao": df[c_delib] if c_delib else "",
        "transito": df[c_trans] if c_trans else "",
    })
    print(f"  TCU: {len(out):,} responsáveis carregados de {path.name}")
    return out


class CruzadorTCU:
    """Cruza candidatos com a lista do TCU. Uso: CruzadorTCU().consultar(cpf, nome)."""

    def __init__(self) -> None:
        self.df = carregar_lista()
        self.disponivel = self.df is not None
        if self.disponivel:
            self._por_cpf = self.df.groupby("cpf")
            self._cpfs = set(self.df["cpf"]) - {""}
            # fallback por nome APENAS para linhas da lista SEM CPF utilizável —
            # se a lista tem o CPF e ele não é o do candidato, homônimo não conta
            sem_cpf = self.df[self.df["cpf"] == ""]
            self._nomes_sem_cpf = set(sem_cpf["nome_norm"]) - {""}

    def consultar(self, cpf: str, nome: str) -> dict:
        if not self.disponivel:
            return {"disponivel": False, "listado": None, "registros": [],
                    "criterio": None}
        cpf = _so_digitos(cpf)
        nome_n = _norm(nome)
        criterio, hits = None, pd.DataFrame()
        if cpf and cpf in self._cpfs:
            criterio, hits = "cpf", self._por_cpf.get_group(cpf)
        elif nome_n and nome_n in self._nomes_sem_cpf:
            criterio = "nome"  # homônimo possível — a ficha avisa
            hits = self.df[(self.df["nome_norm"] == nome_n) & (self.df["cpf"] == "")]
        registros = [
            {"processo": r.processo, "deliberacao": r.deliberacao,
             "transito": r.transito}
            for r in hits.itertuples()
        ][:20]
        return {
            "disponivel": True,
            "listado": bool(registros),
            "criterio": criterio,
            "registros": registros,
        }
