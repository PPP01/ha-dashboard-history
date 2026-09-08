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
  }
  @keyframes dh-spin { to { transform: rotate(360deg); } }
  /* Somebody who has asked for less movement gets the ring without the
     movement: it still marks the spot, it just does not turn. */
  @media (prefers-reduced-motion: reduce) {
    .spin .ring { animation: none; }
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
  details.more { margin-top: 16px; }
  details.more > summary {
    color: var(--secondary-text-color, #727272);
    font-size: 13px;
    cursor: pointer;
  }
  details.more > summary:hover { color: var(--primary-text-color, #212121); }
  .older { display:flex; justify-content:center; padding:12px 0 4px; }
  .mode { background:none; border:1px solid var(--divider-color,#444); color:inherit;
        border-radius:6px; padding:4px 10px; font-size:13px; cursor:pointer; }
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
  /* Both indented past the chevron, so that everything a row says
     stands under the title rather than under the marker. */
  .vsum .why { margin:4px 0 0 19px; }
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
  .keep { padding:0 16px 8px; }
  .keep label { display:flex; align-items:center; gap:8px; margin-bottom:8px; }
`;
