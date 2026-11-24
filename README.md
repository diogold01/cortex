![Cortex Banner](./cortex-banner.svg)

# Cortex (`cortex-mcp`)

> **Servidor MCP local-first de memória persistente, busca híbrida (FTS5 + Vetores Exatos + RRF) e engenharia de agentes (Sanitização Tipada, Handoff Claim-Once e Evals Reproduzíveis).**

Servidor MCP (Model Context Protocol) em Python para memória persistente de agentes, com armazenamento em Markdown versionado no Git, busca híbrida local (SQLite FTS5 + vetores NumPy via `fastembed` + RRF), sanitização de segredos em fronteira tipada e controle de concorrência otimista (`expected_version`), operando 100% offline e com custo zero no Windows 11.

---

## Índice de Documentação e Registro de Decisões

Toda a pesquisa, comparação de repositórios, conciliação entre múltiplos modelos avaliadores e auditoria de código/ambiente está registrada na pasta [`docs/`](./docs/):

1. **[01 — Análise Comparativa dos Repositórios de Referência](./docs/01-analise-comparativa-repositorios.md)**
   - Leitura técnica de `second-brain-mcp` e `ai-memory`.
   - O que ambos têm em comum, onde se complementam, o que transplantar e o que descartar (*over-engineering*).
   - Achados da auditoria direta no código-fonte (`notes.ts`, `hybrid.ts`, `migrations/` e `sanitizer_vectors.json`).
2. **[02 — Conciliação das Análises Multi-IA (Rodadas 1 e 2)](./docs/02-conciliacao-analises-ias.md)**
   - Síntese das avaliações de 5 modelos (Gemini, GPT-6, DeepSeek, Venice/DeepSeek V4.1 e Claude Sonnet 5.5).
   - Resolução das divergências técnicas com base em benchmarks, restrições do Windows 11 e valor para portfólio de AI Engineer.
3. **[03 — Auditoria de Ambiente (Windows 11) e Decisões Arquiteturais](./docs/03-auditoria-ambiente-e-decisoes.md)**
   - Resultado do *Pre-Flight Check* na máquina local (`uv`, Python 3.12, SQLite 3.53.1 com FTS5, Git e falha do daemon Ollama).
   - Stack definitiva e regras de engenharia (chunking estrutural com breadcrumb, correção de siglas de 2 letras no FTS5, prefixos `e5`, fronteira `Sanitized`, `expected_version` e modo `explain=True`).
4. **[04 — Roadmap em Fases e Critérios de Aceite (Done When)](./docs/04-roadmap-e-criterios-de-aceite.md)**
   - Plano de execução incremental (`v1` -> `v2` -> `v3`) com critérios de aceite testáveis e foco em métricas de Recuperação de Informação (`Recall@5`, `MRR@10`, `nDCG@10`, latência `p50/p95`).
5. **[05 — Progresso e Desvios do Plano](./docs/05-progresso.md)**
   - Registro por etapa do que foi entregue, evidências (testes, mutação, medições) e onde a implementação divergiu do plano original.

---

## Resumo Rápido da Stack Fechada (R$ 0,00)

| Camada | Escolha | Justificativa Principal |
|---|---|---|
| **Linguagem & Runtime** | Python 3.12+ (`uv`, Pydantic v2, Pytest) | Ecossistema nativo de AI Engineering, Evals e NumPy; já instalado e validado via `uv`. |
| **Interface de Agentes** | MCP SDK oficial (`stdio` na v1/v2; `HTTP` na v3) | Compatível com Claude Code, Antigravity, Codex e Cursor sem manter 20+ adaptadores. |
| **Fonte da Verdade** | Arquivos Markdown (`.md`) + Git local | Portável, auditável, editável em qualquer editor; o banco é apenas índice derivado. |
| **Busca Lexical** | SQLite `FTS5` (`unicode61 remove_diacritics 2`, `prefix='3'`) | Nativo no Python 3.12 (`SQLite 3.53.1`), zero dependência externa. |
| **Busca Vetorial** | `NumPy` (cosseno exato sobre BLOBs `float32` normalizados) | Até ~20k chunks ocupa ~30 MB de RAM, roda em 2–8 ms, 100% exato e evita erro de DLL do `sqlite-vec` no Windows 11. |
| **Embeddings Locais** | `fastembed` (`intfloat/multilingual-e5-small` ONNX) | Roda *in-process* em CPU, sem depender do daemon do Ollama e compatível com GitHub Actions CI gratuito. |
| **Fusão & Ranking** | RRF (`k=60`) + Decaimento por acesso (pós-filtro) | Combina match exato e semântico com modo `explain=True` auditável. |
| **Segurança & Concorrência** | Fronteira `Sanitized` + `expected_version` + Single-Writer | Impede vazamento de segredos no Git/SQLite e evita sobrescrita silenciosa entre agentes. |
