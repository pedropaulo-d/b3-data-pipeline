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

### DT-5.2 — `requirements` único arrasta deps de dev para a imagem ✅ *resolvida*
A imagem do Airflow instalava o conjunto completo, trazendo `jupyter`,
`ipykernel`, `plotly` etc. para o runtime do orquestrador — peso que
nenhuma task usa.

- **Resolução (2026-06-18):** `jupyter`, `ipykernel` e `plotly` saíram do
  `requirements.txt` e foram para `requirements-dev.txt`. Como o
  `airflow/Dockerfile` instala apenas `requirements.txt`, a imagem do
  Airflow ficou mais enxuta automaticamente, sem tocar no Dockerfile. A
  motivação imediata foi a segurança (ver DT-SEC.4), mas o efeito colateral
  resolve esta dívida de peso de imagem.

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
  versões contra as constraints da imagem base.
- **Estado:** a reprodutibilidade do build da **imagem do Airflow** vem
  da imagem base `apache/airflow:2.10.5` (que já fixa as versões das libs
  comuns) + `requirements.txt`, estável o suficiente para um projeto de
  portfólio.
- **Atualização (2026-06-18):** o `requirements.lock` foi **removido** do
  repo (ver DT-SEC.4) — era órfão e desatualizado. Se um dia for preciso
  um lock determinístico, gerá-lo via constraints oficiais do Airflow,
  p.ex.:
  `pip install -c https://raw.githubusercontent.com/apache/airflow/constraints-2.10.5/constraints-3.x.txt`
  e então as deps do projeto.

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

### DT-SEC.4 — `requirements.lock` removido ✅ *resolvida*
O `requirements.lock` foi **removido** do repositório (2026-06-18). Era um
arquivo **órfão**: não entrava no `airflow/Dockerfile` (que usa
`requirements.txt` por DT-SEC.1) nem no CI (que passou a auditar só o
runtime), e estava **desatualizado** — congelado quando Jupyter ainda
fazia parte do `requirements.txt`, listava transitivas de dev (`bleach`,
`tornado`, `jupyter-server`) e os 8 CVEs que faziam o `pip-audit` falhar.

- **Decisão:** mantê-lo dava **falsa sensação de reprodutibilidade** sem
  uso concreto. A reprodutibilidade do build do Airflow já vem da imagem
  base `apache/airflow:2.10.5` (constraints próprias) + `requirements.txt`.
- **Gatilho (recriar):** se reprodutibilidade exata do ambiente HOST virar
  requisito, gerar um lock determinístico **via constraints oficiais do
  Airflow** (constraints-2.10.5), não por `pip freeze` de um venv
  standalone — ver DT-SEC.1.

---

## Etapa 6 — Indicadores e métricas financeiras

### DT-6.1 — Deprecation do dbt 1.11 em testes genéricos
O `dbt build` emite `MissingArgumentsPropertyInGenericTestDeprecation`
(11 ocorrências). A partir de uma versão futura do dbt, os argumentos de
testes genéricos (ex.: `relationships` com `to`/`field`) precisam migrar
para a propriedade aninhada `arguments:` no `schema.yml`, em vez de
ficarem soltos ao lado de `name:`.

- **Motivo do adiamento:** é só **deprecation warning** — não quebra nada
  hoje, todos os 49 testes passam. Migrar agora seria edição mecânica de
  11 blocos sem ganho funcional imediato.
- **Gatilho:** tratar no refactoring estruturado pós-Etapa 7, ou no
  momento em que a versão do dbt for atualizada (quando o warning vira
  erro).

---

<!-- Próximas etapas adicionam itens abaixo, agrupados por etapa de origem. -->
