-- Custom test: volatilidade nunca é negativa, em nenhuma janela.
--
-- Convenção dbt para tests/: a query DEVE retornar 0 linhas para passar.
--
-- Desvio-padrão (STDDEV_SAMP) é uma raiz quadrada — matematicamente >= 0.
-- Um valor negativo só apareceria por bug de cálculo. NULL (janela parcial
-- nos primeiros pregões, antes de haver 2 retornos) NÃO é violação:
-- `NULL < 0` é NULL, então essas linhas não entram no resultado.

SELECT
    empresa_id,
    tempo_id,
    volatilidade_30d,
    volatilidade_90d,
    volatilidade_252d
FROM {{ ref('mart_indicadores_diarios') }}
WHERE volatilidade_30d  < 0
   OR volatilidade_90d  < 0
   OR volatilidade_252d < 0
