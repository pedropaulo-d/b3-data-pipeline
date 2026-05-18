# ingestion/

Pasta destinada ao código da **Etapa 1 — Ingestão manual com Python puro**.

Atualmente está vazia (Etapa 0 só prepara o terreno). A partir da Etapa 1, será preenchida com os módulos responsáveis por baixar os dados da B3 via `yfinance` e persistir em Parquet particionado por data.

## Estrutura prevista

```
ingestion/
├── __init__.py
├── config.py          # Lista de tickers, paths, parâmetros
├── download.py        # Lógica de download via yfinance
├── storage.py         # Salvamento em Parquet particionado
└── main.py            # Entry point: python -m ingestion.main
```

## Princípios que valerão para o código desta pasta

- **Idempotência:** rodar duas vezes não duplica dado nem corrompe estado.
- **Imutabilidade do raw:** uma vez gravada uma partição, ela não é reescrita silenciosamente; correção vira nova partição.
- **Configuração separada do código:** `config.py` concentra parâmetros (lista de tickers, janela histórica, paths) — não há valores mágicos espalhados pelos módulos.
- **Logging em vez de `print`:** uso da `logging` stdlib, com níveis apropriados (`INFO` para progresso, `WARNING` para retries, `ERROR` para falhas).
