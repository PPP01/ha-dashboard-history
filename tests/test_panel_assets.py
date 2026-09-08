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
        "sidebar.js",
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


def test_the_panel_spells_the_default_dashboard_the_way_the_store_does():
    """The third name written twice, and the quietest of them.

    The store files the default dashboard under a key of its own, and
    `panel/sidebar.js` has to turn that key back into the url_path Home
    Assistant registered its panel under - there is no other way to find
    it among `hass.panels`. Change the key in const.py alone and nothing
    raises: the default dashboard simply stops being in the sidebar and
    drops into the fold below it, which reads like a decision somebody
    made rather than a name that drifted.
    """
    filed = re.search(
        r'^DEFAULT_DASHBOARD_KEY = "([^"]+)"',
        (PANEL / "const.py").read_text(encoding="utf-8"),
        re.M,
    )
    looked = re.search(
        r'^const DEFAULT_KEY = "([^"]+)";',
        (PANEL / "panel" / "sidebar.js").read_text(encoding="utf-8"),
        re.M,
    )
    assert filed and looked, "one of the two declarations was not found at all"
    assert filed.group(1) == looked.group(1)


def test_the_two_halves_of_the_search_look_at_the_same_fields():
    """One rule about what counts as a hit, written on both sides.

    The panel filters what it has already loaded before it asks the
    server, so the common search costs no round trip - task 8 of the
    plan calls for exactly that, and `_searchNote` says out loud how far
    each step looked. The price is two copies of the rule, and nothing
    in either file would notice a field added to one of them: the same
    silent drift the event name above is guarded against, and the same
    nine milliseconds to catch it.

    Compared as field names, not as code. The four kinds are a change's
    generated message, a person's own description, and the title,
    description and number of every version sitting on that state.

    Not compared, and deliberately different: `store.search_changes`
    folds case with `casefold()` and the panel lowercases. The two part
    company over `ß`, so `strasse` finds a row saying `Straße` on the
    server and misses it in the panel. That is the harmless direction -
    a miss up there escalates and arrives at the server, which then
    finds it - and it is the only harmless one, because a local hit the
    server would not have made stands as the whole answer with nothing
    to correct it. JavaScript has no casefold; if these two are ever
    brought closer together, the panel must not end up the stronger of
    the pair. Both files say so where somebody would change it.
    """
    # How a version is joined to a change, and how the panel reaches a
    # row's versions. Neither is a thing either side searches.
    joining = {"revision", "versions"}

    store = (PANEL / "store.py").read_text(encoding="utf-8")
    remote_body = store[
        store.index("    def search_changes(") : store.index("    def descriptions(")
    ]
    # `said` is the version's description as a reader sees it - the
    # marker on an automatic version stripped off - so it reaches the
    # word list through `read_description(version.description)` and is
    # counted by the attribute it is read from.
    remote = set(re.findall(r"\b(?:change|version)\.(\w+)", remote_body)) - joining

    panel = (PANEL / "panel.js").read_text(encoding="utf-8")
    local_body = panel[
        panel.index("  _wordsOf(change) {") : panel.index("  _localMatches() {")
    ]
    local = set(re.findall(r"\b(?:change|v)\.(\w+)", local_body)) - joining

    assert remote == local == {"message", "description", "name", "title"}

    # The simple mode's own filter runs over the version list alone, and
    # it is the third copy of the version half of the same rule.
    versions_body = panel[
        panel.index("  _matchingVersions() {") : panel.index("  _shown() {")
    ]
    versions = set(re.findall(r"\bv\.(\w+)", versions_body))
    assert versions == {"name", "title", "description"}
