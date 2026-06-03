# Airflow — Etapa 5

Orquestração do pipeline B3. Esta pasta concentra tudo do Airflow:
imagem custom, DAGs, logs e plugins. A infraestrutura sobe via Docker
Compose junto com o MinIO (raiz do repo, `docker-compose.yml`).

---

## O que a DAG faz

DAG: **`pipeline_b3_diario`** (arquivo: `dags/pipeline_b3_diario.py`).

Quatro tasks em sequência linear, cada uma um `BashOperator` que roda o
mesmo comando que o usuário rodaria à mão antes da automação:

| Ordem | Task                | Comando                                            | Função |
|-------|---------------------|----------------------------------------------------|--------|
| 1     | `extract_cotacoes`  | `python -m ingestion.main --modo diario`           | Baixa o pregão do dia para os 6 tickers e grava partição Parquet no MinIO. |
| 2     | `refresh_warehouse` | `python -m warehouse.setup`                        | Garante schema `raw` e view `raw.cotacoes` no `warehouse.duckdb`. |
| 3     | `dbt_run`           | `dbt run --profiles-dir ./` (dentro de `dbt/`)     | Materializa staging (view) + marts (`fato_cotacoes_diarias`, `dim_empresa`, `dim_tempo`). |
| 4     | `dbt_test`          | `dbt test --profiles-dir ./` (dentro de `dbt/`)    | Roda os 24 testes (nativos + dbt_utils + custom). |

Dependências: `extract_cotacoes >> refresh_warehouse >> dbt_run >> dbt_test`.

**Schedule:** `0 20 * * *` no fuso `America/Sao_Paulo` — 20h horário de
Brasília, após o fechamento do pregão.

**catchup=False:** despausar a DAG **não** dispara backfill de datas
passadas. A primeira execução ocorre no próximo horário-alvo.

**Política de retry:** 2 tentativas adicionais por task, intervalo fixo
de 5 minutos. Cobre falha transitória do yfinance/MinIO; não esconde bug
persistente (na terceira falha a DAG marca como `failed`).

---

## Como subir

Pré-requisitos: Docker e Docker Compose. O `.env` na raiz precisa
existir (copiar de `.env.example` se ainda não foi).

```bash
# Primeira vez (ou depois de mudar requirements.txt / Dockerfile):
docker compose build

# Subir todos os serviços (MinIO, Postgres, Airflow init/webserver/scheduler):
docker compose up -d
```

A primeira subida demora **1 a 3 minutos**: build da imagem custom +
init do Airflow (`db migrate` + criação do usuário admin). É esperado
ver `b3-airflow-init` no estado `exited (0)` em `docker compose ps`
depois de terminar — é um init container, não um serviço persistente.

Conferir saúde de todos os serviços:

```bash
docker compose ps
```

Você deve ver 6 containers: `b3-minio`, `b3-minio-init` (exited 0),
`b3-airflow-postgres` (healthy), `b3-airflow-init` (exited 0),
`b3-airflow-webserver` (healthy) e `b3-airflow-scheduler` (running).

---

## Acessar a UI

- URL: <http://localhost:8080>
- Login: **admin** / **admin** (criado pelo `airflow-init`)

A DAG `pipeline_b3_diario` aparece **pausada** por padrão
(`DAGS_ARE_PAUSED_AT_CREATION=true`). Para rodar:

1. Clicar no toggle ao lado do nome (despausa).
2. Botão "Trigger DAG" no canto superior direito para forçar execução
   imediata, ou aguardar o schedule cron.
3. Acompanhar as 4 tasks ficando verdes em `Grid View`.

Logs por task: clicar na task no grid → aba "Logs". Os arquivos
correspondentes ficam em `airflow/logs/` no host (bind mount), úteis
para debug fora da UI.

---

## Endpoint MinIO: host vs container

**Este é o ponto mais delicado da etapa.** Errar aqui dá erro de
"connection refused" no `extract_cotacoes`.

