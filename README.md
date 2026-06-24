# b3-data-pipeline

Pipeline de dados de mercado financeiro brasileiro (B3) construído como projeto de portfólio para vaga de engenharia de dados.

**Status atual:** Etapa 7 — Dashboard com Streamlit ✅ concluída (Aba 1 — Visão Individual e Aba 2 — Comparação entre tickers). Próxima: Etapa 8 — Polimento e portfólio.

**🔗 Dashboard ao vivo:** _(preencher após o deploy)_ `https://<app>.streamlit.app` — publicado no Streamlit Community Cloud. O app lê um **snapshot** dos marts versionado no repo (`warehouse.duckdb`), não dados ao vivo; ver `dashboard/README.md` para o passo a passo do deploy e a política de atualização do snapshot.

---

## Escopo

Trabalhamos com seis tickers líquidos cobrindo quatro setores distintos. Histórico inicial de **5 anos**, suficiente para exercitar particionamento, modelagem e cálculo de indicadores sem inflar o volume.

| Ticker | Empresa             | Setor              |
|--------|---------------------|--------------------|
| PETR4  | Petrobras           | Petróleo e Gás     |
| VALE3  | Vale                | Mineração          |
| ITUB4  | Itaú Unibanco       | Financeiro         |
| BBDC4  | Bradesco            | Financeiro         |
| WEGE3  | WEG                 | Bens Industriais   |
| ABEV3  | Ambev               | Consumo Não-Cíclico|

> A lista de tickers e a janela histórica são parâmetros do projeto, não constantes do código. Escalar para o Ibovespa inteiro é trivial — não é o objetivo aqui.

---

## Arquitetura prevista

Peças marcadas com ✅ já estão ativas. As demais entram nas etapas seguintes.

```
                          ┌──────────────────────────┐
                          │        Airflow  ✅       │
                          │     (orquestração)       │
                          └────────────┬─────────────┘
                                       │
                                       ▼
  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
  │ yfinance │──▶ │  Python  │──▶ │  MinIO   │──▶ │  DuckDB  │──▶ │   dbt    │
  │ (origem) │    │ (ingest✅)│    │ (raw  ✅) │    │ (WH   ✅) │    │ (mod. ✅) │
  └──────────┘    └──────────┘    └──────────┘    └──────────┘    └────┬─────┘
                                                                       │
                                                                       ▼
                                                                ┌──────────────┐
                                                                │  Streamlit   │
                                                                │ (dashboard)  │
                                                                └──────────────┘
```

> A partir da Etapa 2 o raw layer mora **exclusivamente no MinIO**. Desde
> a Etapa 6 são **duas fontes**: `raw/cotacoes/...` (particionada por dia)
> e `raw/dividendos/...` (particionada por ano). A pasta `data/raw/` no
> filesystem é histórica da Etapa 1 — o `.gitkeep` documenta a convenção,
> mas nada é gravado lá.
>
> Na camada `marts` do dbt, além da estrela de cotações, a Etapa 6 adiciona
> os marts de indicadores: `mart_indicadores_diarios`,
> `mart_indicadores_resumo`, `fato_dividendos` e `mart_dividend_yield`.

---

## Stack

- **Linguagem:** Python 3.11+
- **Ingestão:** yfinance, pandas, pyarrow
- **Object storage:** MinIO (compatível S3, local)
- **Warehouse analítico:** DuckDB
- **Transformações:** dbt (adapter dbt-duckdb)
- **Orquestração:** Apache Airflow (via Docker)
- **Visualização:** Streamlit + Plotly
- **Ambiente:** local (sem cloud), pip + venv

---

## Status por etapa

