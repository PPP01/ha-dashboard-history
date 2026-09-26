# Sections als Einheit – Umsetzungsplan (Vorhaben O, Issue #31)

> **Umsetzung durch Gemini.** Dieser Plan wird von Gemini umgesetzt, nicht von Claude. Er ist so geschrieben, dass er zusammen mit der Spec ohne weiteren Kontext ausreicht. Steps use checkbox (`- [ ]`) syntax for tracking.

## Regeln für den Umsetzer

1. **Task für Task, in der Reihenfolge 1–9.** Pro Task genau die genannten Dateien und Stellen. Keine »Verbesserungen nebenbei«, keine Umbenennungen, keine eigenen Architekturentscheidungen.
2. **Abweichung heißt anhalten.** Passt eine Stelle im Code nicht zu dem, was der Plan beschreibt (Zeile fehlt, Funktion heißt anders, ein im Plan als grün vorhergesagter Test ist rot, ein als rot vorhergesagter ist grün), dann nicht umdeuten, sondern stoppen und die Abweichung wörtlich melden: Datei, erwartet, vorgefunden.
3. **Tests sind Teil des Tasks.** Die `-k`-Filter in den Rot-/Grün-Schritten sind nur eine Abkürzung. Maßgeblich ist: **Jeder** in Step 1 neu geschriebene Test ist im Rot-Schritt rot und im Grün-Schritt grün. Erfasst ein Filter einen neuen Test nicht, diesen zusätzlich namentlich aufrufen. Erfasst er alte Tests mit, müssen diese grün sein. Der Rot-Schritt wird wirklich ausgeführt und sein Ergebnis gemeldet, ebenso der Grün-Schritt und `python3 -m pytest tests/ -v` am Ende jedes Tasks. Es zählt nur »0 failed«. Ein einzelner `JSONDecodeError` in `tests/test_yaml_io.py` gegen ein echtes Dashboard ist ein bekannter Lese-Wettlauf mit einer fremden Datei: Den einzelnen Test isoliert wiederholen und melden, nicht »reparieren«.
4. **Nicht committen.** Die Commit-Schritte enthalten die fertigen Nachrichten, ausgeführt werden sie erst nach ausdrücklichem Go des Nutzers. Bis dahin bleiben die Änderungen uncommittet im Arbeitsverzeichnis. Kein Push, kein Tag, keine Veröffentlichung.
5. **Test-Anlage.** `docker compose -f docker/compose.yaml restart`, danach 15 Sekunden warten und **nicht pollen** (HAs IP-Sperre). Erst dann `python3 tests/integration/run_checks.py`. Kein Test darf per Präfix löschen, nur über den eigenen, exakt benannten Schlüssel.
6. **Nach jedem Task melden:** geänderte Dateien, Ergebnis Rot/Grün, Suite-Ergebnis, Akzeptanzkriterium erfüllt ja/nein.
7. **Am Ende:** eine Liste aller Stellen, an denen der Plan korrigiert werden müsste (falsche Zeilen, falsche Erwartungen), damit er im Journal nachgezogen werden kann.

**Goal:** Sections werden vor ihren Karten als ganze Blöcke zugeordnet. Ein Tausch, eine Verschiebung, eine hinzugekommene oder verschwundene Section und eine geänderte Section-Einstellung werden als genau das benannt, gezählt und über einen einzigen Schritt je Ansicht exakt zurückgenommen – oder verweigert, wo das nicht beweisbar ist.

**Architecture:** Neue, HA-freie Zuordnung in `analyze.py`: `_pair_view_sections` (vier Durchgänge wie `match_cards`), `_moved` (längste Teilfolge), `_settle_sections` (Beweis für ganze Sections über das Karten-Matching). `match_cards` übersetzt den Platz alter Karten über die gepaarten Sections und trägt das Ergebnis als `Matching.sections`. Das Undo baut je betroffener Ansicht die ganze `sections`-Liste per Merge über `before`s Reihenfolge und schreibt sie als einen `kind="sections_list"`-Schritt; `restore.apply_undo` prüft `expect` und ersetzt die Liste. Der Put-back-Anker parkt zusätzlich, wo ein weggezogener Nachbar Tausch und Hinüberziehen ununterscheidbar macht.

**Tech Stack:** Python 3 (HA-freie Kernmodule, pytest), Testcontainer für `run_checks.py`.

**Spec:** `docs/superpowers/specs/2026-09-25-sections-als-einheit-design.md` (bindend; vier Review-Runden, Entscheidungen 1–13). Dazu Entscheidung 4, 15 und 26 der Haupt-Spec und die Spec zu Vorhaben L. **Voraussetzung:** Vorhaben L, M, N und die Fixes zu #35/#36 sind umgesetzt (Stand `72d125b`).

## Global Constraints

