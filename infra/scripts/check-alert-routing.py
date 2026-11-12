#!/usr/bin/env python3
"""Static gate: every alert severity in the rule tree reaches a real receiver.

Reads every alert rule under infra/monitoring/prometheus/rules (recursively)
and the routing tree in infra/monitoring/alertmanager/alertmanager.yml, then
fails when:

  1. a rule severity is matched by no route,
  2. a route names a receiver that is not defined,
  3. a receiver has no webhook_configs (a receiver that would silently drop),
  4. a rule alert carries no severity label (a `severity:` under `annotations:`
     is prose, not a routing label, and does not count),
  5. a direct child of the root route has no severity matcher, so it assigns no
     severity while looking like an assignment, or
  6. the null receiver `local-null` reappears anywhere in the file.

Severity reachability is decided only by severity matchers. A route that selects
on other labels (`service=proxy` and nothing else) is not evidence that a
severity is routed: this gate cannot evaluate those labels, and pretending
otherwise would make every severity look routed.

The gate also runs a self-test over small fixtures before it exits, so the two
edges above (a `service=`-only route, and a `severity:` in an annotation) are
proven to still fail. A gate that cannot fail is not a gate.

Standard library only, on purpose: this gate runs on a bare CI runner and in
`make repo-guards`, so it must not add a YAML dependency. The parser therefore
understands exactly the subset of YAML these two file families use (block
mappings, block sequences, `matchers:`/`match:` lists, and inline flow lists of
matchers) and fails loudly on a shape it does not understand instead of
guessing. It is a line-oriented scanner rather than a set of regexes: every line
is classified once, so no pattern can backtrack over the input.

Usage:
  python3 infra/scripts/check-alert-routing.py [--rules DIR] [--config FILE]
Exit: 0 when every alert is routed; 1 when a parsed rule set violates routing —
a severity no route matches, an undefined receiver, a receiver with no
`webhook_configs`, a root child with no severity matcher, or `local-null` back in
the config; 2 when the rule set could not be parsed or attributed at all — a
missing or unreadable file, a shape this parser does not understand, or an alert
whose severity label cannot be attributed. A `severity:` under `annotations:` is
exit 2, not 1, on purpose: Alertmanager never routes on it, the alert never
becomes a parsed severity, and the gate cannot name the route that should have
matched it. A non-zero code always means the tree was not proven safe; the
distinction is "violates a known contract" (1) versus "no verdict available" (2).
"""

from __future__ import annotations

import argparse
import re
import string
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RULES = ROOT / "infra/monitoring/prometheus/rules"
DEFAULT_CONFIG = ROOT / "infra/monitoring/alertmanager/alertmanager.yml"

# The only pattern kept: an ASCII label/key token, anchored, with no quantifier
# that can nest. `re.ASCII` makes `\w` exactly `[A-Za-z0-9_]`.
RULE_KEY_RE = re.compile(r"^[A-Za-z_]\w*:", re.ASCII)
MATCHER_OPERATORS = ("=~", "!~", "!=", "=")
GROUP_OR_RULE_TOKENS = ("name:", "alert:", "record:")
# ASCII label tokens: the same sets `isascii() and isalpha()` / `isalnum()` accept.
LABEL_START_CHARS = frozenset(string.ascii_letters + "_")
LABEL_BODY_CHARS = frozenset(string.ascii_letters + string.digits + "_")
QUOTE_CHARS = "\"'"


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip())


def _is_ascii_name(text: str) -> bool:
    """True for ``[A-Za-z_]+``: the YAML key shape this gate understands."""
    return bool(text) and all(char.isascii() and (char.isalpha() or char == "_") for char in text)


def _leading_label(text: str) -> tuple[str, str] | None:
    """Split a leading ``[A-Za-z_]\\w*`` token; ``None`` when the text has none."""
    if not text or text[0] not in LABEL_START_CHARS:
        return None
    end = 1
    while end < len(text) and text[end] in LABEL_BODY_CHARS:
        end += 1
    return text[:end], text[end:]


