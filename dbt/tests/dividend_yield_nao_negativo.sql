-- Custom test: dividend yield nunca é negativo.
--
-- Convenção dbt para tests/: a query DEVE retornar 0 linhas para passar.
--
-- dy_12m = soma de proventos (>= 0, garantido por stg_dividendos que
-- descarta valor <= 0) / preço bruto (> 0). Yield negativo é
-- economicamente impossível; se aparecer, é bug de sinal ou de join.
-- Onde não houve provento, dy_12m = 0 (não NULL) — também passa.

SELECT
    empresa_id,
    tempo_id,
    dy_12m
FROM {{ ref('mart_dividend_yield') }}
WHERE dy_12m < 0
