"""Sanitization boundary: the only door through which external text may reach storage.

Every string that originates outside Cortex (a note body, an observation, a handoff summary)
must be turned into a :class:`Sanitized` value by :func:`sanitize` before it is written to
disk, committed to Git, indexed in SQLite or sent to an embedding model. Later layers declare
``Sanitized`` in their signatures, so the type checker rejects a raw ``str`` by construction.

Python cannot make a constructor truly private, so the guarantee is layered: pyright (strict)
rejects ``str`` where ``Sanitized`` is expected, and the constructor refuses to run unless it
is called from :func:`sanitize`.

The redaction rules are a port of ``companions/ai-memory-client/src/scrub.rs`` from
akitaonrails/ai-memory (MIT, see THIRD_PARTY_NOTICES.md), validated against the same shared
vectors (``tests/fixtures/sanitizer_vectors.json``). Known limits, kept on purpose:

* Pattern based. A secret with no recognisable shape or key name is not detected: entropy
  alone is not used because it produces too many false positives.
* Only the secret shapes below are covered (private-key blocks, GitHub, AWS, ``sk-``, Bearer
  tokens and ``token/secret/password/api_key`` fields). JWTs and connection strings are not.
* Python's ``re`` backtracks, unlike the linear-time Rust engine; see the notes on the
  private-key rules.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, final

__all__ = ["Sanitized", "redact", "sanitize"]

_CREDENTIAL: Final = "[REDACTED:credential]"
_PRIVATE_KEY: Final = "[REDACTED:private_key]"
_BEARER: Final = "[REDACTED:bearer]"
_SECRET_FIELD: Final = "[REDACTED:secret_field]"
_MARKER_PREFIX: Final = "[REDACTED:"
_KEY_BODY_CAP: Final = 16 * 1024

# --------------------------------------------------------------------------------------
# Step 1: characters whose only realistic use in captured text is hiding it.
# Removed *before* matching: a placeholder left inside a credential would split it out of
# reach of every pattern.
# --------------------------------------------------------------------------------------

# Control characters (Unicode Cc) except \t \n \r, bidi overrides/isolates, invisible math
# operators and Unicode tag characters. A tag run that completes an emoji flag sequence
# (U+1F3F4 + tag letters + cancel tag) is kept. A BOM is only dropped after the first char.
_STRIP_RE: Final = re.compile(
    r"(?P<keep>\U0001f3f4(?:[\U000e0020-\U000e007e]+\U000e007f)?)"
    r"|(?P<drop>[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f"
    r"\u202a-\u202e\u2066-\u2069\u2061-\u2064\U000e0000-\U000e007f\ufeff])"
)


def _strip_hidden(text: str) -> str:
    def repl(m: re.Match[str]) -> str:
        if m.group("keep") is not None:
            return m.group("keep")
        return "\ufeff" if m.group("drop") == "\ufeff" and m.start() == 0 else ""

    return _STRIP_RE.sub(repl, text)


# Unicode Default_Ignorable_Code_Point (UAX #44). These stay in the text (they are legitimate
# in emoji, Persian, Thai...), but must not hide a credential from the patterns.
_IGNORABLE_RE: Final = re.compile(
    "[\u00ad\u034f\u061c\u115f\u1160\u17b4\u17b5\u180b-\u180f\u200b-\u200f\u202a-\u202e"
    "\u2060-\u206f\u3164\ufe00-\ufe0f\ufeff\uffa0\ufff0-\ufff8"
    "\U0001bca0-\U0001bca3\U0001d173-\U0001d17a\U000e0000-\U000e0fff]"
)


# --------------------------------------------------------------------------------------
# Step 2: redaction rules, applied in order.
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Rule:
    pattern: re.Pattern[str]
    replace: Callable[[re.Match[str]], str]


def _const(marker: str) -> Callable[[re.Match[str]], str]:
    return lambda _m: marker


def _keep_prefix(marker: str) -> Callable[[re.Match[str]], str]:
    """Replace the match but keep the ``pre`` group, which is only a boundary."""
    return lambda m: m.group("pre") + marker


def _bearer(m: re.Match[str]) -> str:
    return m.group(1) + _BEARER


def _secret_field(m: re.Match[str]) -> str:
    value = m.group(3)
    # Too short to be a secret, or already redacted: leave the text byte for byte (idempotent).
    if len(value) < 6 or value.startswith(_MARKER_PREFIX):
        return m.group(0)
    return m.group(1) + m.group(2) + _SECRET_FIELD


def _unterminated_key(m: re.Match[str]) -> str:
    return _PRIVATE_KEY + m.group("end")


_RULES: Final[tuple[_Rule, ...]] = (
    # A complete private-key block (PEM, OpenSSH, PGP armor). The body is capped: an unbounded
    # ``.*?`` is quadratic when many headers have no end line (8000 headers took ~14 s). Real keys
    # are far below the cap (RSA-4096 is ~3.2 KB). A longer block falls through to the next rule,
    # which still redacts the body and leaves only the harmless end line.
    _Rule(
        re.compile(
            r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----"
            rf".{{0,{_KEY_BODY_CAP}}}?"
            r"-----END [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----",
            re.DOTALL,
        ),
        _const(_PRIVATE_KEY),
    ),
    # A block with no end line (cut off by a size cap or a truncated log), once at least one
    # key-body line follows the header. The line end after it is kept. Works on real newlines
    # and on JSON-escaped ones (a literal backslash + n).
    _Rule(
        re.compile(
            r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----"
            r"(?:(?:\r?\n|(?:\\r)?\\n)[ \t]*"
            r"(?:(?:Proc-Type|DEK-Info|Version|Comment|Hash):[^\r\n\\]*)?)*?"
            r"(?:(?:\r?\n|(?:\\r)?\\n)[ \t]*[A-Za-z0-9+/=]{16,}[ \t]*)+"
            r"(?P<end>\r?(?m:$)|[\"'\\…]|\.\.\.)"
        ),
        _unterminated_key,
    ),
    # GitHub tokens. Left-unanchored: a token glued onto a word by a stripped control
    # character must still be matched.
    _Rule(
        re.compile(r"(?:github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{20,})"),
        _const(_CREDENTIAL),
    ),
    # AWS access-key ids: a boundary or a percent-encoded byte before the exact 20-char shape.
    # A letter directly before ``AKIA`` stays unmatched on purpose: redacting it mid-word
    # would destroy ordinary uppercase text irreversibly.
    _Rule(
        re.compile(r"(?P<pre>\b|%[0-9A-Fa-f]{2})(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
        _keep_prefix(_CREDENTIAL),
    ),
    # Vendor ``sk-`` keys. A letter right before the prefix means it ends a word (``task-...``),
    # so only a letter may not start a match. A ``\b`` would also skip a key glued to ``_``,
    # a digit, a CJK character or a percent escape.
    _Rule(
        re.compile(r"(?P<pre>^|[^A-Za-z]|%[0-9A-Fa-f]{2})sk-[A-Za-z0-9_-]{16,}"),
        _keep_prefix(_CREDENTIAL),
    ),
    # ai-memory's own keys (aim_, ams_, amk_). Inherited so the shared vectors hold unchanged.
    _Rule(re.compile(r"(?:aim|ams|amk)_[A-Za-z0-9_-]{40,}"), _const(_CREDENTIAL)),
    _Rule(re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]{8,}"), _bearer),
    # ``token = "..."``, ``"password":"..."``, also inside JSON-escaped strings.
    _Rule(
        re.compile(
            r"(?i)\b(api[_-]?key|access[_-]?token|auth[_-]?token|token|secret|password)\b"
            r'((?:\\*")?\s*[:=]\s*)'
            r"(\\*\"[^\"\\\r\n]{6,}\\*\"|'[^'\r\n]{6,}'|[^\s,;]+)"
        ),
        _secret_field,
    ),
)


def _redact_through_invisibles(text: str, rule: _Rule) -> str:
    """Run ``rule`` with invisible characters removed, then replace each match's span in
    ``text``, invisible characters inside it included. A split credential is replaced whole."""
    shadow_chars: list[str] = []
    origin: list[int] = []
    for index, ch in enumerate(text):
        if _IGNORABLE_RE.match(ch) is None:
            shadow_chars.append(ch)
            origin.append(index)
    shadow = "".join(shadow_chars)

    out: list[str] = []
    copied = 0
    for m in rule.pattern.finditer(shadow):
        start = origin[m.start()] if m.start() < len(origin) else len(text)
        end = origin[m.end() - 1] + 1 if m.end() > m.start() else start
        replaced = rule.replace(m)
        # A match the rule keeps stays byte for byte, invisible characters and all.
        if start < copied or replaced == m.group(0):
            continue
        out.append(text[copied:start])
        out.append(replaced)
        copied = end
    out.append(text[copied:])
    return "".join(out)


def redact(text: str) -> str:
    """Return ``text`` with hidden characters stripped and known secret shapes replaced by
    ``[REDACTED:<kind>]`` markers. Idempotent. Prefer :func:`sanitize` at storage boundaries."""
    text = _strip_hidden(text)
    for rule in _RULES:
        # Through invisible characters first, so a split credential is replaced whole; then the
        # plain pass, which still finds a match that needs an invisible char as its boundary.
        if _IGNORABLE_RE.search(text) is not None:
            text = _redact_through_invisibles(text, rule)
        text = rule.pattern.sub(rule.replace, text)
    return text


# --------------------------------------------------------------------------------------
# The typed boundary.
# --------------------------------------------------------------------------------------

_MINT: Final = object()


@final
class Sanitized:
    """Text that has passed :func:`sanitize`. Immutable; cannot be built directly."""

    __slots__ = ("_text",)
    _text: str

    def __init__(self, text: str, *, _mint: object = None) -> None:
        if _mint is not _MINT:
            raise TypeError("Sanitized values are minted by cortex.sanitize.sanitize() only")
        object.__setattr__(self, "_text", text)

    @property
    def text(self) -> str:
        return self._text

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("Sanitized is immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("Sanitized is immutable")

    def __str__(self) -> str:
        return self._text

    def __repr__(self) -> str:
        return f"Sanitized({self._text!r})"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Sanitized) and self._text == other._text

    def __hash__(self) -> int:
        return hash(self._text)


def sanitize(text: str) -> Sanitized:
    """The single way to obtain a :class:`Sanitized` value from external text."""
    if not isinstance(text, str):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise TypeError(f"sanitize() expects str, got {type(text).__name__}")
    return Sanitized(redact(text), _mint=_MINT)
