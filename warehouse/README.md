# warehouse/

Camada de **warehouse analítico local** do projeto. Equivalente, em escala de portfólio, ao papel que BigQuery / Snowflake / Redshift cumprem em ambiente corporativo.

## O que mora aqui

- `conexao.py` — função única `obter_conexao()` que abre o arquivo `warehouse.duckdb` na raiz do repo e configura o cliente S3 embutido do DuckDB para falar com o MinIO.
- `setup.py` — cria o schema `raw` e a view `raw.cotacoes`. Ponto de entrada via `python -m warehouse.setup`.

O arquivo `warehouse.duckdb` em si **não é versionado** (ver `.gitignore`). Ele é regenerável: o estado de verdade vive no MinIO (raw) e nos modelos dbt (Etapa 4 em diante).

## Como usar

Pré-requisitos: MinIO no ar (`docker compose -f docker-compose.minio.yml up -d`) e ingestão já executada ao menos uma vez.

```bash
# Cria o schema raw e a view raw.cotacoes, imprime diagnóstico.
python -m warehouse.setup
```

Depois disso, dá pra abrir o `warehouse.duckdb` em qualquer IDE com suporte a DuckDB (DBeaver, VS Code com a extensão DuckDB, DataGrip) ou diretamente em notebook — ver `notebooks/exploracao_etapa3.ipynb`.

## Convenção importante

**Este módulo não faz transformação de dado.** A única coisa que ele cria é a view `raw.cotacoes`, que é um espelho SQL do raw layer no MinIO. Modelagem dimensional, limpeza de tipos, fatos e dimensões — tudo isso é responsabilidade do dbt na Etapa 4, escrevendo nos schemas `staging` e `marts` do **mesmo** arquivo `warehouse.duckdb`.

A escolha de view (em vez de tabela materializada) preserva o conceito de raw imutável: o DuckDB relê o MinIO a cada query, e novos pregões ingeridos aparecem automaticamente sem precisar reexecutar o setup.
