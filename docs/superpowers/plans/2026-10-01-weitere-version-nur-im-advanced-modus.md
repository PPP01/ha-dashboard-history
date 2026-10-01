# »Save this as another version« nur im Advanced-Modus – Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Im Simple-Modus verschwindet »Save this as a version«, sobald »Right now« aufgeräumt (blau) ist; im Advanced-Modus erscheint in diesem Fall stattdessen »Save this as another version« – nur in der ersten »Right now«-Box (GitHub Issue #50, verknüpft mit #14).

**Architecture:** Der Button wird an einer Stelle gezeichnet (`saveButton` in `panel/rows.js`, neben `undoButton`), damit die drei Beschriftungsfälle nicht auseinanderlaufen. Der Simple-Modus lässt ihn bei `standingOn` weg. Im Advanced-Modus gibt es drei aufgeräumte Formen von »Right now«, alle bekommen den Button: die Box nach einem Revert und den Banner hinter einem Tag, wenn die Live-Konfiguration einer älteren Version gleicht (beide über `_nowActs` mit Treffer), und den gekrönten Versionsabschnitt (`versionHead` mit `crowned`, nur der erste von mehreren gestapelten). Rein Panel und Doku; kein Server-, Service- oder Speicher-Code.

**Tech Stack:** Plain Custom Element ohne Build-Schritt (`panel.js`, `panel/*.js`), pytest mit Node-Stand-in für Panel-Logik (`tests/test_panel_behaviour.py`).

**Spec:** Kein eigenes Spec-Dokument. Bindend ist Issue #50 (Anzeige, Ziel); der größere Rahmen steht in #14. Die Spec `specs/2026-08-30-dashboard-history-design.md` bleibt bei Widersprüchen bindend; berührt wird nur Entscheidung 7 am Rande (`create_version` bleibt ohne Bestätigung, unverändert).

## Ausgangslage und Basis

- **Basis ist `main` nach dem Merge von `issue-49-unversioned-marker`.** Dieser Plan wurde gegen den Stand dieses Branches gelesen; der Branch berührt die Dashboard-Liste links, nicht den »Right now«-Block. Die Anker unten sind deshalb **Funktionsnamen**, keine Zeilennummern. Wer auf einen Anker stößt, der nicht mehr passt, hält an und meldet es.
- Branch: `issue-50-save-another-version`, von `main`. Die Plan-Datei selbst wird als erster Commit auf diesen Branch gelegt (`[50] Add the plan for #50`), zusammen mit den Review-Dateien dazu, falls vorhanden. Danach folgen genau **drei Umsetzungs-Commits**, einer je Aufgabe; insgesamt also vier Commits auf dem Branch.
- **Begriffe** (so benutzt der Plan sie): *aufgeräumt/settled* = »Right now« ist blau, der Stand trägt eine Version oder gleicht einer. *unaufgeräumt/unsettled* = orange, nichts Aufgezeichnetes hält den Stand.

## Minimaler Umfang (und was bewusst nicht getan wird)

Getan:
1. Simple, aufgeräumt: Button weg. Simple, unaufgeräumt und »noch keine Versionen«: unverändert.
2. Advanced, aufgeräumt: Button »Save this as another version« in der ersten »Right now«-Box (alle drei Formen: gekrönter Versionsabschnitt, Box nach Revert, Banner hinter einem Tag mit Treffer auf eine ältere Version).
3. FAQ und User-Guide um den Moduswechsel ergänzen.

