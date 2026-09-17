# Vorhaben K — Schmal bedienbar: Implementierungsplan

> **Für agentische Ausführung:** ERFORDERLICHER SUB-SKILL: `superpowers:subagent-driven-development` (empfohlen) oder `superpowers:executing-plans`, Aufgabe für Aufgabe. Die Schritte tragen Kästchen (`- [ ]`).

**Ziel:** Das Panel von rund 360 bis 2560 px durchgehend bedienbar machen — mit dem Home-Assistant-Menü erreichbar, ohne waagerechtes Scrollen, ohne zweite Oberfläche.

**Architektur:** Die Spaltenzahl richtet sich über `@container` nach der Breite des **Panels**, nicht des Fensters; der Menüknopf folgt Home Assistants `narrow`. Unterhalb des schmalen Bandes zeigt das Layout entweder die Dashboard-Liste oder den Verlauf; welche, sagt ein Attribut, das CSS liest — JavaScript misst nie.

**Technik:** Reines Shadow-DOM ohne Home-Assistant-Komponenten, CSS Container Queries, CDP für die Aufnahmen. Kein Build-Schritt, keine Abhängigkeit kommt hinzu.

**Spec:** `docs/superpowers/specs/2026-08-30-dashboard-history-design.md`, Entscheidung 20 (Festlegungen 1–7) und »Nachgetragen am 2026-09-17: K«. Bei Widersprüchen zwischen diesem Plan und der Spec gilt die Spec.

## Durchgehende Vorgaben

Gelten für **jede** Aufgabe, ohne dass sie dort wiederholt werden:

- **Berührt werden ausschließlich** `custom_components/dashboard_history/panel.js`, `custom_components/dashboard_history/panel/style.js`, `tools/capture_demo_screenshots.py` und `tests/test_panel_behaviour.py`. K fasst keine Logik an — nichts an `store.py`, `analyze.py`, `restore.py`, `operations.py`, `versions.py`, `keys.py`, `yaml_io.py` oder den beiden Schnittstellen.
- **Kein Backtick in `style.js`.** Der ganze Inhalt ist ein Template-Literal (`export const STYLE = \`…\``), und ein Backtick in einem CSS-Kommentar beendet es. Gemessen am 2026-09-17: `SyntaxError: Unexpected identifier`. Code-Namen in den Kommentaren dort stehen deshalb ohne Auszeichnung — `_showsMenuButton`, nicht in Backticks. Die CSS-Blöcke in diesem Plan sind bereits so geschrieben; `node --input-type=module --check` fängt einen Rückfall sofort.
- **Keine Home-Assistant-Komponenten im Panel.** Kein `<ha-...>`-Element, kein Lit, kein Import aus dem Frontend-Bündel.
- **Englisch** in Code, Kommentaren und Commit-Nachrichten. Commit-Betreff im Imperativ, erster Buchstabe groß, max. 50 Zeichen; Leerzeile; Fließtext auf 72 Zeichen umgebrochen, der das *Warum* erklärt.
- **Das Basis-CSS bleibt die heutige Zweispaltigkeit.** `@container`-Regeln verengen nur. Ein Browser ohne `@container` muss genau das bekommen, was er heute bekommt.
- **Nach jeder Änderung an einer Panel-Datei ist der Container neu zu starten**, sonst meldet `run_checks.py` den Fingerabdruck als veraltet — das ist dann kein Codefehler, sondern ein alter Container:
  ```bash
  docker compose -f docker/compose.yaml restart
  ```
- **`pytest` muss grün bleiben.** Die Zahl der Tests schwankt mit den Dashboards der echten `.storage`; zählbar ist allein »0 failed«.
- **Nichts wird gepusht.** Committen ja, `git push` nur auf ausdrückliche Ansage des Nutzers.

### Die drei Prüfmittel, und was jedes kann

| Mittel | Befehl | Beantwortet |
|---|---|---|
| Syntax | `node --input-type=module --check < <datei>` | Ist die Datei noch gültiges ES-Modul? Fängt jeden Tippfehler in Sekunden |
| Integration | `python3 tests/integration/run_checks.py` | Wird `panel.js` samt aller Teile ausgeliefert, und stimmt der Fingerabdruck in der Modul-URL? |
| Verhalten | `python3 -m pytest tests/test_panel_behaviour.py -v` | Was tut die Panel-Logik bei gleichzeitigen und verspäteten Abläufen? |
| Layout | die Wegwerf-Sonde aus Aufgabe 1, Schritt 8 | Was misst der Browser an der laufenden Seite wirklich? |

⚠️ **`docScrolls: false` ist kein Beleg dafür, dass alles hineinpasst.** `.main` trägt `overflow-y: auto`, und CSS hebt die waagerechte Achse mit auf `auto` — zu breiter Inhalt scrollt dann **in der Spalte** und erreicht das Dokument nie. Jede Aufgabe, die »kein waagerechtes Scrollen« behauptet, liest **`mainCutOff`** aus der Sonde, nicht `docScrolls`.

`sticksOut` daneben ist ein **Hinweis, kein Kriterium**: Es listet auch Boxen, die niemand sieht — `.card` trägt `overflow: hidden` und schneidet seine Kinder ab, `.pen` steht außerhalb des Berührungszweigs auf `opacity: 0`. Am 2026-09-17 meldete es fünf `pen`, während `.main` `scrollWidth == clientWidth` antwortete. Es sagt, **wo** man suchen soll, wenn `mainCutOff` rot ist.

**`tests/test_panel_behaviour.py` ist der wichtigste davon, und die erste Fassung dieses Plans hat ihn übersehen.** Dort steht: »`panel.js` ist ein Custom Element, aber die Teile davon, die auf eine Weise falsch sein können, die niemand sieht — was es mit einer zu spät eintreffenden Antwort tut — brauchen keinen Browser.« Node lädt das Modul mit einem DOM-Ersatz, der Test ersetzt `_call` durch Versprechen, die er von Hand einlöst, und sieht sich danach den Zustand an, in dem das Panel steht.

Genau das ist die Form, in der `_pane` zu prüfen ist. Die Übergänge aus Festlegung 4 sind Abläufe mit Gleichzeitigkeit — eine Vorauswahl, die noch lädt, während jemand tippt —, und das ist die Fehlerklasse, die an einem Screenshot unsichtbar bleibt und in einer Handprüfung nur zufällig auftritt. **Aufgabe 1 und Aufgabe 5 bekommen deshalb echte Test-zuerst-Zyklen**, keine bloße Handprüfung.

Was `pytest` weiterhin **nicht** sieht: jede Zeile CSS. Die Aufgaben 2, 3, 4 und 6 haben deshalb die Sonde als Prüfmittel und sonst nichts — das ist kein Versäumnis, sondern die Grenze des Machbaren, und der Grund, warum die Sonde misst statt zu behaupten.

---

## Welche Festlegung wo landet

Damit nachlesbar ist, dass nichts aus Entscheidung 20 unter den Tisch fällt:

| Spec | Aufgabe |
|---|---|
| Festlegung 1 — Hamburger als eigener Knopf, der `hass-toggle-menu` feuert | 1 |
| Festlegung 2 — gemessen wird die Panel-Breite (`@container`), Zahlen hier | 2 |
| Festlegung 3 — eine Spalte, Master/Detail | 5 |
| Festlegung 4 — CSS entscheidet; `_pane` und die drei Übergänge | 5 |
| Festlegung 5 — Balken bricht um, `calc(100% - 56px)` fällt | 3 |
| Festlegung 6 — Suchzeile bricht um, 360-px-Kriterium | 4 |
| Festlegung 7 — Tippziele unter `@media (hover: none)` | 6 |
| Abnahme — Aufnahmen, `hover`-Nachweis in beide Richtungen, 900-px-Bild | 7 |
| Abnahme — die fünf Übergänge von Hand | 5, Schritt 11 |
| Prüfung der Logik hinter Festlegung 1 und 4 | 1 Schritt 1–4, 5 Schritt 1–6 (Node, `test_panel_behaviour.py`) |

Die Reihenfolge der Aufgaben folgt nicht der Nummerierung der Festlegungen, sondern dem Risiko: Aufgabe 1 behebt den einzigen Befund, der ausweglos ist; Aufgabe 3 muss vor 5 liegen, weil ein festgenagelter Balken die Master/Detail-Prüfung an einem fremden Fehler scheitern ließe.

---

## Dateien und Zuständigkeit

| Datei | Was sich ändert |
|---|---|
| `custom_components/dashboard_history/panel.js` | `set narrow`, der Menüknopf und sein Ereignis, `_pane` samt den drei Übergängen, die Weiche in `_select`, der Zurück-Knopf, `data-pane` am Layout |
| `custom_components/dashboard_history/panel/style.js` | `container-type` auf dem Host, drei Bänder, Master/Detail-Regeln, umbrechender Balken, Flex statt `calc(100% - 56px)`, umbrechende Suchzeile, Tippziele |
| `tools/capture_demo_screenshots.py` | Chrome-Startoption für den Desktop-Zweig, Umschalten auf den Berührungszweig, vier schmale Aufnahmen, die 900-px-Aufnahme, `matchMedia`-Nachweis je Bild |
| `tests/test_panel_behaviour.py` | Zwei neue Szenarien: der Menüknopf und seine Bedingung (Aufgabe 1), `_pane` samt Renn-Fall bei der Vorauswahl (Aufgabe 5) |

