# Eigene Texte und Klartext — Umsetzungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Jede Änderung im Verlauf bekommt eine selbst geschriebene Beschreibung, und jeder Diff eine benannte Klartext-Zusammenfassung darüber.

**Architecture:** Die Beschreibung liegt als git note auf `refs/notes/commits` — der Commit bleibt unangetastet, jede Revision bleibt zitierbar. Die Erklärung entsteht in `analyze.py` aus der bestehenden Zuordnung (`_match_cards`, `_describe`), zwei Zeitformen über einem Motor. Panel und Dienste bleiben dünne Häute über `operations.py`.

**Tech Stack:** Python 3.12 (Entwicklung) / 3.14 (Container), `dulwich==1.2.14`, pytest, Home Assistant 2026.8.3, `panel.js` als reines Custom Element ohne Bauschritt.

**Spec:** `docs/superpowers/specs/2026-08-30-dashboard-history-design.md` — Entscheidung 10 und 11, sowie die Grenze in Entscheidung 7.

## Global Constraints

Aus der Spec, wörtlich, und für **jede** Aufgabe gültig:

- **Kein Systemaufruf von `git`.** Ausschließlich `dulwich`.
- **Keine Home-Assistant-Interna abfangen oder ersetzen.** Kein Monkey-Patching.
- **Nichts blockiert den Start von Home Assistant.** Fehler beim Erfassen werden protokolliert und verschluckt.
- **`yaml_io.py`, `analyze.py`, `restore.py` und `keys.py` bleiben Home-Assistant-frei.** Kein `import homeassistant` darin, und **kein Import eines anderen Projektmoduls** — die Tests laden sie flach, ein `import analyze` scheitert als Paket in HA.
- **Blockierende Arbeit gehört in einen Executor** (`hass.async_add_executor_job`). Jeder `store`-Aufruf aus `operations.py` geht durch einen.
- **Nichts wird ohne Vorschau geschrieben** — für alles, was einen Dashboard-Stand schreibt. Die Beschreibung ist davon ausgenommen (Entscheidung 7, Grenze vom 2026-08-31): kein `confirm`.
- **Code, Kommentare, Docstrings, Dienstnamen, Log-Meldungen, Panel-Text und README: Englisch.** Commit-Botschaften: Deutsch, Betreff im Imperativ, max. 50 Zeichen, Leerzeile, Body max. 72 Zeichen, Abschluss mit `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- **Tests:** `python3 -m pytest tests/ -v` muss durchgehend grün bleiben (Stand vor Beginn: 106 Tests).
- **Kein Push.** Committen ja, auf GitHub schieben nur nach ausdrücklicher Ansage des Nutzers.

## Geprüfte Grundlagen

Nicht vermutet, am 2026-08-31 an dulwich 1.2.14 gemessen:

| Aufruf | Verhalten |
|---|---|
| `notes_add(pfad, sha, text, author=, committer=)` | legt an und überschreibt idempotent; `sha` darf `bytes` **oder** `str` sein |
| `notes_show(pfad, sha)` | `None` bei einem Commit ohne Notiz — kein Fehler |
| `notes_remove(pfad, sha, ...)` | `None` bei einem Commit ohne Notiz — **wirft nicht** |
| `notes_add`/`notes_show` mit unbekanntem sha | `KeyError` — deshalb **immer** vorher `resolve()` |
| `notes_list(pfad)` | `list[tuple[sha_bytes, text_bytes]]`, alle Notizen in einem Durchgang |
| Notiz-Commits | liegen auf `refs/notes/commits`, **nicht** in der Historie: nach zwei Notiz-Operationen führte der Walker weiterhin genau zwei Commits |
| UTF-8 | »äöüß« unverfälscht zurück |

## Dateien und Verantwortung

| Datei | Verantwortung nach dieser Fassung |
|---|---|
| `custom_components/dashboard_history/analyze.py` | Einordnung **und ihr Wortlaut**. Bekommt `explain_change`, `explain_effect`, drei Dataclasses und die Wortlisten. Bleibt ein Modul: `explain` braucht `_match_cards`, `_describe`, `_views_by_key`, `card_containers` — alle privat, und ein zweites HA-freies Modul dürfte sie nicht importieren |
| `custom_components/dashboard_history/store.py` | Ablage. Bekommt `set_description`, `descriptions`, `previous_change`; `Change` bekommt das Feld `description` |
| `custom_components/dashboard_history/operations.py` | Vorgänge. Bekommt `async_describe`, `async_explain`; beide `restore_*` liefern `explanation` mit |
| `custom_components/dashboard_history/websocket_api.py` | zwei Befehle mehr: `describe`, `explain` |
| `custom_components/dashboard_history/services.py`, `services.yaml` | dieselben zwei als Dienste; `create_version`/`versions` bleiben unverändert |
| `custom_components/dashboard_history/panel.js` | Stift und Beschreibungsdialog; Erklärung über dem Diff, Diff in einem `<details>` |
| `tests/test_analyze.py`, `tests/test_store.py` | die neuen Tests |
| `tests/integration/run_checks.py` | drei Prüfungen an echtem Home Assistant |
| `README.md` | Beschreibung erklären, Versionen nach hinten |

---

### Task 1: Die Klartext-Erklärung in `analyze.py`

Der Kern. Reines pytest, ohne laufendes Home Assistant.

**Files:**
- Modify: `custom_components/dashboard_history/analyze.py` (Dataclasses hinter `Summary` ~Zeile 41, Funktionen hinter `summarize` ~Zeile 309)
- Test: `tests/test_analyze.py`

**Interfaces:**
- Consumes: `card_containers`, `_views_by_key`, `_match_cards`, `_describe` — alle schon vorhanden
- Produces:
  ```python
  @dataclass(frozen=True)
  class Entry:
      kind: str    # "removed" | "added" | "edited" | "moved"
      what: str    # "card" | "view"
      label: str
      text: str

  @dataclass(frozen=True)
  class ViewChanges:
      view: str
      entries: list[Entry]
      more: int = 0

  @dataclass(frozen=True)
  class Explanation:
      groups: list[ViewChanges]
      note: str = ""

  def explain_change(old: dict, new: dict) -> Explanation   # Vergangenheit
  def explain_effect(current: dict, target: dict) -> Explanation  # Zukunft
  ```

- [ ] **Step 1: Die fehlschlagenden Tests schreiben**

An `tests/test_analyze.py` anhängen:

```python
# -- the plain-language explanation ------------------------------------
#
# The wording lives in analyze.py rather than in the panel on purpose.
# Three times in this project the code was righter than its own report:
# the false alarm "changed outside Home Assistant", the misleading "does
# not exist at", and the caveat that was silently dropped when a
# dashboard was recreated. Wording that can go wrong belongs where
# pytest can reach it.


def test_a_deleted_card_is_explained_by_name():
    result = analyze.explain_change(_config([A, B]), _config([A]))
    assert [group.view for group in result.groups] == ["Home"]
    assert [entry.text for entry in result.groups[0].entries] == [
        "tile: light.b was deleted"
    ]


def test_the_same_deletion_reads_as_a_warning_in_future_tense():
    result = analyze.explain_effect(_config([A, B]), _config([A]))
    assert result.groups[0].entries[0].text == "tile: light.b will be deleted"
    # Nothing to reassure about: something IS deleted here.
    assert result.note == ""


def test_a_restore_says_plainly_that_nothing_is_lost():
    result = analyze.explain_effect(_config([A]), _config([A, B]))
    assert result.groups[0].entries[0].text == "tile: light.b comes back"
    assert result.note == "Nothing on this dashboard is deleted."


