"""Sanitizer tests.

``test_vector_*`` replay the shared vectors of akitaonrails/ai-memory
(``tests/fixtures/sanitizer_vectors.json``) with the same assertions its own Rust test uses
(``shared_sanitizer_vectors_hold``). The remaining tests are specific to Cortex.
"""

import json
import time
from pathlib import Path
from typing import Any, cast

import pytest

from cortex.sanitize import Sanitized, redact, sanitize

VECTORS_PATH = Path(__file__).parent / "fixtures" / "sanitizer_vectors.json"
# Windows defaults to cp1252: the fixture holds raw UTF-8 (CJK), so say so explicitly.
VECTORS: dict[str, Any] = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))


def _strings(key: str) -> list[str]:
    return cast("list[str]", VECTORS[key])


def _fields() -> list[dict[str, Any]]:
    return cast("list[dict[str, Any]]", VECTORS["credential_fields"])


def _blocks() -> list[dict[str, Any]]:
    return cast("list[dict[str, Any]]", VECTORS["key_blocks"])


def _invisible_id(s: str) -> str:
    return "+".join(f"U{ord(c):04X}" for c in s)


# --------------------------------------------------------------------------------------
# Shared vectors (ai-memory)
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("invisible", _strings("invisibles"), ids=_invisible_id)
@pytest.mark.parametrize("secret", _strings("credentials"), ids=lambda s: s[:8])
def test_vector_credential_split_by_an_invisible_character_is_redacted(
    secret: str, invisible: str
) -> None:
    head, tail = secret[: len(secret) // 2], secret[len(secret) // 2 :]
    out = redact(f"key {head}{invisible}{tail} end")
    assert "[REDACTED:" in out
    assert head not in out
    assert tail not in out
    assert out.startswith("key ")
    assert out.endswith(" end")


@pytest.mark.parametrize("field", _fields(), ids=lambda f: str(f["input"])[:32])
def test_vector_credential_fields(field: dict[str, Any]) -> None:
    out = redact(field["input"])
    assert "[REDACTED:" in out
    assert field["secret"] not in out
    for kept in field.get("kept", []):
        assert kept in out


@pytest.mark.parametrize("block", _blocks(), ids=lambda b: str(b["input"])[:40])
def test_vector_private_key_blocks(block: dict[str, Any]) -> None:
    out = redact(block["input"])
    assert "[REDACTED:private_key]" in out
    assert VECTORS["key_body_line"] not in out
    for kept in block["kept"]:
        assert kept in out


@pytest.mark.parametrize("text", _strings("unchanged"), ids=lambda s: s[:30])
def test_vector_unchanged_text_is_not_corrupted(text: str) -> None:
    assert redact(text) == text


def test_vector_credentials_alone_are_redacted_whole() -> None:
    for secret in _strings("credentials"):
        assert redact(secret) == "[REDACTED:credential]"


# --------------------------------------------------------------------------------------
# Hidden text
# --------------------------------------------------------------------------------------


def test_characters_that_hide_text_are_stripped() -> None:
    hidden = "".join(chr(0xE0000 + ord(c)) for c in "hidden note")
    assert redact(f"visible{hidden} text") == "visible text"
    assert redact("a\u2062b\ufeffc") == "abc"
    assert redact("a\x07b\x1b[0mc") == "ab[0mc"


def test_a_flag_start_without_cancel_tag_loses_its_tags() -> None:
    assert redact("\U0001f3f4\U000e0067\U000e0062 x") == "\U0001f3f4 x"


def test_newlines_and_tabs_survive() -> None:
    assert redact("a\tb\r\nc\nd") == "a\tb\r\nc\nd"


# --------------------------------------------------------------------------------------
# Other secret shapes
# --------------------------------------------------------------------------------------


def test_bearer_token_is_redacted_and_header_kept() -> None:
    out = redact("Authorization: Bearer abcdefghijklmnop1234")
    assert out == "Authorization: Bearer [REDACTED:bearer]"


@pytest.mark.parametrize(
    ("line", "secret"),
    [
        ("password = hunter2hunter2", "hunter2hunter2"),
        ("API_KEY: 'abcdef123456'", "abcdef123456"),
        ('SECRET="abcdef123456"', "abcdef123456"),
    ],
)
def test_key_value_secrets_are_redacted_keeping_the_key_name(line: str, secret: str) -> None:
    out = redact(line)
    assert "[REDACTED:secret_field]" in out
    assert secret not in out
    assert out.lower().startswith(line.split("=")[0].split(":")[0].strip().lower())


def test_short_field_values_are_left_alone() -> None:
    assert redact("token=abc") == "token=abc"


# --------------------------------------------------------------------------------------
# PT-BR / Markdown content must pass through untouched
# --------------------------------------------------------------------------------------

PLAIN_NOTES = [
    "Decisão: usar SQLite com FTS5 para busca de IA e UX no projeto v2.",
    "## Arquitetura\n\nO índice é derivado; apagar o .sqlite e reindexar reconstrói tudo.",
    "```python\ndef task_key(sk: int) -> str:\n    return f'task-{sk}'\n```",
    "Veja task-release-lines e disk-reclaimable-pct (não são chaves).",
    "A senha deve ficar fora do Git; use um gerenciador de segredos.",
]


@pytest.mark.parametrize("note", PLAIN_NOTES, ids=lambda s: s[:30])
def test_ordinary_notes_are_not_modified(note: str) -> None:
    assert redact(note) == note


# --------------------------------------------------------------------------------------
# Idempotence
# --------------------------------------------------------------------------------------


def _all_vector_inputs() -> list[str]:
    inputs = list(_strings("credentials")) + _strings("unchanged")
    inputs += [str(f["input"]) for f in _fields()]
    inputs += [str(b["input"]) for b in _blocks()]
    return inputs


@pytest.mark.parametrize("text", _all_vector_inputs(), ids=lambda s: s[:30])
def test_redaction_is_idempotent(text: str) -> None:
    once = redact(text)
    assert redact(once) == once


# --------------------------------------------------------------------------------------
# The typed boundary
# --------------------------------------------------------------------------------------


def test_sanitize_returns_a_sanitized_value_with_the_redacted_text() -> None:
    s = sanitize("key sk-leak-0123456789abcdef0123 end")
    assert isinstance(s, Sanitized)
    assert s.text == "key [REDACTED:credential] end"
    assert str(s) == s.text


def test_sanitized_cannot_be_built_directly() -> None:
    with pytest.raises(TypeError):
        Sanitized("sk-leak-0123456789abcdef0123")
    with pytest.raises(TypeError):
        Sanitized("raw", _mint=object())


def test_sanitized_is_immutable() -> None:
    s = sanitize("hello")
    with pytest.raises(AttributeError):
        s.text = "x"  # type: ignore[misc]  # pyright: ignore[reportAttributeAccessIssue]
    with pytest.raises(AttributeError):
        s._text = "x"  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(AttributeError):
        del s._text  # pyright: ignore[reportPrivateUsage]


def test_sanitized_equality_and_hash_follow_the_text() -> None:
    assert sanitize("a") == sanitize("a")
    assert hash(sanitize("a")) == hash(sanitize("a"))
    assert sanitize("a") != sanitize("b")
    assert sanitize("a") != "a"


def test_sanitize_rejects_non_text() -> None:
    with pytest.raises(TypeError):
        sanitize(b"bytes")  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
    with pytest.raises(TypeError):
        sanitize(sanitize("already"))  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]


# --------------------------------------------------------------------------------------
# Python's `re` backtracks (the Rust original is linear-time): guard against slow inputs.
# --------------------------------------------------------------------------------------

_SLOW_LIMIT_SECONDS = 5.0


def _timed(text: str) -> float:
    started = time.perf_counter()
    redact(text)
    return time.perf_counter() - started


def test_large_plain_text_is_fast() -> None:
    assert _timed("Linha de nota comum, sem segredos.\n" * 20_000) < _SLOW_LIMIT_SECONDS


def test_many_unterminated_key_headers_stay_bounded() -> None:
    # With an unbounded `.*?` this input took ~14 s (quadratic); the body cap keeps it linear.
    assert _timed("-----BEGIN PRIVATE KEY-----\n" * 8_000) < _SLOW_LIMIT_SECONDS


def test_long_key_body_is_fast_and_redacted() -> None:
    body = "\n".join("A" * 64 for _ in range(5_000))
    text = f"-----BEGIN RSA PRIVATE KEY-----\n{body}\n"
    assert _timed(text) < _SLOW_LIMIT_SECONDS
    assert "A" * 16 not in redact(text)


def test_block_larger_than_the_cap_still_loses_its_body() -> None:
    body = "\n".join("A" * 64 for _ in range(400))  # ~26 KB, above the 16 KiB cap
    text = f"before\n-----BEGIN RSA PRIVATE KEY-----\n{body}\n-----END RSA PRIVATE KEY-----\nafter"
    out = redact(text)
    assert "A" * 16 not in out
    assert "[REDACTED:private_key]" in out
    assert out.startswith("before\n")
    assert out.endswith("after")
