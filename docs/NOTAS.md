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

**Início:** 2026-05-25
**Fim:** —

### Conceitos
(preencher após executar)

### Dúvidas
(preencher após executar)

### Descobertas
(preencher após executar — sugestões para registrar: tempo do
`dbt build`, surpresas na execução, particularidades do DuckDB com
dbt, comportamento da macro `generate_schema_name` no nome final
dos schemas, latência de cold start do httpfs vs warm cache)

---

## Etapa 5 — Orquestração com Airflow

**Início:** 2026-06-03
**Fim:** 2026-06-11

### Conceitos

- **DAG (Directed Acyclic Graph).** Estrutura que descreve um pipeline:
  vértices são tasks, arestas são dependências. Sem ciclos — uma task
  não pode depender (direta ou indiretamente) de si mesma. No Airflow,
  uma DAG é um arquivo Python que **declara** o grafo (não executa);
  o scheduler interpreta e dispara as runs.

- **Operator e task.** *Operator* é o template ("o que fazer" —
  BashOperator roda shell, PythonOperator roda função, etc.).
  *Task* é a instância do operator dentro de uma DAG (com `task_id`,
  parâmetros e posição no grafo). Cada operator tem um contrato: rodar
  até o fim ou falhar; o Airflow registra o resultado.

- **Scheduler vs worker vs webserver.** Três processos do Airflow,
  com responsabilidades distintas:
  - **scheduler** decide *quando* uma task deve rodar (checa cron,
    dependências, retries) e cria *task instances* no banco;
  - **worker** *executa* as task instances (LocalExecutor: workers são
    subprocessos do scheduler; CeleryExecutor: workers em containers
    separados consumindo fila);
  - **webserver** expõe a UI HTTP — não toca em execução, só lê do
    banco e exibe.

- **Executor.** Camada de abstração que decide *onde* o worker roda.
  `SequentialExecutor` (single thread, dev), `LocalExecutor`
  (subprocessos no mesmo host), `CeleryExecutor` (fila + workers
  remotos), `KubernetesExecutor` (pod por task). Nossa escolha:
  LocalExecutor — projeto single-host, sem necessidade de escala
  horizontal.

- **`execution_date` vs `logical_date` (Airflow 2.x).** O Airflow
  agenda runs por *janela*: uma run agendada para `2026-06-03 20:00`
  representa o **dia útil 2026-06-03**. A data lógica daquele run é
  `2026-06-03 20:00` (em Airflow 1.x chamava-se `execution_date`; em
  2.2+ foi renomeada para `logical_date`). Confusão clássica: o run
  "do dia 03" só dispara **depois** das 20h do dia 03, mas a
  `logical_date` é o INÍCIO da janela, não o momento físico do
  disparo. Em pipelines com janela diária, `logical_date` é a chave
  para idempotência: "rodei o pipeline para a janela X" é diferente
  de "rodei o pipeline hoje".

- **`start_date` + `catchup`.** `start_date` é a primeira data lógica
  válida da DAG. Com `catchup=True`, ao despausar uma DAG, o
  scheduler dispara todos os runs perdidos entre `start_date` e
  agora (backfill automático). Com `catchup=False`, ele pula direto
  para o próximo horário-alvo após o despausar. Nossa escolha:
  catchup=False — a fonte (yfinance) não muda valor histórico
  retroativamente; reprocessar passado seria trabalho duplicado sem
  efeito.

- **Retry e retry_delay.** `retries=N` permite N tentativas adicionais
  após a primeira falha (total: N+1 execuções). `retry_delay` define
  o intervalo entre tentativas. Sem backoff exponencial (parâmetro
  separado `retry_exponential_backoff`). Cobertura típica:
  - falha de rede (yfinance, MinIO) — retry resolve;
  - bug no código — retry não resolve, vai falhar 3 vezes seguidas.
  Distinguir cedo: se uma task SEMPRE falha em todas as N+1
  tentativas, é bug, não transiente.

- **BashOperator e bind mount.** BashOperator roda `bash -c "comando"`
  dentro do container do worker. Bind mount monta um diretório do
  host (ou de outro lugar) DENTRO do container — mudanças no host
  aparecem instantaneamente no container e vice-versa. Combinação
  usada aqui: o projeto inteiro (`.`) é bind-montado em
  `/opt/project`, e cada BashOperator faz `cd /opt/project && ...`.

