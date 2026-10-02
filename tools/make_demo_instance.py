#!/usr/bin/env python3
"""Build the demo instance dashboards and history from scratch.

This script provisions a reproducible Home Assistant instance for demo
screenshots (such as the ones captured by tools/capture_demo_screenshots.py).

Prerequisites:
  A running demo Home Assistant instance (e.g. via docker/compose.demo.yaml)
  reachable at DASHBOARD_HISTORY_DEMO_URL (default: http://127.0.0.1:8125).

Dashboards created:
  - home-overview: Plausible overview dashboard with generic entities.
  - dashboard-standard: Standard secondary dashboard for sidebar list.
  - living-room: Main demo dashboard with multiple recorded changes
    (add, edit, remove) and two named milestone versions (v1.0.0, v1.1.0).

Idempotency:
  This script is safe to run multiple times. Dashboards are matched
  strictly by exact url_path (never deleted and recreated). If living-room
  already contains the target versions (v1.0.0 and v1.1.0) and recorded
  history, version creation and history mutations are skipped.
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import sys
import time

import requests
import websockets

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEMO = pathlib.Path(
    os.environ.get("DASHBOARD_HISTORY_DEMO") or ROOT.parent / "ha-dashboard-history-demo"
)
BASE = os.environ.get("DASHBOARD_HISTORY_DEMO_URL", "http://127.0.0.1:8125")
TOKEN_FILE = DEMO / "token.txt"

OWNER = {"name": "Demo User", "username": "demo", "password": "demo-instance-only"}

KEY_HOME = "home-overview"
KEY_STANDARD = "dashboard-standard"
KEY_LIVING_ROOM = "living-room"

TWIN_ENTITY = "sun.sun"


class Socket:
    """Minimal WebSocket client for Home Assistant's API."""

    def __init__(self, access: str) -> None:
        self._access = access
        self._id = 0
        self._connection: websockets.WebSocketClientProtocol | None = None

    async def __aenter__(self) -> Socket:
        url = BASE.replace("http", "ws", 1) + "/api/websocket"
        self._connection = await websockets.connect(url, max_size=32 * 1024 * 1024)
        hello = json.loads(await self._connection.recv())
        assert hello.get("type") == "auth_required", hello
        await self._connection.send(
            json.dumps({"type": "auth", "access_token": self._access})
        )
        result = json.loads(await self._connection.recv())
        assert result.get("type") == "auth_ok", result
        return self

    async def __aexit__(self, *_) -> None:
        if self._connection is not None:
            await self._connection.close()

    async def call(self, type_: str, **payload):
        """Send one command and return its result, or raise RuntimeError."""
        self._id += 1
        await self._connection.send(
            json.dumps({"id": self._id, "type": type_, **payload})
        )
        while True:
            message = json.loads(await self._connection.recv())
            if message.get("id") != self._id or message.get("type") != "result":
                continue
            if not message.get("success"):
                raise RuntimeError(f"{type_}: {message.get('error')}")
            return message.get("result")


def wait_for_api(seconds: int = 180) -> bool:
    """Wait until Home Assistant HTTP API responds."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            if requests.get(f"{BASE}/manifest.json", timeout=5).status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(2)
    return False


def wait_for_integration(access: str, seconds: int = 120) -> bool:
    """Wait until dashboard_history services are registered in Home Assistant."""
    headers = {"Authorization": f"Bearer {access}"}
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            answer = requests.get(f"{BASE}/api/services", headers=headers, timeout=10)
            if answer.status_code == 200 and any(
                entry.get("domain") == "dashboard_history" for entry in answer.json()
            ):
                return True
        except requests.RequestException:
            pass
        time.sleep(2)
    return False


def onboard() -> str | None:
    """Create the owner user account if onboarding is pending."""
    try:
        steps = requests.get(f"{BASE}/api/onboarding", timeout=10).json()
    except requests.RequestException:
        return None
    if not any(s.get("step") == "user" and not s.get("done") for s in steps):
        return None
    answer = requests.post(
        f"{BASE}/api/onboarding/users",
        json={"client_id": f"{BASE}/", "language": "en", **OWNER},
        timeout=30,
    )
    answer.raise_for_status()
    access = _exchange_code(answer.json()["auth_code"])
    headers = {"Authorization": f"Bearer {access}"}
    requests.post(
        f"{BASE}/api/onboarding/core_config",
        headers=headers,
        json={},
        timeout=30,
    )
    try:
        requests.post(
            f"{BASE}/api/onboarding/analytics",
            headers=headers,
            json={"preferences": {}},
            timeout=30,
        )
    except requests.RequestException:
        pass
    try:
        requests.post(
            f"{BASE}/api/onboarding/integration",
            headers=headers,
            json={"client_id": f"{BASE}/", "redirect_uri": f"{BASE}/"},
            timeout=30,
        )
    except requests.RequestException:
        pass
    return access


def _exchange_code(code: str) -> str:
    """Exchange authorization code for an initial access token."""
    granted = requests.post(
        f"{BASE}/auth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": f"{BASE}/",
        },
        timeout=30,
    )
    granted.raise_for_status()
    return granted.json()["access_token"]


async def _make_long_lived(access: str) -> str:
    """Request a long-lived access token valid for 10 years."""
    async with Socket(access) as socket:
        return await socket.call(
            "auth/long_lived_access_token",
            client_name=f"dashboard-history-demo-{int(time.time())}",
            lifespan=3650,
        )


def ensure_integration(access: str) -> bool:
    """Ensure the dashboard_history config entry exists."""
    headers = {"Authorization": f"Bearer {access}"}
    entries = requests.get(
        f"{BASE}/api/config/config_entries/entry", headers=headers, timeout=30
    ).json()
    if any(entry.get("domain") == "dashboard_history" for entry in entries):
        return True
    flow = requests.post(
        f"{BASE}/api/config/config_entries/flow",
        headers=headers,
        json={"handler": "dashboard_history", "show_advanced_options": False},
        timeout=60,
    )
    flow.raise_for_status()
    step = flow.json()
    if step.get("type") == "create_entry":
        return True
    done = requests.post(
        f"{BASE}/api/config/config_entries/flow/{step['flow_id']}",
        headers=headers,
        json={},
        timeout=60,
    )
    done.raise_for_status()
    return done.json().get("type") == "create_entry"


def get_token() -> str:
    """Retrieve existing token or onboard fresh instance."""
    if TOKEN_FILE.exists():
        stored = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if stored:
            return stored

    access = onboard()
    if access is None:
        raise SystemExit(
            f"This instance is already onboarded but no token was found at {TOKEN_FILE}.\n"
            f"Put a long-lived access token there or start from a clean config directory."
        )

    long_lived = asyncio.run(_make_long_lived(access))
    DEMO.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(long_lived + "\n", encoding="utf-8")
    TOKEN_FILE.chmod(0o600)
    print(f"Created long-lived demo token at {TOKEN_FILE}")
    return long_lived


async def _wait_until_recorded(socket: Socket, key: str, seconds: float = 60) -> list[dict]:
    """Wait until the newest recorded state matches what is currently live."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        answer = await socket.call("dashboard_history/history", dashboard=key)
        changes = answer.get("changes", [])
        if changes and changes[0].get("same_as_now"):
            return changes
        await asyncio.sleep(1.0)
    raise TimeoutError(f"Timed out waiting for initial recording on {key}")


