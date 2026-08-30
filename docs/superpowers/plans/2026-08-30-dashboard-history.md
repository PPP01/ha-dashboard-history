# Dashboard-Historie — Implementierungsplan

> **Für agentische Bearbeiter:** ERFORDERLICHES SUB-SKILL: `superpowers:subagent-driven-development` (empfohlen) oder `superpowers:executing-plans`, um diesen Plan Task für Task umzusetzen. Die Schritte nutzen Checkbox-Syntax (`- [ ]`).

**Goal:** Eine Home-Assistant-Integration, die jede Dashboard-Änderung erfasst, den Verlauf pro Dashboard zugänglich macht und Verschwundenes gezielt zurückholt.

**Architecture:** Die Integration horcht auf `lovelace_updated`, holt den Stand **direkt aus dem Speicher** statt aus der Datei und legt ihn als Commit in einem eigenen git-Repository ab, das sie allein verwaltet. Die Einordnung der Änderungen und die Umkehrung sind reine Logik ohne Home-Assistant-Bezug und damit in reinem pytest prüfbar.

**Tech Stack:** Python 3.12+ (Container: 3.14.6), Home Assistant 2026.8.3, `dulwich` (reine Python-Umsetzung von git), PyYAML, pytest.

**Spec:** `docs/superpowers/specs/2026-08-30-dashboard-history-design.md`

## Vor der Umsetzung geprüft (2026-08-30)

Der Code dieses Plans wurde extrahiert und ausgeführt, bevor er umgesetzt
wurde. Sieben Befunde sind bereits eingearbeitet; sie stehen hier, damit die
Abweichungen von der ersten Fassung nachvollziehbar bleiben.

| Befund | Folge | Nachweis |
|---|---|---|
| `restore.py` nutzte einen relativen Import, den die flache Testeinbindung nicht auflösen kann | Task 5 hätte nie grün werden können | `ImportError: attempted relative import with no known parent package` |
| `summarize` verdoppelte umsortierte Karten | Test erwartete 2, Code lieferte 4 | Testlauf |
| `write_snapshot` verglich gegen die Datei statt gegen HEAD, und dulwich sperrt den Index | Von acht parallelen Commits kam einer an; ein so verlorener Stand blieb **dauerhaft und stumm** aus der Historie | gemessen, siehe Kommentar in `store.py` |
| Der Storage-Rückfall verwechselte `id` mit `url_path` | `energie_2.yaml` neben `energie-2.yaml` — jede Historie hätte sich gegabelt | echte Registry: `id=energie_2`, `url_path=energie-2` |
| `ConfigNotFound` wurde als Ausnahme protokolliert | Vollständiger Traceback bei jedem Speichern, weil das Standard-Dashboard keine Konfiguration hat | `.storage/lovelace` existiert nicht; Spook behandelt es als `debug` |
| `lovelace` fehlte als Abhängigkeit im Manifest | `hass.data["lovelace"]` beim Einrichten nicht garantiert vorhanden | HA-Einrichtungsreihenfolge |
| `DEFAULT_DASHBOARD_KEY = "lovelace"` | Kollision mit dem real vorhandenen Dashboard `url_path: lovelace` | echte Registry |

Bestätigt hat die Prüfung außerdem: `dulwich==1.2.14` ist installiert und
trägt, ein Commit des 262-KB-Dashboards dauert **31,2 ms** (Spec: 30 ms),
`hass.data["lovelace"].dashboards` ist die richtige Form — spook und icloud3
greifen auf derselben Anlage genau so zu —, und `yaml_io` bringt alle zehn
echten Dashboards verlustfrei und deterministisch durch den Round-Trip.

## Global Constraints

Diese Vorgaben gelten für **jeden** Task.

- **Der gesamte Code ist englisch.** Bezeichner, Kommentare, Docstrings, Dienstnamen, Log-Meldungen und README. Das Projekt soll veröffentlichungsfähig sein; ein Mitwirkender darf nirgends auf Deutsch stoßen. Spec, Plan und Commit-Botschaften bleiben deutsch.
- **Kein Systemaufruf von `git`.** Ausschließlich `dulwich`. Begründung und Messwerte stehen in Entscheidung 3 der Spec.
- **Nichts blockiert den Start von Home Assistant.** Ein Fehler beim Erfassen wird protokolliert und verschluckt; er darf weder `async_setup_entry` aufhalten noch ein Speichern verhindern.
- **Keine Home-Assistant-Interna abfangen oder ersetzen.** Kein Monkey-Patching von WebSocket-Befehlen oder Diensten.
- **`yaml_io.py`, `analyze.py` und `restore.py` bleiben Home-Assistant-frei** — kein `import homeassistant` darin. Sie sind das Herz und müssen ohne laufende Installation prüfbar sein.
- **Blockierende Arbeit gehört in einen Executor.** Ein Commit dauert rund 30 ms; das hat im Event-Loop nichts verloren. Alle `store`-Aufrufe laufen über `hass.async_add_executor_job`.
- **Nichts wird ohne Vorschau geschrieben.** Jeder Dienst, der ein Dashboard verändert, verlangt ein ausdrückliches Kennzeichen und liefert sonst nur den Diff.
- **Tests laufen aus dem Projekt-Root:** `python3 -m pytest tests/ -v`.
- **Commit-Format:** Subject im Imperativ, erster Buchstabe groß, max. 50 Zeichen. Leerzeile. Body max. 72 Zeichen pro Zeile, begründet das *Warum*. Abschluss mit `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

## Dateistruktur

| Datei | Verantwortung | HA-frei |
|---|---|---|
| `custom_components/dashboard_history/manifest.json` | Metadaten, Abhängigkeit `dulwich` | — |
| `custom_components/dashboard_history/const.py` | Domain und Konstanten | ja |
| `custom_components/dashboard_history/__init__.py` | Einrichtung, Config-Entry, Aufräumen | nein |
| `custom_components/dashboard_history/config_flow.py` | Einrichtungsdialog mit einem Klick | nein |
| `custom_components/dashboard_history/snapshot.py` | Dashboard-Konfigurationen aus HA holen | nein |
| `custom_components/dashboard_history/yaml_io.py` | Deterministische YAML-Ausgabe | **ja** |
| `custom_components/dashboard_history/analyze.py` | Änderungen einordnen | **ja** |
| `custom_components/dashboard_history/restore.py` | Umkehrung anwenden | **ja** |
| `custom_components/dashboard_history/store.py` | Das Repository (dulwich) | Kern ja |
| `custom_components/dashboard_history/capture.py` | Horchen, Stand holen, ablegen | nein |
| `custom_components/dashboard_history/services.py` + `services.yaml` | Dienste für die Entwicklerwerkzeuge | nein |
| `tests/…` | pytest für die HA-freien Teile und den Speicher | — |
| `hacs.json`, `README.md` | Verpackung | — |

---

### Task 1: Gerüst und Nachweis des Zugriffswegs

Der erste Task beantwortet die einzige offene Frage der Spec: Kommt der Dashboard-Stand verlässlich aus dem Speicher? Davon hängt der Hauptvorteil gegenüber einem Skript ab.

**Files:**
- Create: `custom_components/dashboard_history/manifest.json`, `const.py`, `__init__.py`, `config_flow.py`, `snapshot.py`, `services.yaml`
- Create: `hacs.json`, `README.md`

**Interfaces:**
- Consumes: nichts
- Produces:
  - `const.DOMAIN = "dashboard_history"`
  - `async_get_all_configs(hass) -> dict[str, dict]` — Dashboard-Schlüssel auf Konfiguration
  - `async_get_config(hass, key) -> dict | None`
  - `dashboard_key(url_path: str | None) -> str` — `None` wird zu `"lovelace"`, sonst der `url_path`

- [x] **Schritt 1: Metadaten und Konstanten anlegen**

`custom_components/dashboard_history/manifest.json`:

```json
{
  "domain": "dashboard_history",
  "name": "Dashboard History",
  "codeowners": ["@PPP01"],
  "config_flow": true,
  "dependencies": ["lovelace"],
  "documentation": "https://github.com/PPP01/ha-dashboard-history",
  "iot_class": "local_push",
  "issue_tracker": "https://github.com/PPP01/ha-dashboard-history/issues",
  "requirements": ["dulwich==1.2.14"],
  "version": "0.1.0"
}
```

`hacs.json`:

```json
{
  "name": "Dashboard History",
  "homeassistant": "2024.1.0",
  "render_readme": true
}
```

`custom_components/dashboard_history/const.py`:

```python
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
```

- [x] **Schritt 2: Den Zugriffsweg schreiben**

`custom_components/dashboard_history/snapshot.py`:

```python
"""Reading dashboard configurations straight from Home Assistant.

Home Assistant fires `lovelace_updated` *before* it writes the storage
file, so anything that reads the file has to wait and may silently read
the previous state. An integration runs inside Home Assistant and can ask
the Lovelace objects directly, which removes that race entirely.

The lookup is deliberately defensive: `hass.data["lovelace"]` has changed
shape across releases, so we accept both the dataclass and the plain dict
form, and fall back to reading the storage files if neither is present.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.lovelace.const import ConfigNotFound
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DEFAULT_DASHBOARD_KEY

_LOGGER = logging.getLogger(__name__)

LOVELACE_DATA_KEY = "lovelace"

# The value LovelaceConfig.mode returns for a storage dashboard. Compared
# as a literal on purpose: only ConfigNotFound's import path is verified
# against a running installation, and a wrong import would break setup.
MODE_STORAGE = "storage"

# Home Assistant's own storage keys. The default dashboard is stored under
# a bare "lovelace"; every other dashboard under its *id*, which is not the
# same string as its url_path (id "energie_2" vs url_path "energie-2").
_STORAGE_KEY_DEFAULT = "lovelace"
_STORAGE_KEY_TEMPLATE = "lovelace.{}"


def dashboard_key(url_path: str | None) -> str:
    """Map a dashboard url_path to the key we store it under."""
    return url_path or DEFAULT_DASHBOARD_KEY


def _lovelace_dashboards(hass: HomeAssistant) -> dict[str | None, Any] | None:
    """Return Home Assistant's in-memory dashboard objects, or None."""
    data = hass.data.get(LOVELACE_DATA_KEY)
    if data is None:
        return None
    dashboards = getattr(data, "dashboards", None)
    if dashboards is None and isinstance(data, dict):
        dashboards = data.get("dashboards")
    return dashboards if isinstance(dashboards, dict) else None


