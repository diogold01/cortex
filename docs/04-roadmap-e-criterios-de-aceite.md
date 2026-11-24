# 04 — Roadmap em Fases, Modelos Recomendados e Critérios de Aceite (*Done When*)

Seguindo o método **PCCD** e o balanceamento inteligente entre os 3 buckets de cota do Antigravity (**Gemini Models**, **Claude and GPT models** e **Gemini 4 Argon**), o desenvolvimento do **Cortex** está dividido em etapas autocontidas, cada uma com o **Modelo + Nível de Esforço** ideal.

---

## Mapa Rápido de Modelos e Esforço por Etapa

| Etapa | Escopo Principal | Modelo Recomendado | Esforço | Bucket de Cota Utilizado |
|---|---|---|---|---|
| **1.1** | Setup `uv` (Python 3.12) + Sanitizador Tipado (`Sanitized`) | **Claude Sonnet 5.5** | `High` | *Claude and GPT models* |
| **1.2** | Chunker Estrutural (Breadcrumb) + Vault Git (`expected_version`) | **Gemini 4 Hydrogen** | `XHigh` | *Gemini Models* |
| **1.3** | SQLite FTS5 (`manifest` + siglas 2 letras) + Servidor MCP `stdio` | **Claude Sonnet 5.5** | `Medium` | *Claude and GPT models* |
| **1.4** | Harness de Evals + Golden Set Bilíngue (Baseline FTS5) | **Gemini 4 Neon** | `Medium` | *Gemini Models* |
| **2.1** | Embeddings (`fastembed` `e5-small`) + Vetor Exato em `NumPy` | **Gemini 4 Hydrogen** | `High` | *Gemini Models* |
| **2.2** | Fusão Híbrida RRF (`k=60`) + `explain=True` + Eval A/B | **Claude Opus 5.5** | `High` | *Claude and GPT models* |
| **3.1** | Handoff Tipado (*Claim-Once*) + Decaimento por Acesso | **Gemini 4 Argon** | `High` | *Gemini 4 Argon* |
| **3.2** | Transporte HTTP + Bearer Token + Cloudflare Tunnel + Docs Finais | **Gemini 4 Neon** (ou **3.8 Flash**) | `Low` / `Medium` | *Gemini Models* |

---

## Fase 1 (`v1`) — Fundação Segura, Busca Lexical FTS5 e Baseline de Evals

### Etapa 1.1 — Setup do Projeto + Fronteira de Sanitização (`Sanitized`)
- **Modelo & Esforço:** `Claude Sonnet 5.5` — **`High`**
- **Por que este modelo:** O sanitizador exige regexes cirúrgicas (chaves de API, JSON/URL escapados, blocos PEM/SSH/PGP e remoção de caracteres invisíveis Unicode) sem corromper os falsos positivos (`unchanged`) do `sanitizer_vectors.json`.
- **Entregas:**
  1. Inicialização do pacote em `cortex/` com `uv` (Python 3.12), `pyproject.toml`, `.gitattributes` (`* text=auto eol=lf`), `pytest`, `ruff` e `pyright`.
  2. Tipo `Sanitized` em `src/cortex/sanitize.py` (única porta de entrada para persistência).
  3. Suíte `tests/test_sanitizer.py` validando 100% dos vetores reais de `sanitizer_vectors.json`.
- **Critério de Aceite (*Done When*):** `uv run pytest tests/test_sanitizer.py` 100% verde (zero segredos vazados e zero falsos positivos alterados).

---

