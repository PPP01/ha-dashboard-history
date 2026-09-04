# Vorhaben G — Versionen, die halten (Backend)

> **Für agentische Ausführung:** ERFORDERLICHER SUB-SKILL: `superpowers:subagent-driven-development` (empfohlen) oder `superpowers:executing-plans`, Aufgabe für Aufgabe. Die Schritte tragen Checkboxen (`- [ ]`) zum Mitführen.

**Ziel:** Eine Version verschwindet nicht mehr, nur weil ihr Commit aus dem Anzeigefenster gerutscht ist — und die Historie lässt sich über einen Commit-Zeiger weiterblättern statt über eine Zahl.

**Architektur:** Drei voneinander unabhängige Ergänzungen an der Leseseite. Der Store lernt einen Startpunkt für den Verlauf (dulwich `get_walker(include=…)`), `operations` reicht ihn durch und sagt, ob es weitergeht, und die Übereinstimmung mit dem Live-Stand wird gegen **alle** Versionen geprüft statt gegen die zufällig geladenen. Geschrieben wird nichts; jede Aufgabe fügt Antwortfelder hinzu, keine ändert bestehende.

**Technik:** Python 3.12 (Entwicklung) / 3.14 (Container), dulwich 1.2.14, pytest, Home Assistant 2026.8.3.

**Spec:** `docs/superpowers/specs/2026-08-30-dashboard-history-design.md` — Vorhaben G und Entscheidung 17. Der Befund dazu steht als offener Punkt (»Eine Version außerhalb der neuesten 50 Änderungen wird unsichtbar«).

## Globale Randbedingungen

Aus der Spec, für **jede** Aufgabe verbindlich:

- **Kein Systemaufruf von `git`.** Ausschließlich `dulwich`.
- **Keine Home-Assistant-Interna abfangen oder ersetzen.** Kein Monkey-Patching.
- **`yaml_io.py`, `analyze.py`, `restore.py`, `versions.py` bleiben Home-Assistant-frei.** Der Kern von `store.py` ebenfalls: kein `import homeassistant`.
- **Blockierende Arbeit gehört in einen Executor** (`hass.async_add_executor_job`). Jeder git-Zugriff ist blockierend.
- **Nichts blockiert den Start von Home Assistant.**
- **Commit-Botschaften auf Englisch**, Subject im Imperativ, erster Buchstabe groß, max. 50 Zeichen, Leerzeile, Body max. 72 Zeichen pro Zeile mit dem *Warum*, Abschluss `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- **Die Oberfläche wird hier nicht angefasst.** Register, Suchfeld und »Ältere laden« gehören zu Vorhaben H, das `panel.js` ohnehin neu ordnet. Wer hier am Panel arbeitet, baut es zweimal.

**Tests:** `python3 -m pytest tests/ -v` — muss durchgehend grün bleiben (Ausgangsstand: 260 bestanden).

---

### Aufgabe 1: Ein Startpunkt für den Verlauf

**Dateien:**
- Ändern: `custom_components/dashboard_history/store.py` (`list_changes`)
- Test: `tests/test_store.py`

**Schnittstellen:**
- Liefert: `HistoryStore.list_changes(key: str, limit: int | None = 50, before: str | None = None) -> list[Change]`. Mit `before` beginnt die Liste bei der Änderung, die **älter** ist als die genannte Revision; die Revision selbst kommt nicht vor. Eine unbekannte Revision ergibt eine leere Liste.

**Verifiziert am 2026-09-04**, damit niemand es erneut ausprobieren muss: `repo.get_walker(include=[<sha als bytes>], paths=[…], max_entries=n + 1)` liefert den genannten Commit **und** seine n Vorgänger, in dieser Reihenfolge. Der erste Eintrag ist also wegzuwerfen. `include` verlangt den vollen Hash als **Bytes**; ein `str` wirft `ChecksumMismatch` mit einer Meldung, die zweimal denselben Hash nennt. `HistoryStore._resolve` gibt einen **`str`** zurück (`return _as_text(obj.id)`, store.py) — dahinter gehört also ein `.encode()`. Beides am 2026-09-04 nachgesehen, nicht vermutet.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

In `tests/test_store.py` ans Ende anfügen:

```python
def test_history_can_start_at_an_older_revision(store):
    """Blättern heißt: ab hier weiter, nicht ab Position n."""
    revisions = [
        store.write_snapshot("home", f"a: {i}\n", f"home: change {i}")
        for i in range(6)
    ]
    # revisions[0] ist die älteste. Ab der viertältesten weiterblättern:
    older = store.list_changes("home", limit=2, before=revisions[3])
    assert [c.revision for c in older] == [revisions[2], revisions[1]]


