# Notas de aprendizado

Caderno de bordo do projeto. Uma seção por etapa. Em cada uma, três subseções:

- **Conceitos** — o que aprendi de novo (ferramenta, padrão, abstração).
- **Dúvidas** — o que ficou confuso ou em aberto.
- **Descobertas** — o que me surpreendeu, o que mudou minha visão.

O objetivo é ter material concreto para revisar antes de entrevista — não memorizar comandos, mas reconstruir o raciocínio.

---

## Etapa 0 — Preparação

**Início:** 2026-05-18
**Fim:** —

### Conceitos

- **Projeto de portfólio vs ferramenta funcional.** O objetivo deste projeto é demonstrar competências para vaga de engenharia de dados, não substituir Status Invest ou TradingView. Cada peça da stack (Airflow, S3, dbt, DuckDB) existe para aparecer no currículo, não porque o problema exige. Isso muda o critério de decisão em cada etapa: "qual escolha é mais defensável em entrevista" em vez de "qual é a mais eficiente".
- **MinIO vs S3 real.** MinIO implementa a API S3 por construção. Código que escreve em MinIO escreve em S3 trocando apenas o endpoint. Para projeto pessoal, MinIO local é zero custo e velocidade de iteração; o aprendizado conceitual é idêntico. A única coisa que se perde é exercitar IAM da AWS — mitigado por documentar a portabilidade no README.
- **Idempotência como princípio fundamental.** Antes mesmo de escrever a primeira linha, decidi que toda etapa precisaria respeitar idempotência. Isso travou decisões posteriores (sobrescrever vs versionar, como testar reexecução, como o Airflow vai disparar backfill na Etapa 5).
- **Arquitetura medalhão.** Camadas raw → staging → marts. O raw é imutável e fiel à fonte. Staging limpa tipos e nomes (1:1 com raw). Marts são modelos analíticos finais (Kimball: fato + dimensões). Cada camada tem responsabilidade clara, o que evita o anti-padrão "SQL gigante que faz tudo de uma vez".

### Dúvidas

- Em projeto de tamanho médio (não pequeno, não FAANG), onde mora o limite entre "abstrair backend" e "trocar direto"? No meu caso decidi trocar direto na Etapa 2, mas a resposta certa parece variar com o contexto. Vale revisitar quando estudar projetos open-source de engenharia de dados.
- Quando uma empresa adota dbt, ela ainda usa stored procedures para alguma coisa? Ou dbt absorve tudo que era SQL transformacional? (Resposta provável: convive, mas dbt vira o "padrão novo" — confirmar lendo postmortem de empresas que migraram.)

### Descobertas

- **Tabela de "competências por peça" do README virou âncora mental.** Escrever a tabela "qual peça da stack demonstra qual competência" no início do projeto me forçou a justificar cada escolha. Em vaga de engenharia de dados, recrutador olha exatamente isso. Quando bater dúvida "vale a pena adicionar X?", a pergunta certa é: "isso adiciona uma linha nova à tabela, ou é redundante?"
- **CLAUDE.md como artefato de governança.** Não é só prompt — é um documento que define divisão de trabalho humano/IA explicitamente. Quando recrutador perguntar "como você usou IA no projeto?", esse arquivo é a resposta concreta.

---

## Etapa 1 — Ingestão manual com Python puro

**Início:** 2026-05-18
**Fim:** —

### Conceitos a estudar nesta etapa

- **yfinance** — é um *wrapper* não-oficial sobre páginas e endpoints internos do Yahoo Finance. Não é API oficial; pode quebrar quando o Yahoo muda o HTML/JSON interno. Tem *rate limiting* implícito (sem documentação formal) — em loop apertado, o servidor passa a devolver respostas vazias ou 429. Para um projeto de portfólio com 6 tickers é seguro; para algo de produção a fonte deveria ser uma API paga (B3 oficial, Refinitiv, etc.) ou um dump do CEDRO.
- **Parquet** — formato colunar, binário, com schema embutido. Por que importa:
  - *Colunar* — em uma consulta que lê só `fechamento_ajustado`, o Parquet abre apenas essa coluna no disco. Em CSV teria que ler tudo.
  - *Compressão Snappy* — rápida (importa mais que tamanho final para nosso caso), padrão da indústria.
  - *Schema embutido* — não há "qual o tipo de `volume`?" depois; o arquivo já carrega.