### Etapa 1.2 — Chunker Estrutural Bilíngue + Vault Git/Markdown
- **Modelo & Esforço:** `Gemini 4 Hydrogen` — **`XHigh`**
- **Por que este modelo:** O parser estrutural de Markdown (respeitar `#`, `##`, `###`, manter blocos de código ````` e tabelas atômicos, injetar *breadcrumb* `path > # H1 > ## H2`, aplicar overlap apenas intra-seção) e a escrita atômica com *retry* no Windows exigem raciocínio algorítmico profundo.
- **Entregas:**
  1. `src/cortex/chunker.py`: separa `content` (texto limpo) e `index_text` (com breadcrumb), orçamento de 250–350 tokens (teto 512).
  2. `src/cortex/vault.py`: validação estrita de paths `.md`, escrita atômica (`tempfile` + `os.replace` com retry curto para Windows Defender), commit Git por escrita e checagem de versão (`expected_version` SHA de 12 hex).
  3. Testes `tests/test_chunker.py` e `tests/test_vault.py`.
- **Critério de Aceite (*Done When*):** Blocos de código e tabelas nunca são cortados ao meio; escrita com `expected_version` divergente é recusada com erro de conflito; toda escrita válida gera commit Git e exige `Sanitized`.

---

### Etapa 1.3 — Índice SQLite Derivado (`FTS5` + `manifest`) + Servidor MCP `stdio`
- **Modelo & Esforço:** `Claude Sonnet 5.5` — **`Medium`**
- **Por que este modelo:** O contrato MCP e o schema SQLite (`manifest` + `chunks_fts`) já estão 100% especificados; `Claude Sonnet 5.5 (Medium)` entrega código limpo e rápido com baixo consumo de cota.
- **Entregas:**
  1. `src/cortex/store.py`: SQLite em modo `WAL`, escritor único, tabelas `manifest` e `chunks_fts` (`unicode61 remove_diacritics 2`, `prefix='3'`) e rotina `rebuild_index()`.
  2. `src/cortex/fts.py`: query builder anti-injeção FTS5 com stopwords PT/EN separadas e suporte a siglas técnicas de 2 letras (`IA`, `UX`, `QA`, `CI`, `v2`, `DB`).
  3. `src/cortex/mcp_server.py`: 6 tools MCP via `stdio` (`memory_search` com `explain=True`, `memory_read`, `memory_write`, `memory_list`, `memory_delete`, `memory_status`).
  4. Testes `tests/test_store_fts.py` e `tests/test_mcp.py`.
- **Critério de Aceite (*Done When*):** Apagar o arquivo `.sqlite` e rodar `rebuild_index()` reconstrói exatamente os mesmos chunks; nenhuma query malformada (aspas, `*`, `NEAR`, `-`) quebra o FTS5; siglas de 2 letras são encontradas.

---

### Etapa 1.4 — Harness de Evals + Golden Set Bilíngue (Baseline FTS5)
- **Modelo & Esforço:** `Gemini 4 Neon` — **`Medium`**
- **Por que este modelo:** Implementação direta das métricas de IR (`Recall@5`, `MRR@10`, `nDCG@10`, latência `p50/p95`) e geração do relatório de baseline.
- **Entregas:**
  1. `src/cortex/evals.py`: cálculo determinístico de `Recall@5`, `MRR@10`, `nDCG@10` e cronometragem por estágio.
  2. `evals/golden_set.json`: corpus sintético realista + 30–50 queries PT/EN (identificadores exatos, siglas, paráfrases e cross-lingual PT<->EN).
  3. Publicação automática do relatório `docs/benchmarks/v1-baseline-fts5.md` (incluindo comparativo entre chunker ingênuo de 1200 chars vs. chunker estrutural do Cortex).
- **Critério de Aceite (*Done When*):** `uv run python -m cortex.evals` executa em um comando e gera a tabela oficial do Baseline FTS5 da `v1`.

---

## Fase 2 (`v2`) — Busca Híbrida (`fastembed` + NumPy + RRF) e Comparação A/B

### Etapa 2.1 — Camada de Embeddings (`fastembed`) + Motor Vetorial Exato (`NumPy`)
- **Modelo & Esforço:** `Gemini 4 Hydrogen` — **`High`**
- **Por que este modelo:** Exige precisão na normalização L2 em `float32`, aplicação interna dos prefixos `"passage: "` e `"query: "` da família `multilingual-e5-small`, *lazy loading* do modelo ONNX e cache em memória da matriz `N × D` sincronizado com o `manifest`.
- **Critério de Aceite (*Done When*):** Busca vetorial exata (`matrix @ query_vec` + `np.argpartition`) roda em `< 15 ms` para até 20k chunks; vetores de modelo/dimensão diferente são ignorados com segurança; se o embedder estiver desligado, o sistema degrada para `keyword-only` sem erro.

### Etapa 2.2 — Fusão Híbrida RRF (`k=60`) com `explain=True` + Relatório A/B
- **Modelo & Esforço:** `Claude Opus 5.5` — **`High`**
- **Por que este modelo:** Etapa nobre de AI Engineering — calibrar o `semantic_floor`, unificar o ranking RRF (`k=60`) agrupando pelo melhor chunk por nota, expor `explain=True` auditável e analisar criticamente o relatório A/B (`FTS5 Puro` vs. `Vetorial Puro` vs. `Híbrido RRF`).
- **Critério de Aceite (*Done When*):** Relatório `docs/benchmarks/v2-hybrid-ab.md` publicado com ganho comprovado em queries semânticas/cross-lingual e análise automática de falhas (*error analysis*).

---

## Fase 3 (`v3`) — Engenharia de Agentes e Acesso Remoto Gratuito

### Etapa 3.1 — Handoff Tipado (*Claim-Once*) + Decaimento por Acesso
- **Modelo & Esforço:** `Gemini 4 Argon` — **`High`**
- **Por que este modelo:** Aproveita o bucket dedicado do `Gemini 4 Argon` para implementar a transação atômica de disputa de handoff (`BEGIN IMMEDIATE` / `UPDATE ... WHERE status = 'open'`) e o reranker de decaimento temporal ponderado por acesso (`access_count`, `last_accessed_at`, isenção de `pinned`).
- **Critério de Aceite (*Done When*):** Teste com 20 claims concorrentes sobre o mesmo handoff resulta em exatamente 1 sucesso e 19 conflitos; o eval comprova que o decaimento não degrada o Recall do Golden Set.

### Etapa 3.2 — Transporte HTTP + Bearer Token + Cloudflare Tunnel & Fechamento
- **Modelo & Esforço:** `Gemini 4 Neon` (ou `Gemini 3.8 Flash`) — **`Low` / `Medium`**
- **Por que este modelo:** Tarefa enxuta de exposição `Streamable HTTP`, validação de Bearer Token em tempo constante (`hmac.compare_digest`), guia de `cloudflared tunnel` gratuito e acabamento final do `README.md`.
- **Critério de Aceite (*Done When*):** Requisições HTTP sem token retornam `401 Unauthorized`; toda a suíte `pytest` e o runner de Evals passam verdes em um comando.
