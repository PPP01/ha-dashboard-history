# Umbau des Create-Version-Dialogs – Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die Vorschau im Create-Version-Dialog neu gestalten – ein Diff mit vollflächig eingefärbten Zeilen statt nur eingefärbtem Text, ein einzeiliger, sich gegenseitig ausschließender Umschalter zwischen »N changes« und »Technical details« statt zweier unabhängiger Ausklapper, und ein mitwachsendes Beschreibungsfeld ohne willkürliches Zeichenlimit.

**Architecture:** Vier Aufgaben, jede für sich testbar. Aufgabe 1 baut `renderDiff()` so um, dass jede Zeile ihr eigenes Block-Element bekommt (Voraussetzung für vollflächige Zeilenhintergründe, ohne dass ein liegen gebliebenes `\n` eine Geisterzeile erzeugt), und hellt die gemeinsame Diff-Box auf – das wirkt überall im Panel, wo ein Diff gezeigt wird, nicht nur im Create-Version-Dialog. Aufgabe 2 ersetzt die zwei unabhängigen `<details class="raw">` im Versions-Dialog durch zwei sich gegenseitig ausschließende Toggle-Buttons (kein volles ARIA-Tab-Pattern – dafür fehlte Tastatursteuerung, siehe unten) und führt einen statischen Markup-Test gegen die echte `DIALOGS`-Konstante ein, weil der Node-Stand-in jede Selektor-Anfrage mit einem Phantomknoten beantwortet und daher nie beweist, dass das Markup wirklich geändert wurde. Aufgabe 3 entfernt zuerst das bereits entschiedene, aber noch nicht committete Zeichenlimit der Beschreibung, macht das geteilte Feld (Create- **und** Retitle-Dialog) danach zu einer mitwachsenden `<textarea>` und stellt sicher, dass eine vorbefüllte, mehrzeilige Beschreibung schon beim Öffnen des Dialogs korrekt mitwächst, nicht erst nach der ersten Eingabe. Aufgabe 4 ist die Gesamtprüfung plus ein ausdrücklich offen bleibender, manueller Sichtprüfungs-Schritt.

**Tech Stack:** Plain Custom Element, kein Build-Schritt, kein Framework. CSS-Variablen von Home Assistant mit Hex-Fallback. Node (über den vorhandenen pytest-Unterbau) für Verhaltenstests, pytest zur Orchestrierung.

**Spec:** Kein eigenes Spec-Dokument. Diese Änderung lief über den »bounded«-Pfad von `superpowers:brainstorming` – Design im Chat dieser Sitzung entworfen und Punkt für Punkt freigegeben, nicht unter `docs/superpowers/specs/` abgelegt. Bindend ist dieser Plan. Ein externes Review dieses Plans (2026-09-29, vor der ersten Umsetzung) fand vier Lücken; alle vier sind unten eingearbeitet, siehe die Anmerkungen an den betroffenen Schritten.

## Global Constraints

- **Sprache:** Code, Kommentare, Docstrings, Commit-Messages englisch. Dieser Plan ist deutsch (Projekt-Konvention für `docs/superpowers/`).
- **Keine Backticks und kein `${` in `style.js`** – automatisch geprüft durch `tests/test_panel_assets.py::test_the_style_is_one_unbroken_template_literal` und `::test_no_substitution_hides_in_the_stylesheet`. Ein Backtick irgendwo in einer neuen CSS-Regel oder einem neuen Kommentar dort bricht das Template-Literal und damit das ganze Panel.
- **Keine Backticks in `dialogs.js`** – strukturell dieselbe Falle (auch `DIALOGS` ist ein Template-Literal), aber ohne eigenen Test. Selbst prüfen.
- **`tools/complexity_ratchet.py` bleibt grün** – keine der geänderten Funktionen darf komplexer werden, als die Baseline erlaubt.
- **`lint-imports` bleibt grün** – unberührt von diesem Plan (keines der sieben HA-freien Module wird angefasst), trotzdem mitlaufen lassen.
- **Kein bestehender Test wird ohne Grund geändert.** Die eine geplante Ausnahme (`input.desc` → `textarea.desc` in Aufgabe 3) ist eine notwendige Folge der Feldtyp-Änderung und wird in dieser Aufgabe ausdrücklich benannt, nicht still angepasst.
- **Ein Node-Stand-in beweist keine Markup-Änderung.** Der flache DOM-Stand-in in `tests/test_panel_behaviour.py` (`node()`) beantwortet jede `querySelector`-Anfrage mit einem neu erzeugten Phantomknoten, unabhängig davon, was `dialogs.js` tatsächlich enthält (siehe Kommentar über `querySelector` in `_PRELUDE`). Ein Test, der eine echte Markup-Umstellung beweisen soll, muss deshalb die reale `DIALOGS`-Konstante importieren und als Text prüfen – nicht nur über den Stand-in gehen.
- **Commits:** Englisch, Imperativ im Subject, höchstens 50 Zeichen (Ausnahme bis 72), Leerzeile, Body mit dem Warum, höchstens 72 Zeichen je Zeile. Eine Commit-Message darf nur behaupten, was **dieser** Commit tatsächlich ändert – eine bereits vorher committete Änderung gehört nicht in die Begründung eines späteren Commits.
- **Push, Tag oder sonstige unumkehrbare Schritte erst nach ausdrücklichem Go des Nutzers** (Projekt-Regel, `CLAUDE.md`, Abschnitt »Git«).

## Review Focus

Eingaben und Zustände, die kein einzelner Task-Test von sich aus abdeckt – am wahrscheinlichsten zuerst:

1. **Ein Diff, der mit `\n` endet** (jeder echte unified diff tut das). Erwartet: auch die dadurch entstehende letzte, leere Zeile bekommt ihr eigenes `<span>` – sonst bleibt genau eine Zeile in der alten, gemischten Form und erzeugt in einem echten Browser eine Geisterzeile. Geprüft in Aufgabe 1, `test_render_diff_handles_a_trailing_blank_line`.
2. **Ein Dialog, der noch nicht `showModal()` gesehen hat, kennt keine echte `scrollHeight`.** Ein geschlossenes `<dialog>` wird in einem echten Browser nicht gerendert; ein `growTextarea()`-Aufruf davor läse eine falsche, meist `0` lautende Höhe. Betrifft insbesondere die vorbefüllte Retitle-Beschreibung. Geprüft in Aufgabe 3, `test_a_prefilled_multiline_description_grows_the_moment_the_dialog_opens`.
3. **Zwei Aufrufstellen für ein und dasselbe Feld** (Create- und Retitle-Dialog teilen sich die Beschreibung). Erwartet: beide wachsen mit, in derselben Reihenfolge relativ zu `showModal()`. Eine Änderung an nur einer Stelle zu vergessen ist genau die Falle, vor der der Kommentar über `VERSION_FIELDS` in `dialogs.js` bereits warnt. Geprüft in Aufgabe 3 durch zwei eigenständige Tests, nicht nur einen.
4. **Der Dialog bleibt zwischen zwei Öffnungen derselbe DOM-Knoten** (`_render` läuft nie, solange ein `<dialog>` offen ist). Erwartet: ein Umschalter, der beim letzten Mal auf »Technical details« stand, zeigt beim nächsten Öffnen wieder die Wortliste. Geprüft in Aufgabe 2, `test_reopening_the_version_dialog_forgets_the_last_open_tab`.
5. **Keine vorherige Version vorhanden** (die erste je gespeicherte Version eines Dashboards). Erwartet: der Technical-details-Tab erscheint dann nie, nicht einmal leer. Bereits durch `test_the_version_dialog_hides_technical_details_without_a_prior_version` abgedeckt – in Aufgabe 2 nur gegenprüfen, dass er nach dem Umbau weiterhin grün bleibt, keine neue Aufgabe nötig.

Ein sechster, mit der Node-Bank grundsätzlich nicht prüfbarer Punkt (keine Layout-Engine) steht als offener manueller Prüfpunkt in Aufgabe 4: ob die Volltonfarbe einer sehr breiten, langen Diff-Zeile über die gesamte scrollbare Breite reicht.

---

### Aufgabe 1: Diff-Zeilen einzeln einfärben, Box aufhellen

**Files:**
- Modify: `custom_components/dashboard_history/panel/render.js` (Funktion `renderDiff`, ganze Datei aktuell 35 Zeilen)
- Modify: `custom_components/dashboard_history/panel/style.js:466-475` (Regel `pre { … }`)
- Modify: `custom_components/dashboard_history/panel/style.js:739-741` (Regeln `pre .add`/`.del`/`.at`)
- Test: `tests/test_panel_behaviour.py` (neue Konstante `RENDER`, neuer Helfer `_render_diff`, drei neue Tests)

**Interfaces:**
- Consumes: nichts Neues – `renderDiff(diff: string | null | undefined): string` bleibt exportiert wie bisher.
- Produces: `renderDiff(...)` liefert jetzt für jede Zeile genau ein `<span>` (mit `class="add"`/`"del"`/`"at"` oder ganz ohne `class`), ohne verbindende `\n`-Zeichen dazwischen. Aufgabe 2 verlässt sich darauf, dass diese Funktion unverändert über `dialog.querySelector("[data-technical-body]").innerHTML = renderDiff(...)` aufgerufen wird – nur ihre Ausgabe ändert sich. Die Konstante `RENDER` (Pfad zu `render.js`) wird von Aufgabe 2 und 3 nicht gebraucht; sie führen ihre eigene Konstante `DIALOGS_FILE` für `dialogs.js` ein.

- [ ] **Step 1: Die fehlschlagenden Tests schreiben**

In `tests/test_panel_behaviour.py`, direkt nach der Zeile `PANEL = PACKAGE / "panel.js"` (oberhalb von `# The stand-in for the browser, …`), diese Konstante ergänzen:

```python
RENDER = PACKAGE / "panel" / "render.js"
```

Danach, direkt vor dem Kommentarblock `# -- the create-version dialog offers the diff behind the pending span --` (kurz vor der Konstante `_TECHNICAL_DETAILS`), diesen neuen Abschnitt einfügen:

```python
# -- renderDiff's own markup, isolated from the rest of the panel ----------


def _render_diff(tmp_path_factory, diff_text):
    """Call the real renderDiff() directly, without the rest of panel.js.

    render.js is one of the "pure functions" modules - no element, no
    state, no calls of its own - so it needs none of panel.js's DOM
    stand-in to exercise on its own.
    """
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed; the panel's logic cannot be run here")
    harness = tmp_path_factory.mktemp("render") / "render_diff.mjs"
    harness.write_text(
        "import { renderDiff } from %s;\n"
        "process.stdout.write(JSON.stringify({ html: renderDiff(%s) }));\n"
        % (json.dumps(RENDER.as_uri()), json.dumps(diff_text)),
        encoding="utf-8",
    )
    run = subprocess.run(
        [node, str(harness)], capture_output=True, text=True, timeout=60, check=False
    )
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout.strip().splitlines()[-1])["html"]


def test_render_diff_wraps_every_line_in_its_own_block_span(tmp_path_factory):
    # Full-row backgrounds on "+"/"-"/"@@" lines need `display:block` on
    # their spans (style.js), and a block span sitting next to a raw
    # "\n" text node renders as a stray blank line in a real browser -
    # every line, classified or not, gets its own span and nothing else
    # is left over to cause that.
    #
    # No trailing "\n" on this input, on purpose: a real unified diff
    # always ends in one, and split("\n") turns that into a trailing
    # empty line needing its own <span></span> - but that concern
    # belongs entirely to test_render_diff_handles_a_trailing_blank_line
    # below. Mixing it into this one would test two things in one
    # assertion and made this exact mistake once already: an assert
    # that didn't count the trailing span its own input implied.
    html = _render_diff(
        tmp_path_factory,
        "--- before\n+++ after\n@@ -1 +1 @@\n context\n-old\n+new",
    )
    assert html == (
        "<pre>"
        '<span class="del">--- before</span>'
        '<span class="add">+++ after</span>'
        '<span class="at">@@ -1 +1 @@</span>'
        "<span> context</span>"
        '<span class="del">-old</span>'
        '<span class="add">+new</span>'
        "</pre>"
    )


def test_render_diff_handles_a_trailing_blank_line(tmp_path_factory):
    # A unified diff ends in "\n", so split("\n") always leaves one
    # trailing empty string - it needs a span like any other line, or
    # it would be the one line the block-span rule above misses.
    html = _render_diff(tmp_path_factory, "@@ -1 +1 @@\n-old\n+new\n")
    assert html == (
        "<pre>"
        '<span class="at">@@ -1 +1 @@</span>'
        '<span class="del">-old</span>'
        '<span class="add">+new</span>'
        "<span></span>"
        "</pre>"
    )


def test_render_diff_still_says_no_difference_for_an_empty_diff(tmp_path_factory):
    assert _render_diff(tmp_path_factory, "") == '<p class="muted">No difference.</p>'
```

- [ ] **Step 2: Tests laufen lassen, sie müssen fehlschlagen**

Run: `python3 -m pytest tests/test_panel_behaviour.py -k render_diff -v`
Expected: `test_render_diff_wraps_every_line_in_its_own_block_span` und `test_render_diff_handles_a_trailing_blank_line` FAIL (die alte Fassung trennt Zeilen weiterhin mit `\n` und lässt unklassifizierte Zeilen ohne `<span>`); `test_render_diff_still_says_no_difference_for_an_empty_diff` PASS (der frühe Rückgabepfad ist von dieser Aufgabe nicht betroffen).

- [ ] **Step 3: `renderDiff` umbauen**

In `custom_components/dashboard_history/panel/render.js`, den ganzen Block

```js
/** A unified diff, coloured the way people expect to read one. */
export const renderDiff = (diff) => {
  if (!diff) return '<p class="muted">No difference.</p>';
  const body = diff
    .split("\n")
    .map((line) => {
      const cls = line.startsWith("+")
        ? "add"
        : line.startsWith("-")
          ? "del"
          : line.startsWith("@@")
            ? "at"
            : "";
      return cls
        ? `<span class="${cls}">${escape(line)}</span>`
        : escape(line);
    })
    .join("\n");
  return `<pre>${body}</pre>`;
};
```

ersetzen durch:

```js
/**
 * A unified diff, coloured the way people expect to read one.
 *
 * Every line becomes its own block-level span (style.js relies on
 * this for the full-row background behind a "+"/"-"/"@@" line), and
 * there is no separating "\n" text node left between them - a block
 * sitting next to a literal newline renders as an extra blank line in
 * a real browser, a known trap of block-in-inline layout.
 */
export const renderDiff = (diff) => {
  if (!diff) return '<p class="muted">No difference.</p>';
  const body = diff
    .split("\n")
    .map((line) => {
      const cls = line.startsWith("+")
        ? "add"
        : line.startsWith("-")
          ? "del"
          : line.startsWith("@@")
            ? "at"
            : "";
      return `<span${cls ? ` class="${cls}"` : ""}>${escape(line)}</span>`;
    })
    .join("");
  return `<pre>${body}</pre>`;
};
```

- [ ] **Step 4: Tests laufen lassen, sie müssen bestehen**

Run: `python3 -m pytest tests/test_panel_behaviour.py -k render_diff -v`
Expected: alle drei PASS.

- [ ] **Step 5: Die Diff-Box in `style.js` aufhellen und deckeln**

In `custom_components/dashboard_history/panel/style.js`, den Block

```css
  pre {
    margin: 0;
    padding: 12px;
    border-radius: 4px;
    background: var(--secondary-background-color, #fafafa);
    font-size: 12px;
    line-height: 1.5;
    white-space: pre;
    overflow-x: auto;
  }
```

ersetzen durch:

```css
  pre {
    margin: 0;
    padding: 12px;
    border: 1px solid var(--divider-color, #e0e0e0);
    border-radius: 4px;
    background: var(--primary-background-color, #f5f5f5);
    font-size: 12px;
    line-height: 1.5;
    white-space: pre;
    overflow-x: auto;
    max-height: 400px;
    overflow-y: auto;
  }
```

- [ ] **Step 6: Zeilenfarben in `style.js` auf Volltonhintergrund umstellen**

Im selben File den Block

```css
  pre .add { color: var(--success-color, #0f9d58); }
  pre .del { color: var(--error-color, #db4437); }
  pre .at { color: var(--secondary-text-color, #727272); }
```

ersetzen durch:

```css
  /* Every line of a diff is its own block-level span (render.js) so a
     full-row tint can sit behind it - the bleed to pre's own edge is
     padding plus a negative margin the size of pre's own padding, the
     standard trick for a highlight that reaches a scrollable box's
     border. */
  pre span {
    display: block;
    margin: 0 -12px;
    padding: 0 12px;
  }
  pre .add {
    color: var(--success-color, #0f9d58);
    background: rgba(15, 157, 88, 0.1);
    background: color-mix(in srgb, var(--success-color, #0f9d58) 10%, transparent);
  }
  pre .del {
    color: var(--error-color, #db4437);
    background: rgba(219, 68, 55, 0.1);
    background: color-mix(in srgb, var(--error-color, #db4437) 10%, transparent);
  }
  pre .at {
    color: var(--secondary-text-color, #727272);
    background: rgba(224, 224, 224, 0.45);
    background: color-mix(in srgb, var(--divider-color, #e0e0e0) 45%, transparent);
  }
```

- [ ] **Step 7: Die stillen CSS-Wächter laufen lassen**

Run: `python3 -m pytest tests/test_panel_assets.py -v`
Expected: `2 passed` (genau zwei Backticks in `style.js`, kein `${` darin) plus der Teile-Test.

- [ ] **Step 8: Ganze Suite laufen lassen**

Run: `python3 -m pytest tests/ -v`
Expected: alles grün, keine neuen Fehlschläge gegenüber dem Stand vor dieser Aufgabe.

- [ ] **Step 9: Commit**

```bash
git add custom_components/dashboard_history/panel/render.js \
        custom_components/dashboard_history/panel/style.js \
        tests/test_panel_behaviour.py
git commit -m "$(cat <<'EOF'
Give every diff line its own block and lighten its box

Full-row backgrounds behind added/removed lines need display:block
on their spans, and a block next to a leftover newline text node
renders as a stray blank line in a real browser - so every line, not
only the classified ones, gets wrapped and nothing is left over to
join them with. The shared pre element gets the same background and
fallback the pill above it already used, plus a border and a height
cap, since every diff view in the panel shares this one rule.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Aufgabe 2: Zwei sich ausschließende Toggle-Buttons statt zweier unabhängiger Ausklapper

**Hinweis zum Review-Befund P2 (ARIA):** Ein voll ausgestattetes ARIA-Tab-Pattern (`role="tablist"`/`"tab"`/`"tabpanel"`, `aria-controls`, Pfeiltasten-Navigation) wurde bewusst **nicht** gewählt – ein halb umgesetztes Tab-Pattern (Rollen ohne Tastatursteuerung) ist für Screenreader-Nutzer eher irreführend als hilfreich. Stattdessen: zwei gewöhnliche `<button>` mit `aria-pressed` (Toggle-Button-Muster) plus `aria-controls`, das jeden Knopf mit seinem Inhaltsbereich verknüpft – ohne den Anspruch, ein Tab-Widget zu sein.

**Files:**
- Modify: `custom_components/dashboard_history/panel/dialogs.js:132-139` (Versions-Dialog, Block `data-pending`/`data-technical`)
- Modify: `custom_components/dashboard_history/panel.js` (Methode `_createVersion`, der Block ab `const technicalDetails = …` bis `let level = "patch";`)
- Modify: `custom_components/dashboard_history/panel/style.js` (neuer Block direkt nach den in Aufgabe 1 geänderten `pre .add`/`.del`/`.at`-Regeln, vor `details.ver { margin-bottom: 12px; }`)
- Test: `tests/test_panel_behaviour.py` (neue Konstante `DIALOGS_FILE`, neuer Helfer `_dialogs_html`, ein statischer Markup-Test, drei Verhaltens-Tests, ein neues Szenario `_TAB_SWITCH`)

**Interfaces:**
- Consumes: die bestehenden Attribut-Hooks `data-pending`, `data-pending-summary`, `data-pending-body`, `data-technical`, `data-technical-body` – alle fünf bleiben exakt so benannt und werden von `_createVersion` weiterhin über dieselben Zeilen (`pendingDetails.hidden = !pending.length;` usw.) bedient, nur die Elemente dahinter ändern sich.
- Produces: ein neues Attribut `data-pending-tab` auf dem Umschalter-Knopf für die Wortliste (keine bestehende Stelle im Code oder in Tests kennt diesen Namen bisher). Außerdem den Helfer `_dialogs_html(tmp_path_factory)` und die Konstante `DIALOGS_FILE` in `tests/test_panel_behaviour.py` – Aufgabe 3 verwendet beide unverändert weiter, ohne sie neu zu definieren.

- [ ] **Step 1: Die fehlschlagenden Tests schreiben**

In `tests/test_panel_behaviour.py`, direkt nach der in Aufgabe 1 ergänzten Zeile `RENDER = PACKAGE / "panel" / "render.js"`, diese Konstante ergänzen:

```python
DIALOGS_FILE = PACKAGE / "panel" / "dialogs.js"
```

Danach, direkt vor dem Kommentarblock `# -- the create-version dialog offers the diff behind the pending span --` – der nach Aufgabe 1 nicht mehr direkt auf `RENDER` folgt, sondern auf deren neu eingefügten Abschnitt über `renderDiff`; der Kommentarblock selbst bleibt aber ein eindeutiger Ankertext –, diesen neuen Abschnitt einfügen:

```python
# -- the version dialog's real markup is a toggle pair, not <details> ------


def _dialogs_html(tmp_path_factory):
    """The real DIALOGS markup, parsed by nothing but Node's own import.

    The flat DOM stand-in the rest of this file uses (`node()`, in
    `_PRELUDE`) answers every selector with a fresh phantom node
    regardless of what dialogs.js actually contains - proof that a
    markup change really landed has to come from reading dialogs.js
    itself, not from asking the stand-in.
    """
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed; the panel's logic cannot be run here")
    harness = tmp_path_factory.mktemp("dialogs") / "dialogs_html.mjs"
    harness.write_text(
        "import { DIALOGS } from %s;\n"
        "process.stdout.write(JSON.stringify({ html: DIALOGS }));\n"
        % json.dumps(DIALOGS_FILE.as_uri()),
        encoding="utf-8",
    )
    run = subprocess.run(
        [node, str(harness)], capture_output=True, text=True, timeout=60, check=False
    )
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout.strip().splitlines()[-1])["html"]


def _version_dialog_html(tmp_path_factory):
    html = _dialogs_html(tmp_path_factory)
    return html.split('<dialog class="version">')[1].split("</dialog>")[0]


def test_the_version_dialogs_real_markup_has_a_toggle_pair_not_details(
    tmp_path_factory,
):
    version_dialog = _version_dialog_html(tmp_path_factory)
    assert "<details" not in version_dialog
    assert "data-pending-tab" in version_dialog
    assert "data-technical" in version_dialog
    assert 'aria-pressed="true"' in version_dialog
    assert 'aria-pressed="false"' in version_dialog


# -- the two views switch each other off, not open independently -----------

_TAB_SWITCH = """
const changes = [{ revision: "c", message: "3rd card added", versions: [] }];
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._changes = changes;
el.shadowRoot = node();
el._reloadAfterWrite = async () => null;
el._call = (type) =>
  type === "next_versions"
    ? Promise.resolve({ candidates: { patch: "dash/v1.0.1", current: "dash/v1.0.0" } })
    : type === "compare"
      ? Promise.resolve({ diff: "@@ -1 +1 @@\\n-old\\n+new\\n" })
      : Promise.resolve({ created: "dash/v1.0.1" });

const first = el._createVersion("c");
await settle();
const dialog = el.shadowRoot.querySelector("dialog.version");
const pendingTab = dialog.querySelector("[data-pending-tab]");
const technicalTab = dialog.querySelector("[data-technical]");
const pendingBody = dialog.querySelector("[data-pending-body]");
const technicalBody = dialog.querySelector("[data-technical-body]");
const state = () => ({
  pendingPressed: pendingTab.getAttribute("aria-pressed"),
  technicalPressed: technicalTab.getAttribute("aria-pressed"),
  pendingHidden: pendingBody.hidden,
  technicalHidden: technicalBody.hidden,
});
const opened = state();

technicalTab._on.click();
const afterTechnical = state();

pendingTab._on.click();
const afterPending = state();

// Left on "technical" on the way out, on purpose - the next open must
// not remember it.
technicalTab._on.click();
dialog.close("create");
await first;

const second = el._createVersion("c");
await settle();
const reopened = state();
dialog.close("create");
await second;

console.log(JSON.stringify({ opened, afterTechnical, afterPending, reopened }));
"""


@pytest.fixture(scope="session")
def tab_switch(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "tab_switch", _TAB_SWITCH)


def test_the_version_dialog_opens_on_the_plain_language_tab(tab_switch):
    assert tab_switch["opened"] == {
        "pendingPressed": "true",
        "technicalPressed": "false",
        "pendingHidden": False,
        "technicalHidden": True,
    }


def test_the_version_dialogs_two_tabs_show_exactly_one_panel_at_a_time(tab_switch):
    assert tab_switch["afterTechnical"] == {
        "pendingPressed": "false",
        "technicalPressed": "true",
        "pendingHidden": True,
        "technicalHidden": False,
    }
    assert tab_switch["afterPending"] == {
        "pendingPressed": "true",
        "technicalPressed": "false",
        "pendingHidden": False,
        "technicalHidden": True,
    }


def test_reopening_the_version_dialog_forgets_the_last_open_tab(tab_switch):
    assert tab_switch["reopened"] == {
        "pendingPressed": "true",
        "technicalPressed": "false",
        "pendingHidden": False,
        "technicalHidden": True,
    }
```

- [ ] **Step 2: Tests laufen lassen, sie müssen fehlschlagen**

`-k` würde hier auf Fixture-Namen hereinfallen (`tab_switch` ist der Name der Fixture, nicht Teil der drei Testfunktionsnamen, und `-k` prüft nur Modul-, Klassen- und Funktionsnamen) – deshalb die vier Tests einzeln über ihren vollen Namen ausgewählt:

Run: `python3 -m pytest "tests/test_panel_behaviour.py::test_the_version_dialogs_real_markup_has_a_toggle_pair_not_details" "tests/test_panel_behaviour.py::test_the_version_dialog_opens_on_the_plain_language_tab" "tests/test_panel_behaviour.py::test_the_version_dialogs_two_tabs_show_exactly_one_panel_at_a_time" "tests/test_panel_behaviour.py::test_reopening_the_version_dialog_forgets_the_last_open_tab" -v`
Expected: `test_the_version_dialogs_real_markup_has_a_toggle_pair_not_details` FAIL (der Versions-Dialog enthält weiterhin `<details` und kein `data-pending-tab`); die drei übrigen FAIL, weil `technicalTab._on.click` `undefined` ist – `_createVersion` registriert noch keinen Klick-Handler auf diesem Element.

- [ ] **Step 3: Markup in `dialogs.js` umbauen**

In `custom_components/dashboard_history/panel/dialogs.js`, im Versions-Dialog (`<dialog class="version">`) den Block

```html
      <details class="raw" data-pending hidden>
        <summary data-pending-summary></summary>
        <div data-pending-body></div>
      </details>
      <details class="raw" data-technical hidden>
        <summary><span class="glyph">&lt;/&gt;</span> Technical details</summary>
        <div data-technical-body></div>
      </details>
```

ersetzen durch:

```html
      <div class="switcher" data-pending hidden>
        <div class="switcher-bar">
          <span class="switcher-label">Included</span>
          <div class="switcher-tabs">
            <button type="button" class="switcher-tab" data-pending-tab
                    aria-pressed="true" aria-controls="version-pending-body">
              <span data-pending-summary></span>
            </button>
            <button type="button" class="switcher-tab" data-technical hidden
                    aria-pressed="false" aria-controls="version-technical-body">
              <span class="glyph">&lt;/&gt;</span> Technical details
            </button>
          </div>
        </div>
        <div class="switcher-body" data-pending-body id="version-pending-body"></div>
        <div class="switcher-body" data-technical-body id="version-technical-body" hidden></div>
      </div>
```

- [ ] **Step 4: Umschalt-Logik in `panel.js` verkabeln**

In `custom_components/dashboard_history/panel.js`, in der Methode `_createVersion`, den Block