def test_an_edited_card_is_one_event_not_two():
    edited = dict(B, name="Kitchen light")
    result = analyze.explain_change(_config([A, B]), _config([A, edited]))
    assert [entry.kind for entry in result.groups[0].entries] == ["edited"]
    assert result.groups[0].entries[0].text == "tile: Kitchen light was changed"


def test_a_swap_is_explained_as_two_moves():
    result = analyze.explain_change(_config([A, B]), _config([B, A]))
    assert sorted(entry.kind for entry in result.groups[0].entries) == [
        "moved",
        "moved",
    ]


def test_a_deletion_alone_moves_nothing():
    # The same rule _moved already follows: rank among the survivors, not
    # raw position. Otherwise every card behind a deletion is noise.
    result = analyze.explain_change(_config([A, B, C]), _config([A, C]))
    assert [entry.kind for entry in result.groups[0].entries] == ["removed"]


def test_a_whole_deleted_view_is_one_line_and_not_hundreds():
    old = {"views": [{"path": "home", "title": "Home", "cards": [A, B, C]}]}
    result = analyze.explain_change(old, {"views": []})
    assert [entry.text for entry in result.groups[0].entries] == [
        'the whole view "Home" was deleted'
    ]


def test_a_recreated_dashboard_is_one_line_per_view():
    # The heaviest case: a dashboard restored from nothing. Listing every
    # card would be hundreds of lines - on the installation this was built
    # against, 661 of them.
    target = {
        "views": [
            {"path": "home", "title": "Home", "cards": [A, B]},
            {"path": "up", "title": "Upstairs", "cards": [C]},
        ]
    }
    result = analyze.explain_effect({}, target)
    assert [group.view for group in result.groups] == ["Home", "Upstairs"]
    assert [len(group.entries) for group in result.groups] == [1, 1]
    assert result.note == "Nothing on this dashboard is deleted."


def test_a_long_list_is_capped_and_says_how_much_it_hides():
    cards = [{"type": "tile", "entity": f"light.n{index}"} for index in range(20)]
    result = analyze.explain_effect(_config([]), _config(cards))
    assert len(result.groups[0].entries) == 12
    assert result.groups[0].more == 8


def test_an_unnameable_change_never_claims_that_nothing_changed():
    # A renamed view: the cards match exactly, so there is nothing to
    # name. The summary sits directly above a diff that plainly shows the
    # difference - claiming "nothing changed" there would be refuted at a
    # glance, which is worse than having no summary at all.
    old = {"views": [{"path": "home", "title": "Home", "cards": [A]}]}
    new = {"views": [{"path": "home", "title": "Warm", "cards": [A]}]}
    result = analyze.explain_change(old, new)
    assert result.groups == []
    assert "see the details" in result.note


def test_two_views_are_two_groups():
    old = {
        "views": [
            {"path": "home", "title": "Home", "cards": [A, B]},
            {"path": "up", "title": "Upstairs", "cards": [C]},
        ]
    }
    new = {
        "views": [
            {"path": "home", "title": "Home", "cards": [A]},
            {"path": "up", "title": "Upstairs", "cards": []},
        ]
    }
    result = analyze.explain_change(old, new)
    assert [group.view for group in result.groups] == ["Home", "Upstairs"]
    assert [len(group.entries) for group in result.groups] == [1, 1]


def test_a_view_without_a_title_is_named_by_its_path():
    old = {"views": [{"path": "garage", "cards": [A, B]}]}
    new = {"views": [{"path": "garage", "cards": [A]}]}
    result = analyze.explain_change(old, new)
    assert result.groups[0].view == "garage"


def test_a_card_in_a_section_is_explained_too():
    # The sections layout, which is what Home Assistant creates by default
    # for a new dashboard now.
    old = {
        "views": [
            {"path": "home", "title": "Home", "sections": [{"cards": [A, B]}]}
        ]
    }
    new = {"views": [{"path": "home", "title": "Home", "sections": [{"cards": [A]}]}]}
    result = analyze.explain_change(old, new)
    assert [entry.text for entry in result.groups[0].entries] == [
        "tile: light.b was deleted"
    ]


def _without_first_card(config):
    """The same configuration with the first card of each view removed."""
    import copy

    shrunk = copy.deepcopy(config)
    for view in shrunk.get("views") or []:
        for _, cards in analyze.card_containers(view):
            if cards:
                del cards[0]
                break
    return shrunk


def test_every_real_card_can_be_named():
    # The formulations have to hang on real cards, not on the four
    # invented ones above - none of which has a nested container, a
    # missing title or an entity list. Comparing a real configuration
    # against itself minus one card per view is what forces the wording
    # through the card path; explain_effect({}, config) would not, because
    # it folds each view into a single line.
    if not REAL_DASHBOARDS:
        return
    named = 0
    for path in REAL_DASHBOARDS:
        config = json.loads(path.read_text(encoding="utf-8"))["data"]["config"]
        if not (config.get("views") or []):
            continue
        result = analyze.explain_change(config, _without_first_card(config))
        for group in result.groups:
            assert group.view.strip(), f"a view without a name in {path.name}"
            for entry in group.entries:
                assert entry.text.strip(), f"an empty sentence in {path.name}"
                assert entry.kind in ("removed", "added", "edited", "moved")
                assert entry.what in ("card", "view")
                # The label is what makes this worth reading at all. An
                # empty one would produce " was deleted" and tell nobody
                # which card is gone.
                assert entry.label.strip(), f"an unnamed card in {path.name}"
                named += 1
    assert named, "the real dashboards produced no explanation at all"


def test_a_real_dashboard_restored_from_nothing_stays_readable():
    # The heaviest case on real data: 661 cards on this installation, and
    # the summary still has to fit on a screen.
    if not REAL_DASHBOARDS:
        return
    for path in REAL_DASHBOARDS:
        config = json.loads(path.read_text(encoding="utf-8"))["data"]["config"]
        result = analyze.explain_effect({}, config)
        for group in result.groups:
            assert len(group.entries) <= 12
        assert result.note == "Nothing on this dashboard is deleted." or not result.groups
```

Und der Kopf von `tests/test_analyze.py` bekommt dafür den Zugriff auf die echten Dashboards — dasselbe Muster wie `tests/test_yaml_io.py`:

```python
import json
import os
import pathlib

import analyze

# Point DASHBOARD_HISTORY_REAL_STORAGE at any Home Assistant .storage
# directory to run the real-data checks against your own dashboards.
_STORAGE = pathlib.Path(
    os.environ.get(
        "DASHBOARD_HISTORY_REAL_STORAGE",
        "/path/to/home-assistant/.storage",
    )
)
REAL_DASHBOARDS = sorted(_STORAGE.glob("lovelace.*")) if _STORAGE.is_dir() else []
```

- [ ] **Step 2: Laufen lassen und das Scheitern bestätigen**

Run: `python3 -m pytest tests/test_analyze.py -v -k "explain or real_"`
Expected: FAIL — `AttributeError: module 'analyze' has no attribute 'explain_change'`

- [ ] **Step 3: Die Umsetzung schreiben**

Hinter `Summary` in `custom_components/dashboard_history/analyze.py`:

```python
@dataclass(frozen=True)
class Entry:
    """One nameable thing that changed."""

    kind: str  # "removed", "added", "edited" or "moved"
    what: str  # "card" or "view"
    label: str
    text: str  # the finished sentence, ready to show


@dataclass(frozen=True)
class ViewChanges:
    """What changed in one view. `more` is what the cap left out."""

    view: str
    entries: list[Entry]
    more: int = 0


@dataclass(frozen=True)
class Explanation:
    """A diff in words. `note` carries what the groups cannot say."""

    groups: list[ViewChanges]
    note: str = ""
