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

---

## 2026-05-25 — Etapa 4 — Esquema estrela Kimball (fato + 2 dimensões)

**Contexto.** O modelo analítico final pode ser estrutural de três formas principais: (a) **One Big Table** — uma tabela única achatada com tudo desnormalizado (`cotacao_completa` com ticker, nome, setor, ano, mês etc. repetidos em cada linha); (b) **esquema estrela** clássico — uma fato no centro e dimensões em torno; (c) **esquema floco** — dimensões normalizadas em múltiplos níveis (`dim_setor` separada de `dim_empresa`). O dataset é pequeno (~7.500 linhas), então performance não é o critério.

**Decisão.** **Esquema estrela** com três tabelas finais no schema `marts`: `fato_cotacoes_diarias` (medidas), `dim_empresa` (atributos da empresa), `dim_tempo` (atributos da data).

**Racional.**
- **Padrão Kimball é o vocabulário da indústria.** "Fato e dimensão" é o jargão que cai em entrevista para vaga de engenharia de dados. Modelar dessa forma força a conversa explícita sobre granularidade, surrogate vs natural key, SCD — exatamente o que se quer demonstrar.
- **OBT mistura concerns.** Em uma tabela achatada, atualizar o setor de uma empresa exige `UPDATE` em todas as linhas históricas dela. Em estrela, atualizar `dim_empresa.setor` propaga via JOIN.
- **Floco é overkill aqui.** Separar `dim_setor` de `dim_empresa` faria sentido se setor mudasse com frequência ou tivesse atributos próprios. Aqui é metadado estável; estrela é o tamanho certo.

**Trade-off aceito.** Consultas analíticas exigem JOIN entre fato e dims. Em DuckDB com volume pequeno isso é trivial; em escala maior pode justificar materializações desnormalizadas adicionais para BI. Não é o nosso caso agora.

---

## 2026-05-25 — Etapa 4 — Surrogate keys nas dimensões

**Contexto.** Cada dimensão pode usar a natural key (ticker, data) como chave primária, ou ter um **surrogate key** próprio (INTEGER ou hash) com a natural key preservada como atributo. A fato então referencia pelo surrogate.

**Decisão.** **Surrogate key** em ambas as dimensões:
- `dim_empresa.empresa_id` (INTEGER, via `ROW_NUMBER() OVER (ORDER BY ticker)`).
- `dim_tempo.tempo_id` (INTEGER no formato `YYYYMMDD`, ex.: `20260525`).

Natural keys (`ticker`, `data`) **preservadas** nas dimensões como atributos.

**Racional.**
- **Independência da fato vs natural key.** Se a B3 mudar o código de um ticker (ex.: incorporação, fusão), a fato continua referenciando o `empresa_id` antigo sem precisar de UPDATE em massa. A dim atualiza o `ticker` e a história permanece.
- **Tipos compactos e JOINs eficientes.** INTEGER < VARCHAR para storage e index. Pouco relevante no nosso volume, mas é a convenção padrão.
- **`tempo_id` legível.** Formato `YYYYMMDD` é eyeball-friendly (`20260525` lê como "25 de maio de 2026"), preserva ordem cronológica numericamente e é estável independente de `ROW_NUMBER`.

**Trade-off aceito.** JOINs extras toda vez que se quer ler ticker ou data via fato — em vez de ler diretamente da fato. Vale o custo pela disciplina de manter modelo desacoplado.

---

## 2026-05-25 — Etapa 4 — SCD tipo 1 em dim_empresa (sem histórico)

**Contexto.** SCD (Slowly Changing Dimension) define como mudanças em atributos da dimensão são tratadas: **tipo 1** sobrescreve (perde histórico), **tipo 2** versiona com `valid_from`/`valid_to` (preserva histórico), **tipo 3** mantém colunas "current" e "previous" lado a lado. O atributo mais mutável em `dim_empresa` é `setor`/`segmento` (reclassificação da B3, raríssima na prática).

**Decisão.** **SCD tipo 1** em `dim_empresa`: rodar `dbt build` reconstrói a tabela do seed, sobrescrevendo qualquer alteração. Sem snapshots, sem `valid_from`.

**Racional.**
- **Reconsideração consciente.** Inicialmente cogitou-se SCD tipo 2 — soa mais sofisticado em entrevista. Recuou após perceber que **não há mudança real para versionar** no nosso dataset: classificação setorial da B3 não muda nos 5 anos do histórico. Implementar SCD 2 exigiria simular mudança no seed, o que seria teatro, não dado.
- **Snapshot do dbt resolve quando precisar.** Se um dia tickers começarem a migrar de setor com frequência (ou se adicionarmos uma dim mais volátil), basta criar `snapshots/dim_empresa_snapshot.sql` — o snapshot é a forma idiomática do dbt para SCD 2, não há razão para inventar manualmente.
- **Granularidade do seed.** O CSV `empresas.csv` é a fonte da verdade da dimensão; SCD 1 = "a dim espelha o seed", sem fingir uma temporalidade que ela não tem.

