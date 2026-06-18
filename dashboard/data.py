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
