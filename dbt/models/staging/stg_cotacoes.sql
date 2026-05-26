{{ config(materialized='view') }}

-- Staging de cotações: 1:1 com a source, sem agregação nem JOIN.
--
-- A única "limpeza" aqui é descartar linhas com fechamento_ajustado
-- NULL. Razão: na fato e nos indicadores da Etapa 6, todo cálculo
-- (retorno, média móvel, drawdown) depende de fechamento ajustado.
-- Uma linha sem essa coluna não tem valor analítico e contamina os
-- testes de relacionamento da fato. Descartar aqui é a fronteira
-- correta entre "raw como veio" e "modelo analítico".
--
-- View, não tabela: re-execução é barata e a freshness segue o raw
-- automaticamente (sem `dbt run` adicional só por causa de um
-- novo Parquet no MinIO).

SELECT
    data,
    ticker,
    abertura,
    maxima,
    minima,
    fechamento,
    fechamento_ajustado,
    volume
FROM {{ source('raw', 'cotacoes') }}
WHERE fechamento_ajustado IS NOT NULL