def test_the_cursor_itself_is_not_repeated(store):
    """Sonst stünde jede Seite mit dem Ende der vorigen im Panel."""
    revisions = [
        store.write_snapshot("home", f"a: {i}\n", f"home: change {i}")
        for i in range(4)
    ]
    older = store.list_changes("home", limit=10, before=revisions[2])
    assert revisions[2] not in [c.revision for c in older]


def test_an_unknown_cursor_yields_nothing(store):
    """Fragen kostet nichts - eine Revision, die es nicht gibt, ist kein Fehler."""
    store.write_snapshot("home", "a: 1\n", "home: first")
    assert store.list_changes("home", before="f" * 40) == []


def test_history_without_a_cursor_is_unchanged(store):
    """Die Regression, die zählt: der bisherige Aufruf bleibt, wie er war."""
    store.write_snapshot("home", "a: 1\n", "home: first")
    store.write_snapshot("home", "a: 2\n", "home: second")
    assert [c.message for c in store.list_changes("home")] == [
        "home: second",
        "home: first",
    ]
```

- [ ] **Schritt 2: Laufen lassen, Fehlschlag prüfen**

```bash
python3 -m pytest tests/test_store.py -k "cursor or older_revision" -v
```

Erwartet: `TypeError: list_changes() got an unexpected keyword argument 'before'` bei den ersten drei, der vierte besteht bereits.

- [ ] **Schritt 3: Umsetzen**

In `store.py`, `list_changes` ersetzen:

```python
    def list_changes(
        self, key: str, limit: int | None = 50, before: str | None = None
    ) -> list[Change]:
        """Every recorded state of one dashboard, newest first.

        `limit=None` walks the whole history. `before` starts the walk one
        step past that revision - the entry it names is not repeated, so a
        caller can page without stitching duplicates together. A cursor
        rather than an offset because an offset drifts: save while somebody
        is paging and every later page shifts by one.

        An unknown `before` yields nothing. Asking about a revision that is
        gone is not an error - `matching_revisions` takes the same line.
        """
        repo = self._repo()
        if repo is None:
            return []
        notes = self.descriptions()
        # Both paths: a rename touches only the metadata, and a change
        # that is recorded but never shown is the worst of both.
        paths = [f"{key}.yaml".encode(), f"meta/{key}.yaml".encode()]
        walk: dict = {"paths": paths}
        drop_first = False
        if before is not None:
            resolved = self._resolve(repo, before)
            if resolved is None:
                return []
            # `include` walks *from* that commit, so it hands back the
            # commit itself first. Ask for one more and drop it.
            walk["include"] = [resolved.encode()]
            drop_first = True
        if limit is not None:
            walk["max_entries"] = limit + 1 if drop_first else limit
        try:
            entries = list(repo.get_walker(**walk))
        except KeyError:
            # No HEAD yet: an empty repository has no history to walk.
            return []
        if drop_first:
            entries = entries[1:]
        return [
            Change(
                revision=_as_text(entry.commit.id),
                timestamp=entry.commit.commit_time,
                message=entry.commit.message.decode("utf-8").strip(),
                description=notes.get(_as_text(entry.commit.id), ""),
            )
            for entry in entries
        ]
