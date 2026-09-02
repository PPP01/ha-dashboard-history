/* The panel's stylesheet, kept apart so panel.js stays readable. */

export const STYLE = `
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
  .backto {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 16px;
  }
  .mkver {
    display: flex;
    margin-top: 8px;
  }
  .why {
    display: block;
    margin-top: 16px;
    color: var(--secondary-text-color, #727272);
    font-size: 13px;
  }
  /* The same voice as .why, in a dialog body rather than a row. */
  .keeps {
    margin: 0 0 12px;
    color: var(--secondary-text-color, #727272);
    font-size: 13px;
  }
  /* Deliberately not muted: it sits under the muted scope line, and a
     second grey sentence there reads as more small print to skip. */
  .carries {
    margin: 0 0 8px;
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
  details.ver { margin-bottom: 12px; }
  details.ver > summary {
    display: flex;
    align-items: baseline;
    gap: 12px;
    padding: 10px 16px;
    border-radius: 8px;
    background: var(--card-background-color, #fff);
    box-shadow: var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,.15));
    cursor: pointer;
  }
  details.ver > summary .name {
    font-family: monospace;
    font-weight: 500;
    color: var(--primary-color, #03a9f4);
  }
  details.ver > summary .grow { flex: 1 1 auto; }
  details.ver > summary .count {
    color: var(--secondary-text-color, #727272);
    font-size: 13px;
  }
  details.ver > .inner { padding: 12px 0 0 16px; }
  details.ver .also {
    display: block;
    margin-top: 2px;
    font-size: 12px;
    color: var(--secondary-text-color, #727272);
  }
  .levels { display: flex; gap: 8px; margin: 12px 0; }
  .levels button {
    flex: 1 1 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 10px;
    border: 1px solid var(--divider-color, #e0e0e0);
    border-radius: 4px;
    background: none;
    color: inherit;
    font: inherit;
    cursor: pointer;
  }
  .levels button[aria-pressed="true"] {
    border-color: var(--primary-color, #03a9f4);
    box-shadow: inset 0 0 0 1px var(--primary-color, #03a9f4);
  }
  .levels button strong { font-family: monospace; font-size: 15px; }
  .levels button span {
    color: var(--secondary-text-color, #727272);
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: .06em;
  }
`;
