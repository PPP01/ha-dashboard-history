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
    answers with an empty object - falsy in Python. Wait on booleans. The
    same serialisation drops `undefined` values, and the key disappears
    with them: end an optional chain with `?? null` or read a KeyError.

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

# The same walk, stopping one step earlier. Sections that render a state
# rather than read one need the element: it renders from `_changes`, and
# handing it that array drives the real rendering path.
ELEMENT = PANEL.replace(" return panel && panel.shadowRoot; })()", " return panel; })()")


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

            # From here on, and not before. The login navigation above is an
            # artificial flow - an unauthenticated hit on /lovelace, then a
            # token injected mid-redirect - and Home Assistant's own
            # frontend intermittently rejects a promise during it. Reported
            # as a console error it looked like the panel's, three times
            # over. Collecting from the panel onwards means anything printed
            # below is the panel's own.
            page.console.clear()

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
            # Click only if the row is not expanded already - a click on an
            # open row collapses it, and the section then read the words off
            # a `.detail` that was no longer there and threw. Everything
            # below this line, the whole version half of the panel
            # included, sat behind that throw and never ran once.
            opened = False
            for _ in range(3):
                await page.js(
                    f'(() => {{ if (!{PANEL}.querySelector(".detail"))'
                    f' {PANEL}.querySelector(".change").click(); }})()'
                )
                opened = await page.settle(
                    f'!!{PANEL}.querySelector(".detail .plain")', 10
                )
                if opened:
                    break
            if opened:
                plain = await page.js(
                    f'{PANEL}.querySelector(".detail .plain").innerText'
                )
                print("    " + plain.strip().replace("\n", "\n    "))
            else:  # pragma: no cover - kept as a diagnostic
                print("    NO plain words - the row would not stay expanded")
            await page.shot("5-expanded-deletion.png")

            print("\n-- Plain words on a live dashboard --")
            # The first dashboard that still exists, whichever it is. Naming
            # one would put a name out of somebody's installation into a
            # public repository, and nobody else could run this.
            live = await page.js(
                f'(() => {{ const all = [...{PANEL}.querySelectorAll(".dash")];'
                ' const b = all.find((x) => !x.closest("details.dead"));'
                " if (!b) return null; b.click(); return b.dataset.key; })()"
            )
            print(f"    switched to: {live!r}")
            # Wait for the switch to have actually happened. Waiting on a
            # row count is a race: the dashboard before this one already
            # had rows, so the click landed on the old DOM.
            switched = await page.settle(
                f'{PANEL}.querySelector(".change .what").innerText'
                f".indexOf({json.dumps(live)}) === 0"
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
                '  keeps: d.querySelector(".keeps")'
                '    ?.innerText.replace(/\\s+/g, " ").trim() ?? null,'
                " }; })()"
            )
            print(f"    heading: {shape['heading']!r}")
            print(f"    keeps: {shape['keeps']!r}")
            print(f"    diff present: {shape['diffPresent']}, collapsed: {shape['diffCollapsed']}")
            print("    " + shape["plainText"].strip().replace("\n", "\n    "))
            await page.shot("7-confirm-dialog.png")
            # Cancel, emphatically: this instance is disposable but the
            # point of the preview is that nothing is written.
            await page.js(
                f'{PANEL}.querySelector("dialog.confirm").close("cancel")'
            )
            await asyncio.sleep(0.5)

            print("\n-- Where am I: the current state --")
            shape = await page.js(
                "(() => { const p = " + PANEL + "; return {"
                '  heading: p.querySelector(".current .heading")?.innerText,'
                '  chipNow: p.querySelector(".current .chip.now")?.innerText,'
                '  divider: p.querySelector(".divider")?.innerText,'
                '  sameAsNow: p.querySelectorAll(".chip.sameas").length,'
                '  rowsInCurrent: p.querySelectorAll(".current .card").length,'
                " }; })()"
            )
            for name, value in shape.items():
                print(f"    {name}: {value!r}")

            print("\n-- The button, where it would do nothing --")
            # Row 1's target is row 2. On a history that went back and forth
            # that is the current state, and the button used to be offered
            # anyway - with a preview reading "No difference."
            await page.js(f'{PANEL}.querySelectorAll(".change")[1].click()')
            await page.settle(f'!!{PANEL}.querySelectorAll(".detail")[0]')
            state = await page.js(
                "(() => { const d = " + PANEL + '.querySelector(".detail"); return {'
                # `?? null` on purpose: an undefined value is dropped from
                # the object by returnByValue, and the key vanishes with it.
                '  button: d.querySelector("[data-state]")?.innerText.trim() ?? null,'
                '  reason: d.querySelector(".why")?.innerText.replace(/\\s+/g, " ").trim() ?? null,'
                " }; })()"
            )
            print(f"    button: {state['button']!r}")
            print(f"    reason: {state['reason']!r}")
            await page.shot("8-no-pointless-button.png")

            print("\n-- The button on the current state --")
            await page.js(f'{PANEL}.querySelectorAll(".change")[0].click()')
            await page.settle(f'!!{PANEL}.querySelector(".current .detail")')
            label = await page.js(
                f'{PANEL}.querySelector(".current .detail [data-state]")'
                "?.innerText.trim() ?? null"
            )
            print(f"    label: {label!r}")
            await page.shot("9-current-state.png")

            print("\n-- Both destinations on one row, each aimed right --")
            # A row sits between two states and offers both. Which button
            # carries which revision is the whole correctness of it: aimed
            # one row off, it overwrites the dashboard with a state nobody
            # asked for.
            #
            # Both only appear where neither target is the current state, so
            # the row is picked from the data rather than assumed - on a
            # history that went back and forth most rows show one button.
            picked = await page.js(
                "(() => { const el = document.querySelector('dashboard-history-panel')"
                " || (() => { const walk = (root) => {"
                " const hit = root.querySelector('dashboard-history-panel');"
                " if (hit) return hit;"
                " for (const n of root.querySelectorAll('*')) if (n.shadowRoot) {"
                " const f = walk(n.shadowRoot); if (f) return f; } return null; };"
                " return walk(document); })();"
                " const c = el._changes;"
                " for (let i = 0; i < c.length - 1; i++)"
                "   if (!c[i].same_as_now && !c[i + 1].same_as_now)"
                "     return {index: i, self: c[i].revision.slice(0, 7),"
                "             before: c[i + 1].revision.slice(0, 7)};"
                " return null; })()"
            )
            if not picked:
                print("    no row on this dashboard offers both - nothing to check")
            else:
                print(f"    row {picked['index']}: after={picked['self']} "
                      f"before={picked['before']}")
                await page.js(
                    f'{PANEL}.querySelectorAll(".change")[{picked["index"]}].click()'
                )
                await page.settle(f'!!{PANEL}.querySelector(".detail .backto")')
                aim = await page.js(
                    "(() => { const b = [..." + PANEL
                    + '.querySelectorAll(".detail .backto button")];'
                    " return b.map(x => [x.innerText.trim(),"
                    "                     x.dataset.state.slice(0, 7)]); })()"
                )
                for label, target in aim:
                    where = (
                        "the state BEFORE this change"
                        if target == picked["before"]
                        else "the state AFTER this change"
                        if target == picked["self"]
                        else "SOMEWHERE ELSE - WRONG"
                    )
                    print(f"    {label!r} -> {target} = {where}")
                print(f"    buttons on that row: {len(aim)}")
                await page.shot("12-two-destinations.png")

            print("\n-- Naming what each half of a row is about --")
            # Measured on dh-testlauf: a row read "4 moved · same as now",
            # which as one sentence is a contradiction. Both halves were
            # true; nothing said the message was about the change and the
            # chip about the state it left behind.
            # textContent, not innerText: a chip inside a collapsed
            # version section is not rendered, and innerText answers ""
            # for anything unrendered. The element was there, the title
            # read back fine, and the text came out empty - a check that
            # reports nothing where something stands.
            #
            # `now` being absent is not a fault either: the first row of
            # a version section carries no chip of its own, because the
            # section head a few pixels above says the same thing. On a
            # dashboard whose newest entry is marked, there is therefore
            # no `.chip.now` at all.
            chips = await page.js(
                "(() => { const p = " + PANEL + "; return {"
                '  now: p.querySelector(".chip.now")?.textContent.trim() ?? null,'
                '  nowTitle: p.querySelector(".chip.now")?.title ?? null,'
                '  sameas: p.querySelector(".chip.sameas")?.textContent.trim() ?? null,'
                '  sameasTitle: p.querySelector(".chip.sameas")?.title ?? null,'
                '  versionChip: p.querySelector(".chip.ver")?.textContent.trim() ?? null,'
                '  headsThatSayIt: [...p.querySelectorAll("details.ver summary .count")]'
                '    .map(x => x.textContent.trim())'
                '    .filter(x => x.indexOf("state") >= 0),'
                " }; })()"
            )
            for name, value in chips.items():
                print(f"    {name}: {value!r}")

            print("\n-- The sidebar: deleted dashboards folded away --")
            side = await page.js(
                "(() => { const p = " + PANEL + "; return {"
                '  live: p.querySelectorAll(".side > .dash").length,'
                '  fold: p.querySelector("details.dead summary")?.innerText ?? null,'
                '  foldedAway: p.querySelectorAll("details.dead .dash").length,'
                '  openByDefault: p.querySelector("details.dead")?.open ?? null,'
                " }; })()"
            )
            for name, value in side.items():
                print(f"    {name}: {value!r}")
            await page.shot("10-sidebar-folded.png")

            print("\n-- The forget dialog on a deleted dashboard --")
            await page.js(
                "(() => { const f = " + PANEL + '.querySelector("details.dead");'
                " if (f) f.open = true; })()"
            )
            await asyncio.sleep(0.4)
            picked = await page.js(
                "(() => { const b = " + PANEL
                + '.querySelector("details.dead .dash");'
                " if (!b) return null; b.click(); return b.dataset.key; })()"
            )
            print(f"    picked: {picked!r}")
            await page.settle(f'!!{PANEL}.querySelector("[data-forget]")')
            await page.js(f'{PANEL}.querySelector("[data-forget]").click()')
            await page.settle(f'{PANEL}.querySelector("dialog.forget").open')
            body = await page.js(
                f'{PANEL}.querySelector("dialog.forget .body").innerText'
                ".replace(/\\s+/g, " + '" ")'
            )
            print(f"    dialog says: {body[:220]}")
            await page.shot("11-forget-dialog.png")
            # Cancel. Nothing in an inspection script may delete history.
            await page.js(f'{PANEL}.querySelector("dialog.forget").close("cancel")')
            await asyncio.sleep(0.4)
            gone = await page.js(
                f'!!{PANEL}.querySelector("dialog.forget").open'
            )
            print(f"    dialog still open after Cancel: {gone}")

            print("\n-- Loading the module twice, the way an update does --")
            # This Chrome starts empty and therefore never meets the case by
            # itself: a second definition needs a page session that already
            # loaded panel.js under a different fingerprint. The user's own
            # browser had one, and the panel died there with "the name has
            # already been used with this registry" - reported to Home
            # Assistant's log by the frontend, not by anything here.
            # A fresh query string per run, and not a fixed one: Home
            # Assistant sends no Cache-Control on a static path, so a fixed
            # probe URL is answered from this browser's cache on the next
            # run - which made this check pass against a panel.js that had
            # the guard removed. A check that cannot fail proves nothing.
            report = await page.js(
                "(async () => { const tag = Date.now(); try {"
                '  await import("/dashboard_history/panel.js?v=" + tag + "a");'
                '  await import("/dashboard_history/panel.js?v=" + tag + "b");'
                '  return "loaded twice, no error";'
                " } catch (error) { return String(error); } })()"
            )
            print(f"    {report}")
            registered = await page.js(
                '!!customElements.get("dashboard-history-panel")'
            )
            print(f"    element still registered: {registered}")

            print("\n-- Versions as sections --")
            # The dashboard picked out of "DELETED" above carries no
            # versions - back to a live one, the same way "-- Plain words
            # on a live dashboard --" does: the first one that still
            # exists, whichever it is. Naming one would put a name out of
            # somebody's installation into a public repository.
            live = await page.js(
                f'(() => {{ const all = [...{PANEL}.querySelectorAll(".dash")];'
                ' const b = all.find((x) => !x.closest("details.dead"));'
                " if (!b) return null; b.click(); return b.dataset.key; })()"
            )
            if live:
                await page.settle(
                    f'{PANEL}.querySelector(".change .what")?.innerText'
                    f".indexOf({json.dumps(live)}) === 0"
                )
            sections = await page.js(
                "(() => { const p = " + PANEL
                + '; return [...p.querySelectorAll("details.ver")].map(d => ({'
                "  name: d.querySelector('summary .name')?.innerText ?? null,"
                "  title: d.querySelector('summary .grow')?.innerText ?? null,"
                "  count: d.querySelector('summary .count')?.innerText ?? null,"
                "  hasBack: !!d.querySelector('summary [data-state]'),"
                " })); })()"
            )
            print(f"    details.ver found: {len(sections)}")
            for s in sections:
                print(
                    f"    {s['name']!r}  {s['title']!r}  {s['count']!r}"
                    f"  back button: {s['hasBack']}"
                )
            await page.shot("13-version-sections.png")

            print("\n-- The button on a row --")
            await page.js(f'{PANEL}.querySelector(".change").click()')
            # Wait for the row's own explain/deleted_since fetch to settle,
            # not just for the button to appear - it renders on the first,
            # synchronous pass already, before that fetch resolves. Firing
            # the next guarded action while it is still in flight races two
            # re-renders against each other.
            await page.settle(f'!{PANEL}.querySelector(".bar .muted")')
            has_button = await page.js(
                f'!!{PANEL}.querySelector(".detail .mkver button")'
            )
            label = await page.js(
                f'{PANEL}.querySelector(".detail .mkver button")'
                "?.innerText.trim() ?? null"
            )
            print(f"    '.detail .mkver button' present: {has_button}")
            print(f"    label: {label!r}")
            await page.shot("14-version-button.png")

            print("\n-- The three numbers --")
            if not has_button:
                print("    no 'Version up to here' button - nothing to click")
            else:
                await page.js(f'{PANEL}.querySelector(".detail .mkver button").click()')
                opened = await page.settle(f'{PANEL}.querySelector("dialog.version")?.open')
                print(f"    dialog opened: {opened}")
                if opened:
                    levels = await page.js(
                        "(() => { const d = " + PANEL
                        + '.querySelector("dialog.version");'
                        ' return [...d.querySelectorAll(".levels button")].map(b => ['
                        '   b.querySelector("strong")?.innerText ?? null,'
                        "   b.getAttribute('aria-pressed'),"
                        " ]); })()"
                    )
                    for number, pressed in levels:
                        print(f"    {number!r}  aria-pressed={pressed}")
                await page.shot("15-version-dialog.png")
                # Cancel through the dialog's own button, not dialog.close():
                # this exercises the same generic ".actions button" wiring a
                # person clicking it would, and leaves nothing open behind.
                await page.js(
                    f'{PANEL}.querySelector("dialog.version .actions button[value=cancel]")'
                    "?.click()"
                )

            print("\n-- A section stays open behind the preview --")
            # _guard() rebuilds the whole shadow DOM on every guarded call,
            # including the preview fetch "Back to this version" triggers -
            # a section with no persisted open state would report itself
            # collapsed the moment that fetch starts, well before Cancel is
            # ever pressed. _verOpen in panel.js exists to prevent exactly
            # that; this is the section that would notice if it stopped
            # working.
            key = await page.js(
                "(() => { const p = " + PANEL
                + '; const d = [...p.querySelectorAll("details.ver")]'
                '   .find((x) => x.querySelector("summary [data-state]"));'
                " if (!d) return null;"
                # Sections start collapsed - open this one first, then
                # click its own "Back to this version" button, all in one
                # step so there is no gap for another render to land in.
                " if (!d.open) d.open = true;"
                " d.querySelector('summary [data-state]').click();"
                " return d.dataset.key; })()"
            )
            if not key:
                print("    no version section with a 'Back to this version' button")
            else:
                print(f"    section: {key!r}")
                await page.settle(f'{PANEL}.querySelector("dialog.confirm")?.open')
                still_open = await page.js(
                    "(() => { const p = " + PANEL
                    + '; const d = [...p.querySelectorAll("details.ver")]'
                    f"   .find((x) => x.dataset.key === {json.dumps(key)});"
                    " return d ? d.open : null; })()"
                )
                print(
                    f"    {key!r} is "
                    + ("STILL OPEN" if still_open else "COLLAPSED")
                    + " behind the preview dialog"
                )
                await page.shot("16-section-stays-open.png")
                await page.js(
                    f'{PANEL}.querySelector("dialog.confirm .actions button[value=cancel]")'
                    "?.click()"
                )

            print("\n-- Joining the two halves of 'where am I' --")
            # Built rather than waited for. The state this answers takes
            # two writes to reach - make a version, then set the dashboard
            # back to it - and an inspection script writes nothing. The
            # element renders from `_changes` alone, so handing it that
            # shape drives the real _sections / _renderTopSection /
            # _renderVersionHead path without touching the instance.
            #
            # Entry 0 is where the dashboard is and carries no version.
            # Entry 1 carries v1.0.0 and holds the same content. Entry 2
            # is neither: it is the negative control, and without it this
            # section could not tell a working join from a sentence
            # printed on every history.
            await page.js(
                "(() => { const p = " + ELEMENT + ";"
                " const now = Math.floor(Date.now() / 1000);"
                " p._changes = ["
                "  {revision: 'aaaaaaa1111', timestamp: now,"
                "   message: '1 removed, 1 added', description: null,"
                "   same_as_now: true, versions: []},"
                "  {revision: 'bbbbbbb2222', timestamp: now - 100,"
                "   message: '3 added', description: null, same_as_now: true,"
                "   versions: [{name: 'demo/v1.0.0', title: 'First version',"
                "               description: ''}]},"
                "  {revision: 'ccccccc3333', timestamp: now - 200,"
                "   message: '1 added', description: null,"
                "   same_as_now: false, versions: []},"
                " ];"
                # Entry 0 expanded, so the note beside "Version up to
                # here" renders: it has to be readable *before* the
                # click, which is the whole reason it is not only in the
                # dialog the click opens.
                " p._open = p._changes[0].revision;"
                " p._verOpen = new Set(['demo/v1.0.0']);"
                " p._render(); return p._changes.length; })()"
            )
            joined = await page.js(
                "(() => { const p = " + PANEL + "; return {"
                '  currentSays: p.querySelector(".current .chip.ver")'
                '    ?.innerText.replace(/\\s+/g, " ").trim() ?? null,'
                '  versionHead: [...p.querySelectorAll("details.ver summary .count")]'
                "    .map(x => x.innerText.trim()),"
                '  backButton: !!p.querySelector("details.ver summary [data-state]"),'
                '  besideTheButton: p.querySelector(".mkver .named")'
                '    ?.innerText.replace(/\\s+/g, " ").trim() ?? null,'
                " }; })()"
            )
            for name, value in joined.items():
                print(f"    {name}: {value!r}")
            await page.shot("17-current-names-its-version.png")

            print("\n-- The create dialog, before a second name is given --")
            # Three entries, three answers. Anything that printed the same
            # line for all three would be caught here.
            for index, what in ((0, "holds what v1.0.0 holds"),
                                (1, "carries v1.0.0 itself"),
                                (2, "neither")):
                # Started, not awaited. page.js evaluates with
                # awaitPromise, and _createVersion's promise settles only
                # when the dialog closes - handing it straight to page.js
                # makes the run wait for a dialog nobody will ever close.
                # The IIFE returns at once and leaves the dialog to the
                # settle() below.
                await page.js(
                    "(() => { " + ELEMENT + f"._createVersion({index});"
                    " return true; })()"
                )
                opened = await page.settle(
                    f'{PANEL}.querySelector("dialog.version")?.open'
                )
                if not opened:  # pragma: no cover - kept as a diagnostic
                    print(f"    entry {index} ({what}): dialog never opened")
                    continue
                said = await page.js(
                    "(() => { const c = " + PANEL
                    + '.querySelector("dialog.version [data-carries]");'
                    " return c.hidden ? null : {"
                    '   text: c.innerText.replace(/\\s+/g, " ").trim(),'
                    # The news half is bold. It was plain text under a
                    # muted line once and got read straight past.
                    '   bold: c.querySelector("strong")?.innerText ?? null,'
                    " }; })()"
                )
                print(f"    entry {index} ({what}):\n      {said!r}")
                # Cancelled every time. Nothing above ever clicks Create,
                # so no version is written to the instance.
                await page.js(
                    f'{PANEL}.querySelector("dialog.version .actions'
                    ' button[value=cancel]")?.click()'
                )
                await asyncio.sleep(0.3)
            await page.shot("18-create-dialog-warns.png")

            print("\nconsole:", page.console or "no errors, no warnings")
    finally:
        chrome.terminate()


asyncio.run(main())
