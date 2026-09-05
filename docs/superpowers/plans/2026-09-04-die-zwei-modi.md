# Vorhaben H, zweite Hälfte — Die zwei Modi (Oberfläche)

> **Für agentische Ausführung:** ERFORDERLICHER SUB-SKILL: `superpowers:subagent-driven-development` (empfohlen) oder `superpowers:executing-plans`, Aufgabe für Aufgabe. Die Schritte tragen Checkboxen (`- [ ]`) zum Mitführen.

**Ziel:** Wer zurück auf einen früheren Stand will, findet den Weg dorthin ohne Kurzhashes und ohne Semver — und wer mehr will, schaltet um.

**Architektur:** Acht Aufgaben. Die ersten drei sind Vorarbeit ohne sichtbare Änderung: `restore_state` lernt, den jetzigen Stand zu markieren, die Ablage lernt zu suchen und jede Zeile ihren Vorgänger zu nennen, und `panel.js` wird nach Zuständigkeiten geteilt. Die fünf danach sind die Oberfläche: Blättern, der Moduswechsel samt einfachem Modus, der Rücksprung-Dialog, die Umstellung der Zeilen-Adressierung von der Position auf die Revision — und darauf das Suchfeld.

**Technik:** Python 3.12 / 3.14, dulwich 1.2.14, pytest, Node für die Panel-Logik, Home Assistant 2026.8.3.

**Spec:** `docs/superpowers/specs/2026-08-30-dashboard-history-design.md` — Entscheidung 17, dazu Entscheidung 9 (die Aufschriften der Rückwege) und Entscheidung 13 (Versionen als Tags). Die Zeilen des Test-Plans, die hier eingelöst werden: »Rücksprung mit »verwerfen««, »Rücksprung mit »behalten««, »Blättern, während gespeichert wird«.

**Voraussetzung:** Vorhaben G **und** die erste Hälfte von H müssen stehen. Dieser Plan liest `next_cursor`, `before`, `matching_versions`, `same_as_now` und `automatic` — alles Felder, die dort entstehen. Ohne sie hat der einfache Modus nichts anzuzeigen, und das ist laut Spec der Sperrgrund, aus dem die Reihenfolge überhaupt festgelegt wurde.

## Fünf Entscheidungen, getroffen am 2026-09-04

1. **Der Rücksprung markiert über einen Parameter, nicht über zwei Aufrufe.** Nachgesehen statt vermutet: `_keep_the_live_state` läuft **innerhalb** von `async_restore_state`, zwischen der Vorschau und `async_save_config`. Ein Panel, das vorher `create_version` ruft, markiert den neuesten *aufgezeichneten* Stand — und wenn der Rekorder eine Lücke hatte, ist das nicht der Stand auf dem Bildschirm, sondern der davor. Die einzige Reihenfolge, die immer stimmt, liegt inmitten einer fremden Funktion; also wird sie dort gemacht und nicht von außen nachgebaut. Aufgabe 1.
2. **Jeder Modus durchsucht, was er zeigt — und ein Suchwort findet beides.** Der einfache Modus filtert die Versionsliste, rein im Panel: `_versions` ist vollständig, dafür gab es Vorhaben G, also braucht dieser Filter niemanden zu fragen. Der erweiterte sucht über Änderungen, und zwar zweistufig — erst über das Geladene, das ohne Netz antwortet; findet das nichts, über die ganze Historie beim Server, damit »nichts gefunden« wirklich nichts heißt. Gesucht wird dabei in vier Dingen: Meldung, eigene Beschreibung und Titel, Beschreibung und Nummer jeder Version auf diesem Stand. Wer ein Wort eintippt, muss nicht wissen, ob er es an eine Änderung oder an eine Version geschrieben hat. **Ein Schalter dafür wird bewusst nicht gebaut**; falls sich das im Gebrauch als störend erweist, kommt er später. Aufgabe 2 baut die Serverhälfte, Aufgabe 8 die Oberfläche.
3. **Eine Zeile kennt ihren Vorgänger, statt ihn aus der Nachbarschaft zu erschließen.** Das Panel hat »der Stand vor Zeile 3 ist Zeile 4« gerechnet — richtig nur, solange die Liste lückenlos und vollständig ist. Eine Seite hat einen Rand, eine Trefferliste hat Lücken. Der Vorgänger wird deshalb ein Feld (`previous`), und er kostet nichts: In `history` ist der Extra-Eintrag, der »gibt es Ältere?« beantwortet, genau dieser Vorgänger, in der Suche ist es der nächste Eintrag desselben Laufs. Nebenbei behoben: Die unterste Zeile jeder Seite bot bisher keine gelöschten Karten zum Zurückholen an. Aufgabe 2 liefert das Feld, Aufgabe 7 stellt das Panel darauf um.
4. **Zeilen adressieren sich über ihre Revision, nicht über ihre Position — und das vor dem Suchfeld.** `data-index` in das Markup zu schreiben trägt, solange es genau eine Liste gibt. Das Suchfeld macht eine zweite, und ab da bezeichnet »Zeile 3« zwei verschiedene Zeilen. Aufgabe 7 nimmt die Position aus dem Spiel, ohne Verhalten zu ändern; danach ist das Suchfeld eine Anzeigefrage. Ein eigener Halt dafür, weil ein Umbau, der Gleichheit verspricht, ein eigenes Tor verdient — dasselbe Muster wie Aufgabe 3.
5. **`panel.js` wird nach Zuständigkeit geteilt, nicht nach Modus.** Die beiden Modi teilen sich mehr, als es aussieht: Abschnitte, Zeilen, Dialoge und der Rücksprung sind in beiden dieselben Bausteine, nur unterschiedlich bestückt. Ein Schnitt nach Modus hätte diese Bausteine verdoppelt. Aufgabe 3.

**Und ein Wort zu `matching_versions`.** Vorhaben G liefert das Feld, und bis zu diesem Plan liest es niemand — das Panel rechnet dieselbe Frage über das geladene Fenster selbst nach und verliert damit genau die Versionen, für die G gebaut wurde. Aufgabe 5 stellt das um. `_loadOlder` schreibt das Feld bewusst **nicht** fort: Es ist eine Aussage über das ganze Dashboard, keine über die geladene Seite, und die Antwort der ersten Seite gilt unverändert weiter.

**Und ein Wort zu den »Registern«.** Vorhaben G und die erste Hälfte von H reichen ein Register »Änderungen«/»Versionen« hierher weiter — es stammt aus der Oberflächenhälfte von Issue 1. Es wird **nicht** gebaut, und das ist keine Auslassung: Entscheidung 17 ist laut Spec dieselbe Forderung »verschärft«, und die zwei Modi sind ihre Antwort darauf. Der erweiterte Modus *ist* die Ansicht »Änderungen«, der einfache *ist* die Ansicht »Versionen«. Beides nebeneinander zu bauen ergäbe vier Ansichten, von denen zwei Paare dasselbe zeigen — und eine Registerkarte innerhalb eines Modus, der ohnehin schon eine Auswahl ist, wäre genau die Verdopplung, die dieses Vorhaben an `panel.js` vermeiden soll.

## Globale Randbedingungen

- **Kein Systemaufruf von `git`.** Ausschließlich `dulwich`.
- **Keine Home-Assistant-Interna abfangen oder ersetzen.** Kein Monkey-Patching.
- **`yaml_io.py`, `analyze.py`, `restore.py`, `versions.py` bleiben Home-Assistant-frei.** Dieser Plan fasst keines davon an.
- **Blockierende Arbeit gehört in einen Executor.** Die Suche läuft über die ganze Historie und ist damit die längste Leseoperation, die dieses Werkzeug hat.
- **Nichts wird ohne Vorschau geschrieben.** Der Rücksprung-Dialog bleibt ein Bestätigungsdialog mit Diff; die Frage nach der Version kommt *in* ihm dazu, nicht an seiner Stelle.
- **Das Panel bekommt keine Logik.** Es entscheidet nichts, was der Server entscheiden kann. Der Moduswechsel ist die eine Ausnahme, und er ist reine Anzeige.
- **Alles im Code ist Englisch** — Kommentare, Docstrings, Testnamen, jede Aufschrift im Panel, `strings.json`. Deutsch sind nur die Prosa dieses Plans und die Abschnittsköpfe in `run_checks.py`.
- **Commit-Botschaften auf Englisch**, Subject im Imperativ, erster Buchstabe groß, max. 50 Zeichen, Leerzeile, Body max. 72 Zeichen pro Zeile mit dem *Warum*, Abschluss `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

**Tests:** `python3 -m pytest tests/ -v`, dazu `python3 tests/integration/run_checks.py`.

**Zur Testzahl, und warum hier keine nackte steht.** `tests/test_yaml_io.py` parametrisiert über die Dashboards, die in einer *echten* Ablage liegen — dem Pfad aus `DASHBOARD_HISTORY_REAL_STORAGE` oder `tests/.real-storage`. Die Gesamtzahl hängt damit davon ab, wie viele Dashboards auf der Maschine stehen, auf der gelaufen wird, und sie ändert sich, wenn dort eines dazukommt. Gemessen am 2026-09-04: derselbe Baum meldet `256 passed, 3 skipped` ohne echte Ablage und `269 passed` mit einer, in der zehn Dashboards liegen. Die Zahlen in diesem Plan stehen deshalb **in der Form ohne echte Ablage** — das ist die einzige, die auf jeder Maschine dieselbe ist, und es ist die Form, die auch die CLAUDE.md des Projekts nennt. Wer mit echter Ablage prüft, vergleicht die **Zuwächse**, nicht die Summe.

**Ausgangsstand nach H1: `270 passed, 3 skipped`** (Vorhaben G: 256 + 3; H1 legt vierzehn dazu).

**Womit das Panel geprüft wird**, damit niemand es für ungeprüft hält: `tests/test_panel_behaviour.py` lädt `panel.js` in Node mit einem zweizeiligen Ersatz für das DOM, ersetzt `_call` durch Versprechen, die der Test von Hand einlöst, und sieht sich danach den Zustand an. Alles, was dieser Plan an *Logik* ins Panel legt — welcher Modus gilt, was beim Blättern angehängt wird, wann die Suche eskaliert, was der Rücksprung-Dialog absendet — gehört genau dorthin. Nur was ein Browser zeichnet, bleibt außen vor. `tests/test_panel_assets.py` fängt die statischen Fallen ab und **kennt die Liste der Teildateien namentlich** — sie ist in Aufgabe 3 mitzuziehen.

---

### Aufgabe 1: Der Rücksprung kann den jetzigen Stand markieren

**Dateien:**
- Ändern: `custom_components/dashboard_history/operations.py` (`async_restore_state`, neu: `_async_keep_as_version`)
- Ändern: `custom_components/dashboard_history/websocket_api.py`
- Ändern: `custom_components/dashboard_history/services.py`, `services.yaml`
- Test: `tests/integration/run_checks.py` (neue Prüfung `run_keep_as_version`)

**Schnittstellen:**
- Liefert: `async_restore_state(hass, store, key, revision, confirm=False, keep_as_version=None)`. `keep_as_version` ist `None` oder `{"level": str, "title": str, "description": str}`. Bei `confirm=True` und gesetztem Feld antwortet das Ergebnis zusätzlich mit `kept_as_version` — unverändert das, was `async_create_version` zurückgibt: `{"created": name}` im Erfolgsfall, `{"created": None, "error": …}` sonst. Der `error`-Schlüssel fehlt also bei Erfolg, statt `None` zu sein. Das ist Absicht: dieselbe Nachricht hätte sonst verschachtelt eine andere Gestalt als an der Oberfläche, wo der Dienst `create_version` seit Vorhaben G genau diese Form liefert. Wer sie liest, fragt mit `?.error` bzw. `.get("error")`, nie mit `"error" in …`.
- Verbraucht: `async_create_version` (besteht), `_keep_the_live_state` (besteht).

**Warum das nicht das Panel machen kann.** In `async_restore_state` steht heute, in dieser Reihenfolge: Vorschau bauen, `_keep_the_live_state` (der Rekorder wird gefragt, ob der lebende Stand wirklich in der Historie liegt, und schreibt ihn sonst nach), dann `async_save_config`. Nur zwischen den letzten beiden ist der neueste aufgezeichnete Stand dieses Dashboards *der lebende*. Davor kann er der vorletzte sein — genau in dem Fall, für den `_keep_the_live_state` gebaut wurde: ein Speichervorgang während des HA-Starts, eine von außen bearbeitete Datei, ein einmal fehlgeschlagener Rekorder. Ein Tag, der dort danebengeht, sieht später an nichts falsch aus; er zeigt bloß auf etwas anderes, als der Nutzer markiert zu haben glaubt.

**Und wenn der Stand nicht gesichert werden konnte, wird nicht markiert.** `_keep_the_live_state` antwortet dann mit einer Notiz statt mit `None`. In diesem Fall liegt der lebende Stand nicht in der Historie, es gibt also nichts, was wahrheitsgemäß zu markieren wäre. Die Antwort sagt das; der Rücksprung selbst geht trotzdem durch, aus demselben Grund, aus dem `_keep_the_live_state` niemals verweigert.

- [ ] **Schritt 1: Die fehlschlagende Prüfung schreiben**

In `tests/integration/run_checks.py` vor `def _drop_first_card` einfügen:

```python
async def run_keep_as_version(access: str) -> None:
    """Marking the state a restore is about to replace.

    Only reachable here: the ordering that makes it correct sits between
    two awaits inside `async_restore_state`, and pytest cannot import
    that module at all.
    """
    key = "dh-keep-check"

    async def save(socket, title: str) -> None:
        await socket.call(
            "lovelace/config/save",
            url_path=key,
            config={"views": [{"path": "p", "title": title, "cards": []}]},
        )
        await _wait_until_recorded(socket, key)

    async with Socket(access) as socket:
        listed = (await socket.call("lovelace/dashboards/list")) or []
        if not any(entry.get("url_path") == key for entry in listed):
            await socket.call(
                "lovelace/dashboards/create", url_path=key, title="DH Keep"
            )
            await asyncio.sleep(4)
        await save(socket, "Older")
        older = (await socket.call("dashboard_history/history", dashboard=key))[
            "changes"
        ][0]["revision"]
        await save(socket, "Newer")
        newest = (await socket.call("dashboard_history/history", dashboard=key))[
            "changes"
        ][0]["revision"]

        answer = await socket.call(
            "dashboard_history/restore_state",
            dashboard=key,
            revision=older,
            confirm=True,
            keep_as_version={"level": "minor", "title": "Before going back"},
        )
        kept = answer.get("kept_as_version") or {}
        check(
            "going back can mark the state it replaces",
            answer.get("applied") is True and bool(kept.get("created")),
            f"applied={answer.get('applied')} kept={kept}",
        )
        # The point of the whole exercise: the tag sits on the state that
        # was on the screen, not on the one before it. Two saves were
        # made above so that those two are different revisions.
        listing = (await socket.call("dashboard_history/versions", dashboard=key))[
            "versions"
        ]
        mine = [v for v in listing if v["name"] == kept.get("created")]
        check(
            "and it marks the state that was there, not the one before it",
            bool(mine) and mine[0]["revision"] == newest,
            f"{mine[:1]} vs newest {newest[:10]}",
        )
        check(
            "and it is not marked as one nobody asked for",
            bool(mine) and mine[0].get("automatic") is False,
            str(mine[:1]),
        )
```

Und in `main` registrieren, hinter dem Block für den Tagesversions-Schalter:

```python
    print("\n  -- Den Stand sichern, bevor er ersetzt wird --")
    asyncio.run(run_keep_as_version(access))
```

- [ ] **Schritt 2: Laufen lassen, Fehlschlag prüfen**

```bash
python3 -c "
import asyncio, sys, pathlib
sys.path.insert(0, str(pathlib.Path('tests/integration').resolve()))
import run_checks as rc
asyncio.run(rc.run_keep_as_version(rc.token()))
"
```

Erwartet: ein `RuntimeError` aus `Socket.call` — `extra keys not allowed @ data['keep_as_version']`. Der Fehlschlag kommt aus dem Schema, bevor irgendeine Prüfzeile gedruckt wird.

- [ ] **Schritt 3: Umsetzen**

In `operations.py` vor `async_restore_state` den Helfer einfügen:

```python
async def _async_keep_as_version(
    hass: HomeAssistant,
    store: HistoryStore,
    key: str,
    wanted: dict,
    gap: str | None,
) -> dict:
    """Mark the state that is about to be replaced, if it can be marked.

    Called after `_keep_the_live_state` and before the write, and that
    is the whole reason it exists here rather than in a caller: only
    between those two is the newest recorded state of this dashboard the
    one that is on the screen. A panel marking it beforehand would tag
    whatever was newest *then*, which after a save the recorder missed
    is the state before it - a tag that points somewhere else and looks
    perfectly right ever after.

    `gap` is what `_keep_the_live_state` reported. When it says
    something, the live state is not in the history at all, so there is
    nothing here that could be marked truthfully. Answered rather than
    raised: the restore itself goes ahead, for the same reason
    `_keep_the_live_state` never refuses either.
    """
    if gap is not None:
        return {"created": None, "error": gap}
    return await async_create_version(
        hass,
        store,
        key,
        level=wanted.get("level") or "patch",
        title=wanted.get("title") or "",
        description=wanted.get("description") or "",
    )
```

Die Signatur von `async_restore_state` erweitern:

```python
async def async_restore_state(
    hass: HomeAssistant,
    store: HistoryStore,
    key: str,
    revision: str,
    confirm: bool = False,
    keep_as_version: dict | None = None,
) -> dict:
```

Und den Abschluss der Funktion ersetzen — von `await async_save_config` bis zum `return`:

```python
    kept = None
    if keep_as_version is not None:
        kept = await _async_keep_as_version(
            hass,
            store,
            key,
            keep_as_version,
            # A dashboard that is gone has no live state at all, so there
            # is nothing to keep and nothing to mark. Said in the answer
            # rather than silently skipped: somebody asked for a version.
            "the dashboard was gone, so there was no state to mark"
            if missing
            else note,
        )
    await async_save_config(hass, key, target)
    result = {
        "applied": True,
        "preview": diff,
        "explanation": explanation,
        "created": created,
    }
    if note:
        result["note"] = note
    if kept is not None:
        result["kept_as_version"] = kept
    return result
