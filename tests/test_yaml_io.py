"""Tests for the deterministic YAML representation."""

import copy
import json
import os
import pathlib

import pytest
import yaml

import yaml_io

# Real dashboards, if any are pointed at: set
# DASHBOARD_HISTORY_REAL_STORAGE to a Home Assistant .storage directory
# to run these against your own. Without it the synthetic cases still run.
# No default path: a personal one in a public repository says something
# about a machine and nothing about this project. conftest.py also reads
# tests/.real-storage, which git ignores.
_STORAGE = os.environ.get("DASHBOARD_HISTORY_REAL_STORAGE", "")
REAL_DASHBOARDS = sorted(pathlib.Path(_STORAGE).glob("lovelace.*")) if _STORAGE else []


def _body(text):
    """The YAML without the header comment."""
    return [line for line in text.splitlines() if not line.startswith("#")]


def test_round_trip_simple():
    data = {"views": [{"title": "Home", "cards": [{"type": "map"}]}]}
    assert yaml_io.load(yaml_io.dump(data)) == data


def test_round_trip_multiline():
    data = {"style": "ha-card {\n  border: none;\n}"}
    assert yaml_io.load(yaml_io.dump(data)) == data


def test_multiline_becomes_block_scalar():
    assert "style: |" in yaml_io.dump({"style": "a\nb\nc"})


def test_trailing_space_survives():
    # YAML cannot carry trailing spaces in a block scalar, so the dumper
    # must fall back to a quoted style rather than silently dropping them.
    data = {"style": "first line   \nsecond line"}
    text = yaml_io.dump(data)
    assert "style: |" not in text
    assert yaml_io.load(text) == data


def test_umlauts_stay_readable():
    text = yaml_io.dump({"title": "Küche"})
    assert "Küche" in text
    assert "\\u" not in text


def test_numeric_string_stays_a_string():
    data = {"code": "0123"}
    assert yaml_io.load(yaml_io.dump(data)) == data


def test_dump_is_stable():
    data = {"views": [{"title": "A"}]}
    assert yaml_io.dump(data) == yaml_io.dump(data)


def test_key_order_is_preserved():
    data = {"type": "tile", "entity": "sensor.a", "name": "A"}
    keys = [line.split(":")[0] for line in _body(yaml_io.dump(data)) if ":" in line]
    assert keys == ["type", "entity", "name"]


def test_header_carries_no_timestamp():
    # Anything varying between runs would produce a commit on every save.
    assert yaml_io.dump({"x": 1}) == yaml_io.dump({"x": 1})
    assert "20" not in yaml_io.HEADER


@pytest.mark.skipif(not REAL_DASHBOARDS, reason="no real dashboards available")
@pytest.mark.parametrize("path", REAL_DASHBOARDS, ids=lambda p: p.name)
def test_real_dashboards_survive_the_round_trip(path):
    """The synthetic cases above cannot cover what real dashboards contain.

    This is the test the spec asks for. It is skipped where the storage
    files are not reachable, so the suite still runs anywhere.
    """
    config = json.loads(path.read_text(encoding="utf-8"))["data"]["config"]
    text = yaml_io.dump(config)
    assert yaml_io.load(text) == config
    assert yaml_io.dump(config) == text


def test_the_fast_parser_answers_what_the_slow_one_answers():
    """`load` goes through libyaml where it exists; both must agree.

    The reason for the switch is speed - a 262 KiB dashboard parsed in
    54.8 ms instead of 501 ms, measured 2026-09-11 - and the reason for
    this test is that speed must not buy a different answer. Checked
    once over all 98 dashboards of the test bench before switching;
    this keeps a few shapes of it in the suite. Where PyYAML was built
    without libyaml the two loaders are the same object and this passes
    for the boring reason.
    """
    data = {
        "views": [
            {
                "title": "Küche",
                "cards": [
                    {"type": "markdown", "content": "a\nb\n"},
                    {"code": "0123", "on": "yes", "when": "2026-09-11"},
                    {"note": "space   \nafter", "sign": "🟢 ok"},
                ],
            }
        ]
    }
    text = yaml_io.dump(data)
    assert yaml_io.load(text) == yaml.load(text, Loader=yaml.SafeLoader) == data


