"""The report a tester can hand back, and nothing that identifies them.

Free of Home Assistant on purpose. The one test that matters in this
module - that no dashboard name, path or title survives into the file -
has to run in plain `pytest`, or it is the least often executed test in
the project. See the spec, decision B6.

What this module builds is the `data` block of a diagnostics download.
Home Assistant wraps its own envelope around it (system info including
the timezone, every installed custom integration, the manifest). That
envelope is outside this module's reach and outside its promise; what
is promised here is that this block says nothing about the dashboards
of the installation it came from.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime

import yaml

SCHEMA = 1


def new_secret() -> str:
    """A fresh per-installation secret for the report ids."""
    return secrets.token_hex(16)


def dashboard_id(key: str, secret: str) -> str:
    """A stable, opaque name for one dashboard.

    Keyed, not plain. Dashboard names are short and ordinary -
    `wohnzimmer`, `energie`, `garten` - and a dictionary resolves an
    unsalted hash of one in seconds. A plain digest would claim an
    irreversibility it does not have.

    `hmac` rather than hashing the two strings glued together: it is one
    line of the standard library either way, and nobody has to decide
    later which of the two came first or what separated them.

    Eight hex characters, short enough to say out loud in an issue. At
    fifty dashboards the chance of two colliding is about 3 in 10
    million; should it ever happen, the length grows to twelve - not
    beforehand on suspicion.
    """
    digest = hmac.new(secret.encode("utf-8"), key.encode("utf-8"), hashlib.sha256)
    return digest.hexdigest()[:8]


def _day(seconds: int | None) -> str | None:
    """A timestamp as a day, in UTC, or None.

    Day-granular everywhere, including the newest capture, although the
    sensor carries the full timestamp locally. A time of day says
    nothing about size and something about the habits of whoever sent
    the file.
    """
    if not seconds:
        return None
    return datetime.fromtimestamp(seconds, UTC).strftime("%Y-%m-%d")


def _environment() -> dict:
    """The two things Home Assistant's own envelope does not carry.

    Everything else - HA version, Python version, architecture,
    installation type, this integration's manifest - is already in the
    envelope, and a value reported twice is a value that can disagree
    with itself.
    """
    try:
        import dulwich

        version = ".".join(str(part) for part in dulwich.__version__)
    except Exception:  # noqa: BLE001
        version = None
    return {
        "dulwich": version,
        # Decides a factor of 8-9 when loading, and without it no other
        # number in this file can be compared with anybody else's. See
        # `.claude/lessons.md`.
        "yaml_c_loader": hasattr(yaml, "CSafeLoader"),
    }


def build(
    measurement,
    secret: str,
    *,
    daily_versions: bool,
    measured_at: float | None,
    stale: bool,
) -> dict:
    """The `data` block, built field by field.

    `measurement` may be `None`, meaning no measurement has ever
    succeeded. That is reported as empty `totals` rather than as zeros,
    because zeros are what a real but empty history looks like.

    Additive, never redacted afterwards. Home Assistant offers
    `async_redact_data` to black out fields on the way out, and that is
    the wrong way round: whoever collects everything and then strikes
    some of it out publishes, at the next new field, exactly the one
    nobody thought of. What is not named here does not exist in the
    result.
    """
    if measurement is None:
        # Never measured, which is not the same as measured and empty.
        # An empty history has a `totals` block of honest zeros; a
        # measurement that never happened has no totals at all, and a
        # reader has to be able to tell the two apart. Spec, B10.
        return {
            "schema": SCHEMA,
            "measured_at": None,
            "stale": True,
            "environment": _environment(),
            "settings": {"daily_versions": daily_versions},
            "totals": {},
            "dashboards": [],
        }
    rows = [
        {
            "id": dashboard_id(facts.key, secret),
            "revisions": facts.revisions,
            "bytes": facts.bytes,
            "versions": facts.versions,
            "first": _day(facts.first),
            "last": _day(facts.last),
            "gone": facts.gone,
        }
        for facts in measurement.dashboards
    ]
    gone = sum(1 for facts in measurement.dashboards if facts.gone)
    live = len(measurement.dashboards) - gone
    return {
        "schema": SCHEMA,
        "measured_at": (
            datetime.fromtimestamp(measured_at, UTC).isoformat()
            if measured_at
            else None
        ),
        "stale": stale,
        "environment": _environment(),
        "settings": {"daily_versions": daily_versions},
        "totals": {
            "dashboards_live": live,
            "dashboards_gone": gone,
            # Written out rather than left to be worked out, so that an
            # inconsistency in the report shows up instead of cancelling
            # itself.
            "dashboards_ever": len(measurement.dashboards),
            "revisions": measurement.revisions,
            "versions": measurement.versions,
            "oldest": _day(measurement.oldest),
            "newest": _day(measurement.newest),
            "bytes_logical": measurement.bytes_logical,
            "bytes_allocated": measurement.bytes_allocated,
            "bytes_git_logical": measurement.bytes_git_logical,
            "bytes_worktree_logical": measurement.bytes_worktree_logical,
            "loose_objects": measurement.loose_objects,
            "packs": measurement.packs,
        },
        "dashboards": rows,
    }
