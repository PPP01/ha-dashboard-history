/*
 * The Dashboard History panel.
 *
 * Plain custom element, no build step: this ships inside a Python
 * integration, and a bundler in that repository would be a toolchain
 * nobody asked for.
 *
 * One rule shapes the whole interaction. People think in *changes*, not in
 * states. Asked to undo a deletion they reach for the line that says the
 * card was deleted - which is one line too late, because what they want is
 * the state before it. So this panel never asks for a revision. You click
 * the change; the panel works out which state that means.
 *
 * And nothing is written without showing the diff first.
 */

const DOMAIN = "dashboard_history";

// Must match EVENT_HISTORY_UPDATED in const.py; a test compares the two.
// Deliberately not `lovelace_updated`: that one fires *before* the
// recorder has written anything, and refreshing on it reads a history
// whose newest entry is the state that was just replaced.
const EVENT_RECORDED = "dashboard_history_updated";
// Must match EVENT_FORGET_PROGRESS in const.py.
const EVENT_FORGETTING = "dashboard_history_forget_progress";
// After this long without a word from a running forget, the lock screen
// stops claiming to know and offers a reload. Not a timeout on the
// operation - it keeps running - but an admission that this page can no
// longer tell "slow" from "stuck". Generous on purpose: the slowest
// phase reports every 25 versions, which on the test bench is 0.4 s.
const SILENCE_BEFORE_DOUBT = 60_000;

// The parts are fetched with this module's own query string, so a new
// release busts them together with the entry point. panel.py digests
// every file into that query for exactly this reason: a plain import
// carries no query at all, and Home Assistant sets no Cache-Control on
// a static path - only ETag and Last-Modified, which makes a stale part
// an intermittent failure rather than an obvious one.
const PARTS = new URL(import.meta.url).search;

// One page of history. Twenty-five and not fifty: a first screen is for
// finding your bearings, not for holding everything, and the button
// below it fetches the rest. Fifty stood until there *was* a button -
// lowering it earlier would have taken thirty entries off the panel and
// offered nothing to get them back with.
const PAGE = 25;

// How many rows' answers are held at once. A page's worth, because a
// page is what somebody works through before moving on, and the cache
// is dropped wholesale at the next dashboard switch or refresh anyway.
// Bounded rather than open-ended because an entry is not small any
// more: since the technical diff joined `explain`, an answer is a few
// hundred bytes for an ordinary edit and as large as the dashboard for
// one that rewrites it - 270 KB, measured against the largest real one
// on 2026-09-11.
const DETAILS_KEPT = PAGE;

// Deliberately `let`, and deliberately no top-level await. The element
// must be defined in this module's FIRST synchronous pass. Home
// Assistant creates the panel element as soon as the module is
// requested; if the definition has not run yet it gets an un-upgraded
// element, assigns `hass` to it as a plain own property, and that own
// property then shadows this class's `set hass` accessor for good.
// Measured on 2026-09-02: with a top-level await the constructor ran
// and the shadow root attached, but `set hass` never fired once in
// ninety seconds, with no error anywhere to say why.
let STYLE;
let escape, renderDiff, renderPlain, when, joinNames;
let sections, someNames, renderRow, versionHead, currentStateRow, nowChip, undoButton;
let DIALOGS;
let renderSimple;
let splitBySidebar, defaultPanelPath, arrangementFrom;

const partsReady = Promise.all([
  import(`./panel/style.js${PARTS}`),
  import(`./panel/render.js${PARTS}`),
  import(`./panel/rows.js${PARTS}`),
  import(`./panel/dialogs.js${PARTS}`),
  import(`./panel/simple.js${PARTS}`),
  import(`./panel/sidebar.js${PARTS}`),
]).then(([style, render, rows, dialogs, simple, sidebar]) => {
  STYLE = style.STYLE;
  ({ escape, renderDiff, renderPlain, when, joinNames } = render);
  ({ sections, someNames, renderRow, versionHead, currentStateRow, nowChip, undoButton } = rows);
  ({ DIALOGS } = dialogs);
  ({ renderSimple } = simple);
  ({ splitBySidebar, defaultPanelPath, arrangementFrom } = sidebar);
});

// Where the chosen mode is remembered. In the browser and not in the
// config entry: the design record calls it a setting of the interface,
// and two admins in one house may reasonably want different ones. It
// costs no round trip, no reload and no restart.
const MODE_KEY = "dashboard-history:mode";
const MODES = ["simple", "advanced"];

// Shown over the main column while anything is in flight, on the same
// `_busy` the bar's "working..." reads. The bar alone was easy to miss:
// it says the page is doing something in the one corner nobody is
// looking at while they wait for the middle of the screen.
//
// `role="status"` with a text label rather than a bare spinning box, so
// a screen reader is told the same thing the animation says; `aria-live`
// polite, because it is not worth interrupting anyone over.
const SPINNER =
  '<div class="spin" role="status" aria-live="polite">'
  + '<span class="ring"></span><span class="sr">Loading</span></div>';

/**
 * The remembered mode, or the simple one.
 *
 * Everything can throw here - a private window, site data switched off -
 * and every failure costs the memory of a choice and never the page.
 * An unrecognised value falls back too: an older version of this panel
 * or a hand edit must not be able to leave somebody with a blank page.
 */
function storedMode() {
  try {
    const found = localStorage.getItem(MODE_KEY);
    if (MODES.includes(found)) return found;
  } catch {
    // Nothing to do and nothing to report: the default is right here.
  }
  return "simple";
}

// The same spelling the automatic versions use, so a list of them reads
// as one list. Built by hand rather than with toLocaleDateString, which
// follows the browser's language: two people in one house would
// otherwise name the same day differently.
const MONTHS = ["January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December"];

function today() {
  const now = new Date();
  return `${now.getDate()} ${MONTHS[now.getMonth()]} ${now.getFullYear()}`;
}

/**
 * `home/v1.2.0` as `v1.2.0`.
 *
 * A version's name carries the dashboard's key as a namespace, and
 * nothing on the screen wants to read that key twice - it is already
 * the title above the list. Eight places said this in the same two
 * calls.
 */
function shortName(name) {
  return name.split("/").pop();
}

class DashboardHistoryPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._mode = storedMode();
    // Every version of the selected dashboard, whatever is loaded of its
    // changes. The simple mode is built from this and not from
    // `change.versions`, so that a version outside the window still
    // appears - which is the whole reason project G came first.
    this._versions = [];
    // What is in the search box, what the server answered (null while it
    // was never asked), whether it is being asked right now, and the
    // pending keystroke timer.
    this._query = "";
    // Whether somebody has asked for the whole history for this
    // word. It belongs to the word, so it is cleared wherever the
    // query is.
    this._wide = false;
    this._found = null;
    this._moreFound = false;
    this._searching = false;
    this._typing = null;
    // Whether the search box holds the caret, and where in the word it
    // sits. A render builds a new box, so both have to live outside it -
    // see the end of `_render`, which puts the caret back only where it
    // was.
    this._inBox = false;
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
    this._caret = null;
    // The versions holding exactly what the dashboard holds now, worked
    // out by the server against *every* version. Read rather than
    // recomputed: doing it here means doing it over the loaded window,
    // and a version below that window is precisely the one that must
    // still be named.
    this._matching = [];
    // Whether `_versions`/`_matching` above are known to belong to the
    // dashboard `_changes` is currently showing. `_select` clears both
    // synchronously, before the fetch that would refill them, while
    // `_changes` itself is left holding the previous dashboard's rows
    // until the answer arrives - the one render `_guard` draws in
    // between would otherwise pair stale, still-displayed rows with a
    // freshly emptied `_versions`, and the "right now" element read
    // that as "nothing has ever been recorded here" for a moment. See
    // `_renderNowSection`/`_renderNowBanner`, the two places that ask.
    this._versionsLoaded = true;
    // What day it is where Home Assistant runs, as `history` answers
    // it. See `_dayTitle`.
    this._serverToday = null;
    this._dashboards = [];
    this._changes = [];
    // Where the next page starts, or null when there is nothing older.
    // A commit and not a count: save something while somebody is
    // reading, and every offset below them shifts by one.
    this._cursor = null;
    // Whether a page below the one on the screen is already on its way.
    // See `_loadOlder`.
    this._loadingOlder = false;
    this._selected = null;
    this._open = null; // revision of the expanded change
    this._compareMode = false;
    this._compareSelection = [];
    // The cards `_openCompare` found missing on the historical side, kept
    // as data rather than re-read from the dialog's own rendered markup -
    // see `_openCompare` and the `[data-compare-restore]` handler.
    this._compareMissing = [];
    this._explanation = null;
    this._undo = null;
    this._loadingDetail = null;
    this._loadingUndo = null;
    this._diffOpen = false;
    // Answers for rows already expanded once. Keyed by revision, dropped
    // when the dashboard changes or the history is refreshed after an
    // outside save - both of which make cached undo previews stale.
    this._detailCache = new Map();
    // How this user has arranged their sidebar, as `frontend/get_user_data`
    // answers it, or null while it has not been read or could not be.
    // See `_loadSidebar`.
    this._sidebar = null;
    // The sidebar's two groups below the dashboards. Kept out here for
    // the same reason as `_verOpen`: a re-render builds new <details>
    // elements, and without this the fold somebody is working in shuts
    // itself the moment anything else on the page changes.
    //
    // The sidebar's, and nothing else. The simple mode's current-state
    // box sat here too, on the grounds that `_verOpen` is keyed by
    // version name and the box is not a version - which stopped being
    // true when the box began carrying one. A fold that changed shelves
    // depending on the data was a fact in two places, so it moved to
    // the set below and this one is what its name says again.
    this._foldOpen = { apart: false, dead: false };
    // Which folds in the main area are open, keyed by name: a version
    // section by its first version, and the simple mode's current-state
    // box by the version it carries - or by the bare word `now` where
    // it carries none. Those cannot collide: a version's key is a
    // dashboard and a number with a slash between them.
    //
    // Native <details> state alone does not survive a re-render -
    // _render() replaces the whole shadow DOM, so without this a "Back
    // to this version" click would collapse the very section it was
    // clicked from, the moment _guard's preview fetch triggers the
    // first re-render.
    this._verOpen = new Set();
    // A count, not a flag. Two requests can be in flight at once - a row
    // opened while the previous row's answers are still coming - and a
    // flag went dark when the *first* of them finished. Measured on
    // 2026-09-03 in the Node run behind tests/test_panel_behaviour.py.
    this._busy = 0;
    // The one state that takes the whole page away: what `forget` is
    // doing right now, or null. Everything else here is a spinner beside
    // a page somebody can still use; this is not. Measured 2026-09-18 on
    // the test bench: forgetting takes 24 s undisturbed and 76 s while
    // this panel keeps asking questions, because both compete for the
    // same interpreter. Taking the controls away is not politeness, it
    // is what makes the operation three times faster.
    this._forgetting = null;
    // A render that fell due while a dialog was open. See `_render`.
    this._renderOwed = false;
    // The 180 ms the glider is given to slide before the panel is
    // rebuilt under it. Held so it can be called off - see
    // `disconnectedCallback`.
    this._modeSlide = null;
    this._error = null;
    this._loaded = false;
    // One ticket counter per slot the page can fill - the change list,
    // the open row's detail. Comparing the selection or the open revision
    // after an answer is not enough: choose A, then B, then A again, and
    // the first A's late answer passes that check and overwrites the
    // second's. See `_claim`.
    // `write` is claimed by everything that previews a write before
    // doing it. It exists apart from the other two because a search or
    // an older page must not invalidate a preview, and picking another
    // dashboard must.
    this._tickets = { changes: 0, detail: 0, search: 0, write: 0 };
  }

  /**
   * Take a slot for one request; answers whether it is still yours.
   *
   * Every request that fills a slot claims it first, which invalidates
   * whoever held it before. The predicate goes to `_guard` so a late
   * failure stays off the banner, and is asked again before the answer
   * is written. One mechanism for every place that had grown its own -
   * `_select` by key, `_expand` by revision, `_refresh` by key alone.
   */
  _claim(slot) {
    const ticket = ++this._tickets[slot];
    return () => this._tickets[slot] === ticket;
  }

  /**
   * Switch the mode and remember it, in that order.
   *
   * The switch itself never depends on the remembering: a browser that
   * refuses to store still shows the other mode for as long as the page
   * is open, which is the part somebody just asked for.
   */
  /**
   * Switch the mode, but let the glider arrive first.
   *
   * Rebuilding the panel replaces the switch along with everything
   * else, and a glider replaced mid-slide never slides: it is simply
   * drawn at the far end. 180 ms buys the animation its own time.
   *
   * Held in `_modeSlide` rather than left to run. Two things overtake
   * it - a second click inside the window, and leaving the panel - and
   * `_setMode` is not free at the end of it: with a word in the search
   * box it puts the search again, which walks the whole history, about
   * half a second per thousand commits. Running that for a page nobody
   * is on is the case `disconnectedCallback` was already cancelling a
   * keystroke for.
   *
   * `globalThis` and not `window`: the same reach in a browser, and
   * the panel's own tests run this in Node, where `window` is not a
   * name at all and `window.matchMedia?.()` throws before the optional
   * call can help.
   */
  _modeAfterSlide(mode) {
    const reduced = globalThis.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
    if (reduced) return this._setMode(mode);
    clearTimeout(this._modeSlide);
    this._modeSlide = setTimeout(() => {
      this._modeSlide = null;
      this._setMode(mode);
    }, 180);
  }

  _setMode(mode) {
    if (!MODES.includes(mode)) return;
    this._mode = mode;
    try {
      localStorage.setItem(MODE_KEY, mode);
    } catch {
      // See `storedMode`. The choice holds for this page and no longer.
    }
    // The two modes search different things - the simple one filters the
    // complete version list and needs nobody, the advanced one walks the
    // whole history over the network - so a query standing at the switch
    // has to be put again in the new mode's terms. Without this, coming
    // over to the advanced view with a word in the box answered
    // "Nothing matches." for a question nobody had asked: the simple
    // mode never asks, so `_found` was still `null`, and only a further
    // keystroke set the search going.
    if (this._query.trim()) return this._search(this._query);
    this._render();
  }

  /** Turns the compare mode's checkboxes on or off, clearing any pick. */
  _toggleCompareMode() {
    this._compareMode = !this._compareMode;
    this._compareSelection = [];
    this._render();
  }

  /**
   * One pick in the compare mode. `revision` is `null` for "Current
   * state" - the one pick that is not a recorded revision at all.
   *
   * `now` says this pick is *known* to hold exactly what the dashboard
   * holds right now - true by definition for "Current state" itself,
   * and also true for an ordinary row or version that carries the same
   * fact (`same_as_now`, or a version sitting on the newest change).
   * `_openCompare` reads it to decide whether Put-back applies, rather
   * than asking only "is this literally the pinned pick" - a picked
   * revision that is *known* current is exactly as good a baseline as
   * the pinned one, and treating it as a different case is what made
   * Put-back silently withhold itself from a row that already told you
   * it was current.
   *
   * A third pick evicts the oldest of the two standing picks (FIFO),
   * never an error: comparing is exploratory, and blocking a third
   * click would only make somebody uncheck one first for no reason.
   * Picking an already-selected revision again removes just that one.
   */
  _toggleCompareRevision(revision, label, now = false) {
    const at = this._compareSelection.findIndex((s) => s.revision === revision);
    if (at >= 0) {
      this._compareSelection.splice(at, 1);
    } else {
      this._compareSelection.push({ revision, label, now: now || revision === null });
      if (this._compareSelection.length > 2) this._compareSelection.shift();
    }
    this._render();
    if (this._compareSelection.length === 2) this._openCompare();
  }

  /**
   * The jump a refused undo offers into compare mode: the row's own
   * predecessor against the current state, the same pair the removed
   * row-level list used to show automatically.
   *
   * Sets the end state directly rather than calling
   * `_toggleCompareMode`/`_toggleCompareRevision` in sequence - doing
   * that with a *different* pick already standing would fire
   * `_openCompare` once with the wrong pair and once more on top of
   * the dialog that first call already opened.
   */
  _jumpToCompareFrom(previousRevision) {
    if (!previousRevision) return;
    const row = this._changeAt(previousRevision);
    this._compareMode = true;
    this._compareSelection = [
      { revision: previousRevision, label: row?.description || row?.message || "" },
      { revision: null, label: "Current state", now: true },
    ];
    this._render();
    this._openCompare();
  }

  /**
   * Opens the compare dialog for the two current picks.
   *
   * Sends both picks to `compare` in whatever order they were selected
   * - the backend works out which one is actually older, not this
   * method. A picked row can outlive a refresh that dropped it from
   * `_changes` (spec decision 19's own edge case), so `_changes`
   * cannot be trusted here the way an earlier draft of this method
   * trusted it. `revision_a`/`revision_b` come back reassigned into
   * chronological order; matching them against the two local picks
   * says which label and date belong on which side.
   */
  async _openCompare() {
    const [first, second] = this._compareSelection;
    // Read once, not re-read after the awaits below: `_select` claims
    // "write" on a dashboard switch, which is exactly what a stale
    // in-flight compare must not survive - reading `this._selected`
    // again down there would ask `deleted_since` about *this*
    // dashboard's revision against whatever dashboard somebody has
    // since switched to.
    const dashboard = this._selected;
    const mine = this._claim("write");
    const dialog = this.shadowRoot.querySelector("dialog.compare");
    const body = dialog.querySelector("[data-compare-body]");
    body.innerHTML = `<p class="muted row-loading"><span class="ring mini"></span> Comparing…</p>`;
    dialog.returnValue = "";
    dialog.showModal();

    const compareArgs = { dashboard };
    if (first.revision !== null) compareArgs.revision_a = first.revision;
    if (second.revision !== null) compareArgs.revision_b = second.revision;
    const comparison = await this._call("compare", compareArgs);
    // Bail out silently once the context has moved on: `!mine()` means
    // a dashboard switch since this call started, and `!dialog.open`
    // means the dialog itself was closed while it was in flight -
    // either way, nothing below is still meant for whoever is looking
    // at the page now. Left this way rather than proceeding: writing
    // into a closed dialog's body is harmless on its own, but the
    // `deleted_since` call further down is not - it would otherwise
    // ask about the dashboard picked *here* against whatever dashboard
    // is selected by the time it runs.
    if (!mine() || !dialog.open) return;

    if (comparison.error) {
      body.innerHTML = `<p class="why">${escape(comparison.error)}</p>`;
      await this._answerFrom(dialog);
      return;
    }

    const older = first.revision === comparison.revision_a ? first : second;
    const newer = older === first ? second : first;

    // Spec decision 19/9: naming date and automatic message on each
    // side is not decoration - it is what removes the "one row too
    // early" trap decision 9 removed for the single-change case.
    // Without it, nothing here says which picked row ended up which
    // side of the sentence below.
    // Not escaped here: the whole heading this builds into is escaped
    // once, wholesale, by `renderPlain` (`<h3>${escape(heading)}</h3>`)
    // - escaping the label again here as well doubled every `&` in it
    // to `&amp;amp;`. The literal double quotes around the label still
    // come out as `&quot;`, from that one, outer escape.
    const describe = (entry, time) =>
      entry.revision === null
        ? "Current state"
        : `the state after "${entry.label}" (${escape(when(time))})`;

    let missingHtml = "";
    // Put back wherever the newer side is *known* to hold the current
    // state - not only where it is literally the pinned "Current state"
    // pick. A row or version already marked as holding exactly today's
    // content (`now`, set in `_toggleCompareRevision`) is just as valid
    // a baseline: `deleted_since`/`restore_deleted` always work against
    // the live configuration regardless of which revision named it.
    const historicalSide = newer.now ? older : null;
    if (historicalSide) {
      const missing = await this._call("deleted_since", {
        dashboard,
        revision: historicalSide.revision,
      });
      if (!mine() || !dialog.open) return;
      const items = missing.items || [];
      // Grouped by view, the same way the diff above already groups its
      // own entries (`renderPlain`) - the items themselves arrive in
      // view order (`find_removed` walks the views in order), so a plain
      // first-seen grouping lines up with that diff's groups without
      // having to sort anything.
      const missingGroups = [];
      const byView = new Map();
      for (const item of items) {
        const view = item.view_title || item.view || "";
        if (!byView.has(view)) {
          const group = { view, items: [] };
          byView.set(view, group);
          missingGroups.push(group);
        }
        byView.get(view).items.push(item);
      }
      missingHtml = items.length
        ? `<p class="why" style="margin-top:16px">Missing since then, still gone:</p>` +
          // `.view`'s indent-and-border look comes from `.plain .view` -
          // a descendant rule, so this reuses it verbatim only by
          // sitting inside a `.plain` wrapper of its own, the same way
          // the diff's groups above already do.
          `<div class="plain">` +
          missingGroups
            .map(
              (group) => `
          <div class="view">
            <strong>In the view ${escape(group.view)}</strong>
            ${group.items
              .map(
                (item) => `
            <div class="item">
              <span class="label">${escape(item.label)}
                <span class="where">${escape(item.kind)}</span>
              </span>
              <button class="act" data-compare-restore="${item.position}">Put back</button>
            </div>`,
              )
              .join("")}
          </div>`,
            )
            .join("") +
          `</div>`
        : `<p class="muted">Nothing from before this state is missing today.</p>`;
      dialog.dataset.compareReference = historicalSide.revision;
      // Retained for the click handler below: `.label`'s rendered
      // markup nests a `.where` badge inside it, so reading the
      // button's own item back out of `.textContent` would run the
      // two together (`"Gone card card · view a"`) instead of naming
      // the clean label `_restoreItem`'s dialog title shows.
      this._compareMissing = items;
    } else {
      delete dialog.dataset.compareReference;
    }

    const diff = comparison.diff || "";
    body.innerHTML = diff
      ? renderPlain(
          comparison,
          `What changed between ${describe(older, comparison.time_a)} and ${describe(newer, comparison.time_b)}`,
        ) +
        `<details class="raw"><summary><span class="glyph">&lt;/&gt;</span> Technical details</summary>${renderDiff(diff)}</details>` +
        missingHtml
      : `<p class="muted">No difference between these two states.</p>`;

    await this._answerFrom(dialog);
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._loaded) {
      this._loaded = true;
      // Only the first render waits for the parts. Everything else in
      // this class reads STYLE, escape, renderDiff, renderPlain and when
      // at call time, and no render can happen before _loadDashboards -
      // there is no connectedCallback, the constructor draws nothing, and
      // every listener is bound inside _render itself.
      partsReady.then(
        () => this._loadDashboards(),
        (err) => this._failedToLoad(err),
      );
    }
    this._listen();
    // `dockedSidebar` and `kioskMode` arrive here, not through `narrow`.
    this._refreshMenuButton();
  }

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

  /**
   * Hear about recorded changes, once.
   *
   * `set hass` runs again and again, so the slot is claimed before the
   * subscription resolves - two subscriptions would refresh the page
   * twice for one change. A failure here costs live updates and nothing
   * else: the reload button and the panel's own actions still work, so
   * it is reported to the console rather than to the page.
   */
  _listen() {
    if (this._sub || !this._hass?.connection) return;
    this._sub = "pending";
    this._hass.connection
      .subscribeEvents((event) => this._onForgetting(event), EVENT_FORGETTING)
      .then(
        (off) => {
          this._subForget = off;
          if (!this.isConnected) this._unlisten();
        },
        () => {
          // A lock screen without a counter still locks, and the reload
          // it offers after a minute of silence is the way out. Not
          // worth a banner over a page nobody can act on anyway.
          this._subForget = null;
        },
      );
    this._hass.connection
      .subscribeEvents((event) => this._onRecorded(event), EVENT_RECORDED)
      .then(
        (off) => {
          this._sub = off;
          // Removed while we were subscribing.
          if (!this.isConnected) this._unlisten();
        },
        (err) => {
          this._sub = null;
          console.warn(`${DOMAIN}: no live updates; use the reload button`, err);
        },
      );
  }

  _unlisten() {
    const off = this._sub;
    this._sub = null;
    if (typeof off === "function") off();
    const offForget = this._subForget;
    this._subForget = null;
    if (typeof offForget === "function") offForget();
  }

  disconnectedCallback() {
    // Home Assistant keeps panels around between visits. A subscription
    // that outlives the element would keep fetching a history nobody is
    // looking at.
    this._unlisten();
    // And an observer waiting for a column that will never appear now.
    this._unwatchDiff();
    // And so would a keystroke's 400 ms. Type, then leave the panel,
    // and the walk over the whole history - about half a second per
    // thousand commits - runs for a page nobody is on, to write its
    // answer into an element that is off the screen. Cancelled here for
    // the same reason `7d37e9c` cancels a mark in flight on unload.
    clearTimeout(this._typing);
    this._typing = null;
    // And the mode switch's 180 ms, for the same reason: it ends on
    // `_setMode`, which puts a standing search again.
    clearTimeout(this._modeSlide);
    this._modeSlide = null;
  }

  /**
   * A change has been recorded. Decide whether this page cares.
   */
  /**
   * One step of a running `forget`, straight from the rewrite.
   *
   * Ignored unless this page started it. The event goes to every open
   * panel, and a second browser tab that is merely watching must not be
   * locked by somebody else's operation - it will notice soon enough,
   * the way it notices any other change.
   */
  _onForgetting(event) {
    if (!this._forgetting) return;
    const data = event?.data || {};
    if (data.dashboard !== this._forgetting.key) return;
    this._forgetting.phase = data.phase;
    this._forgetting.done = data.done;
    this._forgetting.total = data.total;
    this._forgetting.heard = Date.now();
    this._render();
  }

  /**
   * The whole page while a history is being rewritten.
   *
   * Everything else is deliberately gone: no list, no history, no
   * buttons. The reason is measured rather than tidy - a click here
   * costs the operation more than it costs the person waiting (24 s
   * undisturbed against 76 s while this panel asks questions), because
   * the rewrite and every answer this page wants come out of the same
   * Python interpreter.
   *
   * What it does say is how far the rewrite has got, and that is the
   * part that matters: a number that moves is the difference between
   * waiting and reloading. When it stops moving for a minute, the text
   * says so rather than pretending - see SILENCE_BEFORE_DOUBT.
   */
  _renderLock() {
    const state = this._forgetting;
    const quiet = Date.now() - state.heard > SILENCE_BEFORE_DOUBT;
    const phases = {
      rewriting: "Rewriting the recorded states",
      versions: "Rebuilding the version marks",
      cleaning: "Clearing out what is left",
      reloading: "Reading the history back in",
    };
    const what = phases[state.phase] || "Working";
    const counted =
      state.total > 0 ? ` — ${state.done} of ${state.total}` : "";
    return `
      <div class="lock">
        <div class="lockbox">
          <h2>Forgetting ${escape(state.title)}</h2>
          <p class="step">${escape(what)}${escape(counted)}</p>
          ${SPINNER}
          <p class="muted">
            The stored history is being rewritten, which takes a while when
            there are many version marks. Home Assistant itself keeps
            running normally — only this page waits, and leaving it alone
            is what makes it finish soonest.
          </p>
          ${quiet
        ? `<p class="doubt">Nothing has been reported for a minute. The
               operation may still be running, but this page can no longer
               tell. If nothing changes, reload it.</p>`
        : ""}
        </div>
      </div>`;
  }

  _onRecorded(event) {
    if (this._awaiting) {
      // An action of our own is waiting for exactly this and refreshes
      // itself; a second refresh here would race it.
      const done = this._awaiting;
      this._awaiting = null;
      done();
      return;
    }
    if (this.shadowRoot?.querySelector("dialog[open]")) return;
    const named = event?.data?.dashboards;
    if (
      Array.isArray(named) &&
      named.length &&
      this._selected &&
      !named.includes(this._selected)
    ) {
      // Another dashboard. The sidebar may have gained or lost one; the
      // history in front of this person did not change.
      this._loadDashboardsQuietly();
      return;
    }
    this._refreshQuietly();
  }

  /**
   * Resolve once the recorder reports, or after `seconds` regardless.
   *
   * The fallback is not decoration. A confirmed write always changes the
   * configuration and therefore always produces a commit - but if the
   * announcement were ever lost, waiting for it forever would leave the
   * page frozen mid-action, which is worse than the flicker this exists
   * to remove.
   */
  _recorded(seconds = 3) {
    return new Promise((resolve) => {
      const timer = setTimeout(() => {
        this._awaiting = null;
        resolve();
      }, seconds * 1000);
      this._awaiting = () => {
        clearTimeout(timer);
        resolve();
      };
    });
  }

  /** Read everything again, keeping the row that is open if it survives. */
  async _refresh() {
    const [listed] = await Promise.all([
      this._call("dashboards"),
      this._loadSidebar(),
    ]);
    this._dashboards = listed.dashboards || [];
    if (this._selected) {
      const asked = this._selected;
      const mine = this._claim("changes");
      const [history, versions] = await Promise.all([
        this._call("history", { dashboard: asked, limit: PAGE }),
        this._call("versions", { dashboard: asked }),
      ]);
      // Same race as in `_select`, and reachable from further away: this
      // one is started by an event, so it can be in flight at the moment
      // somebody picks another dashboard. Its answer is dropped, but the
      // list read before it is still current and worth drawing.
      if (!mine()) {
        this._render();
        return;
      }
      this._changes = history.changes || [];
      // Deliberately back to the first page. A refresh happens because
      // the history grew, and stitching a fresh top onto pages fetched
      // before it grew would show a list that never existed. Whoever had
      // loaded older entries presses the button again - which is honest,
      // and cheap, and the alternative is a list nobody can trust.
      this._cursor = history.next_cursor ?? null;
      this._matching = history.matching_versions || [];
      this._serverToday = history.today ?? null;
      this._versions = versions.versions || [];
      // An expanded row keeps its place, but not its answers: after a
      // change from outside, "Put back" would be offering items worked
      // out against a dashboard that has moved on.
      this._detailCache.clear();
      const open = this._changeAt(this._open);
      if (!open) {
        this._claim("detail");
        this._open = null;
        this._clearDetail();
      } else {
        const detailMine = this._claim("detail");
        const detail = await this._detailFor(open);
        // Taken only while the slot is still this request's; a newer
        // one for the same row wins. Not a `return` any more, because
        // whatever became of the row's detail, the search below still
        // has to be dealt with.
        if (detailMine()) this._take(detail);
      }
      // A search standing over a history that has just been replaced is
      // put again. Its hits were worked out against the list this
      // refresh has just thrown away, so leaving them would show
      // matches from before the change; and where the refresh landed
      // *while* the search was out, this is the only thing that starts
      // it again.
      if (mine() && this._query.trim()) {
        await this._search(this._query);
        return;
      }
    }
    this._render();
  }

  /**
   * The same, with its failures swallowed.
   *
   * For the refresh nobody asked for - a save somewhere else in Home
   * Assistant announcing itself - and for that one only. The reload a
   * writing flow ends on is `_reloadAfterWrite`, which says when it
   * fails.
   */
  async _refreshQuietly() {
    try {
      await this._refresh();
    } catch {
      // Nobody asked for this one. An error banner arriving from nowhere
      // is worse than a page that is briefly out of date; the button
      // reports its own failures.
    }
  }

  /**
   * The reload every writing flow ends on. Answers with a sentence
   * where it failed, and null where it came through.
   *
   * `_select` used to do that job, and `_select` clears the query, the
   * results and the cursor along with everything else. Describing a row
   * the server had found therefore dropped whoever wrote it back onto
   * the unfiltered first page with an empty box, to type the search
   * again for every further hit. The search belongs to the dashboard,
   * and the dashboard has not changed; so does the open row, which
   * `_refresh` keeps and fetches fresh answers for.
   *
   * Not `_refreshQuietly`, though, and this is the whole point of the
   * method: the deliberate quiet there is for a refresh nobody asked
   * for. This one follows a write somebody just made. Swallow its
   * failure and the write lands, the page goes on showing the state
   * from before it, and nothing on the screen says why - the worst
   * outcome this integration knows. `done` names what did succeed, so
   * the sentence can carry both halves at once.
   *
   * Busy while it runs, for the same reason: it is part of the action
   * somebody started, and `_refresh` on its own draws no "working..."
   * at all. Rendered in the `finally` as well, or the indicator raised
   * here would stay up on the last frame `_refresh` drew.
   */
  async _reloadAfterWrite(done) {
    this._busy += 1;
    this._render();
    try {
      await this._refresh();
      return null;
    } catch (err) {
      const why = err?.message || String(err);
      return `${done}, but the page could not be reloaded: ${why}`;
    } finally {
      this._busy -= 1;
      this._render();
    }
  }

  get hass() {
    return this._hass;
  }

  /**
   * The panel is built from three files and two of them arrive over the
   * network. If they do not, nothing else here can run: STYLE and escape
   * are still undefined, so even the banner _render draws for a failure
   * would throw on its way out. Hence plain markup built without them,
   * and the console as well - a banner in a shadow root is invisible to
   * anyone reading a log.
   */
  _failedToLoad(err) {
    console.error(`${DOMAIN}: the panel could not load its parts`, err);
    const note = document.createElement("p");
    note.style.cssText = "padding:24px;font:14px sans-serif;color:#b00020";
    note.textContent =
      "Dashboard History could not load part of itself. Reload the page; " +
      "if that does not help, restart Home Assistant. " +
      (err?.message || String(err));
    this.shadowRoot.replaceChildren(note);
  }

  _call(type, extra = {}) {
    return this._hass.callWS({ type: `${DOMAIN}/${type}`, ...extra });
  }

  /**
   * Run one request with the busy indicator on and its failure shown.
   *
   * `stillWanted`, when given, is asked before a failure is shown: a
   * request whose answer nobody is waiting for any more must not put
   * its error under the thing that replaced it. Measured on 2026-09-04:
   * dashboard A chosen, then B; B drawn, then A failed late - and the
   * banner over B's history said "A failed".
   */
  async _guard(work, stillWanted = null) {
    this._busy += 1;
    this._error = null;
    this._render();
    try {
      return await work();
    } catch (err) {
      if (stillWanted === null || stillWanted()) {
        this._error = err?.message || String(err);
      }
      return null;
    } finally {
      this._busy -= 1;
      this._render();
    }
  }

  /**
   * Put one sentence in the banner, and draw it.
   *
   * The two lines belong together - a message set without a render is a
   * message nobody sees - and seven places had written them out one
   * under the other.
   */
  _showError(message) {
    this._error = message;
    this._render();
  }

  /**
   * The banner for an action that has finished, over the dashboard the
   * action was about and over no other.
   *
   * The write itself has been pinned to the dashboard somebody approved
   * it for since `_confirm` learned to hold the key across the dialog.
   * The sentence reporting it was not. Between Apply and the banner the
   * write runs, the recorder is waited for - up to three seconds - and
   * the page is reloaded, and the sidebar is live throughout: pick
   * another dashboard in that window and a sentence about the first one
   * lands over the second one's history. A message in the wrong place
   * rather than a write in the wrong place, but the same fault, and the
   * same answer `_guard` already gives it with `stillWanted`.
   *
   * Dropped rather than kept for later. The sentence belongs to an
   * action somebody watched start; showing it over a page they have
   * moved on to would be a second wrong place, not the right one. What
   * the write did is on the screen either way - the history below has
   * been reloaded - and the person can come back to the dashboard and
   * read it there.
   *
   * The render is not conditional. Whatever the banner does, the page
   * behind this call has just changed.
   */
  _sayAbout(asked, message) {
    // Cleared where there is nothing to say: the banner above belongs
    // to the action that has just finished.
    if (this._selected === asked) this._error = message || null;
    this._render();
  }

  async _loadDashboards() {
    const [result] = await Promise.all([
      this._guard(() => this._call("dashboards")),
      this._loadSidebar(),
    ]);
    if (!result) return;
    this._dashboards = result.dashboards || [];
    // The first row of the list on the left, which is not the first
    // dashboard the server named: see `_orderedDashboards`.
    //
    // A live one, because the order puts the deleted ones last. This
    // used to open on a deleted dashboard, on the reasoning that a loss
    // is what people come here for - but with a dozen deleted ones it
    // picks an arbitrary gravestone, and they are behind a fold now
    // anyway.
    const [first] = this._orderedDashboards().listed;
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
  }

  /**
   * Put the top of the panel back in front of whoever just clicked.
   *
   * With enough dashboards the sidebar is longer than the window, so the
   * row somebody picks sits far down the page - and the history they
   * asked for is drawn at the top of a column they have scrolled past.
   * What they get is the grey underneath it, which reads as a dashboard
   * with no history rather than as a page that needs scrolling.
   *
   * Both ways this page can be scrolled, because which one applies is
   * not this panel's to know: `.main` scrolls where the panel is given a
   * height of its own, and Home Assistant's page scrolls where it is
   * not - measured in Chrome on 2026-09-07, where the document had moved
   * 600px and the column none.
   *
   * Guarded, like every other reach for the platform in here. `pytest`
   * runs this module in Node against a two-line stand-in for the DOM,
   * and a panel that cannot be loaded without a browser is a panel with
   * no tests.
   */
  _backToTheTop() {
    try {
      const main = this.shadowRoot?.querySelector(".main");
      // On its own this moves nothing: .main never scrolls, because
      // the host sizes to its content - the note beside its rule in
      // style.js has the measurements. `scrollIntoView` below is what
      // does the work. Kept as the correct half of the pair for the
      // day the column is given a height of its own.
      if (main) main.scrollTop = 0;
      this.scrollIntoView?.({ block: "start" });
    } catch {
      // A view that stays where it was is a poor answer; a switch that
      // throws is a worse one.
    }
  }

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

  async _select(key) {
    const mine = this._claim("changes");
    this._claim("detail"); // the open row went with the old selection
    // And so did any preview that was fetched for it. See `_confirm`:
    // the request that writes used to read `this._selected` a second
    // time, long after the diff somebody approved was built.
    this._claim("write");
    this._claim("search"); // and any walk over the old dashboard's history
    this._selected = key;
    // Before the history is asked for, not after it arrives: the point
    // is that the answer is drawn where somebody is looking, and by the
    // time it lands they have been staring at grey for a second.
    this._backToTheTop();
    this._open = null;
    this._clearDetail();
    this._detailCache.clear();
    // A pick made while viewing one dashboard must not survive a switch
    // to another: found by the final review, a standing selection from
    // dashboard A - one checkbox click away from completing a compare,
    // or "current state" already picked and one click away from
    // reopening the dialog - would otherwise pair up with a pick made
    // on B, comparing B's freshly-picked state against A's leftover
    // commit and labelling the whole thing with A's message and date.
    this._compareMode = false;
    this._compareSelection = [];
    this._compareMissing = [];
    this._cursor = null;
    this._versions = [];
    this._matching = [];
    this._versionsLoaded = false;
    this._query = "";
    // Whether somebody has asked for the whole history for this
    // word. It belongs to the word, so it is cleared wherever the
    // query is.
    this._wide = false;
    this._found = null;
    this._moreFound = false;
    this._searching = false;
    // A keystroke whose 400 ms run out after the switch would send the
    // old word to the new dashboard.
    clearTimeout(this._typing);
    this._typing = null;
    const result = await this._guard(
      () =>
        Promise.all([
          this._call("history", { dashboard: key, limit: PAGE }),
          this._call("versions", { dashboard: key }),
        ]),
      mine,
    );
    // Click two dashboards quickly and both requests are in flight. The
    // slower answer arriving last would be written into the list under
    // the name of the dashboard the faster one selected - a history
    // shown beside the wrong title, with buttons that act on the title.
    // Whoever no longer holds the slot drops its answer.
    if (!mine()) return;
    const [history, versions] = result || [null, null];
    this._changes = history ? history.changes || [] : [];
    this._cursor = history ? history.next_cursor ?? null : null;
    this._matching = history ? history.matching_versions || [] : [];
    this._serverToday = history ? history.today ?? null : null;
    this._versions = versions ? versions.versions || [] : [];
    this._versionsLoaded = true;
    this._render();
  }

  /**
   * Fetch the page below the one that is showing, and append it.
   *
   * Appended, never substituted: the button says "load older", and a
   * list that got shorter after pressing it would be a lie told by a
   * label. The claim ticket is the same one `_select` uses, so a page
   * that arrives after somebody has picked another dashboard is dropped
   * rather than stitched under a stranger's history.
   */
  async _loadOlder() {
    if (!this._cursor || !this._selected) return;
    // A second press while the first page is still on its way asks for
    // exactly the same page again. Nothing breaks - the claim ticket
    // drops the loser, so the list is right either way - but the button
    // invites the double click more than anything else here does: it
    // sits at the bottom of a list, nothing about it changes while it
    // works, and the page it fetches is the slowest read the ordinary
    // path makes. Every other guarded action is one click on one row,
    // and answering "the others behave like this too" would be
    // answering about a different button.
    if (this._loadingOlder) return;
    const mine = this._claim("changes");
    const asked = this._cursor;
    this._loadingOlder = true;
    try {
      const result = await this._guard(
        () =>
          this._call("history", {
            dashboard: this._selected,
            limit: PAGE,
            before: asked,
          }),
        mine,
      );
      if (!mine() || !result) return;
      this._changes = this._changes.concat(result.changes || []);
      this._cursor = result.next_cursor ?? null;
      this._render();
    } finally {
      // In a `finally`, so a failure lets the button work again. A flag
      // that stuck after one refused request would leave the rest of
      // the history unreachable for as long as the page is open.
      this._loadingOlder = false;
    }
  }

  /**
   * Search in two steps: what is loaded, then the whole history.
   *
   * The first step answers without a round trip and covers almost every
   * search, because what somebody looks for is usually what they have
   * just read. The second exists so that "nothing found" means nothing
   * found - the panel holds twenty-five entries, and letting that decide
   * the answer would be the same invisible gap this project has closed
   * three times elsewhere.
   *
   * The simple mode never gets here past the first line: it filters the
   * complete version list, which needs nobody's help to be complete.
   */
  async _search(text) {
    // A new word is a new question. `_search` runs again on every
    // recorded change of this dashboard, with the same word, and that
    // must not take back what somebody asked for - so the flag is
    // dropped on a change of word, not on every call.
    if (text.trim() !== this._query.trim()) this._wide = false;
    this._query = text;
    this._found = null;
    this._moreFound = false;
    // The empty box needs no test of its own: nobody is asked for
    // nothing, and nobody is asked for a single letter either.
    if (
      this._mode === "simple" ||
      text.trim().length < 2 ||
      (!this._wide && this._localMatches().length)
    ) {
      this._render();
      return;
    }
    // Its own slot, not the change list's. A refresh - and one runs on
    // every recorded change of this dashboard - used to take the
    // search's ticket away: the answer was then dropped, correctly, and
    // nobody started the search again, so the page said "Nothing
    // matches." over a history holding thirty of them.
    const mine = this._claim("search");
    const run = (this._searchRuns = (this._searchRuns || 0) + 1);
    this._searching = true;
    this._render();
    const result = await this._guard(
      () =>
        this._call("search", { dashboard: this._selected, text, limit: 100 }),
      mine,
    );
    // Cleared before the claim is checked, not after: a run whose claim
    // was taken by something that is not a search - `_loadOlder`, say -
    // would otherwise leave "Searching the whole history…" standing for
    // good.
    //
    // But only the newest run may clear it. Type, wait, type again, and
    // the first answer lands while the second is still out; clearing on
    // that one blanks the indicator while a search really is running,
    // and the screen says nothing is happening when something is.
    if (run === this._searchRuns) this._searching = false;
    if (!mine()) return;
    this._found = result ? result.changes || [] : [];
    this._moreFound = result ? Boolean(result.more) : false;
    this._render();
  }

  /**
   * The words a row is searched by: its own, and its versions'.
   *
   * The same four kinds `store.search_changes` matches on - the
   * generated message, a person's own description, and the title,
   * description and number of every version sitting on that state. One
   * rule written twice, on purpose: the local step answers the common
   * search without a round trip, and `_searchNote` says out loud how
   * far it looked. What keeps the two copies from drifting apart is a
   * test - `test_the_two_halves_of_the_search_look_at_the_same_fields`
   * in tests/test_panel_assets.py reads both sides and compares the
   * fields, the way the event name has been held together since it was
   * renamed on one side only.
   *
   * One difference is real and stays: `toLowerCase()` here against
   * `casefold()` there. Casefolding is the stronger of the two - it
   * folds `ß` into `ss`, which lowercasing does not - so searching
   * `strasse` finds a row saying `Straße` on the server and misses it
   * here. That is the safe direction, and it is the *only* safe one: a
   * miss here escalates to the server, which then finds it, while a hit
   * here that the server would not have made stands as the whole answer
   * and nothing ever corrects it. So if these two are ever brought
   * closer together, the local step must not end up the stronger of the
   * two. JavaScript has no casefold, and the near-equivalents cost more
   * than the one letter is worth.
   */
  _wordsOf(change) {
    return [
      change.message || "",
      change.description || "",
      ...(change.versions || []).flatMap((v) => [
        shortName(v.name || ""),
        v.title || "",
        v.description || "",
      ]),
    ]
      .join("\n")
      .toLowerCase();
  }

  /** The loaded changes whose words hold the query. */
  _localMatches() {
    const needle = this._query.trim().toLowerCase();
    if (!needle) return [];
    return this._changes.filter((c) => this._wordsOf(c).includes(needle));
  }

  /**
   * The versions the query matches - the simple mode's whole search.
   *
   * Over `_versions`, which is complete, so this needs no second step
   * and no server: there is no window here that a search could fall out
   * of.
   */
  _matchingVersions() {
    const needle = this._query.trim().toLowerCase();
    if (!needle) return this._versions;
    return this._versions.filter((v) =>
      [shortName(v.name || ""), v.title || "", v.description || ""]
        .join("\n")
        .toLowerCase()
        .includes(needle),
    );
  }

  /**
   * What the advanced list should show: the plain history, the local
   * hits, what the server found - or `null`, where nobody has answered
   * yet. One place decides it, so no renderer has to.
   *
   * `null` is the distinction this used to lack, and three findings of
   * the final review came out of it. An empty list was the answer both
   * to "nothing matched" and to "nobody has been asked", and
   * `_renderMain` turned both into "Nothing matches." - a flat sentence
   * about a question that had not been put. It stood over the note
   * reading "Searching the whole history…" for as long as the walk took,
   * and it stood for good after a mode switch or a query too short to
   * send.
   */
  _shown() {
    if (!this._query.trim()) return this._changes;
    // An answer from the whole history outranks the loaded page it
    // contains. The server matches with `casefold` where the panel uses
    // `toLowerCase`, so what it found is the wider set of the two -
    // never the smaller one, which is why this can simply take over.
    if (this._found !== null) return this._found;
    const local = this._localMatches();
    if (local.length) return local;
    return this._found;
  }

  /**
   * Whether there is a wider search left to offer.
   *
   * Only where a step was skipped: the loaded page answered, and the
   * server was therefore never asked. The note says how far that step
   * looked, which is true and was, until this, the end of the road -
   * "Load older" is hidden for as long as a query stands, so a word
   * with one hit on the page and forty behind it showed the one and no
   * way to the rest.
   *
   * Offered rather than taken: what somebody searches for is usually
   * what they have just read, and that case must keep costing nothing.
   */
  _offersWider() {
    return (
      this._mode !== "simple" &&
      !this._searching &&
      this._found === null &&
      this._query.trim().length >= 2 &&
      this._localMatches().length > 0
    );
  }

  /** Ask the whole history for the word that is already in the box. */
  async _searchWider() {
    this._wide = true;
    await this._search(this._query);
  }

  /**
   * The loaded change with this revision, or null.
   *
   * A row addresses itself by revision and not by its place in a list.
   * The place was a fine address while there was exactly one list; the
   * search box makes a second one, and then "row 3" means two different
   * rows depending on who is asking.
   */
  _changeAt(revision) {
    // Both lists, because there are two. A row the server found is by
    // definition not among the loaded changes - that is what "search the
    // whole history" means - so looking only in `this._changes` makes
    // every remote hit inert: clicking it opens nothing, describing it
    // writes nothing, and neither says why. The loaded list is asked
    // first, so the ordinary path is unchanged.
    return (
      this._changes.find((c) => c.revision === revision) ||
      (this._found || []).find((c) => c.revision === revision) ||
      null
    );
  }

  /**
   * How many loaded changes are newer than this one, or null when it is
   * not in the loaded window at all.
   *
   * A count over the history, never over whatever list is on screen. It
   * carries the half-sentence "and keeps the 3 changes made since", and
   * where the number is not known the half-sentence goes rather than
   * being guessed.
   */
  _madeSince(change) {
    const at = this._changes.findIndex((c) => c.revision === change.revision);
    return at < 0 ? null : at;
  }

  /** Whether this is the newest recorded state of this dashboard. */
  _isNewest(change) {
    return Boolean(change) && change.revision === this._changes[0]?.revision;
  }

  async _expand(revision) {
    const change = this._changeAt(revision);
    if (!change) return;
    if (this._open === revision) {
      this._claim("detail"); // closing it makes any answer in flight stale
      this._open = null;
      this._clearDetail();
      this._render();
      return;
    }
    const mine = this._claim("detail");
    this._open = revision;
    this._diffOpen = false;

    // A row expanded once keeps its answers until the dashboard changes.
    const cached = this._detailCache.get(revision);
    if (cached) {
      this._explanation = cached.explanation;
      this._undo = cached.undo;
      this._loadingDetail = null;
      this._loadingUndo = null;
      this._render();
      return;
    }

    this._clearDetail();
    this._loadingDetail = revision;
    this._loadingUndo = change.previous ? revision : null;

    const [explainPromise, undoPromise] = this._detailCalls(change);

    // Both phases below ask `mine()` before they write anything. A row
    // opened while this one's answers are still out takes the slot,
    // and what arrives afterwards belongs to nobody: `_claim` holds
    // the ticket and the case it was built for. Measured on
    // 2026-09-03, before there were two phases: the later row's
    // answers arrived first, these arrived second, and the page
    // settled on the wrong ones.

    // Fast phase: explanation
    const fastPhase = explainPromise
      .then((explanation) => {
        if (!mine()) return;
        this._explanation = explanation;
        this._loadingDetail = null;
        this._render();
      })
      .catch((err) => {
        if (!mine()) return;
        this._loadingDetail = null;
        this._error = err?.message || String(err);
        this._render();
      });

    // Slower phase: undo availability and preview
    let undoFailed = false;
    const slowPhase = undoPromise
      .then((undo) => {
        if (!mine()) return;
        this._undo = undo;
      })
      .catch((err) => {
        undoFailed = true;
        if (!mine()) return;
        // Written down, not dropped. Without the answer the row falls
        // back to "the answer did not arrive. Any message above says
        // why" - a sentence that is only true while something up
        // there does say it. The rejection used to reach `_guard`,
        // which set the banner; separating the undo from the
        // explanation so one failure could not wipe the other took
        // the banner away with it, and left the row pointing at
        // nothing.
        //
        // Only where the line is still free: if the explanation
        // failed as well, that is the cause worth reading, and this
        // one would be standing on top of it.
        if (!this._error) this._error = err?.message || String(err);
      })
      .finally(() => {
        if (!mine()) return;
        this._loadingUndo = null;
        this._render();
      });

    await this._guard(() => Promise.all([fastPhase, slowPhase]), mine);

    // Keep for the next time this row is opened, unless somebody else
    // has claimed the slot while the answers were on their way.
    //
    // And not where the undo failed. Caching that stored a network
    // error as though it were an answer: re-opening the row asked
    // nothing, showed "the answer did not arrive" again, and pointed
    // at a banner the next action had already cleared. One hiccup took
    // the undo off a row until the whole history was reloaded. A
    // failed explanation was never cached - `_explanation` stays null
    // - and this is the same rule for the other half.
    if (mine() && this._explanation && !undoFailed) {
      this._detailCache.set(revision, {
        explanation: this._explanation,
        undo: this._undo,
      });
      // Oldest out. A Map hands its keys back in insertion order, so
      // the first one is the row opened longest ago.
      while (this._detailCache.size > DETAILS_KEPT) {
        this._detailCache.delete(this._detailCache.keys().next().value);
      }
    }
  }

  _detailCalls(change) {
    const explain = this._call("explain", {
      dashboard: this._selected,
      revision: change.revision,
    });
    // Asked only where the answer has somewhere to go. `_renderDetail`
    // returns before the undo section when a change has no predecessor
    // - "the first recorded state, so there is nothing before it to
    // compare against" - and `_replaceCandidates`, the only other reader
    // of `_undo`, is reached from below that return. So the oldest change
    // of a dashboard used to have its undo computed and thrown away:
    // measured at 1.2-1.5 s on a 28-view dashboard, which is the cost
    // this row was split into two phases to avoid in the first place.
    // `preview` deliberately left out - it defaults to false server-side.
    // This row never shows a diff for its own sake; `_undo` here is read
    // for `available`, `reason` and `equals_state_before` alone. Asking
    // for the preview too would dump the dashboard twice on every row
    // opened, for a dialog that opens on a click `_undoChange` sends
    // separately - measured on 2026-09-12 at 613 ms against roughly
    // 120 ms without it, on a dashboard the size of "Standard".
    const undo = change.previous
      ? this._call("undo_change", {
        dashboard: this._selected,
        revision: change.revision,
      })
      : Promise.resolve(null);
    return [explain, undo];
  }

  /** The two answers a row's detail is built from. */
  _detailFor(change) {
    return Promise.all(this._detailCalls(change));
  }

  /**
   * Forget the open row's answers.
   *
   * `_open` itself stays with the caller: opening a row puts a revision
   * there, the two flows that lose a row clear it. What all three share
   * is the three fields below, and all three named them by hand - so a
   * fourth answer would have had to be remembered in three places, and
   * would have been added to two.
   */
  _clearDetail() {
    this._explanation = null;
    this._undo = null;
    this._loadingDetail = null;
    this._loadingUndo = null;
    this._diffOpen = false;
  }

  _take(answers) {
    const [explanation, undo] = answers || [null, null];
    this._explanation = explanation;
    this._undo = undo || null;
  }

  /**
   * Show the preview, and write only if the person says so.
   *
   * `request` is called twice - once to build the preview, once to
   * write - and gets the dashboard handed to it both times rather than
   * reading `this._selected` itself. That is not tidiness. Between the
   * two calls the sidebar is fully live: the dialog appears only once
   * the preview is back, nothing announces that one is coming, and the
   * only sign of anything happening is a small "working..." in the bar.
   * Measured on 2026-09-05: preview a restore on one dashboard, click
   * another in the sidebar, press Apply - and the write went to the
   * second dashboard carrying the first one's revision. A state written
   * with nobody having seen its diff, which is the one rule this panel
   * exists to keep.
   */
  async _confirm(
    title,
    request,
    wantsKeep = false,
    { intro = "", applyLabel = "Apply" } = {},
  ) {
    const asked = this._selected;
    // Claimed as well, so the dialog does not open at all when the
    // selection moved while the preview was out: a diff for a dashboard
    // nobody is looking at any more is an invitation to write the wrong
    // thing, and it carries the wrong title too. Its own slot - a
    // search or an older page must not invalidate a preview, and
    // `_select` must.
    //
    // Only up to the dialog. Once it is open the selection cannot move
    // any more (a modal dialog makes the rest of the page inert, and
    // `_onRecorded` steps aside while one is open), and after Apply the
    // write must go through: dropping it there would leave somebody who
    // pressed a button with nothing happening and nothing said.
    const mine = this._claim("write");
    const preview = await this._guard(
      () => this._call(...request(false, null, asked)),
      mine,
    );
    if (!mine() || !preview) return;
    if (preview.error) {
      this._showError(preview.error);
      return;
    }
    // The undo re-proves itself on every call, so a preview can come
    // back as a refusal - somebody saved between the row being drawn and
    // the button being pressed, which is exactly the case decision 15
    // asks it to catch. Without this the dialog opened on an empty diff
    // with a live Apply, and the sentence that names the reason and the
    // card was thrown away by the one screen that exists to show it.
    if (preview.available === false) {
      this._showError(preview.reason || "this cannot be taken back exactly");
      return;
    }
    const dialog = this.shadowRoot.querySelector("dialog.confirm");
    dialog.querySelector("h2").textContent = title;
    // The integration answers "already identical" when the target state is
    // what the dashboard holds already. Showing an empty diff as "No
    // difference." next to a live Apply button was the panel throwing that
    // answer away and offering a change that changes nothing.
    const nothingToDo = !preview.preview && preview.note;
    // The versions that hold what the dashboard holds right now, as the
    // short names a sentence uses. Where there is one, the state being
    // replaced is not going anywhere: it stands in the list of versions
    // under a name, which is the only list the simple mode shows. So the
    // offer below has nothing left to protect, and taking it up produced
    // exactly what it was meant to prevent - going back and forth twice
    // on the test rig left two dated versions byte-identical to two
    // older ones (2026-09-08). The same rule `milestones.py` follows
    // before it makes a day mark, one module further out.
    //
    // From `history` and worked out there against every version of this
    // dashboard, so a version below the loaded window counts too. As
    // fresh as the badge the panel already draws from it, and stale in
    // one window only: between that answer and this dialog. A save made
    // there does announce itself, but the announcement is set aside
    // while a dialog stands - and the cost of being wrong is small,
    // because `_keep_the_live_state` records the state either way. It
    // would only lack a name. (An edit straight to `.storage` is *not*
    // that window: Home Assistant reads that file once and serves its
    // dashboards from memory afterwards, so it has not seen the change
    // either. See the README on when a change is recorded.)
    //
    // Only where a whole state is replaced, which is where the box is.
    // "Put back" and "Undo" keep the live state rather than replacing
    // it, and a sentence about versions in front of them would be an
    // answer to a question nobody asked.
    const covered = wantsKeep ? this._versionsMatchingNow() : [];
    // The paragraph that says what happens to the state being replaced,
    // and the tick box that offers to name it: two answers to one
    // question, so they are worked out together rather than twenty
    // lines apart. Both read `covered` and `creates_dashboard`, and a
    // rule that changed in one place only would leave a box whose
    // paragraph contradicts it.
    //
    // The question the paragraph answers came from a person who had to
    // read the source to find it out: does setting a state back throw
    // the present one away? It does not, and nothing here said so.
    // Nothing in this integration rewrites history except `forget`; a
    // restore writes the live dashboard, and the recorder appends an
    // entry for what was there.
    //
    // Where a version already holds that state, the same paragraph says
    // so instead - the more precise form of the same reassurance, and
    // what explains the missing tick box: an offer that disappears
    // without a word reads as a fault in the tool. Cut at three names
    // like every other list of them, with the full set in the tooltip.
    //
    // Left out entirely when the dashboard is being recreated: there is
    // no present state to keep, and the note beside the buttons already
    // says what happens instead.
    // Plain text, not markup: it goes into the footnote strip below the
    // body through `textContent`, which escapes for us. The strip is the
    // design's own place for a line that reads the same in every dialog
    // - said quietly, once, rather than boxed like news.
    const keeps = preview.creates_dashboard
      ? ""
      : covered.length
        ? `Nothing is lost — the state you leave is already saved as ${someNames(covered)}.`
        : "Nothing is lost — the state you leave stays in the history as its own entry.";
    // Offered only where a whole state is replaced and there is one to
    // keep. Not while a dashboard is being recreated - the answer for
    // that case is an error, and a tick box whose only possible outcome
    // is a failure is worse than none. Not where nothing is applied
    // either. And not where a version already holds the state: there is
    // nothing to lose, so a mark made here would be a second dated name
    // for content that has one.
    const keepable = Boolean(
      wantsKeep && !nothingToDo && !preview.creates_dashboard && !covered.length,
    );
    // The one sentence of consequence first, the itemised account after
    // it: the dialog's opening line answers "what am I about to do", and
    // reading it under a bullet list of cards puts the answer after the
    // detail it summarises. The design's fixed order, and the reason it
    // is fixed.
    dialog.querySelector(".body").innerHTML = nothingToDo
      ? `<p>This state is what the dashboard holds right now, so there is
           nothing to apply.</p>`
      : (intro ? `<p class="lead">${escape(intro)}</p>` : "") +
      renderPlain(preview.explanation, "What applying this does") +
      `<details class="raw">
         <summary><span class="glyph">&lt;/&gt;</span> Technical details</summary>
         ${renderDiff(preview.preview)}
       </details>`;
    this._sayFootnote(dialog, nothingToDo ? "" : keeps, covered);

    const applyButton = dialog.querySelector('.actions button[value="apply"]');
    applyButton.hidden = Boolean(nothingToDo);
    // Named after what it does, never "Apply": a button that says the
    // action back to you is the last place somebody can notice they are
    // in the wrong dialog.
    applyButton.textContent = applyLabel;
    dialog.querySelector('.actions button[value="cancel"]').textContent =
      nothingToDo ? "Close" : "Cancel";
    const note = preview.creates_dashboard
      ? "This recreates the dashboard, with its old title and icon."
      : "";
    dialog.querySelector(".note").textContent = note;
    const keepBlock = this._armKeep(keepable, dialog);
    dialog.returnValue = "";
    dialog.showModal();
    const answer = await this._answerFrom(dialog);
    if (answer !== "apply") return;
    const keep = keepable ? this._keepChoice(keepBlock) : null;
    // Armed before the write: the recorder is quick, and an announcement
    // that arrives first would find nobody waiting.
    const recorded = this._recorded();
    const applied = await this._guard(async () => {
      const result = await this._call(...request(true, keep, asked));
      // Still busy until the recorder has it. Reloading in between reads
      // a history whose newest entry is the state just replaced - so
      // nothing matches the live configuration, nothing is crowned, and
      // the page looks half-built. Measured at 30 to 150 ms of exactly
      // that.
      await recorded;
      return result;
    }, mine);
    // `kept_as_version.error` repeats `note` word for word where the
    // live state could not be recorded - operations hands the one into
    // the other - so it is only worth saying where it says something
    // else.
    //
    // The order below does that work, not this test: `note` sits ahead
    // of `keptFailed`, so wherever there is a note at all it is the note
    // that gets said. Removing this condition changes no outcome
    // (measured). It stays as the statement of intent, and the ordering
    // is what a later edit must not break: put `keptFailed` first and a
    // note about something else disappears behind it.
    const failed = applied?.kept_as_version?.error;
    const keptFailed =
      failed && failed !== applied?.note
        ? `the dashboard went back, but no version was made: ${failed}`
        : "";
    // A write that threw left its message in the banner, and the
    // reload below clears the banner on its way in. Taken here and put
    // back with the rest, or the one failure nobody could see coming is
    // the one that says nothing.
    const threw = applied === null ? this._error : "";
    const said =
      applied?.error ||
      // And a refusal on the confirming call as well, which is the one
      // that matters: the undo re-proves itself there, so this is the
      // answer somebody gets instead of a write.
      (applied?.available === false
        ? applied.reason || "this cannot be taken back exactly"
        : "") ||
      applied?.note ||
      keptFailed ||
      threw ||
      "";
    // Reloaded rather than reselected: a restore reached from a search
    // result used to end on the unfiltered first page. This reads the
    // dashboard list too, so a recreated dashboard still turns up in
    // the sidebar.
    const stale = await this._reloadAfterWrite("the change was made");
    // After the reload, not before it. The reload clears the banner on
    // its way in - so anything written here first is wiped by the very
    // refresh that follows it, which is what happened to every note
    // this dialog has ever tried to leave. Cleared where there is
    // nothing to say, for the same reason it always was: the banner
    // above belongs to the action that has just finished.
    //
    // Both halves, and `said` first. A reload that failed used to be
    // swallowed and then wiped by this very line: the write went
    // through, the page went on showing the state from before it, and
    // the only thing that could have said so was cleared here. What
    // the write itself answered is still the more important half; the
    // second sentence explains why the page below has not caught up.
    //
    // Through `_sayAbout` and not straight into the field, so the
    // sentence lands on the dashboard it is about: everything from
    // Apply to here runs with a live sidebar, and the write is pinned
    // to `asked` while the message was not.
    this._sayAbout(asked, [said, stale].filter(Boolean).join("; "));
  }

  /**
   * Fill in a Replace overlay's body for whichever candidate is
   * currently selected, and (re)arm its keep-as-version block for that
   * candidate specifically - "before" and "after" can each disagree on
   * whether a version already covers the live state, so switching the
   * radio must redo this, not just swap the visible diff.
   *
   * No network call in here: `previews` was fetched once, in full, by
   * `_openReplace`, before this dialog was ever shown.
   */
  _paintReplace(dialog, candidates, previews, selectedIndex) {
    const preview = previews[selectedIndex];
    const nothingToDo = !preview.preview && preview.note;
    const covered = this._versionsMatchingNow();
    // Plain text, not markup: it goes into the footnote strip below the
    // body through `textContent`, which escapes for us. The strip is the
    // design's own place for a line that reads the same in every dialog
    // - said quietly, once, rather than boxed like news.
    const keeps = preview.creates_dashboard
      ? ""
      : covered.length
        ? `Nothing is lost — the state you leave is already saved as ${someNames(covered)}.`
        : "Nothing is lost — the state you leave stays in the history as its own entry.";
    const keepable = Boolean(!nothingToDo && !preview.creates_dashboard && !covered.length);
    dialog.querySelector(".body").innerHTML = nothingToDo
      ? `<p>This state is what the dashboard holds right now, so there is
           nothing to apply.</p>`
      : `<details class="raw">
           <summary><span class="glyph">&lt;/&gt;</span> Technical details</summary>
           ${renderDiff(preview.preview)}
         </details>`;
    this._sayFootnote(dialog, nothingToDo ? "" : keeps, covered);
    const applyButton = dialog.querySelector('.actions button[value="apply"]');
    applyButton.hidden = Boolean(nothingToDo);
    dialog.querySelector('.actions button[value="cancel"]').textContent =
      nothingToDo ? "Close" : "Cancel";
    const note = preview.creates_dashboard
      ? "This recreates the dashboard, with its old title and icon."
      : "";
    dialog.querySelector(".note").textContent = note;
    return { keepable, keepBlock: this._armKeep(keepable, dialog) };
  }

  /**
   * "Replace the whole dashboard", combined: fetches every candidate
   * target state's preview at once (there is at most one "before" and
   * one "after"), so picking between them in the overlay costs no
   * second round trip - see the plan's global constraints for why this
   * is safe (restore_state's preview path is read-only).
   */
  async _openReplace(revision) {
    const change = this._changeAt(revision);
    if (!change) return;
    const { candidates } = this._replaceCandidates(change);
    if (!candidates.length) return;
    const asked = this._selected;
    const mine = this._claim("write");
    const previews = await this._guard(
      () =>
        Promise.all(
          candidates.map((c) =>
            this._call("restore_state", {
              dashboard: asked,
              revision: c.revision,
              confirm: false,
            }),
          ),
        ),
      mine,
    );
    if (!mine() || !previews) return;
    const failed = previews.find((p) => p.error);
    if (failed) {
      this._showError(failed.error);
      return;
    }
    const refused = previews.find((p) => p.available === false);
    if (refused) {
      this._showError(refused.reason || "this cannot be replaced exactly");
      return;
    }

    const dialog = this.shadowRoot.querySelector("dialog.replace");
    const choice = dialog.querySelector("[data-replace-choice]");
    let selected = 0;
    let keepable = false;
    let keepBlock = null;

    const paint = () => {
      ({ keepable, keepBlock } = this._paintReplace(dialog, candidates, previews, selected));
    };

    choice.innerHTML =
      candidates.length > 1
        ? candidates
            .map(
              (c, index) => `<label class="replace-option">
                 <input type="radio" name="replace-target" value="${index}"
                        ${index === 0 ? "checked" : ""}>
                 <span>${escape(c.label)}</span>
                 ${c.timestamp
                   ? `<span class="when">${escape(when(c.timestamp))}</span>`
                   : ""}
               </label>`,
            )
            .join("")
        : "";
    if (candidates.length > 1) {
      choice.querySelectorAll('input[name="replace-target"]').forEach((radio) => {
        radio.addEventListener("change", (event) => {
          selected = Number(event.target.value);
          paint();
        });
      });
    }
    paint();

    dialog.returnValue = "";
    dialog.showModal();
    const answer = await this._answerFrom(dialog);
    if (answer !== "apply") return;
    const target = candidates[selected];
    const keep = keepable ? this._keepChoice(keepBlock) : null;
    const recorded = this._recorded();
    const applied = await this._guard(async () => {
      const result = await this._call("restore_state", {
        dashboard: asked,
        revision: target.revision,
        confirm: true,
        ...(keep ? { keep_as_version: keep } : {}),
      });
      await recorded;
      return result;
    }, mine);
    const failedKeep = applied?.kept_as_version?.error;
    const keptFailed =
      failedKeep && failedKeep !== applied?.note
        ? `the dashboard went back, but no version was made: ${failedKeep}`
        : "";
    const threw = applied === null ? this._error : "";
    const said =
      applied?.error ||
      (applied?.available === false
        ? applied.reason || "this cannot be replaced exactly"
        : "") ||
      applied?.note ||
      keptFailed ||
      threw ||
      "";
    const stale = await this._reloadAfterWrite("the dashboard was replaced");
    this._sayAbout(asked, [said, stale].filter(Boolean).join("; "));
  }

  /**
   * Wait for a dialog's answer, and pay back a render held while it
   * stood.
   *
   * `_render` replaces the whole shadow root, an open <dialog>
   * included - and a <dialog> taken out of the document fires no
   * `close`. The promise below would then never settle: the
   * confirmation disappears from the screen in the middle of somebody
   * deciding, nothing is written, and nothing says why. `_onRecorded`
   * has stepped around that since it was found there; a page of older
   * changes and an answer from the whole-history search reach the same
   * place and did not. So `_render` now steps aside too, and this is
   * where the render it owes is run.
   *
   * Run before the answer is handed on rather than after, which is safe
   * for one reason worth keeping: every caller reads what it still
   * needs from the dialog - the tick box, the typed title - through an
   * element reference taken before the dialog opened, and a reference
   * survives the shadow root being replaced. A caller that looked its
   * fields up again here would read fresh, empty ones.
   */
  _answerFrom(dialog) {
    return new Promise((resolve) => {
      dialog.addEventListener(
        "close",
        () => {
          const answer = dialog.returnValue;
          if (this._renderOwed) this._render();
          resolve(answer);
        },
        { once: true },
      );
    });
  }

  /**
   * Show the block that offers to keep the state being replaced, or
   * hide it again. Answers with the block, for `_keepChoice`.
   *
   * Its own method, and so is `_keepChoice`, for one reason: these two
   * are the only lines of this flow that touch an element. Everything
   * else about it - which call goes first, what rides on the confirming
   * one, whether anything is written at all - is logic, and logic
   * belongs where tests/test_panel_behaviour.py reaches it.
   *
   * Ticked in the simple mode, clear in the advanced one. Somebody in
   * the simple mode sees nothing but versions, so an unmarked state is
   * gone as far as they are concerned; somebody in the advanced mode
   * sees everything anyway and would otherwise collect a mark for every
   * experiment.
   */
  /**
   * The quiet line between a dialog's body and its buttons, or nothing.
   *
   * Its own strip rather than a box inside the body, because it says the
   * same thing in every dialog every time: boxed and tinted it reads as
   * news, and a reader who has seen it twice stops reading the body with
   * it. `textContent` and not markup - the sentence carries version
   * names that came back from the server.
   *
   * `covered` only for the tooltip: the sentence names at most three
   * versions, the title holds the full list, exactly as the paragraph it
   * replaces did.
   */
  _sayFootnote(dialog, text, covered = []) {
    const strip = dialog.querySelector("[data-footnote]");
    if (!strip) return;
    strip.hidden = !text;
    if (!text) return;
    strip.querySelector("[data-footnote-text]").textContent = text;
    if (covered.length) strip.title = joinNames(covered);
    else strip.removeAttribute("title");
  }

  _armKeep(show, dialog) {
    const keep = dialog.querySelector("[data-keep]");
    if (!keep) return null;
    keep.hidden = !show;
    if (!show) return null;
    const isChecked = this._mode === "simple";
    const box = keep.querySelector(".keepbox");
    if (box) box.checked = isChecked;
    const fields = keep.querySelector(".keepfields");
    if (fields) fields.hidden = !isChecked;
    const titleField = keep.querySelector(".keeptitle");
    if (titleField) titleField.value = this._dayTitle();
    return keep;
  }

  /**
   * Today, spelled the way this installation spells it.
   *
   * The string rides in with `history`, worked out on the machine Home
   * Assistant runs on and through the same function the automatic daily
   * versions use. Computed here it is the *browser's* today: near
   * midnight, from a laptop in another time zone, that is a different
   * day from the one this installation would have written, and two
   * names for one day in a list that shows nothing but names is exactly
   * the confusion the simple mode cannot survive.
   *
   * `today()` stays as the fallback, for an answer that does not carry
   * the field - an older integration behind a newer panel, or a history
   * call that failed. It is what this always did, and a date from the
   * wrong side of midnight still beats an empty title.
   */
  _dayTitle() {
    return this._serverToday || today();
  }

  /**
   * The version to make, or null for none.
   *
   * Patch, and never a level somebody has to choose: this is a
   * waypoint, not a milestone, and a three-way choice in front of a
   * restore is a question nobody came here to answer.
   *
   * The block is handed in rather than looked up again. By the time
   * this runs the dialog has closed, and closing it is where
   * `_answerFrom` pays back a render that was held while the dialog
   * stood - so a fresh lookup finds a new, empty tick box and quietly
   * drops the version somebody asked for.
   */
  _keepChoice(keep) {
    const box = keep?.querySelector(".keepbox");
    if (!box?.checked) return null;
    const title = keep.querySelector(".keeptitle").value.trim();
    return { level: "patch", title: title || this._dayTitle() };
  }

  async _loadDashboardsQuietly() {
    try {
      const result = await this._call("dashboards");
      this._dashboards = result.dashboards || [];
      this._render();
    } catch {
      /* the list is a convenience; a failure here changes nothing */
    }
  }

  /**
   * One field, prefilled, Save or Cancel. Nothing more is wanted here -
   * the same shape as Home Assistant's own "rename" on an integration.
   */
  async _describe(revision) {
    const change = this._changeAt(revision);
    if (!change) return;
    // A description is written by revision rather than by dashboard, so
    // nothing here can go to the wrong one - but the sentence about it
    // can still land over a history somebody switched to while the note
    // was being saved and the page reloaded. Same window, same answer.
    const asked = this._selected;
    const dialog = this.shadowRoot.querySelector("dialog.describe");
    const field = dialog.querySelector("input.text");
    field.value = change.description || "";
    dialog.returnValue = "";
    dialog.showModal();
    field.focus();
    field.select();
    const answer = await this._answerFrom(dialog);
    if (answer !== "save") return;
    const result = await this._guard(
      () =>
        this._call("describe", { revision: change.revision, text: field.value }),
      () => this._selected === asked,
    );
    if (result?.error) {
      this._sayAbout(asked, result.error);
      return;
    }
    // Not `_select`: a description written on a row the server found is
    // the one place where losing the search costs the most - the next
    // hit would have to be searched for again.
    //
    // And not `_refreshQuietly` either: the description is stored, but
    // the row on the screen still shows the old one, and a page that is
    // wrong without saying so is worse than a banner.
    const stale = await this._reloadAfterWrite("the description was saved");
    if (stale) this._sayAbout(asked, stale);
  }

  /**
   * The create dialog's two fields, opened again on a version that
   * exists. Same two fields, same wording, no third.
   *
   * The number is not among them, and that is decision 13 of the design
   * record rather than an oversight: the number *is* the tag's name,
   * going back to a version is `restore_state` with that name as the
   * revision, and an automation holding one would break without a word
   * the moment it moved. Whoever wants a different number puts a second
   * version beside this one - one click, and nothing is lost. The
   * reasoning is in `FAQ.md`, because it is the first question this
   * screen provokes.
   *
   * Read out of `_versions`, which is the complete list from the server
   * and is loaded in both modes. Never out of the marks hanging on a
   * loaded change: the advanced mode has those, the simple one is built
   * to work without them, and a version whose commit has slid out of
   * the window is exactly the one somebody scrolls down to rename.
   */
  async _retitleVersion(name) {
    const version = this._versions.find((v) => v.name === name);
    if (!version) return;
    // As in `_describe`: the write is addressed by a name that was
    // resolved before the dialog opened, so it cannot land on the wrong
    // dashboard - but the sentence about it can still arrive over a
    // history somebody switched to in the meantime.
    const asked = this._selected;
    const dialog = this.shadowRoot.querySelector("dialog.retitle");
    // Which one is being renamed, said in the dialog. Two rows of the
    // simple mode can carry the same title - that is what the numbers
    // are there for - so a dialog that only says "this version" leaves
    // somebody checking behind themselves.
    //
    // And that the badge survives, where there is one. It is the one
    // thing about the version this dialog changes nothing about while
    // visibly rewriting what sits next to it.
    dialog.querySelector("[data-which]").textContent =
      shortName(name) +
      (version.automatic ? " — it stays marked as saved automatically." : "");
    const title = dialog.querySelector("input.title");
    const description = dialog.querySelector("input.desc");
    title.value = version.title || "";
    description.value = version.description || "";
    dialog.returnValue = "";
    dialog.showModal();
    title.focus();
    title.select();
    const answer = await this._answerFrom(dialog);
    if (answer !== "save") return;
    const result = await this._guard(
      () =>
        this._call("retitle_version", {
          dashboard: asked,
          name,
          // Sent as typed, empty included. A version cannot be left
          // without a title, and the refusal for it lives on the server
          // where the same fence serves the service call - the panel
          // repeating the rule here would be a second copy of it to
          // keep right, which is what this file is built to avoid.
          title: title.value.trim(),
          description: description.value.trim(),
        }),
      () => this._selected === asked,
    );
    if (result?.error) {
      this._sayAbout(asked, result.error);
      return;
    }
    const stale = await this._reloadAfterWrite("the version was renamed");
    if (stale) this._sayAbout(asked, stale);
  }

  /**
   * Taking a version's mark away: asked twice, like forgetting.
   *
   * Once by the button, once by a dialog carrying the words that are
   * about to go. Those words come from the server rather than from
   * `this._versions`, and that is the same choice `_forget` makes: what
   * the dialog says has to be what the store reads off the tag now, not
   * what a list loaded some time ago still remembers. `highest` is the
   * other half of it - whether the number comes free cannot be worked
   * out here, because the numbering lives in versions.py by decision 13.
   *
   * `asked` and `_claim` are held before the first await, and they do
   * two different jobs. `asked` addresses both calls, so neither can
   * land on a dashboard the dialog never mentioned - that is the reason
   * spelled out in `_confirm`. `mine` decides only whether this attempt
   * is still the current one: a click in the sidebar during the preview
   * makes it stale, and a stale preview must not open a dialog on top of
   * another history. The confirming call is guarded by `asked` instead,
   * exactly as in `_retitleVersion` - by then a dialog has been
   * answered, and the answer belongs to the version it named.
   */
  async _removeVersion(name) {
    const asked = this._selected;
    const mine = this._claim("write");
    const facts = await this._guard(
      () => this._call("remove_version", { dashboard: asked, name }),
      mine,
    );
    if (!mine() || !facts) return;
    if (facts.error) {
      this._sayAbout(asked, facts.error);
      return;
    }
    const dialog = this.shadowRoot.querySelector("dialog.remove");
    // The version names itself first, then one note carrying a list a
    // person can scan. Prose was tried and read worse: three paragraphs
    // of consequence, each having to re-establish what it was about
    // before it could say anything. A labelled list says the subject in
    // two words and the consequence in one sentence, and the reader can
    // stop after the labels.
    //
    // Two things always appear - the identity line and the first bullet
    // - and the rest only where they apply. A hand-made lightweight tag
    // carries neither title nor description, so the head is the number
    // alone and the lead names only the tag: this dialog must not claim
    // a loss that is not real for the very version `bin()` exists to
    // extend the offer to.
    //
    // The freed number is spelled out rather than described. "That
    // number is free again" made a reader look up which number that
    // was, on the row they had just left; `v1.0.3` is the thing they
    // act on. It is only ever shown where the server said `highest`,
    // because only there is it true - the numbering lives in
    // versions.py by decision 13 and is never worked out here.
    //
    // The description itself is shown rather than summarised: it is the
    // one string here the integration cannot write back, and a
    // confirmation the FAQ calls "there to be read rather than clicked
    // through" cannot hide half of what it is about. It sits with the
    // number and the title, not further down: it says what this version
    // *is*, and put between the note and its list - where it was first
    // written - it cut that sentence off from its own bullets.
    //
    // The re-tagging bullet hangs on `returns`, not on `automatic`, and
    // the difference is a real one somebody found on the screen: every
    // automatic version used to be told it would be re-created at the
    // next save, and for a mark about 7 September with states from the
    // 8th behind it that is simply false - it never comes back. Only
    // the server can tell the two apart, because the answer is a
    // calendar question over the dashboard's own states; the panel
    // works out neither that nor the numbering (decision 13).
    const number = escape(shortName(name));
    const head = facts.title ? `${number} — ${escape(facts.title)}` : number;
    // Named in the lead, not in a bullet: it is what the sentence is
    // about, and "only" is doing the reassuring work in front of it.
    //
    // Built as a list and handed to `joinNames`, which is this
    // codebase's own way of writing one - no separator for one item,
    // "a and b" for two, "a, b and c" for three, no Oxford comma. It
    // was a four-branch ternary first, and that spelled out by hand
    // exactly what the helper two screens up already does: change the
    // convention there and a hand-rolled chain keeps the old one
    // silently, because nobody greps for an if/else.
    const goes = ["the tag"];
    if (facts.title) goes.push("its title");
    if (facts.description) goes.push("its description");
    const alsoGoes = goes.length > 1 ? ", which cannot be written back" : "";
    dialog.querySelector(".body").innerHTML = `
      <p class="who"><strong>${head}</strong>${facts.description
        ? `<span class="why"><strong>Description:</strong> ${
             escape(facts.description)}</span>`
        : ""
      }</p>
      <p><strong>Note:</strong><br>
         Removing this version only deletes ${joinNames(goes)}${alsoGoes}:</p>
      <ul class="loss">
        <li><strong>History is preserved:</strong> The underlying state
            remains accessible in the advanced view.</li>
        ${facts.highest
          ? `<li><strong>Version number freed:</strong> The next patch
               will reuse <strong>${number}</strong>.</li>`
          : ""
        }
        ${facts.returns
          ? `<li><strong>Automatic re-tagging:</strong> Because this
               version was generated automatically, saving will create it
               again. You can disable this behavior globally in the
               integration settings.</li>`
          : ""
        }
      </ul>`;
    dialog.returnValue = "";
    dialog.showModal();
    const answer = await this._answerFrom(dialog);
    if (answer !== "remove") return;
    const done = await this._guard(
      () => this._call("remove_version", { dashboard: asked, name, confirm: true }),
      () => this._selected === asked,
    );
    if (done?.error) {
      this._sayAbout(asked, done.error);
      return;
    }
    // Taken out of the set of open sections on the way, or a name that
    // no longer exists would sit in it for the life of the page. Harmless
    // today and the kind of thing that stops being harmless the moment a
    // number is handed out a second time - which is exactly what this
    // operation makes possible.
    this._verOpen.delete(name);
    const stale = await this._reloadAfterWrite("the version was removed");
    if (stale) this._sayAbout(asked, stale);
  }

  /**
   * Three buttons carrying the finished numbers, patch preselected.
   *
   * The number is never typed. A tag name has ref rules - no spaces, no
   * `..`, no `~^:?*[` - and passing those rules through to a dialog would
   * be carrying the storage into the interface. Choosing between patch,
   * minor and major carries a statement instead: was this a correction or
   * a rebuild?
   */
  async _createVersion(revision) {
    const change = this._changeAt(revision);
    if (!change) return;
    // Fetched before the dialog is touched: _guard re-renders, and a
    // re-render replaces the dialog element along with everything else.
    //
    // The dashboard is held across it, and the slot claimed, exactly as
    // in `_confirm`: the numbers on the three buttons are worked out for
    // one dashboard, and the version used to be written into whichever
    // one was selected by the time somebody pressed Create.
    const asked = this._selected;
    const mine = this._claim("write");
    const offered = await this._guard(
      () => this._call("next_versions", { dashboard: asked }),
      mine,
    );
    if (!mine() || !offered) return;
    const candidates = offered.candidates || {};
    const dialog = this.shadowRoot.querySelector("dialog.version");
    dialog.querySelector("[data-scope]").textContent = candidates.current
      ? `Everything from ${candidates.current} up to and including this change.`
      : "Everything up to and including this change.";
    // Said before the choice, not after it. Two routes get you here: the
    // state carries a version already, or - the one that prompted this -
    // it holds exactly what a version holds because going back to that
    // version wrote a fresh entry. Neither is refused. Two versions on
    // one state is allowed, and after a revert a second name can be
    // precisely what somebody wants; the point is that it is a decision
    // rather than a surprise.
    //
    // The content case is only offered for the state the dashboard is
    // in. `same_as_now` compares each entry against the live
    // configuration, so it can answer "is this entry what a version
    // holds" only where "this entry" is the current one. Claiming it
    // anywhere else would need a comparison the panel does not have.
    const already = this._alreadyNamed(change);
    const carries = dialog.querySelector("[data-carries]");
    // Bold, and not because emphasis is decoration. This sentence was
    // plain text under a muted line and got read straight past - the one
    // person it was written for said so. The half that carries the news
    // is the half that gets the weight; the consequence reads normally
    // after it.
    carries.innerHTML = already
      ? `<strong>${escape(already)}</strong> A new version here would be a
         second name for the same content.`
      : "";
    carries.hidden = !already;
    let level = "patch";
    const buttons = [...dialog.querySelectorAll(".levels button")];
    buttons.forEach((button) => {
      const which = button.dataset.level;
      button.querySelector("strong").textContent = shortName(
        candidates[which] || "",
      );
      button.setAttribute("aria-pressed", String(which === level));
    });
    // One listener on the group rather than three on the buttons. Not
    // because they would pile up - _guard re-renders before this line, so
    // the dialog is a fresh element every time - but because relying on
    // that is relying on a re-render two calls away. This holds either way.
    dialog.querySelector(".levels").addEventListener("click", (event) => {
      const button = event.target.closest("button[data-level]");
      if (!button) return;
      level = button.dataset.level;
      buttons.forEach((other) =>
        other.setAttribute(
          "aria-pressed",
          String(other.dataset.level === level),
        ),
      );
    });
    const title = dialog.querySelector("input.title");
    const description = dialog.querySelector("input.desc");
    title.value = "";
    description.value = "";
    dialog.returnValue = "";
    dialog.showModal();
    title.focus();
    const answer = await this._answerFrom(dialog);
    if (answer !== "create") return;
    const result = await this._guard(
      () =>
        this._call("create_version", {
          dashboard: asked,
          level,
          // `|| ""` like everywhere else in this file: `shortName`
          // splits the string it is given, so a level the server left
          // out threw here and took the whole flow with it, after the
          // dialog had been filled in. An empty title is something the
          // server already accepts; a TypeError in a click handler is
          // not.
          title: title.value.trim() || shortName(candidates[level] || ""),
          description: description.value.trim(),
          revision: change.revision,
        }),
      // As in `_confirm`: the dialog stood in front of the write, and
      // the moment it closes the sidebar is live again. A failure of
      // this write is news about `asked` and about nothing else.
      mine,
    );
    if (result?.error) {
      this._sayAbout(asked, result.error);
      return;
    }
    // Remembered before the reload, or the history folds up the moment it
    // is made. Once a version sits on the top row, section 0 is a version
    // section rather than the "Current state" one, and _verOpen - which
    // decides whether a <details class="ver"> renders open - has never
    // heard of a name created a line ago. The whole visible history would
    // shrink to a single collapsed line, right after the one click the
    // design record advertises.
    if (result?.created) this._verOpen.add(result.created);
    // Said rather than swallowed, as in `_confirm`: the version exists
    // on the server, and a history that does not show it invites
    // somebody to make it a second time.
    const stale = await this._reloadAfterWrite("the version was made");
    if (stale) this._sayAbout(asked, stale);
  }

  /**
   * Irreversible, so it is asked twice: once by the button, once by a
   * dialog that counts what is about to be lost. No diff - a diff of
   * this would be the whole history.
   *
   * No superlative here on purpose. What is unique about `forget` - it
   * is the one operation that rewrites the stored history - is said
   * where a reader needs it to decide whether to trust the tool, in
   * the README and in `store.forget`. Repeated at every site that
   * merely *consequences* from it, a claim about the whole set of
   * operations has to be hunted down and reworded every time the set
   * changes; this branch spent five commits doing exactly that.
   */
  async _forget() {
    // Held and claimed before the first await, for the reason spelled
    // out in `_confirm` - and here it is the expensive one. The dialog
    // names a dashboard and counts what is about to be lost; the
    // confirming call read `this._selected` again, so a click in the
    // sidebar while those counts were being fetched threw away the
    // whole history of a dashboard the dialog never mentioned, under a
    // sentence saying in bold that it cannot be undone.
    const asked = this._selected;
    const mine = this._claim("write");
    const dashboard = this._dashboards.find((d) => d.key === asked);
    const facts = await this._guard(
      () => this._call("forget", { dashboard: asked }),
      mine,
    );
    if (!mine() || !facts) return;
    if (facts.error) {
      this._showError(facts.error);
      return;
    }
    const dialog = this.shadowRoot.querySelector("dialog.forget");
    const span =
      facts.first && facts.last
        ? `, from ${escape(when(facts.first))} to ${escape(when(facts.last))}`
        : "";
    dialog.querySelector(".body").innerHTML = `
      <p>This throws away the recorded history of
         <strong>${escape(dashboard?.title || asked)}</strong>.</p>
      <ul class="loss">
        <li>${escape(facts.states)} recorded state${facts.states === 1 ? "" : "s"}${span}</li>
        ${facts.described
        ? `<li>${escape(facts.described)} of them carry a description you wrote</li>`
        : ""
      }
      </ul>
      <p>The dashboard itself is already gone; this removes the record of
         what was on it. <strong>It cannot be undone.</strong></p>
      <p class="muted" style="font-size:13px">One side effect worth knowing:
         the stored history is rewritten, so every revision changes. A
         revision you noted down somewhere will no longer resolve.</p>`;
    dialog.returnValue = "";
    dialog.showModal();
    const answer = await this._answerFrom(dialog);
    if (answer !== "forget") return;
    // Up before the call, down only after the reload below: the rewrite
    // is not the whole wait. Measured 2026-09-18, the first question
    // asked afterwards costs a full index rebuild - 25 s in the
    // container - so releasing the page when `forget` answers would hand
    // back an interface that hangs for another half minute.
    this._forgetting = {
      key: asked,
      title: dashboard?.title || asked,
      phase: "rewriting",
      done: 0,
      total: 0,
      heard: Date.now(),
    };
    this._render();
    try {
      const done = await this._guard(() =>
        this._call("forget", { dashboard: asked, confirm: true }),
      );
      // The same fence the preview above holds, and it was missing here:
      // this call outlives a click elsewhere, and without the check it
      // threw away `_selected` and the loaded history of whatever the
      // person had moved on to. The lock screen makes that click
      // impossible from now on; the fence stays because a fence enforced
      // only by a screen is not a fence.
      if (!mine()) return;
      if (done?.error) this._error = done.error;
      this._selected = null;
      // You just removed what you were looking at. _loadDashboards
      // below picks the first live dashboard again, and with one column
      // that would put you in some other dashboard's history without
      // having asked - a screen that looks right and is not. Covered by
      // _loadDashboards already; said here as well so it survives
      // somebody editing that.
      this._pane = "list";
      this._changes = [];
      // Still locked, and now saying something else: the rewrite is
      // done, but the index it dropped has to be walked again before
      // any answer can come back. The panel knows this phase by itself -
      // no event says it, because it happens inside the next question.
      this._forgetting.phase = "reloading";
      this._forgetting.heard = Date.now();
      this._render();
      await this._loadDashboards();
    } finally {
      // In a `finally` so a call that throws cannot leave somebody
      // locked out of their own panel with nothing but a reload.
      this._forgetting = null;
      this._render();
    }
  }

  _restoreItem(revision, item) {
    this._confirm(
      `Put back: ${item.label}`,
      (confirm, keep, dashboard) => [
        "restore_deleted",
        { dashboard, revision, position: item.position, confirm },
      ],
      false,
      { applyLabel: "Put back" },
    );
  }

  _restoreState(revision, title) {
    // Returned rather than dropped, unlike its two neighbours: the Node
    // scenario waits for it, and a flow whose end nobody can wait for
    // cannot be tested at all.
    return this._confirm(
      title,
      (confirm, keep, dashboard) => [
        "restore_state",
        {
          dashboard,
          revision,
          confirm,
          // Left out entirely when nothing is to be marked. An empty
          // object would be a request for a version with no name, which
          // the server would then have to refuse.
          ...(keep ? { keep_as_version: keep } : {}),
        },
      ],
      true,
      // The button that opened this dialog names the state it goes to
      // ("Bring it back", "Back to this version"); the one that carries
      // it out says the same thing back.
      { applyLabel: title },
    );
  }

  _undoChange(revision) {
    const change = this._changeAt(revision);
    const made = change ? this._madeSince(change) : null;
    const kept =
      made ? ` and keeps the ${made} change${made === 1 ? "" : "s"} made since` : "";
    this._confirm(
      "Undo this change",
      (confirm, keep, dashboard) => [
        "undo_change",
        // `preview` only on the call that shows one - the first, before
        // the write. The second call, with `confirm` true, already has
        // the diff this dialog is displaying; asking for it again would
        // pay for the same two dumps a second time for nothing shown.
        { dashboard, revision, confirm, preview: !confirm },
      ],
      false,
      {
        intro: `Puts this change back${kept}.`,
        applyLabel: "Undo this change",
      },
    );
  }

  _renderDashboard(d) {
    return `
        <button class="dash" data-key="${escape(d.key)}"
                aria-current="${d.key === this._selected}">
          <span>${escape(d.title)}${d.exists ? "" : '<span class="gone">deleted</span>'}</span>
          <span class="key">${escape(d.key)}</span>
        </button>`;
  }

  /**
   * One group of dashboards behind a fold, or nothing when it is empty.
   *
   * Counted and folded away, not hidden: what is in here still has to
   * be findable - a deleted dashboard is the one somebody opens this
   * tool for - but it stays findable forever, and that is the problem.
   * Delete a dashboard every few months and an unfolded list is mostly
   * gravestones.
   *
   * A fold whose dashboard is the one on screen opens itself, or the
   * page would show a history belonging to nothing visible.
   */
  _fold(kind, label, dashboards) {
    if (!dashboards.length) return "";
    const open =
      this._foldOpen[kind] || dashboards.some((d) => d.key === this._selected);
    return `<details class="fold ${kind}" data-fold="${kind}" ${open ? "open" : ""}>
         <summary>${label} (${dashboards.length})</summary>
         ${dashboards.map((d) => this._renderDashboard(d)).join("")}
       </details>`;
  }

  /**
   * The recorded dashboards grouped as the list on the left groups them
   * - the sidebar's own, then the ones outside it, then the gone ones -
   * and `listed`, those same three read as one list.
   *
   * Read by the renderer and by the opening choice, and that is why it
   * is here rather than inside `_renderSide`. This order used to exist
   * only for as long as the markup was being built, so the one place
   * that also needs it - `_loadDashboards`, choosing what to open on -
   * had nothing to read but the server's list, and the panel opened on
   * a dashboard nobody's eye starts at.
   *
   * When the browser can say nothing about the sidebar, the order the
   * server gave stands and nothing is set apart. That case is not
   * exotic: it is every render before the first answer arrives.
   */
  _orderedDashboards() {
    const live = this._dashboards.filter((d) => d.exists);
    const dead = this._dashboards.filter((d) => !d.exists);
    const view = this._sidebarView();
    const { sidebar, apart } = view
      ? splitBySidebar(live, view)
      : { sidebar: live, apart: [] };
    // Flattened here and nowhere else. A caller wanting the first row
    // would otherwise have to name the three groups in the order the
    // renderer happens to draw them, which is the coupling that opened
    // the panel on the wrong dashboard in the first place.
    return { sidebar, apart, dead, listed: [...sidebar, ...apart, ...dead] };
  }

  /**
   * The list on the left as markup.
   *
   * People know a dashboard by where it sits in the sidebar, so the
   * list they are handed here is that list - see `panel/sidebar.js` for
   * whose order it is and why the browser has to work it out.
   */
  _renderSide() {
    if (!this._dashboards.length)
      return '<p class="empty muted">Nothing recorded yet.</p>';
    const { sidebar, apart, dead } = this._orderedDashboards();
    return (
      sidebar.map((d) => this._renderDashboard(d)).join("") +
      this._fold("apart", "Not in the sidebar", apart) +
      this._fold("dead", "Deleted", dead)
    );
  }

  /**
   * Everything the split needs, or null when the browser cannot tell.
   *
   * `_sidebar` being null is not an error worth reporting: a user who
   * has never touched their sidebar has no such record, and the
   * fallbacks below are where Home Assistant itself looks next - the
   * two keys it wrote before this moved into user data. Somebody who
   * arranged their sidebar years ago is exactly the person who would
   * notice the arrangement missing.
   */
  _sidebarView() {
    const panels = this._hass?.panels;
    if (!panels) return null;
    return {
      panels,
      defaultPanel: defaultPanelPath(this._hass),
      language: this._hass.locale?.language,
      ...arrangementFrom(this._sidebar),
    };
  }

  /**
   * Read this user's sidebar arrangement, once per load.
   *
   * Failure costs the order and nothing else, so it is swallowed rather
   * than shown: a banner over a dashboard list because a sort key could
   * not be read would be louder than what it reports. Re-read by the
   * reload button, which is the answer for somebody who rearranged
   * their sidebar in another tab.
   */
  async _loadSidebar() {
    try {
      const answer = await this._hass.callWS({
        type: "frontend/get_user_data",
        key: "sidebar",
      });
      this._sidebar = answer?.value || null;
    } catch {
      this._sidebar = null;
    }
  }

  /**
   * The candidate target states "Replace the whole dashboard" can offer
   * for this change - "before" and/or "after" it - as pure data, plus
   * the one sentence there is to say when there is nothing to offer at
   * all. Kept as data rather than markup: the redesign shows both
   * candidates in one overlay with a radio choice, and the card itself
   * only needs to know whether the trigger button has anything to
   * open.
   *
   * The two conditions are unchanged from the buttons this replaces:
   * "before" is left out where it would write exactly what Undo
   * already writes (`equals_state_before`) or where the predecessor is
   * already known to be the live state; "after" is left out where this
   * very change already is the live state.
   */
  _replaceCandidates(change) {
    const before = change.previous;
    const same = this._undo?.available && this._undo.equals_state_before;
    const beforeIsNow = Boolean(before && this._changeAt(before)?.same_as_now);
    const candidates = [];
    if (before && !beforeIsNow && !same)
      candidates.push({
        revision: before,
        label: "State before this change",
        timestamp: this._changeAt(before)?.timestamp ?? null,
      });
    if (!change.same_as_now)
      candidates.push({
        revision: change.revision,
        label: "State after this change",
        timestamp: change.timestamp ?? null,
      });
    const why = beforeIsNow
      ? "The state before this change is what the dashboard holds now — nothing to set back."
      : "";
    return { candidates, why };
  }

  /**
   * The card's one action bar: Version up to here, Undo (only where
   * available), Replace the whole dashboard (only where there is a
   * candidate to replace it with) - in that order, matching the
   * redesign's "one action bar, not three stacked blocks".
   *
   * `offerReplace: false` is for the one caller with no `previous` at
   * all (the first recorded state): `_replaceCandidates` reading a null
   * `change.previous` would still offer "after" whenever this very
   * change is not the live state, which is new territory this plan
   * does not touch - the code it replaces never called `_renderSetBack`
   * for that branch either.
   */
  _renderActionBar(change, { offerReplace = true } = {}) {
    const undo = this._undo?.available ? this._undo : null;
    const { candidates, why } = offerReplace
      ? this._replaceCandidates(change)
      : { candidates: [], why: "" };
    const named = this._alreadyNamed(change);
    const versionButton = `<button class="act ghost" data-version="${escape(change.revision)}"
                >Version up to here</button>`;
    const undoButton = undo
      ? `<button class="act" data-undo="${escape(change.revision)}">Undo this change</button>`
      : "";
    const replaceButton = candidates.length
      ? `<button class="act replace-trigger" data-replace="${escape(change.revision)}"
                >&#x27F2; Replace the whole dashboard…</button>`
      : "";
    return `<div class="action-bar">
        ${versionButton}
        ${undoButton}
        ${replaceButton}
        ${named ? `<span class="named">${escape(named)}</span>` : ""}
      </div>
      ${why ? `<span class="why">${why}</span>` : ""}`;
  }

  _renderDetail(change) {
    if (this._loadingDetail === change.revision) {
      return `<div class="detail loading">
        <p class="muted row-loading"><span class="ring mini"></span> Loading change details…</p>
      </div>`;
    }
    // Where there is room, both subjects get a full sentence instead of a
    // chip - the explanation says what the change did, this says where it
    // left the dashboard. "again" carries the case the short form cannot:
    // the dashboard may well have changed away and come back since.
    // Not on the top row: the section heading and its chip already say it
    // there, and "again" would be wrong for the state you are simply in.
    const here =
      !this._isNewest(change) && change.same_as_now
        ? `<p class="why" style="margin-top:0">The dashboard holds exactly this
             state again right now.</p>`
        : "";
    const plain =
      here + renderPlain(this._explanation, "What this change did");
    const before = change.previous;
    if (!before)
      return `<div class="detail">${plain}<p class="muted">This is the first
        recorded state, so there is nothing before it to compare against.</p>
        ${this._renderActionBar(change, { offerReplace: false })}</div>`;
    const undo = this._undo?.available ? this._undo : null;
    // The compare bar itself already hides "current state" for a
    // dashboard Home Assistant does not currently have (`_renderMain`,
    // spec decision 19's edge case: put-back only ever writes into a
    // live state) - this jump ends up picking exactly that "current
    // state", so offering it here for the same dashboard would open a
    // door the compare bar was built to keep closed.
    const dashboard = this._dashboards.find((d) => d.key === this._selected);
    const compareFromOffer =
      dashboard?.exists === false
        ? ""
        : `<div class="backto">
               <button class="act ghost" data-compare-from="${escape(change.previous || "")}"
                       >Compare with the current state</button>
             </div>`;

    // Left out where the number is not known - a row from outside the
    // loaded window has no place in it to count from, and a guessed
    // number in a sentence about what is kept would be the worst kind.
    const offer = undo
      ? ""
      : this._loadingUndo === change.revision
        ? `<p class="why row-loading"><span class="ring mini"></span> Checking whether this change can be undone…</p>`
        : this._undo
          ? `<p class="why">This change cannot be taken back exactly:
             ${escape(this._undo.reason || "no reason given")}.</p>
             ${compareFromOffer}`
        : // Nothing was answered at all - the request for it failed, or
          // it is still out. The sentence above makes a statement about
          // the change itself, and this is the one case where the panel
          // cannot know it: with `_undo` null it said "no reason
          // given", which turned a network error into a refusal by the
          // history. The banner above carries the real cause; this says
          // only that the answer is missing.
          `<p class="why">Whether this change can be taken back is not
             known: the answer did not arrive. Any message above says
             why, and the reload button asks again.</p>`;

    // `diff` and not `diff != null`: the shapes that carry no change -
    // an unknown revision, the first recorded state - answer with the
    // empty string, and offering "Technical details" there opens on
    // "No difference.", which reads as an answer about the dashboard
    // when it is an answer about the request.
    const technical =
      this._explanation && this._explanation.diff
        ? `<details class="raw"${this._diffOpen ? " open" : ""}>
             <summary><span class="glyph">&lt;/&gt;</span> Technical details</summary>
             ${renderDiff(this._explanation.diff)}
           </details>`
        : "";

    return `<div class="detail">
      ${plain}
      ${technical}
      ${offer}
      ${this._renderActionBar(change)}
    </div>`;
  }

  /**
   * What is already named at the state of one change, if anything.
   *
   * Two routes reach the same sentence: the state carries a version
   * itself, or it holds exactly what one holds. Written once because two
   * readers need it - the row, before the click, and the dialog after it
   * - and two copies of a rule like this drift.
   *
   * The content case is only offered for the state the dashboard is in.
   * `same_as_now` compares each entry against the live configuration, so
   * it can answer "is this entry what a version holds" only where "this
   * entry" is the current one. Claiming it anywhere else would need a
   * comparison the panel does not have.
   */
  _alreadyNamed(change) {
    if (!change) return "";
    const carried = (change.versions || []).map((v) => shortName(v.name));
    if (carried.length) return `This state already carries ${someNames(carried)}.`;
    const alike = this._matchingElsewhere(change);
    if (alike.length) return `This is the same state as ${someNames(alike)}.`;
    return "";
  }

  /**
   * Versions that hold what this entry holds without sitting on it.
   *
   * A version on the entry itself is excluded: the section head already
   * names that one, and "same state as v1.0.0" on the very entry that
   * v1.0.0 marks reads as a riddle rather than as news.
   *
   * The rule this follows: a version is named only where it sits
   * somewhere else. That is exactly one place - the newest entry - and
   * everywhere else the answer is either circular or two lines away in
   * the section head.
   */
  _matchingElsewhere(change) {
    if (!change || !change.same_as_now) return [];
    const own = (change.versions || []).map((v) => shortName(v.name));
    return this._versionsMatchingNow().filter((name) => !own.includes(name));
  }

  /**
   * The versions whose content is what the dashboard holds right now.
   *
   * Never "the version you are on". Going back to a version writes a
   * fresh entry, so the state you are in is a later one that happens to
   * hold the same thing - a different entry with the same content. The
   * sentence this feeds says "same state as", never "is": states being
   * equal is not entries being the same one, and a reader who concludes
   * they are *on* v1.0.0 draws wrong conclusions from it. The tooltip
   * spells out what a chip has no room for.
   *
   * `matching_versions` from the server, as the short names a chip
   * shows. Worked out there against every version of this dashboard,
   * which is the point: the same sum over `this._changes` would only
   * ever see the loaded window, and a version below it is exactly the
   * one that has to keep its name. That gap is what project G existed
   * to close, and until now the panel closed it again by ignoring the
   * answer.
   */
  _versionsMatchingNow() {
    return this._matching.map((v) => shortName(v.name));
  }

  _renderVersionHead(section, version, crowned = false) {
    const top = section.rows[0];
    return versionHead({
      version,
      top,
      count: section.rows.length,
      here: this._changes[top]?.same_as_now,
      compareMode: this._compareMode,
      compareChecked: this._compareSelection.some((s) => s.revision === version.name),
      crowned,
    });
  }

  /**
   * The search row, and - in the advanced mode - the compare-mode
   * toggle beside it rather than on a row of its own beneath.
   *
   * The simple mode never had a second row here, so the advanced mode
   * carrying one meant its own content always opened a few pixels
   * lower than the simple mode's - visible as a jump on every switch
   * between them. `.find`'s own width cap (see style.js) keeps the
   * field the same size whether or not this button is beside it, so
   * the row's shape does not change with the mode either.
   */
  _renderSearch() {
    const said = this._searchNote();
    const compareToggle =
      this._mode === "advanced"
        ? `<button class="act ghost" data-compare-toggle="1">
             ${this._compareMode ? "Exit compare mode" : "Compare mode"}
           </button>`
        : "";
    return `<div class="search">
        <input class="text find" type="search" maxlength="100"
               placeholder="${this._mode === "simple"
        ? "Search this dashboard's versions"
        : "Search this dashboard's history"}"
               value="${escape(this._query)}">
        ${compareToggle}
        ${said ? `<span class="why">${escape(said)}</span>` : ""}
        ${this._offersWider()
        ? `<button class="act ghost wider" data-wider="1">Search the whole history</button>`
        : ""}
      </div>`;
  }

  /**
   * Which of the two steps answered. Without it an empty result is
   * ambiguous, and a full one does not say how far it looked.
   */
  _searchNote() {
    if (!this._query.trim()) return "";
    if (this._mode === "simple") {
      const hits = this._matchingVersions().length;
      return `${hits} of ${this._versions.length} versions.`;
    }
    if (this._searching) return "Searching the whole history…";
    const local = this._localMatches();
    // Only while that is still the whole answer. Once somebody has
    // asked the whole history, saying how far the cheap step looked
    // would describe a question that has been superseded.
    if (local.length && this._found === null)
      return `${local.length} of the ${this._changes.length} loaded entries.`;
    // Below the length the second step will run at. Said rather than
    // left blank: an empty note under an empty list reads as a search
    // that ran and found nothing, and the reason it did not run is not
    // guessable from anything on the screen.
    if (this._query.trim().length < 2)
      return `Nothing in the ${this._changes.length} loaded entries. Type a
        second character to search the whole history.`.replace(/\s+/g, " ");
    if (this._found === null) return "";
    if (!this._found.length) return "Nothing in the whole history.";
    return this._moreFound
      ? `The first ${this._found.length} in the whole history.`
      : `${this._found.length} in the whole history.`;
  }

  /**
   * What the bar calls the dashboard being looked at.
   *
   * The recorded title, and the key when there is none - the same
   * fallback the sidebar makes, so the heading and the row it was
   * picked from cannot disagree. Empty while nothing is selected, which
   * leaves the bar exactly as it was before there was a heading in it.
   *
   * Deliberately not the panel title Home Assistant holds: a deleted
   * dashboard has no panel and is precisely the one somebody opens this
   * tool to look at.
   */
  _selectedTitle() {
    if (!this._selected) return "";
    const dashboard = this._dashboards.find((d) => d.key === this._selected);
    return dashboard?.title || this._selected;
  }

  _renderMain() {
    if (!this._selected)
      return '<p class="empty muted">Pick a dashboard on the left.</p>';
    const query = this._query.trim();
    const dashboard = this._dashboards.find((d) => d.key === this._selected);
    const banner =
      dashboard && !dashboard.exists
        ? `<div class="banner">
             <span class="grow">This dashboard was deleted. Its history is
               still here, and so is everything that was on it.</span>
             ${this._changes.length > 1
          ? `<button class="act" data-state="${escape(this._changes[1].revision)}">
                      Bring it back
                    </button>`
          : ""
        }
             <button class="act ghost" data-forget="1">Forget for good</button>
           </div>`
        : "";
    if (this._mode === "simple")
      return (
        banner +
        renderSimple({
          // Both lists. The rows are what the search left; the sentence
          // at the top of the page is about the dashboard, and a search
          // says nothing about that.
          versions: this._versions,
          shown: this._matchingVersions(),
          changes: this._changes,
          searching: Boolean(query),
          // The same set the advanced mode's sections use, keyed the
          // same way. A version opened in one mode is open in the
          // other, which is right: it is one fact about one version,
          // not two pieces of furniture that happen to look alike.
          open: this._verOpen,
        })
      );
    // "Current state" is left out for a dashboard Home Assistant does
    // not currently have: there is nothing there to compare against,
    // and Put-back only ever writes into a live state (spec decision
    // 19's edge case table).
    //
    // Also left out wherever the newest change already stands for the
    // current state - as a crowned row, or as the version head above
    // it, both marked `now` in `_renderNowSection`/`_renderVersionHead`
    // - because ticking that one already means the same thing, and a
    // second checkbox for one fact reads as two different facts. Kept
    // only for decision 9's own edge case, the one thing it exists
    // for: nothing recorded matches what Home Assistant holds right
    // now, so nothing on screen can stand in for "Current state" but
    // this pick itself.
    const somethingIsAlreadyCurrent = Boolean(this._changes[0]?.same_as_now);
    // The toggle itself now sits in the search row (`_renderSearch`),
    // beside the field rather than on a row of its own beneath it -
    // this is only the pinned pick that appears once compare mode is
    // actually on.
    const comparePin =
      this._compareMode && dashboard?.exists !== false && !somethingIsAlreadyCurrent
        ? currentStateRow(this._compareSelection.some((s) => s.revision === null))
        : "";
    const topBar = banner + comparePin;
    const shown = this._shown();
    // Nobody has answered yet: the walk is out, or the query is too
    // short to send. The note above the list says which, and a sentence
    // here would contradict it - which is exactly what "Nothing
    // matches." did, for the seconds a walk over a grown history takes.
    if (shown === null) return topBar;
    if (!shown.length)
      return `${topBar}<p class="empty muted">${query
        ? "Nothing matches."
        : "No changes recorded for this dashboard."}</p>`;
    // Solely while searching: the list is flat and "Load older" is gone,
    // because a page belongs to a list that goes on, not to one a search
    // just cut down to whatever matched.
    if (query)
      return topBar + shown.map((c) => this._renderRow(c, false, false)).join("");

    // Only the first section can be version-less: every later one starts
    // at the change a version sits on. So the unbundled case is handled
    // once, outside the loop, rather than guarded for on every section.
    const cut = sections(this._changes);
    // The one shape a "right now" element cannot fold onto: the newest
    // change already carries a tag, but the dashboard has drifted since
    // that tag was made, so nothing here is crowned at all -
    // `_renderNowBanner` says so with no body of its own. Where the
    // front is clean, that tag's own section below *is* the right-now
    // element (see `crowned` on `versionHead`) and needs no banner
    // above it; where the front is not tagged, `_renderNowSection`
    // draws the element itself, folding the rows it names.
    const behind =
      cut[0]?.versions && !this._changes[0]?.same_as_now
        ? this._renderNowBanner()
        : "";
    // flatMap, not map: two tags can sit on one commit, and each gets
    // its own stacked section rather than one head naming both (see
    // rows.js versionHead). Both opened onto the same rows, because
    // that is the one span there is to show either of them.
    const parts = cut.flatMap((section, sectionIndex) => {
      if (!section.versions) return [this._renderNowSection(section)];
      const rows = section.rows
        .map((index, position) =>
          this._renderRow(this._changes[index], position === 0),
        )
        .join("");
      // Only the first section in the list can start at the newest
      // change at all (`sections()` always opens it there when it
      // carries a mark), so this is the one place a version section can
      // also be where the dashboard stands right now - and therefore
      // the one place a section doubles as the right-now element.
      const crowned = sectionIndex === 0 && Boolean(this._changes[0]?.same_as_now);
      const now = crowned ? " now" : "";
      return section.versions.map((version) => {
        const key = version.name;
        return `<details class="ver${now}" data-key="${escape(key)}"
                ${this._verOpen.has(key) ? "open" : ""}>
                ${this._renderVersionHead(section, version, crowned)}
                <div class="inner">${rows}</div>
              </details>`;
      });
    });
    const older = this._cursor
      ? `<div class="older">
           <button class="act ghost" data-older="1">Load older changes</button>
         </div>`
      : "";
    return topBar + behind + parts.join("") + older;
  }

  /**
   * The sentence a "right now" element opens with when it is not
   * crowned - a version's own section never needs one, being crowned
   * already says everything this does.
   *
   * Either/or, never both: a named match (something recorded holds
   * exactly this content) and "changed since the last version" are the
   * same question answered two ways, not two different facts - the
   * simple mode's own `standing` sentence draws the same either/or, and
   * this is that same choice, not `same_as_now`. A front that is
   * itself the live state but simply has not been tagged yet is still
   * "changed since v1.0.1" in every sense that matters here: nothing
   * recorded carries what it holds.
   *
   * Named by the version it drifted from rather than left generic -
   * `this._versions[0]` is the newest version there is, complete and
   * ordered regardless of the loaded window, the same source the
   * simple mode's own "Undo / Go back to" button reads.
   */
  _nowSentence(matching) {
    if (matching.length)
      return `<p class="why matches" title="${escape(joinNames(matching))}"
           >What the dashboard holds right now is the same state as
           ${escape(someNames(matching))}.</p>`;
    return `<p class="why">The dashboard has changed since ${
      this._versions.length
        ? escape(shortName(this._versions[0].name))
        : "it was first recorded"
    }.</p>`;
  }

  /**
   * The two buttons the simple mode's own "right now" box always
   * offers where nothing recorded matches - saving the live state as a
   * version, and undoing back to the last one there is. Reused here
   * rather than redrawn, because a person switching modes mid-task
   * should find the same way out in both.
   */
  _nowActs(matching) {
    if (matching.length) return "";
    const undo = this._versions.length ? undoButton(this._versions[0]) : "";
    return `<span class="acts">
        <button class="act ghost" data-version="now">Save this as a version</button>
        ${undo}
      </span>`;
  }

  /**
   * The badge, class and body together - all three silent at once
   * while `_versionsLoaded` is false, because none of them can answer
   * anything honestly yet.
   *
   * `_select` clears `_versions`/`_matching` before the fetch that
   * would refill them, and the one render `_guard` draws while that
   * fetch is out would otherwise read the empty arrays as "nothing has
   * ever been recorded here" - true of no dashboard this box has ever
   * been drawn for, and false of whichever one is actually loading.
   * Silence for a frame is honest; a confident wrong answer is not.
   *
   * Reads `_versionsMatchingNow()` itself rather than taking it as a
   * parameter: both callers computed it only to hand it straight back
   * in, one call each, for a fact this method already needs. It answers
   * whether anything *recorded* holds this content - never whether the
   * front is clean, which only says it matches the live state, not
   * that a version names it. A front that is itself a tag reads that
   * same question through `crowned` instead (see `versionHead`).
   */
  _nowFacts() {
    if (!this._versionsLoaded) return { chip: "", namedClass: " loading", body: "" };
    const matching = this._versionsMatchingNow();
    const named = Boolean(matching.length);
    return {
      chip: nowChip(named),
      namedClass: named ? " named" : "",
      body: this._nowSentence(matching) + this._nowActs(matching),
    };
  }

  /**
   * The advanced mode's own "right now" - the same element the simple
   * mode draws, opening onto the full rows rather than the simple
   * mode's summarised lines, because a single step stays undoable only
   * here.
   *
   * Only reached for the span nothing has named yet: where the newest
   * change is itself tagged, that version's own section carries the
   * heading instead (`crowned` on `versionHead`) - there is no second,
   * bodyless element sitting above an otherwise ordinary section, only
   * ever one "right now". The ring belongs to `.now-head` alone, never
   * to `.now-inner` below it: opened onto full change cards rather
   * than the simple mode's compact steps, a ring around the whole
   * thing would have framed a list that can run to dozens of rows in
   * one colour, which said far less than it looked like it said.
   */
  _renderNowSection(section) {
    // `spokenFor` on the very first row alone: that is the one row the
    // heading's own badge already speaks for when the front is clean,
    // and letting `renderRow` badge it too said "current state" twice
    // for one fact - once in the frame the eye stops at, once a few
    // pixels below it.
    const rows = section.rows.map((index, position) =>
      this._renderRow(this._changes[index], position === 0),
    );
    const { chip, namedClass, body } = this._nowFacts();
    const count = section.rows.length;
    const key = "now";
    return `<details class="now-panel${namedClass}" data-key="${key}"
              ${this._verOpen.has(key) ? "open" : ""}>
              <summary class="now-head">
                <p class="heading">Right now ${chip}
                  <span class="count">${count} change${count === 1 ? "" : "s"}</span></p>
                ${body}
              </summary>
              <div class="now-inner">
                ${rows.join("")}
              </div>
            </details>`;
  }

  /**
   * The one shape neither `_renderNowSection` nor a crowned version
   * section can draw: the newest change is already tagged, so there is
   * no unversioned span to fold rows behind, and the dashboard has
   * drifted since that tag was made, so nothing here is crowned
   * either. No rows are left unaccounted for, so this carries no body
   * of its own - only the badge and the sentence.
   */
  _renderNowBanner() {
    const { chip, namedClass, body } = this._nowFacts();
    return `<div class="now-panel now-head${namedClass}">
              <p class="heading">Right now ${chip}</p>
              ${body}
            </div>`;
  }

  // `connector` off only for the flat search list: that one has no
  // `.inner`/`.now-inner` bar to the left to draw a line to.
  _renderRow(change, spokenFor = false, connector = true) {
    const newest = this._isNewest(change);
    return renderRow({
      change,
      newest,
      spokenFor,
      connector,
      matching: newest ? this._matchingElsewhere(change) : [],
      detail: this._open === change.revision ? this._renderDetail(change) : "",
      compareMode: this._compareMode,
      compareChecked: this._compareSelection.some((s) => s.revision === change.revision),
    });
  }

  _renderModeSwitch() {
    const isSimple = this._mode === "simple";
    return `<fieldset class="segmented-control" role="radiogroup" aria-label="View mode">
        <div class="segmented-control__track">
          <div class="segmented-control__glider" aria-hidden="true"></div>
          <label class="segmented-control__option">
            <input type="radio" name="view-mode" value="simple" ${isSimple ? "checked" : ""}>
            <span class="segmented-control__label">
              <svg class="segmented-control__icon" viewBox="0 0 20 20" fill="currentColor">
                <path d="M10 2a8 8 0 100 16 8 8 0 000-16zm-1 4a1 1 0 112 0v4a1 1 0 11-2 0V6zm1 8a1 1 0 100-2 1 1 0 000 2z"/>
              </svg>
              Simple
            </span>
          </label>
          <label class="segmented-control__option">
            <input type="radio" name="view-mode" value="advanced" ${!isSimple ? "checked" : ""}>
            <span class="segmented-control__label">
              <svg class="segmented-control__icon" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 012.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 01.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z" clip-rule="evenodd"/>
              </svg>
              Advanced
            </span>
          </label>
        </div>
      </fieldset>`;
  }

  /**
   * Put the diff's offset back when the column appears without a render.
   *
   * Tapping the row again renders, and `_render` restores the offset on
   * the spot. Widening the window does not: CSS reveals the column by
   * itself, nothing redraws, and the reader who had scrolled into a long
   * diff finds line one. Measured on 2026-09-17 - and worse than a plain
   * loss, because an unrelated render happening to arrive first hides
   * it: the same gesture then works or does not, depending on whether
   * Home Assistant said anything in the meantime.
   *
   * An observer and not a render, which is not the thing the stylesheet
   * argues against. What that argues against is redrawing on every
   * resize, because `_render` replaces the whole shadow root and has to
   * put this very offset and the search box's caret back by hand. This
   * writes one number on one element and then lets go.
   *
   * Guarded rather than assumed: the Node harness in
   * `tests/test_panel_behaviour.py` has a stand-in for the DOM and no
   * `ResizeObserver`, and losing a scroll offset there would be a test
   * failure about nothing.
   */
  _watchDiff(pre) {
    this._unwatchDiff();
    if (typeof ResizeObserver !== "function") return;
    this._diffWatch = new ResizeObserver(() => {
      // Zero while the column is still hidden: a display:none element
      // reports no box, and assigning `scrollTop` to it does nothing.
      if (pre.offsetHeight <= 0) return;
      pre.scrollTop = this._diffScroll;
      this._unwatchDiff();
    });
    this._diffWatch.observe(pre);
  }

  /**
   * Let go of the element being watched.
   *
   * Called before every render, because the next line replaces the whole
   * shadow root and the node under observation stops existing - and from
   * `disconnectedCallback`, for the same reason the subscription is
   * dropped there.
   */
  _unwatchDiff() {
    this._diffWatch?.disconnect();
    this._diffWatch = null;
  }

  _render() {
    if (!this.shadowRoot) return;
    // Never while a dialog is open. Everything below replaces the
    // shadow root wholesale, and a <dialog> that goes with it fires no
    // `close` - so whoever is waiting for the answer waits for ever
    // while the confirmation simply vanishes from the screen. Owed
    // rather than dropped: `_answerFrom` runs it the moment the dialog
    // closes, which is the first moment it can do no harm.
    if (this.shadowRoot.querySelector("dialog[open]")) {
      this._renderOwed = true;
      return;
    }
    this._renderOwed = false;
    // The lock screen replaces everything, and nothing below it runs:
    // no handlers to bind, because there is deliberately nothing to
    // click. That is the point rather than a shortcut - markup that is
    // not there cannot start a request that competes with the rewrite.
    if (this._forgetting) {
      this._unwatchDiff();
      this.shadowRoot.innerHTML = `<style>${STYLE}</style>${this._renderLock()}`;
      return;
    }
    // Read before the old nodes go, and used at the very end to decide
    // whether the caret goes back into the search box. Whether removing
    // a focused element fires `blur` is not the same in every engine,
    // and this must not depend on the answer.
    const wasTyping = this._inBox;
    // Same reason, for the one thing in the detail card that scrolls
    // inside itself: the technical diff, capped at 400px. Replacing the
    // shadow root builds a fresh <pre> at the top, so a reader who had
    // scrolled into a long diff was put back at line one by any render
    // - a save announced from elsewhere, or `_guard` on its way in and
    // out of the next call. The open/closed state was already carried
    // across in `_diffOpen`; this is the other half of the same idea.
    // Only while the column it sits in is on screen. With one column
    // the detail is still drawn when the list is showing - `display:
    // none`, and a hidden element answers 0 for `scrollTop`. Reading
    // that would overwrite the offset with a zero nobody scrolled to,
    // and the way back into the row would land at line one. `offsetHeight`
    // rather than `checkVisibility()`, which Safari only learned late
    // and this panel has to run in.
    const openDiff = this.shadowRoot.querySelector(".detail details.raw[open] pre");
    if (openDiff && openDiff.offsetHeight > 0) this._diffScroll = openDiff.scrollTop;
    // On the host, because the bar and the layout are siblings and a
    // rule on one cannot reach the other. "list" whenever nothing is
    // selected, so the back arrow cannot appear over an empty choice.
    this.setAttribute?.("data-pane", this._selected ? this._pane : "list");
    // The next line replaces every node, including any the diff watcher
    // is holding. Here and not at the top of this method: a render that
    // turned back at the open-dialog guard above has replaced nothing,
    // and dropping the watcher there would lose an offset for a render
    // that never happened.
    this._unwatchDiff();
    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <div class="bar">
        ${this._showsMenuButton()
        ? `<button class="menu" data-menu="1" title="Open the Home Assistant sidebar"
                   aria-label="Open the Home Assistant sidebar">
             <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
               <path d="M3 6h18v2H3zm0 5h18v2H3zm0 5h18v2H3z"/>
             </svg>
           </button>`
        : ""}
        ${this._selected
        ? `<button class="back" data-back="1" title="Back to the dashboard list"
                   aria-label="Back to the dashboard list">
             <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
               <path d="M15.4 7.4 14 6l-6 6 6 6 1.4-1.4-4.6-4.6z"/>
             </svg>
           </button>`
        : ""}
        <span class="app">Dashboard History</span>
        ${this._renderModeSwitch()}
        <span class="which">${escape(this._selectedTitle())}</span>
        ${this._busy ? '<span class="muted" style="font-size:14px">working\u2026</span>' : ""}
        <button class="reload" data-refresh="1" title="Reload the history"
                aria-label="Reload the history">\u21bb</button>
      </div>
      ${this._error ? `<div class="banner"><span class="grow">${escape(this._error)}</span></div>` : ""}
      <div class="layout">
        <div class="side">${this._renderSide()}</div>
        <div class="mainwrap">
          <div class="main">
            ${this._selected ? this._renderSearch() : ""}
            ${this._renderMain()}
          </div>
          ${this._busy ? SPINNER : ""}
        </div>
      </div>
      ${DIALOGS}`;

    const root = this.shadowRoot;
    root.querySelectorAll("details[data-fold]").forEach((element) => {
      element.addEventListener("toggle", () => {
        this._foldOpen[element.dataset.fold] = element.open;
      });
    });
    // Mirrors the folds above: without this, "Back to this version"
    // would appear to collapse its own section, because _guard's
    // preview fetch re-renders before the confirm dialog even opens.
    //
    // By the attribute rather than by the class, so that the simple
    // mode's rows - which are the same thing under a different skin -
    // are wired by the same three lines instead of a copy of them.
    root.querySelectorAll("details[data-key]").forEach((element) => {
      const key = element.dataset.key;
      element.addEventListener("toggle", () => {
        if (element.open) this._verOpen.add(key);
        else this._verOpen.delete(key);
      });
    });
    root.querySelectorAll(".detail details.raw").forEach((element) => {
      element.addEventListener("toggle", () => {
        this._diffOpen = element.open;
      });
    });
    if (this._diffScroll) {
      const pre = root.querySelector(".detail details.raw[open] pre");
      // Setting `scrollTop` on a hidden element does nothing, so this
      // puts the offset back at the first render where the column is on
      // screen again - which is the very render `_pick` triggers.
      // Only where the new diff is long enough to hold it; a shorter
      // one clamps to its own end by itself, which is the right answer
      // and not worth a branch.
      if (pre && pre.offsetHeight > 0) pre.scrollTop = this._diffScroll;
      else if (pre) this._watchDiff(pre);
    }
    // Every click below is wired the same way, so the wiring is written
    // once and each line says only the two things that differ: what was
    // clicked, and what that does. The element comes first because most
    // of them want nothing but its `dataset`.
    const onClick = (selector, run) =>
      root.querySelectorAll(selector).forEach((element) =>
        element.addEventListener("click", (event) => {
          // A control drawn inside a <summary> must not toggle it, and
          // that is a fact about where it was drawn rather than about
          // what it does - so it is said here once, not by each handler
          // that happens to land in one. Only `preventDefault` reaches
          // it: the toggle is the summary's own default behaviour, not a
          // listener, so stopping the propagation leaves it standing.
          // Written out twice by hand before a third control moved into
          // a summary, and the failure is quiet - the fold shuts under
          // the hand that clicked, on its way to a dialog.
          if (element.closest("summary")) event.preventDefault();
          run(element, event);
        }),
      );
    onClick(".menu", () => this._toggleHassMenu());
    onClick(".back", () => {
      this._pane = "list";
      this._render();
    });
    onClick(".dash", (element) => this._pick(element.dataset.key));
    onClick(".change", (element) => this._expand(element.dataset.revision));
    onClick("[data-state]", (element, event) => {
      // Or the click reaches the row underneath and collapses it. The
      // summary's own toggle is dealt with in `onClick` above.
      event.stopPropagation();
      // The dialog is titled with the button that opened it. With two
      // of them on a row, a generic heading would leave you guessing
      // which one you pressed.
      this._restoreState(element.dataset.state, element.textContent.trim());
    });
    onClick("[data-undo]", (element, event) => {
      event.stopPropagation();
      this._undoChange(element.dataset.undo);
    });
    onClick("[data-replace]", (element, event) => {
      event.stopPropagation();
      this._openReplace(element.dataset.replace);
    });
    onClick("[data-forget]", () => this._forget());
    onClick("[data-older]", () => this._loadOlder());
    onClick("[data-wider]", () => this._searchWider());
    // Guarded, unlike the automatic one: somebody who pressed a button
    // is owed both the "working" state and the failure if there is one.
    onClick("[data-refresh]", () => this._guard(() => this._refresh()));
    onClick("[data-describe]", (element, event) => {
      // Otherwise the click reaches .change underneath and expands the
      // row at the same time.
      event.stopPropagation();
      this._describe(element.dataset.describe);
    });
    onClick("[data-retitle]", (element, event) => {
      // As with the other controls that sit inside a row: without this
      // the click reaches the row underneath and folds it on the way to
      // the dialog. The summary's own toggle is dealt with in `onClick`.
      event.stopPropagation();
      this._retitleVersion(element.dataset.retitle);
    });
    onClick("[data-remove]", (element, event) => {
      // As with the pen beside it: without this the click reaches the
      // row underneath and folds it on the way to the dialog.
      event.stopPropagation();
      this._removeVersion(element.dataset.remove);
    });
    onClick("[data-version]", (element, event) => {
      // Otherwise the click reaches the row underneath and collapses it.
      event.stopPropagation();
      // "now" is the simple mode's button, which means the newest
      // recorded state. Everything else names a revision.
      const which = element.dataset.version;
      this._createVersion(which === "now" ? this._changes[0]?.revision : which);
    });
    onClick("[data-mode]", (element, event) => {
      event.stopPropagation();
      this._setMode(element.dataset.mode);
    });
    onClick("[data-compare-toggle]", () => this._toggleCompareMode());
    onClick(".compare-check", (element, event) => {
      event.stopPropagation();
      const revision = element.dataset.compare || null;
      const now = element.dataset.compareNow === "1";
      this._toggleCompareRevision(revision, element.dataset.compareLabel || "", now);
    });
    onClick("[data-compare-from]", (element, event) => {
      event.stopPropagation();
      this._jumpToCompareFrom(element.dataset.compareFrom);
    });
    // `[data-compare-restore]` buttons are not in the DOM at the moment
    // this generic pass runs - they are injected later, into
    // `[data-compare-body]`, by `_openCompare`'s own `body.innerHTML =`
    // write, which happens after a click while no full `_render()` runs
    // (a dialog's content must not be torn down under the user - see
    // `_renderOwed`). A listener attached directly to the buttons above
    // would therefore bind to nothing and never fire.
    //
    // `[data-compare-body]` itself is static markup, part of `DIALOGS`
    // from the very first render, so this pass reaches it the ordinary
    // way; delegating from there with `closest` catches a button however
    // long after this wiring pass it was injected. Same idea as the
    // `.levels` button group above, applied to the generic block: one
    // listener on the container rather than one per button that does
    // not exist yet.
    onClick("[data-compare-body]", (element, event) => {
      const button = event.target.closest("[data-compare-restore]");
      if (!button) return;
      const dialog = element.closest("dialog.compare");
      const revision = dialog?.dataset.compareReference;
      if (!revision) return;
      const position = Number(button.dataset.compareRestore);
      const item = (this._compareMissing || []).find(
        (candidate) => candidate.position === position,
      );
      if (!item) return;
      // Closed here rather than kept open and refreshed: putting one
      // item back can shift the positions of whatever else this dialog
      // still lists, and it never re-fetches on its own. A second click
      // on a button drawn before this one either names the wrong item
      // now or a position that no longer exists - closing pins that
      // down to "never", at the cost of a fresh compare to put another
      // item back. `dialog.close()` settles `_openCompare`'s own
      // pending `_answerFrom` wait the same way the Close button would.
      dialog.close();
      this._compareMode = false;
      this._compareSelection = [];
      this._compareMissing = [];
      this._restoreItem(revision, item);
    });
    root.querySelectorAll(".segmented-control input[type='radio']").forEach((radio) => {
      radio.addEventListener("change", (event) => {
        const nextMode = event.target.value;
        if (nextMode === this._mode) return;
        this._modeAfterSlide(nextMode);
      });
    });
    root.querySelectorAll("dialog").forEach((element) =>
      element
        .querySelectorAll(".actions button")
        .forEach((button) =>
          button.addEventListener("click", () => element.close(button.value)),
        ),
    );
    root.querySelectorAll("dialog .keepbox").forEach((keepbox) => {
      keepbox.addEventListener("change", (event) => {
        const fields = keepbox.closest("[data-keep]")?.querySelector(".keepfields");
        if (fields) fields.hidden = !event.target.checked;
      });
    });
    const field = root.querySelector("dialog.describe input.text");
    if (field)
      field.addEventListener("keydown", (event) => {
        // A single field with a button should behave like a form.
        if (event.key === "Enter") {
          event.preventDefault();
          root.querySelector("dialog.describe").close("save");
        }
      });
    const find = root.querySelector("input.find");
    if (find) {
      // The caret goes back where it was - and only if it was here.
      //
      // A render replaces the search box along with everything else, so
      // typing would lose the caret on every keystroke without this.
      // What it used to follow, though, was the *query* and not the
      // person: any render with a word in the box pulled the focus in
      // and pushed the caret to the end of it. Opening a row renders
      // twice (`_guard` on the way in and on the way out), so a click
      // in the list took the caret out of the list and put it in the
      // box; and a save announced from elsewhere jumped a half-typed
      // correction to the end of the word while somebody stood in the
      // middle of it.
      if (wasTyping) {
        find.focus();
        // Where the caret was, not the end of the line. The end is
        // right for the ordinary case - somebody typing forwards is
        // already there - and wrong for the one that hurt: a correction
        // made in the middle of a word.
        const at = this._caret ?? find.value.length;
        find.setSelectionRange?.(at, at);
      }
      // Focus is a fact about the page, so it is read from the page.
      // Both fire on the new box as well - `find.focus()` above is a
      // focus - which is what keeps the flag true across a run of
      // renders while somebody types.
      find.addEventListener("focus", () => {
        this._inBox = true;
      });
      find.addEventListener("blur", () => {
        this._inBox = false;
      });
      find.addEventListener("keydown", (event) => {
        // Somebody who has pressed Enter has finished the word, and the
        // 400 ms below are there for somebody who has not. The same
        // shape the description dialog uses: one field with one thing
        // to do behaves like a form.
        if (event.key !== "Enter") return;
        event.preventDefault();
        // The overtaken timer goes, or the same word is walked over the
        // whole history twice for one keypress.
        clearTimeout(this._typing);
        this._typing = null;
        this._search(find.value);
      });
      find.addEventListener("input", () => {
        // Set here too, and not only in the listener above: this is the
        // one event that certainly came from somebody typing, and it is
        // the moment the caret's position is worth remembering.
        this._inBox = true;
        this._caret = find.selectionStart ?? find.value.length;
        clearTimeout(this._typing);
        const text = find.value;
        // 400 ms, and only then. A walk over the whole history costs
        // about half a second per thousand commits, and firing it per
        // keystroke would spend that eight times for one word.
        this._typing = setTimeout(() => this._search(text), 400);
      });
    }
  }
}

// Defining the same name twice throws, and a second definition is exactly
// what an update now causes: the fingerprint in the module URL changes, so
// the frontend imports panel.js again while the element registered from the
// previous URL is still in this page session. Without this guard the panel
// dies with "the name has already been used with this registry" for anyone
// who does not hard-reload after an update - which is the one moment they
// have no reason to. A definition cannot be replaced, so the previous one
// keeps serving until the next full page load. Stale beats broken.
if (!customElements.get("dashboard-history-panel"))
  customElements.define("dashboard-history-panel", DashboardHistoryPanel);
