"""CLI da ingestão de dividendos (Etapa 6).

Dois modos:

- ``inicial``     — reescreve **todas** as partições de ano com o
  histórico completo de proventos. Uso típico: primeira carga.
- ``incremental`` — reescreve apenas a partição do **ano corrente**.
  Dividendos passados não mudam; só o ano em curso ganha eventos novos,
  então é a única partição que precisa ser atualizada no dia a dia.

Como ``yf.Ticker(...).dividends`` sempre devolve o histórico inteiro, a
diferença entre os modos não está no *download* (idêntico), e sim em
*quais partições de ano são gravadas*. Em ambos os modos a operação é
idempotente: rodar duas vezes produz o mesmo conjunto de objetos.

Destino: MinIO local (bucket de ``.env``). Pré-requisito:
``docker compose up -d minio mc-init``.

Uso::

    python -m ingestion.dividendos.main --modo inicial
    python -m ingestion.dividendos.main --modo incremental
"""

import argparse
import logging
import sys
from datetime import date

import requests

from ingestion.config import MINIO_BUCKET, RAW_PREFIX_DIVIDENDOS, TICKERS
from ingestion.dividendos.download import baixar_dividendos
from ingestion.dividendos.storage import salvar_dividendos_por_ano

logger = logging.getLogger(__name__)


def _configurar_logging() -> None:
    """Configura o root logger com nível INFO e formato com timestamp."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ingestion.dividendos.main",
        description=(
            "Baixa dividendos da B3 via yfinance e grava em Parquet "
            "particionado por ano no raw layer (MinIO)."
        ),
    )
    parser.add_argument(
        "--modo",
        required=True,
        choices=["inicial", "incremental"],
        help=(
            "inicial = reescreve todo o histórico (todas as partições de ano); "
            "incremental = reescreve apenas a partição do ano corrente."
        ),
    )
    return parser


def executar(modo: str) -> int:
    """Orquestra download → gravação para o modo informado.

    Returns:
        Código de saída (0 = sucesso, 1 = falha).
    """
    destino = f"s3://{MINIO_BUCKET}/{RAW_PREFIX_DIVIDENDOS}"
    logger.info("Iniciando ingestão de dividendos | modo=%s | destino=%s", modo, destino)

    try:
        df = baixar_dividendos(TICKERS)
    except (ValueError, requests.RequestException) as exc:
        logger.error("Falha no download de dividendos: %s", exc, exc_info=True)
        return 1

    # Modo incremental reescreve só o ano corrente; inicial, todos os anos.
    anos = {date.today().year} if modo == "incremental" else None

    try:
        n_objetos = salvar_dividendos_por_ano(df, anos=anos)
    except (ValueError, RuntimeError) as exc:
        logger.error("Falha na gravação de dividendos: %s", exc, exc_info=True)
        return 1

    logger.info(
        "Resumo | modo=%s | tickers=%d | proventos=%d | partições=%d",
        modo,
        df["ticker"].nunique() if not df.empty else 0,
        len(df),
        n_objetos,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    _configurar_logging()
    parser = _construir_parser()
    args = parser.parse_args(argv)
    return executar(args.modo)


if __name__ == "__main__":
    sys.exit(main())
