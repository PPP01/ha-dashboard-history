# Ganze entfernte Section parken – Implementierungsplan

> **Für agentische Umsetzer:** ERFORDERLICHER SUB-SKILL: `superpowers:subagent-driven-development` (empfohlen) oder `superpowers:executing-plans`. Schritte mit Checkbox-Syntax (`- [ ]`) abhaken.

**Ziel:** Ist eine ganze Section entfernt worden und ihr Platz in der Reihe nicht mehr beweisbar, kommen ihre Karten in »Imported cards« (`cards:` der Ansicht) zurück, statt dass Undo und »Put back« verweigern (GitHub #39).

**Architektur:** Undo: `_plan_sections` bekommt einen optionalen Parameter `ctx`; steht die Umordnungs-Verweigerung an und war die Entfernung die *einzige* Wirkung in der Ansicht, plant `_park_removed_section` je fehlender Karte einen `UndoStep` mit `parked=True` (die Form, die `apply_undo` seit Vorhaben L kennt – `apply_undo` bleibt unverändert). Put back: `restore.parks()`/`park()` nehmen `kind="section"` an; `operations.py` bleibt unverändert, denn `_reinsertion` ruft schon `parks`/`park` und meldet `[item.label]`.

**Tech Stack:** Python 3.12 (Entwicklung) / 3.14 (Container), pytest, ruff (Komplexitäts-Sperrklinke), import-linter, Home-Assistant-freier Kern.

**Spec:** `docs/superpowers/specs/2026-09-29-abschnitt-parken-design.md` (Commit `5a3f8b5`). Die Spec ist verbindlich; bei Widerspruch gilt sie, nicht dieser Plan.

## Global Constraints

- Der Kern (`analyze/`, `restore.py`, …) bleibt frei von Home Assistant; `restore.py` importiert `analyze` **nicht** zur Laufzeit (nur unter `TYPE_CHECKING`). Deshalb zählt `restore.py` keine Fingerabdrücke.
- **Kein `git`-Aufruf im Produktcode**, kein Monkey-Patching, kein Umbau von `apply_undo`, `analyze/removed.py`, `analyze/matching.py` und Panel.
- Verweigert wird »nie geraten« (Entscheidung 4): Die Richtung »Section hinzugekommen« bleibt hart verweigert, ebenso gemischte Änderungen (Variante A), mehrere entfernte Sections je Ansicht und jede Kartenänderung in derselben Ansicht.
- Der Parkweg ersetzt **nur** die beiden Umordnungs-Verweigerungen (»rearranged since«, »more than one section … changed since«) und sitzt hinter den frühen Prüfungen von `_plan_sections`.
- Überspringen statt Verweigern (Variante B): je Fingerabdruck werden `max(0, deleted − back)` Kopien geparkt, gezählt in der eigenen Ansicht.
- Code, Kommentare, Docstrings, Commit-Messages: **Englisch**. Journal (`docs/superpowers/`): Deutsch mit echten Umlauten und Guillemets »…«.
- Commit-Format: Betreff im Imperativ, groß, höchstens 50 Zeichen, Leerzeile, Body (72 Zeichen), Trailer `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Kein Push, kein Tag ohne ausdrückliches Go des Nutzers.
- Die Sperrklinke (`tools/complexity_ratchet.py`): Wird eine bekannte Funktion einfacher, muss `tools/complexity-baseline.json` **im selben Commit** gesenkt werden; neue Funktionen über dem Limit 10 brauchen einen Eintrag. `# noqa` hilft nicht.
- Arbeitsverzeichnis ist der Repo-Stamm auf dem Branch `feature/park-removed-section`. Die lokal geänderte `CLAUDE.md` gehört **nicht** in die Commits (`git add` nur mit ausdrücklichen Pfaden, nie `-A`/`.`).

## Review Focus

Eingaben, die die Spec nahelegt, die aber leicht durchrutschen; jede hat unten einen Test in der Aufgabe, die den Code besitzt:

1. **Zweites Undo derselben Änderung** darf nichts erneut anhängen (Aufgabe 1, `test_a_second_undo_parks_nothing_again`).
2. **Gleiche Karte mehrfach in der entfernten Section** (`deleted` = 2) und eine davon heute vorhanden → genau eine wird geparkt (Aufgabe 1).
3. **Eine gleiche Karte in einer anderen Ansicht** zählt nicht als Rückkehr (Aufgabe 1).
4. **`cards: null` oder fehlende `cards:`** in der Ansicht: wird angelegt, beim Undo wie bei Put back (Aufgabe 1 und 2).
5. **Section, deren Karten heute schon stehen**, darf bei Put back nicht angeboten werden (Annahme der Spec, Abschnitt 4; Aufgabe 2 belegt sie, statt sie zu glauben).

---

### Aufgabe 1: Planer – entfernte Section als geparkte Karten (Undo)

**Dateien:**
- Ändern: `custom_components/dashboard_history/analyze/undo.py` (`_plan_sections` Zeile ~121, `_plan_section_steps` Zeile ~361; neue Hilfsfunktionen)
- Ändern: `tools/complexity-baseline.json` (Eintrag `undo.py::_plan_sections`)
- Test: `tests/test_analyze.py` (am Ende anhängen; Helfer `_sectioned`, `_sec`, `_md`, `_row`, `A`, `B`, `C` existieren dort schon)

**Interfaces:**
- Verbraucht: `_pair_view_sections`, `_moved`, `_describe`, `fingerprint`, `_section_list`, `UndoStep`, `UndoContext.card_now`/`card_then` (über `_card_came_back(ctx, mark, view_key)`, Zeile ~473).
- Erzeugt:
  - `_plan_sections(key, before_view, after_view, current_view, current_index, change, ctx=None) -> UndoStep | tuple[UndoStep, ...] | str | None`. Ohne `ctx` verhält sie sich **byte-genau wie heute** (alle bestehenden Tests unverändert). Das Tupel gibt es nur im Parkweg.
  - `_rearranged(key, name, after_view, current_view) -> str | None` – die beiden Umordnungs-Verweigerungen, Wortlaut unverändert.
  - `_park_removed_section(ctx, key, current_view, current_index, removed) -> tuple[UndoStep, ...]`.
  - `_park_instead(refusal, ctx, key, current_view, current_index, removed, mixed) -> tuple[UndoStep, ...] | str`.

- [ ] **Schritt 1: Failing Tests schreiben**

An `tests/test_analyze.py` anhängen:

```python
# -- a removed section is parked, not refused (GitHub #39) -----------------


def _parked_state(*sections, cards=None, path="home"):
    view = _sectioned(*sections, path=path)
    if cards is not None:
        view["cards"] = cards
    return {"views": [view]}


def test_a_removed_section_is_parked_when_another_came_since():
    """The case from the ticket, measured on 2026-09-26 (test-2, view a3)."""
    before = _parked_state(_sec("a"), _sec("b"))
    after = _parked_state(_sec("b"))
    current = _parked_state(_sec("b"), _sec("n"))
    plan = analyze.plan_undo(before, after, current)
    assert plan.blocked is None
    assert [(s.action, s.kind, s.location, s.parked) for s in plan.steps] == [
        ("insert", "card", ("cards",), True)
    ]
    assert plan.steps[0].payload == _md("a")
    assert plan.parked == (analyze._describe(_md("a")),)
    assert restore.apply_undo(current, plan) == _parked_state(
        _sec("b"), _sec("n"), cards=[_md("a")]
    )


def test_a_removed_section_is_parked_when_two_others_swapped_since():
    before = _parked_state(_sec("a"), _sec("b"), _sec("c"))
    after = _parked_state(_sec("b"), _sec("c"))
    current = _parked_state(_sec("c"), _sec("b"))
    plan = analyze.plan_undo(before, after, current)
    assert plan.blocked is None
    assert plan.parked == (analyze._describe(_md("a")),)


def test_the_cards_of_a_removed_section_are_parked_in_their_old_order():
    before = _parked_state(_sec("a1", "a2", "a3"), _sec("b"))
    after = _parked_state(_sec("b"))
    current = _parked_state(_sec("b"), _sec("n"))
    plan = analyze.plan_undo(before, after, current)
    assert [s.payload for s in plan.steps] == [_md("a1"), _md("a2"), _md("a3")]
    assert restore.apply_undo(current, plan)["views"][0]["cards"] == [
        _md("a1"), _md("a2"), _md("a3")
    ]


def test_a_removed_section_alone_is_still_put_back_exactly():
    """Nothing rearranged since: the exact step, no asterisk."""
    before = _parked_state(_sec("a"), _sec("b"))
    after = _parked_state(_sec("b"))
    plan = analyze.plan_undo(before, after, after)
    assert plan.blocked is None
    assert [s.kind for s in plan.steps] == ["sections_list"]
    assert plan.parked == ()


def test_a_removed_section_and_a_moved_one_in_one_change_still_refuse():
    before = _parked_state(_sec("a"), _sec("b"), _sec("c"))
    after = _parked_state(_sec("c"), _sec("a"))
    current = _parked_state(_sec("c"), _sec("a"), _sec("n"))
    plan = analyze.plan_undo(before, after, current)
    assert plan.blocked is not None and "rearranged since" in plan.blocked


def test_an_added_section_that_was_rearranged_since_still_refuses():
    """Parking is for the removed direction only (decision 4)."""
    before = _parked_state(_sec("a"))
    after = _parked_state(_sec("a"), _sec("n"))
    current = _parked_state(_sec("a"), _sec("n"), _sec("m"))
    plan = analyze.plan_undo(before, after, current)
    assert plan.blocked is not None and "rearranged since" in plan.blocked


def test_two_removed_sections_still_refuse_although_parking_exists():
    before = _parked_state(_sec("a"), _sec("b"), _sec("c"))
    after = _parked_state(_sec("c"))
    current = _parked_state(_sec("c"), _sec("n"))
    plan = analyze.plan_undo(before, after, current)
    assert plan.blocked is not None and "cannot account for" in plan.blocked


def test_a_card_change_in_the_same_view_keeps_the_refusal():
    """Section removed, and a card of the surviving section deleted in that change.

    Measured against the matching: the survivor pairs as `how="cards"`,
    the removed one is proven whole. Nothing is parked - "all or nothing"
    (decision 2, variant A).
    """
    before = _parked_state(_sec("a", "x"), _sec("b"))
    after = _parked_state(_sec("a"))
    current = _parked_state(_sec("a"), _sec("n"))
    plan = analyze.plan_undo(before, after, current)
    assert plan.blocked is not None
    assert plan.steps == ()


def test_a_card_change_is_refused_even_when_the_removed_cards_stand_again():
    """The hole both reviews of the plan found (Gemini, 2026-09-29).

    Every card of the removed section is back, so parking has nothing to
    plan, `planned["sections"]` stays empty and `_sections_meet_cards`
    cannot see a view to protect. Without `_card_events_in` in
    `_park_instead` this became a partial undo of the card change alone.
    """
    before = _parked_state(_sec("a", "x"), _sec("b"))
    after = _parked_state(_sec("a"))
    current = _parked_state(_sec("a"), _sec("n"), cards=[_md("b")])
    plan = analyze.plan_undo(before, after, current)
    assert plan.blocked is not None
    assert plan.steps == ()


def test_a_removed_section_and_a_reset_one_in_one_change_still_refuse():
    before = _parked_state(_sec("b", column_span=1), _sec("a"))
    after = _parked_state(_sec("b", column_span=2))
    current = _parked_state(_sec("b", column_span=2), _sec("n"))
    plan = analyze.plan_undo(before, after, current)
    assert plan.blocked is not None and "rearranged since" in plan.blocked


def test_a_removed_and_an_added_section_in_one_change_never_reach_parking():
    """The view's section count is unchanged, so neither is proven whole:
    both stay unexplained and the early check refuses (`_settle_sections`)."""
    before = _parked_state(_sec("a"), _sec("b"))
    after = _parked_state(_sec("b"), _sec("n"))
    current = _parked_state(_sec("b"), _sec("n"), _sec("m"))
    plan = analyze.plan_undo(before, after, current)
    assert plan.blocked is not None and "cannot account for" in plan.blocked


def test_two_sections_edited_since_park_the_removed_one():
    """The second of the two rearrangement refusals, not only the first."""
    before = _parked_state(_sec("a"), _sec("b"), _sec("c"))
    after = _parked_state(_sec("b"), _sec("c"))
    current = _parked_state(_sec("b", "b2"), _sec("c", "c2"))
    plan = analyze.plan_undo(before, after, current)
    assert plan.blocked is None
    assert plan.parked == (analyze._describe(_md("a")),)


def test_a_view_whose_cards_is_no_list_refuses_the_parked_undo():
    before = _parked_state(_sec("a"), _sec("b"))
    after = _parked_state(_sec("b"))
    current = _parked_state(_sec("b"), _sec("n"))
    current["views"][0]["cards"] = {"not": "a list"}
    plan = analyze.plan_undo(before, after, current)
    assert plan.blocked is None
    with pytest.raises(LookupError, match="something other"):
        restore.apply_undo(current, plan)


def test_a_parked_section_goes_after_cards_already_in_the_view():
    before = _parked_state(_sec("a"), _sec("b"))
    after = _parked_state(_sec("b"))
    current = _parked_state(_sec("b"), _sec("n"), cards=[_md("z")])
    plan = analyze.plan_undo(before, after, current)
    assert restore.apply_undo(current, plan)["views"][0]["cards"] == [_md("z"), _md("a")]


def test_a_loose_card_added_in_the_same_change_is_refused_even_when_the_section_is_back():
    """Opus review W4: the same hole for a card that sits in `cards:`."""
    before = _parked_state(_sec("a"), _sec("b"))
    after = _parked_state(_sec("b"), cards=[_md("z")])
    current = _parked_state(_sec("b"), _sec("n"), cards=[_md("z"), _md("a")])
    plan = analyze.plan_undo(before, after, current)
    assert plan.blocked is not None
    assert plan.steps == ()


def test_a_pathless_view_parks_a_removed_section_on_undo():
    """Undo parks in a pathless view the way it does everywhere; only put
    back does not (status.md, vorhaben L). Two views, so the title keeps
    the position vouched for."""
    first = {"path": "a", "cards": [A]}
    before = {"views": [first, _sectioned(_sec("a"), _sec("b"), path=None, title="Home")]}
    after = {"views": [first, _sectioned(_sec("b"), path=None, title="Home")]}
    current = {"views": [first, _sectioned(_sec("b"), _sec("n"), path=None, title="Home")]}
    plan = analyze.plan_undo(before, after, current)
    assert plan.blocked is None
    assert [(s.view_path, s.view_index, s.location) for s in plan.steps] == [(None, 1, ("cards",))]


def test_a_removed_section_of_a_view_no_longer_in_sections_layout_refuses():
    before = _parked_state(_sec("a"), _sec("b"))
    after = _parked_state(_sec("b"))
    current = {"views": [{"path": "home", "type": "masonry", "cards": [_md("b")]}]}
    plan = analyze.plan_undo(before, after, current)
    assert plan.blocked is not None


def test_cards_of_a_removed_section_that_all_stand_again_are_skipped():
    before = _parked_state(_sec("a"), _sec("b"))
    after = _parked_state(_sec("b"))
    current = _parked_state(_sec("b"), _sec("n"), cards=[_md("a")])
    plan = analyze.plan_undo(before, after, current)
    assert plan.blocked is None
    assert plan.steps == ()


def test_only_the_missing_cards_of_a_removed_section_are_parked():
    before = _parked_state(_sec("a1", "a2"), _sec("b"))
    after = _parked_state(_sec("b"))
    current = _parked_state(_sec("b"), _sec("n"), cards=[_md("a1")])
    plan = analyze.plan_undo(before, after, current)
    assert [s.payload for s in plan.steps] == [_md("a2")]


def test_two_alike_cards_with_one_back_park_exactly_one():
    before = _parked_state(_sec("a", "a"), _sec("b"))
    after = _parked_state(_sec("b"))
    current = _parked_state(_sec("b"), _sec("n"), cards=[_md("a")])
    plan = analyze.plan_undo(before, after, current)
    assert [s.payload for s in plan.steps] == [_md("a")]


def test_an_alike_card_in_another_view_does_not_count_as_back():
    other = {"path": "other", "cards": [_md("a")]}
    before = {"views": [other, _sectioned(_sec("a"), _sec("b"))]}
    after = {"views": [other, _sectioned(_sec("b"))]}
    current = {"views": [other, _sectioned(_sec("b"), _sec("n"))]}
    plan = analyze.plan_undo(before, after, current)
    assert plan.blocked is None
    assert [s.payload for s in plan.steps] == [_md("a")]


def test_an_alike_card_gone_from_another_section_since_does_not_park_extra():
    """`back` can be negative: `x` stood in a surviving section and is gone
    since. The budget then exceeds what the section held, but only cards
    the section really held are planned - one step, never two."""
    before = _parked_state(_sec("a"), _sec("b", "a"))
    after = _parked_state(_sec("b", "a"))
    current = _parked_state(_sec("b"), _sec("n"))
    plan = analyze.plan_undo(before, after, current)
    assert plan.blocked is None
    assert [s.payload for s in plan.steps] == [_md("a")]


def test_a_second_undo_parks_nothing_again():
    before = _parked_state(_sec("a"), _sec("b"))
    after = _parked_state(_sec("b"))
    current = _parked_state(_sec("b"), _sec("n"))
    first = analyze.plan_undo(before, after, current)
    undone = restore.apply_undo(current, first)
    second = analyze.plan_undo(before, after, undone)
    assert second.blocked is None
    assert second.steps == ()
    assert restore.apply_undo(undone, second) == undone


def test_a_view_with_cards_null_gets_a_cards_list_for_the_parked_ones():
    before = _parked_state(_sec("a"), _sec("b"))
    after = _parked_state(_sec("b"))
    current = _parked_state(_sec("b"), _sec("n"), cards=None)
    current["views"][0]["cards"] = None
    plan = analyze.plan_undo(before, after, current)
    assert restore.apply_undo(current, plan)["views"][0]["cards"] == [_md("a")]


def test_the_swallowed_cards_of_a_removed_section_stay_one_section_item():
    """Only the undo plan works per card; the history keeps one line."""
    before = _parked_state(_sec("a1", "a2"), _sec("b"))
    after = _parked_state(_sec("b"))
    assert [item.kind for item in analyze.find_removed(before, after)] == ["section"]
    assert analyze.match_cards(before, after).loose_removed() == []
```

- [ ] **Schritt 2: Tests laufen lassen, Fehlschlag prüfen**

Run: `python3 -m pytest tests/test_analyze.py -q 2>&1 | tail -30` (die ganze Datei – ein `-k`-Filter würde Verweigerungstests still auslassen).
Erwartet FAIL (Parkfälle, `plan.blocked` ist ein Text mit »rearranged since«): `test_a_removed_section_is_parked_when_another_came_since`, `..._when_two_others_swapped_since`, `test_the_cards_of_a_removed_section_are_parked_in_their_old_order`, `test_only_the_missing_cards_...`, `test_two_alike_cards_...`, `test_an_alike_card_in_another_view_...`, `test_a_second_undo_parks_nothing_again`, `test_a_view_with_cards_null_...`, `test_two_sections_edited_since_park_the_removed_one`, `test_a_view_whose_cards_is_no_list_...`, `test_a_parked_section_goes_after_cards_...`, `test_cards_of_a_removed_section_that_all_stand_again_are_skipped`. Alle übrigen neuen Tests (Verweigerungen, `test_a_removed_section_alone_is_still_put_back_exactly`, `test_the_swallowed_...`) sind schon **grün**: sie sichern ab, dass der Umbau nichts aufweicht. Ist einer davon rot, stimmen die Beispieldaten nicht mit dem Matching überein – nicht den Test passend biegen, sondern mit `analyze.match_cards(before, after).sections` (`removed`, `pairs`, `rest_old`) nachsehen, was das Matching erkennt.

- [ ] **Schritt 3: Umsetzung**

In `custom_components/dashboard_history/analyze/undo.py`:

(a) Die beiden Umordnungs-Verweigerungen aus `_plan_sections` (heute Zeilen 161–177) in eine Hilfsfunktion **direkt vor** `_plan_sections` ziehen, Kommentar mitnehmen, Texte Wort für Wort unverändert:

```python
def _rearranged(key: Any, name: str, after_view: dict, current_view: dict) -> str | None:
    """Why the sections cannot be proven to stand where the change left them.

    Since the change: nothing arrived, went or moved among the sections,
    so each stands at the index it had after the change. One of them may
    have been edited since - its identity is then forced, every other
    one standing byte for byte in its place. Two edited since could as
    well have swapped places too, and index is no proof of which is
    which.
    """
    since, gone, came = _pair_view_sections(key, 0, after_view, 0, current_view)
    if gone or came or _moved(since):
        return (
            f'the other sections of the view "{name}" were rearranged since, '
            f"so there is no telling where these go back"
        )
    if sum(1 for pair in since if pair.how in ("settings", "cards")) > 1:
        return (
            f'more than one section of the view "{name}" was changed since, '
            f"so which is which can no longer be proven"
        )
    return None
```

(b) Direkt danach den Parkweg (Docstring erklärt das Warum, Entscheidung 26 / GitHub #39):

```python
def _park_removed_section(
    ctx: UndoContext,
    key: Any,
    current_view: dict,
    current_index: int,
    removed: SectionSlot,
) -> tuple[UndoStep, ...]:
    """The cards of a removed section, parked in the view's "Imported cards".

    GitHub #39, decision 26 for a whole section: where the section stood
    can no longer be proven, so its cards go to the end of `cards:` -
    one step each, the form `apply_undo` already writes for a parked
    card. Idempotent like the card path: per card, as many copies as
    the change took from the view and are not back since. Nothing is
    ever refused here - only added, so a copy too many is the lesser
    harm, and which of several alike is missing does not matter.

    Reads `ctx.card_now`/`ctx.card_then` here, earlier than the cards
    planner would - both are cached, and only on this path, so no
    entry in `_COMPUTED_BEFORE["sections"]` is needed.
    """
    cards = removed.section["cards"]
    marks = [fingerprint(card) for card in cards]
    missing = {
        mark: max(0, marks.count(mark) - _card_came_back(ctx, mark, key))
        for mark in set(marks)
    }
    steps: list[UndoStep] = []
    for position, (card, mark) in enumerate(zip(cards, marks)):
        if missing[mark] == 0:
            continue
        missing[mark] -= 1
        steps.append(
            UndoStep(
                action="insert",
                kind="card",
                view_path=current_view.get("path"),
                view_index=current_index,
                location=("cards",),
                index=position,
                expect=None,
                payload=copy.deepcopy(card),
                label=_describe(card),
                parked=True,
            )
        )
    return tuple(steps)


def _card_events_in(ctx: UndoContext, key: Any) -> bool:
    """Whether the change touched a single card of this view.

    Edited, moved, added or removed - the card matching's own answer,
    wherever the card sat (a section or `cards:`). The removed section's
    own cards are not among them: `loose_removed` leaves them out.
    """
    matching = ctx.matching
    moves = (*matching.edited, *matching.moved)
    return any(key in (old.view_key, new.view_key) for old, new in moves) or any(
        slot.view_key == key for slot in (*matching.loose_added(), *matching.loose_removed())
    )


def _park_instead(
    refusal: str,
    ctx: UndoContext | None,
    key: Any,
    current_view: dict,
    current_index: int,
    removed: list,
    mixed: bool,
) -> tuple[UndoStep, ...] | str:
    """Park the one removed section's cards where the exact undo refuses.

    Only for a view whose change was that one removal and nothing else:
    `mixed` says a section moved, was reset or arrived, and a single card
    of the view changed as well. That last one is asked here, not left
    to `_sections_meet_cards`: with every removed card back, no section
    step is planned, the gate has no view to protect and would let a
    partial undo of the card change through. Only from the undo: without
    `ctx` there is nothing to count against and the refusal stands.
    """
    if ctx is None or mixed or len(removed) != 1 or _card_events_in(ctx, key):
        return refusal
    return _park_removed_section(ctx, key, current_view, current_index, removed[0])
```

`SectionSlot` muss in den `from .model import (...)`-Block von `undo.py` (alphabetisch zwischen `SectionMatching` und `Slot` einsortieren).

(c) `_plan_sections`: Signatur um `ctx: UndoContext | None = None` erweitern; den ausgezogenen Block (Kommentar `# Since the change: …` bis zum Ende der zweiten Verweigerung) ersetzen durch:

```python
    refusal = _rearranged(key, name, after_view, current_view)
    if refusal is not None:
        return _park_instead(
            refusal, ctx, key, current_view, current_index, removed, bool(moved or reset or added)
        )
```

Den Rest der Funktion (ab `then_sections = …`) **nicht** anfassen. Rückgabetyp der Signatur auf `UndoStep | tuple[UndoStep, ...] | str | None` erweitern und im Docstring einen Satz ergänzen: »In a view whose change was one removed section and nothing else, a rearrangement since parks the section's cards instead of refusing (GitHub #39).«

(d) `_plan_section_steps` (Zeile ~361): `ctx` durchreichen und Tupel auflösen:

```python
        planned = _plan_sections(
            key,
            ctx.old_views[key],
            ctx.new_views[key],
            ctx.now_views.get(key),
            ctx.now_index.get(key, -1),
            ctx.matching.sections,
            ctx,
        )
        if isinstance(planned, str):
            return planned
        if isinstance(planned, tuple):
            steps.extend(planned)
        elif planned is not None:
            steps.append(planned)
```

- [ ] **Schritt 3a: Regression der Darstellung einer entfernten Section**

Die Spec verlangt, dass `summarize`, `_explain` und `change_message` eine entfernte Section weiter als *eine* Section melden. Dafür gibt es schon Tests, die dieser Umbau nicht anfasst; sie müssen im Lauf grün bleiben und werden hier ausdrücklich mit ausgeführt:

Run: `python3 -m pytest tests/test_analyze.py -q -k "deleted_section or a_removed or section_is_one_line or offered_as_one_item" 2>&1 | tail -5`
Erwartet: grün. Findet der Filter weniger als die Tests `test_a_deleted_section_is_offered_as_one_item` und `test_a_deleted_section_is_one_line_named_by_its_heading`, mit `grep -n "def test.*section" tests/test_analyze.py` die richtigen Namen nachschlagen. Kein neuer Test nötig, solange `undo.py` und `restore.py` die einzigen geänderten Module bleiben.

- [ ] **Schritt 4: Tests laufen lassen, Erfolg prüfen**

Run: `python3 -m pytest tests/test_analyze.py -v -q 2>&1 | tail -15`
Erwartet: alle grün, die vorhandenen Section-Tests (`_section_plan` ruft `_plan_sections` **ohne** `ctx`) unverändert. `0 failed` zählt, nicht die Gesamtzahl (schwankt mit der echten Bank).

- [ ] **Schritt 5: Sperrklinke, Baseline senken**

Run: `python3 tools/complexity_ratchet.py`
Erwartet: Meldung, dass `undo.py::_plan_sections` **gesunken** ist (Baseline zu hoch). `_rearranged`, `_park_removed_section`, `_park_instead` liegen unter dem Limit 10 und brauchen keinen Eintrag. Meldet die Sperrklinke eine der neuen Funktionen als zu komplex, sie weiter zerlegen statt einzutragen.
Dann `tools/complexity-baseline.json` anpassen: den in der Meldung genannten neuen Wert für `_plan_sections` eintragen (steht er unter dem Limit, den ganzen Eintrag entfernen) und `python3 tools/complexity_ratchet.py` erneut laufen lassen → grün. Wert nach der Messung setzen, nicht vorhersagen.

- [ ] **Schritt 6: Kern-Regeln und Gesamtlauf**

Run: `lint-imports && python3 -m pytest tests/ -q 2>&1 | tail -5`
Erwartet: Verträge erfüllt, `0 failed`.

- [ ] **Schritt 7: Commit**

```bash
git add custom_components/dashboard_history/analyze/undo.py tools/complexity-baseline.json tests/test_analyze.py
git commit -m "Park a removed section's cards on undo (#39)" -m "A section removed and a neighbour changed afterwards was refused,
although every card of it is known. Cards that cannot be proven a
place already park in Imported cards (decision 26); a whole section
now does the same, one step per card, skipping those already back.

Only the two rearrangement refusals are replaced. Everything else
still refuses, and the complexity baseline is lowered in this commit." -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Aufgabe 2: »Put back« – `parks()`/`park()` für `kind="section"`

**Dateien:**
- Ändern: `custom_components/dashboard_history/restore.py` (`parks` Zeile ~296, `park` Zeile ~347)
- Test: `tests/test_restore.py` (Helfer `_sections` existiert dort schon – vorher prüfen, mit `grep -n "def _sections" tests/test_restore.py`; fehlt er, den in `test_a_section_item_never_parks` benutzten Aufbau kopieren)
- `operations.py` bleibt **unverändert**: `_reinsertion` ruft schon `parks(current, item)` / `park(current, item)` und meldet `[item.label]`; `async_restore_deleted` vergleicht `expected_parked` bereits.

**Interfaces:**
- Verbraucht: `_find_view`, `_paths_share`, `_section_gap_holds`, `_park_for`.
- Erzeugt: `parks(config, item) -> bool` (jetzt auch `True` für eine Section) und `park(config, item) -> dict` (hängt bei einer Section alle Karten aus `item.payload["cards"]` als Block an).

- [ ] **Schritt 1: Failing Tests schreiben**

In `tests/test_restore.py` den Test `test_a_section_item_never_parks` **umbenennen** in `test_a_section_that_fits_its_gap_does_not_park` (Inhalt unverändert; er bleibt grün, weil die Lücke hält) und anhängen:

```python
# -- a removed section parks when its gap cannot be proven (GitHub #39) ---


def _removed_section(old, new):
    return next(i for i in analyze.find_removed(old, new) if i.kind == "section")


def test_a_section_whose_neighbours_changed_parks():
    old = _sections({"cards": [A, B]}, {"cards": [C]})
    new = _sections({"cards": [C]})
    item = _removed_section(old, new)
    today = _sections({"cards": [C]}, {"cards": [A]})
    assert restore.parks(today, item) is True


def test_a_section_parks_into_the_view_cards_as_one_block_in_order():
    old = _sections({"cards": [A, B]}, {"cards": [C]})
    new = _sections({"cards": [C]})
    item = _removed_section(old, new)
    today = _sections({"cards": [C]}, {"cards": [A]})
    result = restore.park(today, item)
    assert result["views"][0]["cards"] == [A, B]
    assert result["views"][0]["sections"] == today["views"][0]["sections"]


def test_a_section_lost_beside_a_swap_is_offered_as_a_section_and_parks():
    """Opus review W2: how the item is really reached.

    The item comes from `find_removed(recorded, today)`, and a section is
    only proven whole there when today's view is exactly one shorter -
    a swap of the survivors is what makes the gap unprovable.
    """
    old = _sections({"cards": [A]}, {"cards": [B]}, {"cards": [C]})
    today = _sections({"cards": [C]}, {"cards": [B]})
    item = next(i for i in analyze.find_removed(old, today) if i.kind == "section")
    assert restore.parks(today, item) is True
    parked = restore.park(today, item)
    assert parked["views"][0]["cards"] == [A]
    assert [i for i in analyze.find_removed(old, parked) if i.kind == "section"] == []


def test_parking_a_section_leaves_the_input_alone():
    old = _sections({"cards": [A, B]}, {"cards": [C]})
    item = _removed_section(old, _sections({"cards": [C]}))
    today = _sections({"cards": [C]}, {"cards": [A]})
    snapshot = copy.deepcopy(today)
    restore.park(today, item)
    assert today == snapshot


def test_parking_a_section_creates_cards_when_null():
    old = _sections({"cards": [A, B]}, {"cards": [C]})
    item = _removed_section(old, _sections({"cards": [C]}))
    today = _sections({"cards": [C]}, {"cards": [A]})
    today["views"][0]["cards"] = None
    assert restore.park(today, item)["views"][0]["cards"] == [A, B]


def test_parking_a_section_appends_after_cards_already_there():
    old = _sections({"cards": [A, B]}, {"cards": [C]})
    item = _removed_section(old, _sections({"cards": [C]}))
    today = _sections({"cards": [C]}, {"cards": []})
    today["views"][0]["cards"] = [C]
    assert restore.park(today, item)["views"][0]["cards"] == [C, A, B]


def test_parking_a_section_into_a_cards_that_is_no_list_refuses():
    old = _sections({"cards": [A, B]}, {"cards": [C]})
    item = _removed_section(old, _sections({"cards": [C]}))
    today = _sections({"cards": [C]}, {"cards": [A]})
    today["views"][0]["cards"] = {"not": "a list"}
    with pytest.raises(LookupError, match="something other"):
        restore.park(today, item)


def test_a_section_never_parks_outside_a_sections_view():
    old = _sections({"cards": [A, B]}, {"cards": [C]})
    item = _removed_section(old, _sections({"cards": [C]}))
    assert restore.parks(_config([C]), item) is False


def test_a_section_of_a_pathless_view_does_not_park():
    old = _sections({"cards": [A, B]}, {"cards": [C]})
    item = _removed_section(old, _sections({"cards": [C]}))
    pathless = dataclasses.replace(item, view_path=None)
    today = _sections({"cards": [C]}, {"cards": [A]})
    assert restore.parks(today, pathless) is False


def test_a_section_does_not_park_when_two_views_share_a_path():
    old = _sections({"cards": [A, B]}, {"cards": [C]})
    item = _removed_section(old, _sections({"cards": [C]}))
    today = _sections({"cards": [C]}, {"cards": [A]})
    today["views"].append(copy.deepcopy(today["views"][0]))
    assert restore.parks(today, item) is False


def test_a_section_whose_cards_stand_again_is_not_offered_back():
    """The assumption behind `restore` not counting cards (spec #39, section 4).

    If this fails, the spec is amended - `restore.py` still does not
    import `analyze`.
    """
    old = _sections({"cards": [A, B]}, {"cards": [C]})
    new = _sections({"cards": [C]})
    new["views"][0]["cards"] = [A, B]
    assert [i for i in analyze.find_removed(old, new) if i.kind == "section"] == []
```

Falls `copy`/`dataclasses` in der Datei noch nicht importiert sind, oben ergänzen (`import copy`, `import dataclasses`). Prüfen, dass `RemovedItem` ein (frozen) Dataclass ist (`dataclasses.replace` braucht das); sonst `RemovedItem(...)` von Hand neu bauen.

- [ ] **Schritt 2: Tests laufen lassen**

Run: `python3 -m pytest tests/test_restore.py -v -q 2>&1 | tail -20`
Erwartet: die Tests `..._neighbours_changed_parks`, `..._one_block_in_order`, `..._creates_cards_when_null`, `..._appends_after_cards_already_there` und `test_a_section_lost_beside_a_swap_...` FAIL (`parks` liefert `False`, `park` hängt die Section selbst an); `test_parking_a_section_leaves_the_input_alone` und `..._no_list_refuses` sind schon grün; die Negativ-Tests und `..._is_not_offered_back` sind grün. **Ist `test_a_section_whose_cards_stand_again_is_not_offered_back` rot, anhalten** und den Nutzer informieren: die Annahme in Abschnitt 4 der Spec ist falsch und die Spec muss geändert werden, bevor weiter gebaut wird.

- [ ] **Schritt 3: Umsetzung**

In `restore.py`, vor `parks` eine kleine Hilfsfunktion, `parks` und `park` erweitern:

```python
def _section_parks(config: dict, item: RemovedItem) -> bool:
    """Whether a removed section goes to "Imported cards" (GitHub #39).

    The same footing as a card: a sections view named by a path, and the
    gap the section left no longer the only one it fits. Anything else is
    `reinsert`'s to answer, refusals included. Whether the section's cards
    already stand is not asked here: `find_removed` does not offer a
    section then.
    """
    if item.view_path is None or _paths_share(config):
        return False
    view = _find_view(config.get("views") or [], item)
    return view is not None and view.get("type") == "sections" and not _section_gap_holds(view, item)
```

In `parks` als erste Anweisung nach dem Docstring:

```python
    if item.kind == "section":
        return _section_parks(config, item)
```

Docstring von `parks` um »a whole removed section (GitHub #39)« ergänzen. `park` ersetzen durch:

```python
def park(config: dict, item: RemovedItem) -> dict:
    """Return a new configuration with `item` at the end of "Imported cards".

    A removed section brings its cards, as one block and in order
    (GitHub #39); its own settings do not come along, since there is no
    section to hold them.
    """
    result = copy.deepcopy(config)
    cards = _park_for(result.get("views") or [], item)
    if item.kind != "section":
        cards.append(copy.deepcopy(item.payload))
        return result
    # `find_removed` offers only a section whose cards it proved gone, so
    # the list is there and not empty.
    cards.extend(copy.deepcopy(item.payload["cards"]))
    return result
```

- [ ] **Schritt 4: Tests, Sperrklinke, Import-Verträge**

Run: `python3 -m pytest tests/ -q 2>&1 | tail -5 && python3 tools/complexity_ratchet.py && lint-imports`
Erwartet: `0 failed`, Sperrklinke grün (`parks` und `park` bleiben unter dem Limit; steigt trotzdem etwas, die Funktion weiter zerlegen), `lint-imports` grün (`restore.py` importiert `analyze` weiter nicht).

- [ ] **Schritt 5: Commit**

```bash
git add custom_components/dashboard_history/restore.py tests/test_restore.py
git commit -m "Park a removed section on put back (#39)" -m "Put back refused a removed section as soon as its neighbours had
changed. Its cards now go to the end of the view's cards list, as
they do on undo. restore.py counts nothing: find_removed does not
offer a section whose cards already stand, and a test pins that." -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Aufgabe 3: Integrationsprobe, Journal und Abnahme

**Dateien:**
- Ändern: `tests/integration/run_checks.py` (neue `run_section_parking(access)` nach `run_section_moves` Zeile ~2746; Aufruf im Hauptablauf bei Zeile ~4705 nach `run_section_moves`)
- Ändern: `docs/superpowers/status.md` (Tabellenzeile in der Vorhabenliste, Abschnitt »Umgesetzt am …« wie bei L und O)
- Ändern: `docs/superpowers/specs/2026-09-29-abschnitt-parken-design.md` (nur die Kopfzeile »Stand«: Umsetzungsdatum, sonst nichts)

Panel und `operations.py` brauchen **keinen** Code: `tests/test_panel_behaviour.py` (`test_a_parking_undo_carries_an_asterisk_and_says_why`, Zeile ~8112) deckt Sternchen und Hinweistext für einen `parked`-Plan schon ab, und das Panel liest keine Bedeutung aus dem Etikett.

- [ ] **Schritt 1: Prüfbank prüfen**

**Der Live-Lauf ist ein Maintainer-Check, kein Teil der reproduzierbaren Abnahme:** Er braucht die Docker-Instanz samt Token außerhalb des Repos. Wer sie nicht hat, überspringt die Schritte 1 bis 3, schreibt die Probe (Schritt 2) trotzdem und nennt im Bericht ausdrücklich, dass der Lauf nicht stattfand. Pflicht sind pytest, Sperrklinke und `lint-imports` (Schritt 5).

Aus `CLAUDE.md`: `run_checks.py` erodiert seine Bank und braucht ein Ziel-Dashboard mit zwei Karten. Vorher die Wegwerf-Instanz starten (`docker compose -f docker/compose.yaml up -d`), `python3 tests/integration/run_checks.py` **einmal ohne Änderung** laufen lassen und festhalten, welche Abschnitte schon vorher rot sind, damit sie nicht dieser Änderung zugeschrieben werden. Nie während eines HA-Neustarts pollen; nie nach Präfix löschen.

- [ ] **Schritt 2: Probe schreiben**

Nach dem Muster von `run_section_moves` (eigenes Dashboard `dh-section-parking`, am Ende **namentlich** löschen):

```python
async def run_section_parking(access: str) -> None:
    """A removed section is parked when the row changed since (GitHub #39).

    pytest proves the plan and the write; only a running Home Assistant
    shows that its backend stores and returns the view's `cards:` list
    unchanged, and that the confirming call reads `expected_parked`.
    """
    a = {"type": "markdown", "content": "A"}
    b = {"type": "markdown", "content": "B"}
    c = {"type": "markdown", "content": "C"}

    def sections(*blocks):
        return {
            "views": [
                {
                    "path": "home",
                    "title": "Home",
                    "type": "sections",
                    "sections": [{"type": "grid", "cards": list(block)} for block in blocks],
                }
            ]
        }

    async with Socket(access) as socket:

        async def ready(key: str) -> None:
            listed = (await socket.call("lovelace/dashboards/list")) or []
            if not any(entry.get("url_path") == key for entry in listed):
                await socket.call("lovelace/dashboards/create", url_path=key, title=key)
                await asyncio.sleep(3)

        async def newest(key: str) -> str:
            rows = (
                await socket.call("dashboard_history/history", dashboard=key, limit=1)
            )["changes"]
            return rows[0]["revision"] if rows else ""

        async def save(key: str, config: dict) -> list:
            # `_wait_for_new_state`, not `_wait_until_recorded`: see `save`
            # in `run_section_moves` - three saves in a row land in the
            # recorder's debounce otherwise.
            seen = await newest(key)
            await socket.call("lovelace/config/save", url_path=key, config=config)
            return await _wait_for_new_state(socket, key, seen, RECORDING_WAIT)

        async def undo(key: str, revision: str) -> dict:
            seen = await newest(key)
            asked = await socket.call(
                "dashboard_history/undo_change", dashboard=key, revision=revision
            )
            if asked.get("available") is True:
                await socket.call(
                    "dashboard_history/undo_change",
                    dashboard=key,
                    revision=revision,
                    confirm=True,
                    expected_parked=asked.get("parked", []),
                )
                # The undo is a save of its own; wait for its row.
                await _wait_for_new_state(socket, key, seen, RECORDING_WAIT)
            return asked

        async def drop(key: str) -> None:
            # Named, never by prefix: this instance holds other dh-* boards.
            listed = (await socket.call("lovelace/dashboards/list")) or []
            mine = next((e for e in listed if e.get("url_path") == key), None)
            if mine is not None:
                await socket.call("lovelace/dashboards/delete", dashboard_id=mine["id"])

        # -- undo -----------------------------------------------------------
        key = "dh-section-parking"
        await ready(key)
        await save(key, sections([a], [b]))
        removed = await save(key, sections([b]))
        revision = removed[0]["revision"]
        await save(key, sections([b], [c]))

        asked = await undo(key, revision)
        live = await socket.call("lovelace/config", url_path=key)
        # The label is read, not guessed: `_describe` drops a markdown
        # heading mark, so the card "A" is "markdown: A".
        check(
            "the undo of a removed section is available, parked",
            asked.get("available") is True and asked.get("parked") == ["markdown: A"],
            asked.get("reason") or f"parked={asked.get('parked')!r}",
        )
        check(
            "the card sits in cards: and the sections are untouched",
            live["views"][0].get("cards") == [a] and len(live["views"][0]["sections"]) == 2,
            f"cards={live['views'][0].get('cards')!r}",
        )

        # The same change once more: the card is there, nothing is added.
        await undo(key, revision)
        live = await socket.call("lovelace/config", url_path=key)
        check(
            "a second undo of the same change adds nothing",
            live["views"][0].get("cards") == [a],
            f"cards={live['views'][0].get('cards')!r}",
        )
        await drop(key)

        # -- put back -------------------------------------------------------
        # A section is only offered as one where today's view is exactly one
        # shorter than the recorded one; with two sections again (a new one
        # instead) `find_removed` offers its cards one by one, and those
        # already park since vorhaben L. A swap of the survivors is what
        # makes the gap unprovable.
        key = "dh-section-parking-putback"
        await ready(key)
        base = (await save(key, sections([a], [b], [c])))[0]["revision"]
        await save(key, sections([b], [c]))
        await save(key, sections([c], [b]))

        gone = await socket.call(
            "dashboard_history/deleted_since", dashboard=key, revision=base
        )
        item = gone["items"][0] if gone.get("items") else {}
        label = item.get("label", "")
        check("a lost section is offered as a section", item.get("kind") == "section", f"{item!r}")
        answer = await socket.call(
            "dashboard_history/restore_deleted", dashboard=key, revision=base, position=0
        )
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
            "and is put back as parked cards",
            bool(label)
            and not answer.get("error")
            and answer.get("parked") == [label]
            and written.get("applied") is True
            and live["views"][0].get("cards") == [a],
            answer.get("error") or written.get("error")
            or f"parked={answer.get('parked')!r}, cards={live['views'][0].get('cards')!r}",
        )
        await drop(key)
```

Die Hilfsfunktionen sind dem Muster von `run_parking` und dem `restore_deleted`-Block bei Zeile ~2270–2320 nachgebaut; die genauen Signaturen dort gegenlesen, bevor die Probe läuft (`Socket`, `_wait_for_new_state`, `RECORDING_WAIT`, `check`). Den Aufruf im Hauptablauf ergänzen:

```python
    print("\n  -- Ganze Section parken statt verweigern --")
    asyncio.run(run_section_parking(access))
```

- [ ] **Schritt 3: Probe laufen lassen**

Run: `python3 tests/integration/run_checks.py`
Erwartet: der neue Abschnitt komplett `ok`. Andere Abschnitte, die schon in Schritt 1 rot waren, bleiben so und werden im Bericht getrennt genannt. Schlägt ein neuer Check fehl, ist das ein Befund über den Code (nicht die Probe anpassen, bis sie passt): Ursache suchen, in der zuständigen Aufgabe beheben.

- [ ] **Schritt 4: Journal**

`docs/superpowers/status.md` lesen; einen Eintrag wie bei L und O ergänzen (Deutsch, Umlaute, Guillemets): Vorhaben-Zeile in der Tabelle (»Ganze entfernte Section parken – Issue #39«, Spec/Plan verlinken, Datum der Umsetzung) und ein kurzer Absatz »Umgesetzt am …«: was geparkt wird (nur die eine entfernte Section, keine gemischten Änderungen), Überspringen statt Verweigern, was verweigert bleibt (»hinzugekommen«, mehrere Sections, Kartenänderungen), dass `apply_undo` unverändert blieb. In der Spec die Kopfzeile »Stand« um »umgesetzt am …« ergänzen und drei Nachträge (Ergebnis der Plan-Reviews vom 2026-09-29, Review-Datei `docs/superpowers/reviews/2026-09-29-abschnitt-parken-plan.md`):

1. **Ausgangslage, Satz »Zwei Wege sind betroffen, und beide verweigern heute«:** Für Put back stimmt das nur teilweise. Kam nach der Entfernung eine Section *hinzu* (der Fall aus dem Ticket), hat die Ansicht wieder gleich viele Sections, `_settle_sections` erkennt keine entfernte Section, und `find_removed` bietet die Karten einzeln an – die parkt Put back schon seit Vorhaben L. Neu ist bei Put back der schmalere Fall »Nettoverlust von einer Section **und** umgeordnete oder bearbeitete Nachbarn« (Beispiel: `[a],[b],[c]` → `[c],[b]`). Den Satz entsprechend berichtigen, und im Journal (`status.md`) ehrlich so nennen.
2. **Randfalltabelle und Testplan:** Die Verweigerung bei einer Kartenänderung in derselben Ansicht kommt jetzt aus `_park_instead` (jedes Kartenereignis der Ansicht laut Kartenabgleich, `_card_events_in`) mit dem Text »rearranged since«, nicht mehr aus `_sections_meet_cards`; das Tor bleibt als zweite Sicherung. Die beiden Zeilen (»… durch `_sections_meet_cards`«) anpassen.
3. **Abschnitt 1, Punkt 4:** einen Satz nachtragen: »Zusätzlich verweigert `_park_instead` selbst, wenn die Änderung in derselben Ansicht irgendeine einzelne Karte berührt hat (bearbeitet, verschoben, hinzugefügt, entfernt – auch in `cards:`); sonst bliebe das Tor `_sections_meet_cards` blind, sobald alle Karten der entfernten Section schon zurück sind und kein Section-Schritt entsteht (Plan-Review 2026-09-29).«

- [ ] **Schritt 5: Abnahme**

Run: `python3 -m pytest tests/ -v 2>&1 | tail -8; python3 tools/complexity_ratchet.py; lint-imports`
Erwartet: `0 failed`, Sperrklinke und Verträge grün. Zusätzlich `git status --short`: nur die vorgesehenen Dateien, `CLAUDE.md` weiterhin uncommittet.

- [ ] **Schritt 6: Commit**

```bash
git add tests/integration/run_checks.py docs/superpowers/status.md docs/superpowers/specs/2026-09-29-abschnitt-parken-design.md docs/superpowers/plans/2026-09-29-abschnitt-parken.md
git commit -m "Check parking a removed section end to end (#39)" -m "The check reaches what pytest structurally cannot: the WebSocket
commands and a real Home Assistant storing the cards list. The
journal records what was done and what still refuses." -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

Das Ticket schließt der Nutzer nach eigener Prüfung; kein `Fix`-Vokabular im Commit, kein Push, kein Tag ohne ausdrückliches Go.

---

## Selbstprüfung gegen die Spec

- **Abschnitt 1 (wann):** Aufgabe 1 – `_park_instead` (genau eine entfernte, `mixed` leer), Parkweg hinter den frühen Prüfungen, Behälter `planned["sections"]` (Rückgabe von `_plan_section_steps`), Tor `_sections_meet_cards` unverändert (Test `test_a_card_change_in_the_same_view_keeps_the_refusal`).
- **Abschnitt 2 (Verweigerungstabelle):** Tests für `added`, zwei entfernte, masonry, Kartenänderung, gemischt.
- **Abschnitt 3 (Schritte, Überspringen, Komplexität):** Aufgabe 1 – Schrittform, Reihenfolge, `max(0, deleted − back)`, Baseline im selben Commit.
- **Abschnitt 4 (Put back):** Aufgabe 2, samt Annahmetest.
- **Abschnitt 5 (Etiketten):** Undo-Etiketten sind Kartenbeschreibungen (Test `plan.parked`); Put-back-Etikett kommt unverändert aus `find_removed` → `operations`.
- **Testplan:** pytest (Aufgaben 1 und 2), Panel (vorhandener Test, kein neuer nötig), Instanz (Aufgabe 3), reale Bank: **bewusst nicht** ergänzt (beide Reviews vom 2026-09-29 haben es als Lücke gemeldet; die Spec verlangt den Fall nur »sofern sich dort eine Ansicht findet«, und das Vorhandensein lässt sich nicht zusichern) – die vorhandenen Tests gegen die reale Bank laufen im Gesamtlauf mit; ein eigener Fall braucht eine Ansicht mit mehreren Sections, die sich nicht zusichern lässt. Ergibt sich beim Umsetzen eine, ergänzen; sonst im Abschlussbericht nennen.
- **Typkonsistenz:** `_plan_sections(..., ctx=None)`, `_rearranged`, `_park_removed_section`, `_park_instead`, `_section_parks` heißen in allen Aufgaben gleich.