- **Particionamento estilo Hive** — `ano=YYYY/mes=MM/dia=DD/`. Não é só convenção de pasta: ferramentas (Spark, dbt, DuckDB) **leem o nome do diretório como coluna virtual**. Isso habilita *partition pruning* — só ler os arquivos cujo caminho casa com o filtro `WHERE ano = 2026 AND mes = 05`.
- **Imutabilidade do raw layer** — uma vez gravado, o raw não é alterado por transformação. Correção de bug em `download.py` não reescreve raw passado; correção da fonte gera nova execução que sobrescreve a partição.
- **Idempotência** — propriedade de rodar várias vezes com o mesmo input e chegar no mesmo output. No nosso caso: gravação sobrescrita por data. Em orquestração (Airflow), idempotência é o que permite re-disparar uma task sem medo.

### Dúvidas

- O `dropna(how="all")` em preços é robusto para nossos 6 tickers, mas e se um dia o yfinance retornar uma linha com `fechamento` válido mas todos os outros NaN? Hoje a linha sobrevive ao filtro. Vale criar uma validação dbt na Etapa 4 que sinalize esse caso.
- Pregão de leilão (dia útil com pregão parcial, ex: véspera de Carnaval) gera dado normal? Não testei explicitamente — vale verificar quando rodar a ingestão por algumas semanas e olhar os dados.
- O `auto_adjust=False` me dá Open/High/Low/Close brutos e Adj Close separado. Mas só o Close tem versão ajustada — Open/High/Low brutos não são "ajustados" pelo Yahoo. Para retornos intraday seria preciso ajustar todos. Como nosso pipeline trabalha em granularidade diária, fechamento ajustado é suficiente, mas se algum dia migrar para intraday a regra muda.

### Descobertas

- **Idempotência** - semântica ≠ byte-a-byte. Descobri que comparar hash de arquivos Parquet entre duas execuções dá False mesmo quando o conteúdo é idêntico — PyArrow embute metadata com timestamp de escrita. O teste correto de idempotência em pipeline de dados é comparar o conteúdo lógico (DataFrame após sort_values + reset_index), não bytes. Airflow, dbt e Spark definem idempotência dessa forma.


---

## Etapa 2 — Object storage com MinIO

**Início:** 2026-05-18
**Fim:** —

### Conceitos a estudar nesta etapa

- **Object storage vs filesystem.** Em S3/MinIO não há "pasta": existe um
  **bucket** (namespace) e dentro dele **objetos** identificados por uma
  **chave** (string opaca). O `/` é só convenção visual — `raw/cotacoes/a.parquet`
  é uma string única, não um arquivo dentro de uma pasta. Listar
  "uma pasta" é na verdade `ListObjectsV2` com `Prefix=raw/cotacoes/`.
- **Operações fundamentais da S3 API.** `PUT` (sobe objeto, sobrescreve se
  existir), `GET` (baixa), `LIST` (paginada, máx 1000 chaves por página),
  `DELETE`. Operações de "renomear" e "mover" não existem nativamente —
  são `COPY` + `DELETE`.
- **Signature v4.** Versão atual do algoritmo de assinatura HMAC-SHA256
  que o S3 (e MinIO) usa para autenticar requisições. Por isso o cliente
  precisa de `aws_access_key_id`, `aws_secret_access_key` e `region_name`
  — a região entra no cálculo da assinatura, mesmo que o MinIO ignore
  ela funcionalmente.
- **Addressing style.** Duas formas de endereçar um bucket: `virtual-hosted`
  (`https://bucket.endpoint/key`) e `path-style` (`https://endpoint/bucket/key`).
  MinIO em `localhost` exige path-style — virtual-hosted precisaria de
  DNS wildcard. Por isso o cliente é configurado com
  `s3={"addressing_style": "path"}`.
- **boto3: client vs resource.** O `client` é a interface baixa, equivalente
  às chamadas da API. O `resource` é uma abstração orientada a objetos
  (`s3.Bucket("nome").upload_file(...)`). Para o nosso caso, `client` é
  suficiente e explícito.
- **MinIO.** Servidor S3-compatível single-binary. Roda no Docker com
  `server /data --console-address ":9001"`. Console web em 9001 mostra
  buckets, objetos e métricas — útil durante aprendizado, dispensável
  em produção.
- **mc (MinIO Client).** CLI oficial do MinIO. Usado no `mc-init` para
  criar o bucket automaticamente: `mc alias set ...` aponta para o
  servidor, `mc mb` cria o bucket, `--ignore-existing` torna idempotente.
- **Docker Compose: depends_on com condition.** Sem `condition`, o
  Compose só garante que o container dependente **iniciou**, não que
  está pronto. Com `condition: service_healthy`, o `mc-init` espera o
  healthcheck do MinIO passar antes de rodar — evita race condition
  na criação do bucket.