**Trade-off aceito.** Mudar `setor` de um ticker e rodar `dbt build` reescreve o histórico relacional (todas as cotações daquele ticker passam a "ter sempre sido" do novo setor). Se essa for uma necessidade real, migrar para SCD 2 via snapshot. Hoje não é.

---

## 2026-05-25 — Etapa 4 — Materialização: view em staging, table em marts

**Contexto.** O dbt suporta quatro materializações principais: `view` (re-executa a cada consulta), `table` (full refresh a cada `dbt run`), `incremental` (apenda registros novos), `ephemeral` (inlineada como CTE em consumidores). Cada camada tem padrão diferente.

**Decisão.** `stg_cotacoes` como **view**; `dim_empresa`, `dim_tempo` e `fato_cotacoes_diarias` como **table**. Sem `incremental` nesta etapa.

**Racional.**
- **Staging como view: freshness automática.** A view re-lê o raw a cada consulta. Quando a ingestão grava uma nova partição no MinIO, a próxima query em `stg_cotacoes` já enxerga — sem `dbt run` adicional. Custo de re-execução é desprezível dado o volume.
- **Marts como table: performance previsível.** Consultas analíticas (notebook, dashboard futuro) batem nas tabelas materializadas — sem pagar o custo de re-ler MinIO + filtrar + JOIN a cada acesso. Trade-off direto: staging prioriza freshness, marts priorizam latência.
- **Incremental fora do escopo.** `incremental` faz sentido quando full refresh é caro (centenas de GB, modelo com janela móvel, custo de warehouse por TB). Nada disso se aplica a 7.500 linhas em DuckDB local. Adicioná-lo agora seria over-engineering — e esconderia a oportunidade de exercitar `incremental` de forma genuína em uma etapa futura.

**Trade-off aceito.** Cada `dbt run` reescreve as 3 tabelas de marts (full refresh). Em DuckDB com volume atual: questão de segundos. Quando deixar de ser, migrar fato para `incremental` com `unique_key=(empresa_id, tempo_id)`.

---

## 2026-05-25 — Etapa 4 — Suite de testes: nativos + 3 custom

**Contexto.** A "qualidade de dado" pode ser garantida em três níveis: (a) só testes nativos do dbt (`not_null`, `unique`, `relationships`, `accepted_values`); (b) só custom SQL tests em `tests/`; (c) combinação. dbt_utils adiciona uma quarta camada com testes genéricos parametrizados (ex.: `unique_combination_of_columns`).

**Decisão.** **Combinação dos três**:
- **Nativos** em `schema.yml`: not_null nas chaves e métricas críticas, unique nas surrogate/natural keys, accepted_values no ticker, relationships fato → dim.
- **dbt_utils**: `unique_combination_of_columns` para chave composta `(empresa_id, tempo_id)` na fato e `(ticker, data)` no staging.
- **Custom em `tests/`**: três SQL que codificam **regras de negócio**:
  - `fato_volume_nao_negativo` — volume < 0 é impossível (NULL é OK).
  - `fato_maxima_maior_igual_minima` — sanidade de OHLC.
  - `fato_fechamento_dentro_do_range` — fechamento entre [minima, maxima].

**Racional.**
- **Cada teste pega uma classe de bug diferente.** `not_null` pega bug de ingestão (campo faltando); `relationships` pega bug de modelagem (FK órfã); custom tests pegam bug de fonte (volume invertido, valores corrompidos). Sem os três níveis, um bug típico passaria silenciosamente.
- **Documentação executável.** Os testes em `schema.yml` viram parte da doc do `dbt docs` — quem lê o esquema vê não só os campos, mas também as garantias.
- **`dbt build` falha rápido.** A combinação garante que `dbt build` retorne erro **na primeira incompatibilidade**, antes que dashboards futuros consumam dado corrompido.

**Trade-off aceito.** Tempo de `dbt build` cresce com a suite — mas testes em DuckDB com este volume rodam em segundos. Quando deixar de ser, separar testes "críticos" (executados em CI a cada PR) de testes "exaustivos" (executados em schedule noturno) via tags do dbt.

---

## 2026-05-25 — Etapa 4 — dim_tempo gera calendário completo, não derivada da fato

**Contexto.** A dimensão de tempo pode ser construída de duas formas: (a) **derivada da fato** — `SELECT DISTINCT data FROM fato`, garantindo que toda data em dim existe em fato; (b) **calendário completo gerado** — `GENERATE_SERIES` cobrindo todo o range temporal de interesse, incluindo finais de semana, feriados e datas onde não houve pregão.

**Decisão.** **Calendário completo gerado** com `GENERATE_SERIES(DATE '2020-01-01', DATE '2030-12-31', INTERVAL 1 DAY)`. Cobre 5 anos de histórico real + projeção razoável de 5 anos.

**Racional.**
- **Padrão Kimball.** dim_tempo é a única dimensão tradicionalmente populada por geração, não por extração. Razão: relatórios temporais (média mensal, dias úteis no trimestre, comparativo YoY) precisam de **continuidade temporal** mesmo quando não há fato — uma série com gaps "mês sem dado" é diferente de "mês com dado zerado".
- **Independência aumenta reutilização.** Outras fatos futuras (eventos corporativos, indicadores macro, dados de proventos) compartilham a mesma dim_tempo sem precisar re-gerar.
- **Range folgado é barato.** ~4.000 linhas para cobrir 11 anos é nada — não justifica restringir.

