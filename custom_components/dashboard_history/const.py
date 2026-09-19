"""Constants for the Dashboard History integration."""

from datetime import timedelta

import voluptuous as vol
from homeassistant.const import Platform

DOMAIN = "dashboard_history"

# The shape of `keep_as_version`, in one place because it has two doors.
# The WebSocket command and the service both take it, and while it was
# written out twice they disagreed: one required a title, the other
# accepted any dict at all - so `keep_as_version: {}` with `confirm:
# true` made a real tag with an empty title. A schema stated once cannot
# drift from itself.
#
# Such a tag can be taken away since decision 18, and the schema is
# still the right place to stop it being made: a version somebody has to
# create and then remove again is a fault, not a way of working. The
# sentence here used to end "and nothing in this integration can delete
# a version again", which excused the gap instead of arguing the rule.
#
# Shaped here, never judged: an unknown level is answered by operations
# with a sentence the panel can show, and a schema that refused first
# would take that sentence away.
KEEP_AS_VERSION = vol.Any(
    None,
    vol.Schema(
        {
            vol.Optional("level", default="patch"): str,
            vol.Required("title"): str,
            vol.Optional("description", default=""): str,
        }
    ),
)

# Home Assistant fires this when a dashboard configuration is saved.
EVENT_LOVELACE_UPDATED = "lovelace_updated"

# The default dashboard has url_path None; we store it under this key.
# It deliberately starts with an underscore: a url_path never can, so this
# cannot collide with a real dashboard. Installations do exist that have a
# dashboard registered under the url_path "lovelace".
DEFAULT_DASHBOARD_KEY = "_default"

# Directory inside the configuration folder that holds our git repository.
REPO_DIRNAME = "dashboard_history"

# The sidebar panel. The url_path needs a hyphen; the domain has none.
PANEL_URL_PATH = "dashboard-history"
PANEL_TITLE = "Dashboard History"
PANEL_ICON = "mdi:history"
PANEL_COMPONENT = "dashboard-history-panel"
# The integration version, and only the fallback for the panel URL: the
# cache key is a digest of panel.js and every part it is built from (see
# panel.py). Keeping a hand-maintained number as the cache key served
# everyone a stale panel until somebody remembered to raise it.
PANEL_VERSION = "0.7.1"

# Fired once the recorder has written something, naming the dashboards it
# wrote. The panel listens for this and not for `lovelace_updated`,
# because that one arrives *before* the commit exists: measured on
# 2026-09-03, restore_state returned after 26 ms and the commit landed
# 150 ms later. A panel refreshing in that window reads a history whose
# newest entry is the state it just replaced - so nothing matches the
# live configuration, nothing is crowned, and the page looks broken.
EVENT_HISTORY_UPDATED = "dashboard_history_updated"

# How far `forget` has got. Its own event rather than a field on the one
# above, because that one means "the history grew, go and read it again"
# and every listener acts on it - while this one means "still working,
# nothing to read yet". Measured on the test bench: a forget takes 24 s
# on its own and up to 76 s while the panel keeps asking, and a spinner
# standing still that long is why somebody reloads mid-rewrite.
EVENT_FORGET_PROGRESS = "dashboard_history_forget_progress"

# Seconds to wait before reconciling after a panel changed. Long enough to
# collapse the burst Home Assistant fires while starting up.
RECONCILE_DELAY = 10

# Whether a version is made for the state at the end of each day. On by
# default: the simple mode of decision 17 shows nothing but versions, and
# an installation that has to be configured before it works is one that
# does not work. Switched off by people who keep their own milestones.
OPTION_DAILY_VERSIONS = "daily_versions"

# The first entity platform of this integration. A list, because
# `async_forward_entry_setups` and `async_unload_platforms` both want one
# and a mismatch between the two leaves entities behind after a reload.
PLATFORMS = [Platform.SENSOR]

# How often the measurement is taken when nothing is being recorded. The
# event does the rest, and does it sooner. Measured before it was set;
# see the plan of 2026-09-19, task 4.
MEASURE_INTERVAL = timedelta(minutes=15)

# Where the per-installation secret behind the report ids lives, inside
# `entry.data`. Not in the repository folder: that is the one directory
# the README invites people to look into, and it is copied as a whole by
# anyone who shares their history to help with a bug.
DATA_REPORT_SECRET = "report_secret"
