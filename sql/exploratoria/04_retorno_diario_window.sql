-- Descrição: 20 maiores altas e 20 maiores quedas diárias do histórico.
-- Calcula o retorno percentual de cada pregão em relação ao anterior
-- *do mesmo ticker* usando LAG. PARTITION BY ticker garante que o LAG
-- não atravesse fronteira de ativo; ORDER BY data ordena dentro do
-- ticker. UNION ALL junta os dois extremos sem deduplicação.

WITH retornos AS (
    SELECT
        ticker,
        data,
        fechamento,
        -- LAG(col) OVER (PARTITION BY ... ORDER BY ...) devolve o valor
        -- da linha anterior dentro da partição. Primeira linha de cada
        -- ticker tem LAG = NULL — a divisão devolve NULL e some no
        -- filtro do SELECT externo.
        ( fechamento
          - LAG(fechamento) OVER (PARTITION BY ticker ORDER BY data) )
        /   LAG(fechamento) OVER (PARTITION BY ticker ORDER BY data)
        * 100 AS retorno_pct
    FROM raw.cotacoes
)
(
    SELECT 'alta' AS extremo, ticker, data, fechamento, retorno_pct
    FROM retornos
    WHERE retorno_pct IS NOT NULL
    ORDER BY retorno_pct DESC
    LIMIT 20
)
UNION ALL
(
    SELECT 'queda' AS extremo, ticker, data, fechamento, retorno_pct
    FROM retornos
    WHERE retorno_pct IS NOT NULL
    ORDER BY retorno_pct ASC
    LIMIT 20
)
ORDER BY extremo, retorno_pct DESC
