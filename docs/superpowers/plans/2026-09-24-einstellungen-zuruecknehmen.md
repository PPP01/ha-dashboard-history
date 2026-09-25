# Benannte Einstellungen zurücknehmen – Umsetzungsplan (Vorhaben M, Issue #28)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eine Änderung, die nur eine benannte Einstellung des Dashboards oder einer Ansicht anfasst (`strategy.show_clock_card`, `icon`, `visible`, …), wird in der Erklärung genannt, in der Verlaufszeile gezählt und ist gezielt zurücknehmbar – über eine einzige Gleichheitsprüfung an ihrer Adresse.

**Architecture:** `analyze.setting_changes(old, new)` liefert je Einstellungsänderung einen `SettingChange` (Behälter, Schlüsselpfad, alter und neuer Wert, »nicht vorhanden« als eigener Marker). Drei Verbraucher: `_explain` (Einträge, eigene Dashboard-Gruppe mit `scope="dashboard"`), `summarize`/`change_message` (Teil `N settings changed`) und `plan_undo` (Schritte `kind="dashboard_setting"`/`"view_setting"` mit `action="set"`/`"unset"`). `restore.apply_undo` wendet diese Schritte vor allen anderen an.

**Tech Stack:** Python 3 (HA-freie Kernmodule, pytest), `operations.py` (nur `_as_dict`), `panel/render.js` (Node-Test), Testcontainer für `run_checks.py`.

**Spec:** `docs/superpowers/specs/2026-09-24-einstellungen-zuruecknehmen-design.md`; dazu Entscheidung 11 und 15 der Haupt-Spec. **Voraussetzung: Vorhaben L ist umgesetzt** (`docs/superpowers/plans/2026-09-24-importierte-karten.md`) – dieser Plan setzt `_section_drift` statt `_sections_lie` voraus. Die Festlegungen im Abschnitt »Entscheidungen« der Spec hat der Nutzer am 2026-09-24 unverändert bestätigt.

## Global Constraints

- `analyze.py`, `restore.py` ohne `import homeassistant`; `restore.py` ohne Laufzeitimport von `analyze`.
- Ausgeschlossen: an der Wurzel `views`; an einer Ansicht `cards`, `sections`, `badges`, `path`, `type`. Section-Einstellungen und `meta/` sind nicht Teil dieses Vorhabens.
- Abstieg nur, wo **beide** Seiten ein Dict sind; sonst ist der Wert ein Blatt.
- `null` und »nicht vorhanden« werden nie verwechselt.
- `python3 -m pytest tests/ -v` nach jedem Task, nur »0 failed« zählt.
- Englisch in Code und UI, Deutsch im Journal. Commit-Format wie in `CLAUDE.md`, Verweis auf `#28`. **Committet wird erst nach ausdrücklichem Go des Nutzers.**

## Review Focus

1. **Zwei Änderungen am selben Block** (`strategy.a` in Änderung 1, `strategy.b` in Änderung 2): Rücknahme von 1 bleibt exakt. Test in Task 3.
2. **Block seither ganz entfernt:** Verweigerung, nie ein halber Block. Test in Task 3.
3. **Wert `1` gegen `true`, `0` gegen `false`:** Python hält sie für gleich; als Einstellung sind sie verschieden. Erwartung: als Änderung erkannt – und zwar **im ganzen Aufrufpfad**, nicht nur in der Differenz: `setting_changes` (Task 1), die erneute Prüfung in `_apply_setting` (Task 4), `change_message` und die beiden Zustandsvergleiche in `operations.async_undo_change` (Task 5). An jeder dieser Stellen stand oder stünde sonst ein `==`, das den Unterschied wieder verschluckt (Review 2026-09-24, W2).
4. **Einstellung einer pfadlosen Ansicht neben einer entfernten Nachbaransicht:** Einstellungsschritte laufen vor dem Entfernen von Ansichten. Das ist harmlos, aber durch keinen Test als notwendig belegt: Eine Ansicht *vor* einer pfadlosen kann nie im selben Undo entfernt werden, weil sich dann deren Schlüssel ändert und `_positions_lie` vorher verweigert. Der Test in Task 4 belegt nur, dass die Reihenfolge nichts kaputt macht.
5. **Riesiger Block** (`button_card_templates` mit vielen Vorlagen): je Vorlage eine Zeile, gedeckelt durch `_ENTRY_LIMIT`. Test in Task 2.

---

## Files touched

| Datei | Rolle |
|---|---|
| `custom_components/dashboard_history/analyze.py` | `SettingChange`, `setting_changes`, `_same`, `_ABSENT`; `ViewChanges.scope`; Einträge in `_explain`; `Summary.settings`, `change_message`, `_COUNT`; `UndoStep.expect_absent`; Einstellungsschritte in `plan_undo` |
| `custom_components/dashboard_history/restore.py` | `_apply_setting`; Aufruf in `apply_undo` vor allen anderen Schritten |
| `custom_components/dashboard_history/operations.py` | `_as_dict` reicht `scope` durch; `_same_state` für die beiden Zustandsvergleiche in `async_undo_change` |
| `custom_components/dashboard_history/panel/render.js` | Überschrift »On the dashboard itself« |
| `tests/test_analyze.py`, `tests/test_restore.py`, `tests/test_panel_behaviour.py` | neue Tests |
| `tests/integration/run_checks.py` | neuer Abschnitt `run_settings`; in `run_undo` der Fall »a change with a part the undo cannot reach«, dessen unerreichbarer Teil (ein Ansichtstitel) mit M erreichbar wird |
| `docs/how-it-works.md`, `docs/limitations.md`, `docs/superpowers/status.md` | Stand nachziehen |

---

### Task 1: Die Einstellungsdifferenz

**Files:**
- Modify: `custom_components/dashboard_history/analyze.py`
- Test: `tests/test_analyze.py`

**Interfaces:**
- Produces:
  - `_ABSENT: object` – Marker für »nicht vorhanden«, nur innerhalb von `analyze.py`.
  - `@dataclass(frozen=True) class SettingChange: view_key: Any; path: tuple; old: Any; new: Any` – `view_key is None` heißt »das Dashboard selbst«; `old`/`new` sind `_ABSENT`, wenn die Einstellung auf dieser Seite fehlt.
  - `setting_changes(old: dict, new: dict) -> list[SettingChange]` – erst die Wurzel, dann die Ansichten in der Reihenfolge von `old`, innerhalb eines Behälters nach Schlüssel sortiert (`key=str`).
  - `_same(a: Any, b: Any) -> bool`.

- [ ] **Step 1: Tests schreiben**

In `tests/test_analyze.py` einen neuen Abschnitt:

```python
# -- named settings (GitHub #28) ------------------------------------------


def _changes(old, new):
    return [
        (c.view_key, c.path,
         "ABSENT" if c.old is analyze._ABSENT else c.old,
         "ABSENT" if c.new is analyze._ABSENT else c.new)
        for c in analyze.setting_changes(old, new)
    ]


def test_a_key_added_under_strategy_is_one_leaf():
    old = {"strategy": {"type": "original-states"}}
    new = {"strategy": {"type": "original-states", "show_clock_card": False}}
    assert _changes(old, new) == [(None, ("strategy", "show_clock_card"), "ABSENT", False)]


def test_a_whole_block_that_appears_is_the_leaf():
    assert _changes({}, {"strategy": {"type": "x"}}) == [
        (None, ("strategy",), "ABSENT", {"type": "x"})
    ]


def test_a_view_setting_is_keyed_by_its_view():
    old = {"views": [{"path": "home", "icon": "mdi:home", "cards": [A]}]}
    new = {"views": [{"path": "home", "icon": "mdi:sofa", "cards": [A, B]}]}
    assert _changes(old, new) == [("home", ("icon",), "mdi:home", "mdi:sofa")]


def test_cards_sections_badges_path_type_and_views_are_not_settings():
    old = {"views": [{"path": "home", "type": "masonry", "cards": [], "badges": []}]}
    new = {"views": [{"path": "home", "type": "sections", "sections": [],
                      "cards": [A], "badges": [{"entity": "sun.sun"}]}]}
    assert _changes(old, new) == []


def test_a_list_valued_setting_is_compared_whole():
    old = {"views": [{"path": "home", "visible": [{"user": "a"}]}]}
    new = {"views": [{"path": "home", "visible": [{"user": "a"}, {"user": "b"}]}]}
    assert _changes(old, new) == [
        ("home", ("visible",), [{"user": "a"}], [{"user": "a"}, {"user": "b"}])
    ]


def test_null_is_not_absent():
    old = {"views": [{"path": "home"}]}
    new = {"views": [{"path": "home", "theme": None}]}
    assert _changes(old, new) == [("home", ("theme",), "ABSENT", None)]


def test_one_and_true_are_different_settings():
    """Review focus 3: Python says 1 == True; a setting does not."""
    old = {"views": [{"path": "home", "max_columns": 1}]}
    new = {"views": [{"path": "home", "max_columns": True}]}
    assert _changes(old, new) == [("home", ("max_columns",), 1, True)]


def test_views_only_one_state_has_carry_no_settings():
    old = {"views": [{"path": "a", "icon": "x"}]}
    new = {"views": [{"path": "b", "icon": "y"}]}
    assert _changes(old, new) == []
```

- [ ] **Step 2: Scheitern prüfen**

Run: `python3 -m pytest tests/test_analyze.py -k "strategy or setting or null_is_not or one_and_true or carry_no or whole_block" -v`
Expected: 8 failed – `AttributeError: module 'analyze' has no attribute 'setting_changes'`.

- [ ] **Step 3: Umsetzen**

In `analyze.py` nach `_view_type_changed`:

```python
# "Not there", as opposed to None - which YAML writes as `null` and which
# is a value like any other (`theme: null`).
_ABSENT = object()

# Everything on a view that is not a named setting: the card world, the
# badges (a list without names, vorhaben N), the view's own key, and its
# layout (a conversion, #32 - refused, never written back as a setting).
_NOT_VIEW_SETTINGS = frozenset({"cards", "sections", "badges", "path", "type"})


@dataclass(frozen=True)
class SettingChange:
    """One named setting that differs between two states (GitHub #28).

    Named, not positional: `strategy.show_clock_card` means the same thing
    in every state, so it needs no matching - its path is its identity.
    `view_key` is None for the dashboard itself.
    """

    view_key: Any
    path: tuple
    old: Any
    new: Any


def _same(one: Any, other: Any) -> bool:
    """Equal as settings. Not `==`: that says 1 is True and 0 is False."""
    if one is _ABSENT or other is _ABSENT:
        return one is other
    return fingerprint(one) == fingerprint(other)


def _setting_leaves(view_key: Any, old: Any, new: Any, path: tuple, out: list) -> None:
    """Descend where both sides are dicts; everywhere else is a leaf."""
    if isinstance(old, dict) and isinstance(new, dict):
        for key in sorted(set(old) | set(new), key=str):
            _setting_leaves(
                view_key, old.get(key, _ABSENT), new.get(key, _ABSENT), path + (key,), out
            )
        return
    if not _same(old, new):
        out.append(SettingChange(view_key, path, old, new))


def setting_changes(old: dict, new: dict) -> list[SettingChange]:
    """Every named setting that differs, dashboard first, then per view.

    Only views both states have under the same key: a view that only one
    of them has is one line of its own, and its settings go with it.
    """
    out: list[SettingChange] = []
    _setting_leaves(
        None,
        {key: value for key, value in old.items() if key != "views"},
        {key: value for key, value in new.items() if key != "views"},
        (),
        out,
    )
    new_views = dict(_views_by_key(new))
    for key, old_view in _views_by_key(old):
        if key not in new_views:
            continue
        _setting_leaves(
            key,
            {k: v for k, v in old_view.items() if k not in _NOT_VIEW_SETTINGS},
            {k: v for k, v in new_views[key].items() if k not in _NOT_VIEW_SETTINGS},
            (),
            out,
        )
    return out
```

- [ ] **Step 4: Suite**

Run: `python3 -m pytest tests/ -v` → 0 failed.

- [ ] **Step 5: Commit (nach Go des Nutzers)**

```bash
git add custom_components/dashboard_history/analyze.py tests/test_analyze.py
git commit -m "Find changed named settings between two states" -m "A setting like strategy.show_clock_card is named, not positional: its
path is its identity, so it needs no matching, only a comparison. This
is the diff the explanation, the history line and the undo will read.
GitHub #28."
```

---

### Task 2: Einstellungen in der Erklärung

**Files:**
- Modify: `custom_components/dashboard_history/analyze.py` (`ViewChanges`, `_capped`, `_PAST`, `_FUTURE`, `_explain`)
- Modify: `custom_components/dashboard_history/operations.py` (`_as_dict`)
- Modify: `custom_components/dashboard_history/panel/render.js` (`renderPlain`)
- Test: `tests/test_analyze.py`, `tests/test_panel_behaviour.py`

**Interfaces:**
- Consumes: `setting_changes`, `SettingChange`, `_ABSENT` (Task 1).
- Produces: `ViewChanges.scope: str = "view"` (`"dashboard"` für die Gruppe des Dashboards); `_capped(name, entries, scope="view")`; `Entry.what == "setting"` mit `kind` aus `added`/`removed`/`edited`; `_as_dict` liefert je Gruppe zusätzlich `"scope"`.

- [ ] **Step 1: Tests schreiben**

```python
def _texts(explanation):
    return [(g.scope, g.view, [e.text for e in g.entries]) for g in explanation.groups]


def test_a_strategy_setting_is_explained_on_the_dashboard_itself():
    old = {"strategy": {"type": "original-states"}}
    new = {"strategy": {"type": "original-states", "show_clock_card": False}}
    assert _texts(analyze.explain_change(old, new)) == [
        ("dashboard", "dashboard",
         ['the setting "strategy.show_clock_card" was set to false'])
    ]


def test_view_settings_come_before_cards_and_after_a_conversion():
    old = {"views": [{"path": "home", "icon": "mdi:home", "cards": [A]}]}
    new = {"views": [{"path": "home", "type": "sections", "icon": "mdi:sofa",
                      "cards": [A, B], "sections": [{"type": "grid", "cards": []}]}]}
    [(scope, view, texts)] = _texts(analyze.explain_change(old, new))
    assert scope == "view"
    assert texts == [
        'the view "home" was converted from masonry to sections',
        'the setting "icon" was changed from "mdi:home" to "mdi:sofa"',
        "tile: light.b was added",
    ]


def test_a_removed_setting_and_a_block_value_are_worded_without_a_value():
    old = {"views": [{"path": "home", "theme": "dark", "visible": [{"user": "a"}]}]}
    new = {"views": [{"path": "home", "visible": []}]}
    [(_, _, texts)] = _texts(analyze.explain_change(old, new))
    assert texts == [
        'the setting "theme" was removed',
        'the setting "visible" was changed',
    ]


def test_the_future_tense_says_where_a_setting_goes():
    current = {"views": [{"path": "home", "max_columns": 4}]}
    target = {"views": [{"path": "home", "max_columns": 3}]}
    [(_, _, texts)] = _texts(analyze.explain_effect(current, target))
    assert texts == ['the setting "max_columns" goes back to 3']


def test_a_removed_setting_counts_as_something_removed():
    """The reassurance "Nothing on this dashboard is deleted" must not follow."""
    current = {"views": [{"path": "home", "theme": "dark"}]}
    target = {"views": [{"path": "home"}]}
    assert analyze.explain_effect(current, target).note == ""


def test_many_changed_templates_are_capped_like_cards():
    """Review focus 5."""
    old = {"button_card_templates": {f"t{i}": {"color": "red"} for i in range(20)}}
    new = {"button_card_templates": {f"t{i}": {"color": "blue"} for i in range(20)}}
    [group] = analyze.explain_change(old, new).groups
    assert len(group.entries) == analyze._ENTRY_LIMIT
    assert group.more == 20 - analyze._ENTRY_LIMIT
```

