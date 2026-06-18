"""Download de dividendos via yfinance.

Diferente das cotações (``yf.download`` em lote), proventos são obtidos
por ticker com ``yf.Ticker(t).dividends`` — uma série temporal indexada
pela **data-ex**, com o valor pago por ação. A API sempre devolve o
histórico completo (não há recorte por data); o recorte por modo
(inicial vs incremental) é decidido na escrita, escolhendo quais
partições de ano reescrever.

O resultado é um DataFrame "long" (1 linha por ``ticker × data-ex``) com
o schema :data:`ingestion.config.COLUNAS_DIVIDENDOS`, pronto para
particionamento por ano.
"""

import logging

import pandas as pd
import yfinance as yf

from ingestion.config import COLUNAS_DIVIDENDOS, ticker_yfinance

logger = logging.getLogger(__name__)


def baixar_dividendos(tickers: list[str]) -> pd.DataFrame:
    """Baixa o histórico completo de dividendos dos tickers informados.

    Para cada ticker, consulta ``yf.Ticker(...).dividends`` e empilha o
    resultado em formato long. Tickers sem nenhum provento (raro para os
    blue chips do escopo) são simplesmente omitidos do resultado.

    Args:
        tickers: Lista de tickers B3 sem sufixo (ex.: ``["PETR4", "VALE3"]``).

    Returns:
        DataFrame "long" com as colunas de
        :data:`ingestion.config.COLUNAS_DIVIDENDOS` (``data_ex``,
        ``ticker``, ``valor_dividendo``). Vazio (mas com o schema certo)
        se nenhum ticker tiver proventos.

    Raises:
        ValueError: Se ``tickers`` estiver vazio.
    """
    if not tickers:
        raise ValueError("Lista de tickers vazia.")

    logger.info("Baixando dividendos de %d tickers via yfinance.", len(tickers))

    parciais: list[pd.DataFrame] = []
    for ticker in tickers:
        serie = yf.Ticker(ticker_yfinance(ticker)).dividends

        if serie is None or serie.empty:
            logger.warning("Ticker %s: nenhum provento retornado pelo yfinance.", ticker)
            continue

        # `serie` é uma Series indexada pela data-ex (tz-aware), valores =
        # dividendo por ação. reset_index() materializa [data_ex, valor].
        parcial = serie.reset_index()
        parcial.columns = ["data_ex", "valor_dividendo"]
        parcial["ticker"] = ticker
        parciais.append(parcial)

    if not parciais:
        logger.info("Nenhum dividendo encontrado para os tickers informados.")
        return _df_vazio()

    longo = pd.concat(parciais, ignore_index=True)

    # data_ex como date puro (não datetime tz-aware): granularidade é
    # diária e queremos a mesma chave que dim_tempo.data. Mesma conversão
    # que ingestion/download.py aplica em cotações, por consistência.
    longo["data_ex"] = pd.to_datetime(longo["data_ex"]).dt.date
    longo["valor_dividendo"] = longo["valor_dividendo"].astype("float64")

    longo = longo[COLUNAS_DIVIDENDOS].reset_index(drop=True)

    _logar_cobertura(longo, tickers)
    return longo


def _logar_cobertura(df: pd.DataFrame, tickers_pedidos: list[str]) -> None:
    """Loga estatísticas de cobertura para detectar tickers sem provento."""
    obtidos = set(df["ticker"].unique())
    vazios = sorted(set(tickers_pedidos) - obtidos)
    if vazios:
        logger.warning("Tickers sem dividendos no histórico: %s.", ", ".join(vazios))
    logger.info(
        "Download de dividendos concluído: %d proventos, %d tickers, datas %s → %s.",
        len(df),
        len(obtidos),
        df["data_ex"].min() if not df.empty else "—",
        df["data_ex"].max() if not df.empty else "—",
    )


def _df_vazio() -> pd.DataFrame:
    """DataFrame vazio com o schema de dividendos, para casos sem proventos."""
    return pd.DataFrame({c: pd.Series(dtype="object") for c in COLUNAS_DIVIDENDOS})