```js
    const technicalDetails = dialog.querySelector("[data-technical]");
    technicalDetails.hidden = true;
    if (pending.length && candidates.current) {
      this._call("compare", {
        dashboard: asked,
        revision_a: candidates.current,
        revision_b: change.revision,
      })
        .then((comparison) => {
          if (!mine() || !comparison?.diff) return;
          technicalDetails.hidden = false;
          dialog.querySelector("[data-technical-body]").innerHTML =
            renderDiff(comparison.diff);
        })
        .catch(() => {});
    }
    let level = "patch";
```

ersetzen durch:

```js
    const technicalDetails = dialog.querySelector("[data-technical]");
    technicalDetails.hidden = true;
    if (pending.length && candidates.current) {
      this._call("compare", {
        dashboard: asked,
        revision_a: candidates.current,
        revision_b: change.revision,
      })
        .then((comparison) => {
          if (!mine() || !comparison?.diff) return;
          technicalDetails.hidden = false;
          dialog.querySelector("[data-technical-body]").innerHTML =
            renderDiff(comparison.diff);
        })
        .catch(() => {});
    }
    // The two views of the same pending span switch each other off -
    // unlike the independent <details class="raw"> pairs elsewhere in
    // the panel, only one of "changes" and "Technical details" is ever
    // on screen at once. Plain toggle buttons (aria-pressed), not a
    // full ARIA tabs pattern - there is no keyboard roving-tabindex
    // navigation here, and claiming role="tab" without it would be
    // worse than claiming nothing. Reset on every open: the dialog
    // element can outlive several openings (_render never runs while a
    // dialog is open), and a tab left on "technical" from the last
    // time would otherwise greet the next change with the diff instead
    // of the plain-language span.
    const pendingTab = dialog.querySelector("[data-pending-tab]");
    const pendingBody = dialog.querySelector("[data-pending-body]");
    const technicalBody = dialog.querySelector("[data-technical-body]");
    const selectTab = (which) => {
      pendingTab.setAttribute("aria-pressed", String(which === "pending"));
      technicalDetails.setAttribute(
        "aria-pressed",
        String(which === "technical"),
      );
      pendingBody.hidden = which !== "pending";
      technicalBody.hidden = which !== "technical";
    };
    selectTab("pending");
    pendingTab.addEventListener("click", () => selectTab("pending"));
    technicalDetails.addEventListener("click", () => selectTab("technical"));
    let level = "patch";
```

- [ ] **Step 5: Tests laufen lassen, sie müssen bestehen**

Run: `python3 -m pytest "tests/test_panel_behaviour.py::test_the_version_dialogs_real_markup_has_a_toggle_pair_not_details" "tests/test_panel_behaviour.py::test_the_version_dialog_opens_on_the_plain_language_tab" "tests/test_panel_behaviour.py::test_the_version_dialogs_two_tabs_show_exactly_one_panel_at_a_time" "tests/test_panel_behaviour.py::test_reopening_the_version_dialog_forgets_the_last_open_tab" -v`
Expected: alle vier PASS.

- [ ] **Step 6: Die bestehenden Tests desselben Dialogs gegenprüfen**

Geprüft mit dem Schlüsselwort `version_dialog` statt `pending_changes or technical_details`: Letzteres verfehlt `test_the_version_dialog_uses_singular_wording_for_one_change` (der Funktionsname enthält keines der beiden Wörter) und trifft dafür `test_the_cards_technical_details_summary_carries_the_pill_glyph`, der mit diesem Dialog nichts zu tun hat. Verifiziert gegen den aktuellen Stand vor dieser Aufgabe: `version_dialog` trifft genau vier Tests, alle vier zum Versions-Dialog gehörig.

Run: `python3 -m pytest tests/test_panel_behaviour.py -k "version_dialog" -v`
Expected: genau die vier bestehenden Tests `test_the_version_dialog_shows_its_own_pending_changes`, `test_the_version_dialog_uses_singular_wording_for_one_change`, `test_the_version_dialog_shows_technical_details_for_the_pending_span`, `test_the_version_dialog_hides_technical_details_without_a_prior_version` weiterhin PASS – sie fragen ausschließlich nach `[data-pending]`, `[data-pending-summary]`, `[data-pending-body]`, `[data-technical]`, `[data-technical-body]`, keiner nach `<details>` als Element.

- [ ] **Step 7: Umschalter-Optik in `style.js` ergänzen**

Direkt nach dem in Aufgabe 1, Step 6 geänderten Block (`pre .at { … }`) und vor `details.ver { margin-bottom: 12px; }`, diesen neuen Block einfügen:

```css
  /* The create-version dialog's own switch between the plain-language
     span and its exact diff (GitHub issue #15, redesigned 2026-09-29):
     one row, a muted label and two pill-shaped toggle buttons, exactly
     one of them pressed at a time - unlike the independent
     details.raw pairs above, which can both be open together. */
  .switcher { margin: 8px 0; }
  .switcher-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 8px;
  }
  .switcher-label {
    color: var(--secondary-text-color, #727272);
    font-size: 11px;
    font-weight: 600;
    letter-spacing: .06em;
    text-transform: uppercase;
  }
  .switcher-tabs { display: flex; gap: 8px; }
  .switcher-tab {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 7px 14px;
    border: 1px solid var(--divider-color, #dfe3e8);
    border-radius: 18px;
    background: var(--primary-background-color, #f5f5f5);
    color: var(--secondary-text-color, #607d8b);
    font: inherit;
    font-size: 13.5px;
    font-weight: 500;
    cursor: pointer;
  }
  .switcher-tab:hover { background: var(--divider-color, #e7ebee); }
  .switcher-tab .glyph { font-family: monospace; font-size: 12px; }
  .switcher-tab::after {
    content: "\\25BC";
    margin-left: 2px;
    font-size: 10px;
    opacity: .7;
    display: inline-block;
    transition: transform .15s ease;
  }
  .switcher-tab[aria-pressed="true"] {
    background: var(--card-background-color, #fff);
    border-color: var(--primary-text-color, #37474f);
    color: var(--primary-text-color, #37474f);
  }
  .switcher-tab[aria-pressed="true"]::after { transform: rotate(180deg); }
  @media (max-width: 600px) {
    .switcher-bar {
      flex-direction: column;
      align-items: flex-start;
      gap: 6px;
    }
  }
```

- [ ] **Step 8: Stille CSS-Wächter und ganze Suite laufen lassen**

Run: `python3 -m pytest tests/test_panel_assets.py tests/test_panel_behaviour.py -v`
Expected: alles grün.

- [ ] **Step 9: Commit**