In `tests/test_panel_behaviour.py`:

```python
_PLAIN_DASHBOARD_GROUP = """
const render = await import(new URL("./panel/render.js", %(url)s).href);
const html = render.renderPlain({
  groups: [
    { scope: "dashboard", view: "dashboard", more: 0,
      entries: [{ kind: "added", text: "the setting \\"strategy.show_clock_card\\" was set to false" }] },
    { scope: "view", view: "Home", more: 0,
      entries: [{ kind: "added", text: "tile: light.b was added" }] },
  ],
  note: "",
}, "What changed");
console.log(JSON.stringify({ html }));
"""


@pytest.fixture(scope="session")
def plain_dashboard_group(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "plain_dashboard_group", _PLAIN_DASHBOARD_GROUP)


def test_a_dashboard_group_is_not_headed_as_a_view(plain_dashboard_group):
    html = plain_dashboard_group["html"]
    assert "On the dashboard itself" in html
    assert "In the view dashboard" not in html
    assert "In the view Home" in html
```

- [ ] **Step 2: Scheitern prüfen**

Run, als zwei Befehle – pytest wertet bei zwei `-k` nur das letzte aus:
`python3 -m pytest tests/test_analyze.py -k "explained_on or before_cards or without_a_value or future_tense_says or counts_as_something or capped_like" -v`
`python3 -m pytest tests/test_panel_behaviour.py -k "dashboard_group" -v`
Expected: FAIL (`ViewChanges` hat kein `scope`; keine Einstellungseinträge; `renderPlain` kennt `scope` nicht).

- [ ] **Step 3: `ViewChanges` und `_capped`**

```python
@dataclass(frozen=True)
class ViewChanges:
    """What changed in one view, or on the dashboard itself.

    `more` is what the cap left out. `scope` is "dashboard" for the one
    group about the dashboard's own settings (GitHub #28), which has no
    view to be headed by.
    """

    view: str
    entries: list[Entry]
    more: int = 0
    scope: str = "view"
```

```python
def _capped(name: str, entries: list[Entry], scope: str = "view") -> ViewChanges:
    """Keep the list readable, and say how much it hides.

    Silently truncating would be the one thing this project must not do:
    a summary that omits without saying so is worse than a long one.
    """
    if len(entries) <= _ENTRY_LIMIT:
        return ViewChanges(view=name, entries=entries, scope=scope)
    return ViewChanges(
        view=name,
        entries=entries[:_ENTRY_LIMIT],
        more=len(entries) - _ENTRY_LIMIT,
        scope=scope,
    )
```

- [ ] **Step 4: Wörter**

In `_PAST` ergänzen:

```python
    ("setting", "added"): 'the setting "{label}" was set to {new}',
    ("setting", "added_bare"): 'the setting "{label}" was set',
    ("setting", "removed"): 'the setting "{label}" was removed',
    ("setting", "edited"): 'the setting "{label}" was changed from {old} to {new}',
    ("setting", "edited_bare"): 'the setting "{label}" was changed',
```

In `_FUTURE` ergänzen:

```python
    ("setting", "added"): 'the setting "{label}" comes back as {new}',
    ("setting", "added_bare"): 'the setting "{label}" comes back',
    ("setting", "removed"): 'the setting "{label}" will be removed',
    ("setting", "edited"): 'the setting "{label}" goes back to {new}',
    ("setting", "edited_bare"): 'the setting "{label}" goes back to how it was',
```

Nach `_entry` einfügen:

```python
def _value_text(value: Any) -> str | None:
    """A setting's value as a sentence can carry it, or None if it cannot.

    Short things only. A list or a block is left to the diff below the
    sentence, which shows it exactly (decision 11).
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return f'"{_shorten(value)}"'
    return None


def _setting_entry(words: dict, change: SettingChange) -> Entry:
    label = ".".join(str(key) for key in change.path)
    if change.new is _ABSENT:
        kind, key, values = "removed", "removed", {}
    elif change.old is _ABSENT:
        new = _value_text(change.new)
        kind = "added"
        key, values = ("added", {"new": new}) if new is not None else ("added_bare", {})
    else:
        old, new = _value_text(change.old), _value_text(change.new)
        kind = "edited"
        if new is not None and (old is not None or words is _FUTURE):
            key, values = "edited", {"old": old, "new": new}
        else:
            key, values = "edited_bare", {}
    return Entry(
        kind=kind,
        what="setting",
        label=label,
        text=words[("setting", key)].format(label=label, **values),
    )
```

Hinweis: Die Zukunftsform von »geändert« nennt nur den Zielwert (`goes back to {new}`), braucht also keinen darstellbaren alten Wert – daher die Ausnahme `words is _FUTURE`. `str.format` ignoriert überzählige Schlüssel (`old` in der Zukunftsform).

- [ ] **Step 5: `_explain`**

Direkt nach `matching = match_cards(old, new)`:

```python
    settings_by_view: dict[Any, list[Entry]] = {}
    for change in setting_changes(old, new):
        settings_by_view.setdefault(change.view_key, []).append(_setting_entry(words, change))
```

Nach `groups: list[ViewChanges] = []` und `removed_anything = False`:

```python
    own = settings_by_view.get(None, [])
    if own:
        # The dashboard's own settings have no view to sit under, and a
        # heading "In the view dashboard" would invent one.
        groups.append(_capped("dashboard", own, scope="dashboard"))
        removed_anything = any(entry.kind == "removed" for entry in own)
```

In der Schleife über `_views_by_key(old)` die Zeile `entries = list(by_view.get(key, []))` ersetzen durch

```python
        entries = [*settings_by_view.get(key, []), *by_view.get(key, [])]
```

(die Konvertierung wird danach wie bisher an Position 0 eingefügt und steht damit vor den Einstellungen).

- [ ] **Step 6: `_as_dict` und `renderPlain`**

`operations.py`, `_as_dict`: im Gruppen-Dict `"scope": group.scope,` nach `"more": group.more,`.

`panel/render.js`, `renderPlain`: die Zeile mit `<strong>In the view …</strong>` ersetzen durch

```js
        <strong>${group.scope === "dashboard" ? "On the dashboard itself" : `In the view ${escape(group.view)}`}</strong>
```

- [ ] **Step 7: Den bestehenden Test für »nicht benennbar« auf einen Fall umstellen, der es bleibt**

`tests/test_analyze.py`, `test_an_unnameable_change_never_claims_that_nothing_changed`, nimmt bisher eine umbenannte Ansicht als Beispiel. Nach diesem Task ist `title` eine benannte Einstellung, der Test würde rot (im Review simuliert: `Left contains one more item: ViewChanges(view='Home', entries=[Entry(kind='edited', what='setting', label='title', …)])`). Die Eigenschaft, die er schützt, bleibt richtig; nur das Beispiel taugt nicht mehr. Eine Section-Einstellung bleibt auch nach M und N unbenennbar (siehe Nicht-Ziele der Spec). Ersetzen durch:

```python
def test_an_unnameable_change_never_claims_that_nothing_changed():
    # A section setting: the cards match exactly, and a section has no
    # name to address a setting by (GitHub #28 leaves sections out on
    # purpose). The summary sits directly above a diff that plainly shows
    # the difference - claiming "nothing changed" there would be refuted
    # at a glance, which is worse than having no summary at all.
    old = {"views": [{"path": "home", "type": "sections",
                      "sections": [{"type": "grid", "cards": [A]}]}]}
    new = {"views": [{"path": "home", "type": "sections",
                      "sections": [{"type": "grid", "column_span": 2, "cards": [A]}]}]}
    result = analyze.explain_change(old, new)
    assert result.groups == []
    assert "see the details" in result.note
```