```

`_resolve` löst dabei mehr als nur volle Hashes auf: abgekürzte Präfixe ab vier Zeichen und Versionsnamen wie `home/v1.0.0` ebenso. Ein Zeiger aus dem Panel wird immer ein voller Hash sein, aber ein Dienstaufruf von Hand muss deshalb nicht scheitern.

- [ ] **Schritt 4: Laufen lassen, Erfolg prüfen**

```bash
python3 -m pytest tests/test_store.py -v
python3 -m pytest tests/ -q
```

Erwartet: alle grün, 264 bestanden.

- [ ] **Schritt 5: Committen**

```bash
git add custom_components/dashboard_history/store.py tests/test_store.py
git commit -m "$(cat <<'EOF'
Let the history start at a revision, not an offset

Paging by number drifts: save something while somebody is reading page
two, and every later page shifts by one entry - one change seen twice,
another never. A commit is a fixed point, so the walk starts there.

dulwich hands the named commit back first, which is why one extra entry
is asked for and the first is dropped. Verified against 1.2.14 rather
than assumed; `include` also insists on bytes and answers a str with a
checksum mismatch that names the same hash twice.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Aufgabe 2: Die Blätterung bis zum WebSocket-Befehl

**Dateien:**
- Ändern: `custom_components/dashboard_history/operations.py` (`async_history`)
- Ändern: `custom_components/dashboard_history/websocket_api.py` (Befehl `dashboard_history/history`)
- Test: `tests/integration/run_checks.py` (neue Prüfung `run_paging`)

**Schnittstellen:**
- Verbraucht: `HistoryStore.list_changes(key, limit, before)` aus Aufgabe 1.
- Liefert: `async_history(hass, store, key, limit=50, before=None) -> dict` mit dem zusätzlichen Feld `next_cursor: str | None`. `None` heißt: Es gibt nichts Älteres mehr. Der WebSocket-Befehl nimmt `before` als optionales Feld entgegen.

**Der Vorgabewert bleibt 50, nicht 25.** Issue 1 nennt 25 für die erste Seite, aber die Schaltfläche »Ältere laden« entsteht erst in Vorhaben H. Ihn jetzt zu senken hieße, dem Panel dreißig Änderungen wegzunehmen und keinen Weg zu geben, sie zu holen. Vorhaben H setzt ihn, wenn die Oberfläche ihn tragen kann.

- [ ] **Schritt 1: Die fehlschlagende Prüfung schreiben**

In `tests/integration/run_checks.py` vor `async def run_live_updates` einfügen:

```python
async def run_paging(access: str) -> None:
    """Weiterblättern über einen Commit-Zeiger.

    Nicht in pytest zu erreichen: `async_history` importiert Home
    Assistant. Und die Frage, um die es geht, stellt sich erst an einer
    Historie mit mehr Einträgen als einer Seite.
    """
    key = "dh-paging-check"

    async def save(socket, index: int):
        seen = (await socket.call("dashboard_history/history", dashboard=key))["changes"]
        await socket.call(
            "lovelace/config/save",
            url_path=key,
            config={"views": [{"path": "p", "title": f"Stand {index}", "cards": []}]},
        )
        await _wait_for_history_to_move(
            socket, key, seen[0]["revision"] if seen else "", RECORDING_WAIT
        )

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
            len(first["changes"]) == 2 and first.get("next_cursor"),
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
```

Und in `main` hinter dem Undo-Block registrieren:

```python
    print("\n  -- Blaettern statt abschneiden --")
    asyncio.run(run_paging(access))
```

- [ ] **Schritt 2: Laufen lassen, Fehlschlag prüfen**

```bash
python3 -c "
import asyncio, sys, pathlib
sys.path.insert(0, str(pathlib.Path('tests/integration').resolve()))
import run_checks as rc
asyncio.run(rc.run_paging(rc.token()))
"
```

Erwartet: Die erste Prüfung schlägt fehl, weil `next_cursor` nicht existiert; die zweite, weil `before` als Feld abgelehnt wird (`extra keys not allowed`).

- [ ] **Schritt 3: Umsetzen**

In `operations.py` die Signatur und den Abschluss von `async_history` ändern:

```python
async def async_history(
    hass: HomeAssistant,
    store: HistoryStore,
    key: str,
    limit: int = 50,
    before: str | None = None,
) -> dict:
```

