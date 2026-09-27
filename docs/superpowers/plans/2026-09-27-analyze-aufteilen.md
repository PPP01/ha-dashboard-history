# `analyze.py` aufteilen – Implementierungsplan (Vorhaben P)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eine Wache gegen erneutes Zuwachsen einführen, `analyze.py` in ein Paket mit fünf Modulen teilen und `plan_undo` in Planer je Art zerlegen – ohne ein einziges Ergebnis zu ändern.

**Architecture:** Drei Teile in dieser Reihenfolge. P1 (Aufgaben 1–2): `ruff` misst Komplexität, ein Skript vergleicht mit einer Baseline, die nur sinken darf; `import-linter` prüft HA-Freiheit und Schichten; beides in der CI. P2 (Aufgaben 3–9): `analyze.py` wird per `git mv` ein Paket, ein Umzugsskript löst fünf Module von unten nach oben heraus, `__init__.py` wird zur erklärten Schnittstelle. P3 (Aufgaben 10–13): ein Vergleichswerkzeug lädt den Stand nach P2 neben dem Arbeitsbaum und vergleicht; dann wird `plan_undo` durch Kontext, Vorprüfungen, fünf Planer und einen Kombinierer ersetzt.

**Tech Stack:** Python 3.12 (Entwicklung) / 3.14 (Container), pytest, `ruff==0.16.9`, `import-linter==2.15`, `dulwich==1.2.14`, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-27-analyze-aufteilen-design.md` (freigegeben am 2026-09-27, Commit `5670afc`). Bei Widerspruch gilt die Spec.

## Vorab: was an diesem Plan schon erprobt ist

Alles Folgende wurde am 2026-09-27 vor dem Schreiben an Kopien des Repositorys im Scratchpad ausprobiert, nicht nur entworfen:

| Baustein | Ergebnis |
|---|---|
| Sperrklinke (Aufgabe 1) | an einer Kopie: 23 Werte, grün; ein um eins gewachsenes `plan_undo` und ein neu über die Grenze geschobenes `_similarity` werden gemeldet, Exit-Code 1 |
| Importverträge (Aufgabe 2) | HA-Freiheit hält am echten Paket, Gegenprobe mit `operations` bricht; optionale Schichten in Klammern halten, solange ein Modul fehlt, und werden streng geprüft, sobald es existiert; der Vertrag gilt auch, solange `analyze` noch eine Datei ist |
| Umzugsskript (Aufgaben 4–8) | an einer Kopie alle fünf Module nacheinander herausgelöst, nach jedem Schritt `968 passed, 2 skipped`; am Ende beide Verträge `KEPT`; `matching.py` 723 Zeilen, `undo.py` 650 vor P3 |
| Planer (Aufgabe 11) | Prototyp gegen das heutige `plan_undo`: alle 105 Aufrufe der Testsuite gleich; 10 001 erzeugte und konstruierte Eingaben (19 Ausgangsstände, davon 14 echte Dashboards) mit 0 Abweichungen; höchste Komplexität 9; `plan_undo` allein rund 18 % schneller (7,4 s gegen 9,0 s) – **nach dem Plan-Review überholt:** der Vorsprung kam daher, dass der Kontext Werte nicht berechnete, die die alte Fassung vorab berechnete, und genau darin lag Astras Befund; mit der Korrektur Verhältnis 1,01 |
| Vergleichswerkzeug (Aufgabe 10) | erreicht mit dem Generator 18 der 23 Verweigerungstexte, mit sieben konstruierten Fällen alle 23; 33 Vorrang-Paare, die übrigen 12 sind strukturell unmöglich (siehe Aufgabe 12) |
| **Der ganze Plan, Aufgaben 1–11** (vor dem Plan-Review) | an einer Kopie mit Wegwerf-Git, jeder Codeblock **wörtlich aus diesem Plan** herausgezogen: Sperrklinke 23 Werte grün, Verträge 2 kept; Umzug 34/27/1/23/10 Namen; `976 passed, 2 skipped` (968 plus 6 plus 2 neue Tests); Werkzeug alt gegen alt 0 Abweichungen, 23/23; nach Aufgabe 11 0 Abweichungen, 23/23, 33 Paare mit genau den zwölf vorhergesagten Lücken, Verhältnis 0,86, drei erwartete Sperrklinken-Zeilen, danach 20 Werte grün; `undo.py` 810 Zeilen, höchste Komplexität dort `_plan_sections` mit 12 (bleibt in der Baseline), dann die Planer mit 9. Dabei gefunden und hier schon korrigiert: der Schnittstellentest ist vor Schritt 3 von Aufgabe 9 nur halb rot, und das Werkzeug brauchte eine abwechselnde Reihenfolge für eine ehrliche Laufzeit |

## Global Constraints

- **Verhaltensneutral:** Für jede Eingabe liefert jede öffentliche Funktion byte-gleich dasselbe Ergebnis, einschließlich Schrittreihenfolge und Wortlaut jeder Verweigerung. **Eine Ausnahme ist auch ein Ergebnis:** Wo die alte Fassung wirft, wirft die neue dieselbe Ausnahme an derselben Stelle (Astra, Plan-Review). Ausgenommen sind nur Klassenmetadaten (`__module__`, Klassen-`repr`, `pickle`-Bytes), Spec Entscheidung 14.
- **Kein bestehender Test wird geändert.** Muss einer geändert werden, ist das ein Export-Fehler, kein Testfehler – anhalten und melden.
- **Keine Stilregeln:** `ruff` prüft nur `C901`, `PLR0912`, `PLR0915` mit den Grenzen 10 / 12 / 50. Nichts wird umformatiert.
- **Keine Änderung** an `operations.py`, `restore.py`, `services.py`, `store.py`, `panel.js` – auch kein Kommentar.
- **`analyze` bleibt frei von Home Assistant**, jedes Teilmodul.
- **No shelling out to `git`** in Code, der im Repository liegt – `dulwich` only. (Git-Befehle, die der Ausführende selbst im Terminal eingibt, sind davon nicht betroffen.)
- **Werkzeugversionen gepinnt:** `ruff==0.16.9`, `import-linter==2.15`.
- **Grenzen:** kein Modul in `analyze/` über 900 physische Zeilen; kein neuer Planer, keine Vorprüfung in der Baseline.
- **Sprache:** Code, Kommentare, Docstrings, Commit-Messages englisch; dieser Plan und sein Nachtrag deutsch.
- **Commits:** Subject englisch, Imperativ, höchstens 50 Zeichen, Leerzeile, Body mit dem Warum, höchstens 72 Zeichen je Zeile, Zeile `Refs #41`, dann `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. **Nicht pushen.**
- **Öffentlich:** Das Repository ist öffentlich. Keine Pfade von diesem Rechner, keine Angaben über die Installation, keine Dashboard-Inhalte in Commits, Code oder Journal.
- **Werkzeugumgebung:** `ruff` und `import-linter` außerhalb des Repositorys installieren und über `PATH` aufrufen:

  ```bash
  python3 -m venv /tmp/dh-tools
  /tmp/dh-tools/bin/pip install "ruff==0.16.9" "import-linter==2.15"
  export PATH=/tmp/dh-tools/bin:$PATH
  ```

  Alle Befehle in diesem Plan laufen aus der Repository-Wurzel.

## Review Focus

Eingaben und Zustände, die die Spec nahelegt, die aber kein bestehender Test abdeckt – am wahrscheinlichsten zuerst:

1. **Home Assistant lädt das Unterpaket nicht oder anders als pytest.** Erwartet: die Integration startet, jeder Dienst und jeder WebSocket-Befehl antwortet wie vorher. Geprüft in Aufgabe 3 (nach `git mv`) und Aufgabe 12 mit `run_checks.py` im Testcontainer.
2. **Ein HACS-Update lässt `analyze.py` neben `analyze/` liegen.** Erwartet: das Paket gewinnt. Geprüft in Aufgabe 3, Schritt 6, im Container unter Python 3.14.
3. **Ein Stand mit einem Nicht-Dict-Eintrag in `views`** (bekannter offener Befund in `status.md`). Erwartet: dasselbe Ergebnis wie vorher, auch wenn es heute falsch ist. Abgedeckt durch einen Ausgangsstand mit `"junk"` im Vergleichswerkzeug (Aufgabe 10).
4. **`True` gegen `1` in einer Einstellung.** Erwartet: die neue Fassung unterscheidet genauso streng wie die alte. Abgedeckt durch die kanonische Form und die Mutationen `column_span`/`visible`/`hide_energy` mit `True` und `1` (Aufgabe 10).
5. **Große echte Dashboards.** Erwartet: `plan_undo` nicht langsamer als 110 %. Gemessen in Aufgabe 12 über die echten Dashboards aus `.real-storage`.

---

## P1 – Die Wache

### Aufgabe 1: Die Komplexitäts-Sperrklinke

**Files:**
- Create: `pyproject.toml`
- Create: `tools/complexity_ratchet.py`
- Create: `tools/complexity-baseline.json`
- Create: `tests/test_complexity_ratchet.py`
- Modify: `.github/workflows/test.yml`

**Interfaces:**
- Produces: `python3 tools/complexity_ratchet.py` (Exit 0 = grün); `tools/complexity-baseline.json` mit Schlüsseln `"<pfad>::<funktion>"` und Werten `{"issue": "#N", "<regel>": <zahl>, …}`. Die Aufgaben 3, 5, 7, 8 und 11 benennen Schlüssel darin um oder streichen sie.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`tests/test_complexity_ratchet.py`:

```python
"""Tests for the complexity ratchet.

The ratchet decides whether a commit may land, so its three refusals
are pinned here on made-up numbers - running ruff is not needed for
that, and the CI job that runs ruff checks the real code.
"""

import importlib.util
import pathlib

_PATH = pathlib.Path(__file__).resolve().parents[1] / "tools" / "complexity_ratchet.py"
_SPEC = importlib.util.spec_from_file_location("complexity_ratchet", _PATH)
ratchet = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ratchet)

BASELINE = {"a.py::big": {"issue": "#41", "C901": 20, "PLR0912": 14}}


def test_nothing_changed_is_clean():
    assert ratchet.compare({"a.py::big": {"C901": 20, "PLR0912": 14}}, BASELINE) == []


def test_a_function_new_to_the_list_is_refused():
    problems = ratchet.compare(
        {"a.py::big": {"C901": 20, "PLR0912": 14}, "a.py::fresh": {"C901": 11}}, BASELINE
    )
    assert problems == ["a.py::fresh: C901 is 11, over the limit and not in the baseline"]


def test_a_known_outlier_that_grew_is_refused():
    problems = ratchet.compare({"a.py::big": {"C901": 21, "PLR0912": 14}}, BASELINE)
    assert problems == ["a.py::big: C901 grew from 20 to 21"]


def test_an_improvement_asks_for_a_lower_baseline():
    problems = ratchet.compare({"a.py::big": {"C901": 18, "PLR0912": 14}}, BASELINE)
    assert problems == ["a.py::big: C901 fell from 20 to 18 - lower the baseline to 18"]


def test_a_value_back_within_the_limit_asks_for_removal():
    problems = ratchet.compare({"a.py::big": {"C901": 20}}, BASELINE)
    assert problems == ["a.py::big: PLR0912 is within the limit now - remove it from the baseline"]


def test_a_function_is_named_with_its_class_and_outer_function():
    source = (
        "class Store:\n"
        "    def method(self):\n"
        "        def inner():\n"
        "            pass\n"
        "def top():\n"
        "    pass\n"
    )
    assert ratchet.function_at(source, 2) == "Store.method"
    assert ratchet.function_at(source, 3) == "Store.method.inner"
    assert ratchet.function_at(source, 5) == "top"
```

- [ ] **Step 2: Test laufen lassen, er muss fehlschlagen**

Run: `python3 -m pytest tests/test_complexity_ratchet.py -v`
Expected: FAIL beim Import – `FileNotFoundError` für `tools/complexity_ratchet.py`.

- [ ] **Step 3: Das Skript schreiben**

`tools/complexity_ratchet.py`:

```python
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
```

- [ ] **Step 4: Tests laufen lassen, sie müssen grün sein**

Run: `python3 -m pytest tests/test_complexity_ratchet.py -v`
Expected: 6 passed.

- [ ] **Step 5: `pyproject.toml` anlegen**

```toml
# Tool configuration only. The integration is distributed through HACS,
# which copies custom_components/dashboard_history/ and nothing else;
# there is deliberately no [project] table and no build system here.

[tool.ruff.lint]
# Complexity only (spec P, decision 6). Style and formatting rules would
# touch nearly every file, and style changes happen here on request only.
select = ["C901", "PLR0912", "PLR0915"]

[tool.ruff.lint.mccabe]
max-complexity = 10

[tool.ruff.lint.pylint]
max-branches = 12
max-statements = 50
```

- [ ] **Step 6: Das Sammel-Issue für die übrigen Ausreißer anlegen – nur nach Freigabe**

Das ist eine öffentliche Aktion. Den folgenden Text dem Nutzer als Vorschau zeigen und **erst nach seinem Go** anlegen (`gh issue create --label enhancement --title … --body-file …`). Die vergebene Nummer als `#N` notieren.

Titel: `Bring the remaining complexity outliers under the limit`

```markdown
`tools/complexity_ratchet.py` (#41) holds every function that broke the complexity limits (`C901` 10, `PLR0912` 12, `PLR0915` 50) when the check was introduced. Some have an issue of their own: `plan_undo` and `_plan_sections` (#41), `_explain` (#37), four methods of `HistoryStore` (#42). This one collects the rest:

| Function | Values |
|---|---|
| `analyze` `_match_slots` | C901 15, PLR0912 13 |
| `analyze` `_pair_view_sections` | C901 12 |
| `operations.async_restore_state` | C901 11 |
| `operations.async_undo_change` | C901 14, PLR0912 13 |
| `operations.async_compare` | C901 15 |
| `restore.reinsert` | C901 12 |
| `restore.apply_undo` | C901 14, PLR0912 13 |
| `services.async_register` | C901 18 |

None of them is urgent: the ratchet already stops them from growing. Each one taken apart lowers the baseline in the same commit.
```

- [ ] **Step 7: Die Baseline schreiben**

`tools/complexity-baseline.json` – exakt diese 23 Werte, gemessen am 2026-09-27; `#N` durch die Nummer aus Schritt 6 ersetzen:

