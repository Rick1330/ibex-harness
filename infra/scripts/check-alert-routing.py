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
     severity while looking like an assignment,
  6. a route carries a severity matcher together with a matcher this gate cannot
     evaluate (`severity=page` plus `service=api`): the route may or may not
     select an alert and the gate cannot tell, so the severity is not counted as
     routed and the named matcher is reported, or
  7. the null receiver `local-null` reappears anywhere in the file.

Severity reachability is decided only by severity matchers, and only by a route
this gate can evaluate in full. A route that selects on other labels
(`service=proxy` and nothing else) is not evidence that a severity is routed.
Neither is a route that selects on `service=proxy` *as well as* severity: this
gate evaluates severity only, so it fails closed on the other label rather than
letting the severity look routed. Every severity matcher on a route must match,
because Alertmanager ANDs a route's matchers: a route carrying `severity=page`
and `severity=ticket` can never fire, so it counts for neither severity.

The gate also runs a self-test over small fixtures before it exits, so the edges
above (a `service=`-only route, a severity route with an extra `service=` matcher,
and a `severity:` in an annotation) are proven to still fail, while a legacy
`match_re`, a non-receiver block after `receivers:`, and conflicting severity
matchers cannot produce a wrong verdict. A gate that cannot fail is not a gate.

Standard library only, on purpose: this gate runs on a bare CI runner and in
`make repo-guards`, so it must not add a YAML dependency. The parser therefore
understands exactly the subset of YAML these two file families use (block
mappings, block sequences, `matchers:`/`match:` lists, and inline flow lists of
matchers) and fails loudly on a shape it does not understand instead of
guessing. It is a line-oriented scanner rather than a set of regexes: every line
is classified once, so no pattern can backtrack over the input.

Usage:
  python3 infra/scripts/check-alert-routing.py [--rules DIR] [--config FILE]

Both inputs are read only after they are confined: a path with a ``..`` segment,
a path that resolves outside the allow-root, or a path that is not an existing
file/directory of the expected kind is refused with exit 2 before anything is
read. The allow-root is the current working directory (run the gate from the
repository root, as every documented invocation does); export
``IBEX_ALERT_ROUTING_ALLOW_ROOT`` to point it at a different tree.
Exit: 0 when every alert is routed; 1 when a parsed rule set violates routing —
a severity no route matches, an undefined receiver, a receiver with no
`webhook_configs`, a root child with no severity matcher, a route with a matcher
this gate cannot evaluate, or `local-null` back in the config; 2 when the rule set
could not be parsed or attributed at all — a missing or unreadable file, a shape
this parser does not understand (including a route `match_re:`, whose regex the
gate never reads), or an alert whose severity label cannot be attributed. A
`severity:` under `annotations:` is exit 2, not 1, on purpose: Alertmanager never
routes on it, the alert never becomes a parsed severity, and the gate cannot name
the route that should have matched it. A non-zero code always means the tree was
not proven safe; the distinction is "violates a known contract" (1) versus "no
verdict available" (2).
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RULES = ROOT / "infra/monitoring/prometheus/rules"
DEFAULT_CONFIG = ROOT / "infra/monitoring/alertmanager/alertmanager.yml"
# Widens the root a CLI-supplied path may resolve under. Unset means the working
# directory; the tests point it at their fixture tree.
ALLOW_ROOT_ENV = "IBEX_ALERT_ROUTING_ALLOW_ROOT"

# Allow `python3 infra/scripts/check-alert-routing.py` without PYTHONPATH.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from alert_routing_parser import (  # noqa: E402
    Alert,
    Receiver,
    Route,
    parse_alertmanager,
    parse_rules,
)


def walk(route: Route) -> list[Route]:
    out = [route]
    for child in route.children:
        out.extend(walk(child))
    return out


