"""Ingestão de dividendos da B3 via yfinance (Etapa 6).

Subpacote **simétrico** ao fluxo de cotações de ``ingestion/``, separado
por duas razões:

1. **Granularidade de partição diferente.** Cotações particionam por dia
   (``raw/cotacoes/ano=YYYY/mes=MM/dia=DD/``); dividendos são esparsos e
   particionam por ano (``raw/dividendos/ano=YYYY/``).
2. **Fonte diferente no yfinance.** Cotações vêm de ``yf.download``;
   dividendos de ``yf.Ticker(t).dividends`` (série temporal de proventos
   por data-ex).

O que é compartilhado **não** é duplicado: ``ingestion.config`` (tickers,
janela, credenciais do MinIO) e ``ingestion.s3_client`` (cliente boto3)
servem aos dois fluxos.

Por que subpacote (e não módulos achatados nem ``--fonte`` no main de
cotações): manter ``ingestion/download.py`` e ``ingestion/storage.py``
intactos (são consumidos pela DAG da Etapa 5) e, ao mesmo tempo, deixar a
simetria visível — ``ingestion/dividendos/download.py`` lê ao lado de
``ingestion/download.py``. A CLI ganha entry point próprio,
``python -m ingestion.dividendos.main``, em vez de uma flag no main de
cotações: os modos de um (inicial/diario/range por data) não fazem
sentido para o outro (inicial/incremental por ano).

Módulos:
- ``download`` — ``yf.Ticker(t).dividends`` → DataFrame long.
- ``storage``  — Parquet particionado por ano no MinIO.
- ``main``     — CLI (modos: inicial, incremental).
"""