```json
{
  "custom_components/dashboard_history/analyze.py::_match_slots": {"issue": "#N", "C901": 15, "PLR0912": 13},
  "custom_components/dashboard_history/analyze.py::_pair_view_sections": {"issue": "#N", "C901": 12},
  "custom_components/dashboard_history/analyze.py::_plan_sections": {"issue": "#41", "C901": 12},
  "custom_components/dashboard_history/analyze.py::plan_undo": {"issue": "#41", "C901": 54, "PLR0912": 40, "PLR0915": 128},
  "custom_components/dashboard_history/analyze.py::_explain": {"issue": "#37", "C901": 29, "PLR0912": 26, "PLR0915": 63},
  "custom_components/dashboard_history/operations.py::async_restore_state": {"issue": "#N", "C901": 11},
  "custom_components/dashboard_history/operations.py::async_undo_change": {"issue": "#N", "C901": 14, "PLR0912": 13},
  "custom_components/dashboard_history/operations.py::async_compare": {"issue": "#N", "C901": 15},
  "custom_components/dashboard_history/restore.py::reinsert": {"issue": "#N", "C901": 12},
  "custom_components/dashboard_history/restore.py::apply_undo": {"issue": "#N", "C901": 14, "PLR0912": 13},
  "custom_components/dashboard_history/services.py::async_register": {"issue": "#N", "C901": 18},
  "custom_components/dashboard_history/store.py::HistoryStore._read_checkpoint": {"issue": "#42", "C901": 15, "PLR0912": 15},
  "custom_components/dashboard_history/store.py::HistoryStore._walked_changes": {"issue": "#42", "C901": 12},
  "custom_components/dashboard_history/store.py::HistoryStore._resolve": {"issue": "#42", "C901": 11},
  "custom_components/dashboard_history/store.py::HistoryStore.survey": {"issue": "#42", "C901": 13}
}
```

- [ ] **Step 8: Die Sperrklinke am echten Code laufen lassen**

Run: `python3 tools/complexity_ratchet.py`
Expected: `complexity: 23 known values, none grew`, Exit 0. Meldet sie etwas anderes, stimmt ein Wert nicht – nicht die Baseline anpassen, sondern anhalten und melden: dann hat sich der Code seit dem 2026-09-27 geändert.

- [ ] **Step 9: Die Gegenprobe – ein Kommentar schützt nicht**

In `custom_components/dashboard_history/analyze.py` vorübergehend hinter `def plan_undo(before: dict, after: dict, current: dict) -> UndoPlan:` den Kommentar `  # noqa: C901` anhängen und eine Zeile `    if before is after:\n        pass` als erste Anweisung nach dem Docstring einfügen.
Run: `python3 tools/complexity_ratchet.py`
Expected: `…plan_undo: C901 grew from 54 to 55` (und ebenso `PLR0912`, `PLR0915`), Exit 1.
Dann **beides zurücknehmen** und mit `git diff --stat custom_components/` prüfen, dass `analyze.py` unverändert ist.

- [ ] **Step 10: Den CI-Job ergänzen**

In `.github/workflows/test.yml` unter `jobs:` nach dem Job `pytest` anfügen:

```yaml
  guards:
    name: complexity and imports
    runs-on: ubuntu-latest
    steps:
      - name: Check out the repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install the pinned tools
        run: python3 -m pip install "ruff==0.16.9" "import-linter==2.15"

      - name: Complexity may only go down
        run: python3 tools/complexity_ratchet.py
```

- [ ] **Step 11: `hassfest` stört sich nicht an `pyproject.toml`**

Spec P, »Fehler- und Randfälle«: Die CI prüft `hassfest` und HACS erst nach einem Push, und gepusht wird in diesem Vorhaben nicht. Deshalb lokal, an einer Kopie außerhalb des Repositorys:

```bash
rm -rf /tmp/dh-hassfest && mkdir -p /tmp/dh-hassfest
cp -r custom_components pyproject.toml /tmp/dh-hassfest/
docker run --rm -v /tmp/dh-hassfest:/github/workspace ghcr.io/home-assistant/hassfest
```

Expected: `Invalid integrations: 0`. Die HACS-Validierung lässt sich lokal nicht sinnvoll nachstellen; HACS kopiert laut eigener Dokumentation nur `custom_components/<domain>/`, und `hacs/integration` selbst hat eine `pyproject.toml` an der Wurzel (Gemini, Spec-Review zweite Fassung). Sie läuft beim ersten Push in `validate.yml`.

**Wenn `hassfest` hier oder HACS nach dem Push anschlägt**, zieht die Konfiguration in zwei eigene Dateien um und `pyproject.toml` entfällt: `ruff.toml` mit demselben Inhalt wie der `ruff`-Teil, nur ohne das Präfix `tool.ruff.` in den Tabellennamen (`[lint]`, `[lint.mccabe]`, `[lint.pylint]`), und `.importlinter` im INI-Format mit dem Inhalt aus Aufgabe 2, Schritt 1a. Die Befehle bleiben dieselben; beide Werkzeuge finden die Dateien von selbst.

- [ ] **Step 12: Gesamte Suite**

Run: `python3 -m pytest tests/ -q`
Expected: `0 failed` (die Zahl der bestandenen Tests schwankt mit den echten Dashboards; nur `0 failed` zählt).

- [ ] **Step 13: Commit**

```bash
git add pyproject.toml tools/complexity_ratchet.py tools/complexity-baseline.json tests/test_complexity_ratchet.py .github/workflows/test.yml
git commit -F - <<'EOF'
Add a complexity ratchet

plan_undo reached a cyclomatic complexity of 54 because nothing ever
said no. ruff now measures complexity, branches and statements per
function; the fifteen functions over the limit today sit in a baseline
that may only go down. noqa is ignored, so an exception is always a
visible change to the baseline, never a comment in the code - and none
of the older modules had to be touched for it.

Refs #41

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

**Akzeptanz:** 6 neue Tests grün, Sperrklinke grün mit 23 Werten, Gegenprobe rot, `hassfest` ohne Befund, CI-Job vorhanden, `git diff HEAD~1 --stat` zeigt keine Datei unter `custom_components/`.

---

### Aufgabe 2: Die Importverträge

**Files:**
- Modify: `pyproject.toml`
- Modify: `.github/workflows/test.yml`
- Modify: `CLAUDE.md` (Abschnitte »Hard rules« und »Tests«)
- Modify: `docs/development.md`

**Interfaces:**
- Consumes: `pyproject.toml` aus Aufgabe 1; CI-Job `guards` aus Aufgabe 1.
- Produces: `lint-imports` (Exit 0 = grün) mit den Verträgen »The core modules stay free of Home Assistant« und »analyze is layered«. Der Schichtenvertrag nennt alle fünf Module als optional; sie entstehen in den Aufgaben 4–8.

- [ ] **Step 1: Die Verträge in `pyproject.toml` anhängen**

```toml
[tool.importlinter]
root_package = "custom_components.dashboard_history"
include_external_packages = true

[[tool.importlinter.contracts]]
# The hard rule in CLAUDE.md, made checkable. Transitive imports count:
# a core module importing const.py would import Home Assistant through it.
name = "The core modules stay free of Home Assistant"
type = "forbidden"
source_modules = [
    "custom_components.dashboard_history.yaml_io",
    "custom_components.dashboard_history.analyze",
    "custom_components.dashboard_history.restore",
    "custom_components.dashboard_history.versions",
    "custom_components.dashboard_history.store",
    "custom_components.dashboard_history.report",
    "custom_components.dashboard_history.keys",
]
forbidden_modules = ["homeassistant"]

[[tool.importlinter.contracts]]
# Spec P, section 2: each module imports only from the layers below it;
# explain and undo share a layer and do not import each other. The
# parentheses make a layer optional, so the contract holds while the
# package is being built one module at a time.
name = "analyze is layered"
type = "layers"
containers = ["custom_components.dashboard_history.analyze"]
layers = [
    "(explain) | (undo)",
    "(removed)",
    "(matching)",
    "(model)",
]
```

- [ ] **Step 1a: Die Fallback-Fassung bereithalten (nur für den Fall aus Aufgabe 1, Schritt 11)**

Nicht anlegen, solange `pyproject.toml` funktioniert. Falls doch nötig, lautet `.importlinter` (am 2026-09-27 in dieser Form erprobt):

```ini
[importlinter]
root_package = custom_components.dashboard_history
include_external_packages = True

[importlinter:contract:ha-free]
name = The core modules stay free of Home Assistant
type = forbidden
source_modules =
    custom_components.dashboard_history.yaml_io
    custom_components.dashboard_history.analyze
    custom_components.dashboard_history.restore
    custom_components.dashboard_history.versions
    custom_components.dashboard_history.store
    custom_components.dashboard_history.report
    custom_components.dashboard_history.keys
forbidden_modules =
    homeassistant

[importlinter:contract:layers]
name = analyze is layered
type = layers
containers =
    custom_components.dashboard_history.analyze
layers =
    (explain) | (undo)
    (removed)
    (matching)
    (model)
```

- [ ] **Step 2: Verträge prüfen**

Run: `lint-imports`
Expected: `The core modules stay free of Home Assistant KEPT`, `analyze is layered KEPT`, `Contracts: 2 kept, 0 broken.`

- [ ] **Step 3: Die Gegenprobe**

In `custom_components/dashboard_history/keys.py` vorübergehend als letzte Zeile `import homeassistant` anhängen.
Run: `lint-imports`
Expected: `The core modules stay free of Home Assistant BROKEN` mit `custom_components.dashboard_history.keys -> homeassistant`.
Dann die Zeile entfernen; `git diff --stat custom_components/` muss leer sein.

- [ ] **Step 4: CI-Job erweitern**

In `.github/workflows/test.yml`, Job `guards`, als letzten Schritt anfügen:

```yaml
      - name: Import contracts
        run: lint-imports
```

- [ ] **Step 5: `CLAUDE.md` nachziehen**

Im Abschnitt »Hard rules« den Punkt zu den HA-freien Modulen ersetzen durch:

```markdown
- **`yaml_io.py`, `analyze.py`, `restore.py`, `versions.py`, `store.py`, `report.py`, and `keys.py` stay free of Home Assistant.** No `import homeassistant` in them, not even through another module — they are the core and have to stay testable in plain pytest. `lint-imports` checks this (contract in `pyproject.toml`).
```

Im Abschnitt »Tests« nach dem pytest-Block anfügen:

```markdown
Two guards run in CI next to pytest, and locally with the pinned versions (`python3 -m pip install "ruff==0.16.9" "import-linter==2.15"`, best in a virtualenv outside the repository):

```bash
python3 tools/complexity_ratchet.py   # complexity may only go down
lint-imports                          # Home Assistant stays out of the core; analyze is layered
```

The ratchet compares ruff's complexity measurements with `tools/complexity-baseline.json`. A function new to the list, or a known one that grew, fails it; so does one that shrank without the baseline being lowered. `# noqa` does not help — the exception belongs in the baseline, where a reviewer sees it.
```

- [ ] **Step 6: `docs/development.md` nachziehen**

Den Absatz aus Schritt 5, der mit »Two guards run in CI« beginnt, samt Codeblock und Folgeabsatz dort an der Stelle einfügen, an der die Datei beschreibt, wie Tests laufen. Vorher `docs/development.md` lesen und die passende Überschrift wählen; nichts sonst ändern.

- [ ] **Step 7: Gesamte Suite und beide Wachen**

Run: `python3 -m pytest tests/ -q && python3 tools/complexity_ratchet.py && lint-imports`
Expected: `0 failed`, `none grew`, `2 kept, 0 broken`.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml .github/workflows/test.yml CLAUDE.md docs/development.md
git commit -F - <<'EOF'
Check the import rules instead of trusting them

"The core stays free of Home Assistant" was a sentence in CLAUDE.md
that nothing enforced. import-linter now checks it, transitive imports
included, and holds the layers the analyze package is about to get.
The layers are optional until the modules exist.

Refs #41

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

**Akzeptanz:** beide Verträge `KEPT`, Gegenprobe `BROKEN`, CI-Job führt beide Wachen aus, keine Datei unter `custom_components/` geändert.

---

## P2 – Das Paket

### Aufgabe 3: `analyze.py` wird ein Paket

**Files:**
- Move: `custom_components/dashboard_history/analyze.py` → `custom_components/dashboard_history/analyze/__init__.py`
- Modify: `tools/complexity-baseline.json` (fünf Schlüssel)

**Interfaces:**
- Produces: Paket `analyze` mit unverändertem Inhalt in `__init__.py`; Baseline-Schlüssel `custom_components/dashboard_history/analyze/__init__.py::<funktion>`.

- [ ] **Step 1: Vergleichslauf der Prüfbank auf dem heutigen Stand**

Bevor irgendetwas umzieht: `docker compose -f docker/compose.yaml up -d`, dann `python3 tests/integration/run_checks.py`, und die Liste der roten Prüfungen notieren. `run_checks.py` erodiert seine eigene Prüfbank; eine Prüfung, die schon hier rot ist, wird später nicht dem Umbau angelastet.

- [ ] **Step 2: Verschieben**

```bash
mkdir custom_components/dashboard_history/analyze
git mv custom_components/dashboard_history/analyze.py custom_components/dashboard_history/analyze/__init__.py
```

- [ ] **Step 3: Baseline-Schlüssel umbenennen**

In `tools/complexity-baseline.json` in den fünf Schlüsseln `…/analyze.py::` durch `…/analyze/__init__.py::` ersetzen (`_match_slots`, `_pair_view_sections`, `_plan_sections`, `plan_undo`, `_explain`). Werte unverändert.

- [ ] **Step 4: Suite und Wachen**

Run: `python3 -m pytest tests/ -q && python3 tools/complexity_ratchet.py && lint-imports`
Expected: `0 failed`, `none grew`, `2 kept, 0 broken`.

- [ ] **Step 5: Im Container gegen einen echten Home Assistant**

```bash
docker restart dashboard-history-test
python3 tests/integration/run_checks.py
```

Expected: dieselben Prüfungen rot wie in Schritt 1, keine weitere. (`run_checks.py` wartet selbst auf die API; nicht selbst pollen.)

- [ ] **Step 6: Eine liegengebliebene `analyze.py` gewinnt nicht**

```bash
docker exec dashboard-history-test sh -c 'd=$(mktemp -d); mkdir $d/m; echo "WHO=\"file\"" > $d/m.py; echo "WHO=\"package\"" > $d/m/__init__.py; cd $d && python3 -c "import m; print(m.WHO)"; rm -rf $d'
```

Expected: `package`.

- [ ] **Step 7: Commit**

```bash
git add tools/complexity-baseline.json
git commit -F - <<'EOF'
Turn analyze.py into a package

A plain move, content unchanged, so git follows the file's history and
the modules carved out next start from one known state.

Refs #41

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

**Akzeptanz:** `git show --stat HEAD` zeigt eine Umbenennung mit 100 % Ähnlichkeit plus die Baseline; Suite, Wachen und `run_checks.py` wie vorher.

---

### Aufgabe 4: `model.py` herauslösen

**Files:**
- Create (außerhalb des Repositorys, wird nicht committet): `/tmp/split_analyze.py`
- Create: `custom_components/dashboard_history/analyze/model.py`
- Modify: `custom_components/dashboard_history/analyze/__init__.py`

**Interfaces:**
- Produces: `/tmp/split_analyze.py <paketverzeichnis> <modul> <docstring> <name> …` – benutzt von den Aufgaben 5–8. Nach jedem Lauf importiert `__init__.py` alle verschobenen Namen zurück.

- [ ] **Step 1: Das Umzugsskript anlegen**

`/tmp/split_analyze.py` (erprobt am 2026-09-27, alle fünf Läufe an einer Kopie grün):

