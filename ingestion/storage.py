"""Persistência do DataFrame em Parquet particionado por data no MinIO.

A partir da Etapa 2, o raw layer mora **exclusivamente em object storage**
(MinIO local, compatível S3). O layout do bucket reproduz exatamente o
que existia em filesystem na Etapa 1:

    s3://b3-data/raw/cotacoes/ano=YYYY/mes=MM/dia=DD/cotacoes.parquet

Decisões refletidas neste módulo (registradas em ``docs/decisoes.md``):

- **boto3 direto** em vez de ``s3fs`` ou ``pyarrow.fs.S3FileSystem``:
  cliente oficial AWS, é o que aparece em vaga e demonstra entendimento
  do protocolo S3.
- **Buffer em memória** (``io.BytesIO``) com ``df.to_parquet`` +
  ``put_object``: simples e suficiente para os volumes do projeto. Sem
  upload multipart aqui — cada objeto tem alguns KB.
- **Sobrescrita silenciosa**: ``put_object`` no S3 substitui o objeto se
  a chave já existir. É a base da idempotência semântica do raw.
"""

import io
import logging
from datetime import date

import pandas as pd
from botocore.exceptions import ClientError, EndpointConnectionError

from ingestion.config import (
    COLUNAS_SAIDA,
    MINIO_BUCKET,
    MINIO_ENDPOINT,
    RAW_PREFIX,
)
from ingestion.s3_client import criar_cliente_s3

logger = logging.getLogger(__name__)


def salvar_particionado(df: pd.DataFrame) -> int:
    """Grava o DataFrame "long" em Parquet particionado por data no MinIO.

    Para cada data presente em ``df["data"]``, escreve um objeto no
    bucket configurado seguindo o esquema
    ``raw/cotacoes/ano=YYYY/mes=MM/dia=DD/cotacoes.parquet``. Objetos
    pré-existentes são sobrescritos (idempotência semântica garantida —
    ver ``docs/decisoes.md``).

    Args:
        df: DataFrame no formato long produzido por
            :func:`ingestion.download.baixar_cotacoes`.

    Returns:
        Número de objetos efetivamente escritos (igual ao número de
        datas únicas em ``df``).

    Raises:
        ValueError: Se ``df`` não tiver o schema esperado.
        RuntimeError: Se o MinIO estiver inacessível, ou se o S3
            retornar erro na chamada de upload.
    """
    if list(df.columns) != COLUNAS_SAIDA:
        raise ValueError(
            f"Schema inesperado em salvar_particionado: {list(df.columns)} "
            f"(esperado {COLUNAS_SAIDA})."
        )

    if df.empty:
        logger.info("DataFrame vazio — nada a gravar.")
        return 0

    s3 = criar_cliente_s3()

    objetos_escritos = 0
    for data_pregao, grupo in df.groupby("data", sort=True):
        chave = _chave_particao(data_pregao)
        buffer = io.BytesIO()
        grupo.to_parquet(
            buffer,
            engine="pyarrow",
            compression="snappy",
            index=False,
        )
        buffer.seek(0)

        try:
            s3.put_object(
                Bucket=MINIO_BUCKET,
                Key=chave,
                Body=buffer.getvalue(),
            )
        except EndpointConnectionError as exc:
            raise RuntimeError(
                f"MinIO inacessível em {MINIO_ENDPOINT}. Verifique que o "
                "serviço está rodando: "
                "`docker compose up -d minio mc-init`."
            ) from exc
        except ClientError as exc:
            codigo = exc.response.get("Error", {}).get("Code", "desconhecido")
            raise RuntimeError(
                f"Erro do S3 ao gravar s3://{MINIO_BUCKET}/{chave} "
                f"(código={codigo}): {exc}."
            ) from exc

        logger.info(
            "Gravado s3://%s/%s (%d linhas).",
            MINIO_BUCKET,
            chave,
            len(grupo),
        )
        objetos_escritos += 1

    logger.info("Total de objetos gravados no MinIO: %d.", objetos_escritos)
    return objetos_escritos


def _chave_particao(data_pregao: date) -> str:
    """Monta a chave ``raw/cotacoes/ano=YYYY/mes=MM/dia=DD/cotacoes.parquet``.

    Em S3 não existem pastas — o que existe é uma chave (string opaca).
    Ferramentas (DuckDB, dbt, Spark) parseiam o estilo Hive
    (``coluna=valor``) na própria chave para fazer partition pruning.
    """
    return (
        f"{RAW_PREFIX}/"
        f"ano={data_pregao.year:04d}/"
        f"mes={data_pregao.month:02d}/"
        f"dia={data_pregao.day:02d}/"
        f"cotacoes.parquet"
    )