**Trade-off aceito.** `dim_tempo` contém datas sem fato correspondente. INNER JOIN entre fato e dim_tempo descarta essas datas — comportamento esperado quando se quer apenas "datas com pregão". Para relatórios calendário-orientados (ex.: dia da semana com mais pregões em N anos), o LEFT JOIN inverso é o caminho.

---

## 2026-05-25 — Etapa 4 — profiles.yml versionado no repo (não em ~/.dbt/)

**Contexto.** O dbt procura `profiles.yml` em `~/.dbt/profiles.yml` por default. Versionar no repo é não-convencional; o padrão da comunidade é manter o profile fora do código (separar credenciais de configuração).

**Decisão.** Manter `profiles.yml` em `dbt/profiles.yml` (dentro do repo). Comandos rodam com `--profiles-dir ./`.

**Racional.**
- **Reprodutibilidade do portfólio.** Quem clona o repo precisa ter o pipeline funcionando com `pip install -r requirements.txt` + `cp .env.example .env` + comandos do README. Adicionar uma etapa "crie `~/.dbt/profiles.yml` copiando o template" é fricção que pesa em projeto público.
- **Não há credencial no arquivo.** O `profiles.yml` consome credenciais via `env_var()`. O arquivo versionado descreve **a forma da conexão** (tipo DuckDB, caminho do arquivo, extensões), não os segredos. Os segredos seguem em `.env` (gitignored).
- **Pattern legítimo em projetos dbt embarcados em monorepo.** Squads que rodam dbt como módulo de um repo maior costumam versionar `profiles.yml` por exatamente esse motivo.

**Trade-off aceito.** Todo comando precisa de `--profiles-dir ./` ou `DBT_PROFILES_DIR=./`. Documentado no `dbt/README.md` e na seção de comandos do README raiz. Em CI ou produção real, o `profiles.yml` viraria template + injeção de secrets via vault — não muda a estrutura, só a origem das variáveis.

---

## 2026-05-25 — Etapa 4 — Sobrescrita de generate_schema_name para schemas limpos no DuckDB

**Contexto.** Por default, dbt concatena `target.schema` com o `+schema` custom de cada model. No DuckDB, `target.schema = main`, então `+schema: staging` materializa em `main_staging`. Isso polui o namespace e fica estranho ao consultar (`SELECT * FROM main_marts.fato_cotacoes_diarias`).

**Decisão.** Sobrescrever a macro `generate_schema_name` (em `dbt/macros/generate_schema_name.sql`) para usar o custom schema diretamente quando declarado, ignorando o `target.schema`. Sem mudar `dbt_project.yml` — os `+schema: staging`, `+schema: marts`, `+schema: seed` continuam como estão; só a interpretação muda.

**Racional.** Comportamento mais legível e alinhado com convenções de data warehouse profissional (Snowflake/BigQuery não tem esse problema — o "comportamento estranho" é específico do DuckDB ter um schema default obrigatório chamado `main`). Macro é a forma idiomática que o próprio dbt oferece para personalizar essa resolução — não é hack.

**Trade-off aceito.** Em ambiente de desenvolvimento compartilhado (múltiplos devs no mesmo banco), o default do dbt serve como isolamento natural (`alice_marts`, `bob_marts`). Em projeto single-developer local, esse isolamento não tem valor. Quando/se migrar para ambiente compartilhado, reverter a macro.

---

## 2026-06-03 — Etapa 5 — Airflow no mesmo Compose do MinIO (renomeado para docker-compose.yml)

**Contexto.** A Etapa 5 introduz Airflow. Há duas formas de organizar a infra: (a) um segundo arquivo Compose dedicado (`docker-compose.airflow.yml`), subido em paralelo ao do MinIO via flag `--profile` ou `-f`; (b) um único `docker-compose.yml` na raiz contendo MinIO + Airflow, carregado por padrão sem `-f`.

**Decisão.** **Compose único.** Renomear `docker-compose.minio.yml` → `docker-compose.yml` (`git mv`, preservando histórico) e adicionar serviços `postgres`, `airflow-init`, `airflow-webserver`, `airflow-scheduler` ao mesmo arquivo. A subida vira `docker compose up -d` (sem `-f`).

**Racional.**
- **Mesma rede Docker é requisito funcional.** A DAG precisa resolver `minio:9000` pelo DNS interno do Compose. Arquivos separados criariam redes separadas — exigiria network externa nomeada, mais complexidade que o ganho.
- **Comando canônico.** `docker compose up -d` é o que aparece em tutorial, doc e CI. Esconder a infra atrás de `-f` é fricção sem benefício.
- **A Etapa 2 já previu este momento.** A decisão "Compose dedicado na raiz" registrada em 2026-05-18 explicitamente apontou que Etapa 5 estenderia o mesmo arquivo — não é mudança de plano, é o plano se concretizando.

