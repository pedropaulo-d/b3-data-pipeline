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
# M5 (fallback aplicado — DT-SEC.1): usamos requirements.txt (>=), NÃO o
# requirements.lock (==). Pinar o lock — gerado num venv standalone
# Python 3.13, sem as constraints da imagem oficial — conflita com as
# versões que o apache/airflow:2.10.5 fixa, e o `pip install` quebra. Com
# o requirements.txt, o pip resolve as deps contra as constraints da
# imagem base. O lock segue no repo como referência do ambiente HOST
# (ingestão/warehouse/dbt fora do Docker), só não entra neste build.
COPY requirements.txt /requirements.txt

# Instala as deps como usuário `airflow` (o root do container é
# bloqueado pela imagem oficial; instalar como `airflow` evita o erro
# "Do not install Python packages as root").
USER airflow
RUN pip install --no-cache-dir -r /requirements.txt
