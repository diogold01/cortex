# 01 — Análise Comparativa dos Repositórios de Referência

Este documento registra a leitura técnica e a auditoria de código realizadas sobre os dois projetos que inspiraram o **Cortex** (`cortex-mcp`), clonados localmente em `../estudo-ai-memory/`.

---

## 1. Visão Geral dos Projetos Analisados

### 1.1 `YudiG12/second-brain-mcp`
- **Repositório:** `https://github.com/YudiG12/second-brain-mcp`
- **Proposta:** Servidor MCP remoto rodando na Cloudflare para disponibilizar as mesmas notas em Markdown em qualquer cliente de IA (Claude Code, Claude Web/Mobile, ChatGPT).
- **Stack Original:** TypeScript, Cloudflare Workers, Artifacts (Git), Durable Objects (`RepoWriter`), Queues, Workflows, D1 (SQLite + FTS5), Vectorize, Workers AI (`bge-m3`) e OAuth 2.1 (GitHub).
- **Custo Operacional Original:** Exige o plano **Cloudflare Workers Paid (US$ 5/mês)**.
- **Superfície MCP (8 tools em `src/index.ts`):**
  - `list_notes`, `read_note`, `search_notes`, `save_idea`, `write_note`, `edit_note`, `delete_note`, `move_note`.

### 1.2 `akitaonrails/ai-memory`
- **Repositório:** `https://github.com/akitaonrails/ai-memory`
- **Proposta:** Memória de longo prazo e protocolo de *handoff* entre mais de 20 CLIs/agentes de codificação (Claude Code, Codex, Cursor, Gemini CLI, OpenCode, etc.), com suporte local e para times.
- **Stack Original:** Workspace Rust com 11 crates (`ai-memory-core`, `ai-memory-store`, `ai-memory-wiki`, `ai-memory-mcp`, `ai-memory-hooks`, etc.), SQLite derivado, wiki Markdown em Git e apps auxiliares (Tauri desktop, macOS).
- **Custo Operacional Original:** R$ 0,00 (caminho padrão *Zero-LLM* e execução local).

---

## 2. O que os Dois Projetos Têm em Comum (Invariantes Compartilhadas)

1. **Markdown + Git como Fonte da Verdade (*Source of Truth*):**
   Nenhum dos dois guarda a memória apenas dentro de um banco proprietário. Os arquivos `.md` versionados em Git são a verdade; o banco de dados é um **índice derivado e descartável** que pode ser reconstruído integralmente a partir dos arquivos.
2. **MCP (Model Context Protocol) como Camada de Acesso:**
   Os agentes interagem com a memória através de ferramentas padronizadas via MCP (`ADR 014` do `second-brain-mcp`).
3. **Busca Híbrida Fundida por RRF (*Reciprocal Rank Fusion*):**
   Ambos combinam busca por palavra-chave (**SQLite FTS5**) com busca semântica (**vetores**) usando RRF (`k = 60`), evitando somar scores de escalas incompatíveis (BM25 bruto vs. cosseno).
