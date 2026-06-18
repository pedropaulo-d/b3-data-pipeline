# CLAUDE.md

> Este arquivo **não é instrução para o usuário** — é contexto persistente carregado em toda sessão do Claude Code neste repositório. Trate-o como diretriz operacional. Este arquivo não pode passar de 200 linhas.

---

## Sobre o projeto

`b3-data-pipeline` é um **projeto de portfólio** para vaga de engenharia de dados. O objetivo principal não é entregar um pipeline funcional o mais rápido possível — é o usuário **aprender cada peça da stack a ponto de saber defender em entrevista**.

Isso muda como você deve colaborar. Otimize para compreensão do usuário, não para velocidade de entrega.

---

## Princípio fundamental

> Use o Claude Code para o que é **trabalho**. O usuário faz o que é **aprendizado**.
>
> **Trabalho:** digitar boilerplate, lembrar sintaxe, configurar Docker, escrever testes.
>
> **Aprendizado:** entender o dado, decidir modelagem, depurar conceitualmente, explicar decisões.

Se algo cai no lado "aprendizado", **pare e devolva ao usuário** — mesmo que seja mais lento. Resolver no automático rouba a entrevista futura dele.

---

## Regras de delegação por tipo de tarefa

O usuário atua como **tech lead / arquiteto de dados** deste projeto. Sua função
é executar a implementação dentro das decisões que ele toma. Ele revisa o
código gerado — não o escreve linha a linha.

### ✅ Pode (e deve) fazer integralmente

- Estrutura de pastas e arquivos
- Scripts Python completos (ingestão, transformação, utilidades)
- `docker-compose.yml`, `Dockerfile`, configuração de serviços
- Modelos dbt em SQL/Jinja a partir da modelagem que o usuário desenhou
- DAGs do Airflow a partir do fluxo que o usuário definiu
- Testes (pytest, dbt tests)
- READMEs, docstrings, comentários, diagramas Mermaid
- Debug de erros, refactor, otimização

Entregue código completo e funcional. Não deixe TODOs nem stubs esperando o
usuário preencher, exceto quando explicitamente pedido.

### ⚠️ NÃO faça sem decisão explícita do usuário

Estas são as áreas que o usuário se reserva. Em todas elas, **pergunte antes
de assumir**, apresente alternativas com trade-offs claros, e só implemente
depois da decisão dele:

- **Modelagem dimensional**
  - Granularidade da fato ("1 linha = o quê?")
  - Quais dimensões existem e por quê
  - Surrogate key vs natural key
  - SCD tipo 1, 2 ou 3 em cada dimensão
  - Esquema estrela vs floco

- **Decisões de arquitetura**
  - Separação de camadas (raw/staging/intermediate/marts)
  - Estratégia de particionamento (por dia, mês, ticker)
  - Formato de storage e compressão
  - Materialização dbt (view, table, incremental, ephemeral)
  - Estratégia de orquestração (uma DAG monolítica vs múltiplas)

- **Regras de negócio e lógica financeira**
  - Definição de retorno (simples, log, ajustado por proventos)
  - Tratamento de dividendos e splits
  - Janelas móveis (qual período, com ou sem preenchimento)
  - Fórmulas de indicadores (P/L, dividend yield, payout, etc.)
  - Como tratar feriados, pregões parciais, NaN

Comportamento esperado nestas áreas: liste as opções viáveis, explique o
trade-off de cada uma, recomende uma se tiver convicção técnica, **e espere
a escolha do usuário antes de codar**.

### Comportamento esperado em sessões

1. **Em decisões de modelagem/arquitetura/negócio:** pergunte primeiro,
   implemente depois. Mesmo que pareça óbvio.
2. **Em implementação:** entregue código completo, idiomático, com docstrings
   e logging adequado. Não peça ao usuário para "preencher os detalhes".
3. **Ao escrever código novo que envolve um conceito não trivial** (window
   function complexa, macro Jinja, retry com backoff), **explique brevemente
   a escolha no commit message ou em comentário** — para o usuário revisar
   conscientemente, não apenas aceitar.
4. **Se o usuário pedir algo que conflita com decisões anteriores** registradas
   em `docs/decisoes.md`, aponte o conflito antes de executar.
5. **Não pule etapas do plano do projeto.** A sequência é pedagógica para o
   usuário; antecipar Airflow antes da Etapa 5 não ajuda.
6. **Sinalize delegação excessiva**: se o usuário pedir algo que cai em "❌",
   lembre-o do escopo de aprendizado antes de executar.

---

## Convenções técnicas

### Python

- Versão **3.11+**
- Gerenciador: **pip + venv** (não Poetry, não uv)
- Bibliotecas centrais: `pandas`, `pyarrow`
- **Logging via `logging` stdlib**, nunca `print` em código de produção
- `except` sempre específico (`except ValueError:`, nunca `except:` ou `except Exception:` sem necessidade)

### Estrutura de dados

- Formato em disco: **Parquet** com particionamento Hive `ano=YYYY/mes=MM/dia=DD/cotacoes.parquet` (raw layer mora no MinIO desde a Etapa 2; ver "Escopo travado").
- **Imutabilidade**: raw é append-only; correções viram nova partição.
- **Idempotência semântica**: rodar duas vezes não duplica nem corrompe estado; bytes podem variar (metadata do PyArrow), conteúdo lógico não.

### Git

- Mensagens de commit em **português**
- Granularidade: um commit por unidade lógica (não acumular dia inteiro em um commit)
- **Nunca commitar** `.env`, conteúdo de `data/raw/`, arquivos `*.duckdb`

### Documentação

