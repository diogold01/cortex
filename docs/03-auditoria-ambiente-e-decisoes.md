# 03 — Auditoria de Ambiente (Windows 11) e Decisões Arquiteturais

Este documento consolida o diagnóstico prático executado na máquina de desenvolvimento (**Windows 11**) e as decisões arquiteturais definitivas do **Cortex**.

---

## 1. Resultado do *Pre-Flight Check* no Windows 11

Auditoria executada via terminal em `2026-11-21`:

| Componente | Comando / Verificação | Resultado Obtido | Decisão Decorrente |
|---|---|---|---|
| **Gerenciador `uv`** | `uv --version` | `uv 0.13.5 (x86_64-pc-windows-msvc)` | Usaremos `uv` para todo o ciclo de vida (`uv init`, `uv add`, `uv run`). |
| **Python** | `uv python list --only-installed` | `cpython-3.12.15` e `cpython-3.14.7` instalados via `uv` *(atalho `python` global aponta para alias vazio da Microsoft Store)* | Fixar `.python-version` em **`3.12`** e executar sempre com `uv run` (garante compatibilidade de wheels binários do `numpy` e `onnxruntime`). |
| **SQLite + FTS5** | `pragma compile_options` no Python 3.12 | `SQLite: 3.53.1 \| FTS5: True` | `FTS5` já está ativo nativamente na stdlib `sqlite3`, zero necessidade de compilar extensões. |
| **Git** | `git --version` | `git version 2.56.0.windows.2` | Pronto para gerenciar os commits do vault Markdown. |
| **Ollama** | `ollama list` | Instalado (`0.40.14`), porém **falhou ao subir o daemon** (`Failed to start: Unable to init instance: Unspecified error`) | **Confirmação crítica:** o Cortex **não** pode depender do daemon do Ollama para funcionar. O padrão será **`fastembed` (ONNX in-process)**, deixando Ollama apenas como adaptador opcional. |

---

## 2. Decisões Arquiteturais Fechadas (ADRs Consolidados)

### ADR-01: Markdown em Git como Fonte da Verdade e SQLite como Índice Derivado
- **Decisão:** Todas as notas e memórias vivem como arquivos `.md` com frontmatter YAML em um diretório versionado por Git. O arquivo `.sqlite` guarda apenas tabelas derivadas (`manifest`, `chunks`, `chunks_fts`, `embeddings`, `access_log`, `handoffs`).
- **Invariante Testável:** Apagar o arquivo `.sqlite` e rodar `cortex rebuild` deve reconstruir 100% do índice e produzir exatamente o mesmo ranking de busca.

### ADR-02: Fronteira Tipada de Sanitização (`Sanitized`)
- **Decisão:** Nenhuma string externa (nota, observação ou resumo de handoff) pode ser escrita em disco, commitada no Git, indexada no SQLite ou enviada ao modelo de embeddings sem passar por `sanitize()`.
- **Cobertura:** Chaves de API (`sk-`, `ghp_`, `AKIA`, etc.), tokens Bearer/JSON/URL, blocos de chave privada (`PEM`, `RSA`, `OPENSSH`, `PGP`), remoção de caracteres invisíveis Unicode de evasão e preservação de falsos positivos (validado contra os vetores de `sanitizer_vectors.json`).

### ADR-03: Chunking Estrutural Bilíngue com Injeção de Breadcrumb
- **Decisão:**
  - Dividir notas pelas fronteiras de `#`, `##` e `###`.
  - Nunca quebrar blocos de código (`````) ou tabelas Markdown ao meio.
  - Alvo de **250–350 tokens** por chunk (teto rígido de **512 tokens**, respeitando a expansão de ~25% do tokenizer em português).
  - **Zero overlap** entre seções diferentes; **10–15% de overlap** apenas quando uma mesma seção longa precisar ser subdividida.
  - Manter duas representações por chunk:
    - `content`: texto original limpo para leitura/exibição.
    - `index_text`: prefixado com o caminho estrutural (`caminho/nota.md > # Título > ## Seção`) para alimentar o FTS5 e o modelo de embeddings.

### ADR-04: Busca Lexical FTS5 Calibrada para Português + Inglês
- **Decisão:**
  - Tabela virtual `FTS5` com `tokenize = 'unicode61 remove_diacritics 2'` e `prefix = '3'`.
  - Query builder seguro contra injeção de sintaxe FTS5 (aspas, `*`, `NEAR`, `-`).
  - **Correção sobre o `second-brain-mcp`:** permitir termos técnicos de **2 caracteres** (como `IA`, `UX`, `QA`, `CI`, `v2`, `DB`) desde que não pertençam à lista de stopwords PT/EN.

### ADR-05: Motor Vetorial Exato com NumPy + `fastembed` (`multilingual-e5-small`)
- **Decisão:**
  - Persistir vetores no SQLite como BLOBs `float32` L2-normalizados na escrita, acompanhados de `(model_name, dim)`.
  - Carregar a matriz contígua `N × D` em memória sob demanda (*lazy loading*) e calcular similaridade de cosseno exata via produto interno (`matrix @ query_vec`) com `np.argpartition`.
  - Usar `fastembed` com `intfloat/multilingual-e5-small` (384 dims, até 512 tokens) aplicando internamente os prefixos obrigatórios `"passage: "` e `"query: "`.
  - Manter interface `Embedder` limpa para permitir benchmark comparativo opcional contra `Ollama (bge-m3)`.

### ADR-06: Fusão RRF (`k=60`) com Modo `explain=True` e Decaimento Pós-Fusão
- **Decisão:**
  - Fundir os rankings lexical e vetorial via Reciprocal Rank Fusion:
    $$\text{RRF}(d) = \sum_{r} \frac{1}{60 + \text{rank}_r(d)}$$
  - Agrupar resultados por nota (`path`), pontuando cada nota pelo seu melhor chunk.
  - Aplicar **decaimento temporal ponderado por acesso** apenas como **multiplicador/reranker pós-RRF** (e nunca como um stream dentro do RRF), com notas marcadas como `pinned` isentas de decaimento.
  - Expor `explain=True` na ferramenta de busca, retornando no mesmo código de produção: `fts_rank`, `vec_rank`, `rrf_fts`, `rrf_vec`, `decay_mult`, `final_score`, `matched_by` (`keyword | semantic | both`) e tempos em milissegundos de cada estágio (`fts_ms`, `embed_ms`, `vec_ms`, `fuse_ms`).

### ADR-07: Cuidados Específicos para Windows 11
- **Decisão:**
  - Incluir `.gitattributes` com `* text=auto eol=lf` desde o primeiro commit para evitar que `CRLF` altere hashes SHA-256 entre leituras.
  - Usar `pathlib.Path` normalizado com barras `/` nos identificadores do manifesto.
  - Implementar escrita atômica em arquivo (`tempfile` + `os.replace`) com *retry* curto (3 tentativas com backoff de 20–50 ms) para lidar com locks transitórios do Windows Defender / Search Indexer.
  - Configurar SQLite com `PRAGMA journal_mode=WAL;` e `PRAGMA busy_timeout=5000;` sob um único escritor serializado.