def _list_item(line: str) -> tuple[int, str] | None:
    """Split ``<indent>- <text>``; ``None`` when the dash is not followed by whitespace.

    Returns the raw text after the dash, so each caller can apply the value rule
    its own key needs.
    """
    body = line.lstrip()
    if not body.startswith("-"):
        return None
    after_dash = body[1:]
    if not after_dash or not after_dash[0].isspace():
        return None
    return _indent_of(line), after_dash


def _item_value(line: str, key: str) -> tuple[int, str] | None:
    """Match ``<indent>- key: <value>``; ``None`` when the shape or value is missing.

    A value that is only whitespace still counts, as it did under the previous
    pattern: the key matches and the scalar strips to an empty string.
    """
    item = _list_item(line)
    if item is None:
        return None
    indent, after_dash = item
    text = after_dash.lstrip()
    if not text.startswith(key + ":"):
        return None
    remainder = text[len(key) + 1 :]
    if not remainder:
        return None
    return indent, remainder.strip()


def _item_expression(line: str) -> str | None:
    """Return the expression of a ``- <expr>`` item; ``None`` when it has none.

    An item that is nothing but whitespace still carries a one-space expression,
    which the matcher parser then rejects; a bare ``- `` carries none at all.
    """
    item = _list_item(line)
    if item is None:
        return None
    _, after_dash = item
    if len(after_dash) < 2:
        return None
    return after_dash.strip() or " "


def _top_level_key(line: str) -> str | None:
    """Return the key of a top-level ``key:`` line with no value, else ``None``."""
    body = line.rstrip()
    if not body.endswith(":"):
        return None
    key = body[:-1]
    return key if _is_ascii_name(key) else None


def _block_key_indent(line: str, key: str) -> int | None:
    """Match ``<indent>key:`` with an empty or comment-only value; return the indent."""
    body = line.lstrip()
    if len(body) == len(line) or not body.startswith(key + ":"):
        return None
    rest = body[len(key) + 1 :].strip()
    if rest and not rest.startswith("#"):
        return None
    return len(line) - len(body)


def _inline_value(line: str, key: str) -> str | None:
    """Match ``<indent>key: <value>`` where the value is not a comment."""
    body = line.lstrip()
    if len(body) == len(line) or not body.startswith(key + ":"):
        return None
    rest = body[len(key) + 1 :].lstrip()
    if not rest or rest.startswith("#"):
        return None
    return rest


def _indented_value(line: str, key: str) -> str | None:
    """Match ``<indent>key: <value>`` and return the stripped value.

    A value that is only whitespace still matches and yields an empty string, so
    it occupies the slot without naming a value, as the previous pattern did.
    """
    body = line.lstrip()
    if len(body) == len(line) or not body.startswith(key + ":"):
        return None
    remainder = body[len(key) + 1 :]
    if not remainder:
        return None
    return remainder.strip()


def _strip_comment(value: str) -> str:
    """Cut an unquoted scalar at its first whitespace-preceded ``#``."""
    index = value.find("#")
    while index != -1:
        if index > 0 and value[index - 1].isspace():
            return value[:index].rstrip()
        index = value.find("#", index + 1)
    return value


def _is_quoted(value: str) -> bool:
    """True for a scalar wrapped in matching single or double quotes."""
    if len(value) < 2:
        return False
    return value[0] == value[-1] and value[0] in QUOTE_CHARS


def strip_scalar(raw: str) -> str:
    value = raw.strip()
    if value.startswith("#"):
        return ""
    if _is_quoted(value):
        return value[1:-1]
    # Drop a trailing comment on an unquoted scalar.
    return _strip_comment(value).strip()


@dataclass
class Alert:
    name: str
    severity: str | None
    source: Path


@dataclass
class Matcher:
    label: str
    op: str
    value: str

    def matches(self, value: str) -> bool:
        if self.op == "=":
            return value == self.value
        if self.op == "!=":
            return value != self.value
        try:
            matched = re.fullmatch(self.value, value) is not None
        except re.error:
            # An invalid regex is a configuration error, not a match.
            matched = False
        return matched if self.op == "=~" else not matched


