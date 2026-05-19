"""Conexão DuckDB persistente configurada para ler do MinIO.

O arquivo do banco (``warehouse.duckdb``) mora na raiz do repositório e
é regenerável: o conteúdo "fonte" é o raw layer no MinIO, e o que vive
dentro do .duckdb são apenas views e (a partir da Etapa 4) modelos dbt.

Toda a configuração de S3 acontece em uma única função pública —
:func:`obter_conexao` — para que notebooks, scripts e (no futuro) o
adapter dbt-duckdb usem exatamente o mesmo setup.
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
    """Retorna conexão DuckDB persistente configurada para ler do MinIO.

    Faz, em uma única sessão:

    - Abre (ou cria) o arquivo ``warehouse.duckdb`` na raiz do repo.
    - Instala e carrega a extensão ``httpfs`` — sem ela o DuckDB não
      consegue resolver chaves ``s3://``.
    - Aplica as configurações de S3 necessárias para falar com o MinIO:
      endpoint, credenciais, região, ``url_style='path'`` (obrigatório
      em endpoint sem DNS wildcard, como ``localhost``) e SSL on/off
      conforme o esquema do ``MINIO_ENDPOINT``.

    Args:
        read_only: Se ``True``, abre o arquivo em modo somente leitura.
            Útil para notebooks de apresentação onde não queremos
            mutar o estado por acidente. Default ``False`` para
            permitir ``CREATE SCHEMA`` / ``CREATE VIEW``.

    Returns:
        Conexão DuckDB pronta para uso. Cabe ao chamador fechar com
        ``con.close()`` ou usar em ``with``-statement.
    """
    host_porta, use_ssl = _normalizar_endpoint(MINIO_ENDPOINT)

    logger.info(
        "Abrindo warehouse DuckDB em %s (read_only=%s); endpoint S3=%s (ssl=%s).",
        CAMINHO_WAREHOUSE,
        read_only,
        host_porta,
        use_ssl,
    )

    con = duckdb.connect(database=str(CAMINHO_WAREHOUSE), read_only=read_only)

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

    return con
