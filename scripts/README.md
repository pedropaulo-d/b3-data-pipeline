# Scripts utilitários

Pasta de **ferramentas operacionais e de validação**, separadas do
código de pipeline em `ingestion/`. Nada aqui faz parte do fluxo normal
de execução do pipeline — são utilitários para verificar propriedades,
investigar incidentes ou operar o ambiente local.

## Convenção de uso

Rode sempre como módulo, a partir da raiz do repositório, com o venv
ativo:

```bash
python -m scripts.<nome_do_script> [argumentos]
```

Rodar como módulo (`-m`) garante que `import ingestion.config`
funcione — Python adiciona a raiz do repositório ao `sys.path` quando
descobre que `scripts/` é um pacote (graças ao `__init__.py`).

## Scripts disponíveis

### `validar_idempotencia.py`

Valida **idempotência semântica** da ingestão contra o MinIO. O
procedimento é o mesmo que vinha sendo feito manualmente após cada
execução: ler o objeto do bucket, rodar a ingestão de novo para a mesma
data, ler o objeto outra vez e comparar o DataFrame.

```bash
# Data default (2026-05-15)
python -m scripts.validar_idempotencia

# Outra data
python -m scripts.validar_idempotencia --data 2026-05-15

# Verbose: imprime ambos DataFrames mesmo em PASS
python -m scripts.validar_idempotencia --data 2026-05-15 --verbose
```

Pré-requisitos:

- MinIO rodando (`docker compose -f docker-compose.minio.yml up -d`).
- Objeto para a data informada já existente no bucket — se não existir,
  o script orienta a rodar a ingestão para ela primeiro.

Saída: relatório textual no stdout, exit code 0 (PASS) ou 1 (FAIL/erro).

ETags das duas execuções são reportados — e tipicamente **vão diferir**.
Isso é esperado: a garantia é semântica, não byte-a-byte. Ver
`docs/decisoes.md` para o racional.
