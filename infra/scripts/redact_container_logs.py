#!/usr/bin/env python3
"""Redact credentials from container logs before they reach public CI output.

The v1 profile's failure step dumps `proxy`, `context`, `memory`, `tei`,
`migrate` and `bootstrap` logs into the CI job output, and those logs are public.
The Go services redact by attribute key only (`packages/logger/redact.go`
replaces the values of token/password/secret/authorization/... keys), so a
credential embedded in a message, an error string or a stack trace sits outside
that guarantee, and every Python service sits outside it entirely. This filter is
defence in depth on top of that, and it lives here rather than in a heredoc
inside the workflow because a filter that decides what may enter a public log is
code, and code that cannot be executed cannot be tested
(`infra/scripts/test_redact_container_logs.py`).

Usage:

    python3 infra/scripts/redact_container_logs.py <service> < container.log

Reads stdin line by line, writes the masked text to stdout, then one summary
line: ``[redaction] <service>: <lines> line(s), <n> sensitive value(s) masked``.
It prints a count of what it masked, never a value.

What is masked:

1. **URL userinfo** -- ``scheme://user:<password>@host``.
2. **Credential assignments anywhere in the line** -- ``password=...``,
   ``"api_key": "..."``, ``\\"token\\":\\"...\\"`` inside an escaped JSON string, a
   ``Cookie: session=...`` header, or a credential quoted inside somebody else's
   value. The scan is position-based and never consumes a value it did not mask:
   a credential does not stop being a credential because it is quoted inside a
   ``message`` field.
3. **``Bearer``/``Basic``/``Digest`` credentials**, where the scheme word itself
   survives and only the token behind it is replaced.
4. **Long opaque runs on a line that also carried a credential** -- a hash or a
   random identifier next to a masked secret. A long identifier on a line with
   no credential is evidence, not a secret and is left alone.

What is deliberately left alone, because it is what the failure step exists to
read: ``tokens_used``, ``elapsed_ms``, ``grpc_code``, ``trace_id``, ``sha`` and
``IBEX_CONTEXT_TIMEOUT``-style keys. A key is matched as one whole token split on
``_ - .``, so ``access_token`` and ``IBEX_RUNTIME_DB_PASSWORD`` are credentials
while ``tokens_used`` and ``sha`` are not.

The input is untrusted. Every pattern here is bounded and unambiguous, the
scanner only moves forward, and the key and its separator are matched on their
own -- a value is read only at a key that names a credential. Redaction is
therefore linear in the size of the line, whatever the line contains: a
pathological line cannot hang the runner.
"""

from __future__ import annotations

import re
import sys
from typing import Final

REDACTED: Final = "[REDACTED]"

# A key is matched as one whole token and then split on _ - . so that
# `access_token` and `IBEX_RUNTIME_DB_PASSWORD` are credentials while
# `tokens_used` and `sha` are not. Substring matching would mask the very fields
# this step exists to read.
_KEY: Final = r"[A-Za-z0-9_.-]{1,80}"
# The negative lookbehind is what keeps the scan linear: a position inside a word
# run fails in O(1) instead of re-attempting the key pattern, so a megabyte of
# `aaaa...` costs one attempt rather than one per character.
_KEY_START: Final = r"(?<![A-Za-z0-9_.-])"
# A quote may itself be escaped (`\"password\":`), which is how an error string
# carrying a nested JSON document appears inside a JSON log line.
_WRAP: Final = r'(?P<wrap>\\?["\']?)'
_SEP: Final = r"(?P<sep>\s*[=:]\s*)"
# The key, its wrapper and its separator -- and nothing more. The value is
# deliberately not part of this pattern. `is_secret_key` is decided from the key
# alone, so a key that names no credential must not pay for reading a value at
# all; and because the scan resumes at `end("sep")`, it resumes *inside* the
# value, which is how a credential quoted inside somebody else's field is still
# reached (`{"message":"... password=<value>"}`).
KEY_SEP: Final = re.compile(_KEY_START + "(?P<key>" + _KEY + ")" + _WRAP + _SEP)

# The value readers, tried in this order at a key that names a credential: a
# properly quoted value, then a quote that never closes on this line (a truncated
# `docker logs --tail` line must still be masked), then a bare run.
#
# The quoted form opens on `"`, `'`, `\"` or `\'` and closes on the same spelling
# (backreference), so `\"x\"` closes on `\"`; `(?:\\.|[^"'\\])*` is deterministic
# at every character -- a backslash matches the first branch and nothing else
# does -- so it cannot backtrack catastrophically. Reading it before the bare run
# is what keeps an escaped quote reading as a quote now that a bare run may
# contain a backslash.
QUOTED_VALUE: Final = re.compile(r'(?P<quote>\\?["\'])(?:\\.|[^"\'\\])*(?P=quote)')
TRUNCATED_VALUE: Final = re.compile(r'(?P<open>\\?["\'])[^\n]*')
# The bare form is limited to eight characters, and the limit is load-bearing: a
# greedy first attempt would re-read the run at every key on the line
# (`a=a=a=...`) and the cost would be quadratic in the length of the line. The
# span is extended over the rest of the run with BARE_TAIL, which is linear.
#
# A backslash is an ordinary character in an unquoted shell or JSON-adjacent
# value, so it is allowed inside the run -- as a unit with the character it
# escapes, because `\"` is how an unquoted value carries a quote. Excluding it
# masked a value only up to its first backslash, and a run that *began* with one
# matched nothing at all, so the whole assignment failed and the line passed
# through unmasked: a disclosure, not a cosmetic miss.
#
# The two branches are disjoint -- a backslash matches only the first, and the
# class excludes it -- so the run is deterministic at every character and cannot
# backtrack, and a lone backslash at end of line simply ends the run.
BARE_VALUE: Final = re.compile(r"""(?:\\.|[^\s,;&"'\\]){1,8}""")
# The maximal run the bounded bare form stopped in the middle of.
BARE_TAIL: Final = re.compile(r"""(?:\\.|[^\s,;&"'\\])*""")
# `(?i)` makes the scheme token case-insensitive and folds the class with it, so
# the letter range is written once: `a-z` already covers `A-Z` here.
SCHEME: Final = re.compile(r"(?i)\b(bearer|basic|digest)\s+[a-z0-9._~+/=-]{4,}")
URL_CRED: Final = re.compile(r"(://[^:/@\s]*:)([^@\s/]+)(@)")
OPAQUE: Final = re.compile(r"\b(?:[A-Fa-f0-9]{32,}|[A-Za-z0-9+/=_-]{40,})\b")
HEX_RUN: Final = re.compile(r"[0-9a-fA-F]{32,}")
KEY_TOKEN: Final = re.compile(_KEY)

SECRET_PARTS: Final = frozenset(
    {
        "authorization",
        "bearer",
        "cookie",
        "token",
        "password",
        "passwd",
        "secret",
        "apikey",
        "credential",
    }
)
SECRET_PAIRS: Final = (("api", "key"), ("private", "key"))
# The scheme word is not the secret, so it survives: SCHEME has already masked
# the token that follows it.
SCHEME_WORDS: Final = frozenset({"bearer", "basic", "digest", "token", "[redacted]"})
# The quote spellings a value may open with, longest first, so an escaped quote --
# how a nested JSON document appears inside an error string -- reads as one spelling
# rather than as a backslash followed by a quote.
QUOTE_SPELLINGS: Final = ('\\"', "\\'", '"', "'")


class Stats:
    """Counts a report may carry. Never a value: the report is public output."""

    __slots__ = ("lines", "masked")

    def __init__(self) -> None:
        self.lines = 0
        self.masked = 0


def is_secret_key(name: str) -> bool:
    """True when `name` names a credential, judged token by token."""
    parts = [part for part in re.split(r"[_.-]+", name.lower()) if part]
    if any(part in SECRET_PARTS for part in parts):
        return True
    return any(first in parts and second in parts for first, second in SECRET_PAIRS)


def opening_quote(value: str) -> str:
    """The quote spelling `value` opens with, or "" when the value is not quoted."""
    for spelling in QUOTE_SPELLINGS:
        if value.startswith(spelling):
            return spelling
    return ""


def closing_quote_present(value: str, quote: str) -> bool:
    """Whether `value` ends with the same spelling that opened it.

    A value with no room for a closer -- a lone ``"``, from a line cut short by
    ``docker logs --tail`` -- does not close, so it is masked as an opener with no
    terminator instead of gaining a quote it never had.
    """
    if len(value) < 2 * len(quote):
        return False
    return value.endswith(quote)


def is_scheme_word(value: str) -> bool:
    """Whether `value` is a scheme word, which survives because it is not the secret.

    ``authorization: Bearer <token>`` names a scheme, and SCHEME has already masked
    the token behind it: masking the word too would delete what the line reports.
    """
    return value.strip("\"'\\").lower() in SCHEME_WORDS


