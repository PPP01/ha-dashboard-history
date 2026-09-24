# Parken statt verweigern – Umsetzungsplan (Vorhaben L, Issue #30)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eine gezielte Rücknahme in einer Sections-Ansicht verweigert nicht mehr, nur weil sich die Sections *seit* der Änderung verschoben haben – sie entfernt wie bisher über den Fingerabdruck und legt jede Karte, deren alte Section sich nicht mehr beweisen lässt, in HAs »Imported cards« (`cards:` der Ansicht) ab; der Knopf heißt dann »Undo this change\*«. »Put back« tut dasselbe und bekommt dafür einen Section-Anker, der tatsächlich etwas beweist.

**Architecture:** `analyze._sections_lie` (dashboardweit, ja/nein) wird durch `analyze._section_drift` ersetzt, das je Ansicht zwischen »von dieser Änderung umgebaut« (verweigert weiter) und »seither verschoben« (Einsetzen wird geparkt) unterscheidet. Ein geparktes Einsetzen ist ein `UndoStep` mit `parked=True` und `location=("cards",)`, den `restore.apply_undo` anhängt statt an einen Index zu schreiben. Für »Put back« entscheidet `operations._reinsertion` über zwei neue Funktionen `restore.parks`/`restore.park`; `restore.reinsert` selbst bleibt unverändert verweigernd. Das Panel liest ein neues Feld `parked` (Liste von Beschriftungen) aus beiden Antworten.

**Tech Stack:** Python 3 (Kernmodule HA-frei, reines pytest), `operations.py`/`websocket_api.py` mit Home Assistant (geprüft über `tests/integration/run_checks.py` am Testcontainer), `panel.js` ohne Build-Schritt (Logik unter Node in `tests/test_panel_behaviour.py`).

**Spec:** `docs/superpowers/specs/2026-09-24-importierte-karten-design.md`. Zuerst lesen, dazu Entscheidung 15 und 26 der Haupt-Spec (`docs/superpowers/specs/2026-08-30-dashboard-history-design.md`, Abschnitte 15 und 26). Die Festlegungen im Abschnitt »Entscheidungen« der Spec hat der Nutzer am 2026-09-24 bestätigt (Punkt 3 geändert: der Undo parkt auch in pfadlosen Ansichten); dieser Plan setzt sie so um.

## Global Constraints

- `analyze.py` und `restore.py` importieren nie `homeassistant`. `restore.py` importiert `analyze` nicht zur Laufzeit (nur unter `TYPE_CHECKING`, siehe Dateikopf).
- Test-Befehl für alles HA-freie: `python3 -m pytest tests/ -v`. Nach jedem Task die **ganze** Suite; nur »0 failed« zählt, die Zahl der bestandenen Tests schwankt mit der echten Prüfbank.
- Laufende Instanz: `docker compose -f docker/compose.yaml up -d`, dann `python3 tests/integration/run_checks.py` (Einrichtung: `docker/README.md`). Nie während eines HA-Neustarts pollen; kein Test löscht nach Präfix.
- Code, Kommentare, Docstrings, UI-Texte, Commit-Messages: Englisch. Design-Journal (`docs/superpowers/`): Deutsch mit echten Umlauten und »…«.
- Commit-Format: englischer Imperativ, Betreff ≤ 50 Zeichen, Leerzeile, Body ≤ 72 Zeichen je Zeile mit dem *Warum*, Verweis auf `#30`. **Committet wird erst nach ausdrücklichem Go des Nutzers** (globale Regel des Nutzers); die Commit-Schritte unten markieren nur die Schnitte.
- UI-Wortlaut aus der Spec, wörtlich: Knopf `Undo this change*`, Begriff `"Imported cards"`.
- Kein Parken in Masonry-/Sidebar-/Panel-Ansichten, keins für `kind="section"`. Der Undo parkt auch in pfadlosen Ansichten (sie haben vorher `_positions_lie` bestanden); »Put back« parkt dort **nicht**, weil `reinsert` eine pfadlose Ansicht nicht beweist.

## Review Focus

1. **Eine Ansicht ohne `cards:`-Schlüssel oder mit `cards: null`** – das ist der Normalfall einer Sections-Ansicht (Prüfbank: 27 von 27). Erwartung: Die Liste wird angelegt, nicht `LookupError`. Test in Task 2.
2. **Mehrere geparkte Karten aus verschiedenen Sections in einer Rücknahme** – Erwartung: Sie landen in der Reihenfolge ihrer alten Plätze, nach jeder gewöhnlichen Einsetzung in dieselbe Liste. Tests in Task 1 und Task 2.
3. **Speichern zwischen Vorschau und Bestätigen**, sodass der neue Plan parkt, die Vorschau aber nicht – Erwartung: nichts wird geschrieben, der Grund wird genannt. Prüfung in Task 5 (laufende Instanz).
4. **Eine Karte, die schon in »Imported cards« lag** und zurückkommt – Erwartung: an ihren Index in `cards:`, nie »geparkt«, kein Sternchen. Test in Task 1.
5. **Put back zweier Karten derselben Section nacheinander** – Erwartung: Die zweite geht nach dem Zurückholen der ersten weiterhin exakt zurück, weil `_removed_since` bei jedem Aufruf gegen den heutigen Stand neu rechnet. Test in Task 4.

---

## Files touched

| Datei | Rolle |
|---|---|
| `custom_components/dashboard_history/analyze.py` | `UndoStep.parked`, `UndoPlan.parked`; `_section_drift` ersetzt `_sections_lie`; `_SECTIONS_REBUILT_REFUSAL`; Parken in `plan_undo`; `_section_name` nennt »Imported cards«; `_section_anchor` trägt Einstellungen und Nachbarkarten |
| `custom_components/dashboard_history/restore.py` | `apply_undo` hängt geparkte Schritte an; `_anchor_holds` prüft den neuen Anker; neue Funktionen `parks`, `park` |
| `custom_components/dashboard_history/operations.py` | `async_undo_change`: Feld `parked`, Parameter `expected_parked`; `_reinsertion`/`async_restore_deleted`: Feld `parked` |
| `custom_components/dashboard_history/websocket_api.py` | `undo_change` nimmt `expected_parked` |
| `custom_components/dashboard_history/panel.js` | Sternchen und Hinweis an der Aktionsleiste; Absatz über geparkte Karten im Dialog; Bestätigung schickt `expected_parked` |
| `tests/test_analyze.py`, `tests/test_restore.py`, `tests/test_panel_behaviour.py` | neue Tests |
| `tests/integration/run_checks.py` | neuer Abschnitt `run_parking`; ein bestehender Fall mit neuer Erwartung |
| `docs/limitations.md`, `docs/how-it-works.md`, `docs/user-guide.md`, `docs/superpowers/status.md`, Haupt-Spec Entscheidung 26 | Stand nachziehen |

---

### Task 1: `analyze.py` – Section-Prüfung je Ansicht, Parken im Plan

**Files:**
- Modify: `custom_components/dashboard_history/analyze.py` (`UndoStep`, `UndoPlan`, `_sections_lie` → `_section_drift`, Konstanten, `plan_undo`)
- Test: `tests/test_analyze.py`

**Interfaces:**
- Produces: `UndoStep.parked: bool = False`; `UndoPlan.parked -> tuple[str, ...]` (Property, Beschriftungen der geparkten Schritte in Planreihenfolge); `_section_drift(before, after, current) -> tuple[set, set]` (`rebuilt`, `shifted`, je Mengen von Ansichtsschlüsseln); `_SECTIONS_REBUILT_REFUSAL: str`. Ein geparkter Schritt hat `action="insert"`, `kind="card"`, `location=("cards",)`, `expect=None`, `payload` = alte Karte, `label=_describe(alte Karte)`, `view_path` gesetzt.

- [ ] **Step 1: Tests schreiben**

Ans Ende des Abschnitts `# -- positions are not identities` in `tests/test_analyze.py` (nach `test_undo_refuses_when_two_untitled_sections_swap_settings`):

```python
# -- sections that moved since: park, do not refuse (GitHub #30) ---------

BETT = {"type": "tile", "entity": "light.x", "name": "Bett"}
BETTLAMPE = {"type": "tile", "entity": "light.x", "name": "Bettlampe"}


def _sectioned(*sections, path="home", **extra):
    view = {"type": "sections", "sections": [dict(s) for s in sections], **extra}
    if path is not None:
        view["path"] = path
    return view


def test_an_edit_whose_section_moved_since_is_parked():
    """Decision 26: the card cannot be proven to belong at index 1 any more.

    The change only edited a card. A section was put in front of it
    afterwards. Taking the edited card out is exact - it is found by its
    fingerprint - but where the old one goes back in is not, so it goes
    into the view's own `cards:`, Home Assistant's "Imported cards".
    """
    before = {"views": [_sectioned({"cards": [BETT]})]}
    after = {"views": [_sectioned({"cards": [BETTLAMPE]})]}
    current = {"views": [_sectioned({"column_span": 2, "cards": []}, {"cards": [BETTLAMPE]})]}
    plan = analyze.plan_undo(before, after, current)
    assert plan.blocked is None
    assert [(s.action, s.location, s.index, s.parked) for s in plan.steps] == [
        ("remove", ("sections", 1, "cards"), 0, False),
        ("insert", ("cards",), 0, True),
    ]
    assert plan.steps[1].payload == BETT
    assert plan.parked == ("tile: Bett",)


def test_sections_that_moved_in_another_view_do_not_block():
    """The check used to cover the whole dashboard; now it covers a view."""
    other = {"path": "a", "cards": [A]}
    moved = _sectioned({"cards": [B]}, path="s")
    moved_since = _sectioned({"cards": [B]}, {"column_span": 2, "cards": []}, path="s")
    plan = analyze.plan_undo(
        {"views": [other, moved]},
        {"views": [{"path": "a", "cards": []}, moved]},
        {"views": [{"path": "a", "cards": []}, moved_since]},
    )
    assert plan.blocked is None
    assert plan.parked == ()
    assert [(s.action, s.location, s.payload) for s in plan.steps] == [
        ("insert", ("cards",), A)
    ]


def test_only_removals_in_a_shifted_view_stay_exact():
    """Nothing goes back in, so there is nothing whose place is in doubt."""
    before = {"views": [_sectioned({"cards": [A]})]}
    after = {"views": [_sectioned({"cards": [A, B]})]}
    current = {"views": [_sectioned({"column_span": 2, "cards": []}, {"cards": [A, B]})]}
    plan = analyze.plan_undo(before, after, current)
    assert plan.blocked is None
    assert plan.parked == ()
    assert [(s.action, s.location, s.index) for s in plan.steps] == [
        ("remove", ("sections", 1, "cards"), 1)
    ]


def test_a_pathless_view_whose_sections_moved_parks_too():
    """Reaching the section check means `_positions_lie` already vouched
    for the view - the same proof an ordinary insert into it relies on.

    Two views, so the single-view rule of #33 does not decide it: here
    the unchanged title is what lets the position check pass. Without
    it the view's changed content would refuse first, for a reason of
    its own (`test_…_without_its_title_refuses_by_position` below)."""
    first = {"path": "a", "cards": [A]}
    before = {"views": [first, _sectioned({"cards": [BETT]}, path=None, title="Home")]}
    after = {"views": [first, _sectioned({"cards": [BETTLAMPE]}, path=None, title="Home")]}
    current = {"views": [first, _sectioned({"column_span": 2, "cards": []}, {"cards": [BETTLAMPE]},
                                           path=None, title="Home")]}
    plan = analyze.plan_undo(before, after, current)
    assert plan.blocked is None
    parked = [s for s in plan.steps if s.parked]
    assert [(s.view_path, s.view_index, s.location) for s in parked] == [(None, 1, ("cards",))]


def test_a_pathless_view_whose_sections_moved_without_its_title_refuses_by_position():
    """The control for the test above: the title is what decided it."""
    first = {"path": "a", "cards": [A]}
    before = {"views": [first, _sectioned({"cards": [BETT]}, path=None)]}
    after = {"views": [first, _sectioned({"cards": [BETTLAMPE]}, path=None)]}
    current = {"views": [first, _sectioned({"column_span": 2, "cards": []}, {"cards": [BETTLAMPE]},
                                           path=None)]}
    plan = analyze.plan_undo(before, after, current)
    assert plan.blocked is not None
    assert "URL path" in plan.blocked


def test_a_change_that_rebuilt_the_sections_says_so():
    """Parking answers "where does this card go", not "what did the view look like"."""
    old = {"views": [_sectioned({"cards": [B]})]}
    new = {"views": [_sectioned({"column_span": 2, "cards": [C]}, {"cards": [B]})]}
    plan = analyze.plan_undo(old, new, new)
    assert plan.blocked is not None
    assert "this change rearranged the sections" in plan.blocked


def test_a_card_from_imported_cards_goes_back_to_its_index_not_parked():
    before = {"views": [_sectioned({"cards": [B]}, cards=[A])]}
    after = {"views": [_sectioned({"cards": [B]}, cards=[])]}
    current = {"views": [_sectioned({"column_span": 2, "cards": []}, {"cards": [B]}, cards=[])]}
    plan = analyze.plan_undo(before, after, current)
    assert plan.blocked is None
    assert [(s.action, s.location, s.index, s.parked) for s in plan.steps] == [
        ("insert", ("cards",), 0, False)
    ]


def test_several_parked_cards_keep_the_order_of_their_old_places():
    before = {"views": [_sectioned({"cards": [A]}, {"cards": [B]})]}
    after = {"views": [_sectioned({"cards": []}, {"cards": []})]}
    current = {"views": [_sectioned({"cards": []}, {"cards": []}, {"column_span": 2, "cards": []})]}
    plan = analyze.plan_undo(before, after, current)
    assert plan.blocked is None
    assert plan.parked == ("tile: light.a", "tile: light.b")


def test_parked_cards_of_two_views_stay_grouped_by_view():
    """The dialog lists them; interleaving two views' cards reads as noise."""
    p_before = _sectioned({"cards": [A]}, {"cards": [B]}, path="p")
    q_before = _sectioned({"cards": [C]}, path="q")
    p_after = _sectioned({"cards": []}, {"cards": []}, path="p")
    q_after = _sectioned({"cards": []}, path="q")
    p_now = _sectioned({"cards": []}, {"cards": []}, {"column_span": 2, "cards": []}, path="p")
    q_now = _sectioned({"cards": []}, {"column_span": 2, "cards": []}, path="q")
    plan = analyze.plan_undo(
        {"views": [p_before, q_before]},
        {"views": [p_after, q_after]},
        {"views": [p_now, q_now]},
    )
    assert plan.parked == ("tile: light.a", "tile: light.b", "tile: light.c")
```

- [ ] **Step 2: Tests laufen lassen, Scheitern prüfen**

Run: `python3 -m pytest tests/test_analyze.py -k "parked or parks_too or shifted or moved_in_another or rebuilt or imported_cards or old_places" -v`
Expected: FAIL – `AttributeError: 'UndoStep' object has no attribute 'parked'` bzw. Verweigerungen mit `_SECTION_REFUSAL`, wo `None` erwartet wird.

- [ ] **Step 3: `UndoStep` und `UndoPlan` erweitern**

In `analyze.py`, an `UndoStep` nach `label: str`:

```python
    # Decision 26: an insertion whose section cannot be proven any more
    # goes to the end of the view's own `cards:` - Home Assistant's
    # "Imported cards" - instead of to an index. `location` is then
    # ("cards",), and `index` only keeps the order of the old place.
    parked: bool = False
```

An `UndoPlan` nach `steps: tuple = ()`:

```python
    @property
    def parked(self) -> tuple[str, ...]:
        """What this plan cannot put back exactly, only make available."""
        return tuple(step.label for step in self.steps if step.parked)
```

- [ ] **Step 4: `_sections_lie` durch `_section_drift` ersetzen**

Die Funktion `_sections_lie` vollständig löschen und an ihrer Stelle einfügen:

```python
def _section_drift(before: dict, after: dict, current: dict) -> tuple[set, set]:
    """Which views' sections cannot be trusted, and in which of two ways.

    `rebuilt`: the change itself altered the run of sections - added,
    removed, swapped or re-set one. Undoing that means rebuilding the
    sections, which no card step does, so it stays a refusal.

    `shifted`: the change left the sections alone, but they have moved
    since. A card can still be taken out exactly - it is found by its
    fingerprint - but where one goes back in cannot be proven any more,
    so an insertion there is parked in the view's own `cards:` (decision
    26, GitHub #30).

    Per view, not per dashboard: a section moved in one view says nothing
    about an index in another. Two sections that agree on every setting
    and differ only in their cards still slip through, as before (#31).
    """
    old, new, now = (dict(_views_by_key(state)) for state in (before, after, current))
    rebuilt: set = set()
    shifted: set = set()
    for key in set(old) & set(new):
        marks = _section_marks(new[key])
        if _section_marks(old[key]) != marks:
            rebuilt.add(key)
        elif key in now and _section_marks(now[key]) != marks:
            shifted.add(key)
    return rebuilt, shifted
```

Den Docstring von `_view_type_changed` anpassen: `exactly what \`_sections_lie\` reacts to` → `exactly what \`_section_drift\` reacts to`. Ebenso den Kommentar in `plan_undo` direkt über der Typprüfung: `# Checked before \`_sections_lie\`: a conversion changes the section` → `# Checked before \`_section_drift\`: a conversion changes the section`. Danach prüfen, dass kein Verweis übrig ist:

Run: `grep -n "_sections_lie\|_SECTION_REFUSAL" custom_components/dashboard_history/*.py tests/*.py`
Expected: keine Ausgabe.

Die Konstante `_SECTION_REFUSAL` durch diese ersetzen – nach dem Umbau verweigert keine Stelle mehr mit ihr, denn verschobene Sections parken jetzt auch in pfadlosen Ansichten (Nachprüfung, Nebenbefund):

```python
_SECTIONS_REBUILT_REFUSAL = (
    "this change rearranged the sections of a view itself, and a section "
    "has no path to recognise it by, so an exact undo cannot rebuild them "
    "- a version or a whole-state restore covers it"
)
```

- [ ] **Step 5: `plan_undo` umbauen**

Die Zeilen

