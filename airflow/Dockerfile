# Imagem custom do Airflow para o pipeline B3.
#
# Partimos da imagem oficial do Airflow 2.10.5 (última estável da série
# 2 quando esta etapa foi escrita) e instalamos as dependências do
# projeto (yfinance, pandas, pyarrow, boto3, duckdb, dbt-core,
# dbt-duckdb, etc.) DENTRO da imagem. Isso permite que os BashOperators
# da DAG chamem `python -m ingestion.main`, `python -m warehouse.setup`
# e `dbt` direto, sem orquestrar um segundo container por task.
#
# Estratégia de execução: bind mount + BashOperator. Ver
# airflow/README.md e docs/decisoes.md (Etapa 5).
FROM apache/airflow:2.10.5

# Copia o requirements.txt do projeto para dentro da imagem. O contexto
# de build do compose é a raiz do repositório (definida em
# docker-compose.yml -> build.context), então requirements.txt está
# acessível pelo path relativo.
#
# M5 (DT-SEC.1): a imagem instala requirements.txt (>=), deixando o pip
# resolver as deps contra as constraints da imagem oficial
# apache/airflow:2.10.5. Pinar versões `==` de um venv standalone (sem
# essas constraints) conflitava com o que a imagem fixa e quebrava o
# `pip install` — por isso o projeto não mantém um lock determinístico
# (ver DT-SEC.1/DT-SEC.4). Reprodutibilidade aqui vem da imagem base +
# requirements.txt.
COPY requirements.txt /requirements.txt

# Instala as deps como usuário `airflow` (o root do container é
# bloqueado pela imagem oficial; instalar como `airflow` evita o erro
# "Do not install Python packages as root").
USER airflow
RUN pip install --no-cache-dir -r /requirements.txt
