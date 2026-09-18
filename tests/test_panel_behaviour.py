"""The panel's own logic, run in Node rather than read by a regex.

`panel.js` is a custom element, but the parts of it that can be wrong in
a way nobody sees - what it does with an answer that arrives late - need
no browser. Node loads the module with a two-line stand-in for the DOM,
the tests replace `_call` with promises they settle by hand, and then
look at the state the panel is left in.

Skipped visibly when there is no `node`, never silently: a skip that
looks like a pass is how this class of test stops meaning anything.
"""

import json
import re
import shutil
import subprocess

import pytest
from conftest import PACKAGE

PANEL = PACKAGE / "panel.js"

# The stand-in for the browser, and the two helpers every scenario uses:
# `settle` lets pending promises run, `answer` settles one held call the
# way the server would.
_PRELUDE = """
globalThis.HTMLElement = class {
  attachShadow() { return {}; }
  setAttribute(name, value) { (this._attrs ||= {})[name] = String(value); }
  getAttribute(name) { return this._attrs?.[name] ?? null; }
  removeAttribute(name) { delete this._attrs?.[name]; }
};
let Panel;
globalThis.customElements = {
  get() { return undefined; },
  define(name, cls) { Panel = cls; },
};
await import(%(url)s);
const settle = () => new Promise((r) => setTimeout(r, 0));
const answer = (call, mark) => {
  if (call.type === "explain") call.resolve({ groups: [], note: mark });
  else call.resolve({ available: false, reason: mark });
};

/**
 * A stand-in for one DOM node, deep enough for a dialog.
 *
 * Flat on purpose: every node answers a selector with a node of its
 * own, remembered per selector, and nothing looks inside anything
 * else. A scenario therefore has to query along the same path the code
 * does - `[data-keep]`, then `.keepbox`, never `.keepbox` straight from
 * the dialog - and that is the feature: a test that found a node the
 * code never touched would pass while proving nothing.
 *
 * The "remembered per selector" cache (`_seen`) is shared by the whole
 * tree, not kept one dictionary per node - `node(shared)` passes the
 * caller's own `_seen` down to whatever it hands back. A real
 * `querySelector` always resolves to the one live element no matter
 * which ancestor asks: `root.querySelectorAll(x)` and
 * `nested.querySelector(x)` find the same node when `x` matches only
 * once, wherever `nested` sits under `root`. Found by the 2026-09-12
 * review: with one cache per calling node instead, a click listener
 * the generic wiring attached via `root.querySelectorAll("[data-
 * compare-body]")` and the container `_openCompare` wrote its content
 * into via `dialog.querySelector("[data-compare-body]")` were two
 * disconnected phantom nodes - the listener bound to one, the content
 * went into the other - and the existing test never noticed, because
 * it queried the selector the listener was bound to and never went
 * anywhere near the one `_openCompare` actually populated.
 */
const node = (shared) => {
  const it = {
    textContent: "", innerHTML: "", value: "", checked: false,
    hidden: false, returnValue: "", open: false, dataset: {},
    _seen: shared || {}, _on: {},
    classList: {
      _classes: new Set(),
      toggle(c, force) {
        const has = this._classes.has(c);
        const should = force !== undefined ? Boolean(force) : !has;
        if (should) this._classes.add(c);
        else this._classes.delete(c);
        return should;
      },
      add(...cs) { cs.forEach((c) => this._classes.add(c)); },
      remove(...cs) { cs.forEach((c) => this._classes.delete(c)); },
      contains(c) { return this._classes.has(c); },
    },
    _attrs: {},
    querySelector(selector) {
      if (selector === "dialog[open]") {
        for (const key of Object.keys(it._seen)) {
          if (key.startsWith("dialog") && it._seen[key]?.open) return it._seen[key];
        }
        return null;
      }
      return (it._seen[selector] ||= node(it._seen));
    },
    querySelectorAll(selector) { return [it.querySelector(selector)]; },
    addEventListener(name, run) { it._on[name] = run; },
    // No real tree to walk, so a scenario that needs an ancestor sets it
    // by hand on `_closest` before firing the click - `element._closest =
    // { "dialog.compare": dialog }` - and an unset selector answers null,
    // same as an ordinary miss. Added once a click handler wired through
    // `onClick` (which always asks `.closest("summary")` first) needed
    // firing for real rather than calling the method it wires straight.
    _closest: {},
    closest(selector) {
      return Object.prototype.hasOwnProperty.call(it._closest, selector)
        ? it._closest[selector]
        : null;
    },
    // `setAttribute` remembers, the other two are no-ops: the version
    // dialog presses its level buttons into shape with `setAttribute`
    // and puts the cursor in the title field, and the description
    // dialog selects the text it prefilled. A stand-in that cannot be
    // told any of it makes those flows untestable for a reason that
    // has nothing to do with what they do. (Scenarios older than this
    // hand their own in; those still work, and are left alone.)
    //
    // Written down rather than dropped, since 2026-09-11: what a
    // control announces to somebody who cannot see it - aria-expanded
    // on the confirmation dialog's two panel buttons - is state like
    // any other, and a stand-in that forgets it makes the one kind of
    // regression that no screenshot shows untestable as well.
    setAttribute(name, value) { it._attrs[name] = String(value); },
    getAttribute(name) { return name in it._attrs ? it._attrs[name] : null; },
    // Added when the footnote strip learned to drop a tooltip it had set
    // for an earlier dialog: a stand-in that only remembers attributes
    // and never forgets them cannot tell "no tooltip" from "the one from
    // last time", which is exactly the bug that call prevents.
    removeAttribute(name) { delete it._attrs[name]; },
    focus() {},
    select() {},
    showModal() { it.open = true; },
    close(value) {
      it.open = false;
      // Exactly what a browser does: a value handed over by a button is
      // remembered, and a dialog dismissed with Escape leaves the last
      // one standing. That is the whole reason `_confirm` clears it
      // before opening.
      if (value !== undefined) it.returnValue = value;
      it._on.close?.();
    },
  };
  return it;
};

// One turn before any scenario starts. The parts arrive over dynamic
// imports, so `renderPlain` and `renderDiff` are still undefined in
// this module's first synchronous pass - measured on 2026-09-04: a
// scenario reaching either one dies with "renderPlain is not a
// function" before its first assertion, and the whole file goes red
// for a reason that has nothing to do with what it tests.
await settle();
"""


def _run_in_node(tmp_path_factory, name, scenario):
    """Run `scenario` after the prelude in Node; the last stdout line is JSON."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed; the panel's logic cannot be run here")
    harness = tmp_path_factory.mktemp("panel") / f"{name}.mjs"
    harness.write_text(
        (_PRELUDE + scenario) % {"url": json.dumps(PANEL.as_uri())}, encoding="utf-8"
    )
    run = subprocess.run(
        [node, str(harness)], capture_output=True, text=True, timeout=60, check=False
    )
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout.strip().splitlines()[-1])


_HARNESS = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._changes = [
  { revision: "a", previous: "b" },
  { revision: "b", previous: "c" },
  { revision: "c", previous: null },
];

// Every WebSocket call is held until the test lets it go.
const calls = [];
el._call = (type, extra) =>
  new Promise((resolve) => calls.push({ type, extra, resolve }));

// Row "a" is opened, then row "b" before "a" has answered.
el._expand("a");
el._expand("b");
const forA = calls.slice(0, 2);
const forB = calls.slice(2, 4);

// "b" answers first...
forB.forEach((call) => answer(call, "B"));
await settle();
const afterB = { open: el._open, explanation: el._explanation?.note, busy: !!el._busy };

// ...and "a" answers last, for a row nobody is looking at any more.
forA.forEach((call) => answer(call, "A"));
await settle();
const afterA = { open: el._open, explanation: el._explanation?.note, busy: !!el._busy };

console.log(JSON.stringify({ afterB, afterA }));
"""


@pytest.fixture(scope="module")
def outcome(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "late-answer", _HARNESS)


def test_a_late_answer_for_a_row_no_longer_open_is_dropped(outcome):
    # Measured on 2026-09-03: the answer for "a" landed after "b" had
    # been chosen and drawn, and the row marked "b" showed "a"'s answer.
    assert outcome["afterA"]["open"] == "b"
    assert outcome["afterA"]["explanation"] == "B"


def test_the_page_stays_busy_while_an_earlier_request_is_still_in_flight(outcome):
    # `_busy` was a boolean, so the first request to finish switched the
    # indicator off while the other was still running.
    assert outcome["afterB"]["busy"] is True
    assert outcome["afterA"]["busy"] is False


# -- errors and repeats belong to the request that made them ----------------
#
# Found by a second review on 2026-09-04. The stale check compared the
# selection (or the open revision) after the answer came - but `_guard`
# had already written a late *failure* into the error banner, and two
# requests for the same row could not be told apart at all.

_HARNESS_GENERATIONS = """
// 1. Dashboard A is chosen, then B. B answers; A fails, late.
//
// `_select` asks for both "history" and "versions" at once (task 5), so
// a fixed position no longer names a single dashboard's call - answered
// by type and by the dashboard each call named instead.
const one = new Panel();
one._render = () => {};
const calls = [];
one._call = (type, extra) =>
  new Promise((resolve, reject) => calls.push({ type, extra, resolve, reject }));
one._select("A");
one._select("B");
const forDash = (type, dashboard) =>
  calls.find((c) => c.type === type && c.extra.dashboard === dashboard);
forDash("history", "B").resolve({ changes: [{ revision: "B-new" }] });
forDash("versions", "B").resolve({ versions: [] });
await settle();
forDash("history", "A").reject(new Error("A failed late"));
await settle();
const lateFailure = {
  selected: one._selected,
  changes: one._changes.map((c) => c.revision),
  error: one._error,
};

// 2. Row "a" is opened, then "b", then "a" again. The second "a" answers
// first, the first "a" last.
const two = new Panel();
two._render = () => {};
two._selected = "dash";
two._changes = [
  { revision: "a", previous: "b" },
  { revision: "b", previous: "c" },
  { revision: "c", previous: null },
];
const opened = [];
two._call = (type, extra) =>
  new Promise((resolve) => opened.push({ type, extra, resolve }));
two._expand("a");
two._expand("b");
two._expand("a");
const firstA = opened.slice(0, 2);
const forB = opened.slice(2, 4);
const secondA = opened.slice(4, 6);
secondA.forEach((call) => answer(call, "A2"));
forB.forEach((call) => answer(call, "B"));
await settle();
firstA.forEach((call) => answer(call, "A1"));
await settle();
const repeat = { open: two._open, explanation: two._explanation?.note };

console.log(JSON.stringify({ lateFailure, repeat }));
"""


@pytest.fixture(scope="module")
def generations(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "generations", _HARNESS_GENERATIONS)


def test_a_late_failure_of_a_superseded_request_shows_no_error(generations):
    assert generations["lateFailure"]["selected"] == "B"
    assert generations["lateFailure"]["changes"] == ["B-new"]
    assert generations["lateFailure"]["error"] is None


def test_reopening_the_same_row_keeps_the_newer_answer(generations):
    assert generations["repeat"]["open"] == "a"
    assert generations["repeat"]["explanation"] == "A2"


# Answered by *type*, never by position, and tolerantly: task 5 gives
# `_select` a second call, and a scenario that popped a fixed number of
# them would go red there for a reason that has nothing to do with
# paging. This shape survives both.
_HELD = """
const calls = [];
el._call = (type, extra) =>
  new Promise((resolve) => calls.push({ type, extra, resolve }));
const waiting = (type) => calls.find((c) => c.type === type);
const reply = (type, value) => {
  const at = calls.findIndex((c) => c.type === type);
  if (at >= 0) calls.splice(at, 1)[0].resolve(value);
};
const openOn = async (key, changes, cursor) => {
  const done = el._select(key);
  await settle();
  reply("versions", { versions: [] });
  reply("history", { changes, next_cursor: cursor });
  await done;
};
"""

_PAGING = """
const el = new Panel();
el._render = () => {};
""" + _HELD + """
await openOn("dash", [{ revision: "a" }, { revision: "b" }], "b");

const older = el._loadOlder();
await settle();
const askedFor = waiting("history").extra;
reply("history", {
  changes: [{ revision: "c" }, { revision: "d" }],
  next_cursor: null,
});
await older;

console.log(JSON.stringify({
  revisions: el._changes.map((c) => c.revision),
  askedFor,
  cursor: el._cursor,
}));
"""


@pytest.fixture(scope="session")
def paging(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "paging", _PAGING)


def test_older_entries_are_appended_and_not_substituted(paging):
    # Replacing would lose the page above and leave the list shorter
    # after pressing a button labelled "load older".
    assert paging["revisions"] == ["a", "b", "c", "d"]


def test_the_next_page_is_asked_for_by_cursor(paging):
    # By the cursor the server handed out, never by an offset: an offset
    # drifts when somebody saves while the page is being read.
    assert paging["askedFor"]["before"] == "b"
    assert paging["askedFor"]["limit"] == 25


def test_the_end_of_the_history_is_remembered(paging):
    # None means there is nothing older. The button goes away rather
    # than fetching an empty page for whoever presses it again.
    assert paging["cursor"] is None


_PAGING_RESET = """
const el = new Panel();
el._render = () => {};
""" + _HELD + """
await openOn("a-dash", [{ revision: "x" }], "x");
const between = el._cursor;

const two = el._select("b-dash");
await settle();
const askedFor = waiting("history").extra;

// The switch is still in flight. Ask for an older page now: without the
// reset in `_select`, `_loadOlder` would still be holding a-dash's
// cursor while `_selected` already says b-dash, and would ask b-dash for
// the page before a commit only a-dash ever had. Not awaited - with the
// reset there is nothing to await, and without it there would be a
// request nobody answers.
el._loadOlder();
await settle();
const leaked = calls.filter(
  (c) => c.type === "history" && c.extra && c.extra.before,
).length;

reply("versions", { versions: [] });
reply("history", { changes: [{ revision: "y" }], next_cursor: null });
await two;

console.log(JSON.stringify({
  between,
  askedFor,
  leaked,
  after: el._changes.map((c) => c.revision),
}));
"""


@pytest.fixture(scope="session")
def paging_reset(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "paging_reset", _PAGING_RESET)


def test_another_dashboard_starts_at_the_top_again(paging_reset):
    # A cursor from one dashboard handed to another would ask for the
    # entries after a commit that dashboard never had.
    assert paging_reset["between"] == "x"
    assert "before" not in paging_reset["askedFor"]
    assert paging_reset["after"] == ["y"]
    # The one that needs the reset to be there. `_select` never sends a
    # `before` of its own, so the two lines above hold whether or not the
    # cursor was cleared; only pressing "load older" mid-switch tells
    # them apart. Deleting `this._cursor = null` from `_select` turns
    # this from 0 into 1.
    assert paging_reset["leaked"] == 0


_MODE = """
const stored = {};
globalThis.localStorage = {
  getItem: (k) => (k in stored ? stored[k] : null),
  setItem: (k, v) => { stored[k] = String(v); },
};

const el = new Panel();
el._render = () => {};
const fresh = el._mode;

el._setMode("advanced");
const afterSwitch = el._mode;
const remembered = stored["dashboard-history:mode"];

const second = new Panel();
second._render = () => {};
const carried = second._mode;

// A stored value nobody recognises must not leave the panel blank.
stored["dashboard-history:mode"] = "sideways";
const third = new Panel();
third._render = () => {};

console.log(JSON.stringify({
  fresh, afterSwitch, remembered, carried, nonsense: third._mode,
}));
"""


@pytest.fixture(scope="session")
def mode(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "mode", _MODE)


def test_a_fresh_panel_opens_in_the_simple_mode(mode):
    # Decision 17 makes it the normal way. Somebody who wants the other
    # one switches once; somebody who needs this one would never look.
    assert mode["fresh"] == "simple"


def test_the_choice_is_remembered(mode):
    assert mode["afterSwitch"] == "advanced"
    assert mode["remembered"] == "advanced"
    assert mode["carried"] == "advanced"


def test_a_stored_value_nobody_recognises_falls_back(mode):
    # Anything can be in there - an older version of this panel, a hand
    # edit. A blank page would be the one unrecoverable answer.
    assert mode["nonsense"] == "simple"


_NO_STORAGE = """
globalThis.localStorage = {
  getItem() { throw new Error("site data is blocked"); },
  setItem() { throw new Error("site data is blocked"); },
};
const el = new Panel();
el._render = () => {};
const fresh = el._mode;
el._setMode("advanced");
console.log(JSON.stringify({ fresh, afterSwitch: el._mode }));
"""


@pytest.fixture(scope="session")
def no_storage(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "no_storage", _NO_STORAGE)


def test_a_browser_that_refuses_to_remember_still_shows_the_panel(no_storage):
    # A private window, or site data switched off. It costs the memory
    # of the choice and must never cost the page.
    assert no_storage["fresh"] == "simple"
    assert no_storage["afterSwitch"] == "advanced"


_SEGMENTED_CONTROL = """
const el = new Panel();
el._render = () => {};

// Initial simple mode:
const simpleHtml = el._renderModeSwitch();

// Switch to advanced mode:
el._setMode("advanced");
const advancedHtml = el._renderModeSwitch();

console.log(JSON.stringify({
  simpleHtml,
  advancedHtml,
}));
"""


@pytest.fixture(scope="session")
def segmented_control(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "segmented_control", _SEGMENTED_CONTROL)


def test_segmented_control_renders_radiogroup_with_glider(segmented_control):
    html = segmented_control["simpleHtml"]
    assert 'class="segmented-control"' in html
    assert 'role="radiogroup"' in html
    assert 'class="segmented-control__glider"' in html
    assert 'value="simple"' in html
    assert 'value="advanced"' in html


def test_segmented_control_reflects_simple_mode(segmented_control):
    html = segmented_control["simpleHtml"]
    assert 'value="simple" checked' in html
    assert 'value="advanced" checked' not in html


def test_segmented_control_reflects_advanced_mode(segmented_control):
    html = segmented_control["advancedHtml"]
    assert 'value="advanced" checked' in html
    assert 'value="simple" checked' not in html


# -- the glider's 180 ms must not outlive the panel ------------------------

_MODE_SLIDE = """
const el = new Panel();
el._render = () => {};
el._mode = "simple";

// Clicked, then the panel is left before the glider has arrived.
el._modeAfterSlide("advanced");
const modeRightAfterClick = el._mode;
const timerWasHeld = el._modeSlide !== null;
el.disconnectedCallback();
const timerWasCleared = el._modeSlide === null;
await new Promise((r) => setTimeout(r, 300));
const modeAfterLeaving = el._mode;

// Nobody leaves: the switch lands.
const stays = new Panel();
stays._render = () => {};
stays._mode = "simple";
stays._modeAfterSlide("advanced");
await new Promise((r) => setTimeout(r, 300));
const modeAfterWaiting = stays._mode;

// Two clicks inside the window are one switch, not two.
const twice = new Panel();
twice._render = () => {};
twice._mode = "simple";
const switched = [];
twice._setMode = (m) => switched.push(m);
twice._modeAfterSlide("advanced");
twice._modeAfterSlide("simple");
await new Promise((r) => setTimeout(r, 300));

console.log(JSON.stringify({
  modeRightAfterClick,
  timerWasHeld,
  timerWasCleared,
  modeAfterLeaving,
  modeAfterWaiting,
  switched,
}));
"""


@pytest.fixture(scope="session")
def mode_slide(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "mode_slide", _MODE_SLIDE)


def test_the_mode_switch_waits_for_its_glider(mode_slide):
    assert mode_slide["modeRightAfterClick"] == "simple"
    assert mode_slide["timerWasHeld"] is True
    assert mode_slide["modeAfterWaiting"] == "advanced"


def test_leaving_the_panel_calls_off_a_pending_mode_switch(mode_slide):
    # `_setMode` puts a standing search again, and that walks the whole
    # history. Running it for a page nobody is on is what
    # `disconnectedCallback` already cancelled a keystroke for.
    assert mode_slide["timerWasCleared"] is True
    assert mode_slide["modeAfterLeaving"] == "simple"


def test_two_clicks_inside_the_window_make_one_switch(mode_slide):
    assert mode_slide["switched"] == ["simple"]



_VERSIONS_LOADED = """
const el = new Panel();
el._render = () => {};

const calls = [];
el._call = (type, extra) =>
  new Promise((resolve) => calls.push({ type, extra, resolve }));

const picked = el._select("dash");
await settle();
// Both are asked for at once; the order they answer in must not matter.
const types = calls.map((c) => c.type).sort();
calls.find((c) => c.type === "versions").resolve({
  versions: [{ name: "dash/v1.0.0", title: "1 September 2026", revision: "b" }],
});
calls.find((c) => c.type === "history").resolve({
  changes: [{ revision: "a" }, { revision: "b" }],
  next_cursor: null,
});
await picked;

console.log(JSON.stringify({
  types,
  versions: el._versions.map((v) => v.name),
  changes: el._changes.map((c) => c.revision),
}));
"""


@pytest.fixture(scope="session")
def versions_loaded(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "versions_loaded", _VERSIONS_LOADED)


def test_picking_a_dashboard_fetches_its_versions_too(versions_loaded):
    # The simple mode is built from the complete version list, not from
    # the versions that happen to sit on a loaded change - which is the
    # finding project G exists for.
    assert versions_loaded["types"] == ["history", "versions"]
    assert versions_loaded["versions"] == ["dash/v1.0.0"]
    assert versions_loaded["changes"] == ["a", "b"]


_MATCHING_FROM_SERVER = """
const el = new Panel();
el._render = () => {};

const calls = [];
el._call = (type, extra) =>
  new Promise((resolve) => calls.push({ type, extra, resolve }));

const picked = el._select("dash");
await settle();
calls.find((c) => c.type === "versions").resolve({ versions: [] });
// The version sits on `deep`, which the loaded window does not contain.
// That is the whole point: the server counted it, the panel could not.
calls.find((c) => c.type === "history").resolve({
  changes: [{ revision: "new", same_as_now: true, versions: [] }],
  next_cursor: "older",
  matching_versions: [{ name: "dash/v1.0.0", revision: "deep" }],
});
await picked;

console.log(JSON.stringify({
  loaded: el._changes.map((c) => c.revision),
  matching: el._versionsMatchingNow(),
  chip: el._matchingElsewhere(el._changes[0]),
}));
"""


@pytest.fixture(scope="session")
def matching_from_server(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "matching_from_server", _MATCHING_FROM_SERVER)


def test_a_matching_version_below_the_window_keeps_its_name(matching_from_server):
    # The negative control for reading `matching_versions` instead of
    # working it out again. `dash/v1.0.0` marks `deep`, and `deep` is not
    # among the loaded changes - so any answer computed over
    # `this._changes` is the empty list, and this case goes red. That
    # recomputation is exactly what the panel did before, and exactly
    # what project G measured as losing versions below the window.
    assert matching_from_server["loaded"] == ["new"]
    assert matching_from_server["matching"] == ["v1.0.0"]
    assert matching_from_server["chip"] == ["v1.0.0"]


_REFRESHED = """
const el = new Panel();
el._render = () => {};
""" + _HELD + """
await openOn("dash", [{ revision: "a" }], "older");

// Load a second page, so a refresh has something it could wrongly keep.
el._loadOlder();
await settle();
reply("history", { changes: [{ revision: "b" }], next_cursor: "deeper" });
await settle();
const paged = { rows: el._changes.map((c) => c.revision), cursor: el._cursor };

const again = el._refresh();
await settle();
reply("dashboards", { dashboards: [{ key: "dash", exists: true }] });
await settle();
const types = calls.map((c) => c.type).sort();
reply("history", {
  changes: [{ revision: "c" }, { revision: "a" }],
  next_cursor: "older",
  matching_versions: [{ name: "dash/v2.0.0", revision: "deep" }],
});
reply("versions", {
  versions: [{ name: "dash/v2.0.0", title: "t", revision: "deep" }],
});
await again;

console.log(JSON.stringify({
  paged,
  types,
  rows: el._changes.map((c) => c.revision),
  cursor: el._cursor,
  matching: el._versionsMatchingNow(),
  versions: el._versions.map((v) => v.name),
}));
"""


@pytest.fixture(scope="session")
def refreshed(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "refreshed", _REFRESHED)


def test_a_refresh_asks_for_both_and_starts_at_the_top(refreshed):
    # `_refresh` is reached by an event rather than by a click, so no
    # scenario had ever run it - and it carries the same two answers
    # `_select` does, plus a decision of its own about paging.
    assert refreshed["paged"] == {"rows": ["a", "b"], "cursor": "deeper"}
    # Both answers, not just the history: the simple mode is drawn from
    # the version list, and a refresh that renewed only one of them would
    # leave the two modes disagreeing about the same dashboard.
    assert refreshed["types"] == ["history", "versions"]
    # Back to the first page on purpose. A refresh happens because the
    # history grew; stitching a fresh top onto pages fetched before it
    # grew would show a list that never existed.
    assert refreshed["rows"] == ["c", "a"]
    assert refreshed["cursor"] == "older"
    # And the server's answer is read here too, not worked out again:
    # `deep` is not among the loaded rows.
    assert refreshed["matching"] == ["v2.0.0"]
    assert refreshed["versions"] == ["dash/v2.0.0"]


_REFRESH_OPEN = """
const el = new Panel();
el._render = () => {};
""" + _HELD + """
await openOn("dash", [{ revision: "a", previous: "b" }], null);

// A row is open, and the history then grows behind it. The row keeps
// its place only if the panel can find it again by revision - by index
// it would now be one further down.
el._open = "a";

const again = el._refresh();
await settle();
reply("dashboards", { dashboards: [{ key: "dash", exists: true }] });
await settle();
reply("history", {
  changes: [
    { revision: "new", previous: "a" },
    { revision: "a", previous: "b" },
  ],
  next_cursor: null,
});
reply("versions", { versions: [] });
await settle();
// The detail is fetched again rather than kept, and explain asks
// against the row's own revision.
const explained = calls.find((c) => c.type === "explain")?.extra.revision;
reply("explain", { groups: [] });
reply("undo_change", { available: false });
await again;

console.log(JSON.stringify({
  open: el._open,
  rows: el._changes.map((c) => c.revision),
  explained,
}));
"""


@pytest.fixture(scope="session")
def refresh_open(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "refresh_open", _REFRESH_OPEN)


def test_an_open_row_survives_a_refresh_that_moved_it(refresh_open):
    # The row was first and is now second. Found by revision it is the
    # same row; found by index it would be the new one above it.
    assert refresh_open["rows"] == ["new", "a"]
    assert refresh_open["open"] == "a"
    assert refresh_open["explained"] == "a"


_KEEP = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._mode = "simple";
el._changes = [{ revision: "a" }, { revision: "b" }];
el.shadowRoot = node();
// A timer and a server event, neither of which says anything about
// what gets sent - and the three-second fallback would say it slowly.
el._recorded = () => Promise.resolve();

const sent = [];
el._call = (type, extra) => {
  sent.push({ type, extra });
  if (type === "restore_state" && !extra.confirm)
    return Promise.resolve({
      applied: false,
      preview: "-a\\n+b",
      explanation: { groups: [], note: "one card removed" },
    });
  return Promise.resolve({ applied: true, changes: [], dashboards: [] });
};

const dialog = () => el.shadowRoot.querySelector("dialog.confirm");
const box = () =>
  el.shadowRoot.querySelector("[data-keep]").querySelector(".keepbox");
const press = async (value) => {
  const done = el._restoreState("b", "Back to this version");
  await settle();
  const seen = {
    body: dialog().querySelector(".body").innerHTML,
    footnote: dialog()
      .querySelector("[data-footnote]")
      .querySelector("[data-footnote-text]").textContent,
    ticked: box().checked,
    title: box() && el.shadowRoot
      .querySelector("[data-keep]").querySelector(".keeptitle").value,
    fieldsHidden: el.shadowRoot
      .querySelector("[data-keep]").querySelector(".keepfields").hidden,
  };
  dialog().close(value);
  await done;
  return seen;
};

const simple = await press("apply");
const kept = sent.filter((c) => c.type === "restore_state" && c.extra.confirm);

el._mode = "advanced";
const advanced = await press("apply");
const plain = sent.filter((c) => c.type === "restore_state" && c.extra.confirm);

// Dismissed without pressing anything - Escape. The stand-in still
// carries "apply" from the run above, exactly as a browser would.
const before = sent.length;
await press(undefined);

