# Decisões técnicas

Registro das decisões de arquitetura e escopo deste projeto. Cada entrada documenta o **contexto** (situação no momento da decisão), a **decisão** em si, o **racional** (por que essa e não outra) e o **trade-off aceito** (o que se abre mão).

A intenção não é provar que cada escolha é a "melhor possível" — é deixar claro **que escolhas foram feitas conscientemente**, com qual motivação, e qual o custo. Esse é o tipo de conversa que aparece em entrevista.

---

## 2026-05-18 — Ambiente local em vez de cloud

**Contexto.** O projeto pode rodar inteiro em cloud (GCP, AWS) ou inteiro local. Cloud daria experiência com IAM, billing, serviços gerenciados; local elimina custo e fricção de setup.

**Decisão.** Rodar todo o pipeline **localmente**, usando MinIO como substituto para S3 e DuckDB no lugar de um data warehouse gerenciado.

**Racional.**
- **Custo zero.** Não há billing nem risco de "esqueci uma instância ligada".
- **Iteração rápida.** Sem latência de deploy, sem espera por provisionamento, sem console web no caminho.
- **MinIO é S3-compatível.** A camada de ingestão usa a mesma SDK (`boto3` / `s3fs`) que usaria contra S3 real. Migrar para AWS depois é trocar credenciais e endpoint.
- **Portabilidade.** Qualquer pessoa clona o repo e roda — não depende de conta na cloud.

**Trade-off aceito.** Não exercito **IAM real** (políticas, roles, federated access), nem billing, nem serviços específicos de cloud (Glue, Athena, Lambda). Se a vaga alvo pedir muito disso, o projeto não cobre — mas isso pode ser endereçado em um projeto seguinte.

---

## 2026-05-18 — 6 tickers em vez do Ibovespa inteiro

**Contexto.** Poderia carregar todos os ~80 tickers do Ibovespa, ou um subconjunto pequeno e representativo. A diferença é volume de dados e abrangência setorial.

**Decisão.** Trabalhar com **6 tickers**: PETR4, VALE3, ITUB4, BBDC4, WEGE3, ABEV3.

**Racional.**
- **Cobertura setorial.** Petróleo (PETR4), Mineração (VALE3), Financeiro (ITUB4, BBDC4), Bens Industriais (WEGE3), Consumo Não-Cíclico (ABEV3). Quatro setores distintos é suficiente para análise setorial básica.
- **Iteração rápida.** Volume pequeno faz cada teste de pipeline rodar em segundos, não minutos. Menos atrito = mais experimentação.
- **Escalar é trivial.** A lista de tickers é parâmetro, não constante. Trocar 6 por 80 é mudar uma lista — a arquitetura não muda.

**Trade-off aceito.** O número absoluto **soa menos impressivo** em apresentação ("6 tickers" vs. "Ibovespa inteiro"). Compenso com profundidade na modelagem e qualidade da análise, não com volume.

---

## 2026-05-18 — DuckDB em vez de BigQuery

**Contexto.** A camada analítica pode ser um data warehouse gerenciado (BigQuery, Snowflake, Redshift) ou um engine embutido que lê arquivos locais (DuckDB).

**Decisão.** Usar **DuckDB** como warehouse analítico.

**Racional.**
- **Roda local.** Sem provisionamento, sem credenciais, sem custo por query.
- **SQL padrão (ANSI).** O dialeto é próximo do PostgreSQL e do BigQuery — a sintaxe que aprendo aqui transfere.
- **Lê Parquet nativamente.** `SELECT * FROM 'data/raw/**/*.parquet'` funciona sem ETL intermediário. Isso muda como penso a arquitetura — o raw layer já é consultável.
- **Zero fricção.** `pip install duckdb` e está pronto. Comparar com setup de qualquer warehouse gerenciado.
- **Adapter dbt maduro.** `dbt-duckdb` é estável e tem boa documentação.

**Trade-off aceito.** Não exercito **BigQuery** (ou Snowflake), que aparecem em descrição de vaga. Mitigação: como o SQL é padrão e o dbt abstrai o adapter, portar para BigQuery depois é trocar `profiles.yml` — não reescrever modelos.