```python
    if any(_sections_lie(one, other) for one, other in pairs):
        return UndoPlan(blocked=_SECTION_REFUSAL)
```

ersetzen durch

```python
    rebuilt, shifted = _section_drift(before, after, current)
    if rebuilt:
        return UndoPlan(blocked=_SECTIONS_REBUILT_REFUSAL)
```

Direkt nach `steps: list[UndoStep] = []` einfügen:

```python
    parked: list[tuple[int, tuple, int, UndoStep]] = []

    def put_back(old_slot: Slot, label: str) -> None:
        """Insert where the card came from, or park it in "Imported cards"."""
        if old_slot.view_key not in shifted or old_slot.location[:1] != ("sections",):
            steps.append(_step(old_slot, "insert", None, old_slot.card, label))
            return
        # A pathless view is found by its position here, which
        # `_positions_lie` above has already vouched for - the same proof
        # an ordinary insert into it rests on.
        parked.append(
            (
                old_slot.view_index,
                old_slot.location,
                old_slot.index,
                UndoStep(
                    action="insert",
                    kind="card",
                    view_path=old_slot.view.get("path"),
                    view_index=old_slot.view_index,
                    location=("cards",),
                    index=old_slot.index,
                    expect=None,
                    payload=old_slot.card,
                    # The card that is parked, not the one taken out: the
                    # dialog lists what somebody has to go and place.
                    label=_describe(old_slot.card),
                    parked=True,
                ),
            )
        )
```

In der Schleife über `(*matching.edited, *matching.moved)` die Zeile

```python
        steps.append(_step(old_slot, "insert", None, old_slot.card, label))
```

ersetzen durch

```python
        put_back(old_slot, label)
```

In der Schleife über `matching.removed` den `steps.append(_step(old_slot, "insert", …))`-Aufruf ersetzen durch

```python
        put_back(old_slot, _describe(old_slot.card))
```

Direkt nach dieser Schleife, vor dem Kommentar `# Whole views, which \`match_cards\` leaves out on purpose`:

```python
    # In the order of the places they came from - view, section, card -
    # whichever of the three tables in decision 15 produced them.
    steps.extend(item[3] for item in sorted(parked, key=lambda item: item[:3]))
```

- [ ] **Step 6: Tests laufen lassen**

Run: `python3 -m pytest tests/test_analyze.py -v`
Expected: PASS, einschließlich der unveränderten `test_undo_refuses_when_a_section_was_inserted_before_another` und `test_undo_refuses_when_two_untitled_sections_swap_settings` (beide sind »von der Änderung umgebaut« und enthalten weiterhin »section«).

- [ ] **Step 7: Ganze Suite**

Run: `python3 -m pytest tests/ -v`
Expected: 0 failed.

- [ ] **Step 8: Commit (nach Go des Nutzers)**

```bash
git add custom_components/dashboard_history/analyze.py tests/test_analyze.py
git commit -m "Park cards whose section moved since the change" -m "A section moved in one view used to refuse every undo on the whole
dashboard. The check is per view now: a change that rebuilt its own
sections still refuses, but one whose sections only moved afterwards
takes cards out by fingerprint and parks what goes back in, in the
view's own cards list - Home Assistant's \"Imported cards\". Decision
26, GitHub #30."
```

---

### Task 2: `restore.apply_undo` – geparkte Schritte anhängen

**Files:**
- Modify: `custom_components/dashboard_history/restore.py` (`apply_undo`)
- Test: `tests/test_restore.py`

**Interfaces:**
- Consumes: `UndoStep.parked` (Task 1).
- Produces: `apply_undo` hängt jeden Schritt mit `parked=True` in Planreihenfolge ans Ende von `view["cards"]` der per `_find_view` gefundenen Ansicht, nach allen nicht geparkten Einsetzungen; legt die Liste an, wenn sie fehlt oder `null` ist, und verweigert mit `LookupError`, wenn dort etwas anderes steht.

- [ ] **Step 1: Tests schreiben**

Ans Ende von `tests/test_restore.py`:

```python
# -- parking (decision 26, GitHub #30) ---------------------------------

BETT = {"type": "tile", "entity": "light.x", "name": "Bett"}
BETTLAMPE = {"type": "tile", "entity": "light.x", "name": "Bettlampe"}


def _parked(payload, path="home"):
    return analyze.UndoStep(
        action="insert", kind="card", view_path=path, view_index=0,
        location=("cards",), index=0, expect=None, payload=payload,
        label=analyze._describe(payload), parked=True,
    )


def test_a_parked_card_creates_the_imported_cards_list():
    before = _sections({"cards": [BETT]})
    after = _sections({"cards": [BETTLAMPE]})
    current = _sections({"column_span": 2, "cards": []}, {"cards": [BETTLAMPE]})
    plan = analyze.plan_undo(before, after, current)
    result = restore.apply_undo(current, plan)
    view = result["views"][0]
    assert view["cards"] == [BETT]
    assert view["sections"][1]["cards"] == []
    assert "cards" not in current["views"][0]


def test_a_parked_card_replaces_a_null_cards_value():
    current = _sections({"cards": []})
    current["views"][0]["cards"] = None
    result = restore.apply_undo(current, analyze.UndoPlan(blocked=None, steps=(_parked(A),)))
    assert result["views"][0]["cards"] == [A]


def test_parked_cards_come_after_an_ordinary_insert_into_the_same_list():
    current = _sections({"cards": []})
    current["views"][0]["cards"] = [C]
    ordinary = analyze.UndoStep(
        action="insert", kind="card", view_path="home", view_index=0,
        location=("cards",), index=0, expect=None, payload=A, label="tile: light.a",
    )
    plan = analyze.UndoPlan(blocked=None, steps=(_parked(B), ordinary))
    result = restore.apply_undo(current, plan)
    assert result["views"][0]["cards"] == [A, C, B]


def test_parked_cards_keep_the_order_the_plan_gives():
    current = _sections({"cards": []})
    plan = analyze.UndoPlan(blocked=None, steps=(_parked(A), _parked(B)))
    assert restore.apply_undo(current, plan)["views"][0]["cards"] == [A, B]


def test_a_parked_card_does_not_replace_something_that_is_no_list():
    current = _sections({"cards": []})
    current["views"][0]["cards"] = {"oops": 1}
    plan = analyze.UndoPlan(blocked=None, steps=(_parked(A),))
    with pytest.raises(LookupError, match="something other than a card list"):
        restore.apply_undo(current, plan)


def test_a_parked_card_refuses_when_its_view_is_gone():
    plan = analyze.UndoPlan(blocked=None, steps=(_parked(A, path="elsewhere"),))
    with pytest.raises(LookupError, match="no longer exists"):
        restore.apply_undo(_sections({"cards": []}), plan)
```

- [ ] **Step 2: Scheitern prüfen**

Run: `python3 -m pytest tests/test_restore.py -k parked -v`
Expected: FAIL – der geparkte Schritt läuft durch den Index-Zweig und scheitert mit `the card list … no longer exists` bzw. landet an Index 0.

- [ ] **Step 3: `apply_undo` anpassen**

In `restore.py` die abschließende Schleife über die Einsetzungen ersetzen durch:

```python
    inserts = [step for step in plan.steps if step.action == "insert"]
    for step in sorted((s for s in inserts if not s.parked), key=lambda s: s.index):
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
    # Parked last and appended, never indexed: they go where Home
    # Assistant shows "Imported cards", after anything that has a real
    # index in the same list, so no append shifts an ordinary insert.
    for step in (s for s in inserts if s.parked):
        view = _find_view(views, step)
        if view is None:
            raise LookupError(
                f"the view {step.label} belonged to no longer exists "
                f"(path={step.view_path!r}, index={step.view_index})"
            )
        cards = view.get("cards")
        if cards is None:
            # A sections view usually has no `cards:` at all, and YAML's
            # `cards: null` arrives as None - neither is a refusal.
            cards = []
            view["cards"] = cards
        elif not isinstance(cards, list):
            # Something that is not a card list: replacing it would throw
            # away whatever it is, which is not this undo's to decide.
            raise LookupError(
                f"the view {step.label} belonged to holds something other "
                f"than a card list under cards:, so nothing is parked there"
            )
        cards.append(copy.deepcopy(step.payload))
    return result
```

- [ ] **Step 4: Tests und Suite**

Run: `python3 -m pytest tests/ -v`
Expected: 0 failed.

- [ ] **Step 5: Commit (nach Go des Nutzers)**

```bash
git add custom_components/dashboard_history/restore.py tests/test_restore.py
git commit -m "Append parked cards to the view's Imported cards" -m "A parked step has no index worth writing to: its section could not be
proven. It goes to the end of the view's own cards list, created when
the view has none - the usual case for a sections view. GitHub #30."
```

---

### Task 3: `_section_name` nennt »Imported cards«

**Files:**
- Modify: `custom_components/dashboard_history/analyze.py` (`_section_name`)
- Test: `tests/test_analyze.py`

**Interfaces:**
- Consumes: `_view_type` (vorhanden).
- Produces: `_section_name(slot)` liefert `'the "Imported cards" area'`, wenn `slot.location == ("cards",)` und die Ansicht `type: sections` trägt.

- [ ] **Step 1: Test schreiben**

