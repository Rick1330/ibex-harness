#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

python3 - "${1:-$ROOT}" <<'PY'
import re
import sys
import unicodedata
from pathlib import Path

# Supported grammar: root jobs mapping, two-space job IDs, four-space job fields, six-space steps,
# eight-space step fields; run: plain single-line or literal | (ten-space lines).
# Commands are bare `go test -fuzz=Name -fuzztime=Nu ./package/` (flags in either
# order), Name=Fuzz[A-Z0-9_][A-Za-z0-9_]*, N=positive integer, u=ns|us|ms|s|m|h,
# <= int64 ns. Executable text uses printable ASCII with ASCII spaces between words.
# Step conditions may be absent, true, false, or exactly ${{ !cancelled() }};
# false supplies no coverage. The resolved target FuzzSplitJWTAndHeader requires
# ${{ !cancelled() }} and must be the sole command in its run step (comments and
# blank lines are ignored) to run after earlier failures while respecting cancellation. Trailing
# ASCII-space-separated # comments may contain Unicode and tabs. Anchors, compound/fractional
# durations, other flags, shell syntax and other run-step fields fail loudly.
# Block scalar contents are not mapping keys; quoted YAML scalars must fit one line.
# YAML keys match [A-Za-z_][A-Za-z0-9_.-]*,
# with optional spaces/tabs before the colon and whitespace after it. Outside
# scalar bodies, only mapping entries and sequence items are modeled. Anchors,
# tags, aliases, complex/quoted keys and uncertain scalar forms fail closed.
# Inline collections are limited to {} and single-line lists of bare tokens.
# Every mapping/sequence value must classify as empty, closed quoted/flow,
# a block header, or plain text with a YAML-safe first character and no colon
# followed by ASCII space/tab or end. Plain -?: prefixes require a follower
# other than ASCII space/tab; Unicode non-space characters remain scalar data.
# Multiword sequence scalars are supported, compact mappings/nested sequences
# outside the key grammar are rejected. Block bodies are bounded by indentation.
# Inventory uses Go's Fuzz/non-lowercase suffix rule; names outside the ASCII
# command grammar are explicitly unsupported, including the bare name Fuzz.
# Each accepted selector must regex-match exactly one discovered name in its package.
# Workflow and go-fuzz job defaults are unsupported: commands assume the checkout
# root and the runner's default shell, with no inherited run overrides.
# Job conditions may be absent, true, or exactly needs.changes.outputs.run_go == 'true'.
# The last is a contextual assumption: coverage applies when that Go-change gate
# opens. Other job conditions are refused, not evaluated as Actions expressions.


def require(condition, reason):
    if not condition:
        raise AssertionError(reason)


def inventory(root):
    targets = set()
    # Remove Go comments and literals so examples cannot invent fuzz targets.
    literals = r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|`[^`]*`|\'(?:\\.|[^\'\\])*\''
    for path in root.rglob("*_test.go"):
        source = re.sub(literals, " ", path.read_text(encoding="utf-8"), flags=re.S)
        tokens = re.findall(r"\w+|[{}()]", source)
        depth = 0
        for index, token in enumerate(tokens):
            if token == "{":
                depth += 1
            elif token == "}":
                depth -= 1
            elif depth == 0 and token == "func" and index + 2 < len(tokens) and tokens[index + 2] == "(":
                name = tokens[index + 1]
                if name.startswith("Fuzz") and (len(name) == 4 or unicodedata.category(name[4]) != "Ll"):
                    require(re.fullmatch(r"Fuzz[A-Z0-9_][A-Za-z0-9_]*", name), "unsupported fuzz target name: " + name)
                    targets.add((name, "./" + path.parent.relative_to(root).as_posix()))
    require(targets, "empty Go fuzz target inventory")
    return targets


def yaml_value(value):
    require(not value.startswith(("&", "!", "*")), "unsupported YAML scalar property")
    if value.startswith(("'", '"')):
        require(re.fullmatch(r"'(?:[^']|'')*'[ \t]*(?:#.*)?", value) or
                re.fullmatch(r'"(?:[^"\\]|\\.)*"[ \t]*(?:#.*)?', value),
                "unsupported multiline quoted YAML scalar")
        return "quoted", value
    value = re.split(r"(?:^|[ \t]+)#", value, maxsplit=1)[0].rstrip(" \t")
    if not value:
        return "empty", value
    if value.startswith(("[", "{")):
        require(value == "{}" or re.fullmatch(r"\[(?:[A-Za-z0-9_./-]+(?:[ \t]*,[ \t]*[A-Za-z0-9_./-]+)*)?\]", value),
                "unsupported YAML flow scalar")
        return "flow", value
    if value.startswith(("|", ">")):
        require(re.fullmatch(r"[|>](?:[1-9][+-]?|[+-][1-9]?)?", value), "unsupported YAML block scalar")
        return "block", value
    plain = re.fullmatch(r"(?:[^ \t\-?:,\[\]{}#&*!|>'\"%@`]|[-?:](?=[^ \t]))[^\r\n]*", value)
    require(plain and not re.search(r":(?:[ \t]|$)", value), "unsupported YAML key or line: unsupported plain scalar")
    return "plain", value