```python
"""Move top-level definitions out of analyze/__init__.py into a new module.

One-off helper for plan P2. Usage:

    python3 split_analyze.py <path/to/analyze> <module> <docstring> <name> [<name> ...]

Each definition travels with everything between the previous top-level
statement and itself, so the comment block above a function moves with
it. The new module gets `from __future__ import annotations`, the
standard-library imports its code uses, and relative imports for every
name it uses from a sibling module that already exists. A name still
defined in __init__.py is a layer violation and aborts the move.
__init__.py imports every moved name back, so the code left there and
the tests keep finding them.
"""

from __future__ import annotations

import ast
import pathlib
import sys


def _names_defined(node: ast.stmt) -> list[str]:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return [node.name]
    if isinstance(node, ast.Assign):
        return [t.id for t in node.targets if isinstance(t, ast.Name)]
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return [node.target.id]
    return []


def _names_used(nodes: list[ast.stmt]) -> set[str]:
    used: set[str] = set()
    for node in nodes:
        for child in ast.walk(node):
            if isinstance(child, ast.Name):
                used.add(child.id)
    return used


def _sibling_names(package: pathlib.Path) -> dict[str, str]:
    owner: dict[str, str] = {}
    for path in sorted(package.glob("*.py")):
        if path.name == "__init__.py":
            continue
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            for name in _names_defined(node):
                owner[name] = path.stem
    return owner


def main(package: pathlib.Path, module: str, docstring: str, wanted: list[str]) -> None:
    init = package / "__init__.py"
    source = init.read_text(encoding="utf-8")
    lines = source.splitlines(keepends=True)
    tree = ast.parse(source)
    body = tree.body

    header_end = 0  # index of the first statement after docstring and imports
    for index, node in enumerate(body):
        is_docstring = index == 0 and isinstance(node, ast.Expr)
        if is_docstring or isinstance(node, (ast.Import, ast.ImportFrom)):
            header_end = index + 1
        else:
            break
    imports = [n for n in body[:header_end] if isinstance(n, (ast.Import, ast.ImportFrom))]
    # Two things this helper does not handle, neither of which analyze.py
    # has - refuse rather than write a module that fails on import
    # (Gemini, plan review).
    if any(alias.asname for node in imports for alias in node.names):
        sys.exit("an import with 'as' in the header; not supported")
    for node in body[header_end:]:
        if isinstance(node, ast.Assign) and not all(isinstance(t, ast.Name) for t in node.targets):
            sys.exit(f"line {node.lineno}: unpacking at the top level; not supported")

    segments: list[tuple[int, int, ast.stmt]] = []  # (first line, last line, node), 1-based
    found: set[str] = set()
    for index in range(header_end, len(body)):
        node = body[index]
        names = _names_defined(node)
        if not set(names) & set(wanted):
            continue
        if not set(names) <= set(wanted):
            sys.exit(f"{names} is one statement; move all of it or none")
        first = body[index - 1].end_lineno + 1
        segments.append((first, node.end_lineno, node))
        found |= set(names)
    missing = set(wanted) - found
    if missing:
        sys.exit(f"not defined at the top of __init__.py: {sorted(missing)}")

    moved_nodes = [node for _, _, node in segments]
    used = _names_used(moved_nodes) - found
    staying = {
        name for node in body[header_end:] if node not in moved_nodes for name in _names_defined(node)
    }
    upward = sorted(used & staying)
    if upward:
        sys.exit(f"{module} would need names still in __init__.py: {upward}")

    stdlib: list[str] = []
    for node in imports:
        if isinstance(node, ast.ImportFrom) and node.level:
            continue  # a relative import of a sibling, handled below
        if isinstance(node, ast.Import):
            kept = [a for a in node.names if (a.asname or a.name) in used]
            if kept:
                stdlib.append("import " + ", ".join(a.name for a in kept) + "\n")
        elif node.module == "__future__":
            continue
        else:
            kept = [a for a in node.names if (a.asname or a.name) in used]
            if kept:
                stdlib.append(f"from {node.module} import " + ", ".join(a.name for a in kept) + "\n")

    owner = _sibling_names(package)
    relative: dict[str, list[str]] = {}
    for name in sorted(used):
        if name in owner:
            relative.setdefault(owner[name], []).append(name)

    parts = [f'"""{docstring}"""\n\nfrom __future__ import annotations\n\n']
    if stdlib:
        parts.append("".join(stdlib) + "\n")
    for sibling, names in sorted(relative.items()):
        parts.append(f"from .{sibling} import (\n" + "".join(f"    {n},\n" for n in names) + ")\n")
    if relative:
        parts.append("\n")
    chunks = ["".join(lines[first - 1 : last]).strip("\n") + "\n" for first, last, _ in segments]
    parts.append("\n" + "\n\n\n".join(chunks))
    target = package / f"{module}.py"
    if target.exists():
        sys.exit(f"{target} exists already")
    target.write_text("".join(parts), encoding="utf-8")

    drop = set()
    for first, last, _ in segments:
        drop |= set(range(first, last + 1))
    kept_lines = [line for number, line in enumerate(lines, start=1) if number not in drop]
    back = f"from .{module} import (\n" + "".join(f"    {n},\n" for n in sorted(found)) + ")\n"
    insert_at = body[header_end - 1].end_lineno  # after the last header statement
    rebuilt = "".join(kept_lines[:insert_at]) + back + "".join(kept_lines[insert_at:])
    init.write_text(rebuilt, encoding="utf-8")
    print(f"moved {len(found)} names into {target.name}")


if __name__ == "__main__":
    main(pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4:])
```

- [ ] **Step 2: `model.py` herauslösen**

```bash
python3 /tmp/split_analyze.py custom_components/dashboard_history/analyze model \
  "Types, and how a dashboard is read and named." \
  _SectionAnchor RemovedItem Summary Entry ViewChanges Explanation Slot SectionMatching Matching \
  UndoStep UndoPlan SectionSlot SectionPair SettingChange _ABSENT _place _translated \
  card_containers badge_containers _views_by_key _by_position _own _section_list fingerprint \
  same_config _view_name _LABEL_LIMIT _shorten _first_line _first_entity _inner_card _weak_key \
  _describe _section_title
```

Expected: `moved 34 names into model.py`. Bricht es mit »would need names still in __init__.py« ab, ist die Zuordnung der Spec verletzt – anhalten und melden, nicht die Liste ändern.

- [ ] **Step 3: Suite und Wachen**

Run: `python3 -m pytest tests/ -q && python3 tools/complexity_ratchet.py && lint-imports`
Expected: `0 failed`, `none grew` (keine Funktion aus der Baseline ist umgezogen), `2 kept, 0 broken`.

- [ ] **Step 4: Sichtprüfung**

`model.py` öffnen: Kopf mit Docstring, `from __future__ import annotations`, danach nur Standardbibliothek-Importe, dann die Definitionen mit ihren Kommentarblöcken. `git diff --stat` zeigt nur `__init__.py` und `model.py`.

- [ ] **Step 5: Commit**

```bash
git add custom_components/dashboard_history/analyze/model.py custom_components/dashboard_history/analyze/__init__.py
git commit -F - <<'EOF'
Move the types and readers into analyze.model

The bottom layer: every type, and how a dashboard is read and named.
_place and _translated come along because Matching.same_place calls
them, and a method resolves its names in the module of its class.

Refs #41

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

**Akzeptanz:** 34 Namen in `model.py`, Suite und Wachen grün, keine andere Datei geändert.

---

### Aufgabe 5: `matching.py` herauslösen

**Files:**
- Create: `custom_components/dashboard_history/analyze/matching.py`
- Modify: `custom_components/dashboard_history/analyze/__init__.py`, `tools/complexity-baseline.json`

**Interfaces:**
- Consumes: `/tmp/split_analyze.py` (Aufgabe 4), `analyze/model.py`.

- [ ] **Step 1: Herauslösen**

```bash
python3 /tmp/split_analyze.py custom_components/dashboard_history/analyze matching \
  "Pairing sections, cards, badges and settings across two states." \
  _pair_view_sections _pair_sections _moved _count_places _whole _settle_sections _positions_lie \
  _paths_collide _section_marks _same_marks _section_drift _section_anchor _view_type \
  _view_type_changed _slots _similarity _unpaired match_cards match_sections _match_slots \
  match_badges _reordered _NOT_VIEW_SETTINGS _same _setting_leaves setting_changes _setting_at
```

Expected: `moved 27 names into matching.py`.

- [ ] **Step 2: Baseline-Schlüssel umbenennen**

`…/analyze/__init__.py::_match_slots` → `…/analyze/matching.py::_match_slots` und `…/analyze/__init__.py::_pair_view_sections` → `…/analyze/matching.py::_pair_view_sections`. Werte unverändert.

- [ ] **Step 3: Suite und Wachen**

Run: `python3 -m pytest tests/ -q && python3 tools/complexity_ratchet.py && lint-imports`
Expected: `0 failed`, `none grew`, `2 kept, 0 broken`.

- [ ] **Step 4: Länge prüfen**

Run: `wc -l custom_components/dashboard_history/analyze/matching.py`
Expected: um 723, jedenfalls unter 900.

- [ ] **Step 5: Commit**

```bash
git add custom_components/dashboard_history/analyze/matching.py custom_components/dashboard_history/analyze/__init__.py tools/complexity-baseline.json
git commit -F - <<'EOF'
Move the pairing into analyze.matching

Sections, cards, badges and settings are paired in one module because
match_cards needs the section pairing first - apart, the two would
import each other.

Refs #41

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

**Akzeptanz:** 27 Namen in `matching.py`, zwei Baseline-Schlüssel umbenannt, Suite und Wachen grün.

---

### Aufgabe 6: `removed.py` herauslösen

**Files:**
- Create: `custom_components/dashboard_history/analyze/removed.py`
- Modify: `custom_components/dashboard_history/analyze/__init__.py`

- [ ] **Step 1: Herauslösen**

```bash
python3 /tmp/split_analyze.py custom_components/dashboard_history/analyze removed \
  "What a change removed, for Put back." find_removed
```

Expected: `moved 1 names into removed.py`.

- [ ] **Step 2: Suite und Wachen**

Run: `python3 -m pytest tests/ -q && python3 tools/complexity_ratchet.py && lint-imports`
Expected: `0 failed`, `none grew`, `2 kept, 0 broken`.

- [ ] **Step 3: Commit**

```bash
git add custom_components/dashboard_history/analyze/removed.py custom_components/dashboard_history/analyze/__init__.py
git commit -F - <<'EOF'
Move find_removed into analyze.removed

Put back reads the pairing but nothing else in the package reads Put
back, so it gets a layer of its own between matching and the two
modules that turn changes into words and into undo steps.

Refs #41

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

**Akzeptanz:** `removed.py` mit `find_removed`, Suite und Wachen grün.

---

### Aufgabe 7: `explain.py` herauslösen

**Files:**
- Create: `custom_components/dashboard_history/analyze/explain.py`
- Modify: `custom_components/dashboard_history/analyze/__init__.py`, `tools/complexity-baseline.json`

- [ ] **Step 1: Herauslösen**

```bash
python3 /tmp/split_analyze.py custom_components/dashboard_history/analyze explain \
  "The words for a change: history line, explanation, counts." \
  summarize _PAST _FUTURE _ENTRY_LIMIT _NOTHING_LOST _NOT_IN_CARDS _entry _value_text \
  _setting_entry _section_setting_changes _capped _section_name _where _explain explain_change \
  explain_effect _meta_detail _views _sections_part change_message _COUNT _counts message_adds
```

Expected: `moved 23 names into explain.py`.

- [ ] **Step 2: Baseline-Schlüssel umbenennen**

`…/analyze/__init__.py::_explain` → `…/analyze/explain.py::_explain`.

- [ ] **Step 3: Suite und Wachen**

Run: `python3 -m pytest tests/ -q && python3 tools/complexity_ratchet.py && lint-imports`
Expected: `0 failed`, `none grew`, `2 kept, 0 broken`.

- [ ] **Step 4: Commit**

```bash
git add custom_components/dashboard_history/analyze/explain.py custom_components/dashboard_history/analyze/__init__.py tools/complexity-baseline.json
git commit -F - <<'EOF'
Move the words for a change into analyze.explain

History line, explanation and counts read the pairing and never the
undo planning, so they share the top layer with undo without either
importing the other.

Refs #41

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

**Akzeptanz:** 23 Namen in `explain.py`, Baseline-Schlüssel umbenannt, Suite und Wachen grün.

---

### Aufgabe 8: `undo.py` herauslösen

**Files:**
- Create: `custom_components/dashboard_history/analyze/undo.py`
- Modify: `custom_components/dashboard_history/analyze/__init__.py`, `tools/complexity-baseline.json`

- [ ] **Step 1: Herauslösen**

```bash
python3 /tmp/split_analyze.py custom_components/dashboard_history/analyze undo \
  "Planning the targeted undo of one change (decision 15)." \
  _POSITION_REFUSAL _SECTIONS_AND_CARDS_REFUSAL _VIEW_TYPE_REFUSAL _DUPLICATE_PATH_REFUSAL \
  _present _group_by_mark _in_view _step _plan_sections plan_undo
```

Expected: `moved 10 names into undo.py`.

- [ ] **Step 2: Nichts mehr definiert in `__init__.py`**

Run: `python3 -c "import ast; t=ast.parse(open('custom_components/dashboard_history/analyze/__init__.py').read()); print([type(n).__name__ for n in t.body if not isinstance(n,(ast.Import,ast.ImportFrom,ast.Expr))])"`
Expected: `[]`.

- [ ] **Step 3: Baseline-Schlüssel umbenennen**

`…/analyze/__init__.py::_plan_sections` → `…/analyze/undo.py::_plan_sections` und `…/analyze/__init__.py::plan_undo` → `…/analyze/undo.py::plan_undo`.

- [ ] **Step 4: Suite und Wachen**

Run: `python3 -m pytest tests/ -q && python3 tools/complexity_ratchet.py && lint-imports`
Expected: `0 failed`, `none grew`, `2 kept, 0 broken`.

- [ ] **Step 5: Commit**

```bash
git add custom_components/dashboard_history/analyze/undo.py custom_components/dashboard_history/analyze/__init__.py tools/complexity-baseline.json
git commit -F - <<'EOF'
Move the undo planning into analyze.undo

plan_undo moves as it is. It is taken apart in its own module next,
where the comparison with this exact state can prove it still answers
the same.

Refs #41

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

**Akzeptanz:** `__init__.py` definiert nichts mehr, Baseline-Schlüssel umbenannt, Suite und Wachen grün.

---

### Aufgabe 9: `__init__.py` wird die erklärte Schnittstelle

**Files:**
- Create: `tests/test_analyze_interface.py`
- Modify (neu schreiben): `custom_components/dashboard_history/analyze/__init__.py`

**Interfaces:**
- Produces: `analyze.__all__` mit genau 26 Namen. Aufgabe 10 braucht den Commit dieser Aufgabe als Basis-Commit.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`tests/test_analyze_interface.py`:

```python
"""The names reachable as `analyze.<name>` are a decision, not an accident.

Spec P, section 2: the package exports what code and tests use today,
and nothing else. Every other name keeps its name in its own module
(analyze.model.fingerprint). A name is added here when a caller needs it.
"""

