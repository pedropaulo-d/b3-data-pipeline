# dashboard/

Dashboard **Streamlit + Plotly** sobre os marts da Etapa 6. Camada de
visualização do pipeline — equivale, em escala de portfólio, a um Looker /
Power BI / Metabase ligado ao warehouse.

> Estado atual: **Aba 1 — Visão Individual**. A Aba 2 (Comparação entre
> tickers) chega na próxima rodada; a estrutura de abas já está pronta.

## O que mora aqui

- `app.py` — entry point Streamlit: layout, abas, cartões `st.metric` e os
  5 gráficos Plotly da visão individual.
- `data.py` — acesso a dados: conexão cacheada (`@st.cache_resource`) e
  queries cacheadas (`@st.cache_data`), todas **parametrizadas** e
  **somente leitura** sobre os marts.

## Como rodar

Pré-requisitos:

1. `warehouse.duckdb` **populado** — rode o pipeline antes (ingestão →
   `warehouse.setup` → `dbt build`), ou dispare a DAG `pipeline_b3_diario`
   no Airflow. Sem os marts materializados, o dashboard não tem o que ler.
2. Dependências do dashboard instaladas:

   ```bash
   pip install -r requirements-dashboard.txt
   ```

Então, a partir da **raiz do repositório**:

```bash
streamlit run dashboard/app.py
```

Abre em `http://localhost:8501`. Rodar da raiz garante que `import
dashboard` / `import warehouse` resolvam.

## Conexão e cache

O Streamlit reexecuta o script inteiro a cada interação (trocar de ticker,
mexer no período). Para não reabrir o banco nem re-rodar SQL a cada rerun:

- a conexão é aberta **uma vez** (`@st.cache_resource`) e reusada;
- cada query é cacheada (`@st.cache_data`) — os marts são estáticos
  durante a sessão.

A conexão é **somente leitura** (`obter_conexao(read_only=True)`), e o
dashboard **não** configura S3: lê apenas marts (tabelas locais no
`.duckdb`), nunca as views `raw.*` que apontam para o MinIO.

## Limitação de concorrência (importante)

O DuckDB embarcado admite **1 escritor exclusivo OU N leitores** sobre o
mesmo arquivo — não os dois ao mesmo tempo. Consequências:

- Vários dashboards / leitores simultâneos: **ok**.
- Se a **DAG do Airflow** (ou um `dbt build` manual) estiver **escrevendo**
  no `warehouse.duckdb`, abrir o dashboard pode falhar com erro de lock.

O `app.py` trata isso graciosamente: se a conexão falhar, mostra um
`st.error` amigável ("warehouse sendo atualizado, tente em instantes") em
vez de estourar stack trace. Recarregar a página depois que a escrita
terminar resolve.

## Deploy futuro (possibilidade)

O dashboard é **deployável por conta própria** (ex.: Streamlit Cloud) —
por isso as deps ficam num `requirements-dashboard.txt` separado, com
ciclo de vida distinto do runtime do pipeline. Pontos a resolver num
deploy real, ainda **fora do escopo** desta rodada:

- **Acesso ao dado.** O `warehouse.duckdb` é local e gitignored; um deploy
  remoto precisaria de uma cópia do arquivo (ou apontar para um warehouse
  acessível pela rede). DuckDB embarcado não foi pensado para acesso
  remoto concorrente.
- **Variáveis de ambiente.** O dashboard importa `warehouse.conexao`, que
  importa `ingestion.config` — este lê `MINIO_*` do `.env` **no import**,
  mesmo o dashboard não usando S3. Num deploy isolado, essas variáveis
  precisam existir (valores podem ser dummy) ou o import falha. Desacoplar
  isso é candidato a dívida técnica se o deploy virar requisito.