---

## 2026-05-18 — Etapa 1 — Preservar preço bruto e ajustado no raw

**Contexto.** O `yfinance` pode entregar o preço já ajustado por proventos (com `auto_adjust=True`, o `Close` vira o ajustado e o `Adj Close` some) ou ambos lado a lado (com `auto_adjust=False`: `Close` bruto + `Adj Close` ajustado). Guardar apenas um dos dois reduz o volume e simplifica o downstream, mas torna o raw layer uma **transformação**, não um espelho da fonte.

**Decisão.** Baixar com `auto_adjust=False` e gravar **ambas** as colunas no Parquet: `fechamento` (bruto) e `fechamento_ajustado` (ajustado).

**Racional.**
- **Imutabilidade do raw.** O raw layer existe para ser o "snapshot" do que a fonte entregou. Reescrevê-lo sob uma definição de ajuste compromete essa propriedade.
- **Reversibilidade.** Se a definição de retorno mudar (ajustado por dividendos vs. apenas por splits, base diferente), a transformação acontece no dbt sem nova ingestão.
- **Auditoria.** É possível recalcular o fator de ajuste (`Adj Close / Close`) para inspeção e validação contra fontes alternativas.

**Trade-off aceito.** Cada linha carrega ~8 bytes extras (um `float64` a mais). Em 6 tickers × ~1250 pregões/ano × 5 anos é desprezível; em datasets maiores o custo aumentaria, mas não a ponto de justificar perder a propriedade.

---

## 2026-05-18 — Etapa 1 — Um arquivo Parquet por data, todos os tickers juntos

**Contexto.** O dado vem com granularidade `ticker × data`. As opções razoáveis de particionamento físico são: (a) um arquivo por data com todos os tickers; (b) um arquivo por ticker com todas as datas; (c) particionamento composto por `ano/mes/ticker` ou similar.

**Decisão.** Particionar **somente por data** (`ano=YYYY/mes=MM/dia=DD/cotacoes.parquet`), com todos os tickers daquele dia em um único arquivo.

**Racional.**
- **Padrão de leitura.** A consulta natural é "todos os tickers em uma janela temporal". Particionar por data permite **partition pruning** direto no caminho.
- **Evita o anti-padrão de micro-arquivos.** Particionar por ticker geraria 6 arquivos minúsculos por dia (~1KB cada) — péssimo para sistemas distribuídos e mesmo para `pyarrow` local. Parquet rende quando o arquivo tem volume suficiente para amortizar o overhead de schema, metadados e dicionários.
- **Crescimento previsível.** O número de arquivos cresce linearmente com o número de pregões, não com tickers. Escalar de 6 para 80 tickers não muda a quantidade de arquivos.

**Trade-off aceito.** Consultas que filtram por **um único ticker** precisam ler todos os arquivos do período e descartar 5/6 das linhas. Para o nosso volume (~7.500 linhas/ano com 6 tickers), o custo é trivial. Em escala maior, o caminho seria adicionar particionamento composto (`ticker=` como segundo nível) — não reverter a decisão.

---

## 2026-05-18 — Etapa 1 — Idempotência semântica por sobrescrita

**Contexto.** Ao reexecutar a ingestão para uma data já baixada, qual deve ser o comportamento: sobrescrever, pular, ou versionar?

**Decisão.** Sobrescrever o arquivo Parquet da data. A idempotência garantida é **semântica**, não byte-a-byte.

**Definição da garantia.** Para qualquer data D, reexecutar a ingestão para D produz um arquivo Parquet cujo *conteúdo lógico* (linhas, colunas, valores) é idêntico ao da execução anterior. Os bytes do arquivo no disco podem variar entre execuções por razões legítimas do formato Parquet:
- Metadata embutida pelo PyArrow com timestamp de escrita
- Ordem das linhas (o yfinance pode retornar tickers em ordem variável)
- Estatísticas de row group (min/max por coluna)

