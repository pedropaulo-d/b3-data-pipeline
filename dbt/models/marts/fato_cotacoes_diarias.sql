{{ config(materialized='table') }}

-- Fato Kimball: 1 linha por (empresa, pregão).
--
-- Chave composta (empresa_id, tempo_id), garantida pelo teste
-- unique_combination_of_columns em schema.yml.
--
-- INNER JOIN é intencional. Uma cotação que NÃO casa com:
--   - dim_empresa (ticker inválido / fora do seed): é problema na
--     ingestão ou no seed; cair silenciosamente seria pior. Cai em
--     erro de qualidade — registrar em NOTAS.md se ocorrer.
--   - dim_tempo (data fora do range 2020-01-01 a 2030-12-31): só
--     aconteceria se ingerirmos histórico fora dessa janela. Sinal
--     de que dim_tempo precisa ser estendida.
--
-- O teste `relationships` em schema.yml protege esse contrato:
-- se algum dia uma FK aparecer sem dim correspondente, o teste falha.

SELECT
    e.empresa_id,
    t.tempo_id,
    s.abertura,
    s.maxima,
    s.minima,
    s.fechamento,
    s.fechamento_ajustado,
    s.volume
FROM {{ ref('stg_cotacoes') }}  AS s
INNER JOIN {{ ref('dim_empresa') }} AS e ON s.ticker = e.ticker
INNER JOIN {{ ref('dim_tempo') }}   AS t ON s.data   = t.data