```

In `websocket_api.py` das Schema von `restore_state` erweitern:

```python
    _command(
        f"{DOMAIN}/restore_state",
        {
            **_DASHBOARD,
            **_REVISION,
            vol.Optional("confirm", default=False): bool,
            # Only shaped here, never judged: an unknown level is
            # answered by operations with a sentence the panel can show,
            # and a schema that refused first would take that sentence
            # away. The same reason create_version takes free text.
            vol.Optional("keep_as_version"): vol.Any(
                None,
                vol.Schema(
                    {
                        vol.Optional("level", default="patch"): str,
                        vol.Required("title"): str,
                        vol.Optional("description", default=""): str,
                    }
                ),
            ),
        },
        operations.async_restore_state,
        lambda msg: {
            "key": msg["dashboard"],
            "revision": msg["revision"],
            "confirm": msg["confirm"],
            "keep_as_version": msg.get("keep_as_version"),
        },
    ),
```

In `services.py` den Aufruf von `restore_state` um das Feld erweitern — die bestehende Funktion und ihr Schema:

```python
    async def restore_state(call: ServiceCall) -> dict:
        return await operations.async_restore_state(
            hass,
            store,
            call.data["dashboard"],
            call.data["revision"],
            call.data.get("confirm", False),
            call.data.get("keep_as_version"),
        )
```

```python
        (
            "restore_state",
            restore_state,
            DASHBOARD.extend(
                {
                    vol.Required("revision"): cv.string,
                    vol.Optional("confirm", default=False): cv.boolean,
                    vol.Optional("keep_as_version"): vol.Any(None, dict),
                }
            ),
        ),
```

In `services.yaml` unter `restore_state` das Feld ergänzen:

```yaml
    keep_as_version:
      description: >-
        Mark the state you are leaving, so it can be found again by name.
        Give a title, and optionally a level (patch, minor, major) and a
        description. The mark is made after the state is safely in the
        history and before the older one is written, which is the only
        moment it is the state you saw. Leave this out to change nothing;
        nothing is deleted either way.
      example: '{"level": "minor", "title": "Before going back"}'
      selector:
        object:
```

- [ ] **Schritt 4: Laufen lassen, Erfolg prüfen**

```bash
python3 -m pytest tests/ -q
docker compose -f docker/compose.yaml restart homeassistant
python3 tests/integration/run_checks.py
```

Erwartet: pytest unverändert (`270 passed, 3 skipped`), alle Integrationsprüfungen bestanden, die drei neuen darunter. Wiederholte Läufe zählen die Version hoch (`v1.1.0`, `v1.2.0`, …); die Prüfungen hängen am zurückgegebenen Namen und nicht an einer festen Nummer.

- [ ] **Schritt 5: Committen**

```bash
git add custom_components/dashboard_history/operations.py \
        custom_components/dashboard_history/websocket_api.py \
        custom_components/dashboard_history/services.py \
        custom_components/dashboard_history/services.yaml \
        tests/integration/run_checks.py
git commit -m "$(cat <<'EOF'
Let a restore mark the state it replaces

Going back to an older state is the moment somebody most wants a name
on the one they are leaving. Doing that from outside cannot be got
right: the only moment the newest recorded state is the one on the
screen sits between two awaits in here, after the live state has been
put in the history and before the older one is written.

A caller marking it beforehand would tag whatever was newest then -
after a save the recorder missed, that is the state before the one on
the screen, and the tag looks perfectly right ever after.

Where the live state could not be recorded at all, nothing is marked
and the answer says so. The restore still goes ahead, for the reason
_keep_the_live_state never refuses either.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Aufgabe 2: Jede Zeile kennt ihren Vorgänger — und die Suche über die ganze Historie

**Dateien:**
- Ändern: `custom_components/dashboard_history/store.py` (`Change` bekommt `previous`; `list_changes` füllt es; neu: `search_changes`)
- Ändern: `custom_components/dashboard_history/operations.py` (neu: `_rendered`, `async_search`; `async_history` benutzt `_rendered` mit)
- Ändern: `custom_components/dashboard_history/websocket_api.py`, `services.py`, `services.yaml`
- Test: `tests/test_store.py`

**Schnittstellen:**
- Liefert: `Change.previous: str | None` — der Stand dieses Dashboards unmittelbar **vor** dieser Änderung, oder `None`, wenn es keinen gibt. `list_changes` füllt es für jede zurückgegebene Zeile.
- Liefert: `HistoryStore.search_changes(key: str, text: str, limit: int = 50) -> list[Change]` — die Änderungen dieses Dashboards, in deren Worten `text` steht, neueste zuerst, Groß- und Kleinschreibung egal. Leerer Text ergibt eine leere Liste.
- Liefert: `operations.async_search(hass, store, key, text, limit=50) -> dict` mit denselben `changes`-Einträgen, die `async_history` liefert, plus `more: bool`.
- Liefert: `operations._rendered(changes, marks, same) -> list[dict]` — die Zeilenform, die bisher in `async_history` eingebaut war, jetzt mit `previous`.

**Warum ein Feld und keine Rechnung.** Das Panel hat den Vorgänger einer Zeile bisher aus ihrer *Position* erschlossen: »der Stand vor Zeile 3 ist Zeile 4«. Das stimmt genau so lange, wie die Liste lückenlos, chronologisch und vollständig ist. Eine Seite hat aber einen Rand, und eine Trefferliste hat Lücken. Der Vorgänger gehört deshalb in die Zeile, nicht in die Nachbarschaft.

**Das behebt zugleich einen Fehler, der schon da ist.** `_before(index)` liefert für die **unterste Zeile jeder geladenen Seite** `null`, obwohl deren Vorgänger sehr wohl in der Historie liegt — nur eben nicht im Fenster. Folge: Diese Zeile bietet kein »Put back« für gelöschte Karten an, weil `_detailFor` bei `before === null` eine leere Liste einsetzt. Bisher traf das die 50. Zeile und fiel kaum auf. Aufgabe 4 senkt das Fenster auf 25 — ab dann trifft es jede Seite.

**Und es kostet nichts.** `async_history` holt schon heute `limit + 1` Änderungen, um zu wissen, ob es ältere gibt; genau dieser Extra-Eintrag *ist* der Vorgänger der letzten gezeigten Zeile. `list_changes` holt darum durchweg einen mehr, als es herausgibt. `search_changes` läuft die ganze gefilterte Historie ohnehin durch, dort ist der Vorgänger der nächste Eintrag desselben Laufs. In beiden Wegen: keine einzige zusätzliche Leseoperation.

**Warum die Ablage sucht und nicht `operations`.** Es ist eine Abfrage über die Historie, genau wie `list_changes`, und `store.py` ist der einzige Ort, der die ganze Historie laufen kann. Der Nebengewinn wiegt schwerer: `tests/test_store.py` erreicht `store.py` in reinem pytest, `operations.py` nie. Die Frage, was als Treffer gilt, ist damit vollständig geprüft.

**Gesucht wird in vier Dingen, und das ist eine Entscheidung.** In der erzeugten Meldung, in der eigenen Beschreibung einer Änderung — und in Titel, Beschreibung und **Nummer** jeder Version, die auf dieser Änderung sitzt. Ein Suchwort findet also beides, ohne dass jemand vorher wählen muss, wonach er sucht; wer »Winterumbau« eintippt, weiß nicht und muss nicht wissen, ob er das als Beschreibung an eine Änderung oder als Titel an eine Version geschrieben hat. Sollte sich das im Gebrauch als störend erweisen, wird es später umschaltbar — jetzt einen Schalter zu bauen, hieße, eine Frage zu stellen, die noch niemand hatte.

**Vom Versionsnamen zählt nur die Nummer.** `home/v1.0.0` wird als `v1.0.0` durchsucht. Der Namensraum ist der Schlüssel des Dashboards, und der ist auch das Wort, mit dem ein Mensch das Dashboard meint — »home« als Suchwort träfe sonst jede einzelne Version davon und nichts sonst.

**Ein Versionstreffer erscheint als die Änderung, die er markiert.** Nicht als eigene Zeilenart: Eine Version *ist* ein Name auf einem Stand, und dieser Stand ist eine Änderung, die die Zeile ohnehin zeichnen kann. Die Zeile trägt die Marke bereits in ihrem Feld `versions`, also sieht man am Treffer, warum er einer ist. Eine zweite Trefferart hätte eine zweite Zeilenform gebraucht, und die Oberfläche hätte lernen müssen, sie zu unterscheiden — Logik im Panel.

- [ ] **Schritt 1: Die fehlschlagenden Tests schreiben**

In `tests/test_store.py` ans Ende anfügen:

```python
# -- what came before this, said by the row itself -------------------------


def test_a_change_knows_the_state_before_it(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    second = store.write_snapshot("home", "a: 2\n", "second")
    newest, older = store.list_changes("home")
    assert newest.revision == second and newest.previous == first
    assert older.revision == first


def test_the_oldest_change_has_no_state_before_it(store):
    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("home", "a: 2\n", "second")
    assert store.list_changes("home")[-1].previous is None


def test_the_last_row_of_a_page_knows_its_predecessor_too(store):
    # The whole reason this is a field. Worked out from the neighbour in
    # the list, the bottom row of every page answers "there is nothing
    # before this" - and the panel then offers no deleted cards to put
    # back, on a row that has a perfectly good predecessor one commit
    # further down.
    made = [store.write_snapshot("home", f"a: {i}\n", f"change {i}") for i in range(6)]
    page = store.list_changes("home", 3)
    assert [c.revision for c in page] == [made[5], made[4], made[3]]
    assert page[-1].previous == made[2]


def test_the_state_before_is_this_dashboards_own(store):
    # Never the commit's parent: another dashboard's commit sits in
    # between all the time, and its state is no state of this one.
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("solar", "b: 1\n", "stranger")
    second = store.write_snapshot("home", "a: 2\n", "second")
    assert store.list_changes("home")[0].previous == first
    assert store.previous_change("home", second) == first


# -- searching the whole history -------------------------------------------


def test_a_search_finds_a_change_by_its_message(store):
    store.write_snapshot("home", "a: 1\n", "home: 1 card added")
    store.write_snapshot("home", "a: 2\n", "home: 2 views removed")
    assert [c.message for c in store.search_changes("home", "views")] == [
        "home: 2 views removed"
    ]


def test_a_search_finds_a_change_by_what_a_person_wrote(store):
    first = store.write_snapshot("home", "a: 1\n", "home: 1 card added")
    store.write_snapshot("home", "a: 2\n", "home: 1 card added")
    store.set_description(first, "The heating page rework")
    assert [c.revision for c in store.search_changes("home", "heating")] == [first]


def test_a_search_finds_a_state_by_the_title_of_a_version_on_it(store):
    store.write_snapshot("home", "a: 1\n", "home: 1 card added")
    marked = store.write_snapshot("home", "a: 2\n", "home: 2 moved")
    store.create_version("home/v1.0.0", "Before the winter rebuild", "", marked)
    assert [c.revision for c in store.search_changes("home", "winter")] == [marked]


def test_a_search_finds_a_state_by_the_description_of_a_version_on_it(store):
    marked = store.write_snapshot("home", "a: 1\n", "home: 1 card added")
    store.create_version("home/v1.0.0", "A title", "the notes I left", marked)
    assert [c.revision for c in store.search_changes("home", "notes")] == [marked]


def test_a_search_finds_a_state_by_the_number_of_a_version_on_it(store):
    marked = store.write_snapshot("home", "a: 1\n", "home: 1 card added")
    store.create_version("home/v1.2.0", "A title", "", marked)
    assert [c.revision for c in store.search_changes("home", "v1.2")] == [marked]


def test_a_search_does_not_match_the_namespace_of_a_version(store):
    # `home/v1.0.0` is searched as `v1.0.0`. The namespace is the
    # dashboard's own key, which is also the word a person uses for the
    # dashboard - so searching it would make every version of it a hit
    # for a word that says nothing.
    marked = store.write_snapshot("home", "a: 1\n", "home: 1 card added")
    store.create_version("home/v1.0.0", "A title", "", marked)
    assert store.search_changes("home", "home/") == []


def test_a_search_does_not_care_about_capitals(store):
    store.write_snapshot("home", "a: 1\n", "home: 1 Card added")
    assert len(store.search_changes("home", "cARD")) == 1


def test_a_search_stays_inside_one_dashboard(store):
    store.write_snapshot("home", "a: 1\n", "home: rework")
    store.write_snapshot("solar", "b: 1\n", "solar: rework")
    assert [c.message for c in store.search_changes("home", "rework")] == [
        "home: rework"
    ]


def test_a_search_reaches_past_the_window_the_panel_loads(store):
    # The whole reason this exists. The panel holds twenty-five entries;
    # the answer to "is that word anywhere" must not be decided by that.
    for index in range(40):
        store.write_snapshot("home", f"a: {index}\n", f"home: change {index}")
    store.write_snapshot("home", "a: last\n", "home: the needle")
    for index in range(40, 70):
        store.write_snapshot("home", f"a: {index}\n", f"home: change {index}")
    assert [c.message for c in store.search_changes("home", "needle")] == [
        "home: the needle"
    ]


def test_a_hit_carries_the_state_before_it(store):
    # Hits are not neighbours in the list they are drawn into, so the row
    # cannot work this out afterwards. It comes out of the same walk.
    first = store.write_snapshot("home", "a: 1\n", "home: first")
    found = store.write_snapshot("home", "a: 2\n", "home: the needle")
    for index in range(5):
        store.write_snapshot("home", f"a: {index + 3}\n", f"home: change {index}")
    hit = store.search_changes("home", "needle")[0]
    assert hit.revision == found and hit.previous == first


def test_a_search_answers_newest_first_and_stops_at_the_limit(store):
    for index in range(5):
        store.write_snapshot("home", f"a: {index}\n", f"home: match {index}")
    found = store.search_changes("home", "match", limit=2)
    assert [c.message for c in found] == ["home: match 4", "home: match 3"]


def test_an_empty_search_finds_nothing_rather_than_everything(store):
    store.write_snapshot("home", "a: 1\n", "home: first")
    assert store.search_changes("home", "") == []
    assert store.search_changes("home", "   ") == []
```

- [ ] **Schritt 2: Laufen lassen, Fehlschlag prüfen**

```bash
python3 -m pytest tests/test_store.py -k "search or before or previous" -v
```

Erwartet: Die vier `previous`-Fälle scheitern mit `AttributeError: 'Change' object has no attribute 'previous'`, die elf Suchfälle mit `AttributeError: 'HistoryStore' object has no attribute 'search_changes'`. Die vorhandenen `previous_change`-Fälle bleiben grün — jene Methode wird nicht angefasst, `undo_change` und `explain` fragen weiterhin einzeln.

- [ ] **Schritt 3: Umsetzen**

In `store.py` das Feld an `Change` anhängen:

```python
    description: str = ""  # what a person wrote about it, if anyone did
    # The state of this dashboard just before this change, or None where
    # there is none. A field rather than a sum: a caller that works it
    # out from the neighbour in a list is right only while that list is
    # whole and in order - which a page and a search result are not.
    previous: str | None = None
```

In `list_changes` den Lauf um einen Eintrag verlängern:

```python
        if limit is not None:
            # One more than asked for, so the last entry handed out knows
            # its predecessor; two more with a cursor, because the cursor
            # entry itself is dropped again below.
            walk["max_entries"] = limit + 2 if cursor is not None else limit + 1
```

Und den Abschluss der Methode ersetzen — von `if limit is not None: entries = entries[:limit]` bis zum `return`:

```python
        found = [
            Change(
                revision=_as_text(entry.commit.id),
                timestamp=entry.commit.commit_time,
                message=entry.commit.message.decode("utf-8").strip(),
                description=notes.get(_as_text(entry.commit.id), ""),
                # The next entry of this same walk. The walk is already
                # filtered on this dashboard's paths, so it is this
                # dashboard's own predecessor and never the commit's
                # parent, which may belong to somebody else entirely.
                previous=(
                    _as_text(entries[at + 1].commit.id)
                    if at + 1 < len(entries)
                    else None
                ),
            )
            for at, entry in enumerate(entries)
        ]
        # Sliced after building, so the extra entry did its one job -
        # being the predecessor of the last one - and then goes.
        return found[:limit] if limit is not None else found
```

Dahinter die Suche einfügen:

```python
    def search_changes(
        self, key: str, text: str, limit: int = 50
    ) -> list[Change]:
        """Recorded states of one dashboard whose words hold `text`.

        The whole history, not the page a caller happens to hold, and
        that is the entire point. The panel searches what it has loaded
        first because that answers without a round trip; it asks this
        only when that found nothing, and at that moment "nothing" has
        to mean nothing - not "nothing among the newest twenty-five".

        Matched against four things, ignoring case: the generated
        message, a person's own description, and the title, description
        and number of every version sitting on that state. One word
        finds either kind, because somebody searching for words they
        remember writing does not remember which of the two places they
        wrote them in.

        Of a version's name only the number counts - `home/v1.0.0` is
        searched as `v1.0.0`. The namespace is the dashboard's own key,
        and that is also the word a person uses for the dashboard, so
        searching it would make every version of it a hit for a word
        that says nothing.

        An empty search finds nothing rather than everything. It is the
        state of a search box somebody has just cleared, and answering
        it with the whole history is the opposite of what that means.
        """
        needle = text.strip().casefold()
        if not needle:
            return []
        marks: dict[str, list[Version]] = {}
        for version in self.list_versions(key):
            marks.setdefault(version.revision, []).append(version)
        found: list[Change] = []
        # The unbounded walk is deliberate and is the expensive part:
        # measured at roughly half a second per thousand commits. It runs
        # in an executor, and only after a local search found nothing.
        for change in self.list_changes(key, None):
            words = [change.message, change.description]
            for version in marks.get(change.revision, []):
                words += [
                    version.name.rsplit("/", 1)[-1],
                    version.title,
                    version.description,
                ]
            if needle in "\n".join(words).casefold():
                found.append(change)
                if len(found) >= limit:
                    break
        return found
```