console.log(JSON.stringify({
  previewFirst: sent[0].extra.confirm === false,
  diffShown: simple.body.includes("Technical details"),
  keepsShown: simple.footnote.includes("Nothing is lost"),
  tickedInSimple: simple.ticked,
  fieldsHiddenInSimple: simple.fieldsHidden,
  offeredTitle: simple.title,
  clearInAdvanced: advanced.ticked,
  fieldsHiddenInAdvanced: advanced.fieldsHidden,
  withKeep: kept[0].extra.keep_as_version ?? null,
  withoutKeep: plain[1].extra.keep_as_version ?? null,
  afterEscape: sent.length - before,
}));
"""


@pytest.fixture(scope="session")
def keeping(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "keeping", _KEEP)


_KEEP_FAILED = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._mode = "simple";
el._changes = [{ revision: "a" }, { revision: "b" }];
el.shadowRoot = node();
el._recorded = () => Promise.resolve();
el._select = async () => {};
el._loadDashboardsQuietly = async () => {};

let nextAnswer = {};
el._call = (type, extra) => {
  if (type === "restore_state" && !extra.confirm)
    return Promise.resolve({
      applied: false,
      preview: "-a\\n+b",
      explanation: { groups: [], note: "one card removed" },
    });
  if (type === "restore_state") return Promise.resolve(nextAnswer);
  return Promise.resolve({ applied: true, changes: [], dashboards: [] });
};

const dialog = () => el.shadowRoot.querySelector("dialog.confirm");
const press = async () => {
  el._error = "";
  const done = el._restoreState("b", "Back to this version");
  await settle();
  dialog().close("apply");
  await done;
  // No banner at all and an empty one mean the same thing here: `_guard`
  // clears the field to null on its way in, so only a written one differs.
  return el._error || "";
};

// The dashboard went back, but the state it replaced could not be
// marked. Nothing on the screen would say so otherwise: the restore
// itself succeeded.
nextAnswer = {
  applied: true,
  kept_as_version: { created: null, error: "the live state is not recorded" },
};
const spoken = await press();

// The same failure, reported twice by the server - `operations` hands
// the one into the other. Said once, or the reader thinks two things
// went wrong.
nextAnswer = {
  applied: true,
  note: "the live state is not recorded",
  kept_as_version: { created: null, error: "the live state is not recorded" },
};
const once = await press();

// A note about something else entirely, with a failed version beside
// it. Two different things went wrong, and the order decides which one
// is said: `note` is what the write itself answered, and it sits ahead
// of the version failure. Put the version failure first and this
// sentence disappears behind it.
nextAnswer = {
  applied: true,
  note: "the dashboard was recreated",
  kept_as_version: { created: null, error: "the live state is not recorded" },
};
const ordered = await press();

// It worked. There is nothing to report, and a banner here would be an
// alarm about a success.
nextAnswer = { applied: true, kept_as_version: { created: "dash/v1.0.1" } };
const quiet = await press();

console.log(JSON.stringify({ spoken, once, ordered, quiet }));
"""


@pytest.fixture(scope="session")
def keep_failed(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "keep_failed", _KEEP_FAILED)


def test_a_version_that_could_not_be_kept_is_said_out_loud(keep_failed):
    # The silent path. The restore worked, so the screen looks right;
    # only the banner can say the version was not made.
    assert keep_failed["spoken"] == (
        "the dashboard went back, but no version was made: "
        "the live state is not recorded"
    )


def test_the_note_from_the_write_is_said_ahead_of_a_failed_version(keep_failed):
    """The `||` order, which is the thing that decides anything here.

    This case used to be called `…the_same_failure_is_not_reported_twice`
    and asserted only the first line below. It could fail - but not for
    what its name promised: the condition `failed !== applied?.note` in
    `panel.js` decides no outcome at all, which the code says of itself
    ("Removing this condition changes no outcome (measured)"). What
    keeps the same sentence from being printed twice is the ordering,
    and the ordering is what a later edit has to leave alone.

    So both halves of it are held here. First: where the two are the
    same sentence - `operations` hands the one into the other when the
    live state could not be recorded - it is said once, because `note`
    comes first and nothing appends to it. Second, and this is the half
    the old name hid: where they are *different* sentences, the note
    still wins. Put `keptFailed` ahead of `note` and a dashboard that
    was recreated stops saying so.
    """
    assert keep_failed["once"] == "the live state is not recorded"
    assert keep_failed["ordered"] == "the dashboard was recreated"


def test_a_version_that_was_kept_says_nothing(keep_failed):
    # Success is not news. A banner here would be an alarm about a
    # thing that went right.
    assert keep_failed["quiet"] == ""


_KEEP_SUPPRESSED = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._mode = "simple";
el._changes = [{ revision: "a" }, { revision: "b" }];
el._recorded = () => Promise.resolve();
el._select = async () => {};
el._loadDashboardsQuietly = async () => {};

let preview = {};
const sent = [];
el._call = (type, extra) => {
  sent.push({ type, extra });
  if (type === "restore_state" && !extra.confirm) return Promise.resolve(preview);
  return Promise.resolve({ applied: true, changes: [], dashboards: [] });
};

// A fresh stand-in per attempt: `querySelector` remembers what it
// handed out, so a box ticked in one case would still be ticked in the
// next and the answer would be about the wrong run.
const attempt = async (shape, matching = []) => {
  preview = shape;
  // What `history` answered about the live state, which is where the
  // panel's own answer to "is this already a version" comes from.
  // Handed in per attempt rather than set once: the default puts it
  // back to none, so the control case below cannot inherit it.
  el._matching = matching;
  el.shadowRoot = node();
  const at = sent.length;
  const done = el._restoreState("b", "Back to this version");
  await settle();
  const offered = !el.shadowRoot.querySelector("[data-keep]").hidden;
  // Along the same path the code walks - the stand-in remembers what it
  // handed out per node, so a second lookup from the shadow root would
  // be a different `.body` than the one `_confirm` wrote into.
  const dialog = el.shadowRoot.querySelector("dialog.confirm");
  const body = dialog.querySelector(".body").innerHTML;
  // Out of the body since the redesign: the sentence is a strip of its
  // own between body and buttons, so it has to be read where the code
  // writes it rather than where it used to sit.
  const footnote = dialog
    .querySelector("[data-footnote]")
    .querySelector("[data-footnote-text]").textContent;
  dialog.close("apply");
  await done;
  const confirming = sent
    .slice(at)
    .find((c) => c.type === "restore_state" && c.extra.confirm);
  return {
    offered,
    body,
    footnote,
    sentKeep: confirming ? confirming.extra.keep_as_version ?? null : null,
  };
};

// The state is already the live one. There is nothing to apply, so
// there is nothing being replaced that could be worth keeping.
const nothing = await attempt({
  applied: false,
  preview: "",
  note: "This state is what the dashboard holds right now",
});

// The dashboard is gone and this restore recreates it. There is no
// live state to keep, and a tick box whose only outcome is a failure
// is worse than none.
const recreating = await attempt({
  applied: false,
  preview: "-a\\n+b",
  creates_dashboard: true,
  explanation: { groups: [], note: "" },
});

// Going back while what the dashboard holds is what a version holds
// already. The box exists to stop a state disappearing from a list
// that shows nothing but versions - and this state is in that list,
// under a name, so there is nothing for it to save. Measured on the
// test rig 2026-09-08: two moves back and forth left v0.0.5 and
// v0.0.6, byte-identical to v0.0.3 and v0.0.4 and titled with the day.
//
// One preview for both runs below, bound rather than written twice: the
// control case only controls anything while it is the *same* restore
// with no version holding the state. Two literals drifting apart would
// break that silently.
const restoring = {
  applied: false,
  preview: "-a\\n+b",
  explanation: { groups: [], note: "one card removed" },
};
const covered = await attempt(restoring, [{ name: "dash/v0.0.4" }]);

// The ordinary case, in the same harness, so that "not offered" above
// means the offer was withheld rather than never reachable.
const ordinary = await attempt(restoring);

console.log(JSON.stringify({ nothing, recreating, covered, ordinary }));
"""


@pytest.fixture(scope="session")
def keep_suppressed(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "keep_suppressed", _KEEP_SUPPRESSED)


def test_nothing_to_apply_offers_nothing_to_keep(keep_suppressed):
    assert keep_suppressed["nothing"]["offered"] is False
    # And the offer being hidden is not enough on its own: a suppressed
    # offer must not send a version either, however the dialog is closed.
    assert keep_suppressed["nothing"]["sentKeep"] is None


def test_recreating_a_dashboard_offers_nothing_to_keep(keep_suppressed):
    assert keep_suppressed["recreating"]["offered"] is False
    assert keep_suppressed["recreating"]["sentKeep"] is None


def test_a_state_a_version_already_holds_offers_nothing_to_keep(keep_suppressed):
    """The tick box is about a loss, and here there is none.

    Going back and forth between two states used to collect one dated
    version per move, each byte-identical to an older one: the box is
    ticked by default in the simple mode, and nothing asked whether the
    state it was about was already named. Rows that duplicate a version
    are exactly the wall the simple mode exists to avoid - the same
    reason a day mark is skipped in `milestones.py` when the highest
    version already holds that state.
    """
    assert keep_suppressed["covered"]["offered"] is False
    assert keep_suppressed["covered"]["sentKeep"] is None
    # And the box's absence is explained rather than silent. Without
    # this the offer somebody is used to seeing is simply gone, which
    # reads as a fault in the tool. The sentence it replaces - "Nothing
    # is lost", for the case where no version holds the state - is held
    # by `test_the_dialog_carries_the_technical_diff_and_the_promise`.
    assert "v0.0.4" in keep_suppressed["covered"]["footnote"]


def test_an_ordinary_restore_still_offers_to_keep(keep_suppressed):
    # The control for the two above. Without it, "not offered" would
    # also be the answer if the harness could never show an offer at all.
    assert keep_suppressed["ordinary"]["offered"] is True
    assert keep_suppressed["ordinary"]["sentKeep"]["level"] == "patch"


def test_the_preview_is_fetched_before_anything_is_written(keeping):
    # The hard rule: nothing that writes a dashboard state goes without
    # a preview. Asking about a version does not change that.
    assert keeping["previewFirst"] is True


def test_the_dialog_carries_the_technical_diff_and_the_promise(keeping):
    # Both are load-bearing and both were once lost. The diff is the
    # exact account and the rule says it is always there; the sentence
    # about the present state answers the question somebody had to read
    # the source for.
    assert keeping["diffShown"] is True
    assert keeping["keepsShown"] is True


def test_the_box_follows_the_mode(keeping):
    # Simple mode: an unmarked state is invisible, so it is ticked and fields shown.
    # Advanced mode: everything shows anyway, and a mark per experiment
    # would pile up, so fields start hidden.
    assert keeping["tickedInSimple"] is True
    assert keeping["fieldsHiddenInSimple"] is False
    assert keeping["clearInAdvanced"] is False
    assert keeping["fieldsHiddenInAdvanced"] is True


def test_a_name_is_offered_in_the_spelling_the_automatic_ones_use(keeping):
    # So that a list of versions reads as one list. Built by hand rather
    # than with toLocaleDateString, which follows the browser's language.
    assert re.fullmatch(r"\d{1,2} [A-Z][a-z]+ \d{4}", keeping["offeredTitle"])


def test_keeping_the_state_sends_a_version_with_the_restore(keeping):
    # One call, not two: the only moment the newest recorded state is
    # the one on the screen sits inside restore_state.
    assert keeping["withKeep"]["level"] == "patch"
    assert keeping["withKeep"]["title"] == keeping["offeredTitle"]


def test_discarding_sends_no_version_at_all(keeping):
    # "Discard" means "do not mark", never "delete". Sending nothing is
    # exactly that, and the state stays in the history either way.
    assert keeping["withoutKeep"] is None


def test_a_dialog_dismissed_without_a_button_writes_nothing(keeping):
    # Escape leaves the previous returnValue standing, so a dialog that
    # was confirmed once would confirm itself for ever after. Only the
    # preview may be fetched here - one call, and no second one.
    assert keeping["afterEscape"] == 1


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
const strip = dialog.querySelector("[data-footnote]");
const footnote = {
  hidden: strip.hidden,
  text: strip.querySelector("[data-footnote-text]").textContent,
};

const beforeOpen = { rawOpen: raw.open };
raw.open = true;
raw._on.toggle?.();
const afterOpen = { rawOpen: raw.open };

dialog.close("cancel");
await done;

console.log(JSON.stringify({ bodyHtml, footnote, beforeOpen, afterOpen }));
"""


@pytest.fixture(scope="session")
def confirm_pill(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "confirm_pill", _CONFIRM_PILL)


def test_the_confirm_dialog_uses_the_same_pill_as_the_card(confirm_pill):
    # One component everywhere, per the redesign - no second
    # disclosure pattern built just for this dialog.
    assert '<span class="glyph">&lt;/&gt;</span> Technical details' in confirm_pill["bodyHtml"]
    assert "confirm-seg-bar" not in confirm_pill["bodyHtml"]
    assert "confirm-info-panel" not in confirm_pill["bodyHtml"]


def test_the_confirm_dialogs_pill_starts_closed(confirm_pill):
    assert confirm_pill["beforeOpen"]["rawOpen"] is False


def test_the_footnote_is_visible_without_any_toggle(confirm_pill):
    # "Nothing is lost..." used to be behind a second, "Current state is
    # preserved" button. It is now always there whenever there is
    # anything to say - no click needed - and it sits in its own strip
    # between the body and the buttons rather than boxed inside the
    # body, because it reads identically in every dialog every time.
    assert confirm_pill["footnote"]["hidden"] is False
    assert confirm_pill["footnote"]["text"] == (
        "Nothing is lost — the state you leave stays in the history as its own entry."
    )
    assert "Nothing is lost" not in confirm_pill["bodyHtml"]


_KEEPBOX_CHANGE = """
const el = new Panel();
el.shadowRoot = node();
el._render();

// After _render(), the wiring code queries with "dialog .keepbox"
// but the test queries with "dialog.confirm .keepbox". In the mock,
// these are different selector keys, so they create different nodes.
// Set up aliases so both selectors resolve to the same nodes.
const realKeepbox = el.shadowRoot.querySelector("dialog .keepbox");
const realDataKeep = el.shadowRoot.querySelector("dialog [data-keep]");
const realFields = el.shadowRoot.querySelector("dialog .keepfields");

el.shadowRoot._seen["dialog.confirm .keepbox"] = realKeepbox;
el.shadowRoot._seen["dialog.confirm [data-keep]"] = realDataKeep;
el.shadowRoot._seen["dialog.confirm .keepfields"] = realFields;

// When the listener calls realDataKeep.querySelector(".keepfields"),
// it looks in realDataKeep._seen, which is the same as el.shadowRoot._seen
// (they share the _seen map). Alias the simple selector too.
el.shadowRoot._seen[".keepfields"] = realFields;
el.shadowRoot._seen[".keepbox"] = realKeepbox;

// The listener uses keepbox.closest("[data-keep]"), which in the mock
// requires _closest to be set up manually.
realKeepbox._closest["[data-keep]"] = realDataKeep;

const keepbox = el.shadowRoot.querySelector("dialog.confirm .keepbox");
const fields = el.shadowRoot.querySelector("dialog.confirm .keepfields");

keepbox._on.change({ target: { checked: true } });
const shownWhenChecked = fields.hidden;

keepbox._on.change({ target: { checked: false } });
const hiddenWhenUnchecked = fields.hidden;

console.log(JSON.stringify({
  shownWhenChecked,
  hiddenWhenUnchecked,
}));
"""


@pytest.fixture(scope="session")
def keepbox_change(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "keepbox_change", _KEEPBOX_CHANGE)


def test_keepbox_change_toggles_keepfields_visibility(keepbox_change):
    assert keepbox_change["shownWhenChecked"] is False
    assert keepbox_change["hiddenWhenUnchecked"] is True


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


_ADDRESSING = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
// The bottom row of a page: its predecessor is a revision the panel has
// never loaded, which is the ordinary case as soon as anybody pages.
el._changes = [
  { revision: "a", previous: "b", message: "" },
  { revision: "b", previous: "c", message: "" },
];

const asked = [];
el._call = (type, extra) => {
  asked.push({ type, extra });
  return Promise.resolve({ items: [], groups: [], available: false });
};

await el._expand("b");
const bottom = {
  types: asked.map((c) => c.type).sort(),
  open: el._open,
};

// And the very first recorded state, which has nothing before it.
asked.length = 0;
el._changes = [{ revision: "z", previous: null, message: "" }];
el._open = null;
await el._expand("z");
const first = { types: asked.map((c) => c.type).sort() };

console.log(JSON.stringify({ bottom, first }));
"""


@pytest.fixture(scope="session")
def addressing(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "addressing", _ADDRESSING)


def test_a_row_is_opened_by_its_revision_and_asks_against_its_own_predecessor(
    addressing,
):
    # Worked out from the row below, the bottom row of every page said
    # "there is nothing before this" and offered no undo. The
    # predecessor is in the row now, so undo is asked too.
    assert addressing["bottom"]["open"] == "b"
    assert addressing["bottom"]["types"] == ["explain", "undo_change"]


def test_the_first_recorded_state_asks_about_nothing_before_it(addressing):
    # There genuinely is nothing there, and asking would be asking about
    # a revision that does not exist. `undo_change` is left out for a
    # second reason: `_renderDetail` returns before the undo section for
    # a change with no predecessor, so the answer had nowhere to go -
    # and it is the expensive one, 1.2 to 1.5 s on a large dashboard.
    assert addressing["first"]["types"] == ["explain"]


_COMPARE_SELECT = """
const el = new Panel();
el._render = () => {};
el._mode = "advanced";
el._changes = [];
// Reaching two picks fires _openCompare() once task 3 lands - a
// never-settling call and stand-ins for shadowRoot/_changes keep that
// harmless here, since this scenario only inspects the synchronous
// selection state and never awaits anything.
el._call = () => new Promise(() => {});
el.shadowRoot = node();

el._toggleCompareMode();
const afterOn = el._compareMode;

el._toggleCompareRevision("a", "1 removed");
el._toggleCompareRevision("b", "2 moved");
const twoSelected = [...el._compareSelection];

// A third pick evicts the oldest, not the newest.
el._toggleCompareRevision("c", "1 added");
const afterThird = [...el._compareSelection];

// Picking an already-selected one again clears just that one.
el._toggleCompareRevision("c", "1 added");
const afterToggleOff = [...el._compareSelection];

el._toggleCompareMode();
const afterOff = { mode: el._compareMode, selection: [...el._compareSelection] };

console.log(JSON.stringify({ afterOn, twoSelected, afterThird, afterToggleOff, afterOff }));
"""


@pytest.fixture(scope="session")
def compare_select(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "compare_select", _COMPARE_SELECT)


def test_compare_mode_selection_keeps_at_most_two(compare_select):
    assert compare_select["afterOn"] is True
    assert [s["revision"] for s in compare_select["twoSelected"]] == ["a", "b"]
    # "a" was the oldest pick; the third eviction drops it, not "b".
    assert [s["revision"] for s in compare_select["afterThird"]] == ["b", "c"]
    assert [s["revision"] for s in compare_select["afterToggleOff"]] == ["b"]
    # Turning compare mode off clears the selection - reopening starts fresh.
    assert compare_select["afterOff"] == {"mode": False, "selection": []}


_COMPARE_CLEARED_ON_SWITCH = """
const el = new Panel();
el._render = () => {};
el._mode = "advanced";
el._changes = [];
el._call = () => Promise.resolve({ changes: [], next_cursor: null, versions: [] });
el.shadowRoot = node();

el._toggleCompareMode();
el._toggleCompareRevision("a", "1 removed");
// A standing pick that never reached two - one checkbox click on the
// next dashboard away from completing a compare against whatever it
// shows - plus leftover `_compareMissing` from an earlier dialog,
// which only `_openCompare` ever populates and only a switch should
// ever clear again.
el._compareMissing = [{ position: 0, kind: "card", label: "Gone card" }];

await el._select("other");

console.log(JSON.stringify({
  mode: el._compareMode,
  selection: el._compareSelection,
  missing: el._compareMissing,
}));
"""


@pytest.fixture(scope="session")
def compare_cleared_on_switch(tmp_path_factory):
    return _run_in_node(
        tmp_path_factory, "compare_cleared_on_switch", _COMPARE_CLEARED_ON_SWITCH
    )


def test_switching_dashboards_clears_a_standing_compare_pick(compare_cleared_on_switch):
    # Found by the final review: a pick made while viewing one dashboard
    # survived a switch to another untouched, so one checkbox click on
    # the new dashboard could complete a stale two-item selection and
    # compare its fresh pick against the old dashboard's leftover
    # commit - mislabelled with the old dashboard's message and date -
    # or, with "current state" already picked, pop the dialog open on
    # the very next click.
    assert compare_cleared_on_switch["mode"] is False
    assert compare_cleared_on_switch["selection"] == []
    assert compare_cleared_on_switch["missing"] == []


_COMPARE_OPEN = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._mode = "advanced";
el.shadowRoot = node();

const calls = [];
el._call = (type, extra) => new Promise((resolve) => {
  calls.push({ type, extra, resolve });
});

el._toggleCompareMode();
el._toggleCompareRevision("a", "1 removed");
el._toggleCompareRevision(null, "Current state");
await settle();

const compareCall = calls.find((c) => c.type === "compare");
// The backend decides order, not this scenario - "a" comes back as
// revision_a because it really is the older side. A non-empty diff:
// an empty one would mean the two states are byte-identical, and then
// deleted_since could not honestly report anything missing either.
compareCall.resolve({
  groups: [], note: "", diff: "-Gone card\\n",
  revision_a: "a", revision_b: null, time_a: 1731000000, time_b: null,
});
await settle();

const missingCall = calls.find((c) => c.type === "deleted_since");
missingCall.resolve({ items: [{ position: 0, kind: "card", label: "Gone card", view: "a" }] });
await settle();

const dialog = el.shadowRoot.querySelector("dialog.compare");
const body = dialog.querySelector("[data-compare-body]");

console.log(JSON.stringify({
  compareArgs: compareCall.extra,
  missingArgs: missingCall.extra,
  bodyHtml: body.innerHTML,
  dialogOpen: dialog.open,
}));
"""


@pytest.fixture(scope="session")
def compare_open(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "compare_open", _COMPARE_OPEN)


def test_compare_dialog_opens_on_two_picks_and_offers_put_back(compare_open):
    # "a" was picked first, "current" second - the backend's revision_a
    # says "a" is genuinely the older side, and the dialog trusts that
    # rather than re-deriving order from `_changes` itself.
    assert compare_open["compareArgs"] == {"dashboard": "dash", "revision_a": "a"}
    assert compare_open["missingArgs"] == {"dashboard": "dash", "revision": "a"}
    # Spec decision 19/9: each side names its own automatic message, not
    # a bare "between X and Y" that could be either of the two rows.
    # `renderPlain` escapes its whole heading, so the quotes `describe()`
    # wraps the label in come back as `&quot;` - correct once a browser
    # renders it, and the form this check has to look for in the raw
    # markup.
    assert "&quot;1 removed&quot;" in compare_open["bodyHtml"]
    assert "Current state" in compare_open["bodyHtml"]
    assert "Gone card" in compare_open["bodyHtml"]
    assert "Put back" in compare_open["bodyHtml"]
    assert compare_open["dialogOpen"] is True


_COMPARE_KNOWN_CURRENT_ROW = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._mode = "advanced";
el.shadowRoot = node();

const calls = [];
el._call = (type, extra) => new Promise((resolve) => {
  calls.push({ type, extra, resolve });
});

el._toggleCompareMode();
// "b" is picked the way a row or version already marked same_as_now
// picks itself - `now: true`, not the pinned "Current state" pick's
// `revision: null`. A dashboard whose newest change already carries a
// version (the case a real installation showed: v1.0.1 sitting on the
// current state) has no pinned pick ticked at all here, and still
// ought to offer Put-back once the backend confirms "b" is the newer
// side.
el._toggleCompareRevision("a", "1 removed");
el._toggleCompareRevision("b", "v1.0.1", true);
await settle();

calls.find((c) => c.type === "compare").resolve({
  groups: [], note: "", diff: "-Gone card\\n",
  revision_a: "a", revision_b: "b", time_a: 1731000000, time_b: 1731100000,
});
await settle();

const missingCall = calls.find((c) => c.type === "deleted_since");
if (missingCall) {
  missingCall.resolve({ items: [{ position: 0, kind: "card", label: "Gone card", view: "a" }] });
  await settle();
}

const dialog = el.shadowRoot.querySelector("dialog.compare");
console.log(JSON.stringify({
  missingCalled: !!missingCall,
  missingArgs: missingCall ? missingCall.extra : null,
  bodyHtml: dialog.querySelector("[data-compare-body]").innerHTML,
}));
"""


@pytest.fixture(scope="session")
def compare_known_current_row(tmp_path_factory):
    return _run_in_node(
        tmp_path_factory, "compare_known_current_row", _COMPARE_KNOWN_CURRENT_ROW
    )


def test_put_back_is_offered_against_a_row_already_known_to_be_current(
    compare_known_current_row,
):
    # Found from a real installation: a row or version can already be
    # marked "current state" (same_as_now, or a version sitting on the
    # newest change) without being the pinned "Current state" pick -
    # and Put-back used to stay hidden for it regardless, because the
    # only check was "is the newer side literally revision === null".
    result = compare_known_current_row
    assert result["missingCalled"] is True
    assert result["missingArgs"] == {"dashboard": "dash", "revision": "a"}
    assert "Put back" in result["bodyHtml"]


_COMPARE_TWO_HISTORICAL_REVISIONS = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._mode = "advanced";
el.shadowRoot = node();

const calls = [];
el._call = (type, extra) => new Promise((resolve) => {
  calls.push({ type, extra, resolve });
});

el._toggleCompareMode();
// Neither side is "now": two ordinary past revisions, neither of them
// known to hold today's content. Put-back has nothing to put back
// *into* here - `deleted_since`/`restore_deleted` always write into
// the live dashboard, and nothing here says the live dashboard is
// either of these two states.
el._toggleCompareRevision("a", "1 removed");
el._toggleCompareRevision("b", "v1.0.0");
await settle();

calls.find((c) => c.type === "compare").resolve({
  groups: [], note: "", diff: "-Gone card\\n",
  revision_a: "a", revision_b: "b", time_a: 1731000000, time_b: 1731100000,
});
await settle();

const dialog = el.shadowRoot.querySelector("dialog.compare");
console.log(JSON.stringify({
  missingCalled: calls.some((c) => c.type === "deleted_since"),
  bodyHtml: dialog.querySelector("[data-compare-body]").innerHTML,
}));
"""


@pytest.fixture(scope="session")
def compare_two_historical_revisions(tmp_path_factory):
    return _run_in_node(
        tmp_path_factory,
        "compare_two_historical_revisions",
        _COMPARE_TWO_HISTORICAL_REVISIONS,
    )


def test_put_back_stays_hidden_between_two_past_revisions(
    compare_two_historical_revisions,
):
    result = compare_two_historical_revisions
    assert result["missingCalled"] is False
    assert "Put back" not in result["bodyHtml"]


_COMPARE_BAR_PINNED_PICK = """
const el = new Panel();
el._selected = "dash";
el._mode = "advanced";
el._dashboards = [{ key: "dash", title: "Dash", exists: true }];
el._versions = [];
el.shadowRoot = node();

// The newest change already stands for the current state - the same
// fact a crowned row or a version head would show on screen. A second,
// separate checkbox saying the same thing is what confused a real user
// (2026-09-13): "the current state is already known, why isn't that
// checkbox the same as this one?" It should be - there is only one.
el._changes = [
  { revision: "a", message: "1 removed", timestamp: 1731000000,
    same_as_now: true, versions: [] },
];
// Not "current-pick" alone: that class name also sits in the
// stylesheet's own CSS rule, right at the top of every render
// (`<style>${STYLE}</style>`), so it is never actually absent from
// `innerHTML` - only the pinned row's own markup is.
const PINNED_PICK = 'data-compare-label="Current state"';
el._toggleCompareMode();
await settle();
const withCrownedRow = el.shadowRoot.innerHTML.includes(PINNED_PICK);

// Decision 9's own edge case: the dashboard changed at Home Assistant's
// back, so nothing recorded matches it any more. Nothing on screen can
// stand in for "Current state" here, so the pinned pick stays - it is
// the one thing decision 9 keeps it for.
el._changes = [
  { revision: "a", message: "1 removed", timestamp: 1731000000,
    same_as_now: false, versions: [] },
];
el._render();
const withNothingCrowned = el.shadowRoot.innerHTML.includes(PINNED_PICK);

console.log(JSON.stringify({ withCrownedRow, withNothingCrowned }));
"""


@pytest.fixture(scope="session")
def compare_bar_pinned_pick(tmp_path_factory):
    return _run_in_node(
        tmp_path_factory, "compare_bar_pinned_pick", _COMPARE_BAR_PINNED_PICK
    )


def test_the_pinned_current_state_pick_hides_once_a_row_already_stands_for_it(
    compare_bar_pinned_pick,
):
    result = compare_bar_pinned_pick
    assert result["withCrownedRow"] is False
    assert result["withNothingCrowned"] is True


_COMPARE_MISSING_GROUPED_BY_VIEW = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._mode = "advanced";
el.shadowRoot = node();

const calls = [];
el._call = (type, extra) => new Promise((resolve) => {
  calls.push({ type, extra, resolve });
});

el._toggleCompareMode();
el._toggleCompareRevision("a", "1 removed");
el._toggleCompareRevision(null, "Current state");
await settle();

calls.find((c) => c.type === "compare").resolve({
  groups: [], note: "", diff: "-3 removed\\n",
  revision_a: "a", revision_b: null, time_a: 1731000000, time_b: null,
});
await settle();

// Two cards from the same view, one from another - arriving in view
// order the way `find_removed` itself walks the views, not sorted or
// shuffled by this scenario. Labels distinct from the diff text above,
// so `indexOf` below cannot accidentally match the raw diff instead of
// the grouped list this test is actually about.
calls.find((c) => c.type === "deleted_since").resolve({
  items: [
    { position: 0, kind: "card", label: "Card A", view: "erste", view_title: "Erste Ansicht" },
    { position: 1, kind: "card", label: "Card B", view: "erste", view_title: "Erste Ansicht" },
    { position: 2, kind: "card", label: "Card C", view: "zweite", view_title: "Zweite Ansicht" },
  ],
});
await settle();

const dialog = el.shadowRoot.querySelector("dialog.compare");
const bodyHtml = dialog.querySelector("[data-compare-body]").innerHTML;

