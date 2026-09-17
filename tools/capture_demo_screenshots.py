"""Capture the screenshots the README shows, from the demo instance.

Documentation, not a test. Nothing here asserts anything and pytest
never collects it, which is why it sits in tools/ and not beside
run_checks.py. Its one job is the job a screenshot has to survive: the
panel changes, and the picture has to change with it. An image nobody
can regenerate is worse than no image at all.

    python3 tools/capture_demo_screenshots.py

WHAT IT NEEDS - and this part is not in the repository yet:

A second Home Assistant, separate from the throwaway one in
docker/compose.yaml. That one belongs to run_checks.py, which edits and
deletes as it goes; a screenshot wants a history that reads tidily.
This script expects the demo instance on http://127.0.0.1:8125 with

  - three dashboards, url_path `home-overview`, `living-room` and
    `dashboard-standard`,
  - `living-room` carrying at least three recorded changes and two
    named versions, v1.0.0 and v1.1.0,
  - a long-lived access token in <demo>/token.txt.

DASHBOARD_HISTORY_DEMO points at that directory; the default is
../ha-dashboard-history-demo, beside this repository. Building the
instance from the repository the way make_probe_dashboard.py builds
its probe is still open work. Until then this script says what it is
missing rather than photographing a blank page.

Overridable, all of it, because the first version wrote one machine's
home directory into a public repository:

    DASHBOARD_HISTORY_DEMO      the demo instance's directory
    DASHBOARD_HISTORY_DEMO_URL  where it answers  (default :8125)
    DASHBOARD_HISTORY_CDP_PORT  Chrome's debug port  (default 9335)
    DASHBOARD_HISTORY_SHOTS     where images land  (default docs/images)

It opens restore dialogs and closes every one of them with `cancel`,
so it writes nothing - but it drives a live panel, and this
repository's rule about the real installation holds here too.
"""

import asyncio
import base64
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time
import urllib.request

import websockets

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEMO = pathlib.Path(
    os.environ.get("DASHBOARD_HISTORY_DEMO") or ROOT.parent / "ha-dashboard-history-demo"
)

BASE = os.environ.get("DASHBOARD_HISTORY_DEMO_URL", "http://127.0.0.1:8125")
PORT = int(os.environ.get("DASHBOARD_HISTORY_CDP_PORT", "9335"))
TOKEN_PATH = DEMO / "token.txt"
PROFILE = DEMO / "chrome-profile"
OUTPUT_DIR = pathlib.Path(
    os.environ.get("DASHBOARD_HISTORY_SHOTS") or ROOT / "docs" / "images"
)


def read_token():
    """Read the token when the run starts, not when the module loads.

    At module level a missing file ends the process with a bare
    FileNotFoundError before anything can say which file or why.
    """
    try:
        return TOKEN_PATH.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        sys.exit(
            f"No access token at {TOKEN_PATH}.\n"
            f"Put a long-lived token there, or set DASHBOARD_HISTORY_DEMO "
            f"to the demo instance's directory."
        )

PANEL = (
    "(() => { const walk = (root) => {"
    ' const hit = root.querySelector("dashboard-history-panel");'
    " if (hit) return hit;"
    ' for (const node of root.querySelectorAll("*")) if (node.shadowRoot) {'
    " const found = walk(node.shadowRoot); if (found) return found; }"
    " return null; };"
    " const panel = walk(document); return panel && panel.shadowRoot; })()"
)
ELEMENT = (
    "(() => { const walk = (root) => {"
    ' const hit = root.querySelector("dashboard-history-panel");'
    " if (hit) return hit;"
    ' for (const node of root.querySelectorAll("*")) if (node.shadowRoot) {'
    " const found = walk(node.shadowRoot); if (found) return found; }"
    " return null; };"
    " const panel = walk(document); return panel; })()"
)


