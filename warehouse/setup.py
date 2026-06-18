"""Setup do schema ``raw`` no warehouse DuckDB.

Este módulo cria duas views sobre o raw layer no MinIO, ambas via
``read_parquet`` com ``hive_partitioning = true`` (View — não tabela
materializada — para preservar o raw imutável no object storage e
refletir automaticamente novas ingestões; ver ``docs/decisoes.md``):

- ``raw.cotacoes``   — Parquet de cotações, particionado por dia.
- ``raw.dividendos`` — Parquet de dividendos, particionado por ano
  (Etapa 6).

Schemas ``staging`` e ``marts`` NÃO são criados aqui: nascem no dbt
(Etapas 4 e 6).

Uso direto::

    python -m warehouse.setup
"""

import logging
import sys

import duckdb

from ingestion.config import MINIO_BUCKET, RAW_PREFIX, RAW_PREFIX_DIVIDENDOS
from warehouse.conexao import CAMINHO_WAREHOUSE, obter_conexao

logger = logging.getLogger(__name__)


def _glob_raw_cotacoes() -> str:
    """Monta o glob ``s3://...`` que casa com todas as partições do raw.

    O padrão ``ano=*/mes=*/dia=*/cotacoes.parquet`` é resolvido pelo
    DuckDB no momento da leitura. Combinado com ``hive_partitioning``,
    expõe ``ano``, ``mes`` e ``dia`` como colunas virtuais.
    """
    return f"s3://{MINIO_BUCKET}/{RAW_PREFIX}/ano=*/mes=*/dia=*/cotacoes.parquet"


def _glob_raw_dividendos() -> str:
    """Monta o glob ``s3://...`` que casa com todas as partições de ano.

    Dividendos particionam só por ano (``ano=*/dividendos.parquet``),
    refletindo a esparsidade dos proventos. ``hive_partitioning`` expõe
    ``ano`` como coluna virtual derivada do path.
    """
    return f"s3://{MINIO_BUCKET}/{RAW_PREFIX_DIVIDENDOS}/ano=*/dividendos.parquet"


def criar_schema_raw(con: duckdb.DuckDBPyConnection) -> None:
    """Cria o schema ``raw`` e as views ``raw.cotacoes`` e ``raw.dividendos``.

    Idempotente: usa ``CREATE SCHEMA IF NOT EXISTS`` e
    ``CREATE OR REPLACE VIEW`` — rodar duas vezes deixa o estado
    exatamente igual a uma única execução.

    Args:
        con: Conexão DuckDB obtida via :func:`warehouse.conexao.obter_conexao`.
            Precisa estar com ``httpfs`` carregado e ``s3_*`` configurado
            (ambos feitos por ``obter_conexao``).
    """
    glob_cotacoes = _glob_raw_cotacoes()
    glob_dividendos = _glob_raw_dividendos()
    logger.info("Criando schema raw e view raw.cotacoes apontando para %s", glob_cotacoes)
    logger.info("Criando view raw.dividendos apontando para %s", glob_dividendos)

    con.execute("CREATE SCHEMA IF NOT EXISTS raw")
    con.execute(
        f"""
        CREATE OR REPLACE VIEW raw.cotacoes AS
        SELECT *
        FROM read_parquet(
            '{glob_cotacoes}',
            hive_partitioning = true
        )
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE VIEW raw.dividendos AS
        SELECT *
        FROM read_parquet(
            '{glob_dividendos}',
            hive_partitioning = true
        )
        """
    )


def _diagnostico(con: duckdb.DuckDBPyConnection) -> None:
    """Imprime um resumo do que as views ``raw.*`` enxergam.

    Reporta cotações e dividendos. Erro de leitura (o prefixo daquela
    fonte ainda não existe no bucket) vira aviso, não exceção — é
    esperado inspecionar o warehouse antes de ter rodado *todas* as
    ingestões.
    """
    print("=" * 60)
    print("Warehouse DuckDB pronto.")
    print(f"  Arquivo: {CAMINHO_WAREHOUSE}")
    _resumir_cotacoes(con)
    _resumir_dividendos(con)
    print("=" * 60)


def _resumir_cotacoes(con: duckdb.DuckDBPyConnection) -> None:
    """Resumo de raw.cotacoes (linhas, tickers, range de datas)."""
    print("\n  raw.cotacoes (cotações — partição por dia)")
    try:
        total = con.execute("SELECT COUNT(*) FROM raw.cotacoes").fetchone()[0]
    except duckdb.IOException:
        total = 0
    if total == 0:
        print("    [!] vazia — rode `python -m ingestion.main --modo inicial`.")
        return

    tickers = con.execute("SELECT COUNT(DISTINCT ticker) FROM raw.cotacoes").fetchone()[0]
    data_min, data_max = con.execute(
        "SELECT MIN(data), MAX(data) FROM raw.cotacoes"
    ).fetchone()
    print(f"    Linhas:  {total:,}")
    print(f"    Tickers: {tickers}")
    print(f"    Datas:   {data_min} a {data_max}")


def _resumir_dividendos(con: duckdb.DuckDBPyConnection) -> None:
    """Resumo de raw.dividendos (proventos, tickers, range de datas-ex)."""
    print("\n  raw.dividendos (dividendos — partição por ano)")
    try:
        total = con.execute("SELECT COUNT(*) FROM raw.dividendos").fetchone()[0]
    except duckdb.IOException:
        total = 0
    if total == 0:
        print(
            "    [!] vazia — rode `python -m ingestion.dividendos.main --modo inicial`."
        )
        return

    tickers = con.execute(
        "SELECT COUNT(DISTINCT ticker) FROM raw.dividendos"
    ).fetchone()[0]
    data_min, data_max = con.execute(
        "SELECT MIN(data_ex), MAX(data_ex) FROM raw.dividendos"
    ).fetchone()
    print(f"    Proventos: {total:,}")
    print(f"    Tickers:   {tickers}")
    print(f"    Datas-ex:  {data_min} a {data_max}")


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
