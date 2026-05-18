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
