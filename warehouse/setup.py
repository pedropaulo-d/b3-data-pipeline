"""Setup do schema ``raw`` no warehouse DuckDB.

A única estrutura criada por este módulo é a view ``raw.cotacoes``,
que aponta para os Parquet do raw layer no MinIO via ``read_parquet``
com ``hive_partitioning = true``. View — não tabela materializada —
para preservar o conceito de raw imutável no object storage e refletir
automaticamente novas datas ingeridas (ver ``docs/decisoes.md``).

Schemas ``staging`` e ``marts`` NÃO são criados aqui: vão nascer na
Etapa 4 sob responsabilidade do dbt.

Uso direto::

    python -m warehouse.setup
"""

import logging
import sys

import duckdb

from ingestion.config import MINIO_BUCKET, RAW_PREFIX
from warehouse.conexao import CAMINHO_WAREHOUSE, obter_conexao

logger = logging.getLogger(__name__)


def _glob_raw_cotacoes() -> str:
    """Monta o glob ``s3://...`` que casa com todas as partições do raw.

    O padrão ``ano=*/mes=*/dia=*/cotacoes.parquet`` é resolvido pelo
    DuckDB no momento da leitura. Combinado com ``hive_partitioning``,
    expõe ``ano``, ``mes`` e ``dia`` como colunas virtuais.
    """
    return f"s3://{MINIO_BUCKET}/{RAW_PREFIX}/ano=*/mes=*/dia=*/cotacoes.parquet"


def criar_schema_raw(con: duckdb.DuckDBPyConnection) -> None:
    """Cria o schema ``raw`` e a view ``raw.cotacoes``.

    Idempotente: usa ``CREATE SCHEMA IF NOT EXISTS`` e
    ``CREATE OR REPLACE VIEW`` — rodar duas vezes deixa o estado
    exatamente igual a uma única execução.

    Args:
        con: Conexão DuckDB obtida via :func:`warehouse.conexao.obter_conexao`.
            Precisa estar com ``httpfs`` carregado e ``s3_*`` configurado
            (ambos feitos por ``obter_conexao``).
    """
    glob = _glob_raw_cotacoes()
    logger.info("Criando schema raw e view raw.cotacoes apontando para %s", glob)

    con.execute("CREATE SCHEMA IF NOT EXISTS raw")
    con.execute(
        f"""
        CREATE OR REPLACE VIEW raw.cotacoes AS
        SELECT *
        FROM read_parquet(
            '{glob}',
            hive_partitioning = true
        )
        """
    )


def _diagnostico(con: duckdb.DuckDBPyConnection) -> None:
    """Imprime um resumo do que a view ``raw.cotacoes`` enxerga.

    Roda três queries baratas:
    - Contagem total de linhas
    - Número de tickers distintos
    - Range (min, max) da coluna ``data``

    Se a contagem voltar zero, sugere rodar a ingestão.
    """
    total = con.execute("SELECT COUNT(*) FROM raw.cotacoes").fetchone()[0]
    if total == 0:
        print(
            "[!] raw.cotacoes está vazia. Provavelmente não há Parquet no "
            "bucket ainda. Rode `python -m ingestion.main --modo inicial` "
            "antes de explorar o warehouse."
        )
        return

    tickers_distintos = con.execute(
        "SELECT COUNT(DISTINCT ticker) FROM raw.cotacoes"
    ).fetchone()[0]
    data_min, data_max = con.execute(
        "SELECT MIN(data), MAX(data) FROM raw.cotacoes"
    ).fetchone()

    print("=" * 60)
    print("Warehouse DuckDB pronto.")
    print(f"  Arquivo:           {CAMINHO_WAREHOUSE}")
    print(f"  View:              raw.cotacoes")
    print(f"  Linhas totais:     {total:,}")
    print(f"  Tickers distintos: {tickers_distintos}")
    print(f"  Datas:             {data_min} a {data_max}")
    print("=" * 60)


def main() -> int:
    """Entry-point CLI: cria o schema raw e imprime o diagnóstico.

    Returns:
        Código de saída: 0 em sucesso, 1 em erro previsível
        (MinIO fora do ar, credenciais erradas, view vazia esperada
        já tratada como aviso e não erro).
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    con = obter_conexao(read_only=False)
    try:
        try:
            criar_schema_raw(con)
        except duckdb.IOException as exc:
            print(
                "[ERRO] Falha ao criar a view raw.cotacoes lendo do MinIO.\n"
                "  Possíveis causas:\n"
                "  1. MinIO fora do ar — suba com:\n"
                "       docker compose -f docker-compose.minio.yml up -d\n"
                "  2. Credenciais erradas no .env (MINIO_ACCESS_KEY/SECRET_KEY).\n"
                "  3. Bucket vazio — rode a ingestão antes:\n"
                "       python -m ingestion.main --modo inicial\n"
                f"\nDetalhe técnico: {exc}",
                file=sys.stderr,
            )
            return 1

        _diagnostico(con)
    finally:
        con.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
