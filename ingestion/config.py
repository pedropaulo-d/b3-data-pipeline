"""Configuração estática da ingestão.

Centraliza tickers, sufixos, janela histórica e parâmetros do object
storage. Nenhum outro módulo do pacote deve declarar essas constantes
— assim, mudar de 6 tickers para 80, de 5 anos para 10, ou trocar o
endpoint do MinIO, é alterar este arquivo apenas.

A partir da Etapa 2 o raw layer mora **exclusivamente no MinIO**
(bucket ``b3-data``, prefixo ``raw/cotacoes``). Variáveis de conexão
são lidas do ``.env`` na raiz do repositório (via ``python-dotenv``)
no momento do import — falha cedo e com mensagem clara se algo estiver
faltando.
"""

import os
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# Paths de filesystem (apenas para localizar o .env)
# ---------------------------------------------------------------------------

# Este arquivo vive em `<repo>/ingestion/config.py`. Subir dois níveis dá a
# raiz do repositório, independentemente de onde o comando foi disparado.
RAIZ_REPO: Path = Path(__file__).resolve().parent.parent

# Carrega o .env uma única vez, no import deste módulo. Demais módulos
# do pacote acessam só as constantes daqui — não chamam load_dotenv de novo.
load_dotenv(dotenv_path=RAIZ_REPO / ".env")


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
# MinIO / S3 — Etapa 2
# ---------------------------------------------------------------------------


def _exigir_var(nome: str) -> str:
    """Lê uma variável de ambiente obrigatória ou levanta RuntimeError claro."""
    valor = os.environ.get(nome)
    if not valor:
        raise RuntimeError(
            f"Variável de ambiente obrigatória ausente: {nome}. "
            "Configure seu .env (veja .env.example) antes de rodar a ingestão."
        )
    return valor


MINIO_ENDPOINT: str = _exigir_var("MINIO_ENDPOINT")
MINIO_ACCESS_KEY: str = _exigir_var("MINIO_ACCESS_KEY")
MINIO_SECRET_KEY: str = _exigir_var("MINIO_SECRET_KEY")
MINIO_BUCKET: str = os.environ.get("MINIO_BUCKET", "b3-data")
MINIO_REGION: str = os.environ.get("MINIO_REGION", "us-east-1")

# Prefixo do raw layer dentro do bucket. Camadas futuras (staging/, marts/)
# entram em etapas seguintes; aqui só registramos a convenção.
RAW_PREFIX: str = "raw/cotacoes"


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
