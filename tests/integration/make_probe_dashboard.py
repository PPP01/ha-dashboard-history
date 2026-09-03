#!/usr/bin/env python3
"""Build a dashboard that exercises the card-matching rules by hand.

The rules this checks are decided in `analyze.py` and covered by pytest,
but the thing being judged is what a *person* reads in the history after
dragging a card around. That judgement needs a dashboard whose cards say
which case they belong to, on an instance nobody minds being edited.

Run it against the throwaway Home Assistant, never against a real one:

    docker compose -f docker/compose.yaml up -d
    python3 tests/integration/make_probe_dashboard.py

It is safe to run twice. An existing dashboard under this exact
url_path - never a prefix of it, because a prefix match in this
directory once swept up a dashboard somebody was working in - keeps its
registry entry and its recorded history, and only its configuration is
overwritten. The first version of this script deleted and recreated it
instead, which threw away nothing recoverable but did produce a
deletion the recorder never saw: Home Assistant collapses a delete and
a recreate inside the ten-second debounce into one save, so the history
read "3 removed, 13 added" where two dashboards had in fact met. That
is a finding of its own, recorded in the design record; there is no
reason for this script to demonstrate it every time it runs.
"""

from __future__ import annotations

import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from run_checks import BASE, Socket, token  # noqa: E402

KEY = "dh-probe"
TITLE = "Änderungs-Erkennung"

# sun.sun exists on every Home Assistant, so the twin cards render
# without anybody having to own a particular device.
TWIN = "sun.sun"


def _heading(text: str) -> dict:
    return {"type": "heading", "heading": text}


def _note(title: str, body: str) -> dict:
    return {"type": "markdown", "content": f"## {title}\n{body}"}


CONFIG = {
    "views": [
        {
            "title": "Ansicht A",
            "path": "a",
            "type": "sections",
            "sections": [
                {
                    "type": "grid",
                    "cards": [
                        _heading("Abschnitt Links"),
                        _note(
                            "① Zwischen Ansichten",
                            "Zieh diese Karte nach **Ansicht B**. Danach darf "
                            "der Verlauf keine Löschung anbieten.",
                        ),
                        _note(
                            "② Zwischen Abschnitten",
                            "Zieh diese Karte nach **Abschnitt Rechts** - "
                            "gleiche Ansicht, anderer Abschnitt.",
                        ),
                        _note(
                            "③ Wirklich löschen",
                            "Lösch diese Karte. Sie *muss* zum Zurückholen "
                            "angeboten werden - das ist die Gegenprobe.",
                        ),
                    ],
                },
                {
                    "type": "grid",
                    "cards": [_heading("Abschnitt Rechts"), _note("Ziel für ②", "")],
                },
            ],
        },
        {
            "title": "Ansicht B",
            "path": "b",
            "type": "sections",
            "sections": [
                {
                    "type": "grid",
                    "cards": [_heading("Ziel für ①"), _note("Hier landet ①", "")],
                },
                {
                    "type": "grid",
                    "cards": [
                        _heading("④ Zwillinge"),
                        # Same type, same entity: one weak key for both. The
                        # old matching took the first hit and married the
                        # deleted card to the survivor.
                        {
                            "type": "tile",
                            "entity": TWIN,
                            "name": "Zwilling A",
                            "color": "blue",
                        },
                        {
                            "type": "tile",
                            "entity": TWIN,
                            "name": "Zwilling B",
                            "color": "red",
                        },
                    ],
                },
                {
                    "type": "grid",
                    "cards": [
                        _heading("⑤ Karte ohne Merkmal"),
                        # No entity, title, name, heading, entity list, text
                        # or nameable inner card - so nothing recognises it
                        # across two states. This is the named limit.
                        {
                            "type": "iframe",
                            "url": "https://www.home-assistant.io/",
                            "aspect_ratio": "60%",
                        },
                    ],
                },
            ],
        },
    ]
}


async def main() -> None:
    access = token()
    async with Socket(access) as socket:
        listed = (await socket.call("lovelace/dashboards/list")) or []
        # The exact key, never a prefix.
        found = any(entry.get("url_path") == KEY for entry in listed)
        if found:
            print(f"  {KEY} gibt es schon - nur die Konfiguration wird ersetzt")
        else:
            await socket.call(
                "lovelace/dashboards/create",
                url_path=KEY,
                title=TITLE,
                icon="mdi:test-tube",
                show_in_sidebar=True,
                require_admin=False,
            )
            print(f"  {KEY} angelegt")
        await socket.call("lovelace/config/save", url_path=KEY, config=CONFIG)
    cards = sum(
        len(section["cards"])
        for view in CONFIG["views"]
        for section in view["sections"]
    )
    print(f"  {TITLE}: {len(CONFIG['views'])} Ansichten, {cards} Karten")
    print(f"  {BASE}/{KEY}")


if __name__ == "__main__":
    asyncio.run(main())
