"""Fábrica única do cliente boto3 apontando para o MinIO.

Centraliza a construção do cliente S3 para que **todos** os módulos de
ingestão (cotações e dividendos) usem exatamente a mesma configuração —
endpoint, credenciais, região, signature v4 e addressing style. As
credenciais vivem em :mod:`ingestion.config` (lidas do ``.env``); este
módulo só sabe *como* montar o cliente, não *quais* são os segredos.

Antes da Etapa 6 essa lógica era um helper privado em ``storage.py``.
Foi promovida a módulo próprio quando a ingestão de dividendos passou a
precisar do mesmo cliente — evita duplicar a construção (e o risco de as
duas cópias divergirem).
"""

import boto3
from botocore.client import Config

from ingestion.config import (
    MINIO_ACCESS_KEY,
    MINIO_ENDPOINT,
    MINIO_REGION,
    MINIO_SECRET_KEY,
)


def criar_cliente_s3():
    """Constrói um cliente boto3 S3 apontando para o MinIO.

    ``signature_version='s3v4'`` é obrigatório para autenticar contra o
    MinIO. ``addressing_style='path'`` força URLs do tipo
    ``http://endpoint/bucket/key`` em vez de ``http://bucket.endpoint/key``
    — virtual-hosted style não funciona em endpoint sem DNS wildcard
    (como ``localhost``).

    Returns:
        Cliente boto3 ``s3`` pronto para ``put_object`` / ``get_object``.
    """
    return boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        region_name=MINIO_REGION,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )
