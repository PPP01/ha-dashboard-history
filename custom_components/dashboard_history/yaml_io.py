"""Deterministic YAML representation of dashboard configurations.

Two properties matter here, and both are load-bearing.

Determinism: an unchanged configuration must produce byte-identical
output, otherwise every save would create a commit that records nothing.

Round-trip fidelity: whatever goes in must come back out unchanged. A
restore writes this back into a live dashboard, so a lossy representation
would corrupt it.
"""

from __future__ import annotations

import yaml

HEADER = (
    "# Written by the dashboard_history integration.\n"
    "# Do not edit by hand; edit dashboards in the Home Assistant UI.\n"
)

# PyYAML ships two parsers and chooses neither for you: `yaml.safe_load`
# always takes the pure-Python one, even where libyaml sits right beside
# it. Measured in the test container on 2026-09-11 against the bench
# repository, a 262 KiB dashboard: 501 ms pure Python, 54.8 ms through
# libyaml - and opening one row of the panel parses two states, which is
# where the better part of a second came from.
#
# Checked before switching, over all 98 dashboards at HEAD of the bench
# repository: both parsers answer equal objects, and `dump()` of either
# answer is byte-identical. Nothing about what gets written changes.
#
# The dumper stays pure Python on purpose - see `_Dumper`.
_Loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)


def _can_use_block(text: str) -> bool:
    """Whether a block scalar would preserve the string exactly.

    PyYAML refuses the block style in these cases anyway; checking here
    makes the behaviour explicit rather than implicit.
    """
    if "\n" not in text:
        return False
    # Written as escapes on purpose: as literal characters they are
    # invisible in an editor, and str.splitlines() splits on them, so any
    # tool that processes this file line by line silently corrupts it.
    if any(char in text for char in ("\r", "\x85", "\u2028", "\u2029")):
        return False
    if text[:1] in (" ", "\t"):
        return False
    for line in text.split("\n"):
        if line != line.rstrip() or "\t" in line:
            return False
    return True


class _Dumper(yaml.SafeDumper):
    """A dumper that renders multi-line strings as readable blocks.

    Pure Python where `load` takes libyaml, and not by oversight.
    libyaml's emitter escapes every character above the basic plane -
    emoji - as `\\U0001F7E2` however `allow_unicode` is set, and a string
    holding one can then no longer be a block scalar at all. Measured on
    2026-09-11: `"\\U0001F7E2 ok"` where pure Python writes the sign
    itself, and 4 of the 98 dashboards in the bench repository came out
    as different bytes. Characters inside the plane - umlauts, the check
    mark - are emitted alike by both.

    Determinism is what this module is for, and a title with an emoji in
    it is an ordinary thing to put on a dashboard. Switching to the C
    emitter for its 2.2x would rewrite those dashboards on the next save
    and record one enormous change that nobody made.
    """


def _represent_str(dumper, data):
    if _can_use_block(data):
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_Dumper.add_representer(str, _represent_str)


def dump(data) -> str:
    """Render a configuration as deterministic YAML."""
    body = yaml.dump(
        data,
        Dumper=_Dumper,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=4096,
        indent=2,
    )
    return HEADER + body


def load(text: str):
    """Parse YAML produced by `dump`."""
    return yaml.load(text, Loader=_Loader)


def load_state(text: str | None) -> dict:
    """A recorded dashboard text as a configuration; nothing as `{}`.

    The one place that decides what an absent or empty text means. It
    used to be decided at every caller, as `load(x) or {}` in five
    spellings - and `load(None)` raises, so each had its own guard.
    """
    if not text:
        return {}
    return load(text) or {}