console.log(JSON.stringify({
  bodyHtml,
  firstHeadingCount: bodyHtml.split("In the view Erste Ansicht").length - 1,
  secondHeadingCount: bodyHtml.split("In the view Zweite Ansicht").length - 1,
  order: [
    bodyHtml.indexOf("In the view Erste Ansicht"),
    bodyHtml.indexOf("Card A"),
    bodyHtml.indexOf("Card B"),
    bodyHtml.indexOf("In the view Zweite Ansicht"),
    bodyHtml.indexOf("Card C"),
  ],
}));
"""


@pytest.fixture(scope="session")
def compare_missing_grouped_by_view(tmp_path_factory):
    return _run_in_node(
        tmp_path_factory,
        "compare_missing_grouped_by_view",
        _COMPARE_MISSING_GROUPED_BY_VIEW,
    )


def test_the_missing_list_is_grouped_by_view(compare_missing_grouped_by_view):
    # Found: the flat "Missing since then" list repeated its view as a
    # small badge on every single row instead of grouping like the diff
    # right above it already does - on a dashboard with a dozen views,
    # scanning for "everything from the Kitchen view" meant reading every
    # row's badge instead of looking at one heading.
    result = compare_missing_grouped_by_view
    # One heading per view, not one per item - two cards from "Erste
    # Ansicht" must not print its heading twice.
    assert result["firstHeadingCount"] == 1
    assert result["secondHeadingCount"] == 1
    (
        first_heading,
        card_a,
        card_b,
        second_heading,
        card_c,
    ) = result["order"]
    assert -1 not in result["order"]
    # Both of "Erste Ansicht"'s cards sit under its own heading, before
    # the next view's heading opens - not scattered across two groups.
    assert first_heading < card_a < card_b < second_heading < card_c


_COMPARE_RESTORE_CLICK = """
const el = new Panel();
el._selected = "dash";
el._mode = "advanced";
el._changes = [];
el._dashboards = [{ key: "dash", title: "Dash", exists: true }];
el._versions = [];
el.shadowRoot = node();

const calls = [];
el._call = (type, extra) => new Promise((resolve) => {
  calls.push({ type, extra, resolve });
});

// `_render` runs for real in this scenario, unlike most others in this
// file: the delegated `[data-compare-body]` listener is wired inside
// it, and a stubbed no-op would leave nothing to click.
el._toggleCompareMode();
el._toggleCompareRevision("a", "1 removed");
el._toggleCompareRevision(null, "Current state");
await settle();

calls.find((c) => c.type === "compare").resolve({
  groups: [], note: "", diff: "-Gone card\\n",
  revision_a: "a", revision_b: null, time_a: 1731000000, time_b: null,
});
await settle();

// A label the old row-level handler never had to deal with: rendered,
// `.label` nests a `.where` badge inside it, so reading the item back
// out of `.textContent` would run the two together.
calls.find((c) => c.type === "deleted_since").resolve({
  items: [{ position: 0, kind: "card", label: "Gone card", view: "a" }],
});
await settle();

const dialog = el.shadowRoot.querySelector("dialog.compare");

// The button itself is never real here - this stand-in does not parse
// the markup `_openCompare` writes into `[data-compare-body]`, so a
// button built by `querySelector` alone would prove nothing either
// way. Built by hand instead, the way a real one would be found by
// `event.target.closest(...)` once a click on it bubbles up.
const button = node();
button.dataset.compareRestore = "0";
button._closest["[data-compare-restore]"] = button;

// Found from the shadow root - exactly what the delegated wiring
// itself queries (`onClick("[data-compare-body]", ...)` in `_render`).
// Before the 2026-09-12 fix, this container and the one
// `_openCompare` writes its content into (reached via
// `dialog.querySelector(...)`) were two disconnected phantom nodes,
// and a test that grabbed a node for `[data-compare-restore]` straight
// from the root - as this one used to - found *a* node with a
// listener on it regardless, without ever proving the listener sat on
// the element a real click could actually reach. Querying the
// container here is what closes that gap: if the click listener were
// still bound to the wrong selector, `container._on.click` would not
// exist and this scenario would throw before it could log anything.
const container = el.shadowRoot.querySelector("[data-compare-body]");
// No real tree here to walk upward through, so the one ancestor the
// handler asks `.closest` for is handed to it directly - see `closest`
// on the stand-in node.
container._closest["dialog.compare"] = dialog;

let restoreArgs = null;
el._restoreItem = (revision, item) => { restoreArgs = { revision, item }; };

// A real click on the button bubbles up to the container the
// delegated listener is bound to; nothing here has a real tree to
// bubble through, so the event is fired on the container directly,
// carrying the button as `event.target` the way the browser would
// deliver it.
container._on.click({ target: button });

console.log(JSON.stringify({
  restoreArgs,
  dialogOpen: dialog.open,
  compareMode: el._compareMode,
  selection: el._compareSelection,
  missing: el._compareMissing,
}));
"""


@pytest.fixture(scope="session")
def compare_restore_click(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "compare_restore_click", _COMPARE_RESTORE_CLICK)


def test_put_back_from_the_compare_dialog_names_the_clean_label(compare_restore_click):
    # Found by review: the button's item was read back out of the
    # dialog's own rendered `.label` text, which nests a `.where` badge
    # inside it - so `.textContent` ran the two together into "Gone
    # card card - view a" instead of "Gone card". The handler looks the
    # item up by position in the retained `_compareMissing` array
    # instead, the same way the old row-level handler looks its item up
    # in `_items` rather than in what was drawn.
    assert compare_restore_click["restoreArgs"] == {
        "revision": "a",
        "item": {"position": 0, "kind": "card", "label": "Gone card", "view": "a"},
    }


def test_put_back_from_the_compare_dialog_closes_it(compare_restore_click):
    # Found by an outside review: putting one item back can shift the
    # positions of whatever else the dialog still lists, and it never
    # refreshes on its own - a second click on a button drawn before
    # this one would then act on a position that no longer means what
    # it did when the dialog opened. Closing it here, rather than
    # trying to keep it in step, is what rules that out - the compare
    # mode's own state goes back to empty too, the same shape a fresh
    # pick starts from.
    assert compare_restore_click["dialogOpen"] is False
    assert compare_restore_click["compareMode"] is False
    assert compare_restore_click["selection"] == []
    assert compare_restore_click["missing"] == []


_COMPARE_ABANDONED_ON_SWITCH = """
const el = new Panel();
el._render = () => {};
el._mode = "advanced";
el._selected = "dash";
el._changes = [];
el.shadowRoot = node();

const calls = [];
el._call = (type, extra) => {
  if (type === "compare" || type === "deleted_since") {
    return new Promise((resolve) => { calls.push({ type, extra, resolve }); });
  }
  // Whatever `_select`'s own refresh needs, answered at once - none of
  // it is what this scenario is testing.
  return Promise.resolve({ changes: [], next_cursor: null, versions: [] });
};

el._toggleCompareMode();
el._toggleCompareRevision("a", "1 removed");
el._toggleCompareRevision(null, "Current state");
await settle();

// The dashboard changes while `compare` is still in flight - `_select`
// claims "write" as one of its first lines, before it awaits anything.
await el._select("other");

const compareCall = calls.find((c) => c.type === "compare");
compareCall.resolve({
  groups: [], note: "", diff: "-Gone card\\n",
  revision_a: "a", revision_b: null, time_a: 1731000000, time_b: null,
});
await settle();

console.log(JSON.stringify({
  deletedSinceCalled: calls.some((c) => c.type === "deleted_since"),
  compareReference: el.shadowRoot.querySelector("dialog.compare").dataset.compareReference ?? null,
}));
"""


@pytest.fixture(scope="session")
def compare_abandoned_on_switch(tmp_path_factory):
    return _run_in_node(
        tmp_path_factory, "compare_abandoned_on_switch", _COMPARE_ABANDONED_ON_SWITCH
    )


def test_a_compare_in_flight_is_abandoned_on_a_dashboard_switch(compare_abandoned_on_switch):
    # Found by an outside review: `_openCompare` used to re-read
    # `this._selected` after its first await, so a dashboard switch
    # while "Comparing..." was still up would ask `deleted_since` about
    # the picked revision against whatever dashboard somebody has since
    # switched to. Claiming "write" up front and checking it back after
    # each await is what `_select` claiming "write" on its own already
    # invalidates.
    assert compare_abandoned_on_switch["deletedSinceCalled"] is False
    assert compare_abandoned_on_switch["compareReference"] is None


_COMPARE_ABANDONED_ON_CLOSE = """
const el = new Panel();
el._render = () => {};
el._mode = "advanced";
el._selected = "dash";
el._changes = [];
el.shadowRoot = node();

const calls = [];
el._call = (type, extra) => new Promise((resolve) => {
  calls.push({ type, extra, resolve });
});

el._toggleCompareMode();
el._toggleCompareRevision("a", "1 removed");
el._toggleCompareRevision(null, "Current state");
await settle();

// Closed here, before `compare` has answered at all - no `close`
// listener is registered yet at this point (`_answerFrom` is only
// reached at the very end of `_openCompare`), so this is exactly what
// a user closing the dialog mid-fetch looks like from the inside.
el.shadowRoot.querySelector("dialog.compare").close();

calls.find((c) => c.type === "compare").resolve({
  groups: [], note: "", diff: "-Gone card\\n",
  revision_a: "a", revision_b: null, time_a: 1731000000, time_b: null,
});
await settle();

console.log(JSON.stringify({
  deletedSinceCalled: calls.some((c) => c.type === "deleted_since"),
}));
"""


@pytest.fixture(scope="session")
def compare_abandoned_on_close(tmp_path_factory):
    return _run_in_node(
        tmp_path_factory, "compare_abandoned_on_close", _COMPARE_ABANDONED_ON_CLOSE
    )


def test_a_compare_closed_mid_fetch_does_not_finish_its_work(compare_abandoned_on_close):
    # Found by an outside review: `_answerFrom` only ever waits for a
    # *future* close event, so a dialog already closed before
    # `_openCompare` reached that line left the wait hanging forever -
    # and along the way, it would still have gone on to fetch
    # `deleted_since` for a dialog nobody was looking at. The `!dialog.open`
    # check added alongside the write-claim check rules out both: this
    # scenario completes (a hang would time this test out) and never
    # asks for the missing-items list.
    assert compare_abandoned_on_close["deletedSinceCalled"] is False


_UNDO_REFUSED_LINKS_TO_COMPARE = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._changes = [{ revision: "b", previous: "a", message: "1 removed" }];
el._open = "b";
el._explanation = { groups: [], note: "" };
el._undo = { available: false, reason: "a section has no path to recognise it by" };
el._loadingDetail = null;
el._loadingUndo = null;

const html = el._renderDetail(el._changes[0]);
console.log(JSON.stringify({ html }));
"""


@pytest.fixture(scope="session")
def undo_refused_links_to_compare(tmp_path_factory):
    return _run_in_node(
        tmp_path_factory, "undo_refused_links_to_compare", _UNDO_REFUSED_LINKS_TO_COMPARE
    )


def test_undo_refusal_offers_a_way_into_compare_mode(undo_refused_links_to_compare):
    html = undo_refused_links_to_compare["html"]
    assert "cannot be taken back exactly" in html
    assert 'data-compare-from="a"' in html


_UNDO_REFUSED_ON_A_DELETED_DASHBOARD = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
// The compare bar itself already hides "current state" for a dashboard
// Home Assistant does not currently have (`_renderMain`) - the jump a
// refused undo offers ends up picking exactly that "current state",
// so it must not be offered here either.
el._dashboards = [{ key: "dash", title: "Dash", exists: false }];
el._changes = [{ revision: "b", previous: "a", message: "1 removed" }];
el._open = "b";
el._explanation = { groups: [], note: "" };
el._undo = { available: false, reason: "a section has no path to recognise it by" };
el._loadingDetail = null;
el._loadingUndo = null;

const html = el._renderDetail(el._changes[0]);
console.log(JSON.stringify({ html }));
"""


@pytest.fixture(scope="session")
def undo_refused_on_a_deleted_dashboard(tmp_path_factory):
    return _run_in_node(
        tmp_path_factory,
        "undo_refused_on_a_deleted_dashboard",
        _UNDO_REFUSED_ON_A_DELETED_DASHBOARD,
    )


def test_the_compare_jump_is_not_offered_for_a_deleted_dashboard(
    undo_refused_on_a_deleted_dashboard,
):
    html = undo_refused_on_a_deleted_dashboard["html"]
    # The refusal itself is still said - only the door into a "current
    # state" that does not exist is closed.
    assert "cannot be taken back exactly" in html
    assert "data-compare-from" not in html


_COMPARE_FROM_CLICK = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._changes = [
  { revision: "z", previous: "y", message: "unrelated" },
  { revision: "b", previous: "a", message: "1 removed" },
];
let openCount = 0;
el._openCompare = () => { openCount += 1; return Promise.resolve(); };

// Compare mode is already on, with an unrelated row already picked -
// exactly the state a naive toggle-based jump would mishandle: one
// _toggleCompareRevision call away from firing _openCompare with the
// wrong pair already.
el._toggleCompareMode();
el._toggleCompareRevision("z", "unrelated");

el._jumpToCompareFrom("a");

console.log(JSON.stringify({
  openCount,
  mode: el._compareMode,
  selection: el._compareSelection.map((s) => s.revision),
}));
"""


@pytest.fixture(scope="session")
def compare_from_click(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "compare_from_click", _COMPARE_FROM_CLICK)


def test_jump_to_compare_from_replaces_any_standing_selection(compare_from_click):
    # Exactly the predecessor and "current state" - the unrelated "z"
    # pick from before the call is gone, not merged into a triple, and
    # _openCompare fires exactly once rather than once with the wrong
    # pair and once more on top of the dialog that first call opened.
    assert compare_from_click["mode"] is True
    assert compare_from_click["selection"] == ["a", None]
    assert compare_from_click["openCount"] == 1


_SEARCH = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._mode = "advanced";
el._changes = [
  { revision: "a", message: "1 card added", description: "", versions: [] },
  { revision: "b", message: "2 views removed", description: "the rework",
    versions: [{ name: "dash/v1.0.0", title: "Winter rebuild" }] },
];
el._versions = [
  { name: "dash/v1.0.0", title: "Winter rebuild", description: "notes" },
  { name: "dash/v0.9.0", title: "Autumn", description: "" },
];

const asked = [];
el._call = (type, extra) => {
  asked.push(type);
  return Promise.resolve({ changes: [{ revision: "z", message: "old rework" }] });
};

await el._search("views");
const local = { shown: el._shown().map((c) => c.revision), asked: [...asked] };

await el._search("rework");
const own = el._shown().map((c) => c.revision);

await el._search("winter");
const byVersion = el._shown().map((c) => c.revision);

await el._search("needle");
const remote = { shown: el._shown().map((c) => c.revision), asked: [...asked] };

await el._search("");
const cleared = { shown: el._shown().map((c) => c.revision), found: el._found };

// The simple mode filters the complete version list, without a server.
el._mode = "simple";
asked.length = 0;
await el._search("autumn");
const simple = {
  names: el._matchingVersions().map((v) => v.name),
  asked: [...asked],
};

// Picking another dashboard drops the search with everything else.
el._call = () => Promise.resolve({ changes: [], next_cursor: null, versions: [] });
await el._select("other");
const afterSwitch = { query: el._query, found: el._found };

console.log(JSON.stringify({
  local, own, byVersion, remote, cleared, simple, afterSwitch,
}));
"""


@pytest.fixture(scope="session")
def searching(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "search", _SEARCH)


def test_a_hit_in_what_is_loaded_never_reaches_the_server(searching):
    # The common case, and it must cost nothing: what somebody searches
    # for is usually what they have just read.
    assert searching["local"]["shown"] == ["b"]
    assert searching["local"]["asked"] == []


def test_a_persons_own_description_is_searched_too(searching):
    # Both are what a row shows, and nobody remembers which of the two
    # they read.
    assert searching["own"] == ["b"]


def test_a_version_sitting_on_a_row_is_searched_too(searching):
    # The same four things the server looks at. A first step that found
    # less than the second would escalate for a hit it already had.
    assert searching["byVersion"] == ["b"]


def test_nothing_loaded_matching_asks_the_whole_history(searching):
    # "Nothing found" has to mean nothing found, not "nothing among the
    # twenty-five that happen to be loaded".
    assert searching["remote"]["asked"] == ["search"]
    assert searching["remote"]["shown"] == ["z"]


def test_clearing_the_box_goes_back_to_the_plain_list(searching):
    # An empty box is not a search for everything; it is no search.
    assert searching["cleared"]["shown"] == ["a", "b"]
    assert searching["cleared"]["found"] is None


def test_the_simple_mode_filters_versions_without_asking_anybody(searching):
    # `_versions` is the complete list, so a filter over it is complete
    # too - which is exactly what project G was for.
    assert searching["simple"]["names"] == ["dash/v0.9.0"]
    assert searching["simple"]["asked"] == []


def test_picking_another_dashboard_drops_the_search(searching):
    # A cursor from one dashboard handed to another was already refused;
    # a query is the same mistake with a different name.
    assert searching["afterSwitch"]["query"] == ""
    assert searching["afterSwitch"]["found"] is None


_FOUND_ROW = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
// A hit the server found, four hundred entries below the loaded window.
// That is the ordinary case for a search: if it were in `_changes` the
// local pass would have caught it and no request would have gone out.
el._changes = [{ revision: "a", previous: "b", message: "" }];
el._query = "winter";
el._found = [{ revision: "deep", previous: "deeper", message: "" }];

const asked = [];
el._call = (type, extra) => {
  asked.push({ type, extra });
  return Promise.resolve({ items: [], groups: [], available: false });
};

await el._expand("deep");
const opened = { open: el._open, shown: el._shown().map((c) => c.revision) };

// The same row, described. `_describe` reads the row through the same
// lookup, so a hit nobody can open is also a hit nobody can annotate.
// The dialog opening is the tell: on a lookup miss `_describe` returns
// before it ever gets there.
el.shadowRoot = node();
const box = el.shadowRoot.querySelector("dialog.describe");
const field = box.querySelector("input.text");
field.focus = () => {};
field.select = () => {};
const asking = el._describe("deep");
await settle();
const describing = box.open;
box.close("");
await asking;

console.log(JSON.stringify({ opened, describing }));
"""


@pytest.fixture(scope="session")
def found_row(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "found_row", _FOUND_ROW)


def test_a_row_the_server_found_can_be_opened(found_row):
    # The whole second stage of the search rests on this. A hit is drawn
    # from `_found`, never from `_changes` - so a lookup that reads only
    # the loaded list makes every remote hit inert, and inert without a
    # word: the row is there, the click does nothing, nothing says why.
    assert found_row["opened"]["shown"] == ["deep"]
    assert found_row["opened"]["open"] == "deep"


def test_a_row_the_server_found_can_be_described(found_row):
    # Same lookup, second caller. Named separately because a fix that
    # only reached `_expand` would leave this one silently broken.
    assert found_row["describing"] is True


_TWO_SEARCHES = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._mode = "advanced";
el._changes = [];
""" + _HELD + """
// Type, wait, type again: the first answer lands while the second
// search is still out.
const first = el._search("winter");
await settle();
const second = el._search("summer");
await settle();

reply("search", { changes: [{ revision: "old" }], more: false });
await first;
const whileSecondRuns = el._searching;

reply("search", { changes: [{ revision: "new" }], more: false });
await second;

console.log(JSON.stringify({
  whileSecondRuns,
  after: el._searching,
  found: (el._found || []).map((c) => c.revision),
}));
"""


@pytest.fixture(scope="session")
def two_searches(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "two_searches", _TWO_SEARCHES)


def test_an_older_answer_does_not_blank_the_note(two_searches):
    # The indicator belongs to the newest run. Cleared by an older one,
    # the screen says nothing is happening while a search really is.
    assert two_searches["whileSecondRuns"] is True
    assert two_searches["after"] is False
    # And the older answer is dropped rather than drawn, which is the
    # claim ticket doing its own job.
    assert two_searches["found"] == ["new"]


# -- a preview belongs to the dashboard it was fetched for -----------------
#
# Found by the final review on 2026-09-05, and verified by running it:
# the request closures read `this._selected` when they were *called*, and
# they are called twice - once for the preview, once for the write. The
# dialog appears only after the preview is back, so the sidebar is live
# in between.

_WRONG_DASHBOARD = """
const el = new Panel();
el._render = () => {};
el._recorded = () => Promise.resolve();
el._loadDashboardsQuietly = async () => {};
el._loadDashboards = async () => {};
el._dashboards = [
  { key: "kitchen", title: "Kitchen", exists: false },
  { key: "garden", title: "Garden", exists: false },
];
el._changes = [{ revision: "b" }];

const sent = [];
const held = [];
el._call = (type, extra) => {
  sent.push({ type, extra });
  return new Promise((resolve) => held.push({ type, extra, resolve }));
};
const reply = (type, value) => {
  const at = held.findIndex((c) => c.type === type);
  if (at >= 0) held.splice(at, 1)[0].resolve(value);
};
const PREVIEW = {
  applied: false,
  preview: "-a\\n+b",
  explanation: { groups: [], note: "one card removed" },
};
const confirming = (type) =>
  sent.filter((c) => c.type === type && c.extra.confirm);
// `create_version` carries no `confirm` flag - it writes a tag, not a
// dashboard state, and decision 7 exempts it from the preview - so the
// writing call is simply the one that goes out.
const made = () => sent.filter((c) => c.type === "create_version");
const CANDIDATES = {
  candidates: {
    current: "kitchen/v1.0.0",
    patch: "kitchen/v1.0.1",
    minor: "kitchen/v1.1.0",
    major: "kitchen/v2.0.0",
  },
};
// Whether a flow has come to an end - without hanging the run when it
// has not. A refused dialog has to let its caller go, and a caller left
// waiting for a `close` that can never come is exactly the shape of
// failure this file exists to catch, so it is measured rather than
// waited for.
const finished = async (promise) => {
  let done = false;
  promise.then(() => { done = true; });
  await settle();
  return done;
};

// 1. Another dashboard is picked while the restore's preview is out.
el._selected = "kitchen";
el.shadowRoot = node();
let restoring = el._restoreState("b", "Back to the state after this change");
await settle();
const previewFor = sent[0].extra.dashboard;
let switching = el._select("garden");
await settle();
reply("restore_state", PREVIEW);
const restoreAfterSwitch = {
  settled: await finished(restoring),
  opened: el.shadowRoot.querySelector("dialog.confirm").open,
  wrote: confirming("restore_state").length,
};
reply("history", { changes: [], next_cursor: null });
reply("versions", { versions: [] });
await switching;

// 2. The same click while `forget` is counting what it would destroy.
el._selected = "kitchen";
el.shadowRoot = node();
sent.length = 0;
const forgetting = el._forget();
await settle();
switching = el._select("garden");
await settle();
reply("forget", { states: 3, described: 0, first: 1000, last: 2000 });
const forgetAfterSwitch = {
  settled: await finished(forgetting),
  opened: el.shadowRoot.querySelector("dialog.forget").open,
  deleted: confirming("forget").length,
};
reply("history", { changes: [], next_cursor: null });
reply("versions", { versions: [] });
await switching;

// 3. And the same click while the version dialog is fetching the three
// numbers it offers. `create_version` writes no dashboard state, so it
// never passes through `_confirm` and needs its own guard.
el._selected = "kitchen";
el.shadowRoot = node();
sent.length = 0;
// Put back by hand: the two runs above each went through the real
// `_select`, and that replaces the list with what the reply carried.
el._changes = [{ revision: "b" }];
const versioning = el._createVersion("b");
await settle();
switching = el._select("garden");
await settle();
reply("next_versions", CANDIDATES);
const versionAfterSwitch = {
  // Named, because "no dialog" and "nothing written" is also what a
  // flow that stopped at its first line would report.
  asked: sent[0].type,
  settled: await finished(versioning),
  opened: el.shadowRoot.querySelector("dialog.version").open,
  created: made().length,
};
reply("history", { changes: [], next_cursor: null });
reply("versions", { versions: [] });
await switching;

// From here the reload at the end of each flow is out of the way; what
// is measured is which dashboard the writing call names.
el._select = async () => {};
el._refreshQuietly = async () => {};
el._reloadAfterWrite = async () => null;

// 4. The control: nothing moves, the dialog opens, the write goes out.
el._selected = "kitchen";
el.shadowRoot = node();
sent.length = 0;
restoring = el._restoreState("b", "Back to the state after this change");
await settle();
reply("restore_state", PREVIEW);
await settle();
const openedNormally = el.shadowRoot.querySelector("dialog.confirm").open;
el.shadowRoot.querySelector("dialog.confirm").close("apply");
await settle();
const restoredTo = confirming("restore_state")[0].extra.dashboard;
reply("restore_state", { applied: true });
await restoring;

// 5. The selection moves without going through `_select`, so the claim
// ticket still holds: only the captured key can keep this write on the
// dashboard whose diff was on the screen.
el._selected = "kitchen";
el.shadowRoot = node();
sent.length = 0;
restoring = el._restoreState("b", "Back to the state after this change");
await settle();
el._selected = "garden";
reply("restore_state", PREVIEW);
await settle();
el.shadowRoot.querySelector("dialog.confirm").close("apply");
await settle();
const carriedTo = confirming("restore_state")[0].extra.dashboard;
reply("restore_state", { applied: true });
await restoring;

// 6. And the irreversible one, the same way round.
el._selected = "kitchen";
el.shadowRoot = node();
sent.length = 0;
const forgetAgain = el._forget();
await settle();
el._selected = "garden";
reply("forget", { states: 3, described: 0, first: 1000, last: 2000 });
await settle();
const dialogSaid = el.shadowRoot
  .querySelector("dialog.forget").querySelector(".body").innerHTML;
el.shadowRoot.querySelector("dialog.forget").close("forget");
await settle();
const forgotten = confirming("forget")[0].extra.dashboard;
reply("forget", { forgotten: true });
await forgetAgain;

// 7. The version, the same way round: the numbers on the three buttons
// were worked out for one dashboard, and only the captured key can keep
// the tag on it.
el._selected = "kitchen";
el.shadowRoot = node();
sent.length = 0;
// Put back by hand: the run above ended in `_forget`, which empties the
// list along with the dashboard it threw away.
el._changes = [{ revision: "b" }];
const versionAgain = el._createVersion("b");
await settle();
el._selected = "garden";
reply("next_versions", CANDIDATES);
await settle();
const versionOpened = el.shadowRoot.querySelector("dialog.version").open;
el.shadowRoot.querySelector("dialog.version").close("create");
await settle();
const versionedOn = made()[0].extra.dashboard;
reply("create_version", { created: "kitchen/v1.0.1" });
await versionAgain;

// 8. Putting one deleted card back. Its own closure, and it was
// repaired separately from `restore_state` - so it is measured
// separately too.
el._selected = "kitchen";
el.shadowRoot = node();
sent.length = 0;
el._restoreItem(
  { revision: "b", previous: "c" },
  { label: "Weather", position: 2 },
);
await settle();
el._selected = "garden";
reply("restore_deleted", PREVIEW);
await settle();
el.shadowRoot.querySelector("dialog.confirm").close("apply");
await settle();
const itemWentTo = confirming("restore_deleted")[0].extra.dashboard;
reply("restore_deleted", { applied: true });
await settle();

// 9. And taking a change back, the third closure of the same shape.
el._selected = "kitchen";
el.shadowRoot = node();
sent.length = 0;
el._undoChange("b");
await settle();
el._selected = "garden";
// The two `undo_change` calls this one flow sends: the preview before
// the write, the write itself. `preview` belongs on the first alone -
// the dialog it fills in has just been read off `reply` above; asking
// again on the write would pay for the same two dumps a second time
// for a screen already drawn. See operations.py on `async_undo_change`.
const undoPreviewFlag = sent.find(
  (c) => c.type === "undo_change" && !c.extra.confirm,
)?.extra?.preview;
reply("undo_change", PREVIEW);
await settle();
el.shadowRoot.querySelector("dialog.confirm").close("apply");
await settle();
const undoneOn = confirming("undo_change")[0].extra.dashboard;
const undoWriteFlag = confirming("undo_change")[0].extra.preview;
reply("undo_change", { applied: true });
await settle();

// 10. And the sentence that reports a write, which is not itself a
// write. Apply is pressed on Kitchen; the write runs, the recorder is
// waited for and the page is reloaded, and the sidebar is live for all
// of it. The note about Kitchen used to land over Garden's history.
el._selected = "kitchen";
el.shadowRoot = node();
sent.length = 0;
const noting = el._restoreState("b", "Back to the state after this change");
await settle();
reply("restore_state", PREVIEW);
await settle();
el.shadowRoot.querySelector("dialog.confirm").close("apply");
await settle();
el._selected = "garden";
reply("restore_state", {
  applied: true,
  note: "the live state could not be recorded",
});
await noting;
const bannerElsewhere = el._error;

// The control: nobody moves, and the same sentence is said.
el._selected = "kitchen";
el.shadowRoot = node();
sent.length = 0;
const staying = el._restoreState("b", "Back to the state after this change");
await settle();
reply("restore_state", PREVIEW);
await settle();
el.shadowRoot.querySelector("dialog.confirm").close("apply");
await settle();
reply("restore_state", {
  applied: true,
  note: "the live state could not be recorded",
});
await staying;
const bannerHere = el._error;