**Trade-off aceito.** Quem só quer subir o MinIO (ex.: rodar ingestão sem Airflow) passa a subir Postgres + Airflow junto, ou usa `docker compose up -d minio mc-init`. Aceitável: o caso normal é "subir tudo".

---

## 2026-06-03 — Etapa 5 — LocalExecutor em vez de CeleryExecutor

**Contexto.** Airflow oferece quatro executors principais: `SequentialExecutor` (default, single-task, sem paralelismo — apenas para desenvolvimento), `LocalExecutor` (multi-process no mesmo host, paralelismo dentro da máquina), `CeleryExecutor` (workers separados via fila Redis/RabbitMQ, escala horizontal), `KubernetesExecutor` (pod por task).

**Decisão.** **LocalExecutor**. Scheduler e workers no mesmo container, sem Redis, sem worker dedicado.

**Racional.**
- **Single-host por design.** O projeto inteiro roda em uma máquina. Escala horizontal não está no escopo (decisão "ambiente local" da Etapa 0).
- **Volume desprezível.** 4 tasks/dia × poucos minutos cada. CeleryExecutor seria 3 containers extras (worker, Redis, flower) para zero ganho.
- **Curva de aprendizado proporcional.** Configurar Celery + broker para um portfólio é overhead de explicação sem payoff em entrevista — qualquer recrutador entende que "subiria para Celery quando o volume exigir".

**Trade-off aceito.** Quando alguém perguntar "como você escalaria isso?", a resposta é narrativa, não demonstração. Mitigação: documentar a transição no `airflow/README.md` ("limites desta etapa") e estar pronto para discutir em entrevista.

---

## 2026-06-03 — Etapa 5 — Bind mount + BashOperator (não PythonOperator nem DockerOperator)

**Contexto.** A DAG precisa rodar os mesmos comandos que o usuário hoje roda no terminal (`python -m ingestion.main`, `python -m warehouse.setup`, `dbt run/test`). Três opções: (a) **PythonOperator** que importa as funções do projeto e chama direto; (b) **DockerOperator** que dispara um container novo por task com a imagem do projeto; (c) **BashOperator** que executa o comando shell exato, com o projeto bind-montado dentro dos containers do Airflow.

**Decisão.** **Bind mount + BashOperator.** A raiz do projeto (`.`) é montada em `/opt/project` nos 3 serviços do Airflow. Cada task é um `BashOperator` rodando o comando do terminal sem modificação.

**Racional.**
- **Paridade exata com a execução manual.** A DAG faz LITERALMENTE o que o usuário fazia à mão na Etapa 4. Zero divergência entre "como reproduzo localmente" e "como o Airflow faz". Em entrevista, "o operador roda o mesmo comando do README" é defesa cristalina.
- **PythonOperator acopla a DAG ao código.** Mudar a assinatura de uma função em `ingestion/` quebraria a DAG. BashOperator depende só do CLI, que é a interface estável já documentada.
- **DockerOperator exigiria docker-in-docker** (ou docker socket exposto), com uma imagem do projeto separada. Para single-host single-developer, é complexidade sem ganho.
- **Idempotência herdada.** Cada comando já é idempotente (decisões da Etapa 1 e 4). Airflow não precisa adicionar nada.

**Trade-off aceito.** A imagem custom do Airflow precisa instalar TODAS as deps do projeto (yfinance, duckdb, dbt etc.) — imagem maior (~1.5GB), build mais lento. Aceitável porque é build local single-time; alternativa multi-container seria mais código, mais variáveis para alinhar, mais lugares para errar.

---

## 2026-06-03 — Etapa 5 — DAG monolítica de 4 tasks por etapa lógica

**Contexto.** O pipeline tem ingestão, refresh de warehouse e duas fases do dbt (run + test). Granularidades possíveis: (a) **uma única task** rodando um shell script com tudo; (b) **uma task por modelo dbt** (40+ tasks via `dbt-airflow` ou parsing de manifest.json); (c) **uma task por etapa lógica** (4 tasks na DAG).

**Decisão.** **4 tasks**, uma por etapa lógica do pipeline: `extract_cotacoes`, `refresh_warehouse`, `dbt_run`, `dbt_test`.

**Racional.**
- **Retry granular onde importa.** Se o yfinance falhar (rede), só `extract_cotacoes` reexecuta; `dbt_run` que rodou ok não precisa repetir. Se um teste falhar, `dbt_test` reexecuta isolado depois do fix.
- **Visibilidade no grid.** 4 quadradinhos verdes/vermelhos contam a história do dia em um olhar. Uma task única perderia a localização de falha; 40 tasks viraria ruído.
- **dbt run + dbt test separados, não `dbt build`.** Permite ver o que falhou — modelagem ou qualidade de dados — sem inspecionar log. Em incidente real, essa distinção é a diferença entre "rollback do modelo" e "investigar fonte".
- **`dbt_test` como gate de qualidade.** Falha em test bloqueia DAGs futuras (catchup=False, mas próximo run vê o estado anterior). É o comportamento desejado: dado ruim não progride.

