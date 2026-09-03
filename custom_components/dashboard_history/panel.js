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
let escape;
let renderDiff;
let renderPlain;
let when;
let joinNames;

const partsReady = Promise.all([
  import(`./panel/style.js${PARTS}`),
  import(`./panel/render.js${PARTS}`),
]).then(([style, render]) => {
  STYLE = style.STYLE;
  ({ escape, renderDiff, renderPlain, when, joinNames } = render);
});

class DashboardHistoryPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._dashboards = [];
    this._changes = [];
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
    this._busy = false;
    this._error = null;
    this._loaded = false;
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
      const history = await this._call("history", { dashboard: asked });
      // Same race as in `_select`, and reachable from further away: this
      // one is started by an event, so it can be in flight at the moment
      // somebody picks another dashboard. Its answer is dropped, but the
      // list read before it is still current and worth drawing.
      if (this._selected !== asked) {
        this._render();
        return;
      }
      this._changes = history.changes || [];
      // An expanded row keeps its place, but not its answers: after a
      // change from outside, "Put back" would be offering items worked
      // out against a dashboard that has moved on.
      const openAt = this._changes.findIndex((c) => c.revision === this._open);
      if (openAt < 0) {
        this._open = null;
        this._items = [];
        this._explanation = null;
      } else {
        const detail = await this._detailFor(openAt);
        if (this._selected !== asked) return;
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

  async _guard(work) {
    this._busy = true;
    this._error = null;
    this._render();
    try {
      return await work();
    } catch (err) {
      this._error = err?.message || String(err);
      return null;
    } finally {
      this._busy = false;
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
    this._selected = key;
    this._open = null;
    this._items = [];
    this._explanation = null;
    this._undo = null;
    const result = await this._guard(() =>
      this._call("history", { dashboard: key }),
    );
    // Click two dashboards quickly and both requests are in flight. The
    // slower answer arriving last would be written into the list under
    // the name of the dashboard the faster one selected - a history
    // shown beside the wrong title, with buttons that act on the title.
    // Whoever is no longer the selection drops its answer.
    if (this._selected !== key) return;
    this._changes = result ? result.changes || [] : [];
    this._render();
  }

  /**
   * The state *before* a change - which is what "undo this" means.
   * The list runs newest first, so the state before entry i is entry i+1.
   */
  _before(index) {
    return this._changes[index + 1]?.revision ?? null;
  }

  async _expand(index) {
    const change = this._changes[index];
    if (this._open === change.revision) {
      this._open = null;
      this._render();
      return;
    }
    this._open = change.revision;
    this._items = [];
    this._explanation = null;
    this._undo = null;
    this._take(await this._guard(() => this._detailFor(index)));
    this._render();
  }

  /** The three answers a row's detail is built from. */
  _detailFor(index) {
    const before = this._before(index);
    return Promise.all([
      before
        ? this._call("deleted_since", {
            dashboard: this._selected,
            revision: before,
          })
        : Promise.resolve({ items: [] }),
      this._call("explain", {
        dashboard: this._selected,
        revision: this._changes[index].revision,
      }),
      this._call("undo_change", {
        dashboard: this._selected,
        revision: this._changes[index].revision,
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
  async _confirm(title, request) {
    const preview = await this._guard(() => this._call(...request(false)));
    if (!preview) return;
    if (preview.error) {
      this._error = preview.error;
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
    dialog.returnValue = "";
    dialog.showModal();
    const answer = await new Promise((resolve) => {
      dialog.addEventListener("close", () => resolve(dialog.returnValue), {
        once: true,
      });
    });
    if (answer !== "apply") return;
    // Armed before the write: the recorder is quick, and an announcement
    // that arrives first would find nobody waiting.
    const recorded = this._recorded();
    const applied = await this._guard(async () => {
      const result = await this._call(...request(true));
      // Still busy until the recorder has it. Reloading in between reads
      // a history whose newest entry is the state just replaced - so
      // nothing matches the live configuration, nothing is crowned, and
      // the page looks half-built. Measured at 30 to 150 ms of exactly
      // that.
      await recorded;
      return result;
    });
    if (applied?.error) this._error = applied.error;
    else if (applied?.note) this._error = applied.note;
    await this._select(this._selected);
    await this._loadDashboardsQuietly();
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
  async _describe(index) {
    const change = this._changes[index];
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
  async _createVersion(index) {
    const change = this._changes[index];
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
    const already = this._alreadyNamed(index);
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
        ${
          facts.described
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

  _restoreItem(index, item) {
    const before = this._before(index);
    this._confirm(`Put back: ${item.label}`, (confirm) => [
      "restore_deleted",
      {
        dashboard: this._selected,
        revision: before,
        position: item.position,
        confirm,
      },
    ]);
  }

  _restoreState(revision, title) {
    this._confirm(title, (confirm) => [
      "restore_state",
      { dashboard: this._selected, revision, confirm },
    ]);
  }

  _undoChange(index) {
    this._confirm("Undo this change", (confirm) => [
      "undo_change",
      {
        dashboard: this._selected,
        revision: this._changes[index].revision,
        confirm,
      },
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
  _renderSetBack(index) {
    const before = this._before(index);
    const buttons = [];
    const same = this._undo?.available && this._undo.equals_state_before;
    if (before && !this._changes[index + 1]?.same_as_now && !same)
      buttons.push({
        revision: before,
        label: "Back to the state before this change",
      });
    if (!this._changes[index]?.same_as_now)
      buttons.push({
        revision: this._changes[index].revision,
        label: "Back to the state after this change",
      });

    const why =
      before && this._changes[index + 1]?.same_as_now
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

  _renderDetail(index) {
    // Where there is room, both subjects get a full sentence instead of a
    // chip - the explanation says what the change did, this says where it
    // left the dashboard. "again" carries the case the short form cannot:
    // the dashboard may well have changed away and come back since.
    // Not on the top row: the section heading and its chip already say it
    // there, and "again" would be wrong for the state you are simply in.
    const here =
      index > 0 && this._changes[index]?.same_as_now
        ? `<p class="why" style="margin-top:0">The dashboard holds exactly this
             state again right now.</p>`
        : "";
    const plain =
      here + renderPlain(this._explanation, "What this change did");
    const before = this._before(index);
    if (!before)
      return `<div class="detail">${plain}<p class="muted">This is the first
        recorded state, so there is nothing before it to compare against.</p>
        ${this._renderMakeVersion(index)}</div>`;
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
    const added = /\d+ added/.test(this._changes[index]?.message || "");
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

    const kept = index === 0 ? "" : ` and keeps the ${index} change${index === 1 ? "" : "s"} made since`;
    const offer = undo
      ? `<div class="backto">
           <button class="act" data-undo="${index}">Undo this change</button>
         </div>
         <p class="why" style="margin-top:8px">Puts this change back${kept}.</p>`
      : `<p class="why">This change cannot be taken back exactly:
           ${escape(this._undo?.reason || "no reason given")}.</p>`;

    return `<div class="detail">
      ${plain}
      ${offer}
      ${list}
      ${this._renderSetBack(index)}
      ${this._renderMakeVersion(index)}
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
  _alreadyNamed(index) {
    const change = this._changes[index];
    if (!change) return "";
    const carried = (change.versions || []).map((v) => v.name.split("/").pop());
    if (carried.length) return `This state already carries ${this._someNames(carried)}.`;
    const alike = this._matchingElsewhere(index);
    if (alike.length) return `This is the same state as ${this._someNames(alike)}.`;
    return "";
  }

  /**
   * A couple of names, and how many were left out.
   *
   * Measured on the test bench: eighteen versions sat on states equal to
   * the live one, and the chip listed every one of them - a label longer
   * than the row it labelled. A history that goes back and forth while
   * versions are made collects these, and the count is unbounded.
   *
   * Cut, never silently: the project's own rule for the explanation
   * lists is that a summary which omits without saying so is worse than
   * a long one. The tooltip carries all of them.
   *
   * The one named is the first, which is the version on the most recent
   * matching state - not the highest number. Those usually coincide and
   * need not: a version made today on an old state sorts by that state.
   */
  _someNames(names) {
    if (names.length <= 2) return joinNames(names);
    return `${names[0]} and ${names.length - 1} more`;
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
  _matchingElsewhere(index) {
    const change = this._changes[index];
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
  _renderMakeVersion(index) {
    const named = this._alreadyNamed(index);
    return `<div class="mkver">
        <button class="act ghost" data-version="${index}">Version up to here</button>
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
   * `same_as_now` is computed against the live configuration for every
   * entry, so an entry carrying a version and matching now is exactly
   * what is wanted here. Newest-first ordering means these entries are
   * always below the current one.
   */
  _versionsMatchingNow() {
    return this._changes
      .filter((change) => change.same_as_now && (change.versions || []).length)
      .flatMap((change) => change.versions.map((v) => v.name.split("/").pop()));
  }

  /**
   * The history, cut into sections at the versions.
   *
   * A version marks a state, so it marks the *newest* change it contains
   * - the section it heads runs from that change downwards to the next
   * version below. Everything above the topmost version is not in a
   * version yet, and that is the section people work in.
   */
  _sections() {
    const out = [];
    let head = null;
    let rows = [];
    this._changes.forEach((change, index) => {
      const marks = change.versions || [];
      if (marks.length) {
        if (rows.length || head) out.push({ versions: head, rows });
        head = marks;
        rows = [index];
      } else {
        rows.push(index);
      }
    });
    if (rows.length || head) out.push({ versions: head, rows });
    return out;
  }

  /**
   * A section head. Two versions can sit on the same state; both are
   * named rather than one of them being silently dropped.
   *
   * The button disappears when its target is what the dashboard holds
   * already - the same rule the row buttons follow, and for the same
   * reason: offering it there opens a dialog reading "No difference."
   * above a live Apply button.
   */
  _renderVersionHead(section) {
    const [first, ...also] = section.versions;
    const count = section.rows.length;
    const extra = also
      .map((v) => `<span class="also">also ${escape(v.name)} — ${escape(v.title)}</span>`)
      .join("");
    // Two different truths, and one wording for both was an overclaim.
    // A version sitting on the newest entry *is* where the dashboard is.
    // A version further down whose state matches only holds the same
    // thing: going back to it wrote a newer entry, and that entry, not
    // this version, is where you are. Saying "current state" there
    // invites the reading Decision 9 exists to prevent.
    //
    // "same state as now" and not a wording of its own: three places say
    // this one fact, and they said it in two vocabularies until somebody
    // read all three together and asked whether they meant the same
    // thing. They do.
    const top = section.rows[0];
    const here = this._changes[top]?.same_as_now;
    const back = here
      ? `<span class="count">${top === 0 ? "current state" : "same state as now"}</span>`
      : `<button class="act ghost" data-state="${escape(first.name)}"
                 >Back to this version</button>`;
    return `
      <summary>
        <span class="name">${escape(first.name.split("/").pop())}</span>
        <span class="grow">${escape(first.title || first.name)}${extra}</span>
        <span class="count">${count} change${count === 1 ? "" : "s"}</span>
        ${back}
      </summary>`;
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
             ${
               this._changes.length > 1
                 ? `<button class="act" data-state="${escape(this._changes[1].revision)}">
                      Bring it back
                    </button>`
                 : ""
             }
             <button class="act ghost" data-forget="1">Forget for good</button>
           </div>`
        : "";
    if (!this._changes.length)
      return `${banner}<p class="empty muted">No changes recorded for this dashboard.</p>`;

    // Only the first section can be version-less: every later one starts
    // at the change a version sits on. So the unbundled case is handled
    // once, outside the loop, rather than guarded for on every section.
    const sections = this._sections();
    const newest = sections.find((s) => s.versions);
    const label = newest
      ? `Since ${newest.versions[0].name.split("/").pop()}`
      : "Not in a version yet";
    const parts = sections.map((section) => {
      if (!section.versions) return this._renderTopSection(section, label);
      const rows = section.rows
        .map((index, position) =>
          this._renderRow(this._changes[index], index, position === 0),
        )
        .join("");
      const key = section.versions[0].name;
      return `<details class="ver" data-key="${escape(key)}"
                ${this._verOpen.has(key) ? "open" : ""}>
                ${this._renderVersionHead(section)}
                <div class="inner">${rows}</div>
              </details>`;
    });
    return banner + parts.join("");
  }

  /**
   * The newest entry is set apart when it is provably the state in front
   * of you. Provably: after a change made at Home Assistant's back it is
   * not, and then nothing is crowned rather than the wrong thing.
   */
  _renderTopSection(section, label) {
    const rows = section.rows.map((index) =>
      this._renderRow(this._changes[index], index),
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
           ${escape(this._someNames(matching))}.</span>`
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

  _renderRow(change, index, spokenFor = false) {
    // The word "state" in both chips is load-bearing, and it was missing.
    //
    // A row says two things about two different subjects: the message is
    // about the *change*, the chip about the *state it left behind*. Read
    // as one sentence, "4 moved · same as now" is a contradiction - four
    // cards moved, and yet nothing differs? Both halves were true and the
    // row still misled, because nothing named what each half was about.
    //
    // The other difference the chips carry: the top entry is where you
    // are. A lower entry can hold byte-identical content without being
    // where you are - move a card up and down and there is a whole run of
    // them, all worded alike.
    // `spokenFor` is the first row of a version section, and its head
    // carries the same chip a few pixels above it. Two identical labels
    // stacked is not emphasis, it is noise - and it was measurable: the
    // head read "same content as now" while the row under it read "same
    // state as now", one fact wearing two coats.
    const chip =
      spokenFor || !change.same_as_now
        ? ""
        : index === 0
          ? `<span class="chip now"
                 title="This is the state the dashboard holds right now."
                 >current state</span>`
          : `<span class="chip sameas"
                   title="The change described here left the dashboard in exactly the state it holds right now."
                   >same state as now</span>`;
    // Beside "current state" rather than in a sentence under the card.
    // Both said the same thing; only one of them sits inside the frame
    // the eye stops at, and the sentence below was read past. Kept short
    // for the same reason - a chip is a label, not a statement - with
    // the part that cannot fit moved into the tooltip, where "a
    // different entry" is spelled out. It says "identical in content
    // to", never "is": going back to a version writes a new entry, and
    // this is that entry, not that version.
    const matches = index === 0 ? this._matchingElsewhere(index) : [];
    const named = matches.length
      ? `<span class="chip ver"
               title="A different entry that holds exactly what ${escape(joinNames(matches))} holds. Going back to a version writes a new entry; this is that entry."
               >same state as ${escape(this._someNames(matches))}</span>`
      : "";
    return `
        <div class="card">
          <div class="change" data-index="${index}">
            <span class="what">${escape(change.description || change.message)}${chip}${named}
              ${change.description ? `<span class="auto">${escape(change.message)}</span>` : ""}
            </span>
            <span class="when">${escape(when(change.timestamp))}</span>
            <span class="rev">${escape(change.revision.slice(0, 7))}</span>
            <button class="pen" data-describe="${index}"
                    title="Describe this change">\u270e</button>
          </div>
          ${this._open === change.revision ? this._renderDetail(index) : ""}
        </div>`;
  }

  _render() {
    if (!this.shadowRoot) return;
    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <div class="bar">
        <span>Dashboard History</span>
        ${this._busy ? '<span class="muted" style="font-size:14px">working…</span>' : ""}
        <button class="reload" data-refresh="1" title="Reload the history"
                aria-label="Reload the history">\u21bb</button>
      </div>
      ${this._error ? `<div class="banner"><span class="grow">${escape(this._error)}</span></div>` : ""}
      <div class="layout">
        <div class="side">${this._renderSide()}</div>
        <div class="main">${this._renderMain()}</div>
      </div>
      <dialog class="confirm">
        <h2></h2>
        <div class="body"></div>
        <div class="actions">
          <span class="note muted" style="margin-right:auto"></span>
          <button class="act ghost" value="cancel">Cancel</button>
          <button class="act" value="apply">Apply</button>
        </div>
      </dialog>
      <dialog class="forget">
        <h2>Forget this dashboard for good</h2>
        <div class="body"></div>
        <div class="actions">
          <button class="act ghost" value="cancel">Cancel</button>
          <button class="act danger" value="forget">Delete for good</button>
        </div>
      </dialog>
      <dialog class="describe">
        <h2>Describe this change</h2>
        <div class="body" style="padding:0 16px 8px">
          <input class="text" type="text" maxlength="200"
                 placeholder="Why did you change this?">
          <p class="muted" style="font-size:13px">
            This becomes the headline of the entry. The automatic message
            stays below it. Leave it empty to remove the description.
          </p>
        </div>
        <div class="actions">
          <button class="act ghost" value="cancel">Cancel</button>
          <button class="act" value="save">Save</button>
        </div>
      </dialog>
      <dialog class="version">
        <h2>Create a version</h2>
        <div class="body" style="padding:0 16px 8px">
          <p class="muted" style="font-size:13px" data-scope></p>
          <p class="carries" data-carries hidden></p>
          <div class="levels">
            <button type="button" data-level="patch" aria-pressed="true">
              <strong></strong><span>Patch</span>
            </button>
            <button type="button" data-level="minor" aria-pressed="false">
              <strong></strong><span>Minor</span>
            </button>
            <button type="button" data-level="major" aria-pressed="false">
              <strong></strong><span>Major</span>
            </button>
          </div>
          <input class="text title" type="text" maxlength="200"
                 placeholder="What is this version?">
          <input class="text desc" type="text" maxlength="500"
                 style="margin-top:8px"
                 placeholder="Anything more worth remembering (optional)">
        </div>
        <div class="actions">
          <button class="act ghost" value="cancel">Cancel</button>
          <button class="act" value="create">Create</button>
        </div>
      </dialog>`;

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
        this._expand(Number(element.dataset.index)),
      ),
    );
    root.querySelectorAll("[data-restore]").forEach((element) =>
      element.addEventListener("click", () => {
        const index = this._changes.findIndex(
          (change) => change.revision === this._open,
        );
        const item = this._items.find(
          (candidate) => candidate.position === Number(element.dataset.restore),
        );
        this._restoreItem(index, item);
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
        this._undoChange(Number(element.dataset.undo));
      }),
    );
    root.querySelectorAll("[data-forget]").forEach((element) =>
      element.addEventListener("click", () => this._forget()),
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
        this._describe(Number(element.dataset.describe));
      }),
    );
    root.querySelectorAll("[data-version]").forEach((element) =>
      element.addEventListener("click", (event) => {
        // Otherwise the click reaches the row underneath and collapses it.
        event.stopPropagation();
        this._createVersion(Number(element.dataset.version));
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