```

Und hinter `summarize`:

```python
# Card labels already carry their type ("tile: light.b"), so they need no
# quotes. A view label is a bare name and does.
_PAST = {
    ("card", "removed"): "{label} was deleted",
    ("card", "added"): "{label} was added",
    ("card", "edited"): "{label} was changed",
    ("card", "moved"): "{label} was moved",
    ("view", "removed"): 'the whole view "{label}" was deleted',
    ("view", "added"): 'the whole view "{label}" was added',
}

_FUTURE = {
    ("card", "removed"): "{label} will be deleted",
    ("card", "added"): "{label} comes back",
    ("card", "edited"): "{label} goes back to how it was",
    ("card", "moved"): "{label} moves back to where it was",
    ("view", "removed"): 'the whole view "{label}" will be deleted',
    ("view", "added"): 'the whole view "{label}" comes back',
}

# A dashboard restored from nothing would otherwise list every card it
# ever had - 661 of them on the installation this was built against.
_ENTRY_LIMIT = 12

_NOTHING_LOST = "Nothing on this dashboard is deleted."
_NOT_IN_CARDS = (
    "This change cannot be described in terms of cards - see the details below."
)


def _view_name(view: dict, key) -> str:
    """What to call a view: its title, else its path, else its position."""
    return str(view.get("title") or view.get("path") or key)


def _entry(words: dict, kind: str, what: str, label: str) -> Entry:
    return Entry(
        kind=kind,
        what=what,
        label=label,
        text=words[(what, kind)].format(label=label),
    )


def _capped(name: str, entries: list[Entry]) -> ViewChanges:
    """Keep the list readable, and say how much it hides.

    Silently truncating would be the one thing this project must not do:
    a summary that omits without saying so is worse than a long one.
    """
    if len(entries) <= _ENTRY_LIMIT:
        return ViewChanges(view=name, entries=entries)
    return ViewChanges(
        view=name,
        entries=entries[:_ENTRY_LIMIT],
        more=len(entries) - _ENTRY_LIMIT,
    )


def _card_entries(words: dict, old_view: dict, new_view: dict) -> list[Entry]:
    """Every nameable card change between two states of one view."""
    old_containers = dict(card_containers(old_view))
    new_containers = dict(card_containers(new_view))
    entries: list[Entry] = []

    for location, old_cards in old_containers.items():
        new_cards = new_containers.get(location, [])
        removed, added, edited, moved = _match_cards(old_cards, new_cards)
        entries += [
            _entry(words, "removed", "card", _describe(old_cards[index]))
            for index in removed
        ]
        entries += [
            _entry(words, "added", "card", _describe(new_cards[index]))
            for index in added
        ]
        entries += [
            _entry(words, "edited", "card", _describe(new_cards[index]))
            for _, index in edited
        ]
        entries += [
            _entry(words, "moved", "card", _describe(old_cards[index]))
            for index, _ in moved
        ]

    # A container that only the new state has - a section added to a view.
    # Its cards are new, and reporting the cards they were moved out of as
    # a bare deletion would be a half-truth.
    for location, new_cards in new_containers.items():
        if location not in old_containers:
            entries += [
                _entry(words, "added", "card", _describe(card)) for card in new_cards
            ]
    return entries


def _explain(old: dict, new: dict, words: dict, reassure: bool) -> Explanation:
    """The engine behind both tenses.

    `reassure` says whether a "nothing is lost" line is wanted when
    nothing is removed. It is passed rather than inferred from `words`:
    identity of a wording table is not the question being asked.
    """
    new_views = dict(_views_by_key(new))
    old_keys = {key for key, _ in _views_by_key(old)}
    groups: list[ViewChanges] = []
    removed_anything = False

    for key, old_view in _views_by_key(old):
        new_view = new_views.get(key)
        name = _view_name(old_view, key)
        if new_view is None:
            # One line for the view, not one per card on it.
            groups.append(
                ViewChanges(name, [_entry(words, "removed", "view", name)])
            )
            removed_anything = True
            continue
        entries = _card_entries(words, old_view, new_view)
        if entries:
            groups.append(_capped(name, entries))
            removed_anything = removed_anything or any(
                entry.kind == "removed" for entry in entries
            )

    for key, new_view in _views_by_key(new):
        if key not in old_keys:
            name = _view_name(new_view, key)
            groups.append(ViewChanges(name, [_entry(words, "added", "view", name)]))

    if not groups:
        # Something changed - the caller only asks when it did - but not
        # anything this can name. Saying "nothing changed" above a diff
        # that shows the difference would be refuted at a glance.
        return Explanation(groups=[], note=_NOT_IN_CARDS)
    if removed_anything or not reassure:
        return Explanation(groups=groups)
    return Explanation(groups=groups, note=_NOTHING_LOST)


def explain_change(old: dict, new: dict) -> Explanation:
    """What one recorded change did, in words. Past tense."""
    return _explain(old, new, _PAST, reassure=False)


def explain_effect(current: dict, target: dict) -> Explanation:
    """What applying a restore would do, in words. Future tense.

    The reassurance matters here and not in the past tense: before
    pressing Apply, the question is not what changed but what is at risk.
    """
    return _explain(current, target, _FUTURE, reassure=True)
```

- [ ] **Step 4: Laufen lassen und Grünwerden bestätigen**

Run: `python3 -m pytest tests/test_analyze.py -v`
Expected: PASS, alle bestehenden Tests eingeschlossen

Dann der ganze Satz: `python3 -m pytest tests/ -v` — 106 vorherige plus 15 neue.

- [ ] **Step 5: Committen**

```bash
git add custom_components/dashboard_history/analyze.py tests/test_analyze.py
```

Botschaft:

```
Erklaere den Diff in Worten, die pytest pruefen kann

Ein Unified-Diff über YAML ist für die meisten Menschen keine Antwort
auf »was passiert mit meinem Dashboard«. Er bleibt als genaue
Auskunft, bekommt aber eine benannte Zusammenfassung darüber.

Der Wortlaut entsteht in analyze.py und nicht im Panel, weil dreimal
in diesem Projekt der Code richtiger war als sein eigener Bericht.
Formulierungen, die schiefgehen können, gehören dorthin, wo Tests
hinkommen — auch an 1526 echte Karten und nicht nur an vier erfundene.

Zwei Stellen sind bewusst unbequem gelöst. Findet die Erklärung
nichts zu benennen, behauptet sie nicht »nichts geändert«, sondern
verweist auf den Diff darunter: eine Zusammenfassung, die man beim
Hinsehen widerlegt, ist schlimmer als keine. Und lange Listen werden
gekappt, sagen aber wie viel — ein wiederhergestelltes Dashboard
hätte sonst 661 Zeilen.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

---

### Task 2: `summarize` sieht einen neuen Abschnitt

Eine eigene Aufgabe, weil sie den Wortlaut bestehender Commit-Botschaften ändert — ein Prüfer kann sie ablehnen und Task 1 trotzdem annehmen.

**Files:**
- Modify: `custom_components/dashboard_history/analyze.py` (`summarize`, ~Zeile 283-309)
- Test: `tests/test_analyze.py`

**Interfaces:**
- Consumes: `card_containers` aus Task 1 unverändert
- Produces: `summarize` zählt Karten in Containern, die nur der neue Stand hat

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

```python
def test_a_card_moved_into_a_new_section_is_not_only_a_deletion():
    # summarize walked the old state's containers and looked each up in
    # the new one. A section added in the new state was therefore never
    # visited, and its cards never counted: moving a card into a new
    # section read as a bare deletion. Half a truth in the one line
    # people scan when looking for something they lost.
    old = {"views": [{"path": "home", "title": "Home", "cards": [A, B]}]}
    new = {
        "views": [
            {"path": "home", "title": "Home", "cards": [A], "sections": [{"cards": [B]}]}
        ]
    }
    counts = analyze.summarize(old, new)
    assert (counts.removed, counts.added) == (1, 1)
```