**Trade-off aceito.** Não exercitamos **`dbt-airflow`** ou parsing de `manifest.json` para uma task por modelo — padrão em data orgs maduras. Aceitável: nosso DAG tem 4 modelos, expandir agora seria teatro. Quando o projeto crescer e o número de modelos justificar a granularidade, refatorar com `Cosmos` ou similar.

---

## 2026-06-03 — Etapa 5 — Schedule 20h America/Sao_Paulo, catchup=False

**Contexto.** Definir quando a DAG roda e como tratar gaps históricos (datas em que a DAG estava pausada ou inexistente).

**Decisão.** Cron `0 20 * * *` no fuso `America/Sao_Paulo`. `catchup=False`. `start_date` fixo em `2026-01-01` (data passada arbitrária; com catchup off, serve só como referência).

**Racional.**
- **20h Brasília = pós-fechamento + ajustes do dia disponíveis.** Pregão fecha 18h (com after-market até 18h30). 20h dá folga para o provedor (Yahoo/yfinance) calcular o ajustado por proventos do dia. Antes disso, risco de pegar dado parcial.
- **Fuso explícito evita armadilha UTC.** Airflow trata datas internamente em UTC, mas o cron lê do `timezone` da DAG. Sem `tz="America/Sao_Paulo"`, "20h" viraria 17h Brasília (UTC-3) — duas horas antes do fechamento, dado pode não estar pronto.
- **catchup=False alinha com a natureza do dado.** Se a DAG ficou pausada por uma semana, fazer 7 backfills agora não conserta nada — o yfinance entregaria os mesmos valores que já entregaria amanhã. Quando precisar reprocessar histórico, é manual e consciente (CLI: `python -m ingestion.main --modo range --inicio ... --fim ...`).
- **start_date no passado fixo.** Convenção do Airflow para escapar do "start_date dinâmico = comportamento confuso". Com catchup=False, a data não causa retroatividade; só serve para o scheduler saber a primeira janela válida.

**Trade-off aceito.** Não exercitamos backfill orquestrado. Em vaga real, backfill costuma ser feature importante. Mitigação: a CLI `--modo range` cobre o caso; documentar em README como rodar manualmente, e mencionar em entrevista que a escolha é consciente, não desconhecimento.

---

## 2026-06-03 — Etapa 5 — Endpoint MinIO: minio:9000 no container, localhost:9000 no host

**Contexto.** O código (`ingestion/config.py`, `warehouse/conexao.py`, `dbt/profiles.yml`) lê `MINIO_ENDPOINT` (e `MINIO_ENDPOINT_HOST_PORT`) de variável de ambiente. Funciona com `http://localhost:9000` quando executado no host, mas falha dentro de container Compose — `localhost` em um container Docker é o próprio container, não o MinIO. Dentro da rede Compose, o serviço `minio` é resolvido por DNS interno: `http://minio:9000`.

**Decisão.** **Duas fontes diferentes do valor.** `.env` no host mantém `localhost:9000` (uso manual via terminal). No `docker-compose.yml`, bloco `x-airflow-common.environment` sobrescreve **explicitamente** `MINIO_ENDPOINT=http://minio:9000` e `MINIO_ENDPOINT_HOST_PORT=minio:9000` para os 3 serviços do Airflow. `python-dotenv` (`override=False` por default) preserva o valor injetado pelo Compose mesmo quando lê o `.env` bind-mountado.

**Racional.**
- **Sem mexer no código.** As variáveis já são lidas de `os.environ`. Quem injetar o valor certo no ambiente certo resolve o problema.
- **Cada contexto fica com a string que funciona naquele contexto.** Não há "string mágica universal" — `minio:9000` não existe no DNS do host (a menos que o usuário edite `/etc/hosts`), `localhost:9000` não existe no DNS do container. Tentar unificar geraria ginástica desnecessária.
- **`override=False` é exatamente o desired behavior.** Variáveis injetadas pelo orquestrador (Compose) vencem variáveis vindas de arquivo (`.env`). Esse é o padrão em qualquer stack de produção: secrets de vault > config file local.

**Trade-off aceito.** Documentar a diferença em três lugares (`.env.example`, `airflow/README.md`, `docs/decisoes.md`). É a fonte mais comum de "funciona na minha máquina mas falha no container" — o custo do documento é menor que o custo de redescobrir.

---

## 2026-06-11 — Etapa 6 — Escopo: indicadores de mercado + dividend yield, sem fundamentalistas

**Contexto.** A Etapa 6 calcula indicadores financeiros. O leque possível vai de indicadores de **mercado** (retorno, volatilidade, drawdown — derivados só de preço e volume) a **fundamentalistas** (P/L, P/VP, ROE, dividend yield, payout — que exigem dados contábeis: lucro, patrimônio líquido, número de ações). O yfinance entrega preço e proventos de forma confiável, mas dados fundamentalistas de empresas brasileiras vêm incompletos, defasados ou ausentes.

