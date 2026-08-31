"""Drive the panel in an isolated Chrome and report what it actually does.

    docker compose -f docker/compose.yaml up -d
    python3 tests/integration/run_checks.py      # onboards, keeps a token
    python3 tests/integration/look_at_panel.py

Not a test - a way to see, and the only thing in this project that
reaches the panel at all. pytest cannot: the panel is JavaScript in a
shadow root inside Home Assistant's own frontend. Reading its source is
not the same as watching whether the pencil sits where a person would
look for it, or whether clicking the pencil also expands the row
underneath it (it did, until it was stopped from doing so).

Writing this found three mistakes in an afternoon, and none of them were
in the panel:

  * `document.querySelector("dashboard-history-panel")` finds nothing.
    Home Assistant nests the panel several shadow roots deep, so the
    search has to walk them.
  * Waiting on a row count is a race. The dashboard shown before the
    switch already had rows, so the click landed on the old DOM.
  * `Runtime.evaluate` with returnByValue cannot serialise a DOM node and
    answers with an empty object - falsy in Python. Wait on booleans.

Its own Chrome, its own profile directory, its own port. Driving the
browser somebody is working in is how a stray localStorage key ends up in
an unrelated project of theirs.
"""

import asyncio
import base64
import json
import pathlib
import os
import subprocess
import sys
import time
import urllib.request

import websockets

BASE = os.environ.get("HA_TEST_URL", "http://127.0.0.1:8124")
PORT = int(os.environ.get("DH_DEBUG_PORT", "9333"))
CONFIG = pathlib.Path(
    os.environ.get(
        "HA_TEST_CONFIG",
        pathlib.Path(__file__).resolve().parents[2].parent
        / "ha-dashboard-history-test"
        / "config",
    )
)
TOKEN_FILE = CONFIG.parent / "token.txt"
# Beside the instance, not in the repository: a browser profile is state,
# and the screenshots are output.
PROFILE = CONFIG.parent / "chrome-profile"
SHOTS = CONFIG.parent / "panel-shots"
BROWSER = os.environ.get("DH_BROWSER", "google-chrome")

if not TOKEN_FILE.exists():
    sys.exit(
        f"No token at {TOKEN_FILE}. Run tests/integration/run_checks.py first; "
        "it onboards the instance and keeps one."
    )
TOKEN = TOKEN_FILE.read_text(encoding="utf-8").strip()


class Session:
    """The few CDP calls this needs, and nothing else."""

    def __init__(self, socket):
        self.socket = socket
        self.session_id = None
        self._next = 0
        self.console = []

    async def send(self, method, params=None, *, on_browser=False):
        self._next += 1
        message = {"id": self._next, "method": method, "params": params or {}}
        if self.session_id and not on_browser:
            message["sessionId"] = self.session_id
        await self.socket.send(json.dumps(message))
        while True:
            answer = json.loads(await self.socket.recv())
            if answer.get("method") == "Runtime.consoleAPICalled":
                entry = answer["params"]
                if entry["type"] in ("error", "warning"):
                    self.console.append(f"{entry['type']}: {entry['args']}")
            if answer.get("method") == "Runtime.exceptionThrown":
                self.console.append(f"exception: {answer['params']}")
            if answer.get("id") == message["id"]:
                if "error" in answer:
                    raise RuntimeError(f"{method}: {answer['error']}")
                return answer.get("result", {})

    async def js(self, expression):
        result = await self.send(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
        )
        if "exceptionDetails" in result:
            raise RuntimeError(result["exceptionDetails"]["text"])
        return result["result"].get("value")

    async def settle(self, expression, seconds=20):
        """Wait until a JavaScript expression turns truthy.

        Give it a boolean, not a DOM node: with returnByValue the protocol
        cannot serialise an element and hands back an empty object, which
        is falsy in Python. That cost two runs of this script to notice.
        """
        deadline = time.time() + seconds
        while time.time() < deadline:
            try:
                if await self.js(expression):
                    return True
            except RuntimeError:
                # Not there yet. Waiting for something to appear means
                # the expression legitimately throws until it does.
                pass
            await asyncio.sleep(0.4)
        return False

    async def shot(self, name):
        result = await self.send("Page.captureScreenshot", {"format": "png"})
        target = SHOTS / name
        target.write_bytes(base64.b64decode(result["data"]))
        print(f"  image: {target}")

    async def mouse(self, x, y, kind="mouseMoved", button="none"):
        await self.send(
            "Input.dispatchMouseEvent",
            {"type": kind, "x": x, "y": y, "button": button, "clickCount": 1},
        )

    async def click_at(self, x, y):
        await self.mouse(x, y, "mouseMoved")
        await self.mouse(x, y, "mousePressed", "left")
        await self.mouse(x, y, "mouseReleased", "left")


