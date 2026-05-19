"""CLI da ingestão.

Três modos:

- ``inicial`` — carrega o histórico desde
  :data:`ingestion.config.DATA_INICIO_HISTORICO` até hoje. Uso típico:
  primeira execução do pipeline.
- ``diario``  — carrega apenas o dia atual. Se não houver pregão (fim de
  semana, feriado), o yfinance retorna vazio e o script sai com sucesso
  sem gravar nada.
- ``range``   — carrega um intervalo arbitrário ``[--inicio, --fim]``.
  Útil para backfill e debug.

Em todos os modos, o destino é o MinIO local (bucket configurado em
``.env``); não há flag para escolher backend. Pré-requisito de execução:
``docker compose -f docker-compose.minio.yml up -d``.

Em todos os modos, a ingestão é idempotente: rodar duas vezes produz o
mesmo conjunto de objetos no bucket (idempotência semântica — ver
``docs/decisoes.md``).
"""

import argparse
import logging
import sys
from dataclasses import dataclass
from datetime import date, datetime

import requests

from ingestion.config import (
    DATA_INICIO_HISTORICO,
    MINIO_BUCKET,
    RAW_PREFIX,
    TICKERS,
)
from ingestion.download import baixar_cotacoes
from ingestion.storage import salvar_particionado

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IntervaloIngestao:
    """Intervalo resolvido a partir dos argumentos de CLI."""

    inicio: date
    fim: date
    rotulo_modo: str


def _configurar_logging() -> None:
    """Configura o root logger com nível INFO e formato com timestamp."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _parse_data(texto: str) -> date:
    """Converte ``YYYY-MM-DD`` em :class:`datetime.date`; argparse type."""
    try:
        return datetime.strptime(texto, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Data inválida {texto!r}; use o formato YYYY-MM-DD."
        ) from exc


def _construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ingestion.main",
        description=(
            "Baixa cotações da B3 via yfinance e grava em Parquet "
            "particionado por data no raw layer local."
        ),
    )
    parser.add_argument(
        "--modo",
        required=True,
        choices=["inicial", "diario", "range"],
        help=(
            "inicial = carga histórica de 5 anos; "
            "diario = apenas o dia de hoje; "
            "range = intervalo arbitrário (requer --inicio e --fim)."
        ),
    )
    parser.add_argument(
        "--inicio",
        type=_parse_data,
        help="Data inicial (YYYY-MM-DD), obrigatória se --modo=range.",
    )
    parser.add_argument(
        "--fim",
        type=_parse_data,
        help="Data final inclusiva (YYYY-MM-DD), obrigatória se --modo=range.",
    )
    return parser


def _resolver_intervalo(args: argparse.Namespace) -> IntervaloIngestao:
    """Traduz os argumentos da CLI em um intervalo concreto de datas."""
    hoje = date.today()

    if args.modo == "inicial":
        return IntervaloIngestao(
            inicio=DATA_INICIO_HISTORICO,
            fim=hoje,
            rotulo_modo="inicial (5 anos)",
        )

    if args.modo == "diario":
        return IntervaloIngestao(
            inicio=hoje,
            fim=hoje,
            rotulo_modo="diario",
        )

    # modo == "range"
    if args.inicio is None or args.fim is None:
        raise SystemExit(
            "Erro: --modo=range requer --inicio e --fim (formato YYYY-MM-DD)."
        )
    if args.inicio > args.fim:
        raise SystemExit(
            f"Erro: --inicio ({args.inicio}) é posterior a --fim ({args.fim})."
        )
    return IntervaloIngestao(
        inicio=args.inicio,
        fim=args.fim,
        rotulo_modo="range",
    )


def executar(intervalo: IntervaloIngestao) -> int:
    """Orquestra download → validação → gravação para o intervalo dado.

    O destino é fixado pela configuração (bucket + prefixo definidos em
    :mod:`ingestion.config`). Não há flag de CLI para escolhê-lo — a
    Etapa 2 estabeleceu MinIO como o único backend do raw layer.

    Returns:
        Código de saída (0 = sucesso, 1 = falha).
    """
    destino = f"s3://{MINIO_BUCKET}/{RAW_PREFIX}"
    logger.info(
        "Iniciando ingestão | modo=%s | período=%s → %s | destino=%s",
        intervalo.rotulo_modo,
        intervalo.inicio.isoformat(),
        intervalo.fim.isoformat(),
        destino,
    )

    try:
        df = baixar_cotacoes(TICKERS, intervalo.inicio, intervalo.fim)
    except (ValueError, requests.RequestException) as exc:
        logger.error("Falha no download: %s", exc, exc_info=True)
        return 1

    try:
        n_objetos = salvar_particionado(df)
    except (ValueError, RuntimeError) as exc:
        logger.error("Falha na gravação: %s", exc, exc_info=True)
        return 1

    logger.info(
        "Resumo | período=%s → %s | tickers=%d | linhas=%d | objetos=%d",
        intervalo.inicio.isoformat(),
        intervalo.fim.isoformat(),
        df["ticker"].nunique() if not df.empty else 0,
        len(df),
        n_objetos,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    _configurar_logging()
    parser = _construir_parser()
    args = parser.parse_args(argv)

    intervalo = _resolver_intervalo(args)
    return executar(intervalo)


if __name__ == "__main__":
    sys.exit(main())