**Decisão.** Escopo da etapa = **indicadores de mercado** (retorno simples/log/acumulado, médias móveis, volatilidade, drawdown) **+ dividend yield** (único "fundamentalista" viável, porque depende só de proventos + preço, ambos confiáveis no yfinance). P/L, P/VP, ROE, payout e afins ficam **fora**.

**Racional.**
- **Confiabilidade da fonte manda no escopo.** Calcular P/L com lucro por ação faltando ou errado produziria um indicador bonito e mentiroso. Melhor não ter do que ter errado.
- **DY é a ponte honesta.** Proventos (`yf.Ticker.dividends`) e preço são exatamente o que o yfinance faz bem. DY entrega o "sabor fundamentalista" sem depender de demonstração contábil.
- **Indicadores de mercado são autossuficientes.** Dependem só da fato de cotações, que já está validada (Etapa 4).

**Trade-off aceito.** O dashboard (Etapa 7) não terá análise fundamentalista clássica. Em entrevista, é uma escolha defensável ("limitação consciente da fonte gratuita; com uma API paga — B3/CVM, Refinitiv — eu adicionaria a camada fundamentalista sem mudar a arquitetura, só a ingestão").

---

## 2026-06-11 — Etapa 6 — Retorno simples E log, lado a lado

**Contexto.** Há duas definições usuais de retorno diário: **simples** (`P_t / P_{t-1} - 1`) e **logarítmico** (`ln(P_t / P_{t-1})`). Poderia guardar só um. Cada um tem um domínio onde é o "certo".

**Decisão.** Calcular e materializar **os dois** em `mart_indicadores_diarios`.

**Racional.**
- **Log é aditivo no tempo.** A soma de retornos log de N dias é o retorno log do período — propriedade que torna o desvio-padrão de retornos log a base correta da **volatilidade** e da anualização por √252. Por isso a volatilidade desta etapa usa `retorno_log`.
- **Simples é intuitivo e compõe entre ativos.** "Subiu 2%" é retorno simples; é o que se reporta e o que se usa para média de carteira num dia.
- **Custo de manter os dois é nulo.** Duas colunas a mais sobre o mesmo `LAG`. Guardar só log forçaria o dashboard a reconverter (`exp(x) - 1`) a cada leitura.

**Trade-off aceito.** Duas colunas semanticamente próximas podem confundir quem não conhece a distinção — mitigado pela descrição explícita em `schema.yml` (log = base de volatilidade; simples = variação reportável).

---

## 2026-06-11 — Etapa 6 — Base de preço: ajustado para retorno/risco, bruto para yield

**Contexto.** A fato de cotações guarda `fechamento` (bruto) e `fechamento_ajustado` (ajustado por proventos e splits) lado a lado (decisão da Etapa 1). Todo indicador da etapa precisa escolher uma base — e a escolha **errada** distorce o número de forma silenciosa.

**Decisão.** Regra que atravessa toda a etapa:
- **Retorno, retorno acumulado, médias móveis, volatilidade, drawdown → fechamento AJUSTADO.**
- **Dividend yield → fechamento BRUTO no denominador.**

**Racional.**
- **Ajustado evita risco fantasma.** Numa data-ex, o preço bruto cai pelo valor do provento. Medir retorno/volatilidade sobre o bruto registraria essa queda como "perda" e "risco" que o investidor (que recebeu o dividendo) não sofreu. O ajustado já incorpora o provento — a série fica contínua.
- **Yield sobre bruto evita contar o dividendo duas vezes.** O ajustado já *desconta* proventos do preço. Usar ajustado no denominador do yield seria dividir o dividendo por um preço que já foi reduzido por causa daquele dividendo — dupla contagem, yield inflado. O yield de mercado é "provento / preço que o mercado pratica" = preço bruto.

**Trade-off aceito.** Exige disciplina: a base certa muda por indicador dentro do mesmo modelo. Mitigado documentando a regra no topo de cada `.sql`, em cada coluna do `schema.yml`, e aqui. É o tipo de detalhe que separa "sei usar window function" de "entendo o dado".

---

## 2026-06-11 — Etapa 6 — Médias móveis 7/30/90/200 com contagem de pregões (janela parcial sinalizada)

**Contexto.** Médias móveis precisam de duas decisões: (a) **quais janelas** (em pregões); (b) **o que fazer no início da série**, quando ainda não há N pregões para preencher a janela. Para (b), as opções são: deixar NULL até completar N (Forma B), ou calcular com o que houver e **sinalizar** quantos pregões entraram (Forma A).

**Decisão.** Janelas de **7, 30, 90 e 200 pregões** (curtíssimo, mensal, trimestral, anual operacional). Início de série: **Forma A** — calcular a média com os pregões disponíveis e expor `pregoes_janela_Nd = COUNT(*)` na mesma janela, que vale N quando a janela está cheia e < N quando é parcial.

