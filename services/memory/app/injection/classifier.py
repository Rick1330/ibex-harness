"""Deterministic prompt-injection heuristic for the memory write path (W10.4).

Memory content is untrusted input (`engineering/SECURITY.md` §7): a stored memory
is retrieved and injected into a model's context later, so content that reads
like an *instruction* is a delivery vehicle, not a fact. This module is the
write-time gate. It reports risk so the pipeline can quarantine the memory for
human review instead of storing it as data that will be trusted on retrieval.

Design constraints, each one deliberate:

* **Deterministic.** Same input, same verdict, forever. No model, no network,
  no clock, no locale-dependent matching — a quarantine must be reproducible in
  a test and defensible in a review.
* **Dependency-free.** `re` and `unicodedata` from the standard library only.
* **Fail-closed.** A rule match quarantines. Human review is the resolution
  path (SECURITY.md §7.5). A false positive costs one review; a false negative
  costs an injected instruction in a live prompt.
* **Readable.** Every rule is a stable name, a compiled pattern, and a one-line
  rationale, held in one explicit ordered tuple. First match wins, so tuple
  order is precedence order and part of the contract.

This is a first-line filter, not a safety proof. Keyword heuristics cannot see
through translation, homoglyphs, base64, or paraphrase, and the rules below are
deliberately narrow to keep ordinary prose out of the quarantine queue. The
primary defence stays where SECURITY.md puts it: memory is framed as data on
retrieval, and never as instructions.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

#: ``quarantine_reason`` reported by the write pipeline when this classifier
#: fires. Stable contract: it is what the response ``meta.message`` and the
#: ``quarantined`` lifecycle event are derived from.
INJECTION_QUARANTINE_REASON = "prompt_injection_heuristic"

#: Returned as the reason when no rule matches, so callers never see ``None``.
NO_RULE = ""

# Zero-width characters are invisible to a human reviewer and are used to split
# keywords ("ig<ZWSP>nore"). Removed before matching; harmless in prose.
_ZERO_WIDTH = str.maketrans(dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff")))

# Verbs that reassign what the model is.
_OVERRIDE_VERB = r"(?:ignore|disregard|forget|override|bypass)"
# Words that point at context the attacker wants discarded.
_PRIOR_MARKER = r"(?:previous|prior|above|earlier|preceding|foregoing|system|initial|original|all)"
# The thing being discarded. Required, so "ignore the previous cache" is clean.
_INSTRUCTION_NOUN = r"(?:instructions?|prompts?|directives?|rules|guidelines)"
# Verbs that ask the model to hand back its own framing.
_LEAK_VERB = r"(?:reveal|show|print|repeat|output|disclose|dump|leak)"
# Qualifiers that make the leaked noun the model's own framing rather than any
# document: "the build instructions" must not match, "the system prompt" must.
_LEAK_QUALIFIER = r"(?:hidden|system|original|initial|secret|full|exact|internal|current)"

# "You are now ..." assigns a role. These continuations describe capability or
# state instead ("You are now able to export reports"), so they are excepted.
_BENIGN_ROLE_CONTINUATION = (
    r"(?!\s+(?:able|unable|ready|allowed|required|responsible|part\b|on\b|in\b|at\b|using\b))"
)

# A role label is spoofing only at line start: "The system: production" is prose.
_ROLE_LABEL_LINE = r"^[ \t]*(?:system|assistant)\s*:"

# Chat-template and tool-call markup, as literal alternatives (no interpolation).
_TEMPLATE_MARKUP = (
    r"<(?:/?system|/?assistant)>"
    r"|\[/?INST\]"
    r"|<<\s*/?SYS\s*>>"
    r"|<\|(?:im_start|im_end|system|assistant|user|endoftext)\|>"
)
_TOOL_MARKUP = (
    r"</?(?:tool_call|function_call|tool_use|function)>"
    r"|<\|(?:tool_call|python_tag)\|>"
    r'|"tool_calls"\s*:'
)


@dataclass(frozen=True, slots=True)
class InjectionRule:
    """One ordered heuristic. ``name`` is the reason reported on a match."""

    name: str
    rationale: str
    pattern: re.Pattern[str]


#: Ordered rule list. First match wins, so this order is the precedence order:
#: specific override language is reported before the broader header and markup
#: rules, and the broadest rule ("mentions the system prompt") comes last.
RULES: tuple[InjectionRule, ...] = (
    InjectionRule(
        name="instruction_override",
        rationale=(
            "Imperative that cancels the running instructions, qualified by the "
            "context it wants discarded: 'ignore previous instructions'."
        ),
        pattern=re.compile(
            rf"\b{_OVERRIDE_VERB}\s+(?:\w+\s+){{0,3}}?{_PRIOR_MARKER}\s+"
            rf"(?:\w+\s+){{0,2}}?{_INSTRUCTION_NOUN}\b",
            re.IGNORECASE,
        ),
    ),
    InjectionRule(
        name="context_dismissal",
        rationale=(
            "Bare dismissal of what came before: 'disregard the above'. The "
            "lookahead requires a clause boundary so 'ignore the above error' "
            "in a bug note stays clean."
        ),
        pattern=re.compile(
            r"\b(?:disregard|ignore|forget)\s+(?:the\s+|all\s+|everything\s+)?"
            r"(?:above|foregoing|preceding)\b(?=\s*(?:$|[,.!:;]|\band\b|\bthen\b))",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    InjectionRule(
        name="instruction_disclosure",
        rationale=(
            "Asks the model to emit its own framing instead of answering: "
            "'reveal your instructions'. A qualified noun is required, so "
            "'show the build instructions' stays clean."
        ),
        pattern=re.compile(
            rf"\b{_LEAK_VERB}\s+(?:me\s+)?(?:your|the|its|all)\s+"
            rf"(?:{_LEAK_QUALIFIER}\s+)*(?:system prompt|instructions?|prompts?|directives?)\b",
            re.IGNORECASE,
        ),
    ),
    InjectionRule(
        name="role_reassignment",
        rationale=(
            "Hands the model a new identity or rule set: 'you are now'. "
            "Capability phrasing ('you are now able to ...') is excepted."
        ),
        pattern=re.compile(
            rf"\byou are now\b{_BENIGN_ROLE_CONTINUATION}",
            re.IGNORECASE,
        ),
    ),
    InjectionRule(
        name="role_label_spoof",
        rationale=(
            "Forges a chat role header at the start of a line: 'system:' or "
            "'assistant:'. Line-anchored, so 'The system: production' is prose."
        ),
        pattern=re.compile(_ROLE_LABEL_LINE, re.IGNORECASE | re.MULTILINE),
    ),
    InjectionRule(
        name="chat_template_markup",
        rationale=(
            "Raw chat-template control tokens that a model reads as turns: "
            "'<system>', '<|im_start|>', '[INST]', '<<SYS>>'."
        ),
        pattern=re.compile(_TEMPLATE_MARKUP, re.IGNORECASE),
    ),
    InjectionRule(
        name="tool_call_markup",
        rationale=(
            "Tool-call markup that would make stored text look like a tool "
            "invocation: '<tool_call>', '<|python_tag|>', '\"tool_calls\":'."
        ),
        pattern=re.compile(_TOOL_MARKUP, re.IGNORECASE),
    ),
    InjectionRule(
        name="system_prompt_reference",
        rationale=(
            "Any reference to the system prompt or system message. Broadest "
            "rule, so it runs last; a human decides whether the mention is "
            "documentation or an attempted override."
        ),
        pattern=re.compile(r"\b(?:system|developer)\s+(?:prompt|message)\b", re.IGNORECASE),
    ),
)


def normalize(content: str) -> str:
    """Fold the cheap obfuscations a keyword rule would otherwise miss.

    NFKC folds full-width and compatibility characters (``ｓｙｓｔｅｍ：`` →
    ``system:``), CRLF becomes LF so ``^`` anchoring is line-stable, and
    zero-width characters are dropped so a split keyword still matches. The
    text is not lowercased: every pattern is case-insensitive already.
    """
    folded = unicodedata.normalize("NFKC", content)
    return folded.replace("\r\n", "\n").replace("\r", "\n").translate(_ZERO_WIDTH)


def classify(content: str) -> tuple[bool, str]:
    """Return ``(risk, rule_name)`` for one memory content string.

    ``risk`` is True when instruction-shaped content was found; ``rule_name`` is
    then the name of the first matching rule, and :data:`NO_RULE` otherwise.
    The verdict depends only on the argument.
    """
    text = normalize(content)
    if not text.strip():
        return False, NO_RULE
    for rule in RULES:
        if rule.pattern.search(text):
            return True, rule.name
    return False, NO_RULE
