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
import hashlib
import json
import os
import pathlib
import re
import sys
import time

import requests
import websockets

BASE = os.environ.get("HA_TEST_URL", "http://127.0.0.1:8124")
# Read from the integration rather than repeated here: this file cannot
# import it (no Home Assistant), and a second copy of an event name is a
# second thing to forget when it changes.
EVENT_HISTORY_UPDATED = re.search(
    r'^EVENT_HISTORY_UPDATED = "([^"]+)"',
    (
        pathlib.Path(__file__).resolve().parents[2]
        / "custom_components"
        / "dashboard_history"
        / "const.py"
    ).read_text(encoding="utf-8"),
    re.M,
).group(1)
CONFIG = pathlib.Path(
    os.environ.get(
        "HA_TEST_CONFIG",
        pathlib.Path(__file__).resolve().parents[2].parent
        / "ha-dashboard-history-test"
        / "config",
    )
)
TOKEN_FILE = CONFIG.parent / "token.txt"

# Which dashboard the checks work against. A name out of one installation
# does not belong in a public repository, and hard-coding one makes these
# checks unrunnable for anybody else besides. Beside the instance like the
# token, or from the environment; failing both, it is chosen (pick_target).
TARGET_FILE = CONFIG.parent / "check-dashboard.txt"
TARGET = os.environ.get("DASHBOARD_HISTORY_CHECK_DASHBOARD", "") or (
    TARGET_FILE.read_text(encoding="utf-8").strip() if TARGET_FILE.exists() else ""
)
OWNER = {"name": "Testbench", "username": "testbench", "password": "testbench-only"}

# Comfortably longer than RECONCILE_DELAY in const.py, which is 10 seconds.
RECONCILE_WAIT = 15

# How long a check may wait for the recorder to have written something.
# Measured on 2026-09-04 against a repository grown by a day of test
# runs: a save appeared after 14.1 s, a deletion after 45.9 s - the
# latter is reconciliation, which walks every tracked dashboard. The
# ceiling here used to be RECORDING_WAIT, which is 45 s, and it sat
# just under that measurement: a slow pass came out as a failed check.
# Every wait ends the moment its condition holds, so a generous ceiling
# costs nothing except in the case it exists for.
RECORDING_WAIT = 120

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


def wait_for_integration(access: str, seconds: int = 120) -> bool:
    """Wait until the integration's services are actually registered.

    /manifest.json answers long before this. On a restart the config entry
    is already there, so ensure_integration returns at once - and the very
    first check then ran against a Home Assistant that had not set the
    integration up yet. That produced two false failures and a crash, twice
    in a row, and cost a container restart to chase. A readiness signal has
    to be the thing the checks depend on, not the nearest thing answering.
    """
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
    access = _exchange_code(answer.json()["auth_code"])
    requests.post(
        f"{BASE}/api/onboarding/core_config",
        headers={"Authorization": f"Bearer {access}"},
        json={},
        timeout=30,
    )
    return access


