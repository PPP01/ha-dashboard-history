"""Tests for the deterministic YAML representation."""

import json
import pathlib

import pytest
import yaml_io

# Real dashboards from the installation this was built against. Optional:
# without them the synthetic cases still run.
_STORAGE = pathlib.Path("/path/to/home-assistant/.storage")
REAL_DASHBOARDS = sorted(_STORAGE.glob("lovelace.*")) if _STORAGE.is_dir() else []


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