Bewusst **nicht** getan:
- **Kein Bestätigungs-Overlay** vor dem Versionsdialog (eigener Folgeschritt, eigener Plan).
- **Kein Umbenennen der Nummer** (bleibt #14).
- Kein Server-, Service-, WebSocket- oder Speicher-Code; der Versionsdialog selbst bleibt unverändert (auch sein Hinweis `data-carries`).
- Keine Änderung an »Version up to here« in den Zeilen. Der erste Eintrag in einer unaufgeräumten Box behält beide Einstiege (Box-Button und »Version up to here« lösen dasselbe aus; die Doppelung besteht schon und ist entschieden).
- Kein Refactoring von `_nowActs`/`versionHead` über das Nötige hinaus.

## Global Constraints

- **Sprache:** Code, Kommentare, Docstrings, Commit-Messages, FAQ und User-Guide englisch; dieser Plan ist deutsch (Projekt-Konvention für `docs/superpowers/`).
- **Keine Backticks und kein `${` in `panel/style.js`**, auch nicht in CSS-Kommentaren: `tests/test_panel_assets.py::test_the_style_is_one_unbroken_template_literal` und `::test_no_substitution_hides_in_the_stylesheet` prüfen das.
- **Kein neuer Click-Handler.** Der vorhandene `onClick("[data-version]", …)` bleibt zuständig; `onClick` verhindert das Auf-/Zuklappen für jedes Element in einem `<summary>` schon zentral (`element.closest("summary")` → `preventDefault`).
- `tools/complexity_ratchet.py` und `lint-imports` bleiben grün; die Baseline `tools/complexity-baseline.json` wird nicht angefasst (nur JS-Änderungen, ruff sieht sie nicht).
- **Zwei bestehende Test-Assertions kippen** und werden in den Aufgaben ausdrücklich geändert (Aufgabe 1: `boxSave`, Aufgabe 2: `noSaveButton`). Sonst wird kein bestehender Test geändert.
- **Commits:** Englisch, Imperativ im Subject, höchstens 50 Zeichen, Leerzeile, Body mit dem *Warum*, höchstens 72 Zeichen je Zeile, Schluss `Refs #50.` (letzter Commit: `Closes #50.`). Eine Commit-Message behauptet nur, was dieser Commit ändert.
- **Kein Push, kein Tag, kein Merge** ohne ausdrückliches Go des Nutzers.

## Review Focus

Eingaben und Zustände, die der Plan nicht ausdrücklich nennt, aber die jemanden beißen können – jede Zeile hat unten in der besitzenden Aufgabe ihren Test:

1. **Zwei Versionen auf demselben neuesten Commit** (gestapelte, beide gekrönte Boxen, wie im Screenshot zu #50): der Button erscheint genau **einmal**, nicht in jeder Box. (Aufgabe 2)
2. **Revert-Fall im Advanced-Modus** (Inhalt gleicht einer älteren Version, nichts gekrönt): Button »another« erscheint, »Undo / Go back to« nicht. (Aufgabe 2)
3. **Simple, Stand gleicht einer *älteren* Version** (aufgeräumt, aber `merged` ist falsch): trotzdem kein Button. (Aufgabe 1)
4. **Simple, noch keine Versionen:** der Button bleibt, er ist der einzige Weg zur ersten Version. (Aufgabe 1)
5. **Versionen noch nicht geladen** im Advanced-Modus: weiterhin keine Buttons (bestehender Test `noButtons`, bleibt grün; Aufgabe 2 prüft ihn mit). Gelöschte Dashboards können nicht gekrönt sein, weil `same_as_now` gegen die Live-Konfiguration rechnet – das wird in Aufgabe 2, Schritt 1 gegengelesen, nicht angenommen.
6. **Banner hinter einem Tag, benannt:** Die neueste Änderung trägt eine Version, ist aber nicht `same_as_now` (Änderung an Home Assistant vorbei), und die Live-Konfiguration gleicht einer *älteren* Version. `matching_versions` kommt vom Server über alle Versionen, der Banner (`_renderNowBanner`) ist dann benannt und zeichnet über `_nowActs` den »another«-Button, ohne Undo. (Aufgabe 2; Befund des Terra-Reviews, Runde 1.)

---

### Task 1: Gemeinsamer Button und Simple-Modus

**Files:**
- Modify: `custom_components/dashboard_history/panel/rows.js` (neue Funktion `saveButton`, neben `undoButton`)
- Modify: `custom_components/dashboard_history/panel/simple.js` (Import und beide Verwendungsstellen: Leerzustand »no versions yet« und `nowHead` in der Simple-Ansicht)
- Modify: `custom_components/dashboard_history/panel.js` (Import-Zeilen: Variable und Destrukturierung neben `undoButton`)
- Test: `tests/test_panel_behaviour.py`

**Interfaces:**
- Produces: `saveButton({ another = false } = {})` aus `panel/rows.js` – liefert den HTML-String eines `<button class="act ghost" data-version="now">`. Text: `Save this as a version` bei `another: false`, `Save this as another version` bei `another: true`. Aufgabe 2 benutzt `saveButton({ another: true })`.

- [ ] **Step 1: Ausgangslage lesen**

Lesen: `rows.js` (`undoButton` und seinen Kommentar), `simple.js` (die Stellen mit `data-version="now"`, das sind genau zwei, und `standingOn`/`undo`/`nowHead`), `panel.js` (`let sections, someNames, … undoButton;` und die Destrukturierung darunter). Bestätigen mit:

Run: `grep -n 'data-version="now"' custom_components/dashboard_history/panel.js custom_components/dashboard_history/panel/*.js`
Expected: drei Treffer – zwei in `simple.js`, einer in `panel.js` (`_nowActs`). Weicht die Zahl ab: anhalten und melden.

- [ ] **Step 2: Failing tests schreiben**

In `tests/test_panel_behaviour.py` nach `_SIMPLE_NOW`/seinen Tests ein neues Szenario und Fixture anfügen (am Ende der Simple-Tests, vor dem nächsten Abschnittskopf):

```python
_SIMPLE_SAVE_BUTTON = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._mode = "simple";
el._dashboards = [{ key: "dash", title: "Dash", exists: true }];
const marked = { revision: "c", message: "3 cards removed",
                 versions: [{ name: "dash/v1.2.0" }], timestamp: 3 };
const since = { revision: "a", message: "1 card added", versions: [], timestamp: 4 };
const version = (name, same, revision) => ({
  name, title: name, description: "", revision, same_as_now: same, timestamp: 1,
});

// Settled, standing on the newest version: no button.
el._versions = [version("dash/v1.2.0", true, "c")];
el._changes = [marked];
const settledOnNewest = el._renderMain();

// Settled, standing on an OLDER version's state (what going back leaves):
// newer versions are drawn above it, the block is not merged - and still
// settled, so still no button.
el._versions = [version("dash/v1.2.0", false, "c"), version("dash/v1.0.0", true, "e")];
el._changes = [since, marked];
const settledOnOlder = el._renderMain();

// Unsettled: nothing holds the state. The button stays, plain wording.
el._versions = [version("dash/v1.2.0", false, "c")];
el._changes = [since, marked];
const unsettled = el._renderMain();

// No version at all: the button is the only way to make the first one.
el._versions = [];
el._changes = [since];
const none = el._renderMain();

console.log(JSON.stringify({
  settledOnNewest: { button: settledOnNewest.includes('data-version="now"') },
  settledOnOlder: { button: settledOnOlder.includes('data-version="now"') },
  unsettled: {
    button: unsettled.includes('data-version="now"'),
    plain: unsettled.includes(">Save this as a version<"),
    noAnother: !unsettled.includes("another version"),
  },
  none: {
    button: none.includes('data-version="now"'),
    plain: none.includes(">Save this as a version<"),
  },
}));
"""


@pytest.fixture(scope="session")
def simple_save_button(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "simple_save_button", _SIMPLE_SAVE_BUTTON)


def test_a_settled_simple_box_offers_no_save_button(simple_save_button):
    # Issue #50. The box already names the version that holds this state;
    # a button that saves it again is an offer that has to be walked back
    # in a dialog. The way to a second version is the advanced mode.
    assert simple_save_button["settledOnNewest"]["button"] is False


def test_a_simple_box_standing_on_an_older_versions_state_offers_no_save_button(
    simple_save_button,
):
    assert simple_save_button["settledOnOlder"]["button"] is False


def test_an_unsettled_simple_box_keeps_the_plain_save_button(simple_save_button):
    assert simple_save_button["unsettled"]["button"] is True
    assert simple_save_button["unsettled"]["plain"] is True
    assert simple_save_button["unsettled"]["noAnother"] is True


def test_the_simple_mode_without_versions_still_offers_the_first_one(
    simple_save_button,
):
    assert simple_save_button["none"]["button"] is True
    assert simple_save_button["none"]["plain"] is True
```

Außerdem die bestehende Assertion umkehren, in `test_the_merged_block_keeps_what_the_row_could_do`: die letzte Zeile `assert simple_mode["plain"]["boxSave"] is True` entfällt dort (Pen und Bin bleiben) – die Aussage steht jetzt im Test oben, nicht mehr hier.

- [ ] **Step 3: Tests laufen lassen, Fehlschlag prüfen**

Run: `python3 -m pytest tests/test_panel_behaviour.py -q -p no:cacheprovider -k "save_button or without_versions_still or merged_block_keeps"`
Expected: `test_a_settled_simple_box_offers_no_save_button` und `test_a_simple_box_standing_on_an_older…` FAIL (Button ist heute immer da); `test_an_unsettled…` und `test_the_simple_mode_without_versions…` PASS (heutiges Verhalten, pinnen es nur fest); `test_the_merged_block_keeps_what_the_row_could_do` PASS. Erwartet: genau zwei FAIL. Skipt der Lauf wegen fehlendem `node`: anhalten und melden – Panel-Tests laufen dann nicht.

- [ ] **Step 4: `saveButton` in `rows.js` anlegen**

Direkt unter `undoButton` (gleiche Datei, gleicher Stil) einfügen:

```js
/**
 * The button that names the state the dashboard holds right now as a
 * version. Exported beside `undoButton` for the same reason: every
 * place that offers it draws one control, not three that drift.
 *
 * `another` is for a state that is already named. The first press on a
 * state nothing holds is a decision about a name; on a state a version
 * holds, it is a second name for the same content, and the word says
 * so before the dialog has to (GitHub #50).
 */
export function saveButton({ another = false } = {}) {
  return `<button class="act ghost" data-version="now"
               >Save this as ${another ? "another" : "a"} version</button>`;
}
```

- [ ] **Step 5: Import in `panel.js` und `simple.js`**

`panel.js`: in der Zeile `let sections, someNames, renderRow, versionHead, currentStateRow, nowChip, undoButton;` und der Destrukturierung darunter `saveButton` ergänzen (Reihenfolge: nach `undoButton`). `simple.js`: die Zeile `const { nowChip, pen, bin, undoButton } = await import(…rows.js…)` um `saveButton` ergänzen.

- [ ] **Step 6: Beide Stellen in `simple.js` umstellen**

Leerzustand: `<button class="act ghost" data-version="now">Save this as a version</button>` → `${saveButton()}`.

`nowHead`: den Block

```js
      <span class="acts">
        <button class="act ghost" data-version="now">Save this as a version</button>
        ${undo}
      </span>`;
```

ersetzen durch einen vorab berechneten Block, der bei aufgeräumtem Stand ganz entfällt (`undo` ist bei `standingOn` ohnehin leer, ein leeres `<span class="acts">` soll nicht übrig bleiben):

```js
  // Settled (blue): the block already names the version that holds this
  // state, so there is nothing to save and nothing to undo. The way to a
  // second version is the advanced mode (GitHub #50).
  const acts = standingOn
    ? ""
    : `<span class="acts">${saveButton()}${undo}</span>`;
```

und in `nowHead` an der Stelle des alten `<span class="acts">…</span>` einfach `${acts}` einsetzen. Die Definition von `acts` steht **nach** `undo` und **vor** `nowHead`.

- [ ] **Step 7: Tests laufen lassen**

Run: `python3 -m pytest tests/test_panel_behaviour.py -q -p no:cacheprovider`
Expected: alle PASS, inklusive der vier neuen. Danach die ganze Suite: `python3 -m pytest tests/ -q -p no:cacheprovider` → `0 failed` (die Zahl der passed/skipped schwankt mit den echten Dashboards, nur »0 failed« zählt).

- [ ] **Step 8: Commit**

```bash
git add custom_components/dashboard_history/panel/rows.js custom_components/dashboard_history/panel/simple.js custom_components/dashboard_history/panel.js tests/test_panel_behaviour.py
git commit
```

Message:

```
[50] Drop the save button from a settled simple box

When "Right now" already names the version that holds the state, the
button offered to save the same state again - an offer the create
dialog then had to walk back. The simple mode is the one meant for
people who do not want to think about that, so the button now shows
only where nothing recorded holds the state, or where no version
exists yet. Drawn through one helper so the advanced mode can reuse
it with its own wording.

Refs #50.
```

---

### Task 2: Advanced-Modus – »Save this as another version«

**Files:**
- Modify: `custom_components/dashboard_history/panel.js` (`_nowActs`, `_renderVersionHead`, die `section.versions.map` in `_renderMain`/der Liste der Abschnitte)
- Modify: `custom_components/dashboard_history/panel/rows.js` (`versionHead`: neuer Parameter `saveAnother`)
- Modify: `custom_components/dashboard_history/panel/style.js` (eine CSS-Regel für `.acts` im `details.ver`-Kopf)
- Test: `tests/test_panel_behaviour.py`

**Interfaces:**
- Consumes: `saveButton({ another })` aus Aufgabe 1 (in `panel.js` bereits destrukturiert, in `rows.js` in derselben Datei).
- Produces: `versionHead({ …, saveAnother = false })` – bei `true` zeichnet der Kopf im `<summary>` unterhalb der Beschreibung `<span class="acts">` mit `saveButton({ another: true })`. `_renderVersionHead(section, version, crowned = false, another = false)` reicht das durch.

- [ ] **Step 1: Ausgangslage lesen und zwei Annahmen belegen**

Lesen: `_nowActs`, `_nowFacts`, `_renderNowSection` und `_renderVersionHead` in `panel.js`; `versionHead` in `rows.js` (Parameterliste, `crowned`, die schließende `</summary>`-Stelle); in `panel.js` die Stelle mit `const crowned = sectionIndex === 0 && …` und `section.versions.map((version) => {`.

Belegen, nicht annehmen: (a) ein gelöschtes Dashboard kann nicht gekrönt sein – Run: `sed -n 485,512p custom_components/dashboard_history/operations.py` und die Stelle lesen, an der `same_as_now` je Eintrag gesetzt wird (`async_history`): rechnet es gegen `async_get_config`, das für ein nicht vorhandenes Dashboard `None` liefert, bleibt `same` leer. Trifft das nicht zu, anhalten und melden – dann braucht `saveAnother` zusätzlich die Bedingung `exists`. (b) Es gibt drei aufgeräumte Formen, nicht zwei. `_renderNowBanner` (neueste Änderung getaggt, aber nicht `same_as_now`) ist unaufgeräumt, wenn `matching` leer ist, und **benannt**, wenn die Live-Konfiguration einer älteren Version gleicht: `matching` kommt aus `_versionsMatchingNow()` über alle Versionen des Servers, unabhängig von der neuesten Änderung. Im zweiten Fall zeichnet `_nowActs` schon über die Änderung aus Schritt 4 den »another«-Button; der Test dafür steht in Schritt 2. Das gegenlesen: `_renderMain` (Bedingung für `behind`), `_nowFacts`, `_versionsMatchingNow`.

- [ ] **Step 2: Failing tests schreiben**

Neues Szenario und Fixture nach den `advanced_now_box`-Tests:

```python
_ADVANCED_SAVE_ANOTHER = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._mode = "advanced";
const count = (text, needle) => text.split(needle).length - 1;
const ANOTHER = "Save this as another version";

// Crowned: the newest change carries a version and is what the dashboard
// holds right now - that version's own section is the "Right now" box.
el._changes = [
  { revision: "a", message: "1 card added",
    versions: [{ name: "dash/v1.0.0", title: "First", timestamp: 1 }],
    same_as_now: true, timestamp: 1 },
];
el._versions = [
  { name: "dash/v1.0.0", title: "First", same_as_now: true, revision: "a" },
];
el._matching = [];
const crowned = el._renderMain();

// Two versions on the same newest commit: two stacked crowned boxes.
el._changes = [
  { revision: "a", message: "1 card added",
    versions: [
      { name: "dash/v1.0.0", title: "First", timestamp: 1 },
      { name: "dash/v1.0.1", title: "Second", timestamp: 2 },
    ],
    same_as_now: true, timestamp: 2 },
];
el._versions = [
  { name: "dash/v1.0.1", title: "Second", same_as_now: true, revision: "a" },
  { name: "dash/v1.0.0", title: "First", same_as_now: true, revision: "a" },
];
const stacked = el._renderMain();

// Reverted: nothing crowned, an older version holds the same content.
el._changes = [
  { revision: "b", message: "2 cards moved", versions: [], same_as_now: true, timestamp: 2 },
  { revision: "a", message: "1 card added", versions: [{ name: "dash/v1.0.0" }],
    same_as_now: false, timestamp: 1 },
];
el._versions = [
  { name: "dash/v1.0.0", title: "First", same_as_now: false, revision: "a" },
];
el._matching = [{ name: "dash/v1.0.0" }];
const reverted = el._renderMain();

// Banner behind a tag, named: the newest change carries a version but
// is not what the dashboard holds (a change at Home Assistant's back),
// and an OLDER version holds exactly what the dashboard holds now.
el._changes = [
  { revision: "a", message: "1 card added", versions: [{ name: "dash/v1.1.0" }],
    same_as_now: false, timestamp: 3 },
  { revision: "b", message: "2 cards moved", versions: [{ name: "dash/v1.0.0" }],
    same_as_now: false, timestamp: 1 },
];
el._versions = [
  { name: "dash/v1.1.0", title: "Second", same_as_now: false, revision: "a" },
  { name: "dash/v1.0.0", title: "First", same_as_now: true, revision: "b" },
];
el._matching = [{ name: "dash/v1.0.0" }];
const namedBanner = el._renderMain();

// Unsettled: the wording stays plain, as before.
el._changes = [
  { revision: "a", message: "1 card added", versions: [], same_as_now: false, timestamp: 2 },
  { revision: "b", message: "2 cards moved", versions: [{ name: "dash/v1.0.0" }],
    same_as_now: false, timestamp: 1 },
];
el._matching = [];
const unsettled = el._renderMain();

// Not yet loaded: no buttons at all, as before.
el._versionsLoaded = false;
const loading = el._renderMain();

console.log(JSON.stringify({
  crowned: { another: count(crowned, ANOTHER), plain: count(crowned, ">Save this as a version<") },
  stacked: { another: count(stacked, ANOTHER), boxes: count(stacked, 'class="ver now"') },
  reverted: {
    another: count(reverted, ANOTHER),
    plain: count(reverted, ">Save this as a version<"),
    noUndo: !reverted.includes("Undo / Go back to"),
  },
  namedBanner: {
    banner: namedBanner.includes('class="now-panel now-head named"'),
    another: count(namedBanner, ANOTHER),
    plain: count(namedBanner, ">Save this as a version<"),
    noUndo: !namedBanner.includes("Undo / Go back to"),
  },
  unsettled: {
    plain: count(unsettled, ">Save this as a version<"),
    another: count(unsettled, ANOTHER),
  },
  loading: { buttons: count(loading, 'data-version="now"') },
}));
"""


@pytest.fixture(scope="session")
def advanced_save_another(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "advanced_save_another", _ADVANCED_SAVE_ANOTHER)


def test_a_crowned_version_box_offers_another_version(advanced_save_another):
    assert advanced_save_another["crowned"]["another"] == 1
    assert advanced_save_another["crowned"]["plain"] == 0


def test_only_the_first_of_several_stacked_boxes_carries_the_button(
    advanced_save_another,
):
    # Two versions on one commit draw two crowned boxes; one button for
    # one state, in the first box.
    assert advanced_save_another["stacked"]["boxes"] == 2
    assert advanced_save_another["stacked"]["another"] == 1


def test_a_reverted_state_offers_another_version_and_no_undo(advanced_save_another):
    assert advanced_save_another["reverted"]["another"] == 1
    assert advanced_save_another["reverted"]["plain"] == 0
    assert advanced_save_another["reverted"]["noUndo"] is True


def test_a_named_banner_behind_a_tag_offers_another_version_and_no_undo(
    advanced_save_another,
):
    # The newest change carries a version but is not the live state, and
    # an older version holds the live content: settled, though drawn as
    # the bodyless banner rather than a crowned section or a folded box.
    assert advanced_save_another["namedBanner"]["banner"] is True
    assert advanced_save_another["namedBanner"]["another"] == 1
    assert advanced_save_another["namedBanner"]["plain"] == 0
    assert advanced_save_another["namedBanner"]["noUndo"] is True


def test_an_unsettled_advanced_box_keeps_the_plain_wording(advanced_save_another):
    assert advanced_save_another["unsettled"]["plain"] == 1
    assert advanced_save_another["unsettled"]["another"] == 0


def test_no_save_button_before_the_versions_have_loaded(advanced_save_another):
    assert advanced_save_another["loading"]["buttons"] == 0
```

Die bestehende, jetzt falsche Assertion ändern. Im Szenario `_ADVANCED_NOW_BOX`, Abschnitt `matched`, die Zeile
`noSaveButton: !matched.includes('data-version="now"'),` ersetzen durch
`anotherButton: matched.includes("Save this as another version"),`
und das zugehörige Kommentarstück darüber (»No way back is offered onto a state already known to be held somewhere – the same rule a version's own row follows.«) so kürzen, dass es nur noch den Undo-Teil trägt (`noUndoButton` bleibt). In `test_a_named_match_wins_over_the_drift_sentence` die Zeile
`assert advanced_now_box["matched"]["noSaveButton"] is True`
ersetzen durch
`assert advanced_now_box["matched"]["anotherButton"] is True`
und den Kommentar der Funktion um den Halbsatz ergänzen, dass die Box statt eines Rückwegs den Weg zu einem zweiten Namen anbietet (#50).

- [ ] **Step 3: Tests laufen lassen, Fehlschlag prüfen**

Run: `python3 -m pytest tests/test_panel_behaviour.py -q -p no:cacheprovider -k "another or stacked or reverted_state or named_match or before_the_versions"`
Expected: `crowned`, `stacked`, `reverted`, `named_banner`, `named_match` FAIL; `unsettled` und `loading` PASS (heutiges Verhalten). Der Filter oben um `named_banner` ergänzen: `-k "another or stacked or reverted_state or named_match or named_banner or before_the_versions"`. Abweichung: anhalten und die Ursache klären, nicht den Test anpassen.

- [ ] **Step 4: `_nowActs` umstellen (panel.js)**

Ersetzen (Docstring und Rumpf):

```js
  /**
   * The buttons the simple mode's own "right now" box offers where
   * nothing recorded matches - saving the live state as a version, and
   * undoing back to the last one there is. Reused here rather than
   * redrawn, because a person switching modes mid-task should find the
   * same way out in both.
   *
   * Where something recorded does match, the state is already named and
   * there is nothing to undo to: only the second name is on offer, here
   * and not in the simple mode (GitHub #50).
   */
  _nowActs(matching) {
    if (matching.length)
      return `<span class="acts">${saveButton({ another: true })}</span>`;
    const undo = this._versions.length ? undoButton(this._versions[0]) : "";
    return `<span class="acts">${saveButton()}${undo}</span>`;
  }
```

- [ ] **Step 5: Gekrönte Box (panel.js und rows.js)**

`panel.js`: `_renderVersionHead(section, version, crowned = false, another = false)` und im Aufruf von `versionHead({ … crowned, saveAnother: another })`. In der Abschnittsschleife `section.versions.map((version) => {` → `section.versions.map((version, position) => {` und den Aufruf zu `this._renderVersionHead(section, version, crowned, crowned && position === 0)`.

`rows.js`, `versionHead`: Parameter `saveAnother = false` ergänzen (neben `crowned = false`), Kommentar zum Parameter: »The first crowned box only: one state gets one button, however many versions are stacked on it.« Direkt nach der Zeile mit `version.description` und vor dem `</summary>` einfügen:

```js
      ${saveAnother ? `<span class="acts">${saveButton({ another: true })}</span>` : ""}
```

- [ ] **Step 6: CSS-Regel (style.js)**

Nach der Regel `details.ver > summary .why { margin: 4px 0 0 19px; }` einfügen (keine Backticks, kein `${`, auch nicht im Kommentar):

```css
  details.ver > summary .acts { display: flex; flex-wrap: wrap; gap: 8px;
    margin: 10px 0 0 19px; }
```

- [ ] **Step 7: Tests laufen lassen**

Run: `python3 -m pytest tests/ -q -p no:cacheprovider`
Expected: `0 failed`, insbesondere `tests/test_panel_assets.py` (CSS-Regeln) und alle neuen Tests PASS. Danach `python3 tools/complexity_ratchet.py` und `lint-imports` (laut CLAUDE.md, in einem Virtualenv): beide grün.

- [ ] **Step 8: Commit**

```bash
git add custom_components/dashboard_history/panel.js custom_components/dashboard_history/panel/rows.js custom_components/dashboard_history/panel/style.js tests/test_panel_behaviour.py
git commit
```

Message:

```
[50] Offer another version from the advanced box

Taking the button out of the simple mode's settled box left no way to
give a state a second name. The advanced mode gets it, worded for what
it is: "Save this as another version". Both settled shapes carry it -
the version section that is the "Right now" element, and the box that
appears after going back to an older version - and with several
versions stacked on one state, only the first box does.

Refs #50.
```

---

### Task 3: Doku und Prüfung am laufenden Panel

> **Zur Reproduzierbarkeit:** Die Schritte 1 und 4 brauchen eine laufende Test-Instanz, deren Konfiguration und Token bewusst außerhalb des Repos liegen (`docker/README.md`). Sie sind deshalb **lokale Abnahme, kein Pflichtschritt für den Commit**. Wer keine Instanz hat, schreibt in den Bericht »nicht ausgeführt: keine lokale Testinstanz« und macht trotzdem Schritt 2, 3, 5 und 6. Für Schritt 2 gilt dann eine Einschränkung: der FAQ-Satz über das Entfernen einer Version im Simple-Modus stützt sich nur auf den Code; ohne die Gegenprobe in Schritt 1 wird er in der FAQ **nicht** neu formuliert, sondern der bisherige Absatz »Or take the wrong one away« bleibt unangetastet. Das Ergebnis jeder Prüfung steht in der Antwort des Umsetzers an den Nutzer (Abschlussbericht), nicht im Repo.

**Files:**
- Modify: `FAQ.md` (Abschnitt »What to do instead«, erster Absatz)
- Modify: `docs/user-guide.md` (Simple View: Aufzählung zum Current-state-Kasten; Advanced View: eine Zeile)

- [ ] **Step 1: Behauptung der FAQ im Panel belegen, bevor sie geschrieben wird**

Die FAQ soll sagen, dass im Simple-Modus der Weg »falsche Version entfernen, dann neu anlegen« ohne Moduswechsel geht. Das ist bisher aus dem Code abgeleitet, nicht gesehen. Im Test-Container (`docker compose -f docker/compose.yaml up -d`, Panel im Browser öffnen; Konfiguration und Token liegen außerhalb des Repos, siehe `docker/README.md`; **nicht** in die Live-Installation) mit einem Wegwerf-Dashboard prüfen: Version anlegen → Simple zeigt blauen Kasten ohne Button → Papierkorb an dieser Version → Kasten wird orange, »Save this as a version« ist wieder da. Ergebnis (gesehen / nicht gesehen) im Bericht festhalten. Erscheint der Button nicht wieder, anhalten: dann stimmt der Satz nicht und die FAQ-Änderung muss anders lauten.

- [ ] **Step 2: FAQ ändern**

In `FAQ.md`, Abschnitt »What to do instead«, den ersten Absatz (»**Put a second version beside the first.** That is one click …«) ersetzen durch:

```markdown
**Put a second version beside the first.** In the simple view that
offer is gone once the dashboard stands on a version: the box already
names it, and a button that saved the same state again was an offer you
had to walk back. Switch to the **advanced** view instead — the "Right
now" box there says **Save this as another version**. It costs nothing
and it loses nothing: the old version stays exactly where it is, still
pointing at its state. Two versions on one state is allowed and normal —
after going back to an older state, a fresh name for it is often
precisely what you want.
```

Der folgende Absatz (»This works because versions group and never squash …«) und »Or take the wrong one away« bleiben unverändert.

- [ ] **Step 3: User-Guide ändern**

`docs/user-guide.md`, Simple View, Zeile »If changes were made since the last version, it displays **Undo / Go back to <version>** and **Save this as a version**.« bleibt wörtlich richtig. Darunter als neue Unterzeile ergänzen:

```markdown
  - Once the dashboard stands on a version, the box offers neither: to give the same state a second name, switch to the advanced view.
```

Im Abschnitt Advanced View an die Aufzählung anfügen:

```markdown
- The **Right now** box carries **Save this as a version** while the dashboard has changed since the last version, and **Save this as another version** while it stands on one — the simple view only has the first.
```

- [ ] **Step 4: Sichtprüfung der Optik im Test-Container**

Die Wertungen aus den Tests sagen nichts über die Optik. Im Test-Container ansehen: (1) Advanced, ein Dashboard, das auf der neuesten Version steht: der Button sitzt unter Titel und Beschreibung im gekrönten Kopf, bricht auf schmalem Fenster um, klappt die Box beim Klicken **nicht** zu und öffnet den Versionsdialog; (2) gestapelte Boxen (zwei Versionen auf einem Stand): nur die erste trägt den Button; (3) Revert-Fall: Box zeigt »another«, kein »Undo«. Gesehen/nicht gesehen je Punkt im Bericht festhalten; kein Screenshot mit Pfaden oder Details der eigenen Installation ins Repo legen.

- [ ] **Step 5: Gesamtprüfung**

Run: `python3 -m pytest tests/ -q -p no:cacheprovider` → `0 failed`.
Run: `python3 tools/complexity_ratchet.py` und `lint-imports` → beide grün.

- [ ] **Step 6: Commit**

```bash
git add FAQ.md docs/user-guide.md
git commit
```

Message:

```
[50] Point the second-version advice at advanced

The FAQ's remedy "put a second version beside the first" assumed a
button the simple view no longer shows on a settled state. It now names
the advanced view and its "Save this as another version", and the user
guide says the same where each view is described. Removing a wrong
version and creating the right one still works in the simple view, so
that remedy stays as it was.

Closes #50.
```

---

## Self-Review (vom Plan-Autor ausgeführt)

- **Abdeckung des Issues #50:** Simple aufgeräumt/unaufgeräumt/leer → Aufgabe 1; Advanced beide aufgeräumte Formen und »nur die erste Box« → Aufgabe 2; FAQ-Schritt und Moduswechsel → Aufgabe 3; die im Issue genannten Randbedingungen (Button im `<summary>`, bestehende Tests) → Global Constraints und die zwei benannten Assertion-Wechsel.
- **Platzhalter-Suche:** keine offenen Stellen. Der einzige bewusst offene Punkt ist Aufgabe 2, Schritt 1 (a): eine Gegenlesung mit Abbruchbedingung, kein TODO.
- **Typkonsistenz:** `saveButton({ another })` (Aufgabe 1) wird in Aufgabe 2 unverändert benutzt; `saveAnother` (Parameter von `versionHead`) und `another` (4. Parameter von `_renderVersionHead`) sind je einmal definiert und durchgereicht.
- **Review Focus:** Zeilen 1–4 haben je einen Test; Zeile 5 ist teils vorhandener Test (`noButtons`) und teils Gegenlesung.
- **Reproduzierbarkeit:** Der Plan ruft nur committete Dateien, Funktionsnamen und Standardbefehle auf; es gibt keine Abhängigkeit von lokalen Änderungen. Der Browser-Teil (Aufgabe 3, Schritte 1 und 4) ist als Handarbeit im Test-Container benannt und kein Test.
