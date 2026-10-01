# Rückfrage vor einer weiteren Version – Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wer eine Version für einen Stand anlegen will, den schon eine Version trägt oder dem eine Version gleicht, wird vor dem Versionsdialog einmal gefragt, ob er wirklich noch einen Namen für denselben Stand will; bei »nein« endet der Vorgang dort (GitHub Issue #51, folgt auf #50, verknüpft mit #14).

**Architecture:** Eine Stelle, eine Bedingung. `_createVersion(revision)` in `panel.js` ist der gemeinsame Einstieg für »Save this as another version« und »Version up to here«; dort fragt ein neuer Aufruf `_askAnother(named)` vor allem anderen, wenn `_alreadyNamed(change)` einen Satz liefert. Die Rückfrage benutzt den vorhandenen Bestätigungsdialog über `_confirmOverride`, der Titel und Beschriftungen als Parameter bekommt (Standardwerte unverändert für die zwei bestehenden Aufrufer, die auf `dialog.confirm` und `dialog.replace` arbeiten). Rein Panel und Doku, kein Server-, Service- oder Speicher-Code.

**Review-Stand:** Dieser Plan wurde am 2026-10-01 von zwei unabhängigen Läufen geprüft (Codex Terra und Gemini, Runde 1; `reviews/2026-10-01-rueckfrage-vor-weiterer-version-review-1-terra.md` und `-gemini.md`). Beide meldeten unabhängig dieselben zwei Testlücken, beide sind in dieser Fassung geschlossen: der Ja-Test bestand schon ohne Umsetzung und belegte die Frage nicht (er prüft jetzt, dass sie offen war und nach der Antwort zu ist), und Suchtreffer (`_found`) liefen nicht durch die Tests (neuer Fall). Gemini fand außerdem eine Ungenauigkeit: Der zweite Aufrufer von `_confirmOverride` benutzt `dialog.replace`, nicht `dialog.confirm`; Text und Gegenlesung sind angepasst. Keine kritischen oder hohen Befunde; Astra war nicht nötig.

**Tech Stack:** Plain Custom Element ohne Build-Schritt (`panel.js`), pytest mit Node-Stand-in für Panel-Logik (`tests/test_panel_behaviour.py`).

**Spec:** Kein eigenes Spec-Dokument. Bindend ist Issue #51; der Rahmen steht in #50 (der Button) und #14 (Nummer bearbeiten). Die Spec `specs/2026-08-30-dashboard-history-design.md` bleibt bei Widersprüchen bindend; berührt wird Entscheidung 7 am Rande: `create_version` bleibt ohne `confirm` (die Vorschau-Regel gilt für Dashboard-Änderungen, hier wird nur ein Klick abgesichert).

## Ausgangslage und Basis

