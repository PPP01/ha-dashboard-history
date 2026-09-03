# Die gezielte Rücknahme — Umsetzungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eine Änderung gezielt zurücknehmen — nur ihre Karten, alles Spätere bleibt stehen — und zwar genau dann, wenn sich beweisen lässt, dass das eindeutig ist.

**Architecture:** `analyze.py` rechnet und liefert einen **Plan aus mechanischen Schritten** (`UndoPlan`); `restore.py` führt ihn aus; `operations.py` verbindet beides mit Vorschau und `confirm`; das Panel zeigt eine **Weiche** — Undo oder »Put back«, nie beides für dieselbe Sache. Die Kennung einer Karte ist ihr Byte-Inhalt: Was die Änderung erzeugt hat, muss im heutigen Dashboard **genau einmal** stehen, sonst wird verweigert.

**Tech Stack:** Python 3.12 (Entwicklung) / 3.14 (Container), dulwich, Home Assistant 2026.8.3, Vanilla-JS-Webkomponente ohne Bauschritt.

**Spec:** `docs/superpowers/specs/2026-08-30-dashboard-history-design.md` — **Entscheidung 15** ist die Begründung dieses Plans; Entscheidung 4 (eingegrenzt), 5 (eingelöst), 7 (Vorschau) und 14 (Zuordnung) sind die Nachbarn.

## Global Constraints

Wortwörtlich aus Spec und `CLAUDE.md`, sie binden **jede** Aufgabe:

- **Kein Systemaufruf von `git`.** Ausschließlich `dulwich`.
- **Keine Home-Assistant-Interna abfangen oder ersetzen.** Kein Monkey-Patching.
- **Nichts blockiert den Start von Home Assistant.** Fehler beim Erfassen werden protokolliert und verschluckt.
- **`yaml_io.py`, `analyze.py`, `restore.py` und `versions.py` bleiben Home-Assistant-frei** — kein `import homeassistant`, **und keine relativen Importe**: Die vier Module werden von `tests/conftest.py` flach geladen (`import analyze`). Nachgeprüft: Sie enthalten heute keinen einzigen relativen Import. Das ist der Grund, warum `restore.py` seinen `UndoPlan` **übergeben** bekommt, statt `analyze` zu importieren.
- **Blockierende Arbeit gehört in einen Executor** (`hass.async_add_executor_job`).
- **Nichts wird ohne Vorschau geschrieben.** `confirm: true` ist Pflicht; ausgenommen bleiben nur `describe` und `create_version`.
- **Sprache:** Code, Kommentare, Docstrings, Log-Meldungen und **Commit-Botschaften auf Englisch**. Dieser Plan ist Deutsch, weil er nach innen gehört.
- **Commit-Format:** Subject im Imperativ, erster Buchstabe groß, max. 50 Zeichen; Leerzeile; Body max. 72 Zeichen, begründet das *Warum*; Abschluss `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- **Nicht schieben, nicht taggen, nicht veröffentlichen.** Nur auf ausdrückliche Ansage des Nutzers.
- **Der Prüfstand ist die Wegwerf-Instanz auf Port 8124.** Nie während eines HA-Neustarts anpollen; nie über ein Präfix löschen, nur über den genau benannten eigenen Schlüssel.
- **Nach jeder Python-Änderung Container neu starten**, sonst hält er das alte Modul im Speicher und `pytest` ist grün, während die Integration falsch läuft.
- **`panel/style.js` ist EIN Template-Literal.** Genau zwei Backticks in der Datei, kein `${`. `tests/test_panel_assets.py` wacht darüber.

## Ausgangslage

```
pytest:      205 passed
run_checks:  91 von 91
```

Beides muss am Ende mindestens so dastehen, mit den neuen Fällen obendrauf.

Die 205 sind der Stand **nach** den Korrekturen aus dem Review vom 2026-09-03 (zehn neue Fälle in `test_keys.py` und `test_store.py`); die absoluten Zahlen in den Aufgaben rechnen von hier aus. Sollte sich das noch verschieben, gilt nur: nichts wird rot, und die Zahl wächst genau um die Fälle der jeweiligen Aufgabe.

## Dateiübersicht

| Datei | Verantwortung nachher |
|---|---|
| `analyze.py` | zusätzlich: `fingerprint` (öffentlich), `UndoStep`, `UndoPlan`, `plan_undo` — **rechnet, schreibt nie** |
| `restore.py` | zusätzlich: `apply_undo` — **führt aus, rechnet nie** |
| `operations.py` | zusätzlich: `async_undo_change` — Vorschau, `confirm`, Executor |
| `websocket_api.py` | zusätzlich: Befehl `undo_change` |
| `services.py` / `services.yaml` | zusätzlich: Dienst `undo_change` |
| `panel.js` | die Weiche, die Klappe, der dritte Aufruf |
| `panel/style.js` | `.more`-Klappe |
| `tests/test_analyze.py` | Fälle für `plan_undo` |
| `tests/test_restore.py` | Fälle für `apply_undo` |
| `tests/integration/run_checks.py` | `run_undo` |

---

## Task 1: Der Plan für Karten

**Files:**
- Modify: `custom_components/dashboard_history/analyze.py`
- Test: `tests/test_analyze.py`

**Interfaces:**
- Consumes: `Slot`, `Matching`, `match_cards`, `_slots`, `_views_by_key`, `_describe` — alle vorhanden.
- Produces: `fingerprint(card) -> str`, `UndoStep`, `UndoPlan`, `plan_undo(before, after, current) -> UndoPlan`. Task 2 erweitert `plan_undo` um Views, Task 3 führt `UndoPlan` aus, Task 4 ruft `plan_undo` auf.

- [ ] **Schritt 1: `_fingerprint` öffentlich machen**

Es wird ab jetzt von außen gebraucht — als *Kennung*, nicht mehr nur zur Beschleunigung. Ein Name mit Unterstrich, den ein anderes Modul benutzt, ist eine Lüge über die Schnittstelle.

```bash
grep -n "_fingerprint" custom_components/dashboard_history/analyze.py
```

⚠️ **Nur in `analyze.py`.** `panel.py` hat ein eigenes `_fingerprint()`, das
mit Karten nichts zu tun hat — es ist der Digest, mit dem das Panel seinen
Cache bricht, und `run_checks.py` nennt es namentlich in zwei Kommentaren.
Ein repo-weites Suchen-und-Ersetzen benennt es mit um und bricht beides.

Jede Fundstelle auf `fingerprint` umbenennen und den Docstring ergänzen:

```python
def fingerprint(card: Any) -> str:
    """A card reduced to one string, equal exactly when the cards are.

    Two jobs, and the second is the heavier one. It makes the exact
    passes of `match_cards` linear instead of quadratic. And it is the
    *identity* an undo is addressed by: a card whose fingerprint occurs
    once in a dashboard can be pointed at without an `id` field, which
    is what decision 15 rests on. Anything that made two different cards
    share a fingerprint would make an undo overwrite the wrong one.
    """
```

- [ ] **Schritt 2: Den fehlschlagenden Test schreiben**

In `tests/test_analyze.py` ans Ende:

`_config(cards)` gibt es in dieser Datei bereits und baut genau die
gebrauchte Form — nicht neu anlegen. Ans Ende der Datei:

```python
def test_an_edited_card_can_be_taken_back():
    old = {"type": "tile", "entity": "light.a", "name": "Bett"}
    new = {"type": "tile", "entity": "light.a", "name": "Bettlampe"}
    plan = analyze.plan_undo(_config([old]), _config([new]), _config([new]))
    assert plan.blocked is None
    assert [(s.action, s.expect, s.payload) for s in plan.steps] == [
        ("remove", new, None),
        ("insert", None, old),
    ]
```

- [ ] **Schritt 3: Lauf zur Bestätigung, dass er fehlschlägt**

Run: `python3 -m pytest tests/test_analyze.py::test_an_edited_card_can_be_taken_back -v`
Expected: FAIL, `AttributeError: module 'analyze' has no attribute 'plan_undo'`

- [ ] **Schritt 4: `UndoStep` und `UndoPlan` anlegen**

Direkt hinter `class Matching`:

```python
@dataclass(frozen=True)
class UndoStep:
    """One mechanical edit, addressed the way `RemovedItem` is.

    `expect` is what has to sit at that place for the step to be
    applied. It travels with the step so the writing side can refuse
    rather than overwrite something it never looked at: the plan is made
    against a state read a moment earlier, and a moment is enough for
    somebody to press save.

    It answers one question and not the other: *is this still that
    card*, never *is this the right destination*. The destination lives
    on the old side of the change, and only an insertion carries it -
    which is why a card is put back by being removed and inserted rather
    than written over in place.
    """

    action: str  # "remove" | "insert"
    kind: str  # "card" | "view"
    view_path: str | None
    view_index: int
    location: tuple
    index: int
    expect: Any
    payload: Any
    label: str


@dataclass(frozen=True)
class UndoPlan:
    """Either a reason not to take a change back, or the steps that do.

    Never both. A half-applied undo leaves a state nobody asked for and
    which the row beside it no longer describes, so one unresolvable
    piece blocks the whole thing - decision 15.
    """

    blocked: str | None
    steps: tuple = ()
```

- [ ] **Schritt 5: `plan_undo` schreiben**

Hinter `find_removed`:

```python
def _present(config: dict) -> list[Slot]:
    """Every card of a state, with the place it sits in."""
    return _slots(config, {key for key, _ in _views_by_key(config)})


def _step(slot: Slot, action: str, expect: Any, payload: Any, label: str) -> UndoStep:
    """A card step at the place `slot` names."""
    return UndoStep(
        action=action,
        kind="card",
        view_path=slot.view.get("path"),
        view_index=slot.view_index,
        location=slot.location,
        index=slot.index,
        expect=expect,
        payload=payload,
        label=label,
    )


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
    matching = match_cards(before, after)
    if not (matching.removed or matching.added or matching.edited or matching.moved):
        return UndoPlan(blocked="this change did not alter any cards")

    by_mark: dict[str, list[Slot]] = {}
    for slot in _present(current):
        by_mark.setdefault(fingerprint(slot.card), []).append(slot)

    def sole(card: Any, label: str) -> tuple[Slot | None, str | None]:
        found = by_mark.get(fingerprint(card), [])
        if len(found) == 1:
            return found[0], None
        if not found:
            return None, (
                f"{label} was changed again after this, so there is no "
                f"exact version left to put back"
            )
        return None, (
            f"{len(found)} cards now look exactly like {label}, so an "
            f"exact undo cannot tell them apart"
        )

    steps: list[UndoStep] = []

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
        here, why = sole(new_slot.card, label)
        if here is None:
            return UndoPlan(blocked=why)
        steps.append(_step(here, "remove", new_slot.card, None, label))
        steps.append(_step(old_slot, "insert", None, old_slot.card, label))

    for new_slot in matching.added:
        label = _describe(new_slot.card)
        here, why = sole(new_slot.card, label)
        if here is None:
            return UndoPlan(blocked=why)
        steps.append(_step(here, "remove", new_slot.card, None, label))

    for old_slot in matching.removed:
        # Already back by some other route. Inserting would make a second
        # copy, and this part of the change is undone either way.
        if by_mark.get(fingerprint(old_slot.card)):
            continue
        steps.append(
            _step(old_slot, "insert", None, old_slot.card, _describe(old_slot.card))
        )

    return UndoPlan(blocked=None, steps=tuple(steps))
```

- [ ] **Schritt 6: Test läuft**

Run: `python3 -m pytest tests/test_analyze.py::test_an_edited_card_can_be_taken_back -v`
Expected: PASS

- [ ] **Schritt 7: Die Verweigerungen und die Sonderfälle testen**

```python
def test_a_card_edited_twice_is_refused():
    old = {"type": "tile", "entity": "light.a", "name": "Bett"}
    once = {"type": "tile", "entity": "light.a", "name": "Bettlampe"}
    twice = {"type": "tile", "entity": "light.a", "name": "Nachttisch"}
    plan = analyze.plan_undo(_config([old]), _config([once]), _config([twice]))
    assert plan.steps == ()
    assert "changed again after this" in plan.blocked
    # Named the way the tool names cards everywhere else - `_describe`
    # prefers the card's own name over its entity, so this reads
    # "tile: Bettlampe", not "tile: light.a".
    assert "Bettlampe" in plan.blocked


def test_two_identical_candidates_are_refused():
    old = {"type": "tile", "entity": "light.a", "name": "Bett"}
    new = {"type": "tile", "entity": "light.a", "name": "Bettlampe"}
    plan = analyze.plan_undo(_config([old]), _config([new]), _config([new, new]))
    assert plan.steps == ()
    assert "cannot tell them apart" in plan.blocked


def test_a_deleted_card_is_planned_back_at_its_old_place():
    a = {"type": "tile", "entity": "light.a"}
    b = {"type": "tile", "entity": "light.b"}
    plan = analyze.plan_undo(_config([a, b]), _config([a]), _config([a]))
    assert [(s.action, s.index, s.payload) for s in plan.steps] == [("insert", 1, b)]


def test_a_deleted_card_already_back_needs_no_step():
    a = {"type": "tile", "entity": "light.a"}
    b = {"type": "tile", "entity": "light.b"}
    plan = analyze.plan_undo(_config([a, b]), _config([a]), _config([a, b]))
    assert plan.blocked is None
    assert plan.steps == ()


def test_an_added_card_is_planned_away():
    a = {"type": "tile", "entity": "light.a"}
    b = {"type": "tile", "entity": "light.b"}
    plan = analyze.plan_undo(_config([a]), _config([a, b]), _config([a, b]))
    assert [(s.action, s.expect) for s in plan.steps] == [("remove", b)]


def test_a_change_without_card_effect_is_refused():
    a = {"type": "tile", "entity": "light.a"}
    plan = analyze.plan_undo(_config([a]), _config([a]), _config([a]))
    assert plan.blocked == "this change did not alter any cards"


def test_later_work_elsewhere_does_not_block():
    """The check is on what the change produced, not on its neighbours."""
    old = {"type": "tile", "entity": "light.a", "name": "Bett"}
    new = {"type": "tile", "entity": "light.a", "name": "Bettlampe"}
    later = {"type": "tile", "entity": "light.z"}
    plan = analyze.plan_undo(_config([old]), _config([new]), _config([new, later]))
    assert plan.blocked is None
    assert [s.action for s in plan.steps] == ["remove", "insert"]


def test_a_moved_card_is_removed_here_and_put_back_there():
    stays = {"type": "markdown", "content": "Stays"}
    travels = {"type": "markdown", "content": "Travels"}
    before = {
        "views": [
            {"path": "a", "cards": [stays, travels]},
            {"path": "b", "cards": []},
        ]
    }
    after = {
        "views": [
            {"path": "a", "cards": [stays]},
            {"path": "b", "cards": [travels]},
        ]
    }
    plan = analyze.plan_undo(before, after, after)
    actions = [(s.action, s.view_path, s.index) for s in plan.steps]
    assert ("remove", "b", 0) in actions
    assert ("insert", "a", 1) in actions


def test_an_edited_card_goes_back_to_its_own_place():
    """Where an edit is put back is decided on the old side, not today's.

    An edit can move a card too, and `_place` leaves the index out - so
    such a card arrives as *edited*, not as moved, and a step written at
    today's index would land on its neighbour. Two edited cards that
    also swapped are the smallest case where that shows: today card 0
    is `new1` and card 1 is `new0`, so `old0` must be taken off index 1
    and put back at index 0.
    """
    old0 = {"type": "tile", "entity": "light.a", "name": "Bett"}
    old1 = {"type": "tile", "entity": "light.b", "name": "Tisch"}
    new0 = {"type": "tile", "entity": "light.a", "name": "Bettlampe"}
    new1 = {"type": "tile", "entity": "light.b", "name": "Tischlampe"}
    plan = analyze.plan_undo(
        _config([old0, old1]), _config([new1, new0]), _config([new1, new0])
    )
    assert plan.blocked is None
    assert [(s.action, s.index) for s in plan.steps] == [
        ("remove", 1),
        ("insert", 0),
        ("remove", 0),
        ("insert", 1),
    ]
```

- [ ] **Schritt 8: Alle laufen lassen**

Run: `python3 -m pytest tests/ -q`
Expected: alles grün, 205 + 10 = **215 passed**

- [ ] **Schritt 9: Commit**

```bash
git add custom_components/dashboard_history/analyze.py tests/test_analyze.py
git commit -m "$(cat <<'MSG'
Plan an exact undo, or say why there is none

A card has no id, so decision 4 refused replacing restores outright.
Uniqueness is decidable, though: the content a change produced either
sits in the dashboard exactly once or it does not. Once means it can
be pointed at; anything else is refused by name, which is what
decision 5 promised and decision 15 now spells out.

An edit is planned as a removal plus an insertion, not as a
replacement in place: the place a card sits in leaves its index out,
so a card edited *and* shifted arrives here as edited, and writing it
at today's index would land it on the neighbour. Measured over 6000
generated histories: 48 silently wrong results that way, none this
way, and not one refusal more.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
)"
```

---

## Task 2: Ganze Views im Plan

**Files:**
- Modify: `custom_components/dashboard_history/analyze.py`
- Test: `tests/test_analyze.py`

**Interfaces:**
- Consumes: `UndoStep`, `UndoPlan`, `plan_undo` aus Task 1.
- Produces: `plan_undo` erzeugt zusätzlich Schritte mit `kind="view"`.

**Warum eine eigene Aufgabe:** `match_cards` lässt Views, die nur eine Seite hat, **absichtlich** ganz aus (`common = old_keys & new_keys`). Ohne diesen Schritt liefert `plan_undo` für »ganze View gelöscht« einen leeren Plan und der Knopf verspräche etwas, das nichts tut.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

```python
def test_a_deleted_view_is_planned_back():
    a = {"path": "a", "title": "A", "cards": [{"type": "tile", "entity": "light.a"}]}
    b = {"path": "b", "title": "B", "cards": []}
    plan = analyze.plan_undo({"views": [a, b]}, {"views": [a]}, {"views": [a]})
    assert plan.blocked is None
    assert [(s.action, s.kind, s.payload) for s in plan.steps] == [
        ("insert", "view", b)
    ]