Keine neue Datei. `style.js` ist mit 1188 Zeilen groß, aber sortiert nach Bildschirmbereichen, und dieses Vorhaben fügt an den vorhandenen Stellen ein — ein Aufteilen wäre eine eigene Entscheidung und gehört nicht in K.

---

## Aufgabe 1: Der Menüknopf und `narrow`

Ohne ihn ist das Panel auf dem Handy eine Sackgasse. Zuerst, weil es der einzige Befund ist, der nicht nur unschön, sondern ausweglos ist — und weil die Aufgabe für sich steht: Sie funktioniert auch dann, wenn alles Übrige noch aussieht wie heute.

**Dateien:**
- Ändern: `custom_components/dashboard_history/panel.js` (`set hass` Zeile 552; Balken-Markup Zeile 3246; Verdrahtung Zeile 3320)
- Ändern: `custom_components/dashboard_history/panel/style.js` (`.bar`-Block ab Zeile 34)
- Test: `tests/test_panel_behaviour.py`

**Schnittstellen:**
- Verbraucht: nichts aus anderen Aufgaben
- Liefert: `this._narrow` (Boolean), `_showsMenuButton()` → Boolean, `_refreshMenuButton()`. Aufgabe 5 liest keines davon — dort entscheidet CSS

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

Ans Ende von `tests/test_panel_behaviour.py`. Die Form ist die der übrigen Fälle dort: ein Szenario-String, der in Node läuft, eine Fixture, die ihn ausführt, und Behauptungen über das Ergebnis.

```python
# -- when the panel has to offer the way into the sidebar -------------------
#
# Home Assistant hides its sidebar below 870px and expects the page to
# provide the button. The condition is not only `narrow`: pinning the
# sidebar away changes it too, and it arrives through `hass`, which is
# assigned again and again without ever drawing.

_HARNESS_MENU = """
const make = () => {
  const p = new Panel();
  p._renders = 0;
  p._render = () => { p._renders += 1; };
  p._listen = () => {};
  // As if a first picture had been drawn: the setters below only redraw
  // once there is something to redraw.
  p.shadowRoot = { firstChild: {} };
  // So that assigning `hass` does not start loading dashboards.
  p._loaded = true;
  return p;
};

const asks = (hass, narrow) => {
  const p = make();
  p._hass = hass;
  p._narrow = narrow;
  return p._showsMenuButton();
};

// A dock change while the window stays wide still has to reach the bar,
// and an ordinary state update must not redraw the whole page.
const live = make();
live._hass = { dockedSidebar: "docked" };
live._menuShown = false;
live.hass = { dockedSidebar: "always_hidden" };
const drewOnDockChange = live._renders;
live.hass = { dockedSidebar: "always_hidden", states: {} };
const drewAgainOnNoChange = live._renders - drewOnDockChange;

console.log(JSON.stringify({
  narrowAlone: asks({}, true),
  pinnedAway: asks({ dockedSidebar: "always_hidden" }, false),
  wideAndDocked: asks({ dockedSidebar: "docked" }, false),
  kioskBeatsBoth: asks({ kioskMode: true, dockedSidebar: "always_hidden" }, true),
  withoutAnyKioskFlag: asks({ dockedSidebar: "always_hidden" }, false),
  drewOnDockChange,
  drewAgainOnNoChange,
}));
"""


@pytest.fixture(scope="module")
def menu(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "menu", _HARNESS_MENU)


def test_the_menu_button_shows_when_the_window_is_narrow(menu):
    assert menu["narrowAlone"] is True


def test_the_menu_button_shows_when_the_sidebar_is_pinned_away(menu):
    # Home Assistant's own rule, and the half that is easy to forget:
    # a wide window with `always_hidden` has no sidebar to click either.
    assert menu["pinnedAway"] is True


def test_the_menu_button_stays_away_where_the_sidebar_is(menu):
    assert menu["wideAndDocked"] is False


def test_kiosk_mode_beats_both(menu):
    assert menu["kioskBeatsBoth"] is False


def test_an_installation_without_kiosk_mode_still_gets_the_button(menu):
    # The one deliberate difference from Home Assistant's code, which
    # writes `false === kioskMode` because it reads the flag from a
    # context that always has one. Off `hass` it is simply absent, and
    # `=== false` would hide the button for everybody.
    assert menu["withoutAnyKioskFlag"] is True


def test_pinning_the_sidebar_away_redraws_the_bar(menu):
    # `set hass` runs on every state change in the house and never drew.
    # Without this the button appears only after something else happens
    # to redraw the page.
    assert menu["drewOnDockChange"] == 1


def test_an_ordinary_state_update_does_not_redraw(menu):
    # And the other side of it: comparing the condition rather than
    # rendering on every assignment, or the panel repaints per event.
    assert menu["drewAgainOnNoChange"] == 0
```

- [ ] **Schritt 2: Den Test laufen lassen und scheitern sehen**

```bash
python3 -m pytest tests/test_panel_behaviour.py -k "menu or kiosk or pinning_the_sidebar or ordinary_state_update" -v
```

Erwartet: **FAIL** — `_showsMenuButton is not a function`.

**`-k menu` allein reicht nicht** und wäre die Art Prüfung, die grün aussieht und nichts sagt: Nur drei der sieben Namen enthalten »menu«, und `-k` sieht Fixture-Namen nicht — am 2026-09-17 nachgemessen, `-k menu` wählt 3 von 7 aus.

- [ ] **Schritt 3: Accessor, Regel und Ereignis einsetzen**

In `panel.js`, direkt hinter `set hass` (endet bei Zeile 570):

```js
  /**
   * Home Assistant's own "the sidebar is not there" flag.
   *
   * `ha-panel-custom` assigns `panel`, `hass`, `narrow` and `route` on
   * this element and keeps them current; `narrow` follows the media
   * query `(max-width: 870px)`. Read out of the frontend bundle of
   * 2026.8.3 on 2026-09-17, not assumed. Until now only `hass` was
   * read, so this arrived and fell on the floor - and with it the one
   * thing that says whether this page has to provide the menu button.
   *
   * The accessor has to exist by the time the element is defined, for
   * the reason written out at the top of this file: Home Assistant may
   * assign to a not-yet-upgraded element, and the plain own property
   * that creates shadows the accessor for good.
   *
   * Only the menu button depends on this. How many columns there are is
   * decided by CSS against the panel's own width, which is a different
   * question - see the stylesheet's `@container` bands.
   */
  set narrow(value) {
    this._narrow = Boolean(value);
    this._refreshMenuButton();
  }

  get narrow() {
    return this._narrow;
  }

  /**
   * Whether this page has to offer the way into the sidebar.
   *
   * Home Assistant's own rule, taken from `ha-menu-button` on
   * 2026-09-17: show it where the sidebar is not there to be clicked -
   * narrow, or pinned away - and never in kiosk mode, whose whole point
   * is that there is no chrome.
   *
   * One deliberate difference. Home Assistant writes `false ===
   * kioskMode`, because it reads the flag from a context that always
   * carries one. Here it comes off `hass`, where an installation
   * without kiosk mode simply has none - and `=== false` would then be
   * false for everybody and hide the button always. `!== true` is the
   * same rule applied to the shape the data actually has here.
   */
  _showsMenuButton() {
    if (this._hass?.kioskMode === true) return false;
    return Boolean(this._narrow) || this._hass?.dockedSidebar === "always_hidden";
  }

  /**
   * Redraw if, and only if, the button's answer changed.
   *
   * Called from both setters, because both carry part of the condition:
   * `narrow` from the window, `dockedSidebar` and `kioskMode` from
   * `hass`. `set hass` runs on every state change in the house, so a
   * render there would be a repaint per event - and leaving it out
   * altogether was the bug: pinning the sidebar away at a wide window
   * left the button that replaces it invisible until something else
   * happened to draw.
   *
   * Nothing else depends on `narrow`, which is why this is the whole
   * reaction to it and not a first step.
   */
  _refreshMenuButton() {
    const shows = this._showsMenuButton();
    if (shows === this._menuShown) return;
    this._menuShown = shows;
    // Not before the first picture. The constructor attaches the shadow
    // root and draws nothing, and the parts this draws from are still
    // being imported at that point - rendering here would put
    // `undefined` in the stylesheet. An empty shadow root is exactly
    // that state.
    if (this.shadowRoot?.firstChild) this._render();
  }

  /**
   * Open Home Assistant's sidebar.
   *
   * What `ha-menu-button` does, without being it: that element lives in
   * a lazily loaded frontend chunk whose presence on a custom panel
   * page is promised nowhere, and this panel deliberately uses no Home
   * Assistant components at all. `home-assistant-main` listens for this
   * event on itself, so it has to leave the shadow root - which is what
   * `composed` is for. `bubbles` alone would not be enough.
   */
  _toggleHassMenu() {
    this.dispatchEvent(
      new CustomEvent("hass-toggle-menu", { bubbles: true, composed: true }),
    );
  }
```

Und in `set hass`, als **letzte** Zeile des Setters, hinter `this._listen();`:

```js
    // `dockedSidebar` and `kioskMode` arrive here, not through `narrow`.
    this._refreshMenuButton();
```

- [ ] **Schritt 4: Den Test laufen lassen und bestehen sehen**

```bash
python3 -m pytest tests/test_panel_behaviour.py -k "menu or kiosk or pinning_the_sidebar or ordinary_state_update" -v
```

Erwartet: **7 passed**. Steht dort »3 passed«, wurde mit `-k menu` gefiltert und vier Fälle sind gar nicht gelaufen.

