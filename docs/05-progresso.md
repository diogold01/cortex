# 05 — Progresso e Desvios do Plano

Registro por etapa: o que foi entregue, a evidência e onde a implementação divergiu do plano de [04](./04-roadmap-e-criterios-de-aceite.md).

---

## Etapa 1.1 — Setup + Fronteira de Sanitização — CONCLUÍDA (2026-11-21)

**Modelo usado:** Claude Sonnet 5.5 (High).

### Entregue
- Pacote `cortex-mcp` (módulo `cortex`) com `uv`, Python 3.12, `pytest`, `ruff` e `pyright` (strict, `src` e `tests`).
- `.gitattributes` (`* text=auto eol=lf`), `.gitignore` e `.python-version`.
- `src/cortex/sanitize.py`: `redact()`, `sanitize()` e o tipo `Sanitized`.
- `tests/test_sanitizer.py` + `tests/fixtures/sanitizer_vectors.json` (cópia byte a byte do upstream; proveniência em `THIRD_PARTY_NOTICES.md`).

### Evidência (Done When)
| Verificação | Resultado |
|---|---|
| `uv run pytest` | **151 passed** (~2,3 s) |
| Vetores compartilhados do `ai-memory` | 100% (68 credencial×invisível, 7 campos, 6 blocos de chave, 15 `unchanged`) |
| `ruff check` / `ruff format --check` / `pyright` (strict) | 0 erros |
| Mutação (10 mutantes no `sanitize.py`) | **10/10 pegos** |
| Caso patológico: 8000 cabeçalhos `BEGIN` sem `END` | ~14 s → **~1,9 s** após o teto de corpo |

### Desvios do plano (decisões conscientes)
1. **`Sanitized`, não `Sanitized[T]`.** Um genérico não traria nada na v1 (só existe texto). O tipo é `@final`, imutável e só nasce em `sanitize()`. Python não tem construtor privado: a garantia é em camadas (pyright rejeita `str` onde se espera `Sanitized` + guarda em runtime).
2. **Teto de 16 KiB no corpo da regra de bloco completo de chave privada.** O `re` do Python usa backtracking (o Rust do original é linear) e o `.*?` sem limite era quadrático. Bloco acima do teto cai na regra "sem linha END", que ainda redige o corpo (só a linha `END` sobra, sem segredo).
3. **O pacote raiz não reexporta nada.** Reexportar a função `sanitize` sobrescreveria o submódulo `cortex.sanitize` (`import cortex.sanitize as m` devolveria a função). Importar sempre de `cortex.sanitize`.
4. **Marcadores `[REDACTED:<tipo>]`** (`credential`, `private_key`, `bearer`, `secret_field`), alinhados às asserções do teste upstream.
5. **Regra `aim_/ams_/amk_` mantida** (chaves do próprio `ai-memory`), só para os vetores compartilhados passarem sem alteração.

### Limites conhecidos (não resolvidos de propósito)
- Detecção por padrão: segredo sem forma reconhecível e sem nome de campo não é detectado (entropia sozinha gera falsos positivos).
- Fora de cobertura: JWT e connection strings. Candidatos a vetores próprios se virarem requisito.
- Em `key = valor`, valores com menos de 6 caracteres são preservados (herdado do original).
- O teste de desempenho usa limite de 5 s sobre ~1,9 s medidos: margem de ~2,6×, pode oscilar em máquina lenta.

### Próxima etapa
**1.2 — Chunker Estrutural + Vault Git/Markdown**, recomendado **Gemini 4 Hydrogen — XHigh**.
