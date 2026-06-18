"""Camada de warehouse analítico local (Etapa 3).

Expõe um arquivo ``warehouse.duckdb`` persistente na raiz do repositório
que serve de ponto de query SQL sobre o raw layer no MinIO. O DuckDB
abre os Parquet via extensão ``httpfs`` — não há cópia local do dado.

A partir da Etapa 4, este mesmo arquivo é o destino dos modelos dbt
(schemas ``staging`` e ``marts``). Este módulo cria apenas o schema
``raw`` e a view ``raw.cotacoes``; transformações vivem no dbt.
"""

from warehouse.conexao import configurar_s3, obter_conexao
from warehouse.setup import criar_schema_raw

__all__ = ["obter_conexao", "configurar_s3", "criar_schema_raw"]