- [ ] **Schritt 5: Den Knopf in den Balken zeichnen**

In `_render()`, im `<div class="bar">` (Zeile 3246), **als erstes Kind** — vor `<span>Dashboard History</span>`:

```js
        ${this._showsMenuButton()
        ? `<button class="menu" data-menu="1" title="Open the Home Assistant sidebar"
                   aria-label="Open the Home Assistant sidebar">
             <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
               <path d="M3 6h18v2H3zm0 5h18v2H3zm0 5h18v2H3z"/>
             </svg>
           </button>`
        : ""}
```

Und die Verdrahtung neben `onClick(".dash", ...)` (Zeile 3320):

```js
    onClick(".menu", () => this._toggleHassMenu());
```

- [ ] **Schritt 6: Den Knopf gestalten**

In `style.js`, hinter dem `.bar .reload:hover`-Block (Zeile 82):

```css
  /* Home Assistant's menu button, drawn here because a custom panel has
     to provide its own - see _showsMenuButton for the rule that
     decides when. Sized like the built-in one and inheriting the bar's
     colour, so it does not read as a control belonging to this panel
     rather than to the page around it. */
  .bar .menu {
    flex: 0 0 auto;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 40px;
    height: 40px;
    margin-left: -8px;
    padding: 0;
    border: 0;
    border-radius: 50%;
    background: transparent;
    color: inherit;
    cursor: pointer;
  }
  .bar .menu svg { width: 24px; height: 24px; fill: currentColor; }
  .bar .menu:hover { background: rgba(127, 127, 127, 0.16); }
```

- [ ] **Schritt 7: Syntax und die volle Testsuite**

```bash
node --input-type=module --check < custom_components/dashboard_history/panel.js
node --input-type=module --check < custom_components/dashboard_history/panel/style.js
python3 -m pytest tests/ -q
```

Erwartet: beide Syntaxprüfungen ohne Ausgabe, `pytest` mit `0 failed`.

- [ ] **Schritt 8: Die Wegwerf-Sonde anlegen und den Knopf messen**

Diese Sonde wird in den Aufgaben 2 bis 6 wiederverwendet. Sie gehört **nicht** ins Repository — sie liegt im Scratchpad-Verzeichnis der Sitzung.

```python
"""Throwaway: what does the browser actually measure on the live panel?

Not committed. Reads the test instance the way run_checks.py does:
HA_TEST_URL (default http://127.0.0.1:8124) and token.txt beside the
instance's configuration, both outside this repository.

    python3 <scratchpad>/probe_layout.py 390 844
"""
import asyncio, json, os, pathlib, subprocess, sys, tempfile, time, urllib.request
import websockets

BASE = os.environ.get("HA_TEST_URL", "http://127.0.0.1:8124")
# Exactly where run_checks.py looks: HA_TEST_CONFIG, or the instance
# beside this repository. Both outside it - the token is a credential.
REPO = pathlib.Path(os.environ.get("DASHBOARD_HISTORY_REPO", pathlib.Path.cwd()))
CONFIG = pathlib.Path(
    os.environ.get("HA_TEST_CONFIG", REPO.parent / "ha-dashboard-history-test" / "config")
)
TOKEN = CONFIG.parent / "token.txt"
PORT, PROFILE = 9410, tempfile.mkdtemp(prefix="probe-")
WIDTH = int(sys.argv[1]) if len(sys.argv) > 1 else 390
HEIGHT = int(sys.argv[2]) if len(sys.argv) > 2 else 844
TOUCH = "--touch" in sys.argv

class S:
    def __init__(self, ws): self.ws, self.n, self.sid = ws, 0, None
    async def send(self, m, p=None, *, browser=False):
        self.n += 1
        msg = {"id": self.n, "method": m, "params": p or {}}
        if self.sid and not browser: msg["sessionId"] = self.sid
        await self.ws.send(json.dumps(msg))
        while True:
            got = json.loads(await self.ws.recv())
            if got.get("id") == self.n:
                if "error" in got: raise RuntimeError(f"{m}: {got['error']}")
                return got.get("result", {})
    async def js(self, e):
        r = await self.send("Runtime.evaluate", {"expression": e, "returnByValue": True, "awaitPromise": True})
        return r.get("result", {}).get("value")

# The panel element sits inside Home Assistant's own shadow roots, not in
# the document - the same walk capture_demo_screenshots.py uses (PANEL).
REPORT = """(() => {
  const walk = (root) => {
    const hit = root.querySelector("dashboard-history-panel");
    if (hit) return hit;
    for (const node of root.querySelectorAll("*")) if (node.shadowRoot) {
      const found = walk(node.shadowRoot); if (found) return found; }
    return null;
  };
  const host = walk(document);
  const r = host && host.shadowRoot;
  const box = (sel) => {
    const el = r && r.querySelector(sel);
    if (!el) return null;
    const b = el.getBoundingClientRect();
    return { w: Math.round(b.width), h: Math.round(b.height), shown: b.width > 0 && b.height > 0 };
  };
  return JSON.stringify({
    hoverNone: matchMedia("(hover: none)").matches,
    pointerCoarse: matchMedia("(pointer: coarse)").matches,
    innerWidth: innerWidth,
    panelWidth: host ? Math.round(host.getBoundingClientRect().width) : null,
    docScrolls: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    overflowBy: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    // `docScrolls` alone is not enough, and believing it would have
    // passed a broken panel. `.main` carries `overflow-y: auto`, and
    // CSS raises the other axis to `auto` with it - so content wider
    // than the column scrolls INSIDE it and never reaches the document.
    // Measured on 2026-09-17 at 390px: the document did not scroll while
    // `.main` was 179px wide around 440px of content.
    mainCutOff: (() => {
      const el = r && r.querySelector(".main");
      return el ? { scrollW: el.scrollWidth, clientW: el.clientWidth,
                    cutOff: el.scrollWidth > el.clientWidth + 1 } : null;
    })(),
    // A HINT, not a criterion. It lists boxes whose right edge is past
    // the column's, which includes ones nothing can see: `.card` has
    // `overflow: hidden` and clips its children, and `.pen` sits at
    // `opacity: 0` outside the touch branch. Both showed up here on
    // 2026-09-17 while `.main` reported no overflow at all. The hard
    // answer is `mainCutOff`, which asks the scroll container itself.
    sticksOut: (() => {
      const main = r && r.querySelector(".main");
      if (!main) return null;
      const edge = main.getBoundingClientRect().right + 1;
      return [...main.querySelectorAll("*")]
        .filter((e) => e.getBoundingClientRect().right > edge)
        .slice(0, 6).map((e) => e.className || e.tagName);
    })(),
    bar: box(".bar"), side: box(".side"), main: box(".main"),
    menu: box(".bar .menu"), back: box(".bar .back"), reload: box(".bar .reload"),
    search: box(".search"), find: box(".search .find"),
    pane: host ? host.getAttribute("data-pane") : null
  }, null, 1);
})()"""

async def main():
    token = TOKEN.read_text().strip()
    chrome = subprocess.Popen(
        ["google-chrome", "--headless=new", f"--remote-debugging-port={PORT}",
         f"--user-data-dir={PROFILE}", "--no-first-run", "--no-default-browser-check",
         "--disable-extensions",
         "--blink-settings=availableHoverTypes=2,primaryHoverType=2,"
         "availablePointerTypes=4,primaryPointerType=4",
         "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        endpoint = None
        for _ in range(40):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=1) as r:
                    endpoint = json.load(r)["webSocketDebuggerUrl"]; break
            except Exception: time.sleep(0.3)
        if not endpoint: sys.exit("Chrome did not start")
        async with websockets.connect(endpoint, max_size=40*1024*1024) as ws:
            p = S(ws)
            t = await p.send("Target.createTarget", {"url": "about:blank"}, browser=True)
            a = await p.send("Target.attachToTarget", {"targetId": t["targetId"], "flatten": True}, browser=True)
            p.sid = a["sessionId"]
            await p.send("Page.enable"); await p.send("Runtime.enable")
            await p.send("Emulation.setDeviceMetricsOverride",
                         {"width": WIDTH, "height": HEIGHT, "deviceScaleFactor": 1, "mobile": False})
            if TOUCH:
                await p.send("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 5})
            await p.send("Page.navigate", {"url": f"{BASE}/lovelace"})
            await asyncio.sleep(2)
            await p.js("(() => { const t = " + json.dumps({
                "access_token": token, "token_type": "Bearer", "expires_in": 3600,
                "clientId": None, "refresh_token": ""}) +
                "; t.hassUrl = location.origin; t.expires = Date.now() + 3600000;"
                " localStorage.setItem('hassTokens', JSON.stringify(t)); })()")
            await p.send("Page.navigate", {"url": f"{BASE}/dashboard-history"})
            await asyncio.sleep(4)
            print(await p.js(REPORT))
    finally:
        chrome.terminate(); chrome.wait()

asyncio.run(main())
```

Ausführen:

```bash
docker compose -f docker/compose.yaml restart
python3 <scratchpad>/probe_layout.py 390 844
```

**Erwartet:** `hoverNone: false` (die Startoption wirkt), `menu.shown: true`, `panelWidth: 390`.
Danach zur Gegenprobe:

```bash
python3 <scratchpad>/probe_layout.py 1400 900
```

**Erwartet:** `menu` ist `null` — bei 1400 px ist `narrow` unwahr, und der Knopf darf gar nicht gezeichnet sein.