- [ ] **Step 2: Laufen lassen und das Scheitern bestätigen**

Run: `python3 -m pytest tests/test_analyze.py -v -k new_section`
Expected: FAIL — `assert (1, 0) == (1, 1)`

- [ ] **Step 3: Die Umsetzung schreiben**

In `summarize`, in der Schleife über die Views, hinter der bestehenden Container-Schleife:

```python
        new_containers = dict(card_containers(new_view))
        old_locations = set()
        for location, old_cards in card_containers(old_view):
            old_locations.add(location)
            r, a, e, m = _match_cards(old_cards, new_containers.get(location, []))
            removed += len(r)
            added += len(a)
            edited += len(e)
            # One entry per moved card already, so a swap contributes
            # two. Multiplying would count each of them twice.
            moved += len(m)
        # A container only the new state has - a section added to a view.
        # Walking the old state's containers alone never visited it, so
        # moving a card into a new section read as a bare deletion.
        for location, new_cards in new_containers.items():
            if location not in old_locations:
                added += len(new_cards)
```

- [ ] **Step 4: Laufen lassen und Grünwerden bestätigen**

Run: `python3 -m pytest tests/ -v`
Expected: PASS — kein bestehender Test darf kippen

- [ ] **Step 5: Committen**

```bash
git add custom_components/dashboard_history/analyze.py tests/test_analyze.py
```

Botschaft:

```
Zaehle Karten in einem neu angelegten Abschnitt mit

summarize lief über die Container des alten Stands und suchte jeden im
neuen. Ein Abschnitt, den erst der neue Stand hat, wurde damit nie
besucht und seine Karten nie gezählt: Wer eine Karte in einen neuen
Abschnitt zieht, sah »1 removed« und nichts weiter.

Das ist genau die Art halber Wahrheit, gegen die dieses Projekt
mehrfach nachgebessert hat — und sie fällt jetzt auf, weil die
Erklärung aus dem vorigen Commit denselben Fall richtig benennt und
der Zeile darüber widersprechen würde.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

---

### Task 3: Notizen in der Ablage

**Files:**
- Modify: `custom_components/dashboard_history/store.py` (`Change` ~Zeile 29-35, Leseteil ab ~Zeile 196)
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `_resolve`, `_repo`, `list_changes`, `_IDENTITY` — alle vorhanden
- Produces:
  ```python
  @dataclass(frozen=True)
  class Change:
      revision: str
      timestamp: int
      message: str
      description: str = ""   # neu

  def set_description(self, revision: str, text: str) -> bool
  def descriptions(self) -> dict[str, str]
  def previous_change(self, key: str, revision: str) -> str | None
  ```

- [ ] **Step 1: Die fehlschlagenden Tests schreiben**

An `tests/test_store.py` anhängen:

```python
# -- descriptions of one's own -----------------------------------------
#
# The automatic message says what happened. Why it happened is only in
# somebody's head, and "before rebuilding the heating cards" is what you
# find again in a year - "2 removed, 1 edited" is not.
#
# The text is a git note, so the commit itself is untouched. That is not
# tidiness: a rewritten commit invalidates every revision this tool
# hands out, in panel responses, service results and error messages.


def test_a_description_appears_in_the_history(store):
    revision = store.write_snapshot("home", "a: 1\n", "first")
    assert store.set_description(revision, "Before the heating rebuild") is True
    assert store.list_changes("home")[0].description == "Before the heating rebuild"


def test_a_change_without_a_description_has_an_empty_one(store):
    store.write_snapshot("home", "a: 1\n", "first")
    assert store.list_changes("home")[0].description == ""


def test_a_description_does_not_change_the_revision(store):
    # The whole reason for using notes instead of rewriting the commit.
    revision = store.write_snapshot("home", "a: 1\n", "first")
    store.set_description(revision, "Something")
    assert store.list_changes("home")[0].revision == revision


def test_a_description_replaces_the_previous_one(store):
    revision = store.write_snapshot("home", "a: 1\n", "first")
    store.set_description(revision, "First wording")
    store.set_description(revision, "Second wording")
    assert store.list_changes("home")[0].description == "Second wording"


def test_an_emptied_description_is_gone_not_blank(store):
    # A blank note would leave the row with an invisible headline and the
    # automatic message hidden underneath it.
    revision = store.write_snapshot("home", "a: 1\n", "first")
    store.set_description(revision, "Something")
    store.set_description(revision, "   ")
    assert store.list_changes("home")[0].description == ""
    assert store.descriptions() == {}


def test_emptying_a_description_that_was_never_there_is_harmless(store):
    revision = store.write_snapshot("home", "a: 1\n", "first")
    assert store.set_description(revision, "") is True


def test_a_description_survives_umlauts(store):
    revision = store.write_snapshot("home", "a: 1\n", "first")
    store.set_description(revision, "Vor dem Umbau der Heizung — äöüß")
    assert store.list_changes("home")[0].description == (
        "Vor dem Umbau der Heizung — äöüß"
    )


def test_an_abbreviated_revision_can_be_described(store):
    # What anyone copies out of the panel, which shows seven characters.
    revision = store.write_snapshot("home", "a: 1\n", "first")
    assert store.set_description(revision[:7], "Short form") is True
    assert store.list_changes("home")[0].description == "Short form"


def test_an_unknown_revision_is_refused(store):
    # dulwich raises KeyError for an unknown object, so this must be
    # resolved first. Refusing is right anyway: a note filed against
    # nothing is a note nobody ever sees again.
    store.write_snapshot("home", "a: 1\n", "first")
    assert store.set_description("f" * 40, "Nowhere") is False
    assert store.descriptions() == {}


