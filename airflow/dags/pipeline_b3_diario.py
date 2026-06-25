"""DAG principal do pipeline B3 — execução diária.

Automatiza a sequência manual das Etapas 4 e 6:

    1a. python -m ingestion.main --modo diario             ┐ em
    1b. python -m ingestion.dividendos.main --modo incremental ┘ paralelo
    2.  python -m warehouse.setup                          (espera 1a e 1b)
    3.  dbt run  (no diretório dbt/)
    4.  dbt test (no diretório dbt/)

As duas ingestões (cotações e dividendos) são independentes entre si e
rodam em PARALELO — o LocalExecutor executa tasks concorrentes no mesmo
host. ``refresh_warehouse`` é um ponto de fan-in: só dispara depois que
AMBAS terminam, porque ele (re)cria as views ``raw.cotacoes`` e
``raw.dividendos``, e o ``dbt run`` seguinte consome as duas.

Cada passo vira uma task BashOperator que executa o MESMO comando que
rodaria no terminal do host. O projeto inteiro é montado em
``/opt/project`` dentro dos containers do Airflow (ver
``docker-compose.yml`` -> ``x-airflow-common.volumes``), então os
módulos Python e o subdiretório ``dbt/`` ficam acessíveis a partir
desse caminho.

Schedule: 0 20 * * * em America/Sao_Paulo (todo dia às 20h horário de
Brasília — depois do fechamento do pregão e do prazo de publicação dos
dados ajustados pelo provedor).

Política de retries: 2 tentativas adicionais por task, com intervalo
fixo de 5 minutos (sem backoff exponencial). Cobre falhas transitórias
do yfinance e do MinIO sem mascarar bugs persistentes.
"""

from __future__ import annotations

import pendulum
from airflow.models.dag import DAG
from airflow.operators.bash import BashOperator

# Raiz do projeto dentro do container, conforme bind mount em
# docker-compose.yml (`.:/opt/project`).
PROJECT_DIR = "/opt/project"

# Aplicado a TODAS as tasks da DAG via `default_args`. Reaproveitar
# essa estrutura mantém a política de retry consistente entre tasks
# sem repetir parâmetros em cada operador.
default_args = {
    "retries": 2,
    "retry_delay": pendulum.duration(minutes=5),
}

with DAG(
    dag_id="pipeline_b3_diario",
    description=(
        "Pipeline diário B3: ingestão de cotações + dividendos (yfinance, "
        "em paralelo) -> warehouse (DuckDB) -> dbt run -> dbt test."
    ),
    schedule="0 20 * * *",
    # start_date no passado recente + catchup=False: a primeira
    # execução agendada acontece no próximo horário-alvo após a DAG
    # ser despausada, sem reprocessar datas históricas.
    start_date=pendulum.datetime(2026, 1, 1, tz="America/Sao_Paulo"),
    catchup=False,
    default_args=default_args,
    tags=["b3", "etl", "producao"],
    max_active_runs=1,
) as dag:

    extract_cotacoes = BashOperator(
        task_id="extract_cotacoes",
        bash_command=(
            f"cd {PROJECT_DIR} && python -m ingestion.main --modo diario"
        ),
    )

    # Ingestão de dividendos (Etapa 6), em paralelo com as cotações.
    # MODO INCREMENTAL: reescreve só a partição do ano corrente — espelha
    # o `--modo diario` das cotações. `inicial` reescreveria todas as
    # partições de ano a cada execução, custo inútil já que proventos
    # passados não mudam (ver ingestion/dividendos/main.py).
    extract_dividendos = BashOperator(
        task_id="extract_dividendos",
        bash_command=(
            f"cd {PROJECT_DIR} && python -m ingestion.dividendos.main "
            "--modo incremental"
        ),
    )

    refresh_warehouse = BashOperator(
        task_id="refresh_warehouse",
        bash_command=(
            f"cd {PROJECT_DIR} && python -m warehouse.setup"
        ),
    )

    dbt_run = BashOperator(
        task_id="dbt_run",
        bash_command=(
            f"cd {PROJECT_DIR}/dbt && dbt run --profiles-dir ./"
        ),
    )

    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=(
            f"cd {PROJECT_DIR}/dbt && dbt test --profiles-dir ./"
        ),
    )

    # Fan-in: refresh_warehouse só roda após AMBAS as ingestões. A lista à
    # esquerda do `>>` declara que extract_cotacoes e extract_dividendos
    # são upstream de refresh_warehouse (sem criar dependência entre elas —
    # seguem paralelas). Daí o pipeline volta a ser linear.
    [extract_cotacoes, extract_dividendos] >> refresh_warehouse >> dbt_run >> dbt_test
