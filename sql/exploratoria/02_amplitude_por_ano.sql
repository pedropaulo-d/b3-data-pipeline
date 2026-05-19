-- Descrição: maior amplitude intradiária por ticker e ano.
-- Amplitude = (máxima - mínima) / mínima do pregão. Indica dias de
-- movimento extremo — útil para identificar visualmente picos de
-- volatilidade (anúncio de balanço, intervenção política, etc.).

SELECT
    ticker,
    ano,
    MAX( (maxima - minima) / minima ) AS amplitude_maxima
FROM raw.cotacoes
WHERE minima > 0  -- evita divisão por zero em dados eventualmente sujos
GROUP BY ticker, ano
ORDER BY ticker, ano
