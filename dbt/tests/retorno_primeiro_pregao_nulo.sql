-- Custom test: o PRIMEIRO pregão de cada ticker tem retorno_simples NULL.
--
-- Convenção dbt para tests/: a query DEVE retornar 0 linhas para passar.
--
-- O retorno do primeiro pregão da série depende de um pregão anterior que
-- não existe (LAG retorna NULL → retorno NULL). Se o primeiro pregão de
-- algum ticker tiver retorno NÃO-nulo, a janela LAG está particionada ou
-- ordenada errado — exatamente o tipo de bug silencioso que corromperia
-- retorno acumulado e volatilidade.
--
-- QUALIFY filtra sobre o resultado da window function: isola a 1ª linha de
-- cada empresa (ROW_NUMBER = 1) e retorna só as que violam (retorno não
-- nulo). Se nenhuma violar, resultado vazio = teste passa.

SELECT
    empresa_id,
    tempo_id,
    retorno_simples
FROM {{ ref('mart_indicadores_diarios') }}
QUALIFY ROW_NUMBER() OVER (PARTITION BY empresa_id ORDER BY data) = 1
    AND retorno_simples IS NOT NULL