class CDPSession:
    def __init__(self, socket):
        self.socket = socket
        self.session_id = None
        self._next = 0

    async def send(self, method, params=None, *, on_browser=False):
        self._next += 1
        message = {"id": self._next, "method": method, "params": params or {}}
        if self.session_id and not on_browser:
            message["sessionId"] = self.session_id
        await self.socket.send(json.dumps(message))
        while True:
            raw = await self.socket.recv()
            answer = json.loads(raw)
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
            details = result["exceptionDetails"]
            said = (details.get("exception") or {}).get("description")
            raise RuntimeError(said or details.get("text") or "unknown")
        return result["result"].get("value")

    async def settle(self, expression, seconds=15):
        """Wait for `expression` to go true, and give up loudly.

        This returned False once, and not one of its callers looked.
        A panel that never rendered was therefore photographed blank,
        and the run still ended on "All screenshots captured
        successfully!". Every expression below reaches into the
        panel's own internals - `_select`, `_setMode`, `_busy` - so a
        rename in panel.js is exactly how that happens.
        """
        deadline = time.time() + seconds
        last = None
        while time.time() < deadline:
            try:
                if await self.js(expression):
                    return True
            except RuntimeError as trouble:
                last = trouble
            await asyncio.sleep(0.3)
        raise TimeoutError(
            f"waited {seconds}s for: {expression}"
            + (f"\nlast error: {last}" if last else "")
        )

    async def shot(self, name):
        result = await self.send("Page.captureScreenshot", {"format": "png"})
        target = OUTPUT_DIR / name
        target.write_bytes(base64.b64decode(result["data"]))
        print(f"Captured: {target.name} ({len(result['data'])} bytes base64)")


