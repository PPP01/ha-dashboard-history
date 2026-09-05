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
globalThis.HTMLElement = class { attachShadow() { return {}; } };
let Panel;
globalThis.customElements = {
  get() { return undefined; },
  define(name, cls) { Panel = cls; },
};
await import(%(url)s);
const settle = () => new Promise((r) => setTimeout(r, 0));
const answer = (call, mark) => {
  if (call.type === "deleted_since") call.resolve({ items: [{ label: mark }] });
  else if (call.type === "explain") call.resolve({ groups: [], note: mark });
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
 */
const node = () => {
  const it = {
    textContent: "", innerHTML: "", value: "", checked: false,
    hidden: false, returnValue: "", open: false, dataset: {},
    _seen: {}, _on: {},
    querySelector(selector) {
      return (it._seen[selector] ||= node());
    },
    querySelectorAll(selector) { return [it.querySelector(selector)]; },
    addEventListener(name, run) { it._on[name] = run; },
    // Three no-ops rather than three more properties: the version
    // dialog presses its level buttons into shape with `setAttribute`
    // and puts the cursor in the title field, and the description
    // dialog selects the text it prefilled. A stand-in that cannot be
    // told any of it makes those flows untestable for a reason that
    // has nothing to do with what they do. (Scenarios older than this
    // hand their own in; those still work, and are left alone.)
    setAttribute() {},
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
const forA = calls.slice(0, 3);
const forB = calls.slice(3, 6);

// "b" answers first...
forB.forEach((call) => answer(call, "B"));
await settle();
const afterB = { open: el._open, items: el._items.map((i) => i.label), busy: !!el._busy };

// ...and "a" answers last, for a row nobody is looking at any more.
forA.forEach((call) => answer(call, "A"));
await settle();
const afterA = { open: el._open, items: el._items.map((i) => i.label), busy: !!el._busy };

console.log(JSON.stringify({ afterB, afterA }));
"""


@pytest.fixture(scope="module")
def outcome(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "late-answer", _HARNESS)


def test_a_late_answer_for_a_row_no_longer_open_is_dropped(outcome):
    # Measured on 2026-09-03: the answer for "a" landed after "b" had
    # been chosen and drawn, and the row marked "b" showed "a"'s items.
    assert outcome["afterA"]["open"] == "b"
    assert outcome["afterA"]["items"] == ["B"]


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
const firstA = opened.slice(0, 3);
const forB = opened.slice(3, 6);
const secondA = opened.slice(6, 9);
secondA.forEach((call) => answer(call, "A2"));
forB.forEach((call) => answer(call, "B"));
await settle();
firstA.forEach((call) => answer(call, "A1"));
await settle();
const repeat = { open: two._open, items: two._items.map((i) => i.label) };

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
    assert generations["repeat"]["items"] == ["A2"]


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
el._items = ["stale"];

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
// The detail is fetched again. Two different questions about two
// different revisions: what was deleted asks against the row's
// predecessor, what happened asks about the row itself.
const deletedSince = calls.find((c) => c.type === "deleted_since")?.extra.revision;
const explained = calls.find((c) => c.type === "explain")?.extra.revision;
reply("deleted_since", { items: ["fresh"], available: true });
reply("explain", { groups: [] });
reply("undo_change", { available: false });
await again;

console.log(JSON.stringify({
  open: el._open,
  rows: el._changes.map((c) => c.revision),
  deletedSince,
  explained,
  items: el._items,
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
    # And its answers are fetched again rather than kept: after a change
    # from outside, "Put back" would offer items worked out against a
    # dashboard that has moved on.
    #
    # Two questions, two revisions, and this is where addressing by
    # position used to go wrong. What was deleted is asked against the
    # row's own predecessor `b`; what happened is asked about the row
    # itself. By index after the refresh, `a` sits at 1 and the row
    # below it at 2 - neither of which is `b`.
    assert refresh_open["deletedSince"] == "b"
    assert refresh_open["explained"] == "a"
    assert refresh_open["items"] == ["fresh"]


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
    ticked: box().checked,
    title: box() && el.shadowRoot
      .querySelector("[data-keep]").querySelector(".keeptitle").value,
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
  diffShown: simple.body.includes("Show the technical details"),
  keepsShown: simple.body.includes("is not lost"),
  tickedInSimple: simple.ticked,
  offeredTitle: simple.title,
  clearInAdvanced: advanced.ticked,
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

// It worked. There is nothing to report, and a banner here would be an
// alarm about a success.
nextAnswer = { applied: true, kept_as_version: { created: "dash/v1.0.1" } };
const quiet = await press();

console.log(JSON.stringify({ spoken, once, quiet }));
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


def test_the_same_failure_is_not_reported_twice(keep_failed):
    # `note` and `kept_as_version.error` are the same sentence when the
    # live state could not be recorded - operations passes one into the
    # other. Twice reads as two faults.
    assert keep_failed["once"] == "the live state is not recorded"


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
const attempt = async (shape) => {
  preview = shape;
  el.shadowRoot = node();
  const at = sent.length;
  const done = el._restoreState("b", "Back to this version");
  await settle();
  const offered = !el.shadowRoot.querySelector("[data-keep]").hidden;
  el.shadowRoot.querySelector("dialog.confirm").close("apply");
  await done;
  const confirming = sent
    .slice(at)
    .find((c) => c.type === "restore_state" && c.extra.confirm);
  return {
    offered,
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

// The ordinary case, in the same harness, so that "not offered" above
// means the offer was withheld rather than never reachable.
const ordinary = await attempt({
  applied: false,
  preview: "-a\\n+b",
  explanation: { groups: [], note: "one card removed" },
});

console.log(JSON.stringify({ nothing, recreating, ordinary }));
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
    # Simple mode: an unmarked state is invisible, so it is ticked.
    # Advanced mode: everything shows anyway, and a mark per experiment
    # would pile up.
    assert keeping["tickedInSimple"] is True
    assert keeping["clearInAdvanced"] is False


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
  against: asked.find((c) => c.type === "deleted_since")?.extra.revision,
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
    # "there is nothing before this" and offered no deleted cards to put
    # back. The predecessor is in the row now, so it asks against it.
    assert addressing["bottom"]["open"] == "b"
    assert addressing["bottom"]["against"] == "c"
    assert addressing["bottom"]["types"] == ["deleted_since", "explain", "undo_change"]


def test_the_first_recorded_state_asks_about_nothing_before_it(addressing):
    # There genuinely is nothing there, and asking would be asking about
    # a revision that does not exist.
    assert addressing["first"]["types"] == ["explain", "undo_change"]


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
const against = asked.find((c) => c.type === "deleted_since")?.extra.revision;

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

console.log(JSON.stringify({ opened, against, describing }));
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
    # And it asks against its own predecessor, which came with the hit.
    assert found_row["against"] == "deeper"


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

// From here the reload at the end of each flow is out of the way; what
// is measured is which dashboard the writing call names.
el._select = async () => {};
el._refreshQuietly = async () => {};
el._reloadAfterWrite = async () => null;

// 3. The control: nothing moves, the dialog opens, the write goes out.
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

// 4. The selection moves without going through `_select`, so the claim
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

// 5. And the irreversible one, the same way round.
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

console.log(JSON.stringify({
  previewFor, restoreAfterSwitch, forgetAfterSwitch,
  openedNormally, restoredTo, carriedTo,
  named: dialogSaid.includes("Kitchen"), forgotten,
}));
"""


@pytest.fixture(scope="session")
def wrong_dashboard(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "wrong_dashboard", _WRONG_DASHBOARD)


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
    set() { it._seen = {}; },
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

console.log(JSON.stringify({
  opened,
  stillThere,
  owed,
  settled: await finished(restoring),
  caughtUp: el._renderOwed,
  wrote: written.length,
  keep: written[0] ? written[0].extra.keep_as_version ?? null : null,
  rows: el._changes.map((c) => c.revision),
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


def test_the_held_render_runs_when_the_dialog_closes(dialog_survives):
    # Held, not dropped: the older page is in the list, and the render
    # that was owed has been paid by the time the flow moves on.
    assert dialog_survives["owed"] is True
    assert dialog_survives["caughtUp"] is False
    assert dialog_survives["rows"] == ["a", "b"]


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
el._versions = [
  { name: "dash/v1.2.0", title: "Kitchen rebuild", description: "",
    revision: "a", same_as_now: true },
  { name: "dash/v1.0.0", title: "Autumn tidy", description: "",
    revision: "c", same_as_now: false },
];
el._changes = [
  { revision: "a", message: "1 card added", versions: [{ name: "dash/v1.2.0" }],
    timestamp: 1 },
  { revision: "b", message: "2 cards moved", versions: [], timestamp: 2 },
  { revision: "c", message: "3 cards removed",
    versions: [{ name: "dash/v1.0.0" }], timestamp: 3 },
];

const count = (text, needle) => text.split(needle).length - 1;
const plain = el._renderMain();
// The simple mode filters the complete version list and asks nobody,
// so this needs no server at all.
await el._search("autumn");
const filtered = el._renderMain();

console.log(JSON.stringify({
  plain: {
    standing: plain.includes("The dashboard is in the state of Kitchen rebuild."),
    rows: count(plain, "class=\\"vrow\\""),
    twoChanges: plain.includes("The newest 2 changes in this version"),
    oneChange: plain.includes("The newest change in this version"),
  },
  filtered: {
    standing: filtered.includes(
      "The dashboard is in the state of Kitchen rebuild."),
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
    assert simple_mode["plain"]["standing"] is True
    assert simple_mode["plain"]["rows"] == 2


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


# -- rows.js, the other half with no behavioural test ----------------------

_ROWS = """
const rows = await import(new URL("./panel/rows.js", %(url)s).href);

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
    section: {
      versions: [{ name: "dash/v1.0.0", title: "One" }],
      rows: [top, top + 1],
    },
    here,
    top,
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
  crowned: head(true, 0).includes("current state"),
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
  spokenFor: row(CHANGE, { newest: true, spokenFor: true })
    .includes("current state"),
  movedOn: row({ ...CHANGE, same_as_now: false }, { newest: true })
    .includes("chip"),
  named: row(CHANGE, { newest: true, matching: ["v1.0.0"] })
    .includes("same state as v1.0.0"),
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
    # Two truths, two wordings: a version on the newest entry is where
    # the dashboard is; one further down only holds the same thing.
    assert row_parts["crowned"] is True
    assert row_parts["sameState"] is True


def test_a_chip_says_which_kind_of_sameness_it_means(row_parts):
    assert row_parts["newestChip"] is True
    assert row_parts["lowerChip"] is True
    # The head a few pixels above already carries it; twice is noise.
    assert row_parts["spokenFor"] is False
    # And nothing at all where the dashboard has moved on.
    assert row_parts["movedOn"] is False
    assert row_parts["named"] is True


def test_a_long_list_of_names_is_cut_and_says_so(row_parts):
    # Measured on the test bench: eighteen versions sat on states equal
    # to the live one, and the chip listed every one of them.
    assert row_parts["names"] == [
        "v1.0.0",
        "v1.0.0 and v1.1.0",
        "v1.0.0 and 2 more",
    ]


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

console.log(JSON.stringify({
  sent,
  query: el._query,
  shown: el._shown() && el._shown().map((c) => c.revision),
  described: (el._found || []).map((c) => c.description),
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
