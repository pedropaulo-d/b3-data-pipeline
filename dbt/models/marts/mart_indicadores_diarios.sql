{{ config(materialized='table') }}

-- Indicadores de mercado, grão diário: 1 linha por (empresa, pregão) —
-- mesma granularidade da fato de cotações (~7.482 linhas).
--
-- BASE DE PREÇO (regra de domínio, ver docs/decisoes.md):
--   Retorno, médias móveis, volatilidade e drawdown usam SEMPRE o
--   fechamento AJUSTADO. O ajustado já incorpora proventos e splits, então
--   não há queda artificial em data-ex/grupamento — o que mediria "risco"
--   inexistente. O fechamento BRUTO não entra aqui (ele é a base do
--   dividend yield, em mart_dividend_yield).
--
-- Materializada como TABLE: alimenta o resumo e o dashboard; as window
-- functions sobre ~7.500 linhas são baratas, mas a leitura repetida
-- compensa materializar.
--
-- Estrutura em CTEs encadeadas (cada uma adiciona um bloco de colunas):
--   base → retornos → janelas (médias/vol) → drawdown → final.
-- A separação não é só estética: volatilidade depende de retorno_log, e
-- uma window function NÃO pode referenciar outra no mesmo SELECT — então
-- retorno_log nasce numa CTE e é consumido na seguinte.
--
-- A data vive em dim_tempo (a fato só tem tempo_id): por isso o JOIN logo
-- na base, e todas as janelas ordenam por `data`.

WITH base AS (
    SELECT
        f.empresa_id,
        f.tempo_id,
        t.data,
        f.fechamento_ajustado,
        f.volume
    FROM {{ ref('fato_cotacoes_diarias') }} AS f
    INNER JOIN {{ ref('dim_tempo') }} AS t ON f.tempo_id = t.tempo_id
),

-- 1) RETORNOS (base: fechamento ajustado)
retornos AS (
    SELECT
        empresa_id,
        tempo_id,
        data,
        fechamento_ajustado,
        volume,
        -- variação vs pregão anterior; NULL no primeiro pregão (sem LAG)
        fechamento_ajustado / LAG(fechamento_ajustado) OVER w - 1            AS retorno_simples,
        -- retorno log: aditivo no tempo, base correta para volatilidade
        LN(fechamento_ajustado / LAG(fechamento_ajustado) OVER w)           AS retorno_log,
        -- acumulado vs primeiro pregão da série do ticker (0 no 1º dia)
        fechamento_ajustado / FIRST_VALUE(fechamento_ajustado) OVER w - 1    AS retorno_acumulado
    FROM base
    WINDOW w AS (PARTITION BY empresa_id ORDER BY data)
),

-- 2) MÉDIAS MÓVEIS + VOLATILIDADE (janelas móveis em nº de pregões)
janelas AS (
    SELECT
        *,
        -- Médias móveis do fechamento ajustado (7/30/90/200 pregões).
        AVG(fechamento_ajustado) OVER (w ROWS BETWEEN 6   PRECEDING AND CURRENT ROW) AS media_movel_7d,
        AVG(fechamento_ajustado) OVER (w ROWS BETWEEN 29  PRECEDING AND CURRENT ROW) AS media_movel_30d,
        AVG(fechamento_ajustado) OVER (w ROWS BETWEEN 89  PRECEDING AND CURRENT ROW) AS media_movel_90d,
        AVG(fechamento_ajustado) OVER (w ROWS BETWEEN 199 PRECEDING AND CURRENT ROW) AS media_movel_200d,
        -- Contagem de pregões na janela (Forma A): sinaliza janela PARCIAL
        -- nos primeiros pregões (ex.: média "200d" com só 12 pregões).
        COUNT(*) OVER (w ROWS BETWEEN 6   PRECEDING AND CURRENT ROW) AS pregoes_janela_7d,
        COUNT(*) OVER (w ROWS BETWEEN 29  PRECEDING AND CURRENT ROW) AS pregoes_janela_30d,
        COUNT(*) OVER (w ROWS BETWEEN 89  PRECEDING AND CURRENT ROW) AS pregoes_janela_90d,
        COUNT(*) OVER (w ROWS BETWEEN 199 PRECEDING AND CURRENT ROW) AS pregoes_janela_200d,
        -- Volatilidade = desvio-padrão AMOSTRAL (STDDEV_SAMP) do retorno
        -- log na janela. Diária aqui; a anualização (×√252) é na CTE final.
        STDDEV_SAMP(retorno_log) OVER (w ROWS BETWEEN 29  PRECEDING AND CURRENT ROW) AS volatilidade_30d,
        STDDEV_SAMP(retorno_log) OVER (w ROWS BETWEEN 89  PRECEDING AND CURRENT ROW) AS volatilidade_90d,
        STDDEV_SAMP(retorno_log) OVER (w ROWS BETWEEN 251 PRECEDING AND CURRENT ROW) AS volatilidade_252d
    FROM retornos
    WINDOW w AS (PARTITION BY empresa_id ORDER BY data)
),

-- 3) DRAWDOWN (base: fechamento ajustado)
drawdown AS (
    SELECT
        *,
        -- Pico histórico: máximo do fechamento ajustado até o pregão atual
        -- (frame expansivo desde o início da série do ticker).
        MAX(fechamento_ajustado) OVER (
            w ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS pico_historico
    FROM janelas
    WINDOW w AS (PARTITION BY empresa_id ORDER BY data)
)

-- 4) FINAL: anualiza a volatilidade e deriva o drawdown do pico.
SELECT
    empresa_id,
    tempo_id,
    data,
    fechamento_ajustado,
    volume,

    retorno_simples,
    retorno_log,
    retorno_acumulado,

    media_movel_7d,
    media_movel_30d,
    media_movel_90d,
    media_movel_200d,

    pregoes_janela_7d,
    pregoes_janela_30d,
    pregoes_janela_90d,
    pregoes_janela_200d,

    -- Anualização: σ_anual = σ_diário × √252 (≈ nº de pregões/ano).
    volatilidade_30d,
    volatilidade_30d  * SQRT(252) AS volatilidade_30d_anual,
    volatilidade_90d,
    volatilidade_90d  * SQRT(252) AS volatilidade_90d_anual,
    volatilidade_252d,
    volatilidade_252d * SQRT(252) AS volatilidade_252d_anual,

    pico_historico,
    -- Drawdown sempre <= 0: preço atual nunca supera o pico acumulado.
    -- Exatamente 0 quando o pregão é um novo topo histórico.
    fechamento_ajustado / pico_historico - 1 AS drawdown
FROM drawdown