Nicht die Badges als Beispiel nehmen: Die werden mit Vorhaben N benennbar, und der Test bräche dort erneut.

- [ ] **Step 8: Tests und Suite**

Run: `python3 -m pytest tests/ -v` → 0 failed.

Eine Prüfsumme der Panel-Dateien prüft kein pytest-Test; der Digest wird in `panel.py` zur Laufzeit gebildet. Für `run_checks.py` in Task 6 heißt das: nach der Änderung an `render.js` den Testcontainer neu starten, sonst liefert er die alte Datei aus.

- [ ] **Step 9: Commit (nach Go des Nutzers)**

```bash
git add custom_components/dashboard_history/analyze.py custom_components/dashboard_history/operations.py custom_components/dashboard_history/panel/render.js tests/test_analyze.py tests/test_panel_behaviour.py
git commit -m "Explain changed settings, and the dashboard's own" -m "A change that only set a key under strategy: was explained as \"cannot
be described in terms of cards\". Settings are named now, per view and
in a group of their own for the dashboard, which the panel heads as
the dashboard rather than as a view. GitHub #28."
```

---

### Task 3: Einstellungen in `plan_undo`

**Files:**
- Modify: `custom_components/dashboard_history/analyze.py` (`UndoStep`, `plan_undo`, neue Hilfsfunktion `_setting_at`)
- Test: `tests/test_analyze.py`

**Interfaces:**
- Consumes: `setting_changes`, `_same`, `_ABSENT` (Task 1).
- Produces: `UndoStep.expect_absent: bool = False`. Ein Einstellungsschritt hat `kind` `"dashboard_setting"` oder `"view_setting"`, `action` `"set"` oder `"unset"`, `location` = Schlüsselpfad, `index=0`, `view_path` (Pfad der Ansicht oder `None`), `view_index` (bei pfadloser Ansicht der Positionsindex aus dem Schlüssel, sonst `-1`), `expect` = erwarteter heutiger Wert (oder `None` bei `expect_absent=True`), `payload` = zu schreibender Wert (bei `unset` `None`), `label` = `'setting "<pfad>"'`.

- [ ] **Step 1: Tests schreiben**

```python
def _steps(plan):
    return [(s.kind, s.action, s.location, s.payload, s.expect_absent) for s in plan.steps]


def test_a_setting_only_change_is_undoable():
    before = {"strategy": {"type": "original-states"}}
    after = {"strategy": {"type": "original-states", "show_clock_card": False}}
    plan = analyze.plan_undo(before, after, after)
    assert plan.blocked is None
    assert _steps(plan) == [
        ("dashboard_setting", "unset", ("strategy", "show_clock_card"), None, False)
    ]


def test_a_setting_changed_again_refuses():
    before = {"views": [{"path": "home", "icon": "a"}]}
    after = {"views": [{"path": "home", "icon": "b"}]}
    current = {"views": [{"path": "home", "icon": "c"}]}
    plan = analyze.plan_undo(before, after, current)
    assert plan.blocked == 'the setting "icon" was changed again after this'


def test_a_setting_already_back_is_skipped_and_its_neighbour_is_not():
    # Two settings, only one of them back. A plan that ignored settings
    # altogether would pass a single-setting version of this test too.
    before = {"views": [{"path": "home", "icon": "a", "theme": "x"}]}
    after = {"views": [{"path": "home", "icon": "b", "theme": "y"}]}
    current = {"views": [{"path": "home", "icon": "a", "theme": "y"}]}
    plan = analyze.plan_undo(before, after, current)
    assert plan.blocked is None
    assert _steps(plan) == [("view_setting", "set", ("theme",), "x", False)]


def test_another_key_of_the_same_block_changed_since_stays_exact():
    """Review focus 1."""
    before = {"strategy": {"type": "x"}}
    after = {"strategy": {"type": "x", "a": 1}}
    current = {"strategy": {"type": "x", "a": 1, "b": 2}}
    plan = analyze.plan_undo(before, after, current)
    assert plan.blocked is None
    assert _steps(plan) == [("dashboard_setting", "unset", ("strategy", "a"), None, False)]


def test_a_block_removed_since_refuses_rather_than_half_rebuilt():
    """Review focus 2."""
    before = {"strategy": {"type": "x", "a": 1}}
    after = {"strategy": {"type": "x"}}
    current = {}
    plan = analyze.plan_undo(before, after, current)
    assert plan.blocked == 'the setting "strategy.a" no longer has the "strategy" block it belonged to'


def test_setting_back_a_removed_setting_writes_its_old_value():
    before = {"views": [{"path": "home", "theme": None}]}
    after = {"views": [{"path": "home"}]}
    plan = analyze.plan_undo(before, after, after)
    assert _steps(plan) == [("view_setting", "set", ("theme",), None, True)]


def test_a_setting_of_a_view_gone_since_refuses():
    before = {"views": [{"path": "home", "icon": "a"}]}
    after = {"views": [{"path": "home", "icon": "b"}]}
    plan = analyze.plan_undo(before, after, {"views": []})
    assert plan.blocked is not None
    assert "no longer on the dashboard" in plan.blocked


def test_a_refused_card_refuses_the_setting_with_it():
    before = {"views": [{"path": "home", "icon": "a", "cards": []}]}
    after = {"views": [{"path": "home", "icon": "b", "cards": [A]}]}
    current = {"views": [{"path": "home", "icon": "b", "cards": [A, A]}]}
    plan = analyze.plan_undo(before, after, current)
    assert plan.blocked is not None
    assert plan.steps == ()
```

- [ ] **Step 2: Scheitern prüfen**

Run: `python3 -m pytest tests/test_analyze.py -k "setting_only or changed_again_refuses or already_back_is or same_block or half_rebuilt or old_value or view_gone_since or refuses_the_setting" -v`
Expected: 7 failed, 1 passed – u. a. »this change did not alter any cards« und `AttributeError` für `expect_absent`. Grün ist schon vorher `test_a_refused_card_refuses_the_setting_with_it`, weil heute die Karte allein verweigert; der Test ist ein Wächter dafür, dass die Einstellung daran nichts ändert, kein TDD-Test.

- [ ] **Step 3: `UndoStep`**

Nach `parked: bool = False` (aus Vorhaben L):

```python
    # For a setting step: that nothing is expected at this address today.
    # Its own field because None is a value (`theme: null`), not absence.
    expect_absent: bool = False
```

- [ ] **Step 4: Hilfsfunktion**

Nach `setting_changes`:

```python
def _setting_at(container: dict, path: tuple) -> tuple[Any, str | None]:
    """The value at `path`, or `_ABSENT`; and the block that vanished, if one did.

    Every ancestor of a leaf was a dict in both states of the change -
    `_setting_leaves` only descends through dicts on both sides. So one
    that is missing or no dict today was removed since, and writing the
    leaf would rebuild half a block nobody asked for.
    """
    for depth, key in enumerate(path[:-1]):
        container = container.get(key, _ABSENT) if isinstance(container, dict) else _ABSENT
        if not isinstance(container, dict):
            return _ABSENT, ".".join(str(k) for k in path[: depth + 1])
    return container.get(path[-1], _ABSENT), None
```

- [ ] **Step 5: `plan_undo`**

Die Zeile `type_changed = any(...)` bleibt; direkt darunter:

```python
    settings = setting_changes(before, after)
```

In die frühe Bedingung `if not (… or type_changed):` zusätzlich `or settings` aufnehmen.