| Etapa | Tema                                | Status         |
|-------|-------------------------------------|----------------|
| 0     | Preparação (estrutura, docs, escopo)| ✅ Concluída   |
| 1     | Ingestão manual com Python puro     | ✅ Concluída   |
| 2     | Object storage com MinIO            | ✅ Concluída   |
| 3     | Warehouse analítico com DuckDB      | ✅ Concluída   |
| 4     | Transformações com dbt              | ✅ Concluída   |
| 5     | Orquestração com Airflow (Docker)   | ✅ Concluída   |
| 6     | Indicadores e métricas financeiras  | ✅ Concluída   |
| 7     | Dashboard com Streamlit             | ✅ Concluída   |
| 8     | Polimento, documentação e portfólio | ⏳ Pendente    |

---

## Estrutura do repositório

```
b3-data-pipeline/
├── ingestion/                  # Scripts de download e persistência (Etapa 1+2)
│   ├── dividendos/             # Ingestão de dividendos (Etapa 6)
│   ├── s3_client.py            # Cliente boto3/MinIO compartilhado (cotações + dividendos)
│   └── README.md
├── warehouse/                  # Conexão e setup do DuckDB local (Etapa 3); views raw.cotacoes + raw.dividendos
│   └── README.md
├── dbt/                        # Projeto dbt (Etapas 4 e 6)
│   ├── dbt_project.yml
│   ├── profiles.yml            # Versionado conscientemente (credenciais via env_var)
│   ├── packages.yml
│   ├── seeds/empresas.csv
│   ├── models/{staging,marts}/ # marts: estrela de cotações + indicadores e dividend yield (Etapa 6)
│   ├── tests/                  # Custom tests (regras de negócio; +4 na Etapa 6)
│   └── README.md
├── sql/
│   └── exploratoria/           # Queries .sql versionadas, executadas pelo notebook
├── scripts/                    # Utilitários de validação e operação (não-pipeline)
│   └── README.md
├── data/
│   └── raw/                    # Histórico da Etapa 1 (não mais escrito; raw atual mora no MinIO)
│       └── .gitkeep
├── notebooks/                  # Exploração ad-hoc em Jupyter
│   └── exploracao_etapa3.ipynb
├── dashboard/                  # Dashboard Streamlit + Plotly (Etapa 7)
│   ├── app.py                  # Entry point; abas e gráficos
│   ├── data.py                 # Acesso a dados (read-only, cacheado)
│   └── README.md
├── airflow/                    # Orquestração (Etapa 5)
│   ├── Dockerfile              # Imagem custom (airflow + deps do projeto)
│   ├── dags/pipeline_b3_diario.py
│   ├── logs/                   # Gitignored, bind mount em runtime
│   ├── plugins/                # Gitignored, bind mount em runtime
│   └── README.md
├── .github/
│   └── workflows/security.yml  # CI de segurança: pip-audit + gitleaks (M6)
├── docs/
│   ├── decisoes.md             # Decisões técnicas com racional
│   ├── divida_tecnica.md       # Dívida técnica consciente, por etapa
│   └── NOTAS.md                # Caderno de aprendizados por etapa
├── docker-compose.yml          # MinIO (Etapa 2) + Airflow (Etapa 5)
├── warehouse.duckdb            # Arquivo do warehouse local (gitignored, regenerável)
├── .env.example                # Template das credenciais (versionado)
├── .env                        # Credenciais reais (gitignored)
├── .gitignore
├── README.md
├── CLAUDE.md                   # Diretrizes para sessões com Claude Code
├── requirements.txt            # RUNTIME do pipeline (>=; build do Airflow + auditado pelo CI)
├── requirements-dev.txt        # Dev/exploração (Jupyter, plotly, pip-audit); não auditado pelo CI
└── requirements-dashboard.txt  # Deps do dashboard (Streamlit; deployável à parte)
```

> O repositório evolui em camadas, não nasce pronto: cada pasta apareceu na etapa que a exigiu.

---

## Setup local

Pré-requisitos: Python 3.11+, Docker e Docker Compose.