Nenhuma dessas variações afeta camadas downstream (DuckDB, dbt, dashboard), porque todas elas consomem o *conteúdo* do Parquet, não os bytes.

**Validação empírica realizada em 2026-05-18.** Executado `--modo range --inicio 2026-05-15 --fim 2026-05-15` duas vezes seguidas. Comparado o DataFrame resultante em ambas as execuções (ordenado por ticker): linhas, colunas, tipos e valores idênticos. Hash MD5 do arquivo .parquet variou — esperado e aceitável.

**Racional.**
- **Padrão da indústria.** Airflow, dbt, Spark e Kafka definem idempotência em termos semânticos. Garantir byte-a-byte exigiria ordenar o DataFrame antes de salvar, desabilitar estatísticas e fixar metadata — custo desproporcional ao benefício.
- **Auditoria semântica é o que importa.** Para reconstruir o estado do warehouse a partir do raw layer, basta que o conteúdo seja reproduzível. A camada downstream (dbt) é determinística em cima de dado lógico.
- **Sobrescrita simplifica retroatividade.** Se a fonte (yfinance) corrigir um valor histórico, basta reexecutar a data; a versão nova vence. Sem necessidade de migração ou limpeza.

**Trade-off aceito.** Não há rastreabilidade de quando uma data foi re-baixada. Mitigação: se isso virar requisito, futuramente migrar para dbt snapshots no warehouse (Etapa 4+), que dão SCD tipo 2 sem custo no raw layer.

---

## 2026-05-18 — Etapa 1 — Tratamento de volume NaN: Int64 nullable

**Contexto.** O `yfinance` ocasionalmente devolve `NaN` na coluna `Volume` — para tickers em dias específicos onde o feed não trouxe dado de volume, embora preço esteja presente. A versão inicial do `download.py` aplicava `fillna(0).astype("int64")` para forçar tipo inteiro nativo do numpy, o que tinha o efeito colateral de **transformar "desconhecido" em "zero negócios"** — duas semânticas distintas colapsadas em um valor.

**Decisão.** Usar o tipo nullable do pandas (`"Int64"` com I maiúsculo) na coluna `volume`, **preservando NaN** quando o yfinance não traz o valor.

**Racional.**
- **Imutabilidade semântica do raw.** O raw layer deve refletir a fonte. `NaN` = "a fonte não tem ou não nos contou esse valor"; `0` = "houve pregão e ninguém negociou". São fatos diferentes e não devem ser confundidos no nível mais bruto.
- **Decisão de tratamento sobe para staging.** Se a regra de negócio futura for "imputar volume desconhecido como 0", ou "descartar a linha", ou "interpolar", essa decisão pertence ao dbt na Etapa 4 — onde fica auditável e mudável sem re-baixar dado.
- **Parquet preserva nullability.** PyArrow grava `Int64` do pandas como inteiro com bitmap de validade, sem precisar de mágica adicional.

**Trade-off aceito.** O tipo `Int64` do pandas exige cuidado em comparações e agregações em Python (`NaN` propaga; `==` não funciona contra `NA`). Aceitável porque a manipulação analítica acontece em **SQL no DuckDB/dbt** a partir da Etapa 3 — e em SQL, `NULL` é tratado naturalmente em agregações (`SUM` ignora, `COUNT(*)` inclui, `COUNT(volume)` não).

---

## 2026-05-18 — Etapa 2 — MinIO em Docker, Compose dedicado na raiz

**Contexto.** O raw layer precisa migrar de filesystem local para object storage. Opções: (a) usar bucket S3 real (custo + IAM); (b) rodar MinIO via binário nativo; (c) MinIO em Docker Compose. Outra dimensão: onde mora o arquivo Compose — em uma pasta `infra/`, dentro de `ingestion/`, ou na raiz do repositório.

**Decisão.** MinIO em **Docker Compose dedicado** (`docker-compose.minio.yml`), arquivo na **raiz do repositório**. Um único serviço `minio` + um auxiliar `mc-init` que cria o bucket na primeira subida.