- [ ] **Schritt 9: Von Hand prüfen, dass das Menü wirklich aufgeht**

Die Sonde belegt, dass der Knopf da ist — nicht, dass er wirkt. Im Browser bei schmalem Fenster auf `<HA_TEST_URL>/dashboard-history`: Knopf drücken, Seitenleiste muss aufgehen und aus dem Panel herausführen. Danach dasselbe bei **breitem** Fenster, nachdem die Seitenleiste über ihr eigenes Menü auf »immer verbergen« gestellt wurde — das ist der Fall, den Schritt 1 als Test hat und den nur diese Handprüfung im echten Zusammenspiel zeigt.

- [ ] **Schritt 10: Committen**

```bash
git add custom_components/dashboard_history/panel.js custom_components/dashboard_history/panel/style.js tests/test_panel_behaviour.py
git commit -m "$(cat <<'MSG'
Give the panel Home Assistant's menu button

Below 870px Home Assistant hides its sidebar and expects the page to
offer the way back into it. This panel built a bar of its own and put
nothing there, so a phone had no way out but the browser's own back
gesture.

The button fires hass-toggle-menu rather than being ha-menu-button:
that element sits in a lazily loaded chunk no custom panel page is
promised, and this panel uses no Home Assistant components anywhere.

When it shows is Home Assistant's rule, copied rather than invented -
including the half that is easy to miss, where a wide window with the
sidebar pinned away needs the button just as much. That half arrives
through hass, which is assigned on every state change and never drew,
so the condition is compared there rather than rendered blindly.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
)"
```

---

## Aufgabe 2: Der Host wird ein Container, die Seitenspalte wandert mit

**Dateien:**
- Ändern: `custom_components/dashboard_history/panel/style.js` (`:host` ab Zeile 4, `.side` ab Zeile 85)

**Schnittstellen:**
- Verbraucht: nichts
- Liefert: den Containernamen `panel` und die Bandgrenzen, auf die Aufgabe 3, 4 und 5 sich beziehen

- [ ] **Schritt 1: Den Host zum Container machen**

In `style.js`, im `:host`-Block, direkt hinter `display: block;`:

```css
    /* Two different questions are easy to mistake for one. "Is Home
       Assistant's sidebar hidden?" decides the menu button, and
       narrow answers it. "How much room do I have?" decides how many
       columns there are - and narrow answers that one wrongly. At a
       900px window narrow is false, Home Assistant docks its 256px
       sidebar, and this panel really has about 640px. A media query
       inside the panel measures the window regardless and says "wide".
       Measured on 2026-09-17.

       Containment on the inline axis only: the height still follows the
       content, which the long note beside .main below relies on. */
    container-type: inline-size;
    container-name: panel;
```

- [ ] **Schritt 2: Die Seitenspalte mitwandern lassen**

`.side` (Zeile 85) bekommt zwei `@container`-Bänder. Der `.side`-Block selbst bleibt **unverändert** — er ist das Basis-CSS, das ein Browser ohne `@container` bekommt. Direkt dahinter, hinter der schließenden Klammer:

```css
  /* Below a wide window the fixed 280px stops being a width and starts
     being a claim on space there is not. It gives way before the main
     column does - a history nobody can read is worse than a list of
     names set a little tighter - but never below 200px, where the two
     lines of a row start wrapping.

     The band starts at 1000px of PANEL width, not window width. With
     the sidebar docked that is roughly a 1260px window.

     flex-shrink stays 0, and that is not the mistake it looks like
     next to the bug this replaces. There, flex: 0 0 280px pinned a
     constant and the container grew past the window. Here the basis
     itself follows the container, so it cannot. Written as 0 1 first
     and measured on 2026-09-17: shrink applies to the RESULT, not to
     the basis, so the clamp's 200px floor did nothing and the column
     came out at 160px - under a comment promising it never would. */
  @container panel (max-width: 1000px) {
    .side {
      flex: 0 0 clamp(200px, 30cqw, 280px);
      width: clamp(200px, 30cqw, 280px);
    }
  }
```

- [ ] **Schritt 3: Syntax und Tests**

```bash
node --input-type=module --check < custom_components/dashboard_history/panel/style.js
python3 -m pytest tests/ -q
```

- [ ] **Schritt 4: Die Bänder messen**

```bash
docker compose -f docker/compose.yaml restart
python3 <scratchpad>/probe_layout.py 1400 900
python3 <scratchpad>/probe_layout.py 950 900
python3 <scratchpad>/probe_layout.py 700 900
```

**Erwartet:**

Am 2026-09-17 an der Prüfanlage gemessen — das sind die Zahlen, die herauskommen müssen:

| Fensterbreite | Panel | `side.w` | `main.w` | `docScrolls` |
|---|---|---|---|---|
| 1400 | 1134 | 281 | 853 | `false` |
| 950 | 684 | 206 | 478 | `false` |
| 700 | 690 | 208 | 482 | `false` |

**Panel ≠ Fenster, und die 700er Zeile zeigt warum.** Bei 1400 px dockt Home Assistant seine Seitenleiste an und nimmt 266 px weg; bei 700 px ist `narrow` wahr, die Seitenleiste ist fort, und das Panel bekommt fast das ganze Fenster. Deshalb ist das Panel bei 700 px Fenster **breiter** als bei 950 px. Genau der Zusammenhang, den eine Media-Query nicht sehen kann.

Kommt bei 950 px etwas unter 200 heraus, schrumpft die Spalte unter die `clamp`-Untergrenze — dann steht `flex-shrink` nicht auf 0.

Zusätzlich zur Gegenprobe, dass Aufgabe 5 noch aussteht:

```bash
python3 <scratchpad>/probe_layout.py 390 844
```

**Erwartet:** `docScrolls: true`, `overflowBy` rund 42. Das ist **kein Fehler dieser Aufgabe** — bei 380 px Panel bleiben neben 201 px Liste nur 179 px, und die eine Spalte kommt erst in Aufgabe 5. Vor dieser Aufgabe waren es 117 px Überlauf; notiere den Wert, um ihn in Aufgabe 5 auf 0 zu sehen.

- [ ] **Schritt 5: Committen**

```bash
git add custom_components/dashboard_history/panel/style.js
git commit -m "$(cat <<'MSG'
Let the dashboard list give way before the history does

The list was pinned at flex 0 0 280px, which in a flex row does not
mean "280px" but "never shrink" - so the container grew past the
window instead of the column getting narrower.

Measured against the panel's own width rather than the window's,
because with Home Assistant's sidebar docked at a 900px window the
panel really has about 640px and a media query cannot see that.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
)"
```

---

## Aufgabe 3: Der Balken darf umbrechen

Muss **vor** Aufgabe 5 liegen: Solange der Balken auf 56 px festgenagelt ist, überlappt sein zweizeiliger Inhalt im schmalen Band den Bereich darunter, und die Master/Detail-Prüfung würde an einem Fehler scheitern, der gar nicht zu ihr gehört.

**Dateien:**
- Ändern: `custom_components/dashboard_history/panel/style.js` (`:host` ab Zeile 4, `.bar` ab Zeile 34, `.layout` Zeile 84)

- [ ] **Schritt 1: Den Host zur Flex-Spalte machen**

Im `:host`-Block `display: block;` ersetzen durch:

```css
    /* A column, so that .layout can take the rest of the height
       without anybody having to name the bar's height twice. The bar
       used to be exactly 56px and .layout was told calc(100% - 56px)
       - two places that had to agree, and they stop agreeing the moment
       the bar is allowed to wrap. */
    display: flex;
    flex-direction: column;
```

- [ ] **Schritt 2: `.layout` von der magischen 56 befreien**

Zeile 84 ersetzen:

```css
  .layout { display: flex; align-items: stretch; flex: 1 1 auto; min-height: 0; }
```

- [ ] **Schritt 3: Dem Balken das Umbrechen erlauben**

Im `.bar`-Block `height: 56px;` ersetzen durch:

```css
    /* A floor, not a height. Below the narrow band the bar carries a
       second row - the mode switch drops under the title rather than
       being taken away from a phone, which would cost it one of the two
       modes. align-items: center keeps a single row looking exactly
       as it did. */
    min-height: 56px;
    flex-wrap: wrap;
```

Und dahinter, hinter `.bar .menu:hover`:

```css
  /* Below the narrow band the title gets the first row to itself,
     between the two round buttons, and the mode switch takes the
     second. order rather than a different markup: the switch is one
     element drawn once, and moving it in JavaScript would mean either
     duplicate radio inputs sharing a name - which makes one group out of
     two controls - or measuring the width in JavaScript, which is what
     the _pane note argues against. */
  @container panel (max-width: 560px) {
    .bar { gap: 8px 12px; padding: 6px 12px; }
    .bar > .segmented-control { order: 10; flex-basis: 100%; }
    .bar .which { flex: 1 1 auto; }
  }
```

`_renderModeSwitch()` (Zeile 3190) liefert `<fieldset class="segmented-control" role="radiogroup">` — das ist das Element, das `order` und `flex-basis` bekommt. Es trägt `all: unset` (Zeile 810); die beiden Eigenschaften hier stehen danach und in einer spezifischeren Regel, wirken also. Kein Markup muss dafür geändert werden.

- [ ] **Schritt 4: Syntax und Tests**

```bash
node --input-type=module --check < custom_components/dashboard_history/panel/style.js
node --input-type=module --check < custom_components/dashboard_history/panel.js
python3 -m pytest tests/ -q
```

- [ ] **Schritt 5: Messen**

