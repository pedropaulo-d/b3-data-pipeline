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

## 2026-05-18 — Etapa 1 — Idempotência por sobrescrita do arquivo de data

**Contexto.** Como tratar reexecução do pipeline para um período já ingerido? As opções típicas são: (a) sobrescrever a partição inteira; (b) versionar por timestamp/ingestion-id (`cotacoes_20260518T031530.parquet`); (c) detectar e pular se o arquivo já existe.

**Decisão.** **Sobrescrever** o arquivo da data. Reexecução produz o mesmo conjunto de arquivos com o mesmo conteúdo (assumindo que a fonte não mudou).

**Racional.**
- **Idempotência declarativa.** O resultado final depende só do intervalo solicitado, não do histórico de execuções. Essa propriedade é central para orquestração (Etapa 5) — Airflow pode re-disparar uma task sem preocupação.
- **Simplicidade.** Sem necessidade de tabela de controle, sem lógica de "qual versão é a oficial". A pasta `data/raw/cotacoes/` é a verdade.
- **Correção de fonte.** Se o yfinance corrigir um valor histórico (acontece, especialmente em ajustes retroativos por proventos), uma reexecução do range incorpora a correção naturalmente.

**Trade-off aceito.** **Perde-se o histórico de versões do raw** — não é possível saber, depois, qual era o `Adj Close` que o yfinance servia em uma data anterior. Em ambiente real, isso seria coberto por snapshot em object storage versionado (S3 versioning). Aqui, fica como nota: o raw é "verdade atual segundo a fonte", não "verdade histórica do que vimos".

---

## 2026-05-18 — Etapa 1 — Tratamento de volume NaN: Int64 nullable

**Contexto.** O `yfinance` ocasionalmente devolve `NaN` na coluna `Volume` — para tickers em dias específicos onde o feed não trouxe dado de volume, embora preço esteja presente. A versão inicial do `download.py` aplicava `fillna(0).astype("int64")` para forçar tipo inteiro nativo do numpy, o que tinha o efeito colateral de **transformar "desconhecido" em "zero negócios"** — duas semânticas distintas colapsadas em um valor.

**Decisão.** Usar o tipo nullable do pandas (`"Int64"` com I maiúsculo) na coluna `volume`, **preservando NaN** quando o yfinance não traz o valor.

**Racional.**
- **Imutabilidade semântica do raw.** O raw layer deve refletir a fonte. `NaN` = "a fonte não tem ou não nos contou esse valor"; `0` = "houve pregão e ninguém negociou". São fatos diferentes e não devem ser confundidos no nível mais bruto.
- **Decisão de tratamento sobe para staging.** Se a regra de negócio futura for "imputar volume desconhecido como 0", ou "descartar a linha", ou "interpolar", essa decisão pertence ao dbt na Etapa 4 — onde fica auditável e mudável sem re-baixar dado.
- **Parquet preserva nullability.** PyArrow grava `Int64` do pandas como inteiro com bitmap de validade, sem precisar de mágica adicional.

**Trade-off aceito.** O tipo `Int64` do pandas exige cuidado em comparações e agregações em Python (`NaN` propaga; `==` não funciona contra `NA`). Aceitável porque a manipulação analítica acontece em **SQL no DuckDB/dbt** a partir da Etapa 3 — e em SQL, `NULL` é tratado naturalmente em agregações (`SUM` ignora, `COUNT(*)` inclui, `COUNT(volume)` não).
