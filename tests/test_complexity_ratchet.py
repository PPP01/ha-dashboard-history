"""Tests for the complexity ratchet.

The ratchet decides whether a commit may land, so its three refusals
are pinned here on made-up numbers - running ruff is not needed for
that, and the CI job that runs ruff checks the real code.
"""

import importlib.util
import pathlib

_PATH = pathlib.Path(__file__).resolve().parents[1] / "tools" / "complexity_ratchet.py"
_SPEC = importlib.util.spec_from_file_location("complexity_ratchet", _PATH)
ratchet = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ratchet)

BASELINE = {"a.py::big": {"issue": "#41", "C901": 20, "PLR0912": 14}}


def test_nothing_changed_is_clean():
    assert ratchet.compare({"a.py::big": {"C901": 20, "PLR0912": 14}}, BASELINE) == []


def test_a_function_new_to_the_list_is_refused():
    problems = ratchet.compare(
        {"a.py::big": {"C901": 20, "PLR0912": 14}, "a.py::fresh": {"C901": 11}}, BASELINE
    )
    assert problems == ["a.py::fresh: C901 is 11, over the limit and not in the baseline"]


def test_a_known_outlier_that_grew_is_refused():
    problems = ratchet.compare({"a.py::big": {"C901": 21, "PLR0912": 14}}, BASELINE)
    assert problems == ["a.py::big: C901 grew from 20 to 21"]


def test_an_improvement_asks_for_a_lower_baseline():
    problems = ratchet.compare({"a.py::big": {"C901": 18, "PLR0912": 14}}, BASELINE)
    assert problems == ["a.py::big: C901 fell from 20 to 18 - lower the baseline to 18"]


def test_a_value_back_within_the_limit_asks_for_removal():
    problems = ratchet.compare({"a.py::big": {"C901": 20}}, BASELINE)
    assert problems == ["a.py::big: PLR0912 is within the limit now - remove it from the baseline"]


def test_a_function_is_named_with_its_class_and_outer_function():
    source = (
        "class Store:\n"
        "    def method(self):\n"
        "        def inner():\n"
        "            pass\n"
        "def top():\n"
        "    pass\n"
    )
    assert ratchet.function_at(source, 2) == "Store.method"
    assert ratchet.function_at(source, 3) == "Store.method.inner"
    assert ratchet.function_at(source, 5) == "top"
