{#
  Sobrescreve o comportamento default do dbt que concatena
  target.schema com custom_schema_name (gerando 'main_staging' etc.
  no DuckDB).

  Comportamento desta versão:
    - Se o model NÃO declara +schema custom: usa target.schema (default).
    - Se o model declara +schema custom: usa o custom schema diretamente,
      sem concatenar com target.schema.

  Resultado no DuckDB para este projeto:
    - staging.* (em vez de main_staging.*)
    - marts.*   (em vez de main_marts.*)
    - seed.*    (em vez de main_seed.*)

  Referência:
  https://docs.getdbt.com/docs/build/custom-schemas#how-does-dbt-generate-a-models-schema-name
#}

{% macro generate_schema_name(custom_schema_name, node) -%}

    {%- if custom_schema_name is none -%}

        {{ target.schema }}

    {%- else -%}

        {{ custom_schema_name | trim }}

    {%- endif -%}

{%- endmacro %}