- `analyze.py`, `restore.py` ohne `import homeassistant`; `restore.py` ohne Laufzeitimport von `analyze`.
- Zuordnung nur über exakte Gleichheit (`fingerprint`, also `1` ≠ `True`); keine Ähnlichkeit, keine Identitätskette (Entscheidung 16 bleibt ungebaut).
- `match_cards(old, new)` und `match_badges(old, new)` behalten ihre Signatur; Badges gehen nie durch die Section-Zuordnung.
- Eine Ansicht mit geändertem `type` (#32) wird von der Section-Zuordnung übersprungen; sie wird weiterhin als Konvertierung erklärt und verweigert.
- Jeder nicht erklärte Section-Rest verweigert das Undo der ganzen Ansicht, ausnahmslos (Spec-Entscheidung 13).
- Ein `sections_list`-Schritt und ein Karten-Schritt in derselben Ansicht verweigern.
- Für Sections wird nicht geparkt.
- Das Panel bleibt unverändert: Erklärungseinträge benutzen nur die vorhandenen `kind`-Werte `removed`, `added`, `edited`, `moved`.
- `python3 -m pytest tests/ -v` nach jedem Task – es zählt nur »0 failed« (die Zahl schwankt mit der echten `.storage`).
- Englisch in Code, Kommentaren, Meldungen und Commits; Deutsch im Journal. Commit-Format wie in `CLAUDE.md` (Subject ≤ 50 Zeichen, Imperativ), Verweis auf `#31`, Abschluss `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. **Committet wird erst nach ausdrücklichem Go des Nutzers.**

## Review Focus

1. **Die einzige Karte einer Section wird in eine leere, gleich eingestellte Section gezogen.** Vorher `[{a}, {}]`, nachher `[{}, {a}]`: Beide Sections sind danach bytegleich zur jeweils anderen, Durchgang 2 liest das als Tausch. Erwartung: Die Erklärung sagt »section 2 was moved« (nicht die Karte), das Undo stellt exakt den Stand davor her. Beide Deutungen ergeben denselben Stand. Tests in Task 4 (Wortlaut) und Task 6 (Undo).
2. **`sections:` fehlt, ist `null` oder enthält einen Nicht-Dict-Eintrag.** Erwartung: keine Ausnahme, fehlende Liste gilt als leer, ein fremder Eintrag wird wie jede andere Section über seinen Fingerabdruck gepaart. Tests in Task 2.
3. **Echte Dashboards gegen sich selbst.** Erwartung: jede Section in Durchgang 1, kein Ereignis, und die echten Namens-Tests bleiben grün, auch wenn eine Section beim Entfernen der ersten Karte leer wird. Tests in Task 3 und Task 4.
4. **Section-Tausch in einer Ansicht ohne URL-Pfad** (einzige Ansicht, Position steht fest). Erwartung: Undo exakt; die Ansicht wird über ihren Index gefunden. Test in Task 7.
5. **Heading-Karte mit leerem oder nicht-textlichem `heading`, oder ein `heading`-Feld auf einer Karte anderen Typs.** Erwartung: Der Name fällt auf `title`, dann auf die Position zurück. Tests in Task 4.
6. **Zwei bytegleiche Sections, die beide verschoben wurden.** Erwartung: Das Undo verweigert als mehrdeutig, statt eine zu wählen. Test in Task 6.

---

## Files touched

| Datei | Rolle |
|---|---|
| `custom_components/dashboard_history/analyze.py` | `SectionSlot`, `SectionPair`, `SectionMatching`, `_own`, `_section_list`, `_pair_view_sections`, `_pair_sections`, `_moved`, `_translated`, `_count_places`, `_whole`, `_settle_sections`, `_match_slots` (bisheriger Rumpf von `match_cards`); `Matching.sections/translate/same_place/loose_removed/loose_added`; `_section_title` statt `_section_label`; Section-Einträge in `_explain`; `Summary.sections_*`; `_sections_part`, `_COUNT`; `_plan_sections`; `plan_undo`; `_section_drift` nur noch »seither verschoben«; `_SectionAnchor.departed`; `_sections_gone` und `_SECTIONS_REBUILT_REFUSAL` entfallen |
| `custom_components/dashboard_history/restore.py` | strenger Einstellungsvergleich im Anker; `_apply_sections_list`; `_departed_is_ambiguous` |
| `tests/test_analyze.py`, `tests/test_restore.py` | neue Tests; drei bestehende Tests bewusst umgeschrieben (Task 7) |
| `tests/integration/run_checks.py` | neuer Abschnitt `run_section_moves` |
| `docs/limitations.md`, `docs/how-it-works.md`, `docs/superpowers/status.md`, Haupt-Spec | Stand nachziehen |

---

### Task 1: Section-Einstellungen streng vergleichen

Reine Schärfung vorhandener Prüfungen (Spec §1, Entscheidung 8). Kein neuer Mechanismus.

**Files:**
- Modify: `custom_components/dashboard_history/analyze.py` (`_section_drift`, neue Hilfsfunktion `_same_marks` direkt davor)
- Modify: `custom_components/dashboard_history/restore.py` (`_anchored_index`)
- Test: `tests/test_analyze.py`, `tests/test_restore.py`

**Interfaces:**
- Produces: `_same_marks(one: dict, other: dict) -> bool` (zwei Ansichten, strenger Vergleich ihrer `_section_marks`).

**Akzeptanz:** Beide neuen Tests sind vor der Änderung rot und danach grün; die Suite meldet 0 failed.

- [ ] **Step 1: Tests schreiben**

In `tests/test_analyze.py` direkt hinter `_sectioned` (der Helfer steht im Block »sections that moved since: park, do not refuse«):

```python
def test_a_section_setting_of_1_against_true_counts_as_moved_since():
    """`==` calls 1 and True equal; the section check must not (#28, #31)."""
    before = {"views": [_sectioned({"column_span": 1, "cards": [A]})]}
    after = {"views": [_sectioned({"column_span": 1, "cards": []})]}
    current = {"views": [_sectioned({"column_span": True, "cards": []})]}
    plan = analyze.plan_undo(before, after, current)
    assert plan.blocked is None
    assert plan.parked == ("tile: light.a",)
```

In `tests/test_restore.py` hinter `test_the_anchor_notices_an_edited_neighbour`:

```python
def test_the_anchor_tells_1_from_true():
    """A section whose setting went from 1 to true is not the same section."""
    old = _sections({"column_span": 1, "cards": [A, B]})
    new = _sections({"column_span": 1, "cards": [A]})
    item = next(i for i in analyze.find_removed(old, new) if i.payload == B)
    today = _sections({"column_span": True, "cards": [A]})
    assert restore.parks(today, item) is True
```

- [ ] **Step 2: Rot prüfen**

Run: `python3 -m pytest tests/test_analyze.py::test_a_section_setting_of_1_against_true_counts_as_moved_since tests/test_restore.py::test_the_anchor_tells_1_from_true -v`
Expected: beide FAIL (`plan.parked == ()` bzw. `parks` ist `False`).

- [ ] **Step 3: Umsetzen**

In `analyze.py` direkt vor `_section_drift`:

```python
def _same_marks(one: dict, other: dict) -> bool:
    """Whether two views' sections agree on every setting, strictly.

    Through `fingerprint`, not `==`: `column_span: 1` and `column_span:
    true` are two states, which `==` calls equal (GitHub #28).
    """
    return fingerprint(_section_marks(one)) == fingerprint(_section_marks(other))
```

Im Rumpf von `_section_drift` die Schleife ersetzen durch:

```python
    for key in set(old_views) & set(new_views):
        if not _same_marks(old_views[key], new_views[key]):
            rebuilt.add(key)
        elif key in now_views and not _same_marks(now_views[key], new_views[key]):
            shifted.add(key)
```

In `restore.py`, `_anchored_index`, die Zeile `if own != settings:` ersetzen durch:

```python
    if not _same_value(own, settings):
```

- [ ] **Step 4: Grün prüfen**

Run: dieselben zwei Tests → PASS. Dann `python3 -m pytest tests/ -v` → 0 failed.

- [ ] **Step 5: Commit (nach Go des Nutzers)**

```bash
git add custom_components/dashboard_history/analyze.py custom_components/dashboard_history/restore.py tests/test_analyze.py tests/test_restore.py
git commit -m "Compare section settings strictly" -m "The section checks compared settings with ==, which calls
column_span: 1 and column_span: true equal - the same blindness #28
closed for named settings. Both the check for sections moved since and
the put-back anchor now compare the way fingerprint does. Groundwork
for GitHub #31.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Sections einer Ansicht paaren

Die Zuordnung als reine Funktionen, noch nirgends verdrahtet (Spec §1).

**Files:**
- Modify: `custom_components/dashboard_history/analyze.py` (neuer Block direkt vor `def _views_by_key`)
- Test: `tests/test_analyze.py`

**Interfaces:**
- Produces:
  - `SectionSlot(view_key: Any, view_index: int, index: int, section: Any)` – frozen dataclass.
  - `SectionPair(old: SectionSlot, new: SectionSlot, how: str)` – `how` ∈ `"same"`, `"found"`, `"settings"`, `"cards"`.
  - `_own(section: Any) -> Any` – Section ohne `cards`.
  - `_section_list(view: dict) -> list` – `sections` oder `[]`.
  - `_pair_view_sections(key, old_index: int, old_view: dict, new_index: int, new_view: dict) -> tuple[list[SectionPair], list[SectionSlot], list[SectionSlot]]` – Paare, Rest alt, Rest neu.
  - `_pair_sections(old: dict, new: dict) -> tuple[list[SectionPair], list[SectionSlot], list[SectionSlot]]` – über alle gemeinsamen, nicht konvertierten Ansichten.
  - `_moved(pairs: list[SectionPair]) -> list[SectionPair]` – für die Paare **einer** Ansicht.

**Akzeptanz:** Alle Tests dieses Tasks grün, darunter der Tie-Break-Test und die Robustheitstests aus Review Focus 2; die Suite meldet 0 failed. Kein bestehender Aufrufer ändert sein Verhalten.

- [ ] **Step 1: Tests schreiben**

Am Ende von `tests/test_analyze.py`:

```python
# -- sections as units (GitHub #31) ---------------------------------------


def _md(text):
    return {"type": "markdown", "content": text}


def _sec(*names, **own):
    return {"type": "grid", **own, "cards": [_md(name) for name in names]}


def _pairing(before, after):
    pairs, gone, came = analyze._pair_sections(before, after)
    return (
        sorted((pair.old.index, pair.new.index, pair.how) for pair in pairs),
        [slot.index for slot in gone],
        [slot.index for slot in came],
    )


def test_identical_sections_in_place_pair_as_same():
    view = {"views": [_sectioned(_sec("a"), _sec("b"))]}
    assert _pairing(view, view) == ([(0, 0, "same"), (1, 1, "same")], [], [])


def test_a_swap_pairs_both_as_found():
    before = {"views": [_sectioned(_sec("a"), _sec("b"))]}
    after = {"views": [_sectioned(_sec("b"), _sec("a"))]}
    assert _pairing(before, after) == ([(0, 1, "found"), (1, 0, "found")], [], [])


def test_changed_settings_with_the_same_cards_pair_as_settings():
    before = {"views": [_sectioned(_sec("a", column_span=1))]}
    after = {"views": [_sectioned(_sec("a", column_span=2))]}
    assert _pairing(before, after) == ([(0, 0, "settings")], [], [])


def test_changed_cards_under_the_same_settings_pair_as_cards():
    before = {"views": [_sectioned(_sec("a"))]}
    after = {"views": [_sectioned(_sec("a", "b"))]}
    assert _pairing(before, after) == ([(0, 0, "cards")], [], [])


def test_a_section_changed_in_both_is_left_over():
    before = {"views": [_sectioned(_sec("a", column_span=1))]}
    after = {"views": [_sectioned(_sec("b", column_span=2))]}
    assert _pairing(before, after) == ([], [0], [0])


def test_a_deleted_section_leaves_one_old_section_over():
    before = {"views": [_sectioned(_sec("a"), _sec("b"))]}
    after = {"views": [_sectioned(_sec("b"))]}
    assert _pairing(before, after) == ([(1, 0, "found")], [0], [])


def test_a_converted_view_has_no_section_pairing():
    """The empty section a conversion adds belongs to the conversion (#32)."""
    before = {"views": [{"path": "home", "cards": [A]}]}
    after = {"views": [{"path": "home", "type": "sections", "cards": [A],
                        "sections": [{"type": "grid", "cards": []}]}]}
    assert _pairing(before, after) == ([], [], [])


def test_a_missing_or_null_sections_list_is_no_section():
    before = {"views": [{"path": "home", "type": "sections", "sections": None}]}
    after = {"views": [{"path": "home", "type": "sections"}]}
    assert _pairing(before, after) == ([], [], [])


def test_a_stray_non_dict_section_does_not_crash():
    before = {"views": [{"path": "home", "type": "sections", "sections": [_sec("a"), "junk"]}]}
    after = {"views": [{"path": "home", "type": "sections", "sections": ["junk", _sec("a")]}]}
    assert _pairing(before, after) == ([(0, 1, "found"), (1, 0, "found")], [], [])


def _moved_names(before, after):
    pairs, _, _ = analyze._pair_sections(before, after)
    return sorted(pair.old.section["cards"][0]["content"] for pair in analyze._moved(pairs))


def test_a_swap_is_one_move():
    before = {"views": [_sectioned(_sec("a"), _sec("b"))]}
    after = {"views": [_sectioned(_sec("b"), _sec("a"))]}
    assert _moved_names(before, after) == ["b"]


def test_the_first_of_five_sent_to_the_end_is_one_move():
    before = {"views": [_sectioned(*(_sec(n) for n in "abcde"))]}
    after = {"views": [_sectioned(*(_sec(n) for n in "bcdea"))]}
    assert _moved_names(before, after) == ["a"]


def test_closing_a_gap_is_no_move():
    before = {"views": [_sectioned(_sec("a"), _sec("b"), _sec("c"))]}
    after = {"views": [_sectioned(_sec("b"), _sec("c"))]}
    assert _moved_names(before, after) == []


def test_a_block_of_four_moved_is_four_moves():
    before = {"views": [_sectioned(*(_sec(n) for n in "AXYZBWCD"))]}
    after = {"views": [_sectioned(*(_sec(n) for n in "ABCDWZYX"))]}
    assert _moved_names(before, after) == ["W", "X", "Y", "Z"]


def test_ties_between_equally_long_runs_keep_the_earlier_old_sections():
    """[a, b, c, d] -> [c, d, a, b]: "a b" and "c d" both keep their order."""
    before = {"views": [_sectioned(*(_sec(n) for n in "abcd"))]}
    after = {"views": [_sectioned(*(_sec(n) for n in "cdab"))]}
    assert _moved_names(before, after) == ["c", "d"]
```

- [ ] **Step 2: Rot prüfen**

Run: `python3 -m pytest tests/test_analyze.py -k "pair or move or converted or stray or missing_or_null or left_over" -v`
Expected: die neuen Tests FAIL mit `AttributeError: module 'analyze' has no attribute '_pair_sections'`.

- [ ] **Step 3: Umsetzen**

In `analyze.py` direkt vor `def _views_by_key` einfügen:

```python
@dataclass(frozen=True)
class SectionSlot:
    """One section at the place it sits in a view (GitHub #31)."""

    view_key: Any
    view_index: int
    index: int
    section: Any


@dataclass(frozen=True)
class SectionPair:
    """One section found in both states; `how` names the pass that found it."""

    old: SectionSlot
    new: SectionSlot
    how: str  # "same", "found", "settings" or "cards"


def _own(section: Any) -> Any:
    """A section's own settings: everything but its cards."""
    if not isinstance(section, dict):
        return section
    return {key: value for key, value in section.items() if key != "cards"}


def _section_list(view: dict) -> list:
    """A view's sections, or none - `sections:` may be missing or null."""
    sections = view.get("sections")
    return sections if isinstance(sections, list) else []


def _pair_view_sections(
    key: Any, old_index: int, old_view: dict, new_index: int, new_view: dict
) -> tuple[list[SectionPair], list[SectionSlot], list[SectionSlot]]:
    """Pair one view's sections across two states, outside in.

    The shape of `match_cards`: identical at the same index, identical
    anywhere else in the view, then - at the same index only - the same
    cards under other settings, and the same settings over other cards.
    The last is the ordinary save, a card edited inside a section. What
    is left is returned as it is; whether it went or came whole is for
    `_settle_sections` to prove, with the cards.
    """
    olds = [SectionSlot(key, old_index, i, s) for i, s in enumerate(_section_list(old_view))]
    news = [SectionSlot(key, new_index, j, s) for j, s in enumerate(_section_list(new_view))]
    old_marks = [fingerprint(slot.section) for slot in olds]
    new_marks = [fingerprint(slot.section) for slot in news]
    taken_old: set[int] = set()
    taken_new: set[int] = set()
    pairs: list[SectionPair] = []

    def claim(i: int, j: int, how: str) -> None:
        taken_old.add(i)
        taken_new.add(j)
        pairs.append(SectionPair(olds[i], news[j], how))

    for i in range(min(len(olds), len(news))):
        if old_marks[i] == new_marks[i]:
            claim(i, i, "same")
    # Old sections in their order, each taking the first free new one:
    # the same pair of states always produces the same pairing.
    for i in range(len(olds)):
        if i in taken_old:
            continue
        j = next(
            (j for j in range(len(news)) if j not in taken_new and new_marks[j] == old_marks[i]),
            None,
        )
        if j is not None:
            claim(i, j, "found")
    for i in range(min(len(olds), len(news))):
        if i in taken_old or i in taken_new:
            continue
        old, new = olds[i].section, news[i].section
        if not isinstance(old, dict) or not isinstance(new, dict):
            continue
        same_cards = fingerprint(old.get("cards")) == fingerprint(new.get("cards"))
        same_own = fingerprint(_own(old)) == fingerprint(_own(new))
        if same_cards and not same_own:
            claim(i, i, "settings")
        elif same_own and not same_cards:
            claim(i, i, "cards")
    return (
        pairs,
        [slot for i, slot in enumerate(olds) if i not in taken_old],
        [slot for j, slot in enumerate(news) if j not in taken_new],
    )


def _pair_sections(
    old: dict, new: dict
) -> tuple[list[SectionPair], list[SectionSlot], list[SectionSlot]]:
    """`_pair_view_sections` for every view both states have.

    A converted view (#32) is left out: its layout changed, and the empty
    section Home Assistant adds with a conversion is a side effect of that
    event, not an event of its own.
    """
    pairs: list[SectionPair] = []
    rest_old: list[SectionSlot] = []
    rest_new: list[SectionSlot] = []
    new_views = {key: (index, view) for index, (key, view) in enumerate(_views_by_key(new))}
    for old_index, (key, old_view) in enumerate(_views_by_key(old)):
        if key not in new_views:
            continue
        new_index, new_view = new_views[key]
        if _view_type(old_view) != _view_type(new_view):
            continue
        found, gone, came = _pair_view_sections(key, old_index, old_view, new_index, new_view)
        pairs += found
        rest_old += gone
        rest_new += came
    return pairs, rest_old, rest_new


def _moved(pairs: list[SectionPair]) -> list[SectionPair]:
    """The pairs of one view outside the longest run that kept its order.

    The run is the longest increasing subsequence of the new indices, read
    in old order; of several equally long, the one whose old indices come
    first, element by element. A swap is then one move, the first of five
    sent to the end is one move, and a section that only closed a gap
    after a deletion is none.
    """
    ordered = sorted(pairs, key=lambda pair: pair.old.index)
    longest = [1] * len(ordered)
    for i in range(len(ordered) - 1, -1, -1):
        for k in range(i + 1, len(ordered)):
            if ordered[k].new.index > ordered[i].new.index:
                longest[i] = max(longest[i], longest[k] + 1)
    kept: set[int] = set()
    need = max(longest, default=0)
    last = -1
    for i, pair in enumerate(ordered):
        if need and longest[i] == need and pair.new.index > last:
            kept.add(i)
            last = pair.new.index
            need -= 1
    return [pair for i, pair in enumerate(ordered) if i not in kept]
```

- [ ] **Step 4: Grün prüfen**

Run: derselbe Aufruf wie in Step 2 → PASS. Dann `python3 -m pytest tests/ -v` → 0 failed.

- [ ] **Step 5: Commit (nach Go des Nutzers)**

```bash
git add custom_components/dashboard_history/analyze.py tests/test_analyze.py
git commit -m "Pair a view's sections outside in" -m "A section carries no id, so it is matched the way cards are: identical
in place, identical elsewhere in the view, then the same cards under
other settings or the same settings over other cards at the same index.
Moves are what lies outside the longest run that kept its order, so a
swap is one move. Not wired in yet. GitHub #31.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Karten über ihre gepaarten Sections zuordnen

Verdrahtung in `match_cards`, Beweis ganzer Sections, `find_removed` auf die neue Zuordnung umgestellt (Spec §1, §2). Die Anzeige folgt in Task 4, das Undo in Task 7 – bis dahin verweigert ein Section-Tausch weiterhin mit `_SECTIONS_REBUILT_REFUSAL`.

**Files:**
- Modify: `custom_components/dashboard_history/analyze.py` (Imports, `SectionMatching` und `Matching`, `_translated`, `_count_places`, `_whole`, `_settle_sections`, `match_cards` → `_match_slots`, `_reordered`, `find_removed`, `_explain`, `plan_undo`; `_sections_gone` entfällt)
- Test: `tests/test_analyze.py`

**Interfaces:**
- Consumes: `_pair_sections`, `_moved`, `_section_list`, `SectionSlot`, `SectionPair` (Task 2).
- Produces:
  - `SectionMatching(pairs, moved, removed, added, rest_old, rest_new)` – alle Felder Tupel; `removed`/`added`/`rest_*` aus `SectionSlot`, `pairs`/`moved` aus `SectionPair`; Methode `views() -> set` (jede Ansicht mit Bewegung, Einstellungsänderung, ganzer Section oder Rest).
  - `Matching.sections: SectionMatching`, `Matching.translate: dict` (`(view_key, alter Section-Index) → neuer Index`, nur für gepaarte Sections), `Matching.same_place(old: Slot, new: Slot) -> bool`, `Matching.loose_removed() -> list`, `Matching.loose_added() -> list`.
  - `_match_slots(old, new, containers, translate) -> Matching` (ohne `sections`); `_unpaired(slot, translate) -> bool`.
  - `match_sections(old: dict, new: dict) -> SectionMatching` – öffentlicher Name aus Spec §1, liest `match_cards(old, new).sections`.

**Akzeptanz:** Alle neuen Tests grün, darunter der Echt-Dashboard-Test (Review Focus 3); die bestehenden Tests zu `find_removed` (`test_a_deleted_section_is_offered_as_one_item`, `test_an_empty_section_that_was_deleted_is_not_offered_back`) und `test_a_card_moved_into_a_new_section_is_not_a_deletion_at_all` bleiben unverändert grün; `grep -n "_sections_gone" custom_components/` findet nichts mehr; Suite 0 failed.

- [ ] **Step 1: Tests schreiben**

Am Ende von `tests/test_analyze.py`:

```python
def test_the_cards_of_a_swapped_section_are_not_moved():
    before = {"views": [_sectioned(_sec("a1", "a2"), _sec("b1"))]}
    after = {"views": [_sectioned(_sec("b1"), _sec("a1", "a2"))]}
    matching = analyze.match_cards(before, after)
    assert (matching.removed, matching.added, matching.edited, matching.moved) == ([], [], [], [])
    assert len(matching.sections.moved) == 1


def test_a_card_reordered_beside_a_swap_is_still_moved():
    before = {"views": [_sectioned(_sec("a1", "a2"), _sec("b"), _sec("c"))]}
    after = {"views": [_sectioned(_sec("a2", "a1"), _sec("c"), _sec("b"))]}
    matching = analyze.match_cards(before, after)
    assert {slot.card["content"] for slot, _ in matching.moved} == {"a1", "a2"}
    assert len(matching.sections.moved) == 1


def test_a_deleted_section_is_proven_whole():
    before = {"views": [_sectioned(_sec("a"), _sec("b1", "b2"))]}
    after = {"views": [_sectioned(_sec("a"))]}
    matching = analyze.match_cards(before, after)
    assert [slot.index for slot in matching.sections.removed] == [1]
    assert matching.loose_removed() == []
    assert len(matching.removed) == 2


def test_an_added_section_with_a_heading_is_proven_whole():
    heading = {"type": "heading", "heading": "Neu"}
    before = {"views": [_sectioned(_sec("a"))]}
    after = {"views": [_sectioned(_sec("a"), {"type": "grid", "cards": [heading]})]}
    matching = analyze.match_cards(before, after)
    assert [slot.index for slot in matching.sections.added] == [1]
    assert matching.loose_added() == []


def test_an_added_empty_section_is_proven_whole():
    """The one left over in a view that grew by one - Home Assistant's "add section"."""
    before = {"views": [_sectioned(_sec("a"))]}
    after = {"views": [_sectioned(_sec("a"), _sec())]}
    assert [s.index for s in analyze.match_cards(before, after).sections.added] == [1]


def test_a_deleted_empty_section_is_left_over():
    before = {"views": [_sectioned(_sec("a"), _sec())]}
    after = {"views": [_sectioned(_sec("a"))]}
    sections = analyze.match_cards(before, after).sections
    assert (sections.removed, [s.index for s in sections.rest_old]) == ((), [1])


def test_two_sections_deleted_at_once_are_left_over():
    before = {"views": [_sectioned(_sec("a"), _sec("b"), _sec("c"))]}
    after = {"views": [_sectioned(_sec("a"))]}
    sections = analyze.match_cards(before, after).sections
    assert (sections.removed, sorted(s.index for s in sections.rest_old)) == ((), [1, 2])


def test_a_section_whose_card_turned_up_elsewhere_is_left_over():
    before = {"views": [_sectioned(_sec("a", "b"), _sec("c"))]}
    after = {"views": [_sectioned(_sec("c", "a"))]}
    sections = analyze.match_cards(before, after).sections
    assert sections.removed == ()
    assert [s.index for s in sections.rest_old] == [1]


def test_a_deleted_section_is_proven_although_the_next_one_holds_the_same_card():
    """The next section moved up to index 0; its own card must stay its own."""
    before = {"views": [_sectioned(_sec("x"), _sec("x", "y"))]}
    after = {"views": [_sectioned(_sec("x", "y"))]}
    assert [s.index for s in analyze.match_sections(before, after).removed] == [0]


def test_cards_of_an_unexplained_section_keep_their_real_index():
    """Spec O, section 1: a rest section is as if there were no pairing."""
    k = {"type": "tile", "entity": "light.k"}
    l = {"type": "tile", "entity": "light.l"}
    before = {"views": [_sectioned({"type": "grid", "column_span": 1, "cards": [k, l]})]}
    after = {"views": [_sectioned({"type": "grid", "column_span": 2, "cards": [k, {**l, "name": "x"}]})]}
    matching = analyze.match_cards(before, after)
    assert (matching.removed, matching.added, matching.moved) == ([], [], [])
    assert len(matching.edited) == 1


def test_a_pure_section_swap_is_not_nothing_to_undo():
    """No card event any more - but the change did something."""
    before = {"views": [_sectioned(_sec("a"), _sec("b"))]}
    after = {"views": [_sectioned(_sec("b"), _sec("a"))]}
    plan = analyze.plan_undo(before, after, after)
    assert plan.blocked is None or "did not alter any cards" not in plan.blocked


def test_real_dashboards_pair_every_section_with_itself():
    if not REAL_DASHBOARDS:
        pytest.skip("set DASHBOARD_HISTORY_REAL_STORAGE to run this")
    for path in REAL_DASHBOARDS:
        config = json.loads(path.read_text(encoding="utf-8"))["data"]["config"]
        sections = analyze.match_sections(config, config)
        assert sections.views() == set(), path.name
        assert all(pair.how == "same" for pair in sections.pairs), path.name
```

Hinweis zu `test_a_card_reordered_beside_a_swap_is_still_moved`: `_reordered` meldet nach seiner bestehenden Rangregel beide Karten, deren Rang sich geändert hat. Der Test hält fest, dass die Umsortierung **innerhalb** der nicht bewegten Section weiterhin gemeldet wird, während der Tausch daneben eine Section-Bewegung ist.

Hinweis zu `test_cards_of_an_unexplained_section_keep_their_real_index`: Das ist ein Wächter, kein Rot-Test. Er ist schon vor diesem Task grün und muss es bleiben. Er fängt ab, dass Karten einer nicht erklärten Section einen künstlichen Platz bekommen (Plan-Review 2026-09-26, Terra).

Hinweis zu `test_a_pure_section_swap_is_not_nothing_to_undo`: Bis Task 7 verweigert der Tausch mit `_SECTIONS_REBUILT_REFUSAL`, ab Task 7 ist er exakt. Der Test hält nur fest, was in beiden Ständen gilt: nie »did not alter any cards«.

- [ ] **Step 2: Rot prüfen**

Run: `python3 -m pytest tests/test_analyze.py -k "swapped_section or reordered_beside or proven_whole or left_over or pure_section_swap or pair_every_section or proven_although or real_index" -v`
Expected: FAIL (`Matching` hat kein Attribut `sections`).

- [ ] **Step 3: Datenklassen**

Import erweitern: `from dataclasses import dataclass, field, replace`.

Direkt vor `class Matching` einfügen:

```python
@dataclass(frozen=True)
class SectionMatching:
    """What happened to a dashboard's sections between two states (#31).

    `pairs` are the sections found in both, `moved` the pairs outside the
    run that kept its order. `removed` and `added` are sections proven to
    have gone or come whole. `rest_old` and `rest_new` are what neither
    explains: the explanation says nothing about them, and an undo of a
    view that has any refuses.
    """

    pairs: tuple = ()
    moved: tuple = ()
    removed: tuple = ()
    added: tuple = ()
    rest_old: tuple = ()
    rest_new: tuple = ()

    def views(self) -> set:
        """Every view this matching has something to say about."""
        return (
            {pair.old.view_key for pair in self.moved}
            | {pair.old.view_key for pair in self.pairs if pair.how == "settings"}
            | {
                slot.view_key
                for slot in (*self.removed, *self.added, *self.rest_old, *self.rest_new)
            }
        )
```

`class Matching` ersetzen durch:

```python
@dataclass(frozen=True)
class Matching:
    """Every card of one dashboard, paired across two of its states."""

    removed: list
    added: list
    edited: list  # (old, new)
    moved: list  # (old, new)
    sections: SectionMatching = field(default_factory=SectionMatching)
    # (view key, old section index) -> new index, for every paired
    # section (GitHub #31).
    translate: dict = field(default_factory=dict)

    def same_place(self, old: Slot, new: Slot) -> bool:
        """Whether a card stayed in its list, its section followed wherever it went."""
        return _translated(old, self.translate) == _place(new)

    def loose_removed(self) -> list:
        """Removed cards, less those of a section that went whole."""
        whole = {(s.view_key, ("sections", s.index, "cards")) for s in self.sections.removed}
        return [slot for slot in self.removed if (slot.view_key, slot.location) not in whole]

    def loose_added(self) -> list:
        """Added cards, less those of a section that came whole."""
        whole = {(s.view_key, ("sections", s.index, "cards")) for s in self.sections.added}
        return [slot for slot in self.added if (slot.view_key, slot.location) not in whole]
```

- [ ] **Step 4: Übersetzung und Beweis**

Direkt hinter `_place` einfügen:

```python
def _translated(slot: Slot, translate: dict) -> tuple:
    """Where an old slot's list is in the new state, its section followed.

    A card in a paired section sits, for comparison, in the list of that
    section wherever it went - so a section moved whole moves none of its
    cards. Every other card keeps its plain place, its real index (spec
    O, section 1): a section nothing paired is as if there were no
    section pairing at all.
    """
    location = slot.location
    if len(location) == 3 and location[0] == "sections" and (slot.view_key, location[1]) in translate:
        return (slot.view_key, ("sections", translate[(slot.view_key, location[1])], "cards"))
    return _place(slot)


def _unpaired(slot: Slot, translate: dict) -> bool:
    """Whether a slot sits in a section the pairing left unexplained."""
    location = slot.location
    return (
        len(location) == 3
        and location[0] == "sections"
        and (slot.view_key, location[1]) not in translate
    )
```

Direkt hinter `_moved` (Task 2) einfügen:

```python
def _count_places(slots: list[Slot]) -> dict:
    """How many of these slots sit in each card list."""
    counts: dict = {}
    for slot in slots:
        place = (slot.view_key, slot.location)
        counts[place] = counts.get(place, 0) + 1
    return counts


def _whole(slot: SectionSlot, counted: dict, empty_counts: bool) -> bool:
    """Whether every card of a section is among the counted ones."""
    cards = slot.section.get("cards") if isinstance(slot.section, dict) else None
    if not isinstance(cards, list):
        return False
    if not cards:
        return empty_counts
    return counted.get((slot.view_key, ("sections", slot.index, "cards")), 0) == len(cards)


def _settle_sections(
    old: dict,
    new: dict,
    pairs: list[SectionPair],
    rest_old: list[SectionSlot],
    rest_new: list[SectionSlot],
    matching: Matching,
) -> SectionMatching:
    """Moves from the pairs, and whole sections from what is left, proven by the cards.

    A left-over section went whole only where its view lost exactly one
    section and every card of it is among those the card matching gave up
    on - the proof put-back has used since package 3 of vorhaben F. An
    empty one never counts as gone: it has nothing to prove itself with,
    and every empty section of a shrunken view would look equally lost.
    Arriving is the same question the other way round. There an empty
    section counts: it is the single one left over in a view that grew by
    exactly one, and Home Assistant's own "add section" makes one.
    """
    old_counts = {key: len(_section_list(view)) for key, view in _views_by_key(old)}
    new_counts = {key: len(_section_list(view)) for key, view in _views_by_key(new)}
    gone = _count_places(matching.removed)
    came = _count_places(matching.added)
    removed: list[SectionSlot] = []
    added: list[SectionSlot] = []
    for key in sorted({slot.view_key for slot in rest_old}, key=str):
        if old_counts[key] - new_counts[key] == 1:
            found = [s for s in rest_old if s.view_key == key and _whole(s, gone, False)]
            if len(found) == 1:
                removed.append(found[0])
    for key in sorted({slot.view_key for slot in rest_new}, key=str):
        if new_counts[key] - old_counts[key] == 1:
            found = [s for s in rest_new if s.view_key == key and _whole(s, came, True)]
            if len(found) == 1:
                added.append(found[0])
    moved: list[SectionPair] = []
    for key in sorted({pair.old.view_key for pair in pairs}, key=str):
        moved += _moved([pair for pair in pairs if pair.old.view_key == key])
    return SectionMatching(
        pairs=tuple(pairs),
        moved=tuple(moved),
        removed=tuple(removed),
        added=tuple(added),
        rest_old=tuple(slot for slot in rest_old if slot not in removed),
        rest_new=tuple(slot for slot in rest_new if slot not in added),
    )
```

- [ ] **Step 5: `match_cards` aufteilen**

Die bisherige Funktion `match_cards` umbenennen in `_match_slots` mit der Signatur `def _match_slots(old: dict, new: dict, containers, translate: dict) -> Matching:` und ihrem Docstring durch eine Zeile ersetzen: `"""The four card passes of `match_cards`, old places followed through `translate`."""`. Darin vier Stellen ändern:

- Die Schleife der Durchgänge 1 und 2, heute

  ```python
      for pairs, buckets, at_place in (
          (in_place, here, True),
          (displaced, anywhere, False),
      ):
          for i, old_slot in enumerate(old_open):
              if i in taken_old:
                  continue
  ```

  wird zu

  ```python
      # Cards of paired sections, and cards outside sections, claim their
      # places first. A card of a section nothing paired keeps its real
      # index but comes last: when a section before it went, that index
      # now names the section that moved up, and its own identical card
      # must not be taken from it (GitHub #31).
      order = sorted(range(len(old_open)), key=lambda i: _unpaired(old_open[i], translate))
      for pairs, buckets, at_place in (
          (in_place, here, True),
          (displaced, anywhere, False),
      ):
          for i in order:
              old_slot = old_open[i]
              if i in taken_old:
                  continue
  ```

  (`sorted` ist stabil: Ohne Section-Reste bleibt die Reihenfolge genau die heutige.)
- `waiting = buckets.get((_place(old_slot), mark) if at_place else mark, ())` → `waiting = buckets.get((_translated(old_slot, translate), mark) if at_place else mark, ())`
- `if j in taken_new or _place(new_slot) != _place(old_slot):` → `if j in taken_new or _place(new_slot) != _translated(old_slot, translate):`
- im `return Matching(...)` als letztes Argument `translate=translate,` ergänzen.

Direkt davor die neue öffentliche Funktion, mit dem vollständigen bisherigen Docstring von `match_cards` und einem angehängten Absatz:

```python
def match_cards(old: dict, new: dict, containers=card_containers) -> Matching:
    """Pair the cards of two states of one dashboard.

    <bisheriger Docstring unverändert>

    Sections first (GitHub #31). A section carries no id either, and a
    card's place names its section by index - so a section moved whole
    used to move every card on it. The sections are paired first, outside
    in, and a card's old place is followed to where its section went
    before the passes compare places. Badges never sit in sections and
    skip this.
    """
    if containers is not card_containers:
        return _match_slots(old, new, containers, {})
    pairs, rest_old, rest_new = _pair_sections(old, new)
    translate = {(pair.old.view_key, pair.old.index): pair.new.index for pair in pairs}
    matching = _match_slots(old, new, containers, translate)
    return replace(
        matching,
        sections=_settle_sections(old, new, pairs, rest_old, rest_new, matching),
    )


def match_sections(old: dict, new: dict) -> SectionMatching:
    """What happened to a dashboard's sections between two states (spec O, section 1).

    The section half of `match_cards`, which needs the cards to prove a
    section went or came whole - so it is that call, read for its
    sections.
    """
    return match_cards(old, new).sections
```

`<bisheriger Docstring unverändert>` steht hier nur für den Text, der heute in `match_cards` steht (»`containers` says which lists are paired …« bis »… the same entity on two views is ordinary.«) – ihn beim Umbau wörtlich übernehmen, nicht diese Markierung einfügen.

In `_reordered` die Zeile `grouped.setdefault(_place(old_open[pair[0]]), []).append(pair)` ersetzen durch `grouped.setdefault(_place(new_open[pair[1]]), []).append(pair)` – ein Paar am selben Platz hat nach der Übersetzung denselben neuen Platz, der rohe alte Index einer verschobenen Section aber nicht mehr.

- [ ] **Step 6: Aufrufer umstellen**

`find_removed`:

```python
    gone_by_view: dict[int, list[Slot]] = {}
    for slot in matching.loose_removed():
        gone_by_view.setdefault(slot.view_index, []).append(slot)
    # Cards that left their place for another list: no survivor a
    # section has to keep for its anchor to hold (spec L, 4a).
    away_by_view: dict[int, set] = {}
    for was, now in matching.moved:
        if not matching.same_place(was, now):
            away_by_view.setdefault(was.view_index, set()).add((was.location, was.index))
```

Weiter unten `whole = _sections_gone(old_view, new_views[key], gone)` ersetzen durch:

```python
        # A section that went whole is one item, not one per card on it -
        # its cards are already out of `gone` (`loose_removed`).
        whole = {
            slot.index: slot.section
            for slot in matching.sections.removed
            if slot.view_key == key
        }
```

Die Zeile `swallowed = {("sections", index, "cards") for index in whole}` und die Bedingung `if slot.location not in swallowed` in der Karten-Liste streichen. Die Funktion `_sections_gone` löschen.

`_explain`, Schleife über `matching.moved`: `if _place(was) == _place(now):` → `if matching.same_place(was, now):`.

`plan_undo`, frühe Bedingung: hinter `or settings` die Zeile `or matching.sections.views()` ergänzen (vor der schließenden Klammer).

- [ ] **Step 7: Grün prüfen**

Run: derselbe Aufruf wie in Step 2 → PASS. `grep -n "_sections_gone" custom_components/` → keine Ausgabe. `python3 -m pytest tests/ -v` → 0 failed.

- [ ] **Step 8: Commit (nach Go des Nutzers)**

```bash
git add custom_components/dashboard_history/analyze.py tests/test_analyze.py
git commit -m "Match cards through their paired sections" -m "Sections are paired before their cards, and a card's old place follows
its section, so a section moved whole no longer moves every card on it.
A section that went or came whole is proven by its cards, the way
put-back already proved a deleted one; find_removed now reads that
instead of its own copy of the proof. GitHub #31.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Sections erklären und zählen

**Files:**
- Modify: `custom_components/dashboard_history/analyze.py` (`Entry`, `Summary`, `_section_title` statt `_section_label`, `_section_name`, `_PAST`, `_FUTURE`, `_section_setting_changes`, `_explain`, `summarize`, `_sections_part`, `change_message`, `_COUNT`, `find_removed`)
- Test: `tests/test_analyze.py`

**Interfaces:**
- Consumes: `Matching.sections`, `loose_removed`, `loose_added`, `SectionPair`, `SectionSlot`, `_own` (Tasks 2/3).
- Produces: `_section_title(section: Any, index: int) -> str` (`'section "X"'` oder `"section N"`); `Summary.sections_moved`, `Summary.sections_added`, `Summary.sections_removed`; `_section_setting_changes(pair: SectionPair) -> list[SettingChange]`.

**Akzeptanz:** Neue Tests grün, darunter Review Focus 1 und 5; `test_a_card_moved_into_a_named_section_says_its_name` bleibt unverändert grün; im Echt-Dashboard-Test ist nur die erlaubte `what`-Menge erweitert; Suite 0 failed.

- [ ] **Step 1: Tests schreiben**

Am Ende von `tests/test_analyze.py`:

```python
def _said(before, after):
    return [e.text for g in analyze.explain_change(before, after).groups for e in g.entries]


def test_a_swap_of_two_sections_is_explained_as_one_move():
    """The case from dashboard test_2, view a2."""
    heading = {"type": "heading", "heading": "Neuer Abschnitt"}
    first = {"type": "grid", "cards": [heading, _md("noon")]}
    second = {"type": "grid", "cards": [_md("person"), _md("sun")]}
    before = {"views": [_sectioned(first, second, title="A2")]}
    after = {"views": [_sectioned(second, first, title="A2")]}
    assert _said(before, after) == ["section 2 was moved"]
    assert analyze.change_message("test-2", before, after, "save") == "test-2: 1 section moved"


def test_undoing_a_swap_is_said_in_the_future_tense():
    heading = {"type": "heading", "heading": "Neuer Abschnitt"}
    first = {"type": "grid", "cards": [heading, _md("noon")]}
    second = {"type": "grid", "cards": [_md("person")]}
    before = {"views": [_sectioned(first, second)]}
    after = {"views": [_sectioned(second, first)]}
    effect = analyze.explain_effect(after, before)
    assert [e.text for g in effect.groups for e in g.entries] == [
        'section "Neuer Abschnitt" moves back to where it was'
    ]


def test_a_deleted_section_is_one_line_named_by_its_heading():
    heading = {"type": "heading", "heading": "Heizung"}
    before = {"views": [_sectioned(_sec("a"), {"type": "grid", "cards": [heading, _md("b")]})]}
    after = {"views": [_sectioned(_sec("a"))]}
    assert _said(before, after) == ['section "Heizung" was removed']
    assert analyze.change_message("home", before, after, "save") == "home: 1 section removed"


def test_an_added_section_is_one_line_and_counts_as_added():
    before = {"views": [_sectioned(_sec("a"))]}
    after = {"views": [_sectioned(_sec("a"), {"type": "grid", "cards": [{"type": "heading", "heading": "Neu"}]})]}
    assert _said(before, after) == ['section "Neu" was added']
    message = analyze.change_message("home", before, after, "save")
    assert message == "home: 1 section added"
    assert analyze.message_adds(message) is True


def test_a_changed_section_setting_is_named_with_old_and_new():
    before = {"views": [_sectioned(_sec("a", column_span=1))]}
    after = {"views": [_sectioned(_sec("a", column_span=2))]}
    assert _said(before, after) == ['section 1: the setting "column_span" was changed from 1 to 2']
    assert analyze.change_message("home", before, after, "save") == "home: 1 setting changed"


def test_a_heading_field_on_another_card_type_names_no_section():
    impostor = {"type": "markdown", "heading": "Nope", "content": "x"}
    before = {"views": [_sectioned(_sec("a"), {"type": "grid", "title": "Titel", "cards": [impostor]})]}
    after = {"views": [_sectioned(_sec("a"))]}
    assert _said(before, after) == ['section "Titel" was removed']


def test_an_empty_heading_falls_back_to_the_position():
    blank = {"type": "heading", "heading": "  "}
    before = {"views": [_sectioned(_sec("a"), {"type": "grid", "cards": [blank]})]}
    after = {"views": [_sectioned(_sec("a"))]}
    assert _said(before, after) == ["section 2 was removed"]


def test_moving_the_only_card_into_an_empty_alike_section_reads_as_a_section_move():
    """Both readings are the same bytes; the pairing takes the exact one."""
    before = {"views": [_sectioned(_sec("a"), _sec())]}
    after = {"views": [_sectioned(_sec(), _sec("a"))]}
    assert _said(before, after) == ["section 2 was moved"]


def test_section_counts_parse_as_a_generated_message():
    assert analyze._counts("home: 2 sections moved, 1 removed") == ["2 sections moved", "1 removed"]
```

In `test_every_real_card_can_be_named` die Zeile `assert entry.what in ("card", "view")` ersetzen durch `assert entry.what in ("card", "view", "section", "section_setting")` – wird eine Section beim Entfernen ihrer ersten Karte leer und ist eine gleich eingestellte leere daneben, liest die Zuordnung das berechtigt als Section-Bewegung (Review Focus 1).

- [ ] **Step 2: Rot prüfen**

Run: `python3 -m pytest tests/test_analyze.py -k "explained or future_tense or one_line or setting_is_named or names_no_section or empty_heading or alike_section or section_counts" -v`
Expected: FAIL.

- [ ] **Step 3: Namen**

`_section_label` löschen und an ihrer Stelle einfügen:

```python
def _section_title(section: Any, index: int) -> str:
    """What to call a section: its heading card, else its title, else its place.

    Home Assistant names a section with a heading card at its top - 72
    of 102 on the installation this was built against - and all but never
    with `title` (0 of 102). Only a real heading card counts: a card of
    another type with a `heading` field of its own names nothing.
    """
    cards = section.get("cards") if isinstance(section, dict) else None
    first = cards[0] if isinstance(cards, list) and cards else None
    if (
        isinstance(first, dict)
        and first.get("type") == "heading"
        and isinstance(first.get("heading"), str)
        and first["heading"].strip()
    ):
        return f'section "{_shorten(first["heading"])}"'
    title = section.get("title") if isinstance(section, dict) else None
    if isinstance(title, str) and title.strip():
        return f'section "{_shorten(title)}"'
    return f"section {index + 1}"
```

In `find_removed` `label=_section_label(section, index)` → `label=_section_title(section, index)`.

In `_section_name` alles ab `sections = slot.view.get("sections") or []` ersetzen durch:

```python
    sections = slot.view.get("sections") or []
    index = slot.location[1]
    section = sections[index] if 0 <= index < len(sections) else {}
    title = _section_title(section, index)
    return f"the {title}" if title.startswith('section "') else title
```

und den Docstring um den Satz ergänzen: `Named by the same rule as every other section (`_section_title`).`

- [ ] **Step 4: Wörter und Zählung**

`Entry`: Kommentar an `what` auf `# "card", "view", "badge", "setting", "section" or "section_setting"`.

`Summary`: drei Felder ergänzen:

```python
    sections_moved: int = 0
    sections_added: int = 0
    sections_removed: int = 0
```

`_PAST` ergänzen:

```python
    ("section", "removed"): "{label} was removed",
    ("section", "added"): "{label} was added",
    ("section", "moved"): "{label} was moved",
```

`_FUTURE` ergänzen:

```python
    ("section", "removed"): "{label} will be removed",
    ("section", "added"): "{label} comes back",
    ("section", "moved"): "{label} moves back to where it was",
```

Hinter `_setting_entry`:

```python
def _section_setting_changes(pair: SectionPair) -> list[SettingChange]:
    """A paired section's own settings that differ, by name like a view's (M)."""
    out: list[SettingChange] = []
    _setting_leaves(pair.old.view_key, _own(pair.old.section), _own(pair.new.section), (), out)
    return out
```

In `_explain` hinter dem Badge-Block (vor `by_view: dict[Any, list[Entry]] = {}`):

```python
    sections_by_view: dict[Any, list[Entry]] = {}

    def section(key: Any, kind: str, slot: SectionSlot) -> None:
        sections_by_view.setdefault(key, []).append(
            _entry(words, kind, "section", _section_title(slot.section, slot.index))
        )

    for slot in matching.sections.removed:
        section(slot.view_key, "removed", slot)
    for slot in matching.sections.added:
        section(slot.view_key, "added", slot)
    for pair in matching.sections.moved:
        section(pair.old.view_key, "moved", pair.old)
    for pair in matching.sections.pairs:
        if pair.how != "settings":
            continue
        title = _section_title(pair.old.section, pair.old.index)
        for change in _section_setting_changes(pair):
            said = _setting_entry(words, change)
            sections_by_view.setdefault(pair.old.view_key, []).append(
                Entry(
                    kind=said.kind,
                    what="section_setting",
                    label=f"{title}: {said.label}",
                    text=f"{title}: {said.text}",
                )
            )
```

In den Karten-Schleifen darunter `for slot in matching.removed:` → `for slot in matching.loose_removed():` und `for slot in matching.added:` → `for slot in matching.loose_added():`. In der Zusammenstellung je Ansicht:

```python
        entries = [
            *settings_by_view.get(key, []),
            *badges_by_view.get(key, []),
            *sections_by_view.get(key, []),
            *by_view.get(key, []),
        ]
```

`summarize`:

```python
    section_settings = sum(
        len(_section_setting_changes(pair))
        for pair in matching.sections.pairs
        if pair.how == "settings"
    )
```

und im `return Summary(...)`: `added=len(matching.loose_added())`, `removed=len(matching.loose_removed())`, `settings=len(setting_changes(old, new)) + section_settings`, dazu `sections_moved=len(matching.sections.moved)`, `sections_added=len(matching.sections.added)`, `sections_removed=len(matching.sections.removed)`.

Hinter `_views`:

```python
def _sections_part(count: int, verb: str) -> str:
    """"1 section moved", "2 sections added", or nothing."""
    if not count:
        return ""
    return f"{count} section{'s' if count != 1 else ''} {verb}"
```

In `change_message` hinter den beiden `_views(...)`-Teilen:

```python
        _sections_part(counts.sections_removed, "removed"),
        _sections_part(counts.sections_added, "added"),
        _sections_part(counts.sections_moved, "moved"),
```

`_COUNT`:

```python
_COUNT = re.compile(
    r"^\d+ (?:views? (?:added|removed)|sections? (?:added|removed|moved)"
    r"|added|removed|edited|moved|settings? changed|badges? changed)$"
)
```

`message_adds` bleibt unverändert: `1 section added` endet auf ` added`.

- [ ] **Step 5: Grün prüfen**

Run: derselbe Aufruf wie in Step 2 → PASS. `python3 -m pytest tests/ -v` → 0 failed.

- [ ] **Step 6: Commit (nach Go des Nutzers)**

```bash
git add custom_components/dashboard_history/analyze.py tests/test_analyze.py
git commit -m "Explain and count whole sections" -m "A section swapped, moved, added or deleted whole is one line now,
named by its heading card, and counted as such in the history line; a
section's own settings read like a view's. Sections are named by one
rule everywhere. GitHub #31.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: `restore.apply_undo` für den `sections_list`-Schritt

**Files:**
- Modify: `custom_components/dashboard_history/restore.py`
- Test: `tests/test_restore.py`

**Interfaces:**
- Consumes: `UndoStep` mit `action="set"`, `kind="sections_list"`, `location=()`, `index=0`, `expect` = heutige Liste, `payload` = Zielliste.
- Produces: `_apply_sections_list(views: list, step: UndoStep) -> None`.

**Akzeptanz:** Neue Tests grün; die übergebene Konfiguration bleibt unverändert; Suite 0 failed.

- [ ] **Step 1: Tests schreiben**

Am Ende von `tests/test_restore.py`:

```python
# -- a whole row of sections (GitHub #31) ----------------------------------


def _sections_step(expect, payload):
    return analyze.UndoStep(
        action="set",
        kind="sections_list",
        view_path="home",
        view_index=0,
        location=(),
        index=0,
        expect=expect,
        payload=payload,
        label='the sections of the view "home"',
    )


def test_a_sections_step_replaces_the_whole_list():
    now = [{"cards": [B]}, {"cards": [A]}]
    target = [{"cards": [A]}, {"cards": [B]}]
    config = _sections(*now)
    plan = analyze.UndoPlan(blocked=None, steps=(_sections_step(now, target),))
    assert restore.apply_undo(config, plan) == _sections(*target)
    assert config == _sections(*now)


def test_a_sections_step_refuses_when_the_list_changed_since():
    now = [{"cards": [B]}, {"cards": [A]}]
    plan = analyze.UndoPlan(
        blocked=None,
        steps=(_sections_step(now, [{"cards": [A]}, {"cards": [B]}]),),
    )
    with pytest.raises(LookupError, match="sections"):
        restore.apply_undo(_sections({"cards": [B]}, {"cards": [A, C]}), plan)


def test_a_sections_step_tells_1_from_true():
    plan = analyze.UndoPlan(
        blocked=None,
        steps=(_sections_step([{"column_span": 1, "cards": []}], [{"cards": []}]),),
    )
    with pytest.raises(LookupError):
        restore.apply_undo(_sections({"column_span": True, "cards": []}), plan)
```

- [ ] **Step 2: Rot prüfen**

Run: `python3 -m pytest tests/test_restore.py -k sections_step -v`
Expected: FAIL (der Schritt wird ignoriert, die Liste bleibt stehen, bzw. kein `LookupError`).

- [ ] **Step 3: Umsetzen**

In `restore.py` hinter `_apply_setting`:

```python
def _apply_sections_list(views: list, step: UndoStep) -> None:
    """Write a view's whole row of sections back, if it is still the one planned against.

    One step for the whole list (GitHub #31): sections have no address but
    their index, and several moved at once shift each other's. The list
    was built in `analyze.plan_undo`; this only checks and writes.
    """
    view = _find_view(views, step)
    if view is None:
        raise LookupError(
            f"the view of {step.label} no longer exists "
            f"(path={step.view_path!r}, index={step.view_index})"
        )
    if not _same_value(view.get("sections"), step.expect):
        raise LookupError(f"{step.label} are no longer as the undo was planned for them")
    view["sections"] = copy.deepcopy(step.payload)
```

In `apply_undo` zwischen der Schleife, die Karten und Badges entfernt, und der Schleife, die Ansichten entfernt:

```python
    # A whole row of sections, after single cards and before whole views:
    # a view is found by its path, else by the index removing a view
    # would move.
    for step in plan.steps:
        if step.kind == "sections_list":
            _apply_sections_list(views, step)
```

Im Docstring von `apply_undo` hinter dem Absatz über die Reihenfolge den Satz ergänzen: `A view's sections, when a change moved them, are one step that writes the whole list (GitHub #31) - after single cards, before whole views.`

- [ ] **Step 4: Grün prüfen**

Run: derselbe Aufruf wie in Step 2 → PASS. `python3 -m pytest tests/ -v` → 0 failed.

- [ ] **Step 5: Commit (nach Go des Nutzers)**

```bash
git add custom_components/dashboard_history/restore.py tests/test_restore.py
git commit -m "Apply a whole-list sections step" -m "An undo can now write a view's whole row of sections in one step,
refusing when the row is no longer the one it was planned against,
compared the way fingerprint compares. Nothing plans such a step yet.
GitHub #31.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Den Section-Schritt einer Ansicht planen

Der Merge und alle Beweise als reine Funktion (Spec §4). Verdrahtet wird sie in Task 7.

**Files:**
- Modify: `custom_components/dashboard_history/analyze.py` (`import copy`; `_plan_sections` direkt vor `def plan_undo`)
- Test: `tests/test_analyze.py` (dazu `import restore` bei den Imports)

**Interfaces:**
- Consumes: `SectionMatching`, `_pair_view_sections`, `_moved`, `_section_list`, `_section_title`, `_view_name`, `fingerprint`, `UndoStep`.
- Produces: `_plan_sections(key: Any, before_view: dict, after_view: dict, current_view: dict | None, current_index: int, change: SectionMatching) -> UndoStep | str | None` – ein `sections_list`-Schritt, ein Verweigerungssatz oder `None`, wenn die Ansicht nichts an Sections zurückzunehmen hat.

**Beweisreihenfolge im Code (verbindlich):**
1. Rest in dieser Ansicht → Verweigerung (»Kein Rest darf bleiben«).
2. Kein Ereignis → `None`.
3. Ansicht heute nicht vorhanden → Verweigerung.
4. `sections` ist in `before` oder heute keine echte Liste (fehlt oder `null`) → Verweigerung. Der Schreibschritt vergleicht und schreibt Rohwerte; eine auf `[]` normalisierte Liste wäre weder ein ehrliches `expect` noch ein exakter Stand davor (Plan-Review 2026-09-26, Terra, Kritisch 2).
5. Durchgänge 1–4 zwischen `after` und heute: Ist ein Rest da oder hat sich etwas bewegt, wird verweigert (Überlebenden-Probe). Zusätzlich darf **höchstens ein** Paar aus Durchgang 3 oder 4 stammen. Nur dann ist dessen Identität erzwungen, weil alle anderen Sections bytegleich an ihrem Platz stehen und genau ein Platz übrig bleibt. Bei zwei oder mehr seither bearbeiteten Sections ist die Paarung per Index geraten: Sie könnten auch seither vertauscht *und* bearbeitet worden sein (Plan-Review 2026-09-26, Astra, mit ausgeführtem Gegenbeispiel). Danach liegen beide Listen Index für Index nebeneinander.
6. Jede hinzugekommene, verschobene oder einstellungs-geänderte Section, gezählt an ihrem Index in `after`: heute bytegleich wie nach der Änderung, und in beiden Ständen genau einmal in der Ansicht.
7. Merge über `before`: gepaart mit `how == "settings"` → `before`s Fassung (die Karten sind nach 6 gleich), sonst gepaart → heutige Fassung am Partner-Index; bewiesen verschwunden → `before`s Fassung. Hinzugekommene fallen heraus.

**Akzeptanz:** Alle Tests dieses Tasks grün, insbesondere Astras Gegenbeispiel aus der Spec-Runde (`apply_undo(...) == before`), Astras Gegenbeispiel aus der Plan-Runde (Verweigerung) und Review Focus 1 und 6; Suite 0 failed.

- [ ] **Step 1: Tests schreiben**

In `tests/test_analyze.py` bei den Imports `import restore` ergänzen. Am Ende:

```python
def _section_plan(before, after, current, key="home"):
    change = analyze.match_cards(before, after).sections
    views = [dict(analyze._views_by_key(state)) for state in (before, after, current)]
    index = next(i for i, (k, _) in enumerate(analyze._views_by_key(current)) if k == key)
    return analyze._plan_sections(key, views[0][key], views[1][key], views[2].get(key), index, change)


def _undone(current, step):
    assert not isinstance(step, str), step
    return restore.apply_undo(current, analyze.UndoPlan(blocked=None, steps=(step,)))


def _row(names):
    return {"views": [_sectioned(*(_sec(n) for n in names))]}


def test_a_block_of_sections_moved_together_is_put_back_exactly():
    """Astra's counter-example to the per-section indices of an earlier draft."""
    before, after = _row("AXYZBWCD"), _row("ABCDWZYX")
    assert _undone(after, _section_plan(before, after, after)) == before


def test_a_swap_of_sections_with_different_settings_is_put_back_settings_and_all():
    before = {"views": [_sectioned(_sec("a", column_span=2), _sec("b", column_span=1))]}
    after = {"views": [_sectioned(_sec("b", column_span=1), _sec("a", column_span=2))]}
    assert _undone(after, _section_plan(before, after, after)) == before


def test_a_rotation_with_a_deleted_section_is_put_back():
    before, after = _row("abcd"), _row("cab")
    assert _undone(after, _section_plan(before, after, after)) == before


def test_an_added_section_is_taken_out():
    before = {"views": [_sectioned(_sec("a"))]}
    after = {"views": [_sectioned(_sec("a"), _sec("n"))]}
    assert _undone(after, _section_plan(before, after, after)) == before


def test_a_changed_section_setting_is_set_back():
    before = {"views": [_sectioned(_sec("a", column_span=1))]}
    after = {"views": [_sectioned(_sec("a", column_span=2))]}
    assert _undone(after, _section_plan(before, after, after)) == before


def test_a_card_edited_since_in_another_section_does_not_block_and_stays():
    before, after = _row("abc"), _row("bac")
    current = {"views": [_sectioned(_sec("b"), _sec("a"), _sec("c", "c2"))]}
    expected = {"views": [_sectioned(_sec("a"), _sec("b"), _sec("c", "c2"))]}
    assert _undone(current, _section_plan(before, after, current)) == expected


def test_survivors_rearranged_since_refuse():
    before, after, current = _row("AXYZBWCD"), _row("ABCDWZYX"), _row("ACBDWZYX")
    assert "rearranged since" in _section_plan(before, after, current)


def test_an_added_section_edited_since_refuses():
    before = {"views": [_sectioned(_sec("a"))]}
    after = {"views": [_sectioned(_sec("a"), _sec("n"))]}
    current = {"views": [_sectioned(_sec("a"), _sec("n", "n2"))]}
    assert "was changed again after this" in _section_plan(before, after, current)


def test_two_alike_sections_both_moved_refuse():
    before = {"views": [_sectioned(_sec("a"), _sec("e"), _sec("e"))]}
    after = {"views": [_sectioned(_sec("e"), _sec("e"), _sec("a"))]}
    assert "look exactly like" in _section_plan(before, after, after)


def test_a_card_dragged_into_a_new_section_refuses():
    before = {"views": [_sectioned(_sec("a", "b"))]}
    after = {"views": [_sectioned(_sec("a"), _sec("b"))]}
    assert "cannot account for" in _section_plan(before, after, after)


def test_a_section_moved_and_edited_in_one_save_refuses():
    before = {"views": [_sectioned(_sec("a"), _sec("b"))]}
    after = {"views": [_sectioned(_sec("b"), _sec("a", "z"))]}
    assert "cannot account for" in _section_plan(before, after, after)


def test_a_view_without_section_changes_needs_no_step():
    state = _row("ab")
    assert _section_plan(state, state, state) is None


def test_two_survivors_edited_and_swapped_since_refuse():
    """Astra's counter-example to the first draft of this plan.

    B moved to the front; since then A and C were both edited and A was
    sent to the end. Paired by index, "A -> C edited" and "C -> A edited"
    look like two edits in place, and the merge wrote C before B.
    """
    before, after = _row("abc"), _row("bac")
    current = {"views": [_sectioned(_sec("b"), _sec("c", "c2"), _sec("a", "a2"))]}
    assert "more than one section" in _section_plan(before, after, current)


def test_a_view_whose_sections_were_missing_before_refuses():
    before = {"views": [{"path": "home", "type": "sections"}]}
    after = {"views": [_sectioned({"type": "grid", "cards": [{"type": "heading", "heading": "Neu"}]})]}
    assert "not a plain list" in _section_plan(before, after, after)


def test_a_view_whose_sections_are_null_today_refuses():
    before, after = _row("ab"), _row("ba")
    current = {"views": [{"path": "home", "type": "sections", "sections": None}]}
    assert "not a plain list" in _section_plan(before, after, current)


def test_the_only_card_moved_into_an_empty_alike_section_is_undone_exactly():
    before = {"views": [_sectioned(_sec("a"), _sec())]}
    after = {"views": [_sectioned(_sec(), _sec("a"))]}
    assert _undone(after, _section_plan(before, after, after)) == before
```

- [ ] **Step 2: Rot prüfen**

Run: `python3 -m pytest tests/test_analyze.py -k "put_back_exactly or settings_and_all or rotation_with or taken_out or set_back or edited_since or rearranged_since or both_moved or dragged_into or moved_and_edited or needs_no_step or undone_exactly or swapped_since or missing_before or null_today" -v`
Expected: FAIL (`_plan_sections` fehlt).

- [ ] **Step 3: Umsetzen**

`import copy` zu den Imports in `analyze.py`. Direkt vor `def plan_undo`:

```python
def _plan_sections(
    key: Any,
    before_view: dict,
    after_view: dict,
    current_view: dict | None,
    current_index: int,
    change: SectionMatching,
) -> UndoStep | str | None:
    """The one step that puts a view's sections back, why it cannot, or None.

    Decision 15 for sections (GitHub #31). A section has no address but
    its index, and several moved at once shift each other's - so nothing
    here is an index: the whole row is rebuilt in `before`'s order and
    written in one step. `before`'s order says where each goes; today's
    state is where each one's content comes from. What makes that exact
    is asked first, all of it or nothing.
    """
    name = _view_name(after_view, key)
    mine = [pair for pair in change.pairs if pair.old.view_key == key]
    moved = [pair for pair in change.moved if pair.old.view_key == key]
    reset = [pair for pair in mine if pair.how == "settings"]
    added = [slot for slot in change.added if slot.view_key == key]
    removed = [slot for slot in change.removed if slot.view_key == key]
    if any(slot.view_key == key for slot in (*change.rest_old, *change.rest_new)):
        return (
            f'the sections of the view "{name}" changed in a way this undo '
            f"cannot account for, so it refuses rather than guess"
        )
    if not (moved or reset or added or removed):
        return None
    if current_view is None:
        return f'the view "{name}" is no longer on the dashboard, so its sections cannot be taken back'
    if not isinstance(before_view.get("sections"), list) or not isinstance(
        current_view.get("sections"), list
    ):
        return (
            f'the sections of the view "{name}" are not a plain list in every '
            f"state, so an exact undo cannot write them back"
        )

    # Since the change: nothing arrived, went or moved among the sections,
    # so each stands at the index it had after the change. One of them may
    # have been edited since - its identity is then forced, every other
    # one standing byte for byte in its place. Two edited since could as
    # well have swapped places too, and index is no proof of which is
    # which.
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

    then_sections = _section_list(after_view)
    now_sections = _section_list(current_view)
    then_marks = [fingerprint(section) for section in then_sections]
    now_marks = [fingerprint(section) for section in now_sections]
    for index in sorted({*(slot.index for slot in added), *(pair.new.index for pair in (*moved, *reset))}):
        title = _section_title(then_sections[index], index)
        mark = then_marks[index]
        if now_marks[index] != mark:
            return (
                f"the {title} was changed again after this, so there is no "
                f"exact version left to take back"
            )
        alike = max(now_marks.count(mark), then_marks.count(mark))
        if alike > 1:
            return (
                f"{alike} sections now look exactly like {title}, so an "
                f"exact undo cannot tell them apart"
            )

    by_old = {pair.old.index: pair for pair in mine}
    target = []
    for index, section in enumerate(_section_list(before_view)):
        pair = by_old.get(index)
        if pair is None or pair.how == "settings":
            # Gone whole, or only its own settings changed - and its cards
            # are today's, proven above.
            target.append(copy.deepcopy(section))
        else:
            target.append(copy.deepcopy(now_sections[pair.new.index]))
    return UndoStep(
        action="set",
        kind="sections_list",
        view_path=current_view.get("path"),
        view_index=current_index,
        location=(),
        index=0,
        expect=copy.deepcopy(now_sections),
        payload=target,
        label=f'the sections of the view "{name}"',
    )
```

`UndoStep.kind`-Kommentar ergänzen: `# "card" | "badge" | "view" | "dashboard_setting" | "view_setting" | "sections_list"`.

- [ ] **Step 4: Grün prüfen**

Run: derselbe Aufruf wie in Step 2 → PASS. `python3 -m pytest tests/ -v` → 0 failed.

- [ ] **Step 5: Commit (nach Go des Nutzers)**

```bash
git add custom_components/dashboard_history/analyze.py tests/test_analyze.py
git commit -m "Plan a view's sections as one step" -m "Undoing section changes rebuilds the whole row in the order it had
before the change and writes it in one step, so sections moved together
cannot shift each other into an order that never existed. It refuses
whatever it cannot prove: a section left unexplained, the others moved
since, or one of its own changed again. Not wired in yet. GitHub #31.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Section-Schritt in `plan_undo`

**Files:**
- Modify: `custom_components/dashboard_history/analyze.py` (`_section_drift`, `plan_undo`, `_SECTIONS_REBUILT_REFUSAL` entfällt, neu `_SECTIONS_AND_CARDS_REFUSAL`)
- Test: `tests/test_analyze.py` (drei bestehende Tests umgeschrieben, neue Tests)

**Interfaces:**
- Consumes: `_plan_sections` (Task 6), `Matching.sections`, `loose_removed`, `loose_added` (Task 3).
- Produces: `_section_drift(new_views: dict, now_views: dict) -> set` (nur noch »seither verschoben«); `_SECTIONS_AND_CARDS_REFUSAL: str`.

**Bewusst umgeschriebene Tests** (Spec, Test-Plan: »im Plan einzeln umgeschrieben, mit Begründung statt stillschweigend«):

| bisher | neu | Begründung |
|---|---|---|
| `test_undo_refuses_when_a_section_was_inserted_before_another` | `test_a_section_inserted_before_another_is_taken_out_again` | Die eingefügte Section ist bewiesen hinzugekommen; der Merge nimmt sie heraus, die Adresse ist kein Index mehr. |
| `test_undo_refuses_when_two_untitled_sections_swap_settings` | `test_a_swap_of_two_untitled_sections_is_undone_settings_and_all` | Der Tausch wird als Section-Bewegung erkannt und ganz zurückgeschrieben – genau der Fall aus #31, der vorher verweigert wurde. |
| `test_a_change_that_rebuilt_the_sections_says_so` | `test_a_change_that_added_a_section_takes_it_out_again` | `_SECTIONS_REBUILT_REFUSAL` entfällt (Spec §4). |

**Akzeptanz:** Die drei Tests sind umgeschrieben wie oben, die neuen Tests grün (darunter Review Focus 4); `grep -rn "_SECTIONS_REBUILT_REFUSAL\|rearranged the sections" custom_components/ tests/` findet nichts; Suite 0 failed.

- [ ] **Step 1: Tests umschreiben und ergänzen**

Die drei Funktionen aus der Tabelle ersetzen durch:

```python
def test_a_section_inserted_before_another_is_taken_out_again():
    """It used to refuse: ("sections", 1, "cards") named a different section.

    Since #31 the inserted section is proven added and the row goes back
    as a whole, so no index has to mean anything.
    """
    old = {"views": [{"path": "home", "type": "sections",
                      "sections": [{"title": "Unten", "cards": [B]}]}]}
    new = {"views": [{"path": "home", "type": "sections",
                      "sections": [{"title": "Neu", "cards": [C]},
                                   {"title": "Unten", "cards": [B]}]}]}
    plan = analyze.plan_undo(old, new, new)
    assert plan.blocked is None
    assert restore.apply_undo(new, plan) == old


def test_a_swap_of_two_untitled_sections_is_undone_settings_and_all():
    """GitHub #31: once refused, before that silently wrong - now exact."""
    old = {"views": [{"path": "home", "type": "sections", "sections": [
        {"column_span": 2, "cards": [A]},
        {"column_span": 1, "cards": [B]},
    ]}]}
    new = {"views": [{"path": "home", "type": "sections", "sections": [
        {"column_span": 1, "cards": [B]},
        {"column_span": 2, "cards": [A]},
    ]}]}
    plan = analyze.plan_undo(old, new, new)
    assert plan.blocked is None
    assert [step.kind for step in plan.steps] == ["sections_list"]
    assert restore.apply_undo(new, plan) == old


def test_a_change_that_added_a_section_takes_it_out_again():
    old = {"views": [_sectioned({"cards": [B]})]}
    new = {"views": [_sectioned({"column_span": 2, "cards": [C]}, {"cards": [B]})]}
    plan = analyze.plan_undo(old, new, new)
    assert plan.blocked is None
    assert restore.apply_undo(new, plan) == old
```

Am Ende der Datei ergänzen:

```python
def test_the_test_2_swap_is_one_step_and_exact():
    heading = {"type": "heading", "heading": "Neuer Abschnitt"}
    first = {"type": "grid", "cards": [heading, _md("noon")]}
    second = {"type": "grid", "cards": [_md("person"), _md("sun")]}
    before = {"views": [_sectioned(first, second, title="A2")]}
    after = {"views": [_sectioned(second, first, title="A2")]}
    plan = analyze.plan_undo(before, after, after)
    assert plan.blocked is None
    assert [step.kind for step in plan.steps] == ["sections_list"]
    assert restore.apply_undo(after, plan) == before


def test_a_section_setting_alone_is_undoable():
    before = {"views": [_sectioned(_sec("a", column_span=1))]}
    after = {"views": [_sectioned(_sec("a", column_span=2))]}
    plan = analyze.plan_undo(before, after, after)
    assert plan.blocked is None
    assert restore.apply_undo(after, plan) == before


def test_sections_and_single_cards_of_one_view_refuse_together():
    before = {"views": [_sectioned(_sec("a"), _sec("b"), _sec("c"))]}
    after = {"views": [_sectioned(_sec("b"), _sec("a"), _sec("c", "c2"))]}
    plan = analyze.plan_undo(before, after, after)
    assert plan.blocked == analyze._SECTIONS_AND_CARDS_REFUSAL


def test_a_section_swap_in_a_pathless_view_is_undone():
    before = {"views": [_sectioned(_sec("a"), _sec("b"), path=None)]}
    after = {"views": [_sectioned(_sec("b"), _sec("a"), path=None)]}
    plan = analyze.plan_undo(before, after, after)
    assert plan.blocked is None
    assert restore.apply_undo(after, plan) == before


def test_two_sections_deleted_at_once_refuse_the_undo():
    before, after = _row("abc"), _row("a")
    plan = analyze.plan_undo(before, after, after)
    assert plan.blocked is not None and "cannot account for" in plan.blocked


def test_a_section_moved_and_edited_in_one_save_refuses_the_undo():
    before = {"views": [_sectioned(_sec("a"), _sec("b"))]}
    after = {"views": [_sectioned(_sec("b"), _sec("a", "z"))]}
    plan = analyze.plan_undo(before, after, after)
    assert plan.blocked is not None and "cannot account for" in plan.blocked


def test_a_section_setting_goes_back_from_true_to_1():
    """`==` calls them equal; the written state must not (#28)."""
    before = {"views": [_sectioned(_sec("a", column_span=1))]}
    after = {"views": [_sectioned(_sec("a", column_span=True))]}
    plan = analyze.plan_undo(before, after, after)
    assert plan.blocked is None
    result = restore.apply_undo(after, plan)
    assert json.dumps(result, sort_keys=True) == json.dumps(before, sort_keys=True)


def test_a_planned_sections_step_refuses_a_state_changed_after_planning():
    before, after = _row("ab"), _row("ba")
    plan = analyze.plan_undo(before, after, after)
    changed = {"views": [_sectioned(_sec("b", "b2"), _sec("a"))]}
    with pytest.raises(LookupError):
        restore.apply_undo(changed, plan)


def test_a_section_swap_in_one_view_leaves_cards_in_another_alone():
    home_before = _sectioned(_sec("a"), _sec("b"))
    home_after = _sectioned(_sec("b"), _sec("a"))
    other_before = {"path": "other", "cards": [A]}
    other_after = {"path": "other", "cards": [A, B]}
    before = {"views": [home_before, other_before]}
    after = {"views": [home_after, other_after]}
    plan = analyze.plan_undo(before, after, after)
    assert plan.blocked is None
    assert restore.apply_undo(after, plan) == before
```

- [ ] **Step 2: Rot prüfen**

Run: `python3 -m pytest tests/test_analyze.py -k "taken_out_again or settings_and_all or test_2_swap or setting_alone or refuse_together or pathless_view_is_undone or leaves_cards_in_another or refuse_the_undo or from_true_to_1 or changed_after_planning" -v`
Expected: FAIL (noch `_SECTIONS_REBUILT_REFUSAL`). Ausnahme: `test_a_planned_sections_step_refuses_a_state_changed_after_planning` ist schon jetzt grün, weil `apply_undo` einen verweigerten Plan ebenfalls mit `LookupError` beantwortet. Er ist ein Wächter für den Zustand nach diesem Task und muss grün bleiben.

- [ ] **Step 3: Umsetzen**

`_section_drift` ersetzen durch:

```python
def _section_drift(new_views: dict, now_views: dict) -> set:
    """The views whose sections moved since the change - their inserts park.

    The change left the sections of these views as they were, or undoes
    its own section changes in one step of its own (`_plan_sections`);
    either way they have moved since. A card can still be taken out
    exactly - it is found by its fingerprint - but where one goes back in
    cannot be proven any more, so an insertion there is parked in the
    view's own `cards:` (decision 26, GitHub #30).

    Per view, not per dashboard: a section moved in one view says nothing
    about an index in another.
    """
    return {
        key
        for key in set(new_views) & set(now_views)
        if not _same_marks(now_views[key], new_views[key])
    }
```

`_SECTIONS_REBUILT_REFUSAL` löschen. An seiner Stelle:

```python
_SECTIONS_AND_CARDS_REFUSAL = (
    "this change moved sections of a view and also changed single cards "
    "in it, so an exact undo cannot put both back at once"
)
```

In `plan_undo` die Zeilen

```python
    rebuilt, shifted = _section_drift(old_views, new_views, now_views)
    if rebuilt:
        return UndoPlan(blocked=_SECTIONS_REBUILT_REFUSAL)
```

ersetzen durch:

```python
    shifted = _section_drift(new_views, now_views)
    # A view whose sections the change rearranged is put back in one step
    # of its own (GitHub #31) - or refused, and then before anything else.
    now_index = {key: index for index, (key, _) in enumerate(_views_by_key(current))}
    section_steps: list[UndoStep] = []
    for key in sorted(matching.sections.views(), key=str):
        planned = _plan_sections(
            key,
            old_views[key],
            new_views[key],
            now_views.get(key),
            now_index.get(key, -1),
            matching.sections,
        )
        if isinstance(planned, str):
            return UndoPlan(blocked=planned)
        if planned is not None:
            section_steps.append(planned)
```

Im Kommentar über der frühen Bedingung den Absatz ergänzen: `A section moved or re-set is a real alteration too, with no card event of its own since its cards follow it (GitHub #31).`

`for new_slot in matching.added:` → `for new_slot in matching.loose_added():`; `for old_slot in matching.removed` in `removed_card_marks` → `for old_slot in matching.loose_removed()`. Die Karten einer ganz hinzugekommenen oder verschwundenen Section gehören zum `sections_list`-Schritt, nicht zu eigenen Karten-Schritten.

Das abschließende `return UndoPlan(blocked=None, steps=tuple(steps))` ersetzen durch:

```python
    # One step writes a view's whole row of sections; a card step in the
    # same view would write into a row that step replaces.
    rewritten = {step.view_path or ("#", step.view_index) for step in section_steps}
    if any(
        step.kind == "card" and (step.view_path or ("#", step.view_index)) in rewritten
        for step in steps
    ):
        return UndoPlan(blocked=_SECTIONS_AND_CARDS_REFUSAL)
    steps.extend(section_steps)
    return UndoPlan(blocked=None, steps=tuple(steps))
```

Im Docstring von `_section_marks` den letzten Satzteil (»… writing a state that never existed.«) stehen lassen und anhängen: `Compared through `_same_marks`, strictly, since vorhaben O.`

- [ ] **Step 4: Grün prüfen**

Run: derselbe Aufruf wie in Step 2 → PASS. `grep -rn "_SECTIONS_REBUILT_REFUSAL\|rearranged the sections" custom_components/ tests/` → keine Ausgabe. `python3 -m pytest tests/ -v` → 0 failed.

- [ ] **Step 5: Commit (nach Go des Nutzers)**

```bash
git add custom_components/dashboard_history/analyze.py tests/test_analyze.py
git commit -m "Undo section changes as one step" -m "A change that swapped, moved, added, deleted or re-set sections is now
undone by writing the view's whole row back, instead of being refused
as rebuilt sections. A swap of two untitled sections with different
settings - the case from GitHub #31 - is exact now. A view that would
need both that step and single card steps is refused.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Put-back-Anker parkt bei weggezogenem Nachbarn (O3)

**Files:**
- Modify: `custom_components/dashboard_history/analyze.py` (`_SectionAnchor`, `_section_anchor`, `find_removed`)
- Modify: `custom_components/dashboard_history/restore.py` (`_anchored_index`, neu `_departed_is_ambiguous`)
- Test: `tests/test_restore.py`

**Interfaces:**
- Consumes: `Matching.same_place` (Task 3).
- Produces: `_SectionAnchor.departed: tuple` (fünftes Feld, Vorgabe `()`); `_section_anchor(view, location, index, left, departed=frozenset())`; `restore._departed_is_ambiguous(sections: list, at: int, settings: Any, departed: tuple) -> bool`.

**Akzeptanz:** Der Lückenfall aus Spec §5 parkt, die beiden Gegenproben (andere Einstellungen ohne Doppelung parkt nicht, Doppelung parkt) verhalten sich wie beschrieben; alle bestehenden Anker-Tests bleiben unverändert grün, ausdrücklich auch `test_a_card_moved_away_in_the_same_save_does_not_park`; Suite 0 failed.

- [ ] **Step 1: Tests schreiben**

Am Ende von `tests/test_restore.py`:

```python
# -- a neighbour that left for an alike section (spec O, section 5) --------


def test_a_neighbour_now_in_an_alike_section_parks_the_card():
    """A swap since and a drag across leave the same bytes; neither is guessed."""
    old = _sections({"cards": [A, B]}, {"cards": []})
    new = _sections({"cards": []}, {"cards": [B]})
    item = next(i for i in analyze.find_removed(old, new) if i.payload == A)
    assert restore.parks(new, item) is True


def test_a_neighbour_now_in_a_differently_set_section_does_not_park():
    old = _sections({"cards": [A, B]}, {"column_span": 2, "cards": []})
    new = _sections({"cards": []}, {"column_span": 2, "cards": [B]})
    item = next(i for i in analyze.find_removed(old, new) if i.payload == A)
    assert restore.parks(new, item) is False


def test_a_neighbour_standing_twice_now_parks_the_card():
    old = _sections(
        {"cards": [A, B]},
        {"column_span": 2, "cards": []},
        {"column_span": 3, "cards": [B]},
    )
    new = _sections(
        {"cards": []},
        {"column_span": 2, "cards": [B]},
        {"column_span": 3, "cards": [B]},
    )
    item = next(i for i in analyze.find_removed(old, new) if i.payload == A)
    assert restore.parks(new, item) is True
```

- [ ] **Step 2: Rot prüfen**

Run: `python3 -m pytest tests/test_restore.py -k "neighbour_now or neighbour_standing" -v`
Expected: der erste und der dritte Test FAIL (`parks` ist `False`), der zweite PASS.

- [ ] **Step 3: Umsetzen – `analyze.py`**

`_SectionAnchor` um ein fünftes Feld ergänzen, Docstring »four positions« → »five positions«:

```python
    departed: tuple = ()  # its neighbours that left for another list in the view since
```

`_section_anchor` bekommt den Parameter `departed: set = frozenset()` hinter `left`, im Docstring ein Absatz:

```python
    `departed` are the neighbours that left for another list of the same
    view: `restore._anchored_index` parks where one of them now stands in
    a section alike this one, because a swap and a drag across are then
    the same bytes (spec O, section 5).
```

Den Rumpf ab `if len(location) < 2 or location[0] != "sections":` ersetzen durch:

```python
    if len(location) < 2 or location[0] != "sections":
        return None
    sections = view.get("sections") or []
    at = location[1]
    settings: dict | None = None
    survivors: list = []
    away: list = []
    before = 0
    if isinstance(at, int) and 0 <= at < len(sections):
        section = sections[at]
        if isinstance(section, dict):
            settings = _section_marks(view)[at]
            for position, card in enumerate(section.get("cards") or []):
                if (location, position) in left:
                    if (location, position) in departed:
                        away.append(card)
                    continue
                survivors.append(card)
                if position < index:
                    before += 1
    return _SectionAnchor(len(sections), settings, tuple(survivors), before, tuple(away))
```

In `find_removed` die Schleife über `matching.moved` erweitern:

```python
    departed_by_view: dict[int, set] = {}
    for was, now in matching.moved:
        if not matching.same_place(was, now):
            away_by_view.setdefault(was.view_index, set()).add((was.location, was.index))
            if now.view_key == was.view_key:
                departed_by_view.setdefault(was.view_index, set()).add((was.location, was.index))
```

und den Anker-Aufruf zu `anchor=_section_anchor(old_view, slot.location, slot.index, left, departed_by_view.get(view_index, set()))`.

- [ ] **Step 4: Umsetzen – `restore.py`**

In `_anchored_index` `count, settings, survivors, before = item.anchor` → `count, settings, survivors, before, departed = item.anchor`. Direkt hinter der Einstellungsprüfung (`if not _same_value(own, settings): return None`):

```python
    # Only where no survivor is left to recognise the section by: then
    # "empty" is all the anchor has, and a swap and a drag across cannot
    # be told apart. With survivors, they already name the section.
    if not survivors and _departed_is_ambiguous(sections, at, settings, departed):
        return None
```

Die Einschränkung auf `not survivors` ist nötig, sonst würde der bestehende Test `test_a_card_moved_away_in_the_same_save_does_not_park` (Vorhaben L) rot. Dort steht A als Überlebender noch neben der gelöschten Karte und beweist die Section, und C ist im selben Save in die andere, gleich eingestellte Section gewandert (Plan-Review 2026-09-26, Gemini).

Hinter `_anchored_index`:

```python
def _departed_is_ambiguous(sections: list, at: int, settings: Any, departed: tuple) -> bool:
    """Whether a neighbour that left makes a swap and a drag look the same.

    Two sections alike in every setting, the card's neighbour now in the
    other one: "the sections swapped" and "the neighbour was dragged
    across" are then the same bytes, and where the card belongs is not in
    them (spec O, section 5). A neighbour that stands more than once now
    says as little - which of them left is not in the bytes either.
    Either way the card is parked, never guessed.
    """
    for card in departed:
        holders = [
            j
            for j, section in enumerate(sections)
            if isinstance(section, dict)
            for other in (section.get("cards") or [])
            if _same_value(other, card)
        ]
        if len(holders) > 1:
            return True
        if holders and holders[0] != at:
            own = {k: v for k, v in sections[holders[0]].items() if k != "cards"}
            if _same_value(own, settings):
                return True
    return False
```

- [ ] **Step 5: Grün prüfen**

Run: derselbe Aufruf wie in Step 2 → alle drei PASS. `python3 -m pytest tests/ -v` → 0 failed.

- [ ] **Step 6: Commit (nach Go des Nutzers)**

```bash
git add custom_components/dashboard_history/analyze.py custom_components/dashboard_history/restore.py tests/test_restore.py
git commit -m "Park when a neighbour left for an alike section" -m "Two sections alike in every setting, and the card's neighbour now in
the other one: a swap since and a drag across leave the same bytes, so
put back filed the card by its old index. It parks the card instead,
and also when that neighbour now stands twice. The residual gap named
in vorhaben L. GitHub #31.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Laufende Instanz und Dokumentation

**Files:**
- Modify: `tests/integration/run_checks.py`
- Modify: `docs/limitations.md`, `docs/how-it-works.md`, `docs/superpowers/status.md`, `docs/superpowers/specs/2026-08-30-dashboard-history-design.md`

**Akzeptanz:** `python3 tests/integration/run_checks.py` meldet alle Prüfungen grün, auch die bestehenden in `run_sections` und `run_parking`; die Doku widerspricht an keiner der unten genannten Stellen mehr dem neuen Verhalten; Suite 0 failed.

- [ ] **Step 1: `run_section_moves`**

Hinter `run_badges` einfügen und im Hauptblock direkt nach `asyncio.run(run_badges(access))` mit `asyncio.run(run_section_moves(access))` aufrufen:

```python
async def run_section_moves(access: str) -> None:
    """Sections swapped or added whole, named and undone as one thing (GitHub #31)."""
    key = "dh-section-moves"
    heading = {"type": "heading", "heading": "Oben"}
    a = {"type": "markdown", "content": "# A"}
    b = {"type": "markdown", "content": "# B"}
    c = {"type": "markdown", "content": "# C"}

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

        async def undo(revision: str) -> dict:
            rows = (
                await socket.call("dashboard_history/history", dashboard=key, limit=1)
            )["changes"]
            asked = await socket.call(
                "dashboard_history/undo_change", dashboard=key, revision=revision
            )
            if asked.get("available") is True:
                await socket.call(
                    "dashboard_history/undo_change",
                    dashboard=key,
                    revision=revision,
                    confirm=True,
                    expected_parked=[],
                )
                # The undo is a save of its own; the next `save` must not
                # mistake its row for the one it waits for.
                await _wait_for_new_state(socket, key, rows[0]["revision"], RECORDING_WAIT)
            return asked

        def standing(live: dict) -> list:
            return [
                [card.get("heading") or card.get("content") for card in section["cards"]]
                for section in live["views"][0]["sections"]
            ]

        await save(sections([heading, a], [b]))
        swapped = (await save(sections([b], [heading, a])))[0]
        check(
            "a swap of two sections is one move",
            swapped["message"].endswith("1 section moved"),
            swapped["message"],
        )
        asked = await undo(swapped["revision"])
        check("and undoable", asked.get("available") is True, asked.get("reason", ""))
        live = await socket.call("lovelace/config", url_path=key)
        check(
            "and the sections stand as before",
            standing(live) == [["Oben", "# A"], ["# B"]],
            f"{standing(live)}",
        )

        grown = (
            await save(sections([heading, a], [b], [{"type": "heading", "heading": "Neu"}, c]))
        )[0]
        check(
            "an added section is one line",
            grown["message"].endswith("1 section added"),
            grown["message"],
        )
        asked = await undo(grown["revision"])
        check(
            "and undoing it is available", asked.get("available") is True, asked.get("reason", "")
        )
        live = await socket.call("lovelace/config", url_path=key)
        check(
            "and takes it out again",
            standing(live) == [["Oben", "# A"], ["# B"]],
            f"{standing(live)}",
        )

        # Named, never by prefix: this instance holds other dh-* boards.
        listed = (await socket.call("lovelace/dashboards/list")) or []
        mine = next((e for e in listed if e.get("url_path") == key), None)
        if mine is not None:
            await socket.call("lovelace/dashboards/delete", dashboard_id=mine["id"])
```

- [ ] **Step 2: Live prüfen**

Den Container neu starten, damit HA den neuen Code lädt, danach **15 Sekunden warten, nicht pollen** (IP-Sperre, siehe `CLAUDE.md`):

```bash
docker compose -f docker/compose.yaml restart
sleep 15
python3 tests/integration/run_checks.py
```

Expected: alle Prüfungen grün. Schlägt eine bestehende Prüfung fehl, die einen Section-Tausch als Verweigerung erwartet, ist das gewolltes neues Verhalten – anhalten und dem Nutzer melden, nicht selbst umschreiben.

- [ ] **Step 3: `docs/limitations.md`**

In der Übersichtstabelle oben die Zeilen `| **Untitled sections swapped**, their settings differ …` und `| **Untitled sections swapped**, settings otherwise identical …` ersetzen durch:

```markdown
| **Sections swapped or moved** as whole blocks, nothing else changed | `1 section moved` — one line per section, named by its heading | **Exact** — the whole row of sections is written back in one step, settings included | Refuses (nothing missing) | **Works** |
| **Section added or deleted** whole (a deleted one with at least one card) | `1 section added` / `1 section removed` | **Exact** while that section and the sections around it are unchanged since | Deleted: offered as one item | **Works** |
| **Section moved and edited in the same save** | Its cards, one line each | **Refuses** — nothing proves it is the same section | Refuses | **Works** |
```

In der Tabelle »What you did | Why it refuses« die Zeilen `Added a section, **in the change being undone**`, `Reordered sections **whose settings tell them apart** …` und `Renamed a section` ersetzen durch die eine Zeile:

```markdown
| Added, deleted or reordered sections in the change being undone, **and** the sections around them were added, deleted or reordered since | The row of sections is written back in one piece, in the order it had before the change; that order only means the same thing while the sections around it still stand as the change left them. Card edits in other sections since do not refuse. |
```

Im Abschnitt `### 3. Sections in detail` den Aufzählungspunkt `- **Reordering untitled sections:** …` (ein Absatz) ersetzen durch:

```markdown
- **Reordering sections:** Since <Datum> sections are matched as whole blocks before their cards ([issue #31](https://github.com/PPP01/ha-dashboard-history/issues/31)). A section swapped, moved, added or deleted in one save reads as one line — *section "Heizung" was moved* — and *Undo this change* writes the whole row of sections back in one step, own settings included. It refuses where it cannot prove that: a section moved **and** edited in the same save, two sections deleted at once, or the sections around it rearranged since.
```

Im Anhang den Absatz, der mit `**What is still open from the same finding.**` beginnt, bis vor `The original case, reordering untitled sections **together with** a` ersetzen durch:

```markdown
**Closed on <Datum>.** Sections are now matched as units
([issue #31](https://github.com/PPP01/ha-dashboard-history/issues/31)):
a whole-section swap reads as one move and is undone as one, settings
included. What remains is what no matching without an identity chain
can close: a section moved and edited in the same save is refused
rather than guessed.
```

Im ersten Aufzählungspunkt der Liste darunter (`- **A section alike in every setting stands at the old index since, …`) vor dem Satz `Needs sections that differ in nothing but their cards` einfügen:

```markdown
  Since <Datum> *Put back* parks instead where a neighbour of the card
  now stands in another section alike in every setting — the one shape
  of this in which a swap and a drag across leave the same bytes.
```

- [ ] **Step 4: `docs/how-it-works.md`**

Im Absatz, der mit `- **The one safety check that exists for this` beginnt, den Satz ab `What remains: two sections that agree on **every** setting` bis zum Satzende `either way.` ersetzen durch: `Since <Datum> sections are also matched as whole blocks before their cards, so a swap reads as one move and is undone as one ([issue #31](https://github.com/PPP01/ha-dashboard-history/issues/31)).`

Im Absatz darunter `A change that rearranged the sections itself is still refused ([GitHub issue #30](https://github.com/PPP01/ha-dashboard-history/issues/30)).` ersetzen durch: `A change that rearranged the sections itself is undone as a whole row since <Datum> ([issue #31](https://github.com/PPP01/ha-dashboard-history/issues/31)); parking is for sections rearranged after the change ([issue #30](https://github.com/PPP01/ha-dashboard-history/issues/30)).`

- [ ] **Step 5: Journal**

`docs/superpowers/status.md`, Tabelle, hinter der Zeile N:

```markdown
| O | Sections als Einheit – Zuordnung von außen nach innen, ein Undo-Schritt je Ansicht (Issue #31) | Erledigt (<Datum>) | `specs/2026-09-25-sections-als-einheit-design.md`, `plans/2026-09-26-sections-als-einheit.md` |
```

Hinter dem Eintrag zu #30 (»Umgesetzt am 2026-09-25 … Vorhaben L«):

```markdown
- **Umgesetzt am <Datum>** (GitHub-Issue [#31](https://github.com/PPP01/ha-dashboard-history/issues/31), Vorhaben O): Sections werden vor ihren Karten als ganze Blöcke zugeordnet (bytegleich am selben Index, bytegleich anderswo, gleiche Karten unter anderen Einstellungen, gleiche Einstellungen über anderen Karten). Ein Tausch ist eine Bewegung, eine hinzugekommene oder verschwundene Section eine Zeile, eine geänderte Section-Einstellung wird benannt wie eine Ansichtseinstellung. Das Undo schreibt die ganze Section-Liste einer Ansicht in einem Schritt (`sections_list`) in der Reihenfolge von vor der Änderung zurück; es verweigert jeden unerklärten Rest, seither umsortierte Nachbarn und seither geänderte beteiligte Sections, und ebenso eine Ansicht, die daneben Karten-Schritte bräuchte. `_SECTIONS_REBUILT_REFUSAL` ist entfallen. Put back parkt zusätzlich, wo ein weggezogener Nachbar in einer gleich eingestellten Section steht – die Restlücke aus L. Vier Review-Runden zur Spec, Details dort (Entscheidungen 6–13).
```

Haupt-Spec, Abschnitt »Reihenfolge der Vorhaben«, hinter dem Punkt **N — Badges**:

```markdown
- **O — Sections als Einheit.** *(Issue [#31](https://github.com/PPP01/ha-dashboard-history/issues/31).)* `specs/2026-09-25-sections-als-einheit-design.md`. Sections werden vor ihren Karten als ganze Blöcke zugeordnet; ein Tausch ist eine Bewegung, und das Undo schreibt die Section-Liste einer Ansicht in einem Schritt zurück.
```

`<Datum>` ist überall das Datum des Tages, an dem dieser Task ausgeführt wird (`date +%F`, Format `YYYY-MM-DD`). Liegt der Commit später an einem anderen Tag, zieht der Nutzer das Datum beim Commit nach.

- [ ] **Step 6: Commit (nach Go des Nutzers)**

```bash
git add tests/integration/run_checks.py docs/limitations.md docs/how-it-works.md docs/superpowers/status.md docs/superpowers/specs/2026-08-30-dashboard-history-design.md
git commit -m "Check section moves live and document them" -m "A running Home Assistant now proves that a section swap is recorded as
one move and that undoing it, or undoing an added section, writes the
row back as it was. The limitations, how-it-works and the journal
describe sections matched as units. GitHub #31.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Self-review notes

**Spec-Abdeckung:** §1 Zuordnung → Tasks 2/3; strenge `_section_marks` → Task 1; §2 Übersetzung und Karten ganzer Sections → Task 3; §3 Anzeige → Task 4; §4 atomarer Schritt, Merge, alle Beweise, Mischungs-Verweigerung, Wegfall von `_SECTIONS_REBUILT_REFUSAL` → Tasks 5–7; §5 Anker → Task 8; Randfall-Tabelle: jede Zeile hat einen Test in Task 4, 6, 7 oder 8; Test-Plan »Laufende Instanz« → Task 9; Dokumentation → Task 9.

**Auslegungen, die die Spec offen ließ – im Plan-Review bitte gezielt prüfen:**

1. **Leere hinzugekommene Section gilt als bewiesen** (`_whole(…, empty_counts=True)`), eine leere verschwundene nicht. Die Spec sagt in §1 »symmetrisch«, schließt aber nur für »verschwunden« leere Sections ausdrücklich aus, und ihre Randfall-Tabelle erwartet für eine von HA angelegte leere Grid-Section »1 section added«. Gegen Raten abgesichert: Die Ansicht muss um genau eine Section gewachsen sein, und es darf genau ein solcher Rest übrig sein. Das Undo verlangt zusätzlich, dass die Section heute genau einmal dasteht.
2. **Beweis der Überlebenden:** Die Spec verlangt eine unveränderte Überlebenden-Teilfolge. Umgesetzt ist das als dieselben vier Durchgänge zwischen `after` und heute, ohne Rest und ohne Bewegung (Task 6, Beweis 4). Dadurch liegen die Listen Index für Index nebeneinander, und Kartenedits seither in anderen Sections sind erlaubt, wie Spec-Entscheidung 3 es vorsieht.
3. **Tie-Break der längsten Teilfolge:** lexikografisch über die alten Indizes, Element für Element. Das erfüllt die Spec-Regel »kleinster alter Index des ersten Elements« und löst weitere Gleichstände vollständig auf. Die Regel »dann kleinster neuer Index« wird nie gebraucht, weil die Paarung eine Bijektion ist.
4. **Wortlaut:** `section "X" was removed` (wie Spec §3, nicht »deleted« wie bei Karten); Einstellungen als `section "X": the setting "column_span" was changed from 1 to 2` (Spec: »dieselbe Form wie Vorhaben M«); die Mischungs-Verweigerung hat in der Spec keinen Wortlaut und steht in `_SECTIONS_AND_CARDS_REFUSAL`.
5. **Konvertierte Ansichten** werden von der Section-Zuordnung übersprungen (Global Constraints). Ohne das bekäme `test_a_view_converted_to_sections_is_explained_as_its_own_event` die Zeile »section 1 was added« dazu.
6. **Karten in nicht gepaarten Sections** behalten ihren echten Index, wie Spec §1 es verlangt, stellen sich in Durchgang 1 und 2 aber hinten an (`_unpaired`). Ohne diese Reihenfolge würde bei einer gelöschten Section, deren Nachfolgerin eine identische Karte trägt, die gelöschte Section der nachgerückten deren Karte am selben Index wegnehmen, und der Beweis »ganz verschwunden« schlüge fehl. *(Nach dem Plan-Review vom 2026-09-26 geändert: Die erste Fassung gab solchen Karten einen künstlichen Platz, was Spec §1 widersprach – Terra, Kritisch 1. Terras Vorschlag »einfach der echte Index« allein hätte aber den eben beschriebenen Löschfall gebrochen, daher die Reihenfolge.)*
7. **Namen in Karten-Bewegungen:** `_section_name` folgt der gemeinsamen Namensregel. »was moved to another section« wird dadurch zu »was moved to section 2«. Kein bestehender Test hält den alten Wortlaut fest.

8. **Spec-Relikte aus der Zeit vor Entscheidung 11:** Die Randfall-Zeile »Beide Nachbarn einer einzusetzenden Section seither geändert« und der Test-Plan-Punkt »nur der vordere Nachbar geändert, der hintere steht noch: geht durch« stammen aus der Einzel-Index-Fassung der Spec. Mit dem atomaren Schritt gibt es keine Nachbarsuche mehr; an ihre Stelle tritt die Überlebenden-Probe (Task 6, Beweis 5). Die Spec wurde am 2026-09-26 entsprechend nachgezogen.
9. **Mehr als ein seither bearbeiteter Überlebender verweigert** (Task 6, Beweis 5). Das ist strenger als der Wortlaut von Spec-Entscheidung 3 (»alle anderen Sections dürfen sich seither beliebig geändert haben«), aber die einzige Fassung, die nicht per Index rät (Astra, Plan-Review 2026-09-26). Eine Kartenänderung seither in *einer* anderen Section geht weiter durch. Die Spec wurde am 2026-09-26 entsprechend nachgezogen (Entscheidung 14).

## Plan-Review vom 2026-09-26 und was daraus wurde

Drei Prüfungen: Codex (Terra, breit), Codex (Astra, eine Frage) und Gemini mit dem Terra-Auftrag. Geminis Bericht beschreibt an mehreren Stellen Code, der weder im Plan noch im Repository steht (`_departed_target`, `_strip_card_settings`, `_KNOWN_KINDS`, `bisect_left`, eine andere Task-Aufteilung). Seine Urteile über »saubere Tasks« wurden deshalb nicht übernommen, nur seine am Code nachgeprüften Befunde.

| Befund | Quelle | Entscheidung |
|---|---|---|
| Überlebenden-Probe akzeptiert per Durchgang 4 zwei seither vertauschte *und* bearbeitete Sections; Merge schreibt still eine falsche Reihenfolge | Astra (ausgeführt) | **Angenommen.** Höchstens ein Paar aus Durchgang 3/4 seither (Task 6, Beweis 5), Test `test_two_survivors_edited_and_swapped_since_refuse` |
| Künstlicher Platz für Karten nicht gepaarter Sections widerspricht Spec §1 | Terra, Kritisch 1 | **Angenommen, anders gelöst:** echter Index, aber gepaarte Sections zuerst (Auslegung 6); Wächter- und Löschfall-Test in Task 3 |
| `sections` fehlend oder `null`: normalisiertes `expect`/`payload` passt nicht zum Rohvergleich | Terra, Kritisch 2 | **Angenommen, als Verweigerung** (Task 6, Beweis 4) statt Rohwert-Durchreichen: Ein fehlender Schlüssel ließe sich in `restore` nur mit einem neuen Abwesenheits-Marker wiederherstellen, für einen in der Praxis handeditierten Randfall |
| Fehlende Tests über den vollen `plan_undo`-Pfad | Terra, Hoch 1 | **Angenommen:** vier Tests in Task 7; die Nachbar-Proben sind Spec-Relikte (Auslegung 8) |
| `==` statt strenger Gleichheit in `_departed_is_ambiguous` | Terra, Hoch 2 | **Angenommen:** `_same_value`. Kein eigener Test: Eine im Wert `1`/`True` geänderte Karte ist nicht »weggezogen«, sondern entfernt, sie erreicht diesen Pfad gar nicht |
| Wortlaut der Section-Einstellungen weicht vom Spec-Beispiel ab | Terra, Mittel | **Plan-Wortlaut beibehalten** (Form aus Vorhaben M, wie Spec §3 selbst verlangt); das Spec-Beispiel wurde angeglichen |
| `<Datum>` für Gemini nicht bestimmbar | Terra, Mittel | **Angenommen:** Datum der Ausführung |
| Bestehender L-Test bricht in Task 8 | Gemini, Finding 1 | **Angenommen.** Ursache war eine zu breite Regel: Mehrdeutigkeit nur ohne Überlebende (Task 8, Step 4) |
| `match_sections` fehlt als öffentlicher Name | Gemini, Finding 2 | **Angenommen** (Task 3) |
| Testfilter in Task 2 unvollständig | Gemini, Finding 3 | **Angenommen**, dazu Umsetzer-Regel 3 (Filter sind nur Abkürzung) |
| Nachbar-Relikt in der Spec | Gemini, Finding 4 | **Angenommen** (Auslegung 8) |
| doppelter Artikel in der Mehrdeutigkeits-Meldung | Gemini, Finding 5 | **Angenommen** |

**Platzhalter-Suche:** `<Datum>` ist das Commit-Datum. Die Markierung `<bisheriger Docstring unverändert>` in Task 3 ist ausdrücklich als »wörtlich übernehmen« erklärt. Sonst keine offenen Stellen.

**Typen:** `SectionSlot.index`/`SectionPair.old|new|how`, `Matching.sections/translate/same_place/loose_*`, `_plan_sections(...) -> UndoStep | str | None` und `_SectionAnchor.departed` sind in Tasks 2, 3, 6 und 8 definiert und werden überall so verwendet.
