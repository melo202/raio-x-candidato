"""Carrega os CSVs do TSE no DuckDB e materializa as visões de cruzamento.

Tabelas criadas:
    cand_{ano}   — consulta_cand (1 linha por candidatura)
    bem_{ano}    — bem_candidato (1 linha por bem declarado)
    patrimonio   — total declarado por candidatura (SQ) por ano
    serie_cpf    — série patrimonial por CPF (a chave-mestra entre eleições)

Uso: python pipeline/build_db.py
"""
from __future__ import annotations

import duckdb

import config


def _csv_glob(pasta: str, ano: int) -> str:
    """Glob dos CSVs por UF, excluindo o consolidado *_BRASIL.csv (duplicaria)."""
    return str(config.RAW_DIR / f"{pasta}_{ano}" / f"{pasta}_{ano}_*.csv")


def _garantir_utf8(pasta: str, ano: int) -> None:
    """Converte os CSVs do TSE (latin-1) para UTF-8, uma única vez (idempotente)."""
    d = config.RAW_DIR / f"{pasta}_{ano}"
    marcador = d / ".utf8_ok"
    if marcador.exists():
        return
    for p in d.glob("*.csv"):
        raw = p.read_bytes()
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError:
            p.write_bytes(raw.decode("latin-1").encode("utf-8"))
    marcador.touch()


def _load_year(con: duckdb.DuckDBPyConnection, pasta: str, tabela: str, ano: int) -> None:
    _garantir_utf8(pasta, ano)
    glob = _csv_glob(pasta, ano)
    con.execute(f"""
        CREATE OR REPLACE TABLE {tabela} AS
        SELECT * FROM read_csv(
            '{glob}',
            delim=';', header=true, quote='"',
            all_varchar=true, union_by_name=true,
            filename=true
        )
        WHERE filename NOT LIKE '%_BRASIL.csv'
    """)
    n = con.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]
    print(f"  {tabela}: {n:,} linhas")


def build(db_path=None) -> None:
    db_path = db_path or config.DB_PATH
    con = duckdb.connect(str(db_path))

    print("== Carregando CSVs ==")
    for ano in config.ANOS_PATRIMONIO:
        _load_year(con, "consulta_cand", f"cand_{ano}", ano)
        _load_year(con, "bem_candidato", f"bem_{ano}", ano)

    print("== Materializando cruzamentos ==")
    # Total declarado por candidatura (SQ_CANDIDATO) em cada ano
    unions = []
    for ano in config.ANOS_PATRIMONIO:
        unions.append(f"""
            SELECT {ano} AS ano, SQ_CANDIDATO,
                   SUM(TRY_CAST(REPLACE(VR_BEM_CANDIDATO, ',', '.') AS DOUBLE)) AS total,
                   COUNT(*) AS n_bens
            FROM bem_{ano}
            GROUP BY SQ_CANDIDATO
        """)
    con.execute("CREATE OR REPLACE TABLE patrimonio AS " + " UNION ALL ".join(unions))

    # Série por CPF: junta cada ano de bens à candidatura daquele ano (fonte do CPF)
    unions = []
    for ano in config.ANOS_PATRIMONIO:
        unions.append(f"""
            SELECT {ano} AS ano,
                   c.NR_CPF_CANDIDATO AS cpf,
                   c.SQ_CANDIDATO     AS sq,
                   c.NM_CANDIDATO     AS nome,
                   c.SG_UF            AS uf,
                   c.NM_UE            AS ue,
                   {1 if ano in config.ANOS_MUNICIPAIS else 0} AS municipal,
                   c.DS_CARGO         AS cargo,
                   c.SG_PARTIDO       AS partido,
                   c.DS_SIT_TOT_TURNO AS resultado,
                   c.DS_SITUACAO_CANDIDATURA AS situacao,
                   COALESCE(p.total, 0)  AS total,
                   COALESCE(p.n_bens, 0) AS n_bens,
                   p.total IS NOT NULL   AS declarou
            FROM cand_{ano} c
            LEFT JOIN patrimonio p
              ON p.SQ_CANDIDATO = c.SQ_CANDIDATO AND p.ano = {ano}
            WHERE c.NR_CPF_CANDIDATO IS NOT NULL
              AND LENGTH(c.NR_CPF_CANDIDATO) >= 11
        """)
    con.execute("CREATE OR REPLACE TABLE serie_cpf AS " + " UNION ALL ".join(unions))

    # Redes sociais declaradas ao TSE (ano corrente; só URLs de verdade)
    try:
        _garantir_utf8("rede_social_candidato", config.ANO_ELEICAO)
        glob_rs = str(config.RAW_DIR / f"rede_social_candidato_{config.ANO_ELEICAO}" / "*.csv")
        con.execute(f"""
            CREATE OR REPLACE TABLE rede_social AS
            SELECT DISTINCT SQ_CANDIDATO, TRIM(DS_URL) AS url
            FROM read_csv('{glob_rs}', delim=';', header=true, quote='"',
                          all_varchar=true, union_by_name=true, filename=true)
            WHERE filename NOT LIKE '%_BRASIL.csv'
              AND (LOWER(TRIM(DS_URL)) LIKE 'http%' OR LOWER(TRIM(DS_URL)) LIKE 'www.%')
        """)
        n = con.execute("SELECT COUNT(*) FROM rede_social").fetchone()[0]
        print(f"  rede_social: {n:,} URLs")
    except Exception as e:
        print(f"  [warn] rede_social indisponível: {e}")
        con.execute("CREATE OR REPLACE TABLE rede_social (SQ_CANDIDATO VARCHAR, url VARCHAR)")

    # Sanidade: maiores variações 2022→2026 (o cruzamento provado em 18/08)
    demo = con.execute(f"""
        WITH a AS (SELECT cpf, MAX(total) t22 FROM serie_cpf
                   WHERE ano=2022 AND declarou GROUP BY cpf),
             b AS (SELECT cpf, nome, uf, MAX(total) t26 FROM serie_cpf
                   WHERE ano={config.ANO_ELEICAO} AND declarou GROUP BY cpf, nome, uf)
        SELECT b.nome, b.uf, a.t22, b.t26, ROUND(100.0*(b.t26-a.t22)/a.t22, 1) pct
        FROM a JOIN b USING (cpf)
        WHERE a.t22 > 100000 AND b.uf = 'GO'
        ORDER BY pct DESC LIMIT 5
    """).fetchall()
    print("  sanidade — top variações GO 2022→2026:")
    for r in demo:
        print(f"    {r[0][:40]:42s} {r[2]:>14,.0f} → {r[3]:>14,.0f}  ({r[4]:+.1f}%)")

    con.close()
    print(f"OK — banco em {db_path}")


if __name__ == "__main__":
    build()