async def async_get_all_configs(hass: HomeAssistant) -> dict[str, dict]:
    """Return every storage-mode dashboard configuration, keyed by our key."""
    dashboards = _lovelace_dashboards(hass)
    if dashboards is None:
        _LOGGER.warning(
            "Lovelace data not available in the expected shape; "
            "falling back to reading storage files"
        )
        return await _async_get_all_configs_from_storage(hass)

    result: dict[str, dict] = {}
    for url_path, dashboard in dashboards.items():
        if getattr(dashboard, "mode", MODE_STORAGE) != MODE_STORAGE:
            # A YAML dashboard already lives in a file the user versions
            # themselves, and it cannot be written back at all.
            continue
        try:
            config = await dashboard.async_load(False)
        except ConfigNotFound:
            # Entirely normal: a dashboard that has never been saved. The
            # default dashboard is usually in this state.
            _LOGGER.debug("Dashboard %s has no stored configuration", url_path)
            continue
        except Exception:  # noqa: BLE001 - a single bad dashboard must not stop the rest
            _LOGGER.exception("Could not load dashboard %s", url_path)
            continue
        if isinstance(config, dict):
            result[dashboard_key(url_path)] = config
    return result


async def async_get_config(hass: HomeAssistant, key: str) -> dict | None:
    """Return one dashboard configuration, or None if it does not exist."""
    return (await async_get_all_configs(hass)).get(key)


async def _async_get_all_configs_from_storage(hass: HomeAssistant) -> dict[str, dict]:
    """Fallback: read the storage files directly.

    Only used when the in-memory objects are not where we expect them. This
    path can read a state that is a fraction of a second old, which is why it
    is the fallback and not the default.
    """
    result: dict[str, dict] = {}
    store = Store(hass, 1, "lovelace_dashboards")
    registry = await store.async_load() or {}

    # (our key, Home Assistant's storage key) - the two differ, and mixing
    # them up would file the same dashboard under two different names.
    wanted = [(DEFAULT_DASHBOARD_KEY, _STORAGE_KEY_DEFAULT)]
    for item in registry.get("items", []):
        url_path = item.get("url_path")
        if url_path is None or "id" not in item:
            continue
        wanted.append((dashboard_key(url_path), _STORAGE_KEY_TEMPLATE.format(item["id"])))

    for key, storage_key in wanted:
        raw = await Store(hass, 1, storage_key).async_load()
        if isinstance(raw, dict) and isinstance(raw.get("config"), dict):
            result[key] = raw["config"]
    return result
```

- [x] **Schritt 3: Einrichtung und Einrichtungsdialog**

`custom_components/dashboard_history/config_flow.py`:

```python
"""Config flow: a single confirmation, there is nothing to configure yet."""

from __future__ import annotations

from homeassistant.config_entries import ConfigFlow

from .const import DOMAIN


class DashboardHistoryConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set the integration up from the user interface."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the single setup step."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is None:
            return self.async_show_form(step_id="user")
        return self.async_create_entry(title="Dashboard History", data={})
```

`custom_components/dashboard_history/__init__.py`:

```python
"""The Dashboard History integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set the integration up.

    Nothing here may raise: a broken history is an inconvenience, a broken
    Home Assistant start is not.
    """
    hass.data.setdefault(DOMAIN, {})
    _LOGGER.debug("Dashboard History set up")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Tear the integration down."""
    hass.data.pop(DOMAIN, None)
    return True
```

- [x] **Schritt 4: Nachweis-Dienst anlegen**

Ein Dienst, dessen einziger Zweck der Nachweis ist. Er bleibt dauerhaft, weil er bei Fehlersuche hilft.

`custom_components/dashboard_history/services.yaml`:

```yaml
debug_snapshot:
  name: Debug snapshot
  description: >-
    Return the dashboard configurations as the integration currently sees
    them. Useful to check that the integration can read them at all.
```

In `__init__.py` innerhalb von `async_setup_entry` ergänzen:

```python
    from homeassistant.core import ServiceCall, SupportsResponse

    from .snapshot import async_get_all_configs

    async def _debug_snapshot(call: ServiceCall) -> dict:
        configs = await async_get_all_configs(hass)
        return {
            "count": len(configs),
            "dashboards": {
                key: {"views": len(config.get("views") or [])}
                for key, config in sorted(configs.items())
            },
        }

    hass.services.async_register(
        DOMAIN, "debug_snapshot", _debug_snapshot,
        supports_response=SupportsResponse.ONLY,
    )
```

- [ ] **Schritt 5: In Home Assistant einrichten und den Zugriffsweg nachweisen**  ← **bestanden am 2026-08-30 an der eigenen Anlage**

Die Integration nach `/config/custom_components/dashboard_history/` kopieren oder verlinken, Home Assistant neu starten, unter *Einstellungen → Geräte & Dienste → Integration hinzufügen* »Dashboard History« hinzufügen.

Dann in den Entwicklerwerkzeugen `dashboard_history.debug_snapshot` ausführen.

**Erwartet:** Eine Antwort mit `count: 10` und je Dashboard der View-Anzahl.
Zehn, nicht zwoelf: Die Anlage hat zehn registrierte Dashboards, und das
Standard-Dashboard hat keine gespeicherte Konfiguration, wird also
uebersprungen. Die Zwoelf in einer frueheren Fassung stammte aus
`dashboards/*.yaml`, wo `_registry.yaml` und `_resources.yaml` mitzaehlten.

**Das ist der eigentliche Nachweis dieses Tasks.** Prüfe zusätzlich im Protokoll, ob die Warnung »Lovelace data not available in the expected shape« erscheint:

- **Erscheint sie nicht**, greift der Speicherweg — Entscheidung 1 der Spec ist bestätigt und der Rückfall bleibt ungenutzter Sicherheitsgurt.
- **Erscheint sie**, arbeitet die Integration über den Rückfall. Dann als Befund melden: Entscheidung 1 hält nicht, und der Erfassungs-Task braucht zusätzlich eine Wartezeit. Nicht selbst reparieren.

- [x] **Schritt 6: Committen**

```bash
git add custom_components/ hacs.json README.md
git commit -m "$(cat <<'MSG'
Lege das Gerüst der Integration an

Der Zugriff auf die Dashboard-Konfigurationen ist bewusst nachgiebig
gebaut: hass.data["lovelace"] hat über HA-Versionen die Form gewechselt,
deshalb werden beide bekannten Formen akzeptiert und die Storage-Dateien
bleiben als Rückfall.

Der Nachweis-Dienst bleibt dauerhaft erhalten - er beantwortet bei jeder
späteren Fehlersuche als Erstes die Frage, ob die Integration die
Dashboards überhaupt sieht.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
)"
```

---

### Task 2: Deterministische YAML-Ausgabe

**Files:**
- Create: `custom_components/dashboard_history/yaml_io.py`
- Create: `tests/conftest.py`, `tests/test_yaml_io.py`

**Interfaces:**
- Consumes: nichts
- Produces:
  - `dump(data) -> str` — deterministisch, mit statischem Kopfkommentar
  - `load(text: str)` — Gegenstück
  - `HEADER: str`

- [x] **Schritt 1: Test-Infrastruktur anlegen**

`tests/conftest.py`:

```python
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
```

- [x] **Schritt 2: Den fehlschlagenden Test schreiben**

`tests/test_yaml_io.py`:

```python
"""Tests for the deterministic YAML representation."""

import json
import os
import pathlib

import pytest
import yaml_io

# Real dashboards from the installation this was built against. Optional:
# without them the synthetic cases still run. Point
# DASHBOARD_HISTORY_REAL_STORAGE at any Home Assistant .storage directory
# to run these against your own dashboards.
_STORAGE = pathlib.Path(
    os.environ.get(
        "DASHBOARD_HISTORY_REAL_STORAGE",
        "/path/to/home-assistant/.storage",
    )
)
REAL_DASHBOARDS = sorted(_STORAGE.glob("lovelace.*")) if _STORAGE.is_dir() else []


def _body(text):
    """The YAML without the header comment."""
    return [line for line in text.splitlines() if not line.startswith("#")]


def test_round_trip_simple():
    data = {"views": [{"title": "Home", "cards": [{"type": "map"}]}]}
    assert yaml_io.load(yaml_io.dump(data)) == data


def test_round_trip_multiline():
    data = {"style": "ha-card {\n  border: none;\n}"}
    assert yaml_io.load(yaml_io.dump(data)) == data


def test_multiline_becomes_block_scalar():
    assert "style: |" in yaml_io.dump({"style": "a\nb\nc"})


def test_trailing_space_survives():
    # YAML cannot carry trailing spaces in a block scalar, so the dumper
    # must fall back to a quoted style rather than silently dropping them.
    data = {"style": "first line   \nsecond line"}
    text = yaml_io.dump(data)
    assert "style: |" not in text
    assert yaml_io.load(text) == data


def test_umlauts_stay_readable():
    text = yaml_io.dump({"title": "Küche"})
    assert "Küche" in text
    assert "\\u" not in text


def test_numeric_string_stays_a_string():
    data = {"code": "0123"}
    assert yaml_io.load(yaml_io.dump(data)) == data


def test_dump_is_stable():
    data = {"views": [{"title": "A"}]}
    assert yaml_io.dump(data) == yaml_io.dump(data)


def test_key_order_is_preserved():
    data = {"type": "tile", "entity": "sensor.a", "name": "A"}
    keys = [line.split(":")[0] for line in _body(yaml_io.dump(data)) if ":" in line]
    assert keys == ["type", "entity", "name"]


def test_header_carries_no_timestamp():
    # Anything varying between runs would produce a commit on every save.
    assert yaml_io.dump({"x": 1}) == yaml_io.dump({"x": 1})
    assert "20" not in yaml_io.HEADER


@pytest.mark.skipif(not REAL_DASHBOARDS, reason="no real dashboards available")
@pytest.mark.parametrize("path", REAL_DASHBOARDS, ids=lambda p: p.name)
def test_real_dashboards_survive_the_round_trip(path):
    """The synthetic cases above cannot cover what real dashboards contain.

    This is the test the spec asks for. It is skipped where the storage
    files are not reachable, so the suite still runs anywhere.
    """
    config = json.loads(path.read_text(encoding="utf-8"))["data"]["config"]
    text = yaml_io.dump(config)
    assert yaml_io.load(text) == config
    assert yaml_io.dump(config) == text
```

- [x] **Schritt 3: Tests laufen lassen, Fehlschlag bestätigen**

Ausführen: `python3 -m pytest tests/test_yaml_io.py -v`
Erwartet: FAIL mit `ModuleNotFoundError: No module named 'yaml_io'`

- [x] **Schritt 4: Implementierung schreiben**

`custom_components/dashboard_history/yaml_io.py`:

```python
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
```

- [x] **Schritt 5: Tests laufen lassen, Erfolg bestätigen**

Ausführen: `python3 -m pytest tests/test_yaml_io.py -v`
Erwartet: PASS, 9 synthetische Tests, dazu einer je echtem Dashboard (auf dieser Anlage 11, also 20)

- [x] **Schritt 6: Committen**

```bash
git add custom_components/dashboard_history/yaml_io.py tests/
git commit -m "$(cat <<'MSG'
Ergänze die deterministische YAML-Ausgabe

Zwei Eigenschaften tragen hier alles: Gleiche Eingabe muss byte-gleiche
Ausgabe erzeugen, sonst entstünde bei jedem Speichern ein Commit ohne
Inhalt. Und der Round-Trip muss verlustfrei sein, weil ein Restore diese
Daten in ein laufendes Dashboard zurückschreibt.

Zeilenende-Leerzeichen kann ein YAML-Block-Scalar nicht tragen; dort
fällt die Ausgabe auf gequotet zurück statt still zu kürzen.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
)"
```

---

### Task 3: Der Speicher

**Files:**
- Create: `custom_components/dashboard_history/store.py`
- Create: `tests/test_store.py`

**Interfaces:**
- Consumes: nichts (arbeitet auf Texten, nicht auf Konfigurationen)
- Produces:
  - `Change(revision: str, timestamp: int, message: str)`
  - `Version(name: str, revision: str, title: str, description: str)`
  - `HistoryStore(path)` mit `ensure()`, `write_snapshot(key, text, message) -> str | None`, `list_changes(key, limit=50) -> list[Change]`, `read_at(key, revision) -> str | None`, `create_version(name, title, description, revision=None)`, `list_versions() -> list[Version]`

- [x] **Schritt 1: Den fehlschlagenden Test schreiben**

`tests/test_store.py`:

```python
"""Tests for the git-backed history store."""

import threading

import pytest
from dulwich.repo import Repo
from store import HistoryStore


@pytest.fixture
def store(tmp_path):
    s = HistoryStore(tmp_path / "history")
    s.ensure()
    return s


def test_first_snapshot_creates_a_revision(store):
    assert store.write_snapshot("home", "a: 1\n", "first") is not None


def test_unchanged_snapshot_creates_nothing(store):
    store.write_snapshot("home", "a: 1\n", "first")
    assert store.write_snapshot("home", "a: 1\n", "second") is None


def test_changed_snapshot_creates_a_revision(store):
    store.write_snapshot("home", "a: 1\n", "first")
    assert store.write_snapshot("home", "a: 2\n", "second") is not None


def test_history_is_per_dashboard(store):
    store.write_snapshot("home", "a: 1\n", "home first")
    store.write_snapshot("other", "b: 1\n", "other first")
    store.write_snapshot("home", "a: 2\n", "home second")
    assert [c.message for c in store.list_changes("home")] == ["home second", "home first"]
    assert [c.message for c in store.list_changes("other")] == ["other first"]


def test_history_of_unknown_dashboard_is_empty(store):
    assert store.list_changes("nothing") == []


def test_history_of_empty_repository_is_empty(store):
    # No commit at all: there is no HEAD to walk.
    assert store.list_changes("home") == []


def test_read_at_returns_the_old_text(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("home", "a: 2\n", "second")
    assert store.read_at("home", first) == "a: 1\n"


def test_read_at_before_the_file_existed_returns_none(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("other", "b: 1\n", "other")
    assert store.read_at("other", first) is None


def test_version_marks_a_revision_without_changing_history(store):
    store.write_snapshot("home", "a: 1\n", "first")
    second = store.write_snapshot("home", "a: 2\n", "second")
    store.create_version("v1", "Kitchen rework", "Two cards moved.", second)
    versions = store.list_versions()
    assert [v.name for v in versions] == ["v1"]
    assert versions[0].title == "Kitchen rework"
    assert versions[0].description == "Two cards moved."
    assert versions[0].revision == second
    # The individual changes are still there and still separate.
    assert len(store.list_changes("home")) == 2


def test_the_temporary_file_is_never_tracked(store, tmp_path):
    # A leftover .tmp must never end up in the repository.
    store.write_snapshot("home", "a: 1\n", "first")
    (tmp_path / "history" / "home.yaml.tmp").write_text("junk", encoding="utf-8")
    store.write_snapshot("home", "a: 2\n", "second")
    repo = Repo(str(tmp_path / "history"))
    assert sorted(path.decode() for path in repo.open_index()) == ["home.yaml"]


def test_a_state_lost_before_the_commit_is_recorded_afterwards(store, tmp_path):
    # A crash between writing the file and committing leaves the file ahead
    # of the repository. Comparing against the file would drop that state
    # from the history for good and without a word; comparing against HEAD
    # picks it up on the next run.
    store.write_snapshot("home", "a: 1\n", "first")
    (tmp_path / "history" / "home.yaml").write_text("a: 2\n", encoding="utf-8")
    assert store.write_snapshot("home", "a: 2\n", "second") is not None
    assert [c.message for c in store.list_changes("home")] == ["second", "first"]


def test_an_unchanged_snapshot_repairs_the_working_tree(store, tmp_path):
    store.write_snapshot("home", "a: 1\n", "first")
    (tmp_path / "history" / "home.yaml").write_text("tampered\n", encoding="utf-8")
    assert store.write_snapshot("home", "a: 1\n", "again") is None
    assert (tmp_path / "history" / "home.yaml").read_text(encoding="utf-8") == "a: 1\n"


def test_parallel_writes_all_arrive(store):
    # dulwich holds an exclusive lock on the git index. Without serialising,
    # eight parallel writes let exactly one commit through.
    def write(number):
        store.write_snapshot(f"d{number}", f"n: {number}\n", f"commit {number}")

    threads = [threading.Thread(target=write, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert all(store.list_changes(f"d{i}") for i in range(8))
```

- [x] **Schritt 2: Tests laufen lassen, Fehlschlag bestätigen**

Ausführen: `python3 -m pytest tests/test_store.py -v`
Erwartet: FAIL mit `ModuleNotFoundError: No module named 'store'`

- [x] **Schritt 3: Implementierung schreiben**

`custom_components/dashboard_history/store.py`:

```python
"""The history store: a git repository the integration owns.

git is used as a storage engine, not as a user-facing tool. It gives
deduplication, compression, history and tags for free — reimplementing
those would be the classic mistake for a feature that *is* version
control.

The repository is created and maintained by this integration alone. It
never shells out to a git binary: whether one exists differs between
Home Assistant OS, Container, Core and Supervised installations.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path

from dulwich import porcelain
from dulwich.repo import Repo

_LOGGER = logging.getLogger(__name__)

_IDENTITY = b"Dashboard History <dashboard-history@localhost>"


@dataclass(frozen=True)
class Change:
    """One recorded state of one dashboard."""

    revision: str
    timestamp: int
    message: str


@dataclass(frozen=True)
class Version:
    """A named point in the history. It groups, it never squashes."""

    name: str
    revision: str
    title: str
    description: str


def _as_text(value) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)


