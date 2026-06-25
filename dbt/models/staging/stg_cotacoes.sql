{{ config(materialized='view') }}

-- Staging de cotações: 1:1 com a source, sem agregação nem JOIN.
--
-- Duas "limpezas" aqui, ambas descartando a linha inteira:
--
-- 1. fechamento_ajustado NULL. Razão: na fato e nos indicadores da
--    Etapa 6, todo cálculo (retorno, média móvel, drawdown) depende de
--    fechamento ajustado. Uma linha sem essa coluna não tem valor
--    analítico e contamina os testes de relacionamento da fato.
--
-- 2. Barra parcial do yfinance (OHL zerado ou nulo). A sessão mais
--    recente do Yahoo costuma vir provisória: abertura/máxima/mínima e
--    volume zerados (ou nulos) com apenas o fechamento preenchido. Essa
--    linha viola a coerência OHLC (fechamento > máxima quando máxima=0)
--    e quebra o teste fato_fechamento_dentro_do_range. Descartamos até
--    a fonte consolidar — a barra volta completa no pregão seguinte.
--    Critério é o OHL (preços), NÃO o volume: volume=0 pode ser legítimo
--    em pregão de baixíssima liquidez. ATENÇÃO ao NULL: `maxima = 0` não
--    pega maxima NULL (retorna unknown em SQL), por isso checamos
--    explicitamente IS NOT NULL além de > 0 — barras parciais futuras
--    podem trazer zero ou nulo.
--
-- Descartar aqui é a fronteira correta entre "raw como veio" e "modelo
-- analítico": o raw segue imutável e fiel à fonte; o teste de coerência
-- segue rígido; a limpeza mora na camada de staging.
--
-- View, não tabela: re-execução é barata e a freshness segue o raw
-- automaticamente (sem `dbt run` adicional só por causa de um
-- novo Parquet no MinIO).

SELECT
    data,
    ticker,
    abertura,
    maxima,
    minima,
    fechamento,
    fechamento_ajustado,
    volume
FROM {{ source('raw', 'cotacoes') }}
WHERE fechamento_ajustado IS NOT NULL
  AND abertura IS NOT NULL AND abertura > 0
  AND maxima   IS NOT NULL AND maxima   > 0
  AND minima   IS NOT NULL AND minima   > 0
