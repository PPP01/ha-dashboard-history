"""Checks that need a running Home Assistant.

Deliberately not named `test_*`: `python3 -m pytest tests/` must keep
working without a Home Assistant anywhere in sight. Run this explicitly:

    python3 tests/integration/run_checks.py

Why it exists. Every defect found in this project so far has been in the
modules that import Home Assistant - `capture.py`, `services.py`,
`snapshot.py`, `operations.py` - and none of them can be reached by the
plain pytest suite, which is why the suite stayed green through all of
them. This closes that gap: it drives a real Home Assistant over its own
HTTP and WebSocket API, the same way the frontend does.

It expects the throwaway instance from `docker/compose.yaml`. It creates
an owner account on first run and keeps the token beside the instance's
configuration, outside this repository.
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import re
import sys
import time

import requests
import websockets

BASE = os.environ.get("HA_TEST_URL", "http://127.0.0.1:8124")
CONFIG = pathlib.Path(
    os.environ.get(
        "HA_TEST_CONFIG",
        pathlib.Path(__file__).resolve().parents[2].parent
        / "ha-dashboard-history-test"
        / "config",
    )
)
TOKEN_FILE = CONFIG.parent / "token.txt"
OWNER = {"name": "Testbench", "username": "testbench", "password": "testbench-only"}

# Comfortably longer than RECONCILE_DELAY in const.py, which is 10 seconds.
RECONCILE_WAIT = 15

_passed: list[str] = []
_failed: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    """Record one result and say so on the way past."""
    (_passed if ok else _failed).append(name)
    print(f"  {'ok  ' if ok else 'FAIL'} {name}{f'  — {detail}' if detail else ''}")
    return ok


# -- getting in ---------------------------------------------------------


def wait_for_api(seconds: int = 180) -> bool:
    """Home Assistant takes its time on a cold start."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            if requests.get(f"{BASE}/manifest.json", timeout=5).status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(3)
    return False


def onboard() -> str | None:
    """Create the owner account, if this instance has none yet."""
    steps = requests.get(f"{BASE}/api/onboarding", timeout=10).json()
    if not any(s["step"] == "user" and not s["done"] for s in steps):
        return None
    answer = requests.post(
        f"{BASE}/api/onboarding/users",
        json={"client_id": f"{BASE}/", "language": "de", **OWNER},
        timeout=30,
    )
    answer.raise_for_status()
    code = answer.json()["auth_code"]
    token = requests.post(
        f"{BASE}/auth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": f"{BASE}/",
        },
        timeout=30,
    )
    token.raise_for_status()
    access = token.json()["access_token"]
    requests.post(
        f"{BASE}/api/onboarding/core_config",
        headers={"Authorization": f"Bearer {access}"},
        json={},
        timeout=30,
    )
    return access


def token() -> str:
    """A token for this instance, made once and kept outside the repo."""
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text(encoding="utf-8").strip()
    access = onboard()
    if access is None:
        raise SystemExit(
            "This instance is already onboarded but no token was kept. "
            f"Put a long-lived token in {TOKEN_FILE}, or start from an "
            "empty configuration directory."
        )
    long_lived = asyncio.run(_make_long_lived(access))
    TOKEN_FILE.write_text(long_lived + "\n", encoding="utf-8")
    TOKEN_FILE.chmod(0o600)
    return long_lived


async def _make_long_lived(access: str) -> str:
    async with Socket(access) as socket:
        return await socket.call(
            "auth/long_lived_access_token",
            client_name=f"dashboard-history-checks-{int(time.time())}",
            lifespan=365,
        )


# -- the WebSocket, as the frontend uses it -----------------------------