class HistoryStore:
    """Stores dashboard states and reads them back."""

    def __init__(self, path) -> None:
        self.path = Path(path)
        # dulwich takes an exclusive lock on the git index while it writes.
        # Two dashboards saved in the same moment run in two executor
        # threads; measured, eight parallel commits let exactly one through
        # and the other seven raised FileLocked. Writes are serialised here
        # rather than left to chance.
        self._lock = threading.Lock()

    # -- writing -------------------------------------------------------

    def ensure(self) -> None:
        """Create the repository if it does not exist yet."""
        with self._lock:
            self._ensure()

    def _ensure(self) -> None:
        """Same, for callers that already hold the lock."""
        if (self.path / ".git").exists():
            return
        self.path.mkdir(parents=True, exist_ok=True)
        porcelain.init(str(self.path))
        _LOGGER.info("Created dashboard history repository at %s", self.path)

    def write_snapshot(self, key: str, text: str, message: str) -> str | None:
        """Record a state. Returns the revision, or None if nothing changed."""
        with self._lock:
            self._ensure()
            target = self.path / f"{key}.yaml"

            # Compare against the last commit, never against the file on
            # disk. If an earlier run wrote the file but did not get to
            # commit it, the file already carries the new text - comparing
            # against it would drop that state from the history for good,
            # and silently, which is the one failure this project must not
            # have. Comparing against HEAD repairs such a gap by itself.
            if self.read_at(key, "HEAD") == text:
                # The repository is already right. Keep the working tree
                # honest anyway: the README invites people to look inside.
                if not target.exists() or target.read_text(encoding="utf-8") != text:
                    self._write_file(target, text)
                return None

            self._write_file(target, text)
            porcelain.add(str(self.path), [str(target)])
            revision = porcelain.commit(
                str(self.path),
                message=message.encode("utf-8"),
                author=_IDENTITY,
                committer=_IDENTITY,
            )
            return _as_text(revision)

    @staticmethod
    def _write_file(target: Path, text: str) -> None:
        """Write through a temporary file.

        An interrupted run must not leave a truncated YAML behind that
        later looks like a real state.
        """
        temp = target.with_name(f"{target.name}.tmp")
        temp.write_text(text, encoding="utf-8")
        os.replace(temp, target)

    def create_version(
        self, name: str, title: str, description: str, revision: str | None = None
    ) -> None:
        """Mark a point in the history with a name, title and description."""
        with self._lock:
            self._ensure()
            self._create_version(name, title, description, revision)

    def _create_version(
        self, name: str, title: str, description: str, revision: str | None
    ) -> None:
        body = f"{title}\n\n{description}".encode("utf-8")
        porcelain.tag_create(
            str(self.path),
            name.encode("utf-8"),
            message=body,
            author=_IDENTITY,
            annotated=True,
            objectish=revision.encode() if revision else b"HEAD",
        )

    # -- reading -------------------------------------------------------

    def _repo(self) -> Repo | None:
        if not (self.path / ".git").exists():
            return None
        return Repo(str(self.path))

    def list_changes(self, key: str, limit: int = 50) -> list[Change]:
        """Every recorded state of one dashboard, newest first."""
        repo = self._repo()
        if repo is None:
            return []
        try:
            walker = repo.get_walker(paths=[f"{key}.yaml".encode()], max_entries=limit)
            return [
                Change(
                    revision=_as_text(entry.commit.id),
                    timestamp=entry.commit.commit_time,
                    message=entry.commit.message.decode("utf-8").strip(),
                )
                for entry in walker
            ]
        except KeyError:
            # No HEAD yet: an empty repository has no history to walk.
            return []

    def resolve(self, revision: str) -> str | None:
        """Turn a revision into a full commit hash, or None if unknown.

        Accepts what a person is actually likely to paste: a full hash, a
        ref such as HEAD, an annotated tag, or an abbreviated hash of the
        kind `git log --oneline` prints. dulwich resolves none of the
        abbreviated forms by itself, and the abbreviated form is exactly
        what anyone who looks into the repository will copy out of it.
        """
        repo = self._repo()
        return None if repo is None else self._resolve(repo, revision)

    @staticmethod
    def _resolve(repo: Repo, revision: str) -> str | None:
        name = revision.strip().encode()
        if not name:
            return None
        sha = None
        try:
            sha = repo[name].id
        except (KeyError, ValueError):
            # git itself refuses fewer than four characters; so do we.
            if 4 <= len(name) < 40:
                lowered = name.lower()
                if all(char in b"0123456789abcdef" for char in lowered):
                    matches = list(repo.object_store.iter_prefix(lowered))
                    # An ambiguous prefix is refused rather than guessed:
                    # picking one of two commits would be worse than
                    # saying it is not clear which was meant.
                    if len(matches) == 1:
                        sha = matches[0]
        if sha is None:
            return None
        obj = repo[sha]
        while obj.type_name == b"tag":
            # An annotated tag points at the commit; that is what is wanted.
            obj = repo[obj.object[1]]
        return _as_text(obj.id)

    def read_at(self, key: str, revision: str) -> str | None:
        """The text of one dashboard at one revision, or None if absent.

        None means two different things - the revision is unknown, or the
        dashboard did not exist in it. Callers that report to a person
        must tell those apart with `resolve`; conflating them sends people
        looking for a fault in their dashboard instead of in their input.
        """
        repo = self._repo()
        if repo is None:
            return None
        resolved = self._resolve(repo, revision)
        if resolved is None:
            return None
        try:
            tree = repo[repo[resolved.encode()].tree]
            _, blob_id = tree.lookup_path(repo.get_object, f"{key}.yaml".encode())
        except KeyError:
            return None
        return repo[blob_id].data.decode("utf-8")

    def list_versions(self) -> list[Version]:
        """Every named point, newest first."""
        repo = self._repo()
        if repo is None:
            return []
        found: list[tuple[int, Version]] = []
        for ref in repo.refs.as_dict(b"refs/tags"):
            tag = repo[repo.refs[b"refs/tags/" + ref]]
            if not hasattr(tag, "object"):
                # A lightweight tag, made by hand. Not ours; skip it rather
                # than crash on the missing fields.
                continue
            message = (tag.message or b"").decode("utf-8")
            title, _, description = message.partition("\n\n")
            found.append(
                (
                    tag.tag_time,
                    Version(
                        name=ref.decode(),
                        revision=_as_text(tag.object[1]),
                        title=title.strip(),
                        description=description.strip(),
                    ),
                )
            )
        # as_dict has no order of its own; the docstring promises one.
        return [version for _, version in sorted(found, key=lambda p: -p[0])]
```

- [x] **Schritt 4: Tests laufen lassen, Erfolg bestätigen**

Ausführen: `python3 -m pytest tests/ -v`
Erwartet: PASS, 22 synthetische plus die echten (auf dieser Anlage 33)

- [x] **Schritt 5: Committen**

```bash
git add custom_components/dashboard_history/store.py tests/test_store.py
git commit -m "$(cat <<'MSG'
Ergänze den git-gestützten Speicher

git dient hier als Ablage, nicht als Werkzeug für den Nutzer. Es liefert
Deduplizierung, Komprimierung, Verlauf und Markierungen fertig - das
selbst zu bauen wäre bei einem Vorhaben, das buchstäblich
Versionsverwaltung ist, der klassische Fehlgriff.

Eine Version ist eine Markierung, kein Zusammenfassen. Genau deshalb
bleiben die Einzeländerungen darunter erhalten.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
)"
```

---

### Task 4: Die Einordnung der Änderungen

Das Herz des Projekts. Von hier hängt ab, ob die Oberfläche das Richtige anbietet — und ob sie Fehlalarme erzeugt.

**Files:**
- Create: `custom_components/dashboard_history/analyze.py`
- Create: `tests/test_analyze.py`

**Interfaces:**
- Consumes: nichts
- Produces:
  - `RemovedItem(kind, view_path, view_index, location, index, payload, label)`
  - `card_containers(view) -> Iterator[tuple[tuple, list]]`
  - `find_removed(old: dict, new: dict) -> list[RemovedItem]`
  - `summarize(old: dict, new: dict) -> Summary` mit `added`, `removed`, `edited`, `moved` (je `int`)

- [x] **Schritt 1: Den fehlschlagenden Test schreiben**

`tests/test_analyze.py`:

```python
"""Tests for change classification.

These are the most important tests in the project: if an edited card were
classified as a deletion, the interface would offer to restore something
that is not missing — and a false alarm destroys trust in exactly the
message people open the tool for.
"""

import analyze


def _config(cards):
    return {"views": [{"path": "home", "title": "Home", "cards": list(cards)}]}


A = {"type": "tile", "entity": "light.a"}
B = {"type": "tile", "entity": "light.b"}
C = {"type": "tile", "entity": "light.c"}


def test_nothing_changed():
    s = analyze.summarize(_config([A, B]), _config([A, B]))
    assert (s.added, s.removed, s.edited, s.moved) == (0, 0, 0, 0)


def test_card_removed_is_found():
    removed = analyze.find_removed(_config([A, B]), _config([A]))
    assert len(removed) == 1
    assert removed[0].kind == "card"
    assert removed[0].payload == B
    assert removed[0].index == 1
    assert removed[0].view_path == "home"


def test_card_added_is_not_a_removal():
    assert analyze.find_removed(_config([A]), _config([A, B])) == []


def test_edited_card_is_not_reported_as_removed():
    edited = dict(A, name="New name")
    assert analyze.find_removed(_config([A, B]), _config([edited, B])) == []
    s = analyze.summarize(_config([A, B]), _config([edited, B]))
    assert (s.edited, s.removed, s.added) == (1, 0, 0)


def test_reordered_cards_are_not_reported_as_removed():
    assert analyze.find_removed(_config([A, B]), _config([B, A])) == []
    s = analyze.summarize(_config([A, B]), _config([B, A]))
    assert s.moved == 2
    assert (s.removed, s.added) == (0, 0)


def test_view_removed_is_found():
    old = {"views": [{"path": "home", "cards": [A]}, {"path": "gone", "cards": [B]}]}
    new = {"views": [{"path": "home", "cards": [A]}]}
    removed = analyze.find_removed(old, new)
    assert len(removed) == 1
    assert removed[0].kind == "view"
    assert removed[0].view_path == "gone"


def test_cards_inside_sections_are_covered():
    old = {"views": [{"path": "home", "type": "sections",
                      "sections": [{"type": "grid", "cards": [A, B]}]}]}
    new = {"views": [{"path": "home", "type": "sections",
                      "sections": [{"type": "grid", "cards": [A]}]}]}
    removed = analyze.find_removed(old, new)
    assert len(removed) == 1
    assert removed[0].payload == B
    assert removed[0].location == ("sections", 0, "cards")


def test_several_removals_in_one_save():
    removed = analyze.find_removed(_config([A, B, C]), _config([B]))
    assert {tuple(sorted(item.payload.items())) for item in removed} == {
        tuple(sorted(A.items())), tuple(sorted(C.items()))
    }


def test_removed_item_has_a_readable_label():
    removed = analyze.find_removed(_config([A, B]), _config([A]))
    assert "light.b" in removed[0].label


def test_removed_view_keeps_its_position():
    old = {"views": [{"path": "a", "cards": []}, {"path": "gone", "cards": []},
                     {"path": "c", "cards": []}]}
    new = {"views": [{"path": "a", "cards": []}, {"path": "c", "cards": []}]}
    item = analyze.find_removed(old, new)[0]
    assert item.index == 1 and item.view_index == 1


def test_views_without_a_path_are_handled():
    old = {"views": [{"title": "No path", "cards": [A, B]}]}
    new = {"views": [{"title": "No path", "cards": [A]}]}
    removed = analyze.find_removed(old, new)
    assert len(removed) == 1
    assert removed[0].view_path is None