console.log(JSON.stringify({
  bannerElsewhere, bannerHere,
  previewFor, restoreAfterSwitch, forgetAfterSwitch, versionAfterSwitch,
  openedNormally, restoredTo, carriedTo,
  versionOpened, versionedOn, itemWentTo, undoneOn,
  undoPreviewFlag, undoWriteFlag,
  named: dialogSaid.includes("Kitchen"), forgotten,
}));
"""


@pytest.fixture(scope="session")
def wrong_dashboard(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "wrong_dashboard", _WRONG_DASHBOARD)


def test_a_note_about_a_write_lands_on_the_dashboard_it_was_about(
    wrong_dashboard,
):
    # The write has been pinned to the dashboard whose diff was approved
    # since the flows learned to hold the key; the sentence reporting it
    # was not. Dropped rather than kept for later: the person watched
    # this action start, and showing it over the page they moved on to
    # would be a second wrong place. The reloaded history says what
    # happened, and it is there when they come back.
    assert wrong_dashboard["bannerElsewhere"] is None
    assert wrong_dashboard["bannerHere"] == "the live state could not be recorded"


def test_a_preview_is_written_to_the_dashboard_it_was_fetched_for(wrong_dashboard):
    # The capture, on its own: the selection moved without invalidating
    # anything, and the write still names the dashboard whose diff was
    # shown. Reading `this._selected` in the closure again puts "garden"
    # here - a state written with nobody having seen its diff.
    assert wrong_dashboard["previewFor"] == "kitchen"
    assert wrong_dashboard["carriedTo"] == "kitchen"


def test_a_dashboard_picked_while_the_preview_is_out_cancels_the_dialog(
    wrong_dashboard,
):
    # The claim ticket, on its own: a diff for a dashboard nobody is
    # looking at any more must not be offered at all - it carries the
    # wrong title as well as the wrong content.
    # And it lets go of whoever was waiting for it, rather than sitting
    # on a `close` that can never arrive.
    assert wrong_dashboard["restoreAfterSwitch"] == {
        "settled": True,
        "opened": False,
        "wrote": 0,
    }


def test_forget_deletes_the_history_the_dialog_named(wrong_dashboard):
    # The expensive one. The dialog counts what is about to be lost and
    # says in bold that it cannot be undone; the confirming call used to
    # read the selection again, so the history that went was another
    # dashboard's.
    assert wrong_dashboard["named"] is True
    assert wrong_dashboard["forgotten"] == "kitchen"
    assert wrong_dashboard["forgetAfterSwitch"] == {
        "settled": True,
        "opened": False,
        "deleted": 0,
    }


def test_every_flow_that_writes_carries_its_own_dashboard(wrong_dashboard):
    # Five sites were repaired and two were measured. These are the
    # other three, each with its own request closure: a fix reaching
    # four of five is worse than none, because it looks finished - and
    # so is a measurement reaching two of five.
    #
    # Read together with the run above: the selection moves without
    # going through `_select`, so nothing is invalidated and the only
    # thing that can keep the write where the diff was is the key taken
    # before the first await.
    assert wrong_dashboard["itemWentTo"] == "kitchen"
    assert wrong_dashboard["undoneOn"] == "kitchen"
    # And the version, which writes with `create_version` rather than
    # through `_confirm`, so it is guarded on its own.
    assert wrong_dashboard["versionOpened"] is True
    assert wrong_dashboard["versionedOn"] == "kitchen"


def test_undo_asks_for_a_preview_only_before_the_write(wrong_dashboard):
    # Issue #5's second half: the diff and explanation cost two YAML
    # dumps, and only the call that fills the dialog needs them. The
    # first `undo_change` this flow sends is the preview, the second
    # the write - see operations.py's `async_undo_change` for why the
    # write does not ask again for a diff it already showed.
    assert wrong_dashboard["undoPreviewFlag"] is True
    assert wrong_dashboard["undoWriteFlag"] is False


def test_a_dashboard_picked_while_the_numbers_are_out_cancels_the_version(
    wrong_dashboard,
):
    # The claim ticket again, on the one flow the behaviour tests did
    # not mention at all. The three buttons carry finished version
    # numbers worked out for one dashboard; offering them under another
    # one's name would put a tag somewhere nobody chose.
    assert wrong_dashboard["versionAfterSwitch"] == {
        "asked": "next_versions",
        "settled": True,
        "opened": False,
        "created": 0,
    }


def test_an_undisturbed_restore_still_opens_and_writes(wrong_dashboard):
    # The control for the two above. Without it, "no dialog" and "no
    # write" would also be the answer if this harness could never
    # produce either.
    assert wrong_dashboard["openedNormally"] is True
    assert wrong_dashboard["restoredTo"] == "kitchen"


# -- a render must not tear an open dialog off the screen -------------------
#
# The one finding of the final review the other scenarios structurally
# cannot reach: they all stub `_render`. This one lets the real one run,
# against a stand-in root that models the single thing that matters -
# writing `innerHTML` throws the old nodes away, and a dialog that goes
# with them is gone from the screen without firing `close`.

_DIALOG_SURVIVES = """
const rootNode = () => {
  const it = node();
  Object.defineProperty(it, "innerHTML", {
    get: () => "",
    // Exactly what a browser does to the shadow root's children, the
    // open dialog included. Nothing fires; the nodes are simply gone.
    //
    // Kept as well, in `_written`: it is the page a person would be
    // looking at, and "did the render that was held ever reach the
    // screen" cannot be asked of a root that only throws things away.
    set(html) { it._written = html; it._seen = {}; },
  });
  const base = it.querySelector.bind(it);
  // The stand-in answers every selector with a node of its own, which
  // would make `dialog[open]` true for ever. This one selector is
  // answered honestly, because the whole scenario turns on it.
  it.querySelector = (selector) =>
    selector === "dialog[open]"
      ? (it._seen["dialog.confirm"]?.open ? it._seen["dialog.confirm"] : null)
      : base(selector);
  return it;
};

const finished = async (promise) => {
  let done = false;
  promise.then(() => { done = true; });
  await settle();
  return done;
};

const el = new Panel();
el.shadowRoot = rootNode();
el._selected = "dash";
el._dashboards = [{ key: "dash", title: "Dash", exists: true }];
el._changes = [{ revision: "a", message: "1 card added", timestamp: 1 }];
el._cursor = "older";
el._recorded = () => Promise.resolve();
el._select = async () => {};
el._refreshQuietly = async () => {};
el._reloadAfterWrite = async () => null;
el._loadDashboardsQuietly = async () => {};

const sent = [];
const held = [];
el._call = (type, extra) => {
  sent.push({ type, extra });
  return new Promise((resolve) => held.push({ type, extra, resolve }));
};
const reply = (type, value) => {
  const at = held.findIndex((c) => c.type === type);
  if (at >= 0) held.splice(at, 1)[0].resolve(value);
};

// The confirmation is up and being read.
const restoring = el._restoreState("a", "Back to the state after this change");
await settle();
reply("restore_state", {
  applied: false,
  preview: "-a\\n+b",
  explanation: { groups: [], note: "one card removed" },
});
await settle();
const dialog = el.shadowRoot.querySelector("dialog.confirm");
const opened = dialog.open;

// ...and a page of older changes lands underneath it. "Load older
// changes" is pressed, the old list stays on the screen and stays
// clickable, and a row above it opens this dialog - so the page
// arriving here is the ordinary case, not a contrivance.
const older = el._loadOlder();
await settle();
reply("history", {
  changes: [{ revision: "b", message: "2 moved", timestamp: 2 }],
  next_cursor: null,
});
await older;

const onScreen = el.shadowRoot.querySelector("dialog.confirm");
const stillThere = onScreen === dialog;
const owed = el._renderOwed;

// Answered the way a person can answer: through whatever the shadow
// root is showing. A dialog torn out of the document is not that.
onScreen.close("apply");
await settle();
const written = sent.filter((c) => c.type === "restore_state" && c.extra.confirm);
reply("restore_state", { applied: true });
// Drained here rather than in the output below, so that nothing left
// over from this flow renders into the next one's shadow root.
const settled = await finished(restoring);

// And the same thing with the dialog refused, which is where the debt
// really has to be paid. `_confirm` returns at `answer !== "apply"`
// without rendering again - so do `_describe` and `_createVersion` -
// so on this path the close handler is the only place left where a
// page held back while the dialog stood can reach the screen.
//
// The advanced view for this half: it lists the changes themselves,
// and what has to arrive is a page of them.
el._mode = "advanced";
el.shadowRoot = rootNode();
el._changes = [{ revision: "a", message: "1 card added", timestamp: 1 }];
el._cursor = "older";
const refusing = el._restoreState("a", "Back to the state after this change");
await settle();
reply("restore_state", {
  applied: false,
  preview: "-a\\n+b",
  explanation: { groups: [], note: "one card removed" },
});
await settle();
const refused = el.shadowRoot.querySelector("dialog.confirm");
const refusedOpened = refused.open;

const olderAgain = el._loadOlder();
await settle();
reply("history", {
  changes: [{ revision: "z", message: "9 cards moved", timestamp: 9 }],
  next_cursor: null,
});
await olderAgain;
const owedWhileRefusing = el._renderOwed;
const beforeCancel = el.shadowRoot._written;

refused.close("cancel");
const refusedSettled = await finished(refusing);
const afterCancel = el.shadowRoot._written;

console.log(JSON.stringify({
  opened,
  stillThere,
  owed,
  settled,
  wrote: written.length,
  keep: written[0] ? written[0].extra.keep_as_version ?? null : null,
  rows: el._changes.map((c) => c.revision),
  refused: {
    opened: refusedOpened,
    owed: owedWhileRefusing,
    settled: refusedSettled,
    heldBack: !beforeCancel.includes("9 cards moved"),
    onScreen: afterCancel.includes("9 cards moved"),
    caughtUp: el._renderOwed,
  },
}));
"""


@pytest.fixture(scope="session")
def dialog_survives(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "dialog_survives", _DIALOG_SURVIVES)


def test_an_open_dialog_survives_a_page_arriving_underneath_it(dialog_survives):
    # Without the hold, `_loadOlder` re-renders, the shadow root hands
    # out a different dialog, and the one on the screen is detached: no
    # `close` ever fires, `_confirm` waits for ever, and the
    # confirmation is simply gone with nothing said.
    assert dialog_survives["opened"] is True
    assert dialog_survives["stillThere"] is True
    assert dialog_survives["settled"] is True
    assert dialog_survives["wrote"] == 1


def test_a_page_held_back_reaches_the_screen_when_the_dialog_is_refused(
    dialog_survives,
):
    # The catch-up render in `_answerFrom`, measured where it decides
    # something. This case used to press Apply, and Apply hides the
    # line it is meant to test: `_confirm` renders again anyway on its
    # way out, so deleting the catch-up changed nothing and the case
    # stayed green over its own missing feature.
    #
    # Cancel is the honest path. Every one of the three flows that open
    # a dialog returns without rendering when the answer is not the one
    # they wanted, so a page that arrived while the dialog stood would
    # stay invisible for good - the quieter return of the very fault the
    # hold was added to fix.
    held = dialog_survives["refused"]
    assert held["opened"] is True
    # Held while the dialog stood: the older page is in the list...
    assert held["owed"] is True
    assert held["heldBack"] is True
    assert dialog_survives["rows"] == ["a", "z"]
    # ...and on the screen the moment it closes, with nothing else left
    # in the flow that could have drawn it.
    assert held["settled"] is True
    assert held["onScreen"] is True
    assert held["caughtUp"] is False


def test_the_held_render_runs_when_the_dialog_closes(dialog_survives):
    # The same debt on the path that is written: the render owed while
    # the confirmation stood has been paid by the time the flow moves
    # on, and the older page is in the list rather than dropped.
    assert dialog_survives["owed"] is True
    assert dialog_survives["settled"] is True


def test_the_kept_version_survives_the_render_that_was_held(dialog_survives):
    # The catch-up render replaces the tick box along with everything
    # else, and it runs before `_confirm` reads the person's choice. Read
    # through the reference taken before the dialog opened it is still
    # ticked; looked up again it is a fresh, empty one and the version
    # somebody asked for is dropped without a word.
    assert dialog_survives["keep"] is not None
    assert dialog_survives["keep"]["level"] == "patch"


# -- an unanswered search is not an empty one ------------------------------
#
# Four findings of the final review with one root: `_shown()` could not
# tell "nobody has been asked" from "asked, and nothing there", so the
# page said "Nothing matches." over questions it had never put.

_UNASKED = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._mode = "simple";
el._changes = [
  { revision: "a", message: "1 card added", description: "", versions: [],
    timestamp: 1 },
];
el._versions = [
  { name: "dash/v1.0.0", title: "Winter rebuild", description: "",
    revision: "z" },
];

const sent = [];
const held = [];
el._call = (type, extra) => {
  sent.push(type);
  return new Promise((resolve) => held.push({ type, extra, resolve }));
};
const reply = (type, value) => {
  const at = held.findIndex((c) => c.type === type);
  if (at >= 0) held.splice(at, 1)[0].resolve(value);
};

// The simple mode finds the version without asking anybody.
await el._search("winter");
const inSimple = {
  hits: el._matchingVersions().map((v) => v.name),
  sent: [...sent],
};

// "Advanced view" is pressed with the word still in the box.
const switching = el._setMode("advanced");
await settle();
const whileWalking = {
  sent: [...sent],
  shown: el._shown(),
  note: el._searchNote(),
  main: el._renderMain(),
};
reply("search", {
  changes: [{ revision: "deep", message: "winter rework", timestamp: 2 }],
  more: false,
});
await switching;
const answered = {
  // Null-safe on purpose: with the switch not asking anybody there is
  // no answer here at all, and this case has to fail on its assertion
  // rather than die reading a property of null.
  shown: el._shown() && el._shown().map((c) => c.revision),
  note: el._searchNote(),
};

// A single character, which the second step will not run for.
await el._search("w");
const oneLetter = {
  sent: [...sent],
  shown: el._shown(),
  note: el._searchNote(),
  main: el._renderMain(),
};

console.log(JSON.stringify({ inSimple, whileWalking, answered, oneLetter }));
"""


@pytest.fixture(scope="session")
def unasked(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "unasked", _UNASKED)


def test_switching_to_the_advanced_view_puts_the_standing_query(unasked):
    # The simple mode never asks the server, so after the switch the
    # advanced list had a query, no local hits and `_found === null` -
    # and answered "Nothing matches." to a question nobody had put. Only
    # a further keystroke set the search going.
    assert unasked["inSimple"] == {"hits": ["dash/v1.0.0"], "sent": []}
    assert unasked["whileWalking"]["sent"] == ["search"]
    assert unasked["answered"]["shown"] == ["deep"]
    assert "1 in the whole history." in unasked["answered"]["note"]


def test_a_running_search_does_not_also_say_nothing_matches(unasked):
    # Both sentences stood on the page at once, for the half second per
    # thousand commits the walk takes.
    assert unasked["whileWalking"]["note"] == "Searching the whole history…"
    assert unasked["whileWalking"]["shown"] is None
    assert "Nothing matches." not in unasked["whileWalking"]["main"]


def test_a_query_too_short_to_send_says_so(unasked):
    # Nobody was asked, and nothing said why. An empty note under
    # "Nothing matches." reads as a search that ran and failed.
    assert unasked["oneLetter"]["sent"] == ["search"]  # still only the one
    assert unasked["oneLetter"]["shown"] is None
    assert "Type a second character" in unasked["oneLetter"]["note"]
    assert "Nothing matches." not in unasked["oneLetter"]["main"]


_SEARCH_THROUGH_REFRESH = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._mode = "advanced";
el._changes = [{ revision: "a", message: "1 card added", versions: [] }];

const sent = [];
const held = [];
el._call = (type, extra) => {
  sent.push(type);
  return new Promise((resolve) => held.push({ type, extra, resolve }));
};
const reply = (type, value) => {
  const at = held.findIndex((c) => c.type === type);
  if (at >= 0) held.splice(at, 1)[0].resolve(value);
};

// The walk over the whole history is out...
const searching = el._search("winter");
await settle();
const walking = el._searching;

// ...and somebody saves a dashboard, which is what fires the refresh
// this panel listens for.
const refreshing = el._refreshQuietly();
await settle();
reply("dashboards", { dashboards: [{ key: "dash", exists: true }] });
await settle();
reply("history", {
  changes: [{ revision: "new", message: "2 moved", versions: [] }],
  next_cursor: null,
});
reply("versions", { versions: [] });
await settle();

// The first walk answers now, against a list that has been replaced
// underneath it. Dropped, and the refresh puts the question again.
reply("search", { changes: [{ revision: "old" }], more: false });
await searching;
await settle();
const asked = sent.filter((t) => t === "search").length;
reply("search", { changes: [{ revision: "deep" }], more: false });
await refreshing;

console.log(JSON.stringify({
  walking,
  asked,
  query: el._query,
  shown: el._shown() && el._shown().map((c) => c.revision),
  note: el._searchNote(),
  rows: el._changes.map((c) => c.revision),
}));
"""


@pytest.fixture(scope="session")
def search_through_refresh(tmp_path_factory):
    return _run_in_node(
        tmp_path_factory, "search_through_refresh", _SEARCH_THROUGH_REFRESH
    )


def test_a_refresh_during_a_search_asks_the_question_again(search_through_refresh):
    # The search and the change list used to share one claim ticket, so
    # a refresh took the search's away: its answer was dropped - rightly,
    # the list it was worked out against is gone - and nobody started it
    # again. The page then said "Nothing matches." for good over a
    # history that held thirty.
    assert search_through_refresh["walking"] is True
    assert search_through_refresh["asked"] == 2
    assert search_through_refresh["query"] == "winter"
    assert search_through_refresh["rows"] == ["new"]
    assert search_through_refresh["shown"] == ["deep"]
    assert search_through_refresh["note"] == "1 in the whole history."


# -- the simple mode, which is the default one and had no test at all ------

_SIMPLE_MODE = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._mode = "simple";
el._dashboards = [{ key: "dash", title: "Dash", exists: true }];
// Two of them alike on purpose: same title, same state, one commit.
// That is what an installation looks like where a routine makes the
// versions - on the bench a whole screen of rows read the same, and
// only the number and the time told them apart.
el._versions = [
  // Made by a routine, like most versions on an installation that has
  // any - which is what puts "saved automatically" on its line.
  { name: "dash/v1.2.0", title: "Kitchen rebuild", description: "",
    revision: "a", same_as_now: true, timestamp: 1757246400,
    annotated: true, automatic: true },
  { name: "dash/v1.1.0", title: "Kitchen rebuild", description: "",
    revision: "a", same_as_now: true, timestamp: 1757246300,
    annotated: true },
  { name: "dash/v1.0.0", title: "Autumn tidy", description: "",
    revision: "c", same_as_now: false, timestamp: 0, annotated: true },
  // Its commit is below the loaded window, so there is nothing under
  // this one to open - the usual case on a dashboard with hundreds.
  { name: "dash/v0.9.0", title: "Older still", description: "",
    revision: "z", same_as_now: false, timestamp: 1757100000,
    annotated: true },
];
// The row somebody has open, remembered across renders the way the
// advanced mode remembers its sections.
el._verOpen = new Set(["dash/v1.0.0"]);
el._changes = [
  { revision: "a", message: "1 card added", versions: [{ name: "dash/v1.2.0" }],
    timestamp: 1 },
  { revision: "b", message: "2 cards moved", versions: [], timestamp: 2 },
  { revision: "c", message: "3 cards removed",
    versions: [{ name: "dash/v1.0.0" }], timestamp: 3 },
];

const count = (text, needle) => text.split(needle).length - 1;
// The current-state block on its own. Counted over the whole page the
// version rows' own lines get mixed in, and what is asked here is what
// *this* block holds. Cut at the first row rather than at the block's
// own end tag: shut, the block has no end tag to cut at, and the cut
// then ran on into the row below and found its pen, its fold and its
// number - a probe that answered yes about the row it was written to
// exclude.
const box = (text) => text.split("class=\\"vrow\\"")[0];
// Whether the block is rendered open. Asked of two pages, so it is
// named once - the same regex twice four lines apart is the shape that
// drifts.
const boxOpen = (text) => /<details class="standing[^"]*"[^>]*\\sopen/.test(text);
const plain = el._renderMain();
// The same page with the block already open. Its fold rides the
// version's own name now, which is what makes it one fact across both
// modes rather than two lookalike pieces of furniture.
const everything = el._versions;
const opens = el._verOpen;
el._verOpen = new Set(["dash/v1.2.0"]);
const opened = el._renderMain();
el._verOpen = opens;
// Standing on an *older* version's state, which is where somebody
// lands after going back. The newest version is then not the one the
// block names, the rows above it are newer and say something else, and
// folding them together would put the wrong number in the block.
el._versions = everything.map((v) => ({
  ...v,
  same_as_now: v.name === "dash/v1.0.0",
}));
const older = el._renderMain();
el._versions = everything;
// A search that leaves the standing version at the top. The rows are
// the answer to what was typed and the block is a statement about the
// dashboard; folding them together here would make the block's content
// depend on the query.
await el._search("kitchen");
const hunting = el._renderMain();
// The simple mode filters the complete version list and asks nobody,
// so this needs no server at all.
await el._search("autumn");
const filtered = el._renderMain();

console.log(JSON.stringify({
  plain: {
    standing: plain.includes("in the state of v1.2.0"),
    rows: count(plain, "class=\\"vrow\\""),
    twoChanges: plain.includes("The newest 2 changes in this version"),
    oneChange: plain.includes("The newest change in this version"),
    numbers: count(plain, "class=\\"name\\""),
    middle: plain.includes(">v1.1.0<"),
    here: count(plain, "where you are"),
    alike: count(plain, "same state as now"),
    dated: count(plain, "class=\\"made\\""),
    opens: count(plain, "<details class=\\"vrow\\""),
    flat: count(plain, "<div class=\\"vrow\\""),
    remembered: /data-key="dash\\/v1\\.0\\.0"\\s+open/.test(plain),
    shut: /data-key="dash\\/v1\\.2\\.0"\\s+open/.test(plain),
    badge: count(plain, "class=\\"chip now"),
    undo: count(plain, "Undo / Go back"),
    pens: count(plain, "data-retitle="),
    bins: count(plain, "data-remove="),
    named: count(plain, ">v1.2.0<"),
    boxNumber: box(plain).includes(">v1.2.0<"),
    boxTitle: box(plain).includes("Kitchen rebuild"),
    boxDated: box(plain).includes("class=\\"made\\""),
    boxAuto: box(plain).includes("saved automatically"),
    boxPen: box(plain).includes("data-retitle=\\"dash/v1.2.0\\""),
    boxBin: box(plain).includes("data-remove=\\"dash/v1.2.0\\""),
    boxSave: box(plain).includes("data-version=\\"now\\""),
    boxSpan: box(plain).includes("The newest 2 changes in this version"),
    boxSince: box(plain).includes("since the last version"),
    boxHere: box(plain).includes("where you are"),
    keyed: /<details class="standing[^"]*" data-key="dash\\/v1\\.2\\.0"/.test(plain),
    boxShut: boxOpen(plain),
    // The dashboard holds exactly what v1.2.0 holds, and stands on it -
    // GitHub issue #11's case 2. Both the box's own ring and the chip
    // inside it have to say "named", the same fact worn two ways.
    namedBox: /class="standing named"/.test(plain),
    namedChip: box(plain).includes("class=\\"chip now named\\""),
  },
  opened: {
    boxOpen: boxOpen(opened),
  },
  older: {
    standing: older.includes("in the state of v1.0.0"),
    rows: count(older, "class=\\"vrow\\""),
    here: count(older, "where you are"),
    // Case 3: clean, but standing on an *older* version - not the top
    // of the list, and not merged into one block with it either. The
    // ring answers the same question regardless: something recorded
    // holds this content, so it is blue.
    namedBox: /class="standing named"/.test(older),
  },
  hunting: {
    standing: hunting.includes("in the state of v1.2.0"),
    rows: count(hunting, "class=\\"vrow\\""),
    named: count(hunting, ">v1.2.0<"),
  },
  filtered: {
    standing: filtered.includes("in the state of v1.2.0"),
    drifted: filtered.includes("has changed since the last version"),
    rows: count(filtered, "class=\\"vrow\\""),
    autumn: filtered.includes("Autumn tidy"),
  },
}));
"""


@pytest.fixture(scope="session")
def simple_mode(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "simple_mode", _SIMPLE_MODE)


def test_the_simple_mode_says_where_the_dashboard_stands(simple_mode):
    # `same_as_now` comes from the server, worked out against every
    # version - including one whose commit is below the loaded window.
    # The sentence is for the case the block cannot say it by itself:
    # standing on an older version's state, with newer ones listed above
    # it. Where the newest version *is* the one being stood on, the
    # block carries that version instead of a sentence about it.
    assert simple_mode["older"]["standing"] is True
    assert simple_mode["older"]["rows"] == 4
    assert simple_mode["plain"]["standing"] is False


def test_the_current_state_rings_blue_wherever_a_version_holds_it(simple_mode):
    # GitHub issue #11: blue used to mean "this is the current state" in
    # this mode and "unclean" in the advanced one - two meanings for one
    # colour. Now it answers one question in both: does anything
    # recorded hold what the dashboard holds right now. Case 2, merged
    # into the top version, and case 3, standing on an older one further
    # down the list, both answer "yes" and both ring blue.
    assert simple_mode["plain"]["namedBox"] is True
    assert simple_mode["plain"]["namedChip"] is True
    assert simple_mode["older"]["namedBox"] is True


def test_the_state_and_the_version_it_holds_are_drawn_once(simple_mode):
    # The block said "the dashboard is in the state of v1.2.0" and the
    # row directly under it said "v1.2.0 - where you are": one version,
    # twice, in two vocabularies. There is nothing to do on that row
    # that the block does not offer, so the two become one and the
    # number is written where the other boxes write it.
    assert simple_mode["plain"]["rows"] == 3
    assert simple_mode["plain"]["named"] == 1
    assert simple_mode["plain"]["boxNumber"] is True
    assert simple_mode["plain"]["boxTitle"] is True
    assert simple_mode["plain"]["boxDated"] is True
    assert simple_mode["plain"]["boxAuto"] is True


def test_the_merged_block_folds_onto_the_versions_own_changes(simple_mode):
    # The version's span, not the block's. Where the two are folded
    # together the changes *since* the version are by definition the
    # ones that did not alter the state - otherwise it would no longer
    # match - so they answer nothing, while the changes the version
    # collected are what somebody came to read.
    assert simple_mode["plain"]["boxSpan"] is True
    assert simple_mode["plain"]["boxSince"] is False


def test_the_merged_block_keeps_what_the_row_could_do(simple_mode):
    # Everything the row offered that the block did not: the pen, the
    # bin. Withholding the pen here would take the newest version - the
    # one most likely to be renamed - out of reach in this mode
    # entirely, against the promise that any version can be renamed.
    assert simple_mode["plain"]["boxPen"] is True
    assert simple_mode["plain"]["boxBin"] is True
    assert simple_mode["plain"]["boxSave"] is True


def test_the_merged_block_says_where_you_are_only_once(simple_mode):
    # The chip beside "Right now" already says it. "where you are" was
    # the row's way of saying the same thing, and inside one block the
    # two would sit four lines apart saying it twice.
    assert simple_mode["plain"]["boxHere"] is False
    assert simple_mode["plain"]["badge"] == 1


def test_the_merged_block_folds_under_the_versions_own_name(simple_mode):
    # Keyed by the version rather than by the block, because what it
    # holds is that version's changes - the same fact the advanced mode
    # folds under that name, and one fact should not need two keys. It
    # also means the version made by "Save this as a version" is open
    # when the page comes back, since the panel puts a created name into
    # that same set.
    assert simple_mode["plain"]["keyed"] is True
    assert simple_mode["plain"]["boxShut"] is False
    assert simple_mode["opened"]["boxOpen"] is True


def test_a_search_leaves_the_block_and_the_rows_apart(simple_mode):
    # Two subjects, and merging them would give the block a content that
    # depends on what somebody typed. The search matches both "Kitchen
    # rebuild" versions, so the standing one is the top row - which is
    # the whole condition for merging, minus the search.
    assert simple_mode["hunting"]["rows"] == 2
    assert simple_mode["hunting"]["standing"] is True
    assert simple_mode["hunting"]["named"] == 1


def test_every_row_carries_the_number_it_is_known_by(simple_mode):
    # The mark that is unique and ordered whatever anybody called the
    # version. Left out, this mode showed three rows reading "Kitchen
    # rebuild" with nothing to choose between them - which is what an
    # installation with automatic versions actually looks like.
    assert simple_mode["plain"]["numbers"] == 4
    assert simple_mode["plain"]["middle"] is True


def test_a_version_is_dated_where_the_date_is_known(simple_mode):
    # The second mark. A tag made by hand has no time of its own, and
    # then the row says nothing rather than showing a date of 1970 -
    # this is a list people read down, and one wrong date in it puts
    # every other one in doubt.
    assert simple_mode["plain"]["dated"] == 3


def test_only_one_row_is_where_you_are(simple_mode):
    # Three versions can hold what the dashboard holds; you still stand
    # in one place. Saying it on each of them was the whole confusion of
    # this mode - a screen on which the answer to "where am I" appeared
    # six times. The others say what is true of them: they hold the same
    # state. No button there, because going back would write nothing.
    #
    # Read off the drifted page, because on the plain one that row is
    # inside the current-state block and its chip says it instead.
    assert simple_mode["older"]["here"] == 1
    assert simple_mode["plain"]["here"] == 0
    assert simple_mode["plain"]["alike"] == 1


def test_a_row_with_nothing_under_it_does_not_pretend_to_open(simple_mode):
    # The whole row is the way in to its changes, so it may only look
    # like one where there are changes to show. A version whose commit
    # is below the loaded window has none - which on a dashboard with
    # hundreds is most of them - and stays a plain row.
    assert simple_mode["plain"]["opens"] == 2
    assert simple_mode["plain"]["flat"] == 1


def test_an_opened_row_survives_a_render(simple_mode):
    # The lesson the advanced mode's sections paid for: a render builds
    # new <details>, so native state alone shuts the row somebody is
    # working in. Here it would shut on the way to the confirm dialog -
    # _guard fetches the preview, which renders, and the row the button
    # was clicked in folds up under the hand that clicked it.
    assert simple_mode["plain"]["remembered"] is True
    assert simple_mode["plain"]["shut"] is False


def test_a_search_does_not_change_what_is_said_about_the_dashboard(simple_mode):
    # Two subjects on one page. The rows answer what was typed; the
    # sentence at the top is about the dashboard, and typing says
    # nothing about that. Handed only the filtered list, the page
    # flipped to "The dashboard has changed since the last version was
    # saved." the moment a search removed the version it is standing on.
    assert simple_mode["filtered"]["rows"] == 1
    assert simple_mode["filtered"]["autumn"] is True
    assert simple_mode["filtered"]["standing"] is True
    assert simple_mode["filtered"]["drifted"] is False


