#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

python3 - "$ROOT" "${1:-$ROOT/.github/scripts/check-go-fuzz.sh}" <<'PY'
import re
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path(sys.argv[1])
guard = Path(sys.argv[2])
prefix = "jobs:\n  go-fuzz:\n    steps:\n"
first = "      - name: first target\n        run: go test -fuzz=FuzzAlpha -fuzztime=30s ./services/alpha/\n"
second = "      - name: second target\n        run: go test -fuzz=FuzzBeta -fuzztime=30s ./services/beta/\n"
good = prefix + first + second
real_workflow = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
real_sources = [(path.relative_to(root), path.read_text(encoding="utf-8")) for path in root.rglob("*_test.go")]

with tempfile.TemporaryDirectory(prefix="go-fuzz-test-") as temporary:
    fixture = Path(temporary)
    workflow = fixture / ".github/workflows/ci.yml"
    workflow.parent.mkdir(parents=True)
    for name, package in [("FuzzAlpha", "alpha"), ("FuzzBeta", "beta")]:
        path = fixture / "services" / package / "fuzz_test.go"
        path.parent.mkdir(parents=True)
        path.write_text(f"package {package}\nimport \"testing\"\nfunc {name}(f *testing.F) {{}}\n", encoding="utf-8")

    result = subprocess.run(["bash", str(guard), str(root)], text=True, capture_output=True)
    assert result.returncode == 0, f"real inventory while fixture exists\n{result.stdout}{result.stderr}"
    print("PASS: real inventory while fixture exists")

    def expect_status(expected, label, content=good, reason=""):
        workflow.write_text(content, encoding="utf-8")
        result = subprocess.run(["bash", str(guard), str(fixture)], text=True, capture_output=True)
        assert result.returncode == expected, f"{label}: got {result.returncode}, want {expected}\n{result.stdout}{result.stderr}"
        if expected:
            assert "AssertionError:" in result.stderr and reason in result.stderr, f"{label}: wrong failure\n{result.stderr}"
        print(f"PASS: {label}")

    expect_status(0, "both target steps run")
    for opener in ['- display name: "', '- display name: &label "', '- display name: !!str "', '- - "']:
        hidden_job = "jobs:\n  real:\n    steps:\n      - run: echo done\n    strategy:\n      matrix:\n        include:\n          " + opener + "\n" + good.removeprefix("jobs:\n").rstrip() + ' #"\n'
        expect_status(1, "sequence content must be classified: " + opener, hidden_job, "unsupported plain scalar")
    for value in ["?why", ":smile", "-dash"]:
        expect_status(0, "legal plain prefix: " + value, "name: " + value + "\n" + good)
        expect_status(0, "legal sequence scalar prefix: " + value, "values:\n  - " + value + "\n" + good)
    for character in ["\u00a0", "\u2009"]:
        for value in ["Build:" + character + "tests", "?" + character + "why", ":" + character + "smile",
                      "-" + character + "dash", character + "? value", "Build:" + character, character + "# text"]:
            expect_status(0, "Unicode non-space mapping scalar: " + ascii(value), "name: " + value + "\n" + good)
            expect_status(0, "Unicode non-space sequence scalar: " + ascii(value), "values:\n  - " + value + "\n" + good)
        expect_status(1, "Unicode non-space cannot separate a comment: " + ascii(character),
                      "name: text" + character + "# hidden: value\n" + good, "unsupported plain scalar")
        for quote in ["'", '"']:
            expect_status(1, "Unicode non-space after quote: " + ascii(quote + character),
                          "name: " + quote + "text" + quote + character + "# comment\n" + good,
                          "unsupported multiline quoted YAML scalar")
        expect_status(1, "Unicode non-space after block header: " + ascii(character),
                      "name: |" + character + "\n  text\n" + good, "unsupported YAML block scalar")
        for line in [character, character + "# comment"]:
            expect_status(1, "Unicode non-space line is not ignorable: " + ascii(line),
                          line + "\n" + good, "unsupported YAML key or line")
    for character in ["\u0085", "\u2028", "\u2029"]:
        expect_status(0, "Unicode character is not a YAML line break: " + ascii(character),
                      "name: Build" + character + "tests\n" + good)
    for character in ["\u0085", "\u2028", "\u2029", "\u00a0", "\u2009", "é", "\t", "\x7f"]:
        for form, content in [("plain", good), ("literal", good.replace("run: go test", "run: |\n          go test"))]:
            expect_status(1, form + " command rejects non-ASCII-space separator: " + ascii(character),
                          content.replace("go test", "go" + character + "test"), "unsupported command character")
            if character != "\t":
                for position, changed in [("leading", content.replace("go test", character + "go test")),
                                          ("trailing", content.replace("./services/alpha/", "./services/alpha/" + character)),
                                          ("comment boundary", content.replace("./services/alpha/", "./services/alpha/" + character + "# comment"))]:
                    expect_status(1, form + " command preserves " + position + " character: " + ascii(character),
                                  changed, "unsupported command character")
    for codepoint in range(32):
        if codepoint in (9, 10, 13):
            continue  # Tabs/LF are legal; read_text normalizes CR/CRLF to LF.
        for form, scalar in [("plain", "name: x{}y\n"), ("quoted", 'name: "x{}y"\n'),
                             ("sequence", "values:\n  - x{}y\n"), ("literal", "name: |\n  x{}y\n")]:
            expect_status(1, form + f" scalar rejects raw control U+{codepoint:04X}",
                          scalar.format(chr(codepoint)) + good, "unsupported YAML control character")
    expect_status(0, "tab remains legal scalar data", "name: x\ty\n" + good)
    expect_status(0, "literal LF remains legal scalar data", "name: |\n  x\n  y\n" + good)
    for ending in ["\r", "\r\n"]:
        expect_status(0, "normalized YAML line ending: " + ascii(ending), good.replace("\n", ending))
    expect_status(0, "repeated ASCII command spaces", good.replace("go test", "go   test"))
    for separator in [" ", "\t"]:
        for value in ["?" + separator + "key", ":" + separator + "value", "-" + separator + "nested",
                      "display name:" + separator + "value"]:
            expect_status(1, "separated indicator or compact mapping: " + ascii(value),
                          "name: " + value + "\n" + good, "unsupported plain scalar")
            expect_status(1, "separated sequence indicator or compact mapping: " + ascii(value),
                          "values:\n  - " + value + "\n" + good, "unsupported plain scalar")
    expect_status(1, "mapping-key indicator rejected", "? key\n" + good, "unsupported YAML key or line")
    expect_status(1, "sequence mapping-value indicator rejected", "values:\n  - : value\n" + good, "unsupported plain scalar")
    for indicator in ["?", ":", "-"]:
        expect_status(1, "empty plain indicator rejected: " + indicator, "name: " + indicator + "\n" + good, "unsupported plain scalar")
    expect_status(0, "ordinary multiword sequence scalar", "values:\n  - just text\n" + good)
    expect_status(0, "literal quotes inside plain scalar", 'name: ordinary "literal\n' + good)
    expect_status(0, "colon without separation inside plain scalar", "name: scheme:value\n" + good)
    expect_status(0, "run block sequence text is opaque YAML data", "jobs:\n  real:\n    steps:\n      - run: |\n          - echo done\n" + good.removeprefix("jobs:\n"))
    scalar_job = "jobs:\n  real:\n    steps:\n      - run: echo done\n    name : \"\n" + good.removeprefix("jobs:\n") + "    \"\n"
    expect_status(1, "spaced colon cannot hide a multiline scalar", scalar_job, "unsupported multiline quoted YAML scalar")
    expect_status(1, "anchor property cannot hide a multiline scalar", scalar_job.replace('name : "', 'name: &label "'), "unsupported YAML scalar property")
    expect_status(1, "tag property cannot hide a multiline scalar", scalar_job.replace('name : "', 'name: !!str "'), "unsupported YAML scalar property")
    expect_status(0, "spaced colon with ordinary single-line value", "name : description\n" + good.replace("name: first target", "name : first target"))
    for separator in ["  : ", "\t:\t"]:
        expect_status(1, "key colon whitespace preserves quote detection", scalar_job.replace("name : ", "name" + separator), "unsupported multiline quoted YAML scalar")
    for value in ['&label "safe"', '!!str "safe"', '*label', '!<tag:yaml.org,2002:str> "safe"']:
        expect_status(1, "root scalar property rejected: " + value, "name: " + value + "\n" + good, "unsupported YAML scalar property")
    for key in ["'name'", '"name"', "display name", "? name"]:
        expect_status(1, "unsupported key form rejected: " + key, scalar_job.replace("name : ", key + ": "), "unsupported YAML key or line")
    for value in ['["', '{label: "']:
        expect_status(1, "uncertain flow scalar rejected: " + value, scalar_job.replace('name : "', "name: " + value), "unsupported YAML flow scalar")
    expect_status(1, "flow alias rejected", "name: [*label]\n" + good, "unsupported YAML flow scalar")
    expect_status(1, "missing colon separation rejected", scalar_job.replace('name : "', 'name:"'), "unsupported YAML key or line")
    expect_status(1, "unmodeled scalar indicator rejected", "name: ? unknown\n" + good, "unsupported YAML key or line")
    expect_status(1, "uncertain block header rejected", "name: |unknown\n" + good, "unsupported YAML block scalar")
    expect_status(0, "supported inline collections remain valid", "permissions: {}\n" + good.replace("    steps:", "    needs: [first, second]\n    steps:"))
    fake_job = "name: |\n" + good.removeprefix("jobs:\n") + "jobs:\n  real:\n    steps:\n      - run: echo done\n"
    expect_status(1, "root scalar cannot impersonate go-fuzz", fake_job, "exactly one go-fuzz job")
    expect_status(0, "root block scalar before real jobs", "name: |\n  description\n" + good)
    expect_status(0, "single-line quoted YAML values", "name: 'description'\n" + good.replace("first target", '"first target"'))
    expect_status(1, "quoted scalar cannot impersonate go-fuzz", fake_job.replace("name: |", 'name: "').replace("\njobs:\n", '\n  "\njobs:\n'), "unsupported multiline quoted YAML scalar")
    expect_status(1, "jobs must be a root mapping", good.replace("jobs:", "jobs: |"), "root jobs mapping")
    expect_status(1, "nested jobs mapping rejected", "wrapper:\n" + "\n".join("  " + line for line in good.splitlines()), "root jobs mapping")
    expect_status(1, "duplicate root jobs mapping rejected", good + good, "root jobs mapping")
    expect_status(1, "job scalar cannot supply steps", good.replace("go-fuzz:", "go-fuzz: |"), "exactly one go-fuzz job")
    expect_status(1, "steps scalar cannot supply commands", good.replace("steps:", "steps: |"), "one go-fuzz steps list")
    expect_status(1, "removed target run", prefix + first, "FuzzBeta")
    expect_status(1, "YAML comment cannot supply flags", good.replace("-fuzz=FuzzBeta", "# -fuzz=FuzzBeta"), "expected exactly one")
    expect_status(1, "commented-out run cannot supply coverage", good.replace("        run: go test -fuzz=FuzzBeta", "        # run: go test -fuzz=FuzzBeta"), "FuzzBeta")
    expect_status(1, "disabled step cannot supply coverage", good.replace(second, second + "        if: false\n"), "FuzzBeta")
    expect_status(0, "explicit true condition", good.replace(second, second + "        if: true\n"))
    for condition in ["${{ !cancelled() }}", "${{ !cancelled() }} # respect cancellation"]:
        expect_status(0, "cancellation-aware step condition: " + condition,
                      good.replace(second, second + "        if: " + condition + "\n"))
    expect_status(1, "unknown condition fails closed", good.replace(second, second + "        if: success()\n"), "unsupported step condition")
    expect_status(1, "expression condition fails closed", good.replace(second, second + "        if: ${{ inputs.fuzz }}\n"), "unsupported step condition")

    for bound, reason in [
        ("0.1ns", "unsupported -fuzztime bound"),
        ("1.5s", "unsupported -fuzztime bound"),
        ("0s", "non-positive"),
        ("-1s", "non-positive"),
        ("1m30s", "unsupported -fuzztime bound"),
        ("30", "unsupported -fuzztime bound"),
        ("30x", "unsupported -fuzztime bound"),
    ]:
        expect_status(1, f"reject bound {bound}", good.replace("30s", bound), reason)

    # Hand-calculated adjacent int64-nanosecond boundaries discriminate each
    # unit conversion in both directions, including a smaller wrong factor.
    for unit, last_valid, first_invalid in [
        ("ns", "9223372036854775807", "9223372036854775808"),
        ("us", "9223372036854775", "9223372036854776"),
        ("ms", "9223372036854", "9223372036855"),
        ("s", "9223372036", "9223372037"),
        ("m", "153722867", "153722868"),
        ("h", "2562047", "2562048"),
    ]:
        expect_status(0, f"adjacent valid boundary {unit}", good.replace("30s", last_valid + unit))
        expect_status(1, f"just-over-limit boundary {unit}", good.replace("30s", first_invalid + unit), "overflow -fuzztime")
        expect_status(0, f"small valid bound {unit}", good.replace("30s", "1" + unit))

    for flag in ["-fuzztime=30s", "-fuzztime=1s", "-fuzz=FuzzAlpha", "-fuzz=FuzzBeta"]:
        reason = "duplicate -" + flag.split("=", 1)[0][1:]
        expect_status(1, f"duplicate or conflicting {flag}", good.replace(" ./services/alpha/", f" {flag} ./services/alpha/"), reason)
    for content in [good.replace("-fuzz=FuzzAlpha", "-args -fuzz=FuzzAlpha"), good.replace(" ./services/alpha/", " -args ./services/alpha/")]:
        expect_status(1, "-args placement", content, "unsupported -args")
    expect_status(1, "anchored selector rejected explicitly", good.replace("FuzzAlpha -fuzztime", "^FuzzAlpha$ -fuzztime"), "unsupported -fuzz selector")
    expect_status(1, "unsupported extra flag", good.replace("go test", "go test -v"), "unsupported go test flag")
    expect_status(1, "missing time bound", good.replace(" -fuzztime=30s", ""), "expected exactly one")
    expect_status(1, "empty run cannot supply coverage", good.replace("go test -fuzz=FuzzBeta -fuzztime=30s ./services/beta/", ""), "FuzzBeta")
    expect_status(1, "wrong package does not cover target", good.replace("./services/beta/", "./services/other/"), "FuzzBeta")
    expect_status(1, "package wildcard rejected", good.replace("./services/beta/", "./services/..."), "unsupported package path")
    expect_status(1, "shell wrapper rejected", good.replace("go test", "echo go test"), "expected bare go test")
    expect_status(1, "shell operator rejected", good.replace("go test", "true && go test"), "unsupported shell syntax")
    expect_status(1, "shell expansion rejected", good.replace("30s", "$(bound)"), "unsupported -fuzztime bound")
    expect_status(0, "flags in either order", good.replace("-fuzz=FuzzAlpha -fuzztime=30s", "-fuzztime=30s -fuzz=FuzzAlpha"))
    expect_status(0, "trailing comments allowed", good.replace("./services/beta/", "./services/beta/ # a comment"))
    for form, content in [("plain", good), ("literal", good.replace("run: go test", "run: |\n          go test"))]:
        for character in ["é", "\t", "\u0085", "\u2028", "\u2029", "\u00a0", "\u2009"]:
            commented = content.replace("./services/beta/", "./services/beta/ # note" + character + "text")
            expect_status(0, form + " trailing comment allows " + ascii(character), commented)
            expect_status(1, form + " comment cannot hide executable character " + ascii(character),
                          commented.replace("go test", "go" + character + "test"), "unsupported command character")
        expect_status(1, form + " attached hash is not a comment",
                      content.replace("./services/beta/", "./services/beta/#comment"), "unsupported shell syntax")
        for character in ["\x01", "\x1f"]:
            expect_status(1, form + " comment retains workflow control refusal " + ascii(character),
                          content.replace("./services/beta/", "./services/beta/ # note" + character + "text"),
                          "unsupported YAML control character")
    expect_status(0, "literal run block", good.replace("run: go test", "run: |\n          go test"))
    expect_status(0, "comment-only literal line", good.replace("run: go test", "run: |\n          # comment\n          go test"))
    expect_status(0, "blank lines", good.replace(first, "\n" + first + "\n"))
    for indent in [0, 2, 4, 6, 8, 10]:
        for location, content in [("before steps", good.replace("    steps:", " " * indent + "# comment\n    steps:")), ("between steps", good.replace(second, " " * indent + "# comment\n" + second))]:
            expect_status(0, f"standalone comment at indent {indent} {location}", content)
    expect_status(0, "next job cannot corrupt scan", good + "  other:\n    steps:\n      - run: false\n")
    expect_status(1, "another job cannot supply coverage", prefix + first + "  other:\n    steps:\n" + second, "FuzzBeta")
    expect_status(0, "action metadata ignored", prefix + "      - uses: example/action\n        with:\n          arbitrary: value\n" + first + second)

    for label, content, reason in [
        ("missing job", good.replace("  go-fuzz:", "  other:"), "exactly one go-fuzz job"),
        ("duplicate job", good + good.removeprefix("jobs:\n"), "exactly one go-fuzz job"),
        ("missing steps", good.replace("    steps:", "    absent:"), "one go-fuzz steps list"),
        ("duplicate steps", good + "    steps:\n", "one go-fuzz steps list"),
        ("bad step structure", good.replace("      - name: first target", "        name: first target"), "unsupported steps structure"),
        ("bad run indentation", good + "          stray: value\n", "unsupported run indentation"),
        ("bad step field", good.replace("        run:", "        Invalid: value\n        run:"), "unsupported step field syntax"),
        ("working directory override", good.replace(second, second + "        working-directory: elsewhere\n"), "unsupported run-step field"),
        ("duplicate condition", good.replace(second, second + "        if: true\n        if: true\n"), "duplicate run-step field"),
        ("folded scalar", good.replace("run: go test", "run: >\n          go test"), "unsupported run scalar"),
        ("quoted scalar", good.replace("run: go test", "run: 'go test").replace("./services/alpha/", "./services/alpha/'").replace("./services/beta/", "./services/beta/'"), "unsupported run scalar"),
    ]:
        expect_status(1, label, content, reason)

    extra = fixture / "services/alpha/extra_test.go"
    extra.write_text("package alpha\nfunc FuzzNew(f *testing.F) {}\n", encoding="utf-8")
    expect_status(1, "new fuzz target requires command", reason="FuzzNew")
    extra.write_text("package alpha\nfunc helper() {}; func FuzzNew(f *testing.F) {}\n", encoding="utf-8")
    expect_status(1, "same-line fuzz declaration requires command", reason="FuzzNew")
    expect_status(0, "same-line fuzz declaration with command", good + "      - run: go test -fuzz=FuzzNew -fuzztime=30s ./services/alpha/\n")
    for name in ["FuzzÉ", "FuzzAlphaÉ", "Fuzz"]:
        extra.write_text(f"package alpha\nfunc {name}(f *testing.F) {{}}\n", encoding="utf-8")
        expect_status(1, f"unsupported Go fuzz name {name} rejected explicitly", reason="unsupported fuzz target name: " + name)
    for name in ["Fuzzé", "Fuzzhelper"]:
        extra.write_text(f"package alpha\nfunc {name}(f *testing.F) {{}}\n", encoding="utf-8")
        expect_status(0, f"lowercase suffix {name} is not a Go fuzz name")
    extra.write_text("package alpha\ntype helper struct{}\nfunc (helper) FuzzMethod(f *testing.F) {}\n", encoding="utf-8")
    expect_status(0, "receiver method is not a top-level fuzz declaration")
    for name in ["Fuzz0", "Fuzz_"]:
        extra.write_text(f"package alpha\nfunc {name}(f *testing.F) {{}}\n", encoding="utf-8")
        expect_status(0, f"Go fuzz name {name} has a command", good + f"      - run: go test -fuzz={name} -fuzztime=30s ./services/alpha/\n")
    extra.write_text("package alpha\nfunc FuzzAlphaExtra(f *testing.F) {}\n", encoding="utf-8")
    expect_status(1, "prefix-colliding selectors cannot supply coverage", good + "      - run: go test -fuzz=FuzzAlphaExtra -fuzztime=30s ./services/alpha/\n", "ambiguous -fuzz selector: FuzzAlpha")
    extra.write_text("package alpha\n", encoding="utf-8")
    expect_status(0, "unique substring selector follows Go regex matching", good.replace("FuzzAlpha -fuzztime", "FuzzAl -fuzztime"))
    expect_status(1, "unmatched selector rejected explicitly", good.replace("FuzzAlpha -fuzztime", "FuzzAbsent -fuzztime"), "no matching Go fuzz target")
    other_package = fixture / "services/beta/extra_test.go"
    other_package.write_text("package beta\nfunc FuzzAlphaExtra(f *testing.F) {}\n", encoding="utf-8")
    expect_status(0, "selector ambiguity is scoped to its package", good + "      - run: go test -fuzz=FuzzAlphaExtra -fuzztime=30s ./services/beta/\n")
    other_package.write_text("package beta\n", encoding="utf-8")
    extra.write_text('// func FuzzComment(f *testing.F) {}\n/*\nfunc FuzzBlock(f *testing.F) {}\n*/\nvar example = `\nfunc FuzzString(f *testing.F) {}\n`\n', encoding="utf-8")
    expect_status(0, "Go comments and strings are not targets")
    for path in fixture.rglob("*_test.go"):
        path.write_text("package empty\n", encoding="utf-8")
    expect_status(1, "empty inventory fails closed", reason="empty Go fuzz target inventory")

    for relative, source in real_sources:
        path = fixture / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    expect_status(0, "both real target steps run", real_workflow)
    jwt_step = re.search(r"(?m)^      - name: Run Go fuzz smoke \(JWT[^\n]*\n(?:        [^\n]*\n)*", real_workflow).group(0)
    unconditional_jwt = re.sub(r"(?m)^        if:.*\n", "", jwt_step)
    expect_status(0, "conditioned shortened JWT selector covers resolved target",
                  real_workflow.replace(jwt_step, jwt_step.replace("-fuzz=FuzzSplitJWTAndHeader", "-fuzz=FuzzSplit"), 1))
    expect_status(1, "ungated shortened JWT selector requires resolved target condition",
                  real_workflow.replace(jwt_step, unconditional_jwt.replace("-fuzz=FuzzSplitJWTAndHeader", "-fuzz=FuzzSplit"), 1),
                  "JWT fuzz step must use if: ${{ !cancelled() }}")
    expect_status(0, "isolated JWT literal command allows comments and blank lines",
                  real_workflow.replace(jwt_step, jwt_step.replace("        run: ", "        run: |\n          # JWT command\n\n          ", 1), 1))
    chat_step = re.search(r"(?m)^      - name: Run Go fuzz smoke \(chat request parser\)\n        run: (.*)\n", real_workflow)
    combined_jwt = jwt_step.replace("        run: ", "        run: |\n          " + chat_step[1] + "\n          ", 1)
    expect_status(1, "combined chat and JWT literal block cannot supply independent coverage",
                  real_workflow.replace(chat_step[0], "", 1).replace(jwt_step, combined_jwt, 1),
                  "JWT fuzz command must be isolated in its run step")
    for condition in [None, "true", "success()", "${{ success() }}", "always()", "${{ always() }}"]:
        changed_step = unconditional_jwt if condition is None else unconditional_jwt + "        if: " + condition + "\n"
        reason = ("JWT fuzz step must use if: ${{ !cancelled() }}" if condition in (None, "true")
                  else "unsupported step condition: " + condition)
        expect_status(1, "JWT step rejects success gating or cancellation bypass: " + str(condition),
                      real_workflow.replace(jwt_step, changed_step, 1), reason)
    for field, value in [("working-directory", "services/auth"), ("shell", "python")]:
        for location in ["before", "after"]:
            defaults = f"defaults:\n  run:\n    {field}: {value}\n"
            changed = defaults + real_workflow if location == "before" else real_workflow + "\n" + defaults
            expect_status(1, f"workflow defaults {field} {location} jobs", changed, "unsupported workflow defaults")
            defaults = "\n".join("    " + line for line in defaults.split("\n") if line) + "\n"
            changed = real_workflow.replace("  go-fuzz:\n", "  go-fuzz:\n" + defaults) if location == "before" else real_workflow.replace("\n  trivy:", "\n" + defaults + "\n  trivy:")
            expect_status(1, f"job defaults {field} {location} steps", changed, "unsupported go-fuzz defaults")
    expect_status(0, "sibling job defaults do not affect fuzz commands",
                  real_workflow.replace("  trivy:\n", "  trivy:\n    defaults:\n      run:\n        shell: python\n"))
    job = re.search(r"(?ms)^  go-fuzz:\n(.*?)(?=^  \S|\Z)", real_workflow).group(1)
    for condition in ["false", "'false'", '"false"', "False", "FALSE", "${{ false }}", "0", "null", "''", '""',
                      "success()", "${{ inputs.fuzz }}"]:
        changed_job = re.sub(r"(?m)^    if:.*$", "    if: " + condition, job, count=1)
        expect_status(1, "real disabled or unsupported job condition: " + condition,
                      real_workflow.replace(job, changed_job, 1), "unsupported or disabled go-fuzz job condition")
    unconditional_job = re.sub(r"(?m)^    if:.*\n", "", job, count=1)
    expect_status(0, "explicit true job condition", real_workflow.replace(job, unconditional_job + "    if: true\n", 1))
    expect_status(1, "disabled job condition after steps", real_workflow.replace(job, unconditional_job + "    if: false\n", 1),
                  "unsupported or disabled go-fuzz job condition")
    expect_status(1, "duplicate job condition", real_workflow.replace("  go-fuzz:\n", "  go-fuzz:\n    if: true\n"),
                  "duplicate go-fuzz job condition")
    expect_status(1, "disabled real step cannot supply coverage",
                  real_workflow.replace(jwt_step, unconditional_jwt + "        if: false\n", 1),
                  "FuzzSplitJWTAndHeader")
    for character in ["\u0085", "\u2028", "\u2029"]:
        expect_status(0, "real workflow Unicode name: " + ascii(character),
                      re.sub(r"(?m)^name:.*$", "name: Build" + character + "tests", real_workflow, count=1))
        expect_status(1, "real workflow Unicode command separator: " + ascii(character),
                      real_workflow.replace("run: go test", "run: go" + character + "test"), "unsupported command character")
    for value in ["?why", ":smile", "Build:\u00a0tests", "Build:\u2009tests"]:
        expect_status(0, "real workflow name prefix: " + value, re.sub(r"(?m)^name:.*$", "name: " + value, real_workflow, count=1))
    real_runs = re.findall(r"(?m)^        run: go test -fuzz=(\w+) -fuzztime=\S+ \S+\n", job)
    assert real_runs, "expected real fuzz commands for removal checks"
    for name in real_runs:
        without_run = re.sub(r"(?m)^        run: go test -fuzz=" + name + r" -fuzztime=\S+ \S+\n", "", real_workflow)
        expect_status(1, f"removed real run: {name}", without_run, name)

print("All Go fuzz guard regression cases passed.")
PY
