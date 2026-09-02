# Versionen pro Dashboard — Umsetzungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Jedes Dashboard bekommt benannte Versionen mit Versionsnummern — anlegbar an jeder Zeile des Verlaufs, sichtbar als Abschnitte darin, und jederzeit in beide Richtungen anspringbar.

**Architecture:** Eine Version ist ein annotierter git-Tag `<schlüssel>/v<major>.<minor>.<patch>`. Das Anlegen schreibt **keinen** Commit, es markiert einen vorhandenen. Die Nummernrechnung liegt in einem neuen Home-Assistant-freien Modul `versions.py`; das Zurückwechseln ist der bestehende `restore_state` mit dem Versionsnamen als Revision, was erst funktioniert, nachdem `store._resolve()` Tag-Namen auflösen kann — heute tut es das nachweislich nicht.

**Tech Stack:** Python 3.12 (Entwicklung) / 3.14 (Container), dulwich 1.2.14, Home Assistant 2026.8.3, pytest, reines JavaScript ohne Build-Schritt.

**Spec:** `docs/superpowers/specs/2026-08-30-dashboard-history-design.md` — **Entscheidung 13** und der Nachtrag zu Entscheidung 10. Bindend bei Widersprüchen.

## Global Constraints

Diese gelten für **jede** Aufgabe. Sie stehen so in der Spec und in `CLAUDE.md`:

- **Kein Systemaufruf von `git`.** Ausschließlich `dulwich`.
- **Keine Home-Assistant-Interna abfangen oder ersetzen.** Kein Monkey-Patching.
- **Nichts blockiert den Start von Home Assistant.** Fehler beim Erfassen werden protokolliert und verschluckt.
- **`yaml_io.py`, `analyze.py`, `restore.py` und das neue `versions.py` bleiben Home-Assistant-frei.** Kein `import homeassistant` darin.
- **Blockierende Arbeit gehört in einen Executor** (`hass.async_add_executor_job`).
- **Nichts wird ohne Vorschau geschrieben.** Jeder verändernde Dienst verlangt `confirm: true`. *Ausnahme wie bei `describe`: Eine Version anzulegen ändert kein Dashboard und braucht keine.*
- **Zurückgeholt wird nur Verschwundenes, nicht Bearbeitetes** (Entscheidung 4). Ein ganzer Stand ist davon ausgenommen und wird ersetzt.
- **Sprache: Englisch für alles, was nach außen geht** — Code, Kommentare, Docstrings, Dienstnamen, Log-Meldungen **und Commit-Botschaften**. Am 2026-09-02 umgestellt; die 51 älteren deutschen Botschaften bleiben stehen und werden nicht umgeschrieben. Nur dieser Plan und die Spec sind Deutsch.
- **Commit-Format:** Subject im Imperativ, erster Buchstabe groß, max. 50 Zeichen. Leerzeile. Body max. 72 Zeichen je Zeile, begründet das *Warum*. Abschluss mit `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- **Kein Push.** Branch ist `main`, es gibt kein Remote.

**Prüfbefehle:**

```bash
python3 -m pytest tests/ -v                      # Aufgaben 1-3, 8
docker compose -f docker/compose.yaml up -d      # Voraussetzung für 4-6
python3 tests/integration/run_checks.py          # Aufgaben 4, 5, 8
python3 tests/integration/look_at_panel.py       # Aufgaben 6, 8
```

## Dateien

| Datei | Verantwortung |
|---|---|
| **Neu** `custom_components/dashboard_history/versions.py` | Versionsnummern: einlesen, ordnen, hochzählen, Namen bilden. Home-Assistant-frei |
| **Neu** `tests/test_versions.py` | Prüfungen dazu, reines pytest |
| `store.py` | `_resolve` löst Tag-Namen auf; `list_versions` filtert nach Dashboard; `create_version` prüft Kollisionen |
| `operations.py` | `async_next_versions`, `async_create_version` mit Stufe, `async_versions` mit Filter, `async_history` nennt die Versionen je Änderung |
| `services.py` + `services.yaml` | Dieselben drei Vorgänge als Dienste |
| `websocket_api.py` | Dieselben drei Vorgänge für das Panel |
| `panel.js` | Abschnitte im Verlauf, Anlege-Dialog, »Zurück zu« |
| **Neu** `custom_components/dashboard_history/panel/` | Nur Aufgabe 8: die ausgelagerten Teile |
| `panel.py` | Nur Aufgabe 8: Fingerabdruck über alle Teile, Verzeichnis ausliefern |
| `README.md`, `CLAUDE.md` | Die zwei Falschaussagen berichtigen |

**Reihenfolge:** 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8. Aufgabe 8 ist bewusst zuletzt und einzeln verwerfbar: Sie fasst die Auslieferung an, nicht das Merkmal.

---

### Task 1: `versions.py` — die Nummernrechnung

Reine Logik, kein Home Assistant. Sie kommt zuerst, weil alles Weitere sie benutzt.

**Files:**
- Create: `custom_components/dashboard_history/versions.py`
- Test: `tests/test_versions.py`

**Interfaces:**
- Consumes: nichts
- Produces:
  - `LEVELS: tuple[str, ...]` — `("patch", "minor", "major")`
  - `version_name(key: str, parts: tuple[int, int, int]) -> str`
  - `parse(key: str, name: str) -> tuple[int, int, int] | None`
  - `latest(key: str, names: Iterable[str]) -> tuple[int, int, int] | None`
  - `bump(parts: tuple[int, int, int], level: str) -> tuple[int, int, int]`
  - `candidates(key: str, names: Iterable[str]) -> dict[str, str | None]` — Schlüssel `"patch"`, `"minor"`, `"major"`, `"current"`

- [ ] **Step 1: Write the failing test**

`tests/test_versions.py`:

```python
"""Tests for version numbers: reading, ordering, counting up."""

import pytest
import versions


def test_a_name_is_read_back():
    assert versions.parse("heizung", "heizung/v1.2.3") == (1, 2, 3)


def test_another_dashboards_version_is_not_ours():
    assert versions.parse("heizung", "solar/v1.2.3") is None


def test_a_hand_made_tag_is_not_a_version():
    assert versions.parse("heizung", "heizung/before-the-rework") is None
    assert versions.parse("heizung", "heizung/v1.2") is None
    assert versions.parse("heizung", "heizung/v1.2.3-beta") is None
    assert versions.parse("heizung", "heizung/v01.2.3") is None


def test_the_default_dashboard_key_works():
    # The default dashboard is stored under "_default"; an underscore is
    # legal in a ref name and must not be treated as a special case.
    assert versions.parse("_default", "_default/v0.0.1") == (0, 0, 1)


def test_ordering_is_numeric_not_alphabetical():
    # The classic: as text, "v1.10.0" sorts below "v1.9.0".
    names = ["heizung/v1.9.0", "heizung/v1.10.0", "heizung/v1.2.0"]
    assert versions.latest("heizung", names) == (1, 10, 0)


def test_unusable_names_do_not_shift_the_count():
    names = ["heizung/v1.0.0", "heizung/hand-made", "solar/v9.9.9"]
    assert versions.latest("heizung", names) == (1, 0, 0)


def test_a_dashboard_without_versions_has_no_latest():
    assert versions.latest("heizung", ["solar/v1.0.0"]) is None


def test_the_three_candidates():
    names = ["heizung/v1.2.3"]
    assert versions.candidates("heizung", names) == {
        "patch": "heizung/v1.2.4",
        "minor": "heizung/v1.3.0",
        "major": "heizung/v2.0.0",
        "current": "heizung/v1.2.3",
    }


def test_the_first_version_counts_from_zero():
    assert versions.candidates("heizung", []) == {
        "patch": "heizung/v0.0.1",
        "minor": "heizung/v0.1.0",
        "major": "heizung/v1.0.0",
        "current": None,
    }


def test_bumping_resets_what_is_below_it():
    assert versions.bump((1, 2, 3), "patch") == (1, 2, 4)
    assert versions.bump((1, 2, 3), "minor") == (1, 3, 0)
    assert versions.bump((1, 2, 3), "major") == (2, 0, 0)