def test_the_fold_counts_only_what_it_can_show(simple_mode):
    # The fold holds the loaded changes of that version, cut at the
    # older end by whatever the window reaches. "2 changes in this
    # version" was flatly wrong for a version spanning a hundred, and
    # this mode has no "load older" that could ever make it right.
    assert simple_mode["plain"]["twoChanges"] is True
    assert simple_mode["plain"]["oneChange"] is True


def test_every_version_offers_a_way_to_rename_itself(simple_mode):
    # Every one of the four, including the one whose commit is below the
    # window and the one somebody is standing in - which is drawn inside
    # the current-state block rather than as a row. Renaming touches a
    # tag's wording and nothing else, so none of the reasons a row
    # withholds its *button* - it holds the live state, it is where you
    # are - has any bearing on this one.
    assert simple_mode["plain"]["pens"] == 4


def test_every_version_in_the_simple_mode_offers_a_way_to_remove_itself(
    simple_mode,
):
    # The mode a fresh panel opens in, and the one `look_at_panel.py`
    # never reads - it only checks the advanced head. Without this, the
    # bin could be deleted from `simple.js` and nothing here would
    # notice.
    assert simple_mode["plain"]["bins"] == 4


def test_the_current_state_carries_the_badge_the_other_mode_carries(simple_mode):
    # One chip, and the advanced mode's chip word for word. What it
    # labels here is the box and not a recorded row, which is why it
    # needs no proof: "right now" is the live state by definition.
    assert simple_mode["plain"]["badge"] == 1


def test_no_way_back_is_offered_from_a_state_that_is_a_version(simple_mode):
    # The dashboard holds v1.2.0's state, so there is nothing to undo.
    # Offering it would open the confirm dialog on an empty diff with a
    # live Apply - the same reason the rows leave their button out.
    assert simple_mode["plain"]["undo"] == 0


# -- the current-state block, once the dashboard has drifted from every ----
# -- version: the badge, the way back, and the changes folded under it -----

_SIMPLE_NOW = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._mode = "simple";
el._dashboards = [{ key: "dash", title: "Dash", exists: true }];
// Nothing the dashboard holds is any version's state: somebody has been
// editing since the last one was saved. That is the case the
// current-state block exists for, and the only one offering a way back.
el._versions = [
  { name: "dash/v1.2.0", title: "Kitchen rebuild", description: "",
    revision: "c", same_as_now: false, timestamp: 1757246400 },
  { name: "dash/v1.0.0", title: "Autumn tidy", description: "",
    revision: "e", same_as_now: false, timestamp: 1757100000 },
];
// The box's fold, remembered in the one set that remembers folds in
// the main area. Not a second store beside it: the box carries a
// version's own name where the two are drawn as one, and a fact that
// changed shelves depending on the data was a fact in two places.
// "now" cannot collide with a version, which always carries a slash.
el._verOpen = new Set(["now"]);
const since = [
  { revision: "a", message: "1 card added", versions: [], timestamp: 1 },
  { revision: "b", message: "2 cards moved", versions: [], timestamp: 2 },
];
const marked = { revision: "c", message: "3 cards removed",
                 versions: [{ name: "dash/v1.2.0" }], timestamp: 3 };

const count = (text, needle) => text.split(needle).length - 1;
// Inside the current-state block and nothing else. Counted over the
// whole page, the lines of the version row below get mixed in - and the
// question here is what *this* block folded.
const inside = (text) =>
  text.split("<details class=\\"standing\\"")[1]?.split("</details>")[0] || "";

// The version bounding the changes sits in the window, so the count is
// the whole truth.
el._changes = since.concat([marked]);
const drifted = el._renderMain();

// It does not, so the count is whatever the window reached - and says so.
el._changes = since;
const cut = el._renderMain();

// Nothing recorded since the last version, and yet the dashboard holds
// something else: a change made at Home Assistant's back. Nothing to
// fold, and the way back is the one thing that matters.
el._changes = [marked];
const behind = el._renderMain();

console.log(JSON.stringify({
  drifted: {
    opens: count(drifted, "<details class=\\"standing\\""),
    flat: count(drifted, "<div class=\\"standing\\""),
    exact: drifted.includes("The 2 changes since the last version"),
    steps: count(inside(drifted), "class=\\"step\\""),
    ownStep: inside(drifted).includes("3 cards removed"),
    badge: count(drifted, "class=\\"chip now\\""),
    undo: drifted.includes(">Undo / Go back to v1.2.0<"),
    target: /data-state="dash\\/v1\\.2\\.0"[^>]*>Undo/.test(drifted),
    remembered: /data-key="now"\\s+open/.test(drifted),
    // Case 1, GitHub issue #11: nothing recorded holds this content, so
    // neither the box nor its chip may carry the "named" modifier that
    // turns the ring blue.
    unnamedBox: !drifted.includes("class=\\"standing named\\""),
    unnamedChip: !drifted.includes("class=\\"chip now named\\""),
  },
  cut: {
    hedged: cut.includes("The newest 2 changes since the last version"),
    exact: cut.includes("The 2 changes since the last version"),
    undo: cut.includes(">Undo / Go back to v1.2.0<"),
  },
  behind: {
    opens: count(behind, "<details class=\\"standing\\""),
    flat: count(behind, "<div class=\\"standing\\""),
    undo: behind.includes(">Undo / Go back to v1.2.0<"),
  },
}));
"""


@pytest.fixture(scope="session")
def simple_now(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "simple_now", _SIMPLE_NOW)


def test_the_current_state_offers_one_way_back_to_the_last_version(simple_now):
    # The whole point of the button: one press, and everything since the
    # last saved state is off the dashboard. It is the version rows'
    # "Go back to this" aimed at the top row, so it goes through
    # `restore_state` and shows its diff first like everything else.
    assert simple_now["drifted"]["undo"] is True
    assert simple_now["drifted"]["target"] is True
    assert simple_now["behind"]["undo"] is True
    assert simple_now["cut"]["undo"] is True


def test_the_current_state_rings_orange_where_nothing_holds_it(simple_now):
    # GitHub issue #11, case 1: unsaved changes, no matching version -
    # the ring and its chip stay unnamed, which is what turns them
    # orange in the stylesheet.
    assert simple_now["drifted"]["unnamedBox"] is True
    assert simple_now["drifted"]["unnamedChip"] is True


def test_the_current_state_opens_onto_the_changes_it_holds(simple_now):
    # Two changes since v1.2.0, and the third is the version's own - it
    # belongs to the row below, not in here.
    assert simple_now["drifted"]["opens"] == 1
    assert simple_now["drifted"]["flat"] == 0
    assert simple_now["drifted"]["steps"] == 2
    # And not the version's own change: that one is the state v1.2.0
    # marks, so it belongs to the row below rather than to the changes
    # made since it.
    assert simple_now["drifted"]["ownStep"] is False


def test_the_current_state_counts_exactly_where_it_can(simple_now):
    # The version bounding the fold is in the window, so nothing is cut
    # at the older end and the count needs no hedge. This is the one
    # place in this mode that can say so - a version row never knows
    # where its own span ends.
    assert simple_now["drifted"]["exact"] is True
    assert simple_now["cut"]["exact"] is False
    assert simple_now["cut"]["hedged"] is True


def test_the_current_state_does_not_open_onto_nothing(simple_now):
    # Same rule as the version rows: a fold with nothing behind it is a
    # promise broken as soon as it is taken up. Here it happens when the
    # dashboard was changed at Home Assistant's back - no change was
    # recorded since the version, and yet the state differs.
    assert simple_now["behind"]["opens"] == 0
    assert simple_now["behind"]["flat"] == 1


def test_the_opened_current_state_survives_a_render(simple_now):
    # The lesson the version rows paid for, and this block needs it
    # more: its own button re-renders the page on the way to the confirm
    # dialog, so without this the box folds up under the hand that
    # clicked it.
    assert simple_now["drifted"]["remembered"] is True


def test_the_drifted_current_state_still_carries_the_badge(simple_now):
    assert simple_now["drifted"]["badge"] == 1


# -- rows.js, the other half with no behavioural test ----------------------

_RETITLE = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._mode = "simple";
// The complete list from the server, which is what this reads. Neither
// version's commit is in `_changes` below - the ordinary case on a
// dashboard with more versions than a window holds, and the one a
// lookup through the loaded marks would get wrong.
el._versions = [
  { name: "dash/v1.0.0", title: "Autumn tidy", description: "the old note",
    revision: "a", automatic: false },
  { name: "dash/v1.1.0", title: "7 September 2026", description: "",
    revision: "b", automatic: true },
];
el._changes = [{ revision: "z", message: "1 card added", versions: [] }];

const sent = [];
el._call = (type, extra) => {
  sent.push({ type, extra });
  return Promise.resolve({ applied: true });
};
// The reload is the sibling flows' and is measured with them; what
// matters here is that this flow reaches it at all.
let reloaded = 0;
el._reloadAfterWrite = () => {
  reloaded += 1;
  return Promise.resolve(null);
};
el.shadowRoot = node();
const box = el.shadowRoot.querySelector("dialog.retitle");
const which = box.querySelector("[data-which]");
const title = box.querySelector("input.title");
const desc = box.querySelector("input.desc");

// A version somebody made: both fields arrive prefilled.
const editing = el._retitleVersion("dash/v1.0.0");
await settle();
const opened = {
  open: box.open,
  title: title.value,
  desc: desc.value,
  which: which.textContent,
};
title.value = "Before the rework";
desc.value = "handed over to the tenant";
box.close("save");
await editing;
const wrote = sent.map((call) => ({ type: call.type, ...call.extra }));

// One a routine made. The dialog promises the badge survives, which is
// the one thing about the version it changes nothing about.
sent.length = 0;
const automatic = el._retitleVersion("dash/v1.1.0");
await settle();
const badge = which.textContent;
const prefilled = title.value;
box.close("cancel");
await automatic;
const afterCancel = sent.length;

// A name that is not in the list opens nothing. Same shape as the
// lookup miss in `_describe`: the dialog never showing is the tell.
box.open = false;
await el._retitleVersion("dash/v9.9.9");
const missing = box.open;

console.log(JSON.stringify({
  opened, wrote, badge, prefilled, afterCancel, missing, reloaded,
}));
"""


@pytest.fixture(scope="session")
def retitling(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "retitling", _RETITLE)


def test_the_two_fields_arrive_carrying_what_the_version_says(retitling):
    # Prefilled, because this is a correction far more often than a
    # rewrite - and an empty title field would be a trap: a version
    # cannot be left without one, so somebody who only wanted to add a
    # note would have to retype the name to get past the refusal.
    assert retitling["opened"]["open"] is True
    assert retitling["opened"]["title"] == "Autumn tidy"
    assert retitling["opened"]["desc"] == "the old note"


def test_the_dialog_names_the_version_it_is_about(retitling):
    # Two rows of the simple mode can carry the same title - that is
    # what the numbers are for - so "this version" alone leaves
    # somebody checking behind themselves.
    assert retitling["opened"]["which"] == "v1.0.0"


def test_saving_sends_the_dashboard_the_name_and_both_fields(retitling):
    assert retitling["wrote"] == [
        {
            "type": "retitle_version",
            "dashboard": "dash",
            "name": "dash/v1.0.0",
            "title": "Before the rework",
            "description": "handed over to the tenant",
        }
    ]
    # And ends on the reload, or the row on the screen would go on
    # showing the title that was just replaced.
    assert retitling["reloaded"] == 1


def test_renaming_an_automatic_version_promises_the_badge_survives(retitling):
    # It does survive - `async_retitle_version` puts the marker back -
    # and the badge is the one thing next to the words that this dialog
    # visibly rewrites without touching. Said, rather than left to be
    # discovered by whoever wonders where it went.
    assert retitling["badge"] == (
        "v1.1.0 — it stays marked as saved automatically."
    )
    assert retitling["prefilled"] == "7 September 2026"


def test_a_dialog_dismissed_without_saving_writes_nothing(retitling):
    assert retitling["afterCancel"] == 0


def test_a_version_that_is_not_in_the_list_opens_nothing(retitling):
    assert retitling["missing"] is False


_ROWS = """
const rows = await import(new URL("./panel/rows.js", %(url)s).href);
const annotated = { name: "dash/v1.0.0", title: "First", annotated: true };
const byHand = { name: "dash/v2.0.0", title: "", annotated: false };

// A version marks a state, so it heads the section running from its own
// change downwards to the next version below. Everything above the
// topmost version is not in a version yet.
const cut = rows.sections([
  { revision: "a", versions: [] },
  { revision: "b", versions: [{ name: "dash/v1.0.0", title: "One" }] },
  { revision: "c", versions: [] },
]);

const head = (here, top) =>
  rows.versionHead({
    version: { name: "dash/v1.0.0", title: "One", annotated: true },
    here,
    top,
    count: 2,
  });
const headCompare = (here, top) =>
  rows.versionHead({
    version: { name: "dash/v1.0.0", title: "One", annotated: true },
    here,
    top,
    count: 2,
    compareMode: true,
  });

// Two versions on one state: each gets a head of its own - stacked,
// not folded into one head naming both - so both need their own way
// to be renamed. The panel builds one of these per name in a
// section's `versions`, all opening onto the same rows.
const stackedFirst = rows.versionHead({
  version: { name: "dash/v1.0.0", title: "One", annotated: true },
  here: false,
  top: 2,
  count: 2,
});
const stackedSecond = rows.versionHead({
  version: { name: "dash/v1.1.0", title: "Also one", annotated: true },
  here: false,
  top: 2,
  count: 2,
});
const stacked = stackedFirst + stackedSecond;

const auto = rows.versionHead({
  version: { name: "dash/v1.0.0", title: "One", automatic: true },
  here: false,
  top: 2,
  count: 1,
});
const described = rows.versionHead({
  version: { name: "dash/v1.0.0", title: "One", description: "Why it was made" },
  here: false,
  top: 2,
  count: 1,
});
const undescribed = rows.versionHead({
  version: { name: "dash/v1.0.0", title: "One" },
  here: false,
  top: 2,
  count: 1,
});

const row = (change, extra) =>
  rows.renderRow({ change, ...extra });
const CHANGE = { revision: "abcdef012345", message: "2 cards moved",
                 timestamp: 1, same_as_now: true };

console.log(JSON.stringify({
  sections: cut.map((s) => ({
    named: s.versions ? s.versions[0].name : null,
    rows: s.rows,
  })),
  // "current state" is said once now, by the right-now element alone -
  // a version's own head says "same state as now" whether it is the
  // newest entry (top 0) or one further down (top 2).
  sameStateOnTop: head(true, 0).includes("same state as now"),
  noCurrentStateOnTop: head(true, 0).includes("current state"),
  sameState: head(true, 2).includes("same state as now"),
  wayBack: head(false, 2).includes("Back to this version"),
  noWayBackWhereYouAre: head(true, 0).includes("Back to this version"),
  names: [
    rows.someNames(["v1.0.0"]),
    rows.someNames(["v1.0.0", "v1.1.0"]),
    rows.someNames(["v1.0.0", "v1.1.0", "v1.2.0"]),
  ],
  newestChip: row(CHANGE, { newest: true }).includes("current state"),
  lowerChip: row(CHANGE, { newest: false }).includes("same state as now"),
  // GitHub issue #11: the crowned row's own chip has to agree with the
  // ring drawn around its card - orange where nothing recorded holds
  // this content, blue the moment a version does.
  nowChipUnnamed: row(CHANGE, { newest: true }).includes('class="chip now"'),
  nowChipNamed: row(CHANGE, { newest: true, matching: ["v1.0.0"] })
    .includes('class="chip now named"'),
  spokenFor: row(CHANGE, { newest: true, spokenFor: true })
    .includes("current state"),
  // A version sitting on the newest change is known-current for
  // compare mode even though nothing here calls it a "chip" - the
  // version head states it in plain text instead (`crowned` above).
  headNowWhereCrowned: headCompare(true, 0).includes('data-compare-now="1"'),
  // Further down, `here` still means "this is where this version's
  // state sits", but not on the newest change - "same state as now",
  // never "current state" - so it must not carry the flag either.
  headNowFurtherDown: headCompare(true, 2).includes('data-compare-now="1"'),
  headNowWhereNotHere: headCompare(false, 0).includes('data-compare-now="1"'),
  // `spokenFor` mutes only the chip's *text* - the checkbox underneath
  // a crowned version head is still the newest, still same_as_now, and
  // compare mode has to know that regardless of what the row says.
  rowNowWhenCrowned: row(CHANGE, { newest: true, compareMode: true, spokenFor: true })
    .includes('data-compare-now="1"'),
  rowNowWhenNotSameAsNow: row({ ...CHANGE, same_as_now: false }, { newest: true, compareMode: true })
    .includes('data-compare-now="1"'),
  // Byte-identical further down without being where you are (moved a
  // card back and forth) is not "now" for compare mode either - the
  // same distinction `lowerChip` above already draws.
  rowNowWhenNotNewest: row(CHANGE, { newest: false, compareMode: true })
    .includes('data-compare-now="1"'),
  movedOn: row({ ...CHANGE, same_as_now: false }, { newest: true })
    .includes("chip"),
  named: row(CHANGE, { newest: true, matching: ["v1.0.0"] })
    .includes("same state as v1.0.0"),
  pen: head(false, 2).includes('data-retitle="dash/v1.0.0"'),
  stackedPens: (stacked.match(/data-retitle=/g) || []).length,
  stackedBins: (stacked.match(/data-remove=/g) || []).length,
  autoBadge: auto.includes("saved automatically"),
  noAutoBadgeByDefault: head(false, 2).includes("saved automatically"),
  describedShowsIt: described.includes("Why it was made"),
  undescribedShowsNothing: undescribed.includes('class="why"'),
  penOnAHandMadeTag: rows.pen({ name: "dash/by-hand", title: "", annotated: false }),
  penOnATitlelessAnnotatedTag: rows.pen({
    name: "dash/odd", title: "", annotated: true,
  }).includes("data-retitle"),
  binOnAnnotated: rows.bin(annotated).includes("data-remove"),
  binOnByHand: rows.bin(byHand).includes("data-remove"),
  binCarriesTheName: rows.bin(annotated).includes('data-remove="dash/v1.0.0"'),
  binIsRevealedLikeThePen: rows.bin(annotated).includes('class="pen bin"'),
}));
"""


@pytest.fixture(scope="session")
def row_parts(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "rows", _ROWS)


def test_the_history_is_cut_into_sections_at_the_versions(row_parts):
    # The first section can be version-less and the later ones cannot -
    # which is why `_renderMain` handles the unbundled case once,
    # outside the loop.
    assert row_parts["sections"] == [
        {"named": None, "rows": [0]},
        {"named": "dash/v1.0.0", "rows": [1, 2]},
    ]


def test_a_section_head_offers_the_way_back_only_where_it_leads_somewhere(
    row_parts,
):
    # Offering it on the state the dashboard already holds opens a
    # dialog reading "No difference." above a live Apply button.
    assert row_parts["wayBack"] is True
    assert row_parts["noWayBackWhereYouAre"] is False
    # One wording wherever it sits: "current state" belongs to the
    # right-now element alone now, so a version's own head says "same
    # state as now" whether it is the newest entry or one further down.
    assert row_parts["sameStateOnTop"] is True
    assert row_parts["noCurrentStateOnTop"] is False
    assert row_parts["sameState"] is True


def test_a_chip_says_which_kind_of_sameness_it_means(row_parts):
    assert row_parts["newestChip"] is True
    assert row_parts["lowerChip"] is True
    # The head a few pixels above already carries it; twice is noise.
    assert row_parts["spokenFor"] is False
    # And nothing at all where the dashboard has moved on.
    assert row_parts["movedOn"] is False
    assert row_parts["named"] is True


def test_the_now_chip_rings_the_same_colour_as_its_card(row_parts):
    assert row_parts["nowChipUnnamed"] is True
    assert row_parts["nowChipNamed"] is True


def test_compare_mode_marks_a_pick_that_is_known_to_be_current(row_parts):
    # Found from a real installation: a version sitting on the newest
    # change is already known to be "current state" - the panel says so
    # in the version head's own text - but its compare-mode checkbox
    # used to carry only its own revision, with nothing distinguishing
    # it from an arbitrary past pick. `data-compare-now` is that
    # distinction, and it must land on exactly the picks the panel
    # already calls current, in either rendering path (a row, or a
    # version head), and nowhere else.
    assert row_parts["headNowWhereCrowned"] is True
    assert row_parts["headNowFurtherDown"] is False
    assert row_parts["headNowWhereNotHere"] is False
    assert row_parts["rowNowWhenCrowned"] is True
    assert row_parts["rowNowWhenNotSameAsNow"] is False
    assert row_parts["rowNowWhenNotNewest"] is False


def test_every_version_a_head_names_can_be_renamed(row_parts):
    # Two tags on one state get a head each, stacked - not one head
    # naming both - so both need their own way to be renamed.
    assert row_parts["pen"] is True
    assert row_parts["stackedPens"] == 2
    # The bin is offered on every version, unlike the pen, so it needs
    # the same twin assertion to be exercised at all in this shape.
    assert row_parts["stackedBins"] == 2


def test_a_versions_own_badge_and_note_show_in_the_advanced_head_too(row_parts):
    # Both used to be simple-mode-only, which made no sense: an
    # automatic version and a person's own words about a version are
    # facts about the version, not about which mode happens to draw it.
    assert row_parts["autoBadge"] is True
    assert row_parts["noAutoBadgeByDefault"] is False
    assert row_parts["describedShowsIt"] is True
    assert row_parts["undescribedShowsNothing"] is False


def test_a_version_made_by_hand_gets_no_pen(row_parts):
    # A lightweight tag has no message, so there is nothing to change
    # and the store says so. An offer that can only produce that
    # sentence is not an offer.
    assert row_parts["penOnAHandMadeTag"] == ""


def test_the_pen_asks_the_kind_of_tag_and_not_the_title(row_parts):
    # This used to read "does it have a title", which was reading a fact
    # out of a name - and wrong in both directions. A hand-made
    # *annotated* tag with an empty first line can be renamed, and the
    # FAQ promises that any version can be.
    assert row_parts["penOnATitlelessAnnotatedTag"] is True


def test_a_long_list_of_names_is_cut_and_says_so(row_parts):
    # Measured on the test bench: eighteen versions sat on states equal
    # to the live one, and the chip listed every one of them.
    assert row_parts["names"] == [
        "v1.0.0",
        "v1.0.0 and v1.1.0",
        "v1.0.0 and 2 more",
    ]


# -- the current-state ring answers one question, in both modes -------------
# GitHub issue #11: blue used to mean "current state" in the simple view
# and "unclean" in the advanced one. Now both ask the same question -
# does anything recorded hold what the dashboard holds right now - and
# only the crowned row or version section can ever be asked it at all.

_CURRENT_STATE_COLOUR = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._mode = "advanced";

// Case 1: unsaved changes, no version holds them.
el._changes = [
  { revision: "a", message: "1 card added", versions: [], same_as_now: true, timestamp: 2 },
  { revision: "b", message: "2 cards moved", versions: [], same_as_now: false, timestamp: 1 },
];
el._versions = [];
el._matching = [];
const unclean = el._renderMain();

// Case 2: the newest change already carries a version, and it is what
// the dashboard holds right now - the version section itself is the
// crowned one. `sections()` reads a change's own `.versions` entries,
// not `el._versions` - the date has to sit there for `versionHead` to
// find it.
el._changes = [
  { revision: "a", message: "1 card added",
    versions: [{ name: "dash/v1.0.0", title: "First", timestamp: 1 }],
    same_as_now: true, timestamp: 1 },
];
el._versions = [
  { name: "dash/v1.0.0", title: "First", same_as_now: true, revision: "a" },
];
el._matching = [];
const cleanOnTop = el._renderMain();

// Case 3: nothing recorded since v1.0.0, but the dashboard's content is
// still exactly what it holds - a version further down the list, not
// the newest change, so the ring belongs to the current-state box and
// not to that version's own section.
el._changes = [
  { revision: "b", message: "2 cards moved", versions: [], same_as_now: true, timestamp: 2 },
  { revision: "a", message: "1 card added", versions: [{ name: "dash/v1.0.0" }],
    same_as_now: false, timestamp: 1 },
];
el._versions = [
  { name: "dash/v1.0.0", title: "First", same_as_now: false, revision: "a" },
];
el._matching = [{ name: "dash/v1.0.0" }];
const cleanOnOlder = el._renderMain();

console.log(JSON.stringify({
  unclean: {
    panel: unclean.includes('class="now-panel"'),
    named: unclean.includes('class="now-panel named"'),
    verNow: unclean.includes('class="ver now"'),
  },
  cleanOnTop: {
    verNow: cleanOnTop.includes('class="ver now"'),
    // The crowned section *is* the right-now element now - its own
    // head carries the "Right now" heading, the blue badge and a
    // date, and there is no second, bodyless element above it saying
    // the same thing again.
    rightNowHeading: cleanOnTop.includes('<p class="heading">Right now'),
    date: cleanOnTop.includes('class="made"'),
    noBanner: !cleanOnTop.includes('class="now-panel'),
    noCountTextAtAll: !cleanOnTop.includes('<span class="count">current state</span>')
      && !cleanOnTop.includes('<span class="count">same state as now</span>'),
  },
  cleanOnOlder: {
    named: cleanOnOlder.includes('class="now-panel named"'),
    verNow: cleanOnOlder.includes('class="ver now"'),
  },
}));
"""


@pytest.fixture(scope="session")
def current_state_colour(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "current_state_colour", _CURRENT_STATE_COLOUR)


def test_the_crowned_row_rings_orange_when_nothing_recorded_holds_it(
    current_state_colour,
):
    assert current_state_colour["unclean"]["panel"] is True
    assert current_state_colour["unclean"]["named"] is False
    assert current_state_colour["unclean"]["verNow"] is False


def test_a_version_section_rings_blue_when_it_is_also_the_current_state(
    current_state_colour,
):
    # Only the first section in the list can start at the newest change
    # at all, so this is the one place a version's own section can also
    # carry the current-state ring.
    assert current_state_colour["cleanOnTop"]["verNow"] is True


def test_a_tagged_clean_front_is_the_right_now_element_itself(
    current_state_colour,
):
    # No second, bodyless element above an otherwise ordinary section:
    # a version that is both the newest thing recorded and what the
    # dashboard holds right now carries the "Right now" heading and a
    # date on its own head, exactly the way the simple mode's merged
    # block draws it - and says neither "current state" nor "same
    # state as now" there, since the heading already says it once.
    assert current_state_colour["cleanOnTop"]["rightNowHeading"] is True
    assert current_state_colour["cleanOnTop"]["date"] is True
    assert current_state_colour["cleanOnTop"]["noBanner"] is True
    assert current_state_colour["cleanOnTop"]["noCountTextAtAll"] is True


def test_the_ring_follows_the_content_not_the_position_in_the_list(
    current_state_colour,
):
    # Standing on an older version's state rings the current-state box
    # blue - the same fact case 2 above marks on a version section
    # instead - and leaves that older version's own section unmarked,
    # since it is not the newest change.
    assert current_state_colour["cleanOnOlder"]["named"] is True
    assert current_state_colour["cleanOnOlder"]["verNow"] is False


# -- the advanced mode's own "right now" box, folded like a version's own --

_ADVANCED_NOW_BOX = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._mode = "advanced";

// The dashboard has changed at Home Assistant's back since the last
// recorded change, and nothing recorded holds what it holds now. The
// box has to appear here too, not only when the state happens to be
// clean - that is the whole point of aligning it with the simple mode.
el._changes = [
  { revision: "a", message: "1 card added", versions: [], same_as_now: false, timestamp: 2 },
  { revision: "b", message: "2 cards moved", versions: [{ name: "dash/v1.0.0" }],
    same_as_now: false, timestamp: 1 },
];
el._versions = [
  { name: "dash/v1.0.0", title: "First", same_as_now: false, revision: "b" },
];
el._matching = [];
const drifted = el._renderMain();

// The rarer shape of the same fact: the newest change is already
// tagged, so there is no unversioned span left to fold a box around -
// and yet the dashboard has drifted since that tag was made. Nothing
// crowned, and nothing to fold behind the sentence either.
el._changes = [
  { revision: "a", message: "1 card added", versions: [{ name: "dash/v1.0.0" }],
    same_as_now: false, timestamp: 1 },
];
el._versions = [
  { name: "dash/v1.0.0", title: "First", same_as_now: false, revision: "a" },
];
el._matching = [];
const behindTag = el._renderMain();

// The front is drifted (nothing recorded is provably current) *and*
// an older version happens to hold the exact same content anyway -
// the either/or a named match always wins, the same choice the simple
// mode's own box makes.
el._changes = [
  { revision: "a", message: "1 card added", versions: [], same_as_now: false, timestamp: 2 },
  { revision: "b", message: "2 cards moved", versions: [{ name: "dash/v1.0.0" }],
    same_as_now: false, timestamp: 1 },
];
el._versions = [
  { name: "dash/v1.0.0", title: "First", same_as_now: false, revision: "b" },
];
el._matching = [{ name: "dash/v1.0.0" }];
const matched = el._renderMain();

// The crowned newest change, unversioned, sits inside the box - point
// 2: no second "current state" chip on the row itself, and indented
// with the version-style left rule rather than the lighter one.
el._changes = [
  { revision: "a", message: "1 card added", versions: [], same_as_now: true, timestamp: 2 },
  { revision: "b", message: "2 cards moved", versions: [{ name: "dash/v1.0.0" }],
    same_as_now: false, timestamp: 1 },
];
el._versions = [
  { name: "dash/v1.0.0", title: "First", same_as_now: false, revision: "b" },
];
el._matching = [];
const cleanBox = el._renderMain();

console.log(JSON.stringify({
  drifted: {
    folds: drifted.includes('<details class="now-panel" data-key="now"'),
    sentence: drifted.includes("The dashboard has changed since v1.0.0"),
    noDivider: !drifted.includes('class="divider"'),
    row: drifted.includes("1 card added"),
    // Section "a" alone: "b" already carries a mark, so sections()
    // starts a new section there and "a" is the only unversioned row.
    count: drifted.includes('<span class="count">1 change</span>'),
    // The two buttons the simple mode's own box offers wherever
    // nothing recorded matches - reused rather than redrawn.
    saveButton: drifted.includes('data-version="now"'),
    undoButton: drifted.includes('data-state="dash/v1.0.0"')
      && drifted.includes("Undo / Go back to v1.0.0"),
  },
  behindTag: {
    div: behindTag.includes('class="now-panel now-head"'),
    sentence: behindTag.includes("The dashboard has changed since v1.0.0"),
    verNow: behindTag.includes('class="ver now"'),
    saveButton: behindTag.includes('data-version="now"'),
  },
  // The either/or the simple mode's own box already draws: a named
  // match wins outright, and there is nothing left to explain about a
  // drift once the dashboard's content is already accounted for
  // somewhere recorded.
  matched: {
    noDrift: !matched.includes("has changed since"),
    matches: matched.includes("the same state as") && matched.includes('title="v1.0.0"'),
    // No way back is offered onto a state already known to be held
    // somewhere - the same rule a version's own row follows.
    noSaveButton: !matched.includes('data-version="now"'),
    noUndoButton: !matched.includes("Undo / Go back to"),
  },
  cleanBox: {
    innerClass: cleanBox.includes('<div class="now-inner">'),
    noVbody: cleanBox.includes('class="vbody"'),
    // Only one "current state" on the whole page: the heading's own
    // badge. The row inside must not carry a second one.
    chipCount: (cleanBox.match(/class="chip now/g) || []).length,
    // The ring belongs to .now-head; .now-inner (and the cards inside
    // it) must never carry the panel's own class, or the ring would
    // reach into the rows through it.
    innerNotPanel: !cleanBox.includes('class="now-inner now-panel"')
      && !cleanBox.includes('class="now-panel now-inner"'),
  },
}));
"""