def _exchange_code(code: str) -> str:
    """Trade an authorization code for an access token, as a browser would."""
    granted = requests.post(
        f"{BASE}/auth/token",
        data={"grant_type": "authorization_code", "code": code, "client_id": f"{BASE}/"},
        timeout=30,
    )
    granted.raise_for_status()
    return granted.json()["access_token"]


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

    async def wait_for_event(self, event_type: str, seconds: float = 10):
        """Read pushed messages until one is the event asked for.

        Its own reader, because `call` throws away every message that is
        not the answer it waits for - subscribed events included. Answers
        None on timeout rather than raising: "it never came" is a result
        a check wants to report, not an exception.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + seconds
        while True:
            left = deadline - loop.time()
            if left <= 0:
                return None
            try:
                raw = await asyncio.wait_for(self._connection.recv(), timeout=left)
            except (asyncio.TimeoutError, TimeoutError):
                return None
            message = json.loads(raw)
            if message.get("type") != "event":
                continue
            if message.get("event", {}).get("event_type") == event_type:
                return message["event"]


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


async def pick_target(access: str) -> str:
    """Which dashboard the checks work on, when nobody has named one.

    The live dashboard with the most recorded states: these checks need
    history to read and an existing dashboard to write back to. Chosen
    rather than named, so that somebody else can run them at all.
    """
    async with Socket(access) as socket:
        listing = await socket.call("dashboard_history/dashboards")
        best, most = "", -1
        for entry in listing.get("dashboards") or []:
            if not entry.get("exists"):
                continue
            answer = await socket.call(
                "dashboard_history/history", dashboard=entry["key"]
            )
            if len(answer["changes"]) > most:
                best, most = entry["key"], len(answer["changes"])
    return best

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

    # And so do the parts it imports. The directory is registered as a
    # static path of its own, separately from panel.js - so it can break on
    # its own too, and then the panel loads and draws nothing. Naming each
    # part in the check means a failure says which one is missing.
    for part in ("style.js", "render.js"):
        served = requests.get(f"{BASE}/dashboard_history/panel/{part}", timeout=30)
        on_disk = source.parent / "panel" / part
        size = on_disk.stat().st_size if on_disk.exists() else -1
        check(
            f"panel/{part} is served",
            served.status_code == 200 and len(served.content) == size,
            f"HTTP {served.status_code}, {len(served.content)} bytes"
            f" against {size} on disk",
        )

    # And it is served under a URL that changes when the file does. This
    # used to be a hand-maintained constant, so a changed panel kept being
    # served from the browser cache under the same URL - which is how a
    # finished feature reached somebody as "the button is not there".
    async with Socket(access) as socket:
        panels = await socket.call("get_panels")
    module_url = (panels.get("dashboard-history") or {}).get("config", {}).get(
        "_panel_custom", {}
    ).get("module_url", "")
    # Mirrors panel.py's _fingerprint: every file the panel is built from,
    # entry point first and the parts sorted after it, each one's path
    # relative to the package plus its content. Digesting panel.js alone
    # would let a changed part keep its cached URL.
    digest = hashlib.sha256()
    for path in [source, *sorted((source.parent / "panel").rglob("*.js"))]:
        digest.update(path.relative_to(source.parent).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    want = digest.hexdigest()[:12]
    fresh = f"v={want}" in module_url
    if not module_url:
        detail = "no module_url found"
    elif fresh:
        detail = module_url
    else:
        detail = (
            f"{module_url} but the files hash to {want} - either the panel "
            "changed since Home Assistant registered it, so restart the "
            "container, or this digest has drifted apart from _fingerprint "
            "in panel.py and the two no longer compute the same thing"
        )
    check("the panel module URL carries a fingerprint of the file", fresh, detail)

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

        target = TARGET
        history = await socket.call("dashboard_history/history", dashboard=target)
        first = history["changes"][0]["message"] if history["changes"] else "-"
        check(
            f"history of {target} is recorded",
            bool(history["changes"]),
            f"{len(history['changes'])} entries, newest: {first!r}",
        )

        # The false alarm this project shipped once: a metadata-only commit
        # must not claim somebody changed the dashboard from outside. The
        # newest entry only - that is the one a startup pass writes. Every
        # entry used to be asked, and a genuine outside change anywhere in
        # the last fifty (this bench has one: a save lost to a crashed run,
        # recorded at the next start, correctly) failed the check for weeks.
        messages = [c["message"] for c in history["changes"]]
        check(
            "no bogus 'changed outside Home Assistant' on a first run",
            "changed outside" not in messages[0],
            f"newest: {messages[0]!r}",
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
        # Polled, not slept: right after a restart the recorder is still
        # in its startup pass over every dashboard, and a save heard then
        # waits for the write lock behind it - about twenty seconds on
        # this bench. Measured on 2026-09-04, a three-second sleep looked
        # at the history before the save had reached it.
        newest = await _wait_for_newest(socket, target, "removed", RECORDING_WAIT)
        after = await socket.call("dashboard_history/history", dashboard=target)
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
            and bool(preview.get("preview"))
            and live == config,
            preview.get("error", ""),
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
    # One key for every run, not one per run.
    #
    # It used to carry a timestamp, because a restored dashboard could not
    # be deleted again and a reused name would have collided with the
    # leftover. That reason is gone: restoring now goes through Home
    # Assistant's own collection, so the cleanup below actually works.
    #
    # The timestamp had a cost that only showed up in the panel. A deleted
    # dashboard keeps its history forever - that is the point of the tool -
    # so every run added another dead "DH Probe" to the dashboard list, and
    # after a dozen runs that list was mostly litter.
    key = "dh-probe-check"
    title, icon = "DH Probe", "mdi:test-tube"
    renamed_title = "DH Probe umbenannt"
    async with Socket(access) as socket:
        # Clear a leftover from an earlier run - this key and nothing else.
        #
        # It used to match on the prefix "dh-probe", and on 2026-09-01 that
        # swept up a dashboard somebody was working in, because "dh-probe"
        # starts with "dh-probe". It had been wrong for days without
        # showing: deleting a restored dashboard failed with not_found back
        # then, so the loop was destructive in intent and harmless in
        # effect. Fixing that failure made it bite. A test that deletes
        # things must name them exactly.
        for existing in (await socket.call("lovelace/dashboards/list")) or []:
            if existing.get("url_path") == key:
                try:
                    await socket.call(
                        "lovelace/dashboards/delete", dashboard_id=existing["id"]
                    )
                except RuntimeError:
                    pass  # Not there in a shape we can delete; the run goes on.

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
        await _wait_until_recorded(socket, key)
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
            title=renamed_title,
        )
        # Polled rather than slept for a fixed time. The reconciliation
        # starts RECONCILE_DELAY after the rename and then walks every
        # dashboard under the write lock - measured on 2026-09-04 at
        # about ten seconds for the eighteen on this bench, which put the
        # rename commit within a second of a fixed fifteen-second wait
        # and made this check fail one run in three.
        newest = await _wait_for_newest(socket, key, "renamed to", RECORDING_WAIT)
        check("a rename is recorded and named", "renamed to" in newest, f"{newest!r}")

        # 2. Deleting the whole dashboard while Home Assistant runs.
        await socket.call("lovelace/dashboards/delete", dashboard_id=made["id"])
        newest = await _wait_for_newest(socket, key, "dashboard deleted", RECORDING_WAIT)
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
            and entry["title"] == renamed_title,
            f"{entry}",
        )

        # 3. Bringing it back - the least-tested path in the project.
        history = await socket.call("dashboard_history/history", dashboard=key)
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
        check(
            "no caveat is left to report",
            not applied.get("note"),
            applied.get("note") or "none - the dashboard is fully restored",
        )
        await asyncio.sleep(3)
        dashboards = await socket.call("lovelace/dashboards/list")
        back = next((d for d in dashboards if d.get("url_path") == key), None)
        check(
            "it is back with its title and its icon",
            back is not None
            and back.get("title") == renamed_title
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
            # Home Assistant reads a dashboard list from one place and
            # applies changes to another: `lovelace/dashboards/list` is
            # overridden to report LovelaceData.dashboards, while update and
            # delete go to its own DashboardsCollection. A restored
            # dashboard that only reached the first looks perfectly healthy
            # and cannot be renamed - which is what a person hits, and what
            # these three checks are for.
            try:
                await socket.call(
                    "lovelace/dashboards/update",
                    dashboard_id=back["id"],
                    title=f"{renamed_title} II",
                )
                renamed = True
                detail = "renamed through Home Assistant's own settings"
            except RuntimeError as err:
                renamed = False
                detail = str(err)
            check("a restored dashboard can be renamed", renamed, detail)

            # And the harder half. Home Assistant's collection writes its
            # whole in-memory state back to the store on any create or
            # delete. An entry it does not know is therefore dropped from
            # disk without a word, and the dashboard is gone at the next
            # restart. Measured on 2026-08-31: exactly that had happened to
            # two restored dashboards, still in the sidebar, no longer on
            # disk.
            on_disk = await _wait_for_store_entry(back["id"])
            check(
                "and it is on disk, not only in memory",
                on_disk,
                f"{back['id']} in lovelace_dashboards"
                if on_disk
                else f"{back['id']} MISSING from lovelace_dashboards - it would "
                "vanish at the next restart",
            )

            # Durability on disk, which the two checks above cannot show on
            # their own: the entry was just written, so of course it is
            # there. This provokes a save by Home Assistant itself - a
            # create and a delete through its own commands - and then looks
            # again.
            #
            # Honest about what this does and does not catch: measured on
            # 2026-08-31, the old fallback path passed here too. The
            # suspicion that Home Assistant's own save dropped the entry was
            # wrong. What was observed instead was a state where a restored
            # dashboard was in memory and not on disk, whose mechanism was
            # never established. This check guards the property that
            # matters - the entry stays on disk across a foreign save - and
            # claims nothing about the bug it did not find.
            touch = f"{key}-touch"
            touch_id = touch.replace("-", "_")
            await socket.call(
                "lovelace/dashboards/create", url_path=touch, title="DH Touch"
            )
            await socket.call("lovelace/dashboards/delete", dashboard_id=touch_id)
            # Waiting for the touch entry to *leave* the file is the whole
            # trick. Home Assistant saves a collection with a delay, so
            # simply looking for the restored entry finds it immediately -
            # before the destructive save has even happened. The touch entry
            # disappearing is proof that the save has been written.
            wrote = await _wait_for_store_absence(touch_id)
            check(
                "Home Assistant wrote the registry while we watched",
                wrote,
                "its own save landed"
                if wrote
                else "no save observed - the check below proves nothing",
            )
            survived = _store_has(back["id"])
            check(
                "and the restored dashboard survived that save",
                survived,
                "still on disk"
                if survived
                else f"{back['id']} was dropped from disk by Home Assistant's "
                "own save - the dashboard would be gone at the next restart",
            )

            try:
                await socket.call(
                    "lovelace/dashboards/delete", dashboard_id=back["id"]
                )
                deleted = True
                detail = "deleted at once, no restart needed"
            except RuntimeError as err:
                deleted = False
                detail = str(err)
            check("and it can be deleted again", deleted, detail)


async def _wait_for(fetch, accept, seconds: float, every: float = 1.0):
    """Poll `fetch` until `accept` likes its answer; hand back the last one.

    The one loop behind every wait in this file. A fixed sleep was the
    alternative, and it failed one run in three wherever the recorder's
    pass ran close to the sleep's length; the last answer is returned
    either way, so the check that follows can say what was there.
    """
    deadline = time.time() + seconds
    while True:
        value = await fetch()
        if accept(value) or time.time() >= deadline:
            return value
        await asyncio.sleep(every)


async def _newest_message(socket, key: str) -> str:
    history = await socket.call("dashboard_history/history", dashboard=key)
    return history["changes"][0]["message"] if history["changes"] else ""


async def _wait_for_newest(socket, key: str, phrase: str, seconds: float) -> str:
    """The newest history message for `key`, once it contains `phrase`."""
    return await _wait_for(
        lambda: _newest_message(socket, key), lambda m: phrase in m, seconds
    )


async def _wait_until_recorded(socket, key: str, seconds: float = RECORDING_WAIT):
    """Wait until the newest recorded state is the one the dashboard holds.

    `same_as_now` is the recorder's own answer to that question, so this
    needs no bookkeeping from the caller and stays right for a save that
    changed nothing.

    What stood here was `asyncio.sleep(4)`, and four seconds is not a
    measurement. capture.py has the numbers: a reconciliation over a
    grown repository held the write lock for 16.6 s while a save waited
    7.2 s for it, and RECONCILE_DELAY is 10 s on its own. On a quiet
    instance four seconds pass; in the middle of a full run, where the
    repository has grown, two saves land in one commit and every
    revision the check reaches for afterwards is the wrong one. Three
    checks failed that way on 2026-09-04 - in `run_undo` and in
    `run_forget` - and every one of them passed when run alone, which is
    the signature of a wait that is too short rather than a defect.
    """

    async def fetch():
        answer = await socket.call("dashboard_history/history", dashboard=key)
        return answer["changes"]

    return await _wait_for(fetch, lambda c: bool(c) and c[0].get("same_as_now"), seconds)


async def _wait_for_history_to_move(socket, key: str, seen: str, seconds: float) -> list:
    """The history of `key`, once its newest revision is no longer `seen`."""
    async def fetch():
        return (await socket.call("dashboard_history/history", dashboard=key))["changes"]

    return await _wait_for(fetch, lambda c: bool(c) and c[0]["revision"] != seen, seconds)


def _store_has(dashboard_id: str) -> bool:
    """Whether the dashboard registry *on disk* holds this entry.

    Reading the file is deliberate. The failure being guarded against is
    invisible over the API: `lovelace/dashboards/list` is overridden to
    answer from memory, so a dashboard can be listed, opened and used
    while its registry entry is no longer on disk - and then be gone at
    the next restart.
    """
    path = CONFIG / ".storage" / "lovelace_dashboards"
    try:
        items = json.loads(path.read_text(encoding="utf-8"))["data"]["items"]
    except (OSError, KeyError, json.JSONDecodeError):
        return False
    return any(item.get("id") == dashboard_id for item in items)


async def _wait_for_store_entry(dashboard_id: str, seconds: int = 20) -> bool:
    """Wait until the registry on disk holds this entry."""
    async def fetch():
        return _store_has(dashboard_id)

    return await _wait_for(fetch, bool, seconds)


async def _wait_for_store_absence(dashboard_id: str, seconds: int = 30) -> bool:
    """Wait until the registry on disk no longer holds this entry.

    Used as evidence that Home Assistant has actually written the file,
    which its delayed save makes impossible to assume.
    """
    async def fetch():
        return not _store_has(dashboard_id)

    return await _wait_for(fetch, bool, seconds)


async def run_current_marker(access: str) -> None:
    """Which recorded entry is the state in front of you.

    A history that went back and forth holds several entries with identical
    content and identical wording. Without a mark the panel is a wall of
    "2 moved" - which is what a person hit, and what sent them clicking a
    button whose preview then said "No difference."
    """
    async with Socket(access) as socket:
        key = TARGET
        changes = (await socket.call("dashboard_history/history", dashboard=key))[
            "changes"
        ]
        check(
            "every entry says whether it is the state in front of you",
            all("same_as_now" in change for change in changes),
            f"{len(changes)} entries",
        )
        check(
            "and the newest one is",
            changes[0]["same_as_now"] is True,
            f"{changes[0]['revision'][:8]} {changes[0]['message']!r}",
        )

        # Undo the newest change. What must NOT happen is the mark staying
        # on an entry that is no longer the current state.
        before_newest = changes[1]["revision"]
        applied = await socket.call(
            "dashboard_history/restore_state",
            dashboard=key,
            revision=before_newest,
            confirm=True,
        )
        check("the newest change can be undone", applied["applied"] is True, str(applied.get("note")))
        after = await _wait_for_history_to_move(
            socket, key, changes[0]["revision"], RECORDING_WAIT
        )
        # Counting is the wrong measure: `history` answers at most 50
        # entries, and this history passed that a while ago - a new entry at
        # the top pushes one off the bottom, so the count cannot grow. What
        # "appends" actually means is that the previous newest is still
        # there, one place down.
        check(
            "undoing appends a new entry rather than replacing one",
            after[0]["revision"] != changes[0]["revision"]
            and after[1]["revision"] == changes[0]["revision"],
            f"{changes[0]['revision'][:8]} moved from position 0 to 1",
        )
        check(
            "the mark moved to it",
            after[0]["same_as_now"] is True,
            f"{after[0]['revision'][:8]} {after[0]['message']!r}",
        )
        check(
            "and left the entry that is no longer current",
            after[1]["same_as_now"] is False,
            f"{after[1]['revision'][:8]} was newest before",
        )
        # The entry whose content the undo brought back holds it again, and
        # says so. That run of look-alike entries is exactly what the chip
        # explains.
        older = next(
            (c for c in after[1:] if c["revision"] == before_newest), None
        )
        check(
            "the state we went back to is marked as identical, not as current",
            older is not None and older["same_as_now"] is True,
            f"{before_newest[:8]} same_as_now="
            f"{older['same_as_now'] if older else 'not found'}",
        )

        # And the button that used to be offered pointlessly: its target is
        # now the current state, so the preview says there is nothing to do.
        pointless = await socket.call(
            "dashboard_history/restore_state", dashboard=key, revision=after[0]["revision"]
        )
        check(
            "restoring to the current state reports nothing to do",
            pointless.get("note") == "already identical"
            and not pointless.get("preview"),
            str(pointless),
        )

        # Put the dashboard back the way it was found.
        #
        # This section undoes a change to prove the mark follows, and it
        # used to leave it undone. That is one card fewer on a real
        # dashboard per run of this suite, until no card list had two left
        # and the very first check of the suite failed for want of a card to
        # drop. The history growing by these entries is fine - that is what
        # a history is - but the dashboard itself has to end where it
        # started.
        await socket.call(
            "dashboard_history/restore_state",
            dashboard=key,
            revision=changes[0]["revision"],
            confirm=True,
        )
        restored = await _wait_for_history_to_move(
            socket, key, after[0]["revision"], RECORDING_WAIT
        )
        check(
            "and this section leaves the dashboard as it found it",
            restored[0]["same_as_now"] is True
            and _same_content(restored, changes[0]["revision"], restored[0]["revision"]),
            f"back to the content of {changes[0]['revision'][:8]}",
        )


def _same_content(changes: list, one: str, other: str) -> bool:
    """Whether two entries hold the same dashboard content.

    Read off `same_as_now`, which the integration works out against the
    live dashboard: if both entries are marked, both hold what is there.
    """
    marked = {c["revision"] for c in changes if c["same_as_now"]}
    return one in marked and other in marked


async def run_forget(access: str) -> None:
    """Forgetting a deleted dashboard for good.

    The only irreversible operation here, and the only one that rewrites
    the stored history. Which is why the interesting check is not that the
    dashboard is gone - that is easy - but that a description on a
    *different* dashboard survived. Descriptions are git notes keyed by
    commit sha, and a rewrite changes every sha; carrying them across is
    the part that can go silently wrong.
    """
    key = "dh-forget-check"
    async with Socket(access) as socket:
        # A live dashboard must be refused, whatever else happens.
        refused = await socket.call(
            "dashboard_history/forget", dashboard=TARGET
        )
        check(
            "forgetting a live dashboard is refused",
            refused.get("applied") is False
            and "not a deleted dashboard" in refused.get("error", ""),
            str(refused.get("error"))[:80],
        )
        unknown = await socket.call("dashboard_history/forget", dashboard="nope-nope")
        check(
            "forgetting something with no history is refused",
            unknown.get("applied") is False and "no history" in unknown.get("error", ""),
            str(unknown.get("error")),
        )

        # A sacrificial dashboard of its own, so nothing else is touched.
        for existing in (await socket.call("lovelace/dashboards/list")) or []:
            if existing.get("url_path") == key:
                try:
                    await socket.call(
                        "lovelace/dashboards/delete", dashboard_id=existing["id"]
                    )
                except RuntimeError:
                    pass
        await socket.call(
            "lovelace/dashboards/create", url_path=key, title="DH Forget", icon="mdi:delete"
        )
        # Not `_wait_until_recorded` here, and the difference matters: that
        # one waits for the newest state to match what the dashboard holds,
        # and this dashboard is about to be deleted - `same_as_now` is
        # false for every entry of a dashboard that is gone, so the wait
        # would sit out its timeout while reconciliation moved the ground
        # underneath the checks below. What this needs is narrower anyway:
        # that the save was recorded at all, before the deletion follows.
        seen = (await socket.call("dashboard_history/history", dashboard=key))["changes"]
        await socket.call(
            "lovelace/config/save",
            url_path=key,
            config={"views": [{"path": "p", "title": "P", "cards": [{"type": "map"}]}]},
        )
        await _wait_for_history_to_move(
            socket, key, seen[0]["revision"] if seen else "", RECORDING_WAIT
        )
        made = await socket.call(
            "lovelace/dashboards/list"
        )
        await socket.call(
            "lovelace/dashboards/delete",
            dashboard_id=next(d["id"] for d in made if d["url_path"] == key),
        )
        # Recorded, not merely gone: the list says `exists: False` as soon
        # as Home Assistant has dropped the dashboard, while the recorder
        # writes the deletion up to RECONCILE_DELAY later. Forgetting in
        # that gap was what uncovered the stale index on 2026-09-04, so
        # the wait here is for the history, and the list is read after.
        newest = await _wait_for_newest(socket, key, "dashboard deleted", RECORDING_WAIT)
        listed = (await socket.call("dashboard_history/dashboards"))["dashboards"]
        check(
            "the sacrificial dashboard is recorded as deleted",
            "dashboard deleted" in newest
            and any(d["key"] == key and not d["exists"] for d in listed),
            f"{newest!r}",
        )

        # A description on another dashboard, which the rewrite must carry.
        other = TARGET
        # Asked for without a cap on purpose. The default limit of 50 is
        # what left the check at the end of this section unable to fail;
        # the comment there says why.
        changes = (
            await socket.call(
                "dashboard_history/history", dashboard=other, limit=100_000
            )
        )["changes"]
        keepsake = "Diese Beschreibung muss die Umschreibung überleben"
        await socket.call(
            "dashboard_history/describe",
            revision=changes[0]["revision"],
            text=keepsake,
        )
        # What each recorded state IS, not how many there are. `forget`
        # rewrites every revision, so revisions cannot be compared across
        # it - but it copies each commit's message and time over verbatim,
        # so those two identify a state on both sides of the rewrite.
        before_states = [(c["timestamp"], c["message"]) for c in changes]

        facts = await socket.call("dashboard_history/forget", dashboard=key)
        check(
            "without confirm it counts what would be lost and writes nothing",
            facts.get("applied") is False and facts.get("states", 0) > 0,
            f"{facts.get('states')} states, revisions_change="
            f"{facts.get('revisions_change')}",
        )
        still_there = (await socket.call("dashboard_history/dashboards"))["dashboards"]
        check(
            "and the dashboard is still listed",
            any(d["key"] == key for d in still_there),
            key,
        )

        done = await socket.call(
            "dashboard_history/forget", dashboard=key, confirm=True
        )
        check(
            "with confirm the history is removed",
            done.get("applied") is True and done.get("removed", 0) > 0,
            f"{done.get('removed')} commits removed",
        )
        after = (await socket.call("dashboard_history/dashboards"))["dashboards"]
        check(
            "and it is gone from the list for good",
            not any(d["key"] == key for d in after),
            f"{len(listed)} -> {len(after)} dashboards",
        )
        check(
            "no history left to read",
            (await socket.call("dashboard_history/history", dashboard=key))["changes"]
            == [],
            "empty",
        )

        # The part that can go wrong silently.
        survivor = (
            await socket.call(
                "dashboard_history/history", dashboard=other, limit=100_000
            )
        )["changes"]
        # Counting the entries could not show this, for the same reason it
        # could not in `run_versions`: `history` answers with a default
        # limit of 50, this bench adds states to TARGET on every run, and
        # once it has reached fifty both sides read 50 whatever the rewrite
        # did to the history underneath. Both lists are asked for without a
        # cap now, and compared entry by entry: a state dropped anywhere in
        # the history changes the sequence, and no limit can swallow that.
        kept = [(c["timestamp"], c["message"]) for c in survivor]
        gap = next(
            (
                i
                for i, state in enumerate(before_states)
                if i >= len(kept) or kept[i] != state
            ),
            None,
        )
        check(
            "the other dashboard's states all came through the rewrite",
            kept == before_states,
            f"{len(before_states)} -> {len(kept)}"
            + ("" if gap is None else f", first difference at entry {gap}"),
        )
        check(
            "and the description written on it survived the rewrite",
            survivor[0]["description"] == keepsake,
            survivor[0]["description"] or "GONE",
        )
        check(
            "its revisions still resolve, new ones though they are",
            (
                await socket.call(
                    "dashboard_history/explain",
                    dashboard=other,
                    revision=survivor[0]["revision"],
                )
            ).get("error")
            is None,
            survivor[0]["revision"][:10],
        )

        # Take the keepsake back off. It served its purpose, and a check
        # that leaves a description behind leaves one more every run - four
        # had piled up before this was noticed.
        await socket.call(
            "dashboard_history/describe", revision=survivor[0]["revision"], text=""
        )


async def run_descriptions(access: str) -> None:
    """A description of one's own: written, read back, replaced, removed.

    The whole point is that the commit is untouched, so that is checked
    rather than assumed: a rewritten commit would invalidate every
    revision this tool hands out.
    """
    async with Socket(access) as socket:
        key = TARGET
        changes = (await socket.call("dashboard_history/history", dashboard=key))[
            "changes"
        ]
        check("there is a change to describe", bool(changes), f"{len(changes)} changes")
        if not changes:
            return
        revision = changes[0]["revision"]
        text = "Vor dem Umbau der Heizungskarten — äöüß"

        result = await socket.call(
            "dashboard_history/describe", revision=revision, text=text
        )
        check("a description is accepted", result.get("applied") is True, str(result))

        newest = (await socket.call("dashboard_history/history", dashboard=key))[
            "changes"
        ][0]
        check(
            "it comes back with the history, umlauts intact",
            newest["description"] == text,
            newest["description"],
        )
        check(
            "the revision is unchanged - the commit was not rewritten",
            newest["revision"] == revision,
            newest["revision"][:10],
        )
        check(
            "the automatic message is still there underneath it",
            newest["message"] == changes[0]["message"],
            newest["message"],
        )

        await socket.call(
            "dashboard_history/describe", revision=revision, text="Zweite Fassung"
        )
        replaced = (await socket.call("dashboard_history/history", dashboard=key))[
            "changes"
        ][0]
        check(
            "a second description replaces the first",
            replaced["description"] == "Zweite Fassung",
            replaced["description"],
        )

        await socket.call("dashboard_history/describe", revision=revision, text="   ")
        emptied = (await socket.call("dashboard_history/history", dashboard=key))[
            "changes"
        ][0]
        check(
            "emptying it removes the description rather than blanking it",
            emptied["description"] == "",
            repr(emptied["description"]),
        )

        bad = await socket.call(
            "dashboard_history/describe", revision="f" * 40, text="Nowhere"
        )
        check(
            "an unknown revision is refused, and says so",
            bad.get("applied") is False and "unknown revision" in bad.get("error", ""),
            str(bad),
        )


async def run_explanation(access: str) -> None:
    """The plain-language explanation, against real dashboards."""
    async with Socket(access) as socket:
        key = TARGET
        changes = (await socket.call("dashboard_history/history", dashboard=key))[
            "changes"
        ]
        check(
            "there is a change with a state before it",
            len(changes) > 1,
            f"{len(changes)} changes",
        )
        result = await socket.call(
            "dashboard_history/explain", dashboard=key, revision=changes[0]["revision"]
        )
        check(
            "explain answers in shape",
            "groups" in result and "note" in result and "error" not in result,
            str(sorted(result)),
        )
        named = [
            entry["text"] for group in result["groups"] for entry in group["entries"]
        ]
        check(
            "it either names something or admits it cannot - never both silent",
            bool(named) or "see the details" in result["note"],
            str(named[:3]) or result["note"],
        )
        for group in result["groups"]:
            check(
                f"the list for view {group['view']!r} is capped",
                len(group["entries"]) <= 12,
                f"{len(group['entries'])} entries, {group['more']} hidden",
            )

        # The change most in need of an explanation, and the one that used
        # to answer "did not exist at": a deletion, where the dashboard's
        # file has left the tree. Every deleted dashboard is asked, not
        # the first in the list: since the list stopped ending at a
        # thousand commits (2026-09-04) it begins with a probe that never
        # had a view, and for that one "cannot be described in terms of
        # cards" is the truth. None may answer with an error, and at least
        # one has to name the view it lost.
        deleted = [
            dashboard["key"]
            for dashboard in (await socket.call("dashboard_history/dashboards"))[
                "dashboards"
            ]
            if not dashboard["exists"]
        ]
        errors, named = [], []
        for key in deleted:
            gone = (await socket.call("dashboard_history/history", dashboard=key))[
                "changes"
            ]
            answer = await socket.call(
                "dashboard_history/explain", dashboard=key, revision=gone[0]["revision"]
            )
            if "error" in answer:
                errors.append(f"{key}: {answer['error']}")
            named += [
                f"{key}: {entry['text']}"
                for group in answer["groups"]
                for entry in group["entries"]
                if "deleted" in entry["text"]
            ]
        if deleted:
            check(
                "a deletion is explained rather than reported as an error",
                not errors and bool(named),
                str(errors[:2] or named[:2]),
            )


async def run_preview_explains(access: str) -> None:
    """What a person sees before pressing Apply."""
    async with Socket(access) as socket:
        key = TARGET
        changes = (await socket.call("dashboard_history/history", dashboard=key))[
            "changes"
        ]
        before = changes[1]["revision"]
        preview = await socket.call(
            "dashboard_history/restore_state", dashboard=key, revision=before
        )
        check(
            "nothing is written without confirm",
            preview.get("applied") is False,
            str(preview.get("applied")),
        )
        check(
            "the preview carries words AND the diff, not one instead of the other",
            "explanation" in preview and "preview" in preview,
            str(sorted(preview)),
        )
        entries = [
            entry["text"]
            for group in preview.get("explanation", {}).get("groups", [])
            for entry in group["entries"]
        ]
        check(
            "and the words are in the future tense, since nothing has happened yet",
            not entries
            or all(
                "will be" in text or "comes back" in text or "goes back" in text
                or "moves back" in text
                for text in entries
            ),
            str(entries[:3]),
        )


async def run_moves(access: str) -> None:
    """A card that moved is not missing, over the real path.

    pytest settles the rule inside `analyze.py`. What it cannot reach is
    the path a person actually travels: Home Assistant saves, the
    recorder writes a commit, and the panel asks `deleted_since` what to
    offer. Every bug this project has found lived in exactly that gap.
    """
    key = "dh-move-check"
    a_card = {"type": "markdown", "content": "Stays where it is"}
    travels = {"type": "markdown", "content": "Travels between the views"}
    b_card = {"type": "markdown", "content": "Waits in the other view"}

    def state(a_cards, b_cards):
        return {
            "views": [
                {"path": "a", "title": "A", "cards": list(a_cards)},
                {"path": "b", "title": "B", "cards": list(b_cards)},
            ]
        }

    async with Socket(access) as socket:
        listed = (await socket.call("lovelace/dashboards/list")) or []
        # The exact key, never a prefix, and never deleted-then-created:
        # Home Assistant collapses that pair inside the debounce and the
        # recorder never sees the deletion.
        if not any(entry.get("url_path") == key for entry in listed):
            await socket.call(
                "lovelace/dashboards/create", url_path=key, title="DH Move"
            )
            await asyncio.sleep(4)

        await socket.call(
            "lovelace/config/save",
            url_path=key,
            config=state([a_card, travels], [b_card]),
        )
        await _wait_until_recorded(socket, key)
        before = (await socket.call("dashboard_history/history", dashboard=key))[
            "changes"
        ][0]["revision"]

        await socket.call(
            "lovelace/config/save",
            url_path=key,
            config=state([a_card], [b_card, travels]),
        )
        await _wait_until_recorded(socket, key)

        changes = (await socket.call("dashboard_history/history", dashboard=key))[
            "changes"
        ]
        message = changes[0]["message"]
        check(
            "moving a card between views is recorded as a move",
            "moved" in message and "removed" not in message,
            f"{message!r}",
        )

        offered = await socket.call(
            "dashboard_history/deleted_since", dashboard=key, revision=before
        )
        check(
            "and nothing is offered back, because nothing is missing",
            offered["items"] == [],
            f"{[item['label'] for item in offered['items']]}"
            if offered["items"]
            else "no offer - the card is on the dashboard, elsewhere",
        )

        # The revision of the move itself, not the state before it:
        # `explain` is given the change, and working that out wrongly is
        # the trap decision 9 removed rather than signposted.
        words = await socket.call(
            "dashboard_history/explain", dashboard=key, revision=changes[0]["revision"]
        )
        said = [
            entry["text"] for group in words["groups"] for entry in group["entries"]
        ]
        check(
            "and the words say which view it went to",
            any('moved to "B"' in line for line in said),
            f"{said}",
        )

        # The control. Without it this section could not tell a working
        # rule from one that stopped offering anything at all.
        await socket.call(
            "lovelace/config/save", url_path=key, config=state([a_card], [b_card])
        )
        await _wait_until_recorded(socket, key)
        gone = await socket.call(
            "dashboard_history/deleted_since", dashboard=key, revision=before
        )
        check(
            "a card really deleted is still offered back",
            [item["label"] for item in gone["items"]] != [],
            f"{[item['label'] for item in gone['items']]}",
        )


async def run_undo(access: str) -> None:
    """Taking one change back while keeping the ones after it.

    pytest settles the arithmetic. What it cannot reach is the path a
    person travels: Home Assistant saves, the recorder commits, the
    panel asks, and only then does anything get written back.
    """
    key = "dh-undo-check"
    keep = {"type": "markdown", "content": "Untouched"}
    first = {"type": "markdown", "content": "Card one\n\nOriginal body"}
    edited = {"type": "markdown", "content": "Card one\n\nEdited body"}
    later = {"type": "markdown", "content": "Added afterwards"}

    fresh = {"type": "markdown", "content": "Brand new"}
    tail = {"type": "markdown", "content": "Saved after that"}

    # The title is a parameter because one check needs a change the undo
    # cannot fully reach: it works on cards and views, never on a view's
    # own labels, and that is exactly when `equals_state_before` has to
    # say no.
    def state(cards, title="A"):
        return {"views": [{"path": "a", "title": title, "cards": list(cards)}]}

    async def save(socket, cards, title="A"):
        await socket.call(
            "lovelace/config/save", url_path=key, config=state(cards, title)
        )
        await _wait_until_recorded(socket, key)

    async def newest(socket):
        answer = await socket.call("dashboard_history/history", dashboard=key)
        return answer["changes"][0]["revision"]

    async with Socket(access) as socket:
        listed = (await socket.call("lovelace/dashboards/list")) or []
        if not any(entry.get("url_path") == key for entry in listed):
            await socket.call(
                "lovelace/dashboards/create", url_path=key, title="DH Undo"
            )
            await asyncio.sleep(4)

        await save(socket, [keep, first])
        await save(socket, [keep, edited])
        the_edit = await newest(socket)
        await save(socket, [keep, edited, later])

        answer = await socket.call(
            "dashboard_history/undo_change", dashboard=key, revision=the_edit
        )
        check(
            "an edit two saves back is still exactly undoable",
            answer.get("available") is True,
            answer.get("reason", ""),
        )
        check(
            "the preview writes nothing without confirm",
            answer.get("applied") is False and bool(answer.get("preview")),
        )
        live = await socket.call("lovelace/config", url_path=key)
        check(
            "the dashboard is untouched after a preview",
            live["views"][0]["cards"] == [keep, edited, later],
        )

        answer = await socket.call(
            "dashboard_history/undo_change",
            dashboard=key,
            revision=the_edit,
            confirm=True,
        )
        await asyncio.sleep(4)
        live = await socket.call("lovelace/config", url_path=key)
        check(
            "the undo restores the old card and keeps the later one",
            live["views"][0]["cards"] == [keep, first, later],
            str(live["views"][0]["cards"]),
        )
        check(
            "the undo leaves exactly one copy, not two",
            len(live["views"][0]["cards"]) == 3,
        )

        # The control. Edit the same card twice, then ask for the first
        # edit back: there is no exact version left, and a tool that said
        # yes here would overwrite the second edit.
        await save(socket, [keep, first, later])
        await save(socket, [keep, edited, later])
        once = await newest(socket)
        await save(socket, [keep, {"type": "markdown", "content": "Card one\n\nThird body"}, later])
        answer = await socket.call(
            "dashboard_history/undo_change", dashboard=key, revision=once
        )
        check(
            "a card edited again since refuses the undo",
            answer.get("available") is False
            and "changed again" in (answer.get("reason") or ""),
            answer.get("reason", ""),
        )

        # `equals_state_before` is what the panel drops its coarse "back
        # to the state before this change" button on, so a wrong answer
        # here either hides a real way back or offers two buttons that
        # look alike and are not. Both directions, because a flag that is
        # always true would pass one of them on its own.
        await save(socket, [keep, first, later])
        await save(socket, [keep, later])
        lone = await newest(socket)
        answer = await socket.call(
            "dashboard_history/undo_change", dashboard=key, revision=lone
        )
        check(
            "one deletion, nothing since: the undo writes the whole old state",
            answer.get("available") is True
            and answer.get("equals_state_before") is True,
            f"available={answer.get('available')} "
            f"equals={answer.get('equals_state_before')} "
            f"{answer.get('reason', '')}",
        )

        await save(socket, [keep, first, later])
        await save(socket, [keep, later], title="Renamed")
        mixed = await newest(socket)
        answer = await socket.call(
            "dashboard_history/undo_change", dashboard=key, revision=mixed
        )
        check(
            "a change with a part the undo cannot reach says so",
            answer.get("available") is True
            and answer.get("equals_state_before") is False,
            f"available={answer.get('available')} "
            f"equals={answer.get('equals_state_before')} "
            f"{answer.get('reason', '')}",
        )

        # The undo that *deletes*. Decision 15 calls this the first time
        # this tool removes a card, so it is checked against the exact
        # card list rather than against a count: what has to hold is that
        # the added card goes and the one saved after it stays.
        await save(socket, [keep, later, fresh], title="Renamed")
        the_add = await newest(socket)
        await save(socket, [keep, later, fresh, tail], title="Renamed")
        answer = await socket.call(
            "dashboard_history/undo_change", dashboard=key, revision=the_add
        )
        check(
            "an added card can be taken back away again",
            answer.get("available") is True,
            answer.get("reason", ""),
        )
        await socket.call(
            "dashboard_history/undo_change",
            dashboard=key,
            revision=the_add,
            confirm=True,
        )
        await asyncio.sleep(4)
        live = await socket.call("lovelace/config", url_path=key)
        check(
            "the added card is gone and the later one is still there",
            live["views"][0]["cards"] == [keep, later, tail],
            str(live["views"][0]["cards"]),
        )


async def run_positions(access: str) -> None:
    """A position is an address, not an identity.

    Found on 2026-09-04. A view without a URL path is keyed by where it
    sits, and a section has nothing else at all - Home Assistant gives it
    neither path nor id. Delete the view in front of such a view, or drop
    a new one before it, and the same key names something else. Measured
    before the fix: the undo wrote a card onto a view nobody had touched,
    and in one case left the dashboard empty, both times behind a preview
    that read like any other undo.

    None of it was reachable from pytest, and every case here writes
    nothing - the refusal has to happen while the plan is made.
    """
    light = {"type": "markdown", "content": "# Licht"}
    weather = {"type": "markdown", "content": "# Wetter"}
    guest = {"type": "markdown", "content": "# Gast"}

    def sections(*blocks):
        return {
            "views": [
                {
                    "path": "home",
                    "title": "Home",
                    "type": "sections",
                    "sections": [dict(block) for block in blocks],
                }
            ]
        }

    async def ready(socket, key: str) -> None:
        listed = (await socket.call("lovelace/dashboards/list")) or []
        if not any(entry.get("url_path") == key for entry in listed):
            await socket.call("lovelace/dashboards/create", url_path=key, title=key)
            await asyncio.sleep(3)

    async def save(socket, key: str, config: dict) -> list:
        """Save, then wait for the recorder to move past what stood before.

        Counting entries was the first attempt and it does not hold:
        creating a dashboard records a state of its own, so the count is
        already where the wait wants it before the save is even seen.
        """
        await socket.call("lovelace/config/save", url_path=key, config=config)
        return await _wait_until_recorded(socket, key)

    async def undo_of_the_last_change(socket, key: str, before: dict, after: dict):
        await ready(socket, key)
        await save(socket, key, before)
        changes = await save(socket, key, after)
        return await socket.call(
            "dashboard_history/undo_change", dashboard=key, revision=changes[0]["revision"]
        )

    refused = (
        (
            "dh-position-gone",
            "a pathless view deleted before another is refused",
            {
                "views": [
                    {"title": "Home", "cards": [light]},
                    {"title": "Wetter", "cards": [weather]},
                ]
            },
            {"views": [{"title": "Wetter", "cards": [weather]}]},
            "URL path",
        ),
        (
            "dh-position-shifted",
            "a pathless view shifted by a deletion is refused",
            {
                "views": [
                    {"path": "a", "title": "Erd", "cards": [light]},
                    {"path": "b", "title": "Gaeste", "cards": [guest]},
                    {"title": "Home", "cards": [weather]},
                ]
            },
            {
                "views": [
                    {"path": "a", "title": "Erd", "cards": [light]},
                    {"title": "Home", "cards": [weather]},
                ]
            },
            "URL path",
        ),
        (
            "dh-position-pushed",
            "a view inserted before a pathless one is refused",
            {"views": [{"title": "Home", "cards": [weather]}]},
            {
                "views": [
                    {"path": "neu", "title": "Neu", "cards": [guest]},
                    {"title": "Home", "cards": [weather]},
                ]
            },
            "URL path",
        ),
        (
            "dh-position-section",
            "a section inserted before another is refused",
            sections({"title": "Unten", "cards": [weather]}),
            sections(
                {"title": "Neu", "cards": [guest]}, {"title": "Unten", "cards": [weather]}
            ),
            "section",
        ),
    )

    async with Socket(access) as socket:
        for key, name, before, after, phrase in refused:
            answer = await undo_of_the_last_change(socket, key, before, after)
            check(
                name,
                answer.get("available") is False and phrase in (answer.get("reason") or ""),
                answer.get("reason", "the undo was offered"),
            )

        # The everyday case has to survive all of that: nothing moved, so
        # the position does mean the same view, and the undo stands.
        answer = await undo_of_the_last_change(
            socket,
            "dh-position-steady",
            {
                "views": [
                    {"path": "a", "title": "Erd", "cards": [light]},
                    {"title": "Home", "cards": [weather, guest]},
                ]
            },
            {
                "views": [
                    {"path": "a", "title": "Erd", "cards": [light]},
                    {"title": "Home", "cards": [guest]},
                ]
            },
        )
        check(
            "a card deleted from a pathless view that stayed put is still undoable",
            answer.get("available") is True,
            answer.get("reason", ""),
        )

        # And the other way back, which walks the same section index.
        key = "dh-position-putback"
        await ready(socket, key)
        changes = await save(
            socket,
            key,
            sections(
                {"title": "Oben", "cards": [light]},
                {"title": "Unten", "cards": [weather, guest]},
            ),
        )
        base = changes[0]["revision"]
        await save(
            socket,
            key,
            sections(
                {"title": "Neu", "cards": []},
                {"title": "Oben", "cards": [light]},
                {"title": "Unten", "cards": [weather]},
            ),
        )
        gone = await socket.call(
            "dashboard_history/deleted_since", dashboard=key, revision=base
        )
        answer = await socket.call(
            "dashboard_history/restore_deleted",
            dashboard=key,
            revision=base,
            position=0,
        )
        check(
            "a card whose section was pushed along is not filed in a stranger",
            bool(gone.get("items")) and "section" in (answer.get("error") or ""),
            answer.get("error", "it was offered a place"),
        )

        key = "dh-position-putback-steady"
        await ready(socket, key)
        changes = await save(
            socket, key, sections({"title": "Oben", "cards": [light, weather]})
        )
        base = changes[0]["revision"]
        await save(socket, key, sections({"title": "Oben", "cards": [light]}))
        answer = await socket.call(
            "dashboard_history/restore_deleted",
            dashboard=key,
            revision=base,
            position=0,
        )
        check(
            "a card still goes back into the section it came from",
            bool(answer.get("preview")) and not answer.get("error"),
            answer.get("error", ""),
        )


async def run_paging(access: str) -> None:
    """Paging by commit cursor.

    Out of pytest's reach: `async_history` imports Home Assistant. And
    the question only arises on a history longer than one page.
    """
    key = "dh-paging-check"

    async def save(socket, index: int):
        await socket.call(
            "lovelace/config/save",
            url_path=key,
            config={"views": [{"path": "p", "title": f"Stand {index}", "cards": []}]},
        )
        # Not `_wait_for_history_to_move`: after the first run the
        # dashboard is back on "Stand 0" (restored below), so the first
        # save of the next run changes nothing, and waiting for movement
        # would sit out RECORDING_WAIT. `same_as_now` is true at once for
        # a save that changed nothing - the shape `run_undo` uses.
        await _wait_until_recorded(socket, key)

    async with Socket(access) as socket:
        listed = (await socket.call("lovelace/dashboards/list")) or []
        if not any(entry.get("url_path") == key for entry in listed):
            await socket.call(
                "lovelace/dashboards/create", url_path=key, title="DH Paging"
            )
            await asyncio.sleep(4)
        for index in range(5):
            await save(socket, index)

        first = await socket.call("dashboard_history/history", dashboard=key, limit=2)
        check(
            "a page carries a cursor to the next one",
            len(first["changes"]) == 2 and bool(first.get("next_cursor")),
            str(first.get("next_cursor"))[:12],
        )
        second = await socket.call(
            "dashboard_history/history",
            dashboard=key,
            limit=2,
            before=first["next_cursor"],
        )
        seen_first = {c["revision"] for c in first["changes"]}
        seen_second = {c["revision"] for c in second["changes"]}
        check(
            "the second page repeats nothing from the first",
            not (seen_first & seen_second) and len(seen_second) == 2,
            f"{len(seen_first)} + {len(seen_second)}, overlap {len(seen_first & seen_second)}",
        )
        everything = await socket.call(
            "dashboard_history/history", dashboard=key, limit=1000
        )
        check(
            "the last page says there is nothing older",
            everything.get("next_cursor") is None,
            str(everything.get("next_cursor")),
        )
        combined = [c["revision"] for c in first["changes"] + second["changes"]]
        first_four = [c["revision"] for c in everything["changes"]][:4]
        check(
            "the two pages together are the history's first four, in order",
            combined == first_four,
            f"{combined} vs {first_four}",
        )

        # The badge must not depend on how far somebody has paged.
        # `everything` above is the whole history already - proven by its
        # `next_cursor` being None - so the oldest entry is its last one.
        oldest = everything["changes"][-1]["revision"]
        await socket.call(
            "dashboard_history/create_version",
            dashboard=key,
            revision=oldest,
            level="major",
            title="Der alte Stand",
        )
        restored = await socket.call(
            "dashboard_history/restore_state",
            dashboard=key,
            revision=oldest,
            confirm=True,
        )
        await _wait_until_recorded(socket, key)
        narrow = await socket.call("dashboard_history/history", dashboard=key, limit=1)
        names = [v["name"].split("/")[-1] for v in narrow.get("matching_versions", [])]
        check(
            "a matching version is reported even from outside the window",
            restored.get("applied") is True and "v1.0.0" in names,
            f"applied={restored.get('applied')} matching={names}",
        )

        listing = await socket.call("dashboard_history/versions", dashboard=key)
        names = [v["name"].split("/")[-1] for v in listing.get("versions", [])]
        check(
            "every version of a dashboard is listed, newest number first",
            bool(names) and names == sorted(
                names,
                key=lambda n: [int(p) for p in n.lstrip("v").split(".")],
                reverse=True,
            ),
            str(names),
        )
        check(
            "the listing says which version the dashboard holds right now",
            any(v.get("same_as_now") for v in listing.get("versions", [])),
            str([(v["name"].split("/")[-1], v.get("same_as_now"))
                 for v in listing.get("versions", [])]),
        )


async def run_live_updates(access: str) -> None:
    """The panel is told when the history has grown - and only then.

    The panel used to reload the moment a service returned, which is
    before the recorder has written anything: measured on 2026-09-03,
    restore_state answered after 26 ms and the commit landed 150 ms
    later. In that window the newest recorded entry is the state that was
    just replaced, so nothing matches the live configuration and the page
    shows no current state at all.
    """
    key = "dh-live-check"
    same = {
        "views": [
            {"path": "p", "title": "P", "cards": [{"type": "markdown", "content": "one"}]}
        ]
    }
    async with Socket(access) as socket:
        listed = (await socket.call("lovelace/dashboards/list")) or []
        # The exact key, never a prefix, and never deleted-then-created.
        if not any(entry.get("url_path") == key for entry in listed):
            await socket.call(
                "lovelace/dashboards/create", url_path=key, title="DH Live"
            )
            await asyncio.sleep(4)
        await socket.call("lovelace/config/save", url_path=key, config=same)
        await _wait_until_recorded(socket, key)

        await socket.call("subscribe_events", event_type=EVENT_HISTORY_UPDATED)

        changed = json.loads(json.dumps(same))
        changed["views"][0]["cards"].append(
            {"type": "markdown", "content": f"two {time.time()}"}
        )
        await socket.call("lovelace/config/save", url_path=key, config=changed)
        seen = await socket.wait_for_event(EVENT_HISTORY_UPDATED, 10)
        check(
            "a recorded change is announced on the bus",
            seen is not None,
            str(seen and seen.get("data")),
        )
        if seen:
            named = (seen.get("data") or {}).get("dashboards") or []
            check(
                "and the announcement names the dashboard that changed",
                key in named,
                f"{named}",
            )

        # The control, and the reason this section can fail at all: saving
        # the very same configuration writes no commit, so there is
        # nothing to announce. A panel that reloaded on every save would
        # pass every check above and still be wrong.
        await socket.call("lovelace/config/save", url_path=key, config=changed)
        again = await socket.wait_for_event(EVENT_HISTORY_UPDATED, 6)
        check(
            "a save that changes nothing announces nothing",
            again is None,
            "silent"
            if again is None
            else f"announced anyway: {again.get('data')}",
        )


async def run_versions(access: str) -> None:
    """Versions of one dashboard: counting up, marking, going back.

    The interesting part is that nothing here writes a commit. A version
    marks a state that is already recorded, so the history must be
    exactly as long afterwards as it was before.
    """
    async with Socket(access) as socket:
        key = TARGET
        changes = (await socket.call("dashboard_history/history", dashboard=key))[
            "changes"
        ]
        check(
            "there are two states, so one can be marked that is not the newest",
            len(changes) > 1,
            f"{len(changes)} changes",
        )
        if len(changes) < 2:
            return
        # The newest recorded revision, not the number of entries. See the
        # check further down that uses it.
        newest_before = changes[0]["revision"]
        # The second-newest, deliberately. The newest is also this
        # dashboard's HEAD state, so a version placed there proves nothing:
        # an implementation that ignored the revision entirely and tagged
        # the newest state would pass every check below. The trap this
        # section exists to guard is exactly that fallback.
        revision = changes[1]["revision"]

        # Socket.call raises on a WebSocket error, and an unregistered
        # command is one. Guarded so a missing or misregistered command
        # reports a failed check instead of taking the whole run down with
        # a traceback - the same shape the other checks in this file use.
        try:
            offered = await socket.call(
                "dashboard_history/next_versions", dashboard=key
            )
        except RuntimeError as err:
            check("the next_versions command answers", False, str(err))
            return
        candidates = offered.get("candidates", {})
        check(
            "three candidates are offered, patch among them",
            set(candidates) == {"patch", "minor", "major", "current"},
            str(candidates),
        )

        made = await socket.call(
            "dashboard_history/create_version",
            dashboard=key,
            level="patch",
            title="Prüflauf äöüß",
            description="Von run_checks angelegt.",
            revision=revision,
        )
        created = made.get("created")
        check(
            "the patch candidate is what gets created",
            created == candidates.get("patch"),
            f"{created} vs {candidates.get('patch')}",
        )
        if not created:
            return

        listed = (await socket.call("dashboard_history/versions", dashboard=key))[
            "versions"
        ]
        mine = [v for v in listed if v["name"] == created]
        check("it comes back in the list", len(mine) == 1, str(listed))
        check(
            "with its title, umlauts intact",
            bool(mine) and mine[0]["title"] == "Prüflauf äöüß",
            str(mine[:1]),
        )
        check(
            "pointing at the state it was made from",
            bool(mine) and mine[0]["revision"] == revision,
            str(mine[:1]),
        )

        after = (await socket.call("dashboard_history/history", dashboard=key))[
            "changes"
        ]
        # Counting the entries could not show this. `history` answers with
        # a default limit of 50, and this bench adds states to TARGET on
        # every run - once a dashboard has reached fifty, both sides are
        # 50 and the check passes no matter what marking did. A limit
        # cannot hide the newest revision, though: a commit written here
        # would put a different one at the top of the list.
        check(
            "marking wrote no commit - the newest recorded state is unchanged",
            after[0]["revision"] == newest_before,
            f"{newest_before[:10]} -> {after[0]['revision'][:10]}",
        )
        check(
            "the marked change names its version",
            created in [v["name"] for v in after[1].get("versions", [])],
            str(after[1].get("versions")),
        )

        # The whole point of the namespace: the name is a revision.
        preview = await socket.call(
            "dashboard_history/restore_state", dashboard=key, revision=created
        )
        check(
            "a version name works as a revision",
            "unknown revision" not in preview.get("error", ""),
            str(preview.get("error", "no error"))[:120],
        )

        again = await socket.call("dashboard_history/next_versions", dashboard=key)
        check(
            "the next patch counts up from the one just made",
            again.get("candidates", {}).get("current") == created,
            str(again.get("candidates")),
        )

        bad = await socket.call(
            "dashboard_history/create_version",
            dashboard=key,
            level="enormous",
            title="Nowhere",
        )
        check(
            "an unknown level is refused, and says so",
            bad.get("created") is None and "unknown level" in bad.get("error", ""),
            str(bad),
        )

        # Without a revision the store would fall back to HEAD, and HEAD
        # is whichever dashboard was saved last - one repository holds
        # them all. Measured before this plan was written: it tags a
        # stranger's commit, and the version is then invisible in this
        # dashboard's history for good.
        # The fixture that lets the check below fail. Without it both
        # sides of that comparison were the same commit: TARGET is
        # normally the dashboard saved last, so the repository's HEAD and
        # TARGET's own newest state coincided, and the old fallback to
        # HEAD - the very bug the check is named after - would have
        # passed here unnoticed. A dashboard of its own, saved *after*
        # TARGET's last save, puts a stranger's commit at HEAD.
        #
        # And it is asserted rather than assumed. If the save did not
        # land, or landed on the same commit, the check below is back to
        # comparing something with itself, and that has to be visible in
        # the run rather than hidden in it.
        stranger = "dh-head-check"
        for existing in (await socket.call("lovelace/dashboards/list")) or []:
            # By the exact key, never by a prefix. On 2026-09-01 a prefix
            # match in this file swept up a dashboard somebody was
            # working in, because the prefix was a prefix of that one too.
            if existing.get("url_path") == stranger:
                try:
                    await socket.call(
                        "lovelace/dashboards/delete", dashboard_id=existing["id"]
                    )
                except RuntimeError:
                    pass
        await socket.call(
            "lovelace/dashboards/create", url_path=stranger, title="DH Head"
        )
        await socket.call(
            "lovelace/config/save",
            url_path=stranger,
            config={"views": [{"path": "h", "title": "H", "cards": [{"type": "map"}]}]},
        )
        await _wait_until_recorded(socket, stranger)
        mine = (await socket.call("dashboard_history/history", dashboard=key))["changes"]
        theirs = (await socket.call("dashboard_history/history", dashboard=stranger))[
            "changes"
        ]
        at_head = theirs[0]["revision"] if theirs else None
        foreign = bool(at_head) and bool(mine) and at_head != mine[0]["revision"]
        check(
            "a stranger's save sits at HEAD, so the next check can fail",
            foreign,
            f"HEAD at {at_head[:10]}, {key} newest at {mine[0]['revision'][:10]}"
            if foreign
            else "HEAD and this dashboard's newest state are the same commit - "
            "the check below is comparing something with itself",
        )

        loose = await socket.call(
            "dashboard_history/create_version",
            dashboard=key,
            level="minor",
            title="Ohne Revision",
        )
        placed = loose.get("created")
        check("a version without a revision is still created", bool(placed), str(loose))
        if placed:
            newest = (await socket.call("dashboard_history/versions", dashboard=key))[
                "versions"
            ]
            mark = next((v for v in newest if v["name"] == placed), None)
            history = (await socket.call("dashboard_history/history", dashboard=key))[
                "changes"
            ]
            # Three sides, not two, and the third is the point: the
            # version must sit on this dashboard's newest state *and* not
            # on HEAD, which the fixture above has just made a stranger's
            # commit. The fallback this guards against would land exactly
            # there, and the version would then never appear in this
            # dashboard's history at all - list_changes walks only the
            # paths the dashboard touched.
            check(
                "and it lands on this dashboard's own newest state, not on HEAD",
                bool(mark)
                and mark["revision"] == history[0]["revision"]
                and mark["revision"] != at_head,
                f"{mark and mark['revision'][:10]} vs {history[0]['revision'][:10]}"
                f" for {key}, HEAD at {at_head and at_head[:10]}",
            )

        # Taken down by its own id, never by a prefix. Its history stays -
        # nothing in a check script deletes history - so HEAD stays
        # foreign for the service checks below, which ask the same thing
        # through the other skin.
        made = await socket.call("lovelace/dashboards/list")
        leftover = next((d["id"] for d in made if d["url_path"] == stranger), None)
        if leftover:
            try:
                await socket.call(
                    "lovelace/dashboards/delete", dashboard_id=leftover
                )
            except RuntimeError:
                pass
            # Waited out, not left pending. A deletion is noticed by the
            # reconcile, ten seconds later, and a run that ends before
            # that leaves the burst to collide with the *next* run's
            # first checks - measured on 2026-09-03, where exactly such a
            # collision was recorded as one commit reading "2 removed"
            # and cost two runs to understand. Fifteen seconds here buys
            # an instance that is settled when the run ends.
            await asyncio.sleep(RECONCILE_WAIT)

        # The services layer, not the WebSocket one. Both are thin skins
        # over the same operations, and the point of that design is that
        # they cannot drift - which holds only if both are exercised.
        # services.py passes its arguments positionally, so a reordering
        # there would be invisible to every check above this line.
        offered_by_service = await socket.call(
            "call_service",
            domain="dashboard_history",
            service="next_versions",
            service_data={"dashboard": key},
            return_response=True,
        )
        service_candidates = offered_by_service["response"].get("candidates", {})
        check(
            "the next_versions service answers like the command",
            set(service_candidates) == {"patch", "minor", "major", "current"},
            str(service_candidates),
        )

        made_by_service = await socket.call(
            "call_service",
            domain="dashboard_history",
            service="create_version",
            service_data={
                "dashboard": key,
                "level": "patch",
                "title": "Über den Dienst angelegt",
                "description": "Beweist die Reihenfolge der Argumente.",
            },
            return_response=True,
        )
        by_service = made_by_service["response"].get("created")
        check(
            "the create_version service creates the patch candidate",
            by_service == service_candidates.get("patch"),
            f"{by_service} vs {service_candidates.get('patch')}",
        )
        if not by_service:
            return

        # The title has to have landed in the title. A positional slip in
        # services.py would put it in the description or the level and
        # still answer with a plausible name.
        listed_by_service = await socket.call(
            "call_service",
            domain="dashboard_history",
            service="versions",
            service_data={"dashboard": key},
            return_response=True,
        )
        service_mark = next(
            (
                v
                for v in listed_by_service["response"]["versions"]
                if v["name"] == by_service
            ),
            None,
        )
        check(
            "the versions service puts the title in the title",
            bool(service_mark)
            and service_mark["title"] == "Über den Dienst angelegt",
            str(service_mark),
        )

        # Every version in the installation, not one dashboard's. The only
        # call in this file that leaves the dashboard out, and so the only
        # one that would catch a filter applied when none was asked for.
        everywhere = await socket.call("dashboard_history/versions")
        names = [v["name"] for v in everywhere["versions"]]
        own = [
            v["name"]
            for v in (
                await socket.call("dashboard_history/versions", dashboard=key)
            )["versions"]
        ]
        check(
            "versions without a dashboard answers across all of them",
            by_service in names and set(own) <= set(names),
            f"{len(names)} in total, {len(own)} for this dashboard",
        )


async def run_permissions(access: str) -> None:
    """A user who is not an administrator gets nothing from the services.

    Found on 2026-09-03: `call_service` checks no permissions of its own,
    so a plainly registered service was open to every signed-in user -
    one who cannot edit a dashboard in the frontend could restore one, or
    forget a history for good. The WebSocket commands were admin-only
    from the start; this checks that the services are now too, by making
    a user of the ordinary kind, signing in as them, and asking.

    The user is created and removed here, by their own id, and nothing
    else on the instance is touched.
    """
    headers = {"Authorization": f"Bearer {access}"}
    client = f"{BASE}/"
    made = None
    try:
        async with Socket(access) as socket:
            made = await socket.call(
                "config/auth/create",
                name="Dashboard History non-admin check",
                group_ids=["system-users"],
            )
            user_id = made["user"]["id"]
            await socket.call(
                "config/auth_provider/homeassistant/create",
                user_id=user_id,
                username="dh-nonadmin",
                password="dh-nonadmin-only",
            )
        # Sign in as that user, the way the frontend does.
        flow = requests.post(
            f"{BASE}/auth/login_flow",
            json={"client_id": client, "handler": ["homeassistant", None], "redirect_uri": client},
            timeout=30,
        ).json()
        step = requests.post(
            f"{BASE}/auth/login_flow/{flow['flow_id']}",
            json={"client_id": client, "username": "dh-nonadmin", "password": "dh-nonadmin-only"},
            timeout=30,
        ).json()
        code = step.get("result")
        if not code:
            check("a non-admin user could be signed in", False, json.dumps(step)[:200])
            return
        theirs = {"Authorization": f"Bearer {_exchange_code(code)}"}

        # A read, and a write with confirm: both must be refused, not
        # merely the write. The preview of a restore is the whole
        # configuration, which this user is not shown anywhere else.
        for service, body in (
            ("history", {"dashboard": TARGET}),
            ("restore_state", {"dashboard": TARGET, "revision": "HEAD", "confirm": True}),
        ):
            answer = requests.post(
                f"{BASE}/api/services/dashboard_history/{service}?return_response",
                headers=theirs,
                json=body,
                timeout=30,
            )
            check(
                f"a non-admin is refused {service}",
                answer.status_code == 401,
                f"HTTP {answer.status_code}",
            )
        # And the same call from the administrator still works, so the
        # refusal above is a permission and not a broken service.
        answer = requests.post(
            f"{BASE}/api/services/dashboard_history/history?return_response",
            headers=headers,
            json={"dashboard": TARGET},
            timeout=30,
        )
        check(
            "the administrator still gets history",
            answer.status_code == 200 and "changes" in answer.json().get("service_response", {}),
            f"HTTP {answer.status_code}",
        )
    finally:
        if made is not None:
            async with Socket(access) as socket:
                await socket.call("config/auth/delete", user_id=made["user"]["id"])


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
    if not wait_for_integration(access):
        raise SystemExit("The integration never finished setting up")
    if not TARGET:
        TARGET = asyncio.run(pick_target(access))
        if not TARGET:
            raise SystemExit("No live dashboard with a history to check against")
    print(f"Dashboard für die Prüfungen: {TARGET}")
    print(f"Prüfungen gegen {BASE}\n")
    asyncio.run(run(access))
    print("\n  -- Wer darf: nur Administratoren --")
    asyncio.run(run_permissions(access))
    print("\n  -- Lebenszyklus eines Dashboards: anlegen, umbenennen, löschen, zurückholen --")
    asyncio.run(run_lifecycle(access))
    print("\n  -- Endgueltiges Loeschen --")
    asyncio.run(run_forget(access))
    print("\n  -- Wo bin ich? Der aktuelle Stand --")
    asyncio.run(run_current_marker(access))
    print("\n  -- Eigene Beschreibungen --")
    asyncio.run(run_descriptions(access))
    print("\n  -- Klartext statt Diff --")
    asyncio.run(run_explanation(access))
    print("\n  -- Die Vorschau vor dem Übernehmen --")
    asyncio.run(run_preview_explains(access))
    print("\n  -- Die Seite erfaehrt davon --")
    asyncio.run(run_live_updates(access))
    print("\n  -- Verschieben ist kein Verlust --")
    asyncio.run(run_moves(access))
    print("\n  -- Versionen je Dashboard --")
    asyncio.run(run_versions(access))
    print("\n  -- Eine Aenderung gezielt zuruecknehmen --")
    asyncio.run(run_undo(access))
    print("\n  -- Blaettern statt abschneiden --")
    asyncio.run(run_paging(access))
    print("\n  -- Position ist keine Identitaet --")
    asyncio.run(run_positions(access))
    print(f"\n{len(_passed)} von {len(_passed) + len(_failed)} Prüfungen bestanden")
    if _failed:
        print("Fehlgeschlagen: " + ", ".join(_failed))
        sys.exit(1)
