# Sections zurückholen, und doppelte Pfade verweigern

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Ziel:** W1 und W4 aus dem Befund vom 2026-09-04 schließen — eine
gelöschte Section wird als *eine* Sache zurückholbar, und ein doppelt
belegter URL-Pfad führt zu einer Verweigerung statt zu einem Schreibvorgang.

**Aufbau:** Zwei Änderungen in den beiden Modulen, die das Herz sind und
Home-Assistant-frei bleiben. `analyze.find_removed` bekommt eine dritte
Granularität `kind="section"`; `restore.reinsert` bekommt den Zweig, der
sie einsetzt, und beide Schreibwege bekommen die Pfad-Prüfung. Kein neues
Speicherformat, keine Panel-Änderung, kein Eingriff in `operations.py`.

**Technik:** Python 3.12 (Entwicklungsrechner) / 3.14 (Container), pytest.
Keine neuen Abhängigkeiten.

**Grundlage:** `docs/superpowers/reviews/2026-09-04-pfadlose-views-und-sections.md`
(W1 und W4, sowie der Nachtrag vom 2026-09-09) und
`docs/superpowers/specs/2026-08-30-dashboard-history-design.md`
(Entscheidung 4).

## Globale Randbedingungen

- **`analyze.py` und `restore.py` bleiben Home-Assistant-frei.** Kein
  `import homeassistant`. Harte Regel der Spec.
- **`restore.py` importiert `analyze` nur unter `TYPE_CHECKING`.** Zur
  Laufzeit gibt es diesen Import nicht und darf es nicht geben — die
  Begründung steht in `restore.py` Zeile 16–21: Die Integration lädt das
  Modul relativ, die Tests laden es flach, und beides gleichzeitig geht
  nicht. **Folge für diesen Plan:** Nichts in `restore.py` darf
  `analyze.fingerprint`, `analyze._views_by_key` oder sonst eine Funktion
  von dort aufrufen. Vergleiche werden mit `==` auf mitgereichten Daten
  geführt, und die Pfad-Prüfung wird in `restore.py` als eigene kleine
  Funktion geschrieben, nicht importiert.
- **Kein Raten.** Wo die Daten die Frage nicht beantworten, wird
  verweigert (Entscheidung 4). Zu oft zu verweigern ist der richtige
  Fehler.
- **Nur additiv.** `reinsert` fügt ein und überschreibt nie — auch eine
  Section nicht.
- **Englisch** im Code, in Kommentaren, in Meldungstexten und in
  Commit-Botschaften. Deutsch nur in diesem Plan und im Journal.
- **Commit-Format:** Subject im Imperativ, erster Buchstabe groß, max. 50
  Zeichen, Leerzeile, Body max. 72 Zeichen pro Zeile mit dem *Warum*,
  Abschluss `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- **Testlauf:** `python3 -m pytest tests/ -v`. Ausgangsstand: **529
  bestanden**. Kein Task darf diese Zahl senken.

---

## Dateien

| Datei | Verantwortung | Änderung |
| --- | --- | --- |
| `custom_components/dashboard_history/analyze.py` | Vergleich zweier Stände, Erkennung, Undo-Plan | `_paths_collide`, `_DUPLICATE_PATH_REFUSAL`, Guard in `plan_undo`, Section-Erkennung in `find_removed`, Feld `neighbours` auf `RemovedItem` |
| `custom_components/dashboard_history/restore.py` | Einsetzen in einen lebenden Stand | `_paths_share`, Guard in `reinsert`, Zweig für `kind="section"`, `_section_gap_holds` |
| `tests/test_analyze.py` | Erkennung und Plan | neue Fälle zu W4 und zur Section-Erkennung |
| `tests/test_restore.py` | Schreibseite | neue Fälle zum Einsetzen und zu den Verweigerungen |
| `README.md` | Außendarstellung | drei Zeilen der Grenzen-Tabelle, Abschnitt »Sections in detail« |
| `docs/superpowers/reviews/2026-09-04-pfadlose-views-und-sections.md` | Journal | Nachtrag: W1 und W4 geschlossen |

---

## Task 1: Doppelter URL-Pfad blockiert den Undo (W4, Leseseite)

**Dateien:**
- Ändern: `custom_components/dashboard_history/analyze.py` — neue Funktion
  neben `_positions_lie` (etwa Zeile 511–543), neue Konstante neben
  `_POSITION_REFUSAL` (Zeile 585), Guard in `plan_undo` (Zeile 694–698)
- Test: `tests/test_analyze.py`

**Schnittstellen:**
- Liefert: `analyze._paths_collide(config: dict) -> bool` und
  `analyze._DUPLICATE_PATH_REFUSAL: str`. Task 2 schreibt die Prüfung für
  die Schreibseite **selbst neu** und benutzt diese Funktion *nicht*
  (siehe globale Randbedingung zum fehlenden Import).

**Warum das ohne Identitätskette geht:** Ein doppelter Pfad ist kein
Zuordnungsproblem, sondern ablesbar. `dict(_views_by_key(...))` behält bei
zwei Views mit demselben Pfad nur den letzten — der erste ist für die
gesamte Analyse unsichtbar. Das ist prüfbar, bevor irgendetwas zugeordnet
wird.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

Anhängen an `tests/test_analyze.py`:

```python
def test_undo_refuses_when_two_views_share_one_path():
    """Home Assistant's backend permits it; then a path names two views.

    Measured before this guard: the first of the two was invisible to the
    analysis, deleting it read as cards removed, and the undo wrote those
    cards into the survivor.
    """
    old = {
        "views": [
            {"path": "x", "title": "One", "cards": [{"type": "tile", "entity": "light.a"}]},
            {"path": "x", "title": "Two", "cards": [{"type": "tile", "entity": "light.b"}]},
        ]
    }
    new = {"views": [{"path": "x", "title": "Two", "cards": [{"type": "tile", "entity": "light.b"}]}]}
    plan = analyze.plan_undo(old, new, new)
    assert plan.blocked is not None
    assert "share one URL path" in plan.blocked