@pytest.fixture(scope="session")
def advanced_now_box(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "advanced_now_box", _ADVANCED_NOW_BOX)


def test_the_advanced_mode_gets_its_own_right_now_box_when_drifted(advanced_now_box):
    assert advanced_now_box["drifted"]["folds"] is True
    # Named by the version it drifted from, not a generic "the last
    # version" - and with no separate "Since vX" label needed once the
    # sentence already names it.
    assert advanced_now_box["drifted"]["sentence"] is True
    assert advanced_now_box["drifted"]["noDivider"] is True
    assert advanced_now_box["drifted"]["row"] is True
    assert advanced_now_box["drifted"]["count"] is True


def test_the_drifted_box_offers_the_simple_modes_own_two_buttons(advanced_now_box):
    # Switching modes mid-task should find the same way out in both.
    assert advanced_now_box["drifted"]["saveButton"] is True
    assert advanced_now_box["drifted"]["undoButton"] is True


def test_a_tagged_but_drifted_newest_change_still_says_so(advanced_now_box):
    # Nothing in `cut` can carry this fact - the tag already owns the
    # newest change - so it has to be said outside the section loop,
    # with no rows behind it to fold.
    assert advanced_now_box["behindTag"]["div"] is True
    assert advanced_now_box["behindTag"]["sentence"] is True
    assert advanced_now_box["behindTag"]["verNow"] is False
    assert advanced_now_box["behindTag"]["saveButton"] is True


def test_a_named_match_wins_over_the_drift_sentence(advanced_now_box):
    # Either/or, the same choice the simple mode's own box makes: a
    # named match already accounts for the content, so there is
    # nothing left to explain about drifting, and nowhere left to
    # offer a way back to.
    assert advanced_now_box["matched"]["noDrift"] is True
    assert advanced_now_box["matched"]["matches"] is True
    assert advanced_now_box["matched"]["noSaveButton"] is True
    assert advanced_now_box["matched"]["noUndoButton"] is True


def test_the_boxed_row_carries_no_second_current_state_chip(advanced_now_box):
    # The heading's own badge already says it; a chip on the row inside
    # would say the same fact a second time, a few pixels below it.
    assert advanced_now_box["cleanBox"]["chipCount"] == 1


def test_the_boxed_rows_are_indented_like_a_versions_own(advanced_now_box):
    assert advanced_now_box["cleanBox"]["innerClass"] is True
    assert advanced_now_box["cleanBox"]["noVbody"] is False


# -- each row gets the brand icon's own node-on-a-strand connector ----------

_ROW_CONNECTOR = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._mode = "advanced";

// A row folded under a version's own bar.
el._changes = [
  { revision: "a", message: "1 card added", versions: [{ name: "dash/v1.0.0" }],
    same_as_now: true, timestamp: 1 },
];
el._versions = [
  { name: "dash/v1.0.0", title: "First", same_as_now: true, revision: "a" },
];
el._matching = [];
const inVersion = el._renderMain();

// A row folded under the unversioned "right now" box's own bar.
el._changes = [
  { revision: "a", message: "1 card added", versions: [], same_as_now: false, timestamp: 2 },
  { revision: "b", message: "2 cards moved", versions: [{ name: "dash/v1.0.0" }],
    same_as_now: false, timestamp: 1 },
];
el._versions = [
  { name: "dash/v1.0.0", title: "First", same_as_now: false, revision: "b" },
];
el._matching = [];
const inNowBox = el._renderMain();

// The flat search list has no bar to draw a node against.
el._query = "card added";
const flat = el._renderMain();

console.log(JSON.stringify({
  inVersion: inVersion.includes('<div class="entry">\\n      <div class="card">'),
  inNowBox: inNowBox.includes('<div class="entry">\\n      <div class="card">'),
  flatHasNoEntry: !flat.includes('class="entry"'),
  flatStillHasCard: flat.includes('class="card"'),
}));
"""


@pytest.fixture(scope="session")
def row_connector(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "row_connector", _ROW_CONNECTOR)


def test_a_row_under_a_versions_bar_gets_the_icons_own_connector(row_connector):
    assert row_connector["inVersion"] is True


def test_a_row_in_the_unversioned_right_now_box_gets_it_too(row_connector):
    assert row_connector["inNowBox"] is True


def test_the_flat_search_list_draws_no_node_on_nothing(row_connector):
    assert row_connector["flatHasNoEntry"] is True
    assert row_connector["flatStillHasCard"] is True


# -- the right-now element stays silent while _select's fetch is out -------

_NOW_WHILE_LOADING = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._mode = "advanced";

// The exact shape _select leaves behind for the one render _guard
// draws before its fetch answers: _versions/_matching already
// cleared, _changes still the previous dashboard's rows. Without the
// flag this reads as "nothing has ever been recorded here".
el._changes = [
  { revision: "a", message: "1 card added", versions: [], same_as_now: true, timestamp: 2 },
];
el._versions = [];
el._matching = [];
el._versionsLoaded = false;
const loading = el._renderMain();

// The same shape, moments later, once the fetch has answered.
el._versions = [
  { name: "dash/v1.0.0", title: "First", same_as_now: false, revision: "z" },
];
el._versionsLoaded = true;
const loaded = el._renderMain();

console.log(JSON.stringify({
  loading: {
    // No chip, no sentence, no buttons - none of them could answer
    // honestly yet - but the box and its row count still show, since
    // those come from `_changes` alone and are not stale.
    noChip: !loading.includes('class="chip now'),
    noSentence: !loading.includes("has changed since"),
    noButtons: !loading.includes('data-version="now"'),
    heading: loading.includes('<p class="heading">Right now'),
    count: loading.includes('<span class="count">1 change</span>'),
    row: loading.includes("1 card added"),
    unnamed: !loading.includes('class="now-panel named"'),
    // The ring itself, not only the chip and sentence: without this
    // class the CSS ring still defaults to orange even with an empty
    // badge, which is the same wrong answer worn silently instead of
    // out loud.
    loadingClass: loading.includes('class="now-panel loading"'),
  },
  loaded: {
    sentence: loaded.includes("The dashboard has changed since v1.0.0"),
    buttons: loaded.includes('data-version="now"'),
    noLoadingClass: !loaded.includes("loading"),
  },
}));
"""


@pytest.fixture(scope="session")
def now_while_loading(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "now_while_loading", _NOW_WHILE_LOADING)


def test_the_right_now_element_says_nothing_while_versions_are_still_loading(
    now_while_loading,
):
    assert now_while_loading["loading"]["noChip"] is True
    assert now_while_loading["loading"]["noSentence"] is True
    assert now_while_loading["loading"]["noButtons"] is True
    assert now_while_loading["loading"]["heading"] is True
    assert now_while_loading["loading"]["count"] is True
    assert now_while_loading["loading"]["row"] is True
    assert now_while_loading["loading"]["unnamed"] is True
    assert now_while_loading["loading"]["loadingClass"] is True


def test_the_right_now_element_speaks_again_once_versions_have_loaded(
    now_while_loading,
):
    assert now_while_loading["loaded"]["sentence"] is True
    assert now_while_loading["loaded"]["buttons"] is True
    assert now_while_loading["loaded"]["noLoadingClass"] is True


# -- the compare toggle sits beside the search field, not below it ---------

_SEARCH_ROW = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._dashboards = [{ key: "dash", title: "Dash", exists: true }];
el._changes = [{ revision: "a", message: "1 card added", versions: [] }];
el._versions = [];

el._mode = "advanced";
const advancedSearch = el._renderSearch();

el._mode = "simple";
const simpleSearch = el._renderSearch();

console.log(JSON.stringify({
  // The button is part of the search row's own markup now, not a
  // second row `_renderMain` used to add beneath it - which is what
  // put the two modes' first elements at different heights on screen.
  toggleInAdvancedSearch: advancedSearch.includes("data-compare-toggle"),
  toggleInSimpleSearch: simpleSearch.includes("data-compare-toggle"),
  noSeparateBar: el._renderMain().includes('class="compare-bar"'),
}));
"""


@pytest.fixture(scope="session")
def search_row(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "search_row", _SEARCH_ROW)


def test_the_compare_toggle_moved_into_the_search_row(search_row):
    assert search_row["toggleInAdvancedSearch"] is True
    assert search_row["noSeparateBar"] is False


def test_the_simple_mode_never_offers_compare_mode(search_row):
    # Compare mode is an advanced-only capability - the simple mode's
    # search row stays exactly as wide as before, with nothing new to
    # make room for.
    assert search_row["toggleInSimpleSearch"] is False


# -- writing from a search result keeps the search --------------------------

_WRITE_KEEPS_SEARCH = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._mode = "advanced";
el._changes = [{ revision: "a", message: "1 card added", versions: [] }];
// A hit four hundred entries below the loaded window, which is the
// ordinary case: anything nearer would have been found without asking.
el._query = "winter";
el._found = [
  { revision: "deep", message: "winter rework", description: "", versions: [] },
];
el.shadowRoot = node();

const sent = [];
const held = [];
el._call = (type, extra) => {
  sent.push(type);
  return new Promise((resolve) => held.push({ type, extra, resolve }));
};
const reply = (type, value) => {
  const at = held.findIndex((c) => c.type === type);
  if (at >= 0) held.splice(at, 1)[0].resolve(value);
};

const box = el.shadowRoot.querySelector("dialog.describe");
const field = box.querySelector("input.text");
field.focus = () => {};
field.select = () => {};

const describing = el._describe("deep");
await settle();
field.value = "the winter rework";
box.close("save");
await settle();
reply("describe", { ok: true });
await settle();

// The reload the flow ends on.
reply("dashboards", { dashboards: [{ key: "dash", exists: true }] });
await settle();
reply("history", {
  changes: [{ revision: "a", message: "1 card added", versions: [] }],
  next_cursor: null,
});
reply("versions", { versions: [] });
await settle();
reply("search", {
  changes: [
    { revision: "deep", message: "winter rework",
      description: "the winter rework", versions: [] },
  ],
  more: false,
});
await describing;

const describeSent = sent.slice();
const afterDescribe = {
  query: el._query,
  shown: el._shown() && el._shown().map((c) => c.revision),
  described: (el._found || []).map((c) => c.description),
};

// The reload at the end of a flow, three times over. `_describe` was
// the only one measured; `_confirm` and `_createVersion` end the same
// way and end it on the same reasoning, so they are put through the
// same run rather than trusted.
const reload = async () => {
  reply("dashboards", { dashboards: [{ key: "dash", exists: true }] });
  await settle();
  reply("history", {
    changes: [{ revision: "a", message: "1 card added", versions: [] }],
    next_cursor: null,
  });
  reply("versions", { versions: [] });
  await settle();
  reply("search", {
    changes: [
      { revision: "deep", message: "winter rework",
        description: "the winter rework", versions: [] },
    ],
    more: false,
  });
  await settle();
};

// The state somebody found is put back, from the search result itself.
el._recorded = () => Promise.resolve();
sent.length = 0;
const confirmBox = el.shadowRoot.querySelector("dialog.confirm");
const restoring = el._restoreState("deep", "Back to this state");
await settle();
reply("restore_state", {
  applied: false,
  preview: "-a\\n+b",
  explanation: { groups: [], note: "one card removed" },
});
await settle();
confirmBox.close("apply");
await settle();
reply("restore_state", { applied: true });
await settle();
await reload();
await restoring;
const afterRestore = {
  wrote: sent.filter((t) => t === "restore_state").length,
  query: el._query,
  shown: el._shown() && el._shown().map((c) => c.revision),
};

// And a version made on the same found row.
sent.length = 0;
const versionBox = el.shadowRoot.querySelector("dialog.version");
const versioning = el._createVersion("deep");
await settle();
reply("next_versions", {
  candidates: { current: "dash/v1.0.0", patch: "dash/v1.0.1",
                minor: "dash/v1.1.0", major: "dash/v2.0.0" },
});
await settle();
versionBox.close("create");
await settle();
reply("create_version", { created: "dash/v1.0.1" });
await settle();
await reload();
await versioning;
const afterVersion = {
  made: sent.filter((t) => t === "create_version").length,
  query: el._query,
  shown: el._shown() && el._shown().map((c) => c.revision),
};

console.log(JSON.stringify({
  sent: describeSent,
  query: afterDescribe.query,
  shown: afterDescribe.shown,
  described: afterDescribe.described,
  afterRestore,
  afterVersion,
}));
"""


@pytest.fixture(scope="session")
def write_keeps_search(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "write_keeps_search", _WRITE_KEEPS_SEARCH)


def test_describing_a_found_row_leaves_the_search_standing(write_keeps_search):
    # These flows used to end on `_select`, which clears the query, the
    # results and the cursor - so writing on a row the server had found
    # dropped whoever wrote it onto the unfiltered first page with an
    # empty box, to type the search again for every further hit.
    assert write_keeps_search["query"] == "winter"
    assert write_keeps_search["shown"] == ["deep"]
    # And the reload asked again, so the row shows what was just written
    # on it rather than the answer from before.
    assert write_keeps_search["sent"] == [
        "describe", "dashboards", "history", "versions", "search",
    ]
    assert write_keeps_search["described"] == ["the winter rework"]


def test_a_restore_and_a_version_leave_the_search_standing(write_keeps_search):
    # The other two flows that end on a reload. All three were moved off
    # `_select` for the same reason and only `_describe` was measured -
    # so these two could be moved back with the whole suite staying
    # green, and the search would go on being thrown away by the two
    # actions that cost the most to reach.
    assert write_keeps_search["afterRestore"]["wrote"] == 2  # preview, write
    assert write_keeps_search["afterRestore"]["query"] == "winter"
    assert write_keeps_search["afterRestore"]["shown"] == ["deep"]
    assert write_keeps_search["afterVersion"]["made"] == 1
    assert write_keeps_search["afterVersion"]["query"] == "winter"
    assert write_keeps_search["afterVersion"]["shown"] == ["deep"]


# -- a reload that failed after a write is said out loud --------------------
#
# The flows used to end on `_select`, which runs through `_guard` and
# left a failure in the banner. Moved to a quiet refresh they swallowed
# it, and the line after cleared whatever else stood there: the write
# landed, the page went on showing the state from before it, and nothing
# said why.

_RELOAD_FAILS = """
const el = new Panel();
const drawn = [];
el._render = () => { drawn.push({ busy: el._busy, error: el._error }); };
el._selected = "dash";
el._mode = "advanced";
el._changes = [{ revision: "a", message: "1 card added", versions: [] }];
el.shadowRoot = node();
el._recorded = () => Promise.resolve();

// Everything answers except the first call of the reload.
let busyWhileReloading = null;
el._call = (type, extra) => {
  if (type === "dashboards") {
    busyWhileReloading = el._busy;
    return Promise.reject(new Error("connection lost"));
  }
  if (type === "restore_state")
    return Promise.resolve(
      extra.confirm
        ? { applied: true }
        : { applied: false, preview: "-a\\n+b",
            explanation: { groups: [], note: "one card removed" } },
    );
  if (type === "next_versions")
    return Promise.resolve({ candidates: { patch: "dash/v1.0.1" } });
  if (type === "create_version")
    return Promise.resolve({ created: "dash/v1.0.1" });
  return Promise.resolve({});
};

const confirmBox = el.shadowRoot.querySelector("dialog.confirm");
const restoring = el._restoreState("a", "Back to this state");
await settle();
confirmBox.close("apply");
await restoring;
const afterRestore = { error: el._error, busy: el._busy };
const lastFrame = drawn[drawn.length - 1];

const describeBox = el.shadowRoot.querySelector("dialog.describe");
const describing = el._describe("a");
await settle();
describeBox.close("save");
await describing;
const afterDescribe = el._error;

const versionBox = el.shadowRoot.querySelector("dialog.version");
const versioning = el._createVersion("a");
await settle();
versionBox.close("create");
await versioning;
const afterVersion = el._error;

console.log(JSON.stringify({
  afterRestore, lastFrame, busyWhileReloading, afterDescribe, afterVersion,
}));
"""


@pytest.fixture(scope="session")
def reload_fails(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "reload_fails", _RELOAD_FAILS)


def test_a_reload_that_failed_after_a_write_says_so(reload_fails):
    # Both halves in one sentence: what did happen, and why the page
    # below does not show it. Swallowed, this is the worst outcome this
    # integration knows - a screen that is wrong and quiet about it,
    # with a reload button nothing tells you to press.
    assert reload_fails["afterRestore"]["error"] == (
        "the change was made, but the page could not be reloaded: "
        "connection lost"
    )
    # Every flow that writes, not just the one that was measured.
    assert reload_fails["afterDescribe"] == (
        "the description was saved, but the page could not be reloaded: "
        "connection lost"
    )
    assert reload_fails["afterVersion"] == (
        "the version was made, but the page could not be reloaded: "
        "connection lost"
    )


def test_the_reload_after_a_write_says_it_is_working(reload_fails):
    # `_refresh` draws no "working..." of its own, so the window between
    # Apply and a reloaded page was silent as well as still. And the
    # indicator has to come down again: the last thing drawn is the
    # banner, and it must not be drawn under a spinner that has nothing
    # left to do.
    assert reload_fails["busyWhileReloading"] == 1
    assert reload_fails["afterRestore"]["busy"] == 0
    assert reload_fails["lastFrame"]["busy"] == 0


# -- the caret belongs to the person, not to the render ---------------------
#
# `_render` replaces the search box along with everything else, so a
# keystroke needs its focus put back. It used to be put back on *every*
# render that found a word in the box, which is a different thing: a
# click in the list, or a save announced from elsewhere, pulled the
# caret out of wherever it was and dropped it at the end of the query.
#
# The real `_render` runs here, against a root that answers `dialog[open]`
# honestly - the stand-in otherwise hands out a node for every selector,
# and `_render` would hold every frame back for a dialog nobody opened.

_CARET = """
const rootFor = () => {
  const it = node();
  const base = it.querySelector.bind(it);
  it.querySelector = (selector) =>
    selector === "dialog[open]" ? null : base(selector);
  return it;
};

const el = new Panel();
el.shadowRoot = rootFor();
el._selected = "dash";
el._mode = "advanced";
el._dashboards = [{ key: "dash", title: "Dash", exists: true }];
el._changes = [
  { revision: "a", message: "1 card added", timestamp: 1, versions: [] },
];
let searched = 0;
el._search = async () => { searched += 1; };

// The first paint, so that the box exists to be patched.
el._render();
const find = el.shadowRoot.querySelector("input.find");
let focused = 0;
let caret = null;
find.focus = () => { focused += 1; };
find.setSelectionRange = (at) => { caret = at; };

// 1. Two renders nobody typed for, with a word standing in the box.
// Opening a row does exactly this: `_guard` draws on the way in and on
// the way out.
el._query = "winter";
find.value = "winter";
el._render();
el._render();
const afterPlainRenders = { focused, caret };

// 2. Somebody types, in the middle of the word. The box has the focus,
// so the browser fired one, and the caret sits where they are working.
find._on.focus();
find.selectionStart = 3;
find._on.input();
el._render();
const afterTyping = { focused, caret };

// 3. ...and clicks into the list. A render must leave the caret there.
find._on.blur();
el._render();
const afterLeavingTheBox = { focused, caret };

// 4. A keystroke, and then the panel is left. The 400 ms walk over the
// whole history must not run for a page nobody is on.
find._on.focus();
find._on.input();
el.disconnectedCallback();
await new Promise((r) => setTimeout(r, 450));
const searchesAfterLeaving = searched;

// The control: the same keystroke on a panel nobody leaves.
find._on.input();
await new Promise((r) => setTimeout(r, 450));
const searchesAfterWaiting = searched;

console.log(JSON.stringify({
  afterPlainRenders, afterTyping, afterLeavingTheBox,
  searchesAfterLeaving, searchesAfterWaiting,
}));
"""


@pytest.fixture(scope="session")
def caret(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "caret", _CARET)


def test_a_render_alone_does_not_take_the_caret_into_the_search_box(caret):
    # The finding: `if (this._query) find.focus()` ran on every render.
    # Expanding a row renders twice, so a click in the list ended with
    # the caret in the search box.
    assert caret["afterPlainRenders"]["focused"] == 0
    assert caret["afterPlainRenders"]["caret"] is None


def test_the_caret_comes_back_where_the_typing_left_it(caret):
    # Typing still keeps its caret - that is what the focus call is for -
    # and it comes back to the position it was at, not to the end of the
    # line. Correcting a word in the middle is the case that hurt: an
    # event arriving mid-edit jumped the caret to the end.
    assert caret["afterTyping"]["focused"] == 1
    assert caret["afterTyping"]["caret"] == 3


def test_a_render_after_clicking_away_leaves_the_caret_where_it_went(caret):
    # Focus is a fact about the page. Once it has left the box, no
    # render may fetch it back.
    assert caret["afterLeavingTheBox"]["focused"] == 1


def test_leaving_the_panel_cancels_the_keystroke_still_in_flight(caret):
    # Half a second per thousand commits, for a page nobody is on, to
    # write its answer into an element off the screen. The control below
    # is what makes the zero mean something.
    assert caret["searchesAfterLeaving"] == 0
    assert caret["searchesAfterWaiting"] == 1


# -- what a row says about being taken back --------------------------------
#
# A detail that never arrived says so, rather than reporting a refusal
# the panel cannot know about.

_TAKING_BACK = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._changes = [{ revision: "a", previous: "b" }];
el._explanation = { groups: [{ entries: [
  { kind: "removed", label: "Weather" },
  { kind: "removed", label: "Clock" },
] }] };
el._undo = { available: true, equals_state_before: false };

const row = (adds, message) =>
  el._renderDetail({ revision: "a", previous: "b", adds, message });
// Sentences in this file are written across several lines, indented to
// sit in their template. A test that searched for one as it stands
// would go red the next time somebody reflows a paragraph - a cosmetic
// edit failing a case about meaning.
const flat = (html) => html.replace(/\\s+/g, " ");

// The undo the server said yes to. The control for the two sentences
// below: without it, "does not claim a refusal" would also be true of a
// row that offered nothing at all.
const available = row(false, "2 cards removed");

// The server said no, and why.
el._undo = { available: false, reason: "the state before it is not recorded" };
const refused = row(false, "2 cards removed");
// Nothing was said at all: the request for the detail failed, or it is
// still out.
el._undo = null;
const unknown = row(false, "2 cards removed");

console.log(JSON.stringify({
  available: {
    offers: available.includes("data-undo="),
    saysNothingCannot: !flat(available).includes("cannot be taken back"),
  },
  refused: {
    said: flat(refused).includes("This change cannot be taken back exactly"),
    why: flat(refused).includes("the state before it is not recorded"),
  },
  unknown: {
    claimsRefusal: flat(unknown).includes("cannot be taken back exactly"),
    saysSo: flat(unknown).includes(
      "Whether this change can be taken back is not known"),
    blames: flat(unknown).includes("no reason given"),
  },
}));
"""


@pytest.fixture(scope="session")
def taking_back(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "taking_back", _TAKING_BACK)


def test_an_undo_the_server_allows_is_offered_as_a_button(taking_back):
    # The control that makes the two cases below mean something: a row
    # that rendered nothing at all would also fail to claim a refusal.
    assert taking_back["available"]["offers"] is True
    assert taking_back["available"]["saysNothingCannot"] is True


def test_a_refusal_the_server_explained_is_passed_on_as_it_stands(taking_back):
    # The other control: where there *is* an answer and it is a no, the
    # row still says so, and says why.
    assert taking_back["refused"]["said"] is True
    assert taking_back["refused"]["why"] is True


def test_a_detail_that_never_arrived_is_not_reported_as_a_refusal(taking_back):
    # With `_undo` null the row used to read "This change cannot be
    # taken back exactly: no reason given" - a statement about the
    # history, made out of a failure to reach the server. The banner
    # above carries the real cause.
    assert taking_back["unknown"]["claimsRefusal"] is False
    assert taking_back["unknown"]["blames"] is False
    assert taking_back["unknown"]["saysSo"] is True


# -- progressive expansion and in-card loading states -----------------------

_PROGRESSIVE_EXPAND = """
const el = new Panel();
const rendered = [];
el._render = () => {
  rendered.push({
    open: el._open,
    detailLoading: el._loadingDetail,
    undoLoading: el._loadingUndo,
    explanation: el._explanation ? Boolean(el._explanation) : false,
    undo: el._undo ? el._undo.available : null,
    html: el._open ? el._renderDetail(el._changeAt(el._open)) : "",
  });
};
el._selected = "dash";
el._changes = [
  { revision: "rev1", previous: "rev0", message: "edited card", adds: false },
];

const calls = {};
let undoExtra = null;
el._call = (type, extra) => new Promise((resolve) => {
  calls[type] = resolve;
  if (type === "undo_change") undoExtra = extra;
});

// Start expand
const expandPromise = el._expand("rev1");
await settle();
const frame0 = rendered[rendered.length - 1];

// Fast phase: resolve explain
calls["explain"]({
  groups: [],
  note: "",
  diff: "--- before/dash\\n+++ after/dash\\n@@ -1 +1 @@\\n-old\\n+new\\n",
});
await settle();
const frame1 = rendered[rendered.length - 1];

// User toggles the diff open while undo is still computing
el._diffOpen = true;

// Slow phase: resolve undo_change
calls["undo_change"]({ available: true });
await expandPromise;
await settle();
const frame2 = rendered[rendered.length - 1];

console.log(JSON.stringify({ frame0, frame1, frame2, undoExtra }));
"""


@pytest.fixture(scope="session")
def progressive_expand(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "progressive_expand", _PROGRESSIVE_EXPAND)


def test_expand_shows_incard_loader_without_error_message(progressive_expand):
    frame0 = progressive_expand["frame0"]
    assert frame0["detailLoading"] == "rev1"
    assert "Loading change details" in frame0["html"]
    assert "Whether this change can be taken back is not known" not in frame0["html"]


def test_expand_renders_explanation_while_undo_is_loading(progressive_expand):
    frame1 = progressive_expand["frame1"]
    assert frame1["detailLoading"] is None
    assert frame1["undoLoading"] == "rev1"
    assert "Checking whether this change can be undone" in frame1["html"]
    assert "Whether this change can be taken back is not known" not in frame1["html"]
    assert "data-undo=" not in frame1["html"]


def test_expand_renders_collapsible_technical_diff(progressive_expand):
    frame1 = progressive_expand["frame1"]
    assert 'details class="raw"' in frame1["html"]
    assert "Technical details" in frame1["html"]
    assert '<span class="del">-old</span>' in frame1["html"]
    assert '<span class="add">+new</span>' in frame1["html"]


def test_expand_preserves_diff_open_state_when_undo_resolves(progressive_expand):
    frame2 = progressive_expand["frame2"]
    assert 'details class="raw" open' in frame2["html"]
    assert "Technical details" in frame2["html"]


def test_expand_renders_undo_button_when_undo_resolves(progressive_expand):
    frame2 = progressive_expand["frame2"]
    assert frame2["detailLoading"] is None
    assert frame2["undoLoading"] is None
    assert 'data-undo="rev1"' in frame2["html"]
    assert "Undo this change" in frame2["html"]
    assert "Checking whether this change can be undone" not in frame2["html"]


def test_a_row_opening_does_not_ask_for_a_preview(progressive_expand):
    # The row reads only `available`, `reason` and `equals_state_before`
    # from this answer - `preview` left at its server-side default of
    # false keeps the two YAML dumps for the dialog that may show them,
    # not for every row opened. See operations.py's `async_undo_change`
    # and the companion assertion in the confirm-dialog flow above.
    assert progressive_expand["undoExtra"].get("preview") is not True


# -- the oldest change asks for nothing it cannot show ---------------------

_FIRST_RECORDED_EXPAND = """
const el = new Panel();
const rendered = [];
el._render = () => {
  rendered.push({
    detailLoading: el._loadingDetail,
    undoLoading: el._loadingUndo,
    html: el._open ? el._renderDetail(el._changeAt(el._open)) : "",
  });
};
el._selected = "dash";
// A dashboard's oldest recorded change. store.py answers `previous`
// None for exactly one entry - "the last entry of the walk has nobody
// behind it" - and `_renderDetail` returns before the undo section for
// it, so neither `deleted_since` nor `undo_change` has anywhere to go.
el._changes = [
  { revision: "rev1", previous: null, message: "edited card", adds: false },
];

