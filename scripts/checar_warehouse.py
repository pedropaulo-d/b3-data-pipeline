"""Checagem rápida do estado do warehouse local após uma execução da DAG.

Lê ``warehouse.duckdb`` em modo somente leitura e imprime, para cada
camada relevante:

- ``raw.cotacoes`` (view sobre o MinIO via httpfs): contagem total,
  range de datas, número de tickers distintos.
- ``staging.stg_cotacoes`` (view do dbt, mesma janela do raw já tipada).
- ``marts.fato_cotacoes_diarias`` (table materializada pelo dbt):
  contagem, max(data), media(volume).
- ``marts.dim_empresa`` e ``marts.dim_tempo``: contagem.

É um sanity check, não substitui ``dbt test``. Serve para responder em
30 segundos "a DAG escreveu mesmo, ou só ficou verde sem fazer nada?".

Uso:

    python -m scripts.checar_warehouse
"""

from __future__ import annotations

import duckdb

from warehouse.conexao import CAMINHO_WAREHOUSE


def _imprimir(titulo: str, linhas: list[tuple]) -> None:
    print(f"\n--- {titulo} ---")
    for linha in linhas:
        print("  ", linha)


def main() -> None:
    if not CAMINHO_WAREHOUSE.exists():
        raise SystemExit(
            f"warehouse.duckdb não encontrado em {CAMINHO_WAREHOUSE}. "
            "Rode `python -m warehouse.setup` primeiro."
        )

    print(f"Abrindo {CAMINHO_WAREHOUSE} (somente leitura)...")

    # IMPORTANTE: a view raw.cotacoes depende de httpfs + credenciais S3.
    # Reusamos obter_conexao() para herdar todo esse setup automaticamente.
    # Mas em "somente leitura" o DuckDB recusa SETs — então abrimos uma
    # conexão normal e nos comprometemos a só rodar SELECTs.
    from warehouse.conexao import obter_conexao

    with obter_conexao(read_only=False) as con:
        raw = con.execute(
            """
            SELECT
                COUNT(*)         AS linhas,
                MIN(data)        AS min_data,
                MAX(data)        AS max_data,
                COUNT(DISTINCT ticker) AS tickers
            FROM raw.cotacoes
            """
        ).fetchall()
        _imprimir("raw.cotacoes (view sobre MinIO)", raw)

        stg = con.execute(
            """
            SELECT
                COUNT(*)         AS linhas,
                MIN(data)        AS min_data,
                MAX(data)        AS max_data
            FROM staging.stg_cotacoes
            """
        ).fetchall()
        _imprimir("staging.stg_cotacoes (view dbt)", stg)

        # A fato segue o modelo dimensional: data vive em dim_tempo,
        # referenciada via surrogate key tempo_id (formato YYYYMMDD).
        # Para obter a data real, JOIN com dim_tempo — que é como a
        # query analítica de verdade opera.
        fato = con.execute(
            """
            SELECT
                COUNT(*)              AS linhas,
                MAX(dt.data)          AS max_data,
                ROUND(AVG(f.volume)::DOUBLE, 2) AS volume_medio
            FROM marts.fato_cotacoes_diarias f
            JOIN marts.dim_tempo dt USING (tempo_id)
            """
        ).fetchall()
        _imprimir("marts.fato_cotacoes_diarias (JOIN dim_tempo)", fato)

        dim_emp = con.execute(
            "SELECT COUNT(*) FROM marts.dim_empresa"
        ).fetchall()
        _imprimir("marts.dim_empresa", dim_emp)

        dim_tmp = con.execute(
            "SELECT COUNT(*), MIN(data), MAX(data) FROM marts.dim_tempo"
        ).fetchall()
        _imprimir("marts.dim_tempo", dim_tmp)

    print("\nOK. Se max(data) bate com o último pregão e linhas > 0 em todas,")
    print("o pipeline (ingestão -> warehouse -> dbt) está honesto.")


if __name__ == "__main__":
    main()