```bash
docker compose -f docker/compose.yaml restart
python3 <scratchpad>/probe_layout.py 1400 900
python3 <scratchpad>/probe_layout.py 390 844
```

**Erwartet:** bei 1400 px `bar.h` weiterhin 56 — der breite Schirm darf sich nicht verändert haben. Bei 390 px ist `bar.h` größer als 56 (zwei Zeilen) und `main.h` entsprechend kleiner; nichts überlappt.

- [ ] **Schritt 6: Committen**

```bash
git add custom_components/dashboard_history/panel/style.js custom_components/dashboard_history/panel.js
git commit -m "$(cat <<'MSG'
Let the bar wrap instead of losing what it carries

On a phone the bar has to hold a menu button, a back arrow, the
dashboard's name, the mode switch and reload. Dropping the mode switch
there would take one of the two modes away from the device the simple
mode was built for.

Wrapping means the bar is no longer exactly 56px tall, so .layout can
no longer be told calc(100% - 56px). That line was already inert - the
host sizes to its content, as the note beside it says - and a flex
column replaces it without anybody naming a height twice.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
)"
```

---

## Aufgabe 4: Die Suchzeile bricht um

Eigenständige Ursache des waagerechten Scrollens, unabhängig von der Seitenspalte — Spec, Befund 3 und Festlegung 6.

**Dateien:**
- Ändern: `custom_components/dashboard_history/panel/style.js` (`.search` Zeile 203, `.search .find` Zeile 210)

- [ ] **Schritt 1: Umbrechen erlauben**

Zeile 203 ersetzen:

```css
  .search { display:flex; flex-wrap: wrap; align-items:center; gap:12px; margin-bottom:12px; }
```

- [ ] **Schritt 2: Dem Feld im schmalen Band die Deckelung nehmen**

Hinter `.search .find` (Zeile 210):

```css
  /* The 420px cap exists so that simple and advanced mode have the same
     row shape whether or not the compare toggle sits beside the field -
     the note above says so. That reason stops applying once every
     element has a row of its own anyway, and the cap then only makes
     the field narrower than the space it has. */
  @container panel (max-width: 560px) {
    .search { gap: 8px; }
    .search .find { flex: 1 1 100%; max-width: none; }
  }
```

- [ ] **Schritt 3: Syntax und Tests**

```bash
node --input-type=module --check < custom_components/dashboard_history/panel/style.js
python3 -m pytest tests/ -q
```

- [ ] **Schritt 4: Das Abnahmekriterium der Spec messen**

Die Spec verlangt: bei 360 px sind **alle vier** Bedienelemente erreichbar. Alle vier treten nur im erweiterten Modus und nur bei getipptem Suchwort auf — die Sonde muss also erst in diesen Zustand schalten, sonst misst sie den einfachen Modus und findet nichts.

```bash
docker compose -f docker/compose.yaml restart
python3 <scratchpad>/probe_layout.py 360 800
```

Die Sonde öffnet den einfachen Modus. Für den Prüffall vorher im Browser oder per CDP `_setMode("advanced")` setzen und ein Suchwort von zwei Zeichen eintippen.

⚠️ **Dieses Kriterium ist vor Aufgabe 5 nicht erfüllbar, und das ist keine Ausrede.** Solange zwei Spalten stehen, bleibt der Inhaltsspalte bei 360 px Fenster nur rund 149 px — da passt keine Suchzeile hinein, gleich wie sie umbricht. Am 2026-09-17 gemessen: mit zwei Spalten `cutOff: true` (149 gegen 201), mit einer Spalte `cutOff: false` (350 gegen 350) und das Feld über die volle Zeile. **Prüfe diese Aufgabe deshalb unter einer Spalte**, indem Du der Sonde vorher

```js
const st = document.createElement("style");
st.textContent = ".side { display: none !important; }";
host.shadowRoot.appendChild(st);
```

unterschiebst — oder hebe die Prüfung auf und führe sie in Aufgabe 5, Schritt 10 mit. Was nicht geht: sie für bestanden erklären, weil »das kommt noch«.

**Erwartet: `mainCutOff.cutOff` ist `false`.** Nicht `docScrolls` — am 2026-09-17 vor dieser Aufgabe gemessen war `docScrolls` bereits `false`, während `.main` 179 px breit um 440 px Inhalt stand und fünf Elemente über die rechte Kante ragten: `text find`, `act ghost`, `why`, `act ghost wider`, `when`. Das ist der Zustand, den diese Aufgabe abräumt, und `docScrolls` sieht ihn nicht.

- [ ] **Schritt 5: Committen**

```bash
git add custom_components/dashboard_history/panel/style.js
git commit -m "$(cat <<'MSG'
Let the search row wrap on a narrow screen

In advanced mode the row carries up to four things side by side - the
field, the compare toggle, the result note and "search the whole
history" - and had no flex-wrap, so it demanded more width than it had
and pushed the page sideways. A second cause of the same symptom as
the pinned sidebar, and unaffected by fixing that one.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
)"
```

---

## Aufgabe 5: Master/Detail

Die größte Aufgabe, und die einzige mit neuem Zustand. Die Übergänge sind in der Spec, Festlegung 4, abschließend festgelegt — **eine** Regel und drei Folgerungen daraus. Drei Fallen darin sind beim Review dieses Plans gefunden worden und stehen hier ausdrücklich, weil jede von ihnen einen der vorgeschriebenen Übergangstests scheitern ließe.

**Dateien:**
- Ändern: `custom_components/dashboard_history/panel.js` (`_render` Zeilen 3228–3243 und 3255, `_loadDashboards` Zeile 904, `_forget` Zeile 2407, Verdrahtung Zeile 3320, Konstruktor)
- Ändern: `custom_components/dashboard_history/panel/style.js`
- Test: `tests/test_panel_behaviour.py`

**Schnittstellen:**
- Verbraucht: Container und Bänder aus Aufgabe 2, umbrechender Balken aus Aufgabe 3
- Liefert: `this._pane` (`"list" | "detail"`), `_pick(key)`, das Host-Attribut `data-pane` und `this._diffScroll`

- [ ] **Schritt 1: Die fehlschlagenden Tests schreiben**

Ans Ende von `tests/test_panel_behaviour.py`:

```python
# -- one column: which one, and what a tap means ---------------------------
#
# `_pane` is read by CSS alone, so none of this is visible in a
# screenshot - and the one failure that matters is a race: the panel
# picks a dashboard for you at load time, and while that request is in
# flight the list is already on screen and clickable.

_HARNESS_PANE = """
// 1. A tap during the automatic first selection must not be undone by it.
const p = new Panel();
p._render = () => {};
p._loadSidebar = async () => {};
const calls = [];
p._call = (type, extra) =>
  new Promise((resolve, reject) => calls.push({ type, extra, resolve, reject }));
const find = (type, dashboard) =>
  calls.find((c) => c.type === type && (!dashboard || c.extra?.dashboard === dashboard));

const loading = p._loadDashboards();
await settle();
find("dashboards").resolve({
  dashboards: [{ key: "a", exists: true }, { key: "b", exists: true }],
});
await settle();
// `_select("a")` is in flight. The list is drawn and can be tapped.
const paneWhileLoading = p._pane;
p._pick("b");
const paneRightAfterTap = p._pane;
for (const type of ["history", "versions"]) {
  find(type, "a")?.resolve({ changes: [], versions: [] });
  find(type, "b")?.resolve({ changes: [], versions: [] });
}
await settle();
await loading;
const paneAfterItAllSettled = p._pane;

// 2. Tapping the row that is already selected only switches columns.
const q = new Panel();
q._render = () => {};
const qCalls = [];
q._call = (type, extra) => new Promise((resolve) => qCalls.push({ type, extra, resolve }));
q._selected = "a";
q._query = "kept";
q._pane = "list";
q._pick("a");
const sameRow = { pane: q._pane, calls: qCalls.length, query: q._query };
q._pick("b");
const otherRow = { pane: q._pane, calls: qCalls.length, query: q._query };

console.log(JSON.stringify({
  paneWhileLoading, paneRightAfterTap, paneAfterItAllSettled, sameRow, otherRow,
}));
"""


@pytest.fixture(scope="module")
def pane(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "pane", _HARNESS_PANE)


def test_the_automatic_first_pick_stays_on_the_list(pane):
    # Wide, the preselection keeps the second column from being empty.
    # Narrow, it would drop somebody into a dashboard they never chose.
    assert pane["paneWhileLoading"] == "list"


def test_a_tap_during_the_first_pick_wins(pane):
    # The race this test exists for: `_loadDashboards` awaits `_select`,
    # and the list is clickable throughout that await. Setting the pane
    # after the await put the panel back on the list under the finger
    # of somebody who had already chosen.
    assert pane["paneRightAfterTap"] == "detail"
    assert pane["paneAfterItAllSettled"] == "detail"


def test_tapping_the_selected_row_asks_the_server_for_nothing(pane):
    # `_select` clears the search word and refetches. Running it for the
    # row that is already selected turns "back, then in again" into a
    # reload with a second of grey in the middle - which is the opposite
    # of what the back arrow promises.
    assert pane["sameRow"] == {"pane": "detail", "calls": 0, "query": "kept"}


def test_tapping_another_row_is_still_a_full_switch(pane):
    # Two calls: history and versions, as `_select` has asked since
    # initiative G.
    assert pane["otherRow"] == {"pane": "detail", "calls": 2, "query": ""}
```