def test_an_added_view_is_planned_away():
    a = {"path": "a", "title": "A", "cards": []}
    b = {"path": "b", "title": "B", "cards": []}
    plan = analyze.plan_undo({"views": [a]}, {"views": [a, b]}, {"views": [a, b]})
    assert [(s.action, s.kind, s.index) for s in plan.steps] == [
        ("remove", "view", 1)
    ]


def test_an_added_view_changed_since_is_refused():
    a = {"path": "a", "title": "A", "cards": []}
    b = {"path": "b", "title": "B", "cards": []}
    worked_on = {"path": "b", "title": "B", "cards": [{"type": "tile"}]}
    plan = analyze.plan_undo(
        {"views": [a]}, {"views": [a, b]}, {"views": [a, worked_on]}
    )
    assert plan.steps == ()
    assert "changed again" in plan.blocked
```

- [ ] **Schritt 2: Lauf zur Bestätigung, dass sie fehlschlagen**

Run: `python3 -m pytest tests/test_analyze.py -k view_is_planned -v`
Expected: FAIL — der Plan ist leer bzw. `blocked` ist `None`

- [ ] **Schritt 3: Die Leerprüfung anpassen**

Der Wächter aus Task 1 (`if not (matching.removed or ...)`) muss die Views mitzählen, sonst wird »ganze View gelöscht« als »keine Kartenwirkung« abgewiesen. In `plan_undo` die Zeile ersetzen durch:

```python
    matching = match_cards(before, after)
    old_views = dict(_views_by_key(before))
    new_views = dict(_views_by_key(after))
    now_views = dict(_views_by_key(current))
    view_work = set(old_views) ^ set(new_views)
    if not (
        matching.removed
        or matching.added
        or matching.edited
        or matching.moved
        or view_work
    ):
        return UndoPlan(blocked="this change did not alter any cards")