```

- [x] **Schritt 2: Tests laufen lassen, Fehlschlag bestätigen**

Ausführen: `python3 -m pytest tests/test_analyze.py -v`
Erwartet: FAIL mit `ModuleNotFoundError: No module named 'analyze'`

- [x] **Schritt 3: Implementierung schreiben**

`custom_components/dashboard_history/analyze.py`:

```python
"""Classifying what changed between two dashboard configurations.

Lovelace cards carry no identifier — a card is defined by its position in
a list. Matching them between two states therefore has to work from their
content, and that shapes everything here.

The order matters: an exact content match wins first (that card is
unchanged, possibly moved), then a weak match on type plus the most
identifying field (that card was edited). Only what is left over counts
as removed. Without that ordering an edited card would look like a
deletion plus an addition, and the interface would offer to restore
something that is still there.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RemovedItem:
    """Something that was present before and is gone now."""

    kind: str  # "card" or "view"
    view_path: str | None
    view_index: int  # position of the view in the old configuration
    location: tuple  # path to the card list inside the view
    index: int  # position in the card list, or of the view itself
    payload: dict
    label: str


@dataclass(frozen=True)
class Summary:
    """How many cards were added, removed, edited and moved."""

    added: int = 0
    removed: int = 0
    edited: int = 0
    moved: int = 0


def card_containers(view: dict) -> Iterator[tuple[tuple, list]]:
    """Yield every card list in a view, with the path that locates it.

    Views come in two shapes: the classic one with a flat `cards` list,
    and the sections layout where each section holds its own list.
    """
    if isinstance(view.get("cards"), list):
        yield ("cards",), view["cards"]
    for index, section in enumerate(view.get("sections") or []):
        if isinstance(section, dict) and isinstance(section.get("cards"), list):
            yield ("sections", index, "cards"), section["cards"]


_LABEL_LIMIT = 48


def _shorten(text: str) -> str:
    """Collapse whitespace and cut to a length that fits a list."""
    text = " ".join(text.split())
    if len(text) <= _LABEL_LIMIT:
        return text
    return text[: _LABEL_LIMIT - 1].rstrip() + "\u2026"


def _first_line(card: dict) -> str | None:
    """The first meaningful line of a card's own text, if it has any."""
    for field in ("content", "text"):
        value = card.get(field)
        if isinstance(value, str):
            for line in value.splitlines():
                line = line.lstrip("#").strip()
                if line:
                    return line
    return None


def _first_entity(card: dict) -> str | None:
    """The first entity of a card that is defined by a list of them."""
    entities = card.get("entities")
    if not isinstance(entities, list) or not entities:
        return None
    first = entities[0]
    name = first.get("entity") if isinstance(first, dict) else first
    return str(name) if name else None


def _inner_card(card: dict) -> dict | None:
    """The card a wrapper wraps, if there is an obvious first one."""
    inner = card.get("card")
    if isinstance(inner, dict):
        return inner
    cards = card.get("cards")
    if isinstance(cards, list) and cards and isinstance(cards[0], dict):
        return cards[0]
    return None


def _weak_key(card: Any, depth: int = 0):
    """A content-based identity, good enough to recognise an edited card.

    All of this exists to prevent one specific failure: an edited card read
    as a deletion plus an addition. The interface would then offer to
    restore something that is not missing, and a false alarm of that kind
    destroys trust in exactly the message people open the tool for.

    Which is why it reaches well past entity, title and name. Counted on
    the installation this was built against, most cards carry none of the
    three: 62 headings, 76 entity lists without a title, and 261 wrappers
    whose only content is the card inside them. Identifying by the most
    stable field first is deliberate - an entity outlives a renamed title.
    """
    if not isinstance(card, dict):
        return None
    kind = card.get("type")
    for field in ("entity", "title", "name", "heading"):
        if card.get(field):
            return (kind, field, str(card[field]))
    entity = _first_entity(card)
    if entity is not None:
        return (kind, "entities", entity)
    line = _first_line(card)
    if line is not None:
        # The first line, not the whole text: editing the body below it
        # must not change what the card is.
        return (kind, "text", line)
    if depth < 3:
        inner = _inner_card(card)
        if inner is not None:
            key = _weak_key(inner, depth + 1)
            # Only when the card inside can be named at all. Otherwise two
            # different anonymous wrappers would look like the same card,
            # and a real deletion would be missed.
            if key is not None:
                return (kind, "inside", key)
    return None


def _describe(card: Any, depth: int = 0) -> str:
    """A short human-readable label for a card.

    The field order differs from _weak_key on purpose: identity wants the
    most stable field, a label wants the most human one.
    """
    if not isinstance(card, dict):
        return str(card)
    kind = str(card.get("type", "card"))
    for field in ("title", "name", "heading", "entity"):
        if card.get(field):
            return f"{kind}: {_shorten(str(card[field]))}"
    line = _first_line(card)
    if line is not None:
        return f"{kind}: {_shorten(line)}"
    entity = _first_entity(card)
    if entity is not None:
        rest = len(card["entities"]) - 1
        return f"{kind}: {_shorten(entity)}" + (f" +{rest}" if rest else "")
    if depth < 4:
        inner = _inner_card(card)
        if inner is not None:
            label = _describe(inner, depth + 1)
            # Nested wrappers hand the name up unchanged. A chain of four
            # container types tells nobody which card this was; the name of
            # the first thing inside that has one does.
            return label if depth else f"{kind} > {label}"
    return kind


def _match_cards(old_cards: list, new_cards: list):
    """Return (removed_indices, added_indices, edited_pairs, moved_pairs)."""
    unmatched_new = list(range(len(new_cards)))
    removed: list[int] = []
    edited: list[tuple[int, int]] = []
    exact: list[tuple[int, int]] = []

    # Pass one: exact content matches. Same card, possibly at a new index.
    pending: list[int] = []
    for old_index, card in enumerate(old_cards):
        match = next((j for j in unmatched_new if new_cards[j] == card), None)
        if match is None:
            pending.append(old_index)
            continue
        unmatched_new.remove(match)
        exact.append((old_index, match))

    # Pass two: weak matches among what is left. Same card, edited.
    for old_index in pending:
        key = _weak_key(old_cards[old_index])
        match = (
            next((j for j in unmatched_new if _weak_key(new_cards[j]) == key), None)
            if key is not None
            else None
        )
        if match is None:
            removed.append(old_index)
        else:
            unmatched_new.remove(match)
            edited.append((old_index, match))

    return removed, unmatched_new, edited, _moved(exact, edited)


def _moved(
    exact: list[tuple[int, int]], edited: list[tuple[int, int]]
) -> list[tuple[int, int]]:
    """Which matched cards changed position *relative to each other*.

    A raw index comparison calls every card behind a deletion moved. On a
    large view that is twenty entries of noise wrapped around the single
    fact that matters, and it is not what anyone means by "moved" either.
    What people mean is a change in the order, so that is what is
    measured: a card's rank among the survivors, before against after.

    Edited cards take part in the ranking - they still hold a position -
    but are not reported here, because they are already reported as edited.
    """
    pairs = sorted(exact + edited)
    old_rank = {old: rank for rank, (old, _) in enumerate(pairs)}
    new_rank = {
        new: rank for rank, (_, new) in enumerate(sorted(pairs, key=lambda p: p[1]))
    }
    return [(old, new) for old, new in exact if old_rank[old] != new_rank[new]]


def _views_by_key(config: dict) -> list[tuple[Any, dict]]:
    """Views paired with the key that identifies them across states."""
    result = []
    for index, view in enumerate(config.get("views") or []):
        if not isinstance(view, dict):
            continue
        result.append((view.get("path") or ("#", index), view))
    return result


def find_removed(old: dict, new: dict) -> list[RemovedItem]:
    """Everything that disappeared between two states.

    Only disappearances are reported. Restoring them is additive — nothing
    is overwritten — and therefore always well defined, which is not true
    for undoing an edit.
    """
    new_views = dict(_views_by_key(new))
    items: list[RemovedItem] = []

    for view_index, (key, old_view) in enumerate(_views_by_key(old)):
        new_view = new_views.get(key)
        if new_view is None:
            items.append(
                RemovedItem(
                    kind="view",
                    view_path=old_view.get("path"),
                    view_index=view_index,
                    location=(),
                    index=view_index,
                    payload=old_view,
                    label=f"view: {old_view.get('title') or old_view.get('path') or key}",
                )
            )
            continue

        new_containers = dict(card_containers(new_view))
        for location, old_cards in card_containers(old_view):
            new_cards = new_containers.get(location, [])
            removed, _, _, _ = _match_cards(old_cards, new_cards)
            for index in removed:
                items.append(
                    RemovedItem(
                        kind="card",
                        view_path=old_view.get("path"),
                        view_index=view_index,
                        location=location,
                        index=index,
                        payload=old_cards[index],
                        label=_describe(old_cards[index]),
                    )
                )
    return items


def summarize(old: dict, new: dict) -> Summary:
    """Count what changed, for the history display."""
    new_views = dict(_views_by_key(new))
    added = removed = edited = moved = 0

    for key, old_view in _views_by_key(old):
        new_view = new_views.get(key)
        if new_view is None:
            removed += sum(len(cards) for _, cards in card_containers(old_view))
            continue
        new_containers = dict(card_containers(new_view))
        for location, old_cards in card_containers(old_view):
            r, a, e, m = _match_cards(old_cards, new_containers.get(location, []))
            removed += len(r)
            added += len(a)
            edited += len(e)
            # One entry per moved card already, so a swap contributes
            # two. Multiplying would count each of them twice.
            moved += len(m)

    old_keys = {key for key, _ in _views_by_key(old)}
    for key, new_view in _views_by_key(new):
        if key not in old_keys:
            added += sum(len(cards) for _, cards in card_containers(new_view))

    return Summary(added=added, removed=removed, edited=edited, moved=moved)
```

- [x] **Schritt 4: Tests laufen lassen, Erfolg bestätigen**

Ausführen: `python3 -m pytest tests/ -v`
Erwartet: PASS, 44 synthetische plus die echten (auf dieser Anlage 55)

- [x] **Schritt 5: Committen**

```bash
git add custom_components/dashboard_history/analyze.py tests/test_analyze.py
git commit -m "$(cat <<'MSG'
Ergänze die Einordnung der Änderungen

