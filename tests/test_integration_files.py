"""The files Home Assistant reads before a line of this code runs.

A config flow without translations shows its step as the bare word
"user" and its abort reason as "already_configured", and hassfest - which
HACS runs on a published integration - reports the missing file. Nothing
in the Python suite would notice either: these files are read by Home
Assistant's frontend and by the validator, never by the integration.
"""

import json

from conftest import PACKAGE


def _strings():
    return json.loads((PACKAGE / "strings.json").read_text(encoding="utf-8"))


def test_the_config_flow_step_has_words():
    step = _strings()["config"]["step"]["user"]
    assert step["title"] and step["description"]


def test_the_single_instance_refusal_has_words():
    # config_flow.py aborts with _abort_if_unique_id_configured, whose
    # reason is "already_configured".
    assert _strings()["config"]["abort"]["already_configured"]


def test_the_english_translation_is_the_strings_file():
    # Home Assistant reads translations/<lang>.json, hassfest reads
    # strings.json. In core the second is generated from the first; a
    # custom integration ships both, and they must not drift apart.
    english = json.loads((PACKAGE / "translations" / "en.json").read_text(encoding="utf-8"))
    assert english == _strings()
