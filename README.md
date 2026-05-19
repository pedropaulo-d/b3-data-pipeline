# b3-data-pipeline

Pipeline de dados de mercado financeiro brasileiro (B3) construído como projeto de portfólio para vaga de engenharia de dados.

**Status atual:** Etapa 3 — Warehouse analítico com DuckDB ✅. Próxima: Transformações com dbt.

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
                          │        Airflow           │
                          │     (orquestração)       │
                          └────────────┬─────────────┘
                                       │
                                       ▼
  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
  │ yfinance │──▶ │  Python  │──▶ │  MinIO   │──▶ │  DuckDB  │──▶ │   dbt    │
  │ (origem) │    │ (ingest✅)│    │ (raw  ✅) │    │ (WH   ✅) │    │ (models) │
  └──────────┘    └──────────┘    └──────────┘    └──────────┘    └────┬─────┘
                                                                       │
                                                                       ▼
                                                                ┌──────────────┐
                                                                │  Streamlit   │
                                                                │ (dashboard)  │
                                                                └──────────────┘
```

> A partir da Etapa 2 o raw layer mora **exclusivamente no MinIO**
> (`s3://b3-data/raw/cotacoes/...`). A pasta `data/raw/` no filesystem
> é histórica da Etapa 1 — o `.gitkeep` é mantido para documentar a
> convenção, mas nada é gravado lá.

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
| 4     | Transformações com dbt              | 🔜 Próxima     |
| 5     | Orquestração com Airflow (Docker)   | ⏳ Pendente    |
| 6     | Indicadores e métricas financeiras  | ⏳ Pendente    |
| 7     | Dashboard com Streamlit             | ⏳ Pendente    |
| 8     | Polimento, documentação e portfólio | ⏳ Pendente    |

---

## Estrutura do repositório

```
b3-data-pipeline/
├── ingestion/                  # Scripts de download e persistência (Etapa 1+2)
│   └── README.md
├── warehouse/                  # Conexão e setup do DuckDB local (Etapa 3)
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
├── docs/
│   ├── decisoes.md             # Decisões técnicas com racional
│   └── NOTAS.md                # Caderno de aprendizados por etapa
├── docker-compose.minio.yml    # MinIO + mc-init (Etapa 2)
├── warehouse.duckdb            # Arquivo do warehouse local (gitignored, regenerável)
├── .env.example                # Template das credenciais (versionado)
├── .env                        # Credenciais reais (gitignored)
├── .gitignore
├── README.md
├── CLAUDE.md                   # Diretrizes para sessões com Claude Code
└── requirements.txt
```

> Pastas como `dbt/`, `airflow/` e `dashboard/` ainda não existem — cada uma nasce na sua respectiva etapa. O repositório evolui em camadas, não nasce pronto.

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
pip install -r requirements.txt

# 5. Configurar credenciais do MinIO (raw layer)
cp .env.example .env       # Linux/macOS
copy .env.example .env     # Windows
# Edite .env se quiser trocar credenciais; defaults funcionam para uso local.

# 6. Subir o MinIO (container + criação automática do bucket)
docker compose -f docker-compose.minio.yml up -d

# 7. Aguardar ~10s para o healthcheck passar e o bucket ser criado.
# Console web: http://localhost:9001 (usuário/senha do .env)
# API S3:      http://localhost:9000

# 8. Rodar a ingestão:
python -m ingestion.main --modo inicial

# 9. Setup do warehouse DuckDB — cria o schema raw e a view raw.cotacoes
# apontando para o MinIO. Imprime contagem, tickers e range de datas.
python -m warehouse.setup

# 10. (Opcional) Abrir o notebook exploratório
jupyter notebook notebooks/exploracao_etapa3.ipynb
```

Para derrubar o MinIO preservando os dados:

```bash
docker compose -f docker-compose.minio.yml down       # remove containers, mantém volume
docker compose -f docker-compose.minio.yml down -v    # remove TAMBÉM o volume (apaga raw)
```

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

---

## Aprendizados

O caderno de conceitos, dúvidas e descobertas de cada etapa fica em [`docs/NOTAS.md`](docs/NOTAS.md). O objetivo do projeto não é só entregar o pipeline — é entender cada peça bem o suficiente para defender em entrevista.
