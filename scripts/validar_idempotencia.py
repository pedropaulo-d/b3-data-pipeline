"""Valida idempotência semântica do pipeline de ingestão contra o MinIO.

Procedimento:

1. Lê o objeto correspondente a uma data do bucket ``b3-data`` via boto3
   e materializa em DataFrame (ordenado por ticker, índice resetado).
2. Reexecuta a ingestão para a mesma data via ``subprocess`` chamando
   ``python -m ingestion.main --modo range --inicio D --fim D``.
3. Lê o objeto de novo.
4. Compara o conteúdo lógico dos dois DataFrames com
   :func:`pandas.testing.assert_frame_equal`.

Idempotência **semântica** significa que o conteúdo lógico é idêntico —
não que os bytes do objeto são iguais. Os ETags (hash MD5 para objetos
não-multipart) são reportados justamente para deixar visível que
**vão diferir** entre execuções, mesmo num PASS. A causa é metadata do
PyArrow que carrega timestamp de escrita; o tema está documentado em
``docs/decisoes.md``.

Uso:

    python -m scripts.validar_idempotencia
    python -m scripts.validar_idempotencia --data 2026-05-15
    python -m scripts.validar_idempotencia --data 2026-05-15 --verbose

Exit code: 0 se idempotência semântica vale, 1 se quebrou (ou erro).
"""

import argparse
import io
import logging
import os
import subprocess
import sys
from datetime import date, datetime

import boto3
import pandas as pd
from botocore.client import Config
from botocore.exceptions import ClientError, EndpointConnectionError

from ingestion.config import (
    MINIO_ACCESS_KEY,
    MINIO_BUCKET,
    MINIO_ENDPOINT,
    MINIO_REGION,
    MINIO_SECRET_KEY,
    RAIZ_REPO,
    RAW_PREFIX,
)

logger = logging.getLogger(__name__)

# Data default escolhida porque é o pregão usado nas validações manuais
# anteriores (Etapas 1 e 2). Trocar via --data quando convier.
DATA_DEFAULT: date = date(2026, 5, 15)


def criar_cliente_s3():
    """Constrói um cliente boto3 S3 apontando para o MinIO.

    Reproduz a configuração de ``ingestion/storage.py`` (signature v4 +
    path-style addressing) **sem importar de lá** — este script é
    independente e não deve acoplar-se ao módulo de produção.
    """
    return boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        region_name=MINIO_REGION,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def _chave_para(data_pregao: date) -> str:
    """Monta a chave S3 da partição de uma data."""
    return (
        f"{RAW_PREFIX}/"
        f"ano={data_pregao.year:04d}/"
        f"mes={data_pregao.month:02d}/"
        f"dia={data_pregao.day:02d}/"
        f"cotacoes.parquet"
    )


def ler_dataframe_do_minio(
    s3_client, data_pregao: date
) -> tuple[pd.DataFrame, str]:
    """Lê o objeto Parquet da partição e devolve (DataFrame, ETag).

    O DataFrame é retornado **ordenado por ticker e com índice resetado**
    — eliminando ordem como fonte espúria de diferença. ETag é mantido
    com as aspas duplas que o S3 entrega, para reforçar visualmente que
    é uma string opaca.

    Raises:
        RuntimeError: Se o MinIO estiver inacessível, ou se a chave não
            existir no bucket. Mensagens orientam o que fazer.
    """
    chave = _chave_para(data_pregao)
    try:
        resposta = s3_client.get_object(Bucket=MINIO_BUCKET, Key=chave)
    except EndpointConnectionError as exc:
        raise RuntimeError(
            f"MinIO inacessível em {MINIO_ENDPOINT}. Suba o serviço com "
            "`docker compose up -d minio mc-init`."
        ) from exc
    except ClientError as exc:
        codigo = exc.response.get("Error", {}).get("Code", "desconhecido")
        if codigo in ("NoSuchKey", "404"):
            raise RuntimeError(
                f"Objeto inexistente: s3://{MINIO_BUCKET}/{chave}. "
                f"Rode a ingestão antes — `python -m ingestion.main --modo "
                f"range --inicio {data_pregao} --fim {data_pregao}` — ou "
                "escolha outra data (talvez não tenha pregão neste dia)."
            ) from exc
        raise RuntimeError(
            f"Erro do S3 ao ler s3://{MINIO_BUCKET}/{chave} (código={codigo}): {exc}."
        ) from exc

    etag: str = resposta["ETag"]
    corpo = resposta["Body"].read()
    df = pd.read_parquet(io.BytesIO(corpo), engine="pyarrow")

    # Normalização para comparação: ordena por ticker, reseta índice.
    df = df.sort_values("ticker").reset_index(drop=True)
    return df, etag


