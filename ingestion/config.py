"""Configuração estática da ingestão.

Centraliza tickers, sufixos, paths e janela histórica. Nenhum outro módulo
do pacote deve declarar essas constantes — assim, mudar de 6 tickers para
80, ou de 5 anos para 10, é alterar este arquivo apenas.

Os paths são resolvidos relativamente à **raiz do repositório** (e não ao
`cwd` em que o comando foi disparado). Isso evita que rodar `python -m
ingestion.main` de dentro de um subdiretório quebre o caminho de gravação.
"""

from datetime import date, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Escopo travado do projeto (ver CLAUDE.md > Escopo travado)
# ---------------------------------------------------------------------------

TICKERS: list[str] = [
    "PETR4",
    "VALE3",
    "ITUB4",
    "BBDC4",
    "WEGE3",
    "ABEV3",
]

# Sufixo exigido pelo yfinance para identificar ações listadas na B3.
SUFIXO_B3: str = ".SA"


def ticker_yfinance(ticker: str) -> str:
    """Converte um ticker B3 para a forma aceita pelo yfinance.

    Exemplo: ``ticker_yfinance("PETR4")`` retorna ``"PETR4.SA"``.

    Args:
        ticker: Código do ativo na B3, sem sufixo (ex.: ``"PETR4"``).

    Returns:
        Ticker com o sufixo ``.SA`` apropriado para o yfinance.
    """
    return f"{ticker}{SUFIXO_B3}"


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# Este arquivo vive em `<repo>/ingestion/config.py`. Subir dois níveis dá a
# raiz do repositório, independentemente de onde o comando foi disparado.
RAIZ_REPO: Path = Path(__file__).resolve().parent.parent

# Destino das partições do raw layer.
# Layout final: data/raw/cotacoes/ano=YYYY/mes=MM/dia=DD/cotacoes.parquet
RAW_PATH: Path = RAIZ_REPO / "data" / "raw" / "cotacoes"


# ---------------------------------------------------------------------------
# Janela histórica
# ---------------------------------------------------------------------------

# Janela inicial fixada em 5 anos (ver CLAUDE.md > Escopo travado).
ANOS_HISTORICO_INICIAL: int = 5

# Data de corte para a carga inicial: hoje menos `ANOS_HISTORICO_INICIAL` anos.
# Resolvida em tempo de import; em pipelines orquestrados isso pode ficar
# "preso" em uma data antiga se o processo for de longa duração — para a
# nossa CLI de execução pontual, é seguro.
DATA_INICIO_HISTORICO: date = date.today() - timedelta(days=365 * ANOS_HISTORICO_INICIAL)


# ---------------------------------------------------------------------------
# Schema do Parquet final
# ---------------------------------------------------------------------------

# Ordem e nomes das colunas no DataFrame "long" gravado em Parquet.
# Usado também por `download.py` para validar o resultado antes de salvar.
COLUNAS_SAIDA: list[str] = [
    "data",
    "ticker",
    "abertura",
    "maxima",
    "minima",
    "fechamento",
    "fechamento_ajustado",
    "volume",
]