```

- [ ] **Schritt 4: Die View-Schritte erzeugen**

**Vor** dem `return UndoPlan(blocked=None, steps=tuple(steps))` einfügen:

```python
    # Whole views, which `match_cards` leaves out on purpose: a view that
    # only one state has is one line in the history, not one per card on
    # it. Undoing it is the same two questions in a coarser grain - is it
    # still exactly as the change left it, and is it still there at all.
    for index, (key, view) in enumerate(_views_by_key(current)):
        if key in old_views or key not in new_views:
            continue
        # The change added this view. Take it away, if nobody worked on it.
        if view != new_views[key]:
            name = _view_name(view, key)
            return UndoPlan(
                blocked=f'the view "{name}" was changed again after this'
            )
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
                label=f'view: {_view_name(view, key)}',
            )
        )

    for index, (key, view) in enumerate(_views_by_key(before)):
        if key in new_views or key in now_views:
            # Either the change did not remove it, or it is already back.
            continue
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
```

- [ ] **Schritt 5: Tests laufen**

Run: `python3 -m pytest tests/ -q`
Expected: 215 + 3 = **218 passed**

- [ ] **Schritt 6: Commit**

```bash
git add custom_components/dashboard_history/analyze.py tests/test_analyze.py
git commit -m "$(cat <<'MSG'
Take a whole view back as one thing

match_cards leaves out views only one state has, deliberately: a view
arriving or leaving is one line in the history, not one per card on
it. Without this the plan for "the view is gone" was empty, and the
button would have promised something that did nothing.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
)"
```

---

## Task 3: Den Plan ausführen

**Files:**
- Modify: `custom_components/dashboard_history/restore.py`
- Test: `tests/test_restore.py`

**Interfaces:**
- Consumes: einen `UndoPlan` als **übergebenes Objekt** — `restore.py` importiert `analyze` **nicht** (siehe Global Constraints). Es benutzt nur die Attributnamen, genau wie es heute mit `RemovedItem` tut.
- Produces: `apply_undo(config, plan) -> dict`. Task 4 ruft es auf.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

In `tests/test_restore.py`:

```python
def test_an_edited_card_lands_back_on_the_right_card():
    old = {"type": "tile", "entity": "light.a", "name": "Bett"}
    new = {"type": "tile", "entity": "light.a", "name": "Bettlampe"}
    plan = analyze.plan_undo(_config([old, B]), _config([new, B]), _config([new, B]))
    result = restore.apply_undo(_config([new, B]), plan)
    assert result["views"][0]["cards"] == [old, B]
```

- [ ] **Schritt 2: Lauf zur Bestätigung, dass er fehlschlägt**

Run: `python3 -m pytest tests/test_restore.py::test_an_edited_card_lands_back_on_the_right_card -v`
Expected: FAIL, `AttributeError: module 'restore' has no attribute 'apply_undo'`

- [ ] **Schritt 3: `apply_undo` schreiben**

Ans Ende von `restore.py`:

```python
def _cards_for(views: list, step) -> list:
    """The card list a step points at, or a refusal."""
    view = _find_view(views, step)
    if view is None:
        raise LookupError(
            f"the view {step.label} belonged to no longer exists "
            f"(path={step.view_path!r}, index={step.view_index})"
        )
    cards = _cards_at(view, step.location)
    if cards is None:
        raise LookupError(
            f"the card list {step.label} belonged to no longer exists "
            f"(location={step.location!r})"
        )
    return cards


def _standing_there(items: list, step) -> None:
    """Refuse unless the expected thing is still at that index."""
    if step.index >= len(items) or items[step.index] != step.expect:
        raise LookupError(
            f"{step.label} is no longer where the undo was planned for it"
        )


def apply_undo(config: dict, plan) -> dict:
    """Return a new configuration with an undo plan applied.

    The order is not a detail. Removals first, highest index first, so
    an earlier removal never shifts a later one. Insertions last, lowest
    index first, so each one lands at the index it was given. Any other
    order silently writes to the wrong place.

    There is no replacement step, deliberately: a card is put back by
    being removed where it sits today and inserted where it came from.
    An edit can move a card as well, and a replacement written in place
    would then land on its neighbour - the reasoning and the measurement
    are in `plan_undo`, which is where that is decided.

    Every removal checks that the thing it was planned for is still
    standing there. The plan was made against a state read a moment
    earlier, and a moment is enough for somebody to press save - so this
    refuses rather than overwrites. `LookupError` carries a sentence a
    person can read; the caller turns it into an answer.

    The configuration handed in is never modified.
    """
    if plan.blocked is not None:
        raise LookupError(plan.blocked)
    result = copy.deepcopy(config)
    views = result.setdefault("views", [])

    # Cards before views: a card step finds its view by path, but falls
    # back to the index, and removing a view first would move it.
    removals = [step for step in plan.steps if step.action == "remove"]
    for step in sorted(
        (step for step in removals if step.kind == "card"), key=lambda s: -s.index
    ):
        cards = _cards_for(views, step)
        _standing_there(cards, step)
        del cards[step.index]
    for step in sorted(
        (step for step in removals if step.kind == "view"), key=lambda s: -s.index
    ):
        # Located, not indexed. `_views_by_key` skips anything that is not
        # a dict, so its position and the position in `views` are the same
        # only until somebody writes a stray list entry - and a wrong index
        # here deletes the wrong view.
        view = _find_view(views, step)
        if view is None or view != step.expect:
            raise LookupError(
                f"{step.label} is no longer where the undo was planned for it"
            )
        del views[views.index(view)]

    for step in sorted(
        (step for step in plan.steps if step.action == "insert"),
        key=lambda s: s.index,
    ):
        if step.kind == "view":
            views.insert(min(step.index, len(views)), copy.deepcopy(step.payload))
            continue
        cards = _cards_for(views, step)
        # If the list has shrunk since, append rather than fail - the same
        # trade `reinsert` makes, and for the same reason. What this undo
        # proves is that the change's own cards are untouched, never that
        # their neighbourhood is; `equals_state_before` in the caller is
        # what tells the truth about the whole state.
        cards.insert(min(step.index, len(cards)), copy.deepcopy(step.payload))
    return result
```

- [ ] **Schritt 4: Test läuft**

Run: `python3 -m pytest tests/test_restore.py::test_an_edited_card_lands_back_on_the_right_card -v`
Expected: PASS

- [ ] **Schritt 5: Reihenfolge, Unversehrtheit und Verweigerung testen**

```python
def test_two_removals_in_one_list_do_not_shift_each_other():
    plan = analyze.plan_undo(_config([A]), _config([A, B, C]), _config([A, B, C]))
    result = restore.apply_undo(_config([A, B, C]), plan)
    assert result["views"][0]["cards"] == [A]


def test_a_move_comes_back_exactly_once():
    before = {"views": [{"path": "a", "cards": [A, B]}, {"path": "b", "cards": []}]}
    after = {"views": [{"path": "a", "cards": [A]}, {"path": "b", "cards": [B]}]}
    plan = analyze.plan_undo(before, after, after)
    result = restore.apply_undo(after, plan)
    assert result["views"][0]["cards"] == [A, B]
    assert result["views"][1]["cards"] == []


