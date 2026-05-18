"""Persistência do DataFrame em Parquet particionado por data.

Layout fixado em ``docs/decisoes.md`` e ``CLAUDE.md``:

    data/raw/cotacoes/ano=YYYY/mes=MM/dia=DD/cotacoes.parquet

Cada arquivo contém **uma linha por ticker** para aquela data (no caso de
pregão normal com 6 tickers ativos, 6 linhas). A escrita é **idempotente
por sobrescrita**: rodar o pipeline duas vezes para o mesmo intervalo
produz o mesmo conjunto de arquivos com o mesmo conteúdo.
"""

import logging
from pathlib import Path

import pandas as pd

from ingestion.config import COLUNAS_SAIDA

logger = logging.getLogger(__name__)


def salvar_particionado(df: pd.DataFrame, base_path: Path) -> int:
    """Salva o DataFrame "long" em Parquet particionado por data.

    Para cada data presente em ``df["data"]``, grava
    ``{base_path}/ano=YYYY/mes=MM/dia=DD/cotacoes.parquet`` com as linhas
    correspondentes àquela data. Se o arquivo já existir, é sobrescrito —
    essa é a propriedade de idempotência do raw layer.

    Args:
        df: DataFrame no formato long produzido por
            :func:`ingestion.download.baixar_cotacoes`.
        base_path: Raiz das partições (tipicamente
            :data:`ingestion.config.RAW_PATH`).

    Returns:
        Número de arquivos efetivamente escritos (igual ao número de datas
        únicas em ``df``).

    Raises:
        ValueError: Se ``df`` não tiver o schema esperado.
    """
    if list(df.columns) != COLUNAS_SAIDA:
        raise ValueError(
            f"Schema inesperado em salvar_particionado: {list(df.columns)} "
            f"(esperado {COLUNAS_SAIDA})."
        )

    if df.empty:
        logger.info("DataFrame vazio — nada a gravar.")
        return 0

    arquivos_escritos = 0
    # groupby preservando a chave para iterar (data, sub-df).
    for data_pregao, grupo in df.groupby("data", sort=True):
        destino = _caminho_particao(base_path, data_pregao)
        destino.parent.mkdir(parents=True, exist_ok=True)

        # to_parquet com engine=pyarrow e compression=snappy: padrão da casa.
        # index=False porque o índice do groupby não tem valor analítico.
        grupo.to_parquet(
            destino,
            engine="pyarrow",
            compression="snappy",
            index=False,
        )
        logger.info(
            "Gravado %s (%d linhas).",
            destino.relative_to(base_path.parent.parent.parent),
            len(grupo),
        )
        arquivos_escritos += 1

    logger.info("Total de arquivos gravados: %d.", arquivos_escritos)
    return arquivos_escritos


def _caminho_particao(base_path: Path, data_pregao) -> Path:
    """Monta o caminho ``base/ano=YYYY/mes=MM/dia=DD/cotacoes.parquet``.

    O parâmetro ``data_pregao`` é ``datetime.date`` (vinda do groupby do
    DataFrame). Usamos ``zfill`` implícito via ``%02d`` para garantir o
    padding em mês e dia — é o que ferramentas como Hive/Spark/dbt
    esperam para particionamento estilo Hive.
    """
    return (
        base_path
        / f"ano={data_pregao.year:04d}"
        / f"mes={data_pregao.month:02d}"
        / f"dia={data_pregao.day:02d}"
        / "cotacoes.parquet"
    )