const asked = [];
const calls = {};
el._call = (type, extra) => new Promise((resolve) => {
  asked.push(type);
  calls[type] = resolve;
});

const expanding = el._expand("rev1");
await settle();

calls["explain"]({ heading: "What this change did", groups: [] });
await expanding;
await settle();
const done = rendered[rendered.length - 1];

console.log(JSON.stringify({ asked, done, undo: el._undo }));
"""


@pytest.fixture(scope="session")
def first_recorded_expand(tmp_path_factory):
    return _run_in_node(
        tmp_path_factory, "first_recorded_expand", _FIRST_RECORDED_EXPAND
    )


def test_the_oldest_change_says_there_is_nothing_before_it(first_recorded_expand):
    done = first_recorded_expand["done"]
    assert "This is the first" in done["html"]
    assert done["detailLoading"] is None
    assert done["undoLoading"] is None
    # Never the undo offer, and never the notice that stands in for a
    # missing answer: there is no answer owed here.
    assert "Undo this change" not in done["html"]
    assert "Whether this change can be taken back is not known" not in done["html"]
    assert first_recorded_expand["undo"] is None


# -- undo failure must not wipe out already loaded explanation --------------

_EXPAND_UNDO_FAILURE = """
const el = new Panel();
const rendered = [];
el._render = () => {
  rendered.push({
    open: el._open,
    detailLoading: el._loadingDetail,
    undoLoading: el._loadingUndo,
    error: el._error,
    html: el._open ? el._renderDetail(el._changeAt(el._open)) : "",
  });
};
el._selected = "dash";
el._changes = [
  { revision: "rev1", previous: "rev0", message: "edited card", adds: false },
];

const calls = {};
el._call = (type, extra) => new Promise((resolve, reject) => {
  calls[type] = { resolve, reject };
});

const expandPromise = el._expand("rev1");
await settle();

// Fast phase succeeds
calls["explain"].resolve({
  groups: [],
  note: "",
  diff: "--- before/dash\\n+++ after/dash\\n@@ -1 +1 @@\\n-old\\n+new\\n",
});
await settle();

// Slow phase fails / rejects
calls["undo_change"].reject(new Error("WebSocket timeout"));
await expandPromise;
await settle();
const frameAfterError = rendered[rendered.length - 1];

console.log(JSON.stringify({
  frameAfterError,
  error: el._error,
  errorWasRenderedWith: rendered.map((f) => f.error).filter(Boolean).length,
}));
"""


@pytest.fixture(scope="session")
def expand_undo_failure(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "expand_undo_failure", _EXPAND_UNDO_FAILURE)


def test_undo_failure_preserves_explanation_and_clears_loading_undo(expand_undo_failure):
    frame = expand_undo_failure["frameAfterError"]
    assert frame["detailLoading"] is None
    assert frame["undoLoading"] is None
    assert "Technical details" in frame["html"]
    flat_html = " ".join(frame["html"].split())
    assert "Whether this change can be taken back is not known" in flat_html


def test_undo_failure_leaves_a_message_the_row_can_point_at(expand_undo_failure):
    # The row's fallback says "the answer did not arrive. Any message
    # above says why". That sentence is a promise about the banner, and
    # for a while it was not kept: isolating the undo failure from the
    # explanation swallowed the rejection, so the row sent the reader
    # to a message that was never written.
    frame = expand_undo_failure["frameAfterError"]
    flat_html = " ".join(frame["html"].split())
    assert "Any message above says" in flat_html
    assert expand_undo_failure["error"] == "WebSocket timeout"


# -- what the detail cache is allowed to remember --------------------------

_CACHE_LIMITS = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._changes = [
  { revision: "rev1", previous: "rev0", message: "edited card", adds: false },
];

const asked = [];
let held = {};
el._call = (type) => new Promise((resolve, reject) => {
  asked.push(type);
  held[type] = { resolve, reject };
});

// First expand: the explanation arrives, the undo does not.
const first = el._expand("rev1");
await settle();
held["explain"].resolve({ groups: [], note: "", diff: "-a\\n+b\\n" });
await settle();
held["undo_change"].reject(new Error("WebSocket timeout"));
await first;
await settle();
const cachedAfterFailure = el._detailCache.has("rev1");

// Collapse, then open it again and count what that costs.
await el._expand("rev1");
await settle();
const countBefore = asked.length;
held = {};
const again = el._expand("rev1");
await settle();
const askedOnReExpand = asked.length - countBefore;
held["explain"]?.resolve({ groups: [], note: "", diff: "" });
held["undo_change"]?.resolve({ available: true });
await again;
await settle();
const cachedOnceItAnswered = el._detailCache.has("rev1");

// A second panel, opening far more rows than the cache may hold.
const many = new Panel();
many._render = () => {};
many._selected = "dash";
many._changes = [];
for (let i = 0; i < 40; i++)
  many._changes.push({ revision: "r" + i, previous: "p" + i, message: "m", adds: false });
many._call = (type) =>
  Promise.resolve(
    type === "explain"
      ? { groups: [], note: "", diff: "x" }
      : { available: true },
  );
for (const change of many._changes) {
  await many._expand(change.revision);
  await settle();
}

console.log(JSON.stringify({
  cachedAfterFailure,
  askedOnReExpand,
  cachedOnceItAnswered,
  size: many._detailCache.size,
  keptNewest: many._detailCache.has("r39"),
  droppedOldest: !many._detailCache.has("r0"),
}));
"""


@pytest.fixture(scope="session")
def cache_limits(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "cache_limits", _CACHE_LIMITS)


def test_a_failed_undo_is_not_remembered_as_an_answer(cache_limits):
    # Storing it turned one dropped WebSocket call into a row that had
    # no undo until the whole history was reloaded: re-opening asked
    # nothing and repeated "the answer did not arrive", pointing at a
    # banner the next action had already cleared.
    assert cache_limits["cachedAfterFailure"] is False
    assert cache_limits["askedOnReExpand"] == 2
    assert cache_limits["cachedOnceItAnswered"] is True


def test_the_detail_cache_holds_a_page_and_no_more(cache_limits):
    # An entry carries the technical diff, which is as large as the
    # dashboard for a change that rewrites it.
    assert cache_limits["size"] == 25
    assert cache_limits["keptNewest"] is True
    assert cache_limits["droppedOldest"] is True


# -- detail cache: re-expanding the same row must not re-fetch ---------------

_DETAIL_CACHE = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._changes = [
  { revision: "rev1", previous: "rev0", message: "edited card", adds: false },
];

let callCount = 0;
el._call = (type, extra) => {
  callCount++;
  if (type === "explain") return Promise.resolve({ groups: [], note: "", diff: "diff" });
  if (type === "undo_change") return Promise.resolve({ available: true });
  return Promise.resolve({});
};

// First expand: must call the backend
await el._expand("rev1");
await settle();
const callsAfterFirst = callCount;
const cachedAfterFirst = el._detailCache.size;

// Collapse
await el._expand("rev1");
await settle();

// Re-expand the same row: should be instant from cache
callCount = 0;
await el._expand("rev1");
await settle();
const callsAfterReopen = callCount;
const hasExplanation = !!el._explanation;

console.log(JSON.stringify({
  callsAfterFirst,
  cachedAfterFirst,
  callsAfterReopen,
  hasExplanation,
}));
"""


@pytest.fixture(scope="session")
def detail_cache(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "detail_cache", _DETAIL_CACHE)


def test_first_expand_fetches_from_backend(detail_cache):
    assert detail_cache["callsAfterFirst"] == 2


def test_first_expand_populates_cache(detail_cache):
    assert detail_cache["cachedAfterFirst"] == 1


def test_reexpand_uses_cache_without_network_calls(detail_cache):
    assert detail_cache["callsAfterReopen"] == 0
    assert detail_cache["hasExplanation"] is True


# -- a level the server left out must not take the flow with it ------------

_MISSING_LEVEL = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._changes = [{ revision: "a" }];
el.shadowRoot = node();
el._reloadAfterWrite = async () => null;

const sent = [];
el._call = (type, extra) => {
  sent.push({ type, extra });
  // Patch, minor and major are all missing. Everywhere else in the
  // panel an answer is read with `?.` or `|| ""`; this one place split
  // the string it was handed.
  if (type === "next_versions")
    return Promise.resolve({ candidates: { current: "dash/v1.0.0" } });
  return Promise.resolve({ created: "dash/v1.0.1" });
};

let threw = null;
const making = el._createVersion("a").catch((err) => { threw = String(err); });
await settle();
const dialog = el.shadowRoot.querySelector("dialog.version");
const opened = dialog.open;
dialog.close("create");
await making;
const wrote = sent.filter((c) => c.type === "create_version");

console.log(JSON.stringify({
  threw,
  opened,
  wrote: wrote.length,
  title: wrote[0] ? wrote[0].extra.title : null,
}));
"""


@pytest.fixture(scope="session")
def missing_level(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "missing_level", _MISSING_LEVEL)


def test_a_version_offered_without_its_numbers_still_writes(missing_level):
    # The dialog is filled in and pressed before anything reads the
    # level's name, so a throw here loses the whole flow after the
    # person has done the work. An empty title is a thing the server
    # already accepts.
    assert missing_level["threw"] is None
    assert missing_level["opened"] is True
    assert missing_level["wrote"] == 1
    assert missing_level["title"] == ""


# -- today is the installation's day, not the browser's --------------------
#
# The restore dialog offers to keep the state it replaces and fills the
# title in with today's date. Computed in the browser that is the
# browser's today: near midnight, from a laptop in another time zone, a
# different day from the one this installation would have written - and
# two names for one day in a list that shows nothing but names is what
# the simple mode cannot survive.

_TODAY = """
const el = new Panel();
el._render = () => {};
el._mode = "simple";
el.shadowRoot = node();

const calls = [];
el._call = (type, extra) =>
  new Promise((resolve) => calls.push({ type, extra, resolve }));
const reply = (type, value) => {
  const at = calls.findIndex((c) => c.type === type);
  if (at >= 0) calls.splice(at, 1)[0].resolve(value);
};
const keepBlock = () => el.shadowRoot.querySelector("[data-keep]");
const dialog = el.shadowRoot.querySelector("dialog.confirm");

const first = el._select("dash");
await settle();
reply("versions", { versions: [] });
reply("history", {
  changes: [{ revision: "a" }],
  next_cursor: null,
  today: "1 January 2020",
});
await first;
const offered = el._armKeep(true, dialog).querySelector(".keeptitle").value;

// An emptied field falls back to the same string, not to the browser's.
keepBlock().querySelector(".keeptitle").value = "";
const cleared = el._keepChoice(keepBlock()).title;

// An answer without the field - an older integration behind a newer
// panel. The browser's own spelling is the fallback, and the string
// from the dashboard before must not be left standing.
const second = el._select("other");
await settle();
reply("versions", { versions: [] });
reply("history", { changes: [{ revision: "a" }], next_cursor: null });
await second;
const fallback = el._armKeep(true, dialog).querySelector(".keeptitle").value;

console.log(JSON.stringify({ offered, cleared, fallback }));
"""


@pytest.fixture(scope="session")
def day_title(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "today", _TODAY)


def test_the_offered_title_is_the_day_the_installation_is_having(day_title):
    # Spelled by `versions.day_title` on the machine Home Assistant runs
    # on, which is the same function the automatic daily versions use -
    # so a title somebody accepts unchanged reads like the ones already
    # in the list.
    assert day_title["offered"] == "1 January 2020"


def test_an_emptied_title_falls_back_to_the_same_day(day_title):
    # Two spellings of one day, one from the server and one from the
    # browser, would be exactly the confusion this closes.
    assert day_title["cleared"] == "1 January 2020"


def test_an_answer_without_the_day_falls_back_to_the_browser(day_title):
    # An older integration behind a newer panel. A date from the wrong
    # side of midnight still beats an empty title - and the day the
    # dashboard before it carried must not be left standing.
    assert day_title["fallback"] != "1 January 2020"
    assert re.fullmatch(r"\d{1,2} [A-Z][a-z]+ \d{4}", day_title["fallback"])


# -- a double click on "load older" asks once ------------------------------
#
# The claim ticket keeps the list right either way: the loser's page is
# dropped rather than stitched on twice. What it does not do is stop the
# request, and this is the button that invites the second press - it
# sits at the bottom of a list, nothing about it changes while it works,
# and the page it fetches is the slowest read the ordinary path makes.

_OLDER_TWICE = """
const el = new Panel();
el._render = () => {};
""" + _HELD + """
await openOn("dash", [{ revision: "a" }, { revision: "b" }], "b");

const first = el._loadOlder();
const second = el._loadOlder();
await settle();
const asked = calls.filter((c) => c.type === "history").length;
// Answered as many times as it was asked, so that a second request -
// the very thing being measured - cannot hang the run instead of
// failing the assertion.
while (calls.some((c) => c.type === "history"))
  reply("history", { changes: [{ revision: "c" }], next_cursor: "c" });
await first;
await second;
const rows = el._changes.map((c) => c.revision);

// The control: pressed again once the first page is in, it fetches.
const third = el._loadOlder();
await settle();
const askedAgain = calls.filter((c) => c.type === "history").length;
reply("history", { changes: [{ revision: "d" }], next_cursor: null });
await third;

console.log(JSON.stringify({
  asked, rows, askedAgain, then: el._changes.map((c) => c.revision),
}));
"""


@pytest.fixture(scope="session")
def older_twice(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "older_twice", _OLDER_TWICE)


def test_a_second_press_on_load_older_sends_nothing(older_twice):
    assert older_twice["asked"] == 1
    assert older_twice["rows"] == ["a", "b", "c"]


def test_the_button_works_again_once_the_page_is_in(older_twice):
    # The control, and the reason the flag is cleared in a `finally`: a
    # guard that stuck would leave the rest of the history unreachable
    # for as long as the page is open.
    assert older_twice["askedAgain"] == 1
    assert older_twice["then"] == ["a", "b", "c", "d"]


# A local hit ended the search, and "Load older" is gone while a query
# stands - so the rest of the history was out of reach for that word.
# The way on is offered rather than taken automatically: the common
# search still costs no round trip.

_WIDER = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._mode = "advanced";
el._cursor = "older";
el._changes = [
  { revision: "a", message: "1 card added", description: "", versions: [] },
  { revision: "b", message: "2 views removed", description: "the rework",
    versions: [] },
];
el._versions = [];

const asked = [];
el._call = (type) => {
  asked.push(type);
  return Promise.resolve({
    changes: [
      { revision: "b", message: "2 views removed" },
      { revision: "z", message: "an older rework" },
    ],
  });
};

// 1. A word that is in the loaded page still answers without the server.
await el._search("rework");
const local = {
  shown: el._shown().map((c) => c.revision),
  asked: [...asked],
  note: el._searchNote(),
  offered: el._offersWider(),
};

// 2. Somebody takes the offer.
await el._searchWider();
const wider = {
  shown: el._shown().map((c) => c.revision),
  asked: [...asked],
  note: el._searchNote(),
  offered: el._offersWider(),
};

// 3. A refresh runs `_search` again with the same word. What somebody
// asked for must survive it.
await el._search("rework");
const afterRefresh = {
  shown: el._shown().map((c) => c.revision),
  asked: [...asked],
};

// 4. A new word is a new question, and the cheap step answers it again.
await el._search("card");
const afterNewWord = { asked: [...asked], shown: el._shown().map((c) => c.revision) };

// 5. The simple mode has no second step to offer: it filters the whole
// version list already.
el._mode = "simple";
await el._search("rework");
const inSimple = el._offersWider();

console.log(JSON.stringify({ local, wider, afterRefresh, afterNewWord, inSimple }));
"""


@pytest.fixture(scope="session")
def wider(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "wider", _WIDER)


def test_a_local_hit_still_answers_without_the_server(wider):
    # Unchanged, and it must stay so: the common search costs nothing.
    assert wider["local"]["shown"] == ["b"]
    assert wider["local"]["asked"] == []


def test_the_note_offers_the_rest_of_the_history(wider):
    # The finding: the note said "1 of the 2 loaded entries" and stopped
    # there, while "Load older" is hidden for as long as a query stands.
    # True, and no way onwards from it.
    assert wider["local"]["offered"] is True
    assert "loaded entries" in wider["local"]["note"]


def test_taking_the_offer_asks_the_whole_history(wider):
    assert wider["wider"]["asked"] == ["search"]
    assert wider["wider"]["shown"] == ["b", "z"]
    assert wider["wider"]["offered"] is False
    assert "whole history" in wider["wider"]["note"]


def test_a_refresh_keeps_the_wider_answer(wider):
    # `_search` runs again on every recorded change of this dashboard.
    # Falling back to the loaded page there would take away what
    # somebody asked for, seconds after they asked.
    assert wider["afterRefresh"]["asked"] == ["search", "search"]
    assert wider["afterRefresh"]["shown"] == ["b", "z"]


def test_a_new_word_asks_the_cheap_question_again(wider):
    # The wider search belongs to the word it was asked about.
    assert wider["afterNewWord"]["asked"] == ["search", "search"]
    assert wider["afterNewWord"]["shown"] == ["a"]


def test_the_simple_mode_offers_no_second_step(wider):
    # It filters the complete version list; there is no window to fall
    # out of, so there is nothing to widen.
    assert wider["inSimple"] is False


# The 400 ms wait is right for typing and wrong for somebody who has
# finished. A single field with one thing to do should behave like a
# form, the way the description dialog already does.

_ENTER = """
const rootFor = () => {
  const it = node();
  const base = it.querySelector.bind(it);
  it.querySelector = (selector) =>
    selector === "dialog[open]" ? null : base(selector);
  return it;
};

const el = new Panel();
el.shadowRoot = rootFor();
el._selected = "dash";
el._mode = "advanced";
el._dashboards = [{ key: "dash", title: "Dash", exists: true }];
el._changes = [
  { revision: "a", message: "1 card added", timestamp: 1, versions: [] },
];
const searched = [];
el._search = async (text) => { searched.push(text); };

el._render();
const find = el.shadowRoot.querySelector("input.find");
find.value = "winter";

// 1. Typing alone waits the debounce out.
find._on.input();
const whileTyping = [...searched];

// 2. Enter does not wait.
let prevented = 0;
find._on.keydown({ key: "Enter", preventDefault: () => { prevented += 1; } });
const afterEnter = [...searched];

// 3. And the wait it skipped must not then fire a second search.
await new Promise((r) => setTimeout(r, 450));
const afterTheWait = [...searched];

// 4. Any other key is still just typing.
find._on.input();
find._on.keydown({ key: "r", preventDefault: () => {} });
const afterAnotherKey = [...searched];
await new Promise((r) => setTimeout(r, 450));
const andItsWait = [...searched];

console.log(JSON.stringify({
  whileTyping, afterEnter, afterTheWait, afterAnotherKey, andItsWait, prevented,
}));
"""


@pytest.fixture(scope="session")
def entering(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "enter", _ENTER)


def test_enter_searches_without_waiting_out_the_debounce(entering):
    assert entering["whileTyping"] == []
    assert entering["afterEnter"] == ["winter"]
    assert entering["prevented"] == 1


def test_enter_does_not_leave_a_second_search_behind(entering):
    # The timer it overtook has to go, or the same word is walked twice
    # over the whole history for one keypress.
    assert entering["afterTheWait"] == ["winter"]


def test_any_other_key_is_still_only_typing(entering):
    assert entering["afterAnotherKey"] == ["winter"]
    assert entering["andItsWait"] == ["winter", "winter"]


# One panel as `hass.panels` hands it over. Shared by the scenarios
# below rather than written out in each: the shape belongs to Home
# Assistant, and hand-written copies of somebody else's shape drift
# apart without anything going red.
_PANEL_SHAPE = """
const panel = (url_path, title, extra) => ({
  url_path, title, component_name: "lovelace",
  show_in_sidebar: true, default_visible: true, ...extra,
});
"""

# The sidebar's order is not a property of the server: it lives in each
# user's own frontend data. So the split runs in the panel, and this is
# where it is checked - against `hass.panels` the way Home Assistant
# hands it over, not against a shape invented here.
_SIDEBAR = """
const { splitBySidebar } = await import(
  new URL("./panel/sidebar.js", %(url)s).href
);
""" + _PANEL_SHAPE + """
const panels = {
  lovelace: panel("lovelace", "\\u00dcbersicht"),
  "a-kitchen": panel("a-kitchen", "Kitchen"),
  "b-garden": panel("b-garden", "Garden"),
  "c-test": panel("c-test", "Test", { show_in_sidebar: false }),
  "d-mine": panel("d-mine", "Mine"),
};
// Deliberately in no order at all: whatever the server listed is what
// the panel used to show, and what it must now stop showing.
const dashboards = [
  { key: "c-test", title: "Test", exists: true },
  { key: "b-garden", title: "Garden", exists: true },
  { key: "_default", title: "\\u00dcbersicht", exists: true },
  { key: "a-kitchen", title: "Kitchen", exists: true },
  { key: "d-mine", title: "Mine", exists: true },
];
const view = (extra) => ({
  panels, defaultPanel: "home", order: [], hidden: [], language: "en", ...extra,
});
const keys = (split) => ({
  sidebar: split.sidebar.map((d) => d.key),
  apart: split.apart.map((d) => d.key),
});

const plain = keys(splitBySidebar(dashboards, view()));
const arranged = keys(splitBySidebar(dashboards, view({
  order: ["d-mine", "b-garden"],
})));
const userHid = keys(splitBySidebar(dashboards, view({
  hidden: ["a-kitchen"],
})));
const defaulted = keys(splitBySidebar(dashboards, view({
  defaultPanel: "d-mine",
})));
const noPanel = keys(splitBySidebar(
  [...dashboards, { key: "e-ghost", title: "Ghost", exists: true }], view(),
));

console.log(JSON.stringify({ plain, arranged, userHid, defaulted, noPanel }));
"""


@pytest.fixture(scope="session")
def sidebar(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "sidebar", _SIDEBAR)


def test_an_unarranged_sidebar_is_ordered_the_way_home_assistant_orders_it(sidebar):
    # Nobody has dragged anything, so Home Assistant sorts by title with
    # a collator - which puts "Ubersicht" after "Mine" and not before
    # "Garden", where a byte comparison would have put it.
    assert sidebar["plain"]["sidebar"] == ["b-garden", "a-kitchen", "d-mine", "_default"]


def test_a_dashboard_that_is_not_in_the_sidebar_is_set_apart(sidebar):
    assert sidebar["plain"]["apart"] == ["c-test"]


def test_an_arranged_sidebar_keeps_the_arrangement(sidebar):
    # The two that were dragged come first, in the order they were
    # dragged into; everything else keeps falling back to the title.
    assert sidebar["arranged"]["sidebar"] == [
        "d-mine", "b-garden", "a-kitchen", "_default",
    ]


def test_one_this_user_hid_joins_the_ones_nobody_sees(sidebar):
    # Hidden by this user and hidden for everyone are different causes
    # with one consequence: it is not in the sidebar in front of them.
    assert sidebar["userHid"]["sidebar"] == ["b-garden", "d-mine", "_default"]
    assert sidebar["userHid"]["apart"] == ["a-kitchen", "c-test"]


def test_the_default_dashboard_leads(sidebar):
    assert sidebar["defaulted"]["sidebar"] == [
        "d-mine", "b-garden", "a-kitchen", "_default",
    ]


def test_a_recorded_dashboard_home_assistant_has_no_panel_for_is_set_apart(sidebar):
    # It cannot be in a sidebar it is not registered in, and guessing a
    # position for it would put it somewhere it is not. Set apart, and
    # sorted by title with the rest of them: "Ghost" before "Test".
    assert sidebar["noPanel"]["apart"] == ["e-ghost", "c-test"]


# What the list looks like when the browser can say nothing about the
# sidebar - an old Home Assistant, a call that failed. The order the
# server gave has to survive that untouched, and no empty fold may
# appear beside it.
_SIDEBAR_SIDE = """
const el = new Panel();
el._dashboards = [
  { key: "b-garden", title: "Garden", exists: true },
  { key: "a-kitchen", title: "Kitchen", exists: true },
  { key: "gone", title: "Gone", exists: false },
];
const withoutHass = el._renderSide();

el._hass = {
  panels: {
    "a-kitchen": {
      url_path: "a-kitchen", title: "Kitchen", component_name: "lovelace",
      show_in_sidebar: true, default_visible: true,
    },
    "b-garden": {
      url_path: "b-garden", title: "Garden", component_name: "lovelace",
      show_in_sidebar: false, default_visible: true,
    },
  },
  locale: { language: "en" },
};
const withHass = el._renderSide();

const order = (markup) =>
  [...markup.matchAll(/data-key="([^"]+)"/g)].map((m) => m[1]);
const folds = (markup) =>
  [...markup.matchAll(/<summary>([^<]+)<\\/summary>/g)].map((m) => m[1].trim());

console.log(JSON.stringify({
  withoutHass: { order: order(withoutHass), folds: folds(withoutHass) },
  withHass: { order: order(withHass), folds: folds(withHass) },
}));
"""


@pytest.fixture(scope="session")
def sidebar_side(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "sidebar_side", _SIDEBAR_SIDE)


def test_without_a_readable_sidebar_the_list_is_left_as_the_server_gave_it(
    sidebar_side,
):
    assert sidebar_side["withoutHass"]["order"] == ["b-garden", "a-kitchen", "gone"]
    assert sidebar_side["withoutHass"]["folds"] == ["Deleted (1)"]


def test_the_two_folds_stand_in_their_order_below_the_sidebar_ones(sidebar_side):
    assert sidebar_side["withHass"]["order"] == ["a-kitchen", "b-garden", "gone"]
    assert sidebar_side["withHass"]["folds"] == [
        "Not in the sidebar (1)", "Deleted (1)",
    ]


# -- the view after a switch --------------------------------------------

_TOP_HARNESS = """
const el = new Panel();
el._render = () => {};
el._call = () => new Promise(() => {});   // never answers; the switch is what matters

// The panel sits in Home Assistant's own page, and that page is what
// scrolls when the panel is taller than the window. Both are recorded:
// whichever one the panel reaches for, the test sees it.
let broughtIntoView = 0;
el.scrollIntoView = () => { broughtIntoView += 1; };
const main = { scrollTop: 400 };
el.shadowRoot = { querySelector: (s) => (s === ".main" ? main : null) };

el._select("other");
await settle();

console.log(JSON.stringify({ broughtIntoView, mainScrollTop: main.scrollTop }));
"""


@pytest.fixture(scope="module")
def after_a_switch(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "back-to-the-top", _TOP_HARNESS)


def test_switching_dashboards_brings_the_view_back_to_the_top(after_a_switch):
    # Reported from a real installation: with enough dashboards the
    # sidebar is longer than the window, so the row somebody clicks sits
    # far down the page - and the history they asked for is drawn at the
    # top of a column they are no longer looking at. What they see is
    # the grey below it.
    assert after_a_switch["broughtIntoView"] == 1


def test_switching_dashboards_also_rewinds_a_scrolled_main_column(after_a_switch):
    # The other way the same page can be scrolled: where the panel does
    # get a height of its own, the column scrolls instead of the page,
    # and its offset outlives the switch just the same.
    assert after_a_switch["mainScrollTop"] == 0


# -- the dashboard the panel opens on ------------------------------------

# Which dashboard is showing when the panel is opened. The list beside
# it is in the sidebar's order (see `_SIDEBAR` above), and the opening
# choice has to be read off *that* list: reported from a real
# installation, where the panel always opened on the alphabetically
# first dashboard rather than on the one at the top of the sidebar.
_OPENING = _PANEL_SHAPE + """
const panels = {
  "a-attic": panel("a-attic", "Attic"),
  "b-garden": panel("b-garden", "Garden"),
  "c-test": panel("c-test", "Test", { show_in_sidebar: false }),
};
// This user dragged Garden above Attic. Everything the panel needs to
// know that comes from the browser, so both halves are answered here:
// `hass.panels` and this user's own arrangement.
const seeing = () => ({
  panels,
  locale: { language: "en" },
  callWS: async () => ({ value: { panelOrder: ["b-garden"], hiddenPanels: [] } }),
});

const opened = async (dashboards, hass) => {
  const el = new Panel();
  el._render = () => {};
  el._hass = hass;
  el._call = async (type) => (type === "dashboards" ? { dashboards } : {});
  const picked = [];
  el._select = async (key) => { picked.push(key); };
  await el._loadDashboards();
  return picked;
};

// As the server lists them: sorted by key, because that is all a server
// can do. The deleted one leads, so that a run which stopped filtering
// them out would answer "gone" and be caught.
const live = [
  { key: "gone", title: "Gone", exists: false },
  { key: "a-attic", title: "Attic", exists: true },
  { key: "b-garden", title: "Garden", exists: true },
];

const arranged = await opened(live, seeing());
const noSidebar = await opened(live, {});
const apartOnly = await opened(
  [
    { key: "gone", title: "Gone", exists: false },
    { key: "c-test", title: "Test", exists: true },
  ],
  seeing(),
);
const deadOnly = await opened(
  [{ key: "gone", title: "Gone", exists: false }],
  seeing(),
);