def yaml_structure(workflow):
    # Full-line comments have no YAML structure, regardless of indentation.
    # read_text normalizes CR/CRLF; Unicode separators remain scalar content.
    require(not re.search(r"[\x00-\x08\x0b-\x1f]", workflow), "unsupported YAML control character")
    lines = [line for line in workflow.split("\n") if line.strip(" \t") and not line.lstrip(" \t").startswith("#")]
    structure, index = [], 0
    while index < len(lines):
        line = lines[index]
        index += 1
        match = re.fullmatch(r"( *)(- )?([A-Za-z_][A-Za-z0-9_.-]*)[ \t]*:(?:[ \t]+(.*)|$)", line)
        if match is None:
            item = re.fullmatch(r"( *)- (.*)", line)
            require(item is not None, "unsupported YAML key or line")
            prefix, key, value = item[1] + "- ", None, item[2].strip(" \t")
        else:
            prefix, key, value = match[1] + (match[2] or ""), match[3], (match[4] or "").strip(" \t")
        kind, value = yaml_value(value)
        structure.append(prefix + (key + ":" if key is not None else "") + (" " if key and value else "") + value)
        if kind == "block":
            indent = len(prefix)
            body = []
            while index < len(lines) and len(lines[index]) - len(lines[index].lstrip(" ")) > indent:
                body.append(lines[index])
                index += 1
            if key == "run":
                structure.extend(body)
    return structure


def job_steps(workflow):
    lines = yaml_structure(workflow)
    require(not any(line.startswith("defaults:") for line in lines), "unsupported workflow defaults")
    roots = [i for i, line in enumerate(lines) if line == "jobs:"]
    require(len(roots) == 1, "expected exactly one root jobs mapping")
    jobs = []
    for line in lines[roots[0] + 1:]:
        if not line.startswith(" "):
            break
        jobs.append(line)
    lines = jobs
    starts = [i for i, line in enumerate(lines) if line == "  go-fuzz:"]
    require(len(starts) == 1, "expected exactly one go-fuzz job")
    job = []
    for line in lines[starts[0] + 1:]:
        if len(line) - len(line.lstrip(" ")) <= 2:
            break
        job.append(line)
    require(not any(line.startswith("    defaults:") for line in job), "unsupported go-fuzz defaults")
    conditions = [line.partition(":")[2].strip(" \t") for line in job if line.startswith("    if:")]
    require(len(conditions) <= 1, "duplicate go-fuzz job condition")
    require(not conditions or conditions[0] in {"true", "needs.changes.outputs.run_go == 'true'"},
            "unsupported or disabled go-fuzz job condition")
    require(job.count("    steps:") == 1, "expected one go-fuzz steps list")
    steps, current = [], None
    for line in job[job.index("    steps:") + 1:]:
        indent = len(line) - len(line.lstrip(" "))
        if indent == 4:
            break
        if line.startswith("      - "):
            current = [line[8:]]
            steps.append(current)
        else:
            require(current is not None and indent >= 8, "unsupported steps structure")
            current.append(line[8:])
    return steps


