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


def test_the_options_step_has_words():
    # Without them the switch appears in the interface as the bare word
    # "daily_versions", and hassfest - which HACS runs on a published
    # integration - reports the gap.
    step = _strings()["options"]["step"]["init"]
    assert step["title"] and step["description"]


def test_the_switch_says_what_it_does_and_what_it_does_not():
    # The explanation carries the sentence that matters: nothing is
    # deleted either way. A switch about versions on a tool whose whole
    # promise is that nothing is lost has to say so where it is read.
    step = _strings()["options"]["step"]["init"]
    assert step["data"]["daily_versions"]
    assert "deleted" in step["data_description"]["daily_versions"]


def test_the_option_the_code_writes_is_the_one_the_words_describe():
    # The two halves of the switch live in two files that nothing joins:
    # `const.py` names the key the options flow writes, `strings.json`
    # names the key the interface puts a label on. Rename one and the
    # switch appears as a bare `daily_versions` with no test to notice.
    #
    # Read as text, not imported: `const.py` pulls in `voluptuous`
    # through the package, and this suite runs without Home Assistant.
    source = (PACKAGE / "const.py").read_text(encoding="utf-8")
    assert 'OPTION_DAILY_VERSIONS = "daily_versions"' in source
    assert "daily_versions" in _strings()["options"]["step"]["init"]["data"]