- **`x-` extension fields no Compose.** Yaml permite chaves
  arbitrárias se começarem com `x-`. O Compose usa esse mecanismo
  para definir "anchors" reutilizáveis (`x-airflow-common`) que vários
  serviços referenciam via `<<: *anchor`. Reduz duplicação sem
  inventar uma nova feature do Compose — é puramente YAML.

- **`depends_on` com `condition`.** Sem `condition`, o Compose só
  garante que o container dependente *iniciou* (mesmo que esteja em
  loop de falha). Com `condition: service_healthy`, espera o
  healthcheck passar; com `condition: service_completed_successfully`,
  espera o container sair com exit 0 (padrão para init containers).
  Crítico para o `airflow-init`: webserver e scheduler só sobem
  depois que migrate + create user terminou.

### Dúvidas

- Quando vale a pena migrar de LocalExecutor para CeleryExecutor? Sei
  que é questão de escala (volume de tasks > capacidade de uma máquina),
  mas qual o sinal concreto na prática? Número de DAGs? Duração das
  tasks? Concorrência?

- O `warehouse.duckdb` é escrito por refresh_warehouse e por dbt_run em
  sequência na DAG. Como são sequenciais, não houve lock. Mas se eu
  rodar algo no host (notebook, DBeaver) enquanto a DAG executa, dá
  LockError. Como ambientes de produção lidam com isso? Réplica de
  leitura? Janela de manutenção? (Provavelmente DuckDB não é o banco
  certo para concorrência alta — é OLAP embarcado, não servidor.)

- O retry está configurado (retries=2, retry_delay=5min) mas só vou
  validar empiricamente agora. Backoff fixo vs exponencial: quando cada
  um faz sentido?

- A DAG só roda `--modo diario` (hoje). Backfill histórico segue manual
  via CLI. Como seria implementar backfill via DAG usando
  `{{ data_interval_start }}` do Airflow? Vale o esforço para este
  projeto?

### Descobertas

