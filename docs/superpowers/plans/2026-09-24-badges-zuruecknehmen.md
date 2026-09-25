# Badges zurücknehmen – Umsetzungsplan (Vorhaben N, Issue #29)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die `badges:`-Liste einer Ansicht wird wie eine Kartenliste zugeordnet, erklärt, gezählt und gezielt zurückgenommen – als eigene Welt, die nie mit Karten vermischt wird, und mit einer zweistufigen Eindeutigkeit, weil dieselbe Badge gewöhnlich auf mehreren Ansichten steht.

**Architecture:** `match_cards` bekommt einen Parameter `containers` (Vorgabe `card_containers`); `match_badges` ist derselbe Aufruf mit `badge_containers`. `plan_undo` erzeugt Badge-Schritte (`kind="badge"`, `location=("badges",)`) mit eigener Fingerabdruck-Zählung; `apply_undo` behandelt sie wie Kartenschritte und legt eine fehlende `badges:`-Liste an. `_explain` und `change_message` nennen und zählen Badges.

**Tech Stack:** Python 3 (HA-freie Kernmodule, pytest), Testcontainer für `run_checks.py`.

**Spec:** `docs/superpowers/specs/2026-09-24-badges-zuruecknehmen-design.md`; dazu Entscheidung 14 und 15 der Haupt-Spec. **Voraussetzung: Vorhaben L und M sind umgesetzt** – dieser Plan setzt `put_back`/`parked` (L) und `setting_changes`, `settings_by_view`, `Summary.settings` (M) voraus. Die Festlegungen im Abschnitt »Entscheidungen« der Spec hat der Nutzer am 2026-09-24 unverändert bestätigt.

## Global Constraints

- `analyze.py`, `restore.py` ohne `import homeassistant`; `restore.py` ohne Laufzeitimport von `analyze`.
- Karten und Badges werden **nie** einander zugeordnet und zählen nie gegenseitig bei der Eindeutigkeit mit.
- `match_cards(old, new)` behält Signatur und Verhalten für alle bestehenden Aufrufer.
- Kein Put back für Badges (`find_removed` bleibt unverändert).
- `python3 -m pytest tests/ -v` nach jedem Task, nur »0 failed« zählt.
- Englisch in Code und UI, Deutsch im Journal. Commit-Format wie in `CLAUDE.md`, Verweis auf `#29`. **Committet wird erst nach ausdrücklichem Go des Nutzers.**

## Review Focus

1. **Dieselbe Badge auf mehreren Ansichten** (Prüfbank: 6 von 23): Undo in der eigenen Ansicht exakt. Test in Task 2.
2. **Gelöschte Badge mit unberührter Kopie anderswo:** wird wieder eingesetzt, nicht als »schon zurück« übersprungen. Test in Task 2.
3. **`{type: entity, entity: …}` als Karte und als Badge im selben Dashboard:** keine Zuordnung über die Grenze. Test in Task 1.
4. **Ansicht ohne `badges:`-Schlüssel** beim Einsetzen: Liste wird angelegt. Test in Task 3.
5. **Alte Badge-Form ohne `type`** (Prüfbank: 3): Beschriftung »badge: …«, nicht »card: …«. Test in Task 1.
6. **»Heute genau eine« ist nur mit »damals genau eine« ein Beweis** (Review 2026-09-25, K1): Hat die Änderung mehrere hinterlassen und steht heute noch eine, verweigert der Undo, statt eine Badge zu entfernen, die die Änderung nie berührt hat. Tests in Task 2.
7. **»Schon zurück« zählt nur in der eigenen Ansicht; von mehreren gleichen Gelöschten zählen nur alle oder keine** (Review 2026-09-25, K2/K3, Nachprüfung). Ist nur ein Teil zurück, verweigert der Undo, statt eine Position zu raten. Tests in Task 2.

---

## Files touched

| Datei | Rolle |
|---|---|
| `custom_components/dashboard_history/analyze.py` | `badge_containers`, `match_badges`; `containers`-Parameter an `match_cards`, `_slots`, `_present`; `fallback` an `_describe`; `kind` an `_step`; Badge-Schritte in `plan_undo`; Badge-Einträge in `_explain`; `Summary.badges`, `change_message`, `_COUNT` |
| `custom_components/dashboard_history/restore.py` | `apply_undo` entfernt und setzt Badge-Schritte ein, legt `badges:` an |
| `tests/test_analyze.py`, `tests/test_restore.py` | neue Tests |
| `tests/integration/run_checks.py` | neuer Abschnitt `run_badges` |
| `docs/limitations.md`, `docs/how-it-works.md`, `docs/superpowers/status.md` | Stand nachziehen |

---

### Task 1: Badges zuordnen

**Files:**
- Modify: `custom_components/dashboard_history/analyze.py`
- Test: `tests/test_analyze.py`

**Interfaces:**
- Produces: `badge_containers(view: dict) -> Iterator[tuple[tuple, list]]`; `match_cards(old, new, containers=card_containers) -> Matching`; `match_badges(old: dict, new: dict) -> Matching`; `_slots(config, keys, containers=card_containers)`; `_present(config, containers=card_containers)`; `_describe(card, depth=0, fallback="card")`.

- [ ] **Step 1: Tests schreiben**

