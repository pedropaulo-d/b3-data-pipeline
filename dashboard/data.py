"""Camada de acesso a dados do dashboard.

Tudo aqui é **somente leitura** sobre os marts da Etapa 6. A conexão
DuckDB é aberta uma única vez (``@st.cache_resource``) e reusada; cada
query é cacheada (``@st.cache_data``) porque os marts são estáticos
durante a sessão — o Streamlit reexecuta o script inteiro a cada
interação, e sem cache cada clique reabriria o banco e re-rodaria SQL.

Decisão de conexão (Forma C, ver docs/decisoes.md): o dashboard lê só
marts (tabelas locais no .duckdb), então abre em ``read_only=True`` e
**não** chama ``configurar_s3`` — não toca no MinIO. Modo read-only
permite coexistir com outros leitores; só falha se houver um escritor
ativo (DAG/dbt) segurando o lock — tratado em ``app.py``.

Todas as queries são **parametrizadas** (placeholders ``?`` do DuckDB),
não f-strings com input — boa prática mesmo em read-only.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import streamlit as st

from warehouse.conexao import obter_conexao


@st.cache_resource
def obter_conexao_dashboard():
    """Abre (uma vez) o warehouse em modo somente leitura.

    Decorada com ``@st.cache_resource``: o Streamlit guarda a conexão e a
    reusa entre reruns e sessões, em vez de reabrir o arquivo a cada
    interação. Pode levantar ``duckdb.IOException`` se um escritor estiver
    com o lock — quem chama trata (ver ``app.py``).
    """
    return obter_conexao(read_only=True)


@st.cache_data
def listar_tickers() -> list[str]:
    """Tickers disponíveis (de ``dim_empresa``), para o seletor."""
    con = obter_conexao_dashboard()
    df = con.execute(
        "SELECT ticker FROM marts.dim_empresa ORDER BY ticker"
    ).fetchdf()
    return df["ticker"].tolist()


@st.cache_data
def intervalo_datas(ticker: str) -> tuple[dt.date, dt.date]:
    """(data_mínima, data_máxima) do ticker — dirige o filtro de período."""
    con = obter_conexao_dashboard()
    minimo, maximo = con.execute(
        """
        SELECT MIN(d.data), MAX(d.data)
        FROM marts.mart_indicadores_diarios AS d
        INNER JOIN marts.dim_empresa AS e ON d.empresa_id = e.empresa_id
        WHERE e.ticker = ?
        """,
        [ticker],
    ).fetchone()
    return minimo.date(), maximo.date()


@st.cache_data
def intervalo_serie() -> tuple[dt.date, dt.date]:
    """(data_mínima, data_máxima) GLOBAL da série, sobre todos os tickers.

    A Aba 2 (Comparação) tem um filtro de período próprio que vale para os
    6 tickers de uma vez, então a janela é ancorada no intervalo global —
    não no de um ticker específico (como faz :func:`intervalo_datas`).
    """
    con = obter_conexao_dashboard()
    minimo, maximo = con.execute(
        "SELECT MIN(data), MAX(data) FROM marts.mart_indicadores_diarios"
    ).fetchone()
    return minimo.date(), maximo.date()


@st.cache_data
def carregar_indicadores_diarios(
    ticker: str, data_inicio: dt.date, data_fim: dt.date
) -> pd.DataFrame:
    """Série diária de indicadores de mercado do ticker na janela.

    Resolve ticker→empresa_id via JOIN com ``dim_empresa``; a data já vive
    no próprio mart. Preserva NULL (NaN no DataFrame) dos primeiros
    pregões — não preenche com 0, para o Plotly desenhar lacunas.
    """
    con = obter_conexao_dashboard()
    return con.execute(
        """
        SELECT d.*
        FROM marts.mart_indicadores_diarios AS d
        INNER JOIN marts.dim_empresa AS e ON d.empresa_id = e.empresa_id
        WHERE e.ticker = ?
          AND d.data BETWEEN ? AND ?
        ORDER BY d.data
        """,
        [ticker, data_inicio, data_fim],
    ).fetchdf()


@st.cache_data
def carregar_dividend_yield(
    ticker: str, data_inicio: dt.date, data_fim: dt.date
) -> pd.DataFrame:
    """Série diária de dividend yield (trailing 12m) do ticker na janela."""
    con = obter_conexao_dashboard()
    return con.execute(
        """
        SELECT y.data, y.fechamento_bruto, y.dividendos_12m, y.dy_12m
        FROM marts.mart_dividend_yield AS y
        INNER JOIN marts.dim_empresa AS e ON y.empresa_id = e.empresa_id
        WHERE e.ticker = ?
          AND y.data BETWEEN ? AND ?
        ORDER BY y.data
        """,
        [ticker, data_inicio, data_fim],
    ).fetchdf()


@st.cache_data
def carregar_resumo(ticker: str) -> pd.Series:
    """Linha de ``mart_indicadores_resumo`` do ticker (cartões-resumo).

    Grão por ticker → exatamente 1 linha. Retorna como ``pd.Series`` para
    acesso por nome de coluna no ``app.py``.
    """
    con = obter_conexao_dashboard()
    df = con.execute(
        "SELECT * FROM marts.mart_indicadores_resumo WHERE ticker = ?",
        [ticker],
    ).fetchdf()
    return df.iloc[0]


@st.cache_data
def carregar_dy_atual(ticker: str) -> float | None:
    """Dividend yield 12m mais recente do ticker (cartão "DY atual").

    Independe do filtro de período: é sempre o último pregão disponível.
    Retorna ``None`` se o ticker não tiver linha de yield.
    """
    con = obter_conexao_dashboard()
    linha = con.execute(
        """
        SELECT y.dy_12m
        FROM marts.mart_dividend_yield AS y
        INNER JOIN marts.dim_empresa AS e ON y.empresa_id = e.empresa_id
        WHERE e.ticker = ?
        ORDER BY y.data DESC
        LIMIT 1
        """,
        [ticker],
    ).fetchone()
    return None if linha is None else linha[0]


# ===========================================================================
# Aba 2 — Comparação entre tickers
# ===========================================================================
# Diferença conceitual em relação à Aba 1 (registrada em docs/NOTAS.md):
# o `retorno_acumulado` do mart é medido desde o PRIMEIRO pregão da série
# (≈2021); ele responde "quanto rendeu desde sempre". A Aba 2 compara
# desempenho DENTRO da janela filtrada, então re-ancora o retorno no
# primeiro pregão da JANELA (FIRST_VALUE sobre o conjunto já filtrado pelo
# WHERE). Por isso estas queries recalculam — não leem retorno_acumulado
# nem mart_indicadores_resumo (que é histórico, não da janela).


@st.cache_data
def carregar_retorno_comparado(
    data_inicio: dt.date, data_fim: dt.date
) -> pd.DataFrame:
    """Série normalizada à base da janela, para os 6 tickers (long format).

    Re-ancora cada ticker no seu primeiro pregão DENTRO da janela: o
    ``FIRST_VALUE(...) OVER (PARTITION BY empresa_id ORDER BY data)`` é
    avaliado DEPOIS do ``WHERE`` (ordem de execução do SQL), então a base
    é o preço do primeiro dia filtrado — não o de 2021.

    Devolve as duas leituras equivalentes da mesma normalização, e o app
    escolhe qual plotar via toggle:

    - ``retorno_janela`` — fração vs base (0.0 no 1º dia da janela);
    - ``base_100`` — preço reescalado para começar em 100.

    Base de preço: fechamento ajustado (regra de domínio dos retornos).
    """
    con = obter_conexao_dashboard()
    return con.execute(
        """
        WITH normalizado AS (
            SELECT
                e.ticker,
                d.data,
                d.fechamento_ajustado
                    / FIRST_VALUE(d.fechamento_ajustado) OVER (
                          PARTITION BY d.empresa_id ORDER BY d.data
                      ) AS fator
            FROM marts.mart_indicadores_diarios AS d
            INNER JOIN marts.dim_empresa AS e ON d.empresa_id = e.empresa_id
            WHERE d.data BETWEEN ? AND ?
        )
        SELECT
            ticker,
            data,
            fator - 1   AS retorno_janela,
            fator * 100 AS base_100
        FROM normalizado
        ORDER BY ticker, data
        """,
        [data_inicio, data_fim],
    ).fetchdf()


@st.cache_data
def carregar_risco_retorno_periodo(
    data_inicio: dt.date, data_fim: dt.date
) -> pd.DataFrame:
    """Retorno e volatilidade DO PERÍODO, 1 linha por ticker (scatter).

    Agrega ``mart_indicadores_diarios`` sobre a janela filtrada:

    - ``retorno_periodo`` — preço do último pregão / preço do primeiro,
      ambos da janela. ``arg_max``/``arg_min`` pegam o fechamento ajustado
      na data máxima e mínima do grupo (mais limpo que FIRST/LAST_VALUE
      num contexto de agregação).
    - ``volatilidade_periodo`` — desvio-padrão amostral dos retornos log
      diários na janela, anualizado (×√252). Recalculado sobre a janela:
      a volatilidade do mart_resumo é a média das volatilidades de 30d ao
      longo de toda a série, número diferente do "risco da janela".

    Degrada graciosamente: ``STDDEV_SAMP`` exige ≥2 pontos; com 1 só
    devolve NULL (NaN no DataFrame), que o Plotly simplesmente não plota.
    """
    con = obter_conexao_dashboard()
    return con.execute(
        """
        SELECT
            e.ticker,
            arg_max(d.fechamento_ajustado, d.data)
                / arg_min(d.fechamento_ajustado, d.data) - 1 AS retorno_periodo,
            STDDEV_SAMP(d.retorno_log) * SQRT(252)           AS volatilidade_periodo
        FROM marts.mart_indicadores_diarios AS d
        INNER JOIN marts.dim_empresa AS e ON d.empresa_id = e.empresa_id
        WHERE d.data BETWEEN ? AND ?
        GROUP BY e.ticker
        ORDER BY e.ticker
        """,
        [data_inicio, data_fim],
    ).fetchdf()


@st.cache_data
def carregar_dy_atual_todos() -> pd.DataFrame:
    """Dividend yield 12m do último pregão de cada ticker (ranking).

    NÃO depende do filtro de período: é sempre o DY corrente.
    ``arg_max(dy_12m, data)`` devolve o DY na data mais recente em que ele
    está definido. Ordenado do maior para o menor (maior no topo do
    gráfico de barras horizontais).
    """
    con = obter_conexao_dashboard()
    return con.execute(
        """
        SELECT
            e.ticker,
            arg_max(y.dy_12m, y.data) AS dy_12m
        FROM marts.mart_dividend_yield AS y
        INNER JOIN marts.dim_empresa AS e ON y.empresa_id = e.empresa_id
        GROUP BY e.ticker
        ORDER BY dy_12m DESC NULLS LAST
        """
    ).fetchdf()


@st.cache_data
def carregar_tabela_comparativa() -> pd.DataFrame:
    """Resumo canônico por ticker (histórico completo, NÃO filtrado).

    Lê ``mart_indicadores_resumo`` (1 linha/ticker, agregado sobre TODA a
    série), enriquecido com o nome da empresa (``dim_empresa``) e o DY
    atual (subquery sobre ``mart_dividend_yield``). É a "ficha técnica"
    histórica de cada ativo — independente do filtro de período da aba.
    """
    con = obter_conexao_dashboard()
    return con.execute(
        """
        SELECT
            r.ticker,
            e.nome,
            r.retorno_acumulado_total,
            r.max_drawdown,
            r.volatilidade_media_30d,
            dy.dy_atual,
            r.total_pregoes
        FROM marts.mart_indicadores_resumo AS r
        INNER JOIN marts.dim_empresa AS e ON r.empresa_id = e.empresa_id
        LEFT JOIN (
            SELECT empresa_id, arg_max(dy_12m, data) AS dy_atual
            FROM marts.mart_dividend_yield
            GROUP BY empresa_id
        ) AS dy ON r.empresa_id = dy.empresa_id
        ORDER BY r.ticker
        """
    ).fetchdf()