Lovelace-Karten haben keine Kennung; sie sind allein über ihre Position
bestimmt. Die Zuordnung muss deshalb über den Inhalt laufen, und die
Reihenfolge entscheidet: erst exakte Übereinstimmung, dann eine schwache
über Typ und kennzeichnendes Feld, und erst der Rest gilt als gelöscht.

Ohne diese Reihenfolge sähe eine bearbeitete Karte wie eine Löschung
samt Neuanlage aus, und die Oberfläche böte an, etwas wiederherzustellen,
das gar nicht fehlt.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
)"
```

---

### Task 5: Die Umkehrung

**Files:**
- Create: `custom_components/dashboard_history/restore.py`
- Create: `tests/test_restore.py`

**Interfaces:**
- Consumes: `analyze.RemovedItem`
- Produces: `reinsert(config: dict, item: RemovedItem) -> dict` — neue Konfiguration, die übergebene bleibt unberührt

- [x] **Schritt 1: Den fehlschlagenden Test schreiben**

`tests/test_restore.py`:

```python
"""Tests for putting removed items back."""

import analyze
import pytest
import restore

A = {"type": "tile", "entity": "light.a"}
B = {"type": "tile", "entity": "light.b"}
C = {"type": "tile", "entity": "light.c"}


def _config(cards):
    return {"views": [{"path": "home", "title": "Home", "cards": list(cards)}]}


def test_card_goes_back_to_its_old_position():
    item = analyze.find_removed(_config([A, B, C]), _config([A, C]))[0]
    result = restore.reinsert(_config([A, C]), item)
    assert result["views"][0]["cards"] == [A, B, C]


def test_card_is_appended_when_the_view_has_shrunk():
    item = analyze.find_removed(_config([A, B, C]), _config([A]))
    removed_c = next(i for i in item if i.payload == C)
    result = restore.reinsert(_config([A]), removed_c)
    assert result["views"][0]["cards"] == [A, C]


def test_the_input_is_not_modified():
    original = _config([A, C])
    item = analyze.find_removed(_config([A, B, C]), original)[0]
    restore.reinsert(original, item)
    assert original["views"][0]["cards"] == [A, C]


def test_a_removed_view_comes_back():
    old = {"views": [{"path": "home", "cards": [A]}, {"path": "gone", "cards": [B]}]}
    new = {"views": [{"path": "home", "cards": [A]}]}
    item = analyze.find_removed(old, new)[0]
    result = restore.reinsert(new, item)
    assert [v["path"] for v in result["views"]] == ["home", "gone"]


def test_a_card_inside_a_section_comes_back():
    old = {"views": [{"path": "home", "type": "sections",
                      "sections": [{"type": "grid", "cards": [A, B]}]}]}
    new = {"views": [{"path": "home", "type": "sections",
                      "sections": [{"type": "grid", "cards": [A]}]}]}
    item = analyze.find_removed(old, new)[0]
    result = restore.reinsert(new, item)
    assert result["views"][0]["sections"][0]["cards"] == [A, B]


def test_a_vanished_target_view_is_refused_loudly():
    item = analyze.find_removed(_config([A, B]), _config([A]))[0]
    with pytest.raises(LookupError):
        restore.reinsert({"views": []}, item)
```

- [x] **Schritt 2: Tests laufen lassen, Fehlschlag bestätigen**

Ausführen: `python3 -m pytest tests/test_restore.py -v`
Erwartet: FAIL mit `ModuleNotFoundError: No module named 'restore'`

- [x] **Schritt 3: Implementierung schreiben**

`custom_components/dashboard_history/restore.py`:

```python
"""Putting removed items back into a live configuration.

Restoring a disappearance is additive: nothing is overwritten, so there
is no merge and no ambiguity. That is the whole reason this integration
restricts itself to disappearances rather than trying to undo edits.

The configuration handed in is never modified. The caller still needs the
old state to render a preview against.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Only needed for the annotations, and `from __future__ import
    # annotations` keeps those lazy. A real import would have to be
    # relative inside the integration and absolute in the tests, which
    # load this module flat - it cannot be both.
    from .analyze import RemovedItem


def _find_view(views: list, item: RemovedItem) -> dict | None:
    """Locate the view an item belongs to, by path or by position."""
    if item.view_path is not None:
        for view in views:
            if isinstance(view, dict) and view.get("path") == item.view_path:
                return view
        return None
    if 0 <= item.view_index < len(views):
        candidate = views[item.view_index]
        return candidate if isinstance(candidate, dict) else None
    return None


def _cards_at(view: dict, location: tuple) -> list | None:
    """Walk to the card list a location points at."""
    current = view
    for step in location:
        if isinstance(step, int):
            if not isinstance(current, list) or step >= len(current):
                return None
            current = current[step]
        else:
            if not isinstance(current, dict) or step not in current:
                return None
            current = current[step]
    return current if isinstance(current, list) else None


def reinsert(config: dict, item: RemovedItem) -> dict:
    """Return a new configuration with `item` put back.

    Raises LookupError when the place it belonged to no longer exists —
    guessing a different place would be worse than refusing.
    """
    result = copy.deepcopy(config)
    views = result.setdefault("views", [])

    if item.kind == "view":
        views.insert(min(item.index, len(views)), copy.deepcopy(item.payload))
        return result

    view = _find_view(views, item)
    if view is None:
        raise LookupError(
            f"the view this card belonged to no longer exists "
            f"(path={item.view_path!r}, index={item.view_index})"
        )

    cards = _cards_at(view, item.location)
    if cards is None:
        raise LookupError(
            f"the card list this card belonged to no longer exists "
            f"(location={item.location!r})"
        )

    # If the list has shrunk since, append rather than fail: getting the
    # card back matters more than getting its exact old position back.
    cards.insert(min(item.index, len(cards)), copy.deepcopy(item.payload))
    return result
```

- [x] **Schritt 4: Tests laufen lassen, Erfolg bestätigen**

Ausführen: `python3 -m pytest tests/ -v`
Erwartet: PASS, 50 synthetische plus die echten (auf dieser Anlage 61)

- [x] **Schritt 5: Committen**

```bash
git add custom_components/dashboard_history/restore.py tests/test_restore.py
git commit -m "$(cat <<'MSG'
Ergänze die Umkehrung von Löschungen

Eine Löschung rückgängig zu machen ist additiv: Es wird nichts
überschrieben, also gibt es keine Zusammenführung und keine
Mehrdeutigkeit. Genau darauf beschränkt sich die Integration.

Ist der Platz, an den etwas gehörte, verschwunden, wird laut abgelehnt
statt geraten. Ist die Liste nur kürzer geworden, wird angehängt - die
Karte zurückzubekommen wiegt schwerer als ihre alte Position.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
)"
```

---

### Task 6: Die Erfassung

**Files:**
- Create: `custom_components/dashboard_history/capture.py`
- Modify: `custom_components/dashboard_history/__init__.py`

**Interfaces:**
- Consumes: `snapshot.async_get_all_configs`, `yaml_io.dump`, `store.HistoryStore`, `analyze.summarize`
- Produces: `HistoryCapture(hass, store)` mit `async_start()`, `async_stop()`, `async_capture(key=None, reason="save")`

- [x] **Schritt 1: Die Erfassung schreiben**

`custom_components/dashboard_history/capture.py`:

```python
"""Recording dashboard states as they change.

Home Assistant fires `lovelace_updated` when a dashboard is saved. We do
not read the storage file in response — the event arrives before that
file is written. We ask the in-memory objects instead, which removes the
race completely.