Nach `rebuilt, shifted = _section_drift(...)` / `if rebuilt: …` (Vorhaben L) und vor `by_mark: dict[...] = {}` einfügen:

```python
    setting_steps: list[UndoStep] = []
    for change in settings:
        label = ".".join(str(key) for key in change.path)
        if change.view_key is None:
            container = current
        else:
            container = now_views.get(change.view_key)
            if container is None:
                name = _view_name(old_views[change.view_key], change.view_key)
                return UndoPlan(
                    blocked=f'the view "{name}" is no longer on the dashboard, '
                    f'so its setting "{label}" cannot be taken back'
                )
        standing, vanished = _setting_at(container, change.path)
        if vanished is not None:
            return UndoPlan(
                blocked=f'the setting "{label}" no longer has the "{vanished}" '
                f"block it belonged to"
            )
        if _same(standing, change.old):
            # Already back, the way a deleted card that returned is.
            continue
        if not _same(standing, change.new):
            return UndoPlan(blocked=f'the setting "{label}" was changed again after this')
        key = change.view_key
        setting_steps.append(
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
```

Und direkt nach `steps: list[UndoStep] = []`:

```python
    steps.extend(setting_steps)
```

- [ ] **Step 6: Tests und Suite**

Run: `python3 -m pytest tests/ -v` → 0 failed.

- [ ] **Step 7: Commit (nach Go des Nutzers)**

```bash
git add custom_components/dashboard_history/analyze.py tests/test_analyze.py
git commit -m "Plan undo steps for named settings" -m "A setting's path is its address in every state, so taking one back is a
single question: is what the change left still there? Yes writes the
old value, already-back skips, anything else refuses - and a vanished
parent block refuses rather than rebuilding half of it. GitHub #28."
```

---

### Task 4: `restore.apply_undo` schreibt Einstellungen

**Files:**
- Modify: `custom_components/dashboard_history/restore.py`
- Test: `tests/test_restore.py`

**Interfaces:**
- Consumes: Einstellungsschritte aus Task 3.
- Produces: `apply_undo` wendet alle Schritte mit `kind` in `("dashboard_setting", "view_setting")` in Planreihenfolge vor allen Karten- und Ansichtsschritten an und prüft vor jedem Schreiben den erwarteten Wert.

- [ ] **Step 1: Tests schreiben**

```python
# -- named settings (GitHub #28) ---------------------------------------


def test_a_strategy_key_is_taken_back():
    before = {"strategy": {"type": "x"}}
    after = {"strategy": {"type": "x", "show_clock_card": False}}
    plan = analyze.plan_undo(before, after, after)
    assert restore.apply_undo(after, plan) == before


def test_a_view_setting_goes_back_and_the_input_stays():
    before = {"views": [{"path": "home", "icon": "a"}]}
    after = {"views": [{"path": "home", "icon": "b"}]}
    plan = analyze.plan_undo(before, after, after)
    assert restore.apply_undo(after, plan) == before
    assert after == {"views": [{"path": "home", "icon": "b"}]}


def test_a_removed_null_setting_comes_back_as_null():
    before = {"views": [{"path": "home", "theme": None}]}
    after = {"views": [{"path": "home"}]}
    plan = analyze.plan_undo(before, after, after)
    assert restore.apply_undo(after, plan) == before


def test_a_setting_changed_between_plan_and_write_refuses():
    before = {"views": [{"path": "home", "icon": "a"}]}
    after = {"views": [{"path": "home", "icon": "b"}]}
    plan = analyze.plan_undo(before, after, after)
    with pytest.raises(LookupError, match="icon"):
        restore.apply_undo({"views": [{"path": "home", "icon": "c"}]}, plan)


def test_a_setting_of_a_pathless_view_survives_a_neighbour_being_removed():
    """Review focus 4: settings going first breaks nothing.

    It does not prove the order necessary - a view *before* a pathless
    one can never be removed in the same undo, because that would change
    the pathless view's key and `_positions_lie` refuses first.
    """
    before = {"views": [{"title": "Home", "icon": "a"}]}
    after = {"views": [{"title": "Home", "icon": "b"}, {"path": "neu", "cards": []}]}
    plan = analyze.plan_undo(before, after, after)
    assert plan.blocked is None
    assert restore.apply_undo(after, plan) == before


def test_an_undo_adds_no_views_key_to_a_strategy_dashboard():
    """A strategy dashboard has no `views:`; the undo must not invent one.

    `apply_undo` used `result.setdefault("views", [])` for its own
    bookkeeping, which wrote `views: []` into every configuration that
    had none - harmless while only card changes were undoable, since a
    dashboard without views has no cards. With settings it is the one
    kind of dashboard issue #28 is about.
    """
    before = {"strategy": {"type": "x"}}
    after = {"strategy": {"type": "x", "show_clock_card": False}}
    result = restore.apply_undo(after, analyze.plan_undo(before, after, after))
    assert "views" not in result


def test_undoing_a_takeover_gives_the_strategy_dashboard_back_whole():
    """Home Assistant's "take control" replaces `strategy` with `views`.

    Undone, the strategy comes back and the views go - and the list they
    leave empty goes too, or the result carries a `views: []` the state
    before never had.
    """
    before = {"strategy": {"type": "original-states"}}
    after = {"views": [{"path": "home", "cards": [A]}]}
    plan = analyze.plan_undo(before, after, after)
    assert plan.blocked is None
    assert restore.apply_undo(after, plan) == before


def test_an_empty_views_list_beside_a_strategy_stays_when_the_strategy_did_not_come_back():
    """Only the undo of a takeover drops `views: []`, not every undo near one.

    Home Assistant does not write this pair itself, but the API accepts
    it. Dropping the list anyway would make an undo with nothing left to
    do still differ from today's state, and offer to write that.
    """
    before = {"strategy": {"type": "x"}, "views": []}
    after = {"strategy": {"type": "x", "show_clock_card": False}, "views": []}
    assert restore.apply_undo(after, analyze.plan_undo(before, after, after)) == before
    assert restore.apply_undo(before, analyze.plan_undo(before, after, before)) == before


def test_one_is_not_what_an_undo_planned_as_true():
    """Review focus 3, at the last moment: 1 == True in Python."""
    before = {"views": [{"path": "home", "max_columns": 3}]}
    after = {"views": [{"path": "home", "max_columns": True}]}
    plan = analyze.plan_undo(before, after, after)
    with pytest.raises(LookupError, match="max_columns"):
        restore.apply_undo({"views": [{"path": "home", "max_columns": 1}]}, plan)
```

- [ ] **Step 2: Scheitern prüfen**

Run: `python3 -m pytest tests/test_restore.py -k "strategy_key or view_setting or null_setting or between_plan_and_write or pathless_view_survives or no_views_key or takeover or planned_as_true or did_not_come_back" -v`
Expected: FAIL – die Einstellungsschritte werden ignoriert, das Ergebnis gleicht `after` (beim Strategie-Dashboard zusätzlich mit einem erfundenen `views: []`).

- [ ] **Step 3: Umsetzen**

In `restore.py` vor `apply_undo`:

```python
_SETTING_KINDS = ("dashboard_setting", "view_setting")


def _same_value(one: Any, other: Any) -> bool:
    """Equal as settings. Not `==`: that says 1 is True and 0 is False.

    The same comparison as `analyze.fingerprint`, written out here for
    the reason at the top of this file.
    """
    return json.dumps(one, sort_keys=True, default=str) == json.dumps(
        other, sort_keys=True, default=str
    )


def _apply_setting(config: dict, views: list, step: UndoStep) -> None:
    """Write one named setting back, if it still holds what was planned.

    The lines that walk a path live here rather than being imported from
    `analyze`, for the reason at the top of this file.
    """
    if step.kind == "dashboard_setting":
        container = config
    else:
        container = _find_view(views, step)
        if container is None:
            raise LookupError(
                f"the view {step.label} belonged to no longer exists "
                f"(path={step.view_path!r}, index={step.view_index})"
            )
    *parents, leaf = step.location
    for key in parents:
        container = container.get(key) if isinstance(container, dict) else None
        if not isinstance(container, dict):
            raise LookupError(f"{step.label} no longer has the block it belonged to")
    present = leaf in container
    if step.expect_absent:
        holds = not present
    else:
        holds = present and _same_value(container[leaf], step.expect)
    if not holds:
        raise LookupError(f"{step.label} is no longer what the undo was planned against")
    if step.action == "unset":
        del container[leaf]
    else:
        container[leaf] = copy.deepcopy(step.payload)
```