- **`docs/decisoes.md`** — decisões técnicas com contexto, racional e trade-off aceito
- **`docs/NOTAS.md`** — caderno de aprendizados por etapa (conceitos, dúvidas, descobertas)

---

## Escopo travado (não alterar sem discussão)

### Escopo de domínio

- **Tickers:** PETR4, VALE3, ITUB4, BBDC4, WEGE3, ABEV3
- **Histórico inicial:** 5 anos
- **Granularidade:** diária (1 linha = 1 ticker × 1 data)

### Stack e ambiente

- **Linguagem:** Python 3.11+
- **Gerenciador de pacotes:** pip + venv (não Poetry, não uv)
- **Object storage:** MinIO via Docker Compose
- **Warehouse:** DuckDB (Etapa 3)
- **Transformação:** dbt-duckdb (Etapa 4)
- **Orquestração:** Apache Airflow 2.10 via Docker Compose, LocalExecutor + Postgres metastore (Etapa 5)
- **Dashboard:** Streamlit (Etapa 7)
- **Ambiente:** local, single-host

### Decisões arquiteturais consolidadas

Todas registradas em `docs/decisoes.md`. NÃO questionar em sessões futuras a menos que o usuário peça explicitamente:

**Etapa 1 — Ingestão:** preço bruto+ajustado, 1 arquivo Parquet por data, idempotência por sobrescrita, volume Int64 nullable.

**Etapa 2 — Object storage:** MinIO em Compose dedicado, bucket único b3-data com prefixos por camada, storage.py escreve só no MinIO, boto3 direto (não s3fs).

**Etapa 3 — Warehouse:** DuckDB persistente em `warehouse.duckdb` (raiz, gitignored), schema `raw` como view sobre `read_parquet` do MinIO via httpfs, SQL exploratório em `sql/exploratoria/` + notebook narrativo, `warehouse/conexao.py` reusa credenciais de `ingestion.config`.

**Etapa 4 — dbt:** estrela Kimball em `marts` (`fato_cotacoes_diarias` + `dim_empresa` + `dim_tempo`); surrogate keys nas dims, chave composta na fato; SCD 1 em `dim_empresa`; staging = view, marts = table; seed `empresas.csv`; testes nativos + 3 custom (volume, max≥min, fechamento no range); `dbt/profiles.yml` versionado (credenciais via `env_var`); `dim_tempo` gera calendário 2020–2030 independente da fato.

**Etapa 5 — Airflow:** compose único `docker-compose.yml` (renomeado de `docker-compose.minio.yml`); imagem custom `airflow/Dockerfile` (apache/airflow:2.10.5 + `requirements.txt`); DAG `pipeline_b3_diario` com 4 BashOperator (`extract_cotacoes` → `refresh_warehouse` → `dbt_run` → `dbt_test`); schedule `0 20 * * *` em `America/Sao_Paulo`, `catchup=False`, `retries=2` (5min); projeto bind-montado em `/opt/project`; dentro do container `MINIO_ENDPOINT=http://minio:9000` (host segue com `localhost:9000`).

**Etapa 6 — Indicadores:** ingestão de dividendos (`ingestion/dividendos/`, partição por ano `raw/dividendos/ano=YYYY/`, CLI `--modo inicial|incremental`, reusa `ingestion.s3_client`); marts `mart_indicadores_diarios` (retorno simples/log/acumulado, médias móveis 7/30/90/200 com contagem, volatilidade 30/90/252 amostral anualizada √252, drawdown — base **fechamento ajustado**) + `mart_indicadores_resumo` (1 linha/ticker) + `fato_dividendos` (view, dims conformadas) + `mart_dividend_yield` (DY trailing 12m sobre **fechamento bruto**, range join); 4 custom tests novos; fundamentalistas (P/L, P/VP, ROE) fora por limitação do yfinance.

### Convenções de validação

- Idempotência semântica validada empiricamente em cada etapa que toca storage. Script reutilizável em `scripts/validar_idempotencia.py`.
- Sanity checks informais (contagem de arquivos vs calendário B3, etc) registrados em `docs/NOTAS.md` como descoberta.

### Estrutura do repositório consolidada

```
b3-data-pipeline/
├── ingestion/              # Pipeline de ingestão (Etapa 1+)
├── scripts/                # Utilitários de validação e operação
├── warehouse/              # Conexão e setup do DuckDB (Etapa 3+)
├── dbt/                    # Projeto dbt (Etapa 4); profiles.yml versionado
├── sql/exploratoria/       # SQL exploratório versionado
├── notebooks/              # Exploração e narrativa
├── data/raw/               # HISTÓRICO da Etapa 1; raw vive no MinIO
├── docs/                   # decisoes.md, NOTAS.md
├── airflow/                # Dockerfile, dags/, logs/, plugins/ (Etapa 5)
├── docker-compose.yml      # MinIO (Etapa 2) + Airflow (Etapa 5)
├── .env.example            # Versionado
├── .env                    # Gitignored
├── warehouse.duckdb        # Gitignored, regenerável via warehouse.setup
└── requirements.txt
```

Pasta futura: `dashboard/` (Etapa 7).

---

Mudanças de escopo são discussão consciente entre Claude Code e usuário, não otimização silenciosa.

---

## Glossário rápido

- **Raw layer** — dado bruto, como veio da fonte, particionado por data de ingestão. Nunca é alterado.
- **Staging** — dado limpo e tipado, ainda em formato próximo do raw. Camada intermediária do dbt.
- **Marts** — dado modelado para consumo analítico (fatos e dimensões). Camada final do dbt.
- **Granularidade** — o que cada linha representa. Ex.: "uma linha por ticker por dia".
- **Idempotência** — propriedade de uma operação cujo resultado não muda se ela for executada mais de uma vez com os mesmos inputs.
