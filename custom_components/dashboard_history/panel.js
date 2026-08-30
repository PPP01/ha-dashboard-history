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
    const first = this._dashboards.find((d) => !d.exists) || this._dashboards[0];
    if (first) await this._select(first.key);
  }

  async _select(key) {
    this._selected = key;
    this._open = null;
    this._items = [];
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
    const before = this._before(index);
    if (before) {
      const result = await this._guard(() =>
        this._call("deleted_since", {
          dashboard: this._selected,
          revision: before,
        }),
      );
      this._items = result ? result.items || [] : [];
    }
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
    const dialog = this.shadowRoot.querySelector("dialog");
    dialog.querySelector("h2").textContent = title;
    dialog.querySelector(".body").innerHTML = renderDiff(preview.preview);
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

  _renderSide() {
    if (!this._dashboards.length)
      return '<p class="empty muted">Nothing recorded yet.</p>';
    return this._dashboards
      .map(
        (d) => `
        <button class="dash" data-key="${escape(d.key)}"
                aria-current="${d.key === this._selected}">
          <span>${escape(d.title)}${d.exists ? "" : '<span class="gone">deleted</span>'}</span>
          <span class="key">${escape(d.key)}</span>
        </button>`,
      )
      .join("");
  }

  _renderDetail(index) {
    const before = this._before(index);
    if (!before)
      return `<div class="detail"><p class="muted">This is the first recorded
        state, so there is nothing before it to compare against.</p></div>`;
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
      ${list}
      <div style="margin-top:16px">
        <button class="act ghost" data-state="${escape(before)}">
          Set the whole dashboard back to before this change
        </button>
      </div>
    </div>`;
  }

  _renderMain() {
    if (!this._selected)
      return '<p class="empty muted">Pick a dashboard on the left.</p>';
    const dashboard = this._dashboards.find((d) => d.key === this._selected);
    const banner =
      dashboard && !dashboard.exists && this._changes.length > 1
        ? `<div class="banner">
             <span class="grow">This dashboard was deleted. Its history is
               still here, and so is everything that was on it.</span>
             <button class="act" data-state="${escape(this._changes[1].revision)}">
               Bring it back
             </button>
           </div>`
        : "";
    if (!this._changes.length)
      return `${banner}<p class="empty muted">No changes recorded for this dashboard.</p>`;
    const rows = this._changes
      .map(
        (change, index) => `
        <div class="card">
          <div class="change" data-index="${index}">
            <span class="what">${escape(change.message)}</span>
            <span class="when">${escape(when(change.timestamp))}</span>
            <span class="rev">${escape(change.revision.slice(0, 7))}</span>
          </div>
          ${this._open === change.revision ? this._renderDetail(index) : ""}
        </div>`,
      )
      .join("");
    return banner + rows;
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
      <dialog>
        <h2></h2>
        <div class="body"></div>
        <div class="actions">
          <span class="note muted" style="margin-right:auto"></span>
          <button class="act ghost" value="cancel">Cancel</button>
          <button class="act" value="apply">Apply</button>
        </div>
      </dialog>`;

    const root = this.shadowRoot;
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
    const dialog = root.querySelector("dialog");
    dialog.querySelectorAll(".actions button").forEach((element) =>
      element.addEventListener("click", () => dialog.close(element.value)),
    );
  }
}

customElements.define("dashboard-history-panel", DashboardHistoryPanel);