```python
def test_a_card_moved_out_of_a_section_names_imported_cards():
    """Where Home Assistant shows it, in its own words (decision 26)."""
    old = {"views": [{"path": "home", "type": "sections", "cards": [],
                      "sections": [{"cards": [A, B]}]}]}
    new = {"views": [{"path": "home", "type": "sections", "cards": [A],
                      "sections": [{"cards": [B]}]}]}
    texts = [e.text for g in analyze.explain_change(old, new).groups for e in g.entries]
    assert texts == ['tile: light.a was moved to the "Imported cards" area']
```

- [ ] **Step 2: Scheitern prüfen**

Run: `python3 -m pytest tests/test_analyze.py::test_a_card_moved_out_of_a_section_names_imported_cards -v`
Expected: FAIL – Text endet auf `another place in this view`.

- [ ] **Step 3: Umsetzen**

In `_section_name` den ersten Zweig ersetzen:

```python
    if slot.location[:1] != ("sections",):
        if slot.location == ("cards",) and _view_type(slot.view) == "sections":
            # The view's own list, in a sections view, is what Home
            # Assistant shows as "Imported cards" (decision 26).
            return 'the "Imported cards" area'
        return "another place in this view"
```

- [ ] **Step 4: Suite**

Run: `python3 -m pytest tests/ -v`
Expected: 0 failed.

- [ ] **Step 5: Commit (nach Go des Nutzers)**

```bash
git add custom_components/dashboard_history/analyze.py tests/test_analyze.py
git commit -m "Name Imported cards where Home Assistant does" -m "A card in a sections view's own cards list sits in the area Home
Assistant labels \"Imported cards\". Saying \"another place in this
view\" sent people looking for something the editor names otherwise.
GitHub #30."
```

---

### Task 4: »Put back« – ein beweisender Anker und die Park-Funktionen

**Files:**
- Modify: `custom_components/dashboard_history/analyze.py` (`_section_anchor`, sein Aufruf in `find_removed`, Kommentar an `RemovedItem.anchor`)
- Modify: `custom_components/dashboard_history/restore.py` (`_anchor_holds`, neue `parks`, `park`)
- Test: `tests/test_restore.py`

**Interfaces:**
- Produces: `RemovedItem.anchor` ist `(section_count: int, settings: dict | None, survivors: tuple, before: int)` – `before` ist die Zahl der Überlebenden, die vor der Karte standen; `restore._anchored_index(view, item) -> int | None` (wohin die Karte in ihrer Section zurückgeht, oder `None`, wenn der Anker nicht hält); `restore.parks(config: dict, item: RemovedItem) -> bool`; `restore.park(config: dict, item: RemovedItem) -> dict` (neue Konfiguration, Eingabe unverändert; `LookupError`, wenn die Ansicht fehlt).

- [ ] **Step 1: Tests schreiben**

Ans Ende von `tests/test_restore.py`:

```python
D = {"type": "tile", "entity": "light.d"}
E = {"type": "tile", "entity": "light.e"}


def test_the_anchor_catches_two_untitled_sections_that_swapped():
    """Anchored by count and title, this card went into the wrong section."""
    old = _sections({"column_span": 2, "cards": [A, B]}, {"column_span": 1, "cards": [C]})
    new = _sections({"column_span": 2, "cards": [A]}, {"column_span": 1, "cards": [C]})
    item = next(i for i in analyze.find_removed(old, new) if i.payload == B)
    today = _sections({"column_span": 1, "cards": [C]}, {"column_span": 2, "cards": [A]})
    with pytest.raises(LookupError, match="section"):
        restore.reinsert(today, item)
    assert restore.parks(today, item) is True


def test_the_anchor_notices_an_edited_neighbour():
    """Decision 2 of spec L: an edited neighbour still parks."""
    old = _sections({"cards": [A, B]})
    new = _sections({"cards": [A]})
    item = next(i for i in analyze.find_removed(old, new) if i.payload == B)
    edited_a = {**A, "name": "Anders"}
    assert restore.parks(_sections({"cards": [edited_a]}), item) is True


def test_an_untouched_section_does_not_park():
    old = _sections({"cards": [A, B]})
    new = _sections({"cards": [A]})
    item = next(i for i in analyze.find_removed(old, new) if i.payload == B)
    assert restore.parks(new, item) is False
    assert restore.reinsert(new, item)["views"][0]["sections"][0]["cards"] == [A, B]


def test_a_card_added_beside_it_since_does_not_park():
    """The survivors only have to be there, in order - more is allowed."""
    old = _sections({"cards": [A, B]})
    new = _sections({"cards": [A]})
    item = next(i for i in analyze.find_removed(old, new) if i.payload == B)
    today = _sections({"cards": [A, D]})
    assert restore.parks(today, item) is False
    assert restore.reinsert(today, item)["views"][0]["sections"][0]["cards"] == [A, B, D]


def test_a_card_moved_away_in_the_same_save_does_not_park():
    """C left for the other section; it is no survivor that has to stay."""
    old = _sections({"cards": [A, B, C]}, {"cards": []})
    new = _sections({"cards": [A]}, {"cards": [C]})
    item = next(i for i in analyze.find_removed(old, new) if i.payload == B)
    assert restore.parks(new, item) is False


def test_a_swap_of_sections_with_equal_settings_is_caught_by_their_cards():
    old = _sections({"cards": [A, B]}, {"cards": [C]})
    new = _sections({"cards": [A]}, {"cards": [C]})
    item = next(i for i in analyze.find_removed(old, new) if i.payload == B)
    today = _sections({"cards": [C]}, {"cards": [A]})
    assert restore.parks(today, item) is True


def test_a_card_goes_back_beside_its_neighbour_not_to_its_old_index():
    """Cards inserted before the neighbour since must not push it away.

    The old index would put B between D and E, in the right section but
    away from A - found in the second review. The anchor remembers that
    B stood after one survivor, and B goes back right after A."""
    old = _sections({"cards": [A, B]})
    new = _sections({"cards": [A]})
    item = next(i for i in analyze.find_removed(old, new) if i.payload == B)
    today = _sections({"cards": [D, E, A]})
    assert restore.parks(today, item) is False
    assert restore.reinsert(today, item)["views"][0]["sections"][0]["cards"] == [D, E, A, B]


def test_a_card_that_was_alone_needs_its_section_empty():
    """Nothing beside it to recognise the section by - so it must be as
    empty as the card left it, or any section with the same settings
    (most carry only `type: grid`) would pass for it."""
    old = _sections({"cards": [B]}, {"cards": [C]})
    new = _sections({"cards": []}, {"cards": [C]})
    item = next(i for i in analyze.find_removed(old, new) if i.payload == B)
    assert restore.parks(new, item) is False
    assert restore.parks(_sections({"cards": [C]}, {"cards": []}), item) is True


def test_park_appends_to_imported_cards_and_leaves_the_input_alone():
    old = _sections({"title": "Oben", "cards": [A]}, {"title": "Unten", "cards": [B, C]})
    new = _sections({"title": "Oben", "cards": [A]}, {"title": "Unten", "cards": [B]})
    item = next(i for i in analyze.find_removed(old, new) if i.payload == C)
    today = _sections({"title": "Unten", "cards": [B]})
    assert restore.parks(today, item) is True
    result = restore.park(today, item)
    assert result["views"][0]["cards"] == [C]
    assert result["views"][0]["sections"] == [{"title": "Unten", "cards": [B]}]
    assert "cards" not in today["views"][0]


def test_nothing_parks_outside_a_sections_view_with_a_path():
    masonry = analyze.find_removed(_config([A, B]), _config([A]))[0]
    assert restore.parks(_config([A]), masonry) is False
    old = {"views": [{"type": "sections", "sections": [{"cards": [A, B]}]}]}
    pathless = next(i for i in analyze.find_removed(old, {"views": [{"type": "sections", "sections": [{"cards": [A]}]}]}) if i.payload == B)
    assert restore.parks({"views": [{"type": "sections", "sections": [{"column_span": 2, "cards": []}, {"cards": [A]}]}]}, pathless) is False


def test_a_section_item_never_parks():
    old = _sections({"cards": [A, B]}, {"cards": [C]})
    new = _sections({"cards": [C]})
    item = analyze.find_removed(old, new)[0]
    assert item.kind == "section"
    assert restore.parks(new, item) is False


def test_two_cards_of_one_section_go_back_one_after_the_other():
    """Review focus 5: each put back is planned against today's state."""
    old = _sections({"cards": [A, B, C]})
    now = _sections({"cards": [A]})
    first = next(i for i in analyze.find_removed(old, now) if i.payload == B)
    now = restore.reinsert(now, first)
    second = next(i for i in analyze.find_removed(old, now) if i.payload == C)
    assert restore.parks(now, second) is False
    assert restore.reinsert(now, second)["views"][0]["sections"][0]["cards"] == [A, B, C]
```

- [ ] **Step 2: Scheitern prüfen**

Run: `python3 -m pytest tests/test_restore.py -k "anchor or park or one_after_the_other or beside or moved_away or equal_settings or alone" -v`
Expected: FAIL – `AttributeError: module 'restore' has no attribute 'parks'`; `test_the_anchor_catches_two_untitled_sections_that_swapped` scheitert schon am `pytest.raises`, weil der alte Anker den Tausch durchlässt.

