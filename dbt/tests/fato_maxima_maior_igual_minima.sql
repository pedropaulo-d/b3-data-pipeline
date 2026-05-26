-- Custom test: máxima do pregão >= mínima do pregão.
--
-- Sanidade básica de OHLC. Violação significa que a fonte (yfinance)
-- trouxe valores invertidos ou corrompidos — não é regra de negócio
-- complexa, é integridade do dado.

SELECT
    empresa_id,
    tempo_id,
    maxima,
    minima
FROM {{ ref('fato_cotacoes_diarias') }}
WHERE maxima < minima
