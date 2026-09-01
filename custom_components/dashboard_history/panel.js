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

const STYLE = `
  :host {
    display: block;
    height: 100%;
    background: var(--primary-background-color, #f5f5f5);
    color: var(--primary-text-color, #212121);
    font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif);
  }
  .bar {
    display: flex;
    align-items: center;
    gap: 16px;
    height: 56px;
    padding: 0 16px;
    background: var(--app-header-background-color, var(--primary-color, #03a9f4));
    color: var(--app-header-text-color, #fff);
    font-size: 20px;
    box-sizing: border-box;
  }
  .layout { display: flex; align-items: stretch; height: calc(100% - 56px); }
  .side {
    width: 280px;
    flex: 0 0 280px;
    overflow-y: auto;
    border-right: 1px solid var(--divider-color, #e0e0e0);
    background: var(--card-background-color, #fff);
  }
  .main { flex: 1 1 auto; overflow-y: auto; padding: 16px; }
  .dash {
    display: flex;
    flex-direction: column;
    gap: 2px;
    width: 100%;
    padding: 12px 16px;
    border: 0;
    border-bottom: 1px solid var(--divider-color, #e0e0e0);
    background: none;
    color: inherit;
    font: inherit;
    text-align: left;
    cursor: pointer;
  }
  .dash:hover { background: var(--secondary-background-color, #fafafa); }
  .dash[aria-current="true"] {
    background: var(--secondary-background-color, #fafafa);
    box-shadow: inset 3px 0 0 var(--primary-color, #03a9f4);
  }
  .dash .key { font-size: 12px; color: var(--secondary-text-color, #727272); }
  .gone {
    display: inline-block;
    margin-left: 6px;
    padding: 0 6px;
    border-radius: 8px;
    background: var(--error-color, #db4437);
    color: #fff;
    font-size: 11px;
    vertical-align: 1px;
  }
  details.dead > summary {
    padding: 12px 16px;
    border-bottom: 1px solid var(--divider-color, #e0e0e0);
    color: var(--secondary-text-color, #727272);
    font-size: 12px;
    font-weight: 500;
    letter-spacing: .06em;
    text-transform: uppercase;
    cursor: pointer;
  }
  .card {
    margin-bottom: 12px;
    border-radius: 8px;
    background: var(--card-background-color, #fff);
    box-shadow: var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,.15));
    overflow: hidden;
  }
  .change { display: flex; align-items: baseline; gap: 12px; padding: 14px 16px; cursor: pointer; }
  .change:hover { background: var(--secondary-background-color, #fafafa); }
  .change .what { flex: 1 1 auto; font-weight: 500; }
  .change .when { color: var(--secondary-text-color, #727272); font-size: 13px; white-space: nowrap; }
  .change .rev { color: var(--secondary-text-color, #727272); font-family: monospace; font-size: 12px; }
  .detail { padding: 0 16px 16px; border-top: 1px solid var(--divider-color, #e0e0e0); }
  .item {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 8px 0;
    border-bottom: 1px solid var(--divider-color, #eee);
  }
  .item .label { flex: 1 1 auto; }
  .item .where { color: var(--secondary-text-color, #727272); font-size: 12px; }
  button.act {
    padding: 6px 14px;
    border: 0;
    border-radius: 4px;
    background: var(--primary-color, #03a9f4);
    color: var(--text-primary-color, #fff);
    font: inherit;
    cursor: pointer;
  }
  button.act.ghost {
    background: none;
    color: var(--primary-color, #03a9f4);
    border: 1px solid var(--divider-color, #e0e0e0);
  }
  button.act[disabled] { opacity: .5; cursor: default; }
  .muted { color: var(--secondary-text-color, #727272); }
  .empty { padding: 32px 16px; text-align: center; }
  .banner {
    display: flex;
    align-items: center;
    gap: 16px;
    margin-bottom: 12px;
    padding: 16px;
    border-radius: 8px;
    background: var(--error-color, #db4437);
    color: #fff;
  }
  .banner .grow { flex: 1 1 auto; }
  .banner button.act { background: #fff; color: var(--error-color, #db4437); }
  .banner button.act.ghost {
    background: none;
    color: #fff;
    border: 1px solid rgba(255, 255, 255, .7);
  }
  button.act.danger { background: var(--error-color, #db4437); color: #fff; }
  dialog .loss { margin: 12px 0; padding-left: 18px; }
  dialog .loss li { margin: 4px 0; }
  dialog {
    width: min(900px, 92vw);
    padding: 0;
    border: 0;
    border-radius: 8px;
    background: var(--card-background-color, #fff);
    color: var(--primary-text-color, #212121);
  }
  dialog::backdrop { background: rgba(0,0,0,.4); }
  dialog h2 { margin: 0; padding: 16px; font-size: 18px; }
  dialog .body { max-height: 55vh; overflow: auto; padding: 0 16px; }
  dialog .actions { display: flex; justify-content: flex-end; gap: 8px; padding: 16px; }
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
  .change .pen {
    padding: 4px 8px;
    border: 0;
    border-radius: 4px;
    background: none;
    color: var(--secondary-text-color, #727272);
    font: inherit;
    font-size: 15px;
    cursor: pointer;
    opacity: 0;
  }
  .change:hover .pen, .change .pen:focus { opacity: 1; }
  .change .what .auto {
    display: block;
    margin-top: 2px;
    color: var(--secondary-text-color, #727272);
    font-size: 13px;
    font-weight: 400;
  }
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
  .chip {
    display: inline-block;
    margin-left: 8px;
    padding: 0 8px;
    border-radius: 8px;
    font-size: 11px;
    font-weight: 500;
    vertical-align: 1px;
    white-space: nowrap;
  }
  .chip.now { background: var(--primary-color, #03a9f4); color: #fff; }
  .chip.sameas {
    background: var(--secondary-background-color, #eee);
    color: var(--secondary-text-color, #727272);
  }
  .current .card { box-shadow: 0 0 0 2px var(--primary-color, #03a9f4); }
  .heading {
    margin: 0 0 8px;
    color: var(--secondary-text-color, #727272);
    font-size: 12px;
    font-weight: 500;
    letter-spacing: .08em;
    text-transform: uppercase;
  }
  .divider {
    display: flex;
    align-items: center;
    gap: 12px;
    margin: 20px 0 12px;
    color: var(--secondary-text-color, #727272);
    font-size: 12px;
    font-weight: 500;
    letter-spacing: .08em;
    text-transform: uppercase;
  }
  .divider::before, .divider::after {
    content: "";
    flex: 1 1 auto;
    height: 1px;
    background: var(--divider-color, #e0e0e0);
  }
  .why {
    display: block;
    margin-top: 16px;
    color: var(--secondary-text-color, #727272);
    font-size: 13px;
  }
  .plain { margin: 0 0 12px; }
  .plain h3 { margin: 0 0 8px; font-size: 15px; }
  .plain .view {
    margin: 0 0 10px;
    padding-left: 12px;
    border-left: 3px solid var(--divider-color, #e0e0e0);
  }
  .plain .view > strong { display: block; font-size: 13px; }
  .plain ul { margin: 4px 0 0; padding-left: 18px; }
  .plain li { margin: 2px 0; }
  .plain li.removed { color: var(--error-color, #db4437); }
  .plain li.added { color: var(--success-color, #0f9d58); }
  .plain .note { margin: 8px 0 0; font-size: 13px; }
  details.raw > summary {
    padding: 8px 0;
    color: var(--secondary-text-color, #727272);
    font-size: 13px;
    cursor: pointer;
  }
  pre .add { color: var(--success-color, #0f9d58); }
  pre .del { color: var(--error-color, #db4437); }
  pre .at { color: var(--secondary-text-color, #727272); }
`;

