"""Make the integration importable in plain pytest.

Only the Home-Assistant-free modules are imported this way, so the
package's __init__ (which imports Home Assistant) is never executed.
"""

import pathlib
import sys

_PACKAGE = (
    pathlib.Path(__file__).resolve().parents[1]
    / "custom_components"
    / "dashboard_history"
)
sys.path.insert(0, str(_PACKAGE))