def test_the_input_is_not_modified_by_an_undo():
    original = _config([A, B])
    plan = analyze.plan_undo(_config([A]), original, original)
    restore.apply_undo(original, plan)
    assert original == _config([A, B])


def test_a_card_that_moved_away_since_is_refused():
    """The plan is made against one state and applied to another."""
    plan = analyze.plan_undo(_config([A]), _config([A, B]), _config([A, B]))
    with pytest.raises(LookupError, match="no longer where"):
        restore.apply_undo(_config([B, A]), plan)


def test_a_blocked_plan_refuses_loudly():
    plan = analyze.UndoPlan(blocked="nope")
    with pytest.raises(LookupError, match="nope"):
        restore.apply_undo(_config([A]), plan)


def test_two_cards_edited_and_swapped_come_back_in_order():
    """Both are edited, and they traded places in the same save.

    Written back in place this produces the two cards in the wrong
    order, and nothing refuses: each card really is standing where the
    plan expects it - the expectation just says nothing about where it
    belongs.
    """
    old0 = {"type": "tile", "entity": "light.a", "name": "Bett"}
    old1 = {"type": "tile", "entity": "light.b", "name": "Tisch"}
    new0 = {"type": "tile", "entity": "light.a", "name": "Bettlampe"}
    new1 = {"type": "tile", "entity": "light.b", "name": "Tischlampe"}
    plan = analyze.plan_undo(
        _config([old0, old1]), _config([new1, new0]), _config([new1, new0])
    )
    result = restore.apply_undo(_config([new1, new0]), plan)
    assert result["views"][0]["cards"] == [old0, old1]


def test_an_edit_and_a_move_in_one_save_both_land():
    """One card edited, another moved past it - the two paths together."""
    x = {"type": "gauge", "entity": "sensor.x", "min": 0}
    edited = {"type": "gauge", "entity": "sensor.x", "min": 5}
    before = _config([A, B, x])
    after = _config([edited, B, A])
    plan = analyze.plan_undo(before, after, after)
    assert plan.blocked is None
    result = restore.apply_undo(after, plan)
    assert result["views"][0]["cards"] == [A, B, x]
```

- [ ] **Schritt 6: Alles laufen lassen**

Run: `python3 -m pytest tests/ -q`
Expected: 218 + 8 = **226 passed**

- [ ] **Schritt 7: Commit**

```bash
git add custom_components/dashboard_history/restore.py tests/test_restore.py
git commit -m "$(cat <<'MSG'
Apply an undo in an order that cannot slip

Removals shift everything after them, insertions shift everything
from them on - so removals run highest index first, insertions lowest
index last. Done in any other order the steps write to the wrong
place, quietly. Each step also checks that what it was planned for is
still standing there: the plan was made a moment earlier, and a moment
is enough for a save.

There is no replacement step to order, because there is none: a card
is put back by being removed here and inserted there.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
)"
```

---

## Task 4: Der Weg nach draußen

**Files:**
- Modify: `custom_components/dashboard_history/operations.py`
- Modify: `custom_components/dashboard_history/websocket_api.py`
- Modify: `custom_components/dashboard_history/services.py`
- Modify: `custom_components/dashboard_history/services.yaml`

**Interfaces:**
- Consumes: `analyze.plan_undo`, `restore.apply_undo`, `store.previous_change`, `_state_at`, `_diff`, `_as_dict`, `explain_effect`, `async_get_config`, `async_save_config`, `async_known_keys`, `is_absent` — alle vorhanden.
- Produces: WebSocket-Befehl `dashboard_history/undo_change` und Dienst `dashboard_history.undo_change`, beide mit `{dashboard, revision, confirm}`. Antwort:
  `{"available": bool, "reason": str?, "applied": bool, "preview": str, "explanation": dict, "equals_state_before": bool}`.
  Task 5 baut darauf.

⚠️ **Eingetroffen am 2026-09-03, aus einer parallelen Sitzung.** In
`operations.py` gibt es jetzt `_keep_the_live_state(hass, store, key, current)`:
Es hält den Stand fest, der gleich überschrieben wird, meldet sich mit einer
Notiz statt einer Verweigerung, und **kündigt nichts an** — sonst lüde das Panel
mitten im Vorgang eine Historie nach, deren neuester Eintrag der gerade
ersetzte Stand ist. `async_restore_deleted` und `async_restore_state` rufen es
unmittelbar vor `async_save_config` auf, hinter dem `confirm`-Tor.

**`async_undo_change` ist die dritte schreibende Operation und muss es
genauso tun.** Eine der drei ohne Netz zu lassen wäre genau die Lücke, die
dieses Projekt teuer gelernt hat.

- [ ] **Schritt 1: Importe ergänzen**

```python
from .analyze import explain_change, explain_effect, find_removed, plan_undo
from .restore import apply_undo, reinsert
```

- [ ] **Schritt 2: `async_undo_change` schreiben**

Hinter `async_restore_state`:

```python
async def async_undo_change(
    hass: HomeAssistant,
    store: HistoryStore,
    key: str,
    revision: str,
    confirm: bool = False,
) -> dict:
    """Take one change back and keep everything since - if that is exact.

    The difference to `restore_state` is reach, not degree: this writes
    only the cards the change touched, that one replaces the dashboard.
    It is offered only where the plan can prove itself, and the proof is
    remade here on every call - including the confirming one. Somebody
    can save between seeing the preview and pressing the button, and
    writing a preview computed before that would throw their work away
    with a proof that was true a minute ago.
    """
    full, text, error = await _state_at(hass, store, key, revision)
    if error is not None:
        return {"available": False, "reason": error}

    before = await hass.async_add_executor_job(store.previous_change, key, full)
    if before is None:
        return {
            "available": False,
            "reason": "this is the first recorded state, so there is nothing "
            "before it to go back to",
        }
    _, before_text, error = await _state_at(hass, store, key, before)
    if error is not None:
        return {"available": False, "reason": error}

    known = await async_known_keys(hass)
    if is_absent(key, known):
        # Nothing to undo *into*. Bringing the whole dashboard back is a
        # different operation, and `restore_state` already offers it.
        return {"available": False, "reason": f"{key} does not exist right now"}

    current = await async_get_config(hass, key) or {}
    plan = await hass.async_add_executor_job(
        plan_undo, load(before_text) or {}, load(text) or {}, current
    )
    if plan.blocked is not None:
        return {"available": False, "reason": plan.blocked}
    try:
        result = await hass.async_add_executor_job(apply_undo, current, plan)
    except LookupError as err:
        return {"available": False, "reason": str(err)}

    diff = _diff(current, result, key)
    if not diff:
        return {"available": False, "reason": "this change is already taken back"}

    answer = {
        "available": True,
        "applied": False,
        "preview": diff,
        "explanation": _as_dict(explain_effect(current, result)),
        # Lets the panel drop the coarse "back to the state before this
        # change" button where it would write exactly the same thing.
        # Worked out here because it is a comparison, and a comparison in
        # the panel is logic in the panel.
        "equals_state_before": result == (load(before_text) or {}),
    }
    if not confirm:
        return answer
    # The state about to be overwritten, kept first - the same net the
    # other two writing operations got. It answers with a note rather
    # than a refusal: somebody who cannot be given a snapshot still gets
    # their undo, and is told.
    lost = await _keep_the_live_state(hass, store, key, current)
    await async_save_config(hass, key, result)
    answer["applied"] = True
    if lost:
        answer["note"] = lost
    return answer
