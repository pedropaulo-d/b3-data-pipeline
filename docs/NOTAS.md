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

**Início:** 2026-05-19
**Fim:** 2026-05-19

### Conceitos

- **DuckDB.** Banco analítico embarcado, colunar, sem servidor. Roda
  dentro do processo Python via `import duckdb`. SQLite está para
  Postgres assim como DuckDB está para BigQuery — embarcado vs servidor,
  OLAP vs OLTP. O arquivo `.duckdb` é o banco inteiro: schemas, views,
  tabelas, num único binário. Só um processo pode escrever por vez;
  múltiplos podem ler simultaneamente (`read_only=True`).

- **Extensão httpfs.** O que viabiliza o DuckDB ler do MinIO via HTTP
  usando a S3 API. Sem ela, `read_parquet('s3://...')` daria erro. A
  extensão é instalada uma vez (`INSTALL httpfs`) e carregada por sessão
  (`LOAD httpfs`). Configuração via `SET s3_endpoint`, `SET
  s3_use_ssl`, `SET s3_url_style`, mais credenciais.

- **View vs tabela materializada.** View é query salva com nome — não
  armazena dado, re-executa toda vez. Tabela materializada copia o
  resultado para o disco e fica "congelada" até alguém atualizar.
  Trade-off central: view sempre fresca, custo de re-execução; tabela
  sempre rápida, risco de ficar desatualizada. Escolhi view para
  `raw.cotacoes` porque queria que novos Parquet no MinIO aparecessem
  automaticamente sem rematerializar.

- **hive_partitioning.** Convenção que transforma trechos do path em
  colunas virtuais. `s3://b3-data/raw/cotacoes/ano=2026/mes=05/dia=15/...`
  expõe `ano`, `mes`, `dia` como se fossem colunas da tabela. Filtrar
  por essas colunas habilita **partition pruning** — o DuckDB consulta
  apenas os arquivos cujo path casa com o filtro, em vez de ler tudo.
  Ganho real quando o dataset cresce.

- **Window functions.** Função que opera sobre uma janela de linhas
  sem colapsar elas (diferente do GROUP BY). Anatomia:
  `função(args) OVER (PARTITION BY ... ORDER BY ... ROWS BETWEEN ...)`.
  `PARTITION BY` cria janelas independentes; `ORDER BY` dá ordem
  interna; `ROWS BETWEEN` define moldura móvel. Funções principais:
  `LAG`/`LEAD` (linha anterior/posterior), `ROW_NUMBER`/`RANK`/
  `DENSE_RANK` (ranking), `FIRST_VALUE`/`LAST_VALUE` (extremos da
  janela), `AVG/SUM/MAX OVER (...)` (agregação preservando linhas).
  Habilidade SQL mais durável e portável (sintaxe idêntica entre
  DuckDB, Postgres, BigQuery, Snowflake).

- **CTEs (Common Table Expressions, cláusula WITH).** Maneira de
  nomear subqueries para tornar SQL legível. Cada CTE pode referenciar
  as anteriores. Não materializa nada por padrão — é só açúcar
  sintático. Padrão "gaps and islands" (usado para detectar sequências)
  é exemplo clássico onde CTEs encadeadas tornam a lógica óbvia.