4. **Serialização de Escrita (*Single-Writer*):**
   - `second-brain-mcp` usa **1 Durable Object por repositório** com mutex em memória (`ADR 008`).
   - `ai-memory` usa um **Single-writer SQLite actor** (Invariante #2).
5. **Controle Otimista de Concorrência:**
   - `second-brain-mcp` exige `expected_version` no `write_note` (`ADR 013`).
   - `ai-memory` valida versão/ID da página na transação de escrita.

---

## 3. Auditoria Direta no Código-Fonte Clonado (Achados Críticos)

A inspeção direta dos arquivos em disco revelou oportunidades reais de melhoria para o **Cortex**:

### 3.1 O Chunker do `second-brain-mcp` é Ingênuo (`src/lib/notes.ts`)
- Nas linhas 24–36 de `src/lib/notes.ts`, a função `chunk(body)` faz apenas `body.split(/\n\s*\n/)` e concatena parágrafos até `CHUNK_CHARS = 1200` (`MAX_CHUNKS = 50`).
- **Problemas identificados:**
  - Não respeita fronteiras de cabeçalhos Markdown (`#`, `##`, `###`), misturando seções diferentes no mesmo chunk.
  - Pode quebrar blocos de código (`````) ao meio caso contenham linhas em branco.
  - Não injeta o caminho de títulos (*breadcrumb*) no chunk — parágrafos curtos perdem o contexto de qual projeto ou seção pertencem.
- **Como o Cortex supera isso:** Implementando **Chunking Estrutural por Headings com Injeção de Breadcrumb** (`arquivo.md > # Título > ## Seção`) e atomicidade para blocos de código e tabelas.

### 3.2 O Filtro `MIN_TERM = 3` do `second-brain-mcp` Apaga Siglas Técnicas (`src/search/hybrid.ts`)
- Na linha 9 de `src/search/hybrid.ts`, o código define `MIN_TERM = 3` e filtra `.filter((t) => t.length >= MIN_TERM && !STOPWORDS.has(t))`.
- **Problema identificado:** Em português e tecnologia, isso descarta siglas essenciais de 2 caracteres como **`IA`**, **`UX`**, **`QA`**, **`CI`**, **`CD`**, **`DB`**, **`v1`**, **`v2`**, **`PR`**.
- **Como o Cortex supera isso:** Permitindo termos de 2 caracteres que não estejam na lista de stopwords PT/EN (ou que sejam siglas/identificadores alfanuméricos).

### 3.3 Schema SQLite Diretamente Portável (`migrations/0001` e `0002`)
- As migrações do `second-brain-mcp` têm apenas 25 linhas de SQL e usam recursos nativos do SQLite:
  - `manifest (path TEXT PRIMARY KEY, sha TEXT NOT NULL, chunks INTEGER NOT NULL, indexed_at TEXT NOT NULL)`
  - `chunks_fts USING fts5(path UNINDEXED, seq UNINDEXED, text, tokenize = 'unicode61 remove_diacritics 2', prefix = '3')`

### 3.4 Vetores Reais de Teste de Sanitização (`tests/fixtures/sanitizer_vectors.json` do `ai-memory`)
- O arquivo `sanitizer_vectors.json` do `ai-memory` contém uma bateria pronta de casos de borda que podemos incorporar aos testes do Cortex:
  - Chaves de API (`sk-...`, `ghp_...`, `AKIA...`) isoladas, dentro de JSON escapado, URL-encoded (`?api_key%3Dsk-...`) ou coladas em texto Unicode (`日本sk-...`).
  - Caracteres invisíveis Unicode (`\u200b`, `\ufeff`, etc.) usados para burlar regexes simples.
  - Blocos inteiros de chaves privadas (`-----BEGIN PRIVATE KEY-----`, `RSA`, `OPENSSH`, `PGP PRIVATE KEY`).
  - Casos `unchanged` (falsos positivos que **não** podem ser alterados): emojis com ZWJ, chaves **públicas** PGP e trechos de código que apenas mencionam a string do cabeçalho PEM sem corpo de chave privada.

---

## 4. Mapa de Transplante Seletivo (O que Entra vs. O que Fica de Fora)

### O que Trazemos para o Cortex:
- **Do `second-brain-mcp`:**
  - Superfície MCP enxuta (uma única ferramenta de busca `memory_search` em vez de separar busca lexical e semântica — `ADR 015`).
  - Proteção contra *lost update* via `expected_version` (`ADR 013`).
  - Manifesto de indexação por hash SHA (`ADR 010`) e tokenizer FTS5 `unicode61 remove_diacritics 2`.
  - Fusão por Reciprocal Rank Fusion (`RRF_K = 60`) com agregação do melhor chunk por nota (`ADR 012`).
- **Do `ai-memory`:**
  - Fronteira tipada de sanitização (`Sanitized<T>`) antes de qualquer escrita em disco, Git ou SQLite.
  - Protocolo de **Handoff tipado** com semântica *claim-once* transacional (`open` -> `accepted` / `expired`).
  - **Decaimento ponderado por acesso (Zero-LLM)** atuando como *reranker* pós-RRF.
  - **Harness de Evals** medindo `Recall@K`, `MRR` e `nDCG` com comparação A/B reproduzível.

### O que Descartamos (Prevenção de Over-Engineering):
- Toda a infraestrutura paga da Cloudflare (Workers Paid, Durable Objects, Queues, Vectorize, Artifacts).
- Os 20+ adaptadores e scripts de hooks específicos de CLIs do `ai-memory`.
- OAuth 2.1 completo com GitHub e gestão multiusuário/RBAC (Cortex é *single-user local-first* até a v3).
- Console Web de gerenciamento e passes de *"dreaming"* com LLM generativa em background.