```

- [ ] **Schritt 2: Den Test laufen lassen und rot sehen**

Ausführen:
`python3 -m pytest tests/test_analyze.py::test_undo_refuses_when_two_views_share_one_path -v`

Erwartet: `FAILED` mit `assert None is not None` — heute liefert
`plan_undo` in diesem Fall `blocked=None`.

- [ ] **Schritt 3: Die Funktion und die Konstante schreiben**

In `analyze.py` direkt **nach** `_positions_lie` einfügen:

```python
def _paths_collide(config: dict) -> bool:
    """Whether two views of one state claim the same URL path.

    A path is the identity everything above rests on, and this is the one
    way it stops being one. Home Assistant's backend does not enforce
    uniqueness - saved through the API, `['x', 'x']` goes in without
    complaint - and `_views_by_key` is then read into a dict, which keeps
    only the last of the two. The first view is invisible to every
    comparison from that point on.

    Readable rather than worked out: no matching, no similarity, no
    guessing. Which is why this can be answered today, while the question
    "is the view under this path still the same view" cannot.
    """
    paths = [
        view.get("path")
        for view in config.get("views") or []
        if isinstance(view, dict) and view.get("path")
    ]
    return len(paths) != len(set(paths))
```

In `analyze.py` neben `_POSITION_REFUSAL` und `_SECTION_REFUSAL` einfügen:

```python
_DUPLICATE_PATH_REFUSAL = (
    "two views of this dashboard share one URL path, so a path no longer "
    "tells them apart and an exact undo cannot say which one it means"
)
```

- [ ] **Schritt 4: Den Guard in `plan_undo` einsetzen**

**Vor** der Zeile `pairs = ((before, after), (before, current), (after, current))`
— also vor beiden bestehenden Guards, nicht nach ihnen:

```python
    # Before any pair is compared: a path that names two views is not an
    # identity, and everything below reads views by their path.
    if any(_paths_collide(state) for state in (before, after, current)):
        return UndoPlan(blocked=_DUPLICATE_PATH_REFUSAL)
```

**Die Reihenfolge ist nicht beliebig.** `_sections_lie` liest die Stände
über `dict(_views_by_key(...))`, und dieses `dict` ist genau die Stelle,
an der von zwei Views mit demselben Pfad einer verschwindet. Stünde der
Pfad-Guard dahinter, könnte `_sections_lie` zuerst anschlagen und
`_SECTION_REFUSAL` melden — eine Aussage über Sections für ein Problem,
das keine sind. Der Nutzer bekäme den falschen Grund genannt.

Alle drei Stände, nicht nur `current`: Kollidiert `before`, war schon die
Erkennung blind; kollidiert `current`, landet der Schreibvorgang blind.

- [ ] **Schritt 5: Den Test laufen lassen und grün sehen**

Ausführen: `python3 -m pytest tests/test_analyze.py -v`
Erwartet: der neue Fall `PASSED`, alle übrigen weiter `PASSED`.

- [ ] **Schritt 6: Die ganze Suite laufen lassen**

Ausführen: `python3 -m pytest tests/ -q`
Erwartet: **530 passed** (529 + 1).

- [ ] **Schritt 7: Committen**

```bash
git add custom_components/dashboard_history/analyze.py tests/test_analyze.py
git commit -m "$(cat <<'EOF'
Refuse an undo where one path names two views

Home Assistant does not enforce that view paths are unique, and
`_views_by_key` is read into a dict - so of two views sharing a
path only the last survives the comparison. Deleting the first
then read as cards removed, and the undo wrote those cards into
the survivor.

A duplicate path is readable rather than worked out, so this
needs none of the identity chain the neighbouring cases wait
for. W4 of the 2026-09-04 review.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Doppelter URL-Pfad blockiert das Zurückholen (W4, Schreibseite)

**Dateien:**
- Ändern: `custom_components/dashboard_history/restore.py` — neue Funktion
  vor `_find_view` (Zeile 24), Guard am Anfang von `reinsert` (Zeile 78–89)
- Test: `tests/test_restore.py`

**Schnittstellen:**
- Verbraucht: nichts aus Task 1. Die Prüfung wird hier **neu
  geschrieben**, weil `restore.py` zur Laufzeit nicht aus `analyze`
  importieren darf. Fünf Zeilen doppelt sind der Preis dafür; die
  Alternative wäre ein Import, den die Modulstruktur nicht zulässt.
- Liefert: `restore._paths_share(config: dict) -> bool`

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

Anhängen an `tests/test_restore.py`:

```python
def test_a_card_refuses_to_go_back_when_two_views_share_a_path():
    """With a path naming two views, there is no telling which is meant."""
    old = {
        "views": [
            {"path": "x", "title": "One", "cards": [A, B]},
            {"path": "x", "title": "Two", "cards": [C]},
        ]
    }
    new = {
        "views": [
            {"path": "x", "title": "One", "cards": [A]},
            {"path": "x", "title": "Two", "cards": [C]},
        ]
    }
    item = next(i for i in analyze.find_removed(old, new) if i.payload == B)
    with pytest.raises(LookupError, match="share one URL path"):
        restore.reinsert(new, item)
```

- [ ] **Schritt 2: Den Test laufen lassen und rot sehen**

Ausführen:
`python3 -m pytest tests/test_restore.py::test_a_card_refuses_to_go_back_when_two_views_share_a_path -v`

Erwartet: `Failed: DID NOT RAISE <class 'LookupError'>` — heute setzt
`reinsert` die Karte in den erstgefundenen View mit diesem Pfad ein.

- [ ] **Schritt 3: Die Prüfung schreiben**

In `restore.py` **vor** `_find_view` einfügen:

```python
def _paths_share(config: dict) -> bool:
    """Whether two views of this state claim the same URL path.

    Written here rather than imported: this module has no runtime import
    of `analyze` on purpose (see the note at the top of the file), so the
    five lines live twice. `_find_view` walks the views by path and
    returns the first match, which is exactly the wrong answer when there
    are two.
    """
    paths = [
        view.get("path")
        for view in config.get("views") or []
        if isinstance(view, dict) and view.get("path")
    ]
    return len(paths) != len(set(paths))
```

- [ ] **Schritt 4: Den Guard in `reinsert` einsetzen**

In `reinsert`, **direkt nach** `views = result.setdefault("views", [])` und
**vor** dem `if item.kind == "view":`-Zweig:

```python
    if _paths_share(result):
        raise LookupError(
            "two views of this dashboard share one URL path, so there is "
            "no telling which of them this belongs to"
        )
```

- [ ] **Schritt 5: Den Test laufen lassen und grün sehen**

Ausführen: `python3 -m pytest tests/test_restore.py -v`
Erwartet: der neue Fall `PASSED`, alle übrigen weiter `PASSED`.

- [ ] **Schritt 6: Die ganze Suite laufen lassen**

Ausführen: `python3 -m pytest tests/ -q`
Erwartet: **531 passed**.

- [ ] **Schritt 7: Committen**

```bash
git add custom_components/dashboard_history/restore.py tests/test_restore.py
git commit -m "$(cat <<'EOF'
Refuse to put anything back into a doubled path

`_find_view` walks the views by path and takes the first match,
which is the wrong answer whenever two views carry the same one.
The undo learnt to refuse this in the commit before; the writing
path had the same blind spot and its own guard is what closes it,
because this module cannot import the one over there.

W4 of the 2026-09-04 review.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Eine gelöschte Section wird als eine Sache erkannt (W1, Leseseite)

**Dateien:**
- Ändern: `custom_components/dashboard_history/analyze.py` — Feld und
  Kommentar auf `RemovedItem` (Zeile 25–41), neue Funktionen vor
  `find_removed`, Umbau der Schleife in `find_removed` (Zeile 597–639)
- Ändern: `custom_components/dashboard_history/restore.py` — expliziter
  Dispatch in `reinsert`
- Test: `tests/test_analyze.py`, `tests/test_restore.py`

**Schnittstellen:**
- Liefert: `RemovedItem.kind == "section"` mit `location = ("sections",)`,
  `index` = alter Section-Index, `payload` = die ganze Section als dict,
  `neighbours` = `tuple` der **übrigen** alten Sections in ihrer
  Reihenfolge. Task 4 liest genau diese Felder.
- Bestehende Nutzer bleiben unberührt: `operations.async_deleted_since`
  gibt `item.kind` als Text weiter, und `panel.js` zeigt ihn in
  `<span class="where">` an — ein neues `kind` erscheint dort ohne
  Panel-Änderung.

**Warum die Information schon vorliegt:** `match_cards` weiß, welche
Karten `removed` sind und in welcher `location` sie saßen. Gemessen am
2026-09-09 an einer Section mit zwei Karten: beide landen in
`matching.removed` mit `location = ("sections", 0, "cards")`. Eine
Section ist also genau dann als Ganzes fort, wenn **alle** ihre Karten
dort auftauchen und die Zahl der Sections dieses Views um genau eins
gesunken ist.

**Der Zwischenstand ist nicht von selbst sicher — Schritt 4 macht ihn
sicher.** Nach der Erkennung wird ein Section-Item angeboten, das Task 4
noch nicht einsetzen kann. Nachgemessen am 2026-09-09: `reinsert` fällt
für ein unbekanntes `kind` in den Kartenzweig, und
`_cards_at(view, ("sections",))` liefert dort **nicht** `None`, sondern
`view["sections"]` — das *ist* eine Liste. Die Section würde damit blind
unter die Sections eingefügt, **ohne jede Prüfung von `neighbours`**:
genau der Schreibvorgang, den dieser Plan verhindern soll.

`reinsert` bekommt deshalb schon in diesem Task einen expliziten
Dispatch, der jedes `kind` beantwortet, das es nicht kennt. Das hat einen
zweiten Nutzen: Es macht den ersten Test von Task 4 überhaupt rot.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

Anhängen an `tests/test_analyze.py`:

```python
def _with_sections(*sections):
    """A view in the sections layout, holding the sections given."""
    return {
        "views": [
            {
                "path": "home",
                "title": "H",
                "type": "sections",
                "sections": [dict(section) for section in sections],
            }
        ]
    }


def test_a_deleted_section_is_offered_as_one_item():
    """Not as its cards, each of which refuses on its own.

    Before this, `find_removed` knew only "view" and "card": the cards of
    a deleted section were offered individually and every one of them
    refused, because the section they name is not the one standing at
    that index now. Buttons that reliably fail.
    """
    first = {"title": None, "cards": [{"type": "tile", "entity": "light.a"},
                                      {"type": "tile", "entity": "light.b"}]}
    second = {"title": None, "cards": [{"type": "tile", "entity": "light.z"}]}
    old = _with_sections(first, second)
    new = _with_sections(second)

    items = analyze.find_removed(old, new)

    assert [item.kind for item in items] == ["section"]
    section = items[0]
    assert section.payload == first
    assert section.index == 0
    assert section.location == ("sections",)
    assert section.neighbours == (second,)
```

- [ ] **Schritt 2: Den Test laufen lassen und rot sehen**

Ausführen:
`python3 -m pytest tests/test_analyze.py::test_a_deleted_section_is_offered_as_one_item -v`

Erwartet: `FAILED` mit
`assert ['card', 'card'] == ['section']` — heute werden die beiden Karten
einzeln angeboten.

- [ ] **Schritt 3: Das Feld auf `RemovedItem` ergänzen**

Zuerst den Kommentar an `kind` mitziehen. Aus

```python
    kind: str  # "card" or "view"
```

wird

```python
    kind: str  # "card", "view" or "section"
