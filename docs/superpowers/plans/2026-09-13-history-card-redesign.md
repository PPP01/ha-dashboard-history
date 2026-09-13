# History Card Redesign (Variant 1a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the history entry card's three stacked action blocks (Undo, Version, Replace-as-expander) with one action bar, restyle the technical-details disclosure as a reusable pill, and turn "Replace the whole dashboard" into one overlay that offers both "before" and "after" as a radio choice with both previews already loaded.

**Architecture:** Pure frontend change inside `custom_components/dashboard_history/panel.js` and its `panel/` helper modules (vanilla JS custom element, no build step, no framework). No Python/backend changes: `restore_state` and `undo_change` already exist and already support everything this needs (preview-then-write, `keep_as_version`). The work is: extract two small pure-data helpers out of existing render methods, build one new dialog reusing the existing generic dialog-wiring conventions, and delete the JS/CSS that only existed to fake a disclosure-and-tab UI natively `<details>` can do on its own.

**Tech Stack:** Vanilla JS custom element (Web Components, Shadow DOM), hand-written CSS using Home Assistant theme custom properties (`var(--primary-color, <fallback-hex>)`), Node-based behavioural tests (`tests/test_panel_behaviour.py`, run via `node` subprocess, no browser).

**Spec:** `exchange/design_handoff_history_card_1a/README.md` and `exchange/design_handoff_history_card_1a/History Card Redesign.dc.html` (variant **1a** only — 1b is a discarded alternative and must not be built). Deviations from that spec, agreed with the user before this plan was written, are listed below.

## Global Constraints