```python
# -- badges (GitHub #29) ----------------------------------------------------

SUN = {"type": "entity", "entity": "sun.sun"}
MOON = {"type": "entity", "entity": "sensor.moon"}


def _badge_matching(old, new):
    m = analyze.match_badges(old, new)
    return (
        [s.card for s in m.removed],
        [s.card for s in m.added],
        [(o.card, n.card) for o, n in m.edited],
        [(o.view_key, n.view_key) for o, n in m.moved],
    )


def test_an_added_badge_is_found():
    old = {"views": [{"path": "home", "badges": []}]}
    new = {"views": [{"path": "home", "badges": [SUN]}]}
    assert _badge_matching(old, new) == ([], [SUN], [], [])


def test_an_edited_badge_is_an_edit():
    shown = {**SUN, "show_name": False}
    old = {"views": [{"path": "home", "badges": [SUN]}]}
    new = {"views": [{"path": "home", "badges": [shown]}]}
    assert _badge_matching(old, new) == ([], [], [(SUN, shown)], [])


def test_a_badge_moved_to_another_view_is_a_move():
    old = {"views": [{"path": "a", "badges": [SUN]}, {"path": "b", "badges": []}]}
    new = {"views": [{"path": "a", "badges": []}, {"path": "b", "badges": [SUN]}]}
    assert _badge_matching(old, new) == ([], [], [], [("a", "b")])


def test_a_badge_and_an_identical_card_never_meet():
    """Review focus 3: `type: entity` is a card and a badge."""
    old = {"views": [{"path": "home", "cards": [SUN], "badges": []}]}
    new = {"views": [{"path": "home", "cards": [], "badges": [SUN]}]}
    cards = analyze.match_cards(old, new)
    badges = analyze.match_badges(old, new)
    assert [s.card for s in cards.removed] == [SUN] and not cards.moved
    assert [s.card for s in badges.added] == [SUN] and not badges.moved


def test_badges_are_invisible_to_match_cards():
    old = {"views": [{"path": "home", "cards": [A], "badges": []}]}
    new = {"views": [{"path": "home", "cards": [A], "badges": [SUN]}]}
    m = analyze.match_cards(old, new)
    assert not (m.removed or m.added or m.edited or m.moved)


def test_a_badge_without_a_type_is_described_as_a_badge():
    """Review focus 5: the old form `{entity: …}`, three of them on the bank."""
    assert analyze._describe({"entity": "sun.sun"}, fallback="badge") == "badge: sun.sun"
    assert analyze._describe({"entity": "sun.sun"}) == "card: sun.sun"
```

- [ ] **Step 2: Scheitern prüfen**

Run: `python3 -m pytest tests/test_analyze.py -k "badge" -v`
Expected: FAIL – `AttributeError: module 'analyze' has no attribute 'match_badges'` bzw. `unexpected keyword argument 'fallback'` für fünf der sechs neuen Tests: »5 failed, 2 passed«. `test_badges_are_invisible_to_match_cards` ist schon grün – `match_cards` sieht Badges heute nicht – und steht als Wächter da, dass der `containers`-Parameter daran nichts ändert. Der Filter trifft außerdem `test_cards_sections_badges_path_type_and_views_are_not_settings` aus Vorhaben M; der ist grün und bleibt es.

- [ ] **Step 3: Umsetzen**

Nach `card_containers`:

```python
def badge_containers(view: dict) -> Iterator[tuple[tuple, list]]:
    """Yield a view's own badge list, with the path that locates it.

    Only the list beside `cards:` (GitHub #29). A badge inside a card -
    a heading card's own `badges:` - is part of that card's body and
    travels with it, so it is never looked at here.
    """
    if isinstance(view.get("badges"), list):
        yield ("badges",), view["badges"]
```

`_slots` bekommt den Parameter und nutzt ihn:

```python
def _slots(config: dict, keys: set, containers=card_containers) -> list[Slot]:
    """Every item of the named views, in the order they are written."""
    found: list[Slot] = []
    for view_index, (key, view) in enumerate(_views_by_key(config)):
        if key not in keys:
            continue
        for location, cards in containers(view):
            for index, card in enumerate(cards):
                found.append(Slot(key, view_index, view, location, index, card))
    return found
```

`match_cards`: Signatur zu `def match_cards(old: dict, new: dict, containers=card_containers) -> Matching:`, im Docstring nach dem ersten Satz ergänzen:

```
    `containers` says which lists are paired: cards by default, a view's
    badges for `match_badges`. Never both at once - a badge and a card
    can be byte-identical (`type: entity` is both), and one run over
    both would read a deleted card as "moved into the badges".
```

und im Rumpf `old_open = _slots(old, common)` / `new_open = _slots(new, common)` zu `_slots(old, common, containers)` / `_slots(new, common, containers)`.

Nach `match_cards`:

```python
def match_badges(old: dict, new: dict) -> Matching:
    """Pair the badges of two states - the same four passes, in their own world."""
    return match_cards(old, new, containers=badge_containers)
```

`_present`:

```python
def _present(config: dict, containers=card_containers) -> list[Slot]:
    """Every item of a state, with the place it sits in."""
    return _slots(config, {key for key, _ in _views_by_key(config)}, containers)
```

`_describe`: Signatur `def _describe(card: Any, depth: int = 0, fallback: str = "card") -> str:` und `kind = str(card.get("type", fallback))`. Der rekursive Aufruf bleibt `_describe(inner, depth + 1)` – was in einer Karte steckt, ist eine Karte.

- [ ] **Step 4: Suite**

Run: `python3 -m pytest tests/ -v` → 0 failed.

- [ ] **Step 5: Commit (nach Go des Nutzers)**

```bash
git add custom_components/dashboard_history/analyze.py tests/test_analyze.py
git commit -m "Match a view's badges in a world of their own" -m "Badges carry no id, like cards, so they get the same four passes - but
never together with cards: an entity badge and an entity card can be
byte-identical, and a shared run would read a deleted card as moved
into the badges. GitHub #29."
```

---

### Task 2: Badge-Schritte in `plan_undo`

**Files:**
- Modify: `custom_components/dashboard_history/analyze.py` (`_step`, `plan_undo`)
- Test: `tests/test_analyze.py`

**Interfaces:**
- Consumes: `match_badges`, `badge_containers`, `_present(..., containers)`, `_describe(..., fallback)` (Task 1).
- Produces: `_step(slot, action, expect, payload, label, kind="card")`. Badge-Schritte: `kind="badge"`, `location=("badges",)`, `index` = Position in der Liste, `label = "the badge <beschreibung>"`.

- [ ] **Step 1: Tests schreiben**

