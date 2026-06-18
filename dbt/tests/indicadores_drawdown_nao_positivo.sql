-- Custom test: drawdown é sempre <= 0.
--
-- Convenção dbt para tests/: a query DEVE retornar 0 linhas para passar.
--
-- drawdown = fechamento_ajustado / pico_historico - 1, e o pico histórico
-- é o MÁXIMO acumulado até o pregão atual — logo fechamento <= pico sempre,
-- e o quociente <= 1, e o drawdown <= 0. Exatamente 0 quando o pregão é um
-- novo topo. Qualquer valor > 0 indica bug na janela do pico.

SELECT
    empresa_id,
    tempo_id,
    drawdown
FROM {{ ref('mart_indicadores_diarios') }}
WHERE drawdown > 0
