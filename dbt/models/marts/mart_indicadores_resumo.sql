{{ config(materialized='table') }}

-- Resumo de indicadores, grão por TICKER: 1 linha por empresa (6 linhas).
-- Agrega a série diária de mart_indicadores_diarios num cartão-resumo do
-- período — o tipo de tabela que alimenta um "header" de dashboard.
--
-- retorno_acumulado_total = o retorno_acumulado do ÚLTIMO pregão da série.
-- Resolvido com `arg_max(retorno_acumulado, data)`: agregado nativo do
-- DuckDB que devolve o valor de uma coluna na linha onde outra é máxima.
-- Mais limpo, num contexto de agregação, que LAST_VALUE com frame completo
-- ou um QUALIFY ROW_NUMBER seguido de join.
--
-- volatilidade_media_30d usa a versão ANUAL (volatilidade_30d_anual): a
-- média das volatilidades anualizadas de 30d ao longo do período é o
-- número que se compara entre ativos. AVG ignora os NULLs dos primeiros
-- pregões (janela parcial), então é a média dos dias com volatilidade
-- definida.
--
-- volume_medio vem do volume carregado no diário (que, por sua vez, veio
-- da fato de cotações): AVG ignora NULLs (decisão da Etapa 1: volume NULL
-- = "desconhecido", não zero).

WITH agregado AS (
    SELECT
        empresa_id,
        MIN(drawdown)                          AS max_drawdown,
        arg_max(retorno_acumulado, data)       AS retorno_acumulado_total,
        AVG(volatilidade_30d_anual)            AS volatilidade_media_30d,
        AVG(retorno_simples)                   AS retorno_medio_diario,
        AVG(volume)                            AS volume_medio,
        MIN(data)                              AS primeiro_pregao,
        MAX(data)                              AS ultimo_pregao,
        COUNT(*)                               AS total_pregoes
    FROM {{ ref('mart_indicadores_diarios') }}
    GROUP BY empresa_id
)

SELECT
    a.empresa_id,
    e.ticker,
    a.max_drawdown,
    a.retorno_acumulado_total,
    a.volatilidade_media_30d,
    a.retorno_medio_diario,
    a.volume_medio,
    a.primeiro_pregao,
    a.ultimo_pregao,
    a.total_pregoes
FROM agregado AS a
INNER JOIN {{ ref('dim_empresa') }} AS e ON a.empresa_id = e.empresa_id