```python
def test_an_added_badge_is_undone():
    old = {"views": [{"path": "home", "badges": []}]}
    new = {"views": [{"path": "home", "badges": [SUN]}]}
    plan = analyze.plan_undo(old, new, new)
    assert plan.blocked is None
    assert [(s.action, s.kind, s.location, s.index) for s in plan.steps] == [
        ("remove", "badge", ("badges",), 0)
    ]


def test_a_badge_copied_on_other_views_is_found_in_its_own():
    """Review focus 1: stage 2 of the uniqueness question."""
    b = {"path": "b", "badges": [SUN]}
    c = {"path": "c", "badges": [SUN]}
    old = {"views": [{"path": "a", "badges": []}, b, c]}
    new = {"views": [{"path": "a", "badges": [SUN]}, b, c]}
    plan = analyze.plan_undo(old, new, new)
    assert plan.blocked is None
    assert [(s.action, s.view_path) for s in plan.steps] == [("remove", "a")]


def test_a_badge_moved_elsewhere_since_is_found_there():
    old = {"views": [{"path": "a", "badges": []}, {"path": "b", "badges": []}]}
    new = {"views": [{"path": "a", "badges": [SUN]}, {"path": "b", "badges": []}]}
    current = {"views": [{"path": "a", "badges": []}, {"path": "b", "badges": [SUN]}]}
    plan = analyze.plan_undo(old, new, current)
    assert [(s.action, s.view_path) for s in plan.steps] == [("remove", "b")]


def test_two_identical_badges_in_one_view_refuse():
    old = {"views": [{"path": "a", "badges": []}]}
    new = {"views": [{"path": "a", "badges": [SUN]}]}
    current = {"views": [{"path": "a", "badges": [SUN, SUN]}]}
    plan = analyze.plan_undo(old, new, current)
    assert plan.blocked == (
        "2 badges now look exactly like the badge entity: sun.sun, "
        "so an exact undo cannot tell them apart"
    )


def test_an_edited_badge_changed_again_refuses():
    shown = {**SUN, "show_name": False}
    old = {"views": [{"path": "a", "badges": [SUN]}]}
    new = {"views": [{"path": "a", "badges": [shown]}]}
    current = {"views": [{"path": "a", "badges": [{**SUN, "show_name": True}]}]}
    plan = analyze.plan_undo(old, new, current)
    assert "changed again after this" in plan.blocked


def test_a_deleted_badge_with_an_untouched_copy_elsewhere_is_put_back():
    """Review focus 2: the copy on "b" never left, so it is not this one back."""
    old = {"views": [{"path": "a", "badges": [SUN]}, {"path": "b", "badges": [SUN]}]}
    new = {"views": [{"path": "a", "badges": []}, {"path": "b", "badges": [SUN]}]}
    plan = analyze.plan_undo(old, new, new)
    assert [(s.action, s.kind, s.view_path) for s in plan.steps] == [
        ("insert", "badge", "a")
    ]


def test_a_deleted_badge_added_back_since_is_left_alone():
    old = {"views": [{"path": "a", "badges": [SUN]}]}
    new = {"views": [{"path": "a", "badges": []}]}
    current = {"views": [{"path": "a", "badges": [SUN]}]}
    plan = analyze.plan_undo(old, new, current)
    assert plan.blocked is None
    assert plan.steps == ()


def test_a_badge_only_change_passes_the_early_gate():
    old = {"views": [{"path": "a", "badges": [SUN]}]}
    new = {"views": [{"path": "a", "badges": [MOON]}]}
    plan = analyze.plan_undo(old, new, new)
    assert plan.blocked != "this change did not alter any cards"


def test_the_sole_surviving_badge_of_several_is_not_proof():
    """Review focus 6: the change left two, one went since - the one on
    "a" stood there before and is not the change's to take away."""
    old = {"views": [{"path": "a", "badges": [SUN]}, {"path": "b", "badges": []}]}
    new = {"views": [{"path": "a", "badges": [SUN]}, {"path": "b", "badges": [SUN]}]}
    current = {"views": [{"path": "a", "badges": [SUN]}, {"path": "b", "badges": []}]}
    plan = analyze.plan_undo(old, new, current)
    assert plan.blocked == (
        "the badge entity: sun.sun was changed again after this, so there "
        "is no exact version left to put back"
    )


def test_one_of_two_badges_gone_from_a_view_refuses():
    """Review focus 6, within one view: which of the two the change added is lost."""
    old = {"views": [{"path": "a", "badges": [SUN]}]}
    new = {"views": [{"path": "a", "badges": [SUN, SUN]}]}
    current = {"views": [{"path": "a", "badges": [SUN]}]}
    plan = analyze.plan_undo(old, new, current)
    assert "changed again after this" in plan.blocked


def test_a_badge_copy_added_elsewhere_since_is_not_the_deleted_one_back():
    """Review focus 7: back is counted only in the view it was deleted from."""
    old = {"views": [{"path": "a", "badges": [SUN]}, {"path": "c", "badges": []}]}
    new = {"views": [{"path": "a", "badges": []}, {"path": "c", "badges": []}]}
    current = {"views": [{"path": "a", "badges": []}, {"path": "c", "badges": [SUN]}]}
    plan = analyze.plan_undo(old, new, current)
    assert [(s.action, s.view_path) for s in plan.steps] == [("insert", "a")]


def test_one_badge_back_of_two_deleted_refuses():
    """Review focus 7: one back does not settle both, and which place it
    took is not in the states - [MOON, SUN] now could be either SUN."""
    old = {"views": [{"path": "a", "badges": [SUN, MOON, SUN]}]}
    new = {"views": [{"path": "a", "badges": [MOON]}]}
    current = {"views": [{"path": "a", "badges": [MOON, SUN]}]}
    plan = analyze.plan_undo(old, new, current)
    assert plan.blocked == (
        "only some of the copies of the badge entity: sun.sun this change "
        "deleted are back, so an exact undo cannot tell which are missing"
    )


def test_two_badges_deleted_and_both_back_is_nothing_to_do():
    old = {"views": [{"path": "a", "badges": [SUN, SUN]}]}
    new = {"views": [{"path": "a", "badges": []}]}
    current = {"views": [{"path": "a", "badges": [SUN, SUN]}]}
    plan = analyze.plan_undo(old, new, current)
    assert plan.blocked is None and plan.steps == ()


def test_a_badge_back_in_one_view_does_not_count_for_another():
    """Review focus 7: deleted from "a" and "b", added back only on "a"."""
    old = {"views": [{"path": "a", "badges": [SUN]}, {"path": "b", "badges": [SUN]}]}
    new = {"views": [{"path": "a", "badges": []}, {"path": "b", "badges": []}]}
    current = {"views": [{"path": "a", "badges": [SUN]}, {"path": "b", "badges": []}]}
    plan = analyze.plan_undo(old, new, current)
    assert [(s.action, s.view_path) for s in plan.steps] == [("insert", "b")]


def test_a_badge_of_a_pathless_view_that_moved_refuses():
    old = {"views": [{"badges": []}, {"path": "z", "cards": []}]}
    new = {"views": [{"badges": [SUN]}, {"path": "z", "cards": []}]}
    current = {"views": [{"path": "new"}, {"badges": [SUN]}, {"path": "z", "cards": []}]}
    plan = analyze.plan_undo(old, new, current)
    assert plan.blocked == analyze._POSITION_REFUSAL
```

