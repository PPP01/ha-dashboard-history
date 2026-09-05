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
let sections, someNames, renderRow, versionHead;
let DIALOGS;
let renderSimple;

const partsReady = Promise.all([
  import(`./panel/style.js${PARTS}`),
  import(`./panel/render.js${PARTS}`),
  import(`./panel/rows.js${PARTS}`),
  import(`./panel/dialogs.js${PARTS}`),
  import(`./panel/simple.js${PARTS}`),
]).then(([style, render, rows, dialogs, simple]) => {
  STYLE = style.STYLE;
  ({ escape, renderDiff, renderPlain, when, joinNames } = render);
  ({ sections, someNames, renderRow, versionHead } = rows);
  ({ DIALOGS } = dialogs);
  ({ renderSimple } = simple);
});

// Where the chosen mode is remembered. In the browser and not in the
// config entry: the design record calls it a setting of the interface,
// and two admins in one house may reasonably want different ones. It
// costs no round trip, no reload and no restart.
const MODE_KEY = "dashboard-history:mode";
const MODES = ["simple", "advanced"];

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
    this._found = null;
    this._moreFound = false;
    this._searching = false;
    this._typing = null;
    // The versions holding exactly what the dashboard holds now, worked
    // out by the server against *every* version. Read rather than
    // recomputed: doing it here means doing it over the loaded window,
    // and a version below that window is precisely the one that must
    // still be named.
    this._matching = [];
    this._dashboards = [];
    this._changes = [];
    // Where the next page starts, or null when there is nothing older.
    // A commit and not a count: save something while somebody is
    // reading, and every offset below them shifts by one.
    this._cursor = null;
    this._selected = null;
    this._open = null; // revision of the expanded change
    this._items = [];
    this._explanation = null;
    this._deadOpen = false;
    // Which version sections are expanded, keyed by the name of the
    // section's first version. Native <details> state alone does not
    // survive a re-render - _render() replaces the whole shadow DOM, so
    // without this a "Back to this version" click would collapse the
    // very section it was clicked from, the moment _guard's preview
    // fetch triggers the first re-render.
    this._verOpen = new Set();
    // A count, not a flag. Two requests can be in flight at once - a row
    // opened while the previous row's answers are still coming - and a
    // flag went dark when the *first* of them finished. Measured on
    // 2026-09-03 in the Node run behind tests/test_panel_behaviour.py.
    this._busy = 0;
    this._error = null;
    this._loaded = false;
    // One ticket counter per slot the page can fill - the change list,
    // the open row's detail. Comparing the selection or the open revision
    // after an answer is not enough: choose A, then B, then A again, and
    // the first A's late answer passes that check and overwrites the
    // second's. See `_claim`.
    this._tickets = { changes: 0, detail: 0 };
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
  _setMode(mode) {
    if (!MODES.includes(mode)) return;
    this._mode = mode;
    try {
      localStorage.setItem(MODE_KEY, mode);
    } catch {
      // See `storedMode`. The choice holds for this page and no longer.
    }
    this._render();
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
  }

  disconnectedCallback() {
    // Home Assistant keeps panels around between visits. A subscription
    // that outlives the element would keep fetching a history nobody is
    // looking at.
    this._unlisten();
  }

  /**
   * A change has been recorded. Decide whether this page cares.
   */
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
    const listed = await this._call("dashboards");
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
      this._versions = versions.versions || [];
      // An expanded row keeps its place, but not its answers: after a
      // change from outside, "Put back" would be offering items worked
      // out against a dashboard that has moved on.
      const open = this._changeAt(this._open);
      if (!open) {
        this._claim("detail");
        this._open = null;
        this._items = [];
        this._explanation = null;
        this._undo = null;
      } else {
        const detailMine = this._claim("detail");
        const detail = await this._detailFor(open);
        if (!detailMine()) return;
        this._take(detail);
      }
    }
    this._render();
  }

  async _refreshQuietly() {
    try {
      await this._refresh();
    } catch {
      // Nobody asked for this one. An error banner arriving from nowhere
      // is worse than a page that is briefly out of date; the button
      // reports its own failures.
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

  async _loadDashboards() {
    const result = await this._guard(() => this._call("dashboards"));
    if (!result) return;
    this._dashboards = result.dashboards || [];
    // A live one. This used to open on a deleted dashboard, on the
    // reasoning that a loss is what people come here for - but with a
    // dozen deleted ones it picks an arbitrary gravestone, and they are
    // behind a fold now anyway.
    const first = this._dashboards.find((d) => d.exists) || this._dashboards[0];
    if (first) await this._select(first.key);
  }

  async _select(key) {
    const mine = this._claim("changes");
    this._claim("detail"); // the open row went with the old selection
    this._selected = key;
    this._open = null;
    this._items = [];
    this._explanation = null;
    this._undo = null;
    this._cursor = null;
    this._versions = [];
    this._matching = [];
    this._query = "";
    this._found = null;
    this._moreFound = false;
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
    this._versions = versions ? versions.versions || [] : [];
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
    const mine = this._claim("changes");
    const asked = this._cursor;
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
    this._query = text;
    this._found = null;
    this._moreFound = false;
    if (
      this._mode === "simple" ||
      !text.trim() ||
      text.trim().length < 2 ||
      this._localMatches().length
    ) {
      this._render();
      return;
    }
    const mine = this._claim("changes");
    this._searching = true;
    this._render();
    const result = await this._guard(
      () =>
        this._call("search", { dashboard: this._selected, text, limit: 100 }),
      mine,
    );
    // Cleared before the claim is checked, not after: a search that has
    // been superseded still has to put its own indicator out. The other
    // way round, a run whose claim was taken by something that is not a
    // search - `_loadOlder`, say - would leave "Searching the whole
    // history…" standing for good.
    this._searching = false;
    if (!mine()) return;
    this._found = result ? result.changes || [] : [];
    this._moreFound = result ? Boolean(result.more) : false;
    this._render();
  }

  /** The words a row is searched by: its own, and its versions'. */
  _wordsOf(change) {
    return [
      change.message || "",
      change.description || "",
      ...(change.versions || []).flatMap((v) => [
        (v.name || "").split("/").pop(),
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
      [(v.name || "").split("/").pop(), v.title || "", v.description || ""]
        .join("\n")
        .toLowerCase()
        .includes(needle),
    );
  }

  /**
   * What the advanced list should show: the plain history, the local
   * hits, or what the server found. One place decides it, so no
   * renderer has to.
   */
  _shown() {
    if (!this._query.trim()) return this._changes;
    const local = this._localMatches();
    if (local.length) return local;
    return this._found || [];
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
    return this._changes.find((c) => c.revision === revision) || null;
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
      this._render();
      return;
    }
    const mine = this._claim("detail");
    this._open = revision;
    this._items = [];
    this._explanation = null;
    this._undo = null;
    const detail = await this._guard(() => this._detailFor(change), mine);
    // While this row's answers were on their way, somebody opened another
    // row - or closed this one, or opened it again. Its answers belong to
    // that later request, and writing these here would put row "a"'s
    // items under the heading of row "b", or an older answer over a newer
    // one. Measured on 2026-09-03: the later row's answers arrived first,
    // then these did, and the page settled on the wrong ones.
    if (!mine()) return;
    this._take(detail);
    this._render();
  }

  /** The three answers a row's detail is built from. */
  _detailFor(change) {
    return Promise.all([
      change.previous
        ? this._call("deleted_since", {
          dashboard: this._selected,
          revision: change.previous,
        })
        : Promise.resolve({ items: [] }),
      this._call("explain", {
        dashboard: this._selected,
        revision: change.revision,
      }),
      this._call("undo_change", {
        dashboard: this._selected,
        revision: change.revision,
      }),
    ]);
  }

  _take(answers) {
    const [missing, explanation, undo] = answers || [null, null, null];
    this._items = missing ? missing.items || [] : [];
    this._explanation = explanation;
    this._undo = undo || null;
  }

  /** Show the preview, and write only if the person says so. */
  async _confirm(title, request, wantsKeep = false) {
    const preview = await this._guard(() => this._call(...request(false, null)));
    if (!preview) return;
    if (preview.error) {
      this._error = preview.error;
      this._render();
      return;
    }
    // The undo re-proves itself on every call, so a preview can come
    // back as a refusal - somebody saved between the row being drawn and
    // the button being pressed, which is exactly the case decision 15
    // asks it to catch. Without this the dialog opened on an empty diff
    // with a live Apply, and the sentence that names the reason and the
    // card was thrown away by the one screen that exists to show it.
    if (preview.available === false) {
      this._error = preview.reason || "this cannot be taken back exactly";
      this._render();
      return;
    }
    const dialog = this.shadowRoot.querySelector("dialog.confirm");
    dialog.querySelector("h2").textContent = title;
    // The integration answers "already identical" when the target state is
    // what the dashboard holds already. Showing an empty diff as "No
    // difference." next to a live Apply button was the panel throwing that
    // answer away and offering a change that changes nothing.
    const nothingToDo = !preview.preview && preview.note;
    dialog.querySelector(".body").innerHTML = nothingToDo
      ? `<p>This state is what the dashboard holds right now, so there is
           nothing to apply.</p>`
      : renderPlain(preview.explanation, "What applying this does") +
      // The question this answers came from a person who had to read
      // the source to find it out: does setting a state back throw the
      // present one away? It does not, and nothing here said so.
      // Nothing in this integration rewrites history except `forget`;
      // a restore writes the live dashboard, and the recorder appends
      // an entry for what was there. Left out when the dashboard is
      // being recreated: there is no present state to keep, and the
      // note beside the buttons already says what happens instead.
      (preview.creates_dashboard
        ? ""
        : `<p class="keeps">What the dashboard holds now is not lost: it
               stays in the history as its own entry, so you can set it
               back the same way.</p>`) +
      `<details class="raw">
           <summary>Show the technical details</summary>
           ${renderDiff(preview.preview)}
         </details>`;
    const applyButton = dialog.querySelector('.actions button[value="apply"]');
    applyButton.hidden = Boolean(nothingToDo);
    dialog.querySelector('.actions button[value="cancel"]').textContent =
      nothingToDo ? "Close" : "Cancel";
    const note = preview.creates_dashboard
      ? "This recreates the dashboard, with its old title and icon."
      : "";
    dialog.querySelector(".note").textContent = note;
    // Offered only where a whole state is replaced and there is one to
    // keep. Not while a dashboard is being recreated - there is no live
    // state then, and the answer for that case is an error; a tick box
    // whose only possible outcome is a failure is worse than none. Not
    // where nothing is applied either.
    const keepable = Boolean(
      wantsKeep && !nothingToDo && !preview.creates_dashboard,
    );
    this._armKeep(keepable);
    dialog.returnValue = "";
    dialog.showModal();
    const answer = await new Promise((resolve) => {
      dialog.addEventListener("close", () => resolve(dialog.returnValue), {
        once: true,
      });
    });
    if (answer !== "apply") return;
    const keep = keepable ? this._keepChoice() : null;
    // Armed before the write: the recorder is quick, and an announcement
    // that arrives first would find nobody waiting.
    const recorded = this._recorded();
    const applied = await this._guard(async () => {
      const result = await this._call(...request(true, keep));
      // Still busy until the recorder has it. Reloading in between reads
      // a history whose newest entry is the state just replaced - so
      // nothing matches the live configuration, nothing is crowned, and
      // the page looks half-built. Measured at 30 to 150 ms of exactly
      // that.
      await recorded;
      return result;
    });
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
      "";
    await this._select(this._selected);
    await this._loadDashboardsQuietly();
    // After the reload, not before it. `_select` goes through `_guard`,
    // and `_guard` clears the banner on its way in - so anything written
    // here first is wiped by the very refresh that follows it, which is
    // what happened to every note this dialog has ever tried to leave.
    if (said) {
      this._error = said;
      this._render();
    }
  }

  /**
   * Show the block that offers to keep the state being replaced, or
   * hide it again.
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
  _armKeep(show) {
    const keep = this.shadowRoot.querySelector("[data-keep]");
    if (!keep) return;
    keep.hidden = !show;
    if (!show) return;
    keep.querySelector(".keepbox").checked = this._mode === "simple";
    keep.querySelector(".keeptitle").value = today();
  }

  /**
   * The version to make, or null for none.
   *
   * Patch, and never a level somebody has to choose: this is a
   * waypoint, not a milestone, and a three-way choice in front of a
   * restore is a question nobody came here to answer.
   */
  _keepChoice() {
    const keep = this.shadowRoot.querySelector("[data-keep]");
    const box = keep?.querySelector(".keepbox");
    if (!box?.checked) return null;
    const title = keep.querySelector(".keeptitle").value.trim();
    return { level: "patch", title: title || today() };
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
    const dialog = this.shadowRoot.querySelector("dialog.describe");
    const field = dialog.querySelector("input.text");
    field.value = change.description || "";
    dialog.returnValue = "";
    dialog.showModal();
    field.focus();
    field.select();
    const answer = await new Promise((resolve) => {
      dialog.addEventListener("close", () => resolve(dialog.returnValue), {
        once: true,
      });
    });
    if (answer !== "save") return;
    const result = await this._guard(() =>
      this._call("describe", { revision: change.revision, text: field.value }),
    );
    if (result?.error) {
      this._error = result.error;
      this._render();
      return;
    }
    await this._select(this._selected);
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
    const offered = await this._guard(() =>
      this._call("next_versions", { dashboard: this._selected }),
    );
    if (!offered) return;
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
      button.querySelector("strong").textContent = (
        candidates[which] || ""
      ).split("/").pop();
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
    const answer = await new Promise((resolve) => {
      dialog.addEventListener("close", () => resolve(dialog.returnValue), {
        once: true,
      });
    });
    if (answer !== "create") return;
    const result = await this._guard(() =>
      this._call("create_version", {
        dashboard: this._selected,
        level,
        title: title.value.trim() || candidates[level].split("/").pop(),
        description: description.value.trim(),
        revision: change.revision,
      }),
    );
    if (result?.error) {
      this._error = result.error;
      this._render();
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
    await this._select(this._selected);
  }

  /**
   * The one thing here that cannot be undone, so it is asked twice: once
   * by the button, once by a dialog that counts what is about to be lost.
   * No diff - a diff of this would be the whole history.
   */
  async _forget() {
    const dashboard = this._dashboards.find((d) => d.key === this._selected);
    const facts = await this._guard(() =>
      this._call("forget", { dashboard: this._selected }),
    );
    if (!facts) return;
    if (facts.error) {
      this._error = facts.error;
      this._render();
      return;
    }
    const dialog = this.shadowRoot.querySelector("dialog.forget");
    const span =
      facts.first && facts.last
        ? `, from ${escape(when(facts.first))} to ${escape(when(facts.last))}`
        : "";
    dialog.querySelector(".body").innerHTML = `
      <p>This throws away the recorded history of
         <strong>${escape(dashboard?.title || this._selected)}</strong>.</p>
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
    const answer = await new Promise((resolve) => {
      dialog.addEventListener("close", () => resolve(dialog.returnValue), {
        once: true,
      });
    });
    if (answer !== "forget") return;
    const done = await this._guard(() =>
      this._call("forget", { dashboard: this._selected, confirm: true }),
    );
    if (done?.error) this._error = done.error;
    this._selected = null;
    this._changes = [];
    await this._loadDashboards();
  }

  _restoreItem(change, item) {
    this._confirm(`Put back: ${item.label}`, (confirm) => [
      "restore_deleted",
      {
        dashboard: this._selected,
        revision: change.previous,
        position: item.position,
        confirm,
      },
    ]);
  }

  _restoreState(revision, title) {
    // Returned rather than dropped, unlike its two neighbours: the Node
    // scenario waits for it, and a flow whose end nobody can wait for
    // cannot be tested at all.
    return this._confirm(
      title,
      (confirm, keep) => [
        "restore_state",
        {
          dashboard: this._selected,
          revision,
          confirm,
          // Left out entirely when nothing is to be marked. An empty
          // object would be a request for a version with no name, which
          // the server would then have to refuse.
          ...(keep ? { keep_as_version: keep } : {}),
        },
      ],
      true,
    );
  }

  _undoChange(revision) {
    this._confirm("Undo this change", (confirm) => [
      "undo_change",
      { dashboard: this._selected, revision, confirm },
    ]);
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
   * Live dashboards, then the deleted ones behind a fold.
   *
   * A deleted dashboard has to stay findable - it is the one somebody
   * opens this tool for - but it stays findable forever, and that is the
   * problem. Delete a dashboard every few months and the list is mostly
   * gravestones. So they are counted and folded away, not hidden: one
   * click, and the fold stays open while you work.
   */
  _renderSide() {
    if (!this._dashboards.length)
      return '<p class="empty muted">Nothing recorded yet.</p>';
    const live = this._dashboards.filter((d) => d.exists);
    const dead = this._dashboards.filter((d) => !d.exists);
    const rows = live.map((d) => this._renderDashboard(d)).join("");
    if (!dead.length) return rows;
    const openDead = this._deadOpen || dead.some((d) => d.key === this._selected);
    return (
      rows +
      `<details class="dead" ${openDead ? "open" : ""}>
         <summary>Deleted (${dead.length})</summary>
         ${dead.map((d) => this._renderDashboard(d)).join("")}
       </details>`
    );
  }

  /**
   * The coarse ways back, folded away.
   *
   * They used to stand beside the fine ones, and the first person to
   * meet them read them as two labels for one action - fairly, because
   * in the case they met (newest change, one deleted card) that is
   * exactly what they were. Since decision 15 the row leads with the
   * targeted undo, and these are the escape hatch: replace the whole
   * dashboard, everything since gone. Folded, not removed - it is a
   * real capability and somebody wants it about once a year.
   *
   * The "before" button is left out when it would write exactly what
   * the undo writes. The server says so with `equals_state_before`; the
   * panel does not compare states, because a comparison here is logic
   * here.
   */
  _renderSetBack(change) {
    const before = change.previous;
    const buttons = [];
    const same = this._undo?.available && this._undo.equals_state_before;
    // Where the predecessor is outside the loaded window this is
    // `undefined` and the button stays - exactly what happened before,
    // when `this._changes[index + 1]` was not there either.
    if (before && !this._changeAt(before)?.same_as_now && !same)
      buttons.push({
        revision: before,
        label: "Back to the state before this change",
      });
    if (!change.same_as_now)
      buttons.push({
        revision: change.revision,
        label: "Back to the state after this change",
      });

    const why =
      before && this._changeAt(before)?.same_as_now
        ? `<span class="why">The state before this change is what the
            dashboard holds now — nothing to set back.</span>`
        : "";
    if (!buttons.length) return why;
    return `<details class="more">
        <summary>Replace the whole dashboard instead</summary>
        <p class="why" style="margin-top:8px">Setting a state back replaces
          the whole dashboard with how it was then. Everything saved since
          is no longer what the dashboard holds.</p>
        <div class="backto">
          ${buttons
        .map(
          (b) =>
            `<button class="act ghost" data-state="${escape(b.revision)}"
                  >${b.label}</button>`,
        )
        .join("")}
        </div>${why}
      </details>`;
  }

  _renderDetail(change) {
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
        ${this._renderMakeVersion(change)}</div>`;
    // Which of the missing items the undo takes care of. Two reasons,
    // and only these two - decision 15:
    //
    // "covered": the undo restores exactly this one item and does
    // nothing else. That is one shape only, a change that deleted a
    // single thing, and it is the shape somebody reported as confusing
    // because the two buttons there really do the same work.
    //
    // "trap": the change also *added* something. Then a plain put-back
    // is not merely redundant, it is wrong: an edit whose key field was
    // touched reads as one removal plus one addition, and adding the old
    // card back leaves both versions standing. Measured, not feared.
    const undo = this._undo?.available ? this._undo : null;
    const added = /\d+ added/.test(change.message || "");
    const mine = new Set(
      (this._explanation?.groups || [])
        .flatMap((group) => group.entries)
        .filter((entry) => entry.kind === "removed")
        .map((entry) => entry.label),
    );
    // A missing view's label carries a "view: " lead-in the explanation's
    // entry does not (deleted_since names it for a list of mixed cards and
    // views; explain already sits under a view heading and does not need
    // to say so again). Comparing the two forms as they stand would leave
    // a removed-and-re-added view uncovered - exactly the trap, on the
    // one item shape most likely to hit it.
    const bareLabel = (label) => label.replace(/^view: /, "");
    const swallowed = (item) =>
      undo && mine.has(bareLabel(item.label)) && (added || mine.size === 1);
    const own = this._items.filter((item) => !swallowed(item));

    const rows = own
      .map(
        (item) => `
        <div class="item">
          <span class="label">${escape(item.label)}
            <span class="where">${escape(item.kind)}${item.view ? ` · view ${escape(item.view)}` : ""}</span>
          </span>
          <button class="act" data-restore="${item.position}">Put back</button>
        </div>`,
      )
      .join("");
    // Named when the undo has taken the rest off the list: otherwise the
    // remaining rows read as "this change deleted these", which is then
    // exactly wrong.
    const heading =
      own.length && own.length < this._items.length
        ? `<p class="why" style="margin-top:16px">Also missing since then,
             from later changes:</p>`
        : "";
    const list = rows
      ? heading + rows
      : undo
        ? ""
        : `<p class="muted">Nothing from before this change is missing today.</p>`;

    // Left out where the number is not known - a row from outside the
    // loaded window has no place in it to count from, and a guessed
    // number in a sentence about what is kept would be the worst kind.
    const made = this._madeSince(change);
    const kept =
      made ? ` and keeps the ${made} change${made === 1 ? "" : "s"} made since` : "";
    const offer = undo
      ? `<div class="backto">
           <button class="act" data-undo="${escape(change.revision)}">Undo this change</button>
         </div>
         <p class="why" style="margin-top:8px">Puts this change back${kept}.</p>`
      : `<p class="why">This change cannot be taken back exactly:
           ${escape(this._undo?.reason || "no reason given")}.</p>`;

    return `<div class="detail">
      ${plain}
      ${offer}
      ${list}
      ${this._renderSetBack(change)}
      ${this._renderMakeVersion(change)}
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
    const carried = (change.versions || []).map((v) => v.name.split("/").pop());
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
    const own = (change.versions || []).map((v) => v.name.split("/").pop());
    return this._versionsMatchingNow().filter((name) => !own.includes(name));
  }

  /**
   * The button that makes a version, and what is already named there.
   *
   * The note sits beside the button rather than only in the dialog the
   * button opens: telling somebody after they clicked is telling them
   * late. The button stays, though - unlike "Back to this version",
   * which is a pure no-op on the current state, a second version on the
   * same content creates a name that did not exist and can be exactly
   * what somebody means ("we went back to the old layout, and that is
   * v1.0.0 now"). The design record allows two versions on one state.
   */
  _renderMakeVersion(change) {
    const named = this._alreadyNamed(change);
    return `<div class="mkver">
        <button class="act ghost" data-version="${escape(change.revision)}"
                >Version up to here</button>
        ${named ? `<span class="named">${escape(named)}</span>` : ""}
      </div>`;
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
    return this._matching.map((v) => v.name.split("/").pop());
  }

  _renderVersionHead(section) {
    const top = section.rows[0];
    return versionHead({
      section,
      top,
      here: this._changes[top]?.same_as_now,
    });
  }

  _renderSearch() {
    const said = this._searchNote();
    return `<div class="search">
        <input class="text find" type="search" maxlength="100"
               placeholder="${this._mode === "simple"
        ? "Search this dashboard's versions"
        : "Search this dashboard's history"}"
               value="${escape(this._query)}">
        ${said ? `<span class="why">${escape(said)}</span>` : ""}
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
    if (local.length)
      return `${local.length} of the ${this._changes.length} loaded entries.`;
    if (this._found === null) return "";
    if (!this._found.length) return "Nothing in the whole history.";
    return this._moreFound
      ? `The first ${this._found.length} in the whole history.`
      : `${this._found.length} in the whole history.`;
  }

  _renderMain() {
    if (!this._selected)
      return '<p class="empty muted">Pick a dashboard on the left.</p>';
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
          versions: this._matchingVersions(),
          changes: this._changes,
          searching: Boolean(this._query.trim()),
        })
      );
    const shown = this._shown();
    if (!shown.length)
      return `${banner}<p class="empty muted">${this._query.trim()
        ? "Nothing matches."
        : "No changes recorded for this dashboard."}</p>`;
    // Solely while searching: the list is flat and "Load older" is gone,
    // because a page belongs to a list that goes on, not to one a search
    // just cut down to whatever matched.
    if (this._query.trim())
      return (
        banner +
        shown.map((change) => this._renderRow(change)).join("")
      );

    // Only the first section can be version-less: every later one starts
    // at the change a version sits on. So the unbundled case is handled
    // once, outside the loop, rather than guarded for on every section.
    const cut = sections(this._changes);
    const newest = cut.find((s) => s.versions);
    const label = newest
      ? `Since ${newest.versions[0].name.split("/").pop()}`
      : "Not in a version yet";
    const parts = cut.map((section) => {
      if (!section.versions) return this._renderTopSection(section, label);
      const rows = section.rows
        .map((index, position) =>
          this._renderRow(this._changes[index], position === 0),
        )
        .join("");
      const key = section.versions[0].name;
      return `<details class="ver" data-key="${escape(key)}"
                ${this._verOpen.has(key) ? "open" : ""}>
                ${this._renderVersionHead(section)}
                <div class="inner">${rows}</div>
              </details>`;
    });
    const older = this._cursor
      ? `<div class="older">
           <button class="act ghost" data-older="1">Load older changes</button>
         </div>`
      : "";
    return banner + parts.join("") + older;
  }

  /**
   * The newest entry is set apart when it is provably the state in front
   * of you. Provably: after a change made at Home Assistant's back it is
   * not, and then nothing is crowned rather than the wrong thing.
   */
  _renderTopSection(section, label) {
    const rows = section.rows.map((index) =>
      this._renderRow(this._changes[index]),
    );
    // The panel knew this and kept it to itself: the head of the
    // version's own section reads "same state as now", the row up here
    // reads "current state", and nothing joined the two. Somebody had to
    // read the source to find out which version they were looking at.
    const matching = this._versionsMatchingNow();
    // Only for the branch below, where nothing is crowned and so no row
    // can carry the badge. Where a row *is* crowned, the same fact rides
    // as a chip beside "current state" instead: inside the frame the eye
    // stops at, rather than in a line under it that gets read past.
    const sameVer = matching.length
      ? `<span class="why matches" title="${escape(joinNames(matching))}"
           >What the dashboard holds right now is the same state as
           ${escape(someNames(matching))}.</span>`
      : "";
    // Placed by what it describes. Below, the crowned row *is* the
    // current state and the sentence belongs under it. Here nothing is
    // crowned - the dashboard changed at Home Assistant's back, and no
    // row stands for the present state - so the sentence is the only
    // thing on the page that speaks for it, and leads.
    if (!this._changes[0].same_as_now)
      return `${sameVer}<div class="divider">${escape(label)}</div>${rows.join("")}`;
    // The crowned row sits above the divider, not under it - so when it
    // is the only row, the divider has nothing left to head and the
    // label would disappear with it. It moves into the heading instead:
    // "which version am I building on" is exactly what somebody looking
    // at a change that is not in one yet wants to know.
    const more = rows.length > 1;
    const rest = more
      ? `<div class="divider">${escape(label)}</div>${rows.slice(1).join("")}`
      : "";
    const heading = more ? "Current state" : `Current state · ${label}`;
    return `<div class="current">
              <p class="heading">${escape(heading)}</p>
              ${rows[0]}
            </div>${rest}`;
  }

  _renderRow(change, spokenFor = false) {
    const newest = this._isNewest(change);
    return renderRow({
      change,
      newest,
      spokenFor,
      matching: newest ? this._matchingElsewhere(change) : [],
      detail: this._open === change.revision ? this._renderDetail(change) : "",
    });
  }

  _render() {
    if (!this.shadowRoot) return;
    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <div class="bar">
        <span>Dashboard History</span>
        ${this._busy ? '<span class="muted" style="font-size:14px">working…</span>' : ""}
        <button class="mode" data-mode="${this._mode === "simple" ? "advanced" : "simple"}"
                >${this._mode === "simple" ? "Advanced view" : "Simple view"}</button>
        <button class="reload" data-refresh="1" title="Reload the history"
                aria-label="Reload the history">\u21bb</button>
      </div>
      ${this._error ? `<div class="banner"><span class="grow">${escape(this._error)}</span></div>` : ""}
      <div class="layout">
        <div class="side">${this._renderSide()}</div>
        <div class="main">
          ${this._selected ? this._renderSearch() : ""}
          ${this._renderMain()}
        </div>
      </div>
      ${DIALOGS}`;

    const root = this.shadowRoot;
    const fold = root.querySelector("details.dead");
    if (fold)
      fold.addEventListener("toggle", () => {
        this._deadOpen = fold.open;
      });
    // Mirrors the fold above: without this, "Back to this version"
    // would appear to collapse its own section, because _guard's
    // preview fetch re-renders before the confirm dialog even opens.
    root.querySelectorAll("details.ver").forEach((element) => {
      const key = element.dataset.key;
      element.addEventListener("toggle", () => {
        if (element.open) this._verOpen.add(key);
        else this._verOpen.delete(key);
      });
    });
    root.querySelectorAll(".dash").forEach((element) =>
      element.addEventListener("click", () =>
        this._select(element.dataset.key),
      ),
    );
    root.querySelectorAll(".change").forEach((element) =>
      element.addEventListener("click", () =>
        this._expand(element.dataset.revision),
      ),
    );
    root.querySelectorAll("[data-restore]").forEach((element) =>
      element.addEventListener("click", () => {
        const change = this._changeAt(this._open);
        const item = this._items.find(
          (candidate) => candidate.position === Number(element.dataset.restore),
        );
        if (change && item) this._restoreItem(change, item);
      }),
    );
    root.querySelectorAll("[data-state]").forEach((element) =>
      element.addEventListener("click", (event) => {
        // Inside a <summary> a click would toggle the section as well.
        event.preventDefault();
        event.stopPropagation();
        // The dialog is titled with the button that opened it. With two
        // of them on a row, a generic heading would leave you guessing
        // which one you pressed.
        this._restoreState(element.dataset.state, element.textContent.trim());
      }),
    );
    root.querySelectorAll("[data-undo]").forEach((element) =>
      element.addEventListener("click", (event) => {
        event.stopPropagation();
        this._undoChange(element.dataset.undo);
      }),
    );
    root.querySelectorAll("[data-forget]").forEach((element) =>
      element.addEventListener("click", () => this._forget()),
    );
    root.querySelectorAll("[data-older]").forEach((element) =>
      element.addEventListener("click", () => this._loadOlder()),
    );
    root.querySelectorAll("[data-refresh]").forEach((element) =>
      // Guarded, unlike the automatic one: somebody who pressed a button
      // is owed both the "working" state and the failure if there is one.
      element.addEventListener("click", () => this._guard(() => this._refresh())),
    );
    root.querySelectorAll("[data-describe]").forEach((element) =>
      element.addEventListener("click", (event) => {
        // Otherwise the click reaches .change underneath and expands the
        // row at the same time.
        event.stopPropagation();
        this._describe(element.dataset.describe);
      }),
    );
    root.querySelectorAll("[data-version]").forEach((element) =>
      element.addEventListener("click", (event) => {
        // Otherwise the click reaches the row underneath and collapses it.
        event.stopPropagation();
        // "now" is the simple mode's button, which means the newest
        // recorded state. Everything else names a revision.
        const which = element.dataset.version;
        this._createVersion(
          which === "now" ? this._changes[0]?.revision : which,
        );
      }),
    );
    root.querySelectorAll("[data-mode]").forEach((element) =>
      element.addEventListener("click", (event) => {
        event.stopPropagation();
        this._setMode(element.dataset.mode);
      }),
    );
    root.querySelectorAll("dialog").forEach((element) =>
      element
        .querySelectorAll(".actions button")
        .forEach((button) =>
          button.addEventListener("click", () => element.close(button.value)),
        ),
    );
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
      // Focus survives the re-render this typing causes; without it the
      // box would lose the caret on every keystroke.
      if (this._query) find.focus();
      find.setSelectionRange?.(find.value.length, find.value.length);
      find.addEventListener("input", () => {
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
