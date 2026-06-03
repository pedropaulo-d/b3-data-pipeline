"""DAG principal do pipeline B3 — execução diária.

Automatiza a sequência manual da Etapa 4:

    1. python -m ingestion.main --modo diario
    2. python -m warehouse.setup
    3. dbt run  (no diretório dbt/)
    4. dbt test (no diretório dbt/)

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
        "Pipeline diário B3: ingestão (yfinance) -> warehouse (DuckDB) "
        "-> dbt run -> dbt test."
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

    extract_cotacoes >> refresh_warehouse >> dbt_run >> dbt_test