- [ ] **Step 3: Anker in `analyze.py`**

`_section_anchor` ersetzen:

```python
def _section_anchor(view: dict, location: tuple, index: int, left: set) -> tuple | None:
    """How to recognise the section a card sat in, or None outside one.

    What the section was, not what it was called: how many sections the
    view had, the section's own settings (everything but `cards`, like
    `_section_marks`), and the cards that should still stand in it - the
    old ones minus those in `left`, which disappeared or moved elsewhere
    and so owe the section nothing. Titles alone were a check against
    nothing - 0 of 101 sections carry one - and let a swapped section
    take a stranger's card (GitHub #30). Failing this parks the card now
    rather than refusing it, so being strict costs a hint, not a refusal.

    `before` counts the survivors that stood ahead of the card, so it can
    go back right after the last of them rather than to an old index that
    cards added since may have moved.
    """
    if len(location) < 2 or location[0] != "sections":
        return None
    sections = view.get("sections") or []
    at = location[1]
    settings: dict | None = None
    survivors: list = []
    before = 0
    if isinstance(at, int) and 0 <= at < len(sections):
        section = sections[at]
        if isinstance(section, dict):
            settings = {key: value for key, value in section.items() if key != "cards"}
            for position, card in enumerate(section.get("cards") or []):
                if (location, position) in left:
                    continue
                survivors.append(card)
                if position < index:
                    before += 1
    return (len(sections), settings, tuple(survivors), before)
```

In `find_removed` die Zuordnung einmal rechnen und die weggezogenen Karten merken. Die Zeilen

```python
    gone_by_view: dict[int, list[Slot]] = {}
    for slot in match_cards(old, new).removed:
        gone_by_view.setdefault(slot.view_index, []).append(slot)
```

ersetzen durch

```python
    matching = match_cards(old, new)
    gone_by_view: dict[int, list[Slot]] = {}
    for slot in matching.removed:
        gone_by_view.setdefault(slot.view_index, []).append(slot)
    # Cards that left their place for another list: no survivor a
    # section has to keep for its anchor to hold (spec L, 4a).
    away_by_view: dict[int, set] = {}
    for was, now in matching.moved:
        if _place(was) != _place(now):
            away_by_view.setdefault(was.view_index, set()).add((was.location, was.index))
```

direkt nach `gone = gone_by_view.get(view_index, [])` einfügen

```python
        left = {(slot.location, slot.index) for slot in gone} | away_by_view.get(view_index, set())
```

und den Aufruf `anchor=_section_anchor(old_view, slot.location),` zu `anchor=_section_anchor(old_view, slot.location, slot.index, left),` ändern.

Den Kommentar über `anchor: tuple | None = None` in `RemovedItem` ersetzen:

```python
    # What the section this card sat in was, when it sat in one: how many
    # sections the view had, that section's own settings, and the cards
    # that should still stand beside it. A section carries no path and no
    # id, so this is the only proof there is that index i still means it
    # - and when it fails, the card is parked instead (decision 26).
```

- [ ] **Step 4: `restore.py`**

`_anchor_holds` ersetzen:

```python
def _anchored_index(view: dict, item: RemovedItem) -> int | None:
    """Where the card goes back in its section, or None if that is unproven.

    Only cards that sat in a section carry an anchor, so everything else
    passes straight through. The section has to have the same settings
    and still hold the cards that stood beside this one, in their order;
    cards added since may sit between them. A card that was alone has
    nothing beside it to recognise the section by, so then the section
    has to be empty. See `analyze._section_anchor` for why a title was
    never enough.

    The answer is an index, not a yes: right after the last survivor that
    stood ahead of the card, or right before the first one if none did.
    """
    count, settings, survivors, before = item.anchor
    sections = view.get("sections") or []
    if len(sections) != count:
        return None
    at = item.location[1]
    if not isinstance(at, int) or not 0 <= at < len(sections):
        return None
    section = sections[at]
    if not isinstance(section, dict):
        return None
    own = {key: value for key, value in section.items() if key != "cards"}
    if own != settings:
        return None
    cards = list(section.get("cards") or [])
    if not survivors:
        return 0 if not cards else None
    # In order, extras allowed: each survivor is found after the last.
    found: list[int] = []
    position = 0
    for wanted in survivors:
        while position < len(cards) and cards[position] != wanted:
            position += 1
        if position == len(cards):
            return None
        found.append(position)
        position += 1
    return found[before - 1] + 1 if before else found[0]


def _anchor_holds(view: dict, item: RemovedItem) -> bool:
    """Whether the section at that index is still the one the card left."""
    return item.anchor is None or _anchored_index(view, item) is not None
```

In `reinsert` die Einsetzzeile im Kartenzweig

```python
    cards.insert(min(item.index, len(cards)), copy.deepcopy(item.payload))
```

ersetzen durch

```python
    # A card that sat in a section goes back beside the neighbour it had;
    # the old index is only right while nothing was added in front.
    index = item.index if item.anchor is None else _anchored_index(view, item)
    cards.insert(min(index, len(cards)), copy.deepcopy(item.payload))
```

Nach `reinsert` einfügen:

```python
def parks(config: dict, item: RemovedItem) -> bool:
    """Whether putting `item` back goes to "Imported cards" (decision 26).

    Only a card, only in a sections view named by a path, and only when
    the section it left can no longer be proven to be the one at that
    index. Everything else is `reinsert`'s to answer - including its
    refusals.
    """
    if item.kind != "card" or item.anchor is None or item.view_path is None:
        return False
    if _paths_share(config):
        return False
    view = _find_view(config.get("views") or [], item)
    if view is None or view.get("type") != "sections":
        return False
    return not _anchor_holds(view, item) or _cards_at(view, item.location) is None


def park(config: dict, item: RemovedItem) -> dict:
    """Return a new configuration with `item` at the end of "Imported cards"."""
    result = copy.deepcopy(config)
    view = _find_view(result.get("views") or [], item)
    if view is None:
        raise LookupError(
            f"the view this card belonged to no longer exists "
            f"(path={item.view_path!r}, index={item.view_index})"
        )
    cards = view.get("cards")
    if cards is None:
        cards = []
        view["cards"] = cards
    elif not isinstance(cards, list):
        raise LookupError(
            "the view this card belonged to holds something other than a "
            "card list under cards:, so nothing is parked there"
        )
    cards.append(copy.deepcopy(item.payload))
    return result
```

- [ ] **Step 5: Tests und Suite**

Run: `python3 -m pytest tests/ -v`
Expected: 0 failed – die bestehenden `test_a_card_refuses_to_go_back_into_a_different_section` und `test_a_card_refuses_when_a_section_was_pushed_along` bleiben grün, weil `reinsert` weiterhin verweigert.

- [ ] **Step 6: Commit (nach Go des Nutzers)**

```bash
git add custom_components/dashboard_history/analyze.py custom_components/dashboard_history/restore.py tests/test_restore.py
git commit -m "Anchor a card to what its section was, and park it" -m "The section anchor compared a count and a title, and no section on the
installation carries a title - so two swapped sections took each
other's cards back without a word. The anchor now holds the section's
settings and its remaining cards. When that proof fails, parks() and
park() put the card into Imported cards instead. GitHub #30."
```

---

### Task 5: `operations.py` und `websocket_api.py` – `parked` nach außen

**Files:**
- Modify: `custom_components/dashboard_history/operations.py` (`async_undo_change`, `_reinsertion`, `async_restore_deleted`, Import aus `.restore`)
- Modify: `custom_components/dashboard_history/websocket_api.py` (`undo_change`, `restore_deleted`)
- Modify: `custom_components/dashboard_history/services.py`, `services.yaml` (`undo_change`, `restore_deleted`: `allow_parking`)
- Modify: `tests/integration/run_checks.py` (neuer Abschnitt `run_parking`, geänderte Erwartung in `run_positions`)

**Interfaces:**
- Consumes: `UndoPlan.parked` (Task 1), `restore.parks`, `restore.park` (Task 4).
- Produces: `undo_change`-Antwort mit `available: True` trägt immer `parked: list[str]`; `restore_deleted` antwortet in Vorschau und Ergebnis mit `parked: list[str]` (leer oder die eine Beschriftung). **Beide** WebSocket-Befehle akzeptieren `expected_parked: list[str]` (optional) und verweigern beim Bestätigen, wenn der neu gerechnete Plan anders parkt. Beide Dienste parken nur mit `allow_parking: true`; sonst verweigern sie, wenn geparkt würde. Die gemeinsame Verweigerung ist die Konstante `_UNEXPECTED_PARKING` in `operations.py`.

- [ ] **Step 1: `async_undo_change`**

Oben in `operations.py`, bei den übrigen Modulkonstanten:

```python
# A write that would park cards nobody was shown - the dashboard changed
# between preview and confirmation, or a service call did not allow it.
# A button without an asterisk must not park a card (decision 26).
_UNEXPECTED_PARKING = (
    "this would place cards in \"Imported cards\" that were not expected - "
    "either the dashboard changed since the preview, or parking was not "
    "allowed for this call - so nothing was written"
)
```

Signatur von `async_undo_change` um `expected_parked: list[str] | None = None` erweitern (nach `override_unrecorded_state`). Im Docstring einen Absatz ergänzen:

```
    `parked` names the cards this undo can only make available in the
    view's "Imported cards", not put back into their section (decision
    26). It is part of the cheap answer on purpose: the row asks on
    every expansion, and the asterisk on its button has to be right
    there already. `expected_parked` is what the dialog showed; a
    confirming call whose fresh plan parks differently writes nothing,
    because a button without an asterisk must not park a card. None
    means "not compared" and is only for callers that decided that for
    themselves - the service passes [] unless told `allow_parking`.
```

Direkt nach dem Block `if result == current: return {... "this change is already taken back"}` einfügen:

```python
    parked = list(plan.parked)
    if confirm and expected_parked is not None and parked != list(expected_parked):
        return {"available": False, "reason": _UNEXPECTED_PARKING}
```

und in `answer = {…}` das Feld `"parked": parked,` ergänzen.

- [ ] **Step 2: `_reinsertion` und `async_restore_deleted`**

Import erweitern: `from .restore import apply_undo, park, parks, reinsert`.

In `_reinsertion` den `try`-Block ersetzen:

```python
    item = items[position]
    parked = parks(current, item)
    try:
        restored = park(current, item) if parked else reinsert(current, item)
    except LookupError as err:
        # The place it belonged to is gone. Every other failure here
        # answers with a message rather than an exception; so does this.
        return {"error": str(err)}
```

im Rückgabewert `"item": items[position],` zu `"item": item,` ändern und `"parked": [item.label] if parked else [],` ergänzen.

`async_restore_deleted` bekommt dieselbe Prüfung wie der Undo (Review-Befund K1: ohne sie würde ein Put back, dessen Vorschau exakt war, beim Bestätigen still parken). Signatur um `expected_parked: list[str] | None = None` erweitern (nach `override_unrecorded_state`), die Vorschau-Antwort zu `{"applied": False, "preview": diff, "explanation": explanation, "parked": plan["parked"]}` ändern, und direkt nach `if not confirm: return …`:

```python
    if expected_parked is not None and plan["parked"] != list(expected_parked):
        return {"applied": False, "error": _UNEXPECTED_PARKING}
```

`result` um `"parked": plan["parked"],` ergänzen.

- [ ] **Step 3: `websocket_api.py`**

Im Schema von `f"{DOMAIN}/undo_change"` nach `override_unrecorded_state`:

```python
            # What the dialog showed as parked (decision 26); the
            # confirming call refuses if the fresh plan parks otherwise.
            vol.Optional("expected_parked"): [str],
```

und in der Zuordnung

```python
            # Absent means "I expect no parking", as for the services: a
            # write that would park has to be asked for on every route
            # (second review). None stays for Python callers only.
            "expected_parked": msg.get("expected_parked", []),
```

Dasselbe im Schema und in der Zuordnung von `f"{DOMAIN}/restore_deleted"`. Die bestehenden bestätigenden Aufrufe in `run_checks.py` parken nicht und bleiben daher unberührt.

**Dienste (Review-Befund W1).** Ohne Weiteres würde der Dienst `undo_change` mit `confirm: true` künftig parken, obwohl seine Beschreibung »only offered when it is provably exact« verspricht. Beide Dienste bekommen deshalb einen ausdrücklichen Schalter. In `services.py`, in beiden Schemata (`restore_deleted`, `undo_change`) nach `override_unrecorded_state`:

```python
            vol.Optional("allow_parking", default=False): bool,
```

Der Aufruf von `operations.async_undo_change` im Dienst `undo_change` bekommt

```python
            # Not compared (None) only when parking was allowed; otherwise
            # [] - any parking at all is then a refusal, not a surprise.
            expected_parked=None if call.data.get("allow_parking") else [],
```

und der Aufruf von `operations.async_restore_deleted` im Dienst `restore_deleted` dasselbe als Schlüsselwortargument.

In `services.yaml` bei `undo_change` die Beschreibung ersetzen durch:

```yaml
  description: >-
    Take a single change back and keep everything saved since. Only
    offered when it can be shown what it writes: the cards the change
    produced must still be in the dashboard, unchanged and only once.
    Where a card's section in a sections view cannot be proven any more,
    it can only be placed in the view's "Imported cards" area - that
    needs allow_parking, otherwise the call refuses. Without confirm it
    answers with a preview and writes nothing.
```

und bei beiden Diensten unter `fields` ergänzen (nach `override_unrecorded_state`, oder am Ende, falls es dort fehlt):

```yaml
    allow_parking:
      required: false
      default: false
      description: >-
        Allow cards whose section can no longer be proven to be placed
        in the view's "Imported cards" area instead of refusing.
      selector:
        boolean:
```

Hat das Paket Übersetzungsdateien für Dienste (`grep -rn "override_unrecorded_state" custom_components/dashboard_history --include=*.json`), dort denselben Eintrag ergänzen.

- [ ] **Step 4: Bestehenden Fall in `run_positions` anpassen**

In `tests/integration/run_checks.py` den Check

```python
        check(
            "a card whose section was pushed along is not filed in a stranger",
            bool(gone.get("items")) and "section" in (answer.get("error") or ""),
            answer.get("error", "it was offered a place"),
        )
```

ersetzen durch

```python
        # Since GitHub #30 the card is parked in "Imported cards" rather
        # than refused - what stays true is the point of this check: it
        # never goes into the section that now stands at its old index.
        # Written and looked at, not only previewed: the preview says
        # where it would go, the live state says where it went.
        label = gone["items"][0]["label"] if gone.get("items") else ""
        before_write = await socket.call("lovelace/config", url_path=key)
        written = await socket.call(
            "dashboard_history/restore_deleted",
            dashboard=key,
            revision=base,
            position=0,
            confirm=True,
            expected_parked=[label],
        )
        await asyncio.sleep(2)
        live = await socket.call("lovelace/config", url_path=key)
        check(
            "a card whose section was pushed along is parked, not filed in a stranger",
            bool(label)
            and not answer.get("error")
            and answer.get("parked") == [label]
            and written.get("applied") is True
            and live["views"][0].get("sections") == before_write["views"][0].get("sections")
            and live["views"][0].get("cards") == [guest],
            answer.get("error") or written.get("error")
            or f"parked={answer.get('parked')!r}, cards={live['views'][0].get('cards')!r}",
        )
```

Die Karte, die dort fehlt, ist `guest` (der Stand `base` hielt `Unten` mit `[weather, guest]`, der spätere nur `[weather]`) – vor dem Umbau am Code nachsehen, dass es in diesem Abschnitt so bleibt.

- [ ] **Step 5: Neuer Abschnitt `run_parking`**

Nach `run_sections` einfügen:

```python
async def run_parking(access: str) -> None:
    """A card whose section moved since is parked, and Home Assistant keeps it.

    Decision 26, GitHub #30. pytest proves the plan and the write; only a
    running Home Assistant shows that its backend stores and returns a
    sections view's `cards:` list unchanged, and that the refusal for a
    preview that no longer matches reaches the caller. What the editor
    then shows is decision 26's measurement, not this one's.
    """
    key = "dh-parking"
    old = {"type": "markdown", "content": "# Licht\nalt"}
    new = {"type": "markdown", "content": "# Licht\nneu"}
    other = {"type": "markdown", "content": "# Wetter"}

    def sections(*blocks):
        return {
            "views": [
                {
                    "path": "home",
                    "title": "Home",
                    "type": "sections",
                    "sections": [dict(block) for block in blocks],
                }
            ]
        }

    async with Socket(access) as socket:
        listed = (await socket.call("lovelace/dashboards/list")) or []
        if not any(entry.get("url_path") == key for entry in listed):
            await socket.call("lovelace/dashboards/create", url_path=key, title=key)
            await asyncio.sleep(3)

        async def save(config: dict) -> list:
            await socket.call("lovelace/config/save", url_path=key, config=config)
            return await _wait_until_recorded(socket, key)

        await save(sections({"cards": [old, other]}))
        edited = await save(sections({"cards": [new, other]}))
        revision = edited[0]["revision"]
        await save(sections({"column_span": 2, "cards": []}, {"cards": [new, other]}))

        asked = await socket.call(
            "dashboard_history/undo_change", dashboard=key, revision=revision
        )
        check(
            "an edit whose section moved since is undoable, parked",
            asked.get("available") is True and asked.get("parked") == ["markdown: Licht"],
            asked.get("reason") or f"parked={asked.get('parked')!r}",
        )

        stale = await socket.call(
            "dashboard_history/undo_change",
            dashboard=key,
            revision=revision,
            confirm=True,
            expected_parked=[],
        )
        check(
            "a confirmation that did not show the parking writes nothing",
            stale.get("available") is False and "preview" in (stale.get("reason") or ""),
            stale.get("reason", ""),
        )

        await socket.call(
            "dashboard_history/undo_change",
            dashboard=key,
            revision=revision,
            confirm=True,
            expected_parked=["markdown: Licht"],
        )
        await asyncio.sleep(2)
        live = await socket.call("lovelace/config", url_path=key)
        view = live["views"][0]
        check(
            "the old card lands in Imported cards, the edited one is gone",
            view.get("cards") == [old]
            and [s.get("cards") for s in view["sections"]] == [[], [other]],
            f"cards={view.get('cards')!r}, sections={view.get('sections')!r}",
        )

        # Saved once more through Home Assistant's API, untouched. This
        # shows the backend stores and returns the list as it is - not
        # what the editor does with it; decision 26 measured that in the
        # editor, and no API reaches it.
        await save(live)
        again = await socket.call("lovelace/config", url_path=key)
        check(
            "and Home Assistant keeps it across the next save",
            again["views"][0].get("cards") == [old],
            f"cards={again['views'][0].get('cards')!r}",
        )

        # Named, never by prefix: this instance holds other dh-* boards.
        listed = (await socket.call("lovelace/dashboards/list")) or []
        mine = next((e for e in listed if e.get("url_path") == key), None)
        if mine is not None:
            await socket.call("lovelace/dashboards/delete", dashboard_id=mine["id"])
```