Nothing in here may raise into Home Assistant: a failed recording is an
inconvenience, a failed save is not.
"""

from __future__ import annotations

import logging

from homeassistant.core import Event, HomeAssistant, callback

from .analyze import summarize
from .const import EVENT_LOVELACE_UPDATED
from .snapshot import async_get_all_configs, dashboard_key
from .store import HistoryStore
from .yaml_io import dump, load

_LOGGER = logging.getLogger(__name__)


class HistoryCapture:
    """Listens for dashboard saves and records them."""

    def __init__(self, hass: HomeAssistant, store: HistoryStore) -> None:
        self._hass = hass
        self._store = store
        self._unsubscribe = None

    async def async_start(self) -> None:
        """Reconcile once, then listen."""
        await self.async_capture(reason="startup")
        self._unsubscribe = self._hass.bus.async_listen(
            EVENT_LOVELACE_UPDATED, self._handle_event
        )

    async def async_stop(self) -> None:
        """Stop listening."""
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

    @callback
    def _handle_event(self, event: Event) -> None:
        """React to a save without blocking the event bus."""
        key = dashboard_key(event.data.get("url_path"))
        self._hass.async_create_task(self.async_capture(key=key, reason="save"))

    async def async_capture(self, key: str | None = None, reason: str = "save") -> list[str]:
        """Record the current state of one or all dashboards.

        Returns the revisions that were created. An unchanged dashboard
        produces none.
        """
        try:
            configs = await async_get_all_configs(self._hass)
        except Exception:  # noqa: BLE001 - never let a recording break a save
            _LOGGER.exception("Could not read dashboard configurations")
            return []

        if key is not None:
            configs = {k: v for k, v in configs.items() if k == key}

        revisions: list[str] = []
        for name, config in sorted(configs.items()):
            try:
                revision = await self._hass.async_add_executor_job(
                    self._write_one, name, config, reason
                )
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Could not record dashboard %s", name)
                continue
            if revision is not None:
                revisions.append(revision)
        return revisions

    def _write_one(self, name: str, config: dict, reason: str) -> str | None:
        """Blocking part: build the message and write. Runs in an executor."""
        text = dump(config)
        previous = self._store.read_at(name, "HEAD") if self._has_history(name) else None
        message = self._build_message(name, config, previous, reason)
        return self._store.write_snapshot(name, text, message)

    def _has_history(self, name: str) -> bool:
        return bool(self._store.list_changes(name, limit=1))

    def _build_message(self, name: str, config: dict, previous: str | None, reason: str) -> str:
        """A readable one-line summary of what happened."""
        if previous is None:
            return f"{name}: first recorded state"
        if reason == "startup":
            # Something changed while we were not listening: a restored
            # backup, a hand-edited storage file, another tool. Recording it
            # as a normal save would hide that.
            return f"{name}: changed outside Home Assistant"
        old = load(previous) or {}
        s = summarize(old, config)
        parts = [
            f"{s.removed} removed" if s.removed else "",
            f"{s.added} added" if s.added else "",
            f"{s.edited} edited" if s.edited else "",
            f"{s.moved} moved" if s.moved else "",
        ]
        detail = ", ".join(p for p in parts if p) or "no card changes"
        return f"{name}: {detail}"
```

- [x] **Schritt 2: In die Einrichtung einhängen**

In `__init__.py` `async_setup_entry` erweitern, sodass Speicher und Erfassung angelegt und in `hass.data[DOMAIN]` abgelegt werden, und `async_unload_entry` die Erfassung wieder abmeldet:

```python
    from pathlib import Path

    from .capture import HistoryCapture
    from .const import REPO_DIRNAME
    from .store import HistoryStore

    store = HistoryStore(Path(hass.config.path(REPO_DIRNAME)))
    capture = HistoryCapture(hass, store)
    hass.data[DOMAIN] = {"store": store, "capture": capture}

    # Guarded, because the hard rule says so: a repository that cannot be
    # created - a read-only configuration folder, a full disk - costs the
    # history, and nothing else. It must not cost the start.
    try:
        await hass.async_add_executor_job(store.ensure)
        await capture.async_start()
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Dashboard History could not start recording")
```

- [ ] **Schritt 3: Live prüfen**  ← **bestanden am 2026-08-30 an der eigenen Anlage**

Home Assistant neu starten. Dann:

1. `ls -la config/dashboard_history/` — das Repository muss existieren, mit einer `.yaml` je Dashboard.
2. In der Oberfläche an einem kleinen Dashboard etwas ändern und speichern.
3. Nach wenigen Sekunden erneut schauen: Die betreffende Datei muss den neuen Stand tragen.
4. **Der entscheidende Nachweis:** In der Commit-Botschaft muss die Zusammenfassung stehen, etwa `dashboard-karte: 1 edited`. Steht dort stattdessen `no card changes`, wurde ein veralteter Stand gelesen — dann greift Entscheidung 1 der Spec nicht und der Befund gehört gemeldet, nicht repariert.
5. Ohne Änderung erneut speichern: Es darf **kein** neuer Commit entstehen.

- [x] **Schritt 4: Committen**

```bash
git add custom_components/dashboard_history/capture.py custom_components/dashboard_history/__init__.py
git commit -m "$(cat <<'MSG'
Zeichne Dashboard-Änderungen auf

Der Stand kommt aus dem Speicher, nicht aus der Datei: Home Assistant
feuert das Ereignis, bevor es schreibt. Wer die Datei liest, muss warten
und zeichnet bei zu kurzer Wartezeit lautlos den vorherigen Stand auf.

Beim Start wird abgeglichen. Weicht der Live-Stand vom letzten Commit
ab, wird das als »ausserhalb geaendert« vermerkt statt als normales
Speichern - eine unsichtbare Luecke waere schlimmer als keine Historie,
weil man ihr vertraut.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
)"
```

---

### Task 7: Die Dienste

**Files:**
- Create: `custom_components/dashboard_history/services.py`
- Modify: `custom_components/dashboard_history/services.yaml`, `snapshot.py`, `__init__.py`

**Interfaces:**
- Consumes: alles Bisherige
- Produces: sechs Dienste in der Domäne `dashboard_history` — zusammen mit
  `debug_snapshot` aus Task 1 sind es sieben

- [x] **Schritt 1: Schreibzugriff ergänzen**

An `snapshot.py` anhängen:

```python
async def async_save_config(hass: HomeAssistant, key: str, config: dict) -> None:
    """Write a configuration back into a live dashboard.

    Goes through the same Lovelace object the interface uses, so Home
    Assistant fires its own events and every other listener sees the
    change — including our own recording.
    """
    dashboards = _lovelace_dashboards(hass)
    if dashboards is None:
        raise HomeAssistantError("Lovelace data is not available")
    for url_path, dashboard in dashboards.items():
        if dashboard_key(url_path) == key:
            await dashboard.async_save(config)
            return
    raise HomeAssistantError(f"unknown dashboard: {key}")
```

Dazu oben `from homeassistant.exceptions import HomeAssistantError` ergänzen.

- [x] **Schritt 2: Die Dienste schreiben**

`custom_components/dashboard_history/services.py`:

```python
"""Services: the whole feature, usable from Developer Tools.

The interface comes later. Everything it will need has to work here
first — that way the interface cannot quietly grow logic of its own.

