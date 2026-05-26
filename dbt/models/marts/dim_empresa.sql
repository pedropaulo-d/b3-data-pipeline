{{ config(materialized='table') }}

-- Dimensão de empresa (SCD tipo 1: sobrescreve em mudança, sem histórico).
--
-- Surrogate key (empresa_id) gerada com ROW_NUMBER ordenando por ticker.
-- Como o seed empresas.csv tem ordem estável (alfabética por ticker é
-- determinística), `dbt seed` + `dbt run` repetidos produzem o mesmo
-- mapeamento empresa_id ↔ ticker. Se um ticker fosse adicionado no meio
-- do CSV, os empresa_id seguintes mudariam — aceitável porque dim_empresa
-- é table (full refresh) e fato_cotacoes_diarias é reconstruída na
-- mesma run.
--
-- A natural key (ticker) é preservada na tabela para joins ad-hoc e
-- para que a fato consiga resolver a FK via ticker (ver
-- fato_cotacoes_diarias.sql).

SELECT
    ROW_NUMBER() OVER (ORDER BY ticker) AS empresa_id,
    ticker,
    nome,
    setor,
    subsetor,
    segmento
FROM {{ ref('empresas') }}