@dataclass
class Route:
    receiver: str
    matchers: list[Matcher] = field(default_factory=list)
    children: list["Route"] = field(default_factory=list)
    line: int = 0

    def severity_matchers(self) -> list[Matcher]:
        return [m for m in self.matchers if m.label == "severity"]


@dataclass
class Receiver:
    name: str
    webhook_configs: int
    line: int


@dataclass
class _RuleFileScan:
    """Line-scanner state for one Prometheus rule file.

    ``in_labels`` tracks the label block of the current alert: a ``severity:``
    there is a routing label, a ``severity:`` under ``annotations:`` is prose.
    """

    path: Path
    alerts: list[Alert] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    current: Alert | None = None
    in_labels: bool = False
    labels_indent: int = 0

    def feed(self, lineno: int, line: str) -> None:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            return
        if self._begin_alert(line):
            return
        if self.current is None:
            return
        if self._consume_label_region(lineno, line, self.current):
            return
        if self._is_group_or_rule_item(stripped):
            self.current = None

    def _begin_alert(self, line: str) -> bool:
        item = _item_value(line, "alert")
        if item is None:
            return False
        _, name = item
        self.current = Alert(strip_scalar(name), None, self.path)
        self.alerts.append(self.current)
        self.in_labels = False
        return True

    def _is_group_or_rule_item(self, stripped: str) -> bool:
        item = _list_item(stripped)
        return item is not None and item[1].lstrip().startswith(GROUP_OR_RULE_TOKENS)

    def _consume_label_region(self, lineno: int, line: str, alert: Alert) -> bool:
        """Consume a label/annotation line; ``False`` means the block just ended."""
        if self._reject_inline_labels(lineno, line):
            return True
        if self._begin_labels_block(line):
            return True
        if _block_key_indent(line, "annotations") is not None:
            # A severity inside annotations is prose. It is not a label and
            # Alertmanager never routes on it, so it must not count.
            self.in_labels = False
            return True
        if not self.in_labels:
            return False
        return self._consume_label_line(line, alert)

    def _reject_inline_labels(self, lineno: int, line: str) -> bool:
        """Report an inline ``labels:`` mapping; ``True`` when the line was one."""
        if _inline_value(line, "labels") is None:
            return False
        self.errors.append(
            f"{self.path}:{lineno}: inline `labels:` mapping is not supported by this gate; "
            "use a block mapping so severity is read from the label position"
        )
        self.in_labels = False
        return True

    def _begin_labels_block(self, line: str) -> bool:
        """Open a ``labels:`` block; ``True`` when the line opened one."""
        indent = _block_key_indent(line, "labels")
        if indent is None:
            return False
        self.in_labels = True
        self.labels_indent = indent
        return True

    def _consume_label_line(self, line: str, alert: Alert) -> bool:
        """Read a line inside the label region; ``False`` ends the block."""
        if _indent_of(line) > self.labels_indent or not RULE_KEY_RE.match(line.strip()):
            self._record_severity(line, alert)
            return True
        # A sibling key ends the labels block.
        self.in_labels = False
        return False

    def _record_severity(self, line: str, alert: Alert) -> None:
        severity = _indented_value(line, "severity")
        if severity is not None and alert.severity is None:
            alert.severity = strip_scalar(severity)


def _alert_label_errors(alerts: list[Alert]) -> list[str]:
    """Reasons a routing verdict cannot be given; evaluate() turns these into exit 2.

    An alert with no attributable severity cannot be checked against the routes,
    so this is "no verdict", not "violates routing". A `severity:` written only
    under `annotations:` lands here too: Alertmanager never routes on it.
    """
    errors: list[str] = []
    for alert in alerts:
        if not alert.name:
            errors.append(f"{alert.source}: alert with an empty name")
        if not alert.severity:
            errors.append(f"{alert.source}: alert {alert.name} has no severity label")
    return errors