# The panel is not in the document: Home Assistant nests it several
# shadow roots deep. A plain document.querySelector finds nothing, which
# is what made the first run of this script report a panel that was
# plainly on screen as missing.
PANEL = (
    "(() => { const walk = (root) => {"
    ' const hit = root.querySelector("dashboard-history-panel");'
    " if (hit) return hit;"
    ' for (const node of root.querySelectorAll("*")) if (node.shadowRoot) {'
    " const found = walk(node.shadowRoot); if (found) return found; }"
    " return null; };"
    " const panel = walk(document); return panel && panel.shadowRoot; })()"
)


async def main():
    SHOTS.mkdir(parents=True, exist_ok=True)
    chrome = subprocess.Popen(
        [
            BROWSER,
            "--headless=new",
            f"--remote-debugging-port={PORT}",
            f"--user-data-dir={PROFILE}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
            "--window-size=1500,950",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        endpoint = None
        for _ in range(60):
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{PORT}/json/version", timeout=1
                ) as response:
                    endpoint = json.load(response)["webSocketDebuggerUrl"]
                    break
            except Exception:
                time.sleep(0.5)
        if not endpoint:
            sys.exit("Chrome never came up on the debugging port")

        async with websockets.connect(endpoint, max_size=40 * 1024 * 1024) as socket:
            page = Session(socket)
            target = await page.send(
                "Target.createTarget", {"url": "about:blank"}, on_browser=True
            )
            attached = await page.send(
                "Target.attachToTarget",
                {"targetId": target["targetId"], "flatten": True},
                on_browser=True,
            )
            page.session_id = attached["sessionId"]
            await page.send("Page.enable")
            await page.send("Runtime.enable")

            # Log in the way the frontend logs itself in.
            await page.send("Page.navigate", {"url": f"{BASE}/lovelace"})
            await page.settle('document.readyState === "complete"')
            await page.js(
                "(() => { const t = "
                + json.dumps(
                    {
                        "access_token": TOKEN,
                        "token_type": "Bearer",
                        "expires_in": 1800,
                        "clientId": None,
                        "refresh_token": "",
                    }
                )
                + "; t.hassUrl = location.origin; t.expires = Date.now() + 1800000;"
                " localStorage.setItem('hassTokens', JSON.stringify(t));"
                " return t.hassUrl; })()"
            )

            print("\n-- The history --")
            await page.send("Page.navigate", {"url": f"{BASE}/dashboard-history"})
            ok = await page.settle(f'{PANEL}?.querySelectorAll(".change").length')
            if not ok:
                await page.shot("0-stuck.png")
                sys.exit("The panel showed no changes - see 0-stuck.png")
            rows = await page.js(f'{PANEL}.querySelectorAll(".change").length')
            print(f"  rows: {rows}")
            await page.shot("1-history.png")

            # The pencil only shows on hover, so hover for real.
            box = await page.js(
                f'(() => {{ const r = {PANEL}.querySelector(".change")'
                ".getBoundingClientRect();"
                " return {x: r.x, y: r.y, w: r.width, h: r.height}; })()"
            )
            await page.mouse(box["x"] + box["w"] - 30, box["y"] + box["h"] / 2)
            await asyncio.sleep(0.5)
            opacity = await page.js(
                f'getComputedStyle({PANEL}.querySelector(".pen")).opacity'
            )
            print(f"  pencil opacity while hovering: {opacity}")
            await page.shot("2-pen-visible.png")

            print("\n-- The description dialog --")
            await page.js(f'{PANEL}.querySelector("[data-describe]").click()')
            await page.settle(f'{PANEL}.querySelector("dialog.describe").open')
            focused = await page.js(
                f'{PANEL}.activeElement && {PANEL}.activeElement.className'
            )
            print(f"  focus sits on: {focused!r}")
            await page.shot("3-describe-dialog.png")

            expanded = await page.js(f'{PANEL}.querySelectorAll(".detail").length')
            print(f"  expanded rows (must be 0): {expanded}")

            text = "Vor dem Umbau der Heizungskarten"
            await page.js(
                f'(() => {{ const f = {PANEL}.querySelector("dialog.describe input.text");'
                f" f.value = {json.dumps(text)};"
                ' f.dispatchEvent(new KeyboardEvent("keydown", {key: "Enter", bubbles: true}));'
                " })()"
            )
            await page.settle(
                f'{PANEL}.querySelector(".change .what").innerText.indexOf("Umbau") >= 0'
            )
            headline = await page.js(f'{PANEL}.querySelector(".change .what").innerText')
            print("  headline now:\n    " + headline.replace("\n", "\n    "))
            await page.shot("4-described.png")

            print("\n-- Prefilled on reopening --")
            await page.js(f'{PANEL}.querySelector("[data-describe]").click()')
            await page.settle(f'{PANEL}.querySelector("dialog.describe").open')
            prefilled = await page.js(
                f'{PANEL}.querySelector("dialog.describe input.text").value'
            )
            print(f"  field prefilled with: {prefilled!r}")

            print("\n-- Undone by emptying the field --")
            await page.js(
                f'(() => {{ const f = {PANEL}.querySelector("dialog.describe input.text");'
                ' f.value = "";'
                ' f.dispatchEvent(new KeyboardEvent("keydown", {key: "Enter", bubbles: true}));'
                " })()"
            )
            await page.settle(
                f'{PANEL}.querySelector(".change .what").innerText.indexOf("Umbau") < 0'
            )
            after = await page.js(f'{PANEL}.querySelector(".change .what").innerText')
            print(f"  headline back to: {after.strip()!r}")
            has_auto = await page.js(f'!!{PANEL}.querySelector(".change .auto")')
            print(f"  grey second line still there (must be False): {has_auto}")

            print("\n-- Plain words on expanding: a deletion commit --")
            # The path fixed in operations.py: at a deletion commit the
            # dashboard's file has left the tree. Reporting that as "did
            # not exist at" would fail the one change most in need of an
            # explanation.
            await page.js(f'{PANEL}.querySelector(".change").click()')
            await page.settle(f'!!{PANEL}.querySelector(".detail .plain")')
            plain = await page.js(
                f'{PANEL}.querySelector(".detail .plain").innerText'
            )
            print("    " + plain.strip().replace("\n", "\n    "))
            await page.shot("5-expanded-deletion.png")

            print("\n-- Plain words on a live dashboard --")
            await page.js(
                f'(() => {{ for (const b of {PANEL}.querySelectorAll(".dash"))'
                ' if (b.dataset.key === "ground-floor") { b.click(); return true; }'
                " return false; })()"
            )
            # Wait for the switch to have actually happened. Waiting on a
            # row count is a race: the dashboard before this one already
            # had rows, so the click landed on the old DOM.
            switched = await page.settle(
                f'{PANEL}.querySelector(".change .what").innerText'
                '.indexOf("ground-floor") === 0'
            )
            print(f"    switch completed: {switched}")
            await page.js(f'{PANEL}.querySelector(".change").click()')
            found = await page.settle(f'!!{PANEL}.querySelector(".detail .plain")')
            if not found:  # pragma: no cover - kept as a diagnostic
                state = await page.js(
                    "(() => { const p = " + PANEL + "; return {"
                    '  banner: p.querySelector(".banner") && p.querySelector(".banner").innerText,'
                    '  detail: p.querySelector(".detail") && p.querySelector(".detail").innerText,'
                    '  rows: p.querySelectorAll(".change").length,'
                    '  firstRow: p.querySelector(".change .what").innerText,'
                    " }; })()"
                )
                print("    NO plain words. State:", json.dumps(state, ensure_ascii=False, indent=6))
                await page.shot("6-no-plain.png")
            else:
                plain = await page.js(f'{PANEL}.querySelector(".detail .plain").innerText')
                print("    " + plain.strip().replace("\n", "\n    "))
                await page.shot("6-expanded-live.png")

            print("\n-- The confirm dialog: words on top, diff collapsed --")
            await page.js(f'{PANEL}.querySelector("[data-state]").click()')
            await page.settle(f'{PANEL}.querySelector("dialog.confirm").open')
            await page.settle(f'!!{PANEL}.querySelector("dialog.confirm .plain")')
            shape = await page.js(
                "(() => { const d = "
                + PANEL
                + '.querySelector("dialog.confirm");'
                ' const details = d.querySelector("details.raw");'
                " return {"
                '  heading: d.querySelector(".plain h3").innerText,'
                "  diffCollapsed: details ? !details.open : null,"
                '  diffPresent: !!d.querySelector("details.raw pre"),'
                '  plainText: d.querySelector(".plain").innerText.slice(0, 300),'
                " }; })()"
            )
            print(f"    heading: {shape['heading']!r}")
            print(f"    diff present: {shape['diffPresent']}, collapsed: {shape['diffCollapsed']}")
            print("    " + shape["plainText"].strip().replace("\n", "\n    "))
            await page.shot("7-confirm-dialog.png")
            # Cancel, emphatically: this instance is disposable but the
            # point of the preview is that nothing is written.
            await page.js(
                f'{PANEL}.querySelector("dialog.confirm").close("cancel")'
            )
            await asyncio.sleep(0.5)

            print("\nconsole:", page.console or "no errors, no warnings")
    finally:
        chrome.terminate()


asyncio.run(main())