- **No build step.** `panel.js` and `panel/*.js` ship as-is inside the Python integration; do not introduce ES module bundling, TypeScript, Lit, or any `ha-dialog`/`ha-button`/`mwc-*` import. Keep using native `<dialog>`, `<details>`, `<button>`.
- **Colors via HA theme tokens, not literal hex.** Every color in new/changed CSS must be `var(--some-ha-token, #fallback-hex)`, matching the file's existing convention. Use the hex values from the design spec only as the fallback, never as the only value.
- **`custom_components/dashboard_history/panel/style.js` must stay exactly one unbroken template literal.** It may contain **exactly two backtick characters** (its own delimiters) and must never contain the substring `${`. `tests/test_panel_assets.py::test_the_style_is_one_unbroken_template_literal` and `::test_no_substitution_hides_in_the_stylesheet` enforce this — run them after every edit to this file.
- **Deviations from the design handoff, already agreed with the user (do not re-litigate):**
  1. The "Save the state you are leaving as a version" checkbox's default (ticked in simple mode, clear in advanced mode — `_armKeep`) stays exactly as it is today. Do **not** make it default to unchecked in every mode, as the mockup's `saveVer: false` on open would suggest.
  2. The Undo overlay does **not** get the keep-as-version checkbox at all (matches today's behaviour: `_undoChange` passes no `wantsKeep`). Undo never replaces the whole state — nothing is "left behind" to name. Only the Replace overlay offers it.
  3. Both "before" and "after" previews for the Replace overlay are fetched **in parallel** (`Promise.all`) when the overlay opens, not sequentially per radio click. Confirmed safe: `restore_state`'s preview path is read-only (no `store.py` lock), the websocket handler has no per-dashboard concurrency guard, and the client's `_claim`/`_guard` machinery already supports concurrent in-flight requests.
  4. Guideline 6 of the handoff ("prefer ha-dialog/ha-button/ha-formfield") is **not** followed — see the no-build-step constraint above. Native controls plus HA theme tokens are the intentional equivalent here.
  5. The Replace overlay does **not** show a plain-text explanation of the specific card changes (`renderPlain(preview.explanation, ...)`, the block the Undo/confirm dialog shows above its footnote). It shows only: title → the static consequence sentence → the radio choice → the technical-details pill (collapsed) → the footnote. This matches the design handoff's mockup exactly (it never shows such a block for Replace either) and was confirmed with the user after the final whole-branch review raised it explicitly as a question, not a defect — do not silently add it back in a later change without asking again.
- **`_restoreState` and the generic `[data-state]` wiring stay untouched and in use.** They are not only used by the card's Replace flow — the "this dashboard was deleted" banner's "Bring it back" button (`_renderMain`, the `banner` template) and the "changed since the last version" drift banner (`_renderMain`'s "standing" block) also call them. Do not delete `_restoreState`; only stop calling it from the card's own Replace trigger.
- **Test after every task:** `python3 -m pytest tests/ -v`. The frontend behavioural tests skip visibly (not silently) without a `node` binary on `PATH` — if you see `SKIPPED (node is not installed...)` instead of `PASSED`, treat that as "not verified", not as green.

## File Structure

- `custom_components/dashboard_history/panel/style.js` — add the pill-disclosure look (`details.raw > summary`), the unified action bar (`.action-bar`), the replace-dialog radio choice (`.replace-choice`, `.replace-option`), the orange trigger/confirm button variants; remove the CSS that only existed for markup this plan retires (`.mkver`, `details.more*`, `.confirm-seg-*`, `.confirm-info-panel*`, the `dialog.confirm details.raw > summary { display: none }` override).
- `custom_components/dashboard_history/panel/dialogs.js` — add the new `<dialog class="replace">` static markup, reusing the existing `.keep`/`.keepbox`/`.keepfields`/`.keeptitle`/`.actions`/`.note` structure so the existing generic wiring picks it up.
- `custom_components/dashboard_history/panel.js` — the bulk of the change:
  - `_renderDetail`, `_renderSetBack`, `_renderMakeVersion` → replaced by `_replaceCandidates` (pure data) and `_renderActionBar` (markup).
  - `_confirm` → gains an `intro` parameter, its `.body` assembly loses the diff/info segmented-button pair in favour of a native pill `<details>` plus an always-visible footnote.
  - `_armKeep` → takes the dialog element explicitly instead of always querying `this.shadowRoot`, so it can arm either `dialog.confirm` or the new `dialog.replace`.
  - `_undoChange` → computes the "Puts this change back…" sentence itself and passes it as `_confirm`'s `intro`.
  - New `_openReplace` and `_paintReplace` methods implement the combined overlay.
  - The generic click-wiring block (inside `_render()`) gains `[data-replace]`, and the keepbox `change`-listener wiring generalizes from `dialog.confirm .keepbox` to every dialog's `.keepbox`.
- `tests/test_panel_behaviour.py` — updates alongside each behavioural change; the `confirm_segmented` fixture and its five tests are replaced outright (they test UI being deleted).

---

## Task 1: Pill-styled technical-details disclosure

**Files:**
- Modify: `custom_components/dashboard_history/panel/style.js:510-515` (the `details.raw > summary` rule)
- Modify: `custom_components/dashboard_history/panel.js:2592-2598` (the `technical` block inside `_renderDetail`)
- Test: `tests/test_panel_behaviour.py` (new scenario)

**Interfaces:**
- Produces: a restyled `details.raw > summary` CSS rule (glyph + label + rotating chevron) that Task 5 will rely on when it stops hiding this same summary inside `dialog.confirm`.
- No change to the `_diffOpen` state or the `.detail details.raw` toggle listener (`panel.js:3030-3034`) — leave both exactly as they are.

- [ ] **Step 1: Replace the plain disclosure CSS with a pill**

In `custom_components/dashboard_history/panel/style.js`, replace:

```
  details.raw > summary {
    padding: 8px 0;
    color: var(--secondary-text-color, #727272);
    font-size: 13px;
    cursor: pointer;
  }
```

with:

```
  details.raw > summary {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 7px 14px;
    margin: 8px 0;
    border: 1px solid var(--divider-color, #dfe3e8);
    border-radius: 18px;
    background: var(--secondary-background-color, #f1f3f5);
    color: var(--primary-text-color, #37474f);
    font-size: 13.5px;
    font-weight: 500;
    cursor: pointer;
    list-style: none;
    user-select: none;
  }
  details.raw > summary::-webkit-details-marker { display: none; }
  details.raw > summary:hover {
    background: var(--divider-color, #e7ebee);
  }
  details.raw > summary .glyph {
    font-family: monospace;
    font-size: 12px;
    color: var(--secondary-text-color, #607d8b);
  }
  details.raw > summary::after {
    content: "\25BE";
    margin-left: 2px;
    color: var(--secondary-text-color, #90a4ae);
    display: inline-block;
    transition: transform .15s ease;
  }
  details.raw[open] > summary::after {
    transform: rotate(180deg);
  }
```

(Uses the same escaped-unicode-in-CSS convention as `details.ver > summary::before` a few lines below — plain ASCII in the file, no literal non-ASCII character.)

- [ ] **Step 2: Verify the stylesheet is still one valid template literal**

Run: `python3 -m pytest tests/test_panel_assets.py -v`
Expected: `test_the_style_is_one_unbroken_template_literal` and `test_no_substitution_hides_in_the_stylesheet` both PASS.

- [ ] **Step 3: Add the glyph span to the card's technical-details summary**

In `custom_components/dashboard_history/panel.js`, inside `_renderDetail`, replace:

```javascript
    const technical =
      this._explanation && this._explanation.diff
        ? `<details class="raw"${this._diffOpen ? " open" : ""}>
             <summary>Show the technical details</summary>
             ${renderDiff(this._explanation.diff)}
           </details>`
        : "";
```

with:

```javascript
    const technical =
      this._explanation && this._explanation.diff
        ? `<details class="raw"${this._diffOpen ? " open" : ""}>
             <summary><span class="glyph">&lt;/&gt;</span> Show the technical details</summary>
             ${renderDiff(this._explanation.diff)}
           </details>`
        : "";
```

- [ ] **Step 4: Write the failing test for the pill markup**

Add to `tests/test_panel_behaviour.py`:

```python
_CARD_DIFF_PILL = """
const el = new Panel();
el._render = () => {};
el._changes = [{ revision: "a", previous: "b" }];
el._explanation = { groups: [], note: "", diff: "-old\\n+new" };
el._undo = null;

const html = el._renderDetail(el._changes[0]);
console.log(JSON.stringify({ html }));
"""


@pytest.fixture(scope="session")
def card_diff_pill(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "card_diff_pill", _CARD_DIFF_PILL)


def test_the_cards_technical_details_summary_carries_the_pill_glyph(card_diff_pill):
    # The redesign turns the native triangle into a pill with a `</>`
    # glyph before the label; the label text itself does not change, so
    # the existing progressive-expand tests (which grep for exactly
    # "Show the technical details") keep passing unmodified.
    assert '<span class="glyph">&lt;/&gt;</span> Show the technical details' in card_diff_pill["html"]
    assert 'details class="raw"' in card_diff_pill["html"]
```

- [ ] **Step 5: Run it to make sure it fails, then passes**

Run: `python3 -m pytest tests/test_panel_behaviour.py -k test_the_cards_technical_details_summary_carries_the_pill_glyph -v`
Expected before Step 3: FAIL (glyph span missing). After Step 3: PASS.

- [ ] **Step 6: Run the full suite and commit**

Run: `python3 -m pytest tests/ -v`
Expected: all PASS (or skip visibly without `node`/real storage — no new failures).

```bash
git add custom_components/dashboard_history/panel/style.js custom_components/dashboard_history/panel.js tests/test_panel_behaviour.py
git commit -m "$(cat <<'EOF'
Style the technical-details disclosure as a pill

The redesign wants one reusable "Show the technical details" control
instead of a plain triangle, used identically in the card and (later)
both confirmation overlays. Restyled the existing details.raw/summary
rather than introducing a second component, so every future disclosure
gets it for free.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Unified action bar, `_replaceCandidates` extraction

**Files:**
- Modify: `custom_components/dashboard_history/panel.js:2477-2668` (`_renderSetBack`, `_renderDetail`, `_renderMakeVersion` — replaced by `_replaceCandidates` and `_renderActionBar`)
- Modify: `custom_components/dashboard_history/panel/style.js` (add `.action-bar`, `.action-bar .named`, `button.act.replace-trigger`; remove `.mkver`, `.mkver .named`, `details.more`, `details.more > summary`, `details.more > summary:hover`)
- Test: `tests/test_panel_behaviour.py` (new scenarios)

**Interfaces:**
- Produces: `_replaceCandidates(change)` → `{ candidates: Array<{revision, label, timestamp}>, why: string }` (0, 1 or 2 candidates; `why` is a non-empty sentence only in the one edge case where "before" would just repeat the live state). Task 3 (`_openReplace`) consumes exactly this shape.
- Produces: `_renderActionBar(change, { offerReplace = true } = {})` → HTML string. Called with `offerReplace: false` from `_renderDetail`'s "no previous state" branch, preserving today's behaviour of never offering Replace for the very first recorded change (that branch never called `_renderSetBack` either).
- Produces: `[data-replace]` buttons in the rendered card, wired to a method `this._openReplace` which **does not exist yet** — this task's own tests stub it (`el._openReplace = (...args) => wired.push(args)`) so they test the wiring, not the (not-yet-built) dialog. Task 3 implements the real method; nothing here breaks when it lands.
- Consumes: `this._undo`, `this._changeAt`, `this._alreadyNamed` (unchanged), `escape`, `when` (existing module-level imports).

- [ ] **Step 1: Extract `_replaceCandidates` from `_renderSetBack`**

In `custom_components/dashboard_history/panel.js`, replace the whole `_renderSetBack` method (`panel.js:2477-2517`):

```javascript
  _renderSetBack(change) {
    const before = change.previous;
    const buttons = [];
    const same = this._undo?.available && this._undo.equals_state_before;
    // Where the predecessor is outside the loaded window there is no
    // row to ask, so this stays false and the button stays - exactly
    // what happened before, when `this._changes[index + 1]` was not
    // there either.
    const beforeIsNow = Boolean(before && this._changeAt(before)?.same_as_now);
    if (before && !beforeIsNow && !same)
      buttons.push({
        revision: before,
        label: "Back to the state before this change",
      });
    if (!change.same_as_now)
      buttons.push({
        revision: change.revision,
        label: "Back to the state after this change",
      });

    const why = beforeIsNow
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
```

with:

```javascript
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
      </div>
      ${named ? `<span class="named">${escape(named)}</span>` : ""}
      ${why ? `<span class="why">${why}</span>` : ""}`;
  }
```

- [ ] **Step 2: Fold the old Undo button/sentence and `_renderMakeVersion` into the new action bar inside `_renderDetail`**

In `custom_components/dashboard_history/panel.js`, inside `_renderDetail` (`panel.js:2519-2607`):

Replace the "no previous state" early return:

```javascript
    if (!before)
      return `<div class="detail">${plain}<p class="muted">This is the first
        recorded state, so there is nothing before it to compare against.</p>
        ${this._renderMakeVersion(change)}</div>`;
```

with:

```javascript
    if (!before)
      return `<div class="detail">${plain}<p class="muted">This is the first
        recorded state, so there is nothing before it to compare against.</p>
        ${this._renderActionBar(change, { offerReplace: false })}</div>`;
```

Replace the `offer` assignment (the `undo ? ... : ...` block) so the Undo button and its "Puts this change back…" sentence stop rendering inline in the card — the button moves to the action bar (already handled above) and the sentence moves into the Undo dialog in Task 4:

```javascript
    const made = this._madeSince(change);
    const kept =
      made ? ` and keeps the ${made} change${made === 1 ? "" : "s"} made since` : "";
    const offer = undo
      ? `<div class="backto">
           <button class="act" data-undo="${escape(change.revision)}">Undo this change</button>
         </div>
         <p class="why" style="margin-top:8px">Puts this change back${kept}.</p>`
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
```

with (the `made`/`kept` computation moves to `_undoChange` in Task 4 — drop it here entirely):

```javascript
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
```

Replace the final return:

```javascript
    return `<div class="detail">
      ${plain}
      ${technical}
      ${offer}
      ${this._renderSetBack(change)}
      ${this._renderMakeVersion(change)}
    </div>`;
```

with:

```javascript
    return `<div class="detail">
      ${plain}
      ${technical}
      ${offer}
      ${this._renderActionBar(change)}
    </div>`;
```

- [ ] **Step 3: Delete `_renderMakeVersion`**

Remove the whole method (`panel.js:2661-2668`, right after `_matchingElsewhere`):

```javascript
  _renderMakeVersion(change) {
    const named = this._alreadyNamed(change);
    return `<div class="mkver">
        <button class="act ghost" data-version="${escape(change.revision)}"
                >Version up to here</button>
        ${named ? `<span class="named">${escape(named)}</span>` : ""}
      </div>`;
  }
```

Its whole body is now inlined in `_renderActionBar`.

- [ ] **Step 4: Wire `[data-replace]` in the generic click handler**

In `custom_components/dashboard_history/panel.js`, right after the `[data-undo]` block (`panel.js:3074-3077`):

```javascript
    onClick("[data-undo]", (element, event) => {
      event.stopPropagation();
      this._undoChange(element.dataset.undo);
    });
```

add:

```javascript
    onClick("[data-replace]", (element, event) => {
      event.stopPropagation();
      this._openReplace(element.dataset.replace);
    });
```

`_openReplace` does not exist yet (Task 3 adds it) — this is fine, JS resolves `this._openReplace` at call time, not at parse time, and no test in this task ever clicks the button for real (see Step 6).

- [ ] **Step 5: Replace `.mkver`/`.details.more` CSS with `.action-bar`**

In `custom_components/dashboard_history/panel/style.js`, remove:

```
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
```

Keep `.backto` — it is still used by `_renderDetail`'s `compareFromOffer` and by the drift/"bring it back" banners in `_renderMain`. Replace only the `.mkver`/`.mkver .named` pair above with:

```
  .action-bar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 10px;
    margin-top: 16px;
  }
  .action-bar .named {
    color: var(--secondary-text-color, #727272);
    font-size: 13px;
  }
  button.act.replace-trigger {
    margin-left: auto;
    background: none;
    color: var(--warning-color, #b3541e);
    padding: 8px 10px;
  }
  button.act.replace-trigger:hover {
    background: rgba(179, 84, 30, 0.08);
    background: color-mix(in srgb, var(--warning-color, #b3541e) 10%, transparent);
  }
```

Remove the now-unused `details.more` rules:

```
  details.more { margin-top: 16px; }
  details.more > summary {
    color: var(--secondary-text-color, #727272);
    font-size: 13px;
    cursor: pointer;
  }
  details.more > summary:hover { color: var(--primary-text-color, #212121); }
```

- [ ] **Step 6: Write the failing tests**

Add to `tests/test_panel_behaviour.py`:

```python
_ACTION_BAR = """
const el = new Panel();
el._render = () => {};
el._changes = [
  { revision: "a", previous: "b", same_as_now: false, timestamp: 20 },
  { revision: "b", previous: "c", same_as_now: false, timestamp: 10 },
  { revision: "c", previous: null, same_as_now: false, timestamp: 5 },
];
el._explanation = { groups: [], note: "" };

// Undo available, both replace candidates exist.
el._undo = { available: true, equals_state_before: false };
const withBoth = el._renderDetail(el._changes[0]);

// Undo refused: no undo button, replace candidates unaffected.
el._undo = { available: false, reason: "no reason given" };
const withoutUndo = el._renderDetail(el._changes[0]);

// The oldest loaded change has no previous at all: no replace trigger,
// only the version button - matching today's behaviour exactly.
const first = el._renderDetail(el._changes[2]);

console.log(JSON.stringify({ withBoth, withoutUndo, first }));
"""


@pytest.fixture(scope="session")
def action_bar(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "action_bar", _ACTION_BAR)


def test_the_action_bar_carries_version_undo_and_replace_together(action_bar):
    html = action_bar["withBoth"]
    assert '<div class="action-bar">' in html
    assert 'data-version="a"' in html
    assert 'data-undo="a"' in html
    assert 'data-replace="a"' in html
    assert "Replace the whole dashboard…" in html


def test_the_replace_trigger_is_absent_when_undo_is_refused_but_visible_anyway(action_bar):
    # Replace does not depend on Undo being available - they are two
    # independent offers in the same bar.
    html = action_bar["withoutUndo"]
    assert "data-undo=" not in html
    assert 'data-replace="a"' in html


def test_the_first_recorded_change_offers_no_replace_trigger(action_bar):
    # Unchanged from before this redesign: `_renderDetail`'s "no
    # previous" branch never called `_renderSetBack`, so it must never
    # call `_replaceCandidates` either.
    html = action_bar["first"]
    assert "data-replace=" not in html
    assert 'data-version="c"' in html
```

- [ ] **Step 7: Run to verify failure, then implement, then verify pass**

Run: `python3 -m pytest tests/test_panel_behaviour.py -k "action_bar" -v`
Expected before Steps 1-2: FAIL (`_renderActionBar is not a function`). After: PASS.

- [ ] **Step 8: Run the full suite**

Run: `python3 -m pytest tests/ -v`
Expected: all PASS. Pay particular attention to any test matching `data-undo=`, `data-version=`, `"Show the technical details"`, `class="backto"` — none of them should have broken (grep the failures list for `progressive_expand`, `keeping`, `wrong_dashboard` if anything is red and re-read this task's diff against the exact old markup those tests assert on).

- [ ] **Step 9: Commit**

```bash
git add custom_components/dashboard_history/panel.js custom_components/dashboard_history/panel/style.js tests/test_panel_behaviour.py
git commit -m "$(cat <<'EOF'
Merge the card's three action blocks into one action bar

Undo, Version up to here and Replace the whole dashboard used to be
three separately stacked blocks, one of them a details/summary
expander easy to confuse with the technical-details one right above
it. Extracted the replace candidates as data (_replaceCandidates) so
the upcoming combined overlay can read them without re-deriving the
before/after rules, and folded all three actions into one row.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `_armKeep` dialog-scoping + generalized keepbox wiring

**Files:**
- Modify: `custom_components/dashboard_history/panel.js:1795-1808` (`_armKeep`)
- Modify: `custom_components/dashboard_history/panel.js:1666` (the one existing call site, inside `_confirm`)
- Modify: `custom_components/dashboard_history/panel.js:3180-3186` (the keepbox `change`-listener wiring)
- Test: `tests/test_panel_behaviour.py` (extend the existing keepbox test)

**Interfaces:**
- Produces: `_armKeep(show, dialog)` — `dialog` is now a required second parameter (the `<dialog>` element to scope `[data-keep]` inside), not an implicit `this.shadowRoot` search. `_keepChoice(keep)` is unchanged — it already takes the block `_armKeep` returns, never the shadow root.
- Consumes: nothing new; this is a pure signature generalization so Task 4's `dialog.replace` can arm its own, separate `[data-keep]` block without colliding with `dialog.confirm`'s.

This task exists on its own, ahead of the new dialog, because doing it together with Task 4 would mix "make an existing helper reusable" with "add a whole new overlay" in one diff — a reviewer should be able to check the generalization is behaviour-preserving before also reviewing new behaviour.

- [ ] **Step 1: Write the failing test for a second dialog's keepbox**

Add to `tests/test_panel_behaviour.py`, near `_KEEPBOX_CHANGE`:

```python
_ARM_KEEP_SCOPED = """
const el = new Panel();
el.shadowRoot = node();
el._render();

const confirmDialog = el.shadowRoot.querySelector("dialog.confirm");
const replaceDialog = el.shadowRoot.querySelector("dialog.replace");

// Arming one dialog's [data-keep] must not touch the other's.
const confirmKeep = el._armKeep(true, confirmDialog);
const replaceKeep = el._armKeep(false, replaceDialog);

console.log(JSON.stringify({
  confirmShown: confirmKeep !== null,
  replaceShown: replaceKeep !== null,
}));
"""


@pytest.fixture(scope="session")
def arm_keep_scoped(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "arm_keep_scoped", _ARM_KEEP_SCOPED)


def test_arm_keep_is_scoped_to_the_dialog_it_is_given(arm_keep_scoped):
    # Two dialogs, each with its own [data-keep] block now that
    # dialog.replace exists (Task 4 adds its markup) - _armKeep must
    # arm the one it was handed, not the first [data-keep] anywhere in
    # the shadow root.
    assert arm_keep_scoped["confirmShown"] is True
    assert arm_keep_scoped["replaceShown"] is False
```

Note: this test needs `dialog.replace` to exist in `DIALOGS` to find two `[data-keep]` blocks at all — if you are executing tasks strictly in order, `dialog.replace` does not exist until Task 4. Either reorder this test's own commit to land after Task 4's dialog markup step, or (simpler) add a minimal `<div data-keep hidden></div>` placeholder inside a temporary second dialog for this test's own inline scenario only, not touching `dialogs.js`. The cleanest path: do Step 1 as a plain unit test against two hand-built stand-in nodes rather than the real shadow root, since `_armKeep` only ever touches the `dialog` argument it is given:

```python
_ARM_KEEP_SCOPED = """
const el = new Panel();

// Two independent stand-in dialogs, each with their own [data-keep].
const dialogA = node();
const dialogB = node();
dialogA._seen["[data-keep]"] = node();
dialogB._seen["[data-keep]"] = node();

const shownA = el._armKeep(true, dialogA);
const shownB = el._armKeep(false, dialogB);

console.log(JSON.stringify({
  shownA: shownA !== null,
  hiddenA: dialogA._seen["[data-keep]"].hidden,
  shownB: shownB !== null,
  hiddenB: dialogB._seen["[data-keep]"].hidden,
}));
"""


@pytest.fixture(scope="session")
def arm_keep_scoped(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "arm_keep_scoped", _ARM_KEEP_SCOPED)


def test_arm_keep_is_scoped_to_the_dialog_it_is_given(arm_keep_scoped):
    # _armKeep must query the dialog it is handed, never a shared
    # shadow root - otherwise arming one dialog's checkbox would find
    # (or fail to find) whichever [data-keep] happens to come first.
    assert arm_keep_scoped["shownA"] is True
    assert arm_keep_scoped["hiddenA"] is False
    assert arm_keep_scoped["shownB"] is False
    assert arm_keep_scoped["hiddenB"] is True
```

Use this second version — it needs nothing from Task 4 and stays correct afterwards.

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m pytest tests/test_panel_behaviour.py -k test_arm_keep_is_scoped_to_the_dialog_it_is_given -v`
Expected: FAIL (`_armKeep` still takes one argument and reads `this.shadowRoot`).

- [ ] **Step 3: Scope `_armKeep` to its `dialog` argument**

In `custom_components/dashboard_history/panel.js`, replace:

```javascript
  _armKeep(show) {
    const keep = this.shadowRoot.querySelector("[data-keep]");
```

with:

```javascript
  _armKeep(show, dialog) {
    const keep = dialog.querySelector("[data-keep]");
```

(the rest of the method body is unchanged).

- [ ] **Step 4: Update the one existing call site**

In `custom_components/dashboard_history/panel.js:1666`, inside `_confirm`, replace:

```javascript
    const keepBlock = this._armKeep(keepable);
```

with:

```javascript
    const keepBlock = this._armKeep(keepable, dialog);
```

(`dialog` is already in scope — it is `this.shadowRoot.querySelector("dialog.confirm")` from line 1481.)

- [ ] **Step 5: Generalize the keepbox change-listener wiring**

In `custom_components/dashboard_history/panel.js`, replace:

```javascript
    const keepbox = root.querySelector("dialog.confirm .keepbox");
    if (keepbox) {
      keepbox.addEventListener("change", (event) => {
        const fields = root.querySelector("dialog.confirm .keepfields");
        if (fields) fields.hidden = !event.target.checked;
      });
    }
```

with:

```javascript
    root.querySelectorAll("dialog .keepbox").forEach((keepbox) => {
      keepbox.addEventListener("change", (event) => {
        const fields = keepbox.closest("[data-keep]")?.querySelector(".keepfields");
        if (fields) fields.hidden = !event.target.checked;
      });
    });
```

Note the switch from a dialog-qualified `.keepfields` lookup to `keepbox.closest("[data-keep]")` — with two dialogs each carrying their own `.keepbox`/`.keepfields` pair, a plain `root.querySelector("dialog.confirm .keepfields")` inside the loop would always find `dialog.confirm`'s fields even while wiring `dialog.replace`'s checkbox. `closest` scopes each listener to its own block.

The test harness's stand-in `node()` implements `closest` only via a hand-set `_closest` map (see `_PRELUDE`); real DOM `closest` works natively, so this only matters for tests that exercise this exact listener with the stand-in (Task 4's replace-dialog test will set `_closest` accordingly, mirroring the existing `[data-compare-body]` pattern in `_PRELUDE`'s doc comment).

- [ ] **Step 6: Run to verify pass**

Run: `python3 -m pytest tests/test_panel_behaviour.py -k "test_arm_keep_is_scoped_to_the_dialog_it_is_given or keepbox_change" -v`
Expected: all PASS, including the pre-existing `_KEEPBOX_CHANGE`-based tests (they use the real `_render()` shadow root and `dialog.confirm`, so `closest("[data-keep]")` resolves the same fields it always did).

- [ ] **Step 7: Run the full suite and commit**

Run: `python3 -m pytest tests/ -v`
Expected: all PASS.

```bash
git add custom_components/dashboard_history/panel.js tests/test_panel_behaviour.py
git commit -m "$(cat <<'EOF'
Scope _armKeep and its checkbox wiring to one dialog

Both were written for exactly one dialog and searched the whole shadow
root for [data-keep]/.keepbox. The upcoming Replace overlay needs its
own, separate keep-as-version block; querying by dialog rather than by
"the first one anywhere" is the minimal change that supports a second
consumer without touching what the first one does.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: `_openReplace` — combined overlay with parallel before/after previews

**Files:**
- Create: markup addition to `custom_components/dashboard_history/panel/dialogs.js`
- Modify: `custom_components/dashboard_history/panel/style.js` (add `.replace-choice`, `.replace-option`, `button.act.replace-confirm`)
- Modify: `custom_components/dashboard_history/panel.js` (new `_openReplace`, `_paintReplace` methods)
- Test: `tests/test_panel_behaviour.py` (new scenarios)

**Interfaces:**
- Consumes: `_replaceCandidates(change)` from Task 2, `_armKeep(show, dialog)`/`_keepChoice(keep)` from Task 3, `_claim`, `_guard`, `_showError`, `_sayAbout`, `_reloadAfterWrite`, `_recorded`, `_answerFrom`, `_call`, `escape`, `when`, `renderDiff`, `joinNames`, `someNames` (all pre-existing, unchanged). Deliberately not `renderPlain` — the overlay's one consequence sentence is static markup in `dialogs.js`, not a per-preview explanation.
- Produces: `_openReplace(revision)` — looks the change up itself via `_changeAt`, so callers only ever need to pass a revision string, matching `_undoChange(revision)`'s convention.
- Produces: `_paintReplace(dialog, candidates, previews, selectedIndex)` → `{ keepable: boolean, keepBlock: Element|null }`, a pure(-ish) rendering step callable both on open and on radio switch, with no network call in it.

- [ ] **Step 1: Add the `dialog.replace` markup**

In `custom_components/dashboard_history/panel/dialogs.js`, right after the closing `</dialog>` of `dialog.confirm` (after line 55, before `<dialog class="forget">`):

The static consequence sentence is hardcoded directly in the markup (it
never changes, unlike the per-candidate diff) — matching the design
handoff's fixed overlay order "title → one consequence sentence → choice
→ pill → footnote → footer", where the consequence sentence stays the
same regardless of which radio is picked:

```html
  <dialog class="replace">
    <h2>Replace the whole dashboard</h2>
    <p class="why">The dashboard is set back to a full snapshot.
      Everything saved since is no longer what the dashboard holds.</p>
    <div class="replace-choice" data-replace-choice></div>
    <div class="body"></div>
    <div class="confirm-footer">
      <div class="keep" data-keep hidden>
        <label class="save-checkbox-label">
          <input type="checkbox" class="keepbox">
          <span>Save the state you are leaving as a version</span>
        </label>
        <div class="keepfields" hidden>
          <input class="text keeptitle" type="text" maxlength="200"
                 placeholder="What to call it">
          <p class="muted" style="font-size:13px">
            Kept either way — without a name it is only findable in the
            advanced view. Nothing is deleted.
          </p>
        </div>
      </div>
      <div class="actions">
        <span class="note muted" style="margin-right:auto"></span>
        <button class="act ghost" value="cancel">Cancel</button>
        <button class="act replace-confirm" value="apply">Replace dashboard</button>
      </div>
    </div>
  </dialog>
```

This reuses the exact `.keep`/`.keepbox`/`.keepfields`/`.keeptitle`/`.actions`/`.note` structure `dialog.confirm` already has, so Task 3's generalized wiring (dialog `.actions button` auto-close, `dialog .keepbox` change listener) applies to it with zero extra code.

- [ ] **Step 2: Add its CSS**

In `custom_components/dashboard_history/panel/style.js`, add (anywhere near the other dialog-specific rules, e.g. after the `.info-callout*` rules):

```
  .replace-choice {
    padding: 4px 16px 0;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .replace-option {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    border: 2px solid var(--divider-color, #e0e4e8);
    border-radius: 8px;
    cursor: pointer;
  }
  .replace-option:has(input:checked) {
    border-color: var(--primary-color, #03a9f4);
  }
  .replace-option .when {
    margin-left: auto;
    color: var(--secondary-text-color, #888);
    font-size: 13px;
  }
  button.act.replace-confirm {
    background: var(--warning-color, #b3541e);
  }
```

(`:has()` is already used elsewhere in this file — `.segmented-control__track:has(input[value="advanced"]:checked)` — so this is not a new browser-support bar.)

- [ ] **Step 3: Run the style guard**

Run: `python3 -m pytest tests/test_panel_assets.py -v`
Expected: PASS (still exactly two backticks, still no `${`).

- [ ] **Step 4: Write the failing tests for `_openReplace`**

Add to `tests/test_panel_behaviour.py`:

The stand-in `node()` records one listener per (node, event name) — see the `_PRELUDE` doc comment. `_openReplace` attaches the radio `change` listener to each `<input>` it builds inside `[data-replace-choice]`, but the stand-in has no real child tree to walk, so `querySelectorAll` inside that container answers with the one cached stand-in for the selector string, and both radios' listeners collapse onto it (the same simplification other multi-element scenarios in this file already rely on, e.g. `.levels button` in the version-dialog tests). The scenario below reaches the switch through that same container, `choice._on.change`, rather than through an individual `<input>`:

```python
_OPEN_REPLACE_BOTH = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._mode = "advanced";
el._changes = [
  { revision: "a", previous: "b", same_as_now: false, timestamp: 20 },
  { revision: "b", previous: "c", same_as_now: false, timestamp: 10 },
];
el.shadowRoot = node();
el._recorded = () => Promise.resolve();

const calls = [];
el._call = (type, extra) =>
  new Promise((resolve) => calls.push({ type, extra, resolve }));

const done = el._openReplace("a");
await settle();
const firstBatch = calls.map((c) => ({ type: c.type, extra: c.extra }));

calls[0].resolve({ preview: "-a\\n+b", explanation: { groups: [], note: "" } });
calls[1].resolve({ preview: "-c\\n+d", explanation: { groups: [], note: "" } });
await settle();

const dialog = el.shadowRoot.querySelector("dialog.replace");
const choice = dialog.querySelector("[data-replace-choice]");
const afterOpen = { bodyHtml: dialog.querySelector(".body").innerHTML };

// The stand-in records one listener per (node, event name); the two
// radios _openReplace builds are read back the same way a real
// scenario reads injected buttons - through the container's own
// recorded listener map, since node() has no real child tree.
choice._on.change?.({ target: { value: "1" } });
const afterSwitch = { bodyHtml: dialog.querySelector(".body").innerHTML, calls: calls.length };

dialog.close("apply");
await done;

console.log(JSON.stringify({ firstBatch, afterOpen, afterSwitch,
  writeCall: calls[2] ? { type: calls[2].type, extra: calls[2].extra } : null }));
"""


@pytest.fixture(scope="session")
def open_replace_both(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "open_replace_both", _OPEN_REPLACE_BOTH)
```

```python
def test_both_replace_previews_are_fetched_in_parallel(open_replace_both):
    # Not one after the other on radio click: both restore_state
    # previews go out together when the overlay opens.
    types = [c["type"] for c in open_replace_both["firstBatch"]]
    assert types == ["restore_state", "restore_state"]
    revisions = {c["extra"]["revision"] for c in open_replace_both["firstBatch"]}
    assert revisions == {"a", "b"}
    assert all(c["extra"]["confirm"] is False for c in open_replace_both["firstBatch"])


def test_switching_the_replace_radio_costs_no_extra_request(open_replace_both):
    assert "+b" in open_replace_both["afterOpen"]["bodyHtml"]
    assert "+d" in open_replace_both["afterSwitch"]["bodyHtml"]
    assert open_replace_both["afterSwitch"]["calls"] == 2


def test_confirming_the_replace_writes_the_selected_candidate(open_replace_both):
    # The radio was switched to index 1 (revision "b") before Apply.
    assert open_replace_both["writeCall"] == {
        "type": "restore_state",
        "extra": {"dashboard": "dash", "revision": "b", "confirm": True},
    }
```

```python
_OPEN_REPLACE_SINGLE = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._mode = "advanced";
// Only "after" applies: this is the newest change and its predecessor
// is already known to be today's live state.
el._changes = [{ revision: "a", previous: "b", same_as_now: false }];
el._changeAt = (rev) => rev === "b" ? { revision: "b", same_as_now: true } : el._changes.find((c) => c.revision === rev) || null;
el.shadowRoot = node();
el._recorded = () => Promise.resolve();

const calls = [];
el._call = (type, extra) =>
  new Promise((resolve) => calls.push({ type, extra, resolve }));

const done = el._openReplace("a");
await settle();
calls[0].resolve({ preview: "-a\\n+b", explanation: { groups: [], note: "" } });
await settle();

const dialog = el.shadowRoot.querySelector("dialog.replace");
const choiceHtml = dialog.querySelector("[data-replace-choice]").innerHTML;

dialog.close("cancel");
await done;

console.log(JSON.stringify({ callCount: calls.length, choiceHtml }));
"""


@pytest.fixture(scope="session")
def open_replace_single(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "open_replace_single", _OPEN_REPLACE_SINGLE)


def test_a_single_replace_candidate_skips_the_radio_choice(open_replace_single):
    # Only one option: no server round trip wasted on a choice with one
    # answer, and nothing that reads as a UI asking a question with
    # only one possible reply.
    assert open_replace_single["callCount"] == 1
    assert open_replace_single["choiceHtml"] == ""
```

- [ ] **Step 5: Run to verify all new tests fail**

Run: `python3 -m pytest tests/test_panel_behaviour.py -k "open_replace" -v`
Expected: FAIL (`_openReplace is not a function`).

- [ ] **Step 6: Implement `_paintReplace`**

In `custom_components/dashboard_history/panel.js`, add this new method right after `_confirm` (after line 1742, before the `_answerFrom` doc comment):

```javascript
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
    const keeps = preview.creates_dashboard
      ? ""
      : covered.length
        ? `<p class="keeps" title="${escape(joinNames(covered))}">What the
             dashboard holds now is already saved as
             ${escape(someNames(covered))}, so there is nothing to keep.
             Nothing is deleted.</p>`
        : `<p class="keeps">What the dashboard holds now is not lost: it
             stays in the history as its own entry, so you can set it
             back the same way.</p>`;
    const keepable = Boolean(!nothingToDo && !preview.creates_dashboard && !covered.length);
    const keepsContent = keeps
      ? `<div class="info-callout">
           <div class="info-callout__icon" aria-hidden="true">
             <svg viewBox="0 0 20 20" width="18" height="18" fill="currentColor">
               <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"/>
             </svg>
           </div>
           <div class="info-callout__content">${keeps}</div>
         </div>`
      : "";
    dialog.querySelector(".body").innerHTML = nothingToDo
      ? `<p>This state is what the dashboard holds right now, so there is
           nothing to apply.</p>`
      : `<details class="raw">
           <summary><span class="glyph">&lt;/&gt;</span> Show the technical details</summary>
           ${renderDiff(preview.preview)}
         </details>
         ${keepsContent}`;
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
```

- [ ] **Step 7: Run the new tests**

Run: `python3 -m pytest tests/test_panel_behaviour.py -k "open_replace" -v`
Expected: PASS. If the radio-switch test fails because the stand-in `node()` records listeners per-node rather than per-radio, check that `_openReplace` queries `choice.querySelectorAll(...)` — with the stand-in, `querySelectorAll` returns `[it.querySelector(selector)]` (one shared stand-in node per selector string, per the `_PRELUDE` doc comment), so both radios in the test collapse onto the one `choice._on.change` handler the test reads — this is the harness's known simplification, already relied on by other multi-element scenarios in this file (e.g. `.levels button` in `_KEEPING`-style tests). If it does not behave this way, adjust the test to fire the change event through whichever node the stand-in actually attaches it to (inspect with a `console.log(Object.keys(choice._on))` while iterating) rather than changing production code to fit a guess.

- [ ] **Step 8: Run the full suite and commit**

Run: `python3 -m pytest tests/ -v`
Expected: all PASS.

```bash
git add custom_components/dashboard_history/panel.js custom_components/dashboard_history/panel/dialogs.js custom_components/dashboard_history/panel/style.js tests/test_panel_behaviour.py
git commit -m "$(cat <<'EOF'
Combine before/after into one Replace overlay

Two independent buttons, each opening its own confirm dialog, become
one overlay with a radio choice - matching the redesign. Both
candidates' previews are fetched together when the overlay opens
(confirmed safe: restore_state's preview path takes no store.py lock
and the websocket handler has no per-dashboard concurrency guard), so
switching the radio costs no second round trip.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Move "Puts this change back…" into the Undo overlay

**Files:**
- Modify: `custom_components/dashboard_history/panel.js:1447` (`_confirm` signature) and its body-assembly block
- Modify: `custom_components/dashboard_history/panel.js:2329-2338` (`_undoChange`)
- Test: `tests/test_panel_behaviour.py` (new scenario)

**Interfaces:**
- Produces: `_confirm(title, request, wantsKeep = false, intro = "")` — a 4th, optional parameter rendered as a single sentence above the technical-details pill, used only by the Undo flow.
- Consumes: `_madeSince(change)`, `_changeAt(revision)` (both unchanged), from `_undoChange`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_panel_behaviour.py`:

```python
_UNDO_INTRO = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._changes = [{ revision: "a" }, { revision: "b" }, { revision: "c" }];
el.shadowRoot = node();

const calls = [];
el._call = (type, extra) => new Promise((resolve) => calls.push({ type, extra, resolve }));

const done = el._undoChange("a");
await settle();
calls[0].resolve({ preview: "-x\\n+y", explanation: { groups: [], note: "" } });
await settle();

const dialog = el.shadowRoot.querySelector("dialog.confirm");
const bodyHtml = dialog.querySelector(".body").innerHTML;
dialog.close("cancel");
await done;

console.log(JSON.stringify({ bodyHtml }));
"""


@pytest.fixture(scope="session")
def undo_intro(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "undo_intro", _UNDO_INTRO)


def test_the_undo_dialog_carries_the_kept_since_sentence(undo_intro):
    # Moved out of the card (design handoff point 2): the reader sees
    # this sentence at the point they are asked to confirm, not before.
    assert "Puts this change back and keeps the 2 changes made since." in undo_intro["bodyHtml"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_panel_behaviour.py -k test_the_undo_dialog_carries_the_kept_since_sentence -v`
Expected: FAIL (no such text anywhere yet — `_confirm` has no `intro` parameter).

- [ ] **Step 3: Add the `intro` parameter to `_confirm`**

In `custom_components/dashboard_history/panel.js`, change the signature:

```javascript
  async _confirm(title, request, wantsKeep = false) {
```

to:

```javascript
  async _confirm(title, request, wantsKeep = false, intro = "") {
```

Then, in the same method, find the `.body.innerHTML =` assignment (the ternary starting `dialog.querySelector(".body").innerHTML = nothingToDo ? ... : renderPlain(...) + ...`). Insert `intro` right after the `renderPlain(...)` call and before the technical-details block:

```javascript
    dialog.querySelector(".body").innerHTML = nothingToDo
      ? `<p>This state is what the dashboard holds right now, so there is
           nothing to apply.</p>`
      : renderPlain(preview.explanation, "What applying this does") +
      (intro ? `<p class="why">${escape(intro)}</p>` : "") +
      `<div class="confirm-seg-bar" role="group" aria-label="Details and information">
         ...
```

(Task 6 replaces the rest of this block — the segmented bar — so do not worry about the exact surrounding markup here beyond adding the `intro` line; Task 6's diff will be against whatever this step leaves in place.)

- [ ] **Step 4: Update `_undoChange` to compute and pass the sentence**

Replace:

```javascript
  _undoChange(revision) {
    this._confirm("Undo this change", (confirm, keep, dashboard) => [
      "undo_change",
      // `preview` only on the call that shows one - the first, before
      // the write. The second call, with `confirm` true, already has
      // the diff this dialog is displaying; asking for it again would
      // pay for the same two dumps a second time for nothing shown.
      { dashboard, revision, confirm, preview: !confirm },
    ]);
  }
```

with:

```javascript
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
      `Puts this change back${kept}.`,
    );
  }
```

- [ ] **Step 5: Run to verify it passes**

Run: `python3 -m pytest tests/test_panel_behaviour.py -k test_the_undo_dialog_carries_the_kept_since_sentence -v`
Expected: PASS.

- [ ] **Step 6: Run the full suite and commit**

Run: `python3 -m pytest tests/ -v`
Expected: all PASS (the sentence used to be in the card via `_renderDetail`'s `offer` — Task 2 already removed it from there, so there is no duplicate to worry about).

```bash
git add custom_components/dashboard_history/panel.js tests/test_panel_behaviour.py
git commit -m "$(cat <<'EOF'
Move the "keeps N changes since" sentence into the Undo dialog

It used to sit in the card, next to a button that has since moved
into the unified action bar. Read at the point of confirming rather
than before it, matching the redesign's Undo overlay.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Replace the segmented diff/info toggle with a native pill + always-visible footnote

**Files:**
- Modify: `custom_components/dashboard_history/panel.js` (`_confirm`'s body-assembly and segmented-button JS)
- Modify: `custom_components/dashboard_history/panel/style.js` (remove `.confirm-seg-*`, `.confirm-info-panel*`, the `dialog.confirm details.raw > summary { display: none }` override)
- Modify/Delete: `tests/test_panel_behaviour.py` (the `confirm_segmented` fixture and its five tests, replaced)

**Interfaces:**
- No new public interface — this is a presentational simplification inside `_confirm`. The `intro`/`wantsKeep`/`request`/`title` parameters from Task 5 are unchanged.
- The `keeps`/`keepsContent`/`keepable` computation earlier in `_confirm` (lines ~1487-1569, untouched by this task) still produces exactly the same values; only how they reach the DOM changes.

- [ ] **Step 1: Read the current segmented-button tests so you know exactly what is being retired**

Run: `grep -n "_CONFIRM_SEGMENTED\|confirm_segmented" tests/test_panel_behaviour.py`

You should find the fixture `_CONFIRM_SEGMENTED`/`confirm_segmented` and five tests: `test_the_panel_buttons_say_that_they_disclose`, `test_the_disclosed_state_travels_with_the_panels`, `test_confirm_segmented_bar_starts_collapsed`, `test_confirm_segmented_bar_toggles_diff`, `test_confirm_segmented_bar_toggles_info_and_switches`. Delete the fixture and all five — the UI they test (two buttons play-acting a disclosure `<summary>` never got to be) no longer exists once this task lands.

- [ ] **Step 2: Write the replacement test first**

Add to `tests/test_panel_behaviour.py` in their place:

```python
_CONFIRM_PILL = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._mode = "advanced";
el._changes = [{ revision: "a" }, { revision: "b" }];
el.shadowRoot = node();
el._recorded = () => Promise.resolve();

el._call = (type, extra) => {
  if (type === "restore_state" && !extra.confirm)
    return Promise.resolve({
      applied: false,
      preview: "-a\\n+b",
      explanation: { groups: [], note: "one card removed" },
    });
  return Promise.resolve({ applied: true, changes: [], dashboards: [] });
};

const done = el._restoreState("b", "Back to this version");
await settle();

const dialog = el.shadowRoot.querySelector("dialog.confirm");
const raw = dialog.querySelector("details.raw");
const bodyHtml = dialog.querySelector(".body").innerHTML;

const beforeOpen = { rawOpen: raw.open };
raw.open = true;
raw._on.toggle?.();
const afterOpen = { rawOpen: raw.open };

dialog.close("cancel");
await done;

console.log(JSON.stringify({ bodyHtml, beforeOpen, afterOpen }));
"""


@pytest.fixture(scope="session")
def confirm_pill(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "confirm_pill", _CONFIRM_PILL)


def test_the_confirm_dialog_uses_the_same_pill_as_the_card(confirm_pill):
    # One component everywhere, per the redesign - no second
    # disclosure pattern built just for this dialog.
    assert '<span class="glyph">&lt;/&gt;</span> Show the technical details' in confirm_pill["bodyHtml"]
    assert "confirm-seg-bar" not in confirm_pill["bodyHtml"]
    assert "confirm-info-panel" not in confirm_pill["bodyHtml"]


def test_the_confirm_dialogs_pill_starts_closed(confirm_pill):
    assert confirm_pill["beforeOpen"]["rawOpen"] is False


def test_the_footnote_is_visible_without_any_toggle(confirm_pill):
    # "What the dashboard holds now is not lost..." used to be behind a
    # second, "Current state is preserved" button. It is now always
    # there whenever there is anything to say - no click needed.
    assert "What the dashboard holds now is not lost" in confirm_pill["bodyHtml"]
```

- [ ] **Step 3: Run to verify it fails**

Run: `python3 -m pytest tests/test_panel_behaviour.py -k "confirm_pill" -v`
Expected: FAIL (`confirm-seg-bar` is still present; the footnote is still hidden behind a toggle).

- [ ] **Step 4: Replace the body-assembly block in `_confirm`**

In `custom_components/dashboard_history/panel.js`, replace the `.body.innerHTML =` assignment through the end of the segmented-button wiring (from the line added in Task 5's Step 3 through the `if (rawDetails) { rawDetails.addEventListener("toggle", ...) }` block that follows it):

```javascript
    dialog.querySelector(".body").innerHTML = nothingToDo
      ? `<p>This state is what the dashboard holds right now, so there is
           nothing to apply.</p>`
      : renderPlain(preview.explanation, "What applying this does") +
      (intro ? `<p class="why">${escape(intro)}</p>` : "") +
      `<div class="confirm-seg-bar" role="group" aria-label="Details and information">
         <button type="button" class="confirm-seg-btn" data-seg="diff"
                 aria-expanded="false" aria-controls="confirm-diff-panel">
           <svg viewBox="0 0 20 20" width="15" height="15" fill="currentColor" class="seg-icon">
             <path fill-rule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4zm2 6a1 1 0 011-1h6a1 1 0 110 2H7a1 1 0 01-1-1zm1 3a1 1 0 100 2h6a1 1 0 100-2H7z" clip-rule="evenodd"/>
           </svg>
           <span>Show the technical details</span>
         </button>
         <button type="button" class="confirm-seg-btn" data-seg="info"
                 aria-expanded="false" aria-controls="confirm-info-panel"${keeps ? "" : " hidden"}>
           <svg viewBox="0 0 20 20" width="15" height="15" fill="currentColor" class="seg-icon">
             <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"/>
           </svg>
           <span>Current state is preserved</span>
         </button>
       </div>
       <div class="confirm-panels">
         <details class="raw" id="confirm-diff-panel">
           <summary>Show the technical details</summary>
           ${renderDiff(preview.preview)}
         </details>
         <div class="confirm-info-panel" id="confirm-info-panel" hidden>
           ${keepsContent}
         </div>
       </div>`;

    const segBar = dialog.querySelector(".confirm-seg-bar");
    const rawDetails = dialog.querySelector("details.raw");
    const infoPanel = dialog.querySelector(".confirm-info-panel");
    const diffBtn = segBar?.querySelector('[data-seg="diff"]');
    const infoBtn = segBar?.querySelector('[data-seg="info"]');

    let currentSeg = null;

    // `aria-expanded` and not `aria-pressed`, which is what these
    // carried at first. The two say different things, and the panel
    // uses both: the version dialog's patch/minor/major buttons are a
    // choice among alternatives, and pressed is right there. These two
    // disclose a panel. Pressed would announce a switch that is on and
    // never say that anything appeared, or where - and the `<summary>`
    // these buttons replaced said both by itself, before it was
    // hidden away with `display: none`. `aria-controls` names the
    // panel each one opens.
    const updateSegState = (activeSeg) => {
      currentSeg = activeSeg;
      if (diffBtn) {
        diffBtn.classList.toggle("active", activeSeg === "diff");
        diffBtn.setAttribute("aria-expanded", String(activeSeg === "diff"));
      }
      if (infoBtn) {
        infoBtn.classList.toggle("active", activeSeg === "info");
        infoBtn.setAttribute("aria-expanded", String(activeSeg === "info"));
      }
      if (rawDetails) {
        rawDetails.open = activeSeg === "diff";
      }
      if (infoPanel) {
        infoPanel.hidden = activeSeg !== "info";
      }
    };
    updateSegState(null);

    if (diffBtn) {
      diffBtn.addEventListener("click", () => {
        updateSegState(currentSeg === "diff" ? null : "diff");
      });
    }

    if (infoBtn) {
      infoBtn.addEventListener("click", () => {
        updateSegState(currentSeg === "info" ? null : "info");
      });
    }

    if (rawDetails) {
      rawDetails.addEventListener("toggle", () => {
        if (rawDetails.open && currentSeg !== "diff") {
          updateSegState("diff");
        } else if (!rawDetails.open && currentSeg === "diff") {
          updateSegState(null);
        }
      });
    }
```

with:

```javascript
    dialog.querySelector(".body").innerHTML = nothingToDo
      ? `<p>This state is what the dashboard holds right now, so there is
           nothing to apply.</p>`
      : renderPlain(preview.explanation, "What applying this does") +
      (intro ? `<p class="why">${escape(intro)}</p>` : "") +
      `<details class="raw">
         <summary><span class="glyph">&lt;/&gt;</span> Show the technical details</summary>
         ${renderDiff(preview.preview)}
       </details>
       ${keepsContent}`;
```

Nothing after this point in `_confirm` references `segBar`/`diffBtn`/`infoBtn`/`updateSegState`/`currentSeg` — verify with `grep -n "segBar\|diffBtn\|infoBtn\|updateSegState\|currentSeg" custom_components/dashboard_history/panel.js` and confirm zero remaining matches once this step is done.

- [ ] **Step 5: Remove the now-dead CSS**

In `custom_components/dashboard_history/panel/style.js`, remove this whole block (it sits right before the `.info-callout*` rules, under the comment `/* Segmented toggle bar for confirmation dialogs */`):

```css
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
```

Leave `.info-callout*` itself untouched right after this block — it is reused as-is for the always-visible footnote. Note that `dialog.confirm details.raw { margin-top: 10px; }` is removed along with the rest here: without a `display: none` override to fight, the plain `details.raw > summary` pill rule from Task 1 already gives the confirm dialog's pill the same `margin: 8px 0` every other pill has, so the dedicated 10px override is no longer needed.

- [ ] **Step 6: Run the style guard, then the new tests**

Run: `python3 -m pytest tests/test_panel_assets.py -v`
Expected: PASS.

Run: `python3 -m pytest tests/test_panel_behaviour.py -k "confirm_pill" -v`
Expected: PASS.

- [ ] **Step 7: Run the full suite**

Run: `python3 -m pytest tests/ -v`
Expected: all PASS. In particular, re-check `test_the_dialog_carries_the_technical_diff_and_the_promise` and `test_the_box_follows_the_mode` (both use the `keeping` fixture) — they assert `diffShown`/`keepsShown` booleans computed from the *old* markup; if that fixture greps for `confirm-seg-bar` or `data-seg` anywhere, update it to check for the new `details.raw`/`.info-callout` markup instead. Read the fixture before assuming it is unaffected.

- [ ] **Step 8: Commit**

```bash
git add custom_components/dashboard_history/panel.js custom_components/dashboard_history/panel/style.js tests/test_panel_behaviour.py
git commit -m "$(cat <<'EOF'
Replace the confirm dialog's segmented toggle with a native pill

Two buttons play-acted a disclosure and a tab switch that a styled
native <details>/<summary> already does on its own, and the "nothing
is lost" reassurance sat behind a second click it never needed - it
is the same sentence every time there is anything to keep. Pill now
shared verbatim between the card and every overlay; the reassurance is
always visible when it applies.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Full-suite verification and design-doc cross-check

**Files:** none changed; this task only verifies.

- [ ] **Step 1: Run the whole test suite**

Run: `python3 -m pytest tests/ -v`
Expected: `N passed` with no new failures compared to the baseline before Task 1 (some cases may skip visibly if `DASHBOARD_HISTORY_REAL_STORAGE`/`tests/.real-storage` are not set — that is expected and unrelated to this work).

- [ ] **Step 2: Grep for anything the redesign was supposed to retire**

Run: `grep -n 'class="more"\|"mkver"\|confirm-seg\|confirm-info-panel' custom_components/dashboard_history/panel.js custom_components/dashboard_history/panel/style.js`
Expected: no matches. If anything turns up, an earlier task's removal step was incomplete — go back and finish it before continuing.

- [ ] **Step 3: Cross-check against the design handoff's own checklist**

Re-read `exchange/design_handoff_history_card_1a/README.md`'s "Was geändert wurde" list (points 1-6) and confirm each is implemented exactly as agreed (including the two deviations recorded in this plan's Global Constraints — point 2's checkbox does *not* appear in the Undo overlay, and the checkbox default is *not* always-unchecked). Do not re-open either deviation; both were explicitly decided with the user before this plan was written.

- [ ] **Step 4: Manual smoke check, if a live/throwaway Home Assistant instance is available**

Per `CLAUDE.md`'s "Trying it on a real installation": if the throwaway Docker instance from `docker/compose.yaml` is set up, bring it up and open the panel, expand a change with an undoable predecessor, and confirm:
- One action bar with up to three buttons (Version up to here / Undo this change / Replace the whole dashboard…), no stacked expanders.
- The technical-details pill looks and behaves the same in the card and in both overlays.
- Opening "Replace the whole dashboard…" on a change with both a before and after candidate shows both immediately (no spinner on radio switch).
- The Undo overlay shows "Puts this change back and keeps N changes made since." and has no keep-as-version checkbox.
- The Replace overlay does have the keep-as-version checkbox, defaulting per today's simple/advanced-mode rule.

If no live instance is available, say so explicitly rather than claiming this step was done — per this project's "Verification Before Done" standard, a claim needs evidence, and there is none to give without an instance to look at.

- [ ] **Step 5: Confirm nothing outside this plan's scope was touched**

Run: `git diff --stat` (or `git diff main` if working on a branch) and check that the pre-existing, unrelated compare-mode changes already present in the working tree before this plan started (in `_toggleCompareRevision`, `_jumpToCompareFrom`, `_renderMain`'s compare bar, `rows.js`'s `versionHead`/`renderRow`) are still exactly as they were — this plan must not have touched them.