def parse_rules(rules_dir: Path) -> tuple[list[Alert], list[str]]:
    alerts: list[Alert] = []
    errors: list[str] = []
    files = sorted(p for p in rules_dir.rglob("*.yml") if p.is_file())
    files += sorted(p for p in rules_dir.rglob("*.yaml") if p.is_file())
    if not files:
        return [], [f"no rule files found under {rules_dir}"]
    for path in files:
        scan = _RuleFileScan(path)
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            scan.feed(lineno, line)
        alerts.extend(scan.alerts)
        errors.extend(scan.errors)
    errors.extend(_alert_label_errors(alerts))
    return alerts, errors


def _parse_matcher_expr(expr: str, where: str) -> tuple[Matcher | None, str | None]:
    text = strip_scalar(expr)
    label = _leading_label(text)
    if label is not None:
        name, rest = label
        rest = rest.lstrip()
        for operator in MATCHER_OPERATORS:
            if rest.startswith(operator):
                return Matcher(name, operator, strip_scalar(rest[len(operator) :])), None
    return None, f"{where}: unsupported matcher {expr!r}"


def _legacy_matcher_value(stripped: str) -> tuple[str, str] | None:
    """Split the legacy ``label: value`` matcher form; ``None`` when it is not that."""
    label = _leading_label(stripped)
    if label is None:
        return None
    name, rest = label
    if not rest.startswith(":"):
        return None
    value = rest[1:].lstrip()
    return (name, value) if value else None


def _route_key_value(stripped: str) -> tuple[str, str] | None:
    """Split ``key: rest`` where the key is ASCII letters/underscore."""
    colon = stripped.find(":")
    if colon <= 0:
        return None
    key = stripped[:colon]
    return (key, stripped[colon + 1 :]) if _is_ascii_name(key) else None


@dataclass
class _RouteScan:
    """Line-scanner state for the routing tree and receivers of one config file.

    ``stack`` holds ``(indent, route)`` pairs; the root sits at indent -1 so a
    top-level ``- receiver:`` becomes its child. ``mode`` tracks an open
    ``matchers:`` or ``match:`` block so its items are read as matchers.
    """

    path: Path
    root: Route = field(default_factory=lambda: Route(receiver=""))
    receivers: list[Receiver] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    stack: list[tuple[int, Route]] = field(default_factory=list)
    mode: str | None = None
    mode_target: Route | None = None
    in_receivers: bool = False
    current_receiver: Receiver | None = None

    def feed(self, lineno: int, line: str) -> None:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            return
        if self._feed_top_level(lineno, line):
            return
        if self.in_receivers:
            self._consume_receiver_line(lineno, line)
            return
        self._feed_route_line(lineno, line)

    def _feed_top_level(self, lineno: int, line: str) -> bool:
        """Handle a top-level key; ``True`` when the line was fully consumed."""
        top_key = _top_level_key(line)
        if top_key == "receivers":
            self._begin_receivers()
            return True
        if top_key == "route":
            self._begin_route()
            return True
        if top_key is not None and not self.in_receivers:
            # Any other top-level key (inhibit_rules, templates, ...) closes route.
            self._close_blocks()
        return False

    def _feed_route_line(self, lineno: int, line: str) -> None:
        """Feed one line to the open route blocks."""
        if not self.stack:
            return
        where = f"{self.path}:{lineno}"
        if self._consume_route_item(lineno, line):
            return
        if self._consume_route_key(line, where):
            return
        if self._consume_matcher_item(line, where):
            return
        self._consume_legacy_match(line)

    def _begin_receivers(self) -> None:
        self.in_receivers = True
        self.mode, self.mode_target = None, None
        self.stack.clear()

    def _begin_route(self) -> None:
        self.in_receivers = False
        self.stack.append((-1, self.root))

    def _close_blocks(self) -> None:
        self.mode, self.mode_target = None, None
        self.stack.clear()

    def _consume_receiver_line(self, lineno: int, line: str) -> None:
        item = _item_value(line, "name")
        if item is not None:
            indent, name = item
            if indent <= 2:
                self.current_receiver = Receiver(strip_scalar(name), 0, lineno)
                self.receivers.append(self.current_receiver)
                return
        if self.current_receiver is not None and line.strip() == "webhook_configs:":
            self.current_receiver.webhook_configs += 1

    def _consume_route_item(self, lineno: int, line: str) -> bool:
        item = _item_value(line, "receiver")
        if item is None:
            return False
        child_indent, name = item
        while len(self.stack) > 1 and self.stack[-1][0] >= child_indent:
            self.stack.pop()
        route = Route(strip_scalar(name), line=lineno)
        self.stack[-1][1].children.append(route)
        self.stack.append((child_indent, route))
        self.mode, self.mode_target = None, None
        return True

    def _consume_route_key(self, line: str, where: str) -> bool:
        key_value = _route_key_value(line.strip())
        if key_value is None or _indent_of(line) <= self.stack[-1][0]:
            return False
        key, rest = key_value
        current = self.stack[-1][1]
        rest = rest.strip()
        if key == "receiver":
            current.receiver = strip_scalar(rest)
            self.mode, self.mode_target = None, None
            return True
        if key in ("matchers", "match"):
            self.mode, self.mode_target = key, current
            if rest.startswith("["):
                self._consume_inline_matchers(current, rest, where)
                self.mode, self.mode_target = None, None
            return True
        self.mode, self.mode_target = None, None
        return True

    def _consume_inline_matchers(self, route: Route, rest: str, where: str) -> None:
        for item in rest.strip("[]").split(","):
            if not item.strip():
                continue
            matcher, error = _parse_matcher_expr(item, where)
            if error:
                self.errors.append(error)
            elif matcher:
                route.matchers.append(matcher)

    def _consume_matcher_item(self, line: str, where: str) -> bool:
        if self.mode != "matchers" or self.mode_target is None:
            return False
        expression = _item_expression(line)
        if expression is None:
            return False
        matcher, error = _parse_matcher_expr(expression, where)
        if error:
            self.errors.append(error)
        elif matcher:
            self.mode_target.matchers.append(matcher)
        return True

    def _consume_legacy_match(self, line: str) -> bool:
        if self.mode != "match" or self.mode_target is None:
            return False
        if _indent_of(line) <= self.stack[-1][0]:
            return False
        parsed = _legacy_matcher_value(line.strip())
        if parsed is not None:
            self.mode_target.matchers.append(Matcher(parsed[0], "=", strip_scalar(parsed[1])))
        return True