def rodar_ingestao(data_pregao: date) -> None:
    """Reexecuta a ingestão para a data informada via subprocess.

    Usa ``sys.executable`` para garantir que o Python invocado é o do
    venv ativo. Passa ``cwd=RAIZ_REPO`` por segurança, embora o módulo
    de ingestão resolva paths relativos a partir do próprio
    ``__file__``.

    Raises:
        RuntimeError: Se o processo retornar exit code != 0; embute o
            stderr capturado para diagnóstico.
    """
    comando = [
        sys.executable,
        "-m",
        "ingestion.main",
        "--modo",
        "range",
        "--inicio",
        data_pregao.isoformat(),
        "--fim",
        data_pregao.isoformat(),
    ]
    logger.info("Reexecutando ingestão: %s", " ".join(comando))

    # No Windows em locale PT-BR, o Python filho escreve em cp1252 por
    # padrão; capturar com encoding='utf-8' no lado leitor não basta —
    # precisamos forçar o filho a escrever em UTF-8 via PYTHONIOENCODING.
    # Sem isso, qualquer "ã" do log da ingestão quebra a thread leitora
    # do subprocess e corrompe stdout/stderr capturados.
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}

    try:
        resultado = subprocess.run(
            comando,
            cwd=RAIZ_REPO,
            env=env,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            "Ingestão falhou durante a validação. "
            f"Exit code={exc.returncode}.\n--- stderr ---\n{exc.stderr}"
        ) from exc

    # A ingestão usa logging stdlib, que escreve em stderr por default.
    # Os dois canais são repassados em nível DEBUG; em --verbose o caller
    # os vê na configuração de logging.
    if resultado.stdout:
        logger.debug("stdout da ingestão:\n%s", resultado.stdout)
    if resultado.stderr:
        logger.debug("stderr da ingestão:\n%s", resultado.stderr)


def validar(data_pregao: date, verbose: bool) -> bool:
    """Executa o ciclo de validação e devolve True (PASS) / False (FAIL).

    Saída textual vai para ``stdout`` direto (não via logging) porque é
    interface de relatório para humano, não evento de log estruturado.
    """
    s3 = criar_cliente_s3()

    chave = _chave_para(data_pregao)
    s3_uri = f"s3://{MINIO_BUCKET}/{chave}"

    print(f"[1/3] Lendo objeto inicial do MinIO: {s3_uri}")
    df_antes, etag_antes = ler_dataframe_do_minio(s3, data_pregao)
    print(f"      ETag #1: {etag_antes}")
    print(
        f"      Linhas: {len(df_antes)} | Tickers: {df_antes['ticker'].nunique()}"
    )

    print(f"[2/3] Reexecutando ingestão para {data_pregao.isoformat()}...")
    print(
        f"      {sys.executable} -m ingestion.main --modo range "
        f"--inicio {data_pregao} --fim {data_pregao}"
    )
    rodar_ingestao(data_pregao)
    print("      Exit code: 0")

    print("[3/3] Lendo objeto após reexecução...")
    df_depois, etag_depois = ler_dataframe_do_minio(s3, data_pregao)
    print(f"      ETag #2: {etag_depois}")
    print(
        f"      Linhas: {len(df_depois)} | Tickers: {df_depois['ticker'].nunique()}"
    )
    print()

    if verbose:
        print("--- DataFrame #1 ---")
        print(df_antes.to_string(index=False))
        print()
        print("--- DataFrame #2 ---")
        print(df_depois.to_string(index=False))
        print()

    try:
        pd.testing.assert_frame_equal(
            df_antes,
            df_depois,
            check_like=False,    # já ordenamos por ticker explicitamente
            check_dtype=True,
            check_exact=True,    # valores devem bater bit-a-bit no nível do float
        )
    except AssertionError as exc:
        print("RESULTADO: ❌ FAIL — idempotência semântica QUEBRADA.")
        print()
        print("DataFrame Diff (via pandas.testing.assert_frame_equal):")
        print(str(exc))
        print()
        print("Investigar:")
        print("  - download.py mudou comportamento entre execuções?")
        print("  - yfinance retornou dado diferente?")
        print("  - storage.py introduziu não-determinismo?")
        return False

    print("RESULTADO: ✅ PASS — idempotência semântica validada.")
    print("  - Conteúdo lógico idêntico entre execuções.")
    if etag_antes == etag_depois:
        # Caso raríssimo, mas honesto: se acontecer, vale registrar.
        print("  - ETags iguais (incomum — PyArrow geralmente embute metadata variável).")
    else:
        print(
            "  - ETags diferentes (esperado: PyArrow embute metadata; ver "
            "docs/decisoes.md)."
        )
    return True


def _parse_data(texto: str) -> date:
    """Converte ``YYYY-MM-DD`` em :class:`datetime.date`; argparse type."""
    try:
        return datetime.strptime(texto, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Data inválida {texto!r}; use o formato YYYY-MM-DD."
        ) from exc


def _construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.validar_idempotencia",
        description=(
            "Valida idempotência semântica da ingestão contra o MinIO. "
            "Lê o objeto, reexecuta a ingestão, lê de novo e compara o "
            "DataFrame ordenado por ticker."
        ),
    )
    parser.add_argument(
        "--data",
        type=_parse_data,
        default=DATA_DEFAULT,
        help=(
            "Data do pregão a validar (YYYY-MM-DD). "
            f"Default: {DATA_DEFAULT.isoformat()}."
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Imprime os dois DataFrames mesmo em caso de PASS.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    args = _construir_parser().parse_args(argv)

    try:
        passou = validar(args.data, args.verbose)
    except RuntimeError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 1

    return 0 if passou else 1


if __name__ == "__main__":
    sys.exit(main())