- **YAML folded scalar (`>`) quebra entrypoint bash silenciosamente.**
  Usei `>` (folded scalar) no entrypoint do airflow-init com os
  argumentos do `airflow users create` indentados a mais para
  legibilidade. Regra sutil: `>` preserva newline literal quando há
  indentação extra, então o bash recebeu `\n` no meio dos argumentos e
  antes do `|| true`, quebrando a sintaxe do subshell ("syntax error
  near unexpected token"). Solução: forma de array `[/bin/bash, -c, |]`
  com bloco literal `|` e continuação `\` no fim de cada linha. Lição:
  em entrypoint multi-linha no Compose, bloco literal `|` é mais seguro
  que folded `>`.

- **`.gitignore` com trailing slash impede até a negação do .gitkeep.**
  O pattern `airflow/logs/` (com barra final) faz o git nem entrar no
  diretório, então `!airflow/logs/.gitkeep` não tem efeito — a negação
  não consegue "resgatar" um arquivo dentro de uma pasta que o git
  ignorou inteira. Além disso, uma regra geral `logs/` em outra seção
  do mesmo .gitignore também capturava o diretório. Solução: usar
  `airflow/logs/*` (ignora o conteúdo mas deixa a pasta acessível) +
  `!airflow/logs/.gitkeep`. Lição: para versionar pasta vazia, ignore
  o conteúdo (`pasta/*`), não a pasta (`pasta/`).

- **Airflow mostra horários em UTC na UI apesar de timezone configurado.**
  Configurei `AIRFLOW__CORE__DEFAULT_TIMEZONE=America/Sao_Paulo`, mas a
  UI mostra "Next dagrun" em UTC (ex: 23:00 UTC = 20:00 BRT). A config
  afeta o agendamento (quando a DAG dispara), não a exibição. Tive que
  converter mentalmente UTC-3. Não é bug — é comportamento conhecido do
  Airflow. Lição: timezone-aware scheduling ≠ timezone-aware display.

- **Endpoint do MinIO difere entre host e container.** No host, o código
  acessa o MinIO via `localhost:9000`. Dentro de um container do mesmo
  docker-compose, `localhost` aponta para o próprio container — o MinIO
  é alcançado pelo nome do serviço (`minio:9000`). Resolvi injetando
  `MINIO_ENDPOINT=http://minio:9000` no ambiente dos containers do
  Airflow via compose, enquanto o `.env` do host mantém `localhost`. O
  `load_dotenv(override=False)` garante que a variável injetada pelo
  compose vence o `.env`. Lição: rede Docker resolve serviços por nome,
  não por localhost.

- **Lock de dependências conflita com imagem base que já tem
  constraints.** Tentei usar `requirements.lock` no Dockerfile do
  Airflow, mas a imagem `apache/airflow:2.10.5` já fixa versões de libs
  comuns (Jinja2, click, pydantic). O lock gerado de um venv standalone
  bateu de frente e quebrou o build. Solução: Dockerfile usa
  `requirements.txt` (pip resolve contra as constraints da imagem);
  o lock fica como referência do ambiente host. Lição: ao construir
  sobre imagem base, ela já é parte do lock — impor outro por cima
  cria conflito. A forma correta seria o constraints file oficial do
  Airflow.

---

## Etapa 6 — Indicadores e métricas financeiras

**Início:** 2026-06-11
**Fim:** 2026-06-12

### Conceitos

- **Retorno simples vs logarítmico.** Simples = `P_t/P_{t-1} - 1`;
  log = `ln(P_t/P_{t-1})`. O log é **aditivo no tempo** (somar os logs
  diários dá o log do período), o que o torna a base natural para
  volatilidade e qualquer agregação temporal. O simples é melhor para
  **agregar entre ativos** (retorno de uma carteira é a média ponderada
  dos retornos simples) e para comunicar a leigos. Por isso o mart
  expõe os dois.

- **Preço ajustado para retorno/risco, bruto para dividend yield.** O
  fechamento ajustado já desconta proventos (reinveste dividendos no
  preço), então é o correto para medir retorno total e volatilidade. Mas
  usá-lo no dividend yield **contaria o provento duas vezes** — o ajuste
  já embutiu o dividendo no preço, e o yield voltaria a somá-lo no
  numerador. Por isso o DY usa fechamento **bruto** no denominador.

- **Volatilidade = desvio-padrão dos retornos, anualizada por √252.**
  A variância escala **linear** no tempo (variância de N dias = N ×
  variância diária, sob i.i.d.), logo a volatilidade — que é a raiz —
  escala por **√N**. Com ~252 pregões por ano, anualiza-se multiplicando
  por √252. Uso desvio-padrão **amostral (N-1)** porque estimo a partir
  de uma amostra, não da população inteira.

- **Drawdown = queda desde o pico histórico.** Para cada pregão,
  `drawdown = preço/MAX(preço até aqui) - 1`, com o pico calculado por
  frame expansivo `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`. É
  sempre ≤ 0 (no topo histórico vale 0). O **max drawdown** é o pior
  valor da série — a maior perda que um investidor que comprou no topo
  teria amargado.

- **Médias móveis contam pregões, não dias corridos.** A janela `ROWS
  BETWEEN 29 PRECEDING AND CURRENT ROW` pega 30 **linhas** (pregões),
  não 30 dias de calendário — fim de semana e feriado não entram. Nos
  primeiros N-1 pregões a janela é **parcial** (não há 30 pregões
  anteriores ainda); sinalizo isso com uma coluna de **contagem**
  (`pregoes_janela_Nd`) em vez de descartar as linhas — é a "Forma A".

- **Range join para a janela trailing de 365 dias.** O dividend yield
  soma dividendos dos últimos 365 dias **corridos**. Como a data-ex de
  um provento raramente cai num pregão, não dá para usar frame `ROWS`;
  uso um self-join por intervalo (`d.data BETWEEN c.data - 365 AND
  c.data`). Robusto a datas que não existem na série de cotações.

- **Window function não referencia outra no mesmo SELECT.** Não dá para
  fazer `AVG(retorno) OVER (...)` se `retorno` é ele próprio uma window
  na mesma camada — o SQL avalia todas as windows do SELECT "ao mesmo
  tempo". A solução é encadear CTEs: uma camada calcula o retorno, a
  seguinte calcula a média móvel sobre ele.

- **Named windows com frame estendido.** `WINDOW w AS (PARTITION BY ...
  ORDER BY ...)` declara a janela uma vez; cada uso pode estender o
  frame: `AVG(...) OVER (w ROWS BETWEEN 29 PRECEDING AND CURRENT ROW)`.
  Evita repetir `PARTITION BY ... ORDER BY ...` em cada indicador.

- **Dimensões conformadas.** `dim_empresa` e `dim_tempo` servem **tanto**
  `fato_cotacoes_diarias` quanto `fato_dividendos`. Uma dimensão
  conformada é compartilhada por múltiplas fatos com o mesmo significado
  — é o que permite cruzar as duas fatos pela mesma chave.

- **Fact-to-fact join via dimensão.** O `mart_dividend_yield` cruza
  duas fatos (cotações × dividendos). Não se faz join direto fato-fato;
  o caminho correto é via a dimensão conformada (`dim_tempo` /
  `empresa_id`), que garante o grão e evita produto cartesiano.

### Dúvidas

- **Por que o `dividendos_12m` do yfinance diverge das fontes?** O
  yfinance deu R$2,97 contra ~R$3,69 de algumas fontes. Suspeita: JCP
  não totalmente capturado, ou proventos recentes fora da janela de 365
  dias exatos. Investigar a composição de `yf.Ticker().dividends`.

- **Quando migrar o range join para `SUM() OVER (RANGE INTERVAL)`?** O
  `mart_dividend_yield` tem grão diário (7488 linhas) e o self-join por
  intervalo é barato nesse volume. Mas se o dataset crescer muito, o
  range join pode ficar caro — em que ponto vale trocar pela window com
  frame `RANGE INTERVAL`?

- **`arg_max` do DuckDB tem equivalente portável?** Usei `arg_max` para
  pegar o valor de uma coluna no máximo de outra. Em Postgres/BigQuery o
  equivalente é `(ARRAY_AGG(x ORDER BY y DESC))[1]` ou
  `FIRST_VALUE(... ORDER BY ...)` — confirmar antes de citar em
  entrevista que é específico do DuckDB.

- **√252 assume retornos i.i.d.** A anualização por √252 pressupõe
  retornos independentes e identicamente distribuídos. Na prática há
  autocorrelação e volatility clustering. Quão ruim é a aproximação para
  um horizonte de portfólio? (É a convenção de mercado mesmo sabendo da
  imperfeição.)

- **Indicador de "dias para recuperar do drawdown"?** Tempo "debaixo
  d'água" (do pico até reconquistar o pico) seria a evolução natural do
  drawdown. Ficou fora do escopo — vale a pena adicionar?

### Descobertas

- **Dividendos desde 2005, cotações só desde 2021 — assimetria
  vantajosa.** O yfinance retornou 793 proventos de 2005 a 2026, mas as
  cotações cobrem só 2021+. Isso **não** é problema: o
  `mart_dividend_yield` parte das cotações (INNER JOIN), então só calcula
  yield onde há preço. E é uma vantagem acidental: o DY trailing 12m dos
  primeiros pregões de 2021 já tem **janela completa**, porque os
  dividendos de 2020 existem no raw. Sem isso, os primeiros ~12 meses de
  yield seriam subestimados por falta de proventos anteriores.

- **Dividend yield validado contra o mercado.** O DY 12m calculado para
  PETR4 (pregão de 2026-06-11) deu **7,11%**. Fontes de mercado
  (Investidor10 7,67%, stockinvest 7,24%, Investing 6,5–6,9%) confirmam a
  mesma ordem de grandeza. A pequena diferença vem de: (a) data de corte
  do preço no denominador, (b) escopo de proventos — possível diferença
  no tratamento de JCP pelo yfinance vs as fontes, (c) janela de 365 dias
  corridos vs 12 meses-calendário. Lição: validar cálculo financeiro
  contra fonte externa é mais forte que confiar só em testes de
  invariante.

- **`dividendos_12m` do yfinance (R$2,97) menor que algumas fontes
  (R$3,69).** Diferença a investigar: provável que o yfinance não capture
  todo o JCP, ou que proventos muito recentes não tenham entrado na
  janela de 365 dias exatos. Registrado como diferença conhecida, não
  bug.

- **Volatilidade reage a choques na janela.** A volatilidade anualizada
  de 30d da PETR4 saltou de ~35% para ~47% exatamente quando um retorno
  diário de -10,5% (03/06/2026) entrou na janela de 30 pregões. Confirma
  que a janela móvel captura eventos como esperado.

- **Window nomeada com frame estendido funciona no DuckDB 1.10.1.** A
  sintaxe `WINDOW w AS (PARTITION BY ... ORDER BY ...)` com
  `OVER (w ROWS BETWEEN N PRECEDING AND CURRENT ROW)` nos modelos
  compilou e rodou sem erro. Era o ponto de maior risco de sintaxe da
  etapa.

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
