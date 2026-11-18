#!/usr/bin/env python3
"""Tests for infra/scripts/redact_container_logs.py.

`mask_line` decides what may enter public CI logs, and until this file existed
nothing exercised it: the filter shipped as a heredoc inside
`.github/workflows/ci.yml`, so it could not be executed outside a failing CI run
and the bypass below reached review untested. It is the reason the filter is a
script with a `main()` now.

The bypass this suite pins: for
``{"level":"ERROR","message":"connect failed password=<value>"}`` the previous
key-value pattern matched the **outer** key ``message`` first, consumed the whole
quoted string as its value, and returned it unchanged because ``message`` is not
a credential key -- so the credential inside survived. Any nested error string,
stack trace or free-text field had the same hole. The first four cases in
`LEAK_CASES` are that shape.

Every fixture credential is assembled at import time by `_compose`, never written
down whole. The values are incidental -- what each case needs is a recognisable
credential in a given position at run time -- while a complete one in this file's
bytes is the exact thing secret scanners exist to flag, and a test file is the
last place it belongs. Composing keeps that shape without a scanner allowlist.

`LEAK_CASES` and `HARMLESS_CASES` are module-level data on purpose: a test is only
worth its green tick once it has been shown to fail against the implementation it
replaced, and the tables let the same inputs drive any implementation through its
`main()`. Pointing a harness at the pre-fix heredoc fails on every entry of
`LEAK_CASES`.

Every case is asserted on content, not on the internal call sequence, and the
harmless table is asserted byte-for-byte: `tokens_used`, `elapsed_ms`,
`grpc_code`, `trace_id`, `sha` and `IBEX_CONTEXT_TIMEOUT` are the values the
failure step exists to read, so over-masking is a defect too.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import time
import unittest
from pathlib import Path
from typing import Final

SCRIPT: Final = Path(__file__).with_name("redact_container_logs.py")
SPEC = importlib.util.spec_from_file_location("redact_container_logs", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("could not load redact_container_logs.py")
redact = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = redact
SPEC.loader.exec_module(redact)


def _compose(*parts: str) -> str:
    """Assemble a fixture credential from fragments.

    Each value below has to look like a credential at run time, and writing one
    down whole would put a credential-shaped literal in the tree -- what the
    scanners read, and what this file exists to prove gets masked. The scanner
    sees the fragments; the tests see the value.
    """
    return "".join(parts)


PASSWORD: Final = _compose("hunt", "er2")
API_KEY: Final = _compose("sk-", "live-", "abc123")
NESTED_API_KEY: Final = _compose("sk-", "live-", "9")
URL_PASSWORD: Final = _compose("s3c", "retpw")
DSN_PASSWORD: Final = _compose("ibex", "pw")
BEARER_TOKEN: Final = _compose("abcdef", "123456")
BASIC_TOKEN: Final = _compose("dXNlcjpw", "YXNzd29yZA", "==")
COOKIE_VALUE: Final = _compose("abc123", "def456")

# (label, input line, substrings that must not survive redaction).
LEAK_CASES: Final = (
    (
        "credential in a top-level JSON field",
        '{"level":"ERROR","password":"' + PASSWORD + '"}',
        (PASSWORD,),
    ),
    (
        "credential quoted inside a message string (the reported hole)",
        '{"level":"ERROR","message":"connect failed password=' + PASSWORD + '"}',
        (PASSWORD,),
    ),
    (
        "credential inside a nested error string",
        '{"level":"ERROR","error":"dial tcp: auth failed token=' + API_KEY + '"}',
        (API_KEY,),
    ),
    (
        "credential inside a nested escaped JSON document",
        '{"level":"ERROR","message":"upstream said {\\"api_key\\":\\"' + NESTED_API_KEY + '\\"}"}',
        (NESTED_API_KEY,),
    ),
    (
        "credential in a stack trace frame",
        '  File "login.py", line 7, in <module> login(password="' + PASSWORD + '")',
        (PASSWORD,),
    ),
    (
        "credential in a traceback exception line",
        "ValueError: provider rejected request (Authorization: Bearer " + API_KEY + ")",
        (API_KEY,),
    ),
    (
        "URL userinfo",
        "connect redis://default:" + URL_PASSWORD + "@redis:6379/0 failed",
        (URL_PASSWORD,),
    ),
    (
        "URL userinfo in a quoted DSN value",
        '{"dsn":"postgresql://ibex:' + DSN_PASSWORD + '@postgres:5432/ibex"}',
        (DSN_PASSWORD,),
    ),
    ("Bearer credential", "Authorization: Bearer " + BEARER_TOKEN, (BEARER_TOKEN,)),
    ("Basic credential", "Authorization: Basic " + BASIC_TOKEN, (BASIC_TOKEN,)),
    (
        "quoted JSON value with a space after the colon",
        '{"secret": "' + PASSWORD + '"}',
        (PASSWORD,),
    ),
    ("unquoted assignment", "password=" + PASSWORD, (PASSWORD,)),
    ("single-quoted assignment", "password='" + PASSWORD + "'", (PASSWORD,)),
    ("cookie header", "Cookie: session=" + COOKIE_VALUE + "; Path=/", (COOKIE_VALUE,)),
    (
        "set-cookie header",
        "Set-Cookie: ibex_session=" + COOKIE_VALUE + "; HttpOnly",
        (COOKIE_VALUE,),
    ),
    (
        "truncated line whose quote never closes",
        'password="' + PASSWORD,
        (PASSWORD,),
    ),
)

# Lines that must come back byte-for-byte. These are the diagnostics the v1
# failure step exists to read; masking any of them defeats the step.
HARMLESS_CASES: Final = (
    '{"level":"INFO","message":"context assembled","tokens_used":812,"elapsed_ms":41}\n',
    (
        '{"level":"WARN","message":"context assemble failed; fail-open","service":"proxy",'
        '"grpc_code":"DeadlineExceeded","elapsed_ms":1801,'
        '"trace_id":"4bf92f3577b34da6a3ce929d0e0e4736"}\n'
    ),
    (
        '{"level":"ERROR","message":"context assemble unexpected failure; fail-open",'
        '"elapsed_ms":1812}\n'
    ),
    "IBEX_CONTEXT_TIMEOUT=1800ms IBEX_CONTEXT_DEADLINE_MS=1800\n",
    "sha=abc123def tokens_used=812 elapsed_ms=41\n",
    '{"sha":"9f2c4d7e8a1b3c5d7e9f0a2b4c6d8e0f1a3b5c7d"}\n',
    '{"level":"INFO","message":"migrate: 42 migrations applied"}\n',
)


def mask(text: str) -> str:
    return redact.mask_line(text, redact.Stats())


def run_main(stdin: bytes, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        input=stdin,
        capture_output=True,
        check=False,
        timeout=120,
    )


class CredentialsAreMaskedAnywhere(unittest.TestCase):
    def test_every_credential_case_is_masked(self) -> None:
        for label, line, forbidden in LEAK_CASES:
            with self.subTest(label=label):
                masked = mask(line)
                for secret in forbidden:
                    # The fixture must carry the value it forbids: a composed
                    # literal that stopped landing in its line would make the
                    # absence check below pass for the wrong reason.
                    self.assertIn(secret, line, f"{label}: fixture lacks {secret!r}")
                    self.assertNotIn(secret, masked, f"{label}: {secret!r} survived")
                self.assertIn("[REDACTED]", masked, f"{label}: nothing was masked")

    def test_the_reported_hole_is_closed(self) -> None:
        line = '{"level":"ERROR","message":"connect failed password=' + PASSWORD + '"}'
        masked = mask(line)
        self.assertNotIn(PASSWORD, masked)
        # The outer key and the readable part of its message survive: this is a
        # surgical mask, not a dropped line.
        self.assertIn('"message"', masked)
        self.assertIn("connect failed", masked)
        self.assertEqual('{"level":"ERROR","message":"connect failed password=[REDACTED]"}', masked)

    def test_a_top_level_credential_keeps_its_key_and_quotes(self) -> None:
        self.assertEqual(
            '{"level":"ERROR","password":"[REDACTED]"}',
            mask('{"level":"ERROR","password":"' + PASSWORD + '"}'),
        )

    def test_url_userinfo_keeps_user_and_host(self) -> None:
        masked = mask("connect redis://default:" + URL_PASSWORD + "@redis:6379/0 failed")
        self.assertEqual("connect redis://default:[REDACTED]@redis:6379/0 failed", masked)

    def test_bearer_keeps_the_scheme_word(self) -> None:
        self.assertEqual(
            "Authorization: Bearer [REDACTED]", mask("Authorization: Bearer " + BEARER_TOKEN)
        )

    def test_a_cookie_header_is_masked_as_one_value(self) -> None:
        self.assertEqual(
            "Cookie: [REDACTED]; Path=/", mask("Cookie: session=" + COOKIE_VALUE + "; Path=/")
        )

    def test_an_unterminated_quote_is_masked_to_end_of_line(self) -> None:
        self.assertEqual('password="[REDACTED]', mask('password="' + PASSWORD))


class DiagnosticsSurvive(unittest.TestCase):
    def test_harmless_lines_are_byte_identical(self) -> None:
        for line in HARMLESS_CASES:
            with self.subTest(line=line):
                self.assertEqual(line, mask(line))

    def test_a_key_that_only_contains_token_is_not_a_credential(self) -> None:
        # `tokens_used` must not match `token`: invalidation is by whole token.
        self.assertFalse(redact.is_secret_key("tokens_used"))
        self.assertFalse(redact.is_secret_key("elapsed_ms"))
        self.assertFalse(redact.is_secret_key("sha"))
        self.assertFalse(redact.is_secret_key("grpc_code"))
        self.assertTrue(redact.is_secret_key("access_token"))
        self.assertTrue(redact.is_secret_key("IBEX_RUNTIME_DB_PASSWORD"))
        self.assertTrue(redact.is_secret_key("api_key"))


class CommandLine(unittest.TestCase):
    def test_it_masks_stdin_and_reports_a_count(self) -> None:
        stdin = (
            '{"level":"ERROR","message":"connect failed password=' + PASSWORD + '"}\n'
            '{"level":"INFO","message":"retrying","tokens_used":812}\n'
        ).encode()
        done = run_main(stdin, "proxy")
        self.assertEqual(0, done.returncode, done.stderr.decode())
        out = done.stdout.decode()
        self.assertNotIn(PASSWORD, out)
        self.assertIn('"tokens_used":812', out)
        self.assertRegex(
            out, r"\[redaction\] proxy: 2 line\(s\), [1-9][0-9]* sensitive value\(s\) masked"
        )

    def test_the_summary_never_carries_a_value(self) -> None:
        done = run_main(f"password={PASSWORD}\n".encode(), "memory")
        out = done.stdout.decode()
        self.assertNotIn(PASSWORD, out)
        self.assertIn("[redaction] memory: 1 line(s), 1 sensitive value(s) masked", out)

    def test_a_missing_service_name_does_not_fail_the_dump(self) -> None:
        done = run_main(f"password={PASSWORD}\n".encode())
        self.assertEqual(0, done.returncode)
        self.assertIn("[redaction] unknown: 1 line(s)", done.stdout.decode())

    def test_empty_input_reports_zero_without_failing(self) -> None:
        done = run_main(b"", "tei")
        self.assertEqual(0, done.returncode)
        self.assertIn(
            "[redaction] tei: 0 line(s), 0 sensitive value(s) masked", done.stdout.decode()
        )

    def test_non_utf8_bytes_do_not_stop_the_dump(self) -> None:
        # Container logs are not guaranteed to be UTF-8; a decode error must not
        # truncate the dump that explains a failed smoke.
        done = run_main(b"\xff\xfe level=ERROR password=" + PASSWORD.encode() + b"\n", "proxy")
        self.assertEqual(0, done.returncode, done.stderr.decode())
        out = done.stdout.decode()
        self.assertNotIn(PASSWORD, out)
        self.assertIn("1 line(s)", out)

    def test_every_leak_case_is_masked_through_main(self) -> None:
        stdin = "".join(f"{line}\n" for _, line, _ in LEAK_CASES).encode()
        out = run_main(stdin, "proxy").stdout.decode()
        for label, _, forbidden in LEAK_CASES:
            for secret in forbidden:
                self.assertNotIn(secret, out, f"{label}: {secret!r} survived the CLI")


class BoundedWork(unittest.TestCase):
    """The input is untrusted: a pathological line must not hang the runner."""

    def test_a_pathological_line_stays_linear(self) -> None:
        size = 400_000
        pathological = (
            "a:" * (size // 2),
            "a=a" * (size // 3),
            '"message":"' + "b" * size,
            "password=" + "9" * size,
            '"a="' * (size // 4),
        )
        stats = redact.Stats()
        started = time.monotonic()
        for line in pathological:
            redact.mask_line(line, stats)
        elapsed = time.monotonic() - started
        # Measured at ~0.6 s for the set on a laptop; a quadratic scanner takes
        # minutes here, which is the failure this bound is calibrated against.
        self.assertLess(
            elapsed, 10.0, f"redaction took {elapsed:.1f}s over {len(pathological)} lines"
        )
        # A long bare credential is masked rather than truncated at the bound.
        self.assertEqual("[REDACTED]", mask("password=" + "9" * size)[len("password=") :])


if __name__ == "__main__":
    unittest.main(verbosity=2)