Unter `asyncio.run(run_sections(access))` im Hauptblock `asyncio.run(run_parking(access))` ergänzen.


- [ ] **Step 6: Prüfen**

Run: `python3 -m pytest tests/ -v` → 0 failed.
Run: `docker compose -f docker/compose.yaml up -d` und `python3 tests/integration/run_checks.py`
Expected: alle Checks grün, darunter die vier aus `run_parking` und der geänderte aus `run_positions`. Scheitert »a card whose section was pushed along…« mit einer anderen Beschriftung als erwartet, die tatsächliche Beschriftung aus dem Detail in die Erwartung übernehmen – geprüft wird, *dass* geparkt wird, nicht der Wortlaut von `_describe`.

- [ ] **Step 7: Commit (nach Go des Nutzers)**

```bash
git add custom_components/dashboard_history/operations.py custom_components/dashboard_history/websocket_api.py tests/integration/run_checks.py
git commit -m "Report parked cards and refuse a stale confirmation" -m "undo_change and restore_deleted name the cards that only go to Imported
cards, so the panel can mark its button. A confirmation whose fresh plan
parks differently from what the dialog showed writes nothing: a button
without an asterisk must not park a card. GitHub #30."
```

---

### Task 6: Panel – Sternchen, Hinweis, Dialog

**Files:**
- Modify: `custom_components/dashboard_history/panel.js` (`_renderActionBar`, `_confirm`, `_undoChange`, `_restoreItem`)
- Test: `tests/test_panel_behaviour.py`

**Interfaces:**
- Consumes: `undo_change`/`restore_deleted`-Feld `parked` (Task 5).
- Produces: Die `request`-Funktion, die `_confirm` bekommt, wird künftig mit einem fünften Argument aufgerufen: der Vorschau-Antwort (`request(true, keep, asked, override, preview)`). Bestehende `request`-Funktionen ignorieren es.

- [ ] **Step 1: Tests schreiben**

Ans Ende von `tests/test_panel_behaviour.py`:

```python
_PARKED_ACTION_BAR = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._changes = [{ revision: "a" }];
el._undo = { available: true, parked: ["tile: Bett"] };
const starred = el._renderActionBar({ revision: "a" }, { offerReplace: false });
el._undo = { available: true, parked: [] };
const plain = el._renderActionBar({ revision: "a" }, { offerReplace: false });
console.log(JSON.stringify({ starred, plain }));
"""


@pytest.fixture(scope="session")
def parked_action_bar(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "parked_action_bar", _PARKED_ACTION_BAR)


def test_a_parking_undo_carries_an_asterisk_and_says_why(parked_action_bar):
    # Decision 26: one button, a second form of it. Nobody should expect
    # an exact undo where the cards only become available.
    assert "Undo this change*</button>" in parked_action_bar["starred"]
    assert "Imported cards" in parked_action_bar["starred"]


def test_an_exact_undo_has_no_asterisk(parked_action_bar):
    assert "Undo this change</button>" in parked_action_bar["plain"]
    assert "Imported cards" not in parked_action_bar["plain"]


_PARKED_DIALOG = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._changes = [{ revision: "a" }, { revision: "b" }];
el.shadowRoot = node();
el._recorded = () => Promise.resolve();

const calls = [];
el._call = (type, extra) => new Promise((resolve) => calls.push({ type, extra, resolve }));

el._undoChange("a");
await settle();
calls[0].resolve({
  available: true, parked: ["tile: Bett"],
  preview: "-x\\n+y", explanation: { groups: [], note: "" },
});
await settle();
const dialog = el.shadowRoot.querySelector("dialog.confirm");
const bodyHtml = dialog.querySelector(".body").innerHTML;
dialog.close("apply");
await settle();
await settle();
const confirmExtra = calls[1] ? calls[1].extra : null;
console.log(JSON.stringify({ bodyHtml, confirmExtra }));
"""


@pytest.fixture(scope="session")
def parked_dialog(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "parked_dialog", _PARKED_DIALOG)


def test_the_dialog_lists_every_parked_card_in_home_assistants_words(parked_dialog):
    body = parked_dialog["bodyHtml"]
    assert '"Imported cards"' in body or "&quot;Imported cards&quot;" in body
    assert "tile: Bett" in body
    assert body.index("Puts this change back") < body.index("Imported cards")


def test_the_confirmation_sends_back_what_the_dialog_showed(parked_dialog):
    assert parked_dialog["confirmExtra"]["expected_parked"] == ["tile: Bett"]


_PARKED_PUT_BACK = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._changes = [{ revision: "a" }];
el.shadowRoot = node();
el._recorded = () => Promise.resolve();

const calls = [];
el._call = (type, extra) => new Promise((resolve) => calls.push({ type, extra, resolve }));

el._restoreItem("a", { label: "tile: light.c", position: 0 });
await settle();
calls[0].resolve({
  applied: false, parked: ["tile: light.c"],
  preview: "-x\\n+y", explanation: { groups: [], note: "" },
});
await settle();
const dialog = el.shadowRoot.querySelector("dialog.confirm");
const bodyHtml = dialog.querySelector(".body").innerHTML;
dialog.close("apply");
await settle();
await settle();
const confirmExtra = calls[1] ? calls[1].extra : null;
console.log(JSON.stringify({ bodyHtml, confirmExtra }));
"""


@pytest.fixture(scope="session")
def parked_put_back(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "parked_put_back", _PARKED_PUT_BACK)


def test_a_parking_put_back_says_so_and_sends_it_back(parked_put_back):
    # Review finding K1: "Put back" re-plans on confirmation too, so it
    # needs the same guard as the undo - and the same sentence.
    assert "Imported cards" in parked_put_back["bodyHtml"]
    assert parked_put_back["confirmExtra"]["expected_parked"] == ["tile: light.c"]
```

Wie `_answerFrom` auf `dialog.close("apply")` reagiert, zeigen die bestehenden Szenarien mit `dialog.close("cancel")`. Hält das Szenario nach `close("apply")` an einer anderen Stelle an (etwa weil `_guard` etwas erwartet, das der Stand-in nicht liefert), das Szenario so ergänzen, wie es ein bestehender Apply-Test tut (`grep -n 'close("apply")' tests/test_panel_behaviour.py`), statt die Assertion aufzuweichen.

- [ ] **Step 2: Scheitern prüfen**

Run: `python3 -m pytest tests/test_panel_behaviour.py -k "parked or parking or asterisk" -v`
Expected: FAIL – kein Sternchen, kein Absatz, kein `expected_parked`.

- [ ] **Step 3: `_renderActionBar`**

```js
    const star = undo?.parked?.length ? "*" : "";
    const undoButton = undo
      ? `<button class="act" data-undo="${escape(change.revision)}">Undo this change${star}</button>`
      : "";
```

und in der Rückgabe unter der `why`-Zeile:

```js
      ${star ? `<span class="why">* Some cards can no longer be put back into their exact section, because the sections of this view were rearranged since. They are placed in the view's "Imported cards" area — shown in edit mode — for you to move.</span>` : ""}
```

- [ ] **Step 4: `_confirm`**

Im Aufbau von `.body` zwischen `intro`-Absatz und `renderPlain(...)`:

```js
      (preview.parked?.length
        ? `<p class="lead parked">These cards cannot go back into their exact section and are made available in "Imported cards" instead — you still have to place them: ${escape(preview.parked.join(", "))}</p>`
        : "") +
```

Die beiden schreibenden Aufrufe reichen die Vorschau durch:

```js
      const result = await this._call(...request(true, keep, asked, false, preview));
```

und

```js
          const result = await this._call(...request(true, keep, asked, true, preview));
```

- [ ] **Step 5: `_undoChange`**

Die `request`-Funktion:

```js
      (confirm, keep, dashboard, override = false, shown = null) => [
        "undo_change",
        {
          dashboard, revision, confirm, preview: !confirm,
          override_unrecorded_state: override,
          // What the dialog showed as parked; the server refuses the
          // write if its fresh plan would park anything else.
          ...(confirm && shown ? { expected_parked: shown.parked || [] } : {}),
        },
      ],
