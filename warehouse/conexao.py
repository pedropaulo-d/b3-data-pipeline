"""Conexão DuckDB persistente e configuração de acesso ao MinIO.

O arquivo do banco (``warehouse.duckdb``) mora na raiz do repositório e
é regenerável: o conteúdo "fonte" é o raw layer no MinIO, e o que vive
dentro do .duckdb são apenas views e (a partir da Etapa 4) modelos dbt.

Duas responsabilidades **independentes**, em funções separadas:

- :func:`obter_conexao` — apenas abre o ``warehouse.duckdb`` no modo
  pedido (escrita ou somente leitura). Não toca em S3.
- :func:`configurar_s3` — recebe uma conexão já aberta e instala/carrega
  ``httpfs`` + configura o cliente S3 embutido para falar com o MinIO.

Quem só lê tabelas/marts locais abre em ``read_only=True`` e dispensa o
setup de S3. Quem lê as views ``raw.*`` (que apontam para o MinIO via
``read_parquet('s3://...')``) chama ``configurar_s3`` depois de abrir.
"""

import logging
from pathlib import Path
from urllib.parse import urlparse

import duckdb

from ingestion.config import (
    MINIO_ACCESS_KEY,
    MINIO_ENDPOINT,
    MINIO_REGION,
    MINIO_SECRET_KEY,
)

logger = logging.getLogger(__name__)


# Mesmo padrão usado em `ingestion/config.py`: subir dois níveis a partir
# deste arquivo dá a raiz do repositório, independentemente do CWD.
RAIZ_REPO: Path = Path(__file__).resolve().parent.parent

# Caminho fixo do arquivo .duckdb. Gitignored (ver .gitignore).
CAMINHO_WAREHOUSE: Path = RAIZ_REPO / "warehouse.duckdb"


def _normalizar_endpoint(endpoint: str) -> tuple[str, bool]:
    """Separa esquema (http/https) e host:porta do endpoint do .env.

    O ``s3_endpoint`` do DuckDB aceita apenas ``host:porta`` (sem
    esquema); o uso ou não de TLS é controlado por ``s3_use_ssl``.
    Já o ``MINIO_ENDPOINT`` do .env, por consistência com boto3 e
    com o que aparece em documentação de S3, vem como URL completa
    (``http://localhost:9000``).

    Returns:
        Tupla ``(host_porta, use_ssl)``.
    """
    parsed = urlparse(endpoint)
    if parsed.scheme in ("http", "https"):
        host_porta = parsed.netloc
        use_ssl = parsed.scheme == "https"
    else:
        # Endpoint já veio sem esquema (ex.: "localhost:9000"). Assume
        # HTTP, que é o padrão do MinIO local.
        host_porta = endpoint
        use_ssl = False
    if not host_porta:
        raise ValueError(
            f"MINIO_ENDPOINT inválido: {endpoint!r}. "
            "Esperado algo como 'http://localhost:9000'."
        )
    return host_porta, use_ssl


def obter_conexao(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Abre o ``warehouse.duckdb`` no modo pedido. Não configura S3.

    Responsabilidade única: abrir (ou criar) o arquivo do banco. Para
    ler as views ``raw.*`` (que apontam para o MinIO), chame
    :func:`configurar_s3` na conexão retornada.

    Args:
        read_only: Se ``True``, abre em modo somente leitura — vários
            leitores podem coexistir (ex.: o dashboard da Etapa 7 lendo
            enquanto a DAG escreve). Se ``False`` (default), abre em
            escrita exclusiva, necessário para ``CREATE SCHEMA`` /
            ``CREATE VIEW`` / materializações do dbt.

    Returns:
        Conexão DuckDB aberta. Cabe ao chamador fechar com
        ``con.close()`` ou usar em ``with``-statement.
    """
    logger.info(
        "Abrindo warehouse DuckDB em %s (read_only=%s).",
        CAMINHO_WAREHOUSE,
        read_only,
    )
    return duckdb.connect(database=str(CAMINHO_WAREHOUSE), read_only=read_only)


def configurar_s3(con: duckdb.DuckDBPyConnection) -> None:
    """Configura ``httpfs`` + cliente S3 da conexão para falar com o MinIO.

    Aplica, na conexão recebida:

    - ``INSTALL httpfs`` / ``LOAD httpfs`` — sem a extensão o DuckDB não
      resolve chaves ``s3://``.
    - ``SET s3_*`` — endpoint, credenciais, região, ``url_style='path'``
      (obrigatório em endpoint sem DNS wildcard, como ``localhost``) e
      SSL on/off conforme o esquema do ``MINIO_ENDPOINT``.

    As credenciais vêm de :mod:`ingestion.config` (mesma fonte do boto3
    da ingestão) — não são duplicadas nem hardcodadas aqui.

    Necessária só para quem lê as views ``raw.*``; quem consulta apenas
    tabelas/marts locais pode dispensá-la. Funciona tanto em conexão de
    escrita quanto de leitura: ``LOAD``/``SET`` de S3 são estado de
    sessão, não mutação do arquivo, então rodam em ``read_only=True``
    (verificado empiricamente no DuckDB do projeto).

    Args:
        con: Conexão aberta por :func:`obter_conexao`.
    """
    host_porta, use_ssl = _normalizar_endpoint(MINIO_ENDPOINT)

    logger.info("Configurando S3 na conexão; endpoint=%s (ssl=%s).", host_porta, use_ssl)

    # httpfs: extensão que adiciona suporte a s3://, gcs:// e https://.
    # `INSTALL` baixa o binário uma vez (cache em ~/.duckdb/extensions);
    # `LOAD` carrega na conexão atual.
    con.execute("INSTALL httpfs")
    con.execute("LOAD httpfs")

    # Cada SET abaixo configura uma faceta do cliente S3 embutido do
    # DuckDB. Os nomes seguem o padrão da AWS, exceto `s3_url_style`
    # que é específico do DuckDB.
    con.execute("SET s3_endpoint = ?", [host_porta])
    con.execute("SET s3_use_ssl = ?", [use_ssl])
    con.execute("SET s3_url_style = 'path'")
    con.execute("SET s3_access_key_id = ?", [MINIO_ACCESS_KEY])
    con.execute("SET s3_secret_access_key = ?", [MINIO_SECRET_KEY])
    con.execute("SET s3_region = ?", [MINIO_REGION])