- [ ] **Step 2: Scheitern prüfen**

Run: `python3 -m pytest tests/test_analyze.py -k "badge" -v`
Expected: FAIL für alle 15 neuen Tests – »this change did not alter any cards« bzw. keine Schritte, weil jede reine Badge-Änderung noch an der frühen Bedingung hängen bleibt. Die Tests aus Task 1 und der M-Test bleiben grün.

- [ ] **Step 3: `_step`**

```python
def _step(
    slot: Slot, action: str, expect: Any, payload: Any, label: str, kind: str = "card"
) -> UndoStep:
    """A card or badge step at the place `slot` names."""
    return UndoStep(
        action=action,
        kind=kind,
        view_path=slot.view.get("path"),
        view_index=slot.view_index,
        location=slot.location,
        index=slot.index,
        expect=expect,
        payload=payload,
        label=label,
    )
```

- [ ] **Step 4: `plan_undo`**

Nach `matching = match_cards(before, after)`:

```python
    badge_matching = match_badges(before, after)
```

In die frühe Bedingung zusätzlich:

```python
        or badge_matching.removed
        or badge_matching.added
        or badge_matching.edited
        or badge_matching.moved
```

Nach dem `steps.extend(...)` der geparkten Karten (Vorhaben L) und vor dem Kommentar `# Whole views, which \`match_cards\` leaves out on purpose` einfügen:

```python
    # Badges (GitHub #29): the same table as cards, counted in their own
    # world. The same badge on several views is ordinary - 6 of 23 on the
    # installation this was built against - so "exactly once" is asked in
    # two stages: on the whole dashboard, and failing that, in the view
    # the change left it in. Both answer decision 15's question; the
    # second only asks it where the badge was left. And both compare
    # today with what the change left: one standing today, out of several
    # the change left, may be the one that was there before it.
    badge_now: dict[str, list[Slot]] = {}
    for slot in _present(current, badge_containers):
        badge_now.setdefault(fingerprint(slot.card), []).append(slot)
    badge_then: dict[str, list[Slot]] = {}
    for slot in _present(after, badge_containers):
        badge_then.setdefault(fingerprint(slot.card), []).append(slot)

    def sole_badge(badge: Any, view_key: Any, label: str) -> tuple[Slot | None, str | None]:
        mark = fingerprint(badge)
        found, left = badge_now.get(mark, []), badge_then.get(mark, [])
        if len(found) == 1 and len(left) == 1:
            return found[0], None
        mine = [slot for slot in found if slot.view_key == view_key]
        mine_then = [slot for slot in left if slot.view_key == view_key]
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

    # Counted, not looked up, and only in the badge's own view: a copy on
    # another view - there all along or added since - is not this badge
    # coming back. `came_back` is how many more stand there now than the
    # change left; `deleted` how many alike it took from that view.
    deleted: dict[tuple[str, Any], int] = {}
    for old_slot in badge_matching.removed:
        place = (fingerprint(old_slot.card), old_slot.view_key)
        deleted[place] = deleted.get(place, 0) + 1

    def came_back(mark: str, view_key: Any) -> int:
        def mine(slots: list[Slot]) -> int:
            return sum(1 for slot in slots if slot.view_key == view_key)

        return mine(badge_now.get(mark, [])) - mine(badge_then.get(mark, []))

    def badge_label(badge: Any) -> str:
        return f"the badge {_describe(badge, fallback='badge')}"

    for old_slot, new_slot in (*badge_matching.edited, *badge_matching.moved):
        label = badge_label(new_slot.card)
        here, why = sole_badge(new_slot.card, new_slot.view_key, label)
        if here is None:
            return UndoPlan(blocked=why)
        steps.append(_step(here, "remove", new_slot.card, None, label, kind="badge"))
        steps.append(_step(old_slot, "insert", None, old_slot.card, label, kind="badge"))

    for new_slot in badge_matching.added:
        label = badge_label(new_slot.card)
        here, why = sole_badge(new_slot.card, new_slot.view_key, label)
        if here is None:
            return UndoPlan(blocked=why)
        steps.append(_step(here, "remove", new_slot.card, None, label, kind="badge"))

    for old_slot in badge_matching.removed:
        label = badge_label(old_slot.card)
        mark = fingerprint(old_slot.card)
        back = came_back(mark, old_slot.view_key)
        if back >= deleted[(mark, old_slot.view_key)]:
            continue
        if back > 0:
            # Some of several alike are back: which places they took is
            # not in the states, and picking one would be a guess.
            return UndoPlan(
                blocked=(
                    f"only some of the copies of {label} this change deleted "
                    f"are back, so an exact undo cannot tell which are missing"
                )
            )
        steps.append(_step(old_slot, "insert", None, old_slot.card, label, kind="badge"))
```

- [ ] **Step 5: Suite**

Run: `python3 -m pytest tests/ -v` → 0 failed.

- [ ] **Step 6: Commit (nach Go des Nutzers)**

```bash
git add custom_components/dashboard_history/analyze.py tests/test_analyze.py
git commit -m "Plan undo steps for a view's badges" -m "Decision 15's table, applied to badges in their own world. \"Exactly
once\" is asked on the dashboard and then in the badge's own view,
because the same badge on several views is ordinary. A deleted badge
counts as back only if there is more of it than the change left - a
copy that never left is not it. GitHub #29."
```

---

### Task 3: `restore.apply_undo` für Badges

**Files:**
- Modify: `custom_components/dashboard_history/restore.py`
- Test: `tests/test_restore.py`

**Interfaces:**
- Consumes: Badge-Schritte (Task 2).
- Produces: `apply_undo` entfernt `kind="badge"`-Schritte zusammen mit Kartenschritten (absteigend nach Index) und setzt sie mit den nicht geparkten Einsetzungen ein; eine fehlende oder nicht-listige `badges:` wird angelegt.

- [ ] **Step 1: Tests schreiben**