```

Dann in derselben Klasse **nach** dem Feld `anchor` anfügen:

```python
    # The other sections of that view, in order, as they stood when this
    # section was removed - only on `kind="section"`. It is the proof that
    # the gap this goes back into is the only one it could go into: if
    # today's sections are exactly these, then index `index` is the single
    # place missing. Carried as the sections themselves rather than as
    # fingerprints of them, because `restore` compares it with `==` and
    # cannot import `analyze.fingerprint` at runtime.
    neighbours: tuple | None = None
```

- [ ] **Schritt 4: `reinsert` gegen unbekannte Arten absichern**

Zuerst der Test. Anhängen an `tests/test_restore.py`:

```python
def test_reinsert_refuses_an_item_of_a_kind_it_does_not_know():
    """A kind it has no branch for must not fall into another one.

    Measured on 2026-09-09: `location=("sections",)` walked into the card
    branch, where `_cards_at` returned `view["sections"]` - a list, so no
    refusal at all - and the item was inserted among the sections with
    none of the checks that belong to it. A kind is answered or refused,
    never approximated.
    """
    from analyze import RemovedItem

    config = {"views": [{"path": "home", "sections": [{"cards": [A]}]}]}
    item = RemovedItem(
        kind="something-else",
        view_path="home",
        view_index=0,
        location=("sections",),
        index=0,
        payload={"cards": []},
        label="whatever",
    )
    with pytest.raises(LookupError, match="does not know"):
        restore.reinsert(config, item)
```

Laufen lassen:
`python3 -m pytest tests/test_restore.py::test_reinsert_refuses_an_item_of_a_kind_it_does_not_know -v`

Erwartet: `Failed: DID NOT RAISE`. Zur Kontrolle einmal ohne
`pytest.raises` laufen lassen und `config` ansehen — sie steht dann mit
**zwei** Einträgen unter `sections`, und das ist der Schreibvorgang, den
dieser Schritt verhindert.

Dann in `restore.py` den Kartenzweig abgrenzen. Aus

```python
    view = _find_view(views, item)
    if view is None:
        raise LookupError(
            f"the view this card belonged to no longer exists "
            f"(path={item.view_path!r}, index={item.view_index})"
        )
```

wird

```python
    if item.kind != "card":
        # Answered or refused, never approximated. A `location` meant for
        # another kind walks straight into the card branch otherwise:
        # measured on 2026-09-09, `("sections",)` made `_cards_at` return
        # the list of sections, which is a list and therefore no refusal,
        # and the item went in among them with none of its own checks run.
        raise LookupError(
            f"this is an item of a kind restore does not know: {item.kind!r}"
        )

    view = _find_view(views, item)
    if view is None:
        raise LookupError(
            f"the view this card belonged to no longer exists "
            f"(path={item.view_path!r}, index={item.view_index})"
        )
```

Test erneut laufen lassen. Erwartet: `PASSED`.

- [ ] **Schritt 5: Die Erkennung schreiben**

In `analyze.py` **vor** `find_removed` einfügen:

```python
def _sections_gone(old_view: dict, new_view: dict, gone: list[Slot]) -> dict:
    """Sections of `old_view` that went away whole, by their old index.

    Answers with at most one, and only where the answer is not a guess:
    the view has to have lost exactly one section, and every card of the
    section in question has to be among the ones the matching gave up on.
    A section whose cards turned up elsewhere is not gone - they are in
    `moved`, not in `removed` - and then nothing is reported here, which
    is correct: nothing was lost.

    An **empty** section is never reported. It has no cards to prove
    anything with, so every empty section in a shrunken view would look
    equally deleted; and there is nothing on it to lose.
    """
    old_sections = old_view.get("sections") or []
    new_sections = new_view.get("sections") or []
    if len(new_sections) != len(old_sections) - 1:
        return {}
    found = {}
    for index, section in enumerate(old_sections):
        if not isinstance(section, dict):
            continue
        cards = section.get("cards")
        if not isinstance(cards, list) or not cards:
            continue
        here = ("sections", index, "cards")
        if sum(1 for slot in gone if slot.location == here) == len(cards):
            found[index] = section
    return found if len(found) == 1 else {}


def _section_label(section: dict, index: int) -> str:
    """What to call a section in a list somebody has to choose from.

    Its title where it has one. Where it has none - and on the
    installation this was built against, none of the 80 sections did -
    the position it sat at, one-based, because that is the only thing
    left to say about it.
    """
    title = section.get("title")
    if isinstance(title, str) and title.strip():
        return f"section: {_shorten(title)}"
    return f"section {index + 1}"
```

- [ ] **Schritt 6: `find_removed` umbauen**

In `find_removed` den Kartenzweig ersetzen. Heute steht dort:

```python
        items += [
            RemovedItem(
                kind="card",
                view_path=old_view.get("path"),
                view_index=view_index,
                location=slot.location,
                index=slot.index,
                payload=slot.card,
                label=_describe(slot.card),
                anchor=_section_anchor(old_view, slot.location),
            )
            for slot in gone_by_view.get(view_index, [])
        ]
```

Das wird zu:

```python
        gone = gone_by_view.get(view_index, [])
        # A section that went whole is one item, not one per card on it.
        # Its cards each refuse on their own - the section they name is
        # not the one standing at that index now - so offering them was
        # offering buttons that reliably fail.
        whole = _sections_gone(old_view, new_views[key], gone)
        for index, section in whole.items():
            items.append(
                RemovedItem(
                    kind="section",
                    view_path=old_view.get("path"),
                    view_index=view_index,
                    location=("sections",),
                    index=index,
                    payload=section,
                    label=_section_label(section, index),
                    neighbours=tuple(
                        other
                        for position, other in enumerate(old_view.get("sections") or [])
                        if position != index
                    ),
                )
            )
        swallowed = {("sections", index, "cards") for index in whole}
        items += [
            RemovedItem(
                kind="card",
                view_path=old_view.get("path"),
                view_index=view_index,
                location=slot.location,
                index=slot.index,
                payload=slot.card,
                label=_describe(slot.card),
                anchor=_section_anchor(old_view, slot.location),
            )
            for slot in gone
            if slot.location not in swallowed
        ]
