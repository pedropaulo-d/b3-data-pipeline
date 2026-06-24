# Dívida técnica

> Arquivo **vivo**: cada etapa adiciona o que ficou consciente e
> deliberadamente para depois. Não é lista de bugs — é registro de
> trade-offs aceitos, com o gatilho de quando reabrir cada um.

**Convenção de cada item:** `ID` · descrição · motivo do adiamento ·
gatilho de quando tratar. Ordenado por etapa de origem.

---

## Etapa 5 — Orquestração (Airflow)

### DT-5.1 — `read_only=False` na conexão do DuckDB ✅ *resolvida*
`scripts/checar_warehouse.py` (e o setup) abriam o DuckDB com
`read_only=False`, acoplando o setup de S3 (`httpfs`, credenciais) à
abertura da conexão em `warehouse/conexao.py`. Funcionava para um
processo de cada vez, mas impedia leitura concorrente.

- **Resolução (2026-06-18, Forma C):** `obter_conexao(read_only)` agora
  **só abre** o arquivo; o setup de S3 saiu para uma função separada,
  `configurar_s3(con)`. Quem só lê marts locais (`validar_etapa6`) abre
  em `read_only=True` sem S3; quem lê as views `raw.*`/`staging`
  (`checar_warehouse`) abre em `read_only=True` **e** chama
  `configurar_s3` — descoberta empírica: `LOAD`/`SET` de S3 são estado de
  sessão e rodam em conexão read-only (a premissa antiga de que "SET exige
  read-write" não se confirmou no DuckDB do projeto). `setup.py` abre em
  escrita (cria views) + `configurar_s3`. Habilita o dashboard da Etapa 7
  a ler concorrentemente enquanto a DAG escreve.
- **Trade-off aceito:** quem precisa de S3 faz duas chamadas
  (`obter_conexao` + `configurar_s3`) em vez de uma. Ver
  `docs/decisoes.md` (2026-06-18).

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

## Etapa 7 — Dashboard (deploy)

### DT-7.1 — `warehouse.duckdb` versionado incha o histórico do Git
Para o deploy no Streamlit Cloud, o `warehouse.duckdb` (6,6 MB) passou a
ser versionado como **snapshot** dos marts (ver `docs/decisoes.md`,
2026-06-24). O Git versiona o arquivo binário **inteiro** a cada commit,
não o delta — então cada atualização do snapshot soma ~6 MB ao histórico
permanente do `.git`, mesmo que poucas linhas dos marts tenham mudado.

- **Motivo do adiamento:** com atualização deliberada (não a cada `dbt
  build`) e um arquivo pequeno, o crescimento é lento e aceitável para um
  portfólio. A alternativa custaria código novo agora, sem ganho
  proporcional.
- **Gatilho:** se o `.git` passar de um tamanho incômodo (regra de bolso:
  alguns commits do snapshot tornando o `git clone` visivelmente lento, ou
  `.git` > ~100 MB). Aí migrar para uma das opções já consideradas:
  - **Parquet (opção 2):** exportar os 4 marts para Parquet e versionar só
    eles; o dashboard abre via DuckDB `read_parquet`. Repo mais leve e
    diff-friendly (colunar), mas exige um passo de export e ajuste no
    `data.py`.
  - **Git LFS:** manter o `.duckdb` mas fora do histórico regular (ponteiros
    + storage LFS). Resolve o inchaço sem mudar o app; depende de o host de
    deploy suportar LFS no checkout.

### DT-7.2 — Dashboard acopla a `ingestion.config` (exige credenciais S3 no import)
O dashboard, ao importar `warehouse.conexao`, importa transitivamente
`ingestion.config`, que **valida `MINIO_*` no import** (`_exigir_var`).
Resultado: para subir o dashboard no Streamlit Cloud é preciso definir
secrets `MINIO_*` **placeholder (dummy)** — mesmo o dashboard NÃO usando
MinIO (abre o DuckDB em `read_only=True` e lê só marts locais, sem
`configurar_s3`).

- **Por que é dívida:** o dashboard não deveria depender de configuração de
  *ingestão*. Abrir o DuckDB em read-only deveria exigir apenas o **caminho
  do arquivo** — nenhuma credencial de S3. Hoje a exigência vem "de carona"
  numa cadeia de imports, não de uma necessidade real do app.
- **Motivo do adiamento:** desacoplar agora mexeria em `ingestion.config`
  (consumido também pela ingestão e pelo setup do warehouse); o custo não se
  justifica só para o deploy, e o contorno (secrets dummy) é trivial e está
  documentado em `dashboard/README.md`.
- **Gatilho/solução:** na refatoração estruturada (pós-Etapa 7), fazer
  `obter_conexao(read_only=True)` **não importar nem exigir**
  `ingestion.config`. Caminhos possíveis:
  - mover a resolução das credenciais S3 para **dentro** de `configurar_s3`
    (lazy — só lê `MINIO_*` quando a função é de fato chamada), ou
  - separar a config de **caminho do DuckDB** da config de **S3** (módulos
    distintos), para `conexao.py` depender só da primeira.

  Quando resolvido, os secrets dummy do Streamlit Cloud deixam de ser
  necessários. Relacionado à refatoração **Forma C** (DT-5.1, parcialmente
  feita: separou `obter_conexao` de `configurar_s3`, mas o import de
  `ingestion.config` em `conexao.py` permaneceu).

---

<!-- Próximas etapas adicionam itens abaixo, agrupados por etapa de origem. -->
