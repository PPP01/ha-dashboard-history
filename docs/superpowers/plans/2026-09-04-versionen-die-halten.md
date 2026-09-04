# Vorhaben G — Versionen, die halten (Backend)

> **Für agentische Ausführung:** ERFORDERLICHER SUB-SKILL: `superpowers:subagent-driven-development` (empfohlen) oder `superpowers:executing-plans`, Aufgabe für Aufgabe. Die Schritte tragen Checkboxen (`- [ ]`) zum Mitführen.

**Ziel:** Eine Version verschwindet nicht mehr, nur weil ihr Commit aus dem Anzeigefenster gerutscht ist — und die Historie lässt sich über einen Commit-Zeiger weiterblättern statt über eine Zahl.

**Architektur:** Vier voneinander unabhängige Ergänzungen an der Leseseite. Der Store lernt einen Startpunkt für den Verlauf (dulwich `get_walker(include=…)`), `operations` reicht ihn durch und sagt, ob es weitergeht, die Übereinstimmung mit dem Live-Stand wird gegen **alle** Versionen geprüft statt gegen die zufällig geladenen, und die bestehende Versionsliste sagt, welche Version gerade gilt. Geschrieben wird nichts; jede Aufgabe fügt Antwortfelder hinzu, keine ändert bestehende.

**Technik:** Python 3.12 (Entwicklung) / 3.14 (Container), dulwich 1.2.14, pytest, Home Assistant 2026.8.3.

**Spec:** `docs/superpowers/specs/2026-08-30-dashboard-history-design.md` — Vorhaben G und Entscheidung 17. Der Befund dazu steht als offener Punkt (»Eine Version außerhalb der neuesten 50 Änderungen wird unsichtbar«).

**Korrigiert am 2026-09-04 nach Review**, vor der Ausführung. Vier Dinge waren falsch oder fehlten:

1. **Aufgabe 4 wollte bauen, was es schon gibt.** `async_versions` und der Befehl `dashboard_history/versions` existieren seit dem Plan vom 2026-09-02 — samt Sortierung nach Nummer und samt der Variante *ohne* Dashboard, die der Dienst `versions` mit »Leave empty for all« verspricht. Der ursprüngliche Entwurf hätte den Befehl doppelt registriert und die Alle-Dashboards-Variante mit `versioning.parse(None, …)` gebrochen. Die Aufgabe schrumpft auf das eine fehlende Feld: `same_as_now`.
2. **Der Zeiger in Aufgabe 1 hätte eine echte Änderung verschluckt**, wenn er kein Commit dieses Dashboards ist (`HEAD`, ein Commit eines anderen Dashboards). Nachgestellt mit dulwich, Einzelheiten unter Aufgabe 1. `previous_change` löst es seit dem 2026-09-03 richtig; der Plan übernimmt dessen Prüfung.
3. **Der Integrationstest wäre bei jeder Wiederholung zwei Minuten stehengeblieben.** Nach dem ersten Lauf steht das Dashboard durch `restore_state` wieder auf »Stand 0«; das erste Speichern des nächsten Laufs ändert dann nichts, und `_wait_for_history_to_move` wartet auf eine Bewegung, die nicht kommt. `run_undo` macht es richtig vor.
4. **Kommentare und Docstrings in den Codeblöcken waren deutsch.** Code liest ein fremder Mitwirkender; die Sprachregel des Projekts gilt auch für Tests und für `run_checks.py`, dessen Docstrings durchweg englisch sind. Deutsch bleibt die Prosa dieses Plans.

## Globale Randbedingungen

Aus der Spec, für **jede** Aufgabe verbindlich:

- **Kein Systemaufruf von `git`.** Ausschließlich `dulwich`.
- **Keine Home-Assistant-Interna abfangen oder ersetzen.** Kein Monkey-Patching.
- **`yaml_io.py`, `analyze.py`, `restore.py`, `versions.py` bleiben Home-Assistant-frei.** Der Kern von `store.py` ebenfalls: kein `import homeassistant`.
- **Blockierende Arbeit gehört in einen Executor** (`hass.async_add_executor_job`). Jeder git-Zugriff ist blockierend.
- **Nichts blockiert den Start von Home Assistant.**
- **Alles im Code ist Englisch** — Kommentare, Docstrings, Testnamen, die Namen der Integrationsprüfungen. Deutsch sind nur die Abschnittsköpfe, die `main` in `run_checks.py` ausgibt, und die sind dort bereits so.
- **Commit-Botschaften auf Englisch**, Subject im Imperativ, erster Buchstabe groß, max. 50 Zeichen, Leerzeile, Body max. 72 Zeichen pro Zeile mit dem *Warum*, Abschluss `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- **Die Oberfläche wird hier nicht angefasst.** Register, Suchfeld und »Ältere laden« gehören zu Vorhaben H, das `panel.js` ohnehin neu ordnet. Wer hier am Panel arbeitet, baut es zweimal.

**Tests:** `python3 -m pytest tests/ -v` — muss durchgehend grün bleiben (Ausgangsstand: 260 bestanden).

---

### Aufgabe 1: Ein Startpunkt für den Verlauf

**Dateien:**
- Ändern: `custom_components/dashboard_history/store.py` (`list_changes`)
- Test: `tests/test_store.py`

**Schnittstellen:**
- Liefert: `HistoryStore.list_changes(key: str, limit: int | None = 50, before: str | None = None) -> list[Change]`. Mit `before` beginnt die Liste bei der Änderung, die **älter** ist als die genannte Revision; die Revision selbst kommt nicht vor. Ist die Revision gar keine Änderung dieses Dashboards, beginnt die Liste bei der neuesten Änderung, die älter ist als sie. Eine unbekannte Revision ergibt eine leere Liste.

**Verifiziert am 2026-09-04**, damit niemand es erneut ausprobieren muss: `repo.get_walker(include=[<sha als bytes>], paths=[…], max_entries=n + 1)` liefert den genannten Commit **und** seine n Vorgänger, in dieser Reihenfolge — **sofern der Commit selbst einen der Pfade berührt.** Tut er das nicht, fehlt er in der Ausgabe, und der erste Eintrag ist bereits eine echte Änderung. Nachgestellt: vier Änderungen an `home`, danach eine an `other`; `include=[<other>]` mit den Pfaden von `home` liefert `home 3, home 2, home 1`. Ein bedingungsloses »ersten Eintrag verwerfen« hätte `home 3` verschluckt, und `before="HEAD"` ist der naheliegende Aufruf von Hand, der genau das trifft. Der erste Eintrag wird darum nur verworfen, wenn er der Zeiger **ist** — dieselbe Prüfung, die `previous_change` (store.py) seit dem 2026-09-03 mit `found[0] == full` macht. Das ist die Präzedenz im eigenen Code, nicht nur eine Messung.

Außerdem: `include` verlangt den vollen Hash als **Bytes**; ein `str` wirft `ChecksumMismatch` mit einer Meldung, die zweimal denselben Hash nennt. `HistoryStore._resolve` gibt einen **`str`** zurück (`return _as_text(obj.id)`, store.py) — dahinter gehört also ein `.encode()`.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

In `tests/test_store.py` ans Ende anfügen:

```python
def test_history_can_start_at_an_older_revision(store):
    """Paging means: carry on from here, not from position n."""
    revisions = [
        store.write_snapshot("home", f"a: {i}\n", f"home: change {i}")
        for i in range(6)
    ]
    # revisions[0] is the oldest. Carry on from the fourth-oldest:
    older = store.list_changes("home", limit=2, before=revisions[3])
    assert [c.revision for c in older] == [revisions[2], revisions[1]]