**Racional.**
- **7/30/90/200 cobrem horizontes distintos.** 200 pregões ≈ um ano útil de bolsa; é a média móvel "longa" clássica em análise técnica.
- **Forma A não joga dado fora.** Os primeiros 199 pregões teriam média 200d NULL na Forma B. A Forma A entrega um número desde o pregão 1, e a coluna de contagem deixa o consumidor decidir se confia (filtrar `pregoes_janela_200d = 200` se quiser só janela cheia).
- **Contagem é autoexplicativa.** `COUNT(*) OVER (mesma janela)` é barato e elimina a pergunta "essa média de 200 dias tem mesmo 200 dias?".

**Trade-off aceito.** Quem consumir a média sem olhar a contagem pode tratar uma média parcial como cheia. Mitigado pela coluna explícita e pela documentação; a alternativa (NULL) seria mais "segura" mas esconderia informação útil.

---

## 2026-06-11 — Etapa 6 — Volatilidade amostral, anualizada por √252

**Contexto.** Volatilidade = desvio-padrão dos retornos. Três decisões: (a) desvio-padrão **amostral** (`STDDEV_SAMP`, divide por n-1) ou **populacional** (`STDDEV_POP`, divide por n); (b) sobre qual retorno; (c) reportar diária ou **anualizada**.

**Decisão.** **Amostral** (`STDDEV_SAMP`) sobre **retorno log**, janelas de 30/90/252 pregões, exposta nas duas formas: diária e **anualizada por √252** (`σ_anual = σ_diário × √252`).

**Racional.**
- **Amostral é o padrão em finanças.** A série de retornos é uma *amostra* do processo gerador, não a população inteira. n-1 (correção de Bessel) é a convenção de mercado e do que ferramentas como `numpy.std(ddof=1)`/Excel `STDEV.S` assumem.
- **√252 porque variância escala linearmente no tempo** (retornos log ~i.i.d.): variância de 252 dias = 252 × variância diária, logo desvio = √252 × diário. 252 ≈ pregões/ano na B3.
- **252d como janela "anual".** Volatilidade de 30/90/252 dá leitura de curto, médio e ciclo anual.

**Trade-off aceito.** A independência dos retornos (premissa do √252) é aproximação — há autocorrelação e clustering de volatilidade reais. Para o nível do projeto, a anualização padrão é suficiente e é o que se espera ver; modelos GARCH etc. seriam sobre-engenharia aqui.

---

## 2026-06-11 — Etapa 6 — Dividendos particionados por ano; fato_dividendos conformada

**Contexto.** A ingestão de dividendos espelha a de cotações, mas proventos são **esparsos**: cada ticker paga poucos eventos por ano. Particionar por dia (como cotações) geraria centenas de objetos quase vazios. Há também a decisão de modelagem: como a fato de dividendos se relaciona com as dimensões existentes.

**Decisão.** Raw de dividendos particionado **por ano** (`raw/dividendos/ano=YYYY/dividendos.parquet`, todos os tickers juntos). `fato_dividendos` (grão: ticker × data-ex) reusa as **dimensões conformadas** `dim_empresa` e `dim_tempo` — as mesmas da fato de cotações. Ingestão em subpacote `ingestion/dividendos/`, com entry point próprio (`python -m ingestion.dividendos.main`, modos inicial/incremental).

**Racional.**
- **Partição por ano casa com a cardinalidade.** Poucos eventos/ano → um arquivo/ano é o tamanho certo; evita o anti-padrão de micro-arquivos sem perder partition pruning por ano.
- **Dimensões conformadas são o ponto do Kimball.** Reusar `dim_tempo` é o que permite, no `mart_dividend_yield`, alinhar proventos e preços pelo **mesmo** calendário (fact-to-fact via dimensão de tempo).
- **Subpacote mantém simetria sem acoplar.** `ingestion/dividendos/download.py` lê ao lado de `ingestion/download.py`; o código de cotações (consumido pela DAG da Etapa 5) não é tocado. Config e cliente S3 são compartilhados (`ingestion.config`, `ingestion.s3_client`), sem duplicar credenciais. CLI própria porque os modos de cotações (por data) não fazem sentido para dividendos (por ano).

**Trade-off aceito.** Dois fluxos de ingestão para manter. Aceitável: a simetria os deixa parecidos, e a fronteira (fonte e granularidade de partição diferentes) é real, não acidental.

---

## 2026-06-11 — Etapa 6 — Dividend yield trailing 12 meses sobre preço bruto, via range join

**Contexto.** O DY de 12 meses pode ser pontual (só "hoje") ou diário (recalculado a cada pregão, com janela de 365 dias deslizante). E o cálculo da soma móvel de proventos pode ser feito com window `RANGE BETWEEN INTERVAL` ou com self-join por faixa de data.

**Decisão.** DY **trailing 12m, grão diário**: para cada pregão, soma dos proventos com data-ex em `(data - 365, data]` dividido pelo fechamento **bruto** daquele dia. Implementado com **range join** (self-join por faixa) entre cotações e dividendos. Onde não há provento na janela, `dy_12m = 0` (não NULL).