Den `store.list_changes`-Aufruf ersetzen — eine Änderung mehr anfordern, als geliefert wird, denn nur so ist zu erkennen, ob es weitergeht:

```python
    # Eine mehr als verlangt: ihr Vorhandensein ist die Antwort auf
    # "gibt es noch ältere?", und sie kostet einen Commit statt einer
    # zweiten Abfrage.
    changes, versions = await asyncio.gather(
        hass.async_add_executor_job(store.list_changes, key, limit + 1, before),
        hass.async_add_executor_job(store.list_versions, key),
    )
    more = len(changes) > limit
    changes = changes[:limit]
```

Und den `return` ersetzen — die gerenderte Liste wird vorher gebaut, damit der Zeiger aus ihr stammen kann:

```python
    rendered = [
        {
            "revision": c.revision,
            "timestamp": c.timestamp,
            "message": c.message,
            "description": c.description,
            "same_as_now": c.revision in same,
            "versions": marks.get(c.revision, []),
        }
        for c in changes
    ]
    return {
        "changes": rendered,
        # Der Zeiger für die nächste Seite: die älteste gelieferte
        # Änderung. None heißt, dass es keine älteren gibt - das Panel
        # lässt die Schaltfläche dann weg, statt eine leere Seite zu holen.
        "next_cursor": rendered[-1]["revision"] if more and rendered else None,
    }
```

In `websocket_api.py` das Schema des Befehls erweitern:

```python
    _command(
        f"{DOMAIN}/history",
        {
            **_DASHBOARD,
            vol.Optional("limit", default=50): int,
            vol.Optional("before"): vol.Any(None, str),
        },
        operations.async_history,
        lambda msg: {
            "key": msg["dashboard"],
            "limit": msg["limit"],
            "before": msg.get("before"),
        },
    ),
```

- [ ] **Schritt 4: Laufen lassen, Erfolg prüfen**

```bash
docker compose -f docker/compose.yaml restart homeassistant
python3 -m pytest tests/ -q
python3 tests/integration/run_checks.py
```

Erwartet: pytest grün, alle Integrationsprüfungen bestanden, die drei neuen darunter.

- [ ] **Schritt 5: Committen**

```bash
git add custom_components/dashboard_history/operations.py \
        custom_components/dashboard_history/websocket_api.py \
        tests/integration/run_checks.py
git commit -m "$(cat <<'EOF'
Hand out a cursor to the next page of history

The panel has no way to ask for more, and no way to know whether more
exists. One extra change is fetched and dropped again: its presence is
the answer, and it costs a commit rather than a second query.

The default stays at 50. Issue 1 asks for 25 on the first page, but the
button that fetches the rest belongs to project H - lowering it now
would take thirty changes off the panel and offer nothing to get them
back with.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Aufgabe 3: Übereinstimmende Versionen, unabhängig vom Fenster

**Dateien:**
- Ändern: `custom_components/dashboard_history/operations.py` (`async_history`, `_same_as_live`)
- Test: `tests/integration/run_checks.py` (`run_paging` erweitern)

**Schnittstellen:**
- Verbraucht: `HistoryStore.matching_revisions(key, revisions, text) -> set[str]` (existiert bereits).
- Liefert: `async_history` antwortet zusätzlich mit `matching_versions: list[dict]` — jede Version, deren markierter Stand byteweise dem Live-Dashboard entspricht, mit `name`, `title` und `revision`. Unabhängig davon, ob ihr Commit im geladenen Fenster liegt.

Das ist der eigentliche Befund hinter Vorhaben G: Heute wird die Übereinstimmung nur für die geladenen Änderungen berechnet, und das Panel liest die Plakette aus `change.versions`. Fällt der Commit aus dem Fenster, verschwindet die Plakette — obwohl der Stand identisch ist.

- [ ] **Schritt 1: Die fehlschlagende Prüfung schreiben**

Ans Ende von `run_paging` anfügen:

```python
        # Die Plakette darf nicht daran hängen, wie weit geblättert wurde.
        oldest = (
            await socket.call("dashboard_history/history", dashboard=key, limit=1000)
        )["changes"][-1]["revision"]
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
```

- [ ] **Schritt 2: Laufen lassen, Fehlschlag prüfen**

```bash
python3 -c "
import asyncio, sys, pathlib
sys.path.insert(0, str(pathlib.Path('tests/integration').resolve()))
import run_checks as rc
asyncio.run(rc.run_paging(rc.token()))
"
```

Erwartet: `matching=[]`, weil `matching_versions` noch nicht existiert.

- [ ] **Schritt 3: Umsetzen**

In `operations.py` den Übereinstimmungs-Block von `async_history` ersetzen:

```python
    live = await async_get_config(hass, key)
    same: set[str] = set()
    if live is not None:
        # Änderungen *und* Versionen in einem Durchgang: der Vergleich
        # geht über die Blob-Kennung, ein zweiter Aufruf würde dasselbe
        # Repository ein zweites Mal öffnen. Die Versionen kommen dazu,
        # weil die Plakette sonst daran hinge, wie weit jemand geblättert
        # hat - der Befund, für den es dieses Vorhaben gibt.
        wanted = [c.revision for c in changes] + [v.revision for v in versions]
        if wanted:
            same = await hass.async_add_executor_job(
                _same_as_live, store, key, wanted, live
            )