async def main():
    if shutil.which("google-chrome") is None:
        sys.exit("google-chrome is not on PATH; this script drives it over CDP.")
    token = read_token()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Demo instance: {BASE}   images: {OUTPUT_DIR}")
    chrome = subprocess.Popen(
        [
            "google-chrome",
            "--headless=new",
            f"--remote-debugging-port={PORT}",
            f"--user-data-dir={PROFILE}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
            "--lang=en-US",
            "--window-size=1400,900",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        endpoint = None
        for _ in range(30):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=1) as resp:
                    endpoint = json.load(resp)["webSocketDebuggerUrl"]
                    break
            except Exception:
                time.sleep(0.3)
        if not endpoint:
            sys.exit("Chrome did not start")

        async with websockets.connect(endpoint, max_size=40 * 1024 * 1024) as socket:
            page = CDPSession(socket)
            target = await page.send("Target.createTarget", {"url": "about:blank"}, on_browser=True)
            attached = await page.send(
                "Target.attachToTarget",
                {"targetId": target["targetId"], "flatten": True},
                on_browser=True,
            )
            page.session_id = attached["sessionId"]
            await page.send("Page.enable")
            await page.send("Runtime.enable")

            # Set Device Metrics: 1400x900, deviceScaleFactor: 2 for sharp retina screenshots
            await page.send(
                "Emulation.setDeviceMetricsOverride",
                {
                    "width": 1400,
                    "height": 900,
                    "deviceScaleFactor": 2,
                    "mobile": False,
                },
            )

            # Navigate to lovelace and set token
            print("Navigating to Lovelace and setting auth...")
            await page.send("Page.navigate", {"url": f"{BASE}/lovelace"})
            await page.settle('document.readyState === "complete"')
            await page.js(
                "(() => { const t = "
                + json.dumps(
                    {
                        "access_token": token,
                        "token_type": "Bearer",
                        "expires_in": 3600,
                        "clientId": None,
                        "refresh_token": "",
                    }
                )
                + "; t.hassUrl = location.origin; t.expires = Date.now() + 3600000;"
                " localStorage.setItem('hassTokens', JSON.stringify(t));"
                " localStorage.setItem('selectedLanguage', 'en');"
                " return t.hassUrl; })()"
            )

            # Navigate to dashboard-history panel
            print("Navigating to Dashboard History panel...")
            await page.send("Page.navigate", {"url": f"{BASE}/dashboard-history"})
            await page.settle(f"!!{PANEL}")
            await page.settle(f'!!{PANEL}.querySelector(".bar")')

            # -------------------------------------------------------------
            # LIGHT THEME
            # -------------------------------------------------------------
            print("\n=== LIGHT THEME ===")
            await page.send(
                "Emulation.setEmulatedMedia",
                {"features": [{"name": "prefers-color-scheme", "value": "light"}]},
            )
            await asyncio.sleep(0.5)

            # Select living-room dashboard and set advanced mode
            print("Selecting living-room dashboard in Advanced Mode...")
            setup_light = f"""(async () => {{
                const p = {ELEMENT};
                await p._select("living-room");
                p._setMode("advanced");
                p._open = null;
                p._verOpen.add("now");
                p._verOpen.add("living-room/v1.1.0");
                p._render();
            }})()"""
            await page.js(setup_light)
            await page.settle(f'{PANEL}?.querySelectorAll(".change").length >= 3')
            await asyncio.sleep(1.0)

            # 1. Advanced Mode Overview Light
            print("1. Capturing 01-history-overview-light.png...")
            await page.shot("01-history-overview-light.png")

            # 2. Diff Expanded Light
            print("2. Expanding first change row...")
            expand_js = f"""(async () => {{
                const p = {ELEMENT};
                const rev = p._changes[0].revision;
                await p._expand(rev);
            }})()"""
            await page.js(expand_js)
            await page.settle(f'!!{PANEL}.querySelector(".detail")')
            await page.settle(f'{ELEMENT}._busy === 0')
            # Open the new technical diff inside the detail card
            await page.js(
                f'(() => {{ const raw = {PANEL}.querySelector(".detail details.raw"); if (raw) raw.open = true; }})()'
            )
            await asyncio.sleep(1.0)
            print("Capturing 02-diff-expanded-light.png...")
            await page.shot("02-diff-expanded-light.png")

            # 3. Replace Dialog Light
            print("3. Opening replace dialog...")
            await page.js(
                f'(() => {{ const btn = {PANEL}.querySelector(".detail .action-bar [data-replace]"); '
                'if (!btn) throw new Error(".detail .action-bar [data-replace] not found"); '
                'btn.click(); })()'
            )
            await page.settle(f'{PANEL}.querySelector("dialog.replace")?.open')
            await page.settle(f'!!{PANEL}.querySelector("dialog.replace .replace-choice")')
            # Open the raw diff details inside the dialog
            await page.js(
                f'(() => {{ const raw = {PANEL}.querySelector("dialog.replace details.raw"); if (raw) raw.open = true; }})()'
            )
            await asyncio.sleep(0.5)
            print("Capturing 03-restore-dialog-light.png...")
            await page.shot("03-restore-dialog-light.png")
            await page.shot("03-replace-dialog-light.png")

            # Click checkbox to show keepfields
            await page.js(
                f'(() => {{ const cb = {PANEL}.querySelector("dialog.replace .keepbox"); if (cb) cb.click(); }})()'
            )
            await asyncio.sleep(0.5)
            print("Capturing 03b-restore-dialog-checked-light.png...")
            await page.shot("03b-restore-dialog-checked-light.png")

            # Close dialog
            await page.js(f'{PANEL}.querySelector("dialog.replace").close("cancel")')
            await asyncio.sleep(0.5)

            # 4. Compare Mode
            print("4. Opening Compare Mode...")
            await page.js(f"{PANEL}.querySelector('[data-compare-toggle]').click()")
            await page.js(
                f"(() => {{ const boxes = [...{PANEL}.querySelectorAll('.compare-check')];"
                " boxes[0].click();"
                " const differs = boxes.slice(1).find("
                "   (box) => box.closest('.penholder')?.querySelector('[data-state], [data-replace]'));"
                " (differs || boxes[boxes.length - 1]).click(); })()"
            )
            await page.settle(
                f'!!{PANEL}.querySelector("dialog.compare[open]") &&'
                f' !{PANEL}.querySelector("dialog.compare .row-loading")',
                10,
            )
            await asyncio.sleep(0.5)
            print("Capturing 04-compare-mode-light.png...")
            await page.shot("04-compare-mode-light.png")

            has_restore = await page.js(
                f'!!{PANEL}.querySelector("dialog.compare [data-compare-restore]")'
            )
            if has_restore:
                await page.js(
                    f'(() => {{ const btn = {PANEL}.querySelector("dialog.compare [data-compare-restore]"); if (btn) btn.click(); }})()'
                )
                await page.settle(f'{PANEL}.querySelector("dialog.confirm")?.open')
                await page.settle(f'!!{PANEL}.querySelector("dialog.confirm .plain")')
                await asyncio.sleep(0.5)
                print("Capturing 03c-put-back-dialog-light.png...")
                await page.shot("03c-put-back-dialog-light.png")
                await page.js(f'{PANEL}.querySelector("dialog.confirm").close("cancel")')

            await page.js(f'{PANEL}.querySelector("dialog.compare").close("cancel")')
            await page.js(f"{PANEL}.querySelector('[data-compare-toggle]').click()")
            await asyncio.sleep(0.5)

            # 4. Simple Mode Light
            print("4. Switching to Simple Mode...")
            simple_js = f"""(async () => {{
                const p = {ELEMENT};
                p._open = null;
                p._verOpen.delete("now");
                p._setMode("simple");
            }})()"""
            await page.js(simple_js)
            await asyncio.sleep(1.0)
            print("Capturing 04-simple-mode-versions-light.png...")
            await page.shot("04-simple-mode-versions-light.png")

            # -------------------------------------------------------------
            # DARK THEME
            # -------------------------------------------------------------
            print("\n=== DARK THEME ===")
            await page.send(
                "Emulation.setEmulatedMedia",
                {"features": [{"name": "prefers-color-scheme", "value": "dark"}]},
            )
            await asyncio.sleep(1.5)

            # 5. Simple Mode Dark
            print("5. Capturing 08-simple-mode-versions-dark.png...")
            await page.shot("08-simple-mode-versions-dark.png")

            # 6. Advanced Mode Overview Dark
            print("6. Setting Advanced Mode (Dark)...")
            setup_dark = f"""(async () => {{
                const p = {ELEMENT};
                p._setMode("advanced");
                p._open = null;
                p._verOpen.add("now");
                p._verOpen.add("living-room/v1.1.0");
                p._render();
            }})()"""
            await page.js(setup_dark)
            await page.settle(f'{PANEL}?.querySelectorAll(".change").length >= 3')
            await asyncio.sleep(1.0)
            print("Capturing 05-history-overview-dark.png...")
            await page.shot("05-history-overview-dark.png")

            # 7. Diff Expanded Dark
            print("7. Expanding first change row (Dark)...")
            await page.js(expand_js)
            await page.settle(f'!!{PANEL}.querySelector(".detail")')
            await page.settle(f'{ELEMENT}._busy === 0')
            await page.js(
                f'(() => {{ const raw = {PANEL}.querySelector(".detail details.raw"); if (raw) raw.open = true; }})()'
            )
            await asyncio.sleep(1.0)
            print("Capturing 06-diff-expanded-dark.png...")
            await page.shot("06-diff-expanded-dark.png")

            # 8. Replace Dialog Dark
            print("8. Opening replace dialog (Dark)...")
            await page.js(
                f'(() => {{ const btn = {PANEL}.querySelector(".detail .action-bar [data-replace]"); '
                'if (!btn) throw new Error(".detail .action-bar [data-replace] not found"); '
                'btn.click(); })()'
            )
            await page.settle(f'{PANEL}.querySelector("dialog.replace")?.open')
            await page.settle(f'!!{PANEL}.querySelector("dialog.replace .replace-choice")')
            await page.js(
                f'(() => {{ const raw = {PANEL}.querySelector("dialog.replace details.raw"); if (raw) raw.open = true; }})()'
            )
            await asyncio.sleep(0.5)
            print("Capturing 07-restore-dialog-dark.png...")
            await page.shot("07-restore-dialog-dark.png")
            await page.shot("07-replace-dialog-dark.png")

            # Click checkbox to show keepfields
            await page.js(
                f'(() => {{ const cb = {PANEL}.querySelector("dialog.replace .keepbox"); if (cb) cb.click(); }})()'
            )
            await asyncio.sleep(0.5)
            print("Capturing 07b-restore-dialog-checked-dark.png...")
            await page.shot("07b-restore-dialog-checked-dark.png")

            # Close dialog
            await page.js(f'{PANEL}.querySelector("dialog.replace").close("cancel")')
            await asyncio.sleep(0.5)

            # Open Put back dialog (Dark) - via compare mode
            await page.js(f"{PANEL}.querySelector('[data-compare-toggle]').click()")
            await page.js(
                f"(() => {{ const boxes = [...{PANEL}.querySelectorAll('.compare-check')];"
                " boxes[0].click();"
                " const differs = boxes.slice(1).find("
                "   (box) => box.closest('.penholder')?.querySelector('[data-state], [data-replace]'));"
                " (differs || boxes[boxes.length - 1]).click(); })()"
            )
            await page.settle(
                f'!!{PANEL}.querySelector("dialog.compare[open]") &&'
                f' !{PANEL}.querySelector("dialog.compare .row-loading")',
                10,
            )
            await asyncio.sleep(0.5)
            print("Capturing 08-compare-mode-dark.png...")
            await page.shot("08-compare-mode-dark.png")

            has_restore_dark = await page.js(
                f'!!{PANEL}.querySelector("dialog.compare [data-compare-restore]")'
            )
            if has_restore_dark:
                await page.js(
                    f'(() => {{ const btn = {PANEL}.querySelector("dialog.compare [data-compare-restore]"); if (btn) btn.click(); }})()'
                )
                await page.settle(f'{PANEL}.querySelector("dialog.confirm")?.open')
                await page.settle(f'!!{PANEL}.querySelector("dialog.confirm .plain")')
                await asyncio.sleep(0.5)
                print("Capturing 07c-put-back-dialog-dark.png...")
                await page.shot("07c-put-back-dialog-dark.png")
                await page.js(f'{PANEL}.querySelector("dialog.confirm").close("cancel")')

            await page.js(f'{PANEL}.querySelector("dialog.compare").close("cancel")')
            await page.js(f"{PANEL}.querySelector('[data-compare-toggle]').click()")

            print("\nAll screenshots captured successfully!")

    finally:
        chrome.terminate()
        chrome.wait()


if __name__ == "__main__":
    asyncio.run(main())