def test_the_cursor_itself_is_not_repeated(store):
    """Otherwise every page would open with the end of the one before."""
    revisions = [
        store.write_snapshot("home", f"a: {i}\n", f"home: change {i}")
        for i in range(4)
    ]
    older = store.list_changes("home", limit=10, before=revisions[2])
    assert revisions[2] not in [c.revision for c in older]


def test_a_cursor_that_is_not_a_change_of_this_dashboard_drops_nothing(store):
    """The walker yields the cursor only if it touches this dashboard.

    If it does not - another dashboard's commit, HEAD - the first entry
    is already a real change, and dropping it blindly would lose one.
    Same guard as `previous_change`.
    """
    revisions = [
        store.write_snapshot("home", f"a: {i}\n", f"home: change {i}")
        for i in range(3)
    ]
    other = store.write_snapshot("other", "b: 1\n", "other: change")
    assert [c.revision for c in store.list_changes("home", before=other)] == list(
        reversed(revisions)
    )
    # And the limit still means what it says.
    assert len(store.list_changes("home", limit=2, before=other)) == 2


def test_an_unknown_cursor_yields_nothing(store):
    """Asking is free - a revision that does not exist is not an error."""
    store.write_snapshot("home", "a: 1\n", "home: first")
    assert store.list_changes("home", before="f" * 40) == []


def test_history_without_a_cursor_is_unchanged(store):
    """The regression that counts: the existing call stays as it was."""
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

