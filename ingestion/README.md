# ingestion/

Código da **Etapa 1 — Ingestão manual com Python puro**.

Baixa cotações diárias da B3 via `yfinance` e grava em **Parquet
particionado por data** no raw layer local (`data/raw/cotacoes/`). Não há
ainda orquestração, object storage remoto, nem warehouse — essas peças
entram nas etapas seguintes.

## Estrutura

```
ingestion/
├── __init__.py
├── config.py          # Tickers, paths, janela histórica, schema de saída
├── download.py        # yfinance.download + normalização para formato long
├── storage.py         # Parquet particionado por data (ano=/mes=/dia=)
├── main.py            # CLI: python -m ingestion.main --modo {inicial,diario,range}
└── README.md          # Este arquivo
```

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

## Onde os dados são gravados

```
data/raw/cotacoes/
└── ano=YYYY/
    └── mes=MM/
        └── dia=DD/
            └── cotacoes.parquet
```

Cada arquivo contém **uma linha por ticker** para a data correspondente.
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

## Propriedades do raw layer

- **Imutabilidade conceitual.** Não calculamos nada aqui — só guardamos o
  que veio. Cálculo de retorno, ajuste de janelas, indicadores: tudo fica
  para o dbt na Etapa 4.
- **Idempotência.** Rodar duas vezes para o mesmo período sobrescreve as
  partições com o mesmo conteúdo. Não há duplicação nem versionamento por
  timestamp.
- **Granularidade do arquivo = data.** Um arquivo Parquet por dia, com
  todos os tickers daquele dia. Granularidade da linha = `ticker × data`.

## O que NÃO está aqui ainda

- **Object storage remoto (MinIO/S3).** Vem na Etapa 2 — vai trocar o
  caminho de saída do `storage.py` por um endpoint S3 via `s3fs`/`boto3`,
  preservando o layout de partições.
- **Orquestração.** Vem na Etapa 5 — uma DAG do Airflow vai disparar
  `python -m ingestion.main --modo diario` em horário fixo.
- **Testes.** Vêm parte na Etapa 4 (`dbt tests` no staging) e parte na
  Etapa 8 (suíte `pytest` para a ingestão).
- **Backfill em paralelo.** A CLI roda single-threaded por intervalo. Se
  precisar reprocessar 5 anos rapidamente, `threads=True` no yfinance já
  paraleliza por ticker dentro de um intervalo.