**Racional.**
- **Portabilidade.** Qualquer máquina com Docker roda. Zero instalação nativa, zero conflito de versão.
- **Preparação para Airflow.** A Etapa 5 vai estender o mesmo arquivo Compose adicionando o serviço do Airflow, que precisa estar na mesma network do MinIO para resolver `minio:9000`. Manter o arquivo na raiz e visível agora simplifica o merge depois.
- **`mc-init` automatiza setup.** O usuário não precisa abrir o console web só para criar o bucket — a primeira execução do Compose já deixa tudo pronto.

**Trade-off aceito.** Cria **dependência de Docker** para qualquer pessoa que rode o projeto. Não dá mais para executar a ingestão 100% offline em uma máquina sem Docker. Mitigação: Docker Desktop é padrão de mercado e o setup é uma linha de comando.

---

## 2026-05-18 — Etapa 2 — Bucket único com prefixos por camada

**Contexto.** Em um data lake clássico, há duas formas de separar raw / staging / marts: (a) buckets distintos (`b3-raw`, `b3-staging`, `b3-marts`); (b) bucket único com prefixos (`b3-data/raw/...`, `b3-data/staging/...`).

**Decisão.** **Bucket único** chamado `b3-data`, com prefixos internos por camada. O raw layer ocupa `b3-data/raw/cotacoes/...`; staging e marts ocuparão `b3-data/staging/...` e `b3-data/marts/...` na Etapa 4.

**Racional.**
- **Simplicidade.** Um bucket, um conjunto de credenciais, uma configuração no `.env`. Operacionalmente menos coisa para errar.
- **Padrão comum em lakes pequenos a médios.** Buckets separados fazem sentido quando permissões IAM precisam ser granulares por camada (ex.: dbt só pode ler raw, não escrever; analista só pode ler marts). Em um projeto pessoal local, esse benefício não se materializa.
- **Layout previsível para downstream.** DuckDB e dbt receberão o prefixo como parâmetro de configuração; trocar `raw/` por `staging/` é mudar um caminho, não uma credencial.

**Trade-off aceito.** Se permissões granulares por camada virarem requisito (ex.: deploy em produção real com múltiplos consumidores), será preciso **refatorar para múltiplos buckets** — mudança simples no IaC, mas mudança. Aceitável porque o projeto não tem esse requisito agora e o custo da refatoração futura é baixo.

---

## 2026-05-18 — Etapa 2 — Trocar storage local por S3 direto, sem abstração

**Contexto.** Na Etapa 1 o `storage.py` escrevia em filesystem (`Path`). Ao migrar para MinIO, há duas escolas: (a) criar uma camada de abstração (`StorageBackend` com implementações `LocalStorage` e `S3Storage`, escolhida por configuração ou flag CLI); (b) trocar direto — raw layer mora em S3 e ponto.

**Decisão.** **Trocar direto.** O `storage.py` passa a escrever exclusivamente no MinIO via boto3. Não há flag para alternar backend, não há classe `StorageBackend`, não há fallback para local.

**Racional.**
- **YAGNI.** A abstração só vale se houver um segundo backend real. "Talvez eu queira voltar para filesystem" não é um segundo backend — é incerteza disfarçada de flexibilidade.
- **Direção do projeto é clara.** O pipeline real (Etapas 3 a 7) vai operar contra MinIO. Manter um caminho local "para emergência" é manter código morto.
- **Erro fica explícito.** Se o MinIO está fora, a falha aparece no setup (passo de subir o Compose), não em runtime escondido por fallback silencioso.
- **Menos código a manter.** Cada abstração inventada custa testes, documentação e dúvida ("qual o backend default mesmo?"). Não há ganho aqui que justifique o custo.

**Trade-off aceito.** Perde-se a capacidade de **rodar a ingestão 100% offline** — o Docker precisa estar funcionando. Aceitável porque object storage é peça central das etapas seguintes; rodar sem ele já não testaria o caminho real.

---

## 2026-05-19 — Etapa 3 — DuckDB persistente em arquivo na raiz