```

- [ ] **Schritt 3: WebSocket-Befehl anmelden**

In `websocket_api.py`, in `_COMMANDS` hinter `restore_state`:

```python
    _command(
        f"{DOMAIN}/undo_change",
        {**_DASHBOARD, **_REVISION, vol.Optional("confirm", default=False): bool},
        operations.async_undo_change,
        lambda msg: {
            "key": msg["dashboard"],
            "revision": msg["revision"],
            "confirm": msg["confirm"],
        },
    ),
```

- [ ] **Schritt 4: Dienst anmelden**

In `services.py` neben `restore_state`:

```python
    async def undo_change(call: ServiceCall) -> dict:
        return await operations.async_undo_change(
            hass,
            store,
            call.data["dashboard"],
            call.data["revision"],
            bool(call.data.get("confirm")),
        )
```

Und in derselben Datei bei den `async_register_service`-Aufrufen nach dem Muster von `restore_state` eintragen — Name `undo_change`, `supports_response=SupportsResponse.ONLY`, Schema mit `dashboard`, `revision` und optionalem `confirm`. Vorher ansehen:

```bash
grep -n "restore_state" custom_components/dashboard_history/services.py
```

- [ ] **Schritt 5: `services.yaml` ergänzen**

Nach dem Muster von `restore_state`, mit Feldern `dashboard`, `revision`, `confirm`. Beschreibung auf Englisch:

```yaml
undo_change:
  name: Undo one change
  description: >-
    Take a single change back and keep everything saved since. Only
    offered when it is provably exact: the cards the change produced
    must still be in the dashboard, unchanged and only once. Without
    confirm it answers with a preview and writes nothing.
```

- [ ] **Schritt 6: Container neu starten und prüfen**

Der Container hält die Module seit seinem Start im Speicher. **Ohne Neustart ist `pytest` grün und die Integration läuft mit altem Code.**

```bash
docker compose -f docker/compose.yaml restart
```

Eine Minute warten, dann:

```bash
python3 tests/integration/run_checks.py
```

Expected: **91 von 91** — unverändert. Neue Prüfungen kommen in Task 6.

- [ ] **Schritt 7: Commit**

```bash
git add custom_components/dashboard_history/operations.py \
        custom_components/dashboard_history/websocket_api.py \
        custom_components/dashboard_history/services.py \
        custom_components/dashboard_history/services.yaml
git commit -m "$(cat <<'MSG'
Offer the undo as a service and a command

The proof is remade on the confirming call, not carried over from the
preview. Somebody can save in between, and writing a result computed
before that would throw their work away with a proof that was true a
minute ago.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
)"
```

---

## Task 5: Die Weiche in der Oberfläche

**Files:**
- Modify: `custom_components/dashboard_history/panel.js`
- Modify: `custom_components/dashboard_history/panel/style.js`
- Test: `tests/test_panel_assets.py` (läuft unverändert mit)

**Interfaces:**
- Consumes: `dashboard_history/undo_change` aus Task 4.
- Produces: nichts für spätere Aufgaben.

**Die Regel, die hier umgesetzt wird** (Entscheidung 15): Ein »Put back«-Knopf verschwindet aus genau zwei Gründen — der Undo holt genau dessen eine Karte und sonst nichts (**Deckungsgleichheit**), oder die Änderung hat außer dem Entfernen auch etwas **hinzugefügt** (**die Falle**, weil ein additives Zurückholen dort ein Duplikat erzeugt). Was aus *späteren* Änderungen fehlt, behält seinen Knopf immer.

- [ ] **Schritt 1: Den dritten Aufruf ergänzen**

`_detailFor` und `_take` ersetzen:

```javascript
  /** The three answers a row's detail is built from. */
  _detailFor(index) {
    const before = this._before(index);
    return Promise.all([
      before
        ? this._call("deleted_since", {
            dashboard: this._selected,
            revision: before,
          })
        : Promise.resolve({ items: [] }),
      this._call("explain", {
        dashboard: this._selected,
        revision: this._changes[index].revision,
      }),
      this._call("undo_change", {
        dashboard: this._selected,
        revision: this._changes[index].revision,
      }),
    ]);
  }

  _take(answers) {
    const [missing, explanation, undo] = answers || [null, null, null];
    this._items = missing ? missing.items || [] : [];
    this._explanation = explanation;
    this._undo = undo || null;
  }
```

Und in `_expand` sowie `_select` neben `this._explanation = null;` jeweils `this._undo = null;` ergänzen, damit kein Rest der vorigen Zeile stehen bleibt.

- [ ] **Schritt 2: Den Auslöser schreiben**

Neben `_restoreState`:

```javascript
  _undoChange(index) {
    this._confirm("Undo this change", (confirm) => [
      "undo_change",
      {
        dashboard: this._selected,
        revision: this._changes[index].revision,
        confirm,
      },
    ]);
  }
```

- [ ] **Schritt 3: `_renderSetBack` in eine Klappe legen**

Den Rumpf so ändern, dass er (a) den `apart`-Satz nicht mehr erzeugt, (b) den »before«-Knopf auslässt, wenn `equals_state_before` gilt, und (c) das Ganze in `<details>` einwickelt. Der Kopf der Methode wird:

```javascript
  /**
   * The coarse ways back, folded away.
   *
   * They used to stand beside the fine ones, and the first person to
   * meet them read them as two labels for one action - fairly, because
   * in the case they met (newest change, one deleted card) that is
   * exactly what they were. Since decision 15 the row leads with the
   * targeted undo, and these are the escape hatch: replace the whole
   * dashboard, everything since gone. Folded, not removed - it is a
   * real capability and somebody wants it about once a year.
   *
   * The "before" button is left out when it would write exactly what
   * the undo writes. The server says so with `equals_state_before`; the
   * panel does not compare states, because a comparison here is logic
   * here.
   */
  _renderSetBack(index) {
    const before = this._before(index);
    const buttons = [];
    const same = this._undo?.available && this._undo.equals_state_before;
    if (before && !this._changes[index + 1]?.same_as_now && !same)
      buttons.push({
        revision: before,
        label: "Back to the state before this change",
      });
    if (!this._changes[index]?.same_as_now)
      buttons.push({
        revision: this._changes[index].revision,
        label: "Back to the state after this change",
      });

    const why =
      before && this._changes[index + 1]?.same_as_now
        ? `<span class="why">The state before this change is what the
            dashboard holds now — nothing to set back.</span>`
        : "";
    if (!buttons.length) return why;
    return `<details class="more">
        <summary>Replace the whole dashboard instead</summary>
        <p class="why" style="margin-top:8px">Setting a state back replaces
          the whole dashboard with how it was then. Everything saved since
          is no longer what the dashboard holds.</p>
        <div class="backto">
          ${buttons
            .map(
              (b) =>
                `<button class="act ghost" data-state="${escape(b.revision)}"
                  >${b.label}</button>`,
            )
            .join("")}
        </div>${why}
      </details>`;
  }