```bash
git add custom_components/dashboard_history/panel/dialogs.js \
        custom_components/dashboard_history/panel.js \
        custom_components/dashboard_history/panel/style.js \
        tests/test_panel_behaviour.py
git commit -m "$(cat <<'EOF'
Replace the create-version dialog's two bubbles with one switcher

"N pending changes" and "Technical details" used to be independent
<details>, both open or both closed at once - the mockup for this
redesign showed one row with exactly one of the two always active, a
plainer question to answer than "did I remember to expand both". Two
plain toggle buttons (aria-pressed), not a full ARIA tabs pattern -
there is no keyboard roving-tabindex navigation, and a half-built
tabs widget would mislead assistive tech more than a plain button
pair. The dialog can stay open across several calls to
_createVersion without a render in between, so the switch back to
"changes" on every open is explicit rather than assumed. A static
check against the real DIALOGS markup accompanies the behavioural
tests, since the panel's flat DOM stand-in answers every selector
with a phantom node regardless of what dialogs.js actually contains.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Aufgabe 3: Beschreibungsfeld verliert sein Zeichenlimit und wird eine mitwachsende Textarea

**Hinweis zum Review-Befund P1 (Ausgangszustand):** Die Entfernung von `maxlength="500"` wurde in dieser Sitzung bereits entschieden (siehe Chat-Verlauf und den für Step 1 unten vorgesehenen Journal-Eintrag), lag aber nur als uncommittete lokale Änderung vor und ist **nicht** Teil des committeten Standes, den dieser Plan voraussetzt. Step 1 unten macht diese Änderung deshalb explizit zum ersten, eigenständigen Schritt dieser Aufgabe, mit eigenem Commit – nicht als stillschweigende Vorbedingung.

**Hinweis zum Review-Befund P1 (Reihenfolge von `growTextarea`):** Ein geschlossenes `<dialog>` wird in einem echten Browser nicht gerendert; `scrollHeight` einer darin liegenden Textarea antwortet deshalb mit `0`, solange `showModal()` noch nicht gelaufen ist. `growTextarea(description)` muss deshalb **nach** `dialog.showModal()` aufgerufen werden, nicht davor – sonst wüchse eine vorbefüllte, mehrzeilige Retitle-Beschreibung erst nach der ersten Eingabe auf ihre wirkliche Höhe. Die Schritte 7 und 8 unten setzen das um; Step 4 fügt dafür einen eigenen Regressionstest hinzu, der das Stand-in-Objekt in dem einen Moment gezielt verändert, der dafür zählt (`dialog.showModal` wird für den Test überschrieben).

**Files:**
- Modify: `custom_components/dashboard_history/panel/dialogs.js:31-46` (`VERSION_FIELDS` – zuerst `maxlength="500"` entfernen, danach zur `<textarea>` umbauen)
- Modify: `docs/superpowers/status.md` (Journal-Eintrag zur Entfernung des Zeichenlimits)
- Modify: `custom_components/dashboard_history/panel.js` (neue Funktion `growTextarea`, direkt nach `shortName`; Methoden `_createVersion` und `_retitleVersion`)
- Modify: `custom_components/dashboard_history/panel/style.js:540-549` (`dialog input.text`)
- Modify: `tests/test_panel_behaviour.py` (`_PRELUDE`: `style`/`scrollHeight` auf dem Stand-in-Knoten; bestehender Test `_RETITLE` – ein geänderter Selektor; vier neue Tests, einer davon nutzt den in Aufgabe 2 eingeführten Helfer `_dialogs_html` weiter)

**Interfaces:**
- Consumes: den Helfer `_dialogs_html(tmp_path_factory)` und die Konstante `DIALOGS_FILE` aus Aufgabe 2 (für den statischen Markup-Test in Step 4) – beide werden hier nicht neu definiert.
- Produces: `growTextarea(textarea): void`, modulweite Funktion in `panel.js` neben `shortName`. Wird von `_createVersion` und `_retitleVersion` gleich verwendet, jeweils **nach** `dialog.showModal()` – jede künftige dritte Stelle mit demselben Feld sollte dieselbe Funktion in derselben Reihenfolge relativ zu `showModal()` aufrufen, nicht eine eigene Höhenberechnung schreiben.

- [ ] **Step 1: Das Zeichenlimit der Beschreibung entfernen (eigener Commit, unabhängig vom Textarea-Umbau unten)**

In `custom_components/dashboard_history/panel/dialogs.js`, den Block

```js
// The two fields a version's words are typed into, and the one place
// they are spelled. Two dialogs ask for them - one making a version,
// one renaming it - and they have to ask the same way: the classes are
// a contract with `panel.js` and with two test harnesses, and a
// `maxlength` that drifted would let one dialog accept a title the
// other refuses, against the same store.
const VERSION_FIELDS = `
      <input class="text title" type="text" maxlength="200"
             placeholder="What is this version?">
      <input class="text desc" type="text" maxlength="500"
             style="margin-top:8px"
             placeholder="Anything more worth remembering (optional)">`;
```

ersetzen durch:

```js
// The two fields a version's words are typed into, and the one place
// they are spelled. Two dialogs ask for them - one making a version,
// one renaming it - and they have to ask the same way: the classes are
// a contract with `panel.js` and with two test harnesses, and a
// `maxlength` that drifted would let one dialog accept a title the
// other refuses, against the same store.
//
// The description carries none (decided 2026-09-29): neither the
// service schemas nor the git commit message it ends up in enforce a
// length, so 500 was never anything but an arbitrary UI number.
const VERSION_FIELDS = `
      <input class="text title" type="text" maxlength="200"
             placeholder="What is this version?">
      <input class="text desc" type="text"
             style="margin-top:8px"
             placeholder="Anything more worth remembering (optional)">`;
```

In `docs/superpowers/status.md`, den Block

```markdown
## Bekannte offene Punkte

Aus der Spec, Abschnitt »Offene Punkte« (dort mit vollem Messbefund). Bei
Zweifeln über den aktuellen Stand zählt der Code, nicht diese Zeile.

