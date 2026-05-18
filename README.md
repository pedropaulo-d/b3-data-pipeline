# b3-data-pipeline

Pipeline de dados de mercado financeiro brasileiro (B3) construído como projeto de portfólio para vaga de engenharia de dados.

**Status atual:** Etapa 1 — Ingestão manual com Python puro ✅. Próxima: Object storage com MinIO.

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

```
                          ┌──────────────────────────┐
                          │        Airflow           │
                          │     (orquestração)       │
                          └────────────┬─────────────┘
                                       │
                                       ▼
  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
  │ yfinance │──▶ │  Python  │──▶ │  MinIO   │──▶ │  DuckDB  │──▶ │   dbt    │
  │ (origem) │    │ (ingest) │    │  (raw)   │    │   (WH)   │    │ (models) │
  └──────────┘    └──────────┘    └──────────┘    └──────────┘    └────┬─────┘
                                                                       │
                                                                       ▼
                                                                ┌──────────────┐
                                                                │  Streamlit   │
                                                                │ (dashboard)  │
                                                                └──────────────┘
```

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
| 2     | Object storage com MinIO            | 🔜 Próxima     |
| 3     | Warehouse analítico com DuckDB      | ⏳ Pendente    |
| 4     | Transformações com dbt              | ⏳ Pendente    |
| 5     | Orquestração com Airflow (Docker)   | ⏳ Pendente    |
| 6     | Indicadores e métricas financeiras  | ⏳ Pendente    |
| 7     | Dashboard com Streamlit             | ⏳ Pendente    |
| 8     | Polimento, documentação e portfólio | ⏳ Pendente    |

---

## Estrutura do repositório

```
b3-data-pipeline/
├── ingestion/             # Scripts de download e persistência (Etapa 1)
│   └── README.md
├── data/
│   └── raw/               # Parquet particionado (gitignored)
│       └── .gitkeep
├── notebooks/             # Exploração ad-hoc em Jupyter
├── docs/
│   ├── decisoes.md        # Decisões técnicas com racional
│   └── NOTAS.md           # Caderno de aprendizados por etapa
├── .gitignore
├── README.md
├── CLAUDE.md              # Diretrizes para sessões com Claude Code
└── requirements.txt
```

> Pastas como `dbt/`, `airflow/` e `dashboard/` ainda não existem — cada uma nasce na sua respectiva etapa. O repositório evolui em camadas, não nasce pronto.

---

## Setup local

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
```

---

## Decisões técnicas

As decisões de arquitetura e seus trade-offs estão documentadas em [`docs/decisoes.md`](docs/decisoes.md). Resumo das decisões já tomadas:

1. **Ambiente local em vez de cloud** — custo zero e iteração rápida; abro mão de exercitar IAM real.
2. **DuckDB em vez de BigQuery** — roda na máquina, SQL padrão e lê Parquet nativo; não exercito o BigQuery.
3. **6 tickers em vez do Ibovespa inteiro** — 4 setores cobertos, escalar é trivial; o número absoluto soa menos impressivo.
4. **Preço bruto e ajustado lado a lado no raw** (Etapa 1) — imutabilidade do raw; permite recalcular ajustes sem re-baixar.
5. **Arquivo Parquet por data, tickers juntos** (Etapa 1) — evita micro-arquivos por ticker e mantém partition pruning eficiente.
6. **Reexecução sobrescreve a partição** (Etapa 1) — idempotência simples no raw; correções viram nova execução, não nova versão.

---

## Aprendizados

O caderno de conceitos, dúvidas e descobertas de cada etapa fica em [`docs/NOTAS.md`](docs/NOTAS.md). O objetivo do projeto não é só entregar o pipeline — é entender cada peça bem o suficiente para defender em entrevista.