**Contexto.** O DuckDB pode operar em dois modos: (a) **in-memory**, abrindo conexão nova a cada execução, configurando S3, consultando os Parquet remotos e fechando — o "warehouse" é apenas o engine, sem estado próprio; (b) **persistente em arquivo** (`*.duckdb` no disco), em que schemas, views e tabelas sobrevivem entre sessões. Há também a decisão de onde mora esse arquivo: pasta de dados, pasta dedicada, ou na raiz do repo.

**Decisão.** Usar **arquivo persistente** `warehouse.duckdb` na **raiz do repositório**. Gitignored.

**Racional.**
- **Warehouse de verdade tem estado.** A view `raw.cotacoes` criada nesta etapa precisa estar disponível para o dbt na Etapa 4 sem ter que ser recriada toda vez. Modo in-memory forçaria todo consumidor (notebook, IDE, dbt) a refazer setup — repetição que aumenta a chance de divergência.
- **Mesmo arquivo será usado pelo dbt na Etapa 4.** O `profiles.yml` do dbt-duckdb aponta para um arquivo específico; manter o caminho previsível (`./warehouse.duckdb`) simplifica a configuração.
- **Arquivo na raiz é o padrão dos exemplos da comunidade.** O `dbt-duckdb` e tutoriais oficiais assumem caminho relativo curto. Esconder em uma subpasta criaria fricção sem benefício.

**Trade-off aceito.** O `.duckdb` **não é versionado** (regenerável a partir do MinIO + scripts). Quem clona o repo precisa rodar `python -m warehouse.setup` para ter a view disponível. Aceito porque o arquivo contém estado local e cresce com o uso — versioná-lo poluiria o diff e expor dados que devem ser regenerados.

---

## 2026-05-19 — Etapa 3 — Schema `raw` como view, não tabela materializada

**Contexto.** Ao expor o raw layer no DuckDB, há duas formas: (a) `CREATE VIEW raw.cotacoes AS SELECT * FROM read_parquet('s3://.../*.parquet', hive_partitioning=true)` — a cada query, o DuckDB relê do MinIO; (b) `CREATE TABLE raw.cotacoes AS SELECT * FROM read_parquet(...)` — copia o conteúdo dos Parquet para dentro do `.duckdb` uma vez; consultas subsequentes são puramente locais.

**Decisão.** **View**. O schema `raw` é uma janela lógica sobre o MinIO, não uma cópia.

**Racional.**
- **Preservar a imutabilidade do raw no object storage.** O raw "verdadeiro" é o conjunto de objetos Parquet no MinIO. Materializar dentro do `.duckdb` cria uma segunda cópia que pode divergir — se a ingestão grava uma nova partição, a tabela materializada não vê até ser refeita.
- **Releitura automática.** Ingestão grava `ano=2026/mes=06/dia=02/cotacoes.parquet`; próxima query no DuckDB já enxerga. Sem job de refresh, sem `INSERT INTO`.
- **`hive_partitioning = true` resolve o resto.** O DuckDB expõe `ano`, `mes`, `dia` como colunas virtuais derivadas do path. Filtros temporais habilitam partition pruning, então a "view leve" não é cara mesmo lendo do MinIO.

**Trade-off aceito.** Queries leem do MinIO toda vez (latência de rede HTTP). O DuckDB tem cache interno por sessão, mas notebooks de cold-start pagam o custo. Aceitável porque (a) MinIO é local, latência é desprezível; (b) o volume atual (~7.500 linhas) é minúsculo. Se o volume escalasse para milhões de linhas, valeria materializar tabelas analíticas — mas isso já é o trabalho do dbt na Etapa 4, sob os schemas `staging`/`marts`.

---

## 2026-05-19 — Etapa 3 — SQL exploratório em arquivos `.sql` versionados

**Contexto.** Em exploração analítica via notebook há duas escolas: (a) **SQL inline na célula** — cada bloco de análise tem o SELECT dentro de uma f-string Python; (b) **SQL externo em arquivos** — cada query mora num `.sql` separado em `sql/exploratoria/`; o notebook só lê e executa.

