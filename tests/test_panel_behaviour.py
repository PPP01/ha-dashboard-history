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
