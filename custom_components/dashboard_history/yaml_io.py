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
    """A dumper that renders multi-line strings as readable blocks."""


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
    return yaml.safe_load(text)