```bash
# 1. Clone do repositório
git clone https://github.com/<seu-usuario>/b3-data-pipeline.git
cd b3-data-pipeline

# 2. Criar ambiente virtual
python -m venv .venv

# 3. Ativar o ambiente
# Linux / macOS:
source .venv/bin/activate
# Windows (PowerShell):
.venv\Scripts\Activate.ps1

# 4. Instalar dependências
#    Runtime do pipeline (ingestão, warehouse, dbt):
pip install -r requirements.txt
#    Para desenvolver / rodar notebooks (Jupyter, plotly) e auditar:
#    pip install -r requirements.txt -r requirements-dev.txt

# 5. Configurar credenciais do MinIO (raw layer)
cp .env.example .env       # Linux/macOS
copy .env.example .env     # Windows
# Edite .env se quiser trocar credenciais; defaults funcionam para uso local.

# 6. Subir todo o ambiente: MinIO + Airflow (Postgres + scheduler + webserver)
#    Primeira vez, ou após mudar requirements.txt / airflow/Dockerfile:
docker compose build
docker compose up -d

# 7. Aguardar ~1-2 min na primeira subida (build da imagem + init do Airflow).
# Conferir saúde: docker compose ps  (6 containers; mc-init e airflow-init
# em "exited (0)" é esperado — são init containers).
# Console MinIO:    http://localhost:9001 (usuário/senha do .env)
# API S3 MinIO:     http://localhost:9000
# Airflow webserver: http://localhost:8080 (login admin / admin)

# 8. Rodar a ingestão (manual, fora da DAG):
python -m ingestion.main --modo inicial

# 9. Setup do warehouse DuckDB — cria o schema raw e a view raw.cotacoes
# apontando para o MinIO. Imprime contagem, tickers e range de datas.
python -m warehouse.setup

# 10. (Opcional) Abrir o notebook exploratório
jupyter notebook notebooks/exploracao_etapa3.ipynb

# 11. Etapa 4 — rodar o dbt (cria schemas staging/seed/marts no mesmo .duckdb)
cd dbt
dbt deps --profiles-dir ./
dbt build --profiles-dir ./        # seed + run + test em um único comando
dbt docs generate --profiles-dir ./
dbt docs serve --profiles-dir ./ --port 8081   # 8080 está com o Airflow

# 12. Etapa 5 — usar o Airflow para automatizar os passos 8, 9 e 11.
# Na UI (http://localhost:8080) localizar a DAG `pipeline_b3_diario`,
# despausar e clicar em "Trigger DAG". As 4 tasks devem ficar verdes.
# Detalhes em airflow/README.md.

# 13. Etapa 7 — dashboard Streamlit (lê os marts, somente leitura).
# Requer os marts já materializados (passo 11 ou a DAG). Da raiz do repo:
pip install -r requirements-dashboard.txt
streamlit run dashboard/app.py        # abre em http://localhost:8501
# Deploy no Streamlit Cloud: o repo já versiona warehouse.duckdb como
# snapshot e tem dashboard/requirements.txt. Passo a passo (incl. secrets
# dummy de MinIO) e limitação de concorrência em dashboard/README.md.
```

Para derrubar todos os serviços preservando os dados:

```bash
docker compose down       # remove containers, mantém volumes (raw + metastore)
docker compose down -v    # remove TAMBÉM volumes (apaga raw e metastore do Airflow)
```

---

## Dependências e CI de segurança

Dois arquivos de dependências, com papéis distintos:

| Arquivo                 | Papel       | Versões | Quem consome | Auditado pelo CI? |
|-------------------------|-------------|---------|--------------|-------------------|
| `requirements.txt`      | **runtime (intenção)** | `>=`   | Build da imagem do Airflow + `pip-audit` no CI | **Sim** |
| `requirements-dev.txt`  | dev/exploração/segurança | `>=`  | Notebooks (Jupyter, plotly) e auditoria local (`pip-audit`) | Não |

`requirements.txt` declara o **runtime** do pipeline — só o que ingestão,
warehouse, dbt e Airflow precisam para rodar (deps diretas, `>=`,
legível). É o arquivo usado no `docker build` da imagem do Airflow (o
`pip` resolve as versões respeitando as constraints da imagem base
`apache/airflow:2.10.5`) **e** a única superfície auditada pelo CI.