- [ ] **Schritt 2: Laufen lassen und scheitern sehen**

```bash
python3 -m pytest tests/test_panel_behaviour.py -k "first_pick or tapping_the_selected_row or tapping_another_row" -v
```

Erwartet: **4 selected**, alle **FAIL** — `p._pick is not a function`.

**Nicht `-k pane`:** Keiner der vier Testnamen enthält »pane«, und `-k` sieht den Fixture-Namen nicht. `-k pane` wählt null Tests aus, pytest endet mit »no tests ran« — und das liest sich in einem Protokoll wie ein bestandener Lauf.

- [ ] **Schritt 3: Den Zustand anlegen**

In den Konstruktor, hinter `this._inBox = false;`:

```js
    // Which of the two columns is on screen while there is room for one.
    // Read by CSS alone - see the `@container` band in the stylesheet -
    // so JavaScript never learns how wide it is. A ResizeObserver
    // setting a `_wide` flag was the obvious alternative and the wrong
    // one: `_render` replaces the whole shadow root and has to put the
    // diff's scroll offset and the search box's caret back by hand, so
    // turning a phone would fire the most expensive path in this class
    // over and over.
    //
    // It becomes "detail" only through a deliberate tap on a dashboard
    // row. Every other way `_selected` gets a value leaves it on the
    // list: the automatic first pick at load time, and whatever
    // `_loadDashboards` picks after a dashboard was forgotten.
    this._pane = "list";
    // The diff's scroll offset, kept out here rather than read off the
    // page at render time. See `_render`, where the reason is written
    // out: with one column the detail is still drawn while the list is
    // showing, and a hidden element answers 0.
    this._diffScroll = 0;
```

- [ ] **Schritt 4: Die Weiche vor `_select` setzen**

`_select` selbst bleibt unverändert. Neben ihm:

```js
  /**
   * A tap on a row in the dashboard list.
   *
   * Two things that used to be one. `_select` clears everything that
   * belonged to the old dashboard - the search word, compare mode and
   * its selection, the open row, the detail cache, the loaded versions -
   * and asks the server for history and versions again. That is right
   * for a switch and wrong for the row that is already selected: with
   * one column, "back to the list, then in again" would run it, and the
   * immediate return this panel promises would be a reload with a
   * second of grey in the middle.
   *
   * Tapping the row that is already selected therefore only decides
   * which column is on screen. On a wide screen that makes such a click
   * do nothing at all, where it used to reload and throw away a typed
   * search word on the way. Deliberate: reloading is the button that
   * says so.
   */
  _pick(key) {
    this._pane = "detail";
    if (key === this._selected) {
      this._render();
      return;
    }
    return this._select(key);
  }
```

Und die Verdrahtung bei Zeile 3320:

```js
    onClick(".dash", (element) => this._pick(element.dataset.key));
```

- [ ] **Schritt 5: Die beiden Stellen, die von selbst wählen**

In `_loadDashboards` (Zeile 904). **Die Reihenfolge trägt den ganzen Punkt:** Der Anfangszustand wird *vor* dem Abruf gesetzt, nicht danach — während des `await` ist die Liste längst gezeichnet und bedienbar, und ein `_pane = "list"` dahinter überholt die Entscheidung dessen, der inzwischen getippt hat.

```js
    if (first) {
      // Before the await, not after it. This selection is the panel's
      // own, not anybody's finger, so with one column it starts on the
      // list - but `_select` below takes as long as the server does,
      // and the list can be tapped throughout. Setting it afterwards
      // would put somebody who had already chosen back on the list.
      // Wide, the preselection is what keeps the second column from
      // being empty; and it is no wasted request either way, because it
      // is what makes the first tap on that very row open without
      // waiting.
      this._pane = "list";
      await this._select(first.key);
    }
```

In `_forget` (Zeile 2407) hinter `this._selected = null;`:

```js
    // You just removed what you were looking at. `_loadDashboards`
    // below picks the first live dashboard again, and with one column
    // that would put you in some other dashboard's history without
    // having asked - a screen that looks right and is not. Covered by
    // `_loadDashboards` already; said here as well so it survives
    // somebody editing that.
    this._pane = "list";
```

- [ ] **Schritt 6: Laufen lassen und bestehen sehen**

```bash
python3 -m pytest tests/test_panel_behaviour.py -k "first_pick or tapping_the_selected_row or tapping_another_row" -v
python3 -m pytest tests/ -q
```

Erwartet: **4 passed** dort, `0 failed` insgesamt. Kommt »no tests ran«, war der Filter falsch und nicht der Code.

- [ ] **Schritt 7: Das Attribut, den Zurück-Knopf und die Scroll-Erhaltung zeichnen**

Das Attribut gehört an den **Host**, nicht an das Layout: `.bar` und `.layout` sind Geschwister unter dem Shadow-Root, und eine Regel an `.layout` erreicht den Knopf im Balken nicht. Am 2026-09-17 gemessen, dass `:host([data-pane="detail"]) .bar .back` innerhalb einer `@container`-Regel greift — der Container darf sich nicht selbst gestalten, das Ziel der Regel ist hier aber ein Nachfahre.

In `_render()`, unmittelbar vor `this.shadowRoot.innerHTML = ...`:

```js
    // On the host, because the bar and the layout are siblings and a
    // rule on one cannot reach the other. "list" whenever nothing is
    // selected, so the back arrow cannot appear over an empty choice.
    this.setAttribute("data-pane", this._selected ? this._pane : "list");
```

Im Balken, direkt hinter dem Menüknopf aus Aufgabe 1:

```js
        ${this._selected
        ? `<button class="back" data-back="1" title="Back to the dashboard list"
                   aria-label="Back to the dashboard list">
             <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
               <path d="M15.4 7.4 14 6l-6 6 6 6 1.4-1.4-4.6-4.6z"/>
             </svg>
           </button>`
        : ""}
```

Er wird immer gezeichnet, wenn etwas gewählt ist, und ist außerhalb des schmalen Bandes **und** auf der Liste per CSS unsichtbar — dasselbe Prinzip wie bei den Spalten.

Die Verdrahtung neben `onClick(".menu", ...)`:

```js
    onClick(".back", () => {
      this._pane = "list";
      this._render();
    });
```

**Und die Scroll-Erhaltung des Diffs.** Zeile 3228–3232 lesen den Wert heute direkt aus dem DOM. Mit einer Spalte ist der Detailbereich beim Wechsel auf die Liste noch gezeichnet, aber `display: none` — und ein verborgenes Element antwortet `0`. Gemessen: `180 → Liste: 0 → Rückkehr: 0`, also genau der Übergang, den Schritt 9 Nummer 3 prüft. Ersetze die Zeile

```js
    const diffScroll =
      this.shadowRoot.querySelector(".detail details.raw[open] pre")?.scrollTop ?? 0;
```

durch:

```js
    // Only while the column it sits in is on screen. With one column
    // the detail is still drawn when the list is showing - `display:
    // none`, and a hidden element answers 0 for `scrollTop`. Reading
    // that would overwrite the offset with a zero nobody scrolled to,
    // and the way back into the row would land at line one. `offsetHeight`
    // rather than `checkVisibility()`, which Safari only learned late
    // and this panel has to run in.
    const openDiff = this.shadowRoot.querySelector(".detail details.raw[open] pre");
    if (openDiff && openDiff.offsetHeight > 0) this._diffScroll = openDiff.scrollTop;
```

und den Wiederherstellungs-Block am Ende von `_render` (Zeile 3238–3243) durch:

```js
    if (this._diffScroll) {
      const pre = root.querySelector(".detail details.raw[open] pre");
      // Setting `scrollTop` on a hidden element does nothing, so this
      // puts the offset back at the first render where the column is on
      // screen again - which is the very render `_pick` triggers.
      // Only where the new diff is long enough to hold it; a shorter
      // one clamps to its own end by itself, which is the right answer
      // and not worth a branch.
      if (pre && pre.offsetHeight > 0) pre.scrollTop = this._diffScroll;
    }
```

- [ ] **Schritt 8: Das dritte Band in CSS**

In `style.js`, hinter das Band aus Aufgabe 2:

```css
  /* Below this the two columns stop fitting: a 200px list next to a
     main column of less than about 360px is two things neither of which
     can be read. One column then, and which one is the only thing
     _pane decides. Everything is drawn on every render; this band is
     the only thing that knows there is a narrow case at all. */
  .bar .back { display: none; }
  @container panel (max-width: 560px) {
    .side {
      flex: 1 1 auto;
      width: auto;
      border-right: 0;
    }
    :host([data-pane="list"]) .mainwrap { display: none; }
    :host([data-pane="detail"]) .side { display: none; }
    /* Bound to the pane as well, not only to the band: with the
       automatic first pick something is selected the moment the panel
       opens, so a back arrow that asked only about the width would sit
       on the list doing nothing. */
    :host([data-pane="detail"]) .bar .back {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      flex: 0 0 auto;
      width: 40px;
      height: 40px;
      padding: 0;
      border: 0;
      border-radius: 50%;
      background: transparent;
      color: inherit;
      cursor: pointer;
    }
    .bar .back svg { width: 24px; height: 24px; fill: currentColor; }
  }