```

- [ ] **Schritt 7: Den einen bestehenden Test umstellen, der davon lebt**

Nachgezählt am 2026-09-09: von allen Tests, die `find_removed` mit
Sections aufrufen, bricht **genau einer** —
`test_a_card_refuses_to_go_back_into_a_different_section` in
`tests/test_restore.py` (heute Zeile 148–155). Er benutzt »die erste von
zwei Sections ist fort« als Kulisse für eine Aussage über den
*Karten*-Anker; nach diesem Task liefert `find_removed` dort ein
Section-Item, und sein `next(...)` findet die Karte nicht mehr
(`StopIteration`).

Die geprüfte Eigenschaft bleibt richtig und soll erhalten bleiben. Nur
die Kulisse wechselt: Das Item entsteht aus einer Kartenlöschung, und
eingesetzt wird es in einen **dritten** Stand, in dem die Section
inzwischen fehlt. Das ist ohnehin der Weg, den `reinsert` in der Praxis
geht.

Ersetze in `tests/test_restore.py`:

```python
def test_a_card_refuses_to_go_back_into_a_different_section():
    """The first of two sections is gone, so index 0 is now "Unten"."""
    old = _sections({"title": "Oben", "cards": [A]}, {"title": "Unten", "cards": [B]})
    new = _sections({"title": "Unten", "cards": [B]})
    item = next(i for i in analyze.find_removed(old, new) if i.payload == A)
    with pytest.raises(LookupError, match="section"):
        restore.reinsert(new, item)
```

durch:

```python
def test_a_card_refuses_to_go_back_into_a_different_section():
    """Its section went away after the card did, so index 1 means another.

    The card is what disappeared between `old` and `new` - one card, no
    section - and the state it would be written into is a third one, in
    which "Oben" has since been removed. That is the shape `reinsert`
    meets in practice: a plan made against one state, applied to a later
    one.
    """
    old = _sections({"title": "Oben", "cards": [A]}, {"title": "Unten", "cards": [B, C]})
    new = _sections({"title": "Oben", "cards": [A]}, {"title": "Unten", "cards": [B]})
    item = next(i for i in analyze.find_removed(old, new) if i.payload == C)
    today = _sections({"title": "Unten", "cards": [B]})
    with pytest.raises(LookupError, match="section"):
        restore.reinsert(today, item)
```

- [ ] **Schritt 8: Den umgestellten Test laufen lassen**

Ausführen:
`python3 -m pytest tests/test_restore.py::test_a_card_refuses_to_go_back_into_a_different_section -v`

Erwartet: `PASSED`. Er muss aus dem *Anker* heraus verweigern
(`len(sections) != count`, also 1 gegen 2), nicht daran, dass die
Kartenliste fehlt — zur Kontrolle die Meldung ansehen: Sie muss die mit
»file it in a stranger« sein.

- [ ] **Schritt 9: Den neuen Test laufen lassen und grün sehen**

Ausführen: `python3 -m pytest tests/test_analyze.py tests/test_restore.py -v`
Erwartet: alle `PASSED`. Bricht ein **weiterer** bestehender Fall, ist er
nicht vorhergesehen — dann anhalten und melden, nicht anpassen.

- [ ] **Schritt 10: Den Fall dazuschreiben, in dem nichts verloren ging**

Anhängen an `tests/test_analyze.py`:

```python
def test_an_empty_section_that_was_deleted_is_not_offered_back():
    """It had nothing on it, and nothing to prove itself with.

    An empty section carries no cards, so nothing in the matching can
    say it was the one that went - every empty section in a shrunken
    view would look equally deleted. And there was nothing on it to
    lose, so refusing to offer it costs nobody anything.
    """
    card = {"type": "tile", "entity": "light.a"}
    old = _with_sections({"title": None, "cards": [card]}, {"title": None, "cards": []})
    new = _with_sections({"title": None, "cards": [card]})

    assert analyze.find_removed(old, new) == []
```

- [ ] **Schritt 11: Diesen Test laufen lassen**

Ausführen: `python3 -m pytest tests/test_analyze.py -v`
Erwartet: `PASSED` ohne weitere Änderung am Code — die Regel »nur wenn
alle Karten fort sind« und »keine leeren Sections« deckt das ab. Falls
nicht: den Grund melden, bevor irgendetwas angepasst wird.

- [ ] **Schritt 12: Die ganze Suite laufen lassen**

Ausführen: `python3 -m pytest tests/ -q`
Erwartet: **534 passed** (531 + zwei neue in `test_analyze.py` und einer
in `test_restore.py`; der umgestellte Fall zählt schon mit).

- [ ] **Schritt 13: Committen**

```bash
git add custom_components/dashboard_history/analyze.py tests/test_analyze.py tests/test_restore.py
git commit -m "$(cat <<'EOF'
Offer a deleted section as one thing

`find_removed` knew "view" and "card" and nothing between them,
so a deleted section arrived as a row of cards that each refused
on their own: the section a card names is not the one standing
at that index any more. The panel was offering buttons that
reliably fail, and the section itself was never offered at all.

The proof was already in hand. The matching says which cards it
gave up on and where they sat, so a section is gone as a whole
exactly when every card of it is among them and the view lost
one section. Anything less certain reports nothing.

W1 of the 2026-09-04 review, first half.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Eine gelöschte Section wird eingesetzt (W1, Schreibseite)

**Dateien:**
- Ändern: `custom_components/dashboard_history/restore.py` — neue Funktion
  nach `_anchor_holds`, neuer Zweig in `reinsert`
- Test: `tests/test_restore.py`

**Schnittstellen:**
- Verbraucht aus Task 3: `RemovedItem` mit `kind="section"`,
  `location = ("sections",)`, `index` (alter Section-Index), `payload`
  (die Section), `neighbours` (`tuple` der übrigen alten Sections).
- Liefert: `restore._section_gap_holds(view: dict, item: RemovedItem) -> bool`