```

- [ ] **Schritt 4: Die Weiche in `_renderDetail`**

Den Teil ab `const list = …` bis zum `return` ersetzen:

```javascript
    // Which of the missing items the undo takes care of. Two reasons,
    // and only these two - decision 15:
    //
    // "covered": the undo restores exactly this one item and does
    // nothing else. That is one shape only, a change that deleted a
    // single thing, and it is the shape somebody reported as confusing
    // because the two buttons there really do the same work.
    //
    // "trap": the change also *added* something. Then a plain put-back
    // is not merely redundant, it is wrong: an edit whose key field was
    // touched reads as one removal plus one addition, and adding the old
    // card back leaves both versions standing. Measured, not feared.
    const undo = this._undo?.available ? this._undo : null;
    const added = /\d+ added/.test(this._changes[index]?.message || "");
    const mine = new Set(
      (this._explanation?.groups || [])
        .flatMap((group) => group.entries)
        .filter((entry) => entry.what === "removed")
        .map((entry) => entry.label),
    );
    const swallowed = (item) =>
      undo && mine.has(item.label) && (added || mine.size === 1);
    const own = this._items.filter((item) => !swallowed(item));

    const rows = own
      .map(
        (item) => `
        <div class="item">
          <span class="label">${escape(item.label)}
            <span class="where">${escape(item.kind)}${item.view ? ` · view ${escape(item.view)}` : ""}</span>
          </span>
          <button class="act" data-restore="${item.position}">Put back</button>
        </div>`,
      )
      .join("");
    // Named when the undo has taken the rest off the list: otherwise the
    // remaining rows read as "this change deleted these", which is then
    // exactly wrong.
    const heading =
      own.length && own.length < this._items.length
        ? `<p class="why" style="margin-top:16px">Also missing since then,
             from later changes:</p>`
        : "";
    const list = rows
      ? heading + rows
      : undo
        ? ""
        : `<p class="muted">Nothing from before this change is missing today.</p>`;

    const kept = index === 0 ? "" : ` and keeps the ${index} change${index === 1 ? "" : "s"} made since`;
    const offer = undo
      ? `<div class="backto">
           <button class="act" data-undo="${index}">Undo this change</button>
         </div>
         <p class="why" style="margin-top:8px">Puts this change back${kept}.</p>`
      : `<p class="why">This change cannot be taken back exactly:
           ${escape(this._undo?.reason || "no reason given")}.</p>`;

    return `<div class="detail">
      ${plain}
      ${offer}
      ${list}
      ${this._renderSetBack(index)}
      ${this._renderMakeVersion(index)}
    </div>`;
```

Und den Aufruf `this._renderSetBack(index, this._items.length > 0)` weiter oben (der Zweig »erster aufgezeichneter Stand«) auf `this._renderSetBack(index)` kürzen — das zweite Argument gibt es nicht mehr.

- [ ] **Schritt 5: Den Klick anmelden**

Bei den anderen `querySelectorAll`-Blöcken:

```javascript
    root.querySelectorAll("[data-undo]").forEach((element) =>
      element.addEventListener("click", (event) => {
        event.stopPropagation();
        this._undoChange(Number(element.dataset.undo));
      }),
    );