Erwartet: `TypeError: list_changes() got an unexpected keyword argument 'before'` bei vier der fünf; `test_history_without_a_cursor_is_unchanged` besteht bereits.

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

        A `before` that is no change of this dashboard - another
        dashboard's commit, HEAD - starts the walk at the newest change
        older than it. An unknown `before` yields nothing: asking about a
        revision that is gone is not an error, and `matching_revisions`
        takes the same line.
        """
        repo = self._repo()
        if repo is None:
            return []
        notes = self.descriptions()
        # Both paths: a rename touches only the metadata, and a change
        # that is recorded but never shown is the worst of both.
        paths = [f"{key}.yaml".encode(), f"meta/{key}.yaml".encode()]
        walk: dict = {"paths": paths}
        cursor: bytes | None = None
        if before is not None:
            resolved = self._resolve(repo, before)
            if resolved is None:
                return []
            # `include` walks *from* that commit and hands the commit
            # itself back first - but only if it touches these paths. A
            # cursor from another dashboard is not in the list at all,
            # so the first entry is dropped only when it *is* the cursor.
            # Same guard as `previous_change`.
            cursor = resolved.encode()
            walk["include"] = [cursor]
        if limit is not None:
            walk["max_entries"] = limit + 1 if cursor is not None else limit
        try:
            entries = list(repo.get_walker(**walk))
        except KeyError:
            # No HEAD yet: an empty repository has no history to walk.
            return []
        if cursor is not None and entries and entries[0].commit.id == cursor:
            entries = entries[1:]
        if limit is not None:
            entries = entries[:limit]
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

Erwartet: alle grün, 265 bestanden.

- [ ] **Schritt 5: Committen**

```bash
git add custom_components/dashboard_history/store.py tests/test_store.py
git commit -m "$(cat <<'EOF'
Let the history start at a revision, not an offset

Paging by number drifts: save something while somebody is reading page
two, and every later page shifts by one entry - one change seen twice,
another never. A commit is a fixed point, so the walk starts there.

dulwich hands the named commit back first, which is why one extra entry
is asked for - but only when that commit touches the dashboard at all.
A cursor from another dashboard, or HEAD, is not in the filtered list,
and dropping the first entry blindly would drop a real change; the
guard is the one previous_change already uses. Verified against 1.2.14
rather than assumed; `include` also insists on bytes and answers a str
with a checksum mismatch that names the same hash twice.

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
- Liefert: `async_history(hass, store, key, limit=50, before=None) -> dict` mit dem zusätzlichen Feld `next_cursor: str | None`. `None` heißt: Es gibt nichts Älteres mehr. Der WebSocket-Befehl nimmt `before` als optionales Feld entgegen und verlangt für `limit` mindestens 1.

**Der Vorgabewert bleibt 50, nicht 25.** Issue 1 nennt 25 für die erste Seite, aber die Schaltfläche »Ältere laden« entsteht erst in Vorhaben H. Ihn jetzt zu senken hieße, dem Panel dreißig Änderungen wegzunehmen und keinen Weg zu geben, sie zu holen. Vorhaben H setzt ihn, wenn die Oberfläche ihn tragen kann.

**`limit` mindestens 1.** Mit `limit=0` gäbe es keine älteste gelieferte Änderung, aus der ein Zeiger stammen könnte; die Antwort wäre `next_cursor: None`, obwohl es Älteres gibt — eine Antwort, die falsch ist, ohne falsch auszusehen. Das Schema lehnt die Frage ab, statt sie falsch zu beantworten. Der Dienst `history` in `services.py` hat sein eigenes Schema und bleibt unangetastet; er kennt keinen Zeiger.

- [ ] **Schritt 1: Die fehlschlagende Prüfung schreiben**

In `tests/integration/run_checks.py` vor `async def run_live_updates` einfügen:

```python
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

Erwartet: Die erste Prüfung meldet `FAIL`, weil `next_cursor` fehlt. Der zweite Aufruf endet dann mit einem **Traceback**, nicht mit einer zweiten roten Zeile: `Socket.call` wirft `RuntimeError` bei einem abgelehnten Befehl, und `before` ist noch kein erlaubtes Feld (`extra keys not allowed`). Beides ist der erwartete Fehlschlag.

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
    # One more than asked for: its presence answers "is there anything
    # older?", and it costs one commit rather than a second query.
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
        # The cursor for the next page: the oldest change handed out.
        # None means there is nothing older - the panel then leaves the
        # button out rather than fetching an empty page.
        "next_cursor": rendered[-1]["revision"] if more and rendered else None,
    }
```

In `websocket_api.py` das Schema des Befehls erweitern:

```python
    _command(
        f"{DOMAIN}/history",
        {
            **_DASHBOARD,
            # At least one: with zero there is no oldest entry to point
            # from, and the answer would claim there is nothing older.
            vol.Optional("limit", default=50): vol.All(int, vol.Range(min=1)),
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

Erwartet: pytest grün, alle Integrationsprüfungen bestanden, die drei neuen darunter. Ein zweiter Lauf von `run_paging` direkt hinterher muss ebenso durchgehen, **ohne** zwei Minuten am ersten Speichern zu hängen — das ist die Probe auf die Wartebedingung in `save`.

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
back with. A limit below one is refused: there would be no oldest entry
to point from, and the answer would claim there is nothing older.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Aufgabe 3: Übereinstimmende Versionen, unabhängig vom Fenster

**Dateien:**
- Ändern: `custom_components/dashboard_history/operations.py` (`async_history`; neu: `_by_number`)
- Test: `tests/integration/run_checks.py` (`run_paging` erweitern)

**Schnittstellen:**
- Verbraucht: `HistoryStore.matching_revisions(key, revisions, text) -> set[str]` (existiert bereits, über `_same_as_live`), `versions.parse`.
- Liefert: `async_history` antwortet zusätzlich mit `matching_versions: list[dict]` — jede Version, deren markierter Stand byteweise dem Live-Dashboard entspricht, mit `name`, `title` und `revision`, nach Versionsnummer absteigend. Unabhängig davon, ob ihr Commit im geladenen Fenster liegt.
- Neu: `_by_number(key, versions) -> list[Version]` — die Sortierung nach Nummer, die heute als Lambda in `async_versions` steckt, als benannte Hilfsfunktion. Aufgabe 4 stellt `async_versions` darauf um; sonst stünde dieselbe Sortierung an zwei Stellen, und Vorhaben H bräuchte sie an einer dritten.

Das ist der eigentliche Befund hinter Vorhaben G: Heute wird die Übereinstimmung nur für die geladenen Änderungen berechnet, und das Panel liest die Plakette aus `change.versions`. Fällt der Commit aus dem Fenster, verschwindet die Plakette — obwohl der Stand identisch ist.

- [ ] **Schritt 1: Die fehlschlagende Prüfung schreiben**

Ans Ende von `run_paging` anfügen:

```python
        # The badge must not depend on how far somebody has paged.
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

Wiederholte Läufe legen weitere Major-Versionen auf denselben ältesten Stand (`v2.0.0`, `v3.0.0`, …). Zwei Versionen auf einem Commit sind erlaubt, `v1.0.0` bleibt darunter, die Prüfung hält.

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

In `operations.py` hinter `_same_as_live` einfügen:

```python
def _by_number(key: str, versions: list) -> list:
    """Versions by number, highest first; names that will not parse last.

    Ordered here rather than in the store: `list_versions` orders by the
    time a tag was made, the only order that module can know, and the
    numbering lives in `versions.py` by decision 13. Time and number
    differ as soon as somebody goes back and marks an older state. A
    name that will not parse sorts last instead of pretending to be
    version zero.
    """
    return sorted(
        versions,
        key=lambda v: versioning.parse(key, v.name) or (-1, -1, -1),
        reverse=True,
    )
```

Den Übereinstimmungs-Block von `async_history` ersetzen:

```python
    live = await async_get_config(hass, key)
    same: set[str] = set()
    if live is not None:
        # Changes *and* versions in one pass: the comparison is by blob
        # id, and a second call would open the same repository again.
        # The versions join in because the badge would otherwise depend
        # on how far somebody has paged - the finding this project is for.
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
        for v in _by_number(key, versions)
        if v.revision in same
    ]
```

Im `return` ergänzen:

```python
        "matching_versions": matching_versions,
```

`_same_as_live` bleibt unverändert — es nimmt bereits eine beliebige Liste entgegen. Dass `wanted` eine Revision doppelt enthalten kann, wenn eine Version auf einer geladenen Änderung sitzt, ist harmlos: `matching_revisions` liefert eine Menge.

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

### Aufgabe 4: Die Versionsliste sagt, welche gerade gilt

**Dateien:**
- Ändern: `custom_components/dashboard_history/operations.py` (`async_versions`, **bestehend**)
- Ändern: `custom_components/dashboard_history/services.yaml` (Beschreibung von `versions`)
- Test: `tests/integration/run_checks.py` (`run_paging` erweitern)

**Schnittstellen:**
- Verbraucht: `_by_number` und `_same_as_live` aus Aufgabe 3, `HistoryStore.list_versions(key)`.
- Liefert: `async_versions(hass, store, key=None)` — **Signatur unverändert** — antwortet je Version zusätzlich mit `same_as_now: bool`. Ohne Dashboard bleibt das Feld `False`: Es gibt dann keinen einzelnen Live-Stand, gegen den zu vergleichen wäre.

**Was schon da ist, und was nicht.** `async_versions` (operations.py) und der Befehl `dashboard_history/versions` (websocket_api.py) existieren seit dem Plan vom 2026-09-02, mit optionalem `dashboard` und Sortierung nach Nummer. Der Dienst `versions` bietet dieselbe Funktion an und verspricht in `services.yaml` »Leave empty for all«. **Kein neuer Befehl, keine neue Registrierung, keine neue Signatur.** Was fehlt, ist das eine Feld, ohne das der einfache Modus von Entscheidung 17 nicht weiß, wo er steht: Er zeigt nur Versionen, und `same_as_now` lebte bisher allein an den Änderungen — die es im einfachen Modus nicht gibt.

- [ ] **Schritt 1: Die fehlschlagende Prüfung schreiben**

Ans Ende von `run_paging` anfügen:

```python
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

Erwartet: Die Sortier-Prüfung **besteht bereits** — der Befehl und seine Ordnung sind da. Nur »says which version the dashboard holds right now« meldet `FAIL`, mit lauter `None` in der Ausgabe. Wer hier `unknown_command` sieht, arbeitet an einem falschen Stand.

- [ ] **Schritt 3: Umsetzen**

In `operations.py` die bestehende `async_versions` ersetzen:

```python
async def async_versions(
    hass: HomeAssistant, store: HistoryStore, key: str | None = None
) -> dict:
    """Every named point, newest first. One dashboard's, or all of them.

    With a dashboard, each version also says whether it is the state the
    dashboard holds right now (`same_as_now`). The simple mode of
    decision 17 shows nothing but this list, so the list has to answer
    that on its own - and against every version, not the ones inside a
    window: a version outside the loaded window is exactly the one it
    must still find. Without a dashboard there is no single live state
    to compare against, and the field stays False.
    """
    found = await hass.async_add_executor_job(store.list_versions, key)
    same: set[str] = set()
    if key is not None:
        found = _by_number(key, found)
        live = await async_get_config(hass, key)
        if live is not None and found:
            same = await hass.async_add_executor_job(
                _same_as_live, store, key, [v.revision for v in found], live
            )
    return {
        "versions": [
            {
                "name": v.name,
                "revision": v.revision,
                "title": v.title,
                "description": v.description,
                "same_as_now": v.revision in same,
            }
            for v in found
        ]
    }
```

Die bisherige Sortierung als Lambda samt ihrem Kommentar entfällt hier — sie ist in `_by_number` aufgegangen, mit demselben Wortlaut der Begründung.

In `services.yaml` die Beschreibung von `versions` ergänzen, damit der Dienst sagt, was er jetzt kann:

```yaml
versions:
  name: Versions
  description: >-
    The named points in the history. Give a dashboard to see only its
    own, ordered by version number, each saying whether it is the state
    the dashboard holds right now.
```

`websocket_api.py` bleibt unangetastet.

- [ ] **Schritt 4: Laufen lassen, Erfolg prüfen**

```bash
docker compose -f docker/compose.yaml restart homeassistant
python3 -m pytest tests/ -q
python3 tests/integration/run_checks.py
```

Erwartet: alles grün. `run_versions` weiter oben im Lauf ist die Regression für die Alle-Dashboards-Variante und die Sortierung — beide müssen unverändert bestehen.

- [ ] **Schritt 5: Committen**

```bash
git add custom_components/dashboard_history/operations.py \
        custom_components/dashboard_history/services.yaml \
        tests/integration/run_checks.py
git commit -m "$(cat <<'EOF'
Say which version a dashboard holds right now

The simple mode of decision 17 shows versions and nothing else, so the
list has to carry the one mark the history carried so far: which entry
is the live state. Compared against every version of the dashboard,
not the ones inside a window - the window is what this project removes.

The command and its ordering by number were already there; the sort
moves into a named helper that history shares, rather than living as
the same lambda in two places.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Wenn alles vier steht

`python3 -m pytest tests/ -v` und `python3 tests/integration/run_checks.py` müssen beide vollständig grün sein — und `run_paging` ein zweites Mal direkt hinterher, ohne Wartezeit am ersten Speichern. Danach ist Vorhaben G auf der Datenseite fertig, und die Oberfläche in Vorhaben H kann darauf aufsetzen:

- `history` blättert über `before` und sagt mit `next_cursor`, ob es weitergeht.
- `history` meldet unter `matching_versions`, welche Version dem Live-Stand entspricht — unabhängig davon, was geladen ist, nach Nummer geordnet.
- `versions` liefert wie bisher alle Versionen eines Dashboards nach Nummer, jetzt mit `same_as_now` an jeder.

**Was hier bewusst nicht passiert** und in Vorhaben H gehört: Register »Änderungen«/»Versionen«, das Suchfeld, die Schaltfläche »Ältere laden«, der abgesenkte Vorgabewert von 50 auf 25 — und jede Zeile in `panel.js`.