Oben in `restore.py` `import json` ergänzen; `Any` aus `typing` mit importieren, falls es dort noch nicht steht (heute: `from typing import TYPE_CHECKING`).

In `apply_undo` direkt nach dem `_paths_share`-Block, vor `# Cards before views`:

```python
    # Settings first: they shift no index, and a pathless view is found
    # by its position, which removing a whole view would move.
    for step in plan.steps:
        if step.kind in _SETTING_KINDS:
            _apply_setting(result, views, step)
```

Den `views`-Schlüssel nicht mehr erfinden. Die Zeilen

```python
    result = copy.deepcopy(config)
    views = result.setdefault("views", [])
```

ersetzen durch

```python
    result = copy.deepcopy(config)
    # Remembered so the bookkeeping list below never ends up in a
    # configuration that had no `views:` - a strategy dashboard has none,
    # and an undo of one of its settings must not add an empty list.
    had_views = "views" in result
    views = result.setdefault("views", [])
```

und direkt vor dem abschließenden `return result` von `apply_undo`:

```python
    # An empty list also goes when this undo brought the whole strategy
    # block back: that is the undo of Home Assistant's "take control",
    # which swapped the strategy for views, and the state before it had
    # no `views:`. Only then - a `views: []` that already stood beside a
    # strategy is left alone, or an undo with nothing to do would still
    # find something to write.
    restores_strategy = any(
        step.kind == "dashboard_setting"
        and step.action == "set"
        and tuple(step.location) == ("strategy",)
        for step in plan.steps
    )
    if not views and (not had_views or restores_strategy):
        del result["views"]
```

- [ ] **Step 4: Suite**

Run: `python3 -m pytest tests/ -v` → 0 failed.

- [ ] **Step 5: Commit (nach Go des Nutzers)**

```bash
git add custom_components/dashboard_history/restore.py tests/test_restore.py
git commit -m "Write named settings back in an undo" -m "Setting steps run before every card and view step: they move no index,
and a pathless view is still where the plan saw it. Each one checks the
value it was planned against before writing. GitHub #28."
```

---

### Task 5: Die Verlaufszeile zählt Einstellungen, und `1` bleibt nicht `true`

**Files:**
- Modify: `custom_components/dashboard_history/analyze.py` (`Summary`, `summarize`, `change_message`, `_COUNT`)
- Modify: `custom_components/dashboard_history/operations.py` (`_same_state`, `async_undo_change`)
- Test: `tests/test_analyze.py` (`operations.py` importiert Home Assistant und ist nicht in pytest erreichbar; seine Hälfte prüft `run_settings` in Task 6)

**Interfaces:**
- Produces: `Summary.settings: int = 0`; `change_message` hängt `"N setting changed"`/`"N settings changed"` als letzten Zählteil an; `_COUNT` liest ihn. `operations._same_state(one: dict, other: dict) -> bool`.

**Warum die Gleichheit hier mitkommt (Review W2):** `change_message` beginnt mit `if old == new:` und antwortet dann `metadata recorded`. Für `max_columns: 1 → true` sagt Python `==`, obwohl ein Commit entsteht (`capture._write_one` vergleicht Text) und die Erklärung darunter `the setting "max_columns" was changed from 1 to true` liefert – genau der Widerspruch, den Entscheidung 2 der Spec beseitigen soll. Ebenso `result == current` (»this change is already taken back«, obwohl nichts zurückgenommen wurde) und `result == before_state` (`equals_state_before`) in `operations.async_undo_change`. Karten sind davon heute schon betroffen (`show_state: 1 → true` an einer Tile-Karte wird als »edited« erklärt, aber als »metadata recorded« verbucht; nachgerechnet am 2026-09-25); das wird hier mit behoben, weil es derselbe Vergleich ist.

- [ ] **Step 1: Tests schreiben**

```python
def test_a_setting_only_save_is_counted_in_the_history_line():
    old = {"strategy": {"type": "x"}}
    new = {"strategy": {"type": "x", "show_clock_card": False}}
    assert analyze.change_message("dash", old, new, "save") == "dash: 1 setting changed"


def test_settings_are_counted_after_cards():
    old = {"views": [{"path": "home", "icon": "a", "theme": "x", "cards": []}]}
    new = {"views": [{"path": "home", "icon": "b", "cards": [A]}]}
    assert analyze.change_message("dash", old, new, "save") == "dash: 1 added, 2 settings changed"


def test_a_settings_part_parses_and_is_no_addition():
    assert not analyze.message_adds("dash: 2 settings changed")
    assert analyze.message_adds("dash: 1 added, 1 setting changed")


def test_one_becoming_true_is_a_change_not_metadata():
    """Review focus 3: `old == new` says yes, the commit says no."""
    old = {"views": [{"path": "home", "max_columns": 1}]}
    new = {"views": [{"path": "home", "max_columns": True}]}
    assert analyze.change_message("dash", old, new, "save") == "dash: 1 setting changed"
```

- [ ] **Step 2: Scheitern prüfen**

Run: `python3 -m pytest tests/test_analyze.py -k "history_line or counted_after or settings_part or becoming_true" -v`
Expected: FAIL – »no card changes« bzw. `message_adds` liest die Zeile mit unbekanntem Teil gar nicht; für `1 → true` `dash: metadata recorded`.

- [ ] **Step 3: Umsetzen**

`Summary`: nach `views_removed: int = 0` das Feld `settings: int = 0`.

`summarize`: im Rückgabewert `settings=len(setting_changes(old, new)),`.

`change_message`: in `parts` als letzten Eintrag

```python
        f"{counts.settings} setting{'s' if counts.settings != 1 else ''} changed"
        if counts.settings
        else "",
```

`_COUNT`:

```python
_COUNT = re.compile(
    r"^\d+ (?:views? (?:added|removed)|added|removed|edited|moved|settings? changed)$"
)
```

Den Kommentar über `_COUNT` nicht ändern – er beschreibt genau diese Kopplung.

`change_message`: `if old == new:` ersetzen durch

```python
    # `==` alone says 1 is True; the commit this message goes with does
    # not, and neither does the explanation shown under it.
    if old == new and fingerprint(old) == fingerprint(new):
```

`fingerprint` läuft nur, wenn `==` schon ja gesagt hat – also nicht bei jedem Speichern.

- [ ] **Step 4: `operations.py`**

`fingerprint` in den Import aus `.analyze` aufnehmen (alphabetisch, zwischen `find_removed` und `message_adds`). Vor `async_undo_change`:

```python
def _same_state(one: dict, other: dict) -> bool:
    """`==`, but not blind to 1 against True (GitHub #28).

    Since named settings are undoable, `max_columns: 1` and
    `max_columns: true` are two states an undo moves between; Python's
    `==` calls them equal. `fingerprint` only runs when `==` already
    said yes, so the common case costs what it did.
    """
    return one == other and fingerprint(one) == fingerprint(other)
```

In `async_undo_change` die beiden Vergleiche ersetzen, im Executor, weil `fingerprint` zwei ganze Dashboards schreibt, sobald sie gleich aussehen:

- `if result == current:` → `if await hass.async_add_executor_job(_same_state, result, current):`. Der lange Kommentar darunter bleibt bis auf einen Satz: Er begründet mit »every step moves a whole card or view verbatim«, und das stimmt mit Einstellungsschritten nicht mehr ganz. Ergänzen: ``or writes one setting's value back, which may give back a key `current` lacked but never reorders what `current` has`` – der Schluss (gleich heißt leerer Diff) bleibt, weil ein Schritt, der wirklich schreibt, `result` ungleich `current` macht.
- `"equals_state_before": result == before_state,` → vor dem Dict `equals = await hass.async_add_executor_job(_same_state, result, before_state)` und im Dict `"equals_state_before": equals,`.

- [ ] **Step 5: Suite**

Run: `python3 -m pytest tests/ -v` → 0 failed.

- [ ] **Step 6: Commit (nach Go des Nutzers)**

```bash
git add custom_components/dashboard_history/analyze.py custom_components/dashboard_history/operations.py tests/test_analyze.py
git commit -m "Count changed settings in the history line" -m "\"no card changes\" was literally true and contradicted the explanation
right under it, which now lists the setting. One count part for all
three kinds keeps the line short; _COUNT learns it in the same change
so the line still parses as generated.

Python's == says 1 is True, so a save from max_columns: 1 to true was
logged as \"metadata recorded\", and undoing it would have answered
\"already taken back\". Both comparisons now use the fingerprint the
explanation already relies on. GitHub #28."
```

---

### Task 6: Laufende Instanz und Dokumentation

**Files:**
- Modify: `tests/integration/run_checks.py`
- Modify: `docs/how-it-works.md`, `docs/limitations.md`, `docs/superpowers/status.md`

- [ ] **Step 1: `run_settings` in `run_checks.py`**

Nach `run_parking` (Vorhaben L) einfügen und im Hauptblock nach `asyncio.run(run_parking(access))` mit `asyncio.run(run_settings(access))` aufrufen:

```python
async def run_settings(access: str) -> None:
    """Named settings, explained, counted and taken back (GitHub #28)."""
    key = "dh-settings"

    async with Socket(access) as socket:
        listed = (await socket.call("lovelace/dashboards/list")) or []
        if not any(entry.get("url_path") == key for entry in listed):
            await socket.call("lovelace/dashboards/create", url_path=key, title=key)
            await asyncio.sleep(3)

        async def save(config: dict) -> dict:
            # The newest entry *after* this save - `_wait_for_new_state`,
            # not `_wait_until_recorded`, for the reason in `run_undo`'s
            # `save`: the latter is satisfied by the entry before, and
            # every check below hangs on the entry it returns. Every state
            # saved here differs from the one before it, so a commit is
            # always coming.
            rows = (
                await socket.call("dashboard_history/history", dashboard=key, limit=1)
            )["changes"]
            await socket.call("lovelace/config/save", url_path=key, config=config)
            changes = await _wait_for_new_state(
                socket, key, rows[0]["revision"] if rows else "", RECORDING_WAIT
            )
            return changes[0]

        async def undo(revision: str) -> tuple[dict, dict]:
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
                await asyncio.sleep(2)
            return asked, await socket.call("lovelace/config", url_path=key)

        # A view's icon: counted, explained by name, taken back.
        view = {"path": "home", "title": "Home", "icon": "mdi:home", "cards": []}
        await save({"views": [view]})
        entry = await save({"views": [{**view, "icon": "mdi:sofa"}]})
        check(
            "a setting-only save is counted",
            entry["message"].endswith("1 setting changed"),
            entry["message"],
        )
        told = await socket.call(
            "dashboard_history/explain", dashboard=key, revision=entry["revision"]
        )
        texts = [e["text"] for g in told["groups"] for e in g["entries"]]
        check(
            "and explained by name",
            texts == ['the setting "icon" was changed from "mdi:home" to "mdi:sofa"'],
            f"{texts}",
        )
        asked, live = await undo(entry["revision"])
        check("and undoable", asked.get("available") is True, asked.get("reason", ""))
        check(
            "and the icon goes back",
            live["views"][0].get("icon") == "mdi:home",
            f"{live['views'][0]!r}",
        )

        # The case issue #28 is about: a key in a strategy dashboard's
        # `strategy:` block. Only the running instance shows that a state
        # without `views:` is saved and handed back as such - the undo
        # must not slip in the empty list `apply_undo` keeps for itself.
        strategy = {"type": "original-states"}
        await save({"strategy": strategy})
        entry = await save({"strategy": {**strategy, "show_clock_card": False}})
        asked, live = await undo(entry["revision"])
        check(
            "a strategy key is taken back",
            asked.get("available") is True
            and "views" not in live
            and live.get("strategy") == strategy,
            f"{asked.get('reason', '')} {live!r}",
        )

        # 1 against true, which Python's == calls equal: the history line
        # must count it, and the undo must write rather than answer
        # "already taken back". The half of this in operations.py has no
        # pytest to reach it.
        await save({"views": [{**view, "max_columns": 1}]})
        entry = await save({"views": [{**view, "max_columns": True}]})
        check(
            "1 becoming true is counted as a setting",
            entry["message"].endswith("1 setting changed"),
            entry["message"],
        )
        asked, live = await undo(entry["revision"])
        standing = live["views"][0].get("max_columns")
        check(
            "and taken back to 1, not reported as already back",
            asked.get("available") is True and standing == 1 and standing is not True,
            f"{asked.get('reason', '')} max_columns={standing!r}",
        )

        listed = (await socket.call("lovelace/dashboards/list")) or []
        mine = next((e for e in listed if e.get("url_path") == key), None)
        if mine is not None:
            await socket.call("lovelace/dashboards/delete", dashboard_id=mine["id"])
```

Die Verlaufseinträge tragen ihr Feld `message`; heißt es in der Antwort von `_wait_for_new_state` anders, den Namen aus `run_explanation` übernehmen (`grep -n "message" tests/integration/run_checks.py | head`). Bleibt das Dashboard nach einem abgebrochenen Lauf stehen und gleicht sein Stand zufällig dem ersten `save`, kommt kein Commit und `_wait_for_new_state` läuft in seine Frist – dann das Dashboard `dh-settings` (genau dieser Schlüssel, nie per Präfix) von Hand löschen.

- [ ] **Step 1b: `run_undo` – der Teil, den der Undo nicht erreicht, ist keiner mehr**

`run_undo` prüft `equals_state_before` in beide Richtungen. Für »nein« nimmt es eine Änderung, die eine Karte löscht **und** den Titel der Ansicht umbenennt (`title="Renamed"`), begründet im Kommentar über `state()`: der Undo »works on cards and views, never on a view's own labels«. Mit diesem Vorhaben nimmt er den Titel mit zurück, `equals_state_before` wird `True`, der Check rot. pytest sieht das nicht (Befund aus der Einarbeitung des Reviews, nicht vom Reviewer).

Einen anderen unerreichbaren Teil zu suchen wäre ein Wettlauf gegen die nächsten Vorhaben (Badges werden mit N erreichbar). Was dauerhaft zu »nein« führt, ist eine spätere Speicherung, die der Undo stehen lässt. Den Block ab `await save(socket, [keep, first, later])` vor `mixed = await newest(socket)` bis einschließlich `the_add = await newest(socket)` ersetzen durch:

```python
        await save(socket, [keep, first, later])
        await save(socket, [keep, later])
        mixed = await newest(socket)
        # A later save the undo leaves standing: the one way to "no" that
        # no future undo can reach. A renamed view title served here
        # until named settings became undoable (GitHub #28).
        await save(socket, [keep, later, fresh])
        the_add = await newest(socket)
        answer = await socket.call(
            "dashboard_history/undo_change", dashboard=key, revision=mixed
        )
        check(
            "a change with a later save after it says so",
            answer.get("available") is True
            and answer.get("equals_state_before") is False,
            f"available={answer.get('available')} "
            f"equals={answer.get('equals_state_before')} "
            f"{answer.get('reason', '')}",
        )
```