import analyze

INTERFACE = {
    # used by operations.py, capture.py and restore.py
    "RemovedItem", "UndoPlan", "UndoStep", "change_message", "explain_change",
    "explain_effect", "find_removed", "message_adds", "plan_undo", "same_config",
    # used by the tests
    "card_containers", "match_badges", "match_cards", "match_sections",
    "setting_changes", "summarize",
    "_ABSENT", "_ENTRY_LIMIT", "_POSITION_REFUSAL", "_SECTIONS_AND_CARDS_REFUSAL",
    "_counts", "_describe", "_moved", "_pair_sections", "_plan_sections", "_views_by_key",
}


def test_the_package_exports_exactly_its_interface():
    assert set(analyze.__all__) == INTERFACE


def test_every_exported_name_resolves():
    for name in INTERFACE:
        assert getattr(analyze, name) is not None, name
```

- [ ] **Step 2: Test laufen lassen, er muss fehlschlagen**

Run: `python3 -m pytest tests/test_analyze_interface.py -v`
Expected: `1 failed, 1 passed` – `test_the_package_exports_exactly_its_interface` scheitert mit `AttributeError: module 'analyze' has no attribute '__all__'`; `test_every_exported_name_resolves` ist schon grün, weil `__init__.py` nach Aufgabe 8 alle Namen zurückimportiert.

- [ ] **Step 3: `__init__.py` neu schreiben**

Den bisherigen Modul-Docstring behalten und um einen Absatz ergänzen; alles andere ersetzen:

```python
"""Classifying what changed between two dashboard configurations.

Lovelace cards carry no identifier — a card is defined by its position in
a list. Matching them between two states therefore has to work from their
content, and that shapes everything here.

The order matters: an exact content match wins first (that card is
unchanged, possibly moved), then a weak match on type plus the most
identifying field (that card was edited). Only what is left over counts
as removed. Without that ordering an edited card would look like a
deletion plus an addition, and the interface would offer to restore
something that is still there.

The package has five modules in layers, each importing only from those
below it (checked by `lint-imports`): `model` (types, reading and naming
a dashboard), `matching` (pairing two states), `removed` (Put back),
and on top `explain` (the words) and `undo` (the targeted undo). This
file holds no logic; it names what callers reach as `analyze.<name>`.
"""

from __future__ import annotations

from .explain import (
    _ENTRY_LIMIT,
    _counts,
    change_message,
    explain_change,
    explain_effect,
    message_adds,
    summarize,
)
from .matching import (
    _moved,
    _pair_sections,
    match_badges,
    match_cards,
    match_sections,
    setting_changes,
)
from .model import (
    _ABSENT,
    RemovedItem,
    UndoPlan,
    UndoStep,
    _describe,
    _views_by_key,
    card_containers,
    same_config,
)
from .removed import find_removed
from .undo import _POSITION_REFUSAL, _SECTIONS_AND_CARDS_REFUSAL, _plan_sections, plan_undo