console.log(JSON.stringify({ arranged, noSidebar, apartOnly, deadOnly }));
"""


@pytest.fixture(scope="module")
def opening(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "opening", _OPENING)


def test_the_panel_opens_on_the_first_dashboard_in_its_own_list(opening):
    # Not "a-attic", which is what the server listed first and what the
    # panel used to open on. The list on the left starts with the one
    # this user dragged to the top of their sidebar, and a panel showing
    # a history belonging to the second row is a panel that ignored it.
    assert opening["arranged"] == ["b-garden"]


def test_without_a_readable_sidebar_it_opens_on_the_first_the_server_gave(opening):
    # No `hass.panels`, so there is no order to read - every render
    # before the first answer arrives is this case. The server's own
    # order stands, and a live dashboard still beats a deleted one.
    assert opening["noSidebar"] == ["a-attic"]


def test_one_that_is_not_in_the_sidebar_is_still_opened_on(opening):
    # Nothing is in this user's sidebar, so the fold below it is where
    # the only live dashboard is. Opening on the deleted one instead
    # would show a gravestone to somebody who has a dashboard.
    assert opening["apartOnly"] == ["c-test"]


def test_with_nothing_but_deleted_dashboards_one_of_those_is_opened(opening):
    # A history full of gravestones is exactly the history somebody
    # opens this tool with. An empty page would be the wrong answer.
    assert opening["deadOnly"] == ["gone"]


def test_the_bin_is_offered_on_a_version_made_by_hand_too(row_parts):
    # The one place the two controls part company. Renaming a
    # lightweight tag is refused by the server, so a pen there could only
    # ever produce that sentence; removing one is allowed, and has to be
    # offered, or a hand-made tag would hold its number for ever.
    assert row_parts["binOnAnnotated"] is True
    assert row_parts["binOnByHand"] is True


def test_the_bin_names_the_version_it_would_remove(row_parts):
    assert row_parts["binCarriesTheName"] is True


def test_the_bin_is_revealed_by_the_same_class_as_the_pen(row_parts):
    # The stylesheet reveals `.pen` from a class on whatever holds it,
    # rather than from a list of the buttons that exist - the comment
    # there says why, and the failure mode of a fourth place forgetting
    # itself is silent invisibility. So the bin carries that class too
    # instead of earning a fifth selector.
    assert row_parts["binIsRevealedLikeThePen"] is True


_REMOVE_VERSION = """
// Four removals through one helper, because only three things differ
// between them: the version, the preview the server answers, and how
// the dialog is closed. Written out four times first, and that put
// fifteen lines of identical scaffolding around each of the facts the
// tests are actually about - a new stub or a changed `_call` signature
// would have had to be repeated four times by hand.
const shared = [
  { name: "dash/v1.0.2", title: "Third", description: "a note",
    revision: "c", annotated: true, automatic: false },
];

async function tryRemoval(name, answer, closeAs) {
  const panel = new Panel();
  // Handed in, because `attachShadow()` in the prelude answers `{}` and
  // panel.js throws that answer away - so `this.shadowRoot` is
  // undefined in Node. Every scenario in this file that touches a
  // dialog does this.
  panel.shadowRoot = node();
  panel._render = () => {};
  panel._selected = "dash";
  panel._versions = shared;
  panel._refresh = async () => {};
  const calls = [];
  panel._call = (type, extra) =>
    new Promise((resolve) => calls.push({ type, extra, resolve }));

  const running = panel._removeVersion(name);
  await settle();
  const asked = { ...calls[0] };
  calls[0].resolve(answer);
  await settle();

  const dialog = panel.shadowRoot.querySelector("dialog.remove");
  // Read before the dialog is closed. The stand-in does not clear it,
  // but a body read after `close()` is the shape in which a negative
  // assertion goes quietly vacuous, so both sides read it the same way.
  const body = dialog.querySelector(".body").innerHTML;
  dialog.returnValue = closeAs;
  dialog.close();
  await settle();

  const confirmed = calls[1] ? { ...calls[1] } : null;
  if (calls[1]) calls[1].resolve({ applied: true, name });
  await running;
  return { asked, body, confirmed, calls: calls.length };
}

// Highest and described, confirmed.
const first = await tryRemoval(
  "dash/v1.0.2",
  { applied: false, name: "dash/v1.0.2", title: "Third", description: "a note",
    revision: "c", automatic: false, highest: true },
  "remove",
);
// Automatic and returning, cancelled - the negative case for the
// number sentence and the positive one for re-tagging.
const second = await tryRemoval(
  "dash/v1.0.2",
  { applied: false, name: "dash/v1.0.2", title: "Third", description: "",
    revision: "c", automatic: true, highest: false, returns: true },
  "cancel",
);
// Automatic but NOT the day the next save would close - found on a real
// screen. The old panel hung the bullet on `automatic` alone and told
// this version it would be re-created, which was false.
const midway = await tryRemoval(
  "dash/v0.0.3",
  { applied: false, name: "dash/v0.0.3", title: "7 September 2026",
    description: "", revision: "m", automatic: true, highest: false,
    returns: false },
  "cancel",
);
// A hand-made lightweight tag: no title, no description, nothing that
// would come back. The version `bin()` exists to extend the offer to.
const wordless = await tryRemoval(
  "dash/by-hand",
  { applied: false, name: "dash/by-hand", title: "", description: "",
    revision: "z", automatic: false, highest: false },
  "cancel",
);

console.log(JSON.stringify({
  asked: { type: first.asked.type, extra: first.asked.extra },
  confirmed: first.confirmed
    && { type: first.confirmed.type, extra: first.confirmed.extra },
  saysTheNumberComesFree: first.body.includes("Version number freed"),
  hidesTheNumberSentence: !second.body.includes("Version number freed"),
  // The number itself, not a sentence about it. Matched on the markup
  // so a bullet that lost the `<strong>` and said "the next patch will
  // reuse it" would fail here rather than read as a pass.
  namesTheFreedNumber: first.body.includes("reuse <strong>v1.0.2</strong>"),
  saysTheStateStays: first.body.includes("History is preserved"),
  namesTheVersion: first.body.includes("Third"),
  showsTheDescription: first.body.includes("a note"),
  labelsTheDescription: first.body.includes("<strong>Description:</strong>"),
  callsAfterCancel: second.calls,
  firstSaysAutomatic: first.body.includes("Automatic re-tagging"),
  secondSaysAutomatic: second.body.includes("Automatic re-tagging"),
  // The one that matters: automatic, but not the day the next save
  // would close. Both halves are read from the same body, so a panel
  // that dropped the bullet altogether fails `secondSaysAutomatic`
  // rather than passing this one for the wrong reason.
  midwaySaysAutomatic: midway.body.includes("Automatic re-tagging"),
  midwayStillNamesTheVersion: midway.body.includes("7 September 2026"),
  // A hand-made tag has no title, so the head is the number alone and
  // the lead stops at the tag. Both halves are checked: a head that
  // rendered "by-hand — undefined" would pass the second on its own.
  wordlessHeadIsTheNumberAlone: wordless.body.includes("<strong>by-hand</strong>"),
  wordlessNamesOnlyTheTag: wordless.body.includes("only deletes the tag:"),
  // Matched on "its title" rather than the whole clause: the lead reads
  // ", its title and its description" with both and " and its title"
  // with one, so a matcher tied to either phrasing would go quiet the
  // moment the other one appeared.
  wordlessHidesTheWordsParagraph: !wordless.body.includes("its title"),
  // Matched on the class the description actually carries. It was
  // `muted` until the words moved up beside the number on 2026-09-09
  // and became `why` - and this assertion went on passing, because
  // nothing in this dialog says `muted` any more. A negative matcher
  // tied to a class the code no longer emits is always true.
  wordlessHasNoDescriptionParagraph: !wordless.body.includes('class="why"'),
  wordlessHasNoDescriptionLabel: !wordless.body.includes("Description:"),
}));
"""


@pytest.fixture(scope="module")
def removing(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "removing", _REMOVE_VERSION)


def test_the_dialog_is_filled_from_a_preview_the_server_answered(removing):
    # Asked without confirm first, exactly as `_forget` does: the panel
    # must not word the loss itself, and the words it shows are the ones
    # the server read off the tag a moment ago.
    assert removing["asked"]["type"] == "remove_version"
    assert removing["asked"]["extra"] == {
        "dashboard": "dash",
        "name": "dash/v1.0.2",
    }
    assert removing["namesTheVersion"] is True
    assert removing["saysTheStateStays"] is True


def test_the_dialog_shows_the_description_that_would_be_lost(removing):
    # The one string here that is genuinely unrecoverable, and until now
    # it appeared in neither the dialog nor the log - only its presence
    # as a boolean decided whether a paragraph was shown at all. Read
    # rather than taken on faith, as the FAQ's "there to be read rather
    # than clicked through" promises. Since 2026-09-09 it sits beside
    # the number rather than among the consequences, under a label of
    # its own - it says what the version *is*, and between the note and
    # its list it cut that sentence off from its own bullets.
    assert removing["showsTheDescription"] is True
    assert removing["labelsTheDescription"] is True
    assert removing["wordlessHasNoDescriptionLabel"] is True


def test_the_dialog_says_the_number_comes_free_where_it_does(removing):
    # The one sentence in this dialog somebody acts on. It comes from the
    # server's `highest`, never from the panel comparing numbers - that
    # calculation lives in versions.py by decision 13. Both halves of
    # the name are checked: a panel that printed this sentence
    # unconditionally, or worked it out itself from `this._versions`,
    # would pass the positive half alone.
    assert removing["saysTheNumberComesFree"] is True
    assert removing["hidesTheNumberSentence"] is True
    # And it spells the number out. "That number is free again" made a
    # reader look up which number that was, on the row they had just
    # left; the bullet names `v1.0.2` instead.
    assert removing["namesTheFreedNumber"] is True


def test_the_automatic_paragraph_shows_only_where_it_applies(removing):
    # `facts.automatic` has the same shape as `facts.highest`: a
    # paragraph that only one of the two previews should carry. The
    # first run answers `automatic: false`, the second `automatic:
    # true`, so a panel that rendered this unconditionally - or never
    # rendered it at all - is caught in one direction or the other.
    assert removing["firstSaysAutomatic"] is False
    assert removing["secondSaysAutomatic"] is True


def test_a_day_mark_that_would_not_come_back_is_not_promised_one(removing):
    # Found on a real screen on 2026-09-09, on dh-probe: `v0.0.3` marks
    # 7 September, seven states from the 8th sit behind it, and the
    # dialog told it that saving would create it again. It never would -
    # `end_of_previous_day` finds the most recent earlier day, so at the
    # next save that is the 8th and never the 7th.
    #
    # The bullet therefore hangs on `returns`, which only the server can
    # answer, and not on `automatic`, which the panel can see. The third
    # run is automatic with `returns: false`: the bullet stays away, and
    # the rest of the dialog is unaffected.
    assert removing["midwaySaysAutomatic"] is False
    assert removing["midwayStillNamesTheVersion"] is True


def test_confirming_sends_confirm_and_nothing_else_changes_hands(removing):
    assert removing["confirmed"]["type"] == "remove_version"
    assert removing["confirmed"]["extra"] == {
        "dashboard": "dash",
        "name": "dash/v1.0.2",
        "confirm": True,
    }


def test_cancelling_sends_no_second_call(removing):
    # The preview is a read, so it happens either way; what must not
    # happen is the write. One call, not two.
    assert removing["callsAfterCancel"] == 1


def test_the_wordless_lightweight_tag_claims_nothing_it_does_not_have(removing):
    # A hand-made tag has neither a title nor a description - the very
    # version `bin()` exists to extend the offer to. Three branches at
    # once: the head is the number alone rather than a number followed
    # by an em dash and nothing, the lead stops at "the tag" instead of
    # naming words that are not there, and no description is rendered.
    # The dialog must not claim a loss that is not real.
    assert removing["wordlessHeadIsTheNumberAlone"] is True
    assert removing["wordlessNamesOnlyTheTag"] is True
    assert removing["wordlessHidesTheWordsParagraph"] is True
    assert removing["wordlessHasNoDescriptionParagraph"] is True


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
    # "Technical details") keep passing unmodified.
    assert '<span class="glyph">&lt;/&gt;</span> Technical details' in card_diff_pill["html"]
    assert 'details class="raw"' in card_diff_pill["html"]


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
// Not part of what this scenario measures - `_openReplace` reloads the
// history after a successful write the same way `_confirm` does, and
// that reload runs through the same `_call` stub. Without this the
// scenario's own manual, resolve-by-hand `_call` would leave that
// reload's requests uncollected forever and `await done` below would
// never settle - the same reason several `_confirm`-flow scenarios
// earlier in this file stub it out too.
el._reloadAfterWrite = async () => null;

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

// The stand-in caches one stand-in node per selector *string*, shared
// tree-wide, not one per real element - so both radios `_openReplace`
// builds via `choice.querySelectorAll('input[name="replace-target"]')`
// collapse onto the single node cached under that selector, and that
// is where `addEventListener("change", ...)` actually lands - not on
// `choice` itself. Read via the same selector the production code
// queries with, not through `choice._on` directly.
const radio = choice.querySelector('input[name="replace-target"]');
radio._on.change?.({ target: { value: "1" } });
const afterSwitch = { bodyHtml: dialog.querySelector(".body").innerHTML, calls: calls.length };

dialog.close("apply");
await settle();
const writeCall = calls[2] ? { type: calls[2].type, extra: calls[2].extra } : null;
calls[2]?.resolve({ applied: true });
await done;

console.log(JSON.stringify({ firstBatch, afterOpen, afterSwitch, writeCall }));
"""


@pytest.fixture(scope="session")
def open_replace_both(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "open_replace_both", _OPEN_REPLACE_BOTH)


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
    # `_replaceCandidates` orders "before" (revision "b") first and
    # "after" (revision "a", the change itself) second; the radio was
    # switched to index 1 - "after" - before Apply, matching the "+d"
    # preview `test_switching_the_replace_radio_costs_no_extra_request`
    # already confirms is on screen at that point.
    assert open_replace_both["writeCall"] == {
        "type": "restore_state",
        "extra": {"dashboard": "dash", "revision": "a", "confirm": True},
    }


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
const applyLabel = dialog
  .querySelector(".actions button[value=\\"apply\\"]").textContent;
dialog.close("cancel");
await done;

console.log(JSON.stringify({ bodyHtml, applyLabel }));
"""


@pytest.fixture(scope="session")
def undo_intro(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "undo_intro", _UNDO_INTRO)


def test_the_undo_dialogs_button_says_undo_not_apply(undo_intro):
    # The dialog is shared by four flows, so its button used to read
    # "Apply" in all of them - the one word that says nothing about
    # which of the four you are in. The last place somebody can notice
    # they opened the wrong one is the button they are about to press.
    assert undo_intro["applyLabel"] == "Undo this change"


def test_the_consequence_comes_before_the_itemised_account(undo_intro):
    # "Puts this change back and keeps the 2 changes made since" is the
    # answer to "what am I about to do"; the card-by-card list under
    # "What applying this does" is the detail it summarises. Printed
    # after the list it read as a stray line nobody could place.
    body = undo_intro["bodyHtml"]
    assert body.index("Puts this change back") < body.index("What applying this does")


def test_the_undo_dialog_carries_the_kept_since_sentence(undo_intro):
    # Moved out of the card (design handoff point 2): the reader sees
    # this sentence at the point they are asked to confirm, not before.
    # "a" is _changes[0], the newest of the three loaded changes, so
    # nothing was made since it - the sentence stays plain, with no
    # "and keeps" clause (the fix for a bug that used to invert this:
    # a prior version of this assertion expected "2" here, which was
    # the count of *older* loaded changes, not newer ones).
    assert undo_intro["bodyHtml"].count("Puts this change back.") == 1
    assert "and keeps" not in undo_intro["bodyHtml"]


_UNDO_INTRO_OLDEST = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._changes = [{ revision: "a" }, { revision: "b" }, { revision: "c" }];
el.shadowRoot = node();

const calls = [];
el._call = (type, extra) => new Promise((resolve) => calls.push({ type, extra, resolve }));

const done = el._undoChange("c");
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
def undo_intro_oldest(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "undo_intro_oldest", _UNDO_INTRO_OLDEST)


def test_the_undo_dialog_counts_changes_made_since_the_oldest_loaded_change(
    undo_intro_oldest,
):
    # "c" is _changes[2], the oldest of the three loaded changes - two
    # newer changes ("a" and "b") were made since it. This is the case
    # that catches the inverted formula: the buggy version reported
    # this._changes.length - 1 - made, the count of *older* loaded
    # changes (0 here), not newer ones (2).
    assert (
        "Puts this change back and keeps the 2 changes made since."
        in undo_intro_oldest["bodyHtml"]
    )


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




_FORGET_LOCKS = """
const el = new Panel();
el._render = () => {};
el.shadowRoot = node();
el._selected = "kitchen";
el._dashboards = [{ key: "kitchen", title: "Kitchen" }];
// The dialog is not what is under test here; its answer is.
el._answerFrom = () => Promise.resolve("forget");
el._loadSidebar = () => Promise.resolve();

let release;
const sent = [];
el._call = (type, extra) => {
  sent.push({ type, extra });
  if (type === "forget" && extra.confirm) {
    // Held open, which is the whole point: everything below happens
    // while the rewrite is still running.
    return new Promise((resolve) => { release = resolve; });
  }
  if (type === "forget") {
    return Promise.resolve({ states: 3, described: 0, first: 1000, last: 2000 });
  }
  if (type === "dashboards") return Promise.resolve({ dashboards: [] });
  return Promise.resolve({});
};

const running = el._forget();
await settle();
await settle();

const whileRunning = {
  locked: !!el._forgetting,
  key: el._forgetting?.key ?? null,
  title: el._forgetting?.title ?? null,
  phase: el._forgetting?.phase ?? null,
};

// A step of the rewrite, as the bus delivers it.
el._onForgetting({
  data: { dashboard: "kitchen", phase: "rewriting", done: 100, total: 782 },
});
const counted = {
  phase: el._forgetting?.phase ?? null,
  done: el._forgetting?.done ?? null,
  total: el._forgetting?.total ?? null,
};

// Another dashboard's progress, which this page did not start.
const heardBefore = el._forgetting?.heard ?? null;
el._onForgetting({
  data: { dashboard: "garden", phase: "cleaning", done: 0, total: 0 },
});
const ignoredOther = {
  phase: el._forgetting?.phase ?? null,
  done: el._forgetting?.done ?? null,
  untouched: (el._forgetting?.heard ?? null) === heardBefore,
};

release({ applied: true, removed: 5 });
await running;
const afterwards = { locked: !!el._forgetting };

// And the same once more, with the call failing: a lock nobody can
// leave is worse than no lock.
el.shadowRoot = node();
el._selected = "kitchen";
el._dashboards = [{ key: "kitchen", title: "Kitchen" }];
el._call = (type, extra) => {
  if (type === "forget" && extra.confirm) return Promise.reject(new Error("boom"));
  if (type === "forget") {
    return Promise.resolve({ states: 1, described: 0, first: 1, last: 2 });
  }
  if (type === "dashboards") return Promise.resolve({ dashboards: [] });
  return Promise.resolve({});
};
await el._forget();
const afterFailure = { locked: !!el._forgetting };

console.log(JSON.stringify({
  whileRunning, counted, ignoredOther, afterwards, afterFailure,
}));
"""


@pytest.fixture(scope="session")
def forget_locks(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "forget_locks", _FORGET_LOCKS)


def test_the_page_is_locked_while_the_rewrite_runs(forget_locks):
    # Not decoration. Measured on the test bench on 2026-09-18: the same
    # forget takes 24 s undisturbed and 76 s while this panel keeps
    # asking questions, because the rewrite and every answer come out of
    # one Python interpreter. Taking the controls away is what makes it
    # finish three times sooner.
    assert forget_locks["whileRunning"] == {
        "locked": True,
        "key": "kitchen",
        "title": "Kitchen",
        "phase": "rewriting",
    }


def test_the_lock_counts_what_the_rewrite_reports(forget_locks):
    # A spinner that stands still for a minute is indistinguishable from
    # one that is stuck, and somebody who cannot tell presses reload -
    # in the middle of the one operation that rewrites history.
    assert forget_locks["counted"] == {"phase": "rewriting", "done": 100, "total": 782}


def test_another_dashboards_progress_does_not_touch_this_lock(forget_locks):
    # The event reaches every open panel. A second tab merely watching
    # must not have its own lock repainted by somebody else's rewrite -
    # and `heard` least of all, since a stale one is what the silence
    # warning reads.
    assert forget_locks["ignoredOther"] == {
        "phase": "rewriting",
        "done": 100,
        "untouched": True,
    }


def test_the_lock_is_released_whatever_happens(forget_locks):
    # Both ways out, and the second is the one that matters: a lock left
    # standing by a failed call leaves somebody with a spinner and no way
    # back except the reload this whole screen exists to prevent.
    assert forget_locks["afterwards"] == {"locked": False}
    assert forget_locks["afterFailure"] == {"locked": False}


_LOCK_SCREEN = """
const el = new Panel();
el.shadowRoot = node();
// The module starts loading its parts on import; STYLE and escape are
// undefined until that settles, and a lock screen built too early would
// throw where nobody is watching.
for (let i = 0; i < 50; i++) await settle();

el._forgetting = {
  key: "kitchen",
  title: "Kitchen <script>alert(1)</script>",
  phase: "rewriting",
  done: 100,
  total: 782,
  heard: Date.now(),
};
const screen = el._renderLock();

el._forgetting.heard = Date.now() - 120000;
const afterSilence = el._renderLock();

el._forgetting.heard = Date.now();
el._forgetting.phase = "cleaning";
el._forgetting.total = 0;
const uncounted = el._renderLock();

// And the render that puts it there, which must not bind anything.
el._render();
const painted = el.shadowRoot.innerHTML;

console.log(JSON.stringify({
  names: screen.includes("Kitchen"),
  escaped: !screen.includes("<script>alert"),
  counted: screen.includes("100") && screen.includes("782"),
  phrase: screen.includes("Rewriting the recorded states"),
  noControls: !/data-[a-z-]+=/i.test(screen),
  quietYet: screen.includes("reload it"),
  doubtsAfterSilence: afterSilence.includes("reload it"),
  uncountedHasNoNumbers: !/\\d+ of \\d+/.test(uncounted),
  paintedTheLock: painted.includes('class="lockbox"'),
  paintedNoLayout: !painted.includes('class="layout"'),
}));
"""


@pytest.fixture(scope="session")
def lock_screen(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "lock_screen", _LOCK_SCREEN)


def test_the_lock_screen_says_what_is_happening(lock_screen):
    # Built for real rather than read as source: STYLE and `escape` are
    # loaded asynchronously, and a lock screen that throws while building
    # leaves a blank page in the one moment somebody is watching hardest.
    assert lock_screen["names"] is True
    assert lock_screen["counted"] is True
    assert lock_screen["phrase"] is True
    # A dashboard title is somebody's own text and goes through `escape`
    # like every other one.
    assert lock_screen["escaped"] is True


def test_the_lock_screen_offers_nothing_to_click(lock_screen):
    # The point of the screen, and the measured one: markup that is not
    # there cannot start a request that competes with the rewrite for the
    # same interpreter. Not disabled buttons - no buttons.
    assert lock_screen["noControls"] is True
    assert lock_screen["paintedTheLock"] is True
    assert lock_screen["paintedNoLayout"] is True


def test_the_lock_screen_admits_when_it_stops_hearing(lock_screen):
    # It never claims to know more than it does: while steps arrive it
    # shows them, and after a minute of silence it says the page can no
    # longer tell slow from stuck - which is the honest version of the
    # reload somebody would press anyway.
    assert lock_screen["quietYet"] is False
    assert lock_screen["doubtsAfterSilence"] is True


def test_a_phase_without_numbers_shows_none(lock_screen):
    # `cleaning` reports no count, because the collection walks the whole
    # object store and reports nothing back. "0 of 0" would be a lie
    # dressed as precision.
    assert lock_screen["uncountedHasNoNumbers"] is True


_LOCK_KEEPS_QUIET_WATCH = """
const el = new Panel();
el.shadowRoot = node();
for (let i = 0; i < 50; i++) await settle();

// Hold every timer the panel asks for, so the silence can be made to
// fall due without waiting a real minute for it.
const timers = [];
const realSetTimeout = globalThis.setTimeout;
globalThis.setTimeout = (fn, ms) => {
  // `settle` uses setTimeout too; only the long waits are the panel's.
  if (ms && ms > 1000) { timers.push({ fn, ms }); return timers.length; }
  return realSetTimeout(fn, ms);
};
globalThis.clearTimeout = (id) => { if (timers[id - 1]) timers[id - 1].cleared = true; };

let release;
const sent = [];
el._call = (type, extra) => {
  sent.push({ type, extra });
  if (type === "forget" && extra.confirm) {
    return new Promise((resolve) => { release = resolve; });
  }
  if (type === "forget") {
    return Promise.resolve({ states: 1, described: 0, first: 1, last: 2 });
  }
  if (type === "dashboards") return Promise.resolve({ dashboards: [] });
  return Promise.resolve({});
};
el._loadSidebar = () => Promise.resolve();
// Closes the dialog, which is what the real `_answerFrom` ends up doing:
// it waits for `close`. Left open, the stand-in answers `dialog[open]`
// for ever and `_render` draws nothing at all - a test that would then
// be measuring its own stub.
el._answerFrom = (dialog) => { dialog.open = false; return Promise.resolve("forget"); };
el._selected = "kitchen";
el._dashboards = [{ key: "kitchen", title: "Kitchen" }];

const running = el._forget();
await settle();
await settle();

// A watch has to exist at all, or nothing will ever redraw the screen
// once the reports stop - which is precisely when the notice is needed.
const armed = { waiting: timers.filter((t) => !t.cleared).length };

// Let the silence fall due: the panel heard nothing for over a minute.
el._forgetting.heard = Date.now() - 120000;
const pending = timers.filter((t) => !t.cleared);
pending.forEach((t) => t.fn());
const painted = el.shadowRoot.innerHTML;
const doubts = painted.includes("reload it");

// A fresh report must restart the watch rather than leave a stale one.
timers.length = 0;
el._onForgetting({
  data: { dashboard: "kitchen", phase: "rewriting", done: 5, total: 10 },
});
const rearmed = { waiting: timers.filter((t) => !t.cleared).length };

release({ applied: true, removed: 1 });
await running;
const afterwards = {
  locked: !!el._forgetting,
  leftRunning: timers.filter((t) => !t.cleared).length,
};

globalThis.setTimeout = realSetTimeout;
console.log(JSON.stringify({ armed, doubts, rearmed, afterwards }));
"""


@pytest.fixture(scope="session")
def lock_quiet_watch(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "lock_quiet_watch", _LOCK_KEEPS_QUIET_WATCH)


def test_the_lock_watches_for_its_own_silence(lock_quiet_watch):
    # The notice is worked out while drawing, and the screen is drawn
    # when a report arrives - so without a timer of its own the one
    # message about reports having stopped is the one message that can
    # never appear. Reported as a review finding on 2026-09-18.
    assert lock_quiet_watch["armed"]["waiting"] >= 1
    assert lock_quiet_watch["doubts"] is True


def test_a_fresh_report_restarts_the_silence_watch(lock_quiet_watch):
    # Otherwise the first minute of the operation decides for the whole
    # of it: either the notice never comes, or it comes while steps are
    # still arriving and calls a working rewrite stuck.
    assert lock_quiet_watch["rearmed"]["waiting"] >= 1


def test_the_silence_watch_is_called_off_with_the_lock(lock_quiet_watch):
    # A timer outliving the screen it redraws would repaint a lock over
    # a page somebody is using again.
    assert lock_quiet_watch["afterwards"] == {"locked": False, "leftRunning": 0}


_LOCK_SILENCES_AUTO_REFRESH = """
const el = new Panel();
el.shadowRoot = node();
el._render = () => {};

const sent = [];
el._call = (type, extra) => {
  sent.push({ type, extra });
  return Promise.resolve({ dashboards: [], changes: [], versions: [] });
};
el._loadSidebar = () => Promise.resolve();
el._selected = "kitchen";
el._dashboards = [{ key: "kitchen", title: "Kitchen" }];

// Not locked: the recorder's announcements are what keeps the page live.
el._onRecorded({ data: { dashboards: ["garden"] } });
await settle();
const whenFree = sent.map((c) => c.type);

// Locked: the same announcements must not start anything. A forget is
// three times slower while this panel asks questions, and an automatic
// refresh is a question nobody even chose to ask.
sent.length = 0;
el._forgetting = {
  key: "kitchen", title: "Kitchen", phase: "rewriting",
  done: 0, total: 0, heard: Date.now(),
};
el._onRecorded({ data: { dashboards: ["garden"] } });
el._onRecorded({ data: { dashboards: ["kitchen"] } });
await settle();
await settle();
const whenLocked = sent.map((c) => c.type);

console.log(JSON.stringify({ whenFree, whenLocked }));
"""


@pytest.fixture(scope="session")
def lock_silences_refresh(tmp_path_factory):
    return _run_in_node(
        tmp_path_factory, "lock_silences_refresh", _LOCK_SILENCES_AUTO_REFRESH
    )


def test_the_lock_holds_off_automatic_refreshes(lock_silences_refresh):
    # Taking the controls away is only half of it: the recorder keeps
    # announcing while a forget runs - a save waiting behind the lock, a
    # reconciliation pass - and each announcement used to start a request
    # of its own. That is the same competition for one interpreter the
    # lock exists to end, arriving through a door nobody thought to shut.
    # Reported as a review finding on 2026-09-18.
    assert lock_silences_refresh["whenFree"] != []
    assert lock_silences_refresh["whenLocked"] == []
