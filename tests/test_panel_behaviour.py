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
    hidden: false, returnValue: "", open: false,
    _seen: {}, _on: {},
    querySelector(selector) {
      return (it._seen[selector] ||= node());
    },
    querySelectorAll(selector) { return [it.querySelector(selector)]; },
    addEventListener(name, run) { it._on[name] = run; },
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