Der ersetzte Bereich enthält den Kommentar `# The undo that *deletes*. …` – ihn unverändert direkt hinter den neuen Check setzen, vor die nächste Speicherung. Die ist dann `await save(socket, [keep, later, fresh, tail])` **ohne** `title="Renamed"`; alles ab dort bleibt. Danach hat `title` in `state()` und `save()` keinen Aufrufer mehr: den Parameter aus beiden entfernen und den Kommentar `# The title is a parameter because …` streichen. Die Endprüfung `live["views"][0]["cards"] == [keep, later, tail]` bleibt richtig, weil sich an den Kartenlisten nichts ändert.

- [ ] **Step 2: Prüfen**

Run: `python3 -m pytest tests/ -v` → 0 failed; Testcontainer neu starten (Panel- und Python-Änderungen seit dem letzten Start), dann `python3 tests/integration/run_checks.py` → alle grün, einschließlich `run_undo` mit dem umgestellten Fall.

- [ ] **Step 3: Doku**

`docs/how-it-works.md`, Abschnitt »Badges« (beginnt mit `Badges sit outside card lists and views.`): den Satz ab `The same is true of any other named, non-card setting …` bis zum Ende des Absatzes ersetzen durch:

```markdown
Until badges get the same treatment ([issue #29](https://github.com/PPP01/ha-dashboard-history/issues/29)), that is how it stays for them. Named settings are different, and handled since <Datum> ([issue #28](https://github.com/PPP01/ha-dashboard-history/issues/28)): a view's `title`/`icon`/`theme`/`visible`, or a key in a dashboard's `strategy:` block, is identified by its name in every state. The history explains and counts such a change, and *Undo this change* takes it back after one check — is the value the change left still there? Section settings (`column_span` and the like) are not included: a section has no name to address it by.
```

Der ersetzte Satz trug auch den Verweis auf #29; der erste Satz oben hält ihn, damit der Badge-Satz davor nicht ohne Verweis bleibt (Review K4).

`docs/limitations.md`: Zeile »Badge added, edited, or deleted« der Tabelle bleibt (Vorhaben N). Neue Zeile nach ihr:

`| **View or dashboard setting** changed (`icon`, `strategy:` key, …) | Named, e.g. *the setting "icon" was changed* | **Exact** while the value is unchanged since | Not offered | **Works** |`

`docs/superpowers/status.md`: Eintrag `- **Umgesetzt am <Datum>** (GitHub-Issue [#28](…), Vorhaben M): …` nach dem Muster der Einträge zu #31–#33 – was jetzt erkannt, erklärt, gezählt und zurückgenommen wird, und was ausdrücklich nicht (Sections, `meta/`, Badges bis Vorhaben N).

`<Datum>` ist das Datum des Commits, `YYYY-MM-DD`.

- [ ] **Step 4: Commit (nach Go des Nutzers)**

```bash
git add tests/integration/run_checks.py docs/how-it-works.md docs/limitations.md docs/superpowers/status.md
git commit -m "Check and document undo of named settings" -m "The running instance confirms the history line, the explanation and the
undo of a view icon, a strategy key and a 1 that became true end to
end. run_undo's \"part the undo cannot reach\" was a renamed view title,
which is reachable now; a later save the undo keeps takes its place.
The docs stop saying that only cards are ever compared. GitHub #28."
```

---

## Self-review notes

- **Spec-Abdeckung:** Abschnitt 1 → Task 1; Abschnitt 2 (Tabelle, frühe Bedingung, alles-oder-nichts) → Task 3; Abschnitt 3 (Schrittform, Reihenfolge, erneute Prüfung) → Task 3 + 4; Abschnitt 4 (Wörter, Gruppe, Verlaufszeile, `_COUNT`) → Task 2 + 5; Test-Plan der Spec → Tasks 1–6.
- **Abhängigkeit zu L:** Task 3 setzt `rebuilt, shifted = _section_drift(...)` voraus und `UndoStep.parked`. Ist L noch nicht gebaut, zuerst L.
- **Typen:** `_ABSENT` verlässt `analyze.py` nie – in Schritten wird es zu `expect_absent`/`action="unset"` übersetzt, weil `restore.py` `analyze` nicht importieren darf.

## Review vom 2026-09-24 (Fable) und was daraus wurde

- **W1** (bestehender Test mit umbenannter Ansicht wird rot): Task 2, Step 7 stellt ihn auf eine Section-Einstellung um – nicht auf Badges, die mit N benennbar werden.
- **W2** (`1`/`true` nur in der Differenz getrennt): strenger Vergleich auch in `_apply_setting` (Task 4, `_same_value`), in `change_message` und in beiden Zustandsvergleichen von `async_undo_change` (Task 5, `_same_state`, im Executor). Live belegt in `run_settings`, weil `operations.py` in pytest nicht erreichbar ist.
- **W3** (Strategie-Dashboard live nicht geprüft): zweiter Durchgang in `run_settings`.
- **W4** (`_wait_until_recorded` greift die Revision davor): `save` in `run_settings` wartet mit `_wait_for_new_state`.
- **K1** (Übernahme eines Strategie-Dashboards hinterlässt `views: []`): `apply_undo` entfernt die leere Liste, wenn das Dashboard vorher keine hatte oder der Undo den ganzen `strategy`-Block zurückschreibt. Die erste Fassung (»`strategy` steht daneben«) entfernte in der Nachprüfung auch ein vorher schon vorhandenes `views: []` und ließ einen Undo ohne Schritte etwas zu schreiben finden; zwei Tests in Task 4.
- **K2, K3, K4, K5:** Docstring und Review-Fokus 4 abgeschwächt; Test »already back« mit zwei Einstellungen, erwartete Rot-Zahl korrigiert; #29-Verweis bleibt in der Doku; Prüfsummen-Hinweis durch »Container neu starten« ersetzt.
- **K7, K8:** Spec-Wortlaut an das tatsächliche Verhalten angepasst (eigener Satz für die fehlende Ansicht; `column_span` fällt an der frühen Bedingung, nicht an der Section-Prüfung).
- **K6** (innere Anführungszeichen in Werten): nicht übernommen – Ansichtsnamen stehen genauso unmaskiert in `"…"` (`the whole view "{label}"`), und eine Escape-Regel nur für Einstellungen wäre uneinheitlich (Vergleichsobjekt in der Nachprüfung korrigiert: Kartenbeschriftungen stehen gar nicht in Anführungszeichen); der Diff darunter zeigt den Wert exakt.
- **N1**, bei der Einarbeitung gefunden: `run_undo` brauchte einen Teil, den der Undo nicht erreicht, und nahm dafür einen Ansichtstitel. Task 6, Step 1b ersetzt ihn durch eine spätere Speicherung.

**Nachprüfung am 2026-09-25 (Fable):** alle Befunde adressiert, in der Simulation L Task 1 + M Task 1–5 durchgehend grün (834 passed). Daraus noch eingearbeitet: die engere K1-Bedingung (siehe oben); das Kartenbeispiel in der Begründung zu W2 (`show_state` an einer Tile-Karte statt `columns` an einem Grid, das nach der Korrektur als »1 removed, 1 added« zählt); das Vergleichsobjekt in der Begründung zu K6 (Ansichtsnamen, nicht Kartenbeschriftungen); zwei Prüfbefehle (Task 1 wählt den Block-Test mit aus, Task 2 in zwei Befehlen, weil pytest bei zwei `-k` nur das letzte auswertet). Live nicht ausführbar war in der Nachprüfung nur `run_checks.py` – ob Home Assistant einen Stand ohne `views:` unverändert zurückgibt, zeigt erst der Container.