```

- [ ] **Schritt 9: Syntax, Tests, Integration**

```bash
node --input-type=module --check < custom_components/dashboard_history/panel.js
node --input-type=module --check < custom_components/dashboard_history/panel/style.js
python3 -m pytest tests/ -q
docker compose -f docker/compose.yaml restart
python3 tests/integration/run_checks.py
```

`run_checks.py` läuft hier zum ersten Mal vollständig: Das Panel wurde inzwischen an vielen Stellen geändert, und diese Aufgabe ist die, nach der Fingerabdruck und Auslieferung aller Teile belegt sein müssen. **Container vorher neu starten** — ein roter Fingerabdruck ohne Neustart ist ein alter Container, kein Codefehler.

- [ ] **Schritt 10: Die Bänder messen**

```bash
python3 <scratchpad>/probe_layout.py 390 844
python3 <scratchpad>/probe_layout.py 1400 900
```

**Erwartet bei 390 px, Liste:** `pane: "list"`, `side.shown: true`, `main.shown: false`, `back.shown: false`. Der Zurück-Pfeil ist gezeichnet — es *ist* etwas vorausgewählt —, aber unsichtbar; daran hängt Befund 3.
**Erwartet bei 1400 px:** `side.w: 281`, `main.shown: true`, `back` gezeichnet, `shown: false`.

**Und dann der Teil, den `docScrolls` nicht beantwortet.** Bei `pane: "list"` ist `.main` auf `display: none`, `mainCutOff` also nichtssagend — die Spalte, die abschneiden könnte, ist gar nicht da. Der Beleg muss im **Detail** geführt werden, und dort trägt er zugleich das Kriterium aus Aufgabe 4, das dort mangels Platz nicht zu messen war:

```bash
python3 <scratchpad>/probe_layout.py 360 800   # danach im Detail, erweitert, mit Suchwort
```

Schalte dafür per CDP in den Zustand, der die Suchzeile voll belädt, und miss dann:

```js
host._setMode("advanced"); host._query = "st"; host._pane = "detail"; host._render();
```

**Erwartet: `mainCutOff.cutOff` ist `false`.** Am 2026-09-17 unter einer Spalte vorab gemessen: `.main` 350 gegen 350, `.search` 318 gegen 318, das Feld über die volle Zeile. Kommt hier `true` heraus, ist entweder das Band nicht gegriffen oder die Suchzeile aus Aufgabe 4 doch nicht in Ordnung — beides ein Befund dieser Aufgabe, weil erst sie den Platz schafft, an dem es sich zeigen kann.

Dasselbe für die Liste, die im schmalen Band die ganze Breite trägt und es vorher nie musste:

```js
host._pane = "list"; host._render();
```

**Erwartet:** `side` hat `scrollWidth == clientWidth`. Die Dashboard-Namen dürfen umbrechen, nicht abgeschnitten werden.

- [ ] **Schritt 11: Die fünf Übergänge von Hand prüfen**

Wörtlich die Liste aus der Spec. Jeder einzeln, bei 390 px Fensterbreite:

1. Liste → ein Dashboard antippen → Verlauf → »‹« → **dasselbe** Dashboard erneut antippen. Der Verlauf muss **sofort** stehen: kein Ladekringel, kein Sprung an den Anfang.
2. Ein Suchwort eintippen und eine Vergleichsauswahl halb setzen (eine Checkbox), dann das Fenster breit ziehen und wieder schmal. Beides muss beide Richtungen überleben.
3. Eine Zeile aufklappen, in den technischen Diff scrollen, »‹«, zurück in dasselbe Dashboard: Zeile noch offen, **Scrollposition noch da**. Das ist der Übergang, an dem die erste Fassung dieses Plans gescheitert wäre.
4. Menüknopf: Home Assistants Seitenleiste geht auf und führt aus dem Panel heraus.
5. Das gerade angesehene Dashboard vergessen: Danach steht die **Liste** auf dem Schirm, nicht der Verlauf eines anderen Dashboards. Von Hand und nicht als Node-Test, weil `_forget` durch einen Bestätigungsdialog läuft — der DOM-Ersatz kann ihn, aber der Aufwand stünde in keinem Verhältnis zu dem einen Feld, das hier zu prüfen ist.

Geht einer davon schief, ist das ein Befund dieser Aufgabe und kein Thema für später.

- [ ] **Schritt 12: Committen**

```bash
git add custom_components/dashboard_history/panel.js custom_components/dashboard_history/panel/style.js tests/test_panel_behaviour.py
git commit -m "$(cat <<'MSG'
Show one column at a time when there is room for one

Either the dashboard list or the history, with a back arrow between
them - what Home Assistant itself does under /config. The list needs a
whole screen here: it is three lists, not one, and on the rig this was
found on that is 74 entries behind two folds.

Which column shows is decided by CSS from the panel's own width. A
ResizeObserver would have fired _render on every drag of a window
edge, and _render replaces the entire shadow root.

Three things that only look like details. The automatic first pick is
set before its request, not after, or a tap made while it is in flight
gets undone by it. The back arrow asks about the pane and not only the
width, or it sits on the list doing nothing. And the diff's scroll
offset is kept in a field: the detail stays drawn but hidden while the
list shows, and a hidden element answers 0.

Tapping the already selected row no longer runs _select, which used to
clear the search word and refetch. On a wide screen that makes such a
click do nothing, which is what the reload button is for.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
)"
```

---

## Aufgabe 6: Tippziele

**Dateien:**
- Ändern: `custom_components/dashboard_history/panel/style.js` (`@media (hover: none)` Zeile 379, `.bar .reload` Zeile 71, `details.fold > summary` Zeile 241)

- [ ] **Schritt 1: Den vorhandenen Block erweitern**

Der Block bei Zeile 379 enthält heute nur `.pen`. Er bekommt zwei Regeln dazu:

```css
  @media (hover: none) {
    .pen { opacity: 1; pointer-events: auto; }
    /* Touch, not width, is the criterion: a phone in landscape is wide
       and still a finger, a narrow browser window on a desktop is
       narrow and still a mouse. The reload button works out to just
       under 30px tall from its line-height and padding - about two
       thirds of a usable target. */
    .bar .reload { min-height: 44px; padding: 8px 14px; }
    details.fold > summary { padding: 16px; }
  }
```

- [ ] **Schritt 2: Syntax und Tests**

```bash
node --input-type=module --check < custom_components/dashboard_history/panel/style.js
python3 -m pytest tests/ -q
```

- [ ] **Schritt 3: Beide Zweige messen**

Der Nachweis wird in **beide** Richtungen geführt — die Spec verlangt genau das, nachdem sich beim Messen herausgestellt hat, dass headless Chrome ohne Zutun im Berührungszweig steht.

```bash
docker compose -f docker/compose.yaml restart
python3 <scratchpad>/probe_layout.py 1400 900
python3 <scratchpad>/probe_layout.py 390 844 --touch
```

**Erwartet bei 1400 px:** `hoverNone: false`, `reload.h` unter 32 — der Desktop-Zweig, den die Startoption der Sonde herstellt.
**Erwartet bei 390 px mit `--touch`:** `hoverNone: true`, `pointerCoarse: true`, `reload.h` mindestens 44.

Kommt bei 1400 px `hoverNone: true` heraus, wirkt die Startoption nicht — dann ist die Messung ungültig, nicht der Code.

- [ ] **Schritt 4: Committen**

```bash
git add custom_components/dashboard_history/panel/style.js
git commit -m "$(cat <<'MSG'
Grow the touch targets a finger cannot hit

The reload button comes to just under 30px from its line-height and
padding, and the fold summaries in the dashboard list are no better.

Under @media (hover: none) rather than in a width band: a phone in
landscape is wide and still a finger, and a narrow browser window on a
desktop is narrow and still a mouse. Width is the wrong question here.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
)"
```

---

## Aufgabe 7: Die Aufnahmen

**Dateien:**
- Ändern: `tools/capture_demo_screenshots.py` (Chrome-Start Zeile 173–188, `CDPSession` ab Zeile 111, Geräte-Metriken Zeile 214–223, Ende des hellen und des dunklen Blocks)

**Vorbedingung:** Dieses Werkzeug braucht die **Demo**-Instanz, nicht den Wegwerf-Container — siehe seinen eigenen Docstring. Ist sie nicht da, sagt es das und bricht ab; dann ist diese Aufgabe blockiert und nicht gescheitert.

- [ ] **Schritt 1: Chrome mit dem Desktop-Zweig starten**

In der Argumentliste bei Zeile 175, hinter `"--disable-extensions",`:

```python
            # Headless Chrome has no hover-capable pointing device, so
            # `(hover: none)` matches by default - every screenshot taken
            # so far has been rendering the touch branch, desktop ones
            # included. Measured on 2026-09-17; unnoticed until now
            # because only `.pen` lived in that block.
            #
            # There is no CDP call for this: `Emulation.setEmulatedMedia`
            # accepts `hover` and `pointer` and does nothing with them,
            # measured the same day. Only this launch option moves it.
            "--blink-settings=availableHoverTypes=2,primaryHoverType=2,"
            "availablePointerTypes=4,primaryPointerType=4",
```

- [ ] **Schritt 2: Einen Nachweis je Aufnahme einbauen**

In `CDPSession`, hinter `shot` (Zeile 160):

```python
    async def expect_media(self, *, hover_none, scheme=None):
        """Refuse to let a screenshot stand for something it does not show.

        Which branch Chrome is in is not visible in the image, and the
        answer surprised us once already: headless Chrome sits in the
        touch branch unless it is launched out of it.

        The colour scheme is asked here too, for a duller reason: these
        passes are appended to one another, and a block that forgets to
        set its own would quietly save a dark picture under a light name.
        """
        got = await self.js('matchMedia("(hover: none)").matches')
        if got is not hover_none:
            sys.exit(
                f"expected (hover: none) to be {hover_none}, got {got} - "
                "the screenshots would be of the wrong branch"
            )
        if scheme is not None:
            dark = await self.js('matchMedia("(prefers-color-scheme: dark)").matches')
            if dark is not (scheme == "dark"):
                sys.exit(f"expected the {scheme} scheme, got dark={dark}")
