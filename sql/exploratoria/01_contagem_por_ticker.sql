-- Descrição: contagem de pregões e range temporal por ticker.
-- Sanity check inicial: todos os 6 tickers presentes e com cobertura
-- semelhante (mesmo calendário B3). Qualquer ticker com contagem muito
-- abaixo dos outros sinaliza gap de ingestão.

SELECT
    ticker,
    COUNT(*)        AS pregoes,
    MIN(data)       AS primeiro_pregao,
    MAX(data)       AS ultimo_pregao
FROM raw.cotacoes
GROUP BY ticker
ORDER BY ticker