Nothing writes without `confirm: true`. Every restoring service returns a
preview otherwise.
"""

from __future__ import annotations

import difflib
import logging

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import config_validation as cv

from .analyze import find_removed
from .const import DOMAIN
from .restore import reinsert
from .snapshot import async_get_config, async_save_config
from .yaml_io import dump, load

_LOGGER = logging.getLogger(__name__)

DASHBOARD = vol.Schema({vol.Required("dashboard"): cv.string})


def _diff(old: dict, new: dict, name: str) -> str:
    """A unified diff between two configurations, empty when equal."""
    return "".join(
        difflib.unified_diff(
            dump(old).splitlines(keepends=True),
            dump(new).splitlines(keepends=True),
            fromfile=f"live/{name}",
            tofile=f"restored/{name}",
        )
    )


async def async_register(hass: HomeAssistant) -> None:
    """Register every service."""
    data = hass.data[DOMAIN]
    store = data["store"]

    async def _state_at(key: str, revision: str) -> tuple[str | None, str | None]:
        """The dashboard text at a revision, or a message saying why not.

        The two failures are told apart on purpose. "Unknown revision" is a
        statement about the input; "did not exist" is a statement about the
        dashboard's history. Reporting the second when the first is true
        sends people looking for a fault in their dashboard instead of in
        what they typed - and an abbreviated hash, which is what `git log
        --oneline` prints, used to land exactly there.
        """
        full = await hass.async_add_executor_job(store.resolve, revision)
        if full is None:
            return None, f"unknown revision: {revision}"
        text = await hass.async_add_executor_job(store.read_at, key, full)
        if text is None:
            return None, f"{key} did not exist at {full[:10]}"
        return text, None

    async def history(call: ServiceCall) -> dict:
        key = call.data["dashboard"]
        limit = call.data.get("limit", 50)
        changes = await hass.async_add_executor_job(store.list_changes, key, limit)
        return {
            "changes": [
                {"revision": c.revision, "timestamp": c.timestamp, "message": c.message}
                for c in changes
            ]
        }

    async def deleted_since(call: ServiceCall) -> dict:
        key = call.data["dashboard"]
        text, error = await _state_at(key, call.data["revision"])
        if error is not None:
            return {"items": [], "error": error}
        current = await async_get_config(hass, key) or {}
        items = find_removed(load(text) or {}, current)
        return {
            "items": [
                {
                    "position": position,
                    "kind": item.kind,
                    "label": item.label,
                    "view": item.view_path,
                }
                for position, item in enumerate(items)
            ]
        }

    async def restore_deleted(call: ServiceCall) -> dict:
        key = call.data["dashboard"]
        position = call.data["position"]
        text, error = await _state_at(key, call.data["revision"])
        if error is not None:
            return {"applied": False, "error": error}
        current = await async_get_config(hass, key) or {}
        items = find_removed(load(text) or {}, current)
        if not items:
            # Otherwise the range below reads "0..-1", which is nonsense.
            return {"applied": False, "error": "nothing is missing since that revision"}
        if not 0 <= position < len(items):
            return {
                "applied": False,
                "error": f"position {position} out of range (0..{len(items) - 1})",
            }
        try:
            restored = reinsert(current, items[position])
        except LookupError as err:
            # The place it belonged to is gone. Every other failure here
            # answers with a message rather than an exception; this one
            # should too, or the developer tools show a bare traceback.
            return {"applied": False, "error": str(err)}
        diff = _diff(current, restored, key)
        if not call.data.get("confirm"):
            return {"applied": False, "preview": diff}
        await async_save_config(hass, key, restored)
        return {"applied": True, "preview": diff, "restored": items[position].label}

    async def restore_state(call: ServiceCall) -> dict:
        key = call.data["dashboard"]
        text, error = await _state_at(key, call.data["revision"])
        if error is not None:
            return {"applied": False, "error": error}
        target = load(text) or {}
        current = await async_get_config(hass, key) or {}
        diff = _diff(current, target, key)
        if not diff:
            return {"applied": False, "preview": "", "note": "already identical"}
        if not call.data.get("confirm"):
            return {"applied": False, "preview": diff}
        await async_save_config(hass, key, target)
        return {"applied": True, "preview": diff}

    async def create_version(call: ServiceCall) -> dict:
        revision = call.data.get("revision")
        if revision:
            revision = await hass.async_add_executor_job(store.resolve, revision)
            if revision is None:
                return {
                    "created": None,
                    "error": f"unknown revision: {call.data['revision']}",
                }
        await hass.async_add_executor_job(
            store.create_version,
            call.data["name"],
            call.data["title"],
            call.data.get("description", ""),
            revision,
        )
        return {"created": call.data["name"]}

    async def versions(call: ServiceCall) -> dict:
        found = await hass.async_add_executor_job(store.list_versions)
        return {
            "versions": [
                {"name": v.name, "revision": v.revision,
                 "title": v.title, "description": v.description}
                for v in found
            ]
        }

    registrations = [
        ("history", history, DASHBOARD.extend({vol.Optional("limit", default=50): int})),
        ("deleted_since", deleted_since,
         DASHBOARD.extend({vol.Required("revision"): cv.string})),
        ("restore_deleted", restore_deleted, DASHBOARD.extend({
            vol.Required("revision"): cv.string,
            vol.Required("position"): int,
            vol.Optional("confirm", default=False): bool,
        })),
        ("restore_state", restore_state, DASHBOARD.extend({
            vol.Required("revision"): cv.string,
            vol.Optional("confirm", default=False): bool,
        })),
        ("create_version", create_version, vol.Schema({
            vol.Required("name"): cv.string,
            vol.Required("title"): cv.string,
            vol.Optional("description", default=""): cv.string,
            vol.Optional("revision"): cv.string,
        })),
        ("versions", versions, vol.Schema({})),
    ]
    for name, handler, schema in registrations:
        hass.services.async_register(
            DOMAIN, name, handler, schema=schema,
            supports_response=SupportsResponse.ONLY,
        )
```

In `__init__.py` nach dem Anlegen von `hass.data[DOMAIN]` ergänzen:

```python
    from .services import async_register

    await async_register(hass)
```

- [x] **Schritt 3: `services.yaml` vervollständigen**

Für jeden der sechs Dienste einen Eintrag mit `name`, `description` und Feldern, damit sie in den Entwicklerwerkzeugen bedienbar sind. Muster für den heikelsten:

```yaml
restore_deleted:
  name: Restore a deleted item
  description: >-
    Put a card or view back that disappeared after the given revision.
    Without confirm, only a preview of the change is returned.
  fields:
    dashboard:
      required: true
      example: dashboard-karte
      selector: {text: }
    revision:
      required: true
      description: A revision from the history service.
      selector: {text: }
    position:
      required: true
      description: Index from the deleted_since service.
      selector: {number: {min: 0, mode: box}}
    confirm:
      description: Without this, nothing is written.
      default: false
      selector: {boolean: }
```

- [ ] **Schritt 4: Live prüfen**  ← **bestanden am 2026-08-30 an der eigenen Anlage**

Nach einem Neustart in den Entwicklerwerkzeugen der Reihe nach:

1. `dashboard_history.history` mit einem kleinen Dashboard — muss die bisherigen Stände auflisten.
2. In der Oberfläche eine Karte **löschen** und speichern.
3. `dashboard_history.deleted_since` mit der Revision von vor dem Löschen — muss genau diese eine Karte melden, mit lesbarer Bezeichnung.
4. `dashboard_history.restore_deleted` **ohne** `confirm` — muss einen Diff liefern und `applied: false`. Das Dashboard darf sich nicht ändern.
5. Denselben Aufruf **mit** `confirm: true` — die Karte muss wieder da sein.
6. `dashboard_history.create_version` und `dashboard_history.versions` — die Version muss erscheinen, und `history` muss die Einzeländerungen weiterhin einzeln zeigen.

- [x] **Schritt 5: Committen**

```bash
git add custom_components/dashboard_history/services.py custom_components/dashboard_history/services.yaml custom_components/dashboard_history/snapshot.py custom_components/dashboard_history/__init__.py
git commit -m "$(cat <<'MSG'
Ergänze die Dienste für die Entwicklerwerkzeuge

Die gesamte Funktionalität muss über eine saubere Schnittstelle
erreichbar sein, bevor eine Oberfläche existiert. So bekommt die
Oberfläche später gar nicht erst Gelegenheit, eigene Logik an sich zu
ziehen - und die stünde ausgerechnet in der Schicht mit dem hoechsten
Bruchrisiko.

Kein Dienst schreibt ohne ausdrückliches confirm; ohne das gibt es nur
den Diff.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
)"
```

---

### Task 8: Dokumentation

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: alles Bisherige
- Produces: keine

- [x] **Schritt 1: README schreiben**

`README.md` — dieses Gerüst ausfüllen; die Beispielaufrufe aus den Live-Prüfungen von Task 7 übernehmen, damit sie nachweislich stimmen:

```markdown
# Dashboard History

Records every change to your Home Assistant dashboards and lets you put
back what disappeared.

Home Assistant only offers undo *while* you are editing. Close the editor
and that history is gone; a card you deleted last week is only in a full
backup, if at all. This integration keeps a history of its own.

## What it does

- Records every dashboard save automatically. No configuration needed.
- Shows the history of each dashboard: when it changed and what changed.
- **Puts back what disappeared** — a deleted card, a deleted view.
- Restores a whole dashboard to an earlier state.
- Lets you name a point in the history: a *version* with a title and a
  description.

## What it does not do

- **It does not undo edits.** Only disappearances can be restored. See
  "Why only deletions?" below — the reason is not laziness.
- It does not record *who* made a change. Home Assistant does not pass
  that information to integrations.
- It is not a backup. It covers dashboards, nothing else.

## Why only deletions?

A Lovelace card carries no identifier. It is defined purely by its
position in a list. Putting back a card that is gone is *additive*:
nothing is overwritten, so there is exactly one correct result. Undoing
an *edit* means replacing today's version with an older one — a merge
without identities, and when a later change touched the same card there
is no single correct answer.

Deletions are also the painful case. A card you moved by accident, you
move back. A card you deleted is gone.

## Installation

1. Add this repository to HACS as a custom repository (type: Integration).
2. Install "Dashboard History".
3. Restart Home Assistant.
4. Settings → Devices & Services → Add Integration → Dashboard History.

## Usage

Everything is available as services under Developer Tools → Actions.

### I deleted a card by accident

1. `dashboard_history.history` with your dashboard — note the revision
   from *before* the deletion.
2. `dashboard_history.deleted_since` with that revision — lists what is
   missing, each with a position.
3. `dashboard_history.restore_deleted` with that position — returns a
   preview. **Nothing is written.**
4. Same call again with `confirm: true` — the card is back.

### Services

| Service | What it does |
|---|---|
| `history` | The recorded states of one dashboard |
| `deleted_since` | What disappeared since a revision |
| `restore_deleted` | Put one of them back (needs `confirm`) |
| `restore_state` | Set a dashboard back to an earlier state (needs `confirm`) |
| `create_version` | Name a point in the history |
| `versions` | List the named points |
| `debug_snapshot` | What the integration currently sees |

## Where the data lives

In `config/dashboard_history/`, as a git repository this integration
owns. Each dashboard is one YAML file; each save is one commit; each
version is a tag.

You may look inside it. Do not edit it by hand — the integration writes
it and expects to be the only writer.

No system `git` is required: the integration uses a pure Python
implementation, so it works the same on Home Assistant OS, Container,
Core and Supervised.
```

- [x] **Schritt 2: Committen**

```bash
git add README.md
git commit -m "$(cat <<'MSG'
Ergänze die Dokumentation

Der wichtigste Absatz begründet, warum nur Verschwundenes zurückgeholt
wird. Ohne diese Begründung liest sich die Einschränkung wie Faulheit,
statt als das, was sie ist: die Grenze zwischen einer eindeutigen und
einer mehrdeutigen Operation.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
)"
```

---

## Nach der Umsetzung

### Erledigt und geprüft

Alle acht Tasks sind umgesetzt. Die Testsuite läuft grün: **50 synthetische
Tests** plus einer je echtem Dashboard, auf dieser Anlage zusammen 61.

**Die drei Live-Schritte sind bestanden** (2026-08-30, an der eigenen Anlage,
installiert über HACS von `main`):

| Prüfung | Ergebnis |
|---|---|
| `debug_snapshot` | `count: 10`, alle Schlüssel plausibel |
| Warnung »expected shape« | **erscheint nicht** — der Speicherweg trägt, der Rückfall bleibt ungenutzt |
| Erfassung eines neuen Dashboards | sechs Sekunden später als Commit da, ohne Wartezeit |
| Löschtest | »1 removed«, Diff zeigt genau die entfernte Karte |
| Speichern ohne Änderung | kein neuer Commit, HEAD unverändert |
| Rückholung mit `confirm` | Ergebnis byte-identisch mit dem Erststand |
| Verzeichnis | echtes git-Repository, eine `.yaml` je Dashboard |

**Entscheidung 1 der Spec ist damit beantwortet und bestätigt.**

### Drei Befunde aus dem Live-Durchlauf, alle behoben

- **Verschiebungen wurden absolut statt relativ gezählt.** Eine gelöschte
  Karte schob alle dahinterliegenden, und jede davon wurde als Verschiebung
  gemeldet — auf großen Views zwanzig Zeilen Rauschen um die eine Zeile, auf
  die es ankommt. Gezählt wird jetzt der Rang unter den Überlebenden.
- **Die schwache Zuordnung war viel zu eng — und erzeugte Fehlalarme.** Sie
  kannte nur `entity`, `title` und `name`; die trägt auf dieser Anlage nur
  **57 % von 1526 Karten**. Alle anderen — 62 Überschriften, 76 Entitäten-
  listen ohne Titel, 261 Container — wurden beim Bearbeiten als *gelöscht und
  neu angelegt* gemeldet. Die Oberfläche hätte angeboten, etwas
  wiederherzustellen, das unverändert dastand. Nach der Erweiterung auf
  `heading`, erste Entität, erste Textzeile und die benennbare Karte im
  Container sind es **96 %**.
- **Eine abgekürzte Revision wurde stillschweigend falsch beantwortet.**
  `git log --oneline` druckt genau die Kurzform, und dulwich löst sie nicht
  auf — anders als `git` auf der Kommandozeile. Wer sie kopierte, bekam
  »dashboard does not exist at 9e8458d« zu lesen. Das ist eine Aussage über
  die *Historie* des Dashboards, während in Wahrheit die *Eingabe* nicht
  aufgelöst werden konnte: Man sucht den Fehler am falschen Ort. Der
  Speicher löst Kurzformen jetzt über `object_store.iter_prefix` auf
  (mehrdeutige werden abgelehnt statt geraten), und die Dienste
  unterscheiden »unknown revision« von »did not exist at«.

### Offen

- [x] **Entscheidung 1 der Spec beurteilen.** Beantwortet: Der Speicherweg trägt, keine Wartezeit nötig. Spec und Plan sind entsprechend nachgezogen.
- [ ] **Platzbedarf über echte Nutzung messen.** Nach einigen Wochen `du -sh config/dashboard_history/` gegen die Zahl der Commits halten und mit den 27 KB je Stand aus der Spec vergleichen.
- [ ] **Erst danach über Teil 2 entscheiden** — das Panel. Bis dahin zeigt sich, ob die Einordnung in der Praxis das Richtige erkennt.