In `operations.py` die Zeilenbildung aus `async_history` herausziehen — den Helfer hinter `_version_dict` einfügen:

```python
def _rendered(changes: list, marks: dict, same: set) -> list[dict]:
    """Recorded changes as the rows a panel draws.

    One shape for `history` and for `search`. They differ in which
    changes they hand back and in nothing else, and a row that carried
    different fields depending on how it was found would be a difference
    the panel has to know about - which is logic in the panel.
    """
    return [
        {
            "revision": c.revision,
            "timestamp": c.timestamp,
            "message": c.message,
            "description": c.description,
            # What this row can be compared against and undone towards.
            # Said rather than left to be worked out from the row below:
            # in a page the row below may not exist, and in a search
            # result it is not the predecessor at all.
            "previous": c.previous,
            "same_as_now": c.revision in same,
            "versions": marks.get(c.revision, []),
        }
        for c in changes
    ]
```

In `async_history` die Liste `rendered` durch den Aufruf ersetzen:

```python
    rendered = _rendered(changes, marks, same)
```

Und hinter `async_history` die Suche einfügen:

```python
async def async_search(
    hass: HomeAssistant,
    store: HistoryStore,
    key: str,
    text: str,
    limit: int = 50,
) -> dict:
    """Recorded changes of one dashboard whose words hold `text`.

    Answers in the same shape as `history`, minus the cursor: a search
    result is not a page, and offering to page through one would invite
    a second search with a different answer. `more` says the limit was
    reached, so the panel can say "the first fifty" rather than "fifty".

    The longest read this integration has - the whole history - so it is
    a command of its own rather than a flag on `history`. That keeps the
    ordinary path, which the panel walks on every click, off it.
    """
    changes, versions = await asyncio.gather(
        hass.async_add_executor_job(store.search_changes, key, text, limit + 1),
        hass.async_add_executor_job(store.list_versions, key),
    )
    more = len(changes) > limit
    changes = changes[:limit]
    marks: dict[str, list[dict]] = {}
    for version in versions:
        marks.setdefault(version.revision, []).append(_version_dict(version))
    live = await async_get_config(hass, key)
    same: set[str] = set()
    if live is not None and changes:
        same = await hass.async_add_executor_job(
            _same_as_live, store, key, [c.revision for c in changes], live
        )
    return {"changes": _rendered(changes, marks, same), "more": more}
```

In `websocket_api.py` den Befehl registrieren, hinter `history`:

```python
    _command(
        f"{DOMAIN}/search",
        {
            **_DASHBOARD,
            vol.Required("text"): str,
            vol.Optional("limit", default=50): vol.All(int, vol.Range(min=1)),
        },
        operations.async_search,
        lambda msg: {
            "key": msg["dashboard"],
            "text": msg["text"],
            "limit": msg["limit"],
        },
    ),
```

In `services.py` den Dienst ergänzen, neben `history`:

```python
    async def search(call: ServiceCall) -> dict:
        return await operations.async_search(
            hass, store, call.data["dashboard"], call.data["text"],
            call.data.get("limit", 50),
        )
```

```python
        ("search", search, DASHBOARD.extend({
            vol.Required("text"): cv.string,
            vol.Optional("limit", default=50): int,
        })),
```

Und in `services.yaml`:

```yaml
search:
  name: Search
  description: >-
    Find recorded changes of one dashboard by their words. Searches the
    whole history, not just the newest entries, and looks at the
    automatic message, any description you wrote yourself, and the
    title, description and number of any version sitting on that state.
  fields:
    dashboard:
      required: true
      description: The dashboard, by its url_path.
      example: my-dashboard
      selector:
        text:
    text:
      required: true
      description: The words to look for. Capitals do not matter.
      example: heating
      selector:
        text:
    limit:
      description: How many matches at most. The answer says whether there were more.
      example: 50
      selector:
        number:
          min: 1
          max: 1000
          mode: box
```

- [ ] **Schritt 4: Laufen lassen, Erfolg prüfen**

```bash
python3 -m pytest tests/ -q
docker compose -f docker/compose.yaml restart homeassistant
python3 tests/integration/run_checks.py
```

Erwartet: **`286 passed, 3 skipped`** (sechzehn mehr), Integrationsprüfungen unverändert grün. Zusätzlich beide Dienste von Hand, in den Entwicklerwerkzeugen unter *Aktionen*:

- `dashboard_history.search` mit einem Wort, das nur weit hinten in der Historie vorkommt.
- `dashboard_history.search` mit dem Titel einer Version — der Treffer muss die Änderung sein, auf der sie sitzt, und ihr `versions`-Feld muss die Version nennen.
- `dashboard_history.history` mit `limit: 3` — jede der drei Zeilen muss ein `previous` tragen, auch die unterste.

- [ ] **Schritt 5: Committen**

```bash
git add custom_components/dashboard_history/store.py \
        custom_components/dashboard_history/operations.py \
        custom_components/dashboard_history/websocket_api.py \
        custom_components/dashboard_history/services.py \
        custom_components/dashboard_history/services.yaml \
        tests/test_store.py
git commit -m "$(cat <<'EOF'
Let a row say what came before, and search it all

A row's predecessor was worked out from the row below it, which is
right only while the list is whole and in order. A page is not: the
bottom row of every page answered "nothing came before this" and so
offered no deleted cards to put back, on a row with a perfectly good
predecessor one commit down. That gets worse when the page drops to
twenty-five. It is a field now, and it costs no extra read - the entry
that tells history whether there is more *is* that predecessor.

The search needs the same field for a harder reason: hits are not
neighbours. And it searches the whole history, because the panel holds
twenty-five entries and answering "nothing found" out of those would be
the invisible gap this project exists to prevent, wearing a search box.

One word finds either kind - a change's own words, or the title,
description or number of a version sitting on that state - because
nobody remembers which of the two they wrote it in. A version hit comes
back as the change it marks, so there is one row shape and the panel
has nothing to tell apart.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Aufgabe 3: Das Panel wird nach Zuständigkeiten geteilt

**Dateien:**
- Anlegen: `custom_components/dashboard_history/panel/rows.js`
- Anlegen: `custom_components/dashboard_history/panel/dialogs.js`
- Ändern: `custom_components/dashboard_history/panel.js`
- Test: `tests/test_panel_assets.py` (die Liste der Teile)

**Schnittstellen:**
- `panel/rows.js` liefert reine Funktionen, ohne `this`: `sections(changes)`, `someNames(names)`, `renderRow(options)`, `versionHead(options)`.
- `panel/dialogs.js` liefert `DIALOGS` — die Markup-Zeichenkette aller `<dialog>`-Elemente, die `_render` heute inline trägt.
- `panel.js` behält die Klasse: Zustand, Abrufe, Ereignisverdrahtung und die Abläufe, die diese Bausteine bestücken.

**Reine Bausteine, keine Mixins.** Die vorhandene Teildatei `render.js` macht es vor: Sie exportiert `escape`, `renderDiff`, `renderPlain`, `when`, `joinNames` — Funktionen, die Daten hereinnehmen und Zeichenketten herausgeben. Genau so werden die neuen Teile geschnitten. Was `this` braucht, bleibt in der Klasse; was nur Daten braucht, zieht um. Damit ist der Schnitt mechanisch nachprüfbar und die Node-Tests laufen unverändert weiter.

**Diese Aufgabe ändert kein Verhalten.** Das ist ihre Bedingung, und `tests/test_panel_behaviour.py` ist der Beweis: Es lädt `panel.js` in Node und muss ohne jede Anpassung grün bleiben. Rot ist hier nur `test_the_parts_are_found_at_all`, weil es die Liste der Teildateien namentlich kennt.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

In `tests/test_panel_assets.py` die Liste in `test_the_parts_are_found_at_all` erweitern:

```python
def test_the_parts_are_found_at_all():
    # Without this the two tests below would pass by having nothing to
    # look at, which is the one way a guard fails silently. Named rather
    # than counted: a part that quietly disappears is exactly the kind of
    # loss this list is here to notice.
    assert [path.name for path in PARTS] == [
        "dialogs.js",
        "render.js",
        "rows.js",
        "style.js",
    ]
```

- [ ] **Schritt 2: Laufen lassen, Fehlschlag prüfen**

```bash
python3 -m pytest tests/test_panel_assets.py -v
```

Erwartet: ein Fehlschlag, `assert ['render.js', 'style.js'] == ['dialogs.js', ...]`.

- [ ] **Schritt 3: Umsetzen**

`custom_components/dashboard_history/panel/rows.js` neu anlegen. Die Rümpfe stammen wörtlich aus `panel.js`; was dort über `this` lief, kommt jetzt als Argument herein. **Jeden vorhandenen Kommentar mitnehmen** — sie tragen die Begründungen, und eine Begründung, die beim Umziehen verlorengeht, ist eine Entscheidung, die beim nächsten Mal neu getroffen wird:

```js
/**
 * The pieces a history is drawn from: sections, heads, rows, chips.
 *
 * Pure on purpose - data in, markup out, no `this`. Both modes build
 * their list from exactly these, which is why the split runs along
 * responsibility rather than along the modes: a cut by mode would have
 * made two of each of them.
 */

const PARTS = new URL(import.meta.url).search;
const { escape, when, joinNames } = await import(`./render.js${PARTS}`);

/**
 * The history, cut into sections at the versions.
 *
 * A version marks a state, so it marks the *newest* change it contains
 * - the section it heads runs from that change downwards to the next
 * version below. Everything above the topmost version is not in a
 * version yet, and that is the section people work in.
 */
export function sections(changes) {
  const out = [];
  let head = null;
  let rows = [];
  changes.forEach((change, index) => {
    const marks = change.versions || [];
    if (marks.length) {
      if (rows.length || head) out.push({ versions: head, rows });
      head = marks;
      rows = [index];
    } else {
      rows.push(index);
    }
  });
  if (rows.length || head) out.push({ versions: head, rows });
  return out;
}

/**
 * A couple of names, and how many were left out.
 *
 * Measured on the test bench: eighteen versions sat on states equal to
 * the live one, and the chip listed every one of them - a label longer
 * than the row it labelled. A history that goes back and forth while
 * versions are made collects these, and the count is unbounded.
 *
 * Cut, never silently: the project's own rule for the explanation lists
 * is that a summary which omits without saying so is worse than a long
 * one. The tooltip carries all of them.
 */
export function someNames(names) {
  if (names.length <= 2) return joinNames(names);
  return `${names[0]} and ${names.length - 1} more`;
}

/**
 * A section head. Two versions can sit on the same state; both are
 * named rather than one of them being silently dropped.
 *
 * The button disappears when its target is what the dashboard holds
 * already - the same rule the row buttons follow, and for the same
 * reason: offering it there opens a dialog reading "No difference."
 * above a live Apply button.
 *
 * `here` is whether the newest change in this section is the state the
 * dashboard holds. It comes in rather than being worked out, because
 * working it out needs the change list and this function has only the
 * section.
 */
export function versionHead({ section, here, top }) {
  const [first, ...also] = section.versions;
  const count = section.rows.length;
  const extra = also
    .map((v) => `<span class="also">also ${escape(v.name)} — ${escape(v.title)}</span>`)
    .join("");
  // Two different truths, and one wording for both was an overclaim.
  // A version sitting on the newest entry *is* where the dashboard is.
  // A version further down whose state matches only holds the same
  // thing: going back to it wrote a newer entry, and that entry, not
  // this version, is where you are. Saying "current state" there
  // invites the reading Decision 9 exists to prevent.
  const back = here
    ? `<span class="count">${top === 0 ? "current state" : "same state as now"}</span>`
    : `<button class="act ghost" data-state="${escape(first.name)}"
               >Back to this version</button>`;
  return `
    <summary>
      <span class="name">${escape(first.name.split("/").pop())}</span>
      <span class="grow">${escape(first.title || first.name)}${extra}</span>
      <span class="count">${count} change${count === 1 ? "" : "s"}</span>
      ${back}
    </summary>`;
}

/**
 * One change, as a row.
 *
 * The word "state" in both chips is load-bearing, and it was missing.
 * A row says two things about two different subjects: the message is
 * about the *change*, the chip about the *state it left behind*. Read
 * as one sentence, "4 moved · same as now" is a contradiction - four
 * cards moved, and yet nothing differs? Both halves were true and the
 * row still misled, because nothing named what each half was about.
 *
 * `spokenFor` is the first row of a version section, whose head carries
 * the same chip a few pixels above it. Two identical labels stacked is
 * not emphasis, it is noise.
 *
 * `matching` are versions holding what this row's state holds without
 * sitting on it; `detail` is the already-built detail block, or "".
 */
export function renderRow({ change, index, spokenFor = false, matching = [], detail = "" }) {
  const chip =
    spokenFor || !change.same_as_now
      ? ""
      : index === 0
        ? `<span class="chip now"
               title="This is the state the dashboard holds right now."
               >current state</span>`
        : `<span class="chip sameas"
                 title="The change described here left the dashboard in exactly the state it holds right now."
                 >same state as now</span>`;
  // It says "identical in content to", never "is": going back to a
  // version writes a new entry, and this is that entry, not that version.
  const named = matching.length
    ? `<span class="chip ver"
             title="A different entry that holds exactly what ${escape(joinNames(matching))} holds. Going back to a version writes a new entry; this is that entry."
             >same state as ${escape(someNames(matching))}</span>`
    : "";
  return `
      <div class="card">
        <div class="change" data-index="${index}">
          <span class="what">${escape(change.description || change.message)}${chip}${named}
            ${change.description ? `<span class="auto">${escape(change.message)}</span>` : ""}
          </span>
          <span class="when">${escape(when(change.timestamp))}</span>
          <span class="rev">${escape(change.revision.slice(0, 7))}</span>
          <button class="pen" data-describe="${index}"
                  title="Describe this change">✎</button>
        </div>
        ${detail}
      </div>`;
}
```

`custom_components/dashboard_history/panel/dialogs.js` neu anlegen — die vier `<dialog>`-Blöcke wandern **wörtlich** aus `_render` hierher:

```js
/**
 * Every dialog the panel opens, as markup.
 *
 * Out of `_render` because they are the half of it that never changes:
 * the same four elements are in the shadow root whatever mode is on and
 * whichever dashboard is picked. What differs is what gets written into
 * their `.body` before they are shown, and that stays in the class,
 * where the data is.
 */

export const DIALOGS = `
  <dialog class="confirm">
    <h2></h2>
    <div class="body"></div>
    <div class="actions">
      <span class="note muted" style="margin-right:auto"></span>
      <button class="act ghost" value="cancel">Cancel</button>
      <button class="act" value="apply">Apply</button>
    </div>
  </dialog>
  <dialog class="forget">
    <h2>Forget this dashboard for good</h2>
    <div class="body"></div>
    <div class="actions">
      <button class="act ghost" value="cancel">Cancel</button>
      <button class="act danger" value="forget">Delete for good</button>
    </div>
  </dialog>
  <dialog class="describe">
    <h2>Describe this change</h2>
    <div class="body" style="padding:0 16px 8px">
      <input class="text" type="text" maxlength="200"
             placeholder="Why did you change this?">
      <p class="muted" style="font-size:13px">
        This becomes the headline of the entry. The automatic message
        stays below it. Leave it empty to remove the description.
      </p>
    </div>
    <div class="actions">
      <button class="act ghost" value="cancel">Cancel</button>
      <button class="act" value="save">Save</button>
    </div>
  </dialog>
  <dialog class="version">
    <h2>Create a version</h2>
    <div class="body" style="padding:0 16px 8px">
      <p class="muted" style="font-size:13px" data-scope></p>
      <p class="carries" data-carries hidden></p>
      <div class="levels">
        <button type="button" data-level="patch" aria-pressed="true">
          <strong></strong><span>Patch</span>
        </button>
        <button type="button" data-level="minor" aria-pressed="false">
          <strong></strong><span>Minor</span>
        </button>
        <button type="button" data-level="major" aria-pressed="false">
          <strong></strong><span>Major</span>
        </button>
      </div>
      <input class="text title" type="text" maxlength="200"
             placeholder="What is this version?">
      <input class="text desc" type="text" maxlength="500"
             style="margin-top:8px"
             placeholder="Anything more worth remembering (optional)">
    </div>
    <div class="actions">
      <button class="act ghost" value="cancel">Cancel</button>
      <button class="act" value="create">Create</button>
    </div>
  </dialog>`;
```

In `panel.js` den Ladeblock am Kopf erweitern:

```js
let STYLE;
let escape, renderDiff, renderPlain, when, joinNames;
let sections, someNames, renderRow, versionHead;
let DIALOGS;

const partsReady = Promise.all([
  import(`./panel/style.js${PARTS}`),
  import(`./panel/render.js${PARTS}`),
  import(`./panel/rows.js${PARTS}`),
  import(`./panel/dialogs.js${PARTS}`),
]).then(([style, render, rows, dialogs]) => {
  STYLE = style.STYLE;
  ({ escape, renderDiff, renderPlain, when, joinNames } = render);
  ({ sections, someNames, renderRow, versionHead } = rows);
  ({ DIALOGS } = dialogs);
});
```

Danach in `panel.js` löschen: `_sections`, `_someNames`, `_renderVersionHead`, `_renderRow` und die vier `<dialog>`-Blöcke in `_render`. An ihre Stelle treten die Aufrufe:

```js
  _renderRow(change, index, spokenFor = false) {
    return renderRow({
      change,
      index,
      spokenFor,
      matching: index === 0 ? this._matchingElsewhere(index) : [],
      detail: this._open === change.revision ? this._renderDetail(index) : "",
    });
  }