__all__ = [
    "RemovedItem",
    "UndoPlan",
    "UndoStep",
    "_ABSENT",
    "_ENTRY_LIMIT",
    "_POSITION_REFUSAL",
    "_SECTIONS_AND_CARDS_REFUSAL",
    "_counts",
    "_describe",
    "_moved",
    "_pair_sections",
    "_plan_sections",
    "_views_by_key",
    "card_containers",
    "change_message",
    "explain_change",
    "explain_effect",
    "find_removed",
    "match_badges",
    "match_cards",
    "match_sections",
    "message_adds",
    "plan_undo",
    "same_config",
    "setting_changes",
    "summarize",
]
```

- [ ] **Step 4: Suite und Wachen**

Run: `python3 -m pytest tests/ -q && python3 tools/complexity_ratchet.py && lint-imports`
Expected: `0 failed` (mit den 2 neuen Tests), `none grew`, `2 kept, 0 broken`. Schlägt ein bestehender Test mit `AttributeError` fehl, fehlt ein Name in der Schnittstelle – das ist ein Befund, anhalten und melden, nicht den Test ändern.

- [ ] **Step 5: Längen**

Run: `wc -l custom_components/dashboard_history/analyze/*.py`
Expected: keine Datei über 900.

- [ ] **Step 6: Im Container**

```bash
docker restart dashboard-history-test
python3 tests/integration/run_checks.py
```

Expected: dieselben roten Prüfungen wie in Aufgabe 3, Schritt 1, keine weitere.

- [ ] **Step 7: Commit**

```bash
git add tests/test_analyze_interface.py custom_components/dashboard_history/analyze/__init__.py
git commit -F - <<'EOF'
Name the interface of the analyze package

__init__.py now holds no logic, only the 26 names that operations,
capture, restore and the tests reach through analyze. A test pins the
list, since attribute access alone would never notice a name missing
from __all__.

Refs #41

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

Den Hash dieses Commits notieren (`git rev-parse HEAD`): Er ist der Basis-Commit für Aufgabe 10. `/tmp/split_analyze.py` wird nicht mehr gebraucht und kann gelöscht werden.

**Akzeptanz:** Schnittstellentest grün, `__init__.py` ohne Logik, alle Module unter 900 Zeilen, `run_checks.py` wie vorher.

---

## P3 – Die Planer

### Aufgabe 10: Das Vergleichswerkzeug

**Files:**
- Create: `tests/equivalence/compare_undo.py`

**Interfaces:**
- Consumes: den Commit aus Aufgabe 9 (`BASE_COMMIT`).
- Produces: `python3 tests/equivalence/compare_undo.py` – Exit 0 bei 0 Abweichungen; eine Zusammenfassung ohne Dashboard-Inhalte auf stdout. Sobald `analyze.undo` die Namen `UndoContext`, `_GATES`, `_PLANNERS`, `_CHECK_ORDER`, `_sections_meet_cards` hat (Aufgabe 11), misst es zusätzlich die Vorrang-Paare.

- [ ] **Step 1: Das Werkzeug anlegen**

`tests/equivalence/compare_undo.py`; in `BASE_COMMIT` den Hash aus Aufgabe 9 eintragen:

```python
"""Compare plan_undo as it was after P2 with the working tree (spec P, section 4).

A temporary tool for the duration of P3; the last commit of P removes
it. It loads the analyze package from BASE_COMMIT with dulwich (no git
binary, per the hard rule), under the name analyze_before_p3, next to
the package in the working tree, and feeds both the same inputs: cases
built on purpose, generated histories, and - if one is configured the
way conftest.py finds it - the real dashboards of a .storage directory.
It compares plan_undo and the effect of restore.apply_undo in a strict
canonical form, measures plan_undo's time, and prints a summary that
contains numbers and refusal templates only, never a dashboard.

Run from the repository root: python3 tests/equivalence/compare_undo.py
"""

from __future__ import annotations

import copy
import dataclasses
import importlib
import itertools
import json
import os
import pathlib
import random
import re
import sys
import tempfile
import time
import traceback

from dulwich.object_store import tree_lookup_path
from dulwich.repo import Repo

BASE_COMMIT = "<hash from task 9>"
SEEDS = (1, 2, 3, 4, 5)
TRIPLES_PER_SEED = 2000

ROOT = pathlib.Path(__file__).resolve().parents[2]
PACKAGE_DIR = ROOT / "custom_components" / "dashboard_history"


def _load_old():
    """The analyze package of BASE_COMMIT, importable as analyze_before_p3."""
    target = pathlib.Path(tempfile.mkdtemp()) / "analyze_before_p3"
    target.mkdir()
    with Repo(str(ROOT)) as repo:
        commit = repo[BASE_COMMIT.encode()]
        _mode, sha = tree_lookup_path(
            repo.__getitem__, commit.tree, b"custom_components/dashboard_history/analyze"
        )
        for entry in repo[sha].items():
            name = entry.path.decode()
            if name.endswith(".py"):
                (target / name).write_bytes(repo[entry.sha].data)
        # Both versions run through the working tree's restore.py. That is
        # only fair while it is the restore.py of BASE_COMMIT - P changes
        # nothing there, and this holds it to that (Gemini, plan review).
        _mode, restore_sha = tree_lookup_path(
            repo.__getitem__, commit.tree, b"custom_components/dashboard_history/restore.py"
        )
        if repo[restore_sha].data != (PACKAGE_DIR / "restore.py").read_bytes():
            sys.exit("restore.py differs from BASE_COMMIT; P must not change it")
    sys.path.insert(0, str(target.parent))
    return importlib.import_module("analyze_before_p3")


sys.path.insert(0, str(PACKAGE_DIR))
OLD = _load_old()
import analyze as NEW  # noqa: E402
import restore  # noqa: E402
from analyze import undo as NEW_UNDO  # noqa: E402

# Every refusal plan_undo can give, as it reads in the source; `{…}` is
# whatever gets filled in. Each refusal must match exactly one of them.
TEMPLATES = (
    'the sections of the view "{…}" changed in a way this undo cannot account for, so it refuses rather than guess',
    'the view "{…}" is no longer on the dashboard, so its sections cannot be taken back',
    'the sections of the view "{…}" are not a plain list in every state, so an exact undo cannot write them back',
    'the other sections of the view "{…}" were rearranged since, so there is no telling where these go back',
    'more than one section of the view "{…}" was changed since, so which is which can no longer be proven',
    "the {…} was changed again after this, so there is no exact version left to take back",
    "{…} sections now look exactly like {…}, so an exact undo cannot tell them apart",
    "this change did not alter any cards",
    "__DUPLICATE_PATH__",
    "__POSITION__",
    "__VIEW_TYPE__",
    'the view "{…}" is no longer on the dashboard, so its setting "{…}" cannot be taken back',
    'the setting "{…}" no longer has the "{…}" block it belonged to',
    'the setting "{…}" was changed again after this',
    "{…} was changed again after this, so there is no exact version left to put back",
    "{…} cards now look exactly like {…}, so an exact undo cannot tell them apart",
    "only some of the copies of {…} this change deleted are back, so an exact undo cannot tell which are missing",
    "{…} badges now look exactly like {…}, so an exact undo cannot tell them apart",
    '{…} views now look exactly like "{…}", so an exact undo cannot tell them apart',
    'the view "{…}" was changed again after this',
    'the view "{…}" is no longer on the dashboard as this change left it, so an exact undo cannot take it away',
    'a different view now sits at "{…}", so the view "{…}" cannot be put back there',
    "__SECTIONS_AND_CARDS__",
)
_FIXED = {
    "__DUPLICATE_PATH__": OLD.undo._DUPLICATE_PATH_REFUSAL,
    "__POSITION__": OLD._POSITION_REFUSAL,
    "__VIEW_TYPE__": OLD.undo._VIEW_TYPE_REFUSAL,
    "__SECTIONS_AND_CARDS__": OLD._SECTIONS_AND_CARDS_REFUSAL,
}


def _pattern(template: str) -> re.Pattern:
    if template in _FIXED:
        return re.compile(re.escape(_FIXED[template]))
    return re.compile(".+?".join(re.escape(part) for part in template.split("{…}")), re.S)


PATTERNS = [(t, _pattern(t)) for t in TEMPLATES]


def template_of(text: str) -> str:
    hits = [t for t, p in PATTERNS if p.fullmatch(text)]
    if len(hits) != 1:
        raise AssertionError(f"a refusal matches {len(hits)} templates: {hits}")
    return hits[0]


# -- canonical form -------------------------------------------------------


def canon(value):
    """A form in which True is not 1 and the old and new classes compare."""
    if value is OLD._ABSENT or value is NEW._ABSENT:
        return ("<absent>",)
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, (int, float, str)) or value is None:
        return (type(value).__name__, value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        fields = {f.name: canon(getattr(value, f.name)) for f in dataclasses.fields(value)}
        if type(value).__name__ == "UndoPlan":
            fields["parked"] = canon(value.parked)
        return (type(value).__name__, fields)
    if isinstance(value, dict):
        return ("dict", tuple((canon(k), canon(v)) for k, v in value.items()))
    if isinstance(value, (list, tuple)):
        return (type(value).__name__, tuple(canon(v) for v in value))
    raise TypeError(f"no canonical form for {type(value).__name__}")


def outcome(module, before, after, current):
    """What plan_undo answers, what applying it does, and how long planning took."""
    start = time.perf_counter()
    try:
        plan = module.plan_undo(before, after, current)
    except Exception as exc:  # compared, not hidden
        return ("raised", *_where_raised(exc)), None, time.perf_counter() - start
    took = time.perf_counter() - start
    try:
        effect = ("applied", canon(restore.apply_undo(current, plan)))
    except Exception as exc:  # LookupError is the expected one; any other is compared too
        effect = ("apply raised", *_where_raised(exc))
    return (canon(plan), effect), plan, took


def _where_raised(exc: Exception) -> tuple:
    """Type, text, and the function and source line that raised.

    The innermost frame sits in code both versions share unchanged (the
    helpers moved in P2, restore.py), so the same failure names the same
    function and line in both - and a different one does not (Gemini,
    plan review).
    """
    frame = traceback.extract_tb(exc.__traceback__)[-1]
    return type(exc).__name__, str(exc), frame.name, (frame.line or "").strip()


# -- inputs ---------------------------------------------------------------


def _card(kind, **extra):
    return {"type": kind, **extra}


BASES = [
    {
        "title": "Home",
        "views": [
            {
                "path": "home",
                "title": "Home",
                "icon": "mdi:home",
                "cards": [
                    _card("entities", entities=["light.a", "light.b"]),
                    _card("button", entity="switch.c"),
                    _card("markdown", content="Hello"),
                    _card("entities", entities=["light.a", "light.b"]),
                ],
                "badges": [
                    {"type": "entity", "entity": "sensor.t"},
                    {"type": "entity", "entity": "sensor.h"},
                ],
            },
            {"title": "Zwei", "cards": [_card("tile", entity="light.d")]},
        ],
    },
    {
        "views": [
            {
                "path": "sec",
                "type": "sections",
                "max_columns": 3,
                "sections": [
                    {"type": "grid", "cards": [_card("heading", heading="One"), _card("tile", entity="light.a"), _card("tile", entity="light.b")]},
                    {"type": "grid", "column_span": 2, "cards": [_card("heading", heading="Two"), _card("tile", entity="light.c")]},
                    {"type": "grid", "cards": [_card("tile", entity="light.a")]},
                ],
                "badges": [{"type": "entity", "entity": "sensor.t"}],
            },
            {"path": "other", "cards": [_card("markdown", content="x")], "badges": [{"type": "entity", "entity": "sensor.t"}]},
        ],
    },
    {"strategy": {"type": "original-states", "hide_energy": True}},
    # A stray non-dict entry in views - a known open finding (status.md),
    # kept here so its current answer is pinned, right or wrong.
    {"views": ["junk", {"cards": [_card("tile", entity="light.a")]}, {"path": "p", "cards": [_card("tile", entity="light.b")]}]},
    {
        "views": [
            {"cards": [_card("tile", entity="light.a")]},
            {"cards": [_card("tile", entity="light.a"), _card("tile", entity="light.b")]},
        ],
    },
]


def _real_storage() -> str:
    configured = os.environ.get("DASHBOARD_HISTORY_REAL_STORAGE", "")
    local = ROOT / "tests" / ".real-storage"
    if not configured and local.exists():
        for line in local.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.startswith("#"):
                return line.strip()
    return configured


def real_bases() -> list[dict]:
    storage = _real_storage()
    out = []
    for path in sorted(pathlib.Path(storage).glob("lovelace.*")) if storage else []:
        try:
            config = json.loads(path.read_text(encoding="utf-8"))["data"]["config"]
        except (KeyError, ValueError, TypeError):
            continue
        if isinstance(config, dict):
            out.append(config)
    return out


def _views(config):
    return [v for v in config.get("views", []) if isinstance(v, dict)]


def _containers(config, badges=False):
    out = []
    for view in _views(config):
        if badges:
            out.append(view.setdefault("badges", []))
            continue
        if isinstance(view.get("cards"), list):
            out.append(view["cards"])
        for section in view.get("sections", []) if isinstance(view.get("sections"), list) else []:
            if isinstance(section, dict) and isinstance(section.get("cards"), list):
                out.append(section["cards"])
    return out


def _any_item(config, rng, badges=False):
    lists = [lst for lst in _containers(config, badges) if lst]
    if not lists:
        return None, None
    lst = rng.choice(lists)
    return lst, rng.randrange(len(lst))


def m_delete(config, rng, badges=False):
    lst, i = _any_item(config, rng, badges)
    if lst is not None:
        lst.pop(i)


def m_add(config, rng, badges=False):
    lists = _containers(config, badges)
    if not lists:
        return
    lst = rng.choice(lists)
    src, i = _any_item(config, rng, badges)
    if src is not None and rng.random() < 0.4:
        item = copy.deepcopy(src[i])  # an identical copy
    elif badges:
        item = {"type": "entity", "entity": f"sensor.n{rng.randrange(99)}"}
    else:
        item = _card("markdown", content=f"n{rng.randrange(99)}")
    lst.insert(rng.randrange(len(lst) + 1), item)


def m_edit(config, rng, badges=False):
    lst, i = _any_item(config, rng, badges)
    if lst is not None and isinstance(lst[i], dict):
        lst[i] = {**lst[i], "name": f"e{rng.randrange(9)}"}


def m_move(config, rng):
    src, i = _any_item(config, rng)
    if src is None:
        return
    card = src.pop(i)
    dst = rng.choice(_containers(config))
    dst.insert(rng.randrange(len(dst) + 1), card)


def _section_views(config):
    return [v for v in _views(config) if isinstance(v.get("sections"), list) and v["sections"]]


def m_swap_sections(config, rng):
    views = [v for v in _section_views(config) if len(v["sections"]) > 1]
    if views:
        s = rng.choice(views)["sections"]
        a, b = rng.sample(range(len(s)), 2)
        s[a], s[b] = s[b], s[a]


def m_section_add_remove(config, rng):
    views = _section_views(config)
    if not views:
        return
    s = rng.choice(views)["sections"]
    if rng.random() < 0.5 and s:
        s.pop(rng.randrange(len(s)))
    else:
        s.insert(rng.randrange(len(s) + 1), {"type": "grid", "cards": [_card("heading", heading=f"S{rng.randrange(9)}")]})


def m_section_setting(config, rng):
    views = _section_views(config)
    if views:
        section = rng.choice(rng.choice(views)["sections"])
        if isinstance(section, dict):
            section["column_span"] = rng.choice([1, 2, True])


def m_view_setting(config, rng):
    views = _views(config)
    if views:
        view = rng.choice(views)
        key = rng.choice(["icon", "theme", "title", "visible"])
        if key in view and rng.random() < 0.5:
            del view[key]
        else:
            view[key] = rng.choice(["mdi:a", "dark", "T", False, 1])


def m_dashboard_setting(config, rng):
    if "strategy" in config and rng.random() < 0.5:
        config["strategy"] = {**config["strategy"], "hide_energy": rng.choice([True, 1, False])}
    elif "title" in config and rng.random() < 0.5:
        del config["title"]
    else:
        config["title"] = rng.choice(["A", "B"])


def m_view_add_remove(config, rng):
    views = config.setdefault("views", [])
    if views and rng.random() < 0.5:
        views.pop(rng.randrange(len(views)))
    else:
        dicts = _views(config)
        new = copy.deepcopy(rng.choice(dicts)) if dicts and rng.random() < 0.3 else {"path": f"v{rng.randrange(9)}", "cards": []}
        views.insert(rng.randrange(len(views) + 1), new)


def m_view_path(config, rng):
    views = _views(config)
    if len(views) > 1 and rng.random() < 0.5:
        a, b = rng.sample(views, 2)
        if b.get("path") is not None:
            a["path"] = b["path"]  # a collision
    elif views:
        rng.choice(views)["path"] = f"p{rng.randrange(9)}"


def m_convert(config, rng):
    views = [v for v in _views(config) if v.get("type") != "sections"]
    if views:
        view = rng.choice(views)
        view["type"] = "sections"
        view.setdefault("sections", []).append({"type": "grid", "cards": []})


MUTATIONS = [
    m_delete, m_add, m_edit, m_move,
    lambda c, r: m_delete(c, r, badges=True),
    lambda c, r: m_add(c, r, badges=True),
    lambda c, r: m_edit(c, r, badges=True),
    m_swap_sections, m_section_add_remove, m_section_setting,
    m_view_setting, m_dashboard_setting, m_view_add_remove, m_view_path, m_convert,
]


def mutate(config, rng, times):
    out = copy.deepcopy(config)
    for _ in range(times):
        rng.choice(MUTATIONS)(out, rng)
    return out


def generated(seed: int, bases: list[dict]):
    rng = random.Random(seed)
    for _ in range(TRIPLES_PER_SEED):
        before = copy.deepcopy(rng.choice(bases))
        after = mutate(before, rng, rng.randint(1, 3))
        current = before if rng.random() < 0.1 else mutate(after, rng, rng.choice([0, 0, 1, 2]))
        yield before, after, current


def _sections(*sections):
    return {"views": [{"path": "s", "type": "sections", "sections": list(sections)}]}


def constructed():
    """Cases built on purpose: refusals the generator does not reach, and V2 against V4."""
    heading = lambda text: {"type": "heading", "heading": text}  # noqa: E731
    tile = lambda entity: {"type": "tile", "entity": entity}  # noqa: E731
    first = {"type": "grid", "cards": [heading("A"), tile("x")]}
    second = {"type": "grid", "column_span": 2, "cards": [heading("B"), tile("y")]}
    two_paths = {"views": [{"path": "a", "type": "sections", "cards": []}, {"path": "a", "type": "sections", "cards": []}]}
    yield "V2 before V4 (Astra)", {"views": [{"path": "a", "type": "masonry", "cards": []}]}, two_paths, two_paths
    yield (
        "sections not a plain list",
        _sections(first, second),
        _sections(second, first),
        {"views": [{"path": "s", "type": "sections", "sections": {"0": first}}]},
    )
    yield "sections alike", _sections(first, second), _sections(first, second, first), _sections(first, second, first)
    yield (
        "setting block gone",
        {"strategy": {"type": "x", "a": 1}},
        {"strategy": {"type": "x", "a": 2}},
        {"title": "t"},
    )
    yield (
        "only some copies back (cards)",
        {"views": [{"path": "v", "cards": [tile("x"), tile("x"), tile("y")]}]},
        {"views": [{"path": "v", "cards": [tile("y")]}]},
        {"views": [{"path": "v", "cards": [tile("x"), tile("y")]}]},
    )
    yield (
        "only some copies back (badges)",
        {"views": [{"path": "v", "cards": [], "badges": [tile("x"), tile("x"), tile("y")]}]},
        {"views": [{"path": "v", "cards": [], "badges": [tile("y")]}]},
        {"views": [{"path": "v", "cards": [], "badges": [tile("x"), tile("y")]}]},
    )
    imported = tile("k")
    imported_edited = {**tile("k"), "name": "n"}
    swapped_before = {"type": "sections", "sections": [first, second], "cards": [imported]}
    swapped_after = {"type": "sections", "sections": [second, first], "cards": [imported_edited]}
    doubled = [{"path": "d", "cards": []}, {"path": "d", "cards": []}]
    yield (
        "V2 before Q1",
        {"views": [{**swapped_before, "path": "s"}, *doubled]},
        {"views": [{**swapped_after, "path": "s"}, *doubled]},
        {"views": [{**swapped_after, "path": "s"}, *doubled]},
    )
    yield (
        "V3 before Q1",
        {"views": [swapped_before, {"cards": [tile("m")]}]},
        {"views": [swapped_after, {"cards": [tile("m")]}]},
        {"views": [swapped_after, {"cards": [tile("q")]}]},
    )
    # A section moved and edited in one save: the sections planner refuses.
    second_edited = {**second, "cards": [heading("B"), {**tile("y"), "name": "n"}]}
    yield (
        "V3 before sections",
        {"views": [{"type": "sections", "sections": [first, second]}, {"cards": [tile("k")]}]},
        {"views": [{"type": "sections", "sections": [second_edited, first]}, {"cards": [tile("k")]}]},
        {"views": [{"type": "sections", "sections": [second_edited, first]}, {"cards": [tile("m")]}]},
    )
    # Astra, plan review: the old function computed `shifted` before the
    # settings planner and raised on a view whose sections is a number.
    yield (
        "raises where it raised before",
        {"views": [{"path": "a", "title": "Before", "cards": []}]},
        {"views": [{"path": "a", "title": "After", "cards": []}]},
        {"views": [{"path": "a", "title": "Later", "cards": [], "sections": 1}]},
    )
    yield (
        "a different view at the path",
        {"views": [{"path": "a", "title": "A", "cards": []}, {"path": "b", "cards": []}]},
        {"views": [{"path": "b", "cards": []}]},
        {"views": [{"path": "a", "title": "Other", "cards": []}, {"path": "b", "cards": []}]},
    )


# -- stages, measured one at a time (once the planners exist) ------------

STAGES = ("V1", "V2", "V3", "V4", "sections", "settings", "cards", "badges", "views", "Q1")

# Pairs that cannot both refuse for one input, in the old version as in
# the new: V1 refuses only when the change changed nothing, and then no
# other stage has anything to refuse (a type change counts as a change);
# Q1 is only reached once every planner has passed. Every other pair
# must be met - and one of these showing up means the reasoning is wrong.
UNREACHABLE = {
    frozenset(pair)
    for pair in (
        ("V1", "V4"), ("V1", "sections"), ("V1", "settings"), ("V1", "cards"),
        ("V1", "badges"), ("V1", "views"), ("V1", "Q1"),
        ("sections", "Q1"), ("settings", "Q1"), ("cards", "Q1"), ("badges", "Q1"), ("views", "Q1"),
    )
}
RATIO_LIMIT = 1.10


def refusing_stages(before, after, current) -> frozenset:
    """Which stages would refuse, each asked on its own; empty if one raises."""
    try:
        return _refusing_stages(before, after, current)
    except Exception:  # an input that raises has no stages to measure
        return frozenset()


def _refusing_stages(before, after, current) -> frozenset:
    ctx = NEW_UNDO.UndoContext(before, after, current)
    out = {name for name, gate in zip(STAGES[:4], NEW_UNDO._GATES) if gate(ctx) is not None}
    planned = {}
    for kind in NEW_UNDO._CHECK_ORDER:
        result = NEW_UNDO._PLANNERS[kind](ctx)
        if isinstance(result, str):
            out.add(kind)
        else:
            planned[kind] = result
    if len(planned) == len(NEW_UNDO._PLANNERS) and NEW_UNDO._sections_meet_cards(planned) is not None:
        out.add("Q1")
    return frozenset(out)


def main() -> int:
    bases = BASES + real_bases()
    inputs = [(f"constructed: {name}", b, a, c) for name, b, a, c in constructed()]
    for seed in SEEDS:
        inputs += [(f"seed {seed}", b, a, c) for b, a, c in generated(seed, bases)]
    measure_stages = hasattr(NEW_UNDO, "UndoContext")
    diffs, templates, pairs = 0, {}, set()
    t_old = t_new = 0.0
    for number, (label, before, after, current) in enumerate(inputs):
        # Alternating who goes first: whichever runs first on an input
        # pays for warming up, and a fixed order showed as a 15 % gap
        # between two identical copies.
        if number % 2:
            new, _new_plan, took_new = outcome(NEW, before, after, current)
            old, old_plan, took_old = outcome(OLD, before, after, current)
        else:
            old, old_plan, took_old = outcome(OLD, before, after, current)
            new, _new_plan, took_new = outcome(NEW, before, after, current)
        t_old += took_old
        t_new += took_new
        if old != new:
            diffs += 1
            if diffs <= 3:
                print(f"DIFFERENCE in {label}")
        if old_plan is not None and old_plan.blocked is not None:
            template = template_of(old_plan.blocked)
            templates[template] = templates.get(template, 0) + 1
        if measure_stages:
            refusing = refusing_stages(before, after, current)
            pairs |= {frozenset(p) for p in itertools.combinations(sorted(refusing), 2)}
    print(f"base commit: {BASE_COMMIT}")
    print(f"inputs: {len(inputs)} (constructed: {len(list(constructed()))}, bases: {len(BASES)} built in + {len(bases) - len(BASES)} real, seeds: {SEEDS})")
    print(f"differences: {diffs}")
    print(f"refusal templates reached: {len(templates)} of {len(TEMPLATES)}")
    for template in TEMPLATES:
        print(f"  {templates.get(template, 0):6d}  {template}")
    if measure_stages:
        print(f"pairs of refusing stages met: {len(pairs)}")
        for a, b in itertools.combinations(STAGES, 2):
            print(f"  {'x' if frozenset((a, b)) in pairs else '.'}  {a} + {b}")
    ratio = t_new / t_old
    print(f"plan_undo time: old {t_old:.2f}s, new {t_new:.2f}s, ratio {ratio:.2f}")
    failures = []
    if diffs:
        failures.append(f"{diffs} input(s) answered differently")
    missing = [t for t in TEMPLATES if t not in templates]
    if missing:
        failures.append(f"{len(missing)} refusal template(s) never reached")
    if measure_stages:
        expected = {frozenset(p) for p in itertools.combinations(STAGES, 2)} - UNREACHABLE
        if pairs != expected:
            failures.append(
                f"pairs met are not the expected {len(expected)}: "
                f"missing {sorted(sorted(p) for p in expected - pairs)}, "
                f"unexpected {sorted(sorted(p) for p in pairs - expected)}"
            )
    if ratio > RATIO_LIMIT:
        failures.append(f"plan_undo is {ratio:.2f} times as slow, over {RATIO_LIMIT}")
    for failure in failures:
        print(f"FAIL: {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Alt gegen alt**

Run: `python3 tests/equivalence/compare_undo.py`
Expected: Exit 0; `differences: 0`; `refusal templates reached: 23 of 23` – mit und ohne echte Dashboards (erprobt beides); keine Paarzeilen (die Planer existieren noch nicht); Laufzeitverhältnis `1.00` (erprobt zweimal: 1,00 und 1,00 – ohne die abwechselnde Reihenfolge im Werkzeug waren es 0,85 bei zwei identischen Fassungen). Meldet `template_of` einen Text mit 0 oder 2 Treffern, ist die Vorlagenliste unvollständig – anhalten und melden.

- [ ] **Step 3: pytest sammelt das Werkzeug nicht ein**

Run: `python3 -m pytest tests/ -q --collect-only 2>&1 | (grep -c compare_undo || true)`
Expected: `0`.

- [ ] **Step 4: Commit**

```bash
git add tests/equivalence/compare_undo.py
git commit -F - <<'EOF'
Add a tool that compares plan_undo old and new

Taking plan_undo apart changes which of two refusals wins and in which
order steps come out - things hardly any test looks at. The tool loads
the package as it stood after the move, with dulwich, next to the
working tree and compares both on built, generated and real inputs.
Nothing it reads is stored; it prints numbers only.

Refs #41

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

**Akzeptanz:** Exit 0, 0 Abweichungen alt gegen alt, 23 von 23 Vorlagen, pytest sammelt das Werkzeug nicht ein. Das Werkzeug beendet sich mit Exit 1 und einer Zeile `FAIL: …`, sobald es eine Abweichung, eine nie erreichte Vorlage, ein anderes als die 33 erwarteten Vorrang-Paare oder eine Laufzeit über 110 % findet (Terra, Plan-Review, Hoch 1).

---

### Aufgabe 11: `plan_undo` in Planer zerlegen

**Files:**
- Modify: `custom_components/dashboard_history/analyze/undo.py` (die Definition von `plan_undo` ersetzen, Importe ergänzen)
- Modify: `tools/complexity-baseline.json` (Eintrag `…/analyze/undo.py::plan_undo` streichen)

**Interfaces:**
- Consumes: `tests/equivalence/compare_undo.py` (Aufgabe 10).
- Produces: in `analyze.undo`: `UndoContext(before, after, current)`; `_GATES` (Tupel von vier Funktionen `(ctx) -> str | None`); `_PLANNERS` (dict Art → Funktion `(ctx) -> str | tuple[UndoStep, ...]`); `_CHECK_ORDER`, `_OUTPUT_ORDER` (Tupel von Artnamen); `_sections_meet_cards(planned: dict) -> str | None`; `plan_undo(before, after, current) -> UndoPlan` unverändert in Signatur und Docstring.

- [ ] **Step 1: Importe in `undo.py` ergänzen**

Unter `import copy` einfügen:

```python
from dataclasses import dataclass
from functools import cached_property
```

Die Importblöcke `from .matching import (…)` und `from .model import (…)` so ergänzen, dass sie mindestens diese Namen enthalten (vorhandene bleiben): aus `.matching` `_paths_collide`, `_positions_lie`, `_same`, `_section_drift`, `_setting_at`, `_view_type_changed`, `match_badges`, `match_cards`, `setting_changes`; aus `.model` `Slot`, `UndoPlan`, `UndoStep`, `_ABSENT`, `_describe`, `_view_name`, `_views_by_key`, `badge_containers`.

- [ ] **Step 2: Die Definition von `plan_undo` ersetzen**

Die gesamte Funktion `def plan_undo(…)` bis zu ihrem letzten `return` durch den folgenden Block ersetzen. `_POSITION_REFUSAL` bis `_plan_sections` davor bleiben unverändert. Die Kommentare stammen wörtlich aus dem alten `plan_undo` und stehen jetzt bei dem Planer, dessen Regel sie begründen.

```python
@dataclass(frozen=True, eq=False)
class UndoContext:
    """The three states of one undo, and what several planners read of them.

    Everything derived is computed once and kept. `plan_undo` asks for
    each value at the point where the single function it replaced
    computed it (`_COMPUTED_FIRST`, `_COMPUTED_BEFORE`), so an input that
    makes one of them raise still raises there.
    """

    before: dict
    after: dict
    current: dict

    @cached_property
    def matching(self):
        return match_cards(self.before, self.after)

    @cached_property
    def badge_matching(self):
        return match_badges(self.before, self.after)

    @cached_property
    def old_views(self) -> dict:
        return dict(_views_by_key(self.before))

    @cached_property
    def new_views(self) -> dict:
        return dict(_views_by_key(self.after))

    @cached_property
    def now_views(self) -> dict:
        return dict(_views_by_key(self.current))

    @cached_property
    def now_places(self) -> list:
        return _views_by_key(self.current)

    @cached_property
    def now_index(self) -> dict:
        return {key: index for index, (key, _) in enumerate(_views_by_key(self.current))}

    @cached_property
    def pairs(self) -> tuple:
        # Every state this plan reads from or writes to has to agree on
        # what a position means: `before` and `after` decide what the
        # change was, `current` is where the steps land.
        return (
            (self.before, self.after),
            (self.before, self.current),
            (self.after, self.current),
        )

    @cached_property
    def type_changed(self) -> bool:
        return any(_view_type_changed(one, other) for one, other in self.pairs)

    @cached_property
    def settings(self) -> list:
        return setting_changes(self.before, self.after)

    @cached_property
    def shifted(self) -> set:
        return _section_drift(self.new_views, self.now_views)

    @cached_property
    def card_now(self) -> dict:
        return _group_by_mark(_present(self.current))

    @cached_property
    def card_then(self) -> dict:
        return _group_by_mark(_present(self.after))

    @cached_property
    def badge_now(self) -> dict:
        return _group_by_mark(_present(self.current, badge_containers))

    @cached_property
    def badge_then(self) -> dict:
        return _group_by_mark(_present(self.after, badge_containers))


# -- checks that come before any planner -----------------------------------


def _nothing_changed(ctx: UndoContext) -> str | None:
    # A conversion (masonry to sections, typically) is a real alteration
    # even though it touches no card: Home Assistant leaves every
    # existing card exactly where it was, in the view's own `cards:`
    # list, and only adds an empty grid section. Left out of this check,
    # a save that did nothing but convert the view had nothing here to
    # register, and fell through to "did not alter any cards" - true of
    # the cards, false of the view.
    #
    # A section moved or re-set is a real alteration too, with no card event
    # of its own since its cards follow it (GitHub #31).
    matching, badges = ctx.matching, ctx.badge_matching
    if (
        matching.removed
        or matching.added
        or matching.edited
        or matching.moved
        or badges.removed
        or badges.added
        or badges.edited
        or badges.moved
        or set(ctx.old_views) ^ set(ctx.new_views)
        or ctx.type_changed
        or ctx.settings
        or matching.sections.views()
    ):
        return None
    return "this change did not alter any cards"


def _paths_collide_anywhere(ctx: UndoContext) -> str | None:
    # Before any pair is compared: a path that names two views is not an
    # identity, and everything below reads views by their path.
    if any(_paths_collide(state) for state in (ctx.before, ctx.after, ctx.current)):
        return _DUPLICATE_PATH_REFUSAL
    return None


def _positions_disagree(ctx: UndoContext) -> str | None:
    if any(_positions_lie(one, other) for one, other in ctx.pairs):
        return _POSITION_REFUSAL
    return None


def _view_type_converted(ctx: UndoContext) -> str | None:
    # Checked before `_section_drift`: a conversion changes the section
    # list too, and would otherwise be blamed on "the sections" instead
    # of on itself.
    return _VIEW_TYPE_REFUSAL if ctx.type_changed else None


# -- the planners, one per kind --------------------------------------------


def _plan_section_steps(ctx: UndoContext) -> str | tuple[UndoStep, ...]:
    # A view whose sections the change rearranged is put back in one step
    # of its own (GitHub #31) - or refused, and then before anything else.
    steps: list[UndoStep] = []
    for key in sorted(ctx.matching.sections.views(), key=str):
        planned = _plan_sections(
            key,
            ctx.old_views[key],
            ctx.new_views[key],
            ctx.now_views.get(key),
            ctx.now_index.get(key, -1),
            ctx.matching.sections,
        )
        if isinstance(planned, str):
            return planned
        if planned is not None:
            steps.append(planned)
    return tuple(steps)


def _plan_setting_steps(ctx: UndoContext) -> str | tuple[UndoStep, ...]:
    steps: list[UndoStep] = []
    for change in ctx.settings:
        label = ".".join(str(key) for key in change.path)
        if change.view_key is None:
            container = ctx.current
        else:
            container = ctx.now_views.get(change.view_key)
            if container is None:
                name = _view_name(ctx.old_views[change.view_key], change.view_key)
                return (
                    f'the view "{name}" is no longer on the dashboard, '
                    f'so its setting "{label}" cannot be taken back'
                )
        standing, vanished = _setting_at(container, change.path)
        if vanished is not None:
            return f'the setting "{label}" no longer has the "{vanished}" block it belonged to'
        if _same(standing, change.old):
            # Already back, the way a deleted card that returned is.
            continue
        if not _same(standing, change.new):
            return f'the setting "{label}" was changed again after this'
        key = change.view_key
        steps.append(
            UndoStep(
                action="unset" if change.old is _ABSENT else "set",
                kind="dashboard_setting" if key is None else "view_setting",
                view_path=None if key is None else container.get("path"),
                view_index=key[1] if isinstance(key, tuple) else -1,
                location=change.path,
                index=0,
                expect=None if change.new is _ABSENT else change.new,
                payload=None if change.old is _ABSENT else change.old,
                label=f'setting "{label}"',
                expect_absent=change.new is _ABSENT,
            )
        )
    return tuple(steps)


def _sole_card(ctx: UndoContext, slot: Slot, label: str) -> tuple[Slot | None, str | None]:
    # Counted in two stages, the same way `_sole_badge` below counts
    # badges (GitHub #36): "exactly one today" is not proof by itself -
    # an untouched copy that stood there before the change is not the
    # one the change produced. Asked first dashboard-wide, then, failing
    # that, in the card's own view.
    found, left = ctx.card_now.get(slot.mark, []), ctx.card_then.get(slot.mark, [])
    if len(found) == 1 and len(left) == 1:
        return found[0], None
    view_key = slot.view_key
    mine = _in_view(found, view_key)
    mine_then = _in_view(left, view_key)
    if len(mine) == 1 and len(mine_then) == 1:
        return mine[0], None
    if len(mine) < len(mine_then):
        return None, (
            f"{label} was changed again after this, so there is no "
            f"exact version left to put back"
        )
    return None, (
        f"{len(mine)} cards now look exactly like {label}, so an "
        f"exact undo cannot tell them apart"
    )


def _put_back(ctx: UndoContext, old_slot: Slot, label: str) -> tuple[tuple | None, UndoStep]:
    """Insert where the card came from, or park it in "Imported cards".

    Returns the step and, for a parked one, the place it came from - the
    step's own `view_index` and `index` already carry `old_slot`'s, only
    its original `location` does not, overwritten to `("cards",)` for
    `apply_undo` to find and to show, so that is the one piece kept
    beside the step for sorting. An ordinary insert comes with `None`.
    """
    if old_slot.view_key not in ctx.shifted or old_slot.location[:1] != ("sections",):
        return None, _step(old_slot, "insert", None, old_slot.card, label)
    # A pathless view is found by its position here, which
    # `_positions_lie` has already vouched for - the same proof an
    # ordinary insert into it rests on.
    return old_slot.location, _step(
        old_slot,
        "insert",
        None,
        old_slot.card,
        # The card that is parked, not the one taken out: the dialog
        # lists what somebody has to go and place.
        _describe(old_slot.card),
        location=("cards",),
        parked=True,
    )


def _card_came_back(ctx: UndoContext, mark: str, view_key: Any) -> int:
    return len(_in_view(ctx.card_now.get(mark, []), view_key)) - len(
        _in_view(ctx.card_then.get(mark, []), view_key)
    )


def _parked_order(item: tuple[tuple, UndoStep]) -> tuple:
    # In the order of the places they came from - view, section, card -
    # whichever of the three tables in decision 15 produced them.
    location, step = item
    return (step.view_index, location, step.index)


def _plan_card_steps(ctx: UndoContext) -> str | tuple[UndoStep, ...]:
    matching = ctx.matching
    placed: list[tuple[tuple | None, UndoStep]] = []

    # An edit and a move are the same undo: take the card off the place
    # it sits on today, and put it back on the place it came from. Two
    # steps rather than one replacement, and that is the whole point -
    # `_place` leaves the index out, so a card that was edited *and*
    # shifted arrives here as edited, and a replacement written at
    # today's index would land on its neighbour. Measured over 6000
    # generated histories: 48 silently wrong results that way, none this
    # way, and not one refusal more.
    for old_slot, new_slot in (*matching.edited, *matching.moved):
        label = _describe(new_slot.card)
        here, why = _sole_card(ctx, new_slot, label)
        if here is None:
            return why
        placed.append((None, _step(here, "remove", new_slot.card, None, label)))
        placed.append(_put_back(ctx, old_slot, label))

    for new_slot in matching.loose_added():
        label = _describe(new_slot.card)
        here, why = _sole_card(ctx, new_slot, label)
        if here is None:
            return why
        placed.append((None, _step(here, "remove", new_slot.card, None, label)))

    # Counted, not looked up, and only in the card's own view (GitHub
    # #35): an untouched copy on another view - there all along or added
    # since - is not this one coming back. A dashboard-wide look would
    # reopen the same door the bug used: a copy someone else placed
    # elsewhere after the change would count as this card's return.
    # Mirrors the badge rule below (Vorhaben N) - `deleted` is how many
    # alike the change took from that view, `_card_came_back` how many
    # more stand there now than the change left.
    removed = [(old_slot, old_slot.mark) for old_slot in matching.loose_removed()]
    deleted: dict[tuple[str, Any], int] = {}
    for old_slot, mark in removed:
        place = (mark, old_slot.view_key)
        deleted[place] = deleted.get(place, 0) + 1

    for old_slot, mark in removed:
        label = _describe(old_slot.card)
        back = _card_came_back(ctx, mark, old_slot.view_key)
        if back >= deleted[(mark, old_slot.view_key)]:
            # Already back by some other route. Inserting would make a
            # second copy, and this part of the change is undone either
            # way.
            continue
        if back > 0:
            # Some of several alike are back: which places they took is
            # not in the states, and picking one would be a guess.
            return (
                f"only some of the copies of {label} this change "
                f"deleted are back, so an exact undo cannot tell "
                f"which are missing"
            )
        placed.append(_put_back(ctx, old_slot, label))

    # Parked insertions go after every other card step, sorted.
    ordinary = [step for where, step in placed if where is None]
    parked = sorted(((where, step) for where, step in placed if where is not None), key=_parked_order)
    return (*ordinary, *(step for _where, step in parked))


def _sole_badge(ctx: UndoContext, slot: Slot, label: str) -> tuple[Slot | None, str | None]:
    # Badges (GitHub #29): the same table as cards, counted in their own
    # world. The same badge on several views is ordinary - 6 of 23 on the
    # installation this was built against - so "exactly once" is asked in
    # two stages: on the whole dashboard, and failing that, in the view
    # the change left it in. Both answer decision 15's question; the
    # second only asks it where the badge was left. And both compare
    # today with what the change left: one standing today, out of several
    # the change left, may be the one that was there before it.
    found, left = ctx.badge_now.get(slot.mark, []), ctx.badge_then.get(slot.mark, [])
    if len(found) == 1 and len(left) == 1:
        return found[0], None
    view_key = slot.view_key
    mine = _in_view(found, view_key)
    mine_then = _in_view(left, view_key)
    if len(mine) == 1 and len(mine_then) == 1:
        return mine[0], None
    if len(mine) < len(mine_then):
        return None, (
            f"{label} was changed again after this, so there is no "
            f"exact version left to put back"
        )
    # Here `mine` holds at least two: the view has as many as the
    # change left, or more, and not exactly one of each.
    return None, (
        f"{len(mine)} badges now look exactly like {label}, "
        f"so an exact undo cannot tell them apart"
    )


def _badge_came_back(ctx: UndoContext, mark: str, view_key: Any) -> int:
    return len(_in_view(ctx.badge_now.get(mark, []), view_key)) - len(
        _in_view(ctx.badge_then.get(mark, []), view_key)
    )


def _badge_label(badge: Any) -> str:
    return f"the badge {_describe(badge, fallback='badge')}"


def _plan_badge_steps(ctx: UndoContext) -> str | tuple[UndoStep, ...]:
    matching = ctx.badge_matching
    steps: list[UndoStep] = []
    for old_slot, new_slot in (*matching.edited, *matching.moved):
        label = _badge_label(new_slot.card)
        here, why = _sole_badge(ctx, new_slot, label)
        if here is None:
            return why
        steps.append(_step(here, "remove", new_slot.card, None, label, kind="badge"))
        steps.append(_step(old_slot, "insert", None, old_slot.card, label, kind="badge"))

    for new_slot in matching.added:
        label = _badge_label(new_slot.card)
        here, why = _sole_badge(ctx, new_slot, label)
        if here is None:
            return why
        steps.append(_step(here, "remove", new_slot.card, None, label, kind="badge"))

    # Counted, not looked up, and only in the badge's own view: a copy on
    # another view - there all along or added since - is not this badge
    # coming back. `_badge_came_back` is how many more stand there now
    # than the change left; `deleted` how many alike it took from that
    # view. Each removed slot's mark is kept beside it - `deleted` and the
    # loop below both need it, and it is already sitting on the slot.
    removed = [(old_slot, old_slot.mark) for old_slot in matching.removed]
    deleted: dict[tuple[str, Any], int] = {}
    for old_slot, mark in removed:
        place = (mark, old_slot.view_key)
        deleted[place] = deleted.get(place, 0) + 1

    for old_slot, mark in removed:
        label = _badge_label(old_slot.card)
        back = _badge_came_back(ctx, mark, old_slot.view_key)
        if back >= deleted[(mark, old_slot.view_key)]:
            continue
        if back > 0:
            # Some of several alike are back: which places they took is
            # not in the states, and picking one would be a guess.
            return (
                f"only some of the copies of {label} this change deleted "
                f"are back, so an exact undo cannot tell which are missing"
            )
        steps.append(_step(old_slot, "insert", None, old_slot.card, label, kind="badge"))
    return tuple(steps)


# Whole views, which `match_cards` leaves out on purpose: a view that
# only one state has is one line in the history, not one per card on
# it. Undoing it is the same two questions in a coarser grain - is it
# still exactly as the change left it, and is it still there at all.
#
# Both halves ask that of the view's *content*, not of its key. A
# key is a path, and a path is renameable and reusable: asking only
# whether one is present answers "already taken back" for a view
# somebody renamed, and "already back" for a stranger that happens to
# sit on the same path. Both are the one error this tool must never
# make - a sentence that says nothing changed while something did.


def _plan_added_views(ctx: UndoContext) -> str | tuple[UndoStep, ...]:
    steps: list[UndoStep] = []
    for key, view in _views_by_key(ctx.after):
        if key in ctx.old_views:
            continue
        # The change added this view. Take it away - the very one it
        # added, found by what it holds.
        name = _view_name(view, key)
        found = [index for index, (_, standing) in enumerate(ctx.now_places) if standing == view]
        if len(found) > 1:
            return (
                f'{len(found)} views now look exactly like "{name}", '
                f"so an exact undo cannot tell them apart"
            )
        if not found:
            if key in ctx.now_views:
                return f'the view "{name}" was changed again after this'
            return (
                f'the view "{name}" is no longer on the dashboard as '
                f"this change left it, so an exact undo cannot take it away"
            )
        index = found[0]
        steps.append(
            UndoStep(
                action="remove",
                kind="view",
                view_path=view.get("path"),
                view_index=index,
                location=(),
                index=index,
                expect=view,
                payload=None,
                label=f'view: {name}',
            )
        )
    return tuple(steps)


def _plan_removed_views(ctx: UndoContext) -> str | tuple[UndoStep, ...]:
    steps: list[UndoStep] = []
    for index, (key, view) in enumerate(_views_by_key(ctx.before)):
        if key in ctx.new_views:
            # The change did not remove it.
            continue
        # Already back, either on its own path or - a view without one is
        # keyed by its position - somewhere else. Inserting would make a
        # second copy.
        if any(standing == view for _, standing in ctx.now_places):
            continue
        standing = ctx.now_views.get(key)
        if standing is not None and view.get("path") is not None:
            # A different view holds that path today. Two views on one
            # path is a broken dashboard, and picking one of them is a
            # guess, so this refuses instead.
            return (
                f'a different view now sits at "{view["path"]}", so the '
                f'view "{_view_name(view, key)}" cannot be put back there'
            )
        steps.append(
            UndoStep(
                action="insert",
                kind="view",
                view_path=view.get("path"),
                view_index=index,
                location=(),
                index=index,
                expect=None,
                payload=view,
                label=f'view: {_view_name(view, key)}',
            )
        )
    return tuple(steps)


def _plan_view_steps(ctx: UndoContext) -> str | tuple[UndoStep, ...]:
    added = _plan_added_views(ctx)
    if isinstance(added, str):
        return added
    removed = _plan_removed_views(ctx)
    if isinstance(removed, str):
        return removed
    return (*added, *removed)


def _sections_meet_cards(planned: dict) -> str | None:
    """Q1: a view's whole row of sections next to a card step in the same view.

    One step writes a view's whole row of sections; a card step in the
    same view would write into a row that step replaces. Unlike the
    other stages this reads what the planners produced, not the context,
    so the combiner calls it after the last planner.
    """
    rewritten = {step.view_path or ("#", step.view_index) for step in planned["sections"]}
    if any(
        step.kind == "card" and (step.view_path or ("#", step.view_index)) in rewritten
        for kind in _OUTPUT_ORDER
        if kind != "sections"
        for step in planned[kind]
    ):
        return _SECTIONS_AND_CARDS_REFUSAL
    return None


# -- the combiner ------------------------------------------------------------

_GATES = (_nothing_changed, _paths_collide_anywhere, _positions_disagree, _view_type_converted)

_PLANNERS = {
    "sections": _plan_section_steps,
    "settings": _plan_setting_steps,
    "cards": _plan_card_steps,
    "badges": _plan_badge_steps,
    "views": _plan_view_steps,
}

# The order in which refusals are looked for; the first one found is the
# answer. Sections first: a view whose sections the change rearranged is
# refused before anything else is asked of it (GitHub #31). A new kind of
# change adds its planner here AND to _OUTPUT_ORDER, deciding both places.
_CHECK_ORDER = ("sections", "settings", "cards", "badges", "views")

# Computed where the single plan_undo computed them, whether a planner
# goes on to read them or not. An input that makes one of them raise -
# a view whose "sections" is a number, say - has to raise at the same
# point as before, not later or not at all (Astra, plan review). The
# order inside each tuple is the order they were computed in.
_COMPUTED_FIRST = (
    "matching",
    "badge_matching",
    "old_views",
    "new_views",
    "now_views",
    "type_changed",
    "settings",
)
_COMPUTED_BEFORE = {
    "sections": ("shifted", "now_index"),
    "cards": ("card_now", "card_then"),
    "badges": ("badge_now", "badge_then"),
    "views": ("now_places",),
}

# The order in which the steps are handed to apply_undo. It is observable:
# apply_undo sorts by index only, with a stable sort, so steps on equal
# indices keep this order - across kinds too. Settings first (they shift
# no index), sections last although checked first: a section step
# replaces a whole row, after the single cards in it are settled.
_OUTPUT_ORDER = ("settings", "cards", "badges", "views", "sections")


def plan_undo(before: dict, after: dict, current: dict) -> UndoPlan:
    """How to take one change back, or why that cannot be exact.

    The change is read as `match_cards(before, after)` - what it removed,
    added, edited and moved. For everything it *produced*, the plan then
    asks one question of the state as it stands today: does this card sit
    there exactly once? Once means it can be pointed at. Zero means
    somebody changed it again since. Two or more means an undo would have
    to guess which - and guessing is what decision 4 forbids.

    Note which side is looked up. The check is on what the change left
    behind, never on its surroundings: a card added *next to* an edited
    one does not make the edit ambiguous, and blocking there would refuse
    almost every real history.
    """
    # The work is done by four checks, one planner per kind and one check
    # across two planners (spec P, section 3); this function only runs
    # them in _CHECK_ORDER and hands the steps on in _OUTPUT_ORDER. The
    # docstring above is the old one, unchanged (spec P, section 3).
    ctx = UndoContext(before, after, current)
    for name in _COMPUTED_FIRST:
        getattr(ctx, name)
    for gate in _GATES:
        refusal = gate(ctx)
        if refusal is not None:
            return UndoPlan(blocked=refusal)
    planned: dict[str, tuple[UndoStep, ...]] = {}
    for kind in _CHECK_ORDER:
        for name in _COMPUTED_BEFORE.get(kind, ()):
            getattr(ctx, name)
        result = _PLANNERS[kind](ctx)
        if isinstance(result, str):
            return UndoPlan(blocked=result)
        planned[kind] = result
    refusal = _sections_meet_cards(planned)
    if refusal is not None:
        return UndoPlan(blocked=refusal)
    return UndoPlan(blocked=None, steps=tuple(step for kind in _OUTPUT_ORDER for step in planned[kind]))
```

- [ ] **Step 3: Suite**

Run: `python3 -m pytest tests/ -q`
Expected: `0 failed`.

- [ ] **Step 4: Der Vergleich**

Run: `python3 tests/equivalence/compare_undo.py`
Expected: Exit 0 ohne `FAIL`-Zeile; `differences: 0`; `23 of 23`; `pairs of refusing stages met: 33`; `ratio` höchstens `1.10` (erprobt: 1,01 – die neue Fassung berechnet vorab, was die alte vorab berechnete, und ist deshalb nicht schneller; eine frühere Fassung dieses Plans war mit 0,86 genau deshalb schneller, weil sie das nicht tat). Fehlen dürfen genau die zwölf Paare aus `UNREACHABLE`; das Werkzeug prüft das selbst. Jede Abweichung ist ein Fehler in diesem Schritt – nicht das Werkzeug ändern, sondern den Planer mit dem alten `plan_undo` aus `git show HEAD:custom_components/dashboard_history/analyze/undo.py` vergleichen.

- [ ] **Step 4a: Die Gegenprobe**

In `undo.py` vorübergehend `_GATES` umstellen auf `(_nothing_changed, _view_type_converted, _positions_disagree, _paths_collide_anywhere)`.
Run: `python3 tests/equivalence/compare_undo.py`
Expected: Exit 1, `FAIL: … input(s) answered differently` (erprobt: 366) und `FAIL: pairs met are not the expected 33: missing [['V1', 'V2']], unexpected [['V1', 'V4']]`.
Dann zurücknehmen; `git diff` zeigt wieder nur die Änderungen aus Schritt 1 und 2.

- [ ] **Step 5: Die Sperrklinke**

Run: `python3 tools/complexity_ratchet.py`
Expected: **Exit 1** mit genau drei Zeilen `…/analyze/undo.py::plan_undo: C901 is within the limit now - remove it from the baseline` (ebenso `PLR0912`, `PLR0915`), sonst nichts – das Rot ist hier gewollt: Die Sperrklinke verlangt, die Baseline zu senken (Gemini, Plan-Review). Keine Zeile »over the limit and not in the baseline« – eine solche wäre ein Planer über der Grenze und wird durch weiteres Zerlegen in `undo.py` behoben, nicht durch die Baseline.

- [ ] **Step 6: Baseline senken**

In `tools/complexity-baseline.json` den Eintrag `"custom_components/dashboard_history/analyze/undo.py::plan_undo"` löschen.
Run: `python3 tools/complexity_ratchet.py && lint-imports`
Expected: `complexity: 20 known values, none grew`; `2 kept, 0 broken`.

- [ ] **Step 7: Länge**

Run: `wc -l custom_components/dashboard_history/analyze/undo.py`
Expected: unter 900 (erprobt: 837).

- [ ] **Step 8: Commit**

```bash
git add custom_components/dashboard_history/analyze/undo.py tools/complexity-baseline.json
git commit -F - <<'EOF'
Take plan_undo apart into one planner per kind

Every initiative since L added a block to one 430-line function, and
which refusal won was decided by where the block happened to sit. Now
four checks, five planners and one cross-check are separate functions,
and the order refusals are looked for and the order steps come out in
are two tuples side by side, each with its reason. A new kind of change
adds a planner and has to place it in both.

Compared with the state before, on built, generated and real inputs:
no difference. The baseline loses plan_undo's three entries.

Refs #41

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

**Akzeptanz:** Suite grün, 0 Abweichungen, 23/23 Vorlagen, 33 Paare, Laufzeit höchstens 110 %, Baseline mit 20 Werten, `undo.py` unter 900 Zeilen.

---

### Aufgabe 12: Dokumentation, Container, Nachtrag

**Files:**
- Modify: `docs/superpowers/specs/2026-08-30-dashboard-history-design.md` (Modultabelle, zwei Ablaufdiagramme, Abschnitt »Reihenfolge der Vorhaben«)
- Modify: `docs/superpowers/status.md` (Zeile P, Modul-Übersicht)
- Modify: `CLAUDE.md` (»Hard rules«: `analyze/` statt `analyze.py`)
- Modify: `docs/development.md`, `docs/how-it-works.md` (wo sie `analyze.py` nennen)
- Modify: dieser Plan (Nachtrag)

- [ ] **Step 1: Stellen finden**

Run: `grep -n "analyze\.py" CLAUDE.md docs/development.md docs/how-it-works.md docs/superpowers/status.md docs/superpowers/specs/2026-08-30-dashboard-history-design.md`
Jede Stelle einordnen: **Gegenwartsbezug** (beschreibt, wie der Code heute aufgebaut ist) → auf `analyze/` bzw. das zuständige Teilmodul umstellen; **historisch** (beschreibt, was an einem Datum geschah – etwa Entscheidung 11 oder die Nachträge zu E, F, J, K in der Haupt-Spec) → unverändert lassen. In der Haupt-Spec sind laut Spec P genau die Modultabelle (um Zeile 55) und die beiden Ablaufdiagramme (um Zeilen 99 und 105) gegenwartsbezogen.

- [ ] **Step 2: Haupt-Spec**

Modultabelle: die Zeile `analyze.py` durch `analyze/` (Paket: `model`, `matching`, `removed`, `explain`, `undo`) ersetzen, Aufgabe und »ohne Home Assistant: ja« unverändert. Diagramme: `analyze.py vergleicht …` → `analyze vergleicht …`, `analyze.py bestimmt …` → `analyze bestimmt …`. Im Abschnitt »Reihenfolge der Vorhaben« eine neue Unterüberschrift anfügen:

```markdown
### Nachgetragen am 2026-09-27: P

- **P — `analyze.py` aufteilen.** *(Issue [#41](https://github.com/PPP01/ha-dashboard-history/issues/41).)* `specs/2026-09-27-analyze-aufteilen-design.md`. Kein neues Verhalten: eine Sperrklinke für Komplexität und Importverträge in der CI, `analyze` als Paket mit fünf Modulen in Schichten, `plan_undo` als Kombinierer über einen Planer je Art. Prüf- und Ausgabereihenfolge stehen seither als zwei Tupel in `analyze/undo.py`.
```

- [ ] **Step 3: `status.md`**

In der Tabelle »Vorhaben, Buchstabe für Buchstabe« nach O die Zeile:

```markdown
| P | `analyze.py` aufteilen – Komplexitäts-Sperrklinke und Importverträge, Paket mit fünf Modulen, `plan_undo` als Planer je Art (Issue #41) | Erledigt (2026-09-27) | `specs/2026-09-27-analyze-aufteilen-design.md`, `plans/2026-09-27-analyze-aufteilen.md` |
```

In der Modul-Übersicht die Zeile `analyze.py ✓` ersetzen durch:

```markdown
| `analyze/` ✓ | Erkennt, was sich zwischen zwei Ständen geändert hat; plant Undo. Paket in Schichten: `model` (Typen, Lesen, Benennen) → `matching` (Zuordnung) → `removed` (Put back) → `explain` (Worte) \| `undo` (gezielte Rücknahme); geprüft von `lint-imports` |
```

und die Einleitung der Übersicht (»laut Grep auch (Stand …)«) ergänzen um: »seit Vorhaben P zusätzlich von `lint-imports` geprüft«. Unter »Bekannte offene Punkte« nichts streichen.

- [ ] **Step 4: `CLAUDE.md`**

Im Punkt zu den HA-freien Modulen `analyze.py` durch `analyze/` (the package, every module in it) ersetzen; der Rest des Satzes aus Aufgabe 2 bleibt.

- [ ] **Step 5: `docs/development.md` und `docs/how-it-works.md`**

Das Diagramm in `docs/development.md` (`Analyze["analyze.py (4-Pass Card Matching & Diff Engine)"]`) auf `Analyze["analyze/ (card matching, explanation, undo planning)"]` umstellen, die Modulliste auf das Paket mit seinen fünf Modulen. In `docs/how-it-works.md` nur Stellen mit Gegenwartsbezug anpassen.

- [ ] **Step 6: Container**

```bash
docker restart dashboard-history-test
python3 tests/integration/run_checks.py
```

Expected: dieselben roten Prüfungen wie in Aufgabe 3, Schritt 1, keine weitere.

- [ ] **Step 7: Der letzte Vergleich und der Nachtrag**

Run: `python3 tests/equivalence/compare_undo.py`
Die Ausgabe (sie enthält nur Zahlen und Vorlagen) unter einer neuen Überschrift `## Nachtrag: Abnahme vom <Datum>` an das Ende dieses Plans kopieren, ergänzt um einen Absatz, der die fehlenden Paare begründet. Erwartet sind genau diese zwölf, beide Gruppen strukturell unmöglich:

- **V1 mit V4, `sections`, `settings`, `cards`, `badges`, `views`, Q1** – V1 verweigert nur, wenn die Änderung nichts geändert hat; eine Typänderung zählt dort als Änderung, und ohne Änderung hat kein Planer etwas zu verweigern.
- **Q1 mit `sections`, `settings`, `cards`, `badges`, `views`** – Q1 wird nur ausgewertet, wenn alle Planer durchgekommen sind; das gilt in der alten Fassung genauso.

Fehlt ein anderes Paar, ist das ein Befund: einen konstruierten Fall ergänzen, der es herstellt (Muster wie »V2 before V4 (Astra)«), und neu laufen lassen.

- [ ] **Step 8: Suite und Wachen**

Run: `python3 -m pytest tests/ -q && python3 tools/complexity_ratchet.py && lint-imports`
Expected: `0 failed`, `20 known values, none grew`, `2 kept, 0 broken`.

- [ ] **Step 9: Commit**

```bash
git add CLAUDE.md docs/
git commit -F - <<'EOF'
Document the analyze package

The hard rule, the module overview and the diagrams named a file that
no longer exists. The places that record what happened on a given day
keep naming it; the plan gets the numbers of the final comparison.

Refs #41

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

**Akzeptanz:** keine gegenwartsbezogene Stelle nennt mehr `analyze.py`; historische unverändert; Nachtrag mit Zahlen und Begründung der zwölf Paare; `run_checks.py` wie vorher.

---

### Aufgabe 13: Das Vergleichswerkzeug entfernen

**Files:**
- Delete: `tests/equivalence/compare_undo.py` (und das dann leere Verzeichnis)

- [ ] **Step 1: Entfernen**

```bash
git rm tests/equivalence/compare_undo.py
```

- [ ] **Step 2: Suite und Wachen**

Run: `python3 -m pytest tests/ -q && python3 tools/complexity_ratchet.py && lint-imports`
Expected: `0 failed`, `none grew`, `2 kept, 0 broken`.

- [ ] **Step 3: Commit**

```bash
git commit -F - <<'EOF'
Remove the plan_undo comparison tool

It compared against the state before P3, which no longer exists to be
compared with. Its last run is recorded in the plan; the tool itself
stays in the history in case #42 needs something alike.

Refs #41

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

**Akzeptanz:** `git show --stat HEAD` zeigt genau eine gelöschte Datei; nichts sonst.

---

## Plan-Review vom 2026-09-27 (Terra, Astra, Gemini)

Alle übernommenen Befunde sind an einer Kopie nachgeprüft; die Codeblöcke oben sind die geänderten.

**Übernommen:**

- *Terra Hoch 1* – das Vergleichswerkzeug gab nur aus, statt zu erzwingen. Es endet jetzt mit Exit 1 bei jeder Abweichung, jeder nie erreichten Vorlage, jedem anderen als den 33 erwarteten Vorrang-Paaren (auch einem angeblich unmöglichen, das doch auftaucht) und einer Laufzeit über 110 %. Beim Einarbeiten selbst gefunden: Ohne echte Dashboards kamen nur 30 Paare zustande; drei neue konstruierte Fälle schließen das, 33 Paare mit und ohne.
- *Terra Hoch 2* – der Docstring von `plan_undo` bleibt byte-gleich; der Zusatz ist ein Kommentar.
- *Terra Mittel 1* – `hassfest` nach der neuen `pyproject.toml` lokal im Container (Aufgabe 1, Schritt 11); die Ausweichlösung `ruff.toml`/`.importlinter` steht fertig da, die INI-Fassung erprobt.
- *Astra* – eine Eingabe, bei der die alte Fassung wirft und die neue eine Verweigerung liefert. Behoben für die ganze Klasse: `_COMPUTED_FIRST` und `_COMPUTED_BEFORE` erzwingen jeden Wert an der Stelle, an der die alte Funktion ihn berechnete. Astras Eingabe ist der elfte konstruierte Fall; ohne die Korrektur wird das Werkzeug rot. Preis: der Geschwindigkeitsvorteil ist weg (Verhältnis 1,01 statt 0,86) – er kam genau daher, dass Werte nicht berechnet wurden.
- *Gemini Hoch 1* – die Sperrklinke findet `ruff` auch ohne `PATH` (`shutil.which`, sonst `python -m ruff`).
- *Gemini Hoch 2* – das Werkzeug bricht ab, wenn `restore.py` vom Stand in `BASE_COMMIT` abweicht (beide Fassungen laufen durch dasselbe `restore.py`, und P ändert es nicht).
- *Gemini Mittel 4* – eine Ausnahme wird mit Funktion und Quellzeile ihres innersten Rahmens verglichen, nicht nur mit Typ und Text; eine Ausnahme in `apply_undo` wird verglichen statt das Werkzeug abzubrechen; `refusing_stages` übergeht Eingaben, die werfen.
- *Gemini Mittel 5* – das Umzugsskript bricht bei Importen mit `as` und bei Entpacken auf oberster Ebene ab, statt stillschweigend falsch zu schreiben. Beides kommt in `analyze.py` nicht vor (von Gemini am AST geprüft); es läuft dort unverändert.
- *Gemini Niedrig 6 und 7* – `grep -c … || true`; der gewollte Exit 1 der Sperrklinke in Aufgabe 11, Schritt 5 steht jetzt dabei.

**Zurückgewiesen:**

- *Gemini Mittel 3* (die kanonische Form solle die Reihenfolge von Dict-Schlüsseln ignorieren). `yaml_io.dump` schreibt mit `sort_keys=False`; die Reihenfolge landet byte-genau im gespeicherten Dashboard und ist damit Verhalten. Eine Fassung, die Schlüssel anders ordnet, soll auffallen. Die Feld-Dicts von Datenklassen haben durch ihre Klasse ohnehin eine feste Reihenfolge.

## Selbstprüfung (beim Schreiben erledigt)

- **Spec-Abdeckung:** P1 Sperrklinke → Aufgabe 1; `import-linter` beide Verträge → Aufgabe 2; CI-Job → 1 und 2; Paket per `git mv` → 3; fünf Module in der Reihenfolge der Spec → 4–8; Schnittstelle mit 26 Namen und Test → 9; Werkzeug mit `dulwich`, ganzem Paket, strenger kanonischer Form, konstruierten Fällen, Generator, echten Dashboards, Laufzeit und Zusammenfassung → 10; Kontext, V1–V4, fünf Planer, Q1, zwei Tupel, Hilfsfunktionen auf Modulebene → 11; Baseline sinkt von 23 auf 20 → 11; Dokumentation einschließlich der Stellen der Haupt-Spec → 12; Entfernen als eigener letzter Commit → 13. Das Sammel-Issue der Spec → Aufgabe 1, Schritt 6.
- **Platzhalter:** zwei Werte entstehen erst bei der Ausführung und sind als solche benannt – die Issue-Nummer `#N` (Aufgabe 1, Schritt 6) und `BASE_COMMIT` (Aufgabe 9, letzter Schritt).
- **Namen:** `UndoContext`, `_GATES`, `_PLANNERS`, `_CHECK_ORDER`, `_OUTPUT_ORDER`, `_sections_meet_cards` sind in Aufgabe 11 definiert und in Aufgabe 10 genauso benutzt; `card_now` heißt im Kontext so, was im alten Code `by_mark` hieß.

## Nachtrag: Abnahme vom 2026-09-27

```
base commit: 37472532a1d9e54031a16e370bd828ad39daf025
inputs: 10011 (constructed: 11, bases: 5 built in + 14 real, seeds: (1, 2, 3, 4, 5))
differences: 0
refusal templates reached: 23 of 23
     184  the sections of the view "{…}" changed in a way this undo cannot account for, so it refuses rather than guess
      46  the view "{…}" is no longer on the dashboard, so its sections cannot be taken back
       1  the sections of the view "{…}" are not a plain list in every state, so an exact undo cannot write them back
     148  the other sections of the view "{…}" were rearranged since, so there is no telling where these go back
      33  more than one section of the view "{…}" was changed since, so which is which can no longer be proven
      64  the {…} was changed again after this, so there is no exact version left to take back
       1  {…} sections now look exactly like {…}, so an exact undo cannot tell them apart
    2152  this change did not alter any cards
     475  __DUPLICATE_PATH__
    1010  __POSITION__
     514  __VIEW_TYPE__
      26  the view "{…}" is no longer on the dashboard, so its setting "{…}" cannot be taken back
       1  the setting "{…}" no longer has the "{…}" block it belonged to
      29  the setting "{…}" was changed again after this
     286  {…} was changed again after this, so there is no exact version left to put back
     172  {…} cards now look exactly like {…}, so an exact undo cannot tell them apart
       2  only some of the copies of {…} this change deleted are back, so an exact undo cannot tell which are missing
      54  {…} badges now look exactly like {…}, so an exact undo cannot tell them apart
       9  {…} views now look exactly like "{…}", so an exact undo cannot tell them apart
     222  the view "{…}" was changed again after this
     117  the view "{…}" is no longer on the dashboard as this change left it, so an exact undo cannot take it away
       1  a different view now sits at "{…}", so the view "{…}" cannot be put back there
      82  __SECTIONS_AND_CARDS__
pairs of refusing stages met: 33
  x  V1 + V2
  x  V1 + V3
  .  V1 + V4
  .  V1 + sections
  .  V1 + settings
  .  V1 + cards
  .  V1 + badges
  .  V1 + views
  .  V1 + Q1
  x  V2 + V3
  x  V2 + V4
  x  V2 + sections
  x  V2 + settings
  x  V2 + cards
  x  V2 + badges
  x  V2 + views
  x  V2 + Q1
  x  V3 + V4
  x  V3 + sections
  x  V3 + settings
  x  V3 + cards
  x  V3 + badges
  x  V3 + views
  x  V3 + Q1
  x  V4 + sections
  x  V4 + settings
  x  V4 + cards
  x  V4 + badges
  x  V4 + views
  x  V4 + Q1
  x  sections + settings
  x  sections + cards
  x  sections + badges
  x  sections + views
  .  sections + Q1
  x  settings + cards
  x  settings + badges
  x  settings + views
  .  settings + Q1
  x  cards + badges
  x  cards + views
  .  cards + Q1
  x  badges + views
  .  badges + Q1
  .  views + Q1
plan_undo time: old 19.07s, new 19.23s, ratio 1.01
```

Es fehlen genau die zwölf erwarteten Vorrang-Paare, die in beiden Fassungen strukturell unmöglich sind:
- **V1 mit V4, `sections`, `settings`, `cards`, `badges`, `views`, Q1** – V1 verweigert nur, wenn die Änderung nichts geändert hat; eine Typänderung zählt dort als Änderung, und ohne Änderung hat kein Planer etwas zu verweigern.
- **Q1 mit `sections`, `settings`, `cards`, `badges`, `views`** – Q1 wird nur ausgewertet, wenn alle Planer durchgekommen sind; das gilt in der alten Fassung genauso.
