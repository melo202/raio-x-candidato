"""Camada — doações eleitorais QUE O CANDIDATO FEZ em eleições passadas.

O cruzamento invertido que ninguém entrega mastigado: nos arquivos de receitas
de campanha do TSE, o doador é identificado por CPF/CNPJ. Cruzando o CPF dos
candidatos de 2026 com os DOADORES de 2022/2024, a ficha responde:
"antes de pedir seu voto, ele financiou a campanha de quem?"

Fonte: prestação de contas eleitorais (dados abertos TSE), arquivos
receitas_candidatos_{ano}_{UF}.csv. Os zips são grandes (0,5–1,3 GB);
o módulo extrai só o necessário e materializa apenas as linhas cujo doador
é candidato em 2026 (tabela doacoes_feitas no DuckDB).

Uso:
    python pipeline/doacoes_feitas.py             # anos de config.ANOS_RECEITAS
    python pipeline/doacoes_feitas.py --anos 2022 # só um ano
Depois: rode fichas.py de novo para injetar nas fichas.
"""
from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

import duckdb
import requests

import config

UA = {"User-Agent": f"{config.PROJECT_NAME} (dados abertos; uso civico)"}


def baixar_receitas(ano: int) -> Path:
    url = config.URL_RECEITAS.format(ano=ano)
    dest = config.RAW_DIR / f"prestacao_candidatos_{ano}.zip"
    if not dest.exists():
        print(f"  [get ] {url} (grande — pode demorar)")
        with requests.get(url, headers=UA, stream=True, timeout=3600) as r:
            r.raise_for_status()
            tmp = dest.with_suffix(".part")
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(1 << 22):
                    f.write(chunk)
            tmp.rename(dest)
        print(f"  [ok  ] {dest.name} ({dest.stat().st_size/1e6:.0f} MB)")
    return dest


def extrair_receitas(zip_path: Path, ano: int) -> Path:
    """Extrai só receitas_candidatos_{ano}_*.csv (ignora despesas etc.)."""
    out = config.RAW_DIR / f"receitas_{ano}"
    out.mkdir(exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        # só o consolidado nacional: os arquivos por UF são um subconjunto dele
        # (carregar os dois duplicaria as doações) e o DF só existe no BRASIL
        alvos = [n for n in z.namelist()
                 if n == f"receitas_candidatos_{ano}_BRASIL.csv"]
        for n in alvos:
            if not (out / Path(n).name).exists():
                z.extract(n, out)
    # normaliza para UTF-8 (os CSVs do TSE vêm em latin-1, às vezes com bytes
    # que o leitor do DuckDB rejeita)
    marcador = out / ".utf8_ok"
    if not marcador.exists():
        for p in out.glob("*.csv"):
            raw = p.read_bytes()
            try:
                raw.decode("utf-8")
            except UnicodeDecodeError:
                p.write_bytes(raw.decode("latin-1").encode("utf-8"))
        marcador.touch()
    n_files = len(list(out.glob("*.csv")))
    print(f"  receitas_{ano}: {n_files} arquivos extraídos")
    return out


def materializar(con: duckdb.DuckDBPyConnection, anos: list[int]) -> None:
    ano_atual = config.ANO_ELEICAO
    unions = []
    for ano in anos:
        glob = str(config.RAW_DIR / f"receitas_{ano}"
                   / f"receitas_candidatos_{ano}_BRASIL.csv")
        unions.append(f"""
            SELECT {ano} AS ano,
                   REGEXP_REPLACE(r.NR_CPF_CNPJ_DOADOR, '[^0-9]', '', 'g') AS cpf_doador,
                   r.NM_DOADOR            AS nome_doador,
                   r.SQ_CANDIDATO         AS sq_beneficiado,
                   r.NM_CANDIDATO         AS beneficiado,
                   r.SG_PARTIDO           AS partido,
                   r.DS_CARGO             AS cargo,
                   r.SG_UF                AS uf,
                   r.NM_UE                AS municipio,
                   r.DT_RECEITA           AS data,
                   TRY_CAST(REPLACE(r.VR_RECEITA, ',', '.') AS DOUBLE) AS valor,
                   r.DS_ORIGEM_RECEITA    AS origem,
                   REGEXP_REPLACE(r.NR_CPF_CANDIDATO, '[^0-9]', '', 'g') AS cpf_beneficiado
            FROM read_csv('{glob}', delim=';', header=true, quote='"',
                          all_varchar=true, union_by_name=true) r
        """)
    con.execute(f"""
        CREATE OR REPLACE TABLE doacoes_feitas AS
        WITH doadores AS (
            SELECT DISTINCT NR_CPF_CANDIDATO AS cpf, NM_CANDIDATO AS nome
            FROM cand_{ano_atual}
            WHERE NR_CPF_CANDIDATO IS NOT NULL AND LENGTH(NR_CPF_CANDIDATO) = 11
        ),
        receitas AS ({' UNION ALL '.join(unions)})
        SELECT d.cpf, r.*,
               (r.cpf_beneficiado = d.cpf) AS propria_campanha
        FROM receitas r
        JOIN doadores d ON r.cpf_doador = d.cpf
        WHERE r.valor IS NOT NULL AND r.valor > 0
    """)
    n, ncand = con.execute("""
        SELECT COUNT(*), COUNT(DISTINCT cpf) FROM doacoes_feitas
    """).fetchone()
    terceiros = con.execute("""
        SELECT COUNT(*) FROM doacoes_feitas WHERE NOT propria_campanha
    """).fetchone()[0]
    print(f"  doacoes_feitas: {n:,} doações de {ncand:,} candidatos-doadores "
          f"({terceiros:,} para campanhas de terceiros)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--anos", nargs="*", type=int, default=None)
    args = ap.parse_args()
    anos = args.anos or config.ANOS_RECEITAS

    for ano in anos:
        print(f"-- receitas {ano}")
        z = baixar_receitas(ano)
        extrair_receitas(z, ano)

    con = duckdb.connect(str(config.DB_PATH))
    materializar(con, anos)
    con.close()
    print("OK — rode fichas.py de novo para injetar nas fichas")


if __name__ == "__main__":
    main()
