{{ config(materialized='view') }}

-- Staging de dividendos: 1:1 com a source raw.dividendos.
--
-- Limpeza mínima (mesma filosofia de stg_cotacoes): tipos explícitos e
-- descarte de proventos sem valor analítico — valor_dividendo NULL ou
-- <= 0. Um provento <= 0 não existe economicamente; se aparecer, é ruído
-- da fonte (linha de split mal classificada, por exemplo) e não deve
-- contaminar o dividend yield.
--
-- View, não tabela: re-execução barata e freshness automática quando uma
-- nova partição de ano é gravada no MinIO.
--
-- Não selecionamos a coluna virtual `ano` (derivada do path Hive): a
-- data-ex já carrega o ano, e o staging espelha o schema lógico, não o
-- layout físico de partição.

SELECT
    CAST(data_ex AS DATE)          AS data_ex,
    ticker,
    CAST(valor_dividendo AS DOUBLE) AS valor_dividendo
FROM {{ source('raw', 'dividendos') }}
WHERE valor_dividendo IS NOT NULL
  AND valor_dividendo > 0
