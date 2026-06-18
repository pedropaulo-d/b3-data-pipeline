"""Dashboard Streamlit do pipeline B3 (Etapa 7).

Aplicação de leitura sobre os marts da Etapa 6. Abre o ``warehouse.duckdb``
em ``read_only=True`` (sem S3 — lê só tabelas locais materializadas) e
renderiza visões interativas com Plotly.

Entry point: ``streamlit run dashboard/app.py``.
"""
