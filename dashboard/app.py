"""Dashboard B3 — entry point Streamlit (Etapa 7).

Rodar com:

    streamlit run dashboard/app.py

Pré-requisito: ``warehouse.duckdb`` populado (pipeline + dbt já rodados).

Duas abas:

- **Aba 1 — Visão Individual**: 1 ticker por vez, cartões-resumo e 5
  gráficos de série (preço/médias, retorno, volatilidade, drawdown, DY).
- **Aba 2 — Comparação**: os 6 tickers lado a lado — retorno comparado na
  janela (toggle base 100 / %), scatter risco×retorno, ranking de DY e
  tabela-resumo histórica com destaque de melhor/pior.

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

# Paleta qualitativa (Plotly "D3"). Mapeada por ticker em ordem alfabética
# para que a MESMA empresa tenha a MESMA cor em todos os gráficos da Aba 2
# (linha de retorno, ponto do scatter, barra de DY) — leitura cruzada.
_PALETA_TICKERS = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b",
]


def _cores_por_ticker(tickers: list[str]) -> dict[str, str]:
    """Mapa estável ticker→cor (ordem alfabética), reusado entre gráficos."""
    return {
        ticker: _PALETA_TICKERS[i % len(_PALETA_TICKERS)]
        for i, ticker in enumerate(sorted(tickers))
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
# Construtores de gráfico (Plotly) — Aba 2 (Comparação)
# ---------------------------------------------------------------------------
def grafico_retorno_comparado(
    df: pd.DataFrame, base_100: bool, cores: dict[str, str]
) -> go.Figure:
    """Desempenho dos tickers na janela: 1 linha por ticker, base comum.

    ``base_100=True`` plota o preço reescalado (começa em 100);
    ``False`` plota o retorno acumulado da janela em %. As duas leituras
    vêm da mesma normalização (ver ``data.carregar_retorno_comparado``).
    """
    fig = go.Figure()
    for ticker, grupo in df.groupby("ticker", sort=True):
        y = grupo["base_100"] if base_100 else grupo["retorno_janela"] * 100
        fig.add_trace(
            go.Scatter(
                x=grupo["data"], y=y, name=ticker,
                line=dict(width=1.5, color=cores.get(ticker)),
            )
        )
    # Linha de referência da base: 100 (base 100) ou 0% (retorno).
    fig.add_hline(
        y=100 if base_100 else 0, line=dict(dash="dot", width=1, color="gray")
    )
    fig.update_layout(
        title="Desempenho comparado na janela"
        + (" (base 100)" if base_100 else " (retorno acumulado)"),
        xaxis_title="Data",
        yaxis_title="Base 100" if base_100 else "Retorno acumulado (%)",
        hovermode="x unified", legend_title="Ticker",
    )
    return fig


def grafico_risco_retorno(df: pd.DataFrame, cores: dict[str, str]) -> go.Figure:
    """Scatter risco×retorno do período: 1 ponto rotulado por ticker."""
    fig = go.Figure(
        go.Scatter(
            x=df["volatilidade_periodo"] * 100,
            y=df["retorno_periodo"] * 100,
            mode="markers+text",
            text=df["ticker"],
            textposition="top center",
            marker=dict(
                size=13,
                color=[cores.get(t) for t in df["ticker"]],
                line=dict(width=1, color="white"),
            ),
            showlegend=False,
            hovertemplate=(
                "%{text}<br>Volatilidade: %{x:.1f}%"
                "<br>Retorno: %{y:.1f}%<extra></extra>"
            ),
        )
    )
    # Linha de retorno zero ajuda a separar quem subiu de quem caiu.
    fig.add_hline(y=0, line=dict(dash="dot", width=1, color="gray"))
    fig.update_layout(
        title="Risco × retorno (período filtrado)",
        xaxis_title="Volatilidade anualizada (%)",
        yaxis_title="Retorno do período (%)",
    )
    return fig


def grafico_ranking_dy(df: pd.DataFrame, cores: dict[str, str]) -> go.Figure:
    """Ranking de dividend yield atual: barras horizontais, maior no topo."""
    # Plotly empilha categorias de baixo para cima na ordem dada; ordenar
    # crescente deixa o maior DY no TOPO do gráfico.
    ordenado = df.sort_values("dy_12m", ascending=True)
    fig = go.Figure(
        go.Bar(
            x=ordenado["dy_12m"] * 100,
            y=ordenado["ticker"],
            orientation="h",
            marker_color=[cores.get(t) for t in ordenado["ticker"]],
            text=[
                "—" if pd.isna(v) else f"{v * 100:.2f}%"
                for v in ordenado["dy_12m"]
            ],
            textposition="auto",
            hovertemplate="%{y}: %{x:.2f}%<extra></extra>",
        )
    )
    fig.update_layout(
        title="Dividend yield atual (12m)",
        xaxis_title="Dividend yield (%)", yaxis_title="Ticker",
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
# Aba 2 — Comparação entre tickers
# ---------------------------------------------------------------------------
# Mapeamento e SENTIDO de cada métrica da tabela-resumo. A direção importa
# para colorir corretamente: em retorno e DY, maior é melhor; em drawdown,
# "melhor" é o MENOS negativo (mais perto de 0) → também maior; em
# volatilidade, menor é melhor. "Pregões" é informativo, não entra na cor.
_COLUNAS_TABELA_PT = {
    "ticker": "Ticker",
    "nome": "Empresa",
    "retorno_acumulado_total": "Retorno acumulado",
    "max_drawdown": "Máx. drawdown",
    "volatilidade_media_30d": "Volatilidade média (30d anual)",
    "dy_atual": "Dividend yield atual",
    "total_pregoes": "Pregões",
}

# Por coluna (já renomeada): True = maior é melhor (verde no máximo).
_DIRECAO_METRICA = {
    "Retorno acumulado": True,
    "Máx. drawdown": True,                      # menos negativo é melhor
    "Volatilidade média (30d anual)": False,    # menor é melhor
    "Dividend yield atual": True,
}

_FORMATO_TABELA = {
    "Retorno acumulado": "{:.1%}",
    "Máx. drawdown": "{:.1%}",
    "Volatilidade média (30d anual)": "{:.1%}",
    "Dividend yield atual": "{:.2%}",
    "Pregões": "{:.0f}",
}


def _estilo_melhor_pior(serie: pd.Series, maior_melhor: bool) -> list[str]:
    """Pinta a melhor célula de verde e a pior de vermelho na coluna.

    O sentido depende da métrica (``maior_melhor``): para retorno/DY/
    drawdown o melhor é o máximo; para volatilidade, o mínimo. NaN não é
    candidato a melhor nem pior.
    """
    validos = serie.dropna()
    estilos = [""] * len(serie)
    if validos.empty:
        return estilos
    melhor = validos.max() if maior_melhor else validos.min()
    pior = validos.min() if maior_melhor else validos.max()
    for i, valor in enumerate(serie):
        if pd.isna(valor):
            continue
        if valor == melhor:
            estilos[i] = "background-color: #1b5e20; color: white"
        elif valor == pior:
            estilos[i] = "background-color: #b71c1c; color: white"
    return estilos


def _estilizar_tabela_comparativa(df: pd.DataFrame):
    """Renomeia, formata percentuais e colore melhor/pior por métrica."""
    estilo = df.rename(columns=_COLUNAS_TABELA_PT).style.format(
        _FORMATO_TABELA, na_rep="—"
    )
    for coluna, maior_melhor in _DIRECAO_METRICA.items():
        estilo = estilo.apply(
            _estilo_melhor_pior,
            axis=0,
            subset=[coluna],
            maior_melhor=maior_melhor,
        )
    return estilo


def aba_comparacao(tickers: list[str]) -> None:
    """Filtro de período próprio + 4 componentes de comparação."""
    cores = _cores_por_ticker(tickers)
    minimo, maximo = data.intervalo_serie()

    # Filtro próprio da aba (não sincroniza com a Aba 1 — `key` distinta).
    opcao_periodo = st.radio(
        "Período", list(PERIODOS), index=1, horizontal=True,
        key="periodo_comparacao",
    )
    data_inicio = _data_inicio(opcao_periodo, minimo, maximo)
    data_fim = maximo

    # --- Componente 1: retorno comparado (respeita o filtro) ---------------
    modo = st.radio(
        "Escala", ["Retorno acumulado (%)", "Base 100"], index=0,
        horizontal=True, key="escala_retorno",
    )
    comparado = data.carregar_retorno_comparado(data_inicio, data_fim)
    if comparado.empty:
        st.warning("Sem dados de indicadores para o período selecionado.")
    else:
        st.plotly_chart(
            grafico_retorno_comparado(
                comparado, base_100=(modo == "Base 100"), cores=cores
            ),
            use_container_width=True,
        )

    # --- Componentes 2 e 3: scatter (filtrado) | ranking DY (atual) --------
    col_esq, col_dir = st.columns(2)
    with col_esq:
        risco = data.carregar_risco_retorno_periodo(data_inicio, data_fim)
        st.plotly_chart(grafico_risco_retorno(risco, cores), use_container_width=True)
    with col_dir:
        dy = data.carregar_dy_atual_todos()
        st.plotly_chart(grafico_ranking_dy(dy, cores), use_container_width=True)

    st.caption(
        f"Gráficos acima: janela desde {data_inicio:%d/%m/%Y}. "
        "O ranking de dividend yield usa sempre o último pregão (não filtrado)."
    )

    # --- Componente 4: tabela-resumo histórica (NÃO filtrada) --------------
    st.markdown("#### Resumo histórico por ticker")
    st.caption(
        f"Métricas sobre o histórico completo da série (desde "
        f"{minimo:%d/%m/%Y}), independente do filtro de período acima. "
        "Verde = melhor; vermelho = pior em cada métrica."
    )
    tabela = data.carregar_tabela_comparativa()
    st.dataframe(
        _estilizar_tabela_comparativa(tabela),
        use_container_width=True,
        hide_index=True,
    )


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

    aba_individual_tab, aba_comparacao_tab = st.tabs(
        ["Visão Individual", "Comparação"]
    )

    with aba_individual_tab:
        aba_visao_individual(tickers)

    with aba_comparacao_tab:
        aba_comparacao(tickers)


main()