```

```js
  _renderVersionHead(section) {
    const top = section.rows[0];
    return versionHead({
      section,
      top,
      here: this._changes[top]?.same_as_now,
    });
  }
```

In `_render` ersetzt `${DIALOGS}` die vier gelöschten Blöcke. Dazu zwei Umbenennungen, beide vollständig durchzuziehen:

- **`this._sections()` wird zu `sections(…)` — und die lokale Variable muss weichen.** In `_renderMain` steht `const sections = this._sections();`. Bliebe der Name, hieße die Zeile `const sections = sections(this._changes);`, und das ist in einem Modul eine `ReferenceError: Cannot access 'sections' before initialization`. Die Variable heißt ab hier **`cut`** — nicht `parts`, denn den Namen trägt zwei Zeilen weiter schon die Liste der fertigen Abschnitte:

  ```js
    const cut = sections(this._changes);
    const newest = cut.find((s) => s.versions);
    …
    const parts = cut.map((section) => {
  ```

- **`this._someNames(...)` wird zu `someNames(...)` an *vier* Stellen**, nicht an zwei. Nachgezählt in `panel.js`: Zeile 938 und 940 in `_alreadyNamed`, Zeile 1159 in `_renderTopSection`, Zeile 1224 in `_renderRow`. Die letzte zieht mit `renderRow` nach `rows.js` um; die drei anderen bleiben in der Klasse und rufen ab hier die reine Funktion. Wer nur zwei anpasst, bekommt `this._someNames is not a function` — und zwar im Anlege-Dialog, den kein Test zeichnet.

**Die dünnen Umhüllungen bleiben absichtlich stehen.** `_renderRow` und `_renderVersionHead` sind zwei Zeilen, die nur zusammensuchen, was die reine Funktion braucht. Sie an ihren Aufrufstellen aufzulösen hieße, dieselben drei Zeilen dreimal zu haben — und die Aufrufstellen sind genau die, die in Aufgabe 5 einen zweiten Modus bekommen.

- [ ] **Schritt 4: Laufen lassen, Erfolg prüfen**

```bash
python3 -m pytest tests/ -q
```

Erwartet: unverändert **`286 passed, 3 skipped`** — diese Aufgabe legt keinen Test dazu. `tests/test_panel_behaviour.py` muss **ohne jede Anpassung** grün sein — das ist der Beweis, dass sich kein Verhalten geändert hat. Wer hier etwas anpassen muss, hat mehr verschoben als vorgesehen.

Danach der Augenschein, denn kein Test dieses Projekts zeichnet Markup:

```bash
docker compose -f docker/compose.yaml restart homeassistant
```

Das Panel öffnen, ein Dashboard wählen, eine Zeile aufklappen, den Versions-Dialog öffnen, einen Abschnitt zu- und aufklappen. Nichts davon darf anders aussehen als vorher.

- [ ] **Schritt 5: Committen**

```bash
git add custom_components/dashboard_history/panel/rows.js \
        custom_components/dashboard_history/panel/dialogs.js \
        custom_components/dashboard_history/panel.js \
        tests/test_panel_assets.py
git commit -m "$(cat <<'EOF'
Split the panel along what its pieces are for

Two modes in one file would put them where the most interface bugs
this project had have already been. The cut runs along responsibility
and not along the modes, because the modes share almost everything -
sections, heads, rows, dialogs are the same pieces differently filled,
and a cut by mode would have made two of each.

Pure functions only, the way render.js already works: data in, markup
out, no `this`. Whatever needs the element stays in the class. Nothing
behaves differently, and the Node tests prove it by passing unchanged.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Aufgabe 4: Blättern — »Ältere laden« und fünfundzwanzig

**Dateien:**
- Ändern: `custom_components/dashboard_history/panel.js`
- Test: `tests/test_panel_behaviour.py`

**Schnittstellen:**
- Verbraucht: `history` mit `limit` und `before`, Antwortfeld `next_cursor` (Vorhaben G).
- Liefert: `_cursor` im Zustand, `_loadOlder()` als Ablauf, `PAGE = 25` als Konstante.

**Jetzt fünfundzwanzig, nicht mehr fünfzig.** Vorhaben G hat den Vorgabewert absichtlich stehen lassen: Ihn zu senken, bevor es einen Weg zu den älteren Einträgen gibt, hätte dem Panel dreißig Änderungen weggenommen. Der Weg entsteht hier, also sinkt er hier. Gesetzt wird er vom Panel als `limit`, nicht im Schema — der Vorgabewert des Befehls bleibt 50 für Dienstaufrufe von Hand.

**Angehängt wird, nie ersetzt.** Und der Zeiger wird beim Wechsel des Dashboards und bei jedem Neuladen vergessen: Eine zweite Seite, die zu einer ersten von woanders passt, ergäbe eine Liste, die es nie gab.

- [ ] **Schritt 1: Die fehlschlagenden Tests schreiben**

In `tests/test_panel_behaviour.py` ans Ende anfügen:

```python
# Answered by *type*, never by position, and tolerantly: task 5 gives
# `_select` a second call, and a scenario that popped a fixed number of
# them would go red there for a reason that has nothing to do with
# paging. This shape survives both.
_HELD = """
const calls = [];
el._call = (type, extra) =>
  new Promise((resolve) => calls.push({ type, extra, resolve }));
const waiting = (type) => calls.find((c) => c.type === type);
const reply = (type, value) => {
  const at = calls.findIndex((c) => c.type === type);
  if (at >= 0) calls.splice(at, 1)[0].resolve(value);
};
const openOn = async (key, changes, cursor) => {
  const done = el._select(key);
  await settle();
  reply("versions", { versions: [] });
  reply("history", { changes, next_cursor: cursor });
  await done;
};
"""

_PAGING = """
const el = new Panel();
el._render = () => {};
""" + _HELD + """
await openOn("dash", [{ revision: "a" }, { revision: "b" }], "b");

const older = el._loadOlder();
await settle();
const askedFor = waiting("history").extra;
reply("history", {
  changes: [{ revision: "c" }, { revision: "d" }],
  next_cursor: null,
});
await older;

console.log(JSON.stringify({
  revisions: el._changes.map((c) => c.revision),
  askedFor,
  cursor: el._cursor,
}));
"""


@pytest.fixture(scope="session")
def paging(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "paging", _PAGING)


def test_older_entries_are_appended_and_not_substituted(paging):
    # Replacing would lose the page above and leave the list shorter
    # after pressing a button labelled "load older".
    assert paging["revisions"] == ["a", "b", "c", "d"]


def test_the_next_page_is_asked_for_by_cursor(paging):
    # By the cursor the server handed out, never by an offset: an offset
    # drifts when somebody saves while the page is being read.
    assert paging["askedFor"]["before"] == "b"
    assert paging["askedFor"]["limit"] == 25


def test_the_end_of_the_history_is_remembered(paging):
    # None means there is nothing older. The button goes away rather
    # than fetching an empty page for whoever presses it again.
    assert paging["cursor"] is None


_PAGING_RESET = """
const el = new Panel();
el._render = () => {};
""" + _HELD + """
await openOn("a-dash", [{ revision: "x" }], "x");
const between = el._cursor;

const two = el._select("b-dash");
await settle();
const askedFor = waiting("history").extra;
reply("versions", { versions: [] });
reply("history", { changes: [{ revision: "y" }], next_cursor: null });
await two;

console.log(JSON.stringify({
  between,
  askedFor,
  after: el._changes.map((c) => c.revision),
}));
"""


@pytest.fixture(scope="session")
def paging_reset(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "paging_reset", _PAGING_RESET)


def test_another_dashboard_starts_at_the_top_again(paging_reset):
    # A cursor from one dashboard handed to another would ask for the
    # entries after a commit that dashboard never had.
    assert paging_reset["between"] == "x"
    assert "before" not in paging_reset["askedFor"]
    assert paging_reset["after"] == ["y"]
```

- [ ] **Schritt 2: Laufen lassen, Fehlschlag prüfen**

```bash
python3 -m pytest tests/test_panel_behaviour.py -v
```

Erwartet: Die vier neuen Fälle schlagen fehl — `el._loadOlder is not a function`, und `_cursor` ist `undefined`.

- [ ] **Schritt 3: Umsetzen**

In `panel.js` neben den anderen Konstanten oben:

```js
// One page of history. Twenty-five and not fifty: a first screen is for
// finding your bearings, not for holding everything, and the button
// below it fetches the rest. Fifty stood until there *was* a button -
// lowering it earlier would have taken thirty entries off the panel and
// offered nothing to get them back with.
const PAGE = 25;
```

Im Konstruktor, hinter `this._changes = []`:

```js
    // Where the next page starts, or null when there is nothing older.
    // A commit and not a count: save something while somebody is
    // reading, and every offset below them shifts by one.
    this._cursor = null;
```

In `_select` den Abruf und das Schreiben ersetzen:

```js
    this._cursor = null;
    const result = await this._guard(
      () => this._call("history", { dashboard: key, limit: PAGE }),
      mine,
    );
    if (!mine()) return;
    this._changes = result ? result.changes || [] : [];
    this._cursor = result ? result.next_cursor ?? null : null;
    this._render();
```

In `_refresh` ebenso — der Zeiger wird verworfen und die erste Seite neu geholt:

```js
      const history = await this._call("history", {
        dashboard: asked,
        limit: PAGE,
      });
      if (!mine()) {
        this._render();
        return;
      }
      this._changes = history.changes || [];
      // Deliberately back to the first page. A refresh happens because
      // the history grew, and stitching a fresh top onto pages fetched
      // before it grew would show a list that never existed. Whoever had
      // loaded older entries presses the button again - which is honest,
      // and cheap, and the alternative is a list nobody can trust.
      this._cursor = history.next_cursor ?? null;
```

Und als neuen Ablauf, hinter `_select`:

```js
  /**
   * Fetch the page below the one that is showing, and append it.
   *
   * Appended, never substituted: the button says "load older", and a
   * list that got shorter after pressing it would be a lie told by a
   * label. The claim ticket is the same one `_select` uses, so a page
   * that arrives after somebody has picked another dashboard is dropped
   * rather than stitched under a stranger's history.
   */
  async _loadOlder() {
    if (!this._cursor || !this._selected) return;
    const mine = this._claim("changes");
    const asked = this._cursor;
    const result = await this._guard(
      () =>
        this._call("history", {
          dashboard: this._selected,
          limit: PAGE,
          before: asked,
        }),
      mine,
    );
    if (!mine() || !result) return;
    this._changes = this._changes.concat(result.changes || []);
    this._cursor = result.next_cursor ?? null;
    this._render();
  }
```

In `_renderMain`, ganz am Ende vor dem `return`, den Knopf anhängen:

```js
    const older = this._cursor
      ? `<div class="older">
           <button class="act ghost" data-older="1">Load older changes</button>
         </div>`
      : "";
    return banner + parts.join("") + older;
```

In `_render` bei der Verdrahtung:

```js
    root.querySelectorAll("[data-older]").forEach((element) =>
      element.addEventListener("click", () => this._loadOlder()),
    );
```

Und in `panel/style.js` eine Regel ergänzen, vor der schließenden Backtick-Zeile:

```css
.older { display:flex; justify-content:center; padding:12px 0 4px; }
```

- [ ] **Schritt 4: Laufen lassen, Erfolg prüfen**

```bash
python3 -m pytest tests/ -q
docker compose -f docker/compose.yaml restart homeassistant
python3 tests/integration/run_checks.py
```

Erwartet: **`290 passed, 3 skipped`** (vier mehr), Integrationsprüfungen grün. Dazu am Panel: ein Dashboard mit mehr als 25 Ständen wählen, den Knopf drücken, und sehen, dass die Liste wächst statt zu springen — und dass der Knopf am Ende der Historie verschwindet.

- [ ] **Schritt 5: Committen**

```bash
git add custom_components/dashboard_history/panel.js \
        custom_components/dashboard_history/panel/style.js \
        tests/test_panel_behaviour.py
git commit -m "$(cat <<'EOF'
Let the panel page through the history

Fifty entries and then a wall, with no way to say what was below it.
The server has handed out a cursor since project G; this reads it.

Twenty-five now, because there is finally somewhere to go from the
bottom of the page. A refresh drops back to the first page on purpose:
it happens because the history grew, and stitching a fresh top onto
pages fetched before it grew would draw a list that never existed.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Aufgabe 5: Der Moduswechsel und der einfache Modus

**Dateien:**
- Ändern: `custom_components/dashboard_history/panel.js`
- Anlegen: `custom_components/dashboard_history/panel/simple.js`
- Ändern: `custom_components/dashboard_history/panel/style.js`
- Test: `tests/test_panel_behaviour.py`, `tests/test_panel_assets.py`

**Schnittstellen:**
- Verbraucht: `dashboard_history/versions` mit `same_as_now` und `automatic` (H1), `matching_versions` (Vorhaben G).
- Liefert: `panel/simple.js` mit `renderSimple({versions, changes})`; im Zustand `_mode` (`"simple"` | `"advanced"`), `_versions` und `_matching`.
- Ablage: `localStorage["dashboard-history:mode"]`, Vorgabe `"simple"`.

**Der einfache Modus ist kein aufgeräumter erweiterter.** Er zeigt Versionen, nicht Änderungen. Die Liste kommt aus `versions` und ist damit **vollständig** — sie hängt nicht daran, wie weit jemand geblättert hat, und das ist der Befund, für den es Vorhaben G überhaupt gab. Die einzelnen Speichervorgänge liegen eingeklappt unter der Version, zu der sie gehören; sie stammen aus dem geladenen Fenster, und was noch nicht geladen ist, fehlt dort still — eine Version ohne geladene Änderungen zeigt nur ihren Kopf, und das ist richtig, weil der Kopf das ist, worauf man zurückspringt.

**Was er nicht anbietet:** keine Kurzhashes, keine Semver-Stufen im Text, keine gezielte Rücknahme, kein »Put back«, kein Diff im ersten Blick. An der Stelle der gezielten Rücknahme steht ein Satz, der auf den erweiterten Modus zeigt — die Spec verlangt genau das, und ein Modus, der eine Fähigkeit verschweigt statt sie zu verorten, macht aus einer Einschränkung ein Rätsel.

**Was er sehr wohl anbietet:** einen Rücksprung je Version, und einen Knopf, um den jetzigen Stand zu benennen. Beide Modi dürfen dasselbe schreiben; der einfache bietet nur weniger davon an, und das Benennen ist im einfachen Modus die Hauptwährung.

**Und hier wird eingelöst, was Vorhaben G geliefert hat.** `history` antwortet seit dessen Aufgabe 3 mit `matching_versions` — den Versionen, die inhaltlich halten, was das Dashboard gerade hält, **serverseitig über alle Versionen gerechnet**. Das Panel hat das Feld nie gelesen und rechnet dieselbe Frage in `_versionsMatchingNow()` selbst nach, über `this._changes`: also über das geladene Fenster. Eine Version vierhundert Einträge tiefer fällt dort heraus — genau der Befund, für den es Vorhaben G gab, und mit dem Fenster von fünfundzwanzig aus Aufgabe 4 trifft er häufiger. Diese Aufgabe legt das Feld in den Zustand und lässt `_versionsMatchingNow()` daraus lesen.

**Vorgabe ist der einfache Modus**, weil Entscheidung 17 ihn zum Normalweg erklärt. Wer den erweiterten gewohnt ist, schaltet einmal um, und die Wahl bleibt im Browser stehen. Ein `localStorage`, das nicht schreibbar ist — privates Fenster, gesperrte Website-Daten —, kostet nur die Erinnerung, nie die Anzeige: gelesen wird in einem `try`, und die Vorgabe steht bereit.

- [ ] **Schritt 1: Die fehlschlagenden Tests schreiben**

In `tests/test_panel_assets.py` die Liste erneut erweitern:

```python
    assert [path.name for path in PARTS] == [
        "dialogs.js",
        "render.js",
        "rows.js",
        "simple.js",
        "style.js",
    ]
```

In `tests/test_panel_behaviour.py` ans Ende anfügen — der Prelude kennt kein `localStorage`, also bekommt dieses Szenario eines:

```python
_MODE = """
const stored = {};
globalThis.localStorage = {
  getItem: (k) => (k in stored ? stored[k] : null),
  setItem: (k, v) => { stored[k] = String(v); },
};

const el = new Panel();
el._render = () => {};
const fresh = el._mode;

el._setMode("advanced");
const afterSwitch = el._mode;
const remembered = stored["dashboard-history:mode"];

const second = new Panel();
second._render = () => {};
const carried = second._mode;

// A stored value nobody recognises must not leave the panel blank.
stored["dashboard-history:mode"] = "sideways";
const third = new Panel();
third._render = () => {};

console.log(JSON.stringify({
  fresh, afterSwitch, remembered, carried, nonsense: third._mode,
}));
"""


@pytest.fixture(scope="session")
def mode(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "mode", _MODE)


def test_a_fresh_panel_opens_in_the_simple_mode(mode):
    # Decision 17 makes it the normal way. Somebody who wants the other
    # one switches once; somebody who needs this one would never look.
    assert mode["fresh"] == "simple"


def test_the_choice_is_remembered(mode):
    assert mode["afterSwitch"] == "advanced"
    assert mode["remembered"] == "advanced"
    assert mode["carried"] == "advanced"


def test_a_stored_value_nobody_recognises_falls_back(mode):
    # Anything can be in there - an older version of this panel, a hand
    # edit. A blank page would be the one unrecoverable answer.
    assert mode["nonsense"] == "simple"


_NO_STORAGE = """
globalThis.localStorage = {
  getItem() { throw new Error("site data is blocked"); },
  setItem() { throw new Error("site data is blocked"); },
};
const el = new Panel();
el._render = () => {};
const fresh = el._mode;
el._setMode("advanced");
console.log(JSON.stringify({ fresh, afterSwitch: el._mode }));
"""


@pytest.fixture(scope="session")
def no_storage(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "no_storage", _NO_STORAGE)


def test_a_browser_that_refuses_to_remember_still_shows_the_panel(no_storage):
    # A private window, or site data switched off. It costs the memory
    # of the choice and must never cost the page.
    assert no_storage["fresh"] == "simple"
    assert no_storage["afterSwitch"] == "advanced"


_VERSIONS_LOADED = """
const el = new Panel();
el._render = () => {};

const calls = [];
el._call = (type, extra) =>
  new Promise((resolve) => calls.push({ type, extra, resolve }));

const picked = el._select("dash");
await settle();
// Both are asked for at once; the order they answer in must not matter.
const types = calls.map((c) => c.type).sort();
calls.find((c) => c.type === "versions").resolve({
  versions: [{ name: "dash/v1.0.0", title: "1 September 2026", revision: "b" }],
});
calls.find((c) => c.type === "history").resolve({
  changes: [{ revision: "a" }, { revision: "b" }],
  next_cursor: null,
});
await picked;

console.log(JSON.stringify({
  types,
  versions: el._versions.map((v) => v.name),
  changes: el._changes.map((c) => c.revision),
}));
"""


@pytest.fixture(scope="session")
def versions_loaded(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "versions_loaded", _VERSIONS_LOADED)


def test_picking_a_dashboard_fetches_its_versions_too(versions_loaded):
    # The simple mode is built from the complete version list, not from
    # the versions that happen to sit on a loaded change - which is the
    # finding project G exists for.
    assert versions_loaded["types"] == ["history", "versions"]
    assert versions_loaded["versions"] == ["dash/v1.0.0"]
    assert versions_loaded["changes"] == ["a", "b"]
```

- [ ] **Schritt 2: Laufen lassen, Fehlschlag prüfen**

```bash
python3 -m pytest tests/test_panel_behaviour.py tests/test_panel_assets.py -v
```

Erwartet: `_mode` ist `undefined`, `_setMode` fehlt, `_versions` fehlt, und die Teileliste stimmt nicht.

- [ ] **Schritt 3: Umsetzen**

`custom_components/dashboard_history/panel/simple.js` neu anlegen:

```js
/**
 * The simple mode: versions, and the saves folded under them.
 *
 * Not a tidied version of the other one but a different offer. It
 * answers one question - "take me back to how it was" - and it answers
 * it with names and dates rather than with hashes and semver.
 *
 * The list is built from the *complete* set of versions, never from the
 * versions that happen to sit on a loaded change. A mark that vanishes
 * once its commit slides out of the window is the finding project G
 * exists for, and here it would be the whole mode going dark.
 */

const PARTS = new URL(import.meta.url).search;
const { escape, when } = await import(`./render.js${PARTS}`);

/**
 * `versions` is every version of this dashboard, newest number first
 * and complete. `changes` is the loaded window, newest first, and may
 * hold nothing at all for the older versions - which is why the head
 * carries the way back rather than the rows under it.
 */
export function renderSimple({ versions, changes }) {
  if (!versions.length)
    // The button and the way out come *with* the sentence. Behind an
    // early return they would not exist, and somebody in the default
    // mode with no versions yet would have neither a way to make one nor
    // a visible way to the other mode.
    return `<p class="empty muted">This dashboard has no versions yet.</p>
       <button class="act ghost" data-version="now">Save this as a version</button>
       <p class="why hint">Taking back a single step, or putting back one
         deleted card, lives in the advanced mode.
         <button class="linky" data-mode="advanced">Switch to it</button></p>`;

  // Where the dashboard stands, said in the only vocabulary this mode
  // has. `same_as_now` comes from the server and is worked out against
  // every version, so it is right whether or not that version's commit
  // is in the loaded window.
  const here = versions.filter((v) => v.same_as_now);
  const standing = here.length
    ? `The dashboard is in the state of ${escape(here[0].title || here[0].name)}.`
    : "The dashboard has changed since the last version was saved.";

  const rows = versions.map((version) => {
    // Its changes are the loaded ones from this version's own state
    // downwards, stopping at the next version. What has not been loaded
    // is simply not folded in; the head is what somebody goes back to,
    // and it is always there.
    const start = changes.findIndex((c) => c.revision === version.revision);
    const inside = [];
    if (start >= 0)
      for (let i = start; i < changes.length; i += 1) {
        if (i > start && (changes[i].versions || []).length) break;
        inside.push(changes[i]);
      }
    const folded = inside.length
      ? `<details class="steps">
           <summary>${inside.length} change${inside.length === 1 ? "" : "s"}
             in this version</summary>
           ${inside
        .map(
          (c) =>
            `<p class="step">${escape(c.description || c.message)}
                   <span class="when">${escape(when(c.timestamp))}</span></p>`,
        )
        .join("")}
         </details>`
      : "";
    // No button where its target is what the dashboard already holds.
    // A button that does nothing is a question without an answer.
    const back = version.same_as_now
      ? `<span class="count">where you are</span>`
      : `<button class="act ghost" data-state="${escape(version.name)}"
                 >Go back to this</button>`;
    const made = version.automatic
      ? `<span class="auto">saved automatically</span>`
      : "";
    return `<div class="vrow">
              <div class="vhead">
                <span class="grow">${escape(version.title || version.name)}${made}</span>
                ${back}
              </div>
              ${version.description
        ? `<p class="why">${escape(version.description)}</p>`
        : ""}
              ${folded}
            </div>`;
  });

  return `
    <div class="standing">
      <p class="heading">Right now</p>
      <p>${escape(standing)}</p>
      <button class="act ghost" data-version="now">Save this as a version</button>
    </div>
    ${rows.join("")}
    <p class="why hint">Taking back a single step, or putting back one
      deleted card, lives in the advanced mode.
      <button class="linky" data-mode="advanced">Switch to it</button></p>`;
}
```

In `panel.js` den Ladeblock am Kopf um den neuen Teil erweitern:

```js
let STYLE;
let escape, renderDiff, renderPlain, when, joinNames;
let sections, someNames, renderRow, versionHead;
let DIALOGS;
let renderSimple;

const partsReady = Promise.all([
  import(`./panel/style.js${PARTS}`),
  import(`./panel/render.js${PARTS}`),
  import(`./panel/rows.js${PARTS}`),
  import(`./panel/dialogs.js${PARTS}`),
  import(`./panel/simple.js${PARTS}`),
]).then(([style, render, rows, dialogs, simple]) => {
  STYLE = style.STYLE;
  ({ escape, renderDiff, renderPlain, when, joinNames } = render);
  ({ sections, someNames, renderRow, versionHead } = rows);
  ({ DIALOGS } = dialogs);
  ({ renderSimple } = simple);
});
```

Die Ablage des Modus, oben neben den Konstanten:

```js
// Where the chosen mode is remembered. In the browser and not in the
// config entry: the design record calls it a setting of the interface,
// and two admins in one house may reasonably want different ones. It
// costs no round trip, no reload and no restart.
const MODE_KEY = "dashboard-history:mode";
const MODES = ["simple", "advanced"];

/**
 * The remembered mode, or the simple one.
 *
 * Everything can throw here - a private window, site data switched off -
 * and every failure costs the memory of a choice and never the page.
 * An unrecognised value falls back too: an older version of this panel
 * or a hand edit must not be able to leave somebody with a blank page.
 */
function storedMode() {
  try {
    const found = localStorage.getItem(MODE_KEY);
    if (MODES.includes(found)) return found;
  } catch {
    // Nothing to do and nothing to report: the default is right here.
  }
  return "simple";
}
```

Im Konstruktor:

```js
    this._mode = storedMode();
    // Every version of the selected dashboard, whatever is loaded of its
    // changes. The simple mode is built from this and not from
    // `change.versions`, so that a version outside the window still
    // appears - which is the whole reason project G came first.
    this._versions = [];
    // The versions holding exactly what the dashboard holds now, worked
    // out by the server against *every* version. Read rather than
    // recomputed: doing it here means doing it over the loaded window,
    // and a version below that window is precisely the one that must
    // still be named.
    this._matching = [];
```

Der Wechsel, als Ablauf:

```js
  /**
   * Switch the mode and remember it, in that order.
   *
   * The switch itself never depends on the remembering: a browser that
   * refuses to store still shows the other mode for as long as the page
   * is open, which is the part somebody just asked for.
   */
  _setMode(mode) {
    if (!MODES.includes(mode)) return;
    this._mode = mode;
    try {
      localStorage.setItem(MODE_KEY, mode);
    } catch {
      // See `storedMode`. The choice holds for this page and no longer.
    }
    this._render();
  }
```

In `_select` beide Abrufe nebeneinander stellen — nicht nacheinander, weil sie voneinander nichts wissen:

```js
    this._cursor = null;
    this._versions = [];
    this._matching = [];
    const result = await this._guard(
      () =>
        Promise.all([
          this._call("history", { dashboard: key, limit: PAGE }),
          this._call("versions", { dashboard: key }),
        ]),
      mine,
    );
    if (!mine()) return;
    const [history, versions] = result || [null, null];
    this._changes = history ? history.changes || [] : [];
    this._cursor = history ? history.next_cursor ?? null : null;
    this._matching = history ? history.matching_versions || [] : [];
    this._versions = versions ? versions.versions || [] : [];
    this._render();
```

In `_refresh` denselben Doppelabruf, denn ein Rücksprung oder eine neue Marke ändert auch die Versionen. Die Zeile `const history = await this._call("history", …)` und das Schreiben darunter werden zu:

```js
      const [history, versions] = await Promise.all([
        this._call("history", { dashboard: asked, limit: PAGE }),
        this._call("versions", { dashboard: asked }),
      ]);
      if (!mine()) {
        this._render();
        return;
      }
      this._changes = history.changes || [];
      this._cursor = history.next_cursor ?? null;
      this._matching = history.matching_versions || [];
      this._versions = versions.versions || [];
```

Und `_versionsMatchingNow` liest ab hier das Feld, statt es nachzurechnen — der Rumpf wird ersetzt, der Docstring bekommt seinen letzten Absatz neu:

```js
  /**
   * `matching_versions` from the server, as the short names a chip
   * shows. Worked out there against every version of this dashboard,
   * which is the point: the same sum over `this._changes` would only
   * ever see the loaded window, and a version below it is exactly the
   * one that has to keep its name. That gap is what project G existed
   * to close, and until now the panel closed it again by ignoring the
   * answer.
   */
  _versionsMatchingNow() {
    return this._matching.map((v) => v.name.split("/").pop());
  }
```

In `_renderMain` die Weiche vor die vorhandene Bauerei setzen, direkt hinter dem `banner`:

```js
    if (this._mode === "simple")
      return (
        banner +
        renderSimple({ versions: this._versions, changes: this._changes })
      );
```

In die Leiste den Umschalter, in `_render` neben den Neuladen-Knopf:

```js
        <button class="mode" data-mode="${this._mode === "simple" ? "advanced" : "simple"}"
                >${this._mode === "simple" ? "Advanced view" : "Simple view"}</button>
```

Und die Verdrahtung:

```js
    root.querySelectorAll("[data-mode]").forEach((element) =>
      element.addEventListener("click", (event) => {
        event.stopPropagation();
        this._setMode(element.dataset.mode);
      }),
    );
```

Der Knopf »Save this as a version« trägt `data-version="now"`; die vorhandene Verdrahtung für `[data-version]` gibt `Number(...)` weiter, was hier `NaN` wäre. Sie bekommt deshalb eine Weiche:

```js
    root.querySelectorAll("[data-version]").forEach((element) =>
      element.addEventListener("click", (event) => {
        event.stopPropagation();
        // "now" is the simple mode's button, which means the newest
        // recorded state - index 0. The advanced mode names a row.
        const which = element.dataset.version;
        this._createVersion(which === "now" ? 0 : Number(which));
      }),
    );
```

In `panel/style.js` die Regeln für den neuen Modus ergänzen, vor der schließenden Backtick-Zeile:

```css
.mode { background:none; border:1px solid var(--divider-color,#444); color:inherit;
        border-radius:6px; padding:4px 10px; font-size:13px; cursor:pointer; }
.standing { border:1px solid var(--divider-color,#444); border-radius:10px;
            padding:12px 14px; margin-bottom:14px; }
.standing .heading { margin:0 0 4px; font-size:13px; opacity:.7; }
.standing p { margin:0 0 10px; }
.vrow { border-top:1px solid var(--divider-color,#333); padding:12px 2px; }
.vhead { display:flex; align-items:center; gap:10px; }
.vhead .auto { margin-left:8px; font-size:12px; opacity:.6; }
.steps { margin-top:8px; }
.steps summary { font-size:13px; opacity:.7; cursor:pointer; }
.step { margin:6px 0 0 14px; font-size:13px; display:flex; gap:10px; }
.step .when { margin-left:auto; opacity:.6; }
.hint { margin-top:18px; }
.linky { background:none; border:none; padding:0; color:inherit;
         text-decoration:underline; cursor:pointer; font:inherit; }
```

- [ ] **Schritt 4: Laufen lassen, Erfolg prüfen**

```bash
python3 -m pytest tests/ -q
docker compose -f docker/compose.yaml restart homeassistant
python3 tests/integration/run_checks.py
```

Erwartet: **`295 passed, 3 skipped`** (fünf mehr), Integrationsprüfungen grün. Dann der Augenschein, und zwar zuerst mit geleertem Speicher (privates Fenster oder Website-Daten löschen): Das Panel muss im einfachen Modus öffnen, eine Liste von Versionen zeigen, oben sagen, wo das Dashboard steht, und der Umschalter muss beim Neuladen bei seiner Wahl bleiben. Ein Dashboard mit über fünfzig Ständen und einer alten Version ist die eigentliche Probe: Die alte Version muss dastehen, obwohl ihr Commit nicht geladen ist.

- [ ] **Schritt 5: Committen**

```bash
git add custom_components/dashboard_history/panel.js \
        custom_components/dashboard_history/panel/simple.js \
        custom_components/dashboard_history/panel/style.js \
        tests/test_panel_behaviour.py \
        tests/test_panel_assets.py
git commit -m "$(cat <<'EOF'
Offer a mode that only knows versions

The tool showed short hashes, semver levels and raw YAML diffs. For a
developer that is the substance; for most people it is a hurdle in
front of one simple wish - put the dashboard back the way it was.

So the simple mode answers that one question in names and dates, with
the saves folded under the version they belong to, and points at the
advanced mode for taking back a single step rather than pretending it
does not exist. It is built from the complete version list and never
from the versions sitting on a loaded change, which is what project G
was for.

Remembered in the browser, because the design record calls the mode a
setting of the interface: no round trip, no reload, and two admins in
one house can differ. A browser that refuses to remember costs the
memory of the choice and never the page.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Aufgabe 6: Der Rücksprung fragt nach dem jetzigen Stand

**Dateien:**
- Ändern: `custom_components/dashboard_history/panel.js` (`_confirm`, `_restoreState`; neu: `today`, `_armKeep`, `_keepChoice`)
- Ändern: `custom_components/dashboard_history/panel/dialogs.js`
- Ändern: `custom_components/dashboard_history/panel/style.js`
- Test: `tests/test_panel_behaviour.py` (der Prelude und ein Szenario)

**Schnittstellen:**
- Verbraucht: `restore_state` mit `keep_as_version` (Aufgabe 1), `this._mode` (Aufgabe 5).
- Liefert: `_confirm(title, request, wantsKeep = false)`. `request` bekommt ab hier **zwei** Argumente — `request(confirm, keep)` —, wobei `keep` nur auf dem bestätigenden Aufruf gesetzt ist und sonst `null`. `_restoreItem` und `_undoChange` ignorieren das zweite Argument und bleiben Zeile für Zeile unverändert.
- Liefert: `_armKeep(show)` und `_keepChoice()` — die beiden einzigen Stellen dieses Ablaufs, die das DOM anfassen.
- Liefert: `_restoreState` gibt sein `_confirm` **zurück**, statt es fallen zu lassen.

**Ein Weg, nicht zwei.** Der Rücksprung bleibt in `_confirm`. Ein zweiter Bestätigungsablauf daneben hätte sechs Dinge verloren, die dort einzeln erkämpft wurden und alle in Kommentaren begründet sind: das Verstecken des Apply-Knopfes bei »already identical«, den Hinweis beim Wiederanlegen eines Dashboards, den Satz »was jetzt draufsteht, geht nicht verloren«, das eingeklappte technische Diff, das Warten auf den Rekorder vor dem Neuladen — und die Weitergabe von `error` und `note` an die Leiste, also ausgerechnet den Satz, den Aufgabe 1 sorgfältig zurückgibt. Jedes davon war einmal ein Fehlerbericht. Sie ein zweites Mal einzusammeln wäre der teuerste Weg, dieselbe Aufgabe zu lösen.

Was hinzukommt, ist deshalb ein **Argument**, kein Ablauf: `wantsKeep`. Nur der Rücksprung setzt es.

**»Verwerfen« heißt nicht löschen, sondern nicht markieren.** Das ist die eine Aussage, die dieser Dialog tragen muss, und sie liegt ganz in der Formulierung. Der Stand wird ohnehin vor jedem Schreibvorgang festgehalten; er bleibt in der Historie und ist im erweiterten Modus auffindbar. Er bekommt nur kein Tag — und ist damit im einfachen Modus nicht mehr zu sehen. Der Text sagt beides, ohne dem einfachen Modus eine Erklärung über Modi aufzubürden: **»Kept either way — without a name it is only findable in the advanced view.«**

**Angehakt ist die Vorgabe im einfachen Modus, abgehakt im erweiterten.** Wer im einfachen Modus arbeitet, sieht nur Versionen; ein nicht markierter Stand wäre für ihn verschwunden. Wer im erweiterten arbeitet, sieht ohnehin alles und sammelte sonst bei jedem Ausprobieren eine Marke.

**Die Stufe ist `patch`, das Titelfeld ist vorbelegt** mit dem heutigen Datum in derselben Schreibweise, die H1 für die selbsttätigen Marken benutzt — nur ohne deren Kennzeichnung, denn diese hier hat jemand gewollt.

**Gefragt wird nur, wo es etwas zu behalten gibt.** Zwei Fälle bleiben außen vor, und beide sind Fälle, in denen ein Kästchen nur enttäuschen könnte:

- **Beim Wiederanlegen eines gelöschten Dashboards** gibt es keinen lebenden Stand. Aufgabe 1 antwortet dort mit `{"created": null, "error": …}` — ein Kästchen, dessen einziger möglicher Ausgang ein Fehlschlag ist, ist schlechter als kein Kästchen.
- **Bei »already identical«** wird gar nichts ersetzt; `_confirm` versteckt dort bereits den Apply-Knopf.

**Und der Fehlschlag wird nicht doppelt erzählt.** Wo `_keep_the_live_state` eine Lücke meldet, reicht Aufgabe 1 genau diesen Satz in `kept_as_version.error` weiter — es ist derselbe Wortlaut, den `note` schon trägt. Die Leiste sagt ihn deshalb einmal.

**Womit das geprüft wird, und warum das ein Gewinn ist.** `_confirm` ist die folgenreichste Methode des Panels und bisher von keinem Test berührt, weil sie ein DOM braucht. Diese Aufgabe gibt `tests/test_panel_behaviour.py` einen Ersatz dafür — flach, fünfzehn Zeilen, gerade tief genug für einen Dialog. Damit wird zum ersten Mal geprüft, was bisher nur dastand: dass die Vorschau vor jedem Schreibvorgang kommt, dass das technische Diff immer im Dialog liegt, und dass ein mit Escape geschlossener Dialog nichts schreibt. Die zwei DOM-Zeilen selbst — Kästchen setzen, Kästchen lesen — liegen in `_armKeep` und `_keepChoice` und damit außerhalb dessen, was der Test nachbauen muss.

- [ ] **Schritt 1: Die fehlschlagenden Tests schreiben**

In `tests/test_panel_behaviour.py` oben `import re` neben die vorhandenen Importe setzen.

Den Prelude erweitern — der DOM-Ersatz und ein Durchlauf, bevor irgendein Szenario beginnt. Hinter der Hilfsfunktion `answer` anfügen:

```python
/**
 * A stand-in for one DOM node, deep enough for a dialog.
 *
 * Flat on purpose: every node answers a selector with a node of its
 * own, remembered per selector, and nothing looks inside anything
 * else. A scenario therefore has to query along the same path the code
 * does - `[data-keep]`, then `.keepbox`, never `.keepbox` straight from
 * the dialog - and that is the feature: a test that found a node the
 * code never touched would pass while proving nothing.
 */
const node = () => {
  const it = {
    textContent: "", innerHTML: "", value: "", checked: false,
    hidden: false, returnValue: "", open: false,
    _seen: {}, _on: {},
    querySelector(selector) {
      return (it._seen[selector] ||= node());
    },
    querySelectorAll(selector) { return [it.querySelector(selector)]; },
    addEventListener(name, run) { it._on[name] = run; },
    showModal() { it.open = true; },
    close(value) {
      it.open = false;
      // Exactly what a browser does: a value handed over by a button is
      // remembered, and a dialog dismissed with Escape leaves the last
      // one standing. That is the whole reason `_confirm` clears it
      // before opening.
      if (value !== undefined) it.returnValue = value;
      it._on.close?.();
    },
  };
  return it;
};

// One turn before any scenario starts. The parts arrive over dynamic
// imports, so `renderPlain` and `renderDiff` are still undefined in
// this module's first synchronous pass - measured on 2026-09-04: a
// scenario reaching either one dies with "renderPlain is not a
// function" before its first assertion, and the whole file goes red
// for a reason that has nothing to do with what it tests.
await settle();
```

Und ans Ende der Datei das Szenario:

```python
_KEEP = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._mode = "simple";
el._changes = [{ revision: "a" }, { revision: "b" }];
el.shadowRoot = node();
// A timer and a server event, neither of which says anything about
// what gets sent - and the three-second fallback would say it slowly.
el._recorded = () => Promise.resolve();

const sent = [];
el._call = (type, extra) => {
  sent.push({ type, extra });
  if (type === "restore_state" && !extra.confirm)
    return Promise.resolve({
      applied: false,
      preview: "-a\\n+b",
      explanation: { groups: [], note: "one card removed" },
    });
  return Promise.resolve({ applied: true, changes: [], dashboards: [] });
};

const dialog = () => el.shadowRoot.querySelector("dialog.confirm");
const box = () =>
  el.shadowRoot.querySelector("[data-keep]").querySelector(".keepbox");
const press = async (value) => {
  const done = el._restoreState("b", "Back to this version");
  await settle();
  const seen = {
    body: dialog().querySelector(".body").innerHTML,
    ticked: box().checked,
    title: box() && el.shadowRoot
      .querySelector("[data-keep]").querySelector(".keeptitle").value,
  };
  dialog().close(value);
  await done;
  return seen;
};

const simple = await press("apply");
const kept = sent.filter((c) => c.type === "restore_state" && c.extra.confirm);

el._mode = "advanced";
const advanced = await press("apply");
const plain = sent.filter((c) => c.type === "restore_state" && c.extra.confirm);

// Dismissed without pressing anything - Escape. The stand-in still
// carries "apply" from the run above, exactly as a browser would.
const before = sent.length;
await press(undefined);

console.log(JSON.stringify({
  previewFirst: sent[0].extra.confirm === false,
  diffShown: simple.body.includes("Show the technical details"),
  keepsShown: simple.body.includes("is not lost"),
  tickedInSimple: simple.ticked,
  offeredTitle: simple.title,
  clearInAdvanced: advanced.ticked,
  withKeep: kept[0].extra.keep_as_version ?? null,
  withoutKeep: plain[1].extra.keep_as_version ?? null,
  afterEscape: sent.length - before,
}));
"""


@pytest.fixture(scope="session")
def keeping(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "keeping", _KEEP)


def test_the_preview_is_fetched_before_anything_is_written(keeping):
    # The hard rule: nothing that writes a dashboard state goes without
    # a preview. Asking about a version does not change that.
    assert keeping["previewFirst"] is True


def test_the_dialog_carries_the_technical_diff_and_the_promise(keeping):
    # Both are load-bearing and both were once lost. The diff is the
    # exact account and the rule says it is always there; the sentence
    # about the present state answers the question somebody had to read
    # the source for.
    assert keeping["diffShown"] is True
    assert keeping["keepsShown"] is True


def test_the_box_follows_the_mode(keeping):
    # Simple mode: an unmarked state is invisible, so it is ticked.
    # Advanced mode: everything shows anyway, and a mark per experiment
    # would pile up.
    assert keeping["tickedInSimple"] is True
    assert keeping["clearInAdvanced"] is False


def test_a_name_is_offered_in_the_spelling_the_automatic_ones_use(keeping):
    # So that a list of versions reads as one list. Built by hand rather
    # than with toLocaleDateString, which follows the browser's language.
    assert re.fullmatch(r"\d{1,2} [A-Z][a-z]+ \d{4}", keeping["offeredTitle"])


def test_keeping_the_state_sends_a_version_with_the_restore(keeping):
    # One call, not two: the only moment the newest recorded state is
    # the one on the screen sits inside restore_state.
    assert keeping["withKeep"]["level"] == "patch"
    assert keeping["withKeep"]["title"] == keeping["offeredTitle"]


def test_discarding_sends_no_version_at_all(keeping):
    # "Discard" means "do not mark", never "delete". Sending nothing is
    # exactly that, and the state stays in the history either way.
    assert keeping["withoutKeep"] is None


def test_a_dialog_dismissed_without_a_button_writes_nothing(keeping):
    # Escape leaves the previous returnValue standing, so a dialog that
    # was confirmed once would confirm itself for ever after. Only the
    # preview may be fetched here - one call, and no second one.
    assert keeping["afterEscape"] == 1
```

- [ ] **Schritt 2: Laufen lassen, Fehlschlag prüfen**

```bash
python3 -m pytest tests/test_panel_behaviour.py -v
```

Erwartet: rot, und **nicht mit einem einzigen sauberen Wortlaut** — der Ablauf, den diese Aufgabe baut, gibt es noch nicht, also fällt das Szenario an der ersten Stelle um, die es erreicht. Verlässlich ist zweierlei: `_restoreState` gibt heute nichts zurück, auf das `press` warten könnte, und `keep_as_version` wird nirgends geschickt. Je nachdem, wie das Rennen ausgeht, endet der Lauf mit `TypeError: Cannot read properties of undefined (reading 'extra')` aus `kept[0]` in Node, oder pytest meldet `assert None == 'patch'`. Beides ist derselbe Befund. Die vier bestehenden Fälle der Datei müssen weiter grün sein — sie prüfen den erweiterten Prelude gleich mit.

- [ ] **Schritt 3: Umsetzen**

In `panel/dialogs.js` den Bestätigungsdialog um den Block erweitern, zwischen `.body` und `.actions`:

```js
    <div class="keep" data-keep hidden>
      <label>
        <input type="checkbox" class="keepbox">
        <span>Save the state you are leaving as a version</span>
      </label>
      <input class="text keeptitle" type="text" maxlength="200"
             placeholder="What to call it">
      <p class="muted" style="font-size:13px">
        Kept either way — without a name it is only findable in the
        advanced view. Nothing is deleted.
      </p>
    </div>
```

In `panel.js` die Hilfsfunktion oben im Modul, neben `storedMode`:

```js
// The same spelling the automatic versions use, so a list of them reads
// as one list. Built by hand rather than with toLocaleDateString, which
// follows the browser's language: two people in one house would
// otherwise name the same day differently.
const MONTHS = ["January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December"];

function today() {
  const now = new Date();
  return `${now.getDate()} ${MONTHS[now.getMonth()]} ${now.getFullYear()}`;
}
```

Die Signatur von `_confirm` erweitern:

```js
  /** Show the preview, and write only if the person says so. */
  async _confirm(title, request, wantsKeep = false) {
    const preview = await this._guard(() => this._call(...request(false, null)));
```

Hinter der Zeile, die `.note` beschreibt, und **vor** `dialog.returnValue = ""`, den Block einsetzen:

```js
    // Offered only where a whole state is replaced and there is one to
    // keep. Not while a dashboard is being recreated - there is no live
    // state then, and the answer for that case is an error; a tick box
    // whose only possible outcome is a failure is worse than none. Not
    // where nothing is applied either.
    const keepable = Boolean(
      wantsKeep && !nothingToDo && !preview.creates_dashboard,
    );
    this._armKeep(keepable);
```

Hinter `if (answer !== "apply") return;` die Wahl auslesen, bevor irgendetwas geschrieben wird:

```js
    const keep = keepable ? this._keepChoice() : null;
```

Den bestätigenden Aufruf die Wahl mitgeben — in `const applied = await this._guard(async () => {` wird `request(true)` zu:

```js
      const result = await this._call(...request(true, keep));
```

Und den `said`-Block ersetzen:

```js
    // `kept_as_version.error` repeats `note` word for word where the
    // live state could not be recorded - operations hands the one into
    // the other - so it is only worth saying where it says something
    // else.
    const failed = applied?.kept_as_version?.error;
    const keptFailed =
      failed && failed !== applied?.note
        ? `the dashboard went back, but no version was made: ${failed}`
        : "";
    const said =
      applied?.error ||
      // And a refusal on the confirming call as well, which is the one
      // that matters: the undo re-proves itself there, so this is the
      // answer somebody gets instead of a write.
      (applied?.available === false
        ? applied.reason || "this cannot be taken back exactly"
        : "") ||
      applied?.note ||
      keptFailed ||
      "";
```

Die beiden neuen Methoden hinter `_confirm` einfügen:

```js
  /**
   * Show the block that offers to keep the state being replaced, or
   * hide it again.
   *
   * Its own method, and so is `_keepChoice`, for one reason: these two
   * are the only lines of this flow that touch an element. Everything
   * else about it - which call goes first, what rides on the confirming
   * one, whether anything is written at all - is logic, and logic
   * belongs where tests/test_panel_behaviour.py reaches it.
   *
   * Ticked in the simple mode, clear in the advanced one. Somebody in
   * the simple mode sees nothing but versions, so an unmarked state is
   * gone as far as they are concerned; somebody in the advanced mode
   * sees everything anyway and would otherwise collect a mark for every
   * experiment.
   */
  _armKeep(show) {
    const keep = this.shadowRoot.querySelector("[data-keep]");
    if (!keep) return;
    keep.hidden = !show;
    if (!show) return;
    keep.querySelector(".keepbox").checked = this._mode === "simple";
    keep.querySelector(".keeptitle").value = today();
  }

  /**
   * The version to make, or null for none.
   *
   * Patch, and never a level somebody has to choose: this is a
   * waypoint, not a milestone, and a three-way choice in front of a
   * restore is a question nobody came here to answer.
   */
  _keepChoice() {
    const keep = this.shadowRoot.querySelector("[data-keep]");
    const box = keep?.querySelector(".keepbox");
    if (!box?.checked) return null;
    const title = keep.querySelector(".keeptitle").value.trim();
    return { level: "patch", title: title || today() };
  }
```

Und `_restoreState` selbst:

```js
  _restoreState(revision, title) {
    // Returned rather than dropped, unlike its two neighbours: the Node
    // scenario waits for it, and a flow whose end nobody can wait for
    // cannot be tested at all.
    return this._confirm(
      title,
      (confirm, keep) => [
        "restore_state",
        {
          dashboard: this._selected,
          revision,
          confirm,
          // Left out entirely when nothing is to be marked. An empty
          // object would be a request for a version with no name, which
          // the server would then have to refuse.
          ...(keep ? { keep_as_version: keep } : {}),
        },
      ],
      true,
    );
  }
```

**`_restoreItem` und `_undoChange` bleiben unverändert.** Ihre `request`-Funktionen nehmen ein Argument, bekommen zwei und sehen das zweite nie — das ist in JavaScript keine Auslassung, sondern der Normalfall. Und sie *sollen* nicht fragen: »Put back« und die gezielte Rücknahme ersetzen keinen ganzen Stand, es bleibt also kein Stand übrig, den zu benennen sich lohnte.

In `panel/style.js` ergänzen:

```css
.keep { padding:0 16px 8px; }
.keep label { display:flex; align-items:center; gap:8px; margin-bottom:8px; }
```

- [ ] **Schritt 4: Laufen lassen, Erfolg prüfen**

```bash
python3 -m pytest tests/ -q
docker compose -f docker/compose.yaml restart homeassistant
python3 tests/integration/run_checks.py
```

Erwartet: **`301 passed, 3 skipped`** (sechs mehr), Integrationsprüfungen grün. Am Panel beide Wege gehen:

- Im **einfachen** Modus zurückspringen, das Kästchen angehakt lassen — die neue Version muss danach oben in der Liste stehen, mit dem heutigen Datum als Titel.
- Im **erweiterten** Modus zurückspringen und es abhaken — es darf keine neue Version geben, und der ersetzte Stand muss als Änderung weiterhin in der Liste stehen. Das ist die Test-Plan-Zeile »Rücksprung mit »verwerfen««, und sie ist nur mit den Augen zu prüfen.
- Ein gelöschtes Dashboard über **»Bring it back«** zurückholen: Dort darf **kein** Kästchen erscheinen, und der Hinweis »This recreates the dashboard, with its old title and icon.« muss weiterhin neben den Knöpfen stehen.
- Und einmal **»Undo this change«** öffnen — auch dort kein Kästchen.

- [ ] **Schritt 5: Committen**

```bash
git add custom_components/dashboard_history/panel.js \
        custom_components/dashboard_history/panel/dialogs.js \
        custom_components/dashboard_history/panel/style.js \
        tests/test_panel_behaviour.py
git commit -m "$(cat <<'EOF'
Ask what becomes of the state being replaced

Going back is the moment somebody most wants a name on what they are
leaving, and until now there was nowhere to put one.

Sent with the restore rather than made beforehand, because only the
server can get the order right. Ticked by default in the simple mode,
where an unmarked state is invisible, and clear in the advanced one,
where everything shows anyway and a mark per experiment would pile up.
Not offered at all where there is no live state to keep.

An argument to _confirm rather than a second confirming flow beside
it. That one method carries six things this project learned the hard
way - the hidden Apply, the recreate note, the promise that nothing is
lost, the folded diff, the wait for the recorder, the answer passed on
to the banner - and each of them was a bug report once.

The wording carries the rest: discarding means not marking, never
deleting. The state is recorded before every write either way.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Aufgabe 7: Zeilen adressieren sich über ihre Revision

**Dateien:**
- Ändern: `custom_components/dashboard_history/panel.js`
- Ändern: `custom_components/dashboard_history/panel/rows.js`
- Test: `tests/test_panel_behaviour.py`

**Schnittstellen:**
- Verbraucht: `previous` je Zeile (Aufgabe 2).
- Liefert: `_changeAt(revision)` — die Änderung zu einer Revision, oder `null`. Alle zeilenbezogenen Methoden nehmen ab hier eine **Revision** oder die Änderung selbst statt einer Position: `_expand`, `_describe`, `_createVersion`, `_undoChange`, `_restoreItem`, `_detailFor`, `_renderDetail`, `_renderSetBack`, `_renderMakeVersion`, `_alreadyNamed`, `_matchingElsewhere`.
- Liefert: `renderRow` zeichnet `data-revision` statt `data-index` und bekommt `newest` statt `index`.
- Entfällt: `_before(index)`.

**Warum das vor dem Suchfeld steht.** Das Panel adressiert eine Zeile heute über ihre Position im Array `this._changes`: Das Markup trägt `data-index="3"`, der Klick liest die Zahl zurück und schlägt damit nach. Das trägt, solange es genau eine Liste gibt. Aufgabe 8 führt eine zweite ein — die Trefferliste —, und ab da bedeutet »Position 3« in der gezeichneten Liste etwas anderes als in der nachgeschlagenen. Diese Aufgabe nimmt die Position aus dem Spiel, **bevor** es eine zweite Liste gibt. Danach ist das Suchfeld eine Anzeigefrage und keine Adressierungsfrage mehr.

**Diese Aufgabe ändert kein Verhalten — mit einer Ausnahme, und die ist eine Behebung.** `_before(index)` gab für die unterste Zeile jeder geladenen Seite `null` zurück, obwohl deren Vorgänger in der Historie liegt. Diese Zeile bot deshalb keine gelöschten Karten zum Zurückholen an. Mit `change.previous` aus Aufgabe 2 tut sie es. Alles andere muss aussehen und sich verhalten wie vorher; `tests/test_panel_behaviour.py` bleibt in seinen vorhandenen Fällen unangetastet.

**Zwei Dinge, die eine Position wirklich meint, bekommen eigene Namen.** Nicht jedes `index` war eine Adresse:

- **»bin ich der neueste Eintrag«** — davon hängen die Aufschrift der Plakette (»current state« gegen »same state as now«), der Satz »The dashboard holds exactly this state again right now« und die Frage ab, ob eine inhaltsgleiche Version genannt wird. Das wird `newest`, und das Panel rechnet es aus `change.revision === this._changes[0]?.revision` aus.
- **»wie viele Änderungen sind seither gemacht worden«** — der Halbsatz »and keeps the 3 changes made since« im Rücknahme-Angebot. Das ist eine Zählung über die geladene Historie, keine über die gezeigte Liste. `_madeSince(change)` beantwortet sie und antwortet mit `null`, wenn die Änderung gar nicht im geladenen Fenster liegt; dann entfällt der Halbsatz. Eine Zahl, die man nicht kennt, wird nicht geraten.

**Eine benannte Grenze.** `_renderSetBack` fragt heute, ob der Stand *vor* dieser Änderung der ist, den das Dashboard hält — über `this._changes[index + 1]?.same_as_now`. Nachgeschlagen wird das ab hier über `this._changeAt(change.previous)?.same_as_now`. Liegt der Vorgänger nicht im geladenen Fenster, ist die Antwort `undefined` und der Hinweis entfällt. Das ist **genau das heutige Verhalten** an dieser Stelle, nur ehrlicher begründet: Auch `this._changes[index + 1]` gab es dort nicht.

- [ ] **Schritt 1: Die fehlschlagenden Tests schreiben**

In `tests/test_panel_behaviour.py` ans Ende anfügen:

```python
_ADDRESSING = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
// The bottom row of a page: its predecessor is a revision the panel has
// never loaded, which is the ordinary case as soon as anybody pages.
el._changes = [
  { revision: "a", previous: "b", message: "" },
  { revision: "b", previous: "c", message: "" },
];

const asked = [];
el._call = (type, extra) => {
  asked.push({ type, extra });
  return Promise.resolve({ items: [], groups: [], available: false });
};

await el._expand("b");
const bottom = {
  types: asked.map((c) => c.type).sort(),
  against: asked.find((c) => c.type === "deleted_since")?.extra.revision,
  open: el._open,
};

// And the very first recorded state, which has nothing before it.
asked.length = 0;
el._changes = [{ revision: "z", previous: null, message: "" }];
el._open = null;
await el._expand("z");
const first = { types: asked.map((c) => c.type).sort() };

console.log(JSON.stringify({ bottom, first }));
"""


@pytest.fixture(scope="session")
def addressing(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "addressing", _ADDRESSING)


def test_a_row_is_opened_by_its_revision_and_asks_against_its_own_predecessor(
    addressing,
):
    # Worked out from the row below, the bottom row of every page said
    # "there is nothing before this" and offered no deleted cards to put
    # back. The predecessor is in the row now, so it asks against it.
    assert addressing["bottom"]["open"] == "b"
    assert addressing["bottom"]["against"] == "c"
    assert addressing["bottom"]["types"] == ["deleted_since", "explain", "undo_change"]


def test_the_first_recorded_state_asks_about_nothing_before_it(addressing):
    # There genuinely is nothing there, and asking would be asking about
    # a revision that does not exist.
    assert addressing["first"]["types"] == ["explain", "undo_change"]
```

- [ ] **Schritt 2: Laufen lassen, Fehlschlag prüfen**

```bash
python3 -m pytest tests/test_panel_behaviour.py -v
```

Erwartet: Beide neuen Fälle scheitern. `_expand` nimmt heute eine Zahl, `el._expand("b")` liest also `this._changes["b"]` — `undefined` —, und der Zugriff auf `.revision` darauf beendet den Lauf in Node. Die vorhandenen Fälle bleiben grün.

- [ ] **Schritt 3: Umsetzen**

Der Umbau ist mechanisch und betrifft eine abzählbare Liste von Stellen. Der Reihe nach.

**`_before` ersatzlos löschen** und stattdessen den Nachschlag einfügen, an derselben Stelle:

```js
  /**
   * The loaded change with this revision, or null.
   *
   * A row addresses itself by revision and not by its place in a list.
   * The place was a fine address while there was exactly one list; the
   * search box makes a second one, and then "row 3" means two different
   * rows depending on who is asking.
   */
  _changeAt(revision) {
    return this._changes.find((c) => c.revision === revision) || null;
  }

  /**
   * How many loaded changes are newer than this one, or null when it is
   * not in the loaded window at all.
   *
   * A count over the history, never over whatever list is on screen. It
   * carries the half-sentence "and keeps the 3 changes made since", and
   * where the number is not known the half-sentence goes rather than
   * being guessed.
   */
  _madeSince(change) {
    const at = this._changes.findIndex((c) => c.revision === change.revision);
    return at < 0 ? null : at;
  }

  /** Whether this is the newest recorded state of this dashboard. */
  _isNewest(change) {
    return Boolean(change) && change.revision === this._changes[0]?.revision;
  }
```

**`_expand`** nimmt eine Revision:

```js
  async _expand(revision) {
    const change = this._changeAt(revision);
    if (!change) return;
    if (this._open === revision) {
      this._claim("detail"); // closing it makes any answer in flight stale
      this._open = null;
      this._render();
      return;
    }
    const mine = this._claim("detail");
    this._open = revision;
    this._items = [];
    this._explanation = null;
    this._undo = null;
    const detail = await this._guard(() => this._detailFor(change), mine);
    if (!mine()) return;
    this._take(detail);
    this._render();
  }
```

**`_detailFor`** nimmt die Änderung und liest ihren Vorgänger aus ihr:

```js
  /** The three answers a row's detail is built from. */
  _detailFor(change) {
    return Promise.all([
      change.previous
        ? this._call("deleted_since", {
          dashboard: this._selected,
          revision: change.previous,
        })
        : Promise.resolve({ items: [] }),
      this._call("explain", {
        dashboard: this._selected,
        revision: change.revision,
      }),
      this._call("undo_change", {
        dashboard: this._selected,
        revision: change.revision,
      }),
    ]);
  }
```

**In `_refresh`** wird der offene Zeilenzustand über die Revision gesucht statt über den Index:

```js
      const open = this._changeAt(this._open);
      if (!open) {
        this._claim("detail");
        this._open = null;
        this._items = [];
        this._explanation = null;
        this._undo = null;
      } else {
        const detailMine = this._claim("detail");
        const detail = await this._detailFor(open);
        if (!detailMine()) return;
        this._take(detail);
      }
```

**Die drei Auslöser** nehmen Revisionen beziehungsweise Änderungen:

```js
  _restoreItem(change, item) {
    this._confirm(`Put back: ${item.label}`, (confirm) => [
      "restore_deleted",
      {
        dashboard: this._selected,
        revision: change.previous,
        position: item.position,
        confirm,
      },
    ]);
  }

  _undoChange(revision) {
    this._confirm("Undo this change", (confirm) => [
      "undo_change",
      { dashboard: this._selected, revision, confirm },
    ]);
  }
```

```js
  async _describe(revision) {
    const change = this._changeAt(revision);
    if (!change) return;
```

```js
  async _createVersion(revision) {
    const change = this._changeAt(revision);
    if (!change) return;
```

und darin `this._alreadyNamed(index)` zu `this._alreadyNamed(change)`.

**Die drei Zeilen-Helfer** nehmen die Änderung statt der Position — in `_alreadyNamed`, `_matchingElsewhere` und `_renderMakeVersion` entfällt jeweils die erste Zeile `const change = this._changes[index];`:

```js
  _alreadyNamed(change) {
    if (!change) return "";
    const carried = (change.versions || []).map((v) => v.name.split("/").pop());
    if (carried.length) return `This state already carries ${someNames(carried)}.`;
    const alike = this._matchingElsewhere(change);
    if (alike.length) return `This is the same state as ${someNames(alike)}.`;
    return "";
  }

  _matchingElsewhere(change) {
    if (!change || !change.same_as_now) return [];
    const own = (change.versions || []).map((v) => v.name.split("/").pop());
    return this._versionsMatchingNow().filter((name) => !own.includes(name));
  }

  _renderMakeVersion(change) {
    const named = this._alreadyNamed(change);
    return `<div class="mkver">
        <button class="act ghost" data-version="${escape(change.revision)}"
                >Version up to here</button>
        ${named ? `<span class="named">${escape(named)}</span>` : ""}
      </div>`;
  }
```

**`_renderSetBack`** und **`_renderDetail`** nehmen die Änderung:

```js
  _renderSetBack(change) {
    const before = change.previous;
    const buttons = [];
    const same = this._undo?.available && this._undo.equals_state_before;
    // Where the predecessor is outside the loaded window this is
    // `undefined` and the button stays - exactly what happened before,
    // when `this._changes[index + 1]` was not there either.
    if (before && !this._changeAt(before)?.same_as_now && !same)
      buttons.push({
        revision: before,
        label: "Back to the state before this change",
      });
    if (!change.same_as_now)
      buttons.push({
        revision: change.revision,
        label: "Back to the state after this change",
      });

    const why =
      before && this._changeAt(before)?.same_as_now
        ? `<span class="why">The state before this change is what the
            dashboard holds now — nothing to set back.</span>`
        : "";
```

```js
  _renderDetail(change) {
    const here =
      !this._isNewest(change) && change.same_as_now
        ? `<p class="why" style="margin-top:0">The dashboard holds exactly this
             state again right now.</p>`
        : "";
    const plain =
      here + renderPlain(this._explanation, "What this change did");
    const before = change.previous;
    if (!before)
      return `<div class="detail">${plain}<p class="muted">This is the first
        recorded state, so there is nothing before it to compare against.</p>
        ${this._renderMakeVersion(change)}</div>`;
```

Weiter unten in derselben Methode `this._changes[index]?.message` zu `change.message`, und den Halbsatz mit der Zählung:

```js
    // Left out where the number is not known - a row from outside the
    // loaded window has no place in it to count from, and a guessed
    // number in a sentence about what is kept would be the worst kind.
    const made = this._madeSince(change);
    const kept =
      made ? ` and keeps the ${made} change${made === 1 ? "" : "s"} made since` : "";
    const offer = undo
      ? `<div class="backto">
           <button class="act" data-undo="${escape(change.revision)}">Undo this change</button>
         </div>
         <p class="why" style="margin-top:8px">Puts this change back${kept}.</p>`
```

und am Ende `this._renderSetBack(change)` sowie `this._renderMakeVersion(change)`.

**In `panel/rows.js`** trägt `renderRow` die Revision statt der Position und bekommt gesagt, ob sie die neueste ist:

```js
export function renderRow({ change, newest = false, spokenFor = false, matching = [], detail = "" }) {
  const chip =
    spokenFor || !change.same_as_now
      ? ""
      : newest
        ? `<span class="chip now"
               title="This is the state the dashboard holds right now."
               >current state</span>`
        : `<span class="chip sameas"
                 title="The change described here left the dashboard in exactly the state it holds right now."
                 >same state as now</span>`;
```

```js
      <div class="card">
        <div class="change" data-index="${escape(change.revision)}">
```

wird zu

```js
      <div class="card">
        <div class="change" data-revision="${escape(change.revision)}">
```

und der Stift zu `data-describe="${escape(change.revision)}"`.

**Die Umhüllungen in `panel.js`:**

```js
  _renderRow(change, spokenFor = false) {
    const newest = this._isNewest(change);
    return renderRow({
      change,
      newest,
      spokenFor,
      matching: newest ? this._matchingElsewhere(change) : [],
      detail: this._open === change.revision ? this._renderDetail(change) : "",
    });
  }
```

In `_renderMain` und `_renderTopSection` werden die Indizes der Abschnitte in die Änderungen aufgelöst, aus der Liste, aus der die Abschnitte gebildet wurden:

```js
      const rows = section.rows
        .map((index, position) =>
          this._renderRow(this._changes[index], position === 0),
        )
        .join("");
```

```js
    const rows = section.rows.map((index) =>
      this._renderRow(this._changes[index]),
    );
```

und in `_renderVersionHead` `here: this._changes[top]?.same_as_now` sowie `top === 0` bleiben, wie sie sind — der Abschnittskopf spricht über die geladene Historie, und `sections` bekommt in dieser Aufgabe noch immer genau die.

**Die Verdrahtung in `_render`:**

```js
    root.querySelectorAll(".change").forEach((element) =>
      element.addEventListener("click", () =>
        this._expand(element.dataset.revision),
      ),
    );
    root.querySelectorAll("[data-restore]").forEach((element) =>
      element.addEventListener("click", () => {
        const change = this._changeAt(this._open);
        const item = this._items.find(
          (candidate) => candidate.position === Number(element.dataset.restore),
        );
        if (change && item) this._restoreItem(change, item);
      }),
    );
```

```js
    root.querySelectorAll("[data-undo]").forEach((element) =>
      element.addEventListener("click", (event) => {
        event.stopPropagation();
        this._undoChange(element.dataset.undo);
      }),
    );
```

```js
    root.querySelectorAll("[data-describe]").forEach((element) =>
      element.addEventListener("click", (event) => {
        event.stopPropagation();
        this._describe(element.dataset.describe);
      }),
    );
    root.querySelectorAll("[data-version]").forEach((element) =>
      element.addEventListener("click", (event) => {
        event.stopPropagation();
        // "now" is the simple mode's button, which means the newest
        // recorded state. Everything else names a revision.
        const which = element.dataset.version;
        this._createVersion(
          which === "now" ? this._changes[0]?.revision : which,
        );
      }),
    );
```

- [ ] **Schritt 4: Laufen lassen, Erfolg prüfen**

```bash
python3 -m pytest tests/ -q
docker compose -f docker/compose.yaml restart homeassistant
python3 tests/integration/run_checks.py
```

Erwartet: **`303 passed, 3 skipped`** (zwei mehr), alle Integrationsprüfungen grün. Und dann der Augenschein, denn diese Aufgabe verspricht Gleichheit und kein Test zeichnet Markup — ein Dashboard mit mehr als 25 Ständen wählen und:

- eine Zeile aufklappen, »Undo this change« drücken, den Dialog abbrechen;
- den Stift drücken, eine Beschreibung speichern — sie muss an *dieser* Zeile erscheinen;
- »Version bis hierher« an einer mittleren Zeile öffnen und abbrechen;
- »Ältere laden« drücken und die **unterste Zeile der ersten Seite** aufklappen: Sie muss jetzt ihren Vergleich haben, wo sie vorher »This is the first recorded state« behauptete;
- im einfachen Modus »Save this as a version« öffnen und abbrechen.

- [ ] **Schritt 5: Committen**

```bash
git add custom_components/dashboard_history/panel.js \
        custom_components/dashboard_history/panel/rows.js \
        tests/test_panel_behaviour.py
git commit -m "$(cat <<'EOF'
Address a row by its revision, not by its place

A row carried its index into the markup and every click read that index
back. That is a fine address while there is exactly one list, and the
search box coming next makes a second one - after which "row 3" means
two different rows depending on who is asking.

Two things that really were positions keep a name of their own: whether
this is the newest recorded state, and how many changes were made since
this one. The second answers null outside the loaded window, and the
half-sentence about what is kept goes rather than guessing a number.

Nothing looks different, with one exception that is a fix: the bottom
row of a page used to work out its predecessor from the row below it,
found none, and so offered no deleted cards to put back. It reads the
predecessor from itself now.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Aufgabe 8: Das Suchfeld — jeder Modus durchsucht, was er zeigt

**Dateien:**
- Ändern: `custom_components/dashboard_history/panel.js`
- Ändern: `custom_components/dashboard_history/panel/simple.js`
- Ändern: `custom_components/dashboard_history/panel/style.js`
- Test: `tests/test_panel_behaviour.py`

**Schnittstellen:**
- Verbraucht: `dashboard_history/search` aus Aufgabe 2.
- Liefert: `_query`, `_found` (`null`, solange der Server nicht gefragt wurde), `_moreFound`, `_searching`, `_typing`; `_search(text)`, `_localMatches()`, `_shown()`, `_matchingVersions()`.

**Die eine Regel: jeder Modus durchsucht, was er zeigt.** Der einfache Modus zeigt Versionen, also filtert das Feld dort die Versionsliste. Der erweiterte zeigt Änderungen, also sucht es dort über Änderungen. Ein Feld, das je nach Modus etwas anderes findet, klingt zunächst nach zwei Sachen — es ist aber die einzige Fassung, in der niemand eine Trefferliste bekommt, die aus seinem Modus herausfällt. Die Alternative wäre gewesen, im einfachen Modus Zeilen mit Kurzhashes, Stift und Rücknahme einzublenden: also genau das, wovor Entscheidung 17 den einfachen Modus bewahren soll.

**Im einfachen Modus braucht es keinen Server.** `this._versions` ist die **vollständige** Liste dieses Dashboards — dafür gab es Vorhaben G. Ein Filter darüber ist vollständig, ohne eine einzige Anfrage, und kann »nichts gefunden« wahrheitsgemäß sagen. Gesucht wird in Titel, Beschreibung und Nummer, also in genau dem, was die Zeile zeigt.

**Im erweiterten Modus in zwei Stufen, und warum in dieser Reihenfolge.** Die erste filtert, was das Panel schon geladen hat — das antwortet ohne Netz und deckt fast jede Suche ab, denn wonach man sucht, hat man meist eben gelesen. Erst wenn sie nichts findet, geht die Frage an den Server, der die ganze Historie läuft. Damit ist die schnelle Antwort schnell, die vollständige vollständig, und »nichts gefunden« heißt am Ende wirklich nichts — statt »nichts unter den fünfundzwanzig geladenen«, was dieselbe unsichtbare Lücke wäre, gegen die dieses Projekt an drei anderen Stellen schon angetreten ist.

**Die lokale Stufe sucht dasselbe wie die entfernte.** Meldung, eigene Beschreibung und die Versionen auf der Zeile — sonst fände die erste Stufe weniger als die zweite und eskalierte für einen Treffer, den sie längst hatte.

**Entprellt, und nicht bei jedem Tastendruck.** Der Serverlauf kostet rund eine halbe Sekunde je tausend Commits. Er startet erst, wenn seit dem letzten Tastendruck 400 ms vergangen sind, die lokale Suche nichts gefunden hat und mindestens zwei Zeichen dastehen.

**Gesagt wird, welche Stufe geantwortet hat.** Ohne das wäre eine leere Trefferliste zweideutig und eine volle sagte nicht, wie weit sie gesehen hat.

**Die Trefferliste ist flach.** Keine Versions-Abschnitte: `sections()` schneidet die Historie an Marken, und über einer gefilterten Liste erzeugte das Köpfe, die »3 changes in this version« über drei Treffern behaupten. Und »Ältere laden« entfällt, solange gesucht wird — eine Seite an eine Trefferliste zu hängen ergäbe eine Liste, die es nie gab.

**Der Suchzustand gehört zum Dashboard.** Beim Wechsel wird er verworfen, samt einem noch laufenden Aufschub: Ein Tastendruck, dessen 400 ms erst nach dem Wechsel ablaufen, schickte sonst den alten Text an das neue Dashboard.

- [ ] **Schritt 1: Die fehlschlagenden Tests schreiben**

In `tests/test_panel_behaviour.py` ans Ende anfügen:

```python
_SEARCH = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._mode = "advanced";
el._changes = [
  { revision: "a", message: "1 card added", description: "", versions: [] },
  { revision: "b", message: "2 views removed", description: "the rework",
    versions: [{ name: "dash/v1.0.0", title: "Winter rebuild" }] },
];
el._versions = [
  { name: "dash/v1.0.0", title: "Winter rebuild", description: "notes" },
  { name: "dash/v0.9.0", title: "Autumn", description: "" },
];

const asked = [];
el._call = (type, extra) => {
  asked.push(type);
  return Promise.resolve({ changes: [{ revision: "z", message: "old rework" }] });
};

await el._search("views");
const local = { shown: el._shown().map((c) => c.revision), asked: [...asked] };

await el._search("rework");
const own = el._shown().map((c) => c.revision);

await el._search("winter");
const byVersion = el._shown().map((c) => c.revision);

await el._search("needle");
const remote = { shown: el._shown().map((c) => c.revision), asked: [...asked] };

await el._search("");
const cleared = { shown: el._shown().map((c) => c.revision), found: el._found };

// The simple mode filters the complete version list, without a server.
el._mode = "simple";
asked.length = 0;
await el._search("autumn");
const simple = {
  names: el._matchingVersions().map((v) => v.name),
  asked: [...asked],
};

// Picking another dashboard drops the search with everything else.
el._call = () => Promise.resolve({ changes: [], next_cursor: null, versions: [] });
await el._select("other");
const afterSwitch = { query: el._query, found: el._found };

console.log(JSON.stringify({
  local, own, byVersion, remote, cleared, simple, afterSwitch,
}));
"""


@pytest.fixture(scope="session")
def searching(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "search", _SEARCH)


def test_a_hit_in_what_is_loaded_never_reaches_the_server(searching):
    # The common case, and it must cost nothing: what somebody searches
    # for is usually what they have just read.
    assert searching["local"]["shown"] == ["b"]
    assert searching["local"]["asked"] == []


def test_a_persons_own_description_is_searched_too(searching):
    # Both are what a row shows, and nobody remembers which of the two
    # they read.
    assert searching["own"] == ["b"]


def test_a_version_sitting_on_a_row_is_searched_too(searching):
    # The same four things the server looks at. A first step that found
    # less than the second would escalate for a hit it already had.
    assert searching["byVersion"] == ["b"]


def test_nothing_loaded_matching_asks_the_whole_history(searching):
    # "Nothing found" has to mean nothing found, not "nothing among the
    # twenty-five that happen to be loaded".
    assert searching["remote"]["asked"] == ["search"]
    assert searching["remote"]["shown"] == ["z"]


def test_clearing_the_box_goes_back_to_the_plain_list(searching):
    # An empty box is not a search for everything; it is no search.
    assert searching["cleared"]["shown"] == ["a", "b"]
    assert searching["cleared"]["found"] is None


def test_the_simple_mode_filters_versions_without_asking_anybody(searching):
    # `_versions` is the complete list, so a filter over it is complete
    # too - which is exactly what project G was for.
    assert searching["simple"]["names"] == ["dash/v0.9.0"]
    assert searching["simple"]["asked"] == []


def test_picking_another_dashboard_drops_the_search(searching):
    # A cursor from one dashboard handed to another was already refused;
    # a query is the same mistake with a different name.
    assert searching["afterSwitch"]["query"] == ""
    assert searching["afterSwitch"]["found"] is None
```

- [ ] **Schritt 2: Laufen lassen, Fehlschlag prüfen**

```bash
python3 -m pytest tests/test_panel_behaviour.py -v
```

Erwartet: `el._search is not a function`, und der Lauf endet in Node, bevor eine Zusicherung greift.

- [ ] **Schritt 3: Umsetzen**

Im Konstruktor, hinter `this._versions = []`:

```js
    // What is in the search box, what the server answered (null while it
    // was never asked), whether it is being asked right now, and the
    // pending keystroke timer.
    this._query = "";
    this._found = null;
    this._moreFound = false;
    this._searching = false;
    this._typing = null;
```

In `_select`, neben den anderen Rücksetzungen:

```js
    this._query = "";
    this._found = null;
    this._moreFound = false;
    // A keystroke whose 400 ms run out after the switch would send the
    // old word to the new dashboard.
    clearTimeout(this._typing);
    this._typing = null;
```

Die Abläufe, hinter `_loadOlder`:

```js
  /**
   * Search in two steps: what is loaded, then the whole history.
   *
   * The first step answers without a round trip and covers almost every
   * search, because what somebody looks for is usually what they have
   * just read. The second exists so that "nothing found" means nothing
   * found - the panel holds twenty-five entries, and letting that decide
   * the answer would be the same invisible gap this project has closed
   * three times elsewhere.
   *
   * The simple mode never gets here past the first line: it filters the
   * complete version list, which needs nobody's help to be complete.
   */
  async _search(text) {
    this._query = text;
    this._found = null;
    this._moreFound = false;
    if (
      this._mode === "simple" ||
      !text.trim() ||
      text.trim().length < 2 ||
      this._localMatches().length
    ) {
      this._render();
      return;
    }
    const mine = this._claim("changes");
    this._searching = true;
    this._render();
    const result = await this._guard(
      () =>
        this._call("search", { dashboard: this._selected, text, limit: 100 }),
      mine,
    );
    // Cleared before the claim is checked, not after: a search that has
    // been superseded still has to put its own indicator out. The other
    // way round, a run whose claim was taken by something that is not a
    // search - `_loadOlder`, say - would leave "Searching the whole
    // history…" standing for good.
    this._searching = false;
    if (!mine()) return;
    this._found = result ? result.changes || [] : [];
    this._moreFound = result ? Boolean(result.more) : false;
    this._render();
  }

  /** The words a row is searched by: its own, and its versions'. */
  _wordsOf(change) {
    return [
      change.message || "",
      change.description || "",
      ...(change.versions || []).flatMap((v) => [
        (v.name || "").split("/").pop(),
        v.title || "",
        v.description || "",
      ]),
    ]
      .join("\n")
      .toLowerCase();
  }

  /** The loaded changes whose words hold the query. */
  _localMatches() {
    const needle = this._query.trim().toLowerCase();
    if (!needle) return [];
    return this._changes.filter((c) => this._wordsOf(c).includes(needle));
  }

  /**
   * The versions the query matches - the simple mode's whole search.
   *
   * Over `_versions`, which is complete, so this needs no second step
   * and no server: there is no window here that a search could fall out
   * of.
   */
  _matchingVersions() {
    const needle = this._query.trim().toLowerCase();
    if (!needle) return this._versions;
    return this._versions.filter((v) =>
      [(v.name || "").split("/").pop(), v.title || "", v.description || ""]
        .join("\n")
        .toLowerCase()
        .includes(needle),
    );
  }

  /**
   * What the advanced list should show: the plain history, the local
   * hits, or what the server found. One place decides it, so no
   * renderer has to.
   */
  _shown() {
    if (!this._query.trim()) return this._changes;
    const local = this._localMatches();
    if (local.length) return local;
    return this._found || [];
  }
```

In `_renderMain` die Weiche für den einfachen Modus so lassen, wie Aufgabe 5 sie gesetzt hat, und ihr die gefilterten Versionen geben:

```js
    if (this._mode === "simple")
      return (
        banner +
        renderSimple({
          versions: this._matchingVersions(),
          changes: this._changes,
          searching: Boolean(this._query.trim()),
        })
      );
```

Darunter, im erweiterten Modus, die gezeigte Liste:

```js
    const shown = this._shown();
    if (!shown.length)
      return `${banner}<p class="empty muted">${this._query.trim()
        ? "Nothing matches."
        : "No changes recorded for this dashboard."}</p>`;
```

Solange gesucht wird, ist die Liste **flach** und der Knopf für ältere Einträge weg:

```js
    if (this._query.trim())
      return (
        banner +
        shown.map((change) => this._renderRow(change)).join("")
      );
```

Der Rest von `_renderMain` bleibt, wie er ist, und arbeitet weiter über `sections(this._changes)`: Er wird nur noch ohne Suche erreicht.

In `panel/simple.js` bekommt `renderSimple` das Kennzeichen und sagt es im Leerfall:

```js
export function renderSimple({ versions, changes, searching = false }) {
  if (!versions.length)
    return searching
      ? `<p class="empty muted">No version matches.</p>`
      : `<p class="empty muted">This dashboard has no versions yet.</p>
         <button class="act ghost" data-version="now">Save this as a version</button>
         <p class="why hint">Taking back a single step, or putting back one
           deleted card, lives in the advanced mode.
           <button class="linky" data-mode="advanced">Switch to it</button></p>`;
```

In `_render` das Feld über die Hauptspalte setzen:

```js
      <div class="main">
        ${this._selected ? this._renderSearch() : ""}
        ${this._renderMain()}
      </div>
```

```js
  _renderSearch() {
    const said = this._searchNote();
    return `<div class="search">
        <input class="text find" type="search" maxlength="100"
               placeholder="${this._mode === "simple"
        ? "Search this dashboard's versions"
        : "Search this dashboard's history"}"
               value="${escape(this._query)}">
        ${said ? `<span class="why">${escape(said)}</span>` : ""}
      </div>`;
  }

  /**
   * Which of the two steps answered. Without it an empty result is
   * ambiguous, and a full one does not say how far it looked.
   */
  _searchNote() {
    if (!this._query.trim()) return "";
    if (this._mode === "simple") {
      const hits = this._matchingVersions().length;
      return `${hits} of ${this._versions.length} versions.`;
    }
    if (this._searching) return "Searching the whole history…";
    const local = this._localMatches();
    if (local.length)
      return `${local.length} of the ${this._changes.length} loaded entries.`;
    if (this._found === null) return "";
    if (!this._found.length) return "Nothing in the whole history.";
    return this._moreFound
      ? `The first ${this._found.length} in the whole history.`
      : `${this._found.length} in the whole history.`;
  }
```

Die Verdrahtung, mit dem Aufschub:

```js
    const find = root.querySelector("input.find");
    if (find) {
      // Focus survives the re-render this typing causes; without it the
      // box would lose the caret on every keystroke.
      if (this._query) find.focus();
      find.setSelectionRange?.(find.value.length, find.value.length);
      find.addEventListener("input", () => {
        clearTimeout(this._typing);
        const text = find.value;
        // 400 ms, and only then. A walk over the whole history costs
        // about half a second per thousand commits, and firing it per
        // keystroke would spend that eight times for one word.
        this._typing = setTimeout(() => this._search(text), 400);
      });
    }
```

In `panel/style.js`:

```css
.search { display:flex; align-items:center; gap:12px; margin-bottom:12px; }
.search .find { flex:1; }
```

- [ ] **Schritt 4: Laufen lassen, Erfolg prüfen**

```bash
python3 -m pytest tests/ -q
docker compose -f docker/compose.yaml restart homeassistant
python3 tests/integration/run_checks.py
```

Erwartet: **`309 passed, 3 skipped`** (sechs mehr), Integrationsprüfungen grün. Am Panel, im **erweiterten** Modus: ein Wort aus einer sichtbaren Zeile eingeben — die Liste engt sich sofort ein und der Hinweis nennt »of the … loaded entries«. Dann ein Wort, das nur weit hinten vorkommt — nach kurzer Pause muss der Hinweis auf »in the whole history« wechseln und der Treffer erscheinen. Dann der Titel einer alten Version: Der Treffer muss die Änderung sein, auf der sie sitzt, und ihre Plakette tragen. Ein Unsinnswort muss »Nothing in the whole history« ergeben, nicht bloß eine leere Liste. Und ein aufgeklappter Treffer muss seinen Vergleich haben — das ist Aufgabe 7, hier zum ersten Mal an einer Zeile aus dem Nichts.

Im **einfachen** Modus: dasselbe Feld, aber es filtert die Versionen, es fragt nie nach und der Hinweis zählt »x of y versions«. Danach das Dashboard wechseln: Das Feld muss leer sein.

- [ ] **Schritt 5: Committen**

```bash
git add custom_components/dashboard_history/panel.js \
        custom_components/dashboard_history/panel/simple.js \
        custom_components/dashboard_history/panel/style.js \
        tests/test_panel_behaviour.py
git commit -m "$(cat <<'EOF'
Give each mode a search over what it shows

The simple mode shows versions, so the box filters versions - over the
complete list, which needs no server and cannot fall out of a window.
The advanced mode shows changes, so it searches changes: first what is
loaded, which answers without a round trip and covers almost every
search, then the whole history when that found nothing.

That second step is the point. The panel holds twenty-five entries, and
a search that stopped there would say "nothing found" about a history
holding the word four hundred entries down - the same invisible gap
this project has closed three times elsewhere, wearing a search box.

Both steps look at the same four things, a version's words included, so
the fast one never escalates for a hit it already had. The note under
the field says which step answered, because an empty result is
otherwise ambiguous and a full one does not say how far it looked.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Wenn alle acht stehen

`python3 -m pytest tests/ -v` (`309 passed, 3 skipped` ohne echte Ablage — siehe die Vorbemerkung zur Testzahl) und `python3 tests/integration/run_checks.py` müssen beide vollständig grün sein. Dazu der Augenschein, denn kein Test dieses Projekts zeichnet Markup — die Liste steht in den Schritten 4 der Aufgaben 3, 5, 6, 7 und 8.

Damit ist Vorhaben H fertig, und mit ihm die beiden GitHub-Issues:

- Das Panel öffnet im einfachen Modus, zeigt Versionen mit Datum, und der Weg zurück ist ein Knopf je Version.
- Eine Version verschwindet nicht mehr, weil ihr Commit aus dem Fenster gerutscht ist — weder aus der Liste noch als Plakette.
- Die Historie blättert über einen Commit-Zeiger, fünfundzwanzig auf einmal.
- Die Suche findet, was da ist, und sagt, wo sie gesucht hat — ein Wort findet die Worte einer Änderung ebenso wie den Titel einer Version.
- Jede Zeile kennt den Stand vor sich, auch die unterste einer Seite, und bietet dort erstmals ihre gelöschten Karten an.
- Ein Rücksprung kann den Stand benennen, den er ersetzt, und die Marke sitzt auf dem richtigen.

## Was danach offen bleibt

Damit es nicht als Versäumnis gelesen wird, sondern als das, was es ist — Arbeit mit eigener Begründung:

- **Vorhaben F**, die Identitätskette aus Entscheidung 16. Die Spec ordnet es ausdrücklich hinter H ein: Es dient der gezielten Rücknahme einzelner Stücke, die es im einfachen Modus gar nicht gibt.
- **Vorhaben C**, das Aufräumen — und dort die Entscheidung, die H1 ihm hinterlässt: Automatische Tagesversionen machen jeden Tagesendstand unantastbar, weil ein Tag die Schutzmarke ist. Die Spec sagt, das sei vermutlich genau richtig, müsse dort aber bewusst dastehen statt sich unbemerkt zu ergeben.
- **Vorhaben D**, die sechs Befunde am älteren Kern. Zwei davon wiegen schwerer als alles, was in G und H repariert wurde: das unterbrechbare `forget` und die Verschmelzung zweier Dashboards mit demselben `url_path`.
- **Eine Löschzeile ist als solche nicht erkennbar.** Der einfache Modus umgeht das, weil er keine Zeilenknöpfe hat; im erweiterten steht es unverändert offen.
