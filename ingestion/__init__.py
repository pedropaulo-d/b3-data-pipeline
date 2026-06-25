"""Pacote de ingestão da Etapa 1.

Baixa cotações da B3 via yfinance e persiste em Parquet particionado por
data no raw layer do MinIO (`s3://b3-data/raw/cotacoes/`).

Subdivisão dos módulos:
- `config`   — constantes (tickers, paths, datas, sufixo da B3).
- `download` — chamada ao yfinance e normalização do DataFrame.
- `storage`  — escrita do Parquet particionado por data.
- `main`     — entry point com CLI (modos: inicial, diario, range).
"""
