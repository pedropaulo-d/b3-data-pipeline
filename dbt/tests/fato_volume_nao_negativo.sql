-- Custom test: nenhuma linha da fato pode ter volume negativo.
--
-- Convenção dbt para tests/: a query DEVE retornar 0 linhas para
-- passar; qualquer linha retornada é uma violação.
--
-- Volume NULL é permitido pela decisão da Etapa 1 (Int64 nullable
-- preserva "yfinance não trouxe o valor"). Aqui só pegamos valores
-- explicitamente negativos, que seriam erro de fonte ou de parse.

SELECT
    empresa_id,
    tempo_id,
    volume
FROM {{ ref('fato_cotacoes_diarias') }}
WHERE volume < 0
