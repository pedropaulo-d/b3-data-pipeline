# dashboard/

Dashboard **Streamlit + Plotly** sobre os marts da Etapa 6. Camada de
visualização do pipeline — equivale, em escala de portfólio, a um Looker /
Power BI / Metabase ligado ao warehouse.

> Estado atual: **completo, 2 abas** — Aba 1 (Visão Individual) e Aba 2
> (Comparação entre tickers). Etapa 7 concluída.

## O que mora aqui

- `app.py` — entry point Streamlit: layout, abas, cartões `st.metric`, os
  gráficos Plotly da visão individual e os da comparação.
- `data.py` — acesso a dados: conexão cacheada (`@st.cache_resource`) e
  queries cacheadas (`@st.cache_data`), todas **parametrizadas** e
  **somente leitura** sobre os marts.
- `requirements.txt` — ponteiro (`-r ../requirements-dashboard.txt`) para
  o Streamlit Cloud detectar as deps automaticamente (ver Deploy abaixo).

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

## Deploy no Streamlit Community Cloud

O dashboard é **deployável por conta própria**. O deploy em si é manual,
no site do Streamlit Cloud, com a conta do dono do repo. O repositório já
está preparado: o `warehouse.duckdb` é versionado como **snapshot** dos
marts (ver "Política de atualização do snapshot" abaixo), e o
`dashboard/requirements.txt` faz a nuvem detectar as deps certas.

### Como o app na nuvem lê os dados

O app lê o `warehouse.duckdb` **versionado no repo** (um *snapshot* dos
marts), em modo somente leitura. **Não** são dados ao vivo: a nuvem não
tem acesso ao MinIO nem à máquina local. Por isso a Parte 0 desta entrega
verificou que o dashboard consulta apenas tabelas materializadas
(`marts.*`, fisicamente no `.duckdb`) — nunca as views `raw.*`/`staging.*`,
que apontariam para o MinIO inexistente na nuvem.

### Passos manuais (no site do Streamlit Cloud)

1. Faça push do repo (incluindo o `warehouse.duckdb`) para o GitHub.
2. Em <https://share.streamlit.io>, conecte a conta GitHub e clique em
   **New app** → **Deploy a public app from GitHub**.
3. Preencha:
   - **Repository:** `Pedro/b3-data-pipeline` (o seu fork/remote).
   - **Branch:** `main`.
   - **Main file path:** `dashboard/app.py`.
4. **Dependências:** nada a configurar. O Cloud detecta automaticamente o
   `dashboard/requirements.txt` (busca primeiro no diretório do entrypoint),
   que inclui `../requirements-dashboard.txt`. O `requirements.txt` da raiz
   (runtime do pipeline) é ignorado.
5. **Secrets (OBRIGATÓRIO):** em **Advanced settings → Secrets**, cole as
   variáveis abaixo. O dashboard não usa MinIO, mas importa
   `ingestion.config`, que **exige** essas variáveis no import (senão o app
   quebra ao subir). Valores **dummy** bastam — secrets de nível raiz no
   Streamlit Cloud viram variáveis de ambiente, que é o que o `config` lê:

   ```toml
   MINIO_ENDPOINT = "http://localhost:9000"
   MINIO_ACCESS_KEY = "dummy"
   MINIO_SECRET_KEY = "dummy"
   ```

6. Clique em **Deploy**. A URL pública (`https://<algo>.streamlit.app`) sai
   ao fim — cole-a no README da raiz.

### Política de atualização do snapshot

O `warehouse.duckdb` versionado é um **snapshot atualizado deliberadamente**,
não a cada `dbt build` local. Para publicar dados novos:

1. Regenere o warehouse pelo pipeline (ingestão → `warehouse.setup` →
   `dbt build`, ou rode a DAG).
2. `git add warehouse.duckdb` e **commit consciente** ("atualiza snapshot
   do dashboard — dados até AAAA-MM-DD").
3. Push → o Streamlit Cloud redeploya sozinho ao detectar o commit.

Isso evita inchar o histórico do Git com commits binários a cada build. Se
o `.git` crescer demais, a alternativa (Parquet/Git LFS) está registrada em
`docs/divida_tecnica.md`.