def severity_matches(route: Route, severity: str) -> bool:
    """True only when every severity matcher on the route matches `severity`.

    Fail closed three times over. A route with no severity matcher selects on
    other labels, and a route with a severity matcher *plus* a matcher on another
    label selects on something this gate cannot evaluate — `service=api` may
    exclude the alert the route appears to accept. This gate evaluates `severity`
    only, so neither route makes a severity count as routed; `_unevaluable_matcher_failures`
    names the matcher it could not read. Finally, Alertmanager ANDs every matcher
    on a route, so two conflicting severity matchers (`severity=page` and
    `severity=ticket`) can never fire together and route neither: the route must
    match on all of them, not any one.
    """
    matchers = route.severity_matchers()
    if not matchers or route.unevaluable_matchers():
        return False
    return all(matcher.matches(severity) for matcher in matchers)


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


def _unevaluable_matcher_failures(config: Path, root: Route) -> list[str]:
    """A severity route that also selects on another label cannot be verified.

    This gate evaluates `severity` only. `severity=page` plus `service=api` may
    or may not select an alert, and the gate cannot tell which, so the route is
    not allowed to make `page` look routed (fail closed) and the matcher it could
    not evaluate is named, so the operator knows why the severity lost its route.
    """
    failures: list[str] = []
    for route in walk(root):
        unevaluable = route.unevaluable_matchers()
        if not unevaluable or not route.severity_matchers():
            continue
        named = ", ".join(f"{m.label}{m.op}{m.value}" for m in unevaluable)
        failures.append(
            f"{config}:{route.line}: route to {route.receiver!r} selects on {named} as well as "
            f"severity, and this gate evaluates severity only; its severities are not "
            f"counted as routed until the route selects on severity alone"
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
    failures.extend(_unevaluable_matcher_failures(config, root))
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


def _allow_root() -> Path:
    """The root a CLI-supplied input may live under: the working directory by default."""
    raw = os.environ.get(ALLOW_ROOT_ENV, "").strip()
    return Path.cwd() if not raw else Path(raw).resolve()


def _confine_input(
    raw: Path, allow_root: Path, *, want_dir: bool
) -> tuple[Path | None, str | None]:
    """Prove a caller-supplied path is a real file/directory under ``allow_root``.

    ``--rules`` and ``--config`` come from a command line, so neither is read
    until it passes here: a ``..`` segment is refused outright (an escape that is
    also hard to review), the resolved path must stay inside ``allow_root`` (the
    working directory unless ``IBEX_ALERT_ROUTING_ALLOW_ROOT`` widens it), and it
    must be the expected kind. The resolved path is returned, so every later read
    uses the checked value and a symlink cannot redirect it after the check.
    """
    if ".." in raw.parts:
        return None, f"refusing {raw}: it contains a '..' segment"
    resolved = raw.resolve()
    if not resolved.is_relative_to(allow_root):
        return None, (
            f"refusing {raw}: it resolves outside {allow_root}; "
            f"run from the repository root or set {ALLOW_ROOT_ENV}"
        )
    if want_dir and not resolved.is_dir():
        return None, f"refusing {raw}: it is not an existing directory"
    if not want_dir and not resolved.is_file():
        return None, f"refusing {raw}: it is not an existing regular file"
    return resolved, None


def _confine_inputs(
    rules_dir: Path, config: Path, allow_root: Path | None
) -> tuple[Path | None, Path | None, list[str]]:
    """Confine both CLI inputs; return the checked paths and any refusal lines."""
    base = _allow_root() if allow_root is None else allow_root
    checked_rules, rules_problem = _confine_input(rules_dir, base, want_dir=True)
    checked_config, config_problem = _confine_input(config, base, want_dir=False)
    problems = [problem for problem in (rules_problem, config_problem) if problem]
    return checked_rules, checked_config, problems


def evaluate(
    rules_dir: Path, config: Path, allow_root: Path | None = None
) -> tuple[int, list[str]]:
    """Return (exit code, output lines). main() prints them; the self-test asserts them.

    ``2`` means no routing verdict exists: the rule set could not be parsed or a
    rule's severity could not be attributed (an unlabelled alert, a shape the
    parser rejects, a missing file), or an input path was refused. ``1`` means
    the parsed rule set violates routing. See the module docstring for the full
    contract.
    """
    checked_rules, checked_config, problems = _confine_inputs(rules_dir, config, allow_root)
    if checked_rules is None or checked_config is None:
        return 2, problems

    config_failure = _config_failure(checked_config)
    if config_failure is not None:
        return config_failure

    alerts, root, receivers, errors = _parse_all(checked_rules, checked_config)
    if errors:
        return 2, [f"FAIL {error}" for error in errors]

    failures = _collect_failures(checked_config, root, receivers, alerts)
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

# A severity matcher next to a `service=` matcher. Before the fail-closed rule,
# the severity matcher alone made `page` look routed although the gate cannot
# tell whether `service=selftest` excludes the alert.
SELF_TEST_CONFIG_SEVERITY_PLUS_SERVICE = """\
route:
  receiver: ibex-page
  routes:
    - receiver: ibex-page
      matchers:
        - severity=~"p1|page"
        - service=selftest

receivers:
  - name: ibex-page
    webhook_configs:
      - url: http://alert-receiver:8080/alerts/page
  - name: ibex-digest
    webhook_configs:
      - url: http://alert-receiver:8080/alerts/digest
"""

# A severity route constrained by a legacy `match_re` regex. The gate does not
# read `match_re`, so before the parser rejected it the route looked like a
# severity-only route and `page` was counted as routed although the regex may
# exclude it.
SELF_TEST_CONFIG_MATCH_RE = """\
route:
  receiver: ibex-page
  routes:
    - receiver: ibex-page
      matchers:
        - severity=~"p1|page"
      match_re:
        service: "api|web"

receivers:
  - name: ibex-page
    webhook_configs:
      - url: http://alert-receiver:8080/alerts/page
"""

# A non-receiver top-level block after `receivers:`. Its `- name:` item is a time
# interval, not a receiver: leaving the receiver scan open invented a
# `business-hours` receiver with no webhook and failed an otherwise valid config.
SELF_TEST_CONFIG_TIME_INTERVALS = (
    SELF_TEST_CONFIG_ROUTED + 'time_intervals:\n  - name: business-hours\n'
    '    time_intervals:\n      - weekdays: ["monday:friday"]\n'
)

# Two conflicting severity matchers on one route. Alertmanager ANDs them, so the
# route can never fire; before the all-matchers rule it counted `page` as routed.
SELF_TEST_CONFIG_CONFLICTING_SEVERITY = """\
route:
  receiver: ibex-page
  routes:
    - receiver: ibex-page
      matchers:
        - severity=page
        - severity=ticket

receivers:
  - name: ibex-page
    webhook_configs:
      - url: http://alert-receiver:8080/alerts/page
"""


class _SelfTestCase(NamedTuple):
    """One fixture: the inputs, the expected exit code, and the output it must show."""

    name: str
    rules: str
    config: str
    want_code: int
    want_fragments: tuple[str, ...]
    forbidden: tuple[str, ...] = ()


# Positive control first: a gate that fails everything proves nothing.
_UNROUTED_PAGE = "severity 'page' is matched by no route"

_SELF_TEST_CASES = (
    _SelfTestCase("routed", SELF_TEST_RULES_PAGE, SELF_TEST_CONFIG_ROUTED, 0,
                  ("ok 1 alerts", "page->ibex-page")),
    _SelfTestCase("unrouted-severity", SELF_TEST_RULES_WARN, SELF_TEST_CONFIG_TICKET_ONLY,
                  1, ("severity 'warn' is matched by no route",)),
    _SelfTestCase("service-only-route", SELF_TEST_RULES_PAGE, SELF_TEST_CONFIG_SERVICE_ONLY,
                  1, ("has no severity matcher", _UNROUTED_PAGE)),
    _SelfTestCase("severity-plus-service-route", SELF_TEST_RULES_PAGE,
                  SELF_TEST_CONFIG_SEVERITY_PLUS_SERVICE, 1,
                  ("selects on service=selftest as well as severity",
                   _UNROUTED_PAGE)),
    _SelfTestCase("annotation-severity", SELF_TEST_RULES_ANNOTATION,
                  SELF_TEST_CONFIG_ROUTED, 2, ("has no severity label",)),
    _SelfTestCase("match-re-route", SELF_TEST_RULES_PAGE, SELF_TEST_CONFIG_MATCH_RE, 2,
                  ("`match_re` is not supported by this gate",),
                  forbidden=("ok 1 alerts",)),
    _SelfTestCase("time-intervals-after-receivers", SELF_TEST_RULES_PAGE,
                  SELF_TEST_CONFIG_TIME_INTERVALS, 0,
                  ("ok 1 alerts, 2 receivers", "page->ibex-page"),
                  forbidden=("business-hours",)),
    _SelfTestCase("conflicting-severity-matchers", SELF_TEST_RULES_PAGE,
                  SELF_TEST_CONFIG_CONFLICTING_SEVERITY, 1,
                  (_UNROUTED_PAGE,)),
)


def _self_test_path_refusal() -> list[str]:
    """A CLI path that escapes the allow-root is refused with exit 2, not read."""
    with tempfile.TemporaryDirectory(prefix="alert-routing-escape.") as tmp:
        allowed = Path(tmp) / "allowed"
        allowed.mkdir()
        outside = Path(tmp) / "outside.yml"
        outside.write_text(SELF_TEST_CONFIG_ROUTED, encoding="utf-8")
        escaped = allowed / ".." / outside.name
        code, lines = evaluate(escaped, escaped, allow_root=allowed)
    text = "\n".join(lines)
    if code != 2:
        return [f"path-escape: expected exit 2, got {code}: {text}"]
    if "refusing" not in text or "'..' segment" not in text:
        return [f"path-escape: expected a refusal naming the '..' segment, got: {text}"]
    return []


def _fragment_failures(
    name: str, text: str, fragments: tuple[str, ...], *, present: bool
) -> list[str]:
    """Fragments that contradict the case: expected but absent, or forbidden but present."""
    verdict = "expected" if present else "did not expect"
    failures: list[str] = []
    for fragment in fragments:
        if (fragment in text) != present:
            failures.append(f"{name}: {verdict} {fragment!r} in output, got: {text}")
    return failures


def _self_test_case(case: _SelfTestCase) -> list[str]:
    """Run one fixture and return the reasons it did not behave as specified."""
    with tempfile.TemporaryDirectory(prefix=f"alert-routing-{case.name}.") as tmp:
        base = Path(tmp)
        rules_dir = base / "rules"
        rules_dir.mkdir()
        (rules_dir / "selftest.yml").write_text(case.rules, encoding="utf-8")
        config = base / "alertmanager.yml"
        config.write_text(case.config, encoding="utf-8")
        code, lines = evaluate(rules_dir, config, allow_root=base)
    text = "\n".join(lines)
    if code != case.want_code:
        return [f"{case.name}: expected exit {case.want_code}, got {code}: {text}"]
    return _fragment_failures(
        case.name, text, case.want_fragments, present=True
    ) + _fragment_failures(case.name, text, case.forbidden, present=False)


def run_self_test() -> list[str]:
    """Prove the gate still fails on the edges it exists to catch."""
    failures: list[str] = []
    for case in _SELF_TEST_CASES:
        failures += _self_test_case(case)
    return failures + _self_test_path_refusal()


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
        print("check-alert-routing: self-test ok (8 fixtures + path refusal)")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
