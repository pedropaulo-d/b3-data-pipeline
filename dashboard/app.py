"""Dashboard B3 — entry point Streamlit (Etapa 7).

Rodar com:

    streamlit run dashboard/app.py

Pré-requisito: ``warehouse.duckdb`` populado (pipeline + dbt já rodados).

Esta rodada implementa apenas a **Aba 1 — Visão Individual**. A estrutura
de abas já deixa o lugar da "Comparação" (Aba 2), implementada depois.

O Streamlit reexecuta este script a cada interação; o estado pesado
(conexão, queries) é cacheado em ``dashboard/data.py``.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

# O Streamlit executa este arquivo como SCRIPT standalone (não como módulo
# do pacote `dashboard`): ele coloca a própria pasta `dashboard/` no início
# do sys.path, mas NÃO a raiz do projeto. Resultado: nem o pacote
# `dashboard` nem o `warehouse` (na raiz) são importáveis por padrão.
# Inserir a raiz resolve os dois casos de uma vez — o import irmão
# `import data` (mesma pasta) e o `from warehouse.conexao import ...`
# que roda dentro de data.py. Tem de vir ANTES de `import data`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import duckdb
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import data

# ---------------------------------------------------------------------------
# Configuração da página
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Dashboard B3",
    page_icon="📈",
    layout="wide",
)

# Opções do filtro de período → nº de meses para trás (None = série toda).
PERIODOS: dict[str, int | None] = {
    "6 meses": 6,
    "1 ano": 12,
    "2 anos": 24,
    "Tudo": None,
}


def _data_inicio(opcao: str, minimo: dt.date, maximo: dt.date) -> dt.date:
    """Converte a opção de período na data inicial da janela.

    "Tudo" usa o primeiro pregão; as demais recuam N meses a partir do
    último pregão, sem passar do início real da série.
    """
    meses = PERIODOS[opcao]
    if meses is None:
        return minimo
    inicio = (pd.Timestamp(maximo) - pd.DateOffset(months=meses)).date()
    return max(inicio, minimo)


# ---------------------------------------------------------------------------
# Construtores de gráfico (Plotly). NaN dos primeiros pregões vira lacuna —
# não preenchemos com 0. Percentuais são multiplicados por 100 na exibição.
# ---------------------------------------------------------------------------
def grafico_preco_medias(df: pd.DataFrame, ticker: str) -> go.Figure:
    """Fechamento ajustado + médias móveis (7/30/90/200 pregões)."""
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["data"], y=df["fechamento_ajustado"],
            name="Fechamento ajustado", line=dict(width=2, color="#1f77b4"),
        )
    )
    medias = [
        ("media_movel_7d", "MM 7", "#ff7f0e"),
        ("media_movel_30d", "MM 30", "#2ca02c"),
        ("media_movel_90d", "MM 90", "#d62728"),
        ("media_movel_200d", "MM 200", "#9467bd"),
    ]
    for coluna, rotulo, cor in medias:
        fig.add_trace(
            go.Scatter(
                x=df["data"], y=df[coluna], name=rotulo,
                line=dict(width=1, color=cor),
            )
        )
    fig.update_layout(
        title=f"Preço e médias móveis — {ticker}",
        xaxis_title="Data", yaxis_title="Preço (R$)",
        hovermode="x unified", legend_title="Série",
    )
    return fig


def grafico_retorno_acumulado(df: pd.DataFrame, ticker: str) -> go.Figure:
    """Retorno acumulado vs primeiro pregão da janela (%)."""
    fig = go.Figure(
        go.Scatter(
            x=df["data"], y=df["retorno_acumulado"] * 100,
            name="Retorno acumulado", line=dict(width=2, color="#1f77b4"),
            fill="tozeroy",
        )
    )
    fig.update_layout(
        title=f"Retorno acumulado — {ticker}",
        xaxis_title="Data", yaxis_title="Retorno acumulado (%)",
        hovermode="x unified",
    )
    return fig


def grafico_volatilidade(df: pd.DataFrame, ticker: str) -> go.Figure:
    """Volatilidade anualizada (30d/90d/252d), em %."""
    fig = go.Figure()
    series = [
        ("volatilidade_30d_anual", "30 dias", "#1f77b4"),
        ("volatilidade_90d_anual", "90 dias", "#2ca02c"),
        ("volatilidade_252d_anual", "252 dias", "#d62728"),
    ]
    for coluna, rotulo, cor in series:
        fig.add_trace(
            go.Scatter(
                x=df["data"], y=df[coluna] * 100, name=rotulo,
                line=dict(width=1.5, color=cor),
            )
        )
    fig.update_layout(
        title=f"Volatilidade anualizada — {ticker}",
        xaxis_title="Data", yaxis_title="Volatilidade anual (%)",
        hovermode="x unified", legend_title="Janela",
    )
    return fig


def grafico_drawdown(df: pd.DataFrame, ticker: str) -> go.Figure:
    """Drawdown desde o pico histórico (%, sempre ≤ 0)."""
    fig = go.Figure(
        go.Scatter(
            x=df["data"], y=df["drawdown"] * 100,
            name="Drawdown", line=dict(width=1.5, color="#d62728"),
            fill="tozeroy",
        )
    )
    fig.update_layout(
        title=f"Drawdown — {ticker}",
        xaxis_title="Data", yaxis_title="Drawdown (%)",
        hovermode="x unified",
    )
    return fig


def grafico_dividend_yield(df: pd.DataFrame, ticker: str) -> go.Figure:
    """Dividend yield trailing 12m ao longo do tempo (%)."""
    fig = go.Figure(
        go.Scatter(
            x=df["data"], y=df["dy_12m"] * 100,
            name="DY 12m", line=dict(width=2, color="#2ca02c"),
        )
    )
    fig.update_layout(
        title=f"Dividend yield (12m) — {ticker}",
        xaxis_title="Data", yaxis_title="Dividend yield (%)",
        hovermode="x unified",
    )
    return fig


# ---------------------------------------------------------------------------
# Aba 1 — Visão Individual
# ---------------------------------------------------------------------------
def _formatar_pct(valor: float | None, casas: int = 1) -> str:
    """Formata fração (0.07) como percentual ('7.0%'); '—' se ausente."""
    if valor is None or pd.isna(valor):
        return "—"
    return f"{valor * 100:.{casas}f}%"


def aba_visao_individual(tickers: list[str]) -> None:
    """Seletor de ticker/período, cartões-resumo e os 5 gráficos."""
    col_ticker, col_periodo = st.columns([1, 2])
    with col_ticker:
        ticker = st.selectbox("Ticker", tickers, index=0)
    with col_periodo:
        opcao_periodo = st.radio(
            "Período", list(PERIODOS), index=1, horizontal=True
        )

    minimo, maximo = data.intervalo_datas(ticker)
    data_inicio = _data_inicio(opcao_periodo, minimo, maximo)
    data_fim = maximo

    # --- Cartões-resumo ----------------------------------------------------
    resumo = data.carregar_resumo(ticker)
    dy_atual = data.carregar_dy_atual(ticker)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Retorno acumulado", _formatar_pct(resumo["retorno_acumulado_total"]))
    c2.metric("Máx. drawdown", _formatar_pct(resumo["max_drawdown"]))
    c3.metric("Volatilidade média (30d anual)", _formatar_pct(resumo["volatilidade_media_30d"]))
    c4.metric("Dividend yield atual", _formatar_pct(dy_atual, casas=2))

    st.caption(
        f"Série: {minimo:%d/%m/%Y} a {maximo:%d/%m/%Y} · "
        f"{int(resumo['total_pregoes'])} pregões · "
        f"janela exibida desde {data_inicio:%d/%m/%Y}"
    )

    # --- Gráficos ----------------------------------------------------------
    diarios = data.carregar_indicadores_diarios(ticker, data_inicio, data_fim)
    yield_df = data.carregar_dividend_yield(ticker, data_inicio, data_fim)

    if diarios.empty:
        st.warning("Sem dados de indicadores para o ticker/período selecionado.")
        return

    st.plotly_chart(grafico_preco_medias(diarios, ticker), use_container_width=True)

    col_a, col_b = st.columns(2)
    with col_a:
        st.plotly_chart(grafico_retorno_acumulado(diarios, ticker), use_container_width=True)
    with col_b:
        st.plotly_chart(grafico_volatilidade(diarios, ticker), use_container_width=True)

    col_c, col_d = st.columns(2)
    with col_c:
        st.plotly_chart(grafico_drawdown(diarios, ticker), use_container_width=True)
    with col_d:
        if yield_df.empty:
            st.info("Sem histórico de dividend yield para o período.")
        else:
            st.plotly_chart(grafico_dividend_yield(yield_df, ticker), use_container_width=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    st.title("📈 Dashboard B3 — Indicadores de mercado")

    # Abrir o warehouse pode falhar se um escritor (DAG/dbt) estiver com o
    # lock. Tratamos graciosamente em vez de estourar stack trace.
    try:
        tickers = data.listar_tickers()
    except (duckdb.Error, OSError) as exc:
        st.error(
            "⚠️ Não foi possível abrir o warehouse agora. Ele pode estar "
            "sendo atualizado pelo pipeline (DAG do Airflow ou `dbt build`). "
            "Tente novamente em alguns instantes."
        )
        st.caption(f"Detalhe técnico: {exc}")
        st.stop()

    aba_individual, aba_comparacao = st.tabs(["Visão Individual", "Comparação"])

    with aba_individual:
        aba_visao_individual(tickers)

    with aba_comparacao:
        # Aba 2 — implementada na próxima rodada (comparação entre tickers).
        st.info("🚧 Em construção — comparação entre tickers chega na próxima rodada.")


main()