- **Anti-join via LEFT JOIN + IS NULL.** Padrão para encontrar "o que
  existe num conjunto mas não no outro". `LEFT JOIN B ON ... WHERE
  B.id IS NULL` retorna as linhas de A sem correspondente em B. Usado
  na query 05 para detectar gaps de pregão por ticker.

- **Por que o raw fica fora do warehouse.** Quatro razões: (1) custo —
  object storage é barato, warehouse é caro; (2) imutabilidade — fora
  do warehouse ninguém roda UPDATE acidental no raw; (3)
  reprocessabilidade — bug na transformação não exige re-ingerir da
  fonte; (4) múltiplos consumidores — o mesmo raw pode alimentar
  vários warehouses ou ferramentas. Esse desacoplamento é o que torna
  a arquitetura "lakehouse" possível.

- **Diferença CSV vs Parquet (revisita).** CSV é orientado a linha:
  ler uma coluna exige ler o arquivo inteiro. Parquet é colunar: ler
  uma coluna lê só os bytes dela. Mais: schema embutido (sem
  adivinhação de tipo), compressão por coluna (muito melhor),
  estatísticas por bloco (habilita predicate pushdown). Custo: binário,
  não abre em editor de texto.

### Dúvidas

- Quando usar `RANK`, `DENSE_RANK` e `ROW_NUMBER`? Sei a diferença
  conceitual (RANK deixa lacunas após empate, DENSE_RANK não, ROW_NUMBER
  não tem empate), mas qual usar em entrevista quando o enunciado é
  ambíguo? Revisar antes de entrevista.

- Materialização do dbt vs view: qual o critério em projeto real para
  decidir entre `view`, `table` e `incremental`? Em projeto pequeno
  como o meu, view basta — mas quando o custo de re-execução começa a
  doer? Resposta provável vem na Etapa 4 ao tocar dbt na prática.

- A view `raw.cotacoes` re-lê o MinIO a cada consulta ou o DuckDB
  cacheia? Notei que a primeira query é mais lenta que as subsequentes
  — cache de metadado, de dado, ou ambos?

- `LAST_VALUE` por padrão pega só até a linha atual, não até o fim da
  janela. Pegadinha clássica. Sempre que eu quiser "valor final
  verdadeiro", preciso explicitar `ROWS BETWEEN UNBOUNDED PRECEDING AND
  UNBOUNDED FOLLOWING`. Entendi conceitualmente, mas vale praticar em
  problemas reais para internalizar.

- O padrão "gaps and islands" (soma cumulativa de flag para criar
  grupos) é elegante mas eu travei na primeira tentativa. Vale praticar
  variações além de "sequência de altas consecutivas" — ex: períodos
  ininterruptos sem queda > 5%, sequência de volume acima da média.

### Descobertas

- **Divergência silenciosa entre MinIO e filesystem na Etapa 2.** A
  migração de storage da Etapa 2 trocou o destino do `storage.py` para
  o MinIO, mas a carga histórica gerada na Etapa 1 ficou apenas no
  filesystem local — nunca foi replicada para o bucket. Só percebi
  na Etapa 3, quando o DuckDB reportou 6 linhas em vez de ~7.500 ao
  consultar `raw.cotacoes`. Lição prática: migração de storage exige
  replicação consciente do estado anterior, ou o pipeline parece
  funcionar lendo apenas o último dia ingerido pós-migração. Em
  produção isso seria backfill explícito; aqui foi reexecução acidental
  descoberta uma etapa depois. Material direto para entrevista quando
  perguntarem "conta um bug não óbvio que você descobriu no seu
  pipeline".

- **`hive_partitioning=true` expõe partições como colunas virtuais.**
  Após o setup, `DESCRIBE raw.cotacoes` mostra `ano`, `mes`, `dia` ao
  lado das colunas reais do Parquet. Não é mágica — o DuckDB lê o path
  do arquivo e parseia os segmentos `chave=valor`. Crítico para
  performance: filtrar `WHERE ano = 2026 AND mes = 5` faz o DuckDB
  ignorar os arquivos cujo path não casa, sem nem abrir.

- **Latência da primeira query vs subsequentes.** A primeira `SELECT
  COUNT(*) FROM raw.cotacoes` levou alguns segundos (lê metadata dos
  ~1246 objetos via HTTP). Queries depois ficam rápidas — DuckDB
  cacheia metadados de objetos S3 dentro da sessão. Fechou a sessão e
  abriu de novo, paga o custo de novo. Pegadinha real: se um benchmark
  rodar só queries "frias", a leitura parece lenta; se rodar várias
  vezes, parece rápida. Sempre fazer warmup antes de medir.

- **Servidor e cliente MinIO são imagens Docker separadas.**
  `minio/minio` é o servidor (processo permanente, expõe API S3 e
  console). `minio/mc` é o cliente CLI, usado como init container para
  criar o bucket automaticamente. Vê-los como duas imagens é o
  esperado, não duplicação. Padrão consagrado: Postgres tem
  `postgres` + `psql`; Redis tem `redis-server` + `redis-cli`.

- **`SET` no DuckDB não aceita parametrização (?) como `SELECT`.** A
  documentação não destaca isso, e o erro é confuso quando você tenta
  passar credencial via `con.execute("SET s3_secret_access_key = ?",
  [valor])`. Em versões recentes do DuckDB funciona; em mais antigas
  precisa concatenar string. Cuidado em logs para não vazar credencial.

- **View como abstração viva, não snapshot.** Criar view com
  `WHERE data >= (SELECT MAX(data) - INTERVAL 30 DAY FROM ...)` é
  diferente de `WHERE data >= '2026-04-15'`. A primeira envelhece
  bem; a segunda quebra em duas semanas. Princípio geral: prefira
  lógica computada a literais quando a lógica representa "última N
  unidades", "ativos hoje", "exercício corrente".

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