**Decisão.** **Arquivos `.sql` separados**. O notebook lê via `Path(...).read_text()` e nunca duplica SQL no código Python.

**Racional.**
- **SQL é cidadão de primeira classe.** Em vaga de engenharia de dados, recrutador olha SQL; queries pareadas com schema visível no repo são prova concreta de habilidade. Esconder dentro de string literal Python esconde a evidência.
- **Reutilização.** O mesmo `.sql` pode ser aberto em DBeaver, executado em pipeline de QA, copiado para PR de troubleshooting. SQL em célula de notebook só vive ali.
- **Diff legível.** Mudar uma window function vira diff de uma linha no arquivo, não uma alteração dentro de um blob multi-linha de string Python.

**Trade-off aceito.** Precisa **manter consistência entre notebook e arquivos** — se uma query mudar, mudar no `.sql` e relembrar de não copiar para a célula. Aceito mediante convenção dura: notebook **só lê** SQL, nunca declara inline.

---

## 2026-05-19 — Etapa 3 — Notebook + arquivos `.sql` em vez de só script ou só notebook

**Contexto.** A exploração da Etapa 3 podia virar (a) um script Python puro que roda as queries e gera relatórios em CSV/HTML; (b) um notebook auto-contido com SQL inline; (c) a combinação adotada aqui (notebook narrativo orquestrando `.sql` versionados).

**Decisão.** **Notebook como vitrine narrativa + arquivos `.sql` como código de verdade**. O notebook é publicável no GitHub e tem markdown contínuo; os `.sql` são reaproveitáveis e versionados separadamente.

**Racional.**
- **Notebook publicado no GitHub é portfólio.** Recrutador vê o `.ipynb` direto no navegador — markdown + gráfico Plotly contam mais que um script que precisa ser executado para fazer sentido.
- **Arquivos `.sql` são código real.** Não dependem do notebook para serem úteis. Podem ser executados em qualquer IDE, automatizados em CI, ou virar fonte de modelos dbt na Etapa 4.
- **Separação de responsabilidades clara.** SQL responde "o que perguntar"; notebook responde "como apresentar".

**Trade-off aceito.** Dois lugares para manter (notebook + arquivos). Aceitável porque cada um tem propósito distinto e a duplicação é zero (notebook lê o arquivo, não copia o conteúdo).

---

## 2026-05-18 — Etapa 2 — boto3 direto em vez de s3fs ou pyarrow.fs

**Contexto.** Para escrever em S3 a partir de pandas, há três caminhos: (a) `boto3` direto, com Parquet em buffer de memória (`io.BytesIO`) e `put_object`; (b) `s3fs`, que expõe S3 como filesystem virtual e permite `df.to_parquet("s3://bucket/key.parquet")`; (c) `pyarrow.fs.S3FileSystem`, integrado ao PyArrow.

**Decisão.** Usar **`boto3` direto**. Escrever o DataFrame em `io.BytesIO` com `df.to_parquet(buffer, engine="pyarrow")`, depois `s3.put_object(Body=buffer.getvalue())`.

**Racional.**
- **Cliente oficial AWS.** É o que aparece em descrição de vaga de engenharia de dados. Saber configurar `endpoint_url`, `signature_version='s3v4'`, `region_name` é exatamente o tipo de detalhe que cai em entrevista.
- **MinIO é S3-compatível por construção.** O mesmo código que aponta para `http://localhost:9000` aponta para `https://s3.amazonaws.com` com nada mais que troca de endpoint e credencial — esse é o sentido de "compatível".
- **Sem mágica.** `s3fs` esconde paginação, retries, multipart upload, autenticação, addressing style. Tudo ótimo em produção; tudo problema quando algo falha e você não sabe onde olhar. Para um projeto cujo objetivo é **entender a stack**, ver os parâmetros explícitos é o ponto.

**Trade-off aceito.** O código é **mais verboso** que `df.to_parquet("s3://...")` em uma linha. Aceito porque o código verboso explicita o que está acontecendo no protocolo S3 (signature v4, path-style addressing, content body) — exatamente o conhecimento que o projeto quer construir.