- **Volumes nomeados.** `minio_data:/data` mantém o dado mesmo após
  `docker compose down`. Só `docker compose down -v` (ou `docker volume rm`)
  apaga. O nome do volume real é `b3-minio-data` (definido em `volumes:`).
- **`.env` e python-dotenv.** Arquivo fora do código com pares
  `CHAVE=valor`. Não vai para o git (`.env` no `.gitignore`). O
  `.env.example` é o template versionado — quem clona o repo copia e
  ajusta. `load_dotenv()` lê o arquivo e popula `os.environ` em tempo
  de import.

### Dúvidas

- Bucket único com prefixos funciona para projeto pequeno, mas em vaga real a separação por bucket é padrão. Vale entender melhor quando a granularidade IAM (permissão por bucket) supera a simplicidade de bucket único. Provavelmente quando há múltiplos times consumindo camadas diferentes — não é o nosso caso.
- O cliente boto3 é instanciado a cada call de `salvar_particionado`. Para 1 dia (1 objeto) é irrelevante. Para o `--modo inicial` (1246 objetos), instanciamos 1 cliente para 1246 PUTs — eficiente. Mas e se um dia o pipeline rodar em paralelo (Spark, Dask)? Cada worker instanciaria seu próprio cliente; isso é o esperado em boto3 (clientes são thread-safe mas não devem ser compartilhados entre processos sem cuidado).
- O `endpoint_url=http://localhost:9000` é HTTP, sem TLS. Em produção seria HTTPS com certificado. O código não muda — só a string do endpoint. Vale lembrar disso se algum dia migrar para S3 real.

### Descobertas
- **ETag do MinIO ≠ MD5 quando há multipart upload.** Para objetos pequenos como os nossos (~6KB), o ETag é o MD5 direto. Para objetos grandes via multipart upload (>5MB por padrão no boto3), o ETag passa a ser um hash composto e termina com -N onde N é o número de partes. Em pipelines de produção lidando com arquivos maiores, comparar ETags exige cuidado.
Validação de idempotência contra S3/MinIO usa boto3 get_object, não filesystem. Diferente da Etapa 1 onde bastava Get-FileHash, com object storage o teste correto é ler o objeto via API, materializar em DataFrame, e comparar conteúdo lógico. Reforça a lição da Etapa 1: idempotência em pipeline de dados é sempre semântica.
- **`region_name` é obrigatório no boto3 mesmo apontando para localhost.** A signature v4 do S3 inclui a região no cálculo da assinatura, então o cliente precisa de uma. MinIO não valida o valor (aceita qualquer string), mas o boto3 valida que ela existe. Default `us-east-1` é a convenção. Pegadinha que aparece em entrevista: "por que você está mandando uma região para um servidor que está no seu laptop?" — resposta: signature v4 exige.
- **PyArrow grava Int64 nullable como Arrow int64 com bitmap de validade, transparente entre escrita e leitura.** Não precisei de cast manual. O Parquet preserva o conceito de "valor faltante" no nível do formato, separado do valor em si. Em CSV isso seria impossível (NaN viraria string ou número mágico).
- **mc-init como serviço Compose efêmero.** O serviço `mc-init` no docker-compose existe para criar o bucket na primeira execução, depois sai com exit 0. Vê-lo como "exited (0)" em `docker compose ps` é o estado correto. Padrão útil sempre que precisar de "setup uma vez, esquece" em ambiente containerizado.

---

## Etapa 3 — Warehouse analítico com DuckDB

**Início:** —
**Fim:** —

### Conceitos
(em branco até começar)

### Dúvidas
(em branco até começar)

### Descobertas
(em branco até começar)

---

## Etapa 4 — Transformações com dbt

**Início:** —
**Fim:** —

### Conceitos
(em branco até começar)

### Dúvidas
(em branco até começar)

### Descobertas
(em branco até começar)

---

## Etapa 5 — Orquestração com Airflow

**Início:** —
**Fim:** —

### Conceitos
(em branco até começar)

### Dúvidas
(em branco até começar)

### Descobertas
(em branco até começar)

---

## Etapa 6 — Indicadores e métricas financeiras

**Início:** —
**Fim:** —

### Conceitos
(em branco até começar)

### Dúvidas
(em branco até começar)

### Descobertas
(em branco até começar)

---

## Etapa 7 — Dashboard com Streamlit

**Início:** —
**Fim:** —

### Conceitos
(em branco até começar)

### Dúvidas
(em branco até começar)

### Descobertas
(em branco até começar)

---

## Etapa 8 — Polimento, documentação e portfólio

**Início:** —
**Fim:** —

### Conceitos
(em branco até começar)

### Dúvidas
(em branco até começar)

### Descobertas
(em branco até começar)