```python
# -- badges (GitHub #29) -------------------------------------------------

SUN = {"type": "entity", "entity": "sun.sun"}
MOON = {"type": "entity", "entity": "sensor.moon"}


def test_a_deleted_badge_comes_back_beside_an_untouched_copy():
    old = {"views": [{"path": "a", "badges": [SUN]}, {"path": "b", "badges": [SUN]}]}
    new = {"views": [{"path": "a", "badges": []}, {"path": "b", "badges": [SUN]}]}
    assert restore.apply_undo(new, analyze.plan_undo(old, new, new)) == old


def test_a_badge_goes_into_a_view_that_has_no_badges_list():
    """Review focus 4."""
    old = {"views": [{"path": "a", "badges": [SUN]}]}
    new = {"views": [{"path": "a"}]}
    assert restore.apply_undo(new, analyze.plan_undo(old, new, new)) == old


def test_an_edited_badge_goes_back_to_its_place():
    shown = {**SUN, "show_name": False}
    old = {"views": [{"path": "a", "badges": [SUN, MOON]}]}
    new = {"views": [{"path": "a", "badges": [shown, MOON]}]}
    assert restore.apply_undo(new, analyze.plan_undo(old, new, new)) == old


def test_a_badge_and_a_card_undone_together():
    old = {"views": [{"path": "a", "cards": [A], "badges": []}]}
    new = {"views": [{"path": "a", "cards": [], "badges": [SUN]}]}
    assert restore.apply_undo(new, analyze.plan_undo(old, new, new)) == old


def test_a_badge_written_as_a_bare_string_is_undone():
    """The old form `- sun.sun`: no weak key, so read as delete + add - still exact."""
    old = {"views": [{"path": "a", "badges": ["sun.sun"]}]}
    new = {"views": [{"path": "a", "badges": ["sensor.moon"]}]}
    assert restore.apply_undo(new, analyze.plan_undo(old, new, new)) == old
```

- [ ] **Step 2: Scheitern prüfen**

Run: `python3 -m pytest tests/test_restore.py -k badge -v`
Expected: »4 failed, 1 passed«. Die vier scheitern, weil Badge-Schritte beim Entfernen übergangen werden (`kind == "card"`) bzw. beim Einsetzen die Liste fehlt. `test_a_deleted_badge_comes_back_beside_an_untouched_copy` ist schon grün: Er braucht nur ein Einsetzen in eine vorhandene Liste, und das findet `_cards_for` über `_cards_at(view, ("badges",))` bereits. Er bleibt als Wächter für Review-Fokus 2 auf der Ebene des geschriebenen Ergebnisses.

- [ ] **Step 3: Umsetzen**

Neue Hilfsfunktion nach `_cards_for`:

```python
def _badges_for(views: list, step: UndoStep) -> list:
    """The badge list a step points at, created when the view has none."""
    view = _find_view(views, step)
    if view is None:
        raise LookupError(
            f"the view {step.label} belonged to no longer exists "
            f"(path={step.view_path!r}, index={step.view_index})"
        )
    badges = view.get("badges")
    if not isinstance(badges, list):
        badges = []
        view["badges"] = badges
    return badges
```

In `apply_undo` die Entfernungsschleife für Karten von `(step for step in removals if step.kind == "card")` auf `(step for step in removals if step.kind in ("card", "badge"))` ändern. Das Entfernen einer Badge findet ihre Liste über `_cards_for` (`_cards_at` läuft den Pfad `("badges",)` wie jeden anderen).

In der Schleife über die nicht geparkten Einsetzungen (aus Vorhaben L) die Zeile `cards = _cards_for(views, step)` ersetzen durch:

```python
        cards = _badges_for(views, step) if step.kind == "badge" else _cards_for(views, step)
```

- [ ] **Step 4: Suite**

Run: `python3 -m pytest tests/ -v` → 0 failed.

- [ ] **Step 5: Commit (nach Go des Nutzers)**

```bash
git add custom_components/dashboard_history/restore.py tests/test_restore.py
git commit -m "Apply badge steps in an undo" -m "Badge steps are removed and inserted in the same order as card steps;
their lists never shift each other's indices. A view without a badges
list gets one when a badge goes back into it. GitHub #29."
```

---

### Task 4: Badges in Erklärung und Verlaufszeile

**Files:**
- Modify: `custom_components/dashboard_history/analyze.py` (`_PAST`, `_FUTURE`, `_explain`, `Summary`, `summarize`, `change_message`, `_COUNT`)
- Test: `tests/test_analyze.py`

**Interfaces:**
- Produces: `Entry.what == "badge"`; `Summary.badges: int = 0`; Zählteil `"N badge changed"`/`"N badges changed"` nach dem Einstellungsteil.

- [ ] **Step 1: Tests schreiben**

```python
def test_a_badge_is_explained_as_a_badge():
    old = {"views": [{"path": "home", "badges": []}]}
    new = {"views": [{"path": "home", "badges": [SUN]}]}
    [group] = analyze.explain_change(old, new).groups
    assert [(e.what, e.text) for e in group.entries] == [
        ("badge", "the badge entity: sun.sun was added")
    ]


def test_a_badge_moved_to_another_view_says_where():
    old = {"views": [{"path": "a", "title": "A", "badges": [SUN]},
                     {"path": "b", "title": "Küche", "badges": []}]}
    new = {"views": [{"path": "a", "title": "A", "badges": []},
                     {"path": "b", "title": "Küche", "badges": [SUN]}]}
    [group] = analyze.explain_change(old, new).groups
    assert [e.text for e in group.entries] == [
        'the badge entity: sun.sun was moved to "Küche"'
    ]


def test_badges_come_between_settings_and_cards():
    old = {"views": [{"path": "home", "icon": "a", "badges": [], "cards": []}]}
    new = {"views": [{"path": "home", "icon": "b", "badges": [SUN], "cards": [A]}]}
    [group] = analyze.explain_change(old, new).groups
    assert [e.what for e in group.entries] == ["setting", "badge", "card"]


def test_badges_are_counted_in_the_history_line():
    old = {"views": [{"path": "home", "badges": []}]}
    new = {"views": [{"path": "home", "badges": [SUN, MOON]}]}
    assert analyze.change_message("dash", old, new, "save") == "dash: 2 badges changed"
    assert not analyze.message_adds("dash: 2 badges changed")
    assert analyze.message_adds("dash: 1 added, 1 badge changed")


def test_a_badge_inside_a_heading_card_is_part_of_the_card():
    """A heading card's own `badges:` travel with the card, never as badges."""
    heading = {"type": "heading", "heading": "Top", "badges": [SUN]}
    grown = {**heading, "badges": [SUN, MOON]}
    old = {"views": [{"path": "a", "cards": [heading], "badges": []}]}
    new = {"views": [{"path": "a", "cards": [grown], "badges": []}]}
    [group] = analyze.explain_change(old, new).groups
    assert [e.what for e in group.entries] == ["card"]
```

