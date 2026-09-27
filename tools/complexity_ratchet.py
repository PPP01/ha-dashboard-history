"""Complexity may only go down: compare ruff's measurements with a baseline.

`ruff` checks three rules here (see `pyproject.toml`): cyclomatic
complexity (C901), branches (PLR0912) and statements (PLR0915) per
function. Fifteen functions broke those limits when the check was
introduced; they are listed with their values in
`tools/complexity-baseline.json`, each with the issue meant to take it
apart. This script fails when

- a function not in the baseline breaks a limit (new code stays within it),
- a value is above its baseline (a known outlier grew), or
- a value is below its baseline, or an entry is no longer reported at
  all (then the baseline is lowered in the same commit, so an
  improvement can never quietly be given back).

`# noqa` comments are ignored on purpose: an exception is always a
visible change to the baseline file, never a comment in the code.

Run from the repository root: `python3 tools/complexity_ratchet.py`.
"""

from __future__ import annotations

import ast
import json
import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CHECKED = "custom_components/dashboard_history"
BASELINE = ROOT / "tools" / "complexity-baseline.json"
_VALUE = re.compile(r"\((\d+) > \d+\)")


def function_at(source: str, row: int) -> str:
    """The dotted name of the function whose `def` sits on `row`."""

    def walk(node: ast.AST, stack: list[str]) -> str | None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names = [*stack, child.name]
                if not isinstance(child, ast.ClassDef) and child.lineno == row:
                    return ".".join(names)
                found = walk(child, names)
            else:
                found = walk(child, stack)
            if found is not None:
                return found
        return None

    name = walk(ast.parse(source), [])
    if name is None:
        raise LookupError(f"no function starts on line {row}")
    return name


def _ruff() -> list[str]:
    """ruff on PATH, else the ruff installed next to this interpreter."""
    found = shutil.which("ruff")
    return [found] if found else [sys.executable, "-m", "ruff"]


def measure(root: pathlib.Path = ROOT) -> dict[str, dict[str, int]]:
    """Every reported value, keyed by `path::function`, then by rule."""
    result = subprocess.run(
        [*_ruff(), "check", CHECKED, "--ignore-noqa", "--output-format", "json", "--exit-zero"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    measured: dict[str, dict[str, int]] = {}
    sources: dict[str, str] = {}
    for item in json.loads(result.stdout):
        path = pathlib.Path(item["filename"]).resolve().relative_to(root.resolve()).as_posix()
        if path not in sources:
            sources[path] = (root / path).read_text(encoding="utf-8")
        key = f"{path}::{function_at(sources[path], item['location']['row'])}"
        match = _VALUE.search(item["message"])
        if match is None:
            raise ValueError(f"no value in ruff's message: {item['message']!r}")
        measured.setdefault(key, {})[item["code"]] = int(match.group(1))
    return measured


def compare(measured: dict[str, dict[str, int]], baseline: dict[str, dict]) -> list[str]:
    """Every way `measured` departs from `baseline`, as sentences."""
    problems = []
    for key, rules in sorted(measured.items()):
        for rule, value in sorted(rules.items()):
            known = baseline.get(key, {}).get(rule)
            if known is None:
                problems.append(f"{key}: {rule} is {value}, over the limit and not in the baseline")
            elif value > known:
                problems.append(f"{key}: {rule} grew from {known} to {value}")
            elif value < known:
                problems.append(f"{key}: {rule} fell from {known} to {value} - lower the baseline to {value}")
    for key, rules in sorted(baseline.items()):
        for rule in sorted(r for r in rules if r != "issue"):
            if rule not in measured.get(key, {}):
                problems.append(f"{key}: {rule} is within the limit now - remove it from the baseline")
    return problems


def main() -> int:
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    problems = compare(measure(), baseline)
    for problem in problems:
        print(problem)
    if problems:
        print(f"{len(problems)} problem(s); see tools/complexity_ratchet.py for what each means")
        return 1
    print(f"complexity: {sum(len(r) - ('issue' in r) for r in baseline.values())} known values, none grew")
    return 0


if __name__ == "__main__":
    sys.exit(main())
