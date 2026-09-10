/* The panel's stylesheet, kept apart so panel.js stays readable. */

export const STYLE = `
  :host {
    display: block;
    height: 100%;
    background: var(--primary-background-color, #f5f5f5);
    color: var(--primary-text-color, #212121);
    font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif);
    --sc-bg: #f1f5f9;
    --sc-border: #e2e8f0;
    --sc-text-muted: #64748b;
    --sc-text-active: #0f172a;
    --sc-card-active: #ffffff;
    --sc-hover-bg: rgba(255, 255, 255, 0.45);
    --sc-accent: #2563eb;
  }
  @media (prefers-color-scheme: dark) {
    :host {
      --sc-bg: #1e293b;
      --sc-border: #334155;
      --sc-text-muted: #94a3b8;
      --sc-text-active: #f8fafc;
      --sc-card-active: #0f172a;
      --sc-hover-bg: rgba(255, 255, 255, 0.05);
      --sc-accent: #60a5fa;
    }
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
    /* Sticky and not fixed, which was the ask but not the better fit:
       fixed leaves the flow, so the layout under it jumps up by 56px
       and has to be padded back down, and a fixed bar has to be told
       its own width. Sticky keeps its place and its width and stops at
       the top of whichever ancestor scrolls - the page when the panel
       is taller than the window, and nothing at all when it is not,
       which is exactly when there is nothing to stick to anyway. */
    position: sticky;
    top: 0;
    /* Above the cards, and above the spinner's veil, so the bar stays
       readable while the middle of the screen is greyed out. */
    z-index: 4;
  }
  /* The dashboard being looked at, named where the eye already is. It
     shrinks before the buttons do and gives up with an ellipsis: a long
     title must not push the reload button off a narrow window. */
  .bar .which {
    font-size: 16px;
    font-weight: 500;
    opacity: .9;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  /* Pushed to the far end by margin, not by a spacer element: the bar is
     a flex row and "working..." comes and goes between the two. */
  .bar .reload {
    margin-left: auto;
    padding: 2px 10px 4px;
    border: 1px solid currentColor;
    border-radius: 4px;
    background: transparent;
    color: inherit;
    font-size: 18px;
    line-height: 1.2;
    cursor: pointer;
    opacity: .8;
  }
  .bar .reload:hover { opacity: 1; }
  .layout { display: flex; align-items: stretch; height: calc(100% - 56px); }
  .side {
    width: 280px;
    flex: 0 0 280px;
    overflow-y: auto;
    border-right: 1px solid var(--divider-color, #e0e0e0);
    background: var(--card-background-color, #fff);
  }
  /* Holds the main column and the spinner that covers it. The wrapper
     exists so the veil can sit still: laid inside .main, which is the
     element that scrolls, it would be pinned to the content and scroll
     out of sight the moment anybody moved. */
  .mainwrap {
    position: relative;
    flex: 1 1 auto;
    display: flex;
    min-width: 0;
  }
  .main { flex: 1 1 auto; overflow-y: auto; padding: 16px; }
  /* Over the main column only. The sidebar stays live underneath, and
     so does everything else: pointer-events none means this says
     what is happening without taking the page away while it happens. */
  /* Covers the whole main column, however tall it is. The ring inside
     is *not* centred in it: this panel is often taller than the window
     - the page scrolls, which is why the bar is sticky - and a ring
     centred in the column came out at y=1326 in a 950px window, which
     is to say nowhere. Measured in Chrome on 2026-09-07. */
  .spin {
    position: absolute;
    inset: 0;
    pointer-events: none;
  }
  /* The veil is a layer of its own and not an opacity on the whole
     overlay: opacity applies to every child and cannot be taken back
     from the inside, so the ring faded with the page behind it and came
     out invisible - seen in a screenshot, not in a test, because the
     element was there all along. */
  .spin::before {
    content: "";
    position: absolute;
    inset: 0;
    background: var(--primary-background-color, #f5f5f5);
    opacity: .6;
  }
  /* Sticky just under the bar, and centred across the column: wherever
     somebody has scrolled to, the ring is in front of them rather than
     in the middle of a column they cannot see. Above the veil because
     it is a later sibling of the ::before that draws it. */
  .spin .ring {
    position: sticky;
    top: 84px;
    display: block;
    box-sizing: border-box;
    width: 40px;
    height: 40px;
    margin: 28px auto 0;
    border: 4px solid var(--divider-color, #bdbdbd);
    border-top-color: var(--primary-color, #03a9f4);
    border-radius: 50%;
    animation: dh-spin .9s linear infinite;
    will-change: transform;
  }
  .ring.mini {
    display: inline-block;
    vertical-align: middle;
    width: 14px;
    height: 14px;
    margin: 0 8px 0 0;
    border: 2px solid var(--divider-color, #bdbdbd);
    border-top-color: var(--primary-color, #03a9f4);
    border-radius: 50%;
    animation: dh-spin .9s linear infinite;
    will-change: transform;
  }
  .row-loading {
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 8px 0;
  }
  @keyframes dh-spin { to { transform: rotate(360deg); } }
  /* Reduced motion: keep the ring turning at a gentle pace rather than
     stopping it, so an in-flight operation does not look frozen. */
  @media (prefers-reduced-motion: reduce) {
    .spin .ring, .ring.mini { animation: dh-spin 2s linear infinite; }
  }
  /* Read out, never shown. */
  .sr {
    position: absolute;
    width: 1px;
    height: 1px;
    margin: -1px;
    padding: 0;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
    border: 0;
  }
  .search { display:flex; align-items:center; gap:12px; margin-bottom:12px; }
  .search .find { flex:1; }
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
  details.fold > summary {
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
  /* One rule for every pen: the one on a change, the one on a version
     row in the simple mode, the one on a section head in the advanced
     one. Written for the first alone, it was copied twice before the
     third asked to exist.

     The pointer-events line, and not opacity alone. An invisible
     button is still a click target, so a hidden pen sat in the corner
     of a row taking taps meant for the row behind it - and that is
     true wherever it is hidden, not only on a device with no pointer
     at all. */
  .pen {
    padding: 4px 8px;
    border: 0;
    border-radius: 4px;
    background: none;
    color: var(--secondary-text-color, #727272);
    font: inherit;
    font-size: 15px;
    cursor: pointer;
    opacity: 0;
    pointer-events: none;
  }
  /* Revealed by a class on whatever carries the pen, rather than by a
     list of the things that do. The list had grown to three selectors
     living far from the markup they name, and the failure mode of a
     fourth place forgetting itself is silent invisibility - which is
     why look_at_panel.py had to grow a check reading the computed
     opacity. Keyboard focus reveals it too, or the pen would be
     reachable by Tab and still not visible. */
  .penholder:hover .pen, .pen:focus {
    opacity: 1;
    pointer-events: auto;
  }
  /* The bin borrows the pen's shape and reveal - see bin() in
     rows.js - and differs only where it is about to take something
     away: on hover it says so in the warning colour rather than
     staying grey like the pen beside it. Not red in its resting
     state, because it sits on every version row and a row of red
     glyphs reads as a list of problems. */
  .bin:hover, .bin:focus {
    color: var(--error-color, #db4437);
  }
  /* Where there is no pointer there is no hover, and a control that
     only appears on hover is a control that does not exist. Since the
     simple mode is the one opened on a phone, and renaming a version is
     one of the three things it offers - going back, renaming, removing
     - they are all shown there. */
  @media (hover: none) {
    .pen { opacity: 1; pointer-events: auto; }
  }
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
  /* The same muted look as "sameas": the blue "current state" stays the
     one signal, and this rides along beside it. Allowed to wrap, unlike
     the other chips - it carries a version name and a narrow window
     should break the line rather than the layout. */
  .chip.ver {
    background: var(--secondary-background-color, #eee);
    color: var(--secondary-text-color, #727272);
    white-space: normal;
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
    align-items: center;
    flex-wrap: wrap;
    gap: 10px;
    margin-top: 8px;
  }
  .mkver .named {
    color: var(--secondary-text-color, #727272);
    font-size: 13px;
  }
  .why {
    display: block;
    margin-top: 16px;
    color: var(--secondary-text-color, #727272);
    font-size: 13px;
  }
  /* The line a removal dialog opens with: which version this is, and
     underneath it in the muted voice the words somebody gave it. They
     belong to what the version *is*, so they sit in the identity block
     rather than down among the consequences - between the note and its
     list, which is where they were first put, they cut a sentence in
     two on the way to its own bullets.

     Set off by a line's worth of space and not by the 16px that .why
     carries in a row: there it separates two unrelated things, here it
     joins two halves of one.

     No backticks in this comment, and that is not a style note - see
     the rule two hundred lines up. This file is one template literal;
     a backtick ends the string and takes the file apart. Written with
     them once on 2026-09-08 and again on 2026-09-09, both times caught
     by test_the_style_is_one_unbroken_template_literal within the
     minute, which is exactly what that test is for. */
  dialog .who { margin-bottom: 18px; }
  dialog .who .why { margin-top: 4px; }
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
  .detail details.raw pre {
    margin-top: 4px;
    margin-bottom: 8px;
    max-height: 400px;
    overflow: auto;
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
  /* The pen on a second version named in the same head belongs to a
     12px line, not to the row. At the shared size it stood a third
     taller than the words it sits in and pulled the eye off them. */
  details.ver .also .pen { padding: 0 6px; font-size: 12px; }
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
  details.more { margin-top: 16px; }
  details.more > summary {
    color: var(--secondary-text-color, #727272);
    font-size: 13px;
    cursor: pointer;
  }
  details.more > summary:hover { color: var(--primary-text-color, #212121); }
  /* Segmented control: Simple / Advanced switcher */
  .segmented-control {
    all: unset;
    display: inline-flex;
    vertical-align: middle;
  }
  .segmented-control__track {
    position: relative;
    display: grid;
    grid-template-columns: 1fr 1fr;
    background-color: var(--sc-bg);
    border: 1px solid var(--sc-border);
    border-radius: 8px;
    padding: 2px;
    box-sizing: border-box;
    user-select: none;
    height: 26px;
    align-items: center;
  }
  .segmented-control__glider {
    position: absolute;
    top: 2px;
    bottom: 2px;
    left: 2px;
    width: calc((100% - 4px) / 2);
    background-color: var(--sc-card-active);
    border-radius: 6px;
    box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.08), 0 1px 2px -1px rgba(0, 0, 0, 0.06);
    pointer-events: none;
    z-index: 1;
    transition: transform 0.24s cubic-bezier(0.16, 1, 0.3, 1);
  }
  @media (prefers-reduced-motion: reduce) {
    .segmented-control__glider {
      transition: none;
    }
  }
  .segmented-control__track:has(input[value="advanced"]:checked) .segmented-control__glider {
    transform: translateX(100%);
  }
  .segmented-control__option {
    position: relative;
    z-index: 2;
    display: flex;
    margin: 0;
    cursor: pointer;
    height: 100%;
  }
  .segmented-control__option input[type="radio"] {
    position: absolute;
    opacity: 0;
    width: 0;
    height: 0;
    pointer-events: none;
    margin: 0;
  }
  .segmented-control__label {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 100%;
    gap: 6px;
    padding: 0 10px;
    font-family: inherit;
    font-size: 12px;
    font-weight: 500;
    color: var(--sc-text-muted);
    border-radius: 6px;
    line-height: 1;
    transition: color 0.18s ease, background-color 0.18s ease;
    white-space: nowrap;
  }
  .segmented-control__icon {
    width: 14px;
    height: 14px;
    opacity: 0.7;
    transition: opacity 0.18s ease;
    flex-shrink: 0;
  }
  .segmented-control__option:hover input:not(:checked) + .segmented-control__label {
    color: var(--sc-text-active);
    background-color: var(--sc-hover-bg);
  }
  .segmented-control__option:hover input:not(:checked) + .segmented-control__label .segmented-control__icon {
    opacity: 0.95;
  }
  .segmented-control__option input:checked + .segmented-control__label {
    color: var(--sc-text-active);
    font-weight: 600;
  }
  .segmented-control__option input:checked + .segmented-control__label .segmented-control__icon {
    opacity: 1;
  }
  .segmented-control__option input:focus-visible + .segmented-control__label {
    outline: 2px solid var(--sc-accent);
    outline-offset: 1px;
  }
  /* The card the versions wear, so that the box above them is not the
     one thing on the page drawn in another language - and the outline
     the advanced mode puts round its current-state card, out of the
     same variable. That box and this one are one subject seen from two
     modes, so they are marked the same way. */
  .standing { border-radius:8px; padding:12px 16px; margin-bottom:14px;
            background:var(--card-background-color,#fff);
            box-shadow:0 0 0 2px var(--primary-color,#03a9f4); }
  /* No opacity here. It took the chip down with it - the one
     deliberately vivid thing in the box went grey for no reason other
     than sitting inside the heading - and the muted colour it was doing
     by hand is already what the shared .heading sets. */
  .standing .heading { margin:0 0 4px; font-size:13px; }
  /* The chip keeps its own voice inside a heading that shouts. Uppercase
     and letter-spaced, it would read as a second heading rather than as
     a label - and the advanced mode's chip, which is the same words,
     reads as neither. */
  .standing .heading .chip { text-transform:none; letter-spacing:normal; }
  /* The box's own two paragraphs, and not every paragraph inside it:
     unscoped, this reached the fold's lines as well and the shared
     .step and .stephead margins had to be restated at higher
     specificity to win them back. Three rules where the child selector
     does the job. */
  .standing > p, .standing > summary > p { margin:0 0 10px; }
  /* Two buttons where there was one, and on a phone the second drops to
     its own line rather than squeezing the first to nothing. */
  .standing .acts { display:flex; flex-wrap:wrap; gap:8px; }
  /* The whole head is the way in, exactly as a version row's is. */
  details.standing > summary { display:block; list-style:none; cursor:pointer; }
  details.standing > summary::-webkit-details-marker { display:none; }
  /* The chevron keeps its place even where it is invisible, the same as
     a version row's: whether this box folds depends on whether anything
     was recorded since the last version, and a heading that jumps 11px
     sideways the moment somebody saves is worse than no chevron. */
  .standing .heading::before { content:"\\25B8"; display:inline-block;
            width:9px; margin-right:2px; transition:transform .15s; }
  div.standing .heading::before { visibility:hidden; }
  details.standing[open] .heading::before { transform:rotate(90deg); }
  /* The box brings its own side padding, so the fold needs only the
     indent that puts its lines under the words and not under the
     chevron. */
  .standing .vbody { padding:0 0 2px 11px; }
  /* Where the box and the version it holds are drawn as one, the
     version's line moves in - and its own chevron with it. One box, one
     chevron: the box's sits on the heading above, and a second one on
     the line under it would offer a way in that is not there. Removed
     rather than hidden, because here nothing needs to keep a column -
     this line stands alone, not in a list of numbers. */
  .standing .vhead::before { display:none; }
  /* The gap goes on what follows the line rather than under the line
     itself, so that the note - which is there on some versions and not
     on others - can sit close to the title it belongs to without a
     margin being subtracted again further down. */
  .standing .vhead ~ .acts { margin-top:10px; }
  /* One pill per version - the same card the advanced mode's sections
     wear, and clickable for the same reason: the row is the way in to
     the changes underneath it. A pill that looked like that one and did
     not open was the objection to wearing it at all.
     No backtick in here, nor anywhere in this file - the whole
     stylesheet is one template literal, and one backtick in a comment
     ends it mid-rule. */
  .vrow { margin-bottom:10px; border-radius:8px;
        background:var(--card-background-color,#fff);
        box-shadow:var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,.15)); }
  .vsum { display:block; padding:10px 16px; list-style:none; cursor:pointer; }
  /* Safari drew its own triangle until 16, and this file brings a
     chevron of its own. Two of them is one too many. */
  .vsum::-webkit-details-marker { display:none; }
  /* A row with nothing behind it is not a way in, and does not offer
     itself as one. */
  div.vrow > .vsum { cursor:default; }
  /* The head line, read down a column. It wraps because this panel is
     opened on a phone as well, and there the date and the button drop
     to a second line rather than squeezing the title to nothing.
     Aligned on the baseline and not centred: the number is monospace
     and the title is not. */
  .vhead { display:flex; flex-wrap:wrap; align-items:baseline; gap:4px 10px; }
  /* Kept in its place even where it is invisible: the numbers stand in
     one column whether or not the loaded window reaches that far down,
     and a column that steps sideways halfway is worse than no chevron. */
  .vhead::before { content:"\\25B8"; display:inline-block; width:9px;
                 color:var(--secondary-text-color,#727272);
                 transition:transform .15s; }
  div.vrow .vhead::before { visibility:hidden; }
  details.vrow[open] .vhead::before { transform:rotate(90deg); }
  .vhead .name { font-family:monospace; font-weight:500;
                 color:var(--primary-color,#03a9f4); }
  .vhead .grow { flex:1 1 auto; }
  .vhead .made, .vhead .count { font-size:13px; white-space:nowrap;
                 color:var(--secondary-text-color,#727272); }
  .vhead .auto { margin-left:8px; font-size:12px; opacity:.6; }
  /* The note under a version's line, wherever that line is drawn: in a
     row, or inside the current-state block where the two are one. By
     the sibling it follows rather than by the container it sits in -
     vhead() emits the line and the note as siblings, so one rule serves
     both, and the alternative was the same 4px written a second time
     under a selector with a different logic.

     .why brings a 16px top margin of its own for the places it stands
     alone, which is what has to be overridden here. */
  .vhead + .why { margin:4px 0 0; }
  /* And indented past the chevron where a chevron holds a column, so
     that everything a row says stands under the title rather than under
     the marker. */
  .vsum .why { margin-left:19px; }
  .vbody { padding:0 16px 12px 35px; }
  /* The note above a list of changes, read as a heading rather than as
     the first faint line of the list. Three things make it one, and
     none of them is size: it keeps the 13px of the steps under it, so
     the fold stays one column and nothing shifts.
     Weight and colour instead of opacity - .7 over the body colour was
     a heading dimmer than its own content, which is the wrong way
     round. The colour is the one every other heading in this panel
     wears, so this reads as a label and the steps under it read as the
     content.
     And the space above it, which is the point in the "right now" box:
     with margin:0 the line sat straight under the two buttons and
     looked like a caption belonging to them. */
  .stephead { margin:14px 0 0; font-size:13px; font-weight:600;
            color:var(--secondary-text-color,#727272); }
  .step { margin:6px 0 0; font-size:13px; display:flex; gap:10px; }
  .step .when { margin-left:auto; opacity:.6; }
  .hint { margin-top:18px; }
  .linky { background:none; border:none; padding:0; color:inherit;
         text-decoration:underline; cursor:pointer; font:inherit; }
  /* Segmented toggle bar for confirmation dialogs */
  .confirm-seg-bar {
    margin: 14px 0 6px;
    display: inline-flex;
    background: var(--secondary-background-color, #fafafa);
    border: 1px solid var(--divider-color, rgba(0, 0, 0, .12));
    border-radius: 8px;
    padding: 3px;
    gap: 4px;
    max-width: 100%;
  }
  .confirm-seg-btn {
    background: none;
    border: none;
    padding: 6px 12px;
    border-radius: 6px;
    font-size: 12.5px;
    font-weight: 500;
    color: var(--secondary-text-color, #727272);
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    transition: background .15s ease, color .15s ease, box-shadow .15s ease;
    user-select: none;
    font-family: inherit;
  }
  .confirm-seg-btn:hover {
    color: var(--primary-text-color, #212121);
  }
  .confirm-seg-btn.active {
    background: var(--card-background-color, #fff);
    color: var(--primary-color, #03a9f4);
    font-weight: 600;
    box-shadow: 0 1px 3px rgba(0, 0, 0, .12);
  }
  .confirm-seg-btn .seg-icon {
    flex-shrink: 0;
  }
  dialog.confirm details.raw {
    margin-top: 10px;
  }
  dialog.confirm details.raw > summary {
    display: none;
  }
  .confirm-info-panel {
    margin-top: 10px;
  }
  .confirm-info-panel[hidden] {
    display: none;
  }
  .info-callout {
    background: rgba(3, 169, 244, 0.08);
    border: 1px solid rgba(3, 169, 244, 0.25);
    border-left: 4px solid var(--primary-color, #03a9f4);
    border-radius: 6px;
    padding: 10px 14px;
    display: flex;
    align-items: flex-start;
    gap: 10px;
  }
  .info-callout__icon {
    flex-shrink: 0;
    color: var(--primary-color, #03a9f4);
    margin-top: 1px;
    display: flex;
  }
  .info-callout__content {
    flex: 1;
    font-size: 13px;
    line-height: 1.45;
  }
  .info-callout__content .keeps {
    margin: 0;
    color: var(--primary-text-color, #212121);
    font-size: 13px;
    line-height: 1.45;
  }

  /* Confirm dialog footer with conditional version name fields */
  .confirm-footer {
    display: grid;
    grid-template-columns: 1fr auto;
    align-items: center;
    padding: 12px 16px;
    gap: 12px 16px;
    border-top: 1px solid var(--divider-color, rgba(0, 0, 0, .08));
  }
  .confirm-footer .keep {
    display: contents;
    padding: 0;
  }
  .confirm-footer .keep[hidden] {
    display: none;
  }
  .confirm-footer .save-checkbox-label {
    grid-column: 1;
    grid-row: 1;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    cursor: pointer;
    font-size: 13.5px;
    font-weight: 500;
    user-select: none;
    margin: 0;
  }
  .confirm-footer .save-checkbox-label input[type="checkbox"] {
    margin: 0;
    cursor: pointer;
    accent-color: var(--primary-color, #03a9f4);
  }
  .confirm-footer .actions {
    grid-column: 2;
    grid-row: 1;
    display: flex;
    justify-content: flex-end;
    align-items: center;
    gap: 8px;
    padding: 0;
  }
  .confirm-footer .keepfields {
    grid-column: 1 / span 2;
    grid-row: 2;
  }
  .confirm-footer .keepfields[hidden] {
    display: none;
  }
  .confirm-footer .keepfields input.keeptitle {
    width: 100%;
    box-sizing: border-box;
    margin-bottom: 6px;
  }
  .confirm-footer .keepfields p {
    margin: 0;
  }
  @media (max-width: 600px) {
    .confirm-footer {
      display: flex;
      flex-direction: column;
      align-items: stretch;
      gap: 12px;
    }
    .confirm-footer .actions {
      justify-content: flex-end;
    }
  }
`;