- [ ] **Step 2: Scheitern prüfen**

Run: `python3 -m pytest tests/test_analyze.py -k "explained_as_a_badge or says_where or between_settings or counted_in_the_history or inside_a_heading" -v`
Expected: »4 failed, 2 passed«. Grün sind `test_a_setting_only_save_is_counted_in_the_history_line` aus Vorhaben M, den der Filter mittrifft, und `test_a_badge_inside_a_heading_card_is_part_of_the_card` – ein Wächter, dass `_explain` nach diesem Task die Badges einer Heading-Karte nicht als Ansichts-Badges nennt.

- [ ] **Step 3: Wörter**

In `_PAST`:

```python
    ("badge", "removed"): "the badge {label} was deleted",
    ("badge", "added"): "the badge {label} was added",
    ("badge", "edited"): "the badge {label} was changed",
    ("badge", "moved"): "the badge {label} was moved",
    ("badge", "moved_to"): "the badge {label} was moved to {where}",
```

In `_FUTURE`:

```python
    ("badge", "removed"): "the badge {label} will be deleted",
    ("badge", "added"): "the badge {label} comes back",
    ("badge", "edited"): "the badge {label} goes back to how it was",
    ("badge", "moved"): "the badge {label} moves back to where it was",
    ("badge", "moved_to"): "the badge {label} moves back to {where}",
```

- [ ] **Step 4: `_explain`**

Nach dem Block, der `settings_by_view` füllt (Vorhaben M):

```python
    badges_by_view: dict[Any, list[Entry]] = {}
    badge_matching = match_badges(old, new)

    def badge(key: Any, kind: str, item: Any, where: str | None = None) -> None:
        label = _describe(item, fallback="badge")
        text_key = ("badge", "moved_to" if where else kind)
        badges_by_view.setdefault(key, []).append(
            Entry(
                kind=kind,
                what="badge",
                label=label,
                text=words[text_key].format(label=label, where=where),
            )
        )

    for slot in badge_matching.removed:
        badge(slot.view_key, "removed", slot.card)
    for slot in badge_matching.added:
        badge(slot.view_key, "added", slot.card)
    for _was, now in badge_matching.edited:
        badge(now.view_key, "edited", now.card)
    for was, now in badge_matching.moved:
        where = _where(was, now) if _place(was) != _place(now) else None
        badge(was.view_key, "moved", was.card, where)
```

In der Ansichtsschleife die Zeile (aus Vorhaben M)

```python
        entries = [*settings_by_view.get(key, []), *by_view.get(key, [])]
```

ersetzen durch

```python
        entries = [
            *settings_by_view.get(key, []),
            *badges_by_view.get(key, []),
            *by_view.get(key, []),
        ]
```

- [ ] **Step 5: Verlaufszeile**

`Summary`: `badges: int = 0` nach `settings`.

`summarize`: vor dem `return` `badges = match_badges(old, new)`, im Rückgabewert `badges=len(badges.removed) + len(badges.added) + len(badges.edited) + len(badges.moved),`.

`change_message`: in `parts` nach dem Einstellungsteil

```python
        f"{counts.badges} badge{'s' if counts.badges != 1 else ''} changed"
        if counts.badges
        else "",
```

`_COUNT`:

```python
_COUNT = re.compile(
    r"^\d+ (?:views? (?:added|removed)|added|removed|edited|moved"
    r"|settings? changed|badges? changed)$"
)
```

- [ ] **Step 6: Suite**

Run: `python3 -m pytest tests/ -v` → 0 failed.

- [ ] **Step 7: Commit (nach Go des Nutzers)**

```bash
git add custom_components/dashboard_history/analyze.py tests/test_analyze.py
git commit -m "Explain and count a view's badges" -m "A badge-only save was \"no card changes\" with nothing named above the
diff. Badges are named now, as badges, between the view's settings and
its cards - the order Home Assistant shows them in - and counted in the
history line. GitHub #29."
```

---

### Task 5: Laufende Instanz und Dokumentation

**Files:**
- Modify: `tests/integration/run_checks.py`
- Modify: `docs/limitations.md`, `docs/how-it-works.md`, `README.md`, `docs/superpowers/status.md`

- [ ] **Step 1: `run_badges`**

Nach `run_settings` (Vorhaben M) einfügen, im Hauptblock nach `asyncio.run(run_settings(access))` aufrufen:

```python
async def run_badges(access: str) -> None:
    """A badge added beside a copy on another view, undone (GitHub #29)."""
    key = "dh-badges"
    sun = {"type": "entity", "entity": "sun.sun"}

    async with Socket(access) as socket:
        listed = (await socket.call("lovelace/dashboards/list")) or []
        if not any(entry.get("url_path") == key for entry in listed):
            await socket.call("lovelace/dashboards/create", url_path=key, title=key)
            await asyncio.sleep(3)

        async def save(config: dict) -> list:
            # `_wait_for_new_state`, not `_wait_until_recorded`: see
            # `save` in `run_settings` (Vorhaben M) and in `run_undo`.
            rows = (
                await socket.call("dashboard_history/history", dashboard=key, limit=1)
            )["changes"]
            await socket.call("lovelace/config/save", url_path=key, config=config)
            return await _wait_for_new_state(
                socket, key, rows[0]["revision"] if rows else "", RECORDING_WAIT
            )

        other = {"path": "other", "title": "Other", "badges": [sun], "cards": []}
        await save({"views": [{"path": "home", "title": "Home", "badges": [], "cards": []}, other]})
        added = await save({"views": [{"path": "home", "title": "Home", "badges": [sun], "cards": []}, other]})
        entry = added[0]
        check(
            "a badge-only save is counted",
            entry["message"].endswith("1 badge changed"),
            entry["message"],
        )
        asked = await socket.call(
            "dashboard_history/undo_change", dashboard=key, revision=entry["revision"]
        )
        check(
            "and undoable although the same badge stands on another view",
            asked.get("available") is True,
            asked.get("reason", ""),
        )
        await socket.call(
            "dashboard_history/undo_change",
            dashboard=key,
            revision=entry["revision"],
            confirm=True,
            expected_parked=[],
        )
        await asyncio.sleep(2)
        live = await socket.call("lovelace/config", url_path=key)
        badges = [view.get("badges") for view in live["views"]]
        check(
            "and only the added one goes",
            badges == [[], [sun]],
            f"{badges}",
        )

        listed = (await socket.call("lovelace/dashboards/list")) or []
        mine = next((e for e in listed if e.get("url_path") == key), None)
        if mine is not None:
            await socket.call("lovelace/dashboards/delete", dashboard_id=mine["id"])
```