def test_descriptions_are_per_revision(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    second = store.write_snapshot("home", "a: 2\n", "second")
    store.set_description(first, "The older one")
    store.set_description(second, "The newer one")
    assert [c.description for c in store.list_changes("home")] == [
        "The newer one",
        "The older one",
    ]


def test_the_state_before_a_change_is_the_previous_one_of_that_dashboard(store):
    # Not the commit's parent: another dashboard's commit can sit in
    # between, and its state is no state of this dashboard at all.
    first = store.write_snapshot("home", "a: 1\n", "home first")
    store.write_snapshot("other", "b: 1\n", "other first")
    second = store.write_snapshot("home", "a: 2\n", "home second")
    assert store.previous_change("home", second) == first


def test_the_first_change_has_nothing_before_it(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    assert store.previous_change("home", first) is None


def test_the_state_before_an_unknown_revision_is_unknown(store):
    store.write_snapshot("home", "a: 1\n", "first")
    assert store.previous_change("home", "f" * 40) is None
```

- [ ] **Step 2: Laufen lassen und das Scheitern bestätigen**

Run: `python3 -m pytest tests/test_store.py -v -k "description or previous"`
Expected: FAIL — `AttributeError: 'HistoryStore' object has no attribute 'set_description'`

- [ ] **Step 3: Die Umsetzung schreiben**

`Change` bekommt das Feld:

```python
@dataclass(frozen=True)
class Change:
    """One recorded state of one dashboard."""

    revision: str
    timestamp: int
    message: str
    description: str = ""  # what a person wrote about it, if anyone did
```

Im Schreibteil, hinter `create_version`:

```python
    def set_description(self, revision: str, text: str) -> bool:
        """Attach a person's own words to a recorded change.

        Stored as a git note on `refs/notes/commits`, which leaves the
        commit itself untouched. That is the point rather than a detail:
        rewriting a commit message rewrites the commit, and with it every
        descendant - invalidating exactly the revisions this tool hands
        out in panel responses, service results and error messages.

        An empty text removes the note instead of storing a blank one; a
        blank one would leave a row with an invisible headline and the
        automatic message hidden beneath it.

        Returns False when the revision is unknown. dulwich raises
        KeyError for an unknown object, so it has to be resolved first -
        and refusing is right anyway, since a note filed against nothing
        is a note nobody ever finds again.
        """
        with self._lock:
            self._ensure()
            repo = self._repo()
            if repo is None:
                return False
            full = self._resolve(repo, revision)
            if full is None:
                return False
            body = text.strip()
            if body:
                porcelain.notes_add(
                    str(self.path),
                    full.encode(),
                    body.encode("utf-8"),
                    author=_IDENTITY,
                    committer=_IDENTITY,
                )
            else:
                # Measured: a commit without a note returns None here
                # rather than raising, so this needs no guard of its own.
                porcelain.notes_remove(
                    str(self.path),
                    full.encode(),
                    author=_IDENTITY,
                    committer=_IDENTITY,
                )
            return True
```

Im Leseteil:

```python
    def descriptions(self) -> dict[str, str]:
        """Every description, by revision.

        One pass over the notes rather than one lookup per change: the
        panel asks for fifty changes at a time.
        """
        if not (self.path / ".git").exists():
            return {}
        # Measured: a repository that never held a note answers with an
        # empty list rather than raising, so this needs no guard.
        return {
            _as_text(sha): text.decode("utf-8")
            for sha, text in porcelain.notes_list(str(self.path))
        }

    def previous_change(self, key: str, revision: str) -> str | None:
        """The state of one dashboard just before one of its changes.

        Deliberately not the commit's parent. Another dashboard's commit
        can sit in between, and its state is no state of this dashboard
        at all - reading it would answer a question nobody asked.
        """
        full = self.resolve(revision)
        if full is None:
            return None
        found = False
        for change in self.list_changes(key, limit=1000):
            if found:
                return change.revision
            found = change.revision == full
        return None
```

Und `list_changes` hängt die Beschreibungen an:

```python
    def list_changes(self, key: str, limit: int = 50) -> list[Change]:
        """Every recorded state of one dashboard, newest first."""
        repo = self._repo()
        if repo is None:
            return []
        notes = self.descriptions()
        try:
            # Both paths: a rename touches only the metadata, and a change
            # that is recorded but never shown is the worst of both.
            walker = repo.get_walker(
                paths=[f"{key}.yaml".encode(), f"meta/{key}.yaml".encode()],
                max_entries=limit,
            )
            return [
                Change(
                    revision=_as_text(entry.commit.id),
                    timestamp=entry.commit.commit_time,
                    message=entry.commit.message.decode("utf-8").strip(),
                    description=notes.get(_as_text(entry.commit.id), ""),
                )
                for entry in walker
            ]
        except KeyError:
            # No HEAD yet: an empty repository has no history to walk.
            return []
```

- [ ] **Step 4: Laufen lassen und Grünwerden bestätigen**

Run: `python3 -m pytest tests/ -v`
Expected: PASS

- [ ] **Step 5: Committen**

```bash
git add custom_components/dashboard_history/store.py tests/test_store.py
```

Botschaft:

```
Lege eigene Texte als git note ab, nicht im Commit

Die automatische Meldung sagt, was geschehen ist. Warum es geschehen
ist, weiß nur der Mensch — und »vor dem Umbau der Heizungskarten«
findet man in einem Jahr wieder, »2 removed, 1 edited« nicht.

Eine Commit-Botschaft nachträglich zu ändern wäre der falsche Weg:
Ein Commit ist über seinen Inhalt adressiert, ihn umzuschreiben
schreibt jeden Nachfolger um und macht damit genau die Revisionen
ungültig, die dieses Werkzeug in Panel-Antworten, Dienstergebnissen
und Fehlermeldungen herausgibt. Genau für diese Trennung gibt es git
notes: veränderlicher Kommentar an unveränderlichem Objekt.

Zwei Feinheiten sind gemessen und nicht geraten. Ein geleerter Text
entfernt die Notiz, statt eine leere abzulegen — sonst hätte die
Zeile eine unsichtbare Überschrift und die automatische Meldung wäre
verdeckt. Und eine unbekannte Revision wird abgewiesen, weil dulwich
dort KeyError wirft und eine Notiz an nichts ohnehin niemand
wiederfindet.

previous_change nimmt bewusst nicht den Eltern-Commit: Dazwischen kann
der Commit eines anderen Dashboards liegen, und dessen Stand ist kein
Stand dieses Dashboards.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

---

### Task 4: Vorgänge, WebSocket und Dienste

**Files:**
- Modify: `custom_components/dashboard_history/operations.py` (`async_history` ~Zeile 96, `async_restore_deleted` ~Zeile 128, `async_restore_state` ~Zeile 161, neu am Ende)
- Modify: `custom_components/dashboard_history/websocket_api.py` (`_COMMANDS`)
- Modify: `custom_components/dashboard_history/services.py`, `services.yaml`
- Test: keiner in pytest möglich — HA-gebunden, siehe Task 7

**Interfaces:**
- Consumes: `store.set_description`, `store.previous_change`, `store.list_changes` (Task 3); `analyze.explain_change`, `analyze.explain_effect` (Task 1)
- Produces:
  ```python
  async def async_describe(hass, store, revision: str, text: str) -> dict
  async def async_explain(hass, store, key: str, revision: str) -> dict
  ```
  Antwortformen:
  - `async_describe` → `{"applied": True, "description": "…"}` oder `{"applied": False, "error": "unknown revision: …"}`
  - `async_explain` → `{"groups": [{"view": str, "entries": [{"kind","what","label","text"}], "more": int}], "note": str}`
  - `async_history` → jede Änderung zusätzlich mit `"description"`
  - `async_restore_deleted` / `async_restore_state` → zusätzlich `"explanation"` in derselben Form wie `async_explain`

- [ ] **Step 1: Die Serialisierung und die zwei Vorgänge schreiben**

In `operations.py`, hinter `_diff`:

```python
def _as_dict(explanation) -> dict:
    """An Explanation as plain data, for a service result or the panel."""
    return {
        "groups": [
            {
                "view": group.view,
                "entries": [
                    {
                        "kind": entry.kind,
                        "what": entry.what,
                        "label": entry.label,
                        "text": entry.text,
                    }
                    for entry in group.entries
                ],
                "more": group.more,
            }
            for group in explanation.groups
        ],
        "note": explanation.note,
    }
```

`async_history` gibt die Beschreibung mit heraus:

```python
    return {
        "changes": [
            {
                "revision": c.revision,
                "timestamp": c.timestamp,
                "message": c.message,
                "description": c.description,
            }
            for c in changes
        ]
    }
```

In `async_restore_deleted`, hinter `diff = _diff(current, restored, key)`:

```python
    explanation = _as_dict(explain_effect(current, restored))
    if not confirm:
        return {"applied": False, "preview": diff, "explanation": explanation}
    await async_save_config(hass, key, restored)
    return {
        "applied": True,
        "preview": diff,
        "explanation": explanation,
        "restored": items[position].label,
    }
```

In `async_restore_state`, hinter `diff = _diff(current, target, key)`:

```python
    explanation = _as_dict(explain_effect(current, target))
    if not diff and not missing:
        return {"applied": False, "preview": "", "note": "already identical"}
    if not confirm:
        return {
            "applied": False,
            "preview": diff,
            "explanation": explanation,
            "creates_dashboard": missing,
        }
```

und in der Erfolgsantwort `"explanation": explanation` ergänzen.

Am Ende von `operations.py`:

```python
async def async_describe(
    hass: HomeAssistant, store: HistoryStore, revision: str, text: str
) -> dict:
    """Attach a person's own words to a recorded change.

    No `confirm`, unlike every other writing operation here. The rule in
    the spec protects dashboards from unintended change; a description
    changes no dashboard, is undone by emptying the field, and is read by
    the same person who just wrote it. A dialog in front of it would be
    ceremony without protection - and the opposite of what was asked for.
    """
    ok = await hass.async_add_executor_job(store.set_description, revision, text)
    if not ok:
        return {"applied": False, "error": f"unknown revision: {revision}"}
    return {"applied": True, "description": text.strip()}


async def async_explain(
    hass: HomeAssistant, store: HistoryStore, key: str, revision: str
) -> dict:
    """What one recorded change did, in words.

    `revision` is the change itself, not the state before it - the panel
    must not have to work that out, because working it out wrongly is the
    trap Entscheidung 9 removed rather than signposted.
    """
    full, text, error = await _state_at(hass, store, key, revision)
    if error is not None:
        return {"groups": [], "note": "", "error": error}
    before = await hass.async_add_executor_job(store.previous_change, key, full)
    if before is None:
        return {"groups": [], "note": "This is the first recorded state."}
    old = await hass.async_add_executor_job(store.read_at, key, before)
    # `read_at` answers None when the dashboard did not exist yet, and
    # yaml_io.load(None) raises. Measured, not assumed.
    return _as_dict(explain_change(load(old or "") or {}, load(text) or {}))
```

Und der Import oben erweitert sich:

```python
from .analyze import explain_change, explain_effect, find_removed
```

- [ ] **Step 2: Die WebSocket-Befehle ergänzen**

In `websocket_api.py`, in `_COMMANDS`:

```python
    _command(
        f"{DOMAIN}/describe",
        {**_REVISION, vol.Optional("text", default=""): str},
        operations.async_describe,
        lambda msg: {"revision": msg["revision"], "text": msg["text"]},
    ),
    _command(
        f"{DOMAIN}/explain",
        {**_DASHBOARD, **_REVISION},
        operations.async_explain,
        lambda msg: {"key": msg["dashboard"], "revision": msg["revision"]},
    ),
```

- [ ] **Step 3: Die Dienste ergänzen**

In `services.py`, bei den Handlern:

```python
    async def describe(call: ServiceCall) -> dict:
        return await operations.async_describe(
            hass, store, call.data["revision"], call.data.get("text", "")
        )

    async def explain(call: ServiceCall) -> dict:
        return await operations.async_explain(
            hass, store, call.data["dashboard"], call.data["revision"]
        )
```

und in `registrations`:

```python
        ("describe", describe, vol.Schema({
            vol.Required("revision"): cv.string,
            vol.Optional("text", default=""): cv.string,
        })),
        ("explain", explain, DASHBOARD.extend({vol.Required("revision"): cv.string})),
```

In `services.yaml`, vor `create_version`:

```yaml
describe:
  name: Describe a change
  description: >-
    Give one recorded change your own description. It becomes the
    headline of that entry; the automatic message stays below it. An
    empty text removes the description again. The commit itself is not
    rewritten, so every revision stays valid.
  fields:
    revision:
      required: true
      description: A revision from the history service.
      selector:
        text:
    text:
      description: Your own words. Empty removes the description.
      default: ""
      example: Before rebuilding the heating cards
      selector:
        text:
          multiline: true

explain:
  name: Explain a change
  description: >-
    What one recorded change did, in plain words rather than as a diff.
    Cards and views by name, grouped by view.
  fields:
    dashboard:
      required: true
      example: dashboard-karte
      selector:
        text:
    revision:
      required: true
      description: >-
        The change itself, from the history service - not the state
        before it.
      selector:
        text:
```

- [ ] **Step 4: Prüfen, dass Home Assistant die Integration noch lädt**

```bash
python3 -m pytest tests/ -v
docker compose -f docker/compose.yaml restart
python3 tests/integration/run_checks.py
```

Expected: pytest grün, alle bisherigen 23 Prüfungen grün. Beim ersten Lauf nach dem Neustart etwa zehn Sekunden Anlaufzeit einplanen — **niemals während des Neustarts anpollen.**

- [ ] **Step 5: Committen**

```bash
git add custom_components/dashboard_history/operations.py \
        custom_components/dashboard_history/websocket_api.py \
        custom_components/dashboard_history/services.py \
        custom_components/dashboard_history/services.yaml
```

Botschaft:

```
Biete Beschreibung und Erklaerung als Vorgang an

Beides liegt in operations.py, weil Dienste und Panel zwei dünne Häute
über derselben Schicht sind — sonst stünde das Wesentliche
ausgerechnet dort, wo Home Assistant sich am häufigsten bewegt.

async_explain nimmt die Änderung selbst, nicht den Stand davor. Das
Panel soll das nicht ausrechnen müssen: Es falsch auszurechnen ist die
Stolperstelle, die Entscheidung 9 entfernt statt abgesichert hat.

async_describe verlangt kein confirm. Die Vorschaupflicht schützt
Dashboards vor unbeabsichtigter Veränderung; eine Beschreibung
verändert keines, wird durch Leeren des Feldes zurückgenommen und von
derselben Person gelesen, die sie gerade geschrieben hat.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

---

### Task 5: Der Stift im Panel

**Files:**
- Modify: `custom_components/dashboard_history/panel.js` (`STYLE`, `_renderMain` ~Zeile 405, `_render` ~Zeile 421)

**Interfaces:**
- Consumes: WebSocket `dashboard_history/describe` und `description` in `history` (Task 4)
- Produces: nichts für spätere Aufgaben

- [ ] **Step 1: Den Dialog und den Stift bauen**

`STYLE` bekommt:

```css
  .change .pen {
    padding: 4px 8px;
    border: 0;
    border-radius: 4px;
    background: none;
    color: var(--secondary-text-color, #727272);
    font: inherit;
    font-size: 15px;
    cursor: pointer;
    opacity: 0;
  }
  .change:hover .pen, .change .pen:focus { opacity: 1; }
  .change .what .auto {
    display: block;
    margin-top: 2px;
    color: var(--secondary-text-color, #727272);
    font-size: 13px;
    font-weight: 400;
  }
  dialog input.text {
    width: 100%;
    padding: 10px 12px;
    border: 1px solid var(--divider-color, #e0e0e0);
    border-radius: 4px;
    background: var(--card-background-color, #fff);
    color: inherit;
    font: inherit;
    box-sizing: border-box;
  }
```

Die Zeile in `_renderMain` zeigt die eigene Beschreibung als Überschrift und die automatische Meldung darunter — sie verschwindet nie, weil sie die Angabe ist, der man trauen kann:

```javascript
    const rows = this._changes
      .map(
        (change, index) => `
        <div class="card">
          <div class="change" data-index="${index}">
            <span class="what">${escape(change.description || change.message)}
              ${change.description ? `<span class="auto">${escape(change.message)}</span>` : ""}
            </span>
            <span class="when">${escape(when(change.timestamp))}</span>
            <span class="rev">${escape(change.revision.slice(0, 7))}</span>
            <button class="pen" data-describe="${index}"
                    title="Describe this change">✎</button>
          </div>
          ${this._open === change.revision ? this._renderDetail(index) : ""}
        </div>`,
      )
      .join("");
```

Ein zweiter `<dialog>` in `_render`, mit **einem** Feld — dieselbe Form wie Home Assistants »Umbenennen« bei einer Erweiterung:

```html
      <dialog class="describe">
        <h2>Describe this change</h2>
        <div class="body" style="padding:0 16px 8px">
          <input class="text" type="text" maxlength="200"
                 placeholder="Why did you change this?">
          <p class="muted" style="font-size:13px">
            This becomes the headline of the entry. The automatic message
            stays below it. Leave it empty to remove the description.
          </p>
        </div>
        <div class="actions">
          <button class="act ghost" value="cancel">Cancel</button>
          <button class="act" value="save">Save</button>
        </div>
      </dialog>
```

Die Methode:

```javascript
  /** One field, prefilled, Save or Cancel. Nothing more is wanted here. */
  async _describe(index) {
    const change = this._changes[index];
    const dialog = this.shadowRoot.querySelector("dialog.describe");
    const field = dialog.querySelector("input.text");
    field.value = change.description || "";
    dialog.returnValue = "";
    dialog.showModal();
    field.focus();
    field.select();
    const answer = await new Promise((resolve) => {
      dialog.addEventListener("close", () => resolve(dialog.returnValue), {
        once: true,
      });
    });
    if (answer !== "save") return;
    const result = await this._guard(() =>
      this._call("describe", { revision: change.revision, text: field.value }),
    );
    if (result?.error) {
      this._error = result.error;
      this._render();
      return;
    }
    await this._select(this._selected);
  }
```

Die Verdrahtung in `_render` — der Stift darf die Zeile **nicht** mit aufklappen:

```javascript
    root.querySelectorAll("[data-describe]").forEach((element) =>
      element.addEventListener("click", (event) => {
        // Otherwise the click reaches .change underneath and expands the
        // row at the same time.
        event.stopPropagation();
        this._describe(Number(element.dataset.describe));
      }),
    );
```

Und die Schaltflächen des neuen Dialogs, wo die des alten verdrahtet werden:

```javascript
    root.querySelectorAll("dialog").forEach((element) =>
      element.querySelectorAll(".actions button").forEach((button) =>
        button.addEventListener("click", () => element.close(button.value)),
      ),
    );
```

Enter im Feld soll speichern, weil ein Feld mit einem Knopf sonst nach Formular aussieht und sich nicht wie eines verhält:

```javascript
    const field = root.querySelector("dialog.describe input.text");
    if (field)
      field.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          root.querySelector("dialog.describe").close("save");
        }
      });
```

- [ ] **Step 2: Von Hand prüfen, an der Wegwerf-Instanz**

```bash
docker compose -f docker/compose.yaml restart
```

Auf http://127.0.0.1:8124 anmelden, *Dashboard History* öffnen und der Reihe nach:

1. Stift an einer Zeile → Dialog mit leerem Feld, Fokus im Feld
2. Text eingeben, Enter → Text ist die Überschrift, die automatische Meldung steht grau darunter
3. Stift erneut → Feld ist vorbelegt
4. Feld leeren, Speichern → Überschrift ist wieder die automatische Meldung
5. Stift → die Zeile klappt **nicht** auf
6. Browser-Konsole: keine Fehler

- [ ] **Step 3: Committen**

```bash
git add custom_components/dashboard_history/panel.js
```

Botschaft:

```
Gib jeder Aenderung einen Stift und ein Feld

Ein Klick, ein vorbelegtes Feld, Enter — dieselbe Form wie Home
Assistants »Umbenennen« bei einer Erweiterung, weil das die Bewegung
ist, die hier gewünscht war.

Der eigene Text wird die Überschrift, die automatische Meldung rutscht
grau darunter. Sie verschwindet nicht: Sie ist die Angabe, der man
trauen kann, wenn die eigene Notiz von damals nicht mehr genug sagt.

Der Klick auf den Stift wird angehalten, sonst erreicht er die Zeile
darunter und klappt sie gleichzeitig auf.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

---

### Task 6: Die Erklärung über dem Diff

**Files:**
- Modify: `custom_components/dashboard_history/panel.js` (`STYLE`, `renderDiff`, `_confirm` ~Zeile 286, `_expand` ~Zeile 263, `_renderDetail` ~Zeile 361)

**Interfaces:**
- Consumes: `explanation` aus `restore_deleted`/`restore_state` und der Befehl `explain` (Task 4)
- Produces: nichts für spätere Aufgaben

- [ ] **Step 1: Die Darstellung bauen**

`STYLE` bekommt:

```css
  .plain { margin: 0 0 12px; }
  .plain h3 { margin: 0 0 8px; font-size: 15px; }
  .plain .view {
    margin: 0 0 10px;
    padding-left: 12px;
    border-left: 3px solid var(--divider-color, #e0e0e0);
  }
  .plain .view > strong { display: block; font-size: 13px; }
  .plain ul { margin: 4px 0 0; padding-left: 18px; }
  .plain li { margin: 2px 0; }
  .plain li.removed { color: var(--error-color, #db4437); }
  .plain li.added { color: var(--success-color, #0f9d58); }
  .plain .note { margin: 8px 0 0; font-size: 13px; }
  details.raw > summary {
    padding: 8px 0;
    color: var(--secondary-text-color, #727272);
    font-size: 13px;
    cursor: pointer;
  }
```

Ein Renderer neben `renderDiff`:

```javascript
/**
 * The same difference in words. It sits above the diff, not instead of
 * it: the diff is the exact account, and it stays.
 */
const renderPlain = (explanation, heading) => {
  if (!explanation) return "";
  const groups = (explanation.groups || [])
    .map(
      (group) => `
      <div class="view">
        <strong>In the view ${escape(group.view)}</strong>
        <ul>
          ${group.entries
            .map(
              (entry) =>
                `<li class="${escape(entry.kind)}">${escape(entry.text)}</li>`,
            )
            .join("")}
          ${group.more ? `<li class="muted">and ${escape(group.more)} more</li>` : ""}
        </ul>
      </div>`,
    )
    .join("");
  const note = explanation.note
    ? `<p class="note muted">${escape(explanation.note)}</p>`
    : "";
  return `<div class="plain"><h3>${escape(heading)}</h3>${groups}${note}</div>`;
};
```

Der Bestätigungsdialog setzt beides zusammen, der Diff eingeklappt:

```javascript
    dialog.querySelector(".body").innerHTML =
      renderPlain(preview.explanation, "What applying this does") +
      `<details class="raw">
         <summary>Show the technical details</summary>
         ${renderDiff(preview.preview)}
       </details>`;
```

Beim Aufklappen einer Zeile kommt die Erklärung dazu — ein Aufruf mehr, parallel zum bestehenden:

```javascript
    this._open = change.revision;
    this._items = [];
    this._explanation = null;
    const before = this._before(index);
    const [items, explanation] = await this._guard(() =>
      Promise.all([
        before
          ? this._call("deleted_since", {
              dashboard: this._selected,
              revision: before,
            })
          : Promise.resolve({ items: [] }),
        this._call("explain", {
          dashboard: this._selected,
          revision: change.revision,
        }),
      ]),
    ) || [null, null];
    this._items = items ? items.items || [] : [];
    this._explanation = explanation;
    this._render();
```

`this._explanation = null;` gehört in den Konstruktor und in `_select`.

Und `_renderDetail` stellt sie voran — vor der Liste des Vermissten, weil sie die allgemeinere Auskunft ist:

```javascript
  _renderDetail(index) {
    const plain = renderPlain(this._explanation, "What this change did");
    const before = this._before(index);
    if (!before)
      return `<div class="detail">${plain}<p class="muted">This is the first
        recorded state, so there is nothing before it to compare against.</p></div>`;
```

und im Rückgabewert weiter unten `${plain}` vor `${list}`.

- [ ] **Step 2: Von Hand prüfen, an der Wegwerf-Instanz**

```bash
docker compose -f docker/compose.yaml restart
```

1. Eine Änderung aufklappen → Klartext oben, danach die Liste des Vermissten
2. »Put back« → Dialog mit Klartext oben, »Show the technical details« **zu**
3. Aufklappen → der Diff wie bisher, farbig
4. Bei einer Änderung ohne benennbaren Anteil (etwa eine Umbenennung des Dashboards): kein »nothing changed«, sondern der Verweis auf den Diff
5. »Bring it back« an einem gelöschten Dashboard → eine Zeile je Ansicht, nicht Hunderte
6. Browser-Konsole: keine Fehler

- [ ] **Step 3: Committen**

```bash
git add custom_components/dashboard_history/panel.js
```

Botschaft:

```
Setze Klartext ueber den Diff, den Diff eingeklappt

Der Diff bleibt die genaue Auskunft und verschwindet nicht — er
beantwortet aber für die meisten Menschen nicht die Frage, die sie vor
dem Übernehmen haben. Darüber steht jetzt, was mit welcher Karte in
welcher Ansicht geschieht.

Die Erklärung erscheint an zwei Stellen, weil derselbe Sachverhalt
zweimal gebraucht wird: im Dialog als »was wird passieren«, beim
Aufklappen einer Zeile als »was ist damals passiert«.

Ob der Diff offen oder zu startet, wird später einstellbar; sein Platz
wäre ein Options-Flow. Vorerst zu, denn das ist der Zweck der
Zusammenfassung.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

---

### Task 7: Prüfungen an echtem Home Assistant und die Dokumentation

Die pytest-Tests erreichen `operations.py`, `websocket_api.py` und `services.py` strukturell nicht — und **dort saß jeder in diesem Projekt gefundene Fehler.**

**Files:**
- Modify: `tests/integration/run_checks.py`
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-08-31-eigene-texte-und-klartext.md` (Befunde unter »Nach der Umsetzung«)

**Interfaces:**
- Consumes: alles aus Task 1 bis 6
- Produces: nichts

- [ ] **Step 1: Die Prüfungen schreiben**

Als neue Funktion in `tests/integration/run_checks.py`, aufgerufen wie die bestehenden Abschnitte:

```python
def run_descriptions(client, key):
    """A description of one's own: written, read back, replaced, removed."""
    history = client.ws("dashboard_history/history", dashboard=key)
    changes = history["changes"]
    check(bool(changes), "there is a change to describe", f"{len(changes)} changes")
    revision = changes[0]["revision"]

    result = client.ws(
        "dashboard_history/describe",
        revision=revision,
        text="Vor dem Umbau der Heizungskarten",
    )
    check(result.get("applied") is True, "a description is accepted", result)

    again = client.ws("dashboard_history/history", dashboard=key)
    newest = again["changes"][0]
    check(
        newest["description"] == "Vor dem Umbau der Heizungskarten",
        "it comes back with the history, umlauts intact",
        newest["description"],
    )
    check(
        newest["revision"] == revision,
        "and the revision is unchanged - the commit was not rewritten",
        newest["revision"][:10],
    )
    check(
        newest["message"] == changes[0]["message"],
        "the automatic message is still there underneath it",
        newest["message"],
    )

    client.ws("dashboard_history/describe", revision=revision, text="")
    emptied = client.ws("dashboard_history/history", dashboard=key)
    check(
        emptied["changes"][0]["description"] == "",
        "emptying it removes the description rather than blanking it",
        repr(emptied["changes"][0]["description"]),
    )

    bad = client.ws("dashboard_history/describe", revision="f" * 40, text="Nowhere")
    check(
        bad.get("applied") is False and "unknown revision" in bad.get("error", ""),
        "an unknown revision is refused, and says so",
        bad,
    )


def run_explanation(client, key):
    """The plain-language explanation, on a real dashboard."""
    changes = client.ws("dashboard_history/history", dashboard=key)["changes"]
    check(len(changes) > 1, "there is a change with a state before it", len(changes))
    result = client.ws(
        "dashboard_history/explain", dashboard=key, revision=changes[0]["revision"]
    )
    check("groups" in result and "note" in result, "explain answers in shape", result.keys())
    named = [
        entry["text"]
        for group in result["groups"]
        for entry in group["entries"]
    ]
    check(
        bool(named) or "see the details" in result["note"],
        "it either names something or admits it cannot - never both silent",
        named[:3] or result["note"],
    )
    for group in result["groups"]:
        check(
            len(group["entries"]) <= 12,
            f"the list for view {group['view']!r} is capped",
            f"{len(group['entries'])} entries, {group['more']} hidden",
        )


def run_preview_explains(client, key):
    """The preview a person sees before pressing Apply."""
    changes = client.ws("dashboard_history/history", dashboard=key)["changes"]
    before = changes[1]["revision"]
    preview = client.ws(
        "dashboard_history/restore_state",
        dashboard=key,
        revision=before,
        confirm=False,
    )
    check(preview.get("applied") is False, "nothing is written without confirm", preview.get("applied"))
    check(
        "explanation" in preview and "preview" in preview,
        "the preview carries words AND the diff, not one instead of the other",
        sorted(preview.keys()),
    )
```

- [ ] **Step 2: Laufen lassen**

```bash
docker compose -f docker/compose.yaml up -d
python3 tests/integration/run_checks.py
```

Expected: alle bisherigen 23 Prüfungen plus die neuen, alle grün. Bei einem Fehlschlag gilt die Regel dieses Projekts: **nicht die Prüfung anpassen, sondern die Ursache suchen** — jeder bisherige Fehlschlag hier war ein echter Fehler.

- [ ] **Step 3: Die README nachziehen**

- Abschnitt »What it does«: den Punkt zu Versionen ersetzen durch »**Describe a change in your own words** — one field, and it becomes the headline of that entry.«
- Neuer Abschnitt »Describing a change« nach »The panel«, der den Stift erklärt und einen Satz dazu, dass der Commit nicht umgeschrieben wird und Revisionen darum gültig bleiben.
- Ein Satz im Abschnitt zum Panel, dass vor jedem Schreiben eine Klartext-Zusammenfassung steht und der Diff darunter aufklappbar ist.
- Die Dienst-Tabelle bekommt `describe` und `explain`; `create_version`/`versions` wandern in eine Zeile darunter mit dem Hinweis, dass sie der fortgeschrittene Weg sind: ein Tag ist über seinen Namen als Revision adressierbar, eine Beschreibung nicht.

- [ ] **Step 4: Die Befunde festhalten**

Unter »Nach der Umsetzung« in diesem Plan eintragen, was gemessen wurde und was nicht aufgegangen ist. Nichts beschönigen — die drei Fälle, in denen das Werkzeug etwas verschwieg, sind alle so gefunden worden.

- [ ] **Step 5: Committen**

```bash
git add tests/integration/run_checks.py README.md docs/superpowers/plans/
```

Botschaft:

```
Pruefe Beschreibung und Erklaerung an echtem HA

pytest erreicht operations.py, websocket_api.py und services.py
strukturell nicht — und dort saß jeder in diesem Projekt gefundene
Fehler, während der Testsatz grün blieb.

Geprüft wird deshalb dort, wo es weh tut: dass eine Beschreibung die
Revision nicht verändert, dass Umlaute unverfälscht zurückkommen, dass
ein geleertes Feld die Notiz entfernt statt sie zu leeren, dass eine
unbekannte Revision abgewiesen wird — und dass die Vorschau Worte UND
den Diff trägt, nicht das eine anstelle des anderen.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

---

## Nach der Umsetzung

*(Wird während der Umsetzung gefüllt: was gemessen wurde, was nicht aufging, was der Plan falsch angenommen hat. Die Codeauszüge oben sind ab Fertigstellung historisch — das Repository ist die Wahrheit.)*
