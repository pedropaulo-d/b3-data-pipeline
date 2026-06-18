"""Persistência dos dividendos em Parquet particionado por ANO no MinIO.

Layout no bucket (espelha o de cotações, trocando a granularidade da
partição de dia para ano):

    s3://b3-data/raw/dividendos/ano=YYYY/dividendos.parquet

Cada objeto contém os proventos de **todos os tickers** naquele ano.
Particionar por ano (e não por dia) é a decisão central da Etapa 6 para
dividendos: eles são esparsos (poucos eventos por ticker por ano), então
um arquivo por dia geraria centenas de objetos quase vazios.

Idempotência por sobrescrita, igual às cotações: ``put_object`` substitui
o objeto da partição se a chave já existir.

Reusa ``ingestion.s3_client.criar_cliente_s3`` — mesma conexão boto3 das
cotações, sem duplicar credenciais.
"""

import io
import logging

import pandas as pd
from botocore.exceptions import ClientError, EndpointConnectionError

from ingestion.config import (
    COLUNAS_DIVIDENDOS,
    MINIO_BUCKET,
    MINIO_ENDPOINT,
    RAW_PREFIX_DIVIDENDOS,
)
from ingestion.s3_client import criar_cliente_s3

logger = logging.getLogger(__name__)


def salvar_dividendos_por_ano(
    df: pd.DataFrame,
    anos: set[int] | None = None,
) -> int:
    """Grava o DataFrame de dividendos em Parquet particionado por ano.

    Para cada ano presente em ``df["data_ex"]``, escreve um objeto
    ``raw/dividendos/ano=YYYY/dividendos.parquet`` com todos os proventos
    daquele ano. Objetos pré-existentes são sobrescritos.

    Args:
        df: DataFrame "long" produzido por
            :func:`ingestion.dividendos.download.baixar_dividendos`.
        anos: Se informado, escreve **apenas** as partições desses anos
            (usado pelo modo incremental, que reescreve só o ano corrente).
            Se ``None`` (modo inicial), escreve todos os anos presentes.

    Returns:
        Número de objetos (partições de ano) efetivamente escritos.

    Raises:
        ValueError: Se ``df`` não tiver o schema esperado.
        RuntimeError: Se o MinIO estiver inacessível ou o S3 retornar erro.
    """
    if list(df.columns) != COLUNAS_DIVIDENDOS:
        raise ValueError(
            f"Schema inesperado em salvar_dividendos_por_ano: {list(df.columns)} "
            f"(esperado {COLUNAS_DIVIDENDOS})."
        )

    if df.empty:
        logger.info("DataFrame de dividendos vazio — nada a gravar.")
        return 0

    # Ano da partição = ano da data-ex. Coluna auxiliar só para o groupby;
    # não vai para o Parquet (a partição já codifica o ano na chave Hive).
    anos_serie = pd.to_datetime(df["data_ex"]).dt.year

    s3 = criar_cliente_s3()

    objetos_escritos = 0
    for ano, grupo in df.groupby(anos_serie, sort=True):
        if anos is not None and ano not in anos:
            continue

        chave = _chave_particao(int(ano))
        buffer = io.BytesIO()
        grupo.to_parquet(buffer, engine="pyarrow", compression="snappy", index=False)
        buffer.seek(0)

        try:
            s3.put_object(Bucket=MINIO_BUCKET, Key=chave, Body=buffer.getvalue())
        except EndpointConnectionError as exc:
            raise RuntimeError(
                f"MinIO inacessível em {MINIO_ENDPOINT}. Verifique que o "
                "serviço está rodando: `docker compose up -d minio mc-init`."
            ) from exc
        except ClientError as exc:
            codigo = exc.response.get("Error", {}).get("Code", "desconhecido")
            raise RuntimeError(
                f"Erro do S3 ao gravar s3://{MINIO_BUCKET}/{chave} "
                f"(código={codigo}): {exc}."
            ) from exc

        logger.info(
            "Gravado s3://%s/%s (%d proventos).", MINIO_BUCKET, chave, len(grupo)
        )
        objetos_escritos += 1

    logger.info("Total de partições de dividendos gravadas: %d.", objetos_escritos)
    return objetos_escritos


def _chave_particao(ano: int) -> str:
    """Monta a chave ``raw/dividendos/ano=YYYY/dividendos.parquet``."""
    return f"{RAW_PREFIX_DIVIDENDOS}/ano={ano:04d}/dividendos.parquet"
