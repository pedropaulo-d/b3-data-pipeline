"""Download de cotações via yfinance.

Encapsula a chamada ao ``yfinance.download`` e devolve o dado em formato
"long" (uma linha por ``ticker × data``), pronto para particionamento por
data. O caller não precisa entender o multi-index estranho que o yfinance
retorna com múltiplos tickers.

Decisões refletidas neste módulo (registradas em ``docs/decisoes.md``):

- ``auto_adjust=False`` para preservar **bruto** (``Close``) e **ajustado**
  (``Adj Close``) lado a lado no raw layer. Isso garante imutabilidade do
  raw e permite recalcular ajustes depois sem re-baixar.
- ``threads=True`` acelera carga inicial; ``progress=False`` evita poluir
  stdout (preferimos ``logging``).
- ``group_by="ticker"`` produz colunas no nível ``(ticker, métrica)``, o que
  facilita o ``stack`` para formato long.
"""

import logging
from datetime import date, timedelta

import pandas as pd
import yfinance as yf

from ingestion.config import COLUNAS_SAIDA, SUFIXO_B3, ticker_yfinance

logger = logging.getLogger(__name__)


# Mapa nome-do-yfinance → nome-canônico-do-projeto.
# Mantido aqui (e não em config.py) porque é detalhe da fonte yfinance,
# não da modelagem do projeto.
_RENOMEACAO_COLUNAS: dict[str, str] = {
    "Open": "abertura",
    "High": "maxima",
    "Low": "minima",
    "Close": "fechamento",
    "Adj Close": "fechamento_ajustado",
    "Volume": "volume",
}


def baixar_cotacoes(
    tickers: list[str],
    inicio: date,
    fim: date,
) -> pd.DataFrame:
    """Baixa cotações de múltiplos tickers em um intervalo de datas.

    O intervalo segue a convenção do yfinance: ``start`` inclusivo, ``end``
    **exclusivo**. Para simplificar o caller, esta função recebe ``fim``
    como inclusivo e soma 1 dia internamente.

    Args:
        tickers: Lista de tickers B3 sem sufixo (ex.: ``["PETR4", "VALE3"]``).
        inicio: Primeira data desejada (inclusiva).
        fim: Última data desejada (inclusiva).

    Returns:
        DataFrame "long" com as colunas definidas em
        :data:`ingestion.config.COLUNAS_SAIDA`. Linhas referentes a feriados,
        fins de semana ou tickers sem dado no período simplesmente não
        aparecem (o yfinance omite, e isso é o comportamento esperado para
        o raw layer).

    Raises:
        ValueError: Se ``tickers`` estiver vazio, se ``inicio > fim``, ou se
            o DataFrame resultante não conformar com o schema esperado.
    """
    if not tickers:
        raise ValueError("Lista de tickers vazia.")
    if inicio > fim:
        raise ValueError(
            f"Intervalo inválido: inicio ({inicio}) é posterior a fim ({fim})."
        )

    tickers_yf = [ticker_yfinance(t) for t in tickers]

    logger.info(
        "Baixando cotações: %d tickers, período %s → %s.",
        len(tickers_yf),
        inicio.isoformat(),
        fim.isoformat(),
    )

    # yfinance trata `end` como exclusivo; ajustamos para que `fim` seja
    # inclusivo do ponto de vista do caller.
    bruto = yf.download(
        tickers=tickers_yf,
        start=inicio.isoformat(),
        end=(fim + timedelta(days=1)).isoformat(),
        auto_adjust=False,
        progress=False,
        group_by="ticker",
        threads=True,
    )

    if bruto is None or bruto.empty:
        logger.info(
            "yfinance retornou vazio (provável feriado/fim de semana ou intervalo sem pregão)."
        )
        return _df_vazio()

    longo = _para_formato_long(bruto, tickers)

    _validar_schema(longo)

    _logar_cobertura(longo, tickers)
    return longo


