"""Utilitários de validação e operação do pipeline.

Scripts auxiliares que NÃO fazem parte do fluxo de ingestão/transformação
em si — são sanity checks e validações de aceitação, executáveis via
``python -m scripts.<nome>``:

- ``checar_warehouse``     — resumo do estado do warehouse após a DAG.
- ``validar_etapa6``       — checklist de aceitação dos marts da Etapa 6.
- ``validar_idempotencia`` — valida a idempotência semântica da ingestão.

A saída destes scripts é um relatório para humano no terminal — por isso
usam ``print`` (não ``logging``): a saída é o produto, não evento de log
operacional (ver ``docs/decisoes.md``).
"""
