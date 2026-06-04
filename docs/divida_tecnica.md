# Dívida técnica

> Arquivo **vivo**: cada etapa adiciona o que ficou consciente e
> deliberadamente para depois. Não é lista de bugs — é registro de
> trade-offs aceitos, com o gatilho de quando reabrir cada um.

**Convenção de cada item:** `ID` · descrição · motivo do adiamento ·
gatilho de quando tratar. Ordenado por etapa de origem.

---

## Etapa 5 — Orquestração (Airflow)

### DT-5.1 — `read_only=False` na conexão do DuckDB
`scripts/checar_warehouse.py` (e o setup) abrem o DuckDB com
`read_only=False`, acoplando setup de S3 (`httpfs`, credenciais) à
abertura da conexão em `warehouse/conexao.py`. Funciona para um
processo de cada vez, mas impede leitura concorrente.

- **Motivo do adiamento:** no fluxo atual (DAG sequencial + scripts
  manuais) nunca há dois leitores simultâneos; resolver agora seria
  YAGNI.
- **Gatilho:** quando a Etapa 7 (dashboard Streamlit) exigir leitura
  concorrente do `warehouse.duckdb` enquanto a DAG escreve — aí separar
  conexão read-only do setup de escrita.

### DT-5.2 — `requirements` único arrasta deps de dev para a imagem
A imagem do Airflow instala o conjunto completo (lock incluso), o que
traz `jupyter`, `jupyterlab`, `plotly`, `ipykernel` etc. para o runtime
do orquestrador — ~50 MB+ que nenhuma task usa.

- **Motivo do adiamento:** simplicidade de manter um único conjunto de
  deps; o overhead de imagem é irrelevante em ambiente local single-host.
- **Gatilho:** otimização de imagem no refactoring estruturado pós-Etapa
  7 — separar deps de runtime (ingestão/warehouse/dbt) das de
  exploração (jupyter/plotly), se a imagem virar incômodo.

### DT-5.3 — Retry declarado mas nunca exercitado
A DAG define `retries=2` e `retry_delay=5min`, mas isso nunca foi
disparado de fato — não sabemos empiricamente se o retry se comporta
como esperado sob falha real.

- **Motivo do adiamento:** exigiria injetar falha controlada; não era o
  foco da Etapa 5 (montar a orquestração).
- **Gatilho:** exercício pendente — derrubar o MinIO durante
  `extract_cotacoes` para forçar o retry e validar empiricamente
  (registrar a descoberta em `docs/NOTAS.md`).

### DT-5.4 — Backfill histórico não automatizado na DAG
A DAG só roda `--modo diario`. Backfill de histórico segue manual via
CLI (`--modo range`); não há uso de `data_interval` para reprocessar
datas passadas pela própria DAG.

- **Motivo do adiamento:** yfinance não revisa histórico retroativamente
  e o backfill inicial é evento único — não justifica automação.
- **Gatilho:** implementar `data_interval` na DAG se backfill
  automatizado virar requisito (ex.: reprocessar após correção de regra
  de negócio na Etapa 6).

---

## Derivadas das correções de segurança (M1–M8)

### DT-SEC.1 — Lock pinado conflita com a imagem do Airflow ✅ *fallback aplicado*
Tentamos instalar `requirements.lock` (versões `==`) no
`airflow/Dockerfile`, mas o lock foi gerado num venv standalone
(Python 3.13), **sem** as constraints da imagem `apache/airflow:2.10.5`.
Pinar libs comuns (Jinja2, click, pydantic, MarkupSafe…) sobre a imagem
oficial **quebrou o `docker compose build`** no `pip install`, como
previsto.

- **Resolução (aplicada):** fallback ativo — o `airflow/Dockerfile`
  voltou a usar `requirements.txt` (`>=`), deixando o `pip` resolver as
  versões contra as constraints da imagem base. O `requirements.lock`
  **permanece no repo** como referência do ambiente HOST (venv local de
  ingestão/warehouse/dbt), apenas fora do build do Airflow.
- **Estado:** o build reprodutível do **host** está coberto pelo lock; o
  build da **imagem do Airflow** depende da resolução do pip contra a
  imagem base, que é estável o suficiente para um projeto de portfólio.
- **Pendência (baixa prioridade):** gerar um lock que respeite as
  constraints oficiais do Airflow, p.ex.:
  `pip install -c https://raw.githubusercontent.com/apache/airflow/constraints-2.10.5/constraints-3.x.txt`
  e então as deps do projeto — só vale o esforço se o build da imagem
  precisar de reprodutibilidade byte-a-byte.

### DT-SEC.2 — Defaults de credenciais permanecem fracos em dev
`POSTGRES_PASSWORD`, `AIRFLOW_ADMIN_*` e `AIRFLOW__WEBSERVER__SECRET_KEY`
agora são parametrizados, mas os **defaults** (`airflow`/`admin`/
`CHANGE_ME_IN_PRODUCTION`) continuam fracos por design, para o dev local
subir sem fricção.

- **Motivo do adiamento:** o projeto é local single-host de portfólio;
  endurecer credenciais sem necessidade adiciona atrito sem ganho real.
- **Gatilho:** qualquer exposição além de `localhost` (deploy, demo
  pública) — aí gerar `AIRFLOW_SECRET_KEY` único, senha forte de Postgres
  e admin, todos via `.env` real (gitignored).

### DT-SEC.3 — `pip-audit` sem limiar de severidade
O CI (`.github/workflows/security.yml`) falha em **qualquer** CVE
conhecido, não só severidade alta — `pip-audit` não filtra por
severidade nativamente.

- **Motivo do adiamento:** manter o workflow simples e legível; falhar
  em qualquer CVE é o lado conservador (seguro) do trade-off.
- **Gatilho:** se o build começar a falhar por CVEs de baixa severidade
  sem fix disponível, introduzir `--ignore-vuln` pontual ou um passo de
  triagem por severidade.

---

<!-- Próximas etapas adicionam itens abaixo, agrupados por etapa de origem. -->
