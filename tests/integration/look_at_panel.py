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
            details = result["exceptionDetails"]
            # The message lives under `exception.description`, not under
            # `text` - `text` is the bare word "Uncaught". Reported for a
            # while as exactly that, which turned every failure in here
            # into a traceback saying nothing at all.
            said = (details.get("exception") or {}).get("description")
            raise RuntimeError(said or details.get("text") or "unknown")
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

    async def opacity_at(self, x, y, selector, settle=0.5):
        """What a person would see of `selector`, pointer at (x, y).

        Hovered for real, because CSS :hover answers no synthetic event
        - and *read* rather than assumed, because a control at opacity 0
        is still in the DOM and still clickable: a click alone proves
        nothing about whether it can be found. Three pens are checked
        this way, and the check exists because the reveal is a selector
        living far from the markup it names, whose failure mode is
        silent invisibility.
        """
        await self.mouse(x, y)
        await asyncio.sleep(settle)
        return await self.js(
            f"getComputedStyle({PANEL}.querySelector({json.dumps(selector)})).opacity"
        )

    async def cancel_dialog(self, which="dialog[open]", settle=0.5):
        """Close a dialog the way a person does, through its own button.

        Not `close()`: that skips the wiring, and the wiring is part of
        what this script is here to watch. Every block that opens a
        dialog ends here - nothing on the bench is written by a check
        that is only looking - and the selector it depends on
        (`.actions` plus `button[value=cancel]`) belongs to
        `dialogs.js`. Written out at each call site it had reached four
        copies, and a dialog left open sends the next phase clicking
        against a modal.
        """
        await self.js(
            f'{PANEL}.querySelector("{which} .actions'
            ' button[value=cancel]")?.click()'
        )
        await asyncio.sleep(settle)


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
            # Everything from here to the simple-mode section reads the
            # advanced mode's rows, and which mode the panel opens in is
            # whatever this browser profile last stored - on a fresh one,
            # the simple mode, which has no .change at all. Said rather
            # than assumed: this script sat in "The panel showed no
            # changes" for a profile whose only fault was being new.
            await page.settle(f"!!{PANEL}")
            # And waited for it to have drawn once, not merely to exist.
            # The panel loads its six parts over the network and only its
            # *first* render waits for them; everything after reads
            # `escape` and `STYLE` at call time, on the promise that no
            # render happens before `set hass` has run (see the note above
            # `partsReady` in panel.js). Poking `_setMode` at an element
            # that is only constructed breaks that promise from outside,
            # and the render throws `escape is not a function`. Seen on
            # 2026-09-08, on the first run after a container restart -
            # nothing a browser does on its own, and a flake that would
            # otherwise be blamed on whatever change was in flight.
            await page.settle(f'!!{PANEL}.querySelector(".bar")')
            await page.js(f'{ELEMENT}._setMode("advanced")')
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
            opacity = await page.opacity_at(
                box["x"] + box["w"] - 30, box["y"] + box["h"] / 2, ".change .pen"
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

            # Two kinds of button sit on a row where something is
            # missing, and they differ in reach rather than in wording:
            # "Put back" reinserts one item into today's configuration,
            # setting a state back writes a whole state over the
            # dashboard. They used to share a sentence spelling that
            # difference out ("Put back adds..."), only where both were
            # on screen - decision 15 (Task 5) removed it: the coarse
            # button is now folded behind its own
            # "Replace the whole dashboard instead" summary, which carries
            # that distinction structurally instead of in a shared
            # sentence. Checked here in its place: the fold exists and
            # starts closed wherever a coarse button survives.
            reach = await page.js(
                "(() => { const d = " + PANEL + '.querySelector(".detail");'
                " if (!d) return null;"
                " const fold = d.querySelector('details.more');"
                " return {"
                '  putBack: d.querySelectorAll("[data-restore]").length,'
                '  setBack: d.querySelectorAll(".backto [data-state]").length,'
                "  foldSummary: fold"
                "    ? fold.querySelector('summary').textContent.trim() : null,"
                "  foldStartsClosed: fold ? !fold.open : null,"
                " }; })()"
            )
            for name, value in (reach or {}).items():
                print(f"    {name}: {value!r}")

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
            # Since decision 15, _renderSetBack folds its coarse buttons
            # behind <details class="more"> and can render none at all: the
            # "before" one disappears where the targeted undo already
            # reaches that state, and the "after" one where this row's own
            # state is already current. Row 0 - still expanded from the
            # section above - may or may not have one left, so later rows
            # are tried in turn until one does. A row's own async fetch
            # (deleted_since/explain/undo_change) renders the detail div at
            # once and fills in its buttons only once it resolves, so each
            # try waits for the busy indicator to clear rather than for the
            # div itself. Clicking an element inside a collapsed <details>
            # works regardless: .click() dispatches straight to the
            # handler and does not need the element to be visible.
            total_rows = await page.js(f'{PANEL}.querySelectorAll(".change").length')
            row = 0
            has_state_button = await page.js(f'!!{PANEL}.querySelector("[data-state]")')
            while not has_state_button and row + 1 < total_rows:
                row += 1
                await page.js(f'{PANEL}.querySelectorAll(".change")[{row}].click()')
                await page.settle(f'!{PANEL}.querySelector(".bar .muted")')
                has_state_button = await page.js(
                    f'!!{PANEL}.querySelector("[data-state]")'
                )
            if not has_state_button:
                print(
                    "    no row on this dashboard offers a coarse 'set back' "
                    "button any more - the targeted undo and the current "
                    "state cover everything, so there is nothing left to "
                    "open the confirm dialog with"
                )
            else:
                if row:
                    print(f"    row 0 offered none; row {row} does")
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
                print(
                    f"    diff present: {shape['diffPresent']}, "
                    f"collapsed: {shape['diffCollapsed']}"
                )
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
            #
            # A plain click toggles a row - clicking one already open
            # collapses it instead. The confirm-dialog section above tries
            # rows in order until one still offers a coarse button, since
            # decision 15, and can leave row 1 - not row 0 - open behind
            # it. Read `_open` first and click only when row 1 is not
            # already it, so this always opens rather than sometimes
            # closing.
            await page.js(
                "(() => { const p = " + ELEMENT + "; const rev = p._changes[1].revision;"
                " if (p._open !== rev) " + PANEL + '.querySelectorAll(".change")[1].click();'
                " })()"
            )
            await page.settle(f'!!{PANEL}.querySelectorAll(".detail")[0]')
            state = await page.js(
                "(() => { const d = " + PANEL + '.querySelector(".detail"); return {'
                # `?? null` on purpose: an undefined value is dropped from
                # the object by returnByValue, and the key vanishes with it.
                # `textContent`, not `innerText`: since decision 15 this
                # button can sit inside a closed <details class="more">,
                # and a closed <details> gives its non-summary content no
                # layout box at all - `innerText` answers "" for anything
                # with none, which read as "no label" where there truly
                # was one.
                '  button: d.querySelector("[data-state]")?.textContent.trim() ?? null,'
                '  reason: d.querySelector(".why")?.innerText.replace(/\\s+/g, " ").trim() ?? null,'
                " }; })()"
            )
            print(f"    button: {state['button']!r}")
            print(f"    reason: {state['reason']!r}")
            await page.shot("8-no-pointless-button.png")

            print("\n-- The button on the current state --")
            # Same toggle hazard as above, the other way round: row 0 was
            # the one left open until the section above switched to row 1,
            # so a plain click here normally opens it - but would collapse
            # it instead on a run where row 0 itself was the one still
            # carrying a coarse button. Idempotent for the same reason.
            await page.js(
                "(() => { const p = " + ELEMENT + "; const rev = p._changes[0].revision;"
                " if (p._open !== rev) " + PANEL + '.querySelectorAll(".change")[0].click();'
                " })()"
            )
            await page.settle(f'!!{PANEL}.querySelector(".current .detail")')
            # textContent, not innerText - same reason as above: this
            # button can sit inside the closed "Replace the whole
            # dashboard instead" fold.
            label = await page.js(
                f'{PANEL}.querySelector(".current .detail [data-state]")'
                "?.textContent.trim() ?? null"
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
                # Idempotent for the same reason as the two sections above:
                # row 0 is whatever the section before this one left open,
                # and if that happens to be the very row picked here, a
                # plain click would collapse it instead of opening it.
                await page.js(
                    "(() => { const p = " + ELEMENT + ";"
                    f" const rev = p._changes[{picked['index']}].revision;"
                    " if (p._open !== rev) " + PANEL
                    + f'.querySelectorAll(".change")[{picked["index"]}].click();'
                    " })()"
                )
                await page.settle(f'!!{PANEL}.querySelector(".detail .backto")')
                # textContent, not innerText: since decision 15 these
                # buttons sit inside the closed "Replace the whole
                # dashboard instead" fold, and a closed <details> gives its
                # non-summary content no layout box - innerText reads that
                # as "", which made every label below come back empty
                # while the aim itself was still exactly right.
                aim = await page.js(
                    "(() => { const b = [..." + PANEL
                    + '.querySelectorAll(".detail .backto button")];'
                    " return b.map(x => [x.textContent.trim(),"
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

            print("\n-- The sidebar: two groups folded away --")
            side = await page.js(
                "(() => { const p = " + PANEL + "; return {"
                '  live: p.querySelectorAll(".side > .dash").length,'
                '  fold: p.querySelector("details.dead summary")?.innerText ?? null,'
                '  foldedAway: p.querySelectorAll("details.dead .dash").length,'
                '  openByDefault: p.querySelector("details.dead")?.open ?? null,'
                '  apartFold: p.querySelector("details.apart summary")?.innerText ?? null,'
                '  apartAway: p.querySelectorAll("details.apart .dash").length,'
                " }; })()"
            )
            for name, value in side.items():
                print(f"    {name}: {value!r}")
            await page.shot("10-sidebar-folded.png")

            print("\n-- That order, against Home Assistant's own sidebar --")
            # The claim is that the list *is* the sidebar's order, and the
            # only place that can be checked is a browser holding both.
            # The panel rebuilds the order from `hass.panels` and this
            # user's frontend data; Home Assistant's `ha-sidebar` builds
            # it from the same two, with its own code. Agreeing here is
            # the whole feature; disagreeing is a defect the unit tests
            # cannot see, because they carry the copy of the rules that
            # would be wrong.
            order = await page.js(
                "(() => { const walk = (root, sel) => {"
                " const hit = root.querySelector(sel); if (hit) return hit;"
                " for (const n of root.querySelectorAll('*')) if (n.shadowRoot) {"
                " const f = walk(n.shadowRoot, sel); if (f) return f; }"
                " return null; };"
                " const bar = walk(document, 'ha-sidebar');"
                " const hrefs = bar"
                "   ? [...bar.shadowRoot.querySelectorAll('a[href^=\"/\"]')]"
                "       .map((a) => a.getAttribute('href').slice(1).split('/')[0])"
                "   : [];"
                " const p = " + PANEL + ";"
                " const path = (k) => (k === '_default' ? 'lovelace' : k);"
                " const listed = [...p.querySelectorAll('.side > .dash')]"
                "   .map((b) => path(b.dataset.key));"
                " const shown = hrefs.filter((h) => listed.includes(h));"
                " return { sidebar: shown, panel: listed,"
                "   agree: JSON.stringify(shown) === JSON.stringify(listed) };"
                " })()"
            )
            print(f"    sidebar: {order['sidebar']}")
            print(f"    panel:   {order['panel']}")
            print(f"    same order: {order['agree']}")

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

            print("\n-- The pen on a version section head --")
            # The other half of the rename, and the half with its own CSS
            # selector: the pen on a section head is revealed by
            # `details.ver > summary:hover .pen`, which is a different
            # rule from the one over a simple-mode row. A wrong selector
            # there leaves the pen permanently invisible in this mode -
            # present in the markup, passing every node test, and
            # unfindable on the screen.
            head_pen = await page.js(
                "(() => { const p = " + PANEL
                + '; const mark = p.querySelector("details.ver > summary [data-retitle]");'
                " if (!mark) return null;"
                ' const section = mark.closest("details.ver");'
                " const rect = mark.getBoundingClientRect();"
                " return {name: mark.dataset.retitle, open: section.open,"
                "         x: rect.x + rect.width / 2,"
                "         y: rect.y + rect.height / 2}; })()"
            )
            if not head_pen:
                print("    no version section carries a pen")
            else:
                print(f"    trying it on {head_pen['name']}")
                shown = await page.opacity_at(
                    head_pen["x"],
                    head_pen["y"],
                    "details.ver > summary [data-retitle]",
                )
                print(f"    pen opacity while hovering the head: {shown}")
                await page.shot("13b-version-head-pen.png")
                await page.click_at(head_pen["x"], head_pen["y"])
                asked = await page.settle(
                    f'!!{PANEL}.querySelector("dialog.retitle[open]")', 15
                )
                print(f"    the pen opens the rename dialog: {asked}")
                # The same collision as in the other mode: this pen sits
                # in a <summary> too, and a section folding shut on the
                # way to the dialog is what the two controls before it
                # both did.
                after = await page.js(
                    "(() => { const s = " + PANEL
                    + '.querySelector("details.ver > summary [data-retitle]")'
                    '?.closest("details.ver"); return s ? s.open : null; })()'
                )
                print(
                    f"    and leaves the section as it was: "
                    f"{after == head_pen['open']}"
                )
                await page.cancel_dialog()

            print("\n-- The bin on a version section head --")
            # The fourth place the comment in `style.js` warns about.
            # The reveal is a class on whatever holds the control, so a
            # new button that forgot to carry it is invisible while
            # passing every node test in `test_panel_behaviour.py` -
            # which is why this reads the computed opacity rather than
            # clicking and calling that proof.
            #
            # Found on *any* version, unlike the pen: `bin()` is offered
            # on a lightweight tag too, so a dashboard whose only version
            # somebody made by hand still exercises this.
            head_bin = await page.js(
                "(() => { const p = " + PANEL
                + '; const mark = p.querySelector('
                '"details.ver > summary [data-remove]");'
                " if (!mark) return null;"
                ' const section = mark.closest("details.ver");'
                " const rect = mark.getBoundingClientRect();"
                " return {name: mark.dataset.remove, open: section.open,"
                "         x: rect.x + rect.width / 2,"
                "         y: rect.y + rect.height / 2}; })()"
            )
            if not head_bin:
                print("    no version section carries a bin")
            else:
                print(f"    trying it on {head_bin['name']}")
                shown = await page.opacity_at(
                    head_bin["x"],
                    head_bin["y"],
                    "details.ver > summary [data-remove]",
                )
                print(f"    bin opacity while hovering the head: {shown}")
                await page.shot("13c-version-head-bin.png")
                await page.click_at(head_bin["x"], head_bin["y"])
                asked = await page.settle(
                    f'!!{PANEL}.querySelector("dialog.remove[open]")', 15
                )
                print(f"    the bin opens the removal dialog: {asked}")
                # The words come from the server. An empty body means the
                # preview never arrived - and that looks exactly like a
                # working dialog on a screenshot.
                said = await page.js(
                    "(() => { const d = " + PANEL
                    + '.querySelector("dialog.remove");'
                    ' return d ? d.querySelector(".body").textContent.trim()'
                    "        : null; })()"
                )
                print(f"    and it says something: {bool(said)}")
                # The same collision the pen beside it has: this sits in
                # a <summary>, and a summary toggles on any click it sees.
                after = await page.js(
                    "(() => { const s = " + PANEL
                    + '.querySelector("details.ver > summary [data-remove]")'
                    '?.closest("details.ver"); return s ? s.open : null; })()'
                )
                print(
                    f"    and leaves the section as it was: "
                    f"{after == head_bin['open']}"
                )
                # Cancelled, never confirmed - nothing on the bench is
                # written by a check that is only looking. The preview
                # alone writes nothing; `confirm` is what would.
                await page.cancel_dialog()

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
                await page.cancel_dialog("dialog.version", settle=0)

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
                await page.cancel_dialog("dialog.confirm", settle=0)

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

            print("\n-- Two kinds of button, told apart --")
            # The row the deletion section met had nothing missing, so
            # "Put back" was not on screen and there was nothing to tell
            # apart. Here both are put on one row on purpose: `_items` is
            # what the panel renders the offers from, and entry 1 is the
            # one that has a recorded state before it, so a "Back to"
            # button is offered beside them.
            #
            # Entry 2 was the first choice and produced nothing at all:
            # it is the oldest of the three, so `_before` finds nothing
            # and the detail takes its "first recorded state" branch,
            # which carries neither a list nor a button. Zeros that meant
            # "wrong row", not "missing feature".
            #
            # `_undo` reset to null, deliberately: it is filled in by a
            # real `undo_change` fetch that this synthetic setup never
            # makes, so it would otherwise still carry whatever a real
            # row on this instance answered earlier - and since decision
            # 15 (Task 5), `_renderSetBack` reads it to decide whether the
            # "before" button survives. Left stale, this section could
            # pass or fail depending on what ran before it rather than on
            # what it sets up. The old shared "Put back adds..." sentence
            # is gone with the same change; the fold's own summary now
            # carries that distinction, checked here in its place.
            told = await page.js(
                "(() => { const p = " + ELEMENT + ";"
                " p._items = [{position: 0, kind: 'card',"
                "              label: 'tile: demo', view: 'home'}];"
                " p._open = p._changes[1].revision;"
                " p._undo = null;"
                " p._render();"
                " const d = p.shadowRoot.querySelector('.detail');"
                " if (!d) return null;"
                " const fold = d.querySelector('details.more');"
                " return {"
                "   putBack: d.querySelectorAll('[data-restore]').length,"
                "   setBack: d.querySelectorAll('.backto [data-state]').length,"
                "   foldSummary: fold"
                "     ? fold.querySelector('summary').textContent.trim() : null,"
                " }; })()"
            )
            for name, value in (told or {}).items():
                print(f"    {name}: {value!r}")
            await page.shot("19-two-kinds-of-button.png")

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
                await page.cancel_dialog("dialog.version", settle=0.3)
            await page.shot("18-create-dialog-warns.png")

            print("\n-- The page hears about a change from elsewhere --")
            # The panel subscribes to the recorder's own event. Proving
            # that needs a change made *outside* the panel, so the page's
            # own `hass` connection saves a dashboard directly - the same
            # thing that happens when somebody edits in another tab.
            key = "dh-live-check"
            picked = await page.js(
                "(() => { const p = " + PANEL + ";"
                f' const b = [...p.querySelectorAll(".dash")].find(x => x.dataset.key === {json.dumps(key)});'
                " if (!b) return null; b.click(); return b.dataset.key; })()"
            )
            if not picked:
                print(f"    {key} is not in the list - run run_checks.py first")
            else:
                # Not `_selected` alone: it is assigned before the fetch
                # it starts, so waiting on it succeeded while `_changes`
                # still held the synthetic entries an earlier section put
                # there - and the "before" revision read back as
                # "aaaaaaa1111", which made the check below prove the
                # load rather than the live update. A real revision is
                # forty characters.
                await page.settle(
                    f"{ELEMENT}._selected === {json.dumps(key)}"
                    f" && ({ELEMENT}._changes[0]?.revision || '').length === 40"
                )
                before = await page.js(f"{ELEMENT}._changes[0]?.revision ?? null")
                print(f"    newest before: {before and before[:7]}")
                # Started, not awaited: page.js evaluates with
                # awaitPromise, and this promise settles long before the
                # recorder does. The wait belongs in settle() below.
                await page.js(
                    "(() => { const p = " + ELEMENT + ";"
                    " p.hass.callWS({type: 'lovelace/config/save',"
                    f"   url_path: {json.dumps(key)},"
                    "    config: {views: [{path: 'p', title: 'P', cards: ["
                    "      {type: 'markdown', content: 'from elsewhere ' + Date.now()}"
                    "    ]}]}});"
                    " return true; })()"
                )
                moved = await page.settle(
                    f"{ELEMENT}._changes[0] && {ELEMENT}._changes[0].revision !== "
                    f"{json.dumps(before)}",
                    15,
                )
                after = await page.js(f"{ELEMENT}._changes[0]?.revision ?? null")
                print(f"    newest after : {after and after[:7]}")
                print(f"    refreshed without a reload: {moved}")
                crowned = await page.js(
                    f'!!{PANEL}.querySelector(".current .chip.now")'
                )
                # The whole point: not merely refreshed, but refreshed
                # late enough that the newest entry matches the live
                # configuration and is crowned.
                print(f"    and the newest entry is crowned: {crowned}")
                await page.shot("20-live-update.png")

            print("\n-- The reload button --")
            shape = await page.js(
                "(() => { const b = " + PANEL + '.querySelector(".bar [data-refresh]");'
                # Measured, not read off the declaration: getComputedStyle
                # resolves `margin-left: auto` into the pixels it worked
                # out, so comparing it against "auto" can never be true.
                # Where the button sits is the question anyway.
                " const bar = " + PANEL + '.querySelector(".bar");'
                " if (!b || !bar) return null;"
                " const at = b.getBoundingClientRect();"
                " const row = bar.getBoundingClientRect();"
                " return {label: b.textContent.trim(), title: b.title,"
                "         pixelsFromRightEdge: Math.round(row.right - at.right)};"
                " })()"
            )
            print(f"    {shape}")
            if shape:
                await page.js(
                    f'{PANEL}.querySelector(".bar [data-refresh]").click()'
                )
                await asyncio.sleep(1.5)
                alive = await page.js(
                    f'{PANEL}.querySelectorAll(".change").length'
                )
                print(f"    rows after pressing it: {alive}")

            print("\n-- The simple mode: the row is the way in --")
            # The mode is set rather than clicked for: which way the bar
            # button points depends on what this profile last stored, and
            # a check that only runs half the time is worse than none.
            await page.js(f'{ELEMENT}._setMode("simple")')
            listed = await page.settle(
                f'{PANEL}.querySelectorAll("details.vrow").length'
            )
            print(f"    rows that open: {listed}")
            if listed:
                # A row that has both: something to open, and a button to
                # go back with. Those are the two things that collide.
                where = await page.js(
                    "(() => { const rows = [..." + PANEL
                    + '.querySelectorAll("details.vrow")];'
                    ' const row = rows.find((r) => r.querySelector("[data-state]"));'
                    " if (!row) return null;"
                    ' const head = row.querySelector(".vhead")'
                    ".getBoundingClientRect();"
                    ' const button = row.querySelector("[data-state]")'
                    ".getBoundingClientRect();"
                    " return {key: row.dataset.key,"
                    "         headX: head.x + 60, headY: head.y + head.height / 2,"
                    "         buttonX: button.x + button.width / 2,"
                    "         buttonY: button.y + button.height / 2}; })()"
                )
                print(f"    trying it on {where and where['key']}")
            else:
                where = None
            if where:
                state = (
                    "(() => { const r = " + PANEL
                    + ".querySelector('details.vrow[data-key=\"'"
                    + f" + {json.dumps(where['key'])} + '\"]');"
                    " return r ? r.open : null; })()"
                )
                await page.click_at(where["headX"], where["headY"])
                await asyncio.sleep(0.4)
                print(f"    a click on the row opens it: {await page.js(state)}")
                await page.click_at(where["headX"], where["headY"])
                await asyncio.sleep(0.4)
                print(f"    and a second click shuts it: {not await page.js(state)}")
                await page.shot("21-simple-row.png")

                # The collision this section exists for. A button inside a
                # <summary> toggles it as well unless the click is stopped,
                # and the row would fold up under the hand that clicked -
                # the same fault the pencil had in the advanced mode.
                await page.click_at(where["headX"], where["headY"])
                await asyncio.sleep(0.4)
                await page.click_at(where["buttonX"], where["buttonY"])
                asked = await page.settle(f'!!{PANEL}.querySelector("dialog[open]")', 15)
                print(f"    the button opens the dialog: {asked}")
                print(f"    and leaves the row open: {await page.js(state)}")
                await page.shot("22-simple-row-and-dialog.png")
                # Cancelled, always. Nothing on the bench is written by a
                # check that is only looking.
                await page.js(
                    "(() => { const d = " + PANEL + '.querySelector("dialog[open]");'
                    ' if (d) d.querySelector(".actions [value=\'cancel\']").click();'
                    " return true; })()"
                )
                await asyncio.sleep(0.5)
            print("\n-- The simple mode: renaming a version from its row --")
            # The third control that sits inside a <summary>, and the one
            # with the least reason to be trusted: it was added last, and
            # the two before it both folded the row up under the hand
            # that clicked before they were stopped from doing so. Clicked
            # by coordinates rather than with .click(), because only a
            # real click carries the summary's own default behaviour with
            # it - .click() on the button would pass whether or not the
            # collision is handled.
            #
            # The pen is drawn on hover, so the click has to land on it
            # while the pointer is over the row. A click at a point does
            # both: Chrome moves the pointer there first.
            pen = await page.js(
                "(() => { const row = " + PANEL
                + '.querySelector("details.vrow [data-retitle]")?.closest(".vrow");'
                " if (!row) return null;"
                ' const head = row.querySelector(".vhead").getBoundingClientRect();'
                ' const mark = row.querySelector("[data-retitle]");'
                " const rect = mark.getBoundingClientRect();"
                " return {key: row.dataset.key, name: mark.dataset.retitle,"
                "         headX: head.x + 60, headY: head.y + head.height / 2,"
                "         penX: rect.x + rect.width / 2,"
                "         penY: rect.y + rect.height / 2,"
                "         title: row.querySelector('.grow')?.textContent.trim()"
                "}; })()"
            )
            if not pen:
                # Every version on this dashboard was made by hand, or
                # there are none. Said rather than passed over.
                print("    no version row offers a pen")
            else:
                print(f"    trying it on {pen['name']}")
                open_state = (
                    "(() => { const r = " + PANEL
                    + ".querySelector('details.vrow[data-key=\"'"
                    + f" + {json.dumps(pen['key'])} + '\"]');"
                    " return r ? r.open : null; })()"
                )
                # Opened only if it is shut, and read rather than assumed.
                # The block above leaves this same row open, so a click
                # here on principle shut it - and the whole point below is
                # whether the pen leaves an *open* row open. Measured
                # 2026-09-08: the first run of this reported "leaves the
                # row open: False" and proved nothing, because there was
                # nothing open to leave.
                if not await page.js(open_state):
                    await page.click_at(pen["headX"], pen["headY"])
                    await asyncio.sleep(0.4)
                standing = await page.js(open_state)
                print(f"    the row is open before the pen: {standing}")
                shown = await page.opacity_at(
                    pen["penX"], pen["penY"], "details.vrow [data-retitle]"
                )
                print(f"    pen opacity while hovering the row: {shown}")
                await page.click_at(pen["penX"], pen["penY"])
                asked = await page.settle(
                    f'!!{PANEL}.querySelector("dialog.retitle[open]")', 15
                )
                print(f"    the pen opens the rename dialog: {asked}")
                # The collision. The pen sits inside a <summary>, and a
                # summary toggles on any click it sees; two controls
                # before this one folded the row up under the hand that
                # clicked before they were stopped from doing so.
                still = await page.js(open_state)
                print(f"    and leaves the row as it was: {still == standing}")
                filled = await page.js(
                    "(() => { const d = " + PANEL
                    + '.querySelector("dialog.retitle");'
                    " if (!d) return null; return {"
                    '  which: d.querySelector("[data-which]").textContent,'
                    '  title: d.querySelector("input.title").value,'
                    '  desc: d.querySelector("input.desc").value,'
                    " }; })()"
                )
                print(f"    it names the version: {filled and filled['which']!r}")
                print(f"    the title arrives prefilled: {filled and filled['title']!r}")
                same = bool(filled) and filled["title"] == (pen["title"] or "").split(
                    "saved automatically"
                )[0].strip()
                print(f"    and it is the one on the row: {same}")
                await page.shot("26-simple-rename-dialog.png")
                await page.cancel_dialog()

            print("\n-- The simple mode: the current state is a way in too --")
            badge = await page.js(f'!!{PANEL}.querySelector(".standing .chip.now")')
            print(f"    the box carries the badge: {badge}")
            box = await page.js(
                "(() => { const b = " + PANEL
                + '.querySelector("details.standing");'
                " if (!b) return null;"
                ' const head = b.querySelector(".heading").getBoundingClientRect();'
                ' const save = b.querySelector("[data-version]")'
                ".getBoundingClientRect();"
                ' const back = b.querySelector("[data-state]");'
                " const rect = back && back.getBoundingClientRect();"
                " return {headX: head.x + 40, headY: head.y + head.height / 2,"
                "         saveX: save.x + save.width / 2,"
                "         saveY: save.y + save.height / 2,"
                "         backX: rect ? rect.x + rect.width / 2 : null,"
                "         backY: rect ? rect.y + rect.height / 2 : null,"
                # textContent, never innerText: the box is still shut at
                # this point, and innerText is worked out from the layout -
                # so a hidden line reads as the empty string and the check
                # reports a heading that is plainly there as missing.
                "         says: b.querySelector('.stephead')"
                "?.textContent.trim() ?? null}; })()"
            )
            if not box:
                # Nothing recorded since the last version, so by design it
                # does not open onto anything. Said rather than passed
                # over: a check that reports nothing when it found nothing
                # to check is how this file stops meaning anything.
                flat = await page.js(f'!!{PANEL}.querySelector("div.standing")')
                print(f"    nothing recorded since the last version: {flat}")
            else:
                opened = (
                    "(() => { const b = " + PANEL
                    + '.querySelector("details.standing");'
                    " return b ? b.open : null; })()"
                )
                print(f"    it folds: {box['says']!r}")
                await page.click_at(box["headX"], box["headY"])
                await asyncio.sleep(0.4)
                print(f"    a click on the head opens it: {await page.js(opened)}")
                await page.shot("23-simple-current-state.png")
                # The collision, and this block has it twice: both buttons
                # sit inside the <summary>, and a summary toggles on a
                # click it was never meant to see. Stopping the propagation
                # is not enough - the toggle is its default behaviour, not
                # a listener, so only preventDefault reaches it.
                await page.click_at(box["saveX"], box["saveY"])
                asked = await page.settle(f'!!{PANEL}.querySelector("dialog[open]")', 15)
                print(f"    saving a version opens its dialog: {asked}")
                print(f"    and leaves the box open: {await page.js(opened)}")
                await page.shot("24-simple-save-keeps-it-open.png")
                await page.cancel_dialog()
                if box["backX"] is None:
                    print("    the dashboard is in a version's state, so no way back")
                else:
                    await page.click_at(box["backX"], box["backY"])
                    asked = await page.settle(
                        f'!!{PANEL}.querySelector("dialog[open]")', 15
                    )
                    print(f"    the way back opens its preview: {asked}")
                    print(f"    and leaves the box open: {await page.js(opened)}")
                    await page.shot("25-simple-way-back-dialog.png")
                    # Cancelled, always. Nothing on the bench is written by
                    # a check that is only looking.
                    await page.cancel_dialog()

            # Left as it was found: the mode is stored per browser, and a
            # check that changes what somebody sees next time is a check
            # with a side effect.
            await page.js(f'{ELEMENT}._setMode("advanced")')

            print("\nconsole:", page.console or "no errors, no warnings")
    finally:
        chrome.terminate()


asyncio.run(main())