def test_emoji_is_written_as_itself_not_escaped():
    """Guards the dumper against the switch `load` just made.

    libyaml's emitter escapes everything above the basic plane however
    `allow_unicode` is set: `\\U0001F7E2` instead of the sign, and a
    string holding one cannot be a block scalar any more. Measured
    2026-09-11, that is 4 of the 98 dashboards on the test bench - so a
    C emitter here would reformat them on the next save and record a
    change nobody made. If this test goes red, `_Dumper` has been given
    a C base class.
    """
    text = yaml_io.dump({"title": "🟢 ok", "body": "🟢\nsecond line"})
    assert "🟢 ok" in text
    assert "\\U" not in text
    assert "body: |" in text


def test_equal_dumps_always_come_from_equal_objects():
    """The one direction `operations.py`'s undo path can rely on.

    Round-trip fidelity makes this true unconditionally: if `dump(a)`
    and `dump(b)` are the same text `T`, then `load(T) == a` and
    `load(T) == b` both hold, so `a == b` - `load` cannot answer two
    different things for one text. `async_undo_change` uses the
    contrapositive of this to decide "this change is already taken
    back" without dumping either side - see the note there and in
    `test_restore.py` for what makes that safe in that one call.
    """
    samples = [
        {},
        {"a": 1},
        {"views": [{"title": "A"}]},
        {"views": [{"title": "A"}]},
        {"views": [{"title": "B"}]},
        {"style": "a\nb\nc"},
        {"code": "0123"},
        {"title": "🟢 ok"},
    ]
    for a in samples:
        for b in samples:
            if yaml_io.dump(a) == yaml_io.dump(b):
                assert a == b


def test_equal_objects_do_not_always_dump_to_equal_text():
    """The gap the other direction has, and why it is not a small one.

    Python dict equality does not care about key order; `dump()`, with
    `sort_keys=False`, renders each dict's keys in the order it holds
    them. Two dicts that compare equal can therefore dump to different
    text - determinism only promises that dumping *one* object twice
    gives the same text both times, never that two separately built,
    equal objects will. Documented here so nobody reaches for this
    module's docstring and concludes the general converse of the test
    above; `async_undo_change` does not need it, and says why not.
    """
    a = {"a": 1, "b": 2}
    b = {"b": 2, "a": 1}
    assert a == b
    assert yaml_io.dump(a) != yaml_io.dump(b)


@pytest.mark.skipif(not REAL_DASHBOARDS, reason="no real dashboards available")
@pytest.mark.parametrize("path", REAL_DASHBOARDS, ids=lambda p: p.name)
def test_a_changed_real_dashboard_dumps_to_different_text(path):
    """The direction the synthetic cases above cannot prove by themselves:
    that a real dashboard's own shape does not hide two different
    configurations behind one rendered text. One character changed in
    the first view's title is enough - if that ever dumped to the same
    text as the original, the short-circuit in `async_undo_change`
    would call a real change "already taken back".
    """
    config = json.loads(path.read_text(encoding="utf-8"))["data"]["config"]
    views = config.get("views") or []
    if not views:
        pytest.skip("no views to change")
    mutated = copy.deepcopy(config)
    mutated["views"][0]["title"] = (mutated["views"][0].get("title") or "") + " "
    assert mutated != config
    assert yaml_io.dump(mutated) != yaml_io.dump(config)


def test_load_state_reads_nothing_as_an_empty_configuration():
    # Every caller used to decide this for itself, as `load(x) or {}` in
    # several spellings - and `load(None)` raises.
    assert yaml_io.load_state(None) == {}
    assert yaml_io.load_state("") == {}
    assert yaml_io.load_state(yaml_io.dump({})) == {}
    assert yaml_io.load_state(yaml_io.dump({"views": []})) == {"views": []}
