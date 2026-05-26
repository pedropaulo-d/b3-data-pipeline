{{ config(materialized='table') }}

-- Dimensão de tempo: calendário completo gerado, INDEPENDENTE da fato.
--
-- Kimball clássico — dim_tempo cobre todo o range temporal de interesse
-- (incluindo finais de semana, feriados e datas futuras) para que a fato
-- consiga sempre resolver a FK por data. Faz mais sentido gerar
-- calendário do que extrair as datas presentes em stg_cotacoes:
-- relatórios que perguntam "qual a média mensal" continuam funcionando
-- mesmo em meses com dias sem pregão.
--
-- Range: 2020-01-01 a 2030-12-31 (~11 anos × 365 dias = ~4017 linhas).
-- Cobre os 5 anos de histórico real + projeção razoável.
--
-- Surrogate key tempo_id no formato YYYYMMDD (INTEGER). Vantagem sobre
-- ROW_NUMBER: legibilidade (2024-03-15 → 20240315) e estabilidade
-- (independente da ordem de geração).
--
-- DOW no DuckDB: 0 = domingo, ..., 6 = sábado. Sábado/domingo → fim
-- de semana. Convenção brasileira (PT-BR) nos atributos de nome.

WITH datas AS (
    SELECT UNNEST(GENERATE_SERIES(
        DATE '2020-01-01',
        DATE '2030-12-31',
        INTERVAL 1 DAY
    )) AS data
)

SELECT
    CAST(STRFTIME(data, '%Y%m%d') AS INTEGER) AS tempo_id,
    data,
    EXTRACT(YEAR    FROM data) AS ano,
    EXTRACT(MONTH   FROM data) AS mes,
    EXTRACT(DAY     FROM data) AS dia,
    EXTRACT(DOW     FROM data) AS dia_semana,
    EXTRACT(QUARTER FROM data) AS trimestre,

    CASE EXTRACT(MONTH FROM data)
        WHEN 1  THEN 'Janeiro'
        WHEN 2  THEN 'Fevereiro'
        WHEN 3  THEN 'Março'
        WHEN 4  THEN 'Abril'
        WHEN 5  THEN 'Maio'
        WHEN 6  THEN 'Junho'
        WHEN 7  THEN 'Julho'
        WHEN 8  THEN 'Agosto'
        WHEN 9  THEN 'Setembro'
        WHEN 10 THEN 'Outubro'
        WHEN 11 THEN 'Novembro'
        WHEN 12 THEN 'Dezembro'
    END AS nome_mes,

    CASE EXTRACT(DOW FROM data)
        WHEN 0 THEN 'Domingo'
        WHEN 1 THEN 'Segunda-feira'
        WHEN 2 THEN 'Terça-feira'
        WHEN 3 THEN 'Quarta-feira'
        WHEN 4 THEN 'Quinta-feira'
        WHEN 5 THEN 'Sexta-feira'
        WHEN 6 THEN 'Sábado'
    END AS nome_dia_semana,

    EXTRACT(DOW FROM data) IN (0, 6) AS eh_fim_semana,
    EXTRACT(DAY FROM data) = 1        AS eh_inicio_mes,
    data = LAST_DAY(data)             AS eh_fim_mes
FROM datas
