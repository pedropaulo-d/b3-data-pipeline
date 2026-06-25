"""Validação de aceitação da Etapa 6 (indicadores financeiros).

Roda 6 blocos de SELECTs somente leitura sobre os marts produzidos na
Etapa 6 e imprime os resultados formatados no terminal. Serve como
checklist visual de aceitação: confirma que dividendos, indicadores de
mercado e o resumo agregado foram materializados e batem com o esperado.

Os blocos:

1. ``marts.dim_empresa``    — confirma surrogate keys das empresas.
2. Contagens dos três marts — sanity check de "tem linha em tudo?".
3. Dividend yield PETR4      — DY trailing 12m no pregão mais recente.
4. Indicadores de mercado    — retorno, MM30, vol30 anual e drawdown.
5. Janela parcial (Forma A)  — MM200 e contagem nos primeiros pregões.
6. Resumo agregado           — 1 linha por ticker (max drawdown etc).

É um sanity check, não substitui ``dbt test``. Cada bloco roda dentro de
seu próprio try/except: se um falha, imprime o erro e segue para o
próximo, sem abortar a validação inteira.

Uso:

    python -m scripts.validar_etapa6
"""

from __future__ import annotations

import pandas as pd

from warehouse.conexao import CAMINHO_WAREHOUSE, obter_conexao


# Cada bloco é (cabeçalho, SQL). Mantidos juntos para leitura fácil e
# para que o loop em main() trate todos de forma uniforme.
BLOCOS: list[tuple[str, str]] = [
    (
        "Bloco 1: dim_empresa (confirmar surrogate keys)",
        """
        SELECT *
        FROM marts.dim_empresa
        ORDER BY empresa_id
        """,
    ),
    (
        "Bloco 2: Contagens dos marts",
        """
        SELECT
            (SELECT COUNT(*) FROM marts.mart_indicadores_diarios) AS diarios,
            (SELECT COUNT(*) FROM marts.mart_dividend_yield)      AS yield,
            (SELECT COUNT(*) FROM marts.mart_indicadores_resumo)  AS resumo
        """,
    ),
    (
        "Bloco 3: Dividend Yield PETR4 (pregão mais recente)",
        """
        SELECT y.data, y.fechamento_bruto, y.dividendos_12m,
               ROUND(y.dy_12m * 100, 2) AS dy_pct
        FROM marts.mart_dividend_yield y
        JOIN marts.dim_empresa e ON y.empresa_id = e.empresa_id
        WHERE e.ticker = 'PETR4'
        ORDER BY y.data DESC
        LIMIT 1
        """,
    ),
    (
        "Bloco 4: Indicadores de mercado PETR4 (5 pregões recentes)",
        """
        SELECT data,
               ROUND(retorno_simples * 100, 3)        AS ret_pct,
               ROUND(media_movel_30d, 2)              AS mm30,
               ROUND(volatilidade_30d_anual * 100, 1) AS vol30_anual_pct,
               ROUND(drawdown * 100, 1)               AS drawdown_pct
        FROM marts.mart_indicadores_diarios
        WHERE empresa_id = (
            SELECT empresa_id FROM marts.dim_empresa WHERE ticker = 'PETR4'
        )
        ORDER BY data DESC
        LIMIT 5
        """,
    ),
    (
        "Bloco 5: Janela parcial nos primeiros pregões PETR4 (Forma A)",
        """
        SELECT data, ROUND(media_movel_200d, 2) AS mm200, pregoes_janela_200d
        FROM marts.mart_indicadores_diarios
        WHERE empresa_id = (
            SELECT empresa_id FROM marts.dim_empresa WHERE ticker = 'PETR4'
        )
        ORDER BY data
        LIMIT 5
        """,
    ),
    (
        "Bloco 6: Resumo agregado (todos os tickers)",
        """
        SELECT ticker,
               ROUND(max_drawdown * 100, 1)            AS max_dd_pct,
               ROUND(retorno_acumulado_total * 100, 1) AS ret_acum_pct,
               total_pregoes
        FROM marts.mart_indicadores_resumo
        ORDER BY ticker
        """,
    ),
]


def main() -> None:
    if not CAMINHO_WAREHOUSE.exists():
        raise SystemExit(
            f"warehouse.duckdb não encontrado em {CAMINHO_WAREHOUSE}. "
            "Rode `python -m warehouse.setup` primeiro."
        )

    # Mostra todas as colunas/linhas sem truncar — DataFrames de validação
    # são pequenos e queremos ler o conteúdo inteiro no terminal.
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", None)
    pd.set_option("display.max_colwidth", None)

    print(f"Abrindo {CAMINHO_WAREHOUSE} (validação Etapa 6, somente leitura)...")

    # Todos os blocos leem apenas marts (tabelas locais materializadas pelo
    # dbt) — nenhum toca nas views raw.*/staging do MinIO. Logo não há setup
    # de S3 a fazer, e abrimos em read_only de verdade (coexiste com outros
    # leitores, sem disputar o lock de escrita).
    with obter_conexao(read_only=True) as con:
        for cabecalho, sql in BLOCOS:
            print(f"\n=== {cabecalho} ===")
            try:
                df = con.execute(sql).fetchdf()
                print(df.to_string(index=False))
            except Exception as erro:  # noqa: BLE001 - bloco isolado de propósito
                print(f"[ERRO neste bloco] {type(erro).__name__}: {erro}")

    print("\nOK. Se as contagens são > 0 e os números fazem sentido por ticker,")
    print("a Etapa 6 (indicadores + dividendos) está honesta.")


if __name__ == "__main__":
    main()