- [ ] **Step 2: Prüfen**

Run: `python3 -m pytest tests/ -v` → 0 failed; `python3 tests/integration/run_checks.py` → alle grün.

- [ ] **Step 3: Doku**

`docs/limitations.md`, Tabellenzeile »Badge added, edited, or deleted«: ersetzen durch

`| **Badge** added, edited, moved or deleted | Named, e.g. *the badge entity: sun.sun was added* | **Exact** while the badge is unchanged since | Not offered | **Works** |`

`docs/how-it-works.md`, Abschnitt »Badges«: vom ersten Satz bis einschließlich des Satzes, den Vorhaben M dahinter eingefügt hat (`Until badges get the same treatment ([issue #29](…)), that is how it stays for them.`), ersetzen durch – der M-Satz wäre danach falsch, und der Verweis auf #29 steht im Ersatz:

```markdown
A view's own badges (the list beside `cards:`) carry no identifier either, so since <Datum> they are matched the way cards are — in a world of their own, never paired with a card, even where a badge and a card are byte-identical ([issue #29](https://github.com/PPP01/ha-dashboard-history/issues/29)). Because the same badge commonly stands on several views, *Undo this change* looks for the badge first on the whole dashboard and then in the view the change left it in; in either place exactly one has to stand there today, and the change has to have left exactly one there too. A deleted badge counts as already back only where its own view has more of it than the change left. Badges are not offered by *Put back*; *Undo this change* and the whole-state restore bring a deleted one back.
```

Im Satz direkt dahinter, den Vorhaben M geschrieben hat, `Named settings are different, and handled since` ersetzen durch `Named settings are simpler, and handled since`. Sonst bezieht sich »different« auf den gelöschten Satz über Badges, die keinen Namen haben.

`docs/limitations.md`, Abschnitt `### 2. Badges are outside the card comparison`: Überschrift und Liste bis vor `### 3. Sections in detail` ersetzen durch:

```markdown
### 2. Badges are matched in a world of their own

Home Assistant stores badges beside the view's card list, and like cards they carry no identifier. Since <Datum> they are matched the way cards are, but never paired with a card — an `entity` badge and an `entity` card can be byte-identical ([issue #29](https://github.com/PPP01/ha-dashboard-history/issues/29)). As a result:
- A badge change is named in the explanation (*the badge entity: sun.sun was added*) and counted in the history line (`1 badge changed`).
- *Undo this change* takes it back while the badge is unchanged since. The same badge commonly stands on several views, so it is looked for on the whole dashboard and then in the view the change left it in; where neither settles it, the undo refuses.
- A deleted badge counts as already back only if its own view has more of it today than the change left — a copy on another view is not it.
- *Put back* does not offer badges.
```

`docs/limitations.md`, Abschnitt `### Badges are outside the comparison` (hart umbrochen wie seine Nachbarn): Überschrift und Text bis vor `### Sections in detail` ersetzen durch – bei 72 Zeichen umbrochen:

```markdown
### Badges

Since <Datum>, a view's badges are matched like cards, in a world of
their own — see section 2 above. What remains is *Put back*: it never
offers a badge. A deleted badge comes back through *Undo this change*,
or by setting the dashboard back to a state that had it.
```

`README.md`, Punkt `- **Lovelace badges:** …` unter »Boundaries & Intentional Refusals« ersetzen durch:

```markdown
- **Lovelace badges are never offered by *Put back*.** A change to a view's badges is named in the history and can be undone; a deleted badge comes back through *Undo this change* or a whole-dashboard restore.
```

Prüfen: `grep -n -i badge docs/limitations.md docs/how-it-works.md README.md` – keine Fundstelle sagt mehr, eine Badge-Änderung sei `no card changes`, nicht beschreibbar oder nur über den ganzen Stand zu holen. Die drei Shield-Zeilen oben im README (`img.shields.io/badge/…`) sind keine Lovelace-Badges.

`docs/superpowers/status.md`: Eintrag `- **Umgesetzt am <Datum>** (GitHub-Issue [#29](…), Vorhaben N): …` – Zuordnung als eigene Welt, zweistufige Eindeutigkeit, gezählte »schon zurück«-Regel, und der Verweis auf die beiden offenen Karten-Befunde vom 2026-09-24 und 2026-09-25 (beide Regeln stehen für Karten noch aus).

`<Datum>` ist das Datum des Commits, `YYYY-MM-DD`.

- [ ] **Step 4: Commit (nach Go des Nutzers)**

```bash
git add tests/integration/run_checks.py docs/limitations.md docs/how-it-works.md README.md docs/superpowers/status.md
git commit -m "Check and document undo of badges" -m "The running instance confirms that a badge added beside a copy on
another view is counted, undoable, and taken away alone; the docs stop
saying badges are only restored with the whole state. GitHub #29."
```

---

## Self-review notes

- **Spec-Abdeckung:** Abschnitt 1 (getrennte Welt) → Task 1; Abschnitt 2 (Tabelle, zweistufige Eindeutigkeit, gezählte »schon zurück«-Regel) → Task 2; Abschnitt 3 (Schritte, Anwendung, Liste anlegen) → Task 3; Abschnitt 4 (Wörter, Reihenfolge, Verlaufszeile) → Task 4; Test-Plan → Tasks 1–5.
- **Abhängigkeiten:** Task 2 setzt den `steps.extend(...)` der geparkten Karten aus L voraus, Task 3 die geteilte Einsetzschleife aus L, Task 4 `settings_by_view` und den Einstellungsteil der Verlaufszeile aus M.
- **Nicht Teil dieses Plans, ausdrücklich:** dieselbe gezählte »schon zurück«-Regel für Karten und der Vergleich »heute genau eine« gegen »damals genau eine« für Karten. Beide Fehler sind dort nachgewiesen (`status.md`, Befunde vom 2026-09-24 und 2026-09-25), gehören aber in eigene Issues mit eigenen Tests. Der `status.md`-Eintrag aus Task 5 verweist auf beide.