```

Und direkt hinter `Emulation.setDeviceMetricsOverride` (Zeile 223), vor der ersten Aufnahme:

```python
            await page.expect_media(hover_none=False)
```

- [ ] **Schritt 3: Die 900-px-Aufnahme, ans Ende des hellen Blocks**

Der Fall, an dem Festlegung 2 steht oder fällt. Er gehört hierhin, solange der Desktop-Zweig und das helle Schema noch gelten.

```python
            print("Capturing 11-docked-sidebar-900.png...")
            await page.send(
                "Emulation.setDeviceMetricsOverride",
                {"width": 900, "height": 900, "deviceScaleFactor": 2, "mobile": False},
            )
            await asyncio.sleep(0.5)
            await page.expect_media(hover_none=False, scheme="light")
            # The whole point of this picture is that the panel is
            # narrower than the window - a media query inside it would
            # see 900 and be wrong. Measured rather than trusted: with a
            # collapsed sidebar this would be an ordinary 900px shot and
            # would prove nothing, while looking exactly the same.
            room = await page.js(
                f"(() => {{ const el = {ELEMENT};"
                " return el ? Math.round(el.getBoundingClientRect().width) : null; })()"
            )
            print(f"    the panel has {room}px inside a 900px window")
            if room is None or room >= 880:
                sys.exit(
                    f"the sidebar is not docked (panel {room}px of 900) - this shot is "
                    "meant to show the case a media query gets wrong"
                )
            await page.shot("11-docked-sidebar-900.png")
            # Back to the width the rest of the light pass was taken at,
            # in case anything is appended after this.
            await page.send(
                "Emulation.setDeviceMetricsOverride",
                {"width": 1400, "height": 900, "deviceScaleFactor": 2, "mobile": False},
            )
```

- [ ] **Schritt 4: Der schmale Durchgang, ganz ans Ende**

Die Reihenfolge ist zwingend und nicht Geschmackssache: `setTouchEmulationEnabled: False` stellt den Desktop-Zweig in der **laufenden Seite nicht wieder her**, erst ein Seitenwechsel tut das (am 2026-09-17 gemessen). Alles hinter diesem Punkt ist ein Berührungs-Bild.

Die Spec verlangt Liste **und** Verlauf, jeweils **hell und dunkel** — also vier Aufnahmen, nicht zwei. Die erste Fassung dieses Plans hängte zwei `*-light.png` hinter den dunklen Block, ohne das Schema zurückzusetzen; sie wären dunkel gewesen und hätten hell geheißen.

```python
            # The narrow pass. Last, and not by preference: turning touch
            # emulation off does not bring the hover branch back in the
            # page already open - only a navigation does.
            print("\n=== NARROW PASS (390x844) ===")
            await page.send(
                "Emulation.setDeviceMetricsOverride",
                {"width": 390, "height": 844, "deviceScaleFactor": 2, "mobile": True},
            )
            await page.send(
                "Emulation.setTouchEmulationEnabled",
                {"enabled": True, "maxTouchPoints": 5},
            )
            await page.send("Page.navigate", {"url": f"{BASE}/dashboard-history"})
            await page.settle('document.readyState === "complete"')
            # readyState says the document arrived, not that the panel's
            # modules did - they are fetched separately and drawn from a
            # promise. The bar is the first thing `_render` puts down.
            await page.settle(f'!!{PANEL}?.querySelector(".bar")')
            await page.settle(f'{PANEL}?.querySelectorAll(".dash").length >= 2')

            for scheme in ("light", "dark"):
                await page.send(
                    "Emulation.setEmulatedMedia",
                    {"features": [{"name": "prefers-color-scheme", "value": scheme}]},
                )
                await asyncio.sleep(0.8)
                await page.expect_media(hover_none=True, scheme=scheme)

                # Driven through the panel rather than by clicking, the
                # same way the two passes above do it: a click would
                # leave which dashboard is showing up to whichever row
                # happened to come first.
                print(f"Capturing 09-narrow-list-{scheme}.png...")
                await page.js(
                    f"(() => {{ const p = {ELEMENT}; p._pane = 'list'; p._render(); }})()"
                )
                await page.settle(f'!!{PANEL}?.querySelector(".side .dash")')
                await page.settle(f'!{PANEL}?.querySelector(".spin")')
                await page.shot(f"09-narrow-list-{scheme}.png")

                print(f"Capturing 10-narrow-detail-{scheme}.png...")
                await page.js(f"""(async () => {{
                    const p = {ELEMENT};
                    await p._select("living-room");
                    p._setMode("advanced");
                    p._pane = "detail";
                    p._render();
                }})()""")
                # All three, and each one answers a different doubt: that
                # the history arrived, that nothing is still in flight,
                # and that the column on screen is the one being named.
                await page.settle(f'{PANEL}?.querySelectorAll(".change").length >= 3')
                await page.settle(f'!{PANEL}?.querySelector(".spin")')
                await page.settle(
                    f"{ELEMENT}?.getAttribute('data-pane') === 'detail'"
                )
                await page.shot(f"10-narrow-detail-{scheme}.png")
```

- [ ] **Schritt 5: Laufen lassen**

```bash
python3 tools/capture_demo_screenshots.py
```

**Erwartet:** kein Abbruch aus `expect_media` oder aus der 900-px-Prüfung, und fünf neue Dateien in `docs/images`: `09-narrow-list-light`, `09-narrow-list-dark`, `10-narrow-detail-light`, `10-narrow-detail-dark`, `11-docked-sidebar-900`.

Dann **ansehen**, nicht nur zählen — das Werkzeug kann belegen, in welchem Zweig und welchem Schema es war, nicht, ob das Bild etwas taugt:

- die beiden `09-`: die Dashboard-Liste über die ganze Breite, **kein** Zurück-Pfeil im Balken
- die beiden `10-`: der Verlauf über die ganze Breite, Zurück-Pfeil da, kein waagerechter Scrollbalken
- `11-`: zwei Spalten mit schmaler Liste, oder eine — beides ist richtig, je nachdem, wo 640 px im Band liegen. Falsch wäre ein waagerechter Scrollbalken.
- hell und dunkel müssen sich tatsächlich unterscheiden

- [ ] **Schritt 6: Committen**

```bash
git add tools/capture_demo_screenshots.py docs/images
git commit -m "$(cat <<'MSG'
Photograph both the hover and the touch branch

Headless Chrome has no hover-capable pointing device, so every
screenshot this tool has ever taken was rendering the touch branch,
desktop ones included. Nobody noticed because only .pen lived in that
block; with the touch targets grown, a desktop picture would have
shown finger-sized controls.

Only a launch option moves it. Emulation.setEmulatedMedia accepts
hover and pointer and does nothing with them, and turning touch
emulation back off does not restore the hover branch in the page
already open - hence the narrow pass runs last, in both schemes.

Each shot now says which branch and which scheme it expects, and the
900px one measures that the sidebar really is docked. A picture that
proves nothing looks exactly like one that proves something.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
)"
```

---

## Aufgabe 8: Die Unterlagen nachziehen

- [ ] **Schritt 1: `status.md`**

Die K-Zeile von »**Nicht begonnen**« auf »Erledigt« setzen, mit diesem Plan als Beleg.

- [ ] **Schritt 2: Die Schwellenwerte in der Spec nachtragen**

Entscheidung 20, Festlegung 2 sagt ausdrücklich, die Zahlen stünden im Plan und würden gemessen. Sind sie es, gehört das gemessene Ergebnis als Satz dorthin — 1000 und 560, oder was daraus geworden ist, mit einem Wort dazu, woran es festgemacht wurde.

- [ ] **Schritt 3: README**

Prüfen, ob die README ein Bild oder einen Satz trägt, der jetzt falsch ist, und ob die neuen Handy-Aufnahmen dort hingehören. Die README ist zweigeteilt — Teil 1 ohne Interna, Teil 2 mit Messwerten; diese Teilung beim Fortschreiben halten.

- [ ] **Schritt 4: Committen**

```bash
git add docs/
git commit -m "$(cat <<'MSG'
Write down what initiative K turned out to be

The thresholds were deliberately left out of the decision and settled
against screenshots instead, which is where they now live.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
MSG
)"
```

---

## Was dieser Plan bewusst nicht enthält

- **Eine Aufteilung von `style.js`.** 1188 Zeilen sind viel, aber die Datei ist nach Bildschirmbereichen sortiert und dieses Vorhaben fügt an vorhandenen Stellen ein. Aufteilen wäre eine eigene Entscheidung.
- **Eine Test-Infrastruktur für CSS.** Für die *Logik* gibt es eine — `tests/test_panel_behaviour.py`, in Node —, und die Aufgaben 1 und 5 benutzen sie. Für jede Zeile CSS gibt es keine, und dieses Vorhaben ist der falsche Anlass, eine zu bauen. Die Sonde ist Wegwerf-Werkzeug und wird nicht eingecheckt.
- **Irgendetwas an `operations.py`.** Der beim Review gefundene Umkehrbarkeits-Punkt ist GitHub-Issue #18 und ausdrücklich vertagt.