```

Den bestehenden Kommentar über `preview` darüber stehen lassen.

- [ ] **Step 5b: `_restoreItem`**

Dieselbe Rückmeldung für »Put back« (Review-Befund K1), sonst würde ein beim Bestätigen neu gerechnetes Parken nirgends erwähnt – `_confirm` sagt nach dem Schreiben nur `error`, `available: false` und `note`. Die `request`-Funktion in `_restoreItem`:

```js
      (confirm, keep, dashboard, override = false, shown = null) => [
        "restore_deleted",
        {
          dashboard, revision, position: item.position, confirm,
          override_unrecorded_state: override,
          // What the dialog showed as parked; the server refuses the
          // write if putting it back would now park where it did not.
          ...(confirm && shown ? { expected_parked: shown.parked || [] } : {}),
        },
      ],
```

Nach dem Schreiben muss das Panel nichts zusätzlich sagen: Die Prüfung stellt sicher, dass geschrieben wird, was der Dialog gezeigt hat.

- [ ] **Step 6: Tests und Suite**

Run: `python3 -m pytest tests/ -v`
Expected: 0 failed, einschließlich `test_panel_assets.py` (Prüfsummen o. ä. – schlägt ein Fingerprint-Test an, den Container neu starten; siehe `docker/README.md`).

- [ ] **Step 7: Im Browser ansehen**

`docker compose -f docker/compose.yaml up -d`, im Testcontainer das Dashboard aus `run_parking` nachstellen (Karte bearbeiten, Section davor einfügen), Panel öffnen, die Zeile aufklappen: Knopf mit Sternchen, Hinweis darunter; Dialog öffnen: Absatz mit der Karte vor der Aufzählung. `tests/integration/look_at_panel.py` kann dafür einen Screenshot machen. Erst dann gilt der Task als erledigt.

- [ ] **Step 8: Commit (nach Go des Nutzers)**

```bash
git add custom_components/dashboard_history/panel.js tests/test_panel_behaviour.py
git commit -m "Mark a parking undo with an asterisk" -m "Decision 26: the button keeps its name and gains an asterisk when a card
can only be made available. The hint says why, the dialog lists each
card in Home Assistant's own term, and the confirmation sends back what
it showed so the server can refuse a plan that changed. GitHub #30."
```

---

### Task 7: Dokumentation nachziehen

**Files:**
- Modify: `docs/limitations.md`, `docs/how-it-works.md`, `docs/user-guide.md`, `docs/superpowers/status.md`, `docs/superpowers/specs/2026-08-30-dashboard-history-design.md` (Kopf von Entscheidung 26). `services.yaml` ist schon in Task 5 dran.

- [ ] **Step 1: Stellen finden**

Run: `grep -n "Decided, not yet built\|Imported cards\|#30\|Writes into wrong section\|Give your sections titles\|Section added\|Titled sections reordered\|_sections_lie\|cross-checked against its title" docs/*.md`

- [ ] **Step 2: `docs/limitations.md`**

In der Tabelle »Measured Behaviour Across Edge Cases«:
- Zeile »Section added«: Spalte *Undo this change* von `**Refuses**` zu `**Refuses** if this change added it; later additions park cards (see below)`.
- Zeile »Untitled sections reordered, and a card also edited in the same save«: Spalte *Put back* von `**Writes into wrong section**` zu `**Parks in "Imported cards"**`.
- Neue Zeile nach »Section added«:
  `| **Sections rearranged after the change**, card edited or deleted by it | Correct | **Parks** the card in "Imported cards" — button shows *Undo this change\** | Parks in "Imported cards" | **Works** |`

Den Absatz in der Anlage, der mit `A separate, narrower idea addresses a different cost` beginnt, so enden lassen: `… park such a card in the view's own \`cards:\` list instead of refusing outright. **Built on <Datum der Umsetzung>** — [GitHub issue #30](https://github.com/PPP01/ha-dashboard-history/issues/30). The undo's button then reads *Undo this change\**, and the dialog lists every card that only becomes available.`

- [ ] **Step 3: `docs/how-it-works.md`**

Den Absatz, der mit `Decision 26 in the design journal` beginnt, ersetzen durch:

```markdown
Since <Datum der Umsetzung>, the integration takes the same way out Home Assistant's own editor already uses for the related problem of *where a card belongs* (Decision 26 in the design journal): when a card's section inside a sections view cannot be proven any more — because the sections were rearranged after the change — it is parked in the view's own `cards:` list, the "Imported cards" area Home Assistant shows in edit mode. The undo's button then reads *Undo this change\**. A change that rearranged the sections itself is still refused ([GitHub issue #30](https://github.com/PPP01/ha-dashboard-history/issues/30)).
```

- [ ] **Step 4: `docs/user-guide.md`**

Den Hinweis `> **Give your sections titles.** …` (Zeile um 128) ersetzen durch:

```markdown
> **When a section cannot be recognised.** Home Assistant gives a section no identifier, so Dashboard History recognises one by its position, its settings and the cards around the one being restored. When that no longer fits — the sections were rearranged since — the card is not guessed into a section: it goes into the view's "Imported cards" area, visible in Home Assistant's edit mode, and the button says so with an asterisk. You drag it into place yourself. See [Limitations & Boundaries](limitations.md).
```

Den Satz in Zeile 125 `…cross-checked against its title.` ändern zu `…cross-checked against its settings and neighbouring cards.`

- [ ] **Step 4b: Zwei weitere Stellen (Review-Befund, Kleinigkeiten)**

`docs/how-it-works.md`, der Aufzählungspunkt, der mit `**The one safety check that exists for this` beginnt: den Funktionsnamen `(\`_sections_lie\` in \`analyze.py\`)` durch `(\`_section_drift\` in \`analyze.py\`, since <Datum der Umsetzung> per view rather than per dashboard)` ersetzen.

`docs/limitations.md`, Absatz, der mit `A section as Home Assistant's editor writes it has no path` beginnt: `the section's index in the row, cross-checked against its title. A title is optional, and in practice absent: all 80 sections on the installation this was developed against carry none.` ersetzen durch `the section's index in the row, cross-checked against its own settings - and, for *Put back*, against the cards that stood beside the one being restored. A title would help, but is optional and in practice absent: 0 of 101 sections on the installation this was developed against carry one. Where the check fails, the card is parked in "Imported cards" rather than guessed into a section.`

Danach: `grep -n "_sections_lie\|cross-checked against its title" docs/*.md` – erwartet: keine Ausgabe.

- [ ] **Step 5: Journal**

`docs/superpowers/status.md`: einen Eintrag nach dem Muster der Einträge zu #31–#33 ergänzen: `- **Umgesetzt am <Datum>** (GitHub-Issue [#30](…), Vorhaben L): …` – was geparkt wird, was weiter verweigert (von der Änderung umgebaute Sections, pfadlose Ansichten), der strengere Put-back-Anker, und die Restlücke aus #31 (Sections mit gleichen Einstellungen).

Haupt-Spec, Kopf von Entscheidung 26: `**Entschieden, noch nicht gebaut.**` ersetzen durch `**Gebaut am <Datum> als Vorhaben L**`.

`<Datum>`/`<Datum der Umsetzung>` ist das tatsächliche Datum des Commits, im Format `YYYY-MM-DD`.

- [ ] **Step 6: Commit (nach Go des Nutzers)**

```bash
git add docs/limitations.md docs/how-it-works.md docs/user-guide.md docs/superpowers/status.md docs/superpowers/specs/2026-08-30-dashboard-history-design.md
git commit -m "Document parking in Imported cards" -m "The limitations table, the architecture note and the user guide still
described a refusal and a silent wrong section where the tool now parks
the card and says so. GitHub #30."
```

---

## Self-review notes

- **Spec-Abdeckung:** Abschnitt 1 (je Ansicht, drei Antworten) → Task 1; Abschnitt 2 (was, wohin, Reihenfolge, `("cards",)` nie geparkt) → Task 1 + 2; Abschnitt 3 (`parked` auch ohne `preview`, `equals_state_before`) → Task 5 (`equals_state_before` ergibt sich von selbst, weil das Ergebnis vom Vorher-Stand abweicht); Abschnitt 4a/4b → Task 4 + 5; Abschnitt 5 (Wörter) → Task 3 + 6; »Entscheidungen« Punkt 4 → Task 5/6 (`expected_parked`).
- **Typen:** `UndoPlan.parked` ist ein Tupel; `operations` macht daraus eine Liste, das Panel vergleicht nicht, `expected_parked` wird serverseitig als Liste verglichen.
- **Dienste:** `undo_change` und `restore_deleted` parken nur mit `allow_parking: true` (Review-Befund W1); ohne verweigern sie mit `_UNEXPECTED_PARKING`, statt wie zuvor behauptet »unverändert« zu schreiben.
- **Bewusst hingenommen:** `expected_parked` vergleicht Beschriftungen, nicht Fingerabdrücke. Zwei verschiedene geparkte Karten mit gleicher Beschriftung sind darin ununterscheidbar – vom Review selbst als »sehr konstruiert« eingestuft.
- **Geerbt, nicht Teil dieses Plans:** `Slot.view_index` ist ein verdichteter Index, `_find_view` indiziert die rohe `views`-Liste. Steht ein Nicht-Dict-Eintrag vor einer pfadlosen Ansicht, schreibt schon heute jede Einsetzung in die falsche Ansicht (Review-Befund W3, am Code nachgestellt, `status.md`). Geparkte Schritte erben das wie alle Kartenschritte; die Behebung gehört in ein eigenes Issue.