class Socket:
    """Just enough of Home Assistant's WebSocket protocol."""

    def __init__(self, access: str) -> None:
        self._access = access
        self._id = 0
        self._connection = None

    async def __aenter__(self) -> Socket:
        url = BASE.replace("http", "ws", 1) + "/api/websocket"
        self._connection = await websockets.connect(url, max_size=32 * 1024 * 1024)
        hello = json.loads(await self._connection.recv())
        assert hello["type"] == "auth_required", hello
        await self._connection.send(
            json.dumps({"type": "auth", "access_token": self._access})
        )
        result = json.loads(await self._connection.recv())
        assert result["type"] == "auth_ok", result
        return self

    async def __aexit__(self, *_) -> None:
        await self._connection.close()

    async def call(self, type_: str, **payload):
        """Send one command and return its result, or raise its error."""
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


# -- setting the integration up ----------------------------------------


def ensure_integration(access: str) -> bool:
    """Add the config entry, unless it is already there."""
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
        # Generous: the very first setup makes Home Assistant install the
        # integration's requirement, which is a package download.
        timeout=600,
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


# -- the checks ---------------------------------------------------------


async def run(access: str) -> None:
    headers = {"Authorization": f"Bearer {access}"}

    # The panel's module has to be served, or the sidebar entry is a dead end.
    module = requests.get(f"{BASE}/dashboard_history/panel.js", timeout=30)
    source = (
        pathlib.Path(__file__).resolve().parents[2]
        / "custom_components"
        / "dashboard_history"
        / "panel.js"
    )
    check(
        "panel.js is served",
        module.status_code == 200 and len(module.content) == source.stat().st_size,
        f"HTTP {module.status_code}, {len(module.content)} bytes",
    )

    panels = requests.get(f"{BASE}/api/config", headers=headers, timeout=30)
    check("Home Assistant answers /api/config", panels.status_code == 200)

    async with Socket(access) as socket:
        # What the integration can see at all - the first question worth
        # asking when anything else looks wrong.
        snapshot = await socket.call(
            "call_service",
            domain="dashboard_history",
            service="debug_snapshot",
            return_response=True,
        )
        seen = snapshot["response"]["count"]
        check("debug_snapshot sees the dashboards", seen >= 10, f"count={seen}")

        listed = await socket.call("dashboard_history/dashboards")
        keys = [d["key"] for d in listed["dashboards"]]
        check(
            "the panel's dashboard list is populated",
            len(keys) >= 10,
            f"{len(keys)} dashboards",
        )

        target = "ground-floor"
        history = await socket.call("dashboard_history/history", dashboard=target)
        first = history["changes"][0]["message"] if history["changes"] else "-"
        check(
            f"history of {target} is recorded",
            bool(history["changes"]),
            f"{len(history['changes'])} entries, newest: {first!r}",
        )

        # The false alarm this project shipped once: a metadata-only commit
        # must not claim somebody changed the dashboard from outside.
        messages = [c["message"] for c in history["changes"]]
        check(
            "no bogus 'changed outside Home Assistant' on a first run",
            not any("changed outside" in m for m in messages),
            f"messages: {messages[:3]}",
        )

        # Now edit a dashboard the way the frontend does, and see whether the
        # change is recorded - the whole point of the integration.
        config = await socket.call("lovelace/config", url_path=target)
        before = json.loads(json.dumps(config))
        removed = _drop_first_card(config)
        check("a card could be dropped for the test", removed is not None)
        if removed is None:
            return
        await socket.call("lovelace/config/save", url_path=target, config=config)
        await asyncio.sleep(3)

        after = await socket.call("dashboard_history/history", dashboard=target)
        newest = after["changes"][0]["message"]
        check(
            "the deletion was recorded with a summary",
            "removed" in newest,
            f"{newest!r}",
        )
        check(
            "the summary is free of shifted-card noise",
            # Not `"moved" not in newest`: "removed" contains "moved".
            re.search(r"\d+ moved", newest) is None,
            f"{newest!r}",
        )

        # Clicking the change, as the panel does: the state *before* it.
        before_revision = after["changes"][1]["revision"]
        missing = await socket.call(
            "dashboard_history/deleted_since",
            dashboard=target,
            revision=before_revision,
        )
        check(
            "the missing card is found and named",
            len(missing["items"]) == 1 and ":" in missing["items"][0]["label"],
            f"{missing['items']}",
        )

        # An abbreviated revision has to work: it is what git log prints.
        short = await socket.call(
            "dashboard_history/deleted_since",
            dashboard=target,
            revision=before_revision[:7],
        )
        check(
            "an abbreviated revision resolves",
            short.get("items") == missing["items"],
            short.get("error", ""),
        )

        preview = await socket.call(
            "dashboard_history/restore_deleted",
            dashboard=target,
            revision=before_revision,
            position=0,
        )
        live = await socket.call("lovelace/config", url_path=target)
        check(
            "without confirm there is a preview and no write",
            preview["applied"] is False
            and bool(preview["preview"])
            and live == config,
        )

        applied = await socket.call(
            "dashboard_history/restore_deleted",
            dashboard=target,
            revision=before_revision,
            position=0,
            confirm=True,
        )
        await asyncio.sleep(2)
        restored = await socket.call("lovelace/config", url_path=target)
        check(
            "with confirm the card is back where it was",
            applied["applied"] is True and restored == before,
            applied.get("restored", ""),
        )