def test_an_unknown_level_is_refused():
    with pytest.raises(ValueError):
        versions.bump((1, 2, 3), "enormous")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_versions.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'versions'`

- [ ] **Step 3: Write minimal implementation**

`custom_components/dashboard_history/versions.py`:

```python
"""Version numbers for the history: reading, ordering, counting up.

Home-Assistant-free on purpose. This is a small calculation that can be
wrong in a way nobody notices for months - `v1.10.0` sorting below
`v1.9.0` is the classic - so it lives where plain pytest reaches it,
rather than in the panel. Same rule as the wording in `analyze.py`.

A version is an annotated git tag named `<key>/v<major>.<minor>.<patch>`.
The dashboard key is part of the name because git tags share a single
namespace: without it, only one dashboard in the whole installation
could ever have a `v1.0.0`.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

# Deliberately strict: three plain numbers, no leading zeros, no suffix.
# Anything else is somebody's hand-made tag. Those stay visible, but they
# must never shift the numbering - a tag called `v2.0.0-beta` deciding
# that the next version is 2.0.1 would be a surprise nobody can undo.
_NUMBERS = re.compile(r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")

LEVELS = ("patch", "minor", "major")


def version_name(key: str, parts: tuple[int, int, int]) -> str:
    """The tag name one dashboard's version carries."""
    major, minor, patch = parts
    return f"{key}/v{major}.{minor}.{patch}"


def parse(key: str, name: str) -> tuple[int, int, int] | None:
    """The three numbers in a tag name, or None if it is not this one's."""
    prefix = f"{key}/"
    if not name.startswith(prefix):
        return None
    match = _NUMBERS.match(name[len(prefix) :])
    if match is None:
        return None
    major, minor, patch = match.groups()
    return (int(major), int(minor), int(patch))


def latest(key: str, names: Iterable[str]) -> tuple[int, int, int] | None:
    """The highest version of one dashboard, or None if it has none.

    Compared as numbers rather than as text. Tuples of ints order the way
    versions are meant to; the strings they came from do not.
    """
    found = [
        parsed for name in names if (parsed := parse(key, name)) is not None
    ]
    return max(found) if found else None


def bump(parts: tuple[int, int, int], level: str) -> tuple[int, int, int]:
    """The next version at one level. Everything below it resets to zero."""
    major, minor, patch = parts
    if level == "major":
        return (major + 1, 0, 0)
    if level == "minor":
        return (major, minor + 1, 0)
    if level == "patch":
        return (major, minor, patch + 1)
    raise ValueError(f"unknown level: {level}")


def candidates(key: str, names: Iterable[str]) -> dict[str, str | None]:
    """The three names the three buttons carry, and the current one.

    Counting always starts from the **highest existing** version, even
    after somebody has gone back to an older one. That keeps the numbers
    monotone, so a new version can never collide with one that is already
    there - and a collision would be a refusal in the middle of a dialog.

    Without a predecessor the count starts at 0.0.0, which puts `0.0.1`,
    `0.1.0` and `1.0.0` on the three buttons. Whoever wants a proper first
    release finds it one click away rather than having to reach for it.
    """
    current = latest(key, names)
    base = current or (0, 0, 0)
    found: dict[str, str | None] = {
        level: version_name(key, bump(base, level)) for level in LEVELS
    }
    found["current"] = version_name(key, current) if current else None
    return found
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_versions.py -v`
Expected: PASS, 11 Prüfungen

- [ ] **Step 5: Run the whole suite**

Run: `python3 -m pytest tests/ -v`
Expected: PASS — das neue Modul ändert an keinem bestehenden Test etwas.

- [ ] **Step 6: Commit**

```bash
git add custom_components/dashboard_history/versions.py tests/test_versions.py
git commit -m "$(cat <<'EOF'
Count version numbers where pytest can reach

The numbering is a small calculation that can be wrong for months
without anyone noticing - sorting v1.10.0 below v1.9.0 is the
classic. So it lives in a Home-Assistant-free module rather than in
the panel, by the same rule the wording in analyze.py follows.

Hand-made tags are skipped on purpose. A tag like v2.0.0-beta
deciding that the next version is 2.0.1 would be a surprise with no
way back.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `store.resolve()` löst Tag-Namen auf

Die Berichtigung aus Entscheidung 13. Ohne sie ist das Zurückwechseln nicht möglich, und die Spec behauptete bis heute das Gegenteil.

**Files:**
- Modify: `custom_components/dashboard_history/store.py` — Methode `_resolve`, aktuell ab `@staticmethod` unterhalb von `def resolve`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: nichts
- Produces: `HistoryStore.resolve(revision: str) -> str | None` nimmt ab hier zusätzlich einen Tag-Namen (`"heizung/v1.0.0"`) und einen Branch-Namen an. Aufgabe 4 und 6 bauen darauf.

- [ ] **Step 1: Write the failing test**

An `tests/test_store.py` anhängen, direkt unter `test_a_version_resolves_to_the_commit_it_marks`:

```python
def test_a_version_resolves_by_its_name(store):
    # The claim that a tag name works as a revision stood in the spec and
    # in the README and was never true: dulwich's Repo.__getitem__ does no
    # ref-name expansion, so `repo[b"v1.0.0"]` raises KeyError even when
    # the tag is right there. It went unnoticed because the only test
    # resolved the tag's *object id* instead of its name.
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.create_version("home/v1.0.0", "Title", "Text.", first)
    assert store.resolve("home/v1.0.0") == first


def test_a_version_name_reads_the_state_it_marks(store):
    # This is what makes going back to a version free: read_at takes the
    # name straight through, so restore_state needs no new code at all.
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.create_version("home/v1.0.0", "Title", "Text.", first)
    store.write_snapshot("home", "a: 2\n", "second")
    assert store.read_at("home", "home/v1.0.0") == "a: 1\n"


def test_an_unknown_name_still_resolves_to_nothing(store):
    store.write_snapshot("home", "a: 1\n", "first")
    assert store.resolve("home/v9.9.9") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_store.py -k version -v`
Expected: FAIL — `assert None == '<sha>'` bei `test_a_version_resolves_by_its_name`

- [ ] **Step 3: Write minimal implementation**

In `store.py` die Methode `_resolve` **vollständig** ersetzen:

```python
    @staticmethod
    def _resolve(repo: Repo, revision: str) -> str | None:
        name = revision.strip().encode()
        if not name:
            return None
        sha = None
        # git's own search order. dulwich expands none of it by itself:
        # `repo[b"v1.0.0"]` raises KeyError even when refs/tags/v1.0.0 is
        # right there, because Repo.__getitem__ does no ref-name
        # expansion. Measured on dulwich 1.2.14 (2026-09-02) - and the
        # belief that it did was what Entscheidung 10 rested on when it
        # kept the version services. A tag is only addressable from here.
        for candidate in (name, b"refs/tags/" + name, b"refs/heads/" + name):
            try:
                sha = repo[candidate].id
            except (KeyError, ValueError):
                continue
            break
        if sha is None and 4 <= len(name) < 40:
            # git itself refuses fewer than four characters; so do we.
            lowered = name.lower()
            if all(char in b"0123456789abcdef" for char in lowered):
                matches = list(repo.object_store.iter_prefix(lowered))
                # An ambiguous prefix is refused rather than guessed:
                # picking one of two commits would be worse than saying
                # it is not clear which was meant.
                if len(matches) == 1:
                    sha = matches[0]
        if sha is None:
            return None
        obj = repo[sha]
        while obj.type_name == b"tag":
            # An annotated tag points at the commit; that is what is wanted.
            obj = repo[obj.object[1]]
        return _as_text(obj.id)
```

Im Docstring von `resolve` (der öffentlichen Methode darüber) den letzten Absatz ersetzen:

```python
        Accepts what a person is actually likely to paste: a full hash, a
        ref such as HEAD, the name of a version, or an abbreviated hash of
        the kind `git log --oneline` prints. dulwich resolves neither the
        names nor the abbreviated forms by itself.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_store.py -v`
Expected: PASS — alle bisherigen Prüfungen ebenfalls, besonders `test_a_short_revision_below_four_characters_is_refused` und `test_an_ambiguous_prefix_is_refused`.

- [ ] **Step 5: Run the whole suite**