def parse_alertmanager(path: Path) -> tuple[Route, list[Receiver], list[str]]:
    scan = _RouteScan(path)
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        scan.feed(lineno, line)
    if not scan.root.receiver:
        scan.errors.append(f"{path}: root route has no receiver")
    return scan.root, scan.receivers, scan.errors


def walk(route: Route) -> list[Route]:
    out = [route]
    for child in route.children:
        out.extend(walk(child))
    return out


def severity_matches(route: Route, severity: str) -> bool:
    """True only when the route names `severity` in one of its own matchers.

    A route with no severity matcher selects on other labels. This gate cannot
    evaluate those labels, so such a route does not make a severity count as
    routed; `evaluate` reports it separately rather than treating it as a
    catch-all.
    """
    matchers = route.severity_matchers()
    return bool(matchers) and any(m.matches(severity) for m in matchers)


def resolve(route: Route, severity: str) -> str:
    """First severity-matching child wins, as Alertmanager evaluates children."""
    for child in route.children:
        if severity_matches(child, severity):
            return resolve(child, severity)
    return route.receiver


def _receiver_failures(config: Path, receivers: list[Receiver]) -> list[str]:
    """Every receiver must be able to deliver, or it drops alerts silently."""
    failures: list[str] = []
    for receiver in receivers:
        if receiver.webhook_configs == 0:
            failures.append(
                f"{config}:{receiver.line}: receiver {receiver.name!r} has no webhook_configs "
                "(a receiver with no integration drops alerts)"
            )
    return failures


def _undefined_receiver_failures(config: Path, root: Route, receivers: list[Receiver]) -> list[str]:
    receiver_names = {receiver.name for receiver in receivers}
    failures: list[str] = []
    for route in walk(root):
        if route.receiver not in receiver_names:
            failures.append(
                f"{config}:{route.line}: route targets undefined receiver {route.receiver!r}"
            )
    return failures