`requirements-dev.txt` reúne o que só existe em **desenvolvimento**:
notebooks exploratórios (Jupyter, plotly) e auditoria de segurança
(pip-audit). Não entra na imagem do Airflow nem é auditado pelo CI — dev
local não é superfície de produção, então CVEs em transitivas do Jupyter
(bleach, tornado, jupyter-server) não fazem o build falhar. Para
desenvolver ou rodar os notebooks, instale **ambos**:

```bash
pip install -r requirements.txt -r requirements-dev.txt
```

O projeto **não mantém um `requirements.lock`**. A reprodutibilidade do
build da imagem do Airflow vem da imagem base `apache/airflow:2.10.5` (que
já fixa as versões das libs comuns) + `requirements.txt`. Um lock `==`
gerado por `pip freeze` de um venv standalone conflitava com as
constraints da imagem oficial e não tinha consumidor real (nem Dockerfile,
nem CI), então foi removido (ver
[`docs/divida_tecnica.md`](docs/divida_tecnica.md), DT-SEC.1/DT-SEC.4). Se
um dia um lock determinístico virar requisito, gerá-lo via as constraints
oficiais do Airflow (constraints-2.10.5).

**CI de segurança** (diferencial de portfólio): o repositório roda
[`.github/workflows/security.yml`](.github/workflows/security.yml) em todo
push para `main` e em todo pull request. Dois controles:

- **`pip-audit`** — procura CVEs conhecidos no **runtime** do pipeline
  (`pip-audit -r requirements.txt`). Falha o build em qualquer CVE.
  Auditamos só o runtime de propósito: as deps de desenvolvimento
  (Jupyter etc.) não fazem parte do deploy.
- **`gitleaks`** — procura secrets vazados no histórico do Git. Falha o
  build se encontrar.

Localmente: `pip install pip-audit && pip-audit -r requirements.txt`
(deve reportar *No known vulnerabilities found*). `gitleaks` e
`trufflehog` são binários (não pip) — ver `requirements-dev.txt` para
instalação via Docker ou gerenciador de pacotes.

A dívida técnica consciente do projeto fica registrada em
[`docs/divida_tecnica.md`](docs/divida_tecnica.md).

---

## Decisões técnicas

As decisões de arquitetura e seus trade-offs estão documentadas em [`docs/decisoes.md`](docs/decisoes.md). Resumo das decisões já tomadas:

1. **Ambiente local em vez de cloud** — custo zero e iteração rápida; abro mão de exercitar IAM real.
2. **DuckDB em vez de BigQuery** — roda na máquina, SQL padrão e lê Parquet nativo; não exercito o BigQuery.
3. **6 tickers em vez do Ibovespa inteiro** — 4 setores cobertos, escalar é trivial; o número absoluto soa menos impressivo.
4. **Preço bruto e ajustado lado a lado no raw** (Etapa 1) — imutabilidade do raw; permite recalcular ajustes sem re-baixar.
5. **Arquivo Parquet por data, tickers juntos** (Etapa 1) — evita micro-arquivos por ticker e mantém partition pruning eficiente.
6. **Reexecução sobrescreve a partição** (Etapa 1) — idempotência semântica no raw; correções viram nova execução, não nova versão.
7. **MinIO em Docker Compose dedicado na raiz** (Etapa 2) — portabilidade e preparação para Airflow integrar o mesmo arquivo; abro mão de rodar 100% sem Docker.
8. **Bucket único com prefixos por camada** (Etapa 2) — simplicidade; refatoraria se permissões granulares por camada virassem requisito.
9. **Trocar storage local por S3 direto, sem abstração** (Etapa 2) — YAGNI: raw mora em object storage, ponto; aceito perder execução 100% offline.
10. **boto3 em vez de s3fs/pyarrow.fs** (Etapa 2) — cliente oficial, é o que aparece em vaga; verboso, mas explícito sobre o protocolo S3.
11. **DuckDB persistente em arquivo na raiz** (Etapa 3) — view `raw.cotacoes` sobrevive entre sessões e é compartilhada com o dbt na Etapa 4; arquivo gitignored, regenerável a partir do MinIO.
12. **Schema `raw` como view, não tabela** (Etapa 3) — janela lógica sobre o MinIO; novas partições aparecem sem refresh.
13. **Esquema estrela Kimball** (Etapa 4) — `fato_cotacoes_diarias` + `dim_empresa` + `dim_tempo`; surrogate keys nas dimensões, chave composta na fato.
14. **SCD tipo 1 em `dim_empresa`** (Etapa 4) — sobrescreve sem histórico; sem snapshot do dbt nesta etapa.
15. **dim_tempo gera calendário completo** (Etapa 4) — independente da fato, 2020–2030; padrão Kimball que permite relatórios temporais consistentes.
16. **profiles.yml do dbt versionado no repo** (Etapa 4) — credenciais via `env_var()`, repo continua reproduzível sem etapa "configure seu profile".
17. **Airflow no mesmo `docker-compose.yml` do MinIO** (Etapa 5) — compose único renomeado; mesma rede Docker permite à DAG resolver `minio:9000`.
18. **LocalExecutor em vez de CeleryExecutor** (Etapa 5) — single-host, volume desprezível, sem worker/Redis separados.
19. **Bind mount + BashOperator** (Etapa 5) — DAG roda os mesmos comandos do terminal manual; paridade exata com a execução documentada no README.
20. **DAG de 4 tasks (`extract` → `refresh_warehouse` → `dbt run` → `dbt test`)** (Etapa 5) — uma task por etapa lógica do pipeline; retry e visibilidade na granularidade certa.
21. **Schedule `0 20 * * *` America/Sao_Paulo, `catchup=False`** (Etapa 5) — pós-fechamento + ajustes do dia; sem backfill automático (yfinance não muda histórico retroativamente).
22. **`MINIO_ENDPOINT=http://minio:9000` dentro do container, `localhost:9000` no host** (Etapa 5) — fonte mais comum de "funciona aqui, falha lá"; documentado em três lugares.
23. **Escopo de indicadores: mercado + dividend yield** (Etapa 6) — fundamentalistas (P/L, P/VP, ROE) fora por limitação do yfinance; DY é o único viável (depende só de proventos + preço).
24. **Retorno simples E log** (Etapa 6) — log é aditivo no tempo (base da volatilidade); simples é a variação reportável; manter os dois custa nada.
25. **Base de preço: ajustado para retorno/risco, bruto para yield** (Etapa 6) — ajustado evita queda artificial em data-ex; bruto no denominador do DY evita contar o provento duas vezes.
26. **Médias móveis 7/30/90/200 com contagem de pregões** (Etapa 6) — Forma A: calcula desde o 1º pregão e sinaliza janela parcial via `pregoes_janela_Nd`.
27. **Volatilidade amostral, anualizada por √252** (Etapa 6) — `STDDEV_SAMP` sobre retorno log; √252 porque a variância escala linear no tempo.
28. **Dividendos particionados por ano; `fato_dividendos` conformada** (Etapa 6) — proventos esparsos (1 arquivo/ano); reusa `dim_empresa`/`dim_tempo`; ingestão em subpacote `ingestion/dividendos/`.
29. **DY trailing 12m sobre preço bruto, via range join** (Etapa 6) — grão diário (série do yield); 0 (não NULL) quando não há provento na janela de 365 dias.
30. **Materialização Etapa 6: marts pesados como table, `fato_dividendos` como view** — indicadores/DY relidos pelo dashboard → table; fato de dividendos é ínfima → view.

---

## Aprendizados

O caderno de conceitos, dúvidas e descobertas de cada etapa fica em [`docs/NOTAS.md`](docs/NOTAS.md). O objetivo do projeto não é só entregar o pipeline — é entender cada peça bem o suficiente para defender em entrevista.
