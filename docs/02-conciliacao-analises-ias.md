# 02 — Conciliação das Análises Multi-IA (Rodadas 1 e 2)

Para validar a arquitetura do **Cortex** sem vieses, submetemos o contexto real dos dois repositórios e as nossas restrições (**trilha de AI Engineer + Windows 11 + Custo R$ 0,00**) a **5 modelos de IA** em duas rodadas de questionamento crítico:
- **Gemini (Google)**
- **GPT-6 (OpenAI / ChatGPT)**
- **DeepSeek**
- **Venice (DeepSeek V4.1 Flash Uncensored)**
- **Claude Sonnet 5.5 (Anthropic)**

Os textos brutos estão arquivados em `../../estudo-ai-memory/RESPOSTA.TXT` (Rodada 1) e `../../estudo-ai-memory/RESPOSTA 1.TXT` (Rodada 2).

---

## 1. Evolução da Rodada 1 para a Rodada 2 (Convergência 5/5)

Na **Rodada 1**, havia três divergências principais:
1. **Linguagem:** 3 votavam em Python, 1 (Venice) votava em TypeScript.
2. **Motor Vetorial:** 3 sugeriam `sqlite-vec`, 1 (GPT-6) sugeria `BLOB + NumPy`.
3. **Embeddings:** divisão entre `Ollama (bge-m3)` e `fastembed (ONNX)`.

Na **Rodada 2**, quando exigimos conta de memória/latência para até ~20.000 chunks, verificação de compatibilidade no **Windows 11** e foco no que pesa em **entrevistas de AI Engineering**, **os 5 modelos convergiram de forma unânime**:

- **Venice mudou de TypeScript para Python 3.12 + `uv`:** reconheceu que o coração do portfólio são as **Evals de Recuperação de Informação (`Recall@K`, `MRR`, `nDCG`) e manipulação vetorial (`NumPy`)**, onde Python é nativo.
- **Claude Sonnet 5.5 e DeepSeek mudaram de `sqlite-vec` para `NumPy`:** ao verificarem issues reais do `sqlite-vec` no Windows 11 com Python 3.12 ([issue #45](https://github.com/asg017/sqlite-vec/issues/45) — erro ao carregar `vec0.dll` via `load_extension`), concluíram que `sqlite-vec` traz risco de instalação sem ganho algorítmico nessa escala.

---

## 2. Paridade de Eficiência: Onde o Cortex Ganha e Onde Perde

As 5 análises concordaram na avaliação honesta de eficiência:

### Onde o Cortex é Igual ou Superior aos Originais:
1. **Frescor do Índice e Latência Local (vs. `second-brain-mcp`):**
   - No `second-brain-mcp`, a busca semântica tem consistência eventual (leva de segundos a 2 minutos após editar uma nota, passando por Queue e Vectorize remoto).
   - No **Cortex**, a gravação e a indexação local ocorrem imediatamente, e uma busca em 20.000 chunks no SQLite + NumPy roda em **< 50 ms** sem rede.
2. **Qualidade de Busca em Português + Código (vs. `ai-memory` padrão):**
   - O `ai-memory` usa por padrão `all-MiniLM-L6-v2` (focado em inglês). Usando um modelo multilíngue (`intfloat/multilingual-e5-small` ou `bge-m3`), o Cortex lida melhor com notas bilíngues (PT-BR + termos técnicos em EN).
3. **Chunking Estrutural e Busca de Siglas Curtas (vs. `second-brain-mcp`):**
   - Preservação de hierarquia de headings (`#`, `##`, `###`) com *breadcrumb* e suporte a siglas de 2 caracteres (`IA`, `UX`, `QA`, `v2`).
4. **Exatidão Vetorial (até ~20k chunks):**
   - Produto escalar exato em NumPy sobre vetores normalizados não sofre perda de recall por aproximação (ANN), entregando exatamente o gabarito matemático.

### Onde o Cortex é Conscientemente Inferior (Trade-offs Assumidos):
1. **Sem Captura Passiva em 20+ CLIs (vs. `ai-memory`):**
   - Sem dezenas de hooks específicos de terminal, o Cortex registra o que o agente envia via tools MCP (com possibilidade futura de hook para 1 cliente de referência).
2. **Sem Grafo Multi-Hop de Entidades na v1 (vs. `ai-memory`):**
   - O `ai-memory` funde FTS5 + entidades + vizinhos de wikilinks. O Cortex foca em FTS5 + Vetores + Decaimento.
3. **Sem Disponibilidade Cloud 24/7 com a Máquina Desligada (vs. `second-brain-mcp`):**
   - Por ser *local-first* e custo zero, o acesso remoto via Cloudflare Tunnel na v3 depende de o PC estar ligado.

---

## 3. Pontos de Ouro Extraídos das 5 Análises

- **A conta real de RAM do NumPy:**
  - `20.000 chunks × 384 dimensões × 4 bytes (float32)` = **~29,3 MB de RAM** (ou **~78,1 MB** para 1024 dimensões).
  - Mantendo os vetores L2-normalizados na escrita, a similaridade de cosseno é apenas `scores = matrix @ query_vec`, executando em **2 a 8 ms** em CPU via BLAS/AVX2.
- **Armadilha dos prefixos na família E5 (`fastembed`):**
  - Modelos `intfloat/multilingual-e5-*` **exigem** prefixar documentos com `"passage: "` e consultas com `"query: "`. Esquecer isso degrada silenciosamente a busca semântica.
- **Armadilha do `paraphrase-multilingual-MiniLM-L12-v2`:**
  - Trunca silenciosamente em **128 tokens**, o que cortaria chunks de 250–350 tokens ao meio. Por isso, o modelo embarcado padrão deve suportar **512 tokens** (como `intfloat/multilingual-e5-small`).
- **O valor do Baseline antes do Vetor:**
  - No próprio benchmark do `ai-memory` (`LongMemEval-S`), o FTS5 puro bem configurado atinge `Hit@5` altíssimo (~0,95). Medir primeiro o baseline FTS5 na `v1` e só depois ligar o vetor + RRF na `v2` permite provar com números exatamente em quais tipos de pergunta (ex.: paráfrases e buscas cross-lingual PT<->EN) o vetor adiciona ganho real.