**Der Beweis, und warum er nicht über Titel läuft:** Eingesetzt wird nur,
wenn die heutigen Sections des Views **genau** die in `neighbours` sind, in
derselben Reihenfolge. Dann ist die Lücke an `index` die einzig mögliche.
Über Titel wäre das nicht zu führen: 0 von 80 Sections der Anlage, gegen
die entwickelt wurde, tragen einen. Der Preis ist Strenge — hat sich seit
der Löschung in einer Nachbar-Section etwas geändert, verweigert es. Das
ist dieselbe Grenze, die der Undo längst hat, und der Whole-State-Restore
bleibt unberührt.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

Anhängen an `tests/test_restore.py`:

```python
def test_a_deleted_section_goes_back_into_its_gap():
    """The everyday case: deleted, then wanted back, nothing else touched."""
    first = {"title": None, "cards": [A, B]}
    second = {"title": None, "cards": [C]}
    old = {"views": [{"path": "home", "type": "sections",
                      "sections": [dict(first), dict(second)]}]}
    new = {"views": [{"path": "home", "type": "sections",
                      "sections": [dict(second)]}]}
    item = next(i for i in analyze.find_removed(old, new) if i.kind == "section")

    result = restore.reinsert(new, item)

    assert result["views"][0]["sections"] == [first, second]
```

- [ ] **Schritt 2: Den Test laufen lassen und rot sehen**

Ausführen:
`python3 -m pytest tests/test_restore.py::test_a_deleted_section_goes_back_into_its_gap -v`

Erwartet: `FAILED` mit
`LookupError: this is an item of a kind restore does not know: 'section'`
— der Dispatch aus Task 3 fängt es ab, weil der Zweig für `kind="section"`
noch fehlt. **Nicht** die Meldung über die fehlende Kartenliste: die käme
nie, weil `_cards_at(view, ("sections",))` eine Liste zurückgibt. Ohne den
Dispatch wäre dieser Test hier bereits grün, und der rote Anfang, den TDD
verlangt, fiele aus.

- [ ] **Schritt 3: Den Beweis schreiben**

In `restore.py` **nach** `_anchor_holds` einfügen:

```python
def _section_gap_holds(view: dict, item: RemovedItem) -> bool:
    """Whether the gap this section left is still the only one it fits.

    True exactly when today's sections are the ones that stood beside it,
    in their order. Then the run is one short at `item.index` and there is
    no second place it could belong to.

    Compared with `==` on the sections themselves, which is why the item
    carries them rather than a digest of them: this module has no runtime
    import of `analyze` (see the note at the top) and so no fingerprint
    to compare.

    Not over titles, and that is the point. Of the 80 sections on the
    installation this was developed against, 0 carry one - a check
    against titles would pass on a run of `None`s while telling us
    nothing. Strict instead: a card edited in a neighbouring section
    since the deletion is enough to refuse, and the whole-state restore
    is what covers that.
    """
    if item.neighbours is None:
        return False
    return list(view.get("sections") or []) == list(item.neighbours)
```

- [ ] **Schritt 4: Den Zweig in `reinsert` einsetzen**

In `reinsert`, **nach** dem `if item.kind == "view":`-Zweig und **vor** dem
`if item.kind != "card":`-Guard aus Task 3 — sonst fängt der Guard die
Section ab, bevor ihr eigener Zweig sie sieht:

```python
    if item.kind == "section":
        view = _find_view(views, item)
        if view is None:
            raise LookupError(
                f"the view this section belonged to no longer exists "
                f"(path={item.view_path!r}, index={item.view_index})"
            )
        if not _section_gap_holds(view, item):
            raise LookupError(
                "the other sections of this view are not the ones this "
                "section stood beside, so there is no telling where it "
                "belongs now"
            )
        # Not `setdefault`: a view written as `sections: null` in YAML
        # arrives as {"sections": None}, and `setdefault` hands the None
        # straight back - the key is there. `card_containers` guards the
        # same shape with `or []`, so it does occur.
        sections = view.get("sections")
        if not isinstance(sections, list):
            sections = []
            view["sections"] = sections
        sections.insert(min(item.index, len(sections)), copy.deepcopy(item.payload))
        return result
```

- [ ] **Schritt 5: Den Test laufen lassen und grün sehen**

Ausführen: `python3 -m pytest tests/test_restore.py -v`
Erwartet: der neue Fall `PASSED`.

- [ ] **Schritt 6: Den Verweigerungsfall dazuschreiben**

Anhängen an `tests/test_restore.py`:

```python
def test_a_deleted_section_refuses_when_a_neighbour_changed_since():
    """Then the gap is no longer the only place it could go.

    Strict on purpose: without titles - and 0 of 80 sections on the real
    installation have one - the run of sections carries no identity, so
    "unchanged neighbours" is the whole proof there is.
    """
    first = {"title": None, "cards": [A, B]}
    second = {"title": None, "cards": [C]}
    old = {"views": [{"path": "home", "type": "sections",
                      "sections": [dict(first), dict(second)]}]}
    new = {"views": [{"path": "home", "type": "sections",
                      "sections": [dict(second)]}]}
    item = next(i for i in analyze.find_removed(old, new) if i.kind == "section")
    # A card added to the surviving section after the deletion.
    today = {"views": [{"path": "home", "type": "sections",
                        "sections": [{"title": None, "cards": [C, A]}]}]}

    with pytest.raises(LookupError, match="stood beside"):
        restore.reinsert(today, item)
```

- [ ] **Schritt 7: Den Test laufen lassen und grün sehen**

Ausführen: `python3 -m pytest tests/test_restore.py -v`
Erwartet: `PASSED` ohne weitere Codeänderung.

- [ ] **Schritt 8: Prüfen, dass die Eingabe unberührt bleibt**

Anhängen an `tests/test_restore.py`:

```python
def test_putting_a_section_back_leaves_the_input_alone():
    """The caller still needs the old state to render a preview against."""
    first = {"title": None, "cards": [A]}
    second = {"title": None, "cards": [C]}
    old = {"views": [{"path": "home", "type": "sections",
                      "sections": [dict(first), dict(second)]}]}
    new = {"views": [{"path": "home", "type": "sections",
                      "sections": [dict(second)]}]}
    item = next(i for i in analyze.find_removed(old, new) if i.kind == "section")

    restore.reinsert(new, item)

    assert new["views"][0]["sections"] == [second]
```

- [ ] **Schritt 9: Die Schreibseite des Undo symmetrisch absichern**

`apply_undo` benutzt dasselbe `_find_view`, das bei zwei Views mit einem
Pfad den ersten nimmt. Task 1 hält den Fall in `plan_undo` an, und
`operations` leitet den Plan bei jedem Aufruf neu her — trotzdem gehört
die Prüfung auch hierher: `restore` ist die Schreibseite und muss sich
selbst schützen, genauso wie `reinsert` es seit Task 2 tut. Ein Plan
entsteht gegen einen Stand und wird auf einen späteren angewandt; nur der
spätere entscheidet, wohin geschrieben wird.

Zuerst der Test. Anhängen an `tests/test_restore.py`:

```python
def test_an_undo_refuses_to_write_into_a_doubled_path():
    """The plan was made against a state that had one path per view.

    `plan_undo` stops this case since the guard on the reading side, but
    the plan travels: made against one state, applied to a later one. It
    is the later one that decides where the write lands, so the writing
    side asks again.
    """
    old = {"views": [{"path": "x", "title": "One", "cards": [A]}]}
    new = {"views": [{"path": "x", "title": "One", "cards": [A, B]}]}
    plan = analyze.plan_undo(old, new, new)
    assert plan.blocked is None, "the plan itself has to be sound for this test"
    today = {
        "views": [
            {"path": "x", "title": "One", "cards": [A, B]},
            {"path": "x", "title": "Another that appeared since", "cards": []},
        ]
    }
    with pytest.raises(LookupError, match="share one URL path"):
        restore.apply_undo(today, plan)
```

Laufen lassen:
`python3 -m pytest tests/test_restore.py::test_an_undo_refuses_to_write_into_a_doubled_path -v`

Erwartet: `Failed: DID NOT RAISE`.

Dann in `restore.py` in `apply_undo`, direkt nach dem `plan.blocked`-Guard
und vor der Schleife über die Schritte:

```python
    if _paths_share(result):
        raise LookupError(
            "two views of this dashboard share one URL path, so there is "
            "no telling which of them these steps belong to"
        )
```

Test erneut laufen lassen. Erwartet: `PASSED`.

- [ ] **Schritt 10: Die ganze Suite laufen lassen**

Ausführen: `python3 -m pytest tests/ -q`
Erwartet: **538 passed**.

- [ ] **Schritt 11: Committen**

```bash
git add custom_components/dashboard_history/restore.py tests/test_restore.py
git commit -m "$(cat <<'EOF'
Put a deleted section back into the gap it left

The reading side offers a section as one item since the commit
before; this is the side that writes it. Additive as everything
here: the section fills a gap, it overwrites nothing.

Which gap is proved rather than assumed. The item carries the
sections that stood beside it, and it goes back only where
today's run is exactly those - then one place is missing and it
is the one. Not over titles: 0 of the 80 sections on the real
installation have any, so a title check would pass on a run of
None and mean nothing.

Strict, therefore. A card edited in a neighbouring section since
the deletion refuses, and the whole-state restore covers that.

W1 of the 2026-09-04 review, second half.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Die Außendarstellung nachziehen

**Dateien:**
- Ändern: `README.md` — Grenzen-Tabelle, Abschnitt »Sections in detail«,
  Abschnitt »If your dashboard uses sections« in Teil 1
- Ändern: `docs/superpowers/reviews/2026-09-04-pfadlose-views-und-sections.md`
  — Nachtrag

**Kein Code, keine Tests.** Der Task ist trotzdem eigenständig: er darf
erst laufen, wenn Task 1 bis 4 grün sind, weil er ihr Ergebnis behauptet.

- [ ] **Schritt 1: Zwei Zeilen der Grenzen-Tabelle ändern**

In `README.md`, Tabelle unter »Known limits, measured«:

Aus `| A whole section deleted | its cards, listed as deleted | **refuses** | **refuses** | works |`
wird `| A whole section deleted | the section, as one item | **refuses** | offered, with proof | works |`

Aus `| Two views sharing one path, the first one deleted | read as cards removed, not as a view gone | writes into the surviving view | writes into the surviving view | works |`
wird `| Two views sharing one path | read as cards removed, not as a view gone | **refuses** | **refuses** | works |`

- [ ] **Schritt 2: Den Absatz »Writes something nobody asked for« nachzählen**

Nach Task 1 und 2 schreibt der Fall der doppelten Pfade nicht mehr, also
sind es **drei** statt vier. Ersetze:

```text
- **Two views sharing one path.** Home Assistant's backend allows it,
  its editor does not produce it, and it appears on none of the eleven
  dashboards this was built against. Only the first of the two is
  affected, and only when it is deleted whole: that reads as cards
  removed rather than as a view gone, and both narrow ways back put them
  into the surviving view. Cards edited *inside* either view are handled
  correctly — measured. Noted so that "a path is an identity" is not
  read as a guarantee.
