# CLAUDE.md

> Este arquivo **não é instrução para o usuário** — é contexto persistente carregado em toda sessão do Claude Code neste repositório. Trate-o como diretriz operacional.

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

### ✅ Pode fazer integralmente

- Criar estrutura de pastas e arquivos vazios
- Boilerplate de scripts Python (imports, parsing de argumentos, logging)
- `docker-compose.yml` e `Dockerfile` a partir de requisitos descritos
- Modelos dbt em SQL/Jinja **a partir de uma modelagem já desenhada pelo usuário**
- DAGs do Airflow **a partir de um fluxo de tarefas já definido pelo usuário**
- Testes unitários e de integração
- READMEs, docstrings, comentários explicativos
- Debug de erros de sintaxe, dependência, configuração

### ⚠️ Pode ajudar, mas o usuário decide

- **Modelagem dimensional** (granularidade, chaves, SCDs) — explique trade-offs, deixe escolher
- **Decisões de arquitetura** (separação de camadas, particionamento, formato de storage) — apresente opções
- **Lógica financeira** (definição de retorno, ajuste por proventos, janelas móveis) — confirme antes de codar

### ❌ Não faça sem o usuário tentar primeiro

- **Script de ingestão da Etapa 1** — é o primeiro contato dele com yfinance + Parquet
- **SQL exploratório da Etapa 3** — é onde ele aprende a "conversar" com o DuckDB
- **Definição de indicadores da Etapa 6** — é o coração do storytelling em entrevista

Nesses casos, ofereça pistas, revise código que ele escreveu, sugira melhorias — mas **não entregue a primeira versão pronta**.

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