const escape = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (character) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        character
      ],
  );

/** A unified diff, coloured the way people expect to read one. */
const renderDiff = (diff) => {
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

/**
 * The same difference in words. It sits above the diff, not instead of
 * it: the diff is the exact account, and it stays.
 */
const renderPlain = (explanation, heading) => {
  if (!explanation) return "";
  const groups = (explanation.groups || [])
    .map(
      (group) => `
      <div class="view">
        <strong>In the view ${escape(group.view)}</strong>
        <ul>
          ${group.entries
            .map(
              (entry) =>
                `<li class="${escape(entry.kind)}">${escape(entry.text)}</li>`,
            )
            .join("")}
          ${group.more ? `<li class="muted">and ${escape(group.more)} more</li>` : ""}
        </ul>
      </div>`,
    )
    .join("");
  const note = explanation.note
    ? `<p class="note muted">${escape(explanation.note)}</p>`
    : "";
  return `<div class="plain"><h3>${escape(heading)}</h3>${groups}${note}</div>`;
};

const when = (timestamp) =>
  new Date(timestamp * 1000).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
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
    this._busy = false;
    this._error = null;
    this._loaded = false;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._loaded) {
      this._loaded = true;
      this._loadDashboards();
    }
  }

  get hass() {
    return this._hass;
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
    const result = await this._guard(() =>
      this._call("history", { dashboard: key }),
    );
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
    const before = this._before(index);
    const answers = await this._guard(() =>
      Promise.all([
        before
          ? this._call("deleted_since", {
              dashboard: this._selected,
              revision: before,
            })
          : Promise.resolve({ items: [] }),
        this._call("explain", {
          dashboard: this._selected,
          revision: change.revision,
        }),
      ]),
    );
    const [missing, explanation] = answers || [null, null];
    this._items = missing ? missing.items || [] : [];
    this._explanation = explanation;
    this._render();
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
    const applied = await this._guard(() => this._call(...request(true)));
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
   * The button that sets the whole dashboard back, or the reason there is
   * none. Its target is the state *before* this change - see the note at
   * the top of this file - so it is pointless exactly when that state is
   * what the dashboard holds already. On a history that went back and
   * forth that is every second row, and offering it there produced a
   * dialog reading "No difference." above a live Apply button.
   */
  _renderSetBack(index) {
    const before = this._before(index);
    if (!before) return "";
    if (this._changes[index + 1]?.same_as_now)
      return `<span class="why">The state before this change is what the
        dashboard holds now — nothing to set back.</span>`;
    const label =
      index === 0
        ? "Undo this change"
        : "Set the dashboard back to before this change";
    return `<div style="margin-top:16px">
        <button class="act ghost" data-state="${escape(before)}">${label}</button>
      </div>`;
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
        recorded state, so there is nothing before it to compare against.</p></div>`;
    const list = this._items.length
      ? this._items
          .map(
            (item) => `
          <div class="item">
            <span class="label">${escape(item.label)}
              <span class="where">${escape(item.kind)}${item.view ? ` · view ${escape(item.view)}` : ""}</span>
            </span>
            <button class="act" data-restore="${item.position}">Put back</button>
          </div>`,
          )
          .join("")
      : `<p class="muted">Nothing from before this change is missing today.</p>`;
    return `<div class="detail">
      ${plain}
      ${list}
      ${this._renderSetBack(index)}
    </div>`;
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

    // The newest entry is set apart when it is provably the state in front
    // of you. Provably: after a change made at Home Assistant's back it is
    // not, and then nothing is crowned rather than the wrong thing.
    const topIsCurrent = Boolean(this._changes[0].same_as_now);
    const rows = this._changes.map((change, index) => this._renderRow(change, index));
    if (!topIsCurrent) return banner + rows.join("");
    return (
      banner +
      `<div class="current">
         <p class="heading">Current state</p>
         ${rows[0]}
       </div>` +
      (rows.length > 1
        ? `<div class="divider">History</div>${rows.slice(1).join("")}`
        : "")
    );
  }

  _renderRow(change, index) {
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
    const chip =
      index === 0 && change.same_as_now
        ? `<span class="chip now"
                 title="This is the state the dashboard holds right now."
                 >current state</span>`
        : change.same_as_now
          ? `<span class="chip sameas"
                   title="The change described here left the dashboard in exactly the state it holds right now."
                   >same state as now</span>`
          : "";
    return `
        <div class="card">
          <div class="change" data-index="${index}">
            <span class="what">${escape(change.description || change.message)}${chip}
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
      </dialog>`;

    const root = this.shadowRoot;
    const fold = root.querySelector("details.dead");
    if (fold)
      fold.addEventListener("toggle", () => {
        this._deadOpen = fold.open;
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
      element.addEventListener("click", () =>
        this._restoreState(
          element.dataset.state,
          "Set the dashboard back to this state",
        ),
      ),
    );
    root.querySelectorAll("[data-forget]").forEach((element) =>
      element.addEventListener("click", () => this._forget()),
    );
    root.querySelectorAll("[data-describe]").forEach((element) =>
      element.addEventListener("click", (event) => {
        // Otherwise the click reaches .change underneath and expands the
        // row at the same time.
        event.stopPropagation();
        this._describe(Number(element.dataset.describe));
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

customElements.define("dashboard-history-panel", DashboardHistoryPanel);