```

durch nichts — der Punkt entfällt. Und in derselben Aufzählung wird die
Einleitung

```text
This is not the only row where the tool writes a state nobody asked for
— the table has four, and it is worth knowing which:
```

zu

```text
This is not the only row where the tool writes a state nobody asked for
— the table has three, and it is worth knowing which:
```

Damit der Fall nicht unerwähnt verschwindet, kommt er als Verweigerung an
das Ende des Abschnitts »Views without a URL path«:

```text
A path can also stop being an identity outright: Home Assistant's backend
does not enforce that two views carry different ones, and saved through
the API `['x', 'x']` goes in without complaint. Read into a lookup, only
the last of the two survives, and the first is invisible to every
comparison. Since 2026-09-09 both write paths refuse as soon as a path
appears twice — the whole-state restore is unaffected, and no dashboard
Home Assistant's own editor produces is in that shape.
```

- [ ] **Schritt 3: Die Zeile in »Refuses, honestly, and writes nothing« ersetzen**

Diese Zeile (heute `README.md:809`) beschreibt den behobenen Zustand und
gehört ganz aus der Tabelle heraus:

```text
| Deleted a whole section | `find_removed` knows `view` and `card`, not `section`. Its cards are offered individually, and each refuses: *"the section this card sat in is not the one standing at that place now, so putting it back would file it in a stranger."* The undo refuses for the same reason. |
```

Sie wird ersetzt durch:

```text
| Deleted a whole section, and a neighbouring section changed since | The proof *Put back* works from is that today's sections are the ones this one stood beside — then the gap is the only place it fits. An edit next door takes that away, and the undo refuses regardless: a section has no path to recognise it by. |
```

Und die gelöschte Section ist jetzt der Regelfall und nicht mehr der
Ausfall, gehört also in die Tabelle **Works, and works exactly**. Deren
Kopf lautet `| What you did | The history says | Put back | Undo |` —
Spalte 3 ist *Put back*, Spalte 4 ist *Undo*, und hier verweigert der
Undo weiterhin. Als weitere Zeile also:

```text
| Deleted a whole section | the section, named as one item | into the gap it left | — |
```

- [ ] **Schritt 4: Den Absatz unter der Verweigerungs-Tabelle berichtigen**

Heute steht dort (`README.md:814-817`):

```text
A refusal is the correct outcome for all four — Home Assistant's own data
does not contain the answer, and the design forbids guessing. What it
costs is that a deleted section has **no narrow way back at all**: not
*Put back*, not *Undo*. The whole-state restore recovers it in full.
```

Daraus wird:

```text
A refusal is the correct outcome for all four — Home Assistant's own data
does not contain the answer, and the design forbids guessing. What it
costs is precision, not content: the whole-state restore recovers every
one of these in full, and since 2026-09-09 a deleted section also comes
back on its own as long as the sections beside it are untouched.
```

- [ ] **Schritt 5: Teil 1 nachziehen**

Heute steht dort (`README.md:277-279`):

```text
- **Deleting a whole section** cannot be taken back with the narrow
  tools: neither *Put back* nor *Undo this change* will do it, and both
  say why. The whole-state restore brings it back in full.
```

Daraus wird:

```text
- **Deleting a whole section** comes back through *Put back*, which
  offers the section as one thing rather than as a heap of cards — as
  long as the other sections of that view are as you left them. Edit one
  of them in between and it says so; *Undo this change* declines either
  way, because a section has no name to recognise it by. The whole-state
  restore brings it back in any case.
```

- [ ] **Schritt 6: Den Nachtrag ins Journal schreiben**

An `docs/superpowers/reviews/2026-09-04-pfadlose-views-und-sections.md`
anhängen: ein Abschnitt »## Nachtrag vom 2026-09-09: W1 und W4
geschlossen«, der festhält, **was** geschlossen wurde, **womit** (die
Beweisform, nicht die Zeilen), **warum es ohne Paket 2 ging** — W4 ist
ablesbar, W1 ist über unveränderte Nachbarn beweisbar — und **was offen
bleibt**: W2, die Historientexte aus C1, die pfadlose Restlücke. Dazu die
Korrektur an der eigenen Einschätzung des Reviews, das W1 unter »setzt
Paket 2 voraus« geführt hat.

- [ ] **Schritt 7: Die Anker prüfen**

Ausführen:

```bash
python3 - <<'PY'
import re, pathlib
def slug(t):
    t = re.sub(r"`|\*|\[|\]|\(|\)", "", t).lower().strip()
    return re.sub(r"\s+", "-", re.sub(r"[^\w\s-]", "", t))
doc = pathlib.Path("README.md").read_text(encoding="utf-8")
heads = {slug(m.group(2)) for m in re.finditer(r"^(#+)\s+(.*)$", doc, re.M)}
bad = [a for a in re.findall(r"\]\(#([^)]+)\)", doc) if a not in heads]
print("interne Anker:", "alle auflösbar" if not bad else f"TOT: {bad}")
PY
```

Erwartet: `alle auflösbar`.

- [ ] **Schritt 8: Committen**

```bash
git add README.md docs/superpowers/reviews/2026-09-04-pfadlose-views-und-sections.md
git commit -m "$(cat <<'EOF'
Say what now comes back and what refuses

Part 2 claims to be measured, so it has to move when the
measurements do. Three rows of the limits table change, the count
of cases that write something unasked drops from four to three,
and the sentence that a deleted section has no narrow way back is
simply no longer true.

The journal gets the reasoning, including where the review's own
plan was wrong: it filed W1 under "needs package 2", and the
proof over unchanged neighbours does without it.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Was dieser Plan nicht anfasst

- **W2** — ein freigegebener und neu belegter URL-Pfad. Zwischen
  »derselbe View, dreißig Änderungen später« und »ein anderer View unter
  demselben Pfad« liegt keine Information, die zwei Stände hergeben. Das
  ist die Frage, die Paket 2 beantwortet, und keine Verweigerung kann sie
  ersetzen, ohne den gewöhnlichen Fall mitzunehmen.
- **Die falschen Historientexte aus C1** — Verweigern hält das Schreiben
  an, es korrigiert nicht, was die Zeile erzählt.
- **Die pfadlose Restlücke** — eine Ansicht ohne Pfad, die verschoben
  *und* bearbeitet wurde, ist sich selbst nicht mehr byte-identisch. Steht
  seit dem 2026-09-09 als gemessene Zeile in der README.
- **Die titellosen Sections in einer umsortierten Ansicht** — der eine
  Fall, in dem eine Karte still in der falschen Section landet. Unberührt;
  der Section-Beweis dieses Plans greift nur beim Zurückholen einer
  *ganzen* Section.