def _severity_assignment_failures(config: Path, root: Route) -> list[str]:
    """A direct child of the root is a severity assignment; one that names no
    severity selects on other labels only. It looks like an assignment but cannot
    route a severity, so it is reported instead of being counted."""
    failures: list[str] = []
    for route in root.children:
        if not route.severity_matchers():
            failures.append(
                f"{config}:{route.line}: child route to {route.receiver!r} has no severity "
                "matcher, so it assigns no severity (a route that selects on other labels "
                "cannot make a severity count as routed)"
            )
    return failures


def _unrouted_failures(root: Route, alerts: list[Alert], severities: list[str]) -> list[str]:
    """A severity counts as routed only when a direct child route matches it.

    The root route is the fail-loud safety net, not an assignment; otherwise a new
    severity would silently inherit the catch-all channel.
    """
    failures: list[str] = []
    for severity in severities:
        if any(severity_matches(route, severity) for route in root.children):
            continue
        names = [alert.name for alert in alerts if alert.severity == severity]
        failures.append(f"severity {severity!r} is matched by no route (alerts: {', '.join(names)})")
    return failures


def _severities_of(alerts: list[Alert]) -> list[str]:
    return sorted({alert.severity for alert in alerts if alert.severity})


def _collect_failures(
    config: Path, root: Route, receivers: list[Receiver], alerts: list[Alert]
) -> list[str]:
    """Every reason this routing tree fails, in the order main() has always printed."""
    failures = _undefined_receiver_failures(config, root, receivers)
    failures.extend(_receiver_failures(config, receivers))
    failures.extend(_severity_assignment_failures(config, root))
    failures.extend(_unrouted_failures(root, alerts, _severities_of(alerts)))
    return failures


def _config_failure(config: Path) -> tuple[int, list[str]] | None:
    """Check the config file alone; ``None`` when it is present and clean."""
    if not config.is_file():
        return 2, [f"missing {config}"]
    raw_config = config.read_text(encoding="utf-8")
    if "local-null" in raw_config:
        return 1, [
            f"FAIL local-null receiver is back in {config}; alerts must route to a real receiver"
        ]
    return None


def _parse_all(
    rules_dir: Path, config: Path
) -> tuple[list[Alert], Route, list[Receiver], list[str]]:
    alerts, rule_errors = parse_rules(rules_dir)
    root, receivers, config_errors = parse_alertmanager(config)
    return alerts, root, receivers, rule_errors + config_errors


def _ok_line(root: Route, receivers: list[Receiver], alerts: list[Alert]) -> str:
    route_map = [f"{severity}->{resolve(root, severity)}" for severity in _severities_of(alerts)]
    return f"ok {len(alerts)} alerts, {len(receivers)} receivers, routes {' '.join(route_map)}"


def evaluate(rules_dir: Path, config: Path) -> tuple[int, list[str]]:
    """Return (exit code, output lines). main() prints them; the self-test asserts them.

    ``2`` means no routing verdict exists: the rule set could not be parsed or a
    rule's severity could not be attributed (an unlabelled alert, a shape the
    parser rejects, a missing file). ``1`` means the parsed rule set violates
    routing. See the module docstring for the full contract.
    """
    config_failure = _config_failure(config)
    if config_failure is not None:
        return config_failure

    alerts, root, receivers, errors = _parse_all(rules_dir, config)
    if errors:
        return 2, [f"FAIL {error}" for error in errors]

    failures = _collect_failures(config, root, receivers, alerts)
    if failures:
        return 1, [f"FAIL {failure}" for failure in failures]

    return 0, [_ok_line(root, receivers, alerts)]


SELF_TEST_RULES_PAGE = """\
groups:
  - name: selftest.page
    rules:
      - alert: SelfTestPage
        expr: vector(1)
        labels:
          severity: page
        annotations:
          summary: "selftest page probe"
"""

SELF_TEST_RULES_WARN = SELF_TEST_RULES_PAGE.replace("severity: page", "severity: warn")

SELF_TEST_RULES_ANNOTATION = """\
groups:
  - name: selftest.annotation
    rules:
      - alert: SelfTestAnnotationOnly
        expr: vector(1)
        labels:
          service: selftest
        annotations:
          severity: page
          summary: "severity in an annotation is prose, not a label"
"""

