"""Make the integration importable in plain pytest.

Only the Home-Assistant-free modules are imported this way, so the
package's __init__ (which imports Home Assistant) is never executed.
"""

import os
import pathlib
import sys

# Exported: the file-based tests read the package's assets from here
# rather than each spelling the path out again.
PACKAGE = (
    pathlib.Path(__file__).resolve().parents[1]
    / "custom_components"
    / "dashboard_history"
)
sys.path.insert(0, str(PACKAGE))

# Some tests can run against real dashboards, which is worth a lot: the
# synthetic cards are four, a real installation has hundreds, and the
# weak matching was found to cover only 57 % of them that way. Where they
# live is a detail of somebody's machine, though, and this repository is
# public - so the path comes from the environment, or from a local file
# that git ignores. Neither is required; without one those cases skip and
# say so.
_LOCAL_STORAGE = pathlib.Path(__file__).with_name(".real-storage")
if not os.environ.get("DASHBOARD_HISTORY_REAL_STORAGE") and _LOCAL_STORAGE.exists():
    for line in _LOCAL_STORAGE.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            os.environ["DASHBOARD_HISTORY_REAL_STORAGE"] = line.strip()
            break