def commands(step):
    # Action metadata is irrelevant to this assertion; inspect only run steps.
    if not any(line.startswith("run:") for line in step):
        return "true", []
    fields, body = {}, []
    for line in step:
        if line.startswith("  "):
            require(fields.get("run") == "|", "unsupported run indentation")
            body.append(line[2:])
            continue
        match = re.fullmatch(r"([a-z-]+):[ \t]*(.*)", line)
        require(match is not None, "unsupported step field syntax")
        key, value = match.groups()
        require(key in {"name", "if", "run"}, "unsupported run-step field: " + key)
        require(key not in fields, "duplicate run-step field: " + key)
        fields[key] = re.split(r"[ \t]+#", value, maxsplit=1)[0].strip(" \t")
        if key == "run":
            run = fields[key]
            require(run == "|" or not run.startswith(("|", ">", "'", '"')), "unsupported run scalar")
    condition = fields.get("if", "true")
    require(condition in {"true", "false", "${{ !cancelled() }}"}, "unsupported step condition: " + condition)
    if condition == "false":
        return condition, []
    run = fields["run"]
    return condition, body if run == "|" else [run]


def target_for(command):
    command = re.split(r" +#", command, maxsplit=1)[0].strip(" ")
    require(all(" " <= character <= "~" for character in command), "unsupported command character: expected printable ASCII")
    if not command or command.startswith("#"):
        return None
    require(not re.search(r"[^A-Za-z0-9_./=^$*+?()\[\]{}|: -]", command), "unsupported shell syntax")
    words = [word for word in command.split(" ") if word]
    require(words[:2] == ["go", "test"], "unsupported command: expected bare go test")
    require("-args" not in words, "unsupported -args: fuzz flags must reach go test")
    flags = {}
    for word in words[2:-1]:
        match = re.fullmatch(r"-(fuzz|fuzztime)=(.*)", word)
        require(match is not None, "unsupported go test flag: " + word)
        key, value = match.groups()
        require(key not in flags, "duplicate -" + key + " flag")
        flags[key] = value
    require(set(flags) == {"fuzz", "fuzztime"}, "expected exactly one -fuzz and one -fuzztime")
    name = flags["fuzz"]
    require(re.fullmatch(r"Fuzz[A-Z0-9_]\w*", name), "unsupported -fuzz selector: " + name)
    bound = flags["fuzztime"]
    match = re.fullmatch(r"(-?[0-9]+)(ns|us|ms|s|m|h)", bound)
    require(match is not None, "unsupported -fuzztime bound (integer single-unit duration required): " + bound)
    amount, unit = match.groups()
    factors = {"ns": 1, "us": 1000, "ms": 1000000, "s": 1000000000, "m": 60000000000, "h": 3600000000000}
    duration = int(amount) * factors[unit]
    require(duration > 0, "non-positive -fuzztime bound: " + bound)
    require(duration <= 9223372036854775807, "overflow -fuzztime bound: " + bound)
    package = words[-1]
    require(re.fullmatch(r"\./[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*/?", package), "unsupported package path: " + package)
    return name, package.rstrip("/")


try:
    root = Path(sys.argv[1]).resolve()
    targets = inventory(root)
    workflow = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    covered = set()
    for step in job_steps(workflow):
        condition, step_commands = commands(step)
        for command in step_commands:
            target = target_for(command)
            if target is not None:
                selector, package = target
                matches = sorted(name for name, directory in targets if directory == package and re.search(selector, name))
                require(len(matches) <= 1, "ambiguous -fuzz selector: " + selector + " (" + package + "): " + ", ".join(matches))
                require(matches, "no matching Go fuzz target for -fuzz selector: " + selector + " (" + package + ")")
                require(matches[0] != "FuzzSplitJWTAndHeader" or condition == "${{ !cancelled() }}",
                        "JWT fuzz step must use if: ${{ !cancelled() }} to run after failure and respect cancellation")
                require(matches[0] != "FuzzSplitJWTAndHeader" or len(step_commands) == 1,
                        "JWT fuzz command must be isolated in its run step")
                covered.add((matches[0], package))
    missing = sorted(targets - covered)
    require(not missing, "go-fuzz lacks bounded commands for: " + ", ".join(f"{name} ({package})" for name, package in missing))
    print(f"All {len(targets)} Go fuzz targets have bounded go-fuzz commands.")
except AssertionError as error:
    print(f"AssertionError: {error}", file=sys.stderr)
    sys.exit(1)
PY