```

- [ ] **Schritt 6: Die Klappe gestalten**

In `panel/style.js`, **ohne ein einziges Backtick**, vor der schließenden Zeile:

```css
  details.more { margin-top: 16px; }
  details.more > summary {
    color: var(--secondary-text-color, #727272);
    font-size: 13px;
    cursor: pointer;
  }
  details.more > summary:hover { color: var(--primary-text-color, #212121); }
```

- [ ] **Schritt 7: Beide Dateien syntaktisch prüfen**

**Beide**, nicht nur `panel.js`. Ein Backtick in `style.js` hat das Panel schon einmal ganz umgebracht, und `node --check` auf der falschen Datei hat es nicht gefunden:

```bash
node --check custom_components/dashboard_history/panel.js
node --check custom_components/dashboard_history/panel/style.js
python3 -m pytest tests/test_panel_assets.py -v
```

Expected: beide ohne Ausgabe, die Wächter grün.

- [ ] **Schritt 8: Am lebenden Panel ansehen**

```bash
docker compose -f docker/compose.yaml restart
pkill -f "chrome-[p]rofile"   # Zeichenklasse noetig, sonst trifft pkill die eigene Shell
sleep 60
python3 tests/integration/look_at_panel.py
```

Zu prüfen: eine Zeile mit `1 edited` zeigt **Undo this change**, keine Put-back-Liste und die zugeklappte Zeile; eine Zeile mit mehreren Löschungen zeigt Undo **und** alle einzelnen Knöpfe.

- [ ] **Schritt 9: Commit**

```bash
git add custom_components/dashboard_history/panel.js \
        custom_components/dashboard_history/panel/style.js
git commit -m "$(cat <<'MSG'
Offer one way back per row, not two names for one

The two buttons were reported as confusing, and fairly: in the case
they were met in - newest change, one deleted card - they did the same
work. Now a row leads with the undo where it is exact, keeps the
per-item buttons where they still reach something the undo does not,
and folds the whole-dashboard route away.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
)"
```

---

## Task 6: Der Prüfstand

**Files:**
- Modify: `tests/integration/run_checks.py`

**Interfaces:**
- Consumes: alles aus Task 1–5.
- Produces: nichts.

**Warum das die wichtigste Aufgabe ist:** `pytest` erreicht `operations.py`, `websocket_api.py` und `panel.js` strukturell nicht — und **dort lag jeder bisher gefundene Fehler dieses Projekts**.

- [ ] **Schritt 1: `run_undo` schreiben**

Nach `run_moves`, im selben Muster (eigener, genau benannter Schlüssel; nie über ein Präfix löschen):

```python
async def run_undo(access: str) -> None:
    """Taking one change back while keeping the ones after it.

    pytest settles the arithmetic. What it cannot reach is the path a
    person travels: Home Assistant saves, the recorder commits, the
    panel asks, and only then does anything get written back.
    """
    key = "dh-undo-check"
    keep = {"type": "markdown", "content": "Untouched"}
    first = {"type": "markdown", "content": "Card one\n\nOriginal body"}
    edited = {"type": "markdown", "content": "Card one\n\nEdited body"}
    later = {"type": "markdown", "content": "Added afterwards"}

    def state(cards):
        return {"views": [{"path": "a", "title": "A", "cards": list(cards)}]}

    async def save(socket, cards):
        await socket.call("lovelace/config/save", url_path=key, config=state(cards))
        await asyncio.sleep(4)

    async def newest(socket):
        answer = await socket.call("dashboard_history/history", dashboard=key)
        return answer["changes"][0]["revision"]

    async with Socket(access) as socket:
        listed = (await socket.call("lovelace/dashboards/list")) or []
        if not any(entry.get("url_path") == key for entry in listed):
            await socket.call(
                "lovelace/dashboards/create", url_path=key, title="DH Undo"
            )
            await asyncio.sleep(4)

        await save(socket, [keep, first])
        await save(socket, [keep, edited])
        the_edit = await newest(socket)
        await save(socket, [keep, edited, later])

        answer = await socket.call(
            "dashboard_history/undo_change", dashboard=key, revision=the_edit
        )
        check(
            "an edit two saves back is still exactly undoable",
            answer.get("available") is True,
            answer.get("reason", ""),
        )
        check(
            "the preview writes nothing without confirm",
            answer.get("applied") is False and bool(answer.get("preview")),
        )
        live = await socket.call("lovelace/config", url_path=key)
        check(
            "the dashboard is untouched after a preview",
            live["views"][0]["cards"] == [keep, edited, later],
        )

        answer = await socket.call(
            "dashboard_history/undo_change",
            dashboard=key,
            revision=the_edit,
            confirm=True,
        )
        await asyncio.sleep(4)
        live = await socket.call("lovelace/config", url_path=key)
        check(
            "the undo restores the old card and keeps the later one",
            live["views"][0]["cards"] == [keep, first, later],
            str(live["views"][0]["cards"]),
        )
        check(
            "the undo leaves exactly one copy, not two",
            len(live["views"][0]["cards"]) == 3,
        )

        # The control. Edit the same card twice, then ask for the first
        # edit back: there is no exact version left, and a tool that said
        # yes here would overwrite the second edit.
        await save(socket, [keep, first, later])
        await save(socket, [keep, edited, later])
        once = await newest(socket)
        await save(socket, [keep, {"type": "markdown", "content": "Card one\n\nThird body"}, later])
        answer = await socket.call(
            "dashboard_history/undo_change", dashboard=key, revision=once
        )
        check(
            "a card edited again since refuses the undo",
            answer.get("available") is False
            and "changed again" in (answer.get("reason") or ""),
            answer.get("reason", ""),
        )
```

- [ ] **Schritt 2: Im Hauptblock anmelden**

Vor der Ergebniszeile:

```python
    print("\n  -- Eine Aenderung gezielt zuruecknehmen --")
    asyncio.run(run_undo(access))
```

- [ ] **Schritt 3: Container neu starten und laufen lassen**

```bash
docker compose -f docker/compose.yaml restart
sleep 60
python3 tests/integration/run_checks.py
```

Expected: **97 von 97**. Ein Fehlschlag unmittelbar nach dem Neustart ist Prüfstand-Schaden, kein Befund — dann eine Minute warten und wiederholen.

- [ ] **Schritt 4: Gesamtlauf**

```bash
python3 -m pytest tests/ -q
node --check custom_components/dashboard_history/panel.js
node --check custom_components/dashboard_history/panel/style.js
```

Expected: **226 passed** (plus was in den Aufgaben dazukam), beide `node --check` stumm.

- [ ] **Schritt 5: Commit**

```bash
git add tests/integration/run_checks.py
git commit -m "$(cat <<'MSG'
Drive the undo over the path a person takes

pytest cannot reach operations, the WebSocket layer or the panel, and
every bug this project has found lived in exactly that gap. The
control matters more than the happy case: a card edited twice must
refuse, because saying yes there overwrites the second edit.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
)"
```

---

## Selbstprüfung des Plans

**Abdeckung von Entscheidung 15:**

| Zusage der Spec | Aufgabe |
|---|---|
| Zähler-Regel, genau einmal | 1 |
| Alles-oder-nichts | 1 (Schritt 5, `return` bei erster Verweigerung) |
| Verweigerung nennt Grund und Karte | 1 (Schritt 5, `sole`) |
| Bereits zurück → nichts tun | 1 (Schritt 7) |
| Wohin eine Karte zurückkommt | 1 (Schritt 5, `remove` + `insert`) |
| Ganze Views | 2 |
| Reihenfolge beim Anwenden | 3 |
| Neuberechnung beim Bestätigen | 4 |
| `equals_state_before` | 4, benutzt in 5 |
| Weiche, zwei Gründe fürs Verschwinden | 5 |
| Spätere Verluste behalten ihren Knopf | 5 (`heading`) |
| Klappe für die groben Wege | 5 |

**Offen gelassen, mit Absicht:** Beschriftungen (Titel/Symbol) — `restore_state` schreibt sie ohnehin nicht. Die Duplikat-Falle dort, wo der Undo verweigert. Die beiden Fenster-Fehler (Version außerhalb der 50, Dashboard außerhalb der 1000) — sie stehen unter »Offene Punkte« der Spec und gehören nicht in dieses Vorhaben.

**Nachgetragen am 2026-09-03, vor der Umsetzung gemessen:** Der erste Entwurf dieses Plans setzte eine bearbeitete Karte mit einem `replace`-Schritt an der *heutigen* Stelle zurück. Das ist falsch, und der `expect`-Wächter fängt es nicht ab: Er prüft, ob dort noch dieselbe Karte steht — nicht, ob das der richtige Zielort ist. Weil `_place` den Index absichtlich auslässt, meldet `match_cards` eine Karte, die bearbeitet **und** verschoben wurde, als bearbeitet; beide Prüfungen gehen dann durch, und geschrieben wird die falsche Reihenfolge. In einem Nachbau über 6000 erzeugte Historien gemessen: **48** stillschweigend falsche Ergebnisse mit `replace`, **0** mit `remove` + `insert` — bei genau gleich vielen Verweigerungen (309 zu 309). Die zwei Schritte sind also strikt besser, nicht bloß vorsichtiger. Damit entfällt die Aktion `replace` aus `UndoStep` ganz; Views kannten sie ohnehin nie.

**Ein Risiko, benannt:** Die Erkennung »was hat diese Änderung entfernt« in Task 5 liest die Erklärung (`entry.what === "removed"`) statt einer eigenen Angabe des Servers. Das ist derselbe Griff, den die Spec unter »Offene Punkte« schon als unsauber notiert hat (»Textschnüffelei«). Hier trifft es keine Sicherheitsfrage, sondern nur, ob ein Knopf steht — aber wenn beim Bauen auffällt, dass es klemmt, ist die saubere Lösung, `undo_change` die Etiketten seiner eigenen Schritte mitliefern zu lassen (`plan.steps[].label`). Das ist eine Zeile in Task 4 und eine in Task 5.