- **Behoben am 2026-09-28** (GitHub-Issue [#34](https://github.com/PPP01/ha-dashboard-history/issues/34)):
```

ersetzen durch:

```markdown
## Bekannte offene Punkte

Aus der Spec, Abschnitt »Offene Punkte« (dort mit vollem Messbefund). Bei
Zweifeln über den aktuellen Stand zählt der Code, nicht diese Zeile.

- **Entschieden und umgesetzt am 2026-09-29** (kein Issue, im Zug des
  Dialog-Umbaus für die Versionierung): Das `maxlength="500"` der
  Versions-Beschreibung (`panel/dialogs.js`, `VERSION_FIELDS`) hatte keine
  technische Grundlage – weder die Dienst-Schemas (`services.py`,
  `websocket_api.py`) noch die Ablage als Git-Commit-Message
  (`store.py:_version_body`) begrenzen die Länge. Die Zahl war eine reine
  UI-Vorgabe ohne Bezug zum Speicher und wurde ersatzlos entfernt. Das Feld
  bleibt weiterhin identisch zwischen Create- und Retitle-Dialog (siehe
  Kommentar über `VERSION_FIELDS`) – nur eben ohne Obergrenze in beiden.

- **Behoben am 2026-09-28** (GitHub-Issue [#34](https://github.com/PPP01/ha-dashboard-history/issues/34)):
```

Run: `python3 -m pytest tests/ -v`
Expected: alles weiterhin grün – kein bestehender Test hängt an `maxlength="500"`.

Commit:

```bash
git add custom_components/dashboard_history/panel/dialogs.js docs/superpowers/status.md
git commit -m "$(cat <<'EOF'
Remove the version description's arbitrary length cap

Neither the service schemas (services.py, websocket_api.py) nor the
git commit message the description ends up in (store.py) enforce a
length - 500 was never anything but a UI number nobody could point
to a reason for. Decided 2026-09-29, documented in status.md.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 2: Den Mock um `style`/`scrollHeight` erweitern – ohne das kein Test unten möglich ist**

In `tests/test_panel_behaviour.py`, in der `_PRELUDE`-Konstante, innerhalb der Definition von `node`, den Block

```js
    textContent: "", innerHTML: "", value: "", checked: false,
    hidden: false, returnValue: "", open: false, dataset: {},
    _seen: shared || {}, _on: {},
```

ersetzen durch:

```js
    textContent: "", innerHTML: "", value: "", checked: false,
    hidden: false, returnValue: "", open: false, dataset: {},
    // A textarea's own auto-grow (panel.js's growTextarea) reads
    // scrollHeight and writes style.height; a scenario sets the first
    // by hand - a real browser computes it - and reads the second
    // back.
    style: {}, scrollHeight: 0,
    _seen: shared || {}, _on: {},
```

- [ ] **Step 3: Die restlichen fehlschlagenden Tests schreiben**

Im bestehenden Abschnitt `# -- rows.js, the other half with no behavioural test --`, innerhalb der Konstante `_RETITLE`, die Zeile

```js
const desc = box.querySelector("input.desc");
```

ersetzen durch:

```js
const desc = box.querySelector("textarea.desc");
```

Direkt danach, nach dem letzten Test, der die `retitling`-Fixture verwendet (`test_a_version_that_is_not_in_the_list_opens_nothing`, endet mit `assert retitling["missing"] is False`) und vor der nächsten Konstante `_ROWS = """` (dazwischen nur eine Leerzeile, kein Kommentarblock), diesen neuen Abschnitt einfügen:

```python
# -- the shared description field grows with what is typed into it ---------


def test_the_shared_description_field_is_really_a_textarea(tmp_path_factory):
    # The mock's querySelector answers any selector with a phantom node
    # regardless of what dialogs.js contains - this reads the real
    # markup instead, the same way Aufgabe 2's toggle-pair test does.
    html = _dialogs_html(tmp_path_factory)
    assert '<textarea class="text desc"' in html
    assert 'maxlength="500"' not in html
    assert '<input class="text desc"' not in html


_CREATE_GROWS = """
const changes = [{ revision: "c", message: "3rd card added", versions: [] }];
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._changes = changes;
el.shadowRoot = node();
el._reloadAfterWrite = async () => null;
el._call = (type) =>
  type === "next_versions"
    ? Promise.resolve({ candidates: { patch: "dash/v1.0.1" } })
    : Promise.resolve({ created: "dash/v1.0.1" });

const versioning = el._createVersion("c");
await settle();
const dialog = el.shadowRoot.querySelector("dialog.version");
const description = dialog.querySelector("textarea.desc");
description.scrollHeight = 84;
description.value = "A longer note than the one line the field starts at.";
description._on.input();
const grownHeight = description.style.height;
dialog.close("create");
await versioning;
console.log(JSON.stringify({ grownHeight }));
"""


@pytest.fixture(scope="session")
def create_grows(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "create_grows", _CREATE_GROWS)


def test_the_create_dialogs_description_grows_with_its_content(create_grows):
    assert create_grows["grownHeight"] == "84px"


_RETITLE_GROWS = """
const versions = [
  { name: "dash/v1.0.0", title: "Autumn tidy", description: "the old note",
    revision: "a", automatic: false },
];
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._versions = versions;
el.shadowRoot = node();
el._reloadAfterWrite = async () => null;
el._call = () => Promise.resolve({ applied: true });

const editing = el._retitleVersion("dash/v1.0.0");
await settle();
const dialog = el.shadowRoot.querySelector("dialog.retitle");
const description = dialog.querySelector("textarea.desc");
description.scrollHeight = 96;
description.value = "the old note, now with a good deal more to it";
description._on.input();
const grownHeight = description.style.height;
dialog.close("save");
await editing;
console.log(JSON.stringify({ grownHeight }));
"""


@pytest.fixture(scope="session")
def retitle_grows(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "retitle_grows", _RETITLE_GROWS)


def test_the_retitle_dialogs_description_also_grows_with_its_content(retitle_grows):
    # The two dialogs share one description field by design (see the
    # comment over VERSION_FIELDS in dialogs.js) - wiring the fix into
    # only one of them would be exactly the drift that comment warns
    # about.
    assert retitle_grows["grownHeight"] == "96px"


_RETITLE_GROWS_ON_OPEN = """
const versions = [
  { name: "dash/v1.0.0", title: "Autumn tidy",
    description: "A note that already spans more than the one line the field starts collapsed to.",
    revision: "a", automatic: false },
];
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._versions = versions;
el.shadowRoot = node();
el._reloadAfterWrite = async () => null;
el._call = () => Promise.resolve({ applied: true });

const dialog = el.shadowRoot.querySelector("dialog.retitle");
const description = dialog.querySelector("textarea.desc");
// A closed <dialog> is not laid out in a real browser, so scrollHeight
// answers 0 until showModal() actually renders it. The stand-in cannot
// compute a real scrollHeight on its own, so this fakes the one fact
// that matters: it only becomes the real content height once
// showModal() has run - exactly the ordering growTextarea must match.
description.scrollHeight = 0;
const realShowModal = dialog.showModal.bind(dialog);
dialog.showModal = () => {
  realShowModal();
  description.scrollHeight = 130;
};

const editing = el._retitleVersion("dash/v1.0.0");
await settle();
const heightOnOpen = description.style.height;
dialog.close("save");
await editing;
console.log(JSON.stringify({ heightOnOpen }));
"""


@pytest.fixture(scope="session")
def retitle_grows_on_open(tmp_path_factory):
    return _run_in_node(
        tmp_path_factory, "retitle_grows_on_open", _RETITLE_GROWS_ON_OPEN
    )


def test_a_prefilled_multiline_description_grows_the_moment_the_dialog_opens(
    retitle_grows_on_open,
):
    # growTextarea must run after dialog.showModal(), not before - a
    # closed <dialog> answers 0 for scrollHeight in a real browser, and
    # calling it too early would grow the field to fit nothing at all,
    # leaving a long prefilled description clipped until the first
    # keystroke recalculated it.
    assert retitle_grows_on_open["heightOnOpen"] == "130px"
```

- [ ] **Step 4: Tests laufen lassen, sie müssen fehlschlagen**

Run: `python3 -m pytest tests/test_panel_behaviour.py -k "retitle or grows or shared_description" -v`
Expected: FAIL. `test_the_shared_description_field_is_really_a_textarea` findet weiterhin `<input class="text desc"` und kein `<textarea`. Die drei `_RETITLE`/`_grows`-Szenarien scheitern daran, dass `description._on.input` bzw. `dialog.showModal` (als überschreibbare Funktion) nicht das erwartete Verhalten zeigen, weil `panel.js` weder einen `input`-Listener verkabelt noch `growTextarea` aufruft.

- [ ] **Step 5: Feld in `dialogs.js` zur Textarea machen**

In `custom_components/dashboard_history/panel/dialogs.js`, den Block (Stand nach Step 1 dieser Aufgabe, also bereits ohne `maxlength="500"`)

```js
const VERSION_FIELDS = `
      <input class="text title" type="text" maxlength="200"
             placeholder="What is this version?">
      <input class="text desc" type="text"
             style="margin-top:8px"
             placeholder="Anything more worth remembering (optional)">`;
```

ersetzen durch:

```js
const VERSION_FIELDS = `
      <input class="text title" type="text" maxlength="200"
             placeholder="What is this version?">
      <textarea class="text desc" rows="1"
                style="margin-top:8px"
                placeholder="Anything more worth remembering (optional)"></textarea>`;
```

- [ ] **Step 6: `growTextarea` in `panel.js` ergänzen**

Direkt nach der Funktion

```js
function shortName(name) {
  return name.split("/").pop();
}
```

und vor `class DashboardHistoryPanel extends HTMLElement {`, diese neue Funktion einfügen:

```js
/**
 * Grows a textarea to fit what has been typed into it, so a longer
 * note is never hidden behind a scrollbar of its own. Call this only
 * after the dialog it lives in has been shown (showModal()) - a
 * closed <dialog> is not laid out, so scrollHeight would still answer
 * for whatever was last rendered, typically 0. Two dialogs share the
 * one description field (see the comment over VERSION_FIELDS in
 * dialogs.js) and both wire this the same way, in the same order.
 */
function growTextarea(textarea) {
  textarea.style.height = "auto";
  textarea.style.height = `${textarea.scrollHeight}px`;
}
```

- [ ] **Step 7: In `_createVersion` verkabeln – `growTextarea` erst nach `showModal()`**

In der Methode `_createVersion`, den Block

```js
    const title = dialog.querySelector("input.title");
    const description = dialog.querySelector("input.desc");
    title.value = "";
    description.value = "";
    dialog.returnValue = "";
    dialog.showModal();
```

ersetzen durch:

```js
    const title = dialog.querySelector("input.title");
    const description = dialog.querySelector("textarea.desc");
    title.value = "";
    description.value = "";
    description.addEventListener("input", () => growTextarea(description));
    dialog.returnValue = "";
    dialog.showModal();
    growTextarea(description);
```

- [ ] **Step 8: In `_retitleVersion` verkabeln – dieselbe Reihenfolge**

In der Methode `_retitleVersion`, den Block

```js
    const title = dialog.querySelector("input.title");
    const description = dialog.querySelector("input.desc");
    title.value = version.title || "";
    description.value = version.description || "";
    dialog.returnValue = "";
    dialog.showModal();
```

ersetzen durch:

```js
    const title = dialog.querySelector("input.title");
    const description = dialog.querySelector("textarea.desc");
    title.value = version.title || "";
    description.value = version.description || "";
    description.addEventListener("input", () => growTextarea(description));
    dialog.returnValue = "";
    dialog.showModal();
    growTextarea(description);
```

- [ ] **Step 9: Tests laufen lassen, sie müssen bestehen**

Run: `python3 -m pytest tests/test_panel_behaviour.py -k "retitle or grows or shared_description" -v`
Expected: alle PASS.

- [ ] **Step 10: Optik in `style.js` ergänzen**

Den Block

```css
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

ersetzen durch:

```css
  dialog input.text, dialog textarea.text {
    width: 100%;
    padding: 10px 12px;
    border: 1px solid var(--divider-color, #e0e0e0);
    border-radius: 4px;
    background: var(--card-background-color, #fff);
    color: inherit;
    font: inherit;
    box-sizing: border-box;
  }
  dialog textarea.text {
    resize: none;
    overflow: hidden;
    min-height: 40px;
  }
```

- [ ] **Step 11: Stille CSS-Wächter und ganze Suite laufen lassen**

Run: `python3 -m pytest tests/ -v`
Expected: alles grün.

- [ ] **Step 12: Commit**

```bash
git add custom_components/dashboard_history/panel/dialogs.js \
        custom_components/dashboard_history/panel.js \
        custom_components/dashboard_history/panel/style.js \
        tests/test_panel_behaviour.py
git commit -m "$(cat <<'EOF'
Let the version's description grow instead of scroll

growTextarea reads scrollHeight on input and grows the shared
textarea to fit, wired identically into both dialogs that share this
field (see the comment over VERSION_FIELDS), and always after
showModal() rather than before - a closed <dialog> is not laid out in
a real browser, so scrollHeight would still answer for whatever was
last rendered. A regression test pins a prefilled, multi-line retitle
description growing correctly the moment the dialog opens, not only
after the first keystroke. A static check against the real DIALOGS
markup confirms the field is genuinely a <textarea> now, the same way
Aufgabe 2's toggle-pair check confirms its own markup.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Aufgabe 4: Gesamtprüfung

**Files:**
- Keine Code-Änderung – reine Verifikation.

**Interfaces:**
- Consumes: den Endstand aller drei vorherigen Aufgaben.
- Produces: einen Abschlussbericht (siehe Step 4) für die Person, die diesen Plan freigegeben hat.

- [ ] **Step 1: Ganze Testsuite**

Run: `python3 -m pytest tests/ -v`
Expected: alles grün, keine übersprungenen Fälle außer den schon vorher übersprungenen (echte Dashboards ohne `DASHBOARD_HISTORY_REAL_STORAGE`/`tests/.real-storage`, `node` falls nicht installiert).

- [ ] **Step 2: Komplexitäts-Sperrklinke**

Run: `python3 tools/complexity_ratchet.py`
Expected: Exit-Code 0. Keine der geänderten Funktionen (`renderDiff`, `_createVersion`, `_retitleVersion`, `growTextarea`) darf in der Ausgabe als neu oder gewachsen erscheinen.

- [ ] **Step 3: Importverträge**

Run: `lint-imports`
Expected: `Contracts: 2 kept, 0 broken.` (oder die zum Zeitpunkt der Ausführung aktuelle Vertragszahl) – unverändert, da kein HA-freies Modul angefasst wurde.

- [ ] **Step 4: Abschlussbericht schreiben, nicht stillschweigend als fertig melden**

Dieser Plan ändert nur Markup, JavaScript-Logik und CSS – keiner der Schritte oben kann eine Layout-Frage beantworten, die eine echte Rendering-Engine braucht. Im Abschlussbericht an die Person, die diesen Plan freigegeben hat, ausdrücklich benennen, dass die folgenden Punkte **noch nicht** visuell geprüft sind und einen Blick in einen echten Browser brauchen (`docker compose -f docker/compose.yaml up -d`, siehe `docker/README.md`, oder die Playwright-Tools):

1. Der Umschalter im Create-Version-Dialog sieht wie der freigegebene Entwurf aus (Label »Included«, zwei Pillen, genau eine gedrückt, Umbruch unter 600px Breite).
2. Die Diff-Box ist tatsächlich heller als vorher, mit sichtbarer Umrandung, und die Volltonfarbe je Zeile reicht bei einer sehr breiten, langen Zeile über die gesamte scrollbare Breite (Review-Focus-Punkt 6 – von keinem Test hier abgedeckt).
3. Die Beschreibungs-Textarea wächst beim Tippen sichtbar mit, ohne einen eigenen Scrollbalken zu zeigen, in beiden Dialogen – und eine vorbefüllte, mehrzeilige Retitle-Beschreibung ist schon beim Öffnen in voller Höhe zu sehen, nicht erst nach der ersten Eingabe.

Kein Schritt dieses Plans committet, pusht oder taggt über das oben Genannte hinaus – das bleibt, wie in den Global Constraints festgehalten, bei der Person, die freigibt.