```

Und vor dem `return` die Liste bilden:

```python
    matching_versions = [
        {"name": v.name, "title": v.title, "revision": v.revision}
        for v in versions
        if v.revision in same
    ]
```

Im `return` ergänzen:

```python
        "matching_versions": matching_versions,
```

`_same_as_live` bleibt unverändert — es nimmt bereits eine beliebige Liste entgegen.

- [ ] **Schritt 4: Laufen lassen, Erfolg prüfen**

```bash
docker compose -f docker/compose.yaml restart homeassistant
python3 -m pytest tests/ -q
python3 tests/integration/run_checks.py
```

Erwartet: alles grün, die neue Prüfung darunter.

- [ ] **Schritt 5: Committen**

```bash
git add custom_components/dashboard_history/operations.py tests/integration/run_checks.py
git commit -m "$(cat <<'EOF'
Report a matching version from outside the window

The "same state as v1.0.0" badge was decided from the changes that
happened to be loaded. Tag an old state, save fifty times, and the badge
went away while the dashboard was still byte-identical to it - a mark
that disappears is not a mark.

Versions are now compared alongside the changes, in the same pass over
the repository. It costs nothing extra: the comparison is by blob id,
and the second list simply joins the first.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Aufgabe 4: Alle Versionen eines Dashboards als eigene Abfrage

**Dateien:**
- Ändern: `custom_components/dashboard_history/operations.py` (neu: `async_versions`)
- Ändern: `custom_components/dashboard_history/websocket_api.py` (neuer Befehl)
- Test: `tests/integration/run_checks.py` (`run_paging` erweitern)

**Schnittstellen:**
- Verbraucht: `HistoryStore.list_versions(key) -> list[Version]`, `versions.parse(key, name) -> tuple[int, int, int] | None`.
- Liefert: `async_versions(hass, store, key) -> dict` mit `versions: list[dict]` — `name`, `title`, `description`, `revision`, `same_as_now`. Sortiert nach Versionsnummer absteigend; Namen, die sich nicht als Nummer lesen lassen, stehen hinten in der Reihenfolge, die der Store liefert. WebSocket-Befehl `dashboard_history/versions`.

Vorhaben H braucht diese Liste für seinen Rücksprung, und der einfache Modus baut seine ganze Anzeige darauf. `list_versions` ordnet nach der Zeit der Markierung — die einzige Ordnung, die `store.py` kennen kann, weil die Numerierung laut Entscheidung 13 in `versions.py` lebt. Die Sortierung nach Nummer gehört also hierher, nicht in den Store.

- [ ] **Schritt 1: Die fehlschlagende Prüfung schreiben**

Ans Ende von `run_paging` anfügen:

```python
        listing = await socket.call("dashboard_history/versions", dashboard=key)
        names = [v["name"].split("/")[-1] for v in listing.get("versions", [])]
        check(
            "every version of a dashboard is listed, newest number first",
            names and names == sorted(
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
```

