"""Static traps in the panel's JavaScript that no Python test would meet.

These are not tests of behaviour. They guard two mistakes that are
invisible until a browser refuses to load the panel - and on this
project that costs a container restart to find out, because Home
Assistant serves the file and the browser reports the error to its own
console rather than to anything a check run reads.

Deliberately here rather than in the integration run: this needs no Home
Assistant at all, and a trap that can be caught in nine milliseconds
should not wait for a container.
"""

import pathlib
import re

PANEL = pathlib.Path(__file__).resolve().parent.parent / "custom_components" / (
    "dashboard_history"
)
PARTS = sorted((PANEL / "panel").rglob("*.js"))


def test_the_parts_are_found_at_all():
    # Without this the two tests below would pass by having nothing to
    # look at, which is the one way a guard fails silently. Named rather
    # than counted: a part that quietly disappears is exactly the kind of
    # loss this list is here to notice.
    assert [path.name for path in PARTS] == [
        "dialogs.js",
        "render.js",
        "rows.js",
        "simple.js",
        "style.js",
    ]


def test_the_style_is_one_unbroken_template_literal():
    """Exactly two backticks in style.js: the ones that delimit it.

    `STYLE` is a template literal holding the whole stylesheet, so a
    backtick anywhere inside it ends the string early. Measured on
    2026-09-03: a CSS comment written as `/* like `this` */` turned the
    rest of the sheet into code and the panel died with "Unexpected
    identifier", after a container restart and a seven-minute browser
    run to find out.
    """
    style = (PANEL / "panel" / "style.js").read_text(encoding="utf-8")
    assert style.count("`") == 2


def test_no_substitution_hides_in_the_stylesheet():
    """`${` inside the stylesheet would be evaluated, not printed.

    CSS has no use for it, so its presence in style.js is a mistake
    rather than an intention. render.js builds markup and uses it
    everywhere, which is why only the stylesheet is asked.
    """
    assert "${" not in (PANEL / "panel" / "style.js").read_text(encoding="utf-8")


def test_the_panel_listens_for_the_event_the_recorder_fires():
    """One name, two languages, and nothing else to keep them together.

    The recorder announces a written commit on the bus and the panel
    subscribes to it; that is the whole live-update path. A rename on one
    side alone breaks it silently - the page simply stops refreshing, and
    nothing anywhere reports an error. Nine milliseconds here instead.
    """
    fired = re.search(
        r'^EVENT_HISTORY_UPDATED = "([^"]+)"',
        (PANEL / "const.py").read_text(encoding="utf-8"),
        re.M,
    )
    heard = re.search(
        r'^const EVENT_RECORDED = "([^"]+)";',
        (PANEL / "panel.js").read_text(encoding="utf-8"),
        re.M,
    )
    assert fired and heard, "one of the two declarations was not found at all"
    assert fired.group(1) == heard.group(1)
