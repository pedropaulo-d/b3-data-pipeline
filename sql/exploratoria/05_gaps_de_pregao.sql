-- Descrição: dias em que pelo menos um ticker presente no calendário
-- não tem registro. Constrói o produto cartesiano (datas distintas no
-- raw) × (tickers distintos no raw) e faz LEFT JOIN com a tabela
-- original; linhas onde o LEFT JOIN não casa indicam gap.
--
-- Anti-join: padrão LEFT JOIN + WHERE NULL_NO_LADO_DIREITO. Lê como
-- "linhas do conjunto da esquerda que NÃO existem no conjunto da
-- direita". Equivale ao NOT EXISTS, com plano de execução parecido
-- no DuckDB.
--
-- Causas esperadas de gap:
--   - Feriado nacional (não deveria aparecer, calendário do yfinance
--     já filtra), mas vale validar.
--   - Suspensão de negociação do ativo (evento corporativo).
--   - Falha de ingestão (a corrigir).

WITH calendario AS (
    SELECT DISTINCT data FROM raw.cotacoes
),
tickers AS (
    SELECT DISTINCT ticker FROM raw.cotacoes
),
esperado AS (
    -- Produto cartesiano explícito: toda combinação data × ticker que
    -- deveria existir se a cobertura fosse perfeita.
    SELECT c.data, t.ticker
    FROM calendario c
    CROSS JOIN tickers t
)
SELECT
    e.data,
    e.ticker
FROM esperado e
LEFT JOIN raw.cotacoes c
       ON c.data = e.data
      AND c.ticker = e.ticker
WHERE c.ticker IS NULL  -- anti-join: a linha esperada não existe no raw
ORDER BY e.data, e.ticker