- [ ] **Schritt 2: Laufen lassen, Fehlschlag prüfen**

```bash
python3 -c "
import asyncio, sys, pathlib
sys.path.insert(0, str(pathlib.Path('tests/integration').resolve()))
import run_checks as rc
asyncio.run(rc.run_paging(rc.token()))
"
```

Erwartet: `RuntimeError` mit `unknown_command` für `dashboard_history/versions`.

- [ ] **Schritt 3: Umsetzen**

In `operations.py` hinter `async_history` einfügen:

```python
async def async_versions(
    hass: HomeAssistant, store: HistoryStore, key: str
) -> dict:
    """Every named point of one dashboard, by version number.

    A read, so it needs no `confirm`. It exists apart from `history`
    because the simple mode of decision 17 shows nothing else, and
    because a version outside the loaded window has to be reachable at
    all - which is the whole point of this project.

    Ordered here rather than in the store: `list_versions` orders by the
    time a tag was made, the only order that module can know, and the
    numbering lives in `versions.py` by decision 13.
    """
    versions = await hass.async_add_executor_job(store.list_versions, key)
    live = await async_get_config(hass, key)
    same: set[str] = set()
    if live is not None and versions:
        same = await hass.async_add_executor_job(
            _same_as_live, store, key, [v.revision for v in versions], live
        )

    def order(version) -> tuple:
        parts = versioning.parse(key, version.name)
        # Unreadable names last, in the order the store gave them, rather
        # than crashing or claiming to be version zero.
        return (0,) if parts is None else (1, *parts)

    return {
        "versions": [
            {
                "name": v.name,
                "title": v.title,
                "description": v.description,
                "revision": v.revision,
                "same_as_now": v.revision in same,
            }
            for v in sorted(versions, key=order, reverse=True)
        ]
    }
```

Ein neuer Import ist **nicht** nötig: `operations.py` bindet das Modul bereits als `from . import versions as versioning` ein (Zeile 21). Deshalb steht im Code oben `versioning.parse`, nicht `parse`.

In `websocket_api.py` bei den anderen Befehlen registrieren:

```python
    _command(
        f"{DOMAIN}/versions",
        {**_DASHBOARD},
        operations.async_versions,
        lambda msg: {"key": msg["dashboard"]},
    ),
```

- [ ] **Schritt 4: Laufen lassen, Erfolg prüfen**

```bash
docker compose -f docker/compose.yaml restart homeassistant
python3 -m pytest tests/ -q
python3 tests/integration/run_checks.py
```

Erwartet: alles grün.

- [ ] **Schritt 5: Committen**

```bash
git add custom_components/dashboard_history/operations.py \
        custom_components/dashboard_history/websocket_api.py \
        tests/integration/run_checks.py
git commit -m "$(cat <<'EOF'
List a dashboard's versions on their own

The simple mode of decision 17 shows versions and nothing else, so it
needs them all - not the ones that happen to sit in the loaded window.
The advanced mode gets its Versions tab from the same call.

Sorted by number here rather than in the store: the store orders by the
time a tag was made, the only order it can know, and the numbering
lives in versions.py. A name that will not parse sorts last instead of
pretending to be version zero.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Wenn alles vier steht

`python3 -m pytest tests/ -v` und `python3 tests/integration/run_checks.py` müssen beide vollständig grün sein. Danach ist Vorhaben G auf der Datenseite fertig, und die Oberfläche in Vorhaben H kann darauf aufsetzen:

- `history` blättert über `before` und sagt mit `next_cursor`, ob es weitergeht.
- `history` meldet unter `matching_versions`, welche Version dem Live-Stand entspricht — unabhängig davon, was geladen ist.
- `versions` liefert alle Versionen eines Dashboards, nach Nummer geordnet, mit der Markierung, welche gerade gilt.

**Was hier bewusst nicht passiert** und in Vorhaben H gehört: Register »Änderungen«/»Versionen«, das Suchfeld, die Schaltfläche »Ältere laden«, der abgesenkte Vorgabewert von 50 auf 25 — und jede Zeile in `panel.js`.