**Racional.**
- **Grão diário permite a série temporal do yield.** O yield muda todo dia (janela desliza, preço muda); guardar só "hoje" perderia o gráfico de evolução, que é justamente o que um dashboard de DY mostra.
- **Range join é robusto e explícito.** A condição `data_ex > data - 365 AND data_ex <= data` deixa a semântica do intervalo visível na cláusula `ON`, e não exige que a data-ex coincida com um pregão (o que a versão `RANGE` window assumiria). Como dividendos são pouquíssimos, o custo do range join é desprezível.
- **0, não NULL, para ausência de provento.** "Não pagou dividendo nos últimos 12 meses" é um fato conhecido (yield zero), não um valor desconhecido. NULL contaminaria médias e gráficos.

**Trade-off aceito.** Range join é O(pregões × proventos por ticker) — irrelevante aqui (proventos minúsculos), mas em volume muito maior a versão `SUM() OVER (RANGE ...)` seria mais escalável. Documentado no `.sql` como a alternativa caso o volume cresça.

---

## 2026-06-11 — Etapa 6 — Materialização: marts pesados como table, fato_dividendos como view

**Contexto.** A Etapa 4 fixou "staging = view, marts = table". A Etapa 6 adiciona quatro modelos com perfis de custo diferentes: três pesados (indicadores diários, resumo, dividend yield diário) e um leve (fato de dividendos).

**Decisão.** `mart_indicadores_diarios`, `mart_indicadores_resumo` e `mart_dividend_yield` como **table**; `fato_dividendos` como **view** (exceção consciente ao default de marts).

**Racional.**
- **Tables onde a leitura é repetida e o cálculo não é trivial.** Os indicadores diários têm dezenas de window functions; o dividend yield tem range join. O dashboard (Etapa 7) lerá esses marts muitas vezes — materializar paga o cálculo uma vez.
- **View para `fato_dividendos` porque é ínfima.** Poucas dezenas de proventos por ticker; o JOIN com as dims é instantâneo. Materializar não traria ganho de latência e a view ganha freshness automática quando uma nova partição de ano chega.
- **Coerência com a Etapa 4.** Mantém o princípio (pesado/relido → table) e abre exceção apenas onde o custo justifica, documentando o porquê.

**Trade-off aceito.** `fato_dividendos` como view foge da regra "marts = table" — alguém lendo o `dbt_project.yml` poderia estranhar. Mitigado pelo `{{ config(materialized='view') }}` explícito no modelo e por esta entrada.

---

## 2026-06-18 — Segurança — Separação runtime vs dev em requirements; CI audita só o runtime (Postura A)

**Contexto.** O CI de segurança (`pip-audit`) passou a falhar com **8 CVEs** em transitivas do Jupyter (`bleach`, `jupyter-server`, `tornado`). Esses pacotes não fazem parte do runtime do pipeline (ingestão, warehouse, dbt, Airflow) — entram apenas via `jupyter`/`ipykernel`/`plotly`, usados em notebooks de exploração. A auditoria estava rodando sobre o `requirements.lock`, que incluía essas transitivas de desenvolvimento.

**Decisão.** Separar **runtime** de **desenvolvimento**: `requirements.txt` fica só com o runtime do pipeline (pandas, yfinance, pyarrow, requests, boto3, python-dotenv, duckdb, dbt-core, dbt-duckdb); `jupyter`, `ipykernel` e `plotly` movem-se para `requirements-dev.txt` (ao lado do `pip-audit`). O CI passa a auditar **apenas `requirements.txt`** (`pip-audit -r requirements.txt`), não o lock nem o ambiente resolvido. Versões inalteradas — só mudança de arquivo.

**Racional.**
- **Jupyter não é runtime — é ferramenta de análise local.** O deploy (imagem do Airflow + execução do pipeline) nunca importa Jupyter. Auditar Jupyter no CI mede risco de uma superfície que não vai a produção.
- **Postura A: auditar a superfície de produção, não o dev local.** O CI protege o que é entregue. Dependências de desenvolvimento são responsabilidade do desenvolvedor na sua máquina; falhar o build por CVE de `bleach` (renderização de HTML em notebook) seria ruído, não sinal.
- **Efeito colateral positivo:** a imagem do Airflow (que instala só `requirements.txt`) fica mais enxuta automaticamente, resolvendo a dívida DT-5.2.

**Trade-off aceito.** CVEs em ferramentas de dev deixam de ser sinalizados pelo CI — quem roda notebooks assume esse risco localmente. Aceitável para projeto de portfólio single-host: o dev é o próprio autor, e a superfície real (deploy) continua coberta.

**Adendo (2026-06-18) — remoção do `requirements.lock`.** Fechando esta mesma rodada, o `requirements.lock` foi **removido** do repositório. Estava órfão (não usado no `airflow/Dockerfile` nem no CI) e desatualizado (gerado antes da separação, listava Jupyter e os 8 CVEs). Mantê-lo dava falsa sensação de reprodutibilidade sem consumidor real. A reprodutibilidade do build do Airflow já vem da imagem base `apache/airflow:2.10.5` (constraints próprias) + `requirements.txt`. Se um lock determinístico virar requisito no futuro, gerá-lo via constraints oficiais do Airflow (constraints-2.10.5), não por `pip freeze` de venv standalone (ver DT-SEC.1/DT-SEC.4).