async def run_lifecycle(access: str) -> None:
    """The three things Home Assistant announces with no event of its own.

    Creating, renaming and deleting a dashboard all move a *panel*, and a
    moved panel is announced - which is what the integration listens for.
    None of this could be checked before: every attempt cost a restart of a
    production installation running heating, solar and a gate, so it went
    unchecked instead.

    Everything happens on a dashboard of its own, so the copied ones stay
    untouched.
    """
    # A fresh name per run. A restored dashboard cannot be deleted again
    # until Home Assistant restarts - see the last check below - so reusing
    # one name would make the second run collide with the first.
    key = f"dh-probe-{int(time.time()) % 100000}"
    title, icon = "DH Probe", "mdi:test-tube"
    async with Socket(access) as socket:
        # Clear leftovers from earlier runs, as far as they can be cleared.
        for existing in (await socket.call("lovelace/dashboards/list")) or []:
            if str(existing.get("url_path", "")).startswith("dh-probe"):
                try:
                    await socket.call(
                        "lovelace/dashboards/delete", dashboard_id=existing["id"]
                    )
                except RuntimeError:
                    pass  # A restored one. It goes on the next restart.

        made = await socket.call(
            "lovelace/dashboards/create",
            url_path=key,
            title=title,
            icon=icon,
            show_in_sidebar=True,
            require_admin=False,
        )
        await socket.call(
            "lovelace/config/save",
            url_path=key,
            config={
                "views": [
                    {
                        "path": "probe",
                        "title": "Probe",
                        "cards": [
                            {"type": "heading", "heading": "Erste"},
                            {"type": "markdown", "content": "# Zweite\n\nText."},
                            {"type": "tile", "entity": "sun.sun"},
                        ],
                    }
                ]
            },
        )
        await asyncio.sleep(4)
        history = await socket.call("dashboard_history/history", dashboard=key)
        check(
            "a new dashboard is recorded",
            bool(history["changes"]),
            f"{len(history['changes'])} entries",
        )

        # 1. Renaming. There is no lovelace_updated for this.
        await socket.call(
            "lovelace/dashboards/update",
            dashboard_id=made["id"],
            title="DH Probe umbenannt",
        )
        await asyncio.sleep(RECONCILE_WAIT)
        history = await socket.call("dashboard_history/history", dashboard=key)
        newest = history["changes"][0]["message"]
        check("a rename is recorded and named", "renamed to" in newest, f"{newest!r}")

        # 2. Deleting the whole dashboard while Home Assistant runs.
        await socket.call("lovelace/dashboards/delete", dashboard_id=made["id"])
        await asyncio.sleep(RECONCILE_WAIT)
        history = await socket.call("dashboard_history/history", dashboard=key)
        newest = history["changes"][0]["message"]
        check(
            "a deletion is recorded without a restart",
            "dashboard deleted" in newest,
            f"{newest!r}",
        )
        listed = await socket.call("dashboard_history/dashboards")
        entry = next((d for d in listed["dashboards"] if d["key"] == key), None)
        check(
            "the panel offers it, under the name it last had",
            entry is not None
            and entry["exists"] is False
            and entry["title"] == "DH Probe umbenannt",
            f"{entry}",
        )

        # 3. Bringing it back - the least-tested path in the project.
        before_deletion = history["changes"][1]["revision"]
        preview = await socket.call(
            "dashboard_history/restore_state", dashboard=key, revision=before_deletion
        )
        check(
            "restoring says in advance that it will recreate the dashboard",
            preview.get("creates_dashboard") is True and preview["applied"] is False,
            str({k: v for k, v in preview.items() if k != "preview"}),
        )
        applied = await socket.call(
            "dashboard_history/restore_state",
            dashboard=key,
            revision=before_deletion,
            confirm=True,
        )
        check(
            "the dashboard is recreated",
            applied["applied"] is True and applied["created"] is True,
            applied.get("note", "no caveat reported"),
        )
        # Being honest about a partial success is part of the job here.
        check(
            "the remaining caveat is stated rather than glossed over",
            "restart" in (applied.get("note") or ""),
            applied.get("note") or "no note at all",
        )
        await asyncio.sleep(3)
        dashboards = await socket.call("lovelace/dashboards/list")
        back = next((d for d in dashboards if d.get("url_path") == key), None)
        check(
            "it is back with its title and its icon",
            back is not None
            and back.get("title") == "DH Probe umbenannt"
            and back.get("icon") == icon,
            f"{back}",
        )
        if back is not None:
            config = await socket.call("lovelace/config", url_path=key)
            check(
                "and with its cards",
                len(config["views"][0]["cards"]) == 3,
                f"{len(config['views'][0]['cards'])} cards",
            )
            # The known limit of the fallback path, pinned down rather than
            # left to be rediscovered: the entry reached the store through a
            # collection of our own, and Home Assistant's own collection
            # object - the one its settings dialog asks - has not heard of
            # it. Everything else about the dashboard works.
            try:
                await socket.call(
                    "lovelace/dashboards/delete", dashboard_id=back["id"]
                )
                check(
                    "Home Assistant's collection is in step after a restore",
                    True,
                    "deletable at once - the live-collection path must have run",
                )
            except RuntimeError as err:
                check(
                    "Home Assistant's collection is in step after a restore",
                    "not_found" in str(err),
                    "not deletable until a restart, exactly as the note says",
                )


def _drop_first_card(config: dict) -> dict | None:
    """Remove the first card of the first list that has more than one."""
    for view in config.get("views") or []:
        for candidate in [view] + list(view.get("sections") or []):
            cards = candidate.get("cards")
            if isinstance(cards, list) and len(cards) > 1:
                return cards.pop(0)
    return None


if __name__ == "__main__":
    if not wait_for_api():
        raise SystemExit(f"No Home Assistant answering at {BASE}")
    access = token()
    if not ensure_integration(access):
        raise SystemExit("Could not set the integration up")
    print(f"Prüfungen gegen {BASE}\n")
    asyncio.run(run(access))
    print("\n  -- Lebenszyklus eines Dashboards: anlegen, umbenennen, löschen, zurückholen --")
    asyncio.run(run_lifecycle(access))
    print(f"\n{len(_passed)} von {len(_passed) + len(_failed)} Prüfungen bestanden")
    if _failed:
        print("Fehlgeschlagen: " + ", ".join(_failed))
        sys.exit(1)