def mask_value(value: str) -> str:
    """Replace `value` while keeping its quoting, so a masked line still reads.

    The quote spelling is kept as written, including an escaped ``\\"`` from a
    nested JSON document, so a masked line still shows the shape of what was
    masked without the value.
    """
    quote = opening_quote(value)
    if not quote:
        return REDACTED
    if closing_quote_present(value, quote):
        return f"{quote}{REDACTED}{quote}"
    # An opening quote with no matching close: keep the opener, drop the rest.
    return f"{quote}{REDACTED}"


def end_of_value(text: str, start: int) -> int:
    """End offset of the value beginning at `start`, or `start` when none does.

    Ordered rather than alternated so the preference is visible: a quoted value,
    then an opener with no closer on this line, then a bare run. A bare run is
    extended to the end of the run here, at the one key that is being masked, so
    the bound never costs a second pass.
    """
    quoted = QUOTED_VALUE.match(text, start)
    if quoted is not None:
        return quoted.end()
    truncated = TRUNCATED_VALUE.match(text, start)
    if truncated is not None:
        return truncated.end()
    bare = BARE_VALUE.match(text, start)
    if bare is None:
        return start
    tail = BARE_TAIL.match(text, bare.end())
    return tail.end() if tail is not None else bare.end()


def mask_assignments(text: str, stats: Stats) -> str:
    """Mask credential assignments anywhere in `text`, including nested values.

    Position-based on purpose. A single `re.sub` over a key/value pattern cannot
    do this correctly: for ``{"message":"connect failed password=hunter2"}`` it
    matches the outer key ``message``, hands the whole quoted value back
    unchanged because ``message`` is not a credential, and then resumes scanning
    *after* it -- so the credential inside survives. Here a non-credential key
    consumes only its own key and separator, and the scan continues inside the
    value.

    That split is also what keeps the scan linear: a value is read only at a key
    that names a credential, so no stretch of text is walked twice. Consuming the
    value from the key pattern instead made an escaped line quadratic, because
    the value was matched and discarded at every key and then re-scanned.
    """
    out: list[str] = []
    pos = 0
    length = len(text)
    while pos < length:
        found = KEY_SEP.search(text, pos)
        if found is None:
            out.append(text[pos:])
            break
        key_end = found.end("sep")
        secret = is_secret_key(found.group("key"))
        value_end = end_of_value(text, key_end) if secret else key_end
        if value_end == key_end:
            # Nothing to mask: consume the key and separator only, so the next
            # search starts inside the value. The separator is at least one
            # character, so this always advances; max() is the invariant that
            # keeps it true if that ever changes.
            out.append(text[pos:key_end])
            pos = max(key_end, pos + 1)
            continue
        if is_scheme_word(text[key_end:value_end]):
            # `authorization: Bearer <token>`: SCHEME masks the token.
            out.append(text[pos:value_end])
            pos = value_end
            continue
        out.append(text[pos:key_end])
        out.append(mask_value(text[key_end:value_end]))
        stats.masked += 1
        pos = value_end
    return "".join(out)


def mask_opaque(match: re.Match[str], stats: Stats) -> str:
    run = match.group(0)
    looks_secret = bool(HEX_RUN.fullmatch(run)) or (
        len(run) >= 40
        and any(char.isupper() for char in run)
        and any(char.islower() for char in run)
        and any(char.isdigit() for char in run)
    )
    if not looks_secret:
        # A long identifier is evidence, not a credential.
        return run
    stats.masked += 1
    return REDACTED


def mask_line(line: str, stats: Stats) -> str:
    """Mask one line. Linear in `len(line)`."""
    masked, count = URL_CRED.subn(r"\1" + REDACTED + r"\3", line)
    stats.masked += count
    masked = mask_assignments(masked, stats)
    masked, count = SCHEME.subn(lambda match: match.group(1) + " " + REDACTED, masked)
    stats.masked += count
    if any(is_secret_key(match.group(0)) for match in KEY_TOKEN.finditer(masked)):
        # An opaque run on a line that carried a credential is masked too; a
        # hash on a line without one is left alone.
        masked = OPAQUE.sub(lambda match: mask_opaque(match, stats), masked)
    return masked


def _reconfigure_utf8(stream: object) -> None:
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(errors="replace")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    service = args[0] if args else "unknown"
    stats = Stats()
    _reconfigure_utf8(sys.stdin)
    _reconfigure_utf8(sys.stdout)
    for raw in sys.stdin:
        stats.lines += 1
        sys.stdout.write(mask_line(raw, stats))
    sys.stdout.write(
        f"[redaction] {service}: {stats.lines} line(s), "
        f"{stats.masked} sensitive value(s) masked\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
