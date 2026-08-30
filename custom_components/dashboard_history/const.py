"""Constants for the Dashboard History integration."""

DOMAIN = "dashboard_history"

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
# Bumped whenever panel.js changes, so browsers do not serve a stale copy.
PANEL_VERSION = "0.1.0"
