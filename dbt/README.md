# dbt — Transformações (Etapa 4)

Projeto dbt que transforma o raw layer (lido do MinIO via DuckDB) em
um esquema estrela Kimball: **`fato_cotacoes_diarias`** apoiada nas
dimensões **`dim_empresa`** e **`dim_tempo`**.

## O que vive aqui

```
dbt/
├── dbt_project.yml      # Manifesto do projeto
├── profiles.yml         # Credenciais de conexão (versionado — ver nota)
├── packages.yml         # Dependências externas (dbt_utils)
├── seeds/
│   └── empresas.csv     # Cadastro estático das 6 empresas do escopo
├── models/
│   ├── sources.yml      # Declaração da source raw.cotacoes
│   ├── staging/
│   │   ├── stg_cotacoes.sql
│   │   └── schema.yml
│   └── marts/
│       ├── dim_empresa.sql
│       ├── dim_tempo.sql
│       ├── fato_cotacoes_diarias.sql
│       └── schema.yml
└── tests/
    ├── fato_volume_nao_negativo.sql
    ├── fato_maxima_maior_igual_minima.sql
    └── fato_fechamento_dentro_do_range.sql
```

## profiles.yml versionado no repo

Por padrão, o dbt procura `profiles.yml` em `~/.dbt/`. Aqui ele mora
**dentro do repo** (`dbt/profiles.yml`) — decisão consciente para
torná-lo reproduzível: clonar o repositório, configurar `.env` com as
credenciais do MinIO e rodar — sem etapa "configure seu profile".

Como o `profiles.yml` consome credenciais **via `env_var()`**, ele não
contém segredos. O `.env` (gitignored) é onde as credenciais reais
ficam.

Custo dessa escolha: todo comando dbt precisa de `--profiles-dir ./`
(ou `DBT_PROFILES_DIR=./` exportado).

## Pré-requisitos

1. **MinIO rodando** (Etapa 2):
   ```bash
   docker compose -f ../docker-compose.yml up -d minio mc-init
   ```
2. **Warehouse DuckDB com schema raw** (Etapa 3):
   ```bash
   cd ..
   python -m warehouse.setup
   ```
   Isso cria `warehouse.duckdb` na raiz com a view `raw.cotacoes`
   apontando para o MinIO. É o arquivo que o dbt vai abrir.
3. **Variáveis de ambiente** em `../.env` — em particular
   `MINIO_ENDPOINT_HOST_PORT`, sem esquema (`localhost:9000` e não
   `http://localhost:9000`). Ver `../.env.example`.
4. **dbt instalado** (já está em `../requirements.txt`):
   ```bash
   pip install -r ../requirements.txt
   ```

## Comandos principais

Todos os comandos abaixo assumem `cwd = dbt/`.

| Comando | O que faz |
|---|---|
| `dbt deps --profiles-dir ./` | Instala pacotes externos (dbt_utils) em `dbt_packages/`. |
| `dbt seed --profiles-dir ./` | Carrega `seeds/empresas.csv` no schema `seed`. |
| `dbt run --profiles-dir ./` | Executa todos os models (staging → marts). |
| `dbt test --profiles-dir ./` | Roda testes (nativos em schema.yml + custom em tests/). |
| `dbt build --profiles-dir ./` | Equivalente a `seed` + `run` + `test` em uma única invocação, respeitando DAG. |
| `dbt docs generate --profiles-dir ./` | Gera o site de documentação em `target/`. |
| `dbt docs serve --profiles-dir ./` | Sobe servidor local em `http://localhost:8080` com o DAG navegável. |

## Schemas resultantes no DuckDB

Após `dbt build --profiles-dir ./`, o `warehouse.duckdb` terá:

| Schema | Origem | Conteúdo |
|---|---|---|
| `raw` | warehouse/setup.py | View `raw.cotacoes` (Parquet no MinIO via httpfs). NÃO tocado pelo dbt. |
| `seed` | dbt seed | Tabela `empresas` (6 linhas, sem alterações sobre o CSV). |
| `staging` | dbt run | View `stg_cotacoes` derivada da source raw. |
| `marts` | dbt run | Tabelas `dim_empresa`, `dim_tempo`, `fato_cotacoes_diarias`. |

> O projeto sobrescreve `generate_schema_name` (em `macros/`) para que
> schemas materializem com nomes limpos (`staging`, `marts`, `seed`)
> em vez do default do dbt (`main_staging`, etc.). Isso é decisão
> consciente para clareza dos schemas — veja `docs/decisoes.md`.
>
> Validar com:
> ```bash
> duckdb ../warehouse.duckdb -c "SELECT DISTINCT table_schema FROM information_schema.tables;"
> ```

## Modelagem

- **Granularidade da fato:** 1 linha = 1 ticker × 1 pregão.
- **Surrogate keys:** `empresa_id` (INTEGER, ROW_NUMBER ordenado por
  ticker), `tempo_id` (INTEGER, formato YYYYMMDD).
- **SCD:** tipo 1 em `dim_empresa` — sobrescreve quando muda; sem
  histórico.
- **dim_tempo:** calendário completo gerado (2020-01-01 a 2030-12-31),
  independente das datas presentes na fato. Inclui finais de semana e
  feriados — a fato só referencia datas onde houve pregão.

Detalhes do racional estão em `../docs/decisoes.md`.

## Próxima etapa

Etapa 5 introduz Airflow para orquestrar a sequência completa
(ingestão → warehouse setup → dbt build). Esta pasta cresce apenas
com novos models de indicadores na Etapa 6.
