# ingestion/

Código das **Etapas 1 e 2** do pipeline.

Baixa cotações diárias da B3 via `yfinance` e grava em **Parquet
particionado por data**. A partir da Etapa 2, o destino é o **MinIO**
local (bucket `b3-data`, prefixo `raw/cotacoes/`), acessado por boto3
sobre a S3 API. Não há mais escrita no filesystem local.

Não há ainda orquestração (Etapa 5) nem warehouse (Etapa 3) — essas
peças entram nas etapas seguintes.

## Estrutura

```
ingestion/
├── __init__.py
├── config.py          # Tickers, janela histórica, schema, vars do MinIO (.env)
├── download.py        # yfinance.download + normalização para formato long
├── storage.py         # Parquet em buffer (BytesIO) + upload boto3 para MinIO
├── main.py            # CLI: python -m ingestion.main --modo {inicial,diario,range}
└── README.md          # Este arquivo
```

## Pré-requisitos

1. Dependências instaladas (`pip install -r requirements.txt`).
2. `.env` na raiz do repositório (copiar de `.env.example`).
3. **MinIO rodando** via Docker Compose:
   ```bash
   docker compose -f docker-compose.minio.yml up -d
   ```
   O serviço auxiliar `mc-init` cria o bucket `b3-data` automaticamente
   na primeira subida.

## Como rodar

Sempre dispare a partir da raiz do repositório, com o `venv` ativo.

```bash
# Carga inicial: histórico de 5 anos a partir de hoje.
python -m ingestion.main --modo inicial

# Ingestão diária: apenas o dia de hoje. Se não houver pregão (sábado,
# domingo, feriado), o script sai com sucesso sem gravar nada.
python -m ingestion.main --modo diario

# Range arbitrário (útil para backfill ou debug). Datas inclusivas.
python -m ingestion.main --modo range --inicio 2025-01-01 --fim 2025-01-31
```

Se o MinIO não estiver rodando, o script falha cedo com mensagem clara
apontando o comando do Compose para subir o serviço.

## Onde os dados são gravados

No bucket `b3-data` do MinIO, em chaves que reproduzem o particionamento
estilo Hive:

```
s3://b3-data/raw/cotacoes/ano=YYYY/mes=MM/dia=DD/cotacoes.parquet
```

Cada objeto contém **uma linha por ticker** para a data correspondente.
Colunas do arquivo:

| Coluna                 | Tipo    | Conteúdo                                  |
|------------------------|---------|-------------------------------------------|
| `data`                 | date    | Data do pregão                            |
| `ticker`               | string  | Código B3 sem sufixo `.SA` (ex.: `PETR4`) |
| `abertura`             | float64 | `Open` do yfinance                        |
| `maxima`               | float64 | `High` do yfinance                        |
| `minima`               | float64 | `Low` do yfinance                         |
| `fechamento`           | float64 | `Close` bruto (não ajustado)              |
| `fechamento_ajustado`  | float64 | `Adj Close` (ajustado por proventos)      |
| `volume`               | Int64   | Volume em quantidade negociada (nullable; NaN = desconhecido) |

## Como inspecionar o que foi gravado

```bash
# Via console web do MinIO (recomendado durante aprendizado).
# Abrir http://localhost:9001 e navegar até b3-data → raw → cotacoes.

# Via CLI mc (dentro do container mc-init, ou local se instalado).
docker run --rm --network host minio/mc:latest \
  ls --recursive local/b3-data/raw/cotacoes/ano=2026/

# Via Python (durante debug, no REPL).
python -c "import boto3; from botocore.client import Config; \
import os; \
from dotenv import load_dotenv; load_dotenv(); \
s3=boto3.client('s3', endpoint_url=os.environ['MINIO_ENDPOINT'], \
  aws_access_key_id=os.environ['MINIO_ACCESS_KEY'], \
  aws_secret_access_key=os.environ['MINIO_SECRET_KEY'], \
  config=Config(signature_version='s3v4')); \
print([o['Key'] for o in s3.list_objects_v2(Bucket='b3-data', Prefix='raw/cotacoes/')['Contents']])"
```

## Propriedades do raw layer

- **Imutabilidade conceitual.** Não calculamos nada aqui — só guardamos
  o que veio. Cálculo de retorno, ajuste de janelas, indicadores: tudo
  fica para o dbt na Etapa 4.
- **Idempotência semântica.** Rodar duas vezes para o mesmo período
  sobrescreve os objetos com o mesmo conteúdo lógico. Os bytes podem
  variar (metadata do PyArrow, ordem das linhas) — o que importa é que
  o DataFrame reconstruído é idêntico. Ver `docs/decisoes.md`.
- **Granularidade do arquivo = data.** Um objeto Parquet por dia, com
  todos os tickers daquele dia. Granularidade da linha = `ticker × data`.

## Convenção de prefixos no bucket

```
b3-data/
├── raw/         # Dado bruto (ingestão Etapa 2 — ativo)
│   └── cotacoes/...
├── staging/     # Dado limpo e tipado (dbt staging — Etapa 4)
└── marts/       # Dado modelado (dbt marts — Etapa 4)
```

Os prefixos `staging/` e `marts/` ainda não existem fisicamente; são
documentados aqui como contrato para as etapas seguintes.

## O que NÃO está aqui ainda

- **Orquestração.** Vem na Etapa 5 — uma DAG do Airflow vai disparar
  `python -m ingestion.main --modo diario` em horário fixo.
- **Warehouse.** Vem na Etapa 3 — DuckDB lerá direto do MinIO via
  S3 API (`SELECT * FROM 's3://b3-data/raw/cotacoes/**/*.parquet'`).
- **Testes.** Vêm parte na Etapa 4 (`dbt tests` no staging) e parte na
  Etapa 8 (suíte `pytest` para a ingestão).
- **Backfill em paralelo.** A CLI roda single-threaded por intervalo. Se
  precisar reprocessar 5 anos rapidamente, `threads=True` no yfinance já
  paraleliza por ticker dentro de um intervalo.
