{{ config(materialized='table') }}

-- Dividend yield trailing 12 meses, grão diário: 1 linha por (empresa,
-- pregão). Para cada dia, soma os proventos dos últimos 365 dias e divide
-- pelo preço daquele dia. O grão diário (e não por ticker) é proposital:
-- o DY 12m muda todo dia — a janela de 365 dias desliza e o preço muda —,
-- então a série diária permite o gráfico de evolução do yield.
--
-- BASE DE PREÇO = fechamento BRUTO (regra de domínio, ver decisoes.md).
-- O fechamento AJUSTADO já desconta proventos do preço; usá-lo no
-- denominador contaria o dividendo DUAS vezes (uma no numerador, outra
-- embutida no preço menor). O yield é "dividendo / preço de mercado", e o
-- preço de mercado é o bruto.
--
-- COMO a janela de 365 dias é calculada: RANGE JOIN (self-join por faixa
-- de data) entre cotações e dividendos. Para cada pregão `c`, casa os
-- proventos cuja data-ex caiu em (c.data - 365, c.data]. Avaliado vs a
-- alternativa `SUM(...) OVER (RANGE BETWEEN INTERVAL 365 DAYS PRECEDING
-- AND CURRENT ROW)`: o range join é escolhido por (1) ser robusto a
-- data-ex que não coincida com um pregão e (2) deixar a semântica do
-- intervalo explícita na cláusula ON. Custo é irrelevante — dividendos
-- são pouquíssimos por ticker, então a faixa casada é minúscula.
--
-- Materializada como TABLE: grão diário sobre 6 tickers × ~5 anos, lida
-- repetidamente pelo dashboard.
--
-- Fact-to-fact JOIN via dim_tempo conformada: tanto fato_cotacoes_diarias
-- quanto fato_dividendos guardam tempo_id, não a data — então cada uma faz
-- JOIN em dim_tempo para materializar a data e alinhar pelo calendário.

WITH cotacoes AS (
    SELECT
        f.empresa_id,
        f.tempo_id,
        t.data,
        f.fechamento AS fechamento_bruto
    FROM {{ ref('fato_cotacoes_diarias') }} AS f
    INNER JOIN {{ ref('dim_tempo') }} AS t ON f.tempo_id = t.tempo_id
),

dividendos AS (
    SELECT
        fd.empresa_id,
        t.data AS data_ex,
        fd.valor_dividendo
    FROM {{ ref('fato_dividendos') }} AS fd
    INNER JOIN {{ ref('dim_tempo') }} AS t ON fd.tempo_id = t.tempo_id
),

dividendos_12m AS (
    SELECT
        c.empresa_id,
        c.tempo_id,
        c.data,
        c.fechamento_bruto,
        -- Sem provento na janela → SUM NULL → 0. Ausência de dividendo é
        -- yield ZERO (fato conhecido), não desconhecido (NULL).
        COALESCE(SUM(d.valor_dividendo), 0) AS dividendos_12m
    FROM cotacoes AS c
    LEFT JOIN dividendos AS d
        ON  d.empresa_id = c.empresa_id
        AND d.data_ex >  c.data - INTERVAL '365 days'
        AND d.data_ex <= c.data
    GROUP BY c.empresa_id, c.tempo_id, c.data, c.fechamento_bruto
)

SELECT
    empresa_id,
    tempo_id,
    data,
    fechamento_bruto,
    dividendos_12m,
    -- dy_12m é uma FRAÇÃO (0.08 = 8%), não percentual. Denominador bruto.
    dividendos_12m / fechamento_bruto AS dy_12m
FROM dividendos_12m
