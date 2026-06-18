{{ config(materialized='view') }}

-- Fato de dividendos: 1 linha por (empresa, data-ex).
--
-- Materializada como VIEW (e não table): o volume é ínfimo (poucas
-- dezenas de proventos por ticker em 5 anos), então o custo de
-- re-execução é desprezível e a freshness segue stg_dividendos sem
-- `dbt run` adicional. Contrasta com fato_cotacoes_diarias (~7.500
-- linhas, materializada como table porque alimenta indicadores pesados).
--
-- Dimensões CONFORMADAS: reusa dim_empresa e dim_tempo — as mesmas que a
-- fato de cotações referencia. É o que permite, no mart_dividend_yield,
-- alinhar proventos e preços pela dimensão de tempo compartilhada.
--
-- INNER JOIN, mesma lógica de fato_cotacoes_diarias: um provento que não
-- casa com dim_empresa (ticker fora do seed) ou dim_tempo (data-ex fora
-- de 2020–2030) indica erro de ingestão/seed e deve aparecer, não sumir.

SELECT
    e.empresa_id,
    t.tempo_id,
    d.valor_dividendo
FROM {{ ref('stg_dividendos') }} AS d
INNER JOIN {{ ref('dim_empresa') }} AS e ON d.ticker  = e.ticker
INNER JOIN {{ ref('dim_tempo') }}   AS t ON d.data_ex = t.data