async def _wait_for_new_state(socket: Socket, key: str, seen_rev: str, seconds: float = 60) -> list[dict]:
    """Wait until a new state distinct from seen_rev has been recorded and matches live."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        answer = await socket.call("dashboard_history/history", dashboard=key)
        changes = answer.get("changes", [])
        if changes and changes[0]["revision"] != seen_rev and changes[0].get("same_as_now"):
            return changes
        await asyncio.sleep(1.0)
    raise TimeoutError(f"Timed out waiting for new state on {key} after revision {seen_rev}")


# -- Dashboard Configurations -------------------------------------------

HOME_OVERVIEW_CONFIG = {
    "views": [
        {
            "title": "Overview",
            "path": "overview",
            "cards": [
                {"type": "heading", "heading": "Home Overview"},
                {
                    "type": "tile",
                    "entity": TWIN_ENTITY,
                    "name": "Sun State",
                    "icon": "mdi:weather-sunny",
                },
                {
                    "type": "markdown",
                    "content": "Welcome to the Home Assistant demo instance.",
                },
            ],
        }
    ]
}

STANDARD_CONFIG = {
    "views": [
        {
            "title": "Standard",
            "path": "standard",
            "cards": [
                {"type": "heading", "heading": "Standard Dashboard"},
                {
                    "type": "tile",
                    "entity": TWIN_ENTITY,
                    "name": "Sun Position",
                    "icon": "mdi:sun-compass",
                },
            ],
        }
    ]
}

# Living Room evolution states:
# State 1: Initial layout (Tagged as v1.0.0)
LIVING_ROOM_S1 = {
    "views": [
        {
            "title": "Overview",
            "path": "overview",
            "cards": [
                {"type": "heading", "heading": "Living Room"},
                {
                    "type": "tile",
                    "entity": TWIN_ENTITY,
                    "name": "Sun Elevation",
                    "icon": "mdi:weather-sunny",
                },
                {
                    "type": "markdown",
                    "title": "Morning Checklist",
                    "content": "## Morning Notes\n- Check ambient light\n- Open blinds",
                },
                {
                    "type": "tile",
                    "entity": TWIN_ENTITY,
                    "name": "Solar Noon",
                    "color": "amber",
                    "icon": "mdi:white-balance-sunny",
                },
            ],
        }
    ]
}

# State 2: Add card (Sunset Alert) -> Tagged as v1.1.0
LIVING_ROOM_S2 = {
    "views": [
        {
            "title": "Overview",
            "path": "overview",
            "cards": [
                {"type": "heading", "heading": "Living Room"},
                {
                    "type": "tile",
                    "entity": TWIN_ENTITY,
                    "name": "Sun Elevation",
                    "icon": "mdi:weather-sunny",
                },
                {
                    "type": "markdown",
                    "title": "Morning Checklist",
                    "content": "## Morning Notes\n- Check ambient light\n- Open blinds",
                },
                {
                    "type": "tile",
                    "entity": TWIN_ENTITY,
                    "name": "Solar Noon",
                    "color": "amber",
                    "icon": "mdi:white-balance-sunny",
                },
                {
                    "type": "tile",
                    "entity": TWIN_ENTITY,
                    "name": "Sunset Alert",
                    "icon": "mdi:weather-sunset-down",
                    "color": "deep-orange",
                },
            ],
        }
    ]
}

# State 3: Add card (Night Light) [RIGHT NOW - change 1: added]
LIVING_ROOM_S3 = {
    "views": [
        {
            "title": "Overview",
            "path": "overview",
            "cards": [
                {"type": "heading", "heading": "Living Room"},
                {
                    "type": "tile",
                    "entity": TWIN_ENTITY,
                    "name": "Sun Elevation",
                    "icon": "mdi:weather-sunny",
                },
                {
                    "type": "markdown",
                    "title": "Morning Checklist",
                    "content": "## Morning Notes\n- Check ambient light\n- Open blinds",
                },
                {
                    "type": "tile",
                    "entity": TWIN_ENTITY,
                    "name": "Solar Noon",
                    "color": "amber",
                    "icon": "mdi:white-balance-sunny",
                },
                {
                    "type": "tile",
                    "entity": TWIN_ENTITY,
                    "name": "Sunset Alert",
                    "icon": "mdi:weather-sunset-down",
                    "color": "deep-orange",
                },
                {
                    "type": "tile",
                    "entity": TWIN_ENTITY,
                    "name": "Night Light",
                    "icon": "mdi:weather-night",
                    "color": "indigo",
                },
            ],
        }
    ]
}

# State 4: Edit card (Solar Noon -> Peak Sunlight: change name, color, icon) [RIGHT NOW - change 2: edited]
LIVING_ROOM_S4 = {
    "views": [
        {
            "title": "Overview",
            "path": "overview",
            "cards": [
                {"type": "heading", "heading": "Living Room"},
                {
                    "type": "tile",
                    "entity": TWIN_ENTITY,
                    "name": "Sun Elevation",
                    "icon": "mdi:weather-sunny",
                },
                {
                    "type": "markdown",
                    "title": "Morning Checklist",
                    "content": "## Morning Notes\n- Check ambient light\n- Open blinds",
                },
                {
                    "type": "tile",
                    "entity": TWIN_ENTITY,
                    "name": "Peak Sunlight",
                    "color": "orange",
                    "icon": "mdi:sun-clock",
                },
                {
                    "type": "tile",
                    "entity": TWIN_ENTITY,
                    "name": "Sunset Alert",
                    "icon": "mdi:weather-sunset-down",
                    "color": "deep-orange",
                },
                {
                    "type": "tile",
                    "entity": TWIN_ENTITY,
                    "name": "Night Light",
                    "icon": "mdi:weather-night",
                    "color": "indigo",
                },
            ],
        }
    ]
}

# State 5: Remove card (Morning Checklist deleted) [RIGHT NOW - change 3: removed]
LIVING_ROOM_S5 = {
    "views": [
        {
            "title": "Overview",
            "path": "overview",
            "cards": [
                {"type": "heading", "heading": "Living Room"},
                {
                    "type": "tile",
                    "entity": TWIN_ENTITY,
                    "name": "Sun Elevation",
                    "icon": "mdi:weather-sunny",
                },
                {
                    "type": "tile",
                    "entity": TWIN_ENTITY,
                    "name": "Peak Sunlight",
                    "color": "orange",
                    "icon": "mdi:sun-clock",
                },
                {
                    "type": "tile",
                    "entity": TWIN_ENTITY,
                    "name": "Sunset Alert",
                    "icon": "mdi:weather-sunset-down",
                    "color": "deep-orange",
                },
                {
                    "type": "tile",
                    "entity": TWIN_ENTITY,
                    "name": "Night Light",
                    "icon": "mdi:weather-night",
                    "color": "indigo",
                },
            ],
        }
    ]
}


async def setup_dashboards(access: str) -> None:
    """Provision the three demo dashboards and build living-room history."""
    async with Socket(access) as socket:
        dashboards = (await socket.call("lovelace/dashboards/list")) or []
        existing_keys = {d.get("url_path") for d in dashboards}

        # 1. Home Overview
        if KEY_HOME in existing_keys:
            print(f"  {KEY_HOME} already registered - updating configuration")
        else:
            await socket.call(
                "lovelace/dashboards/create",
                url_path=KEY_HOME,
                title="Home Overview",
                icon="mdi:home",
                show_in_sidebar=True,
                require_admin=False,
            )
            print(f"  Created dashboard {KEY_HOME}")
        await socket.call("lovelace/config/save", url_path=KEY_HOME, config=HOME_OVERVIEW_CONFIG)

        # 2. Standard Dashboard
        if KEY_STANDARD in existing_keys:
            print(f"  {KEY_STANDARD} already registered - updating configuration")
        else:
            await socket.call(
                "lovelace/dashboards/create",
                url_path=KEY_STANDARD,
                title="Standard",
                icon="mdi:home-assistant",
                show_in_sidebar=True,
                require_admin=False,
            )
            print(f"  Created dashboard {KEY_STANDARD}")
        await socket.call("lovelace/config/save", url_path=KEY_STANDARD, config=STANDARD_CONFIG)

        # 3. Living Room
        if KEY_LIVING_ROOM not in existing_keys:
            await socket.call(
                "lovelace/dashboards/create",
                url_path=KEY_LIVING_ROOM,
                title="Living Room",
                icon="mdi:sofa",
                show_in_sidebar=True,
                require_admin=False,
            )
            print(f"  Created dashboard {KEY_LIVING_ROOM}")
        else:
            print(f"  {KEY_LIVING_ROOM} already registered")

        # Check existing versions and history for idempotency
        versions_resp = await socket.call("dashboard_history/versions", dashboard=KEY_LIVING_ROOM)
        existing_versions = [v["name"] for v in versions_resp.get("versions", [])]
        has_v100 = any(name.endswith("/v1.0.0") for name in existing_versions)
        has_v110 = any(name.endswith("/v1.1.0") for name in existing_versions)

        history_resp = await socket.call("dashboard_history/history", dashboard=KEY_LIVING_ROOM)
        existing_changes = history_resp.get("changes", [])
        has_history = len(existing_changes) >= 3

        if has_v100 and has_v110 and has_history:
            print(f"  {KEY_LIVING_ROOM} already has target versions (v1.0.0, v1.1.0) and history - skipping mutations")
            # Ensure final configuration matches desired live state
            await socket.call("lovelace/config/save", url_path=KEY_LIVING_ROOM, config=LIVING_ROOM_S5)
        else:
            print(f"  Building history and versions for {KEY_LIVING_ROOM}...")

            # State 1: Base layout
            print("    1/5 Saving base layout...")
            await socket.call("lovelace/config/save", url_path=KEY_LIVING_ROOM, config=LIVING_ROOM_S1)
            changes = await _wait_until_recorded(socket, KEY_LIVING_ROOM)
            last_rev = changes[0]["revision"]

            # Tag v1.0.0
            next_resp = await socket.call("dashboard_history/next_versions", dashboard=KEY_LIVING_ROOM)
            candidates = next_resp.get("candidates", {})
            level_v100 = next(
                lvl for lvl, tag in candidates.items() if tag and tag.endswith("/v1.0.0")
            )
            print(f"    Tagging v1.0.0 (level={level_v100})...")
            await socket.call(
                "dashboard_history/create_version",
                dashboard=KEY_LIVING_ROOM,
                level=level_v100,
                title="Initial layout",
                description="First working layout with sun elevation and morning checklist.",
            )

            # State 2: Add Sunset Alert card
            print("    2/5 Adding card (Sunset Alert)...")
            await socket.call("lovelace/config/save", url_path=KEY_LIVING_ROOM, config=LIVING_ROOM_S2)
            changes = await _wait_for_new_state(socket, KEY_LIVING_ROOM, last_rev)
            last_rev = changes[0]["revision"]

            # Tag v1.1.0
            next_resp = await socket.call("dashboard_history/next_versions", dashboard=KEY_LIVING_ROOM)
            candidates = next_resp.get("candidates", {})
            level_v110 = next(
                lvl for lvl, tag in candidates.items() if tag and tag.endswith("/v1.1.0")
            )
            print(f"    Tagging v1.1.0 (level={level_v110})...")
            await socket.call(
                "dashboard_history/create_version",
                dashboard=KEY_LIVING_ROOM,
                level=level_v110,
                title="Swap the morning cards",
                description="Added sunset alert card for evening lighting routine.",
            )

            # State 3: Add Night Light card (unversioned change 1)
            print("    3/5 Adding card (Night Light)...")
            await socket.call("lovelace/config/save", url_path=KEY_LIVING_ROOM, config=LIVING_ROOM_S3)
            changes = await _wait_for_new_state(socket, KEY_LIVING_ROOM, last_rev)
            last_rev = changes[0]["revision"]

            # State 4: Edit Solar Noon -> Peak Sunlight (unversioned change 2: title/icon/color)
            print("    4/5 Editing card (Peak Sunlight)...")
            await socket.call("lovelace/config/save", url_path=KEY_LIVING_ROOM, config=LIVING_ROOM_S4)
            changes = await _wait_for_new_state(socket, KEY_LIVING_ROOM, last_rev)
            last_rev = changes[0]["revision"]

            # State 5: Remove Morning Checklist card (unversioned change 3: card removed)
            print("    5/5 Removing card (Morning Checklist)...")
            await socket.call("lovelace/config/save", url_path=KEY_LIVING_ROOM, config=LIVING_ROOM_S5)
            changes = await _wait_for_new_state(socket, KEY_LIVING_ROOM, last_rev)
            last_rev = changes[0]["revision"]

            print(f"  {KEY_LIVING_ROOM} history successfully built.")


def main() -> None:
    """Main setup routine."""
    print("Connecting to demo Home Assistant instance...")
    if not wait_for_api():
        sys.exit(f"Home Assistant is not answering at {BASE}. Is docker/compose.demo.yaml up?")

    access = get_token()
    print("Ensuring dashboard_history integration is set up...")
    ensure_integration(access)

    if not wait_for_integration(access):
        sys.exit("dashboard_history integration services failed to appear.")

    print("Provisioning dashboards and history...")
    asyncio.run(setup_dashboards(access))

    print("\nDemo dashboards ready:")
    print(f"  - Home Overview:    {BASE}/{KEY_HOME}")
    print(f"  - Standard:         {BASE}/{KEY_STANDARD}")
    print(f"  - Living Room:      {BASE}/{KEY_LIVING_ROOM}")
    print(f"  - History Panel:    {BASE}/dashboard-history")


if __name__ == "__main__":
    main()
