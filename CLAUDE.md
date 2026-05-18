# CLAUDE.md

> Este arquivo **não é instrução para o usuário** — é contexto persistente carregado em toda sessão do Claude Code neste repositório. Trate-o como diretriz operacional. Este arqyuivo não pode passar de 200 linhas.

---

## Sobre o projeto

`b3-data-pipeline` é um **projeto de portfólio** para vaga de engenharia de dados. O objetivo principal não é entregar um pipeline funcional o mais rápido possível — é o usuário **aprender cada peça da stack a ponto de saber defender em entrevista**.

Isso muda como você deve colaborar. Otimize para compreensão do usuário, não para velocidade de entrega.

---

## Princípio fundamental

> Use o Claude Code para o que é **trabalho**. O usuário faz o que é **aprendizado**.
>
> **Trabalho:** digitar boilerplate, lembrar sintaxe, configurar Docker, escrever testes.
>
> **Aprendizado:** entender o dado, decidir modelagem, depurar conceitualmente, explicar decisões.

Se algo cai no lado "aprendizado", **pare e devolva ao usuário** — mesmo que seja mais lento. Resolver no automático rouba a entrevista futura dele.

---

## Regras de delegação por tipo de tarefa

O usuário atua como **tech lead / arquiteto de dados** deste projeto. Sua função
é executar a implementação dentro das decisões que ele toma. Ele revisa o
código gerado — não o escreve linha a linha.

### ✅ Pode (e deve) fazer integralmente

- Estrutura de pastas e arquivos
- Scripts Python completos (ingestão, transformação, utilidades)
- `docker-compose.yml`, `Dockerfile`, configuração de serviços
- Modelos dbt em SQL/Jinja a partir da modelagem que o usuário desenhou
- DAGs do Airflow a partir do fluxo que o usuário definiu
- Testes (pytest, dbt tests)
- READMEs, docstrings, comentários, diagramas Mermaid
- Debug de erros, refactor, otimização

Entregue código completo e funcional. Não deixe TODOs nem stubs esperando o
usuário preencher, exceto quando explicitamente pedido.

### ⚠️ NÃO faça sem decisão explícita do usuário

Estas são as áreas que o usuário se reserva. Em todas elas, **pergunte antes
de assumir**, apresente alternativas com trade-offs claros, e só implemente
depois da decisão dele:

- **Modelagem dimensional**
  - Granularidade da fato ("1 linha = o quê?")
  - Quais dimensões existem e por quê
  - Surrogate key vs natural key
  - SCD tipo 1, 2 ou 3 em cada dimensão
  - Esquema estrela vs floco

- **Decisões de arquitetura**
  - Separação de camadas (raw/staging/intermediate/marts)
  - Estratégia de particionamento (por dia, mês, ticker)
  - Formato de storage e compressão
  - Materialização dbt (view, table, incremental, ephemeral)
  - Estratégia de orquestração (uma DAG monolítica vs múltiplas)

- **Regras de negócio e lógica financeira**
  - Definição de retorno (simples, log, ajustado por proventos)
  - Tratamento de dividendos e splits
  - Janelas móveis (qual período, com ou sem preenchimento)
  - Fórmulas de indicadores (P/L, dividend yield, payout, etc.)
  - Como tratar feriados, pregões parciais, NaN

Comportamento esperado nestas áreas: liste as opções viáveis, explique o
trade-off de cada uma, recomende uma se tiver convicção técnica, **e espere
a escolha do usuário antes de codar**.

### Comportamento esperado em sessões

1. **Em decisões de modelagem/arquitetura/negócio:** pergunte primeiro,
   implemente depois. Mesmo que pareça óbvio.
2. **Em implementação:** entregue código completo, idiomático, com docstrings
   e logging adequado. Não peça ao usuário para "preencher os detalhes".
3. **Ao escrever código novo que envolve um conceito não trivial** (window
   function complexa, macro Jinja, retry com backoff), **explique brevemente
   a escolha no commit message ou em comentário** — para o usuário revisar
   conscientemente, não apenas aceitar.
4. **Se o usuário pedir algo que conflita com decisões anteriores** registradas
   em `docs/decisoes.md`, aponte o conflito antes de executar.
5. **Não pule etapas do plano do projeto.** A sequência é pedagógica para o
   usuário; antecipar Airflow antes da Etapa 5 não ajuda.

---

## Comportamento esperado em sessões

- **Confirme a etapa atual** antes de propor mudanças amplas. As etapas são incrementais; não pule.
- **Conecte cada tarefa ao "por quê"**: por que essa peça existe, qual problema ela resolve, o que aconteceria sem ela.
- **Não introduza ferramentas fora da etapa corrente** (sem Docker na Etapa 1, sem dbt na Etapa 3, etc.).
- **Sinalize delegação excessiva**: se o usuário pedir algo que cai em "❌", lembre-o do escopo de aprendizado antes de executar.

---

## Convenções técnicas

### Python

- Versão **3.11+**
- Gerenciador: **pip + venv** (não Poetry, não uv)
- Bibliotecas centrais: `pandas`, `pyarrow`
- **Logging via `logging` stdlib**, nunca `print` em código de produção
- `except` sempre específico (`except ValueError:`, nunca `except:` ou `except Exception:` sem necessidade)

### Estrutura de dados

- Formato em disco: **Parquet** (não CSV em raw)
- **Particionamento por data** no raw layer:
  ```
  data/raw/cotacoes/ano=YYYY/mes=MM/dia=DD/cotacoes.parquet
  ```
- **Imutabilidade**: raw layer é append-only; correções viram nova partição.
- **Idempotência**: rodar o mesmo script duas vezes não deve gerar duplicatas nem corromper estado.

### Git

- Mensagens de commit em **português**
- Granularidade: um commit por unidade lógica (não acumular dia inteiro em um commit)
- **Nunca commitar** `.env`, conteúdo de `data/raw/`, arquivos `*.duckdb`

### Documentação

- **`docs/decisoes.md`** — decisões técnicas com contexto, racional e trade-off aceito
- **`docs/NOTAS.md`** — caderno de aprendizados por etapa (conceitos, dúvidas, descobertas)

---

## Escopo travado

- **Tickers (6):** PETR4, VALE3, ITUB4, BBDC4, WEGE3, ABEV3
- **Histórico inicial:** 5 anos
- **Stack:** Python + MinIO + DuckDB + dbt + Airflow + Streamlit
- **Ambiente:** local (sem cloud)
- **Python:** 3.11+, pip + venv

Não sugira mudar nenhum destes sem o usuário pedir explicitamente.

---

## Glossário rápido

- **Raw layer** — dado bruto, como veio da fonte, particionado por data de ingestão. Nunca é alterado.
- **Staging** — dado limpo e tipado, ainda em formato próximo do raw. Camada intermediária do dbt.
- **Marts** — dado modelado para consumo analítico (fatos e dimensões). Camada final do dbt.
- **Granularidade** — o que cada linha representa. Ex.: "uma linha por ticker por dia".
- **Idempotência** — propriedade de uma operação cujo resultado não muda se ela for executada mais de uma vez com os mesmos inputs.
