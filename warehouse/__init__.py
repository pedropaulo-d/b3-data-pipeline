"""Camada de warehouse analítico local (Etapa 3).

Expõe um arquivo ``warehouse.duckdb`` persistente na raiz do repositório
que serve de ponto de query SQL sobre o raw layer no MinIO. O DuckDB
abre os Parquet via extensão ``httpfs`` — não há cópia local do dado.

A partir da Etapa 4, este mesmo arquivo é o destino dos modelos dbt
(schemas ``staging`` e ``marts``). Este módulo cria apenas o schema
``raw`` e a view ``raw.cotacoes``; transformações vivem no dbt.

Reexportamos apenas a API de conexão (``obter_conexao`` / ``configurar_s3``).
``criar_schema_raw`` mora em :mod:`warehouse.setup` e deve ser importada de
lá — NÃO a reexportamos aqui de propósito:

- importar ``warehouse.setup`` no ``__init__`` puxa ``ingestion.config`` (que
  valida MINIO_* no import) para todo consumidor do pacote, inclusive o
  dashboard, que não usa S3 — o acoplamento que a Forma C / lazy import
  desfez (ver :mod:`warehouse.conexao`);
- e deixava ``warehouse.setup`` em ``sys.modules`` antes de
  ``python -m warehouse.setup``, disparando o ``RuntimeWarning`` do ``runpy``.
"""

from warehouse.conexao import configurar_s3, obter_conexao

__all__ = ["obter_conexao", "configurar_s3"]