Run: `python3 -m pytest tests/ -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add custom_components/dashboard_history/store.py tests/test_store.py
git commit -m "$(cat <<'EOF'
Resolve tag names, as the design record claimed

Decision 10 kept the version services on the grounds that a tag is
addressable by its name. That was never true: dulwich does no
ref-name expansion in Repo.__getitem__, so repo[b"v1.0.0"] raises
KeyError even with refs/tags/v1.0.0 sitting right beside it. Nobody
noticed because the one test for it resolved the tag's object id
rather than its name.

This is what turns going back to a version into existing code:
restore_state takes the name as a revision, read_at passes it
straight through.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Versionen gehören einem Dashboard

**Files:**
- Modify: `custom_components/dashboard_history/store.py` — `_create_version`, `list_versions`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: nichts aus Aufgabe 1 oder 2
- Produces:
  - `HistoryStore.list_versions(key: str | None = None) -> list[Version]` — mit `key` nur die dieses Dashboards
  - `HistoryStore.create_version(...)` wirft `ValueError`, wenn der Name vergeben ist oder mit einem vorhandenen Tag kollidiert

- [ ] **Step 1: Write the failing test**

An `tests/test_store.py` anhängen:

```python
def test_versions_can_be_asked_for_one_dashboard(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    second = store.write_snapshot("solar", "b: 1\n", "solar first")
    store.create_version("home/v1.0.0", "Home", "", first)
    store.create_version("solar/v1.0.0", "Solar", "", second)
    assert [v.name for v in store.list_versions("home")] == ["home/v1.0.0"]
    assert [v.name for v in store.list_versions("solar")] == ["solar/v1.0.0"]
    assert len(store.list_versions()) == 2


def test_the_same_version_twice_is_refused(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.create_version("home/v1.0.0", "Home", "", first)
    with pytest.raises(ValueError, match="already exists"):
        store.create_version("home/v1.0.0", "Again", "", first)


def test_a_flat_tag_blocks_the_namespace_below_it(store):
    # git cannot hold a tag `home` and a tag `home/v1.0.0` at once - the
    # ref file and the ref directory are the same path. Measured: dulwich
    # raises IsADirectoryError and leaves a stray .lock behind, so this is
    # refused up front rather than suffered.
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.create_version("home", "Loose", "", first)
    with pytest.raises(ValueError, match="home"):
        store.create_version("home/v1.0.0", "Blocked", "", first)


def test_a_namespace_blocks_the_flat_tag_above_it(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.create_version("home/v1.0.0", "First", "", first)
    with pytest.raises(ValueError, match="home/v1.0.0"):
        store.create_version("home", "Loose", "", first)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_store.py -k "one_dashboard or refused or blocks" -v`
Expected: FAIL — `list_versions() takes 1 positional argument but 2 were given`, und die drei Kollisionsprüfungen mit `Failed: DID NOT RAISE`

- [ ] **Step 3: Write minimal implementation**

In `store.py` `_create_version` ersetzen:

```python
    def _create_version(
        self, name: str, title: str, description: str, revision: str | None
    ) -> None:
        self._refuse_colliding_name(name)
        body = f"{title}\n\n{description}".encode("utf-8")
        porcelain.tag_create(
            str(self.path),
            name.encode("utf-8"),
            message=body,
            author=_IDENTITY,
            annotated=True,
            objectish=revision.encode() if revision else b"HEAD",
        )

    def _refuse_colliding_name(self, name: str) -> None:
        """Refuse a version name git could not hold beside the others.

        A ref is a file, and a ref namespace is a directory of the same
        path - so `home` and `home/v1.0.0` cannot both exist. Measured on
        dulwich 1.2.14: the attempt raises IsADirectoryError *and* leaves
        a `.lock` file behind, which is a worse thing to hand a person
        than a sentence saying what is in the way.
        """
        repo = self._repo()
        if repo is None:
            return
        existing = {ref.decode() for ref in repo.refs.as_dict(b"refs/tags")}
        if name in existing:
            raise ValueError(f"version already exists: {name}")
        parent, _, _ = name.partition("/")
        if parent != name and parent in existing:
            raise ValueError(
                f"cannot create {name}: a version named {parent} is in the way"
            )
        below = sorted(one for one in existing if one.startswith(f"{name}/"))
        if below:
            raise ValueError(
                f"cannot create {name}: {below[0]} is in the way"
            )
```

Und `list_versions` ersetzen:

```python
    def list_versions(self, key: str | None = None) -> list[Version]:
        """Every named point, newest first. One dashboard's, or all of them.

        Ordered by the time the tag was made, which is the only order this
        class can know. A caller that wants them by version *number* sorts
        them itself - the numbering lives in `versions.py`, and this
        module stays free of it.
        """
        repo = self._repo()
        if repo is None:
            return []
        prefix = None if key is None else f"{key}/"
        found: list[tuple[int, Version]] = []
        for ref in repo.refs.as_dict(b"refs/tags"):
            name = ref.decode()
            if prefix is not None and not name.startswith(prefix):
                continue
            tag = repo[repo.refs[b"refs/tags/" + ref]]
            if not hasattr(tag, "object"):
                # A lightweight tag, made by hand. Not ours; skip it rather
                # than crash on the missing fields.
                continue
            message = (tag.message or b"").decode("utf-8")
            title, _, description = message.partition("\n\n")
            found.append(
                (
                    tag.tag_time,
                    Version(
                        name=name,
                        revision=_as_text(tag.object[1]),
                        title=title.strip(),
                        description=description.strip(),
                    ),
                )
            )
        # as_dict has no order of its own; the docstring promises one.
        return [version for _, version in sorted(found, key=lambda p: -p[0])]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_store.py -v`
Expected: PASS — auch `test_a_named_version_survives_the_rewrite`, das `create_version("v1", ...)` ohne Namensraum benutzt und weiterhin tragen muss.

- [ ] **Step 5: Run the whole suite**

Run: `python3 -m pytest tests/ -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add custom_components/dashboard_history/store.py tests/test_store.py
git commit -m "$(cat <<'EOF'
Give each dashboard its own version namespace

git tags share a single namespace. Without the dashboard key in the
name, only one dashboard in an installation could ever have a v1.0.0.

The collision check is not a precaution, it is measured: a flat tag
`home` cannot exist beside `home/v1.0.0`, because the ref file and
the ref directory are the same path. dulwich answers that with
IsADirectoryError and leaves a stray .lock behind - a sentence
naming what is in the way beats both.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Die Vorgänge in `operations.py`

Ab hier importieren die Module Home Assistant, `pytest` kommt also nicht mehr hin. Geprüft wird mit `run_checks.py` gegen die Wegwerf-Instanz — genau die Lücke, in der bisher **jeder** Fehler dieses Projekts lag.

**Files:**
- Modify: `custom_components/dashboard_history/operations.py`
- Test: `tests/integration/run_checks.py` (neue Funktion `run_versions`)

**Interfaces:**
- Consumes: `versions.LEVELS`, `versions.candidates`, `versions.parse` (Aufgabe 1); `store.list_versions(key)`, `store.create_version` mit `ValueError` (Aufgabe 3); `store.resolve` mit Namen (Aufgabe 2)
- Produces:
  - `async_next_versions(hass, store, key) -> {"candidates": {...}}`
  - `async_create_version(hass, store, key, level, title, description, revision) -> {"created": str|None, "error"?: str}`
  - `async_versions(hass, store, key=None) -> {"versions": [{name,title,description,revision}]}`
  - `async_history(...)` — jede Änderung trägt zusätzlich `"versions": [{"name","title","description"}]`

- [ ] **Step 1: Write the failing test**

In `tests/integration/run_checks.py` **vor** `def _drop_first_card` einfügen:

```python
async def run_versions(access: str) -> None:
    """Versions of one dashboard: counting up, marking, going back.

    The interesting part is that nothing here writes a commit. A version
    marks a state that is already recorded, so the history must be
    exactly as long afterwards as it was before.
    """
    async with Socket(access) as socket:
        key = TARGET
        changes = (await socket.call("dashboard_history/history", dashboard=key))[
            "changes"
        ]
        check("there is a state to mark", bool(changes), f"{len(changes)} changes")
        if not changes:
            return
        before = len(changes)
        revision = changes[0]["revision"]

        offered = await socket.call("dashboard_history/next_versions", dashboard=key)
        candidates = offered.get("candidates", {})
        check(
            "three candidates are offered, patch among them",
            set(candidates) == {"patch", "minor", "major", "current"},
            str(candidates),
        )

        made = await socket.call(
            "dashboard_history/create_version",
            dashboard=key,
            level="patch",
            title="Prüflauf äöüß",
            description="Von run_checks angelegt.",
            revision=revision,
        )
        created = made.get("created")
        check(
            "the patch candidate is what gets created",
            created == candidates.get("patch"),
            f"{created} vs {candidates.get('patch')}",
        )
        if not created:
            return

        listed = (await socket.call("dashboard_history/versions", dashboard=key))[
            "versions"
        ]
        mine = [v for v in listed if v["name"] == created]
        check("it comes back in the list", len(mine) == 1, str(listed))
        check(
            "with its title, umlauts intact",
            bool(mine) and mine[0]["title"] == "Prüflauf äöüß",
            str(mine[:1]),
        )
        check(
            "pointing at the state it was made from",
            bool(mine) and mine[0]["revision"] == revision,
            str(mine[:1]),
        )

        after = (await socket.call("dashboard_history/history", dashboard=key))[
            "changes"
        ]
        check(
            "marking wrote no commit - the history is the same length",
            len(after) == before,
            f"{before} -> {len(after)}",
        )
        check(
            "the marked change names its version",
            created in [v["name"] for v in after[0].get("versions", [])],
            str(after[0].get("versions")),
        )

        # The whole point of the namespace: the name is a revision.
        preview = await socket.call(
            "dashboard_history/restore_state", dashboard=key, revision=created
        )
        check(
            "a version name works as a revision",
            "unknown revision" not in preview.get("error", ""),
            str(preview.get("error", "no error"))[:120],
        )

        again = await socket.call("dashboard_history/next_versions", dashboard=key)
        check(
            "the next patch counts up from the one just made",
            again.get("candidates", {}).get("current") == created,
            str(again.get("candidates")),
        )

        bad = await socket.call(
            "dashboard_history/create_version",
            dashboard=key,
            level="enormous",
            title="Nowhere",
        )
        check(
            "an unknown level is refused, and says so",
            bad.get("created") is None and "unknown level" in bad.get("error", ""),
            str(bad),
        )

        # Without a revision the store would fall back to HEAD, and HEAD
        # is whichever dashboard was saved last - one repository holds
        # them all. Measured before this plan was written: it tags a
        # stranger's commit, and the version is then invisible in this
        # dashboard's history for good.
        loose = await socket.call(
            "dashboard_history/create_version",
            dashboard=key,
            level="minor",
            title="Ohne Revision",
        )
        placed = loose.get("created")
        check("a version without a revision is still created", bool(placed), str(loose))
        if placed:
            newest = (await socket.call("dashboard_history/versions", dashboard=key))[
                "versions"
            ]
            mark = next((v for v in newest if v["name"] == placed), None)
            history = (await socket.call("dashboard_history/history", dashboard=key))[
                "changes"
            ]
            check(
                "and it lands on this dashboard's own newest state, not on HEAD",
                bool(mark) and mark["revision"] == history[0]["revision"],
                f"{mark and mark['revision'][:10]} vs {history[0]['revision'][:10]}",
            )
```

Und im `__main__`-Block, nach dem Aufruf von `run_preview_explains`:

```python
    print("\n  -- Versionen je Dashboard --")
    asyncio.run(run_versions(access))
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose -f docker/compose.yaml up -d
python3 tests/integration/run_checks.py
```

Expected: FAIL bei »three candidates are offered« — der WebSocket-Befehl `next_versions` existiert noch nicht. (Er kommt in Aufgabe 5; diese Aufgabe legt nur die Vorgänge darunter. Die Prüfung bleibt bis dahin rot — das ist beabsichtigt und wird in Aufgabe 5 grün.)

- [ ] **Step 3: Write minimal implementation**

In `operations.py` den Import ergänzen:

```python
from . import versions as versioning
```

*(Unter `from .analyze import ...`. Der Aliasname verhindert eine Verwechslung mit den lokalen Variablen `versions`, die es in diesem Modul schon gibt.)*

`async_create_version` und `async_versions` **ersetzen** und `async_next_versions` daneben stellen:

```python
async def async_next_versions(
    hass: HomeAssistant, store: HistoryStore, key: str
) -> dict:
    """The three names the three buttons carry, and the current one.

    A read, so it needs no `confirm`. The panel must not work these out
    itself: the numbering is the one calculation here that can be quietly
    wrong, and it belongs where pytest reaches it.
    """
    found = await hass.async_add_executor_job(store.list_versions, key)
    return {"candidates": versioning.candidates(key, [v.name for v in found])}


async def async_create_version(
    hass: HomeAssistant,
    store: HistoryStore,
    key: str,
    level: str = "patch",
    title: str = "",
    description: str = "",
    revision: str | None = None,
) -> dict:
    """Mark a recorded state of one dashboard as a version.

    No `confirm`, for the same reason `describe` has none: this writes a
    tag, not a dashboard. Nothing anybody can see changes, and removing
    the tag would undo it.
    """
    if level not in versioning.LEVELS:
        return {"created": None, "error": f"unknown level: {level}"}
    if revision:
        resolved = await hass.async_add_executor_job(store.resolve, revision)
        if resolved is None:
            return {"created": None, "error": f"unknown revision: {revision}"}
        revision = resolved
    else:
        # Emphatically not HEAD, which is what the store would fall back
        # to. One repository holds every dashboard, so HEAD is whichever
        # dashboard was saved last. Measured: marking `heizung` without a
        # revision just after `solar` was saved tags solar's commit - and
        # the version then never shows up in heizung's history at all,
        # because list_changes walks only the paths that dashboard
        # touched. Wrong, invisible, and impossible to notice later.
        newest = await hass.async_add_executor_job(store.list_changes, key, 1)
        if not newest:
            return {"created": None, "error": f"no recorded state for {key}"}
        revision = newest[0].revision
    found = await hass.async_add_executor_job(store.list_versions, key)
    name = versioning.candidates(key, [v.name for v in found])[level]
    try:
        await hass.async_add_executor_job(
            store.create_version, name, title, description, revision
        )
    except ValueError as err:
        # A name git cannot hold beside the others. It is an answer, not a
        # crash: the message says what is in the way.
        return {"created": None, "error": str(err)}
    return {"created": name}


async def async_versions(
    hass: HomeAssistant, store: HistoryStore, key: str | None = None
) -> dict:
    """Every named point, newest first. One dashboard's, or all of them."""
    found = await hass.async_add_executor_job(store.list_versions, key)
    if key is not None:
        # By number, not by the time the tag was made. Those differ as
        # soon as somebody goes back and marks an older state: the newer
        # tag then carries the lower number, and ordering by time would
        # put it on top of one that contains it.
        found = sorted(
            found,
            key=lambda v: versioning.parse(key, v.name) or (-1, -1, -1),
            reverse=True,
        )
    return {
        "versions": [
            {
                "name": v.name,
                "revision": v.revision,
                "title": v.title,
                "description": v.description,
            }
            for v in found
        ]
    }
```

In `async_history` die Versionen mitliefern. Nach der Zeile mit `changes = await hass.async_add_executor_job(store.list_changes, key, limit)` einfügen:

```python
    # Which versions sit on which state. Gathered here rather than in the
    # panel: the panel would need a second call and a join, and a join is
    # logic. Two versions on one commit is allowed, so this is a list.
    marks: dict[str, list[dict]] = {}
    for version in await hass.async_add_executor_job(store.list_versions, key):
        marks.setdefault(version.revision, []).append(
            {
                "name": version.name,
                "title": version.title,
                "description": version.description,
            }
        )
```

und im Rückgabewert je Änderung ergänzen:

```python
                "same_as_now": c.revision in same,
                "versions": marks.get(c.revision, []),
```

Im Docstring von `async_history` einen Absatz anhängen:

```python
    Each entry also names the versions that sit on it, if any. The panel
    builds its sections from that, so it never has to join two calls
    together - a join in the panel is logic in the panel.
```

- [ ] **Step 4: Run the plain suite to be sure nothing below broke**

Run: `python3 -m pytest tests/ -v`
Expected: PASS (unverändert — `operations.py` wird davon nicht berührt)

- [ ] **Step 5: Commit**

```bash
git add custom_components/dashboard_history/operations.py tests/integration/run_checks.py
git commit -m "$(cat <<'EOF'
Tie the version operations to one dashboard

create_version takes a dashboard and a level instead of a free name,
and next_versions supplies the three buttons. The number is worked
out in the executor rather than in the panel: otherwise the one
calculation that can be quietly wrong would sit exactly where pytest
cannot reach it.

async_history now names the versions sitting on each change. That
saves the panel a second call and a join, and a join in the panel
would be logic in the panel.

Ordering is by number, not by tag time. Going back and marking an
older state produces a newer tag carrying a lower number, and
ordering by time would put it above one that contains it.

Without a revision, the newest state of that dashboard is marked -
never HEAD. One repository holds every dashboard, so HEAD is
whichever one was saved last. Measured: marking one dashboard right
after another was saved tags the stranger's commit, and the version
is then invisible in its own history for good.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Dienste und WebSocket-Befehle

**Files:**
- Modify: `custom_components/dashboard_history/services.py`
- Modify: `custom_components/dashboard_history/services.yaml`
- Modify: `custom_components/dashboard_history/websocket_api.py`
- Test: `tests/integration/run_checks.py` (die Prüfung aus Aufgabe 4 wird hier grün)

**Interfaces:**
- Consumes: `operations.async_next_versions`, `async_create_version`, `async_versions` (Aufgabe 4)
- Produces: WebSocket-Befehle `dashboard_history/next_versions`, `.../create_version`, `.../versions`; die gleichnamigen Dienste

- [ ] **Step 1: `services.py` ändern**

Die Funktionen `create_version` und `versions` ersetzen, `next_versions` daneben:

```python
    async def next_versions(call: ServiceCall) -> dict:
        return await operations.async_next_versions(
            hass, store, call.data["dashboard"]
        )

    async def create_version(call: ServiceCall) -> dict:
        return await operations.async_create_version(
            hass,
            store,
            call.data["dashboard"],
            call.data.get("level", "patch"),
            call.data["title"],
            call.data.get("description", ""),
            call.data.get("revision"),
        )

    async def versions(call: ServiceCall) -> dict:
        return await operations.async_versions(
            hass, store, call.data.get("dashboard")
        )
```

und in `registrations` die zwei alten Einträge durch drei ersetzen:

```python
        ("next_versions", next_versions, DASHBOARD),
        ("create_version", create_version, DASHBOARD.extend({
            vol.Optional("level", default="patch"): cv.string,
            vol.Required("title"): cv.string,
            vol.Optional("description", default=""): cv.string,
            vol.Optional("revision"): cv.string,
        })),
        ("versions", versions, vol.Schema({vol.Optional("dashboard"): cv.string})),
```

> **`level` bewusst als freier Text und nicht als `vol.In`.** Ein Schema-Fehler wird von Home Assistant abgefangen, bevor `operations` überhaupt läuft — die Antwort wäre dann ein Validierungsfehler statt `{"created": None, "error": "unknown level: …"}`. Dieselbe Trennung wie überall sonst in diesem Projekt: `restore_deleted` prüft die Position, `describe` die Revision, und beide antworten mit einem Satz statt mit einem Schema-Bruch. Die Auswahlliste in `services.yaml` bleibt trotzdem, denn sie ist Bedienhilfe und nicht Prüfung.

- [ ] **Step 2: `websocket_api.py` ändern**

Die zwei Einträge `versions` und `create_version` in `_COMMANDS` ersetzen:

```python
    _command(
        f"{DOMAIN}/versions",
        {vol.Optional("dashboard"): vol.Any(str, None)},
        operations.async_versions,
        lambda msg: {"key": msg.get("dashboard")},
    ),
    _command(
        f"{DOMAIN}/next_versions",
        {**_DASHBOARD},
        operations.async_next_versions,
        lambda msg: {"key": msg["dashboard"]},
    ),
    _command(
        f"{DOMAIN}/create_version",
        {
            **_DASHBOARD,
            # Free text, not vol.In - see the note under services.py. A
            # schema that refuses first means operations never gets to
            # answer, and the sentence it would have answered with is the
            # one the panel shows a person.
            vol.Optional("level", default="patch"): str,
            vol.Required("title"): str,
            vol.Optional("description", default=""): str,
            vol.Optional("revision"): vol.Any(str, None),
        },
        operations.async_create_version,
        lambda msg: {
            "key": msg["dashboard"],
            "level": msg["level"],
            "title": msg["title"],
            "description": msg["description"],
            "revision": msg.get("revision"),
        },
    ),
```

> **Achtung, sonst schlägt es lautlos fehl:** `operations.async_next_versions` und `async_create_version` erwarten den Dashboard-Schlüssel als `key`, nicht als `dashboard`. Die `args`-Lambda muss ihn umbenennen — genauso wie es die bestehenden Befehle tun.

- [ ] **Step 3: `services.yaml` ändern**

Den Block `create_version:` bis zum Dateiende ersetzen:

```yaml
next_versions:
  name: Next version numbers
  description: >-
    What the next patch, minor and major version of a dashboard would be
    called. Reads only; it creates nothing.
  fields:
    dashboard:
      required: true
      description: The dashboard, by its url_path.
      example: my-dashboard
      selector:
        text:

create_version:
  name: Create a version
  description: >-
    Mark a recorded state of one dashboard as a version. It groups the
    changes below it; it never squashes them. Nothing on the dashboard
    changes, so this needs no confirmation.
  fields:
    dashboard:
      required: true
      description: The dashboard, by its url_path.
      example: my-dashboard
      selector:
        text:
    level:
      description: >-
        How far to count up. The number itself is worked out from the
        highest version this dashboard already has.
      default: patch
      selector:
        select:
          options:
            - patch
            - minor
            - major
    title:
      required: true
      example: Kitchen rework
      selector:
        text:
    description:
      description: What this version is about.
      default: ""
      selector:
        text:
          multiline: true
    revision:
      description: >-
        Which recorded state to mark. Defaults to the most recent one.
      selector:
        text:

versions:
  name: Versions
  description: >-
    The named points in the history. Give a dashboard to see only its
    own, ordered by version number.
  fields:
    dashboard:
      description: The dashboard, by its url_path. Leave empty for all.
      example: my-dashboard
      selector:
        text:
```

- [ ] **Step 4: Run the integration checks**

```bash
docker compose -f docker/compose.yaml restart
python3 tests/integration/run_checks.py
```

Expected: PASS — alle Prüfungen unter »Versionen je Dashboard«, und **kein Rückschritt** in den sieben Abschnitten davor.

- [ ] **Step 5: Run the plain suite**

Run: `python3 -m pytest tests/ -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add custom_components/dashboard_history/services.py \
        custom_components/dashboard_history/services.yaml \
        custom_components/dashboard_history/websocket_api.py
git commit -m "$(cat <<'EOF'
Offer the version operations as service and command

create_version loses its free name and takes a dashboard and a level
instead. This breaks a documented interface, and the break is taken
deliberately: a second, equivalent path would be exactly what
decision 10 warns about.

`level` stays free text rather than vol.In. A schema error is caught
before operations ever runs, so the sentence naming the problem
would never be produced - and that sentence is what a person sees.
The same split the rest of this project uses: restore_deleted checks
the position, describe checks the revision, both answer in words.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Das Panel — Abschnitte, Anlegen, Zurückwechseln

**Files:**
- Modify: `custom_components/dashboard_history/panel.js`
- Test: `tests/integration/look_at_panel.py` (ansehen, nicht behaupten)

**Interfaces:**
- Consumes: WebSocket-Befehle aus Aufgabe 5; `change.versions` aus `async_history` (Aufgabe 4)
- Produces: nichts für spätere Aufgaben außer den CSS-Klassen `details.ver` und `.levels`, die Aufgabe 8 mitnimmt

- [ ] **Step 1: CSS ergänzen**

In `STYLE`, direkt vor der abschließenden Backtick-Zeile mit `pre .at`, einfügen:

```css
  details.ver { margin-bottom: 12px; }
  details.ver > summary {
    display: flex;
    align-items: baseline;
    gap: 12px;
    padding: 10px 16px;
    border-radius: 8px;
    background: var(--card-background-color, #fff);
    box-shadow: var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,.15));
    cursor: pointer;
  }
  details.ver > summary .name {
    font-family: monospace;
    font-weight: 500;
    color: var(--primary-color, #03a9f4);
  }
  details.ver > summary .grow { flex: 1 1 auto; }
  details.ver > summary .count {
    color: var(--secondary-text-color, #727272);
    font-size: 13px;
  }
  details.ver > .inner { padding: 12px 0 0 16px; }
  details.ver .also {
    display: block;
    margin-top: 2px;
    font-size: 12px;
    color: var(--secondary-text-color, #727272);
  }
  .levels { display: flex; gap: 8px; margin: 12px 0; }
  .levels button {
    flex: 1 1 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 10px;
    border: 1px solid var(--divider-color, #e0e0e0);
    border-radius: 4px;
    background: none;
    color: inherit;
    font: inherit;
    cursor: pointer;
  }
  .levels button[aria-pressed="true"] {
    border-color: var(--primary-color, #03a9f4);
    box-shadow: inset 0 0 0 1px var(--primary-color, #03a9f4);
  }
  .levels button strong { font-family: monospace; font-size: 15px; }
  .levels button span {
    color: var(--secondary-text-color, #727272);
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: .06em;
  }
```

- [ ] **Step 2: Den Anlege-Dialog ins Markup aufnehmen**

In `_render()`, nach dem `<dialog class="describe">`-Block, einfügen:

```html
      <dialog class="version">
        <h2>Create a version</h2>
        <div class="body" style="padding:0 16px 8px">
          <p class="muted" style="font-size:13px" data-scope></p>
          <div class="levels">
            <button type="button" data-level="patch" aria-pressed="true">
              <strong></strong><span>Patch</span>
            </button>
            <button type="button" data-level="minor" aria-pressed="false">
              <strong></strong><span>Minor</span>
            </button>
            <button type="button" data-level="major" aria-pressed="false">
              <strong></strong><span>Major</span>
            </button>
          </div>
          <input class="text title" type="text" maxlength="200"
                 placeholder="What is this version?">
          <input class="text desc" type="text" maxlength="500"
                 style="margin-top:8px"
                 placeholder="Anything more worth remembering (optional)">
        </div>
        <div class="actions">
          <button class="act ghost" value="cancel">Cancel</button>
          <button class="act" value="create">Create</button>
        </div>
      </dialog>
```

- [ ] **Step 3: Abschnitte bilden und ausgeben**

`_renderMain` ersetzen und die drei neuen Methoden daneben stellen:

```js
  /**
   * The history, cut into sections at the versions.
   *
   * A version marks a state, so it marks the *newest* change it contains
   * - the section it heads runs from that change downwards to the next
   * version below. Everything above the topmost version is not in a
   * version yet, and that is the section people work in.
   */
  _sections() {
    const out = [];
    let head = null;
    let rows = [];
    this._changes.forEach((change, index) => {
      const marks = change.versions || [];
      if (marks.length) {
        if (rows.length || head) out.push({ versions: head, rows });
        head = marks;
        rows = [index];
      } else {
        rows.push(index);
      }
    });
    if (rows.length || head) out.push({ versions: head, rows });
    return out;
  }

  /**
   * A section head. Two versions can sit on the same state; both are
   * named rather than one of them being silently dropped.
   *
   * The button disappears when its target is what the dashboard holds
   * already - the same rule the row buttons follow, and for the same
   * reason: offering it there opens a dialog reading "No difference."
   * above a live Apply button.
   */
  _renderVersionHead(section) {
    const [first, ...also] = section.versions;
    const count = section.rows.length;
    const extra = also
      .map((v) => `<span class="also">also ${escape(v.name)} — ${escape(v.title)}</span>`)
      .join("");
    const here = this._changes[section.rows[0]]?.same_as_now;
    const back = here
      ? '<span class="count">current state</span>'
      : `<button class="act ghost" data-state="${escape(first.name)}"
                 >Back to this version</button>`;
    return `
      <summary>
        <span class="name">${escape(first.name.split("/").pop())}</span>
        <span class="grow">${escape(first.title || first.name)}${extra}</span>
        <span class="count">${count} change${count === 1 ? "" : "s"}</span>
        ${back}
      </summary>`;
  }

  _renderMain() {
    if (!this._selected)
      return '<p class="empty muted">Pick a dashboard on the left.</p>';
    const dashboard = this._dashboards.find((d) => d.key === this._selected);
    const banner =
      dashboard && !dashboard.exists
        ? `<div class="banner">
             <span class="grow">This dashboard was deleted. Its history is
               still here, and so is everything that was on it.</span>
             ${
               this._changes.length > 1
                 ? `<button class="act" data-state="${escape(this._changes[1].revision)}">
                      Bring it back
                    </button>`
                 : ""
             }
             <button class="act ghost" data-forget="1">Forget for good</button>
           </div>`
        : "";
    if (!this._changes.length)
      return `${banner}<p class="empty muted">No changes recorded for this dashboard.</p>`;

    // Only the first section can be version-less: every later one starts
    // at the change a version sits on. So the unbundled case is handled
    // once, outside the loop, rather than guarded for on every section.
    const sections = this._sections();
    const newest = sections.find((s) => s.versions);
    const label = newest
      ? `Since ${newest.versions[0].name.split("/").pop()}`
      : "Not in a version yet";
    const parts = sections.map((section) => {
      if (!section.versions) return this._renderTopSection(section, label);
      const rows = section.rows
        .map((index) => this._renderRow(this._changes[index], index))
        .join("");
      return `<details class="ver">
                ${this._renderVersionHead(section)}
                <div class="inner">${rows}</div>
              </details>`;
    });
    return banner + parts.join("");
  }

  /**
   * The newest entry is set apart when it is provably the state in front
   * of you. Provably: after a change made at Home Assistant's back it is
   * not, and then nothing is crowned rather than the wrong thing.
   */
  _renderTopSection(section, label) {
    const rows = section.rows.map((index) =>
      this._renderRow(this._changes[index], index),
    );
    if (!this._changes[0].same_as_now)
      return `<div class="divider">${escape(label)}</div>${rows.join("")}`;
    // The crowned row sits above the divider, not under it - so when it
    // is the only row, the divider has nothing left to head and the
    // label would disappear with it. It moves into the heading instead:
    // "which version am I building on" is exactly what somebody looking
    // at a change that is not in one yet wants to know.
    const more = rows.length > 1;
    const rest = more
      ? `<div class="divider">${escape(label)}</div>${rows.slice(1).join("")}`
      : "";
    const heading = more ? "Current state" : `Current state · ${label}`;
    return `<div class="current">
              <p class="heading">${escape(heading)}</p>
              ${rows[0]}
            </div>${rest}`;
  }
```

- [ ] **Step 4: Den Knopf »Version bis hierher« in die aufgeklappte Zeile setzen**

In `_renderDetail` das abschließende `return` ersetzen:

```js
    return `<div class="detail">
      ${plain}
      ${list}
      ${this._renderSetBack(index)}
      <div class="backto">
        <button class="act ghost" data-version="${index}">Version up to here</button>
      </div>
    </div>`;
```

Und den Zweig darüber, der beim ersten aufgezeichneten Stand greift, ebenso:

```js
    if (!before)
      return `<div class="detail">${plain}<p class="muted">This is the first
        recorded state, so there is nothing before it to compare against.</p>
        <div class="backto">
          <button class="act ghost" data-version="${index}">Version up to here</button>
        </div></div>`;
```

- [ ] **Step 5: Den Anlege-Vorgang schreiben**

Neben `_describe` einfügen:

```js
  /**
   * Three buttons carrying the finished numbers, patch preselected.
   *
   * The number is never typed. A tag name has ref rules - no spaces, no
   * `..`, no `~^:?*[` - and passing those rules through to a dialog would
   * be carrying the storage into the interface. Choosing between patch,
   * minor and major carries a statement instead: was this a correction or
   * a rebuild?
   */
  async _createVersion(index) {
    const change = this._changes[index];
    // Fetched before the dialog is touched: _guard re-renders, and a
    // re-render replaces the dialog element along with everything else.
    const offered = await this._guard(() =>
      this._call("next_versions", { dashboard: this._selected }),
    );
    if (!offered) return;
    const candidates = offered.candidates || {};
    const dialog = this.shadowRoot.querySelector("dialog.version");
    dialog.querySelector("[data-scope]").textContent = candidates.current
      ? `Everything from ${candidates.current} up to and including this change.`
      : "Everything up to and including this change.";
    let level = "patch";
    const buttons = [...dialog.querySelectorAll(".levels button")];
    buttons.forEach((button) => {
      const which = button.dataset.level;
      button.querySelector("strong").textContent = (
        candidates[which] || ""
      ).split("/").pop();
      button.setAttribute("aria-pressed", String(which === level));
    });
    // One listener on the group rather than three on the buttons. Not
    // because they would pile up - _guard re-renders before this line, so
    // the dialog is a fresh element every time - but because relying on
    // that is relying on a re-render two calls away. This holds either way.
    dialog.querySelector(".levels").addEventListener("click", (event) => {
      const button = event.target.closest("button[data-level]");
      if (!button) return;
      level = button.dataset.level;
      buttons.forEach((other) =>
        other.setAttribute(
          "aria-pressed",
          String(other.dataset.level === level),
        ),
      );
    });
    const title = dialog.querySelector("input.title");
    const description = dialog.querySelector("input.desc");
    title.value = "";
    description.value = "";
    dialog.returnValue = "";
    dialog.showModal();
    title.focus();
    const answer = await new Promise((resolve) => {
      dialog.addEventListener("close", () => resolve(dialog.returnValue), {
        once: true,
      });
    });
    if (answer !== "create") return;
    const result = await this._guard(() =>
      this._call("create_version", {
        dashboard: this._selected,
        level,
        title: title.value.trim() || candidates[level].split("/").pop(),
        description: description.value.trim(),
        revision: change.revision,
      }),
    );
    if (result?.error) {
      this._error = result.error;
      this._render();
      return;
    }
    await this._select(this._selected);
  }
```

- [ ] **Step 6: Die Klicks verdrahten**

In `_render()`, hinter dem `[data-describe]`-Block, einfügen:

```js
    root.querySelectorAll("[data-version]").forEach((element) =>
      element.addEventListener("click", (event) => {
        // Otherwise the click reaches the row underneath and collapses it.
        event.stopPropagation();
        this._createVersion(Number(element.dataset.version));
      }),
    );
```

Und den `[data-state]`-Block anpassen, damit ein Klick im `<summary>` das `<details>` nicht auf- und zuklappt:

```js
    root.querySelectorAll("[data-state]").forEach((element) =>
      element.addEventListener("click", (event) => {
        // Inside a <summary> a click would toggle the section as well.
        event.preventDefault();
        event.stopPropagation();
        // The dialog is titled with the button that opened it. With two
        // of them on a row, a generic heading would leave you guessing
        // which one you pressed.
        this._restoreState(element.dataset.state, element.textContent.trim());
      }),
    );
```

- [ ] **Step 7: Ansehen, nicht behaupten**

```bash
docker compose -f docker/compose.yaml up -d
python3 tests/integration/run_checks.py       # legt eine Version an
python3 tests/integration/look_at_panel.py
```

Expected — und jede einzelne davon mit eigenen Augen prüfen:
1. `console:` meldet **»no errors, no warnings«**.
2. Der Verlauf zeigt oben »Since v0.0.1« (oder »Not in a version yet«).
3. Darunter ein zuklappbarer Abschnitt mit der Versionsnummer, dem Titel und der Zahl der Änderungen.
4. Eine Zeile aufklappen zeigt »Version up to here«.
5. Ein Klick darauf öffnet den Dialog mit **drei Nummern**, Patch hervorgehoben.
6. »Back to this version« im Abschnittskopf öffnet die **Vorschau**, nicht die Änderung selbst — und klappt den Abschnitt dabei nicht zu.

- [ ] **Step 8: Commit**

```bash
git add custom_components/dashboard_history/panel.js
git commit -m "$(cat <<'EOF'
Cut the history into sections at the versions

This delivers what the data model has promised from the first day:
the individual changes stay and are merely folded away. A second
view beside the history would be the relapse into exactly what
decision 10 warns about.

Instead of checkboxes, every expanded row carries a button. Gaps in
a selection are not awkward here, they are impossible: each commit
holds the complete state, so the state after change 3 carries the
effect of change 2 whether it was ticked or not.

The number is chosen, not typed. Passing ref-name rules through to a
dialog would be carrying the storage into the interface.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Die zwei Falschaussagen berichtigen

Beide behaupten dasselbe Unwahre über `resolve()` wie die Spec es tat. Sie stehen an Stellen, die ein fremder Mitwirkender zuerst liest.

**Files:**
- Modify: `README.md` — der Absatz ab »Two more exist for anyone who wants them«
- Modify: `CLAUDE.md` — die Aufzählung der Home-Assistant-freien Module

- [ ] **Step 1: `README.md` berichtigen**

Den Absatz ersetzen:

```markdown
Three more exist for anyone who wants them: `versions`, `next_versions`
and `create_version`. A version is an annotated git tag named after the
dashboard it belongs to — `my-dashboard/v1.2.0` — and it does one thing a
description cannot: it gives a recorded state a *name you can use as a
revision*. `restore_state` takes that name, which is what makes going
back to a version, and forward again, the same button.

They are in the panel as well, so reach for the services only if you want
to script them.
```

- [ ] **Step 2: `CLAUDE.md` berichtigen**

Die Zeile mit den Home-Assistant-freien Modulen ersetzen:

```markdown
- **`yaml_io.py`, `analyze.py`, `restore.py` und `versions.py` bleiben Home-Assistant-frei.** Kein `import homeassistant` darin — sie sind das Herz und müssen in reinem pytest prüfbar bleiben.
```

- [ ] **Step 3: Verify nothing else claims it**

```bash
grep -rn "as a revision\|name you can use" README.md docs/ CLAUDE.md
grep -rn "drei\|three" CLAUDE.md | grep -i "modul\|module"
```

Expected: Keine weitere Stelle behauptet die alte Fassung, und keine zählt die Module noch zu dritt.

- [ ] **Step 4: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "$(cat <<'EOF'
Correct what the docs said about tag names

The README claimed what the design record claimed, in the same
words: a tag is usable as a revision by its name. Since task 2 that
is true; until then it had stood there unverified.

And the list of Home-Assistant-free modules still counted three,
though versions.py has joined them as the fourth.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: `panel.js` teilen — einzeln verwerfbar

> **Diese Aufgabe fasst die Auslieferung an, nicht das Merkmal.** Wird sie verworfen, funktionieren die Versionen unverändert. Sie steht deshalb zuletzt.

**Warum sie heikel ist:** `panel.js` wird heute als **eine** statische Datei mit einem Fingerabdruck in der Query ausgeliefert. Ein `import` aus einer zweiten Datei bekäme diese Query nicht mit — und Home Assistant setzt auf statischen Pfaden kein `Cache-Control`, nur ETag und Last-Modified. Damit wäre der Cache-Fehler zurück, den `panel.py` ausdrücklich behoben hat, nur eine Ebene tiefer und noch schlechter zu finden. Beides muss deshalb zusammen geändert werden: der Fingerabdruck über **alle** Teile, und die Query an die Teile weitergereicht.

**Files:**
- Create: `custom_components/dashboard_history/panel/style.js`
- Create: `custom_components/dashboard_history/panel/render.js`
- Modify: `custom_components/dashboard_history/panel.js`
- Modify: `custom_components/dashboard_history/panel.py`

**Interfaces:**
- Consumes: `STYLE`, `escape`, `when`, `renderDiff`, `renderPlain` — heute alles oberhalb der Klasse in `panel.js`
- Produces: nichts für spätere Aufgaben

- [ ] **Step 1: Die Teile herausziehen**

Reines Verschieben. **Kein Zeichen des verschobenen Codes wird geändert**, nur `export` davorgesetzt — sonst vermischt sich ein Umbau mit einer Verlagerung, und ein Fehler wäre danach nicht mehr der einen oder der anderen zuzuordnen.

Die Grenzen sind mechanisch bestimmt, nicht über Zeilennummern (Aufgabe 6 hat sie verschoben):

1. **`panel/style.js`** bekommt die vollständige Deklaration `const STYLE = ` … `;` — von der Zeile, die mit `const STYLE =` beginnt und den öffnenden Backtick trägt, bis zur Zeile mit dem schließenden Backtick und Semikolon, einschließlich. Davor diese Kopfzeile, und aus `const` wird `export const`:

```js
/* The panel's stylesheet, kept apart so panel.js stays readable. */
```

2. **`panel/render.js`** bekommt **alles zwischen** dem `` `; `` der `STYLE`-Deklaration und der Zeile `class DashboardHistoryPanel extends HTMLElement {` — also die vier Deklarationen `escape`, `renderDiff`, `renderPlain` und `when` samt ihrer Kommentarblöcke, in dieser Reihenfolge. Jedem `const` wird ein `export` vorangestellt. Davor diese Kopfzeile:

```js
/*
 * Turning answers into markup. Pure functions: no element, no state, no
 * calls of their own. That is what makes them worth having apart - each
 * one can be read and reasoned about without the element around it.
 */
```

3. Beides wird in `panel.js` an seiner alten Stelle **gelöscht**.

**Danach prüfen, bevor irgendetwas anderes geschieht:**

```bash
node --check custom_components/dashboard_history/panel/style.js
node --check custom_components/dashboard_history/panel/render.js
grep -c "^export const" custom_components/dashboard_history/panel/render.js   # 4
grep -c "STYLE\|renderDiff\|renderPlain" custom_components/dashboard_history/panel/style.js
```

Expected: beide Dateien fehlerfrei, `render.js` enthält genau **4** Exporte.

- [ ] **Step 2: `panel.js` auf die Teile umstellen**

Die vier Definitionen und den `STYLE`-Block aus `panel.js` **entfernen** und oben, direkt unter `const DOMAIN = "dashboard_history";`, einsetzen:

```js
// The parts are fetched with this module's own query string, so a new
// release busts them together with the entry point. panel.py digests
// every file into that query for exactly this reason: a static import
// would carry no query at all, and Home Assistant sets no Cache-Control
// on a static path - only ETag and Last-Modified, which makes a stale
// part an intermittent failure rather than an obvious one.
const PARTS = new URL(import.meta.url).search;
const { STYLE } = await import(`./panel/style.js${PARTS}`);
const { escape, when, renderDiff, renderPlain } = await import(
  `./panel/render.js${PARTS}`
);
```

- [ ] **Step 3: `panel.py` beide Änderungen geben**

`_fingerprint` und `_async_serve_module` ersetzen, und die zwei Konstanten ergänzen:

```python
_MODULE_URL = f"/{DOMAIN}/panel.js"
_PARTS_URL = f"/{DOMAIN}/panel"
_SOURCE = Path(__file__).parent / "panel.js"
_PARTS = Path(__file__).parent / "panel"


def _fingerprint() -> str:
    """A short digest of every file the panel is built from.

    Every file, not only the entry point. The parts are fetched with the
    entry point's own query string, so digesting `panel.js` alone would
    serve a stale part whenever only a part changed - the same
    intermittent cache failure the hand-maintained version number caused,
    one level down and considerably harder to spot.

    The file name goes into the digest as well, so that renaming a part
    changes the fingerprint even when its contents do not.
    """
    digest = hashlib.sha256()
    for path in [_SOURCE, *sorted(_PARTS.glob("*.js"))]:
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


async def _async_serve_module(hass: HomeAssistant) -> None:
    """Make panel.js and its parts reachable, on whichever API this has."""
    paths = [(_MODULE_URL, str(_SOURCE)), (_PARTS_URL, str(_PARTS))]
    register_many = getattr(hass.http, "async_register_static_paths", None)
    if register_many is not None:
        from homeassistant.components.http import StaticPathConfig  # noqa: PLC0415

        await register_many(
            [StaticPathConfig(url, source, False) for url, source in paths]
        )
        return
    # Older releases only had the singular, synchronous form.
    for url, source in paths:
        hass.http.register_static_path(url, source, False)
```

- [ ] **Step 4: Verify the fingerprint actually covers a part**

```bash
python3 - <<'PY'
import sys, pathlib
sys.path.insert(0, "custom_components/dashboard_history")
part = pathlib.Path("custom_components/dashboard_history/panel/render.js")
import importlib.util
spec = importlib.util.spec_from_file_location(
    "panelmod", "custom_components/dashboard_history/panel.py"
)
# panel.py imports Home Assistant, so the digest is rebuilt here instead.
import hashlib
def digest():
    d = hashlib.sha256()
    files = [pathlib.Path("custom_components/dashboard_history/panel.js")]
    files += sorted(pathlib.Path("custom_components/dashboard_history/panel").glob("*.js"))
    for p in files:
        d.update(p.name.encode()); d.update(p.read_bytes())
    return d.hexdigest()[:12]
before = digest()
original = part.read_bytes()
part.write_bytes(original + b"\n/* touched */\n")
after = digest()
part.write_bytes(original)
print("vorher :", before)
print("nachher:", after)
print("Teil verändert den Fingerabdruck:", before != after)
assert before != after, "eine Änderung an einem Teil bustet den Cache NICHT"
print("und die Datei ist unverändert zurück:", part.read_bytes() == original)
PY
```

Expected: `Teil verändert den Fingerabdruck: True`

- [ ] **Step 5: Ansehen — hier entscheidet sich alles**

```bash
docker compose -f docker/compose.yaml restart
python3 tests/integration/run_checks.py
python3 tests/integration/look_at_panel.py
```

Expected:
1. `console:` meldet **»no errors, no warnings«**. Ein gescheiterter dynamischer Import erschiene genau hier — und sonst nirgends.
2. Das Panel sieht aus wie vor der Teilung: Seitenleiste, Verlauf, Abschnitte, Dialoge.
3. Alle sechs Punkte aus Aufgabe 6, Schritt 7 gelten unverändert.

**Schlägt einer davon fehl:** Diese Aufgabe zurücknehmen (`git checkout -- custom_components/dashboard_history/`), das Merkmal bleibt vollständig.

- [ ] **Step 6: Run the plain suite**

Run: `python3 -m pytest tests/ -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add custom_components/dashboard_history/panel.js \
        custom_components/dashboard_history/panel.py \
        custom_components/dashboard_history/panel/
git commit -m "$(cat <<'EOF'
Split the panel without the cache bug returning

panel.js had grown past 1200 lines. The design record asks the panel
to be free of logic, not to be short - but a file nobody can hold in
view is where logic moves in unnoticed.

Both changes had to come together. A plain import carries no query
string, and Home Assistant sets no Cache-Control on a static path,
only ETag and Last-Modified. A stale part would have been the same
intermittent failure the fingerprint once fixed, one level down and
harder to find. So the parts are fetched with the entry point's own
query string, and the fingerprint covers every file rather than
panel.js alone.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Wenn alles steht

```bash
python3 -m pytest tests/ -v
python3 tests/integration/run_checks.py
python3 tests/integration/look_at_panel.py
```

Alle drei grün, und das Panel mit eigenen Augen gesehen. Erst dann ist Vorhaben A fertig.

**Nicht in diesem Plan** — sie haben ihre eigene Spec, siehe »Reihenfolge der Vorhaben« in der Spec:

- **B — Beobachten:** Options-Flow und die erste Entity-Plattform (Repository-Größe, Zahl der Stände, Zahl der Dashboards, Zeitpunkt der neuesten Erfassung).
- **C — Aufräumen:** Verlustfreies Verdichten, danach — nur falls die Messwerte aus B es rechtfertigen — eine Aufbewahrungsregel.

**Auch nicht in diesem Plan, bewusst:** Versionen löschen oder umbenennen, zwei Versionen vergleichen, Versionen über mehrere Dashboards hinweg. Alles später nachrüstbar, nichts davon nötig für das, was Entscheidung 13 beschreibt.
