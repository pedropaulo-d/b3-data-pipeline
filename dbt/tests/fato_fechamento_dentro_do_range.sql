-- Custom test: fechamento deve estar entre mínima e máxima do pregão.
--
-- Outra sanidade de OHLC. O fechamento é o último preço negociado;
-- por construção, ele cai no range [minima, maxima] do pregão. Violar
-- é sinal de dado inconsistente.
--
-- Não validamos abertura aqui porque o `auto_adjust=False` do yfinance
-- pode (em teoria) trazer abertura ligeiramente fora do range em dias
-- de auction — fica para discussão se aparecer.

SELECT
    empresa_id,
    tempo_id,
    fechamento,
    maxima,
    minima
FROM {{ ref('fato_cotacoes_diarias') }}
WHERE fechamento < minima
   OR fechamento > maxima