| Onde o código roda                       | `MINIO_ENDPOINT`         |
|------------------------------------------|--------------------------|
| Host (terminal, IDE, `python -m ...`)    | `http://localhost:9000`  |
| Container do Compose (Airflow, etc.)     | `http://minio:9000`      |

**Por quê.** Em ambos os casos o MinIO escuta na porta 9000. A
diferença é o nome:

- O host alcança o MinIO porque a porta 9000 do container está mapeada
  para a porta 9000 do localhost (`ports: 9000:9000`).
- O container do Airflow não passa pelo host: ele resolve o serviço
  `minio` pelo DNS interno do Compose. Dentro daquele namespace,
  `localhost` é o **próprio container**, não o host.

**Como o projeto resolve.**

- `.env` do host: `MINIO_ENDPOINT=http://localhost:9000`.
- `docker-compose.yml`, bloco `x-airflow-common.environment`, hardcoda
  `MINIO_ENDPOINT=http://minio:9000` para os 3 serviços do Airflow.

A sobrescrita explícita no compose vence o `.env` — `ingestion/config.py`
e `warehouse/conexao.py` leem `os.environ`, então recebem o valor certo
para cada contexto.

A variável complementar `MINIO_ENDPOINT_HOST_PORT` (usada pelo dbt-duckdb,
que não aceita esquema) segue o mesmo padrão: `localhost:9000` no host,
`minio:9000` no container.

---

## Estrutura de pastas

```
airflow/
├── Dockerfile           # Imagem custom (airflow:2.10.5 + requirements.txt do projeto)
├── README.md            # Este arquivo
├── dags/
│   └── pipeline_b3_diario.py
├── logs/                # Bind mount em runtime; gitignored (.gitkeep preserva pasta)
└── plugins/             # Bind mount em runtime; gitignored (.gitkeep preserva pasta)
```

O **projeto inteiro** é bind-montado em `/opt/project` dentro dos
containers do Airflow. É por isso que os BashOperators conseguem rodar
`python -m ingestion.main`, `python -m warehouse.setup` e `dbt`
diretamente — eles enxergam os módulos como se estivessem no host.

---

## Troubleshooting comum

**Falha em `extract_cotacoes` com "Could not connect to the endpoint URL"
ou similar.** Endpoint apontando para `localhost:9000` dentro do
container. Confirmar:

```bash
docker compose exec airflow-scheduler env | grep MINIO
```

Deve mostrar `MINIO_ENDPOINT=http://minio:9000`.

**Falha em `dbt_run` ou `dbt_test` com "IO Error: Cannot open file
'../warehouse.duckdb'".** O bind mount do projeto não pegou. Confirmar
que `docker-compose.yml` está com `- .:/opt/project` no bloco
`x-airflow-common.volumes` e fazer `docker compose down && docker compose up -d`.

**Task falha com `ModuleNotFoundError: No module named 'yfinance'` (ou
duckdb, dbt, etc.).** A imagem custom não instalou os requirements ou
foi cacheada antes de ter o pacote. Forçar rebuild:

```bash
docker compose build --no-cache
docker compose up -d
```

**`airflow-init` em loop de restart.** O Postgres ainda não está
healthy. Esperar mais alguns segundos; o `depends_on:
service_healthy` deveria proteger contra isso, mas se o disco está
lento, pode estourar `start_period`.

**Senha admin esquecida.** O usuário admin é recriado a cada
`airflow-init` (que ignora erro de "já existe"). Para resetar:
`docker compose run --rm airflow-init airflow users delete --username admin`
seguido de uma nova subida.

---

## Limites desta etapa

- **Sem indicadores financeiros** (média móvel, retornos acumulados,
  volatilidade) — fica para a Etapa 6.
- **Sem dashboard Streamlit** — Etapa 7.
- **LocalExecutor**, não Celery. Sem worker separado, sem Redis. Para
  o volume do projeto isso basta; ver `docs/decisoes.md` para o porquê.
- **Sem alertas externos** (Slack, e-mail). A UI do Airflow é a única
  fonte de notificação. Adicionar callbacks `on_failure_callback` é
  trivial quando a fonte de alerta existir.