SELF_TEST_CONFIG_ROUTED = """\
route:
  receiver: ibex-page
  group_by: [alertname, severity]
  routes:
    - receiver: ibex-page
      matchers:
        - severity=~"p1|page"
    - receiver: ibex-digest
      matchers:
        - severity=~"p2|p3|ticket"

receivers:
  - name: ibex-page
    webhook_configs:
      - url: http://alert-receiver:8080/alerts/page
  - name: ibex-digest
    webhook_configs:
      - url: http://alert-receiver:8080/alerts/digest
"""

SELF_TEST_CONFIG_TICKET_ONLY = """\
route:
  receiver: ibex-page
  routes:
    - receiver: ibex-digest
      matchers:
        - severity=~"p2|p3|ticket"

receivers:
  - name: ibex-page
    webhook_configs:
      - url: http://alert-receiver:8080/alerts/page
  - name: ibex-digest
    webhook_configs:
      - url: http://alert-receiver:8080/alerts/digest
"""

# A `service=`-only route next to a ticket route. Before the strict severity
# check, the service route matched every severity, so `page` looked routed.
SELF_TEST_CONFIG_SERVICE_ONLY = """\
route:
  receiver: ibex-page
  routes:
    - receiver: ibex-page
      matchers:
        - service=selftest
    - receiver: ibex-digest
      matchers:
        - severity=~"p2|p3|ticket"

receivers:
  - name: ibex-page
    webhook_configs:
      - url: http://alert-receiver:8080/alerts/page
  - name: ibex-digest
    webhook_configs:
      - url: http://alert-receiver:8080/alerts/digest
"""


def run_self_test() -> list[str]:
    """Prove the gate still fails on the edges it exists to catch."""
    failures: list[str] = []

    def case(
        name: str,
        rules_text: str,
        config_text: str,
        want_code: int,
        want_fragments: tuple[str, ...],
    ) -> None:
        with tempfile.TemporaryDirectory(prefix=f"alert-routing-{name}.") as tmp:
            base = Path(tmp)
            rules_dir = base / "rules"
            rules_dir.mkdir()
            (rules_dir / "selftest.yml").write_text(rules_text, encoding="utf-8")
            config = base / "alertmanager.yml"
            config.write_text(config_text, encoding="utf-8")
            code, lines = evaluate(rules_dir, config)
        text = "\n".join(lines)
        if code != want_code:
            failures.append(f"{name}: expected exit {want_code}, got {code}: {text}")
            return
        for fragment in want_fragments:
            if fragment not in text:
                failures.append(f"{name}: expected {fragment!r} in output, got: {text}")

    # Positive control: a gate that fails everything proves nothing.
    case("routed", SELF_TEST_RULES_PAGE, SELF_TEST_CONFIG_ROUTED, 0, ("ok 1 alerts", "page->ibex-page"))
    case(
        "unrouted-severity",
        SELF_TEST_RULES_WARN,
        SELF_TEST_CONFIG_TICKET_ONLY,
        1,
        ("severity 'warn' is matched by no route",),
    )
    case(
        "service-only-route",
        SELF_TEST_RULES_PAGE,
        SELF_TEST_CONFIG_SERVICE_ONLY,
        1,
        ("has no severity matcher", "severity 'page' is matched by no route"),
    )
    case(
        "annotation-severity",
        SELF_TEST_RULES_ANNOTATION,
        SELF_TEST_CONFIG_ROUTED,
        2,
        ("has no severity label",),
    )
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()

    code, lines = evaluate(args.rules, args.config)
    stream = sys.stdout if code == 0 else sys.stderr
    for line in lines:
        print(f"check-alert-routing: {line}", file=stream)

    self_failures = run_self_test()
    for failure in self_failures:
        print(f"check-alert-routing: FAIL self-test {failure}", file=sys.stderr)
    if self_failures:
        return 2 if code == 0 else code
    if code == 0:
        print("check-alert-routing: self-test ok (4 fixtures)")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
