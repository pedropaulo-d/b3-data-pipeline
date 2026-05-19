-- Descrição: volume médio diário negociado por setor, mês a mês.
-- Como ainda não existe dim_empresa (Etapa 4), o mapeamento ticker→setor
-- vive em uma CTE inline. Quando o dbt assumir, esta CTE vira a tabela
-- dim_empresa e o JOIN aqui some.

WITH setores AS (
    -- Mapeamento ticker -> setor. Hardcoded de propósito enquanto não
    -- há dim_empresa. ITUB4 e BBDC4 compartilham setor.
    SELECT 'PETR4' AS ticker, 'Petróleo'   AS setor UNION ALL
    SELECT 'VALE3',           'Mineração'         UNION ALL
    SELECT 'ITUB4',           'Financeiro'        UNION ALL
    SELECT 'BBDC4',           'Financeiro'        UNION ALL
    SELECT 'WEGE3',           'Industrial'        UNION ALL
    SELECT 'ABEV3',           'Consumo'
)
SELECT
    s.setor,
    c.ano,
    c.mes,
    AVG(c.volume) AS volume_medio
FROM raw.cotacoes  AS c
JOIN setores       AS s USING (ticker)
WHERE c.volume IS NOT NULL  -- volume Int64 nullable: NaN da fonte vira NULL
GROUP BY s.setor, c.ano, c.mes
ORDER BY s.setor, c.ano, c.mes