def _para_formato_long(bruto: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    """Converte o DataFrame multi-index do yfinance para formato long.

    Com ``group_by="ticker"`` e múltiplos tickers, o yfinance devolve
    colunas no nível ``(TICKER.SA, métrica)``. Usamos ``stack`` no nível 0
    para empilhar tickers como linhas. Quando há um único ticker, o
    yfinance retorna colunas planas — esse caso é tratado separadamente
    para manter o resultado uniforme.
    """
    if isinstance(bruto.columns, pd.MultiIndex):
        # future_stack=True usa o algoritmo novo do pandas e silencia o
        # FutureWarning sobre mudança de comportamento padrão.
        empilhado = bruto.stack(level=0, future_stack=True).reset_index()
        empilhado = empilhado.rename(columns={"Date": "data", "Ticker": "ticker"})
    else:
        # Caso de ticker único: sem multi-index. Reconstruímos a coluna ticker.
        if len(tickers) != 1:
            raise ValueError(
                "yfinance devolveu colunas planas com múltiplos tickers — "
                "estado inesperado."
            )
        empilhado = bruto.reset_index().rename(columns={"Date": "data"})
        empilhado["ticker"] = ticker_yfinance(tickers[0])

    # Renomeia colunas de métricas para a forma canônica em português.
    empilhado = empilhado.rename(columns=_RENOMEACAO_COLUNAS)

    # Remove o sufixo .SA para que o raw layer carregue apenas o ticker B3.
    empilhado["ticker"] = empilhado["ticker"].str.removesuffix(SUFIXO_B3)

    # Normaliza tipos:
    # - data como date (não datetime; granularidade é diária);
    # - preços como float64 (yfinance já entrega assim, garantimos);
    # - volume como Int64 (nullable do pandas; preserva NaN para indicar
    #   "desconhecido", não convertido para 0 — ver docs/decisoes.md).
    empilhado["data"] = pd.to_datetime(empilhado["data"]).dt.date

    # Remove linhas totalmente vazias de OHLC (acontecem quando um ticker
    # ainda não estava listado no início do intervalo, por exemplo).
    cols_preco = ["abertura", "maxima", "minima", "fechamento", "fechamento_ajustado"]
    empilhado = empilhado.dropna(subset=cols_preco, how="all")

    for c in cols_preco:
        empilhado[c] = empilhado[c].astype("float64")

    empilhado["volume"] = empilhado["volume"].astype("Int64")

    # Mantém apenas as colunas finais, na ordem definida em config.
    empilhado = empilhado[COLUNAS_SAIDA].reset_index(drop=True)
    return empilhado


def _validar_schema(df: pd.DataFrame) -> None:
    """Valida que o DataFrame final segue o schema do raw layer.

    Validação leve, no nível de presença de colunas e tipos. Validação de
    qualidade (faixas, nulos por coluna, dedupe) fica para a Etapa 4 (dbt
    tests).
    """
    faltando = set(COLUNAS_SAIDA) - set(df.columns)
    if faltando:
        raise ValueError(
            f"Colunas faltando no resultado da ingestão: {sorted(faltando)}."
        )

    if list(df.columns) != COLUNAS_SAIDA:
        raise ValueError(
            f"Ordem de colunas inesperada: {list(df.columns)} "
            f"(esperado {COLUNAS_SAIDA})."
        )

    if df.empty:
        return  # Schema OK; só não tem linhas (intervalo sem pregão).

    if not df["data"].map(type).eq(date).all():
        raise ValueError(
            "Coluna 'data' contém valores que não são datetime.date."
        )

    if df["ticker"].str.endswith(SUFIXO_B3).any():
        raise ValueError(
            f"Coluna 'ticker' contém sufixo {SUFIXO_B3!r}; deveria estar "
            "removido no raw layer."
        )


def _logar_cobertura(df: pd.DataFrame, tickers_pedidos: list[str]) -> None:
    """Loga estatísticas de cobertura para detectar tickers sem dado."""
    obtidos = set(df["ticker"].unique())
    pedidos = set(tickers_pedidos)
    vazios = sorted(pedidos - obtidos)
    if vazios:
        logger.warning(
            "Tickers sem dado no período: %s. "
            "(Pode ser ausência de pregão ou ticker ainda não listado.)",
            ", ".join(vazios),
        )
    logger.info(
        "Download concluído: %d linhas, %d tickers com dado, datas %s → %s.",
        len(df),
        len(obtidos),
        df["data"].min() if not df.empty else "—",
        df["data"].max() if not df.empty else "—",
    )


def _df_vazio() -> pd.DataFrame:
    """DataFrame vazio com o schema correto, para casos sem pregão."""
    return pd.DataFrame({c: pd.Series(dtype="object") for c in COLUNAS_SAIDA})
