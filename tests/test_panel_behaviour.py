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
el._changes = [{ revision: "a" }, { revision: "b" }, { revision: "c" }];

// Every WebSocket call is held until the test lets it go.
const calls = [];
el._call = (type, extra) =>
  new Promise((resolve) => calls.push({ type, extra, resolve }));

// Row "a" is opened, then row "b" before "a" has answered.
el._expand(0);
el._expand(1);
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
const one = new Panel();
one._render = () => {};
const calls = [];
one._call = (type, extra) =>
  new Promise((resolve, reject) => calls.push({ type, extra, resolve, reject }));
one._select("A");
one._select("B");
calls[1].resolve({ changes: [{ revision: "B-new" }] });
await settle();
calls[0].reject(new Error("A failed late"));
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
two._changes = [{ revision: "a" }, { revision: "b" }, { revision: "c" }];
const opened = [];
two._call = (type, extra) =>
  new Promise((resolve) => opened.push({ type, extra, resolve }));
two._expand(0);
two._expand(1);
two._expand(0);
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