- **Basis ist `main` ab `1e486b6`** (Stand nach #50). Branch: `issue-51-ask-before-another-version`, von `main`. Die Plan-Datei selbst wird als erster Commit auf diesen Branch gelegt (`[51] Add the plan for #51`), zusammen mit Review-Dateien dazu, falls vorhanden. Danach folgen genau **zwei Umsetzungs-Commits**, einer je Aufgabe. Zusammen mit den Korrekturen aus dem Plan-Review (ein eigener Commit, siehe »Review-Stand«) sind das vier Commits auf dem Branch, bei einem Fix aus dem Abschluss-Review fünf.
- Die Anker sind **Funktionsnamen**, keine Zeilennummern. Passt ein Anker nicht mehr, hält der Umsetzer an und meldet es.
- **Geprüft vor dem Schreiben:** Der Code und die Tests dieses Plans wurden in einer Scratch-Kopie von `main@1e486b6` ausgeführt. Ohne die Umsetzung: 8 der neuen Tests FAIL, 2 PASS (sie halten bestehendes Verhalten fest). Mit der Umsetzung: alle 10 PASS, Gesamtsuite `1133 passed, 5 skipped, 0 failed`. Ohne den angepassten Test aus Aufgabe 1, Schritt 4 sind es zwei ERRORs; die Gründe stehen dort.

## Minimaler Umfang (und was bewusst nicht getan wird)

Getan:
1. Vor dem Versionsdialog fragt eine Bestätigung, wenn der Stand schon benannt ist; »nein« oder Escape beenden, »Save anyway« führt zum Dialog wie bisher.
2. Die Bestätigung kommt überall, wo `_createVersion` mit einem schon benannten Stand läuft: beide »another«-Knöpfe in Advanced und »Version up to here« auf einer Zeile mit Version.
3. FAQ und User-Guide erwähnen die Rückfrage in je einem Satz.

Bewusst **nicht** getan:
- **Der Hinweis im Versionsdialog bleibt** (`data-carries` und seine Quelle `_alreadyNamed`); er ist danach redundant, fällt aber nicht in diesem Schritt weg.
- **Der Banner hinter einem Tag** (neueste Änderung getaggt, Live-Stand weicht ab und gleicht einer älteren Version) bleibt unverändert. Er ist praktisch nicht erreichbar (Issue #51, »Constraints«); wer ihn doch erreicht, bekommt im Overlay den Satz »This state already carries …« über die Version der neuesten Änderung, nicht die des Live-Stands. Das ist hier ausdrücklich nicht gelöst; ob der Button dort bleibt, entscheidet der Nutzer später.
- Keine Ablehnung: ein zweiter Name für denselben Stand bleibt möglich (FAQ: »allowed and normal«).
- Kein neuer `<dialog>`, kein Server-, Service- oder Speichercode, keine neue CSS-Regel, kein neuer Click-Handler.
- Kein Umbau von `_confirmOverride` über die drei Parameter hinaus.

## Global Constraints

- **Sprache:** Code, Kommentare, Docstrings, Commit-Messages, FAQ und User-Guide englisch; dieser Plan ist deutsch (Projekt-Konvention für `docs/superpowers/`).
- **Keine Backticks und kein `${` in `panel/style.js`:** wird hier nicht berührt, aber `tests/test_panel_assets.py` läuft in der Gesamtprüfung mit.
- `tools/complexity_ratchet.py` und `lint-imports` bleiben grün; die Baseline `tools/complexity-baseline.json` wird nicht angefasst (nur JS-Änderungen).
- **Ein bestehender Test wird geändert** und in Aufgabe 1, Schritt 4 ausdrücklich benannt: das Szenario `_PENDING_CHANGES` (`dialogFor`). Sonst wird kein bestehender Test geändert.
- **Commits:** Englisch, Imperativ im Subject, höchstens 50 Zeichen, Leerzeile, Body mit dem *Warum*, höchstens 72 Zeichen je Zeile, Schluss `Refs #51.` (letzter Commit: `Closes #51.`). Eine Commit-Message behauptet nur, was dieser Commit ändert. Keine `Co-Authored-By`-Zeile.
- **Kein Push, kein Tag, kein Merge** ohne ausdrückliches Go des Nutzers.

## Review Focus

Eingaben und Zustände, die der Plan nicht ausdrücklich nennt, aber die jemanden beißen können – jede Zeile außer 6 hat unten in Aufgabe 1 ihren Test:

1. **Escape statt Knopfdruck:** Der Dialog schließt dann mit leerem `returnValue`; das zählt als »nein«. (Test `test_dismissing_the_question_counts_as_no`)
2. **Versionsname aus dem Server mit Markup:** Er steht als Text in der Frage, nicht als HTML (`_confirmOverride` escaped). (Test `test_a_version_name_in_the_question_is_text_not_markup`)
3. **Kein Name, keine Frage:** Ein Stand, den nichts benennt, geht ohne Umweg zum Dialog. (Test `test_a_state_nothing_names_goes_straight_to_the_dialog`)
4. **»Version up to here« auf einer älteren Zeile mit Version** fragt ebenfalls, weil beide Wege durch `_createVersion` laufen. (Test `test_version_up_to_here_on_an_older_versioned_row_asks_as_well`)
5. **Andere Aufrufer von `_confirmOverride`** (die zwei »Write anyway«-Rückfragen nach einem nicht aufgezeichneten Stand) behalten Titel und Beschriftungen. (Test `test_the_override_helper_keeps_its_own_wording_for_other_callers`)
6. **Wiederverwendeter Bestätigungsdialog:** Nach der Rückfrage bleibt `dialog.confirm` in einem Zustand, den der einzige andere Nutzer dieses Elements, `_confirm`, ohnehin überschreibt (Titel, Body, Fußnote, Apply-Sichtbarkeit, beide Button-Texte, `.note`, `returnValue`; dasselbe gilt schon heute nach der bestehenden Wiederholung in `_confirm`). `_openReplace` benutzt `dialog.replace` und ist davon nicht berührt. Das wird in Aufgabe 1, Schritt 1 gegengelesen, nicht angenommen.
7. **Suchtreffer:** Eine Zeile, die der Server bei »Search the whole history« gefunden hat, steht nicht in `this._changes`, sondern in `this._found`; `_changeAt` sucht in beiden. Trägt der Treffer eine Version, fragt `_createVersion` genauso. (Test `test_a_search_hit_that_carries_a_version_asks_as_well`)

---

### Task 1: Rückfrage vor dem Versionsdialog

**Files:**
- Modify: `custom_components/dashboard_history/panel.js` (`_confirmOverride`: Signatur und drei Zeilen; neue Methode `_askAnother` direkt dahinter; `_createVersion`: vier Zeilen am Anfang)
- Modify (Test): `tests/test_panel_behaviour.py` (neues Szenario `_ANOTHER_VERSION_ASKED` mit Fixture und zehn Tests am Ende der Datei; bestehendes Szenario `_PENDING_CHANGES`, in `dialogFor`)

**Interfaces:**
- Produces: `_confirmOverride(dialog, message, { title = "Write anyway?", apply = "Write anyway", cancel = "Cancel" } = {})` – Antwort `true` bei »apply«, sonst `false`. `_askAnother(named)` – `named` ist der Satz aus `_alreadyNamed`; Antwort wie oben.
- Consumes: `_alreadyNamed(change)` (liefert `""`, `"This state already carries …"` oder `"This is the same state as …"`), `_changeAt`, `_answerFrom`.

- [ ] **Step 1: Ausgangslage lesen und die Wiederverwendung belegen**

Lesen: `_createVersion`, `_alreadyNamed`, `_confirmOverride` und seine zwei Aufrufer (`_confirm` und `_openReplace`, jeweils in der Wiederholung nach `applied?.unrecorded_state`), `_answerFrom`, den Anfang von `_confirm`. Belegen, nicht annehmen: `_confirm` ist der einzige Nutzer von `dialog.confirm` neben `_askAnother` (der zweite Aufruf von `_confirmOverride`, in `_openReplace`, nimmt `dialog.replace`), und es setzt `dialog.querySelector("h2").textContent`, `.body`, die Fußnote (`_sayFootnote`), `applyButton.hidden`, `applyButton.textContent` (`applyLabel`), `button[value="cancel"]`.textContent, `.note` und `returnValue` selbst. Trifft eines davon nicht zu, anhalten und melden.

Run: `grep -n "_confirmOverride" custom_components/dashboard_history/panel.js`
Expected: genau drei Treffer – die Definition und zwei Aufrufe (`retryDialog`). Weicht die Zahl ab: anhalten.

- [ ] **Step 2: Failing tests schreiben**

Am Ende von `tests/test_panel_behaviour.py` anfügen:

```python


# -- a second name for the same state is asked about first ------------------
# GitHub issue #51. The create dialog already says "this state already
# carries v1.0.1", under the number choice, where it was read past. The
# panel now asks before the dialog opens; "no" ends there.

_ANOTHER_VERSION_ASKED = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._mode = "advanced";
const CANDIDATES = { candidates: {
  patch: "dash/v1.0.1", minor: "dash/v1.1.0", major: "dash/v2.0.0",
  current: "dash/v1.0.0",
} };
let sent = [];
el._call = async (type) => {
  sent.push(type);
  return type === "next_versions" ? CANDIDATES : {};
};
const confirmBox = () => el.shadowRoot.querySelector("dialog.confirm");
const versionBox = () => el.shadowRoot.querySelector("dialog.version");

// Starts a fresh flow on a clean shadow root, so no dialog is left open
// by an earlier case.
const begin = (revision) => {
  el.shadowRoot = node();
  sent = [];
  return el._createVersion(revision);
};

// 1. The state carries a version: asked, and "no" ends it there.
el._versions = [{ name: "dash/v1.0.0", title: "First", same_as_now: true, revision: "a" }];
el._matching = [];
el._changes = [{ revision: "a", message: "1 card added", timestamp: 1,
  versions: [{ name: "dash/v1.0.0" }], same_as_now: true }];
let flow = begin("a");
await settle();
const carried = {
  asked: confirmBox().open,
  title: confirmBox().querySelector("h2").textContent,
  body: confirmBox().querySelector(".body").innerHTML,
  apply: confirmBox().querySelector('.actions button[value="apply"]').textContent,
  cancel: confirmBox().querySelector('.actions button[value="cancel"]').textContent,
  fetchedBefore: sent.length,
};
confirmBox().close("cancel");
await settle();
carried.fetchedAfterNo = sent.length;
carried.versionDialogOpen = versionBox().open;

// 2. Dismissed with Escape: the dialog keeps an empty return value,
// and that is a "no" as well.
flow = begin("a");
await settle();
confirmBox().close();
await settle();
const escaped = { fetched: sent.length, versionDialogOpen: versionBox().open };

// 3. "Yes": on to the numbers and the create dialog, as before.
flow = begin("a");
await settle();
const yesAsked = confirmBox().open;
confirmBox().close("apply");
await settle();
const yes = {
  asked: yesAsked,
  closed: confirmBox().open === false,
  first: sent[0],
  versionDialogOpen: versionBox().open,
};
versionBox().close("cancel");
await settle();

// 4. The state holds what a version holds without carrying it - the
// shape after going back to an older version.
el._versions = [{ name: "dash/v1.0.0", title: "First", same_as_now: true, revision: "z" }];
el._matching = [{ name: "dash/v1.0.0" }];
el._changes = [{ revision: "b", message: "2 cards moved", timestamp: 2,
  versions: [], same_as_now: true }];
flow = begin("b");
await settle();
const alike = {
  asked: confirmBox().open,
  body: confirmBox().querySelector(".body").innerHTML,
};
confirmBox().close("cancel");
await settle();

// 5. "Version up to here" on an older row that carries a version.
el._changes = [
  { revision: "n", message: "newest", timestamp: 3, versions: [], same_as_now: false },
  { revision: "o", message: "older", timestamp: 1,
    versions: [{ name: "dash/v1.0.0" }], same_as_now: false },
];
el._matching = [];
flow = begin("o");
await settle();
const olderRow = {
  asked: confirmBox().open,
  body: confirmBox().querySelector(".body").innerHTML,
};
confirmBox().close("cancel");
await settle();

// 5b. A hit the server found is not among the loaded changes: it lives
// in `_found`, and `_changeAt` looks there too.
el._changes = [{ revision: "n", message: "newest", timestamp: 3, versions: [], same_as_now: false }];
el._found = [{ revision: "s", message: "found", timestamp: 1,
  versions: [{ name: "dash/v1.0.0" }], same_as_now: false }];
flow = begin("s");
await settle();
const foundHit = {
  asked: confirmBox().open,
  body: confirmBox().querySelector(".body").innerHTML,
  fetched: sent.length,
};
confirmBox().close("apply");
await settle();
foundHit.fetchedAfterYes = sent[0];
foundHit.versionDialogOpen = versionBox().open;
versionBox().close("cancel");
await settle();
el._found = null;

// 6. Nothing names this state: no question, straight to the numbers.
el._changes = [{ revision: "c", message: "3 cards removed", timestamp: 4,
  versions: [], same_as_now: false }];
flow = begin("c");
await settle();
const unnamed = {
  asked: confirmBox().open,
  first: sent[0],
  versionDialogOpen: versionBox().open,
};
versionBox().close("cancel");
await settle();

// 7. A version name comes from the server and is written as text.
el._changes = [{ revision: "a", message: "1 card added", timestamp: 1,
  versions: [{ name: "dash/<i>x" }], same_as_now: true }];
flow = begin("a");
await settle();
const hostile = confirmBox().querySelector(".body").innerHTML;
confirmBox().close("cancel");
await settle();

// 8. The helper's own defaults are untouched for its other callers.
el.shadowRoot = node();
const plain = el._confirmOverride(confirmBox(), "Could not record.");
await settle();
const defaults = {
  title: confirmBox().querySelector("h2").textContent,
  apply: confirmBox().querySelector('.actions button[value="apply"]').textContent,
  cancel: confirmBox().querySelector('.actions button[value="cancel"]').textContent,
};
confirmBox().close("apply");
const defaultAnswer = await plain;

console.log(JSON.stringify({
  carried, escaped, yes, alike, olderRow, foundHit, unnamed, hostile, defaults, defaultAnswer,
}));
"""


@pytest.fixture(scope="session")
def another_version_asked(tmp_path_factory):
    return _run_in_node(
        tmp_path_factory, "another_version_asked", _ANOTHER_VERSION_ASKED
    )


def test_a_state_that_carries_a_version_is_asked_about_before_the_dialog(
    another_version_asked,
):
    carried = another_version_asked["carried"]
    assert carried["asked"] is True
    assert carried["title"] == "Save another version?"
    assert "This state already carries v1.0.0." in carried["body"]
    assert carried["apply"] == "Save anyway"
    assert carried["cancel"] == "Cancel"
    # Nothing was fetched while the question stood: the numbers are only
    # worked out for somebody who has said yes.
    assert carried["fetchedBefore"] == 0


def test_answering_no_ends_it_before_anything_is_fetched_or_drawn(
    another_version_asked,
):
    assert another_version_asked["carried"]["fetchedAfterNo"] == 0
    assert another_version_asked["carried"]["versionDialogOpen"] is False


def test_dismissing_the_question_counts_as_no(another_version_asked):
    assert another_version_asked["escaped"]["fetched"] == 0
    assert another_version_asked["escaped"]["versionDialogOpen"] is False


def test_answering_yes_goes_on_to_the_create_dialog_as_before(another_version_asked):
    # The question stood, and answering it closed it - not only "the
    # dialog opened", which is also what happens without the question.
    assert another_version_asked["yes"]["asked"] is True
    assert another_version_asked["yes"]["closed"] is True
    assert another_version_asked["yes"]["first"] == "next_versions"
    assert another_version_asked["yes"]["versionDialogOpen"] is True


def test_a_state_equal_to_a_version_is_asked_about_too(another_version_asked):
    assert another_version_asked["alike"]["asked"] is True
    assert "This is the same state as v1.0.0." in another_version_asked["alike"]["body"]


def test_version_up_to_here_on_an_older_versioned_row_asks_as_well(
    another_version_asked,
):
    assert another_version_asked["olderRow"]["asked"] is True
    assert "already carries v1.0.0" in another_version_asked["olderRow"]["body"]


def test_a_search_hit_that_carries_a_version_asks_as_well(another_version_asked):
    hit = another_version_asked["foundHit"]
    assert hit["asked"] is True
    assert "already carries v1.0.0" in hit["body"]
    assert hit["fetched"] == 0
    assert hit["fetchedAfterYes"] == "next_versions"
    assert hit["versionDialogOpen"] is True


def test_a_state_nothing_names_goes_straight_to_the_dialog(another_version_asked):
    unnamed = another_version_asked["unnamed"]
    assert unnamed["asked"] is False
    assert unnamed["first"] == "next_versions"
    assert unnamed["versionDialogOpen"] is True


def test_a_version_name_in_the_question_is_text_not_markup(another_version_asked):
    assert "<i>" not in another_version_asked["hostile"]
    assert "&lt;i&gt;x" in another_version_asked["hostile"]


def test_the_override_helper_keeps_its_own_wording_for_other_callers(
    another_version_asked,
):
    assert another_version_asked["defaults"] == {
        "title": "Write anyway?",
        "apply": "Write anyway",
        "cancel": "Cancel",
    }
    assert another_version_asked["defaultAnswer"] is True
```

Hinweis zu den Szenarien: Sie warten nach jeder Antwort mit `await settle()` statt auf den ganzen Ablauf. Ohne die Umsetzung bliebe `_createVersion` sonst an einem Dialog hängen, den nie jemand beantwortet, und der Test brächte statt eines FAIL einen ERROR.

- [ ] **Step 3: Tests laufen lassen, Fehlschlag prüfen**

Run: `python3 -m pytest tests/test_panel_behaviour.py -q -p no:cacheprovider -k "asked_about or answering or dismissing or equal_to_a_version or version_up_to_here_on or nothing_names or in_the_question or override_helper or search_hit"`
Expected: `8 failed, 2 passed`. FAIL: `…asked_about_before_the_dialog`, `…answering_no_ends_it…`, `…dismissing_the_question…`, `…answering_yes…`, `…equal_to_a_version…`, `…version_up_to_here_on_an_older…`, `…search_hit…`, `…in_the_question_is_text…`. PASS (halten bestehendes Verhalten fest): `…nothing_names…`, `…override_helper…`. Weicht das ab: anhalten und die Ursache klären, nicht den Test anpassen.

- [ ] **Step 4: Umsetzung in `panel.js`**

**(a) `_confirmOverride`: Signatur und drei Zeilen.** Ersetze

```js
  async _confirmOverride(dialog, message) {
    dialog.querySelector("h2").textContent = "Write anyway?";
```

durch

```js
  async _confirmOverride(
    dialog,
    message,
    { title = "Write anyway?", apply = "Write anyway", cancel = "Cancel" } = {},
  ) {
    dialog.querySelector("h2").textContent = title;
```

und ersetze

```js
    applyButton.textContent = "Write anyway";
    dialog.querySelector('.actions button[value="cancel"]').textContent = "Cancel";
```

durch

```js
    applyButton.textContent = apply;
    dialog.querySelector('.actions button[value="cancel"]').textContent = cancel;
```

**(b) Neue Methode direkt hinter `_confirmOverride`** (vor dem Kommentar zu `_paintReplace`):

```js
  /**
   * The question in front of the create dialog, where the state is
   * already named: whether a second name for the same content is really
   * wanted. Not a refusal - the FAQ calls it a legitimate move - only a
   * decision where there used to be a click-through, because the line the
   * create dialog carries about it sits under the number choice and was
   * read straight past (GitHub #51).
   *
   * Reuses the confirmation dialog through `_confirmOverride`, which
   * takes the sentence and the three labels. Looked up fresh here: the
   * caller has not rendered since it read its own dialog, but this is
   * the one place in `_createVersion` that opens a dialog before a
   * `_guard`, and a lookup by name costs nothing.
   */
  _askAnother(named) {
    const dialog = this.shadowRoot.querySelector("dialog.confirm");
    return this._confirmOverride(
      dialog,
      `${named} Save another version for the same content anyway?`,
      { title: "Save another version?", apply: "Save anyway" },
    );
  }
```

**(c) `_createVersion`: direkt nach `if (!change) return;`** einfügen:

```js
    // Asked before anything is fetched or drawn: a "no" costs nothing,
    // and a modal question leaves the selection where it was, so the
    // dashboard captured below is still the one that was asked about.
    const named = this._alreadyNamed(change);
    if (named && !(await this._askAnother(named))) return;
```

Die spätere Zeile `const already = this._alreadyNamed(change);` in derselben Funktion bleibt unverändert (der Hinweis im Versionsdialog bleibt).

**(d) Bestehenden Test anpassen.** Im Szenario `_PENDING_CHANGES`, in `dialogFor`, ersetze

```js
  const versioning = el._createVersion(revision);
  await settle();
  const dialog = el.shadowRoot.querySelector("dialog.version");
```

durch

```js
  const versioning = el._createVersion(revision);
  await settle();
  // A change that already carries a version is asked about first (#51);
  // saying yes is what leads on to the dialog this scenario is about.
  const question = el.shadowRoot.querySelector("dialog.confirm");
  if (question.open) {
    question.close("apply");
    await settle();
  }
  const dialog = el.shadowRoot.querySelector("dialog.version");
```

Grund: `dialogFor("a")` benennt die getaggte Änderung; vor dem Versionsdialog steht jetzt die Rückfrage, und der Test wartete sonst auf einen Dialog, der nicht aufgeht (zwei ERRORs: `test_the_version_dialog_shows_its_own_pending_changes` und `…uses_singular_wording_for_one_change`).

- [ ] **Step 5: Tests laufen lassen**

Run: `python3 -m pytest tests/test_panel_behaviour.py -q -p no:cacheprovider -k "asked_about or answering or dismissing or equal_to_a_version or version_up_to_here_on or nothing_names or in_the_question or override_helper or search_hit"`
Expected: `10 passed`.

Run: `python3 -m pytest tests/ -q -p no:cacheprovider`
Expected: `0 failed`. Die Zahl der passed/skipped schwankt mit den echten Dashboards; nur »0 failed« zählt. Zur Orientierung: auf einem Stand ohne `tests/.real-storage` ergab dieselbe Änderung `1133 passed, 5 skipped`.

Run: `python3 tools/complexity_ratchet.py` und `lint-imports` (laut CLAUDE.md in einem Virtualenv außerhalb des Repos). Expected: beide grün.

- [ ] **Step 6: Commit**

```bash
git add custom_components/dashboard_history/panel.js tests/test_panel_behaviour.py
git commit
```

Message:

```
[51] Ask before saving another version

The create dialog already says that a state carries a version, but
as a bold line under the number choice, and it was read straight
past. The question now comes first and "no" ends it before anything
is fetched. It is a decision, not a refusal: a second name for the
same state stays a legitimate move. The confirmation dialog takes its
texts as parameters instead of a second dialog being added.

Refs #51.
```

---

### Task 2: FAQ und User-Guide

**Files:**
- Modify: `FAQ.md` (Abschnitt »What to do instead«, erster Absatz)
- Modify: `docs/user-guide.md` (Advanced View, letzter Aufzählungspunkt)

- [ ] **Step 1: FAQ ändern**

In `FAQ.md`, Abschnitt »What to do instead«, den ersten Absatz (beginnt mit »**Put a second version beside the first.**«) ersetzen durch:

```markdown
**Put a second version beside the first.** In the simple view that
offer is gone once the dashboard stands on a version: the box already
names it, and a button that saved the same state again was an offer you
had to walk back. Switch to the **advanced** view instead — the "Right
now" box there says **Save this as another version**. The panel asks
once whether you really want another name for the same state; say yes
and the usual dialog follows. It costs nothing and it loses nothing: the
old version stays exactly where it is, still pointing at its state. Two
versions on one state is allowed and normal — after going back to an
older state, a fresh name for it is often precisely what you want.
```

Die folgenden Absätze (»This works because versions group and never squash …« und »Or take the wrong one away«) bleiben unverändert.

- [ ] **Step 2: User-Guide ändern**

In `docs/user-guide.md`, Advanced View, den Punkt »The **Right now** box carries …« ersetzen durch:

```markdown
- The **Right now** box carries **Save this as a version** while the dashboard has changed since the last version, and **Save this as another version** while it stands on one — the simple view only has the first. The second asks once whether you really want another name for the same state before the dialog opens.
```

- [ ] **Step 3: Gesamtprüfung**

Run: `python3 -m pytest tests/ -q -p no:cacheprovider` → `0 failed`.
Run: `python3 tools/complexity_ratchet.py` und `lint-imports` → beide grün.

- [ ] **Step 4: Sichtprüfung (lokale Abnahme, kein Pflichtschritt)**

Im Test-Container (`docker/README.md`; Konfiguration und Token liegen außerhalb des Repos, **nie** die Live-Installation) ansehen: (1) Advanced, ein Dashboard, das auf einer Version steht: »Save this as another version« fragt zuerst, »Cancel« und Escape beenden, »Save anyway« öffnet den gewohnten Dialog; (2) Revert-Fall: derselbe Ablauf mit dem Satz »This is the same state as …«; (3) »Version up to here« auf einer Zeile mit Version fragt ebenfalls; (4) ein Stand ohne Version in Advanced und Simple geht ohne Rückfrage direkt zum Dialog. Gesehen / nicht gesehen je Punkt im Abschlussbericht festhalten; gibt es keine Test-Instanz, steht dort »nicht ausgeführt: keine lokale Testinstanz«. Kein Screenshot mit Pfaden oder Details der eigenen Installation ins Repo legen.

- [ ] **Step 5: Commit**

```bash
git add FAQ.md docs/user-guide.md
git commit
```

Message:

```
[51] Mention the question in the FAQ and the guide

Both describe saving a second version for a state that is already
named; they now say that the panel asks once before it opens the
dialog, so nobody takes the question for an error.

Closes #51.
```

---

## Self-Review (vom Plan-Autor ausgeführt)

- **Abdeckung des Issues #51:** Rückfrage vor dem Dialog, Ja/Nein → Aufgabe 1; alle Stellen, an denen »another« steht, und »Version up to here« → durch den gemeinsamen Einstieg `_createVersion` abgedeckt und durch Tests für beide Sätze und die ältere Zeile belegt; Wortlaut neutral (»Save another version?« / »Save anyway« / »Cancel«); Hinweis im Dialog bleibt unberührt; kein Serveränderung → Umfang; Banner → ausdrücklich nicht gelöst und benannt.
- **Platzhalter-Suche:** keine offenen Stellen. Das einzige Gegenlesen mit Abbruchbedingung steht in Aufgabe 1, Schritt 1.
- **Typkonsistenz:** `_askAnother(named)` und `_confirmOverride(dialog, message, { title, apply, cancel })` sind je einmal definiert; die Namen der Parameter stimmen mit den Aufrufen überein (`title`, `apply`, `cancel`).
- **Review Focus:** Zeilen 1 bis 5 und 7 haben je einen Test; Zeile 6 ist eine Gegenlesung (Aufgabe 1, Schritt 1).
- **Reproduzierbarkeit:** Der Plan nutzt nur committete Dateien, Funktionsnamen und Standardbefehle. Der Browser-Teil ist als optionale lokale Abnahme markiert. Code und Tests wurden vorab in einer Scratch-Kopie von `main@1e486b6` ausgeführt (siehe »Ausgangslage«).