## Review vom 2026-09-25 (Fable) und was daraus wurde

Geprüft in einer frischen Sitzung, mit Simulation: L Task 1–2 und M Task 1–5 auf eine Kopie angewendet, dann N. Jede Änderung unten ist in einer Kopie dieser Simulation nachgeprüft: der Plan-Code wörtlich übernommen, alle Plan-Tests grün, die ganze Suite 819 passed, 0 failed. Die Zahl hängt an der Prüfbank.

- **K1 – Stufe 1 und 2 entfernen eine Fremde. Angenommen.** »Heute genau eine« bewies nichts, wenn die Änderung mehrere hinterlassen hatte: Die einzige Überlebende konnte die sein, die schon vorher dastand. `sole_badge` verlangt jetzt in Stufe 1 dashboardweit und in Stufe 2 in der eigenen Ansicht »damals genau eine und heute genau eine«. Dabei hat sich auch die Meldung geklärt. Steht in der eigenen Ansicht heute weniger als damals, heißt es »changed again after this«, sonst »N badges now look exactly like …« mit N ≥ 2. Damit entfällt das »1 badges«, das der Reviewer in seinem Vorschlag noch sah. Zwei Tests (Review-Fokus 6). Spec, Abschnitt 2, entsprechend präzisiert. Am heutigen Code nachgestellt, hat die Karten-Seite dieselbe Lücke und schreibt dort **tatsächlich falsch**. Das steht als eigener Befund in `status.md` und gehört nicht zu diesem Plan.
- **K2 – `back_already` zählte dashboardweit. Angenommen, Spec geändert.** Die Spec selbst war unscharf (»in der Ansicht … oder im ganzen Dashboard«). Gezählt wird jetzt nur in der eigenen Ansicht. Den Preis nennt die Spec: Wurde eine gelöschte Badge von Hand auf einer anderen Ansicht neu angelegt, kommt sie zusätzlich am alten Platz zurück. Das ist additiv nach Entscheidung 4 und besser als ein falsches »nichts zu tun«. Der Vorschlag im Karten-Befund in `status.md` ist entsprechend korrigiert.
- **K3 – Eine Rückkehr tilgte mehrere Löschungen. Angenommen.** Der Überschuss wird je `(Fingerabdruck, Ansicht)` einmal berechnet und je Löschung um eins abgebaut. Zwei Tests.
- **W1 – Drei Doku-Stellen blieben falsch. Angenommen.** Task 5 ersetzt jetzt auch `docs/limitations.md` Abschnitt 2, den Abschnitt »Badges are outside the comparison« und den Badge-Punkt im README, und es gibt einen Prüfbefehl.
- **W2 – Ein Task-3-Test ist vorab grün. Angenommen.** Als Wächter gekennzeichnet, Erwartung »4 failed, 1 passed«. Nachgeprüft mit einer Kopie ohne die `restore.py`-Änderung.
- **Kleinigkeiten:**
  - Die Filter-Erwartungen in Task 1 und Task 4 nennen jetzt den M-Test, den der Filter mittrifft. Beim Nachzählen kam in Task 1 ein zweiter hinzu, den der Reviewer nicht nannte: `test_badges_are_invisible_to_match_cards` ist schon grün und ebenfalls als Wächter gekennzeichnet (»5 failed, 2 passed«).
  - Der hängende Satzanfang »Named settings are different« wird mit ersetzt.
  - Drei Randfall-Tests sind ergänzt: Zeichenketten-Badge (Task 3), pfadlose Ansicht mit wackelnder Position (Task 2), Badge in einer Heading-Karte (Task 4, als Wächter).
- **Kleinigkeit ohne Änderung:** Beim Entfernen einer Badge nennt die Fehlermeldung von `_cards_for` die Liste »card list«. Sie fällt nur, wenn zwischen Planen und Anwenden die `badges:`-Liste verschwindet. Für diesen Fall ist ein eigener Wortlaut mehr Code, als er wert ist.
- **Nachprüfung am 2026-09-25:** K1, K2, K3, W1, W2, die Filter-Erwartungen und der neue Karten-Befund sind als adressiert bestätigt. Belegt ist das an vier zurückgebauten Zwischenständen und an 45.360 erschöpfend durchgerechneten Kombinationen. Die Nachprüfung brachte zwei Kleinigkeiten, beide übernommen:
  - **Die K3-Korrektur riet eine Position.** Wurden zwei gleiche gelöscht und kam eine davon zurück, wurde der Überschuss immer dem ersten gelöschten Platz gutgeschrieben. Bei `[SUN, MOON, SUN]` → `[MOON]`, heute `[MOON, SUN]`, entstand `[MOON, SUN, SUN]`. Nach der Hard Rule »refused, never guessed« verweigert der Undo jetzt, wenn nur ein Teil gleicher Gelöschter zurück ist (»only some of the copies … are back«). `surplus` wird dafür zu `deleted` plus `came_back`. Der Test `test_one_badge_back_accounts_for_one_deletion_only` ist ersetzt durch `test_one_badge_back_of_two_deleted_refuses` (das Szenario des Reviewers) und `test_two_badges_deleted_and_both_back_is_nothing_to_do`. Der Preis ist null, denn auf der Prüfbank steht keine Badge zweimal in derselben Ansicht. Spec, Abschnitt 2 und Tabelle, sowie der Vorschlag in `status.md` sind angepasst. Simuliert: 821 passed, 0 failed.
  - **Der `how-it-works`-Text sagte »exactly as many as the change left«.** Er sagt jetzt »exactly one … and the change has to have left exactly one there too«.
- **Ohne Änderung, bewusst:** Verlaufszeile und Erklärung ordnen unterschiedlich (Zeile: added … setting … badge; Erklärung: Einstellung, Badge, Karte). Die Zeile hält die gewohnte Zählreihenfolge, die Erklärung die Reihenfolge auf dem Schirm.
