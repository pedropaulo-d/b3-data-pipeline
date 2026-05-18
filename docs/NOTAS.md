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
- (preencher conforme surgirem)

### Dúvidas
- (preencher conforme surgirem)

### Descobertas
- (preencher conforme surgirem)

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
(preencher conforme rodar e ler o código)

### Descobertas

Idempotência: semântica ≠ byte-a-byte. Descobri que comparar hash de arquivos Parquet entre duas execuções dá False mesmo quando o conteúdo é idêntico — PyArrow embute metadata com timestamp de escrita. O teste correto de idempotência em pipeline de dados é comparar o conteúdo lógico (DataFrame após sort_values + reset_index), não bytes. Airflow, dbt e Spark definem idempotência dessa forma.

---

## Etapa 2 — Object storage com MinIO

**Início:** —
**Fim:** —

### Conceitos
(em branco até começar)

### Dúvidas
(em branco até começar)

### Descobertas
(em branco até começar)

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
