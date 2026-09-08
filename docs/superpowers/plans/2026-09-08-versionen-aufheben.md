# Versionen aufheben — Umsetzungsplan (Vorhaben I)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eine Version lässt sich aufheben — die Marke verschwindet, der Stand darunter bleibt unangetastet in der Historie.

**Architecture:** Ein `del refs/tags/<name>` im Herzen, umgeben von dem Zaun und den Ablehnungssätzen, die das Umbenennen schon hat. Fünf Schichten in der bestehenden Reihenfolge — `store` → `operations` → `websocket_api` + `services` → `panel` —, jede ohne eigene Logik außer der einen darunter. Kein neues Stück Zustand im Repository, keine Umschreibung der Historie, keine Revision ändert sich.

**Tech Stack:** Python 3.12 (Entwicklung) / 3.14 (Container), dulwich 1.2.14 ohne Systemaufruf von `git`, Home Assistant 2026.8.3, ES-Module ohne Bündler im Panel, pytest, Node für die Panel-Logik.

**Spec:** `docs/superpowers/specs/2026-08-30-dashboard-history-design.md` — **Entscheidung 18** ist die tragende; dazu Entscheidung 7 (zweite Seite), Entscheidung 13 (Nummern und Punkt 3), Entscheidung 17 (»Verwerfen heißt nicht markieren«).

## Global Constraints

Aus der Spec und `CLAUDE.md`, wörtlich, und für **jede** Aufgabe dieses Plans gültig:

- **Kein Systemaufruf von `git`.** Ausschließlich `dulwich`.
- **Keine Home-Assistant-Interna abfangen oder ersetzen.** Kein Monkey-Patching.
- **Nichts blockiert den Start von Home Assistant.** Fehler beim Erfassen werden protokolliert und verschluckt.
- **`yaml_io.py`, `analyze.py`, `restore.py` und `versions.py` bleiben Home-Assistant-frei.** Kein `import homeassistant` darin.
- **Blockierende Arbeit gehört in einen Executor** (`hass.async_add_executor_job`).
- **`forget` bleibt die einzige Operation, die einen Stand wegnimmt.** Der ersetzte Prüfstein aus Entscheidung 13: *Was einen Stand wegnimmt, heißt `forget` — und es bleibt bei dem einen.*
- **Sprache:** Code, Kommentare, Docstrings, Dienstbeschreibungen, Log-Meldungen, Panel-Texte, README, FAQ und **Commit-Botschaften** auf **Englisch**. Dieses Plandokument und die Spec auf Deutsch. Commit-Format: Subject im Imperativ, erster Buchstabe groß, max. 50 Zeichen; Leerzeile; Body max. 72 Zeichen je Zeile, begründet das *Warum*; Abschluss `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- **Nicht committen, pushen oder taggen ohne ausdrückliche Ansage des Nutzers.** Die Commit-Schritte in diesem Plan sind vorbereitet, nicht freigegeben.
- **Tests:** `python3 -m pytest tests/ -v` muss durchlaufen. Ausgangsstand dieses Plans: **489 bestanden** (2026-09-08).

---

## Dateien und wer wofür zuständig ist

| Datei | Rolle in diesem Vorhaben |
|---|---|
| `custom_components/dashboard_history/store.py` | Das Herz: `_version_from` (neu, geteilt), `read_version`, `remove_version`. Der Zaun `_owns` ist da. |
| `custom_components/dashboard_history/operations.py` | `async_remove_version`: Vorschau ohne `confirm`, Aufheben mit. Kein neues Wissen, nur die Reihenfolge. |
| `custom_components/dashboard_history/websocket_api.py` | Ein Befehl mehr in `_COMMANDS`, nach dem Muster von `retitle_version` plus `confirm`. |
| `custom_components/dashboard_history/services.py` | Ein Handler und eine Zeile in `registrations`. |
| `custom_components/dashboard_history/services.yaml` | Ein Eintrag, damit der Dienst in den Developer Tools Namen und Felder hat. |
| `custom_components/dashboard_history/panel/rows.js` | `bin(version)` neben `pen(version)` — dieselbe Steuerung für beide Modi, andere Sichtbarkeitsregel. |
| `custom_components/dashboard_history/panel/simple.js` | `bin(version)` in die Kopfzeile, neben `pen(version)`. |
| `custom_components/dashboard_history/panel/dialogs.js` | Ein sechster Dialog `dialog.remove`. |
| `custom_components/dashboard_history/panel/style.js` | Eine Regel für `.bin`; die Sichtbarkeit erbt es über die Klasse `pen`. |
| `custom_components/dashboard_history/panel.js` | `_removeVersion(name)` und eine `onClick`-Verdrahtung. |
| `tests/test_store.py` | Die Ränder des Herzens, in reinem pytest. |
| `tests/test_versions.py` | Dass die freigewordene Nummer wiederkommt. Kein Produktionscode dafür. |
| `tests/test_integration_files.py` | **Neu:** dass jeder registrierte Dienst einen `services.yaml`-Eintrag hat. Der Grund steht in Aufgabe 2. |
| `tests/test_panel_behaviour.py` | Der Dialogzweig in Node und die zwei Sichtbarkeitsregeln. |
| `tests/integration/run_checks.py` | Der Weg durch echtes Home Assistant. |
| `tests/integration/run_day_marks.py` | Die Rückkehr der aufgehobenen Tagesmarke. |
| `tests/integration/look_at_panel.py` | Dass der neue Knopf auf dem Schirm zu finden ist, gelesen als berechnete Deckkraft. Der Grund steht in Aufgabe 3, Schritt 9. |
| `FAQ.md`, `README.md`, `const.py` | Sechs Sätze, die falsch werden, und eine Liste, die einen Dienst mehr hat. Welche, steht in Aufgabe 5. |

**Warum diese Aufteilung und keine feinere:** Die Schnittstellen-Schicht (`websocket_api`, `services`, `services.yaml`) ist eine Aufgabe und nicht drei. Sie hat einen einzigen Prüfstein — der Dienst ist von außen aufrufbar und heißt in der Oberfläche, wie er heißt —, und ein Prüfer, der zwei der drei Dateien abnimmt und die dritte nicht, hat nichts abgenommen.

---

## Was vorher gemessen wurde, damit niemand es nachmisst

Die ersten vier Befunde stammen aus dem Entwurfsgespräch vom 2026-09-08, die weiteren aus der Review-Runde desselben Tages (siehe den Nachtrag am Ende). Alle tragen Entscheidungen dieses Plans und sind **nicht erneut zu prüfen**:

1. **Eine Version kostet rund 202 Bytes** (Tag-Objekt + Ref-Datei, Titel und zweizeilige Beschreibung), ein Stand rund 2500 Bytes im Wegwerf-Repository und 28 KiB an der echten Anlage. Deshalb geht es hier **nicht** um Größe.
2. **`_survey` und `_index` müssen nicht verworfen werden.** Beide sind nach HEAD verschlüsselt und aus dem Commit-Lauf gebaut; keiner von beiden liest `refs/tags`. `forget` verwirft sie, weil es *Commits* umschreibt — das tut hier nichts. Nachgelesen in `store.py`: `_survey` hält `Survey(names, live, last_meta)` aus Bäumen und Blobs, `_index` trägt sich über HEAD-Bewegungen fort.
3. **`del repo.refs[ref]` ist der Weg**, und er wird in `_rewrite_tags` bereits so benutzt. Kein `garbage_collect` dahinter: das alte Tag-Objekt bleibt lose liegen, wie es `retitle_version` schon hinterlässt.
4. **Eine aufgehobene Tagesmarke kann zurückkommen**, und nur die des Tages, den der nächste Speichervorgang abschließen würde. `_async_mark_day` liest `end_of_previous_day` über die letzten `_RECENT = 20` Stände; der findet den jüngsten *früheren* Tag, nicht einen beliebigen. Nachgesehen: `milestones.py` hält keinen Zustand darüber, welche Tage schon markiert wurden — der zweite Aufruf liest die Lage neu, sonst wäre die Prüfung in Task 4, Schritt 3 wirkungslos.
5. **Der Ausgangsstand ist 489**, gemessen. Und der Produktionscode aus Task 1 ist **probeweise angewandt und gelaufen**: die zehn Store-Fälle und die zwei `candidates`-Fälle bestehen, und die Gesamtzahl bleibt danach bei 489 — die `_version_from`-Extraktion ist also verhaltensgleich, genau wie Schritt 4 zusagt. Wieder zurückgenommen.
6. **Der `services.py`↔`services.yaml`-Test besteht heute**: 14 registrierte Dienste, 14 beschriebene, beide Differenzen leer. Die Regex übermatcht in `services.py` nichts, und `pyyaml` ist über Home Assistants Abhängigkeiten da.
7. **`el.shadowRoot` ist im Node-Stellvertreter `undefined`.** `_PRELUDE` gibt `attachShadow()` ein `{}` zurück, und `panel.js` verwirft den Rückgabewert. Deshalb steht in Task 3 die Zuweisung im Szenario; ohne sie stirbt der Lauf mit `TypeError`.
8. **`_repo()` nimmt kein Lock**, also gibt es unter `self._lock` kein Deadlock — `threading.Lock` ist nicht reentrant, und das war die Frage. Ebenso nachgezählt: es gibt genau **drei** `pen(`-Aufrufstellen im Panel (rows.js 94 und 118, simple.js 282), keine vierte.

---

## Task 1: Das Herz — eine Version lesen und aufheben

**Files:**
- Modify: `custom_components/dashboard_history/store.py` (neue Funktion `_version_from` neben `_version_words`, ~Zeile 148; `list_versions` ~Zeile 1743 darauf umstellen; `read_version` und `remove_version` hinter `retitle_version`, ~Zeile 552)
- Test: `tests/test_store.py`, `tests/test_versions.py`

**Interfaces:**
- Consumes: `_owns(ref: bytes, key: str) -> bool`, `_version_words(message: bytes | None) -> tuple[str, str]`, `_as_text`, `Version`, `HistoryStore._repo`, `HistoryStore._lock` — alle vorhanden.
- Produces:
  - `_version_from(name: str, target) -> Version` (Modulfunktion, nicht öffentlich)
  - `HistoryStore.read_version(key: str, name: str) -> Version` — hebt `ValueError` mit Satz
  - `HistoryStore.remove_version(key: str, name: str) -> Version` — hebt `ValueError` mit Satz, antwortet mit der aufgehobenen Version

- [ ] **Step 1: Write the failing tests**

In `tests/test_store.py` **unmittelbar vor die Abschnittsüberschrift `# -- a history longer than any cap` (Zeile 1203)** setzen. Nicht an das Dateiende und nicht hinter `test_a_version_says_whether_it_has_words_at_all` (Zeile 1029): der Abschnitt, der dort beginnt, läuft bis Zeile 1203, und ein Einschub in seiner Mitte schöbe zehn fremde Fälle unter die neue Überschrift. Vor Zeile 1203 bleiben die Versionsfälle beisammen, ohne einen bestehenden Abschnitt zu zerschneiden.

`_lightweight_tag` und die Fixture `store` sind in der Datei vorhanden.

```python
# -- taking a version away ---------------------------------------------


def test_a_version_can_be_taken_away(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.create_version("home/v1.0.0", "First", "a note", first)

    removed = store.remove_version("home", "home/v1.0.0")

    # Answered with what was taken, so a caller can say what is gone
    # without a second read - and the log line is then the only place
    # those words still exist.
    assert (removed.name, removed.title, removed.description) == (
        "home/v1.0.0",
        "First",
        "a note",
    )
    assert store.list_versions("home") == []


def test_the_state_a_taken_version_marked_is_untouched(store):
    # The whole point of decision 18, and the one test that would catch a
    # slip into `forget` territory: the mark goes, the state stays.
    first = store.write_snapshot("home", "a: 1\n", "first")
    second = store.write_snapshot("home", "a: 2\n", "second")
    store.create_version("home/v1.0.0", "First", "", first)
    head_before = store.list_changes("home")[0].revision

    store.remove_version("home", "home/v1.0.0")

    assert store.read_at("home", first) == "a: 1\n"
    assert [c.revision for c in store.list_changes("home")] == [second, first]
    assert store.list_changes("home")[0].revision == head_before


def test_a_description_on_the_state_survives_the_version_being_taken(store):
    # Notes hang on the commit, versions on a ref beside it. Taking the
    # ref must not go near `refs/notes/commits` - and it is worth its own
    # test because `forget`, the other operation that removes a tag,
    # rewrites the notes as part of its work.
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.set_description(first, "why I did it")
    store.create_version("home/v1.0.0", "First", "", first)

    store.remove_version("home", "home/v1.0.0")

    assert store.list_changes("home")[0].description == "why I did it"


def test_only_the_named_version_goes(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    second = store.write_snapshot("home", "a: 2\n", "second")
    store.create_version("home/v1.0.0", "First", "", first)
    store.create_version("home/v2.0.0", "Second", "", second)

    store.remove_version("home", "home/v1.0.0")

    assert [v.name for v in store.list_versions("home")] == ["home/v2.0.0"]


def test_another_dashboards_version_cannot_be_taken_away(store):
    # The same fence `retitle_version` has, and it has to be `_owns`
    # rather than a `startswith`: a command taking a bare ref name would
    # otherwise delete any tag in the repository.
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("other", "b: 1\n", "other")
    store.create_version("other/v1.0.0", "Theirs", "", first)

    with pytest.raises(ValueError, match="not a version of home"):
        store.remove_version("home", "other/v1.0.0")

    assert [v.name for v in store.list_versions("other")] == ["other/v1.0.0"]


def test_a_nested_key_does_not_reach_into_a_deeper_namespace(store):
    # Measured on 2026-09-04 for `forget`: tested with `startswith`
    # alone, "dh-slash/check/" also claimed the versions of a dashboard
    # whose key holds one more slash. Home Assistant accepts such a
    # url_path, so this is a real dashboard and not a contrivance.
    first = store.write_snapshot("dh-slash/check", "a: 1\n", "first")
    store.create_version("dh-slash/check/deeper/v1.0.0", "Deeper", "", first)

    with pytest.raises(ValueError, match="not a version of dh-slash/check"):
        store.remove_version("dh-slash/check", "dh-slash/check/deeper/v1.0.0")


def test_an_unknown_version_cannot_be_taken_away(store):
    store.write_snapshot("home", "a: 1\n", "first")
    with pytest.raises(ValueError, match="unknown version"):
        store.remove_version("home", "home/v9.9.9")


def test_a_version_made_by_hand_can_be_taken_away(store):
    # The one place this parts company with `retitle_version`, and
    # deliberately. Renaming a lightweight tag would hand back a
    # different kind of tag than the one somebody made; taking it away
    # gives nothing back. And it has to be possible: a lightweight
    # `home/v1.0.0` counts when the next number is worked out, so one
    # that could not be removed would hold a number for ever.
    first = store.write_snapshot("home", "a: 1\n", "first")
    _lightweight_tag(store, "home/v1.0.0", first)

    removed = store.remove_version("home", "home/v1.0.0")

    assert (removed.name, removed.annotated) == ("home/v1.0.0", False)
    assert store.list_versions("home") == []
    assert store.read_at("home", first) == "a: 1\n"


def test_taking_a_version_in_an_empty_repository_is_refused_not_built(
    store, tmp_path
):
    # As with `retitle_version`: no `_ensure()`, because this can only
    # ever take away something that exists. Building a history in order
    # to report that it holds no such version would leave one behind
    # that nobody asked for.
    fresh = HistoryStore(tmp_path / "nothing")
    with pytest.raises(ValueError, match="unknown version"):
        fresh.remove_version("home", "home/v1.0.0")
    assert not (tmp_path / "nothing").exists()


def test_reading_one_version_gives_what_the_list_gives(store):
    # `read_version` and `list_versions` must not drift: the preview of a
    # removal is built from the first and the panel's list from the
    # second, and a field present in one and missing in the other is the
    # kind of difference a frontend renders as False. One builder for
    # both is the fix, and this is the test that keeps it.
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.create_version("home/v1.0.0", "First", "a note", first)
    _lightweight_tag(store, "home/v2.0.0", first)

    for listed in store.list_versions("home"):
        assert store.read_version("home", listed.name) == listed
```

Und an `tests/test_versions.py` anhängen. **`candidates` ist dort nicht als bloßer Name importiert** — die Datei hat nur `import versions` und schreibt durchweg `versions.candidates(...)`. Der Code unten folgt dem. (Bloß importiert ist der Name in `tests/test_store.py`, Zeile 12 — das ist die andere Datei, und die Verwechslung hat diesen Absatz einmal falsch gemacht.)

```python
def test_a_number_that_was_taken_away_is_offered_again():
    # The conditional half of decision 13, and it needs no production
    # code: `candidates` counts from the highest name it is given, so a
    # name that is gone is a name that no longer counts. Written down
    # because it is a promise the interface makes out loud - the dialog
    # says "its number becomes free again" - and a promise nobody tests
    # is a sentence waiting to become false.
    with_it = ["home/v1.0.0", "home/v1.0.1", "home/v1.0.2"]
    without_it = ["home/v1.0.0", "home/v1.0.1"]
    assert versions.candidates("home", with_it)["patch"] == "home/v1.0.3"
    assert versions.candidates("home", without_it)["patch"] == "home/v1.0.2"


def test_taking_a_lower_number_away_frees_nothing():
    # The other half of the same sentence, and the reason the dialog only
    # says it for the highest version: removing one in the middle changes
    # no candidate at all, so a dialog that promised a free number there
    # would be lying in the ordinary case.
    assert versions.candidates("home", ["home/v1.0.0", "home/v1.0.2"])[
        "patch"
    ] == "home/v1.0.3"
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python3 -m pytest tests/test_store.py -k "taken or take or reading_one_version" -v
python3 -m pytest tests/test_versions.py -k "number" -v
```

Erwartet: die `test_store`-Fälle scheitern mit `AttributeError: 'HistoryStore' object has no attribute 'remove_version'` (bzw. `read_version`). Die zwei `test_versions`-Fälle **bestehen sofort** — das ist beabsichtigt und kein Fehler im Plan: sie halten eine Zusage fest, die der vorhandene Code schon einlöst. Wer sie scheitern sehen will, ändert probeweise `candidates`, um zu sehen, dass sie greifen.

- [ ] **Step 3: Extract the one builder both readers use**

In `store.py`, direkt hinter `_version_words` (~Zeile 148) einfügen:

```python
def _version_from(name: str, target) -> Version:
    """One tag as a `Version`, whichever of the two kinds it is.

    `target` is what the ref points at: a tag object for an annotated
    one, and the commit itself for a lightweight one - which is what a
    lightweight tag *is*, a ref straight to the object.

    One builder because there are two readers. `list_versions` walks the
    namespace, `read_version` looks up one name, and the removal of a
    version is previewed from the second while the panel's list comes
    from the first. A field present in one answer and missing from the
    next is the kind of difference a frontend quietly renders as False -
    the same reason `_version_dict` exists one layer up.

    A lightweight tag carries no message, so it has no title and no
    description, and it is ordered by the time of the commit it marks -
    the only time it has. Anything but a commit (a hand-made tag on a
    blob) answers zero rather than raising: it is reported all the same,
    as decision 13 of the design record promises.
    """
    annotated = hasattr(target, "object")
    if annotated:
        title, description = _version_words(target.message)
        marked, made = target.object[1], target.tag_time
    else:
        title, description = "", ""
        marked, made = target.id, getattr(target, "commit_time", 0)
    return Version(
        name=name,
        revision=_as_text(marked),
        title=title,
        description=description,
        timestamp=made,
        annotated=annotated,
    )
```

Dann `list_versions` (~Zeile 1743) auf denselben Bauplan stellen. Der Rumpf der Schleife wird:

```python
        found: list[tuple[int, Version]] = []
        for ref, tag in self._each_tag(repo, key):
            version = _version_from(ref.decode(), tag)
            found.append((version.timestamp, version))
        # as_dict has no order of its own; the docstring promises one.
        return [version for _, version in sorted(found, key=lambda p: -p[0])]
```

Der lange Kommentar über leichtgewichtige Tags, der im alten `else`-Zweig stand, **wandert mit** nach `_version_from` und wird hier nicht ein zweites Mal hingeschrieben.

- [ ] **Step 4: Run the whole suite to prove the extraction changed nothing**

```bash
python3 -m pytest tests/ -q
```

Erwartet: **491 bestanden, 10 gescheitert** — und diese zwei Zahlen sind die Aussage. Die zehn sind die neuen `test_store`-Fälle, jeder mit `AttributeError` auf eine noch nicht existierende Methode; die 491 sind die 489 von vorher **plus** die zwei `test_versions`-Fälle, die ohne Produktionscode bestehen (siehe Schritt 2). Bestehende Fehlschläge: keine. 491 − 2 = 489, also ist der Umbau verhaltensgleich.

*(Am 2026-09-08 berichtigt: Hier stand »489 bestanden«, was dem eigenen Schritt 2 widersprach — der sagt ausdrücklich, dass die zwei `candidates`-Fälle sofort bestehen. Der Umsetzende hat die Arithmetik richtig aufgelöst, aber eine Zahl, die als Prüfstein gemeint ist und nicht stimmt, schickt den nächsten Leser auf die Suche nach einem Rückschritt, den es nicht gibt.)*

Diese Zwischenmessung ist der Sinn des eigenen Schritts: `list_versions` trägt den Verlauf des Panels, die Tagesmarken und die Tag-Umschreibung in `forget`, und der Umbau muss für sich prüfbar sein, bevor Neues darauf kommt.

- [ ] **Step 5: Write `read_version` and `remove_version`**

In `store.py` hinter `retitle_version` einfügen (also vor `_marked_commit`):

```python
    def read_version(self, key: str, name: str) -> Version:
        """One version of one dashboard, by name. Raises where there is none.

        The one-name counterpart to `list_versions`, and it exists for
        the *preview* of a removal: it has to show the words that are
        about to go, before anything goes. Read through the namespace
        instead and that is a scan of every tag this dashboard has to
        answer about one - measured at 365 versions, 35 ms of it. The
        second read, the one that answers with what went, is
        `remove_version`'s own and happens under the same lock as the
        delete; nothing here reads a ref twice.

        The lock is held for a read, which `list_versions` does not do.
        Said out loud, because the lock is documented as a serialiser of
        *writes*: what it buys is `_read_version`, shared with
        `remove_version`, where the read and the delete have to be one
        move. The price is that a preview can queue behind a 30 ms
        commit, and a dialog that is opening can afford that.

        The refusals are the same two `retitle_version` gives, in the
        same shape - a ValueError carrying a sentence: the version is not
        this dashboard's, or there is none by that name. Not a third for
        a lightweight tag: this only reads, and decision 13 says a
        hand-made tag stays visible.
        """
        with self._lock:
            return self._read_version(self._repo(), key, name)

    def _read_version(self, repo, key: str, name: str) -> Version:
        """The read both public doors go through, already under the lock."""
        if not _owns(name.encode("utf-8"), key):
            raise ValueError(f"not a version of {key}: {name}")
        ref = b"refs/tags/" + name.encode("utf-8")
        try:
            target = repo[repo.refs[ref]] if repo is not None else None
        except KeyError:
            target = None
        if target is None:
            raise ValueError(f"unknown version: {name}")
        return _version_from(name, target)

    def remove_version(self, key: str, name: str) -> Version:
        """Take one dashboard's version away. Answers what was taken.

        **The mark, never the state.** What goes is a ref. The commit it
        pointed at keeps standing, stays readable through its revision,
        keeps every note on it, and no other revision changes. Decision
        18 of the design record calls this the discard of decision 17
        made afterwards: there, choosing "discard" leaves a state in the
        history without a name, and this leaves it in exactly the same
        condition later on.

        Which is also why `forget` stays the only destructive operation
        in the sense the design record means. The rule it replaced its
        own wording with: what takes a *state* away is called `forget`,
        and it remains the one.

        No `_ensure()`, as `retitle_version` has none and for the same
        reason: this can only ever take away something that already
        exists, so a repository that is not there is an answer rather
        than a state to be built.

        **Both kinds of tag**, unlike renaming. A lightweight one cannot
        be *given* words - that would hand back a different kind of tag
        than the one somebody made - but it can be taken away, and it
        has to be. It counts when the next number is worked out, so one
        that could not be removed would hold a number for ever. The
        older reason is written into `_rewrite_tags` already: a tag
        operation that quietly skips the lightweight kind ends up
        silently ineffective, which is how `forget` once reported
        success while leaving the forgotten text in the object store.

        Neither `_index` nor `_survey` is dropped, and that is checked
        rather than assumed: both are keyed by HEAD and built from the
        commit walk, and neither reads `refs/tags`. `forget` drops them
        because it rewrites commits, which this does not.

        The old tag object stays behind as a loose object nothing points
        at - the same few hundred bytes `retitle_version` leaves, and for
        the same reason: pruning here would mean a full object-store walk
        per removal, and `forget`'s `garbage_collect` sweeps it up.

        Read before the delete and under the same lock, so the answer
        describes what was actually taken rather than what stood there a
        moment earlier. It is the caller's only copy: once the ref is
        gone, nothing in this integration can read those words again.

        The two refusals are `_read_version`'s, and they reach a caller
        from *this* call rather than from a read before it. That is what
        `operations` catches around the removal itself: between a
        preview and the confirmation the version can be gone - two
        removals at once, or a `forget` in between - and `services.py`
        catches nothing at all.
        """
        with self._lock:
            repo = self._repo()
            version = self._read_version(repo, key, name)
            del repo.refs[b"refs/tags/" + name.encode("utf-8")]
            return version
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
python3 -m pytest tests/test_store.py tests/test_versions.py -v
python3 -m pytest tests/ -q
```

Erwartet: alle neuen Fälle bestehen, die Gesamtzahl steigt von 489 auf **501** — **10** neue in `test_store.py`, 2 in `test_versions.py`. (Nachgezählt: die zehn sind `test_a_version_can_be_taken_away`, `…is_untouched`, `…survives_the_version_being_taken`, `test_only_the_named_version_goes`, `…cannot_be_taken_away`, `…deeper_namespace`, `test_an_unknown_version…`, `…made_by_hand…`, `…refused_not_built`, `test_reading_one_version…`. Die Zahl steht hier als Prüfstein, also muss sie stimmen — eine falsche schickt den Umsetzenden auf die Suche nach einem Fehler, den es nicht gibt.)

- [ ] **Step 7: Commit (nur nach Ansage des Nutzers)**

```bash
git add custom_components/dashboard_history/store.py tests/test_store.py tests/test_versions.py
git commit -F - <<'MSG'
Let a version be taken away again

A version could be made, renamed and never removed, and both places in
the code that noticed said so as an apology rather than a reason. What
goes here is the ref: the commit it pointed at keeps standing, keeps
its note, and no other revision changes - so forget stays the only
operation that takes a state away.

Both kinds of tag, unlike renaming. A lightweight one cannot be given
words, because that would hand back a different kind of tag than the
one somebody made; but it counts when the next number is worked out,
so one that could not be removed would hold a number for ever.

The two readers of a tag now share one builder. The preview of a
removal is built from a single name and the panel's list from a walk of
the namespace, and a field present in one and missing from the other is
the kind of difference a frontend renders as False.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
```

---

## Task 2: Die Schnittstellen — Dienst und WebSocket-Befehl

**Files:**
- Modify: `custom_components/dashboard_history/operations.py` (hinter `async_retitle_version`, ~Zeile 920)
- Modify: `custom_components/dashboard_history/websocket_api.py` (ein Eintrag in `_COMMANDS`, hinter dem von `retitle_version`)
- Modify: `custom_components/dashboard_history/services.py` (ein Handler und eine Zeile in `registrations`)
- Modify: `custom_components/dashboard_history/services.yaml` (ein Eintrag hinter `retitle_version`)
- Test: `tests/test_integration_files.py`

**Interfaces:**
- Consumes: `store.read_version`, `store.remove_version`, `store.list_versions` (Task 1); `_version_dict(version: Version) -> dict` und `versioning.highest(key, versions) -> object | None` (beide vorhanden)
- Produces: `operations.async_remove_version(hass, store, key: str, name: str, confirm: bool = False) -> dict`
  - ohne `confirm`: `{"applied": False, **_version_dict(version), "highest": bool}`
  - mit `confirm`: `{"applied": True, **_version_dict(removed)}`
  - bei Ablehnung: `{"applied": False, "error": str}`
  - WebSocket: `dashboard_history/remove_version` mit `{dashboard, name, confirm}`
  - Dienst: `dashboard_history.remove_version` mit denselben Feldern

**Warum hier ein neuer Test in `tests/test_integration_files.py` steht:** Diese Schicht ist die einzige, für die es heute keinen Prüfstein in reinem pytest gibt — `operations.py` importiert Home Assistant, und `services.yaml` liest niemand außer Home Assistant selbst. Ein Dienst ohne Eintrag dort erscheint in den Developer Tools als nackter Schlüssel ohne Felder, und `hassfest`, das HACS auf einer veröffentlichten Integration laufen lässt, meldet die Lücke. Der Test schließt sie ein für alle Mal und macht diese Aufgabe erst testgetrieben machbar.

- [ ] **Step 1: Write the failing test**

An `tests/test_integration_files.py` anhängen:

```python
def test_every_registered_service_has_words_in_services_yaml():
    # The two halves live in two files that nothing joins: `services.py`
    # registers the name, `services.yaml` gives it a name, a description
    # and its fields in Developer Tools. A service missing there shows up
    # as a bare key with no fields, and hassfest - which HACS runs on a
    # published integration - reports it. Nothing else in this suite
    # reads services.yaml at all.
    #
    # `services.py` is read as text rather than imported: it pulls in
    # Home Assistant, and this suite runs without an installation.
    import re

    import yaml

    source = (PACKAGE / "services.py").read_text(encoding="utf-8")
    registered = set(re.findall(r'^\s*\("([a-z_]+)",\s', source, re.MULTILINE))
    assert registered, "no registrations found - has the table been rewritten?"
    described = set(
        yaml.safe_load((PACKAGE / "services.yaml").read_text(encoding="utf-8"))
    )
    assert registered - described == set()
    # And the other way round, because a leftover entry names a service
    # that no longer exists - a promise in the interface with nothing
    # behind it.
    assert described - registered == set()
```

Anmerkung für den Umsetzenden: `pyyaml` steht über Home Assistants Abhängigkeiten bereits zur Verfügung; `python3 -c "import yaml"` bestätigt das vor dem Schreiben. Ist es nicht da, wird es installiert (`python3 -m pip install pyyaml`) und **nicht** durch eine Textsuche ersetzt — eine Regex über YAML ist genau die Art Prüfung, die ein eingerückter Schlüssel unbemerkt aushebelt.

- [ ] **Step 2: Run it to see it pass on today's code, then fail on tomorrow's**

```bash
python3 -m pytest tests/test_integration_files.py -v
```

Erwartet: **bestanden** — heute stimmen die beiden Listen überein. Das ist der Sinn dieser Reihenfolge: Der Test wird erst durch den nächsten Schritt rot, und dann hat er etwas bewiesen. Wer ihn sofort rot sehen will, hängt probehalber eine Zeile `("nonesuch", versions, DASHBOARD),` an `registrations` an und nimmt sie wieder weg.

- [ ] **Step 3: Write `async_remove_version`**

In `operations.py` hinter `async_retitle_version` einfügen:

```python
async def async_remove_version(
    hass: HomeAssistant,
    store: HistoryStore,
    key: str,
    name: str,
    confirm: bool = False,
) -> dict:
    """Take a version's mark away. The state it names stays where it is.

    Decision 18 of the design record, and the shortest way to say what
    this is: the discard of decision 17, made afterwards. "Discard"
    there means not marking rather than deleting, and this leaves a
    state in exactly that condition - in the history, findable in the
    advanced mode, without a name.

    **`confirm` is required**, which puts this beside `forget` rather
    than beside `describe`. No dashboard changes either way, so the
    reason is not visibility but reversibility: a title and a
    description live in the tag object, and once the ref is gone this
    integration cannot write them back. That is the second side of
    decision 7 - the rule says when `confirm` is *needed*, not when it
    alone suffices.

    Without `confirm` the answer is the version's own words. Not a diff:
    a diff of this would be empty, because nothing on the dashboard
    moves. `highest` comes with them and is the one field a person acts
    on - the number of the highest version becomes free again, which is
    the case this operation was built for.

    **`highest` is in the preview and not in the applied answer**, and
    that is deliberate rather than forgetful. Answering it costs a walk
    of the whole namespace, because it cannot be read off one ref; the
    removal is built to read one ref and nothing else. Whoever gets the
    applied answer has already seen the preview that led to it. The
    objection that moved `retitle_version` off the listing was about
    looking around *a write*, not about looking around at all - a dialog
    that is opening has 35 ms to spend, a 2 ms write does not.

    **One read per path, and each path catches its own refusal.** The
    preview reads the ref to show the words. The removal reads it again
    inside the store, under the lock that also does the delete - so
    reading it *here* first and then removing it would be two reads of
    one ref around a 2 ms write, and `remove_version`'s own docstring
    promises the opposite. The two refusals are the same two sentences
    either way, but on the confirming path they arrive from the write
    call, and that is where they have to be caught: `operations.py` is
    the layer that turns a ValueError into an answer, the WebSocket
    wrapper only swallows what escapes, and `services.py` has no
    `except` anywhere in it. Every other operation here wraps its
    raising store call; this one is not the exception.
    """
    if not confirm:
        try:
            version = await hass.async_add_executor_job(
                store.read_version, key, name
            )
        except ValueError as err:
            # Not this dashboard's version, or none by that name. An
            # answer with a sentence in it, like every other refusal
            # here.
            return {"applied": False, "error": str(err)}
        found = await hass.async_add_executor_job(store.list_versions, key)
        top = versioning.highest(key, found)
        return {
            "applied": False,
            **_version_dict(version),
            "highest": top is not None and top.name == version.name,
        }
    try:
        removed = await hass.async_add_executor_job(store.remove_version, key, name)
    except ValueError as err:
        # The same two sentences, caught a second time because they
        # arrive from a different call. `remove_version` reads the ref
        # again under its own lock, and between a preview and this call
        # the version can be gone - two removals at once, or a `forget`
        # in between. Uncaught it leaves the service as a bare
        # traceback: `services.py` has no `except` in it.
        return {"applied": False, "error": str(err)}
    # At warning, and carrying the words. This log line is the only place
    # a removed version's title still exists - `forget` is loud for a
    # bigger loss, and somebody asking later where a version went has
    # nowhere else to look. The revision is in it so that the same person
    # can see the state was never touched.
    _LOGGER.warning(
        "Removed version %s of dashboard %s (%r); the state it marked is "
        "untouched at %s",
        name,
        key,
        removed.title,
        removed.revision,
    )
    return {"applied": True, **_version_dict(removed)}
```

- [ ] **Step 4: Add the WebSocket command**

In `websocket_api.py`, in `_COMMANDS` hinter dem `retitle_version`-Eintrag:

```python
    _command(
        f"{DOMAIN}/remove_version",
        {
            **_DASHBOARD,
            vol.Required("name"): str,
            vol.Optional("confirm", default=False): bool,
        },
        operations.async_remove_version,
        lambda msg: {
            "key": msg["dashboard"],
            "name": msg["name"],
            "confirm": msg["confirm"],
        },
    ),
```

- [ ] **Step 5: Add the service**

In `services.py`, hinter der Funktion `retitle_version`:

```python
    async def remove_version(call: ServiceCall) -> dict:
        return await operations.async_remove_version(
            hass,
            store,
            call.data["dashboard"],
            call.data["name"],
            bool(call.data.get("confirm")),
        )
```

Und in `registrations`, hinter der `retitle_version`-Zeile:

```python
        ("remove_version", remove_version, DASHBOARD.extend({
            vol.Required("name"): cv.string,
            vol.Optional("confirm", default=False): bool,
        })),
```

- [ ] **Step 6: Add the words in `services.yaml`**

Hinter dem `retitle_version`-Block einfügen. Englisch, wie jede Fläche, die ein Nutzer sieht:

```yaml
remove_version:
  name: Remove a version
  description: >-
    Take a version's mark away. The state it marks stays in the history
    and remains findable in the advanced view - only the name goes, along
    with the title and description you gave it, and those cannot be
    written back. Without confirm, you get the version's own words and
    nothing changes. If it carries the highest number, that number
    becomes free again and the next version will use it.
  fields:
    dashboard:
      required: true
      description: The dashboard, by its url_path.
      example: my-dashboard
      selector:
        text:
    name:
      required: true
      description: >-
        The version to remove, by its full name as `versions` reports it.
      example: my-dashboard/v1.0.0
      selector:
        text:
    confirm:
      description: Without this, nothing is removed.
      default: false
      selector:
        boolean:
```

- [ ] **Step 7: Run the tests**

```bash
python3 -m pytest tests/ -q
```

Erwartet: **502 bestanden** (501 aus Task 1, plus der eine neue Test aus Schritt 1). Wäre der `services.yaml`-Eintrag vergessen, meldet dieser Test `{'remove_version'}` als Differenz — genau der Fall, für den er da ist.

- [ ] **Step 8: Prove it imports where Home Assistant exists**

`operations.py`, `services.py` und `websocket_api.py` importieren Home Assistant; reines pytest kommt nicht an sie heran. Der Container hat es:

```bash
docker compose -f docker/compose.yaml up -d
docker exec -i dashboard-history-test python3 - <<'PY'
import sys
sys.path.insert(0, "/config")
from custom_components.dashboard_history import operations, services, websocket_api
assert hasattr(operations, "async_remove_version")
import inspect
print(inspect.signature(operations.async_remove_version))
print("ok")
PY
```

Erwartet: die Signatur und `ok`. Nur `custom_components/` ist in den Container gemountet — die Änderung ist dort also ohne Neustart sichtbar.

- [ ] **Step 9: Commit (nur nach Ansage des Nutzers)**

```bash
git add custom_components/dashboard_history/operations.py \
        custom_components/dashboard_history/websocket_api.py \
        custom_components/dashboard_history/services.py \
        custom_components/dashboard_history/services.yaml \
        tests/test_integration_files.py
git commit -F - <<'MSG'
Ask before a version's words are gone

Removing a version writes no dashboard, so the preview rule of decision
7 does not reach it - and it needs confirming all the same. The reason
is not visibility but reversibility: a title lives in the tag object,
and once the ref is gone nothing here can write it back. The rule says
when confirm is needed, not when it alone suffices.

The preview answers with the version's own words rather than a diff,
which would be empty, and with whether this is the highest number -
the one thing a person acts on, because that number comes free again.
It is in the preview only: reading it costs a walk of the namespace,
and the removal is built to read one ref.

The log line is loud and carries the title, because after this it is
the only place those words still exist.

Each of the two paths reads the ref once and catches its own refusal.
The removal reads it again in the store, under the lock that does the
delete, so reading it here first would be two reads around a 2 ms
write. And the refusal has to be caught around the write as well: this
layer is what turns a ValueError into an answer, and services.py has
no except in it.

And a test now joins the two halves of a service. services.py
registers the name, services.yaml gives it words, and nothing read the
second file before - a service missing there shows in Developer Tools
as a bare key with no fields, and hassfest reports it.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
```

---

## Task 3: Das Panel

**Files:**
- Modify: `custom_components/dashboard_history/panel/rows.js` (`bin` neben `pen`, ~Zeile 139; Aufrufstellen ~Zeile 94 und ~Zeile 118)
- Modify: `custom_components/dashboard_history/panel/simple.js` (~Zeile 282)
- Modify: `custom_components/dashboard_history/panel/dialogs.js` (sechster Dialog)
- Modify: `custom_components/dashboard_history/panel/style.js` (~Zeile 292)
- Modify: `custom_components/dashboard_history/panel.js` (`_removeVersion` hinter `_retitleVersion` ~Zeile 1477; `onClick` ~Zeile 2422)
- Modify: `tests/integration/look_at_panel.py` (ein Block hinter »The pen on a version section head«, ~Zeile 874 — der Grund steht in Schritt 9)
- Test: `tests/test_panel_behaviour.py`

**Interfaces:**
- Consumes: WebSocket `dashboard_history/remove_version` (Task 2); `pen(version) -> string`, `escape`, `shortName`, `this._call`, `this._guard`, `this._claim`, `this._answerFrom`, `this._sayAbout`, `this._reloadAfterWrite`, `this._versions` — alle vorhanden
- Produces: `bin(version) -> string` (aus `rows.js`), `Panel.prototype._removeVersion(name)`

- [ ] **Step 1: Write the failing tests**

An `tests/test_panel_behaviour.py` anhängen. Der erste prüft die zwei Sichtbarkeitsregeln durch echten Import des Moduls, der zweite den Dialogzweig am ganzen Element.

```python
_CONTROLS = """
const rows = await import(%(rows)s);
const annotated = { name: "dash/v1.0.0", title: "First", annotated: true };
const byHand = { name: "dash/v2.0.0", title: "", annotated: false };
console.log(JSON.stringify({
  penOnAnnotated: rows.pen(annotated).includes("data-retitle"),
  penOnByHand: rows.pen(byHand),
  binOnAnnotated: rows.bin(annotated).includes("data-remove"),
  binOnByHand: rows.bin(byHand).includes("data-remove"),
  binCarriesTheName: rows.bin(annotated).includes('data-remove="dash/v1.0.0"'),
  binIsRevealedLikeThePen: rows.bin(annotated).includes('class="pen bin"'),
}));
"""


@pytest.fixture(scope="module")
def controls(tmp_path_factory):
    """The two controls a version row carries, imported as a module.

    `rows.js` is pure - data in, markup out, no `this` - so it needs no
    stand-in for the browser at all. Imported rather than read with a
    regex, because what is being checked is a rule with a branch in it.
    """
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed; the panel's logic cannot be run here")
    harness = tmp_path_factory.mktemp("panel") / "controls.mjs"
    rows = PANEL.parent / "panel" / "rows.js"
    harness.write_text(
        _CONTROLS % {"rows": json.dumps(rows.as_uri())}, encoding="utf-8"
    )
    run = subprocess.run(
        [node, str(harness)], capture_output=True, text=True, timeout=60, check=False
    )
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout.strip().splitlines()[-1])


def test_the_pen_stays_off_a_version_made_by_hand(controls):
    # Unchanged, and here as the control for the test below it: the two
    # rules differ, and a change that quietly aligned them would be
    # caught by nothing else.
    assert controls["penOnAnnotated"] is True
    assert controls["penOnByHand"] == ""


def test_the_bin_is_offered_on_a_version_made_by_hand_too(controls):
    # The one place the two controls part company. Renaming a
    # lightweight tag is refused by the server, so a pen there could only
    # ever produce that sentence; removing one is allowed, and has to be
    # offered, or a hand-made tag would hold its number for ever.
    assert controls["binOnAnnotated"] is True
    assert controls["binOnByHand"] is True


def test_the_bin_names_the_version_it_would_remove(controls):
    assert controls["binCarriesTheName"] is True


def test_the_bin_is_revealed_by_the_same_class_as_the_pen(controls):
    # The stylesheet reveals `.pen` from a class on whatever holds it,
    # rather than from a list of the buttons that exist - the comment
    # there says why, and the failure mode of a fourth place forgetting
    # itself is silent invisibility. So the bin carries that class too
    # instead of earning a fifth selector.
    assert controls["binIsRevealedLikeThePen"] is True


_REMOVE_VERSION = """
const el = new Panel();
// Handed in, because `attachShadow()` in the prelude answers `{}` and
// panel.js throws that answer away - so `this.shadowRoot` is undefined
// in Node. Every scenario in this file that touches a dialog does this;
// without it the run dies at the first `querySelector` with a TypeError,
// and all four tests below fail at the fixture instead of at what they
// are about.
el.shadowRoot = node();
el._render = () => {};
el._selected = "dash";
el._versions = [
  { name: "dash/v1.0.2", title: "Third", description: "a note",
    revision: "c", annotated: true, automatic: false },
];
const calls = [];
el._call = (type, extra) =>
  new Promise((resolve) => calls.push({ type, extra, resolve }));
el._refresh = async () => {};

const dialog = el.shadowRoot.querySelector("dialog.remove");
// Answered the way a person would: the dialog is closed with the value
// the button carries, once the preview has been put into it.
let bodyWhenOpened = null;
const opening = el._removeVersion("dash/v1.0.2");
await settle();
const asked = { ...calls[0] };
calls[0].resolve({
  applied: false, name: "dash/v1.0.2", title: "Third", description: "a note",
  revision: "c", automatic: false, highest: true,
});
await settle();
bodyWhenOpened = dialog.querySelector(".body").innerHTML;
dialog.returnValue = "remove";
dialog.close();
await settle();
const confirmed = calls[1] ? { ...calls[1] } : null;
if (calls[1]) calls[1].resolve({ applied: true, name: "dash/v1.0.2" });
await opening;

// And the second run, cancelled.
const two = new Panel();
two.shadowRoot = node();
two._render = () => {};
two._selected = "dash";
two._versions = el._versions;
const twoCalls = [];
two._call = (type, extra) =>
  new Promise((resolve) => twoCalls.push({ type, extra, resolve }));
two._refresh = async () => {};
const cancelling = two._removeVersion("dash/v1.0.2");
await settle();
twoCalls[0].resolve({
  applied: false, name: "dash/v1.0.2", title: "Third", description: "",
  revision: "c", automatic: false, highest: false,
});
await settle();
const cancelDialog = two.shadowRoot.querySelector("dialog.remove");
cancelDialog.returnValue = "cancel";
cancelDialog.close();
await settle();
await cancelling;

console.log(JSON.stringify({
  asked: { type: asked.type, extra: asked.extra },
  confirmed: confirmed && { type: confirmed.type, extra: confirmed.extra },
  saysTheNumberComesFree: bodyWhenOpened.includes("becomes free"),
  saysTheStateStays: bodyWhenOpened.includes("stays in the history"),
  namesTheVersion: bodyWhenOpened.includes("Third"),
  callsAfterCancel: twoCalls.length,
}));
"""


@pytest.fixture(scope="module")
def removing(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "removing", _REMOVE_VERSION)


def test_the_dialog_is_filled_from_a_preview_the_server_answered(removing):
    # Asked without confirm first, exactly as `_forget` does: the panel
    # must not word the loss itself, and the words it shows are the ones
    # the server read off the tag a moment ago.
    assert removing["asked"]["type"] == "remove_version"
    assert removing["asked"]["extra"] == {
        "dashboard": "dash",
        "name": "dash/v1.0.2",
    }
    assert removing["namesTheVersion"] is True
    assert removing["saysTheStateStays"] is True


def test_the_dialog_says_the_number_comes_free_where_it_does(removing):
    # The one sentence in this dialog somebody acts on. It comes from the
    # server's `highest`, never from the panel comparing numbers - that
    # calculation lives in versions.py by decision 13.
    assert removing["saysTheNumberComesFree"] is True


def test_confirming_sends_confirm_and_nothing_else_changes_hands(removing):
    assert removing["confirmed"]["type"] == "remove_version"
    assert removing["confirmed"]["extra"] == {
        "dashboard": "dash",
        "name": "dash/v1.0.2",
        "confirm": True,
    }


def test_cancelling_sends_no_second_call(removing):
    # The preview is a read, so it happens either way; what must not
    # happen is the write. One call, not two.
    assert removing["callsAfterCancel"] == 1
```

Zwei Anmerkungen für den Umsetzenden, beide über die Attrappe und nicht über das Panel:

- **`el.shadowRoot = node()` ist Pflicht, nicht Kosmetik.** `_PRELUDE` definiert `HTMLElement` mit `attachShadow() { return {}; }`, und `panel.js` verwirft den Rückgabewert — `this.shadowRoot` bleibt also `undefined`. Alle zwanzig Szenarien der Datei, die einen Dialog anfassen, weisen deshalb selbst zu (Zeilen 673, 744, 884, 1233, …). Fehlt die Zeile, stirbt der Lauf mit `TypeError: Cannot read properties of undefined (reading 'querySelector')`, `_run_in_node` prüft `returncode == 0`, und **alle vier** `removing`-Fälle fallen an der Fixture aus.
- **`querySelector(".body")` trägt.** Die Attrappe merkt sich pro Selektor einen Knoten, und Szenario und Code fragen denselben `shadowRoot` — sie bekommen also denselben `.body`. `dataset`, `returnValue`, `showModal()` und `close()` sind ebenfalls da. `_PRELUDE` braucht **nichts** Neues; sollte doch etwas fehlen, ist es dort nach dem Muster der vorhandenen Zeilen zu ergänzen und **nicht** durch Umbau des Panels.

- [ ] **Step 2: Run them to verify they fail**

```bash
python3 -m pytest tests/test_panel_behaviour.py -k "bin or dialog or confirming or cancelling or pen_stays" -v
```

Erwartet: `SyntaxError`/`TypeError` aus Node — `rows.bin` ist keine Funktion, `el._removeVersion` existiert nicht.

⚠️ **Der Ausdruck hieß bis zum 2026-09-08 `-k "bin or removing or pen_stays"` und wählte die vier Dialog-Fälle nicht aus.** `removing` ist der Name der **Fixture**, nicht der Tests: die heißen `test_the_dialog_is_filled_from_a_preview_the_server_answered`, `…_says_the_number_comes_free_where_it_does`, `test_confirming_sends_confirm_…` und `test_cancelling_sends_no_second_call`, und `-k` liest Testnamen. Nachgezählt beim Review: von 136 Fällen wählte der alte Ausdruck **5** aus, darunter keinen einzigen `_removeVersion`-Fall — die Hälfte des RED-Schritts bewies also nichts. Dieselbe Klasse Fehler wie der Grep in Task 5: ein Ausdruck, der *etwas* trifft, sieht aus wie einer, der das Richtige trifft. Wer ihn anfasst, zählt mit `--collect-only` nach.

- [ ] **Step 3: Add `bin` to `rows.js`**

Hinter `pen` (~Zeile 152) einfügen:

```javascript
/**
 * The way to take one version's mark away. Exported beside `pen` so
 * that both modes draw the same control rather than two that drift.
 *
 * Offered on **every** version, which is where it parts company with
 * the pen - and the difference is the point rather than an oversight. A
 * lightweight tag cannot be renamed, so a pen on one could only ever
 * produce the server's refusal; it can be removed, and it has to be,
 * because it counts when the next number is worked out.
 *
 * It carries the pen's class as well as its own. The stylesheet reveals
 * `.pen` from a class on whatever holds the control, not from a list of
 * the controls that exist - the comment there says why, and the failure
 * mode of a fourth place forgetting itself is silent invisibility. So
 * this earns no fifth selector; `.bin` adds only what differs.
 */
export function bin(version) {
  return `<button class="pen bin" data-remove="${escape(version.name)}"
               title="Remove this version">🗑</button>`;
}
```

Dann die drei Aufrufstellen ergänzen, jeweils direkt hinter dem `pen(...)`:

- `rows.js` ~Zeile 94: `${pen(v)}${bin(v)}` in der `also`-Zeile
- `rows.js` ~Zeile 118: `${pen(first)}` → `${pen(first)}\n      ${bin(first)}`
- `simple.js` ~Zeile 282: `${pen(version)}` → `${pen(version)}\n                ${bin(version)}` — und die Importzeile dort um `bin` erweitern

- [ ] **Step 4: Add the dialog**

In `dialogs.js`, hinter dem `retitle`-Dialog, innerhalb des `DIALOGS`-Literals:

```html
  <dialog class="remove">
    <h2>Remove this version</h2>
    <div class="body"></div>
    <div class="actions">
      <button class="act ghost" value="cancel">Cancel</button>
      <button class="act" value="remove">Remove version</button>
    </div>
  </dialog>
```

**Kein `danger` auf dem Knopf**, anders als bei `forget`. Dort stirbt eine Historie; hier bleibt der Stand, und ein roter Knopf würde dem Satz daneben widersprechen. Die Abstufung zwischen den beiden ist die Aussage — trüge beides Rot, wäre keins von beidem eine Warnung.

- [ ] **Step 5: Add the one style rule**

In `style.js`, hinter `.penholder:hover .pen, .pen:focus { … }`:

⚠️ **Keine Backticks in diesem Kommentar**, und das ist kein Stilhinweis. `style.js` ist **ein** durchgehendes Template-Literal; ein Backtick darin beendet den String und zerlegt die Datei. Die erste Fassung dieses Blocks schrieb `` `bin()` `` in Markdown-Manier, und der Umsetzende lief am 2026-09-08 hinein — gefangen hat es der bestehende Wächter `test_the_style_is_one_unbroken_template_literal`, den das Projekt genau dafür hält. Derselbe Grund, aus dem es daneben `test_no_substitution_hides_in_the_stylesheet` gibt.

```css
  /* The bin borrows the pen's shape and reveal - see bin() in
     rows.js - and differs only where it is about to take something
     away: on hover it says so in the warning colour rather than
     staying grey like the pen beside it. Not red in its resting
     state, because it sits on every version row and a row of red
     glyphs reads as a list of problems. */
  .bin:hover, .bin:focus {
    color: var(--error-color, #db4437);
  }
```

- [ ] **Step 6: Add `_removeVersion` to `panel.js`**

Hinter `_retitleVersion` (~Zeile 1477) einfügen:

```javascript
  /**
   * Taking a version's mark away: asked twice, like forgetting.
   *
   * Once by the button, once by a dialog carrying the words that are
   * about to go. Those words come from the server rather than from
   * `this._versions`, and that is the same choice `_forget` makes: what
   * the dialog says has to be what the store reads off the tag now, not
   * what a list loaded some time ago still remembers. `highest` is the
   * other half of it - whether the number comes free cannot be worked
   * out here, because the numbering lives in versions.py by decision 13.
   *
   * `asked` and `_claim` are held before the first await, and they do
   * two different jobs. `asked` addresses both calls, so neither can
   * land on a dashboard the dialog never mentioned - that is the reason
   * spelled out in `_confirm`. `mine` decides only whether this attempt
   * is still the current one: a click in the sidebar during the preview
   * makes it stale, and a stale preview must not open a dialog on top of
   * another history. The confirming call is guarded by `asked` instead,
   * exactly as in `_retitleVersion` - by then a dialog has been
   * answered, and the answer belongs to the version it named.
   */
  async _removeVersion(name) {
    const asked = this._selected;
    const mine = this._claim("write");
    const facts = await this._guard(
      () => this._call("remove_version", { dashboard: asked, name }),
      mine,
    );
    if (!mine() || !facts) return;
    if (facts.error) {
      this._sayAbout(asked, facts.error);
      return;
    }
    const dialog = this.shadowRoot.querySelector("dialog.remove");
    // Three sentences, and each is a different thing to say. The first
    // is what stays - it comes first because it is the reassurance the
    // whole design rests on. The second is what goes, and it is the only
    // loss there is. The third and fourth appear where they apply.
    const words = facts.title
      ? `<strong>${escape(facts.title)}</strong>`
      : "this version";
    dialog.querySelector(".body").innerHTML = `
      <p>${escape(shortName(name))} — ${words}</p>
      <p>The state it marks <strong>stays in the history</strong> and
         remains findable in the advanced view. Only the mark goes.</p>
      <p>The title and description go with it, and they cannot be
         written back.</p>
      ${facts.automatic
        ? `<p class="muted" style="font-size:13px">Made automatically for
             the end of a day. If that day is recent enough to still be in
             reach, the next save will mark it again. The switch in the
             integration's options is the way to stop that for good.</p>`
        : ""
      }
      ${facts.highest
        ? `<p class="muted" style="font-size:13px">It carries the highest
             number, so that number becomes free again — the next version
             you create will use it.</p>`
        : ""
      }`;
    dialog.returnValue = "";
    dialog.showModal();
    const answer = await this._answerFrom(dialog);
    if (answer !== "remove") return;
    const done = await this._guard(
      () => this._call("remove_version", { dashboard: asked, name, confirm: true }),
      () => this._selected === asked,
    );
    if (done?.error) {
      this._sayAbout(asked, done.error);
      return;
    }
    // Taken out of the set of open sections on the way, or a name that
    // no longer exists would sit in it for the life of the page. Harmless
    // today and the kind of thing that stops being harmless the moment a
    // number is handed out a second time - which is exactly what this
    // operation makes possible.
    this._verOpen.delete(name);
    const stale = await this._reloadAfterWrite("the version was removed");
    if (stale) this._sayAbout(asked, stale);
  }
```

- [ ] **Step 7: Wire the click**

In `panel.js`, hinter dem `[data-retitle]`-Block (~Zeile 2422):

```javascript
    onClick("[data-remove]", (element, event) => {
      // As with the pen beside it: without this the click reaches the
      // row underneath and folds it on the way to the dialog.
      event.stopPropagation();
      this._removeVersion(element.dataset.remove);
    });
```

- [ ] **Step 8: Run the tests to verify they pass**

```bash
python3 -m pytest tests/test_panel_behaviour.py -v
python3 -m pytest tests/ -q
```

Erwartet: **510 bestanden** (8 neue auf die 502 aus Task 2). Ohne `node` überspringen die Panel-Fälle **sichtbar**, wie es die Datei für ihre übrigen tut — ein Lauf ohne `node` ist kein Nachweis.

- [ ] **Step 9: Teach `look_at_panel.py` about the new control**

Der neue Knopf ist genau der **vierte Fall**, vor dem der Kommentar in `style.js` warnt: die Sichtbarkeit kommt aus einer CSS-Regel, die weit weg von der Markierung lebt, und ihr Versagen ist *stille Unsichtbarkeit* — im DOM vorhanden, in jedem Node-Test grün, auf dem Schirm nicht zu finden. Dagegen liest dieses Skript die **berechnete Deckkraft** unter einem echten Zeiger. Es kennt den Stift heute über zwei fest verdrahtete Selektoren (`details.ver > summary [data-retitle]` bei ~Zeile 839, `details.vrow [data-retitle]` bei ~Zeile 1251) und warnt bei ~Zeile 831 selbst davor, dass ein falscher Selektor still nichts beweist. Der Knopf braucht also einen eigenen Block, und der wird hier ausgeschrieben statt angekündigt.

In `look_at_panel.py` **hinter** den Block »The pen on a version section head« einfügen, also nach dessen abschließendem `await page.cancel_dialog()` und vor `print("\n-- The button on a row --")`:

```python
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
```

Dann laufen lassen:

```bash
python3 tests/integration/look_at_panel.py
```

Erwartet: `bin opacity while hovering the head: 1`, der Dialog öffnet, `and it says something: True`, und der Abschnitt bleibt, wie er war. Eine Deckkraft von `0` heißt, dass `class="pen bin"` verlorengegangen ist — dann fehlt die Klasse in `bin()`, nicht eine Regel in `style.js`.

**Der einfache Modus braucht keinen zweiten Block.** Dort liegt der Knopf in derselben `.vhead penholder` wie der Stift, und dessen Prüfung bei ~Zeile 1251 deckt die Regel bereits ab; der Abschnittskopf im erweiterten Modus ist die Stelle, an der der Stift eine eigene Geschichte des Verfehlens hat.

- [ ] **Step 10: Commit (nur nach Ansage des Nutzers)**

```bash
git add custom_components/dashboard_history/panel.js \
        custom_components/dashboard_history/panel/rows.js \
        custom_components/dashboard_history/panel/simple.js \
        custom_components/dashboard_history/panel/dialogs.js \
        custom_components/dashboard_history/panel/style.js \
        tests/test_panel_behaviour.py \
        tests/integration/look_at_panel.py
git commit -F - <<'MSG'
Offer a version row a way out

The dialog has to carry an asymmetry: the state is safe, the words are
not. Saying only one half would be a lie either way round, so it says
what stays first - that is the reassurance the whole design rests on -
and what goes second.

Its words come from the server, not from the list the page is holding.
Whether a number comes free cannot be worked out here, because the
numbering lives in versions.py; and what a tag says now is not
necessarily what a list loaded minutes ago remembers.

The button is not red. forget is, because a history dies there; here
the state stays, and a red button would contradict the sentence beside
it. Two identical warnings are neither.

The bin sits on every version row while the pen skips the hand-made
ones. That difference is the point: a lightweight tag cannot be given
words, but it counts when the next number is worked out, so one that
could not be removed would hold a number for ever.

And look_at_panel.py learns the fourth control. Its reveal is a class
on whatever holds it, which is a rule living far from the markup it
names, and the failure mode is silent invisibility - present in the
DOM, green in every node test, unfindable on the screen. Only a
computed opacity under a real pointer says otherwise.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
```

---

## Task 4: Die Prüfungen, die pytest nicht erreicht

**Files:**
- Modify: `tests/integration/run_checks.py` (`run_remove_version` hinter `run_retitle`, ~Zeile 2600; Aufruf im `main`-Block hinter dem von `run_retitle`)
- Modify: `tests/integration/run_day_marks.py` (ein dritter Abschnitt in `main`)

**Interfaces:**
- Consumes: `Socket`, `check`, `TARGET`, `_versions_settled` (in `run_checks.py` vorhanden); `scenario`, `Rewound`, `Hass`, `Entry`, `marking`, `check` (in `run_day_marks.py` vorhanden)
- Produces: nichts, was anderer Code liest

- [ ] **Step 1: Add the check against a real installation**

In `run_checks.py`, hinter `run_retitle`:

```python
async def run_remove_version(access: str) -> None:
    """Taking a version's mark away, with the state left standing.

    Everything plain pytest cannot reach is in here: the WebSocket
    command, the schema, the argument order in `services.py`, and the
    two-step shape of a preview followed by a confirmation. Every fault
    this project has found so far lived in exactly that layer.

    It brings its own version and takes it away again, so the bench is
    left as it was found. That matters here more than usually: the
    checks below this one read the history of the same dashboard, and a
    check that eats a version other checks rely on turns a real failure
    into a puzzle about which check ran first.
    """
    async with Socket(access) as socket:
        key = TARGET

        async def listed() -> list:
            return (
                await socket.call("dashboard_history/versions", dashboard=key)
            )["versions"]

        async def remove(name: str, **extra):
            return await socket.call(
                "dashboard_history/remove_version",
                dashboard=key,
                name=name,
                **extra,
            )

        changes = (await socket.call("dashboard_history/history", dashboard=key))[
            "changes"
        ]
        if not check("this dashboard has a state to mark", bool(changes), str(len(changes))):
            return
        before = {v["name"] for v in await listed()}
        made = await socket.call(
            "dashboard_history/create_version",
            dashboard=key,
            level="patch",
            title="Aufgehoben im Prüflauf äöüß",
            description="Diese Version wird gleich wieder entfernt.",
            revision=changes[0]["revision"],
        )
        name = made.get("created")
        if not check("a version to remove was made", bool(name), str(made)):
            return

        # The preview: the words, and nothing changed by asking.
        facts = await remove(name)
        check(
            "the preview answers with the version's own words",
            facts.get("applied") is False
            and facts.get("title") == "Aufgehoben im Prüflauf äöüß"
            and facts.get("description") == "Diese Version wird gleich wieder entfernt."
            and facts.get("revision") == changes[0]["revision"],
            str(facts),
        )
        check(
            "and says the number would come free",
            facts.get("highest") is True,
            str(facts.get("highest")),
        )
        check(
            "and the version is still there after asking",
            name in {v["name"] for v in await listed()},
            name,
        )

        # The fence, from the outside: another dashboard's namespace.
        refused = await remove("someone-else/v1.0.0")
        check(
            "a version of another dashboard is refused with a sentence",
            refused.get("applied") is False
            and "not a version of" in str(refused.get("error", "")),
            str(refused),
        )
        unknown = await remove(f"{key}/v99.99.99")
        check(
            "and so is one that does not exist",
            unknown.get("applied") is False
            and "unknown version" in str(unknown.get("error", "")),
            str(unknown),
        )

        # And the removal itself.
        done = await remove(name, confirm=True)
        check(
            "confirming takes the version away",
            done.get("applied") is True and done.get("name") == name,
            str(done),
        )
        # `_versions_settled` answers bare names, not the dicts `listed`
        # gives - it maps `v["name"]` internally and returns the strings.
        # Indexing them again raises `TypeError: string indices must be
        # integers`, which is where the first draft of this block went.
        after = await _versions_settled(socket, key)
        check(
            "the list no longer holds it",
            name not in after,
            name,
        )
        check(
            "and the bench is as it was found",
            set(after) == before,
            f"{sorted(after)} vs {sorted(before)}",
        )
        # The state is the whole point: the mark went, the history did
        # not. Read back by revision, which is how going back to it works.
        still = (await socket.call("dashboard_history/history", dashboard=key))[
            "changes"
        ]
        check(
            "the state the version marked is still in the history",
            any(c["revision"] == changes[0]["revision"] for c in still),
            changes[0]["revision"],
        )
        check(
            "and no other revision moved",
            [c["revision"] for c in still] == [c["revision"] for c in changes],
            f"{len(still)} vs {len(changes)}",
        )
```

Und im `main`-Block, hinter der `run_retitle`-Zeile:

```python
    print("\n  -- Eine Version wieder aufheben --")
    asyncio.run(run_remove_version(access))
```

- [ ] **Step 2: Run it**

```bash
docker compose -f docker/compose.yaml up -d
python3 tests/integration/run_checks.py
```

Erwartet: alle Prüfungen bestanden, einschließlich der **zwölf** neuen aus `run_remove_version` (nachgezählt an den `check(...)`-Aufrufen). **Die zwei Fallen bei diesem Skript stehen in `docker/README.md`** und sind vor dem Lauf zu lesen.

Zu erwartender Reibungspunkt: Die Prüfung »und die Prüfbank ist, wie sie war« schlägt fehl, wenn zwischen `create_version` und dem Aufheben eine automatische Tagesmarke entsteht. Das ist dann **kein Fehler dieser Änderung**, sondern der bekannte Zustand, dass das Skript seine eigene Bank verändert; in dem Fall ist der Vergleich auf die eine selbst angelegte Version zu verengen, nicht die Prüfung zu streichen.

- [ ] **Step 3: Add the day-mark check**

In `run_day_marks.py`, in `main()` hinter dem zweiten Abschnitt. Es braucht einen Ablauf, der die Marke anlegt, aufhebt und dann noch einmal markiert:

```python
        print("\n  -- Eine aufgehobene Tagesmarke kommt wieder --")
        # Decision 18 says this out loud rather than preventing it, and
        # the dialog in the panel repeats the sentence. Which makes it a
        # promise, and a promise about a rule that runs once a day is
        # worth a check: the alternative reading - "removed means gone" -
        # is the one a person will have.
        where = root / "three"
        store = Rewound(where)
        for text, ago in [(A, 2), (B, 1), (A2, 1), (B, 0)]:
            revision = store.write_snapshot(KEY, text, f"{KEY}: {text.strip()}")
            assert revision is not None
            store.shifts[revision] = ago * DAY
        made = marking.Milestones(Hass(), store, Entry())
        await made.async_lay_the_floor()
        await made._async_mark_day(KEY)
        marked = sorted(v.name.split("/")[-1] for v in store.list_versions(KEY))
        if check(
            "the day was marked to begin with", marked == ["v1.0.0", "v1.0.1"], str(marked)
        ):
            store.remove_version(KEY, f"{KEY}/v1.0.1")
            gone = sorted(v.name.split("/")[-1] for v in store.list_versions(KEY))
            check("and taking the mark away leaves it gone", gone == ["v1.0.0"], str(gone))
            # The same call the next save would make. Nothing else
            # changed: same states, same calendar, same walk.
            await made._async_mark_day(KEY)
            again = sorted(v.name.split("/")[-1] for v in store.list_versions(KEY))
            check(
                "and the next save marks that day again",
                again == ["v1.0.0", "v1.0.1"],
                str(again),
            )
```

- [ ] **Step 4: Run it**

```bash
docker exec -i dashboard-history-test python3 - < tests/integration/run_day_marks.py
```

Erwartet: sechs Prüfungen bestanden, darunter »and the next save marks that day again«. Käme dort `["v1.0.0"]` zurück, wäre die Aussage in Entscheidung 18 und im Panel-Dialog falsch — dann ist **der Satz** zu berichtigen, nicht die Prüfung.

- [ ] **Step 5: Commit (nur nach Ansage des Nutzers)**

```bash
git add tests/integration/run_checks.py tests/integration/run_day_marks.py
git commit -F - <<'MSG'
Prove the mark goes and the state does not

The claim this whole change rests on cannot be made in pytest. Removing
a version is a WebSocket command, a schema and an argument order, and
every fault found in this project so far lived in that layer - so the
check drives a real installation, brings its own version, and takes it
away again, leaving the bench as it found it.

Two of the checks are about what did not happen: the state the version
marked is still in the history, and no other revision moved. Those are
the two ways this could have quietly become a second forget.

And one more in the container, where a clock can be moved: an automatic
day mark that is taken away comes back at the next save. The design
record says so on purpose rather than preventing it, and the panel
repeats the sentence to a person - which makes it a promise, not an
implementation detail.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
```

---

## Task 5: Die Sätze, die falsch werden

**Files:**
- Modify: `FAQ.md` (Abschnitt »What to do instead«, ~Zeile 53; »What you *can* change, at any time«, ~Zeile 65; der Schlussabsatz)
- Modify: `README.md` (die Liste der Dienste, ~Zeile 830 — **und** die Notiz für Skripte darunter, ~Zeile 842)
- Modify: `custom_components/dashboard_history/const.py` (der Kommentar über `KEEP_AS_VERSION`, Zeilen 7–17)
- Modify: `custom_components/dashboard_history/store.py` (der Docstring von `_marked_commit`, ~Zeile 566)
- Modify: `custom_components/dashboard_history/operations.py` (zwei Kommentare: ~Zeile 821 in `async_create_version`, ~Zeile 904 in `async_retitle_version`)

**Interfaces:** keine. Reine Prosa, Englisch, weil jede dieser Flächen nach außen gelesen wird.

**Warum das eine eigene Aufgabe ist und kein Anhängsel:** An **sechs** Stellen steht heute ein Satz, der schlicht falsch wird, und in jedem Fall bleibt der *Schluss* richtig, während die *Begründung* wegfällt:

| Stelle | Der Satz, der fällt |
|---|---|
| `FAQ.md`, Schlussabsatz (~Zeile 78) | »unlike a description, there is nothing that would put a name back« |
| `README.md`, Notiz für Skripte (~Zeile 843) | »nothing in this integration deletes a tag« |
| `const.py`, über `KEEP_AS_VERSION` (Zeile 11) | »nothing in this integration can delete a version again« |
| `store._marked_commit` (~Zeile 566) | »a version, unlike a description, has nothing that deletes it again« |
| `operations.async_create_version` (~Zeile 821) | »this integration has nothing that deletes a tag« |
| `operations.async_retitle_version` (~Zeile 904) | »unlike a description there is nothing that would put a name back« |

Das sind keine Ergänzungen, sondern Berichtigungen, und die Spec nennt das Muster unter Entscheidung 18, »Drittens«, ausdrücklich einen Befund: Kommentare, die eine Auslassung *entschuldigen*, statt eine Entscheidung zu begründen. Sie haben einen eigenen Prüfer verdient. **Alle sechs bleiben stehen und werden umformuliert — keine wird gestrichen.** (Vier davon sind Code-Kommentare und werden in Schritt 6 zusammen erledigt; die zwei in `FAQ.md` und `README.md` in den Schritten 3 und 5. Wo unten »alle vier« steht, sind die Kommentare gemeint.)

⚠️ **Die Zeilennummern in dieser Aufgabe stammen aus der Zeit vor Task 1 bis 3.** `store.py` und `operations.py` wachsen dort um je einige Dutzend Zeilen, `README.md` und `FAQ.md` nicht. Jede Stelle wird über ihren **Wortlaut** gesucht, nie über die Zahl.

- [ ] **Step 1: Correct the answer under »What to do instead«**

**Hinter *beide* vorhandenen Absätze** setzen — also nach »This works because versions group and never squash. …«, nicht zwischen die zwei. Der zweite Absatz beginnt mit »This works because« und bezieht sich auf den ersten; ein Einschub dazwischen nimmt ihm den Bezug.

```markdown
**Or take the wrong one away.** Since a version can be removed, a
number that was given out by mistake is not a permanent fixture: remove
the version and the mark is gone, while the state it pointed at stays
in the history exactly where it was. If the one you remove carries the
highest number, that number becomes free again and the next version you
create will use it — which is the short way out of "I clicked patch and
meant minor".

What this does not do is move a version. Removing one and creating
another is two acts, and the second is addressed at whatever state you
point it at. That is the difference from renaming a number, and it is
the reason the number still is not typed.
```

- [ ] **Step 2: Extend »What you *can* change, at any time«**

Als weiteren Aufzählungspunkt:

```markdown
- Whether a version exists **at all**, in both views, through the bin on
  the version — or with the `dashboard_history.remove_version` service.
  It asks first, and without `confirm` it answers with the words it
  would take. The state stays either way; what cannot be written back
  is the title and description, so the confirmation is there to be read
  rather than clicked through.
```

- [ ] **Step 3: Correct the reasoning in the closing paragraph**

Der letzte Absatz begründet die Ablehnung eines leeren Titels mit »unlike a description, there is nothing that would put a name back«. Diese Begründung fällt weg. Der Satz wird:

```markdown
One thing cannot be undone by this route: a version cannot be left
without a title. Emptying the field is refused rather than accepted,
because a version with no name is a row you cannot pick out of a list
again — and because leaving a field blank is not a way of saying
anything. If what you want is for the version to be gone, the bin says
that plainly and asks you first; a form whose emptiness destroys
something would be a trap.
```

- [ ] **Step 4: Add the service to the README's list**

Der `remove_version`-Dienst gehört in die Aufzählung, an dieselbe Stelle in der Reihenfolge, an der er in `services.yaml` steht — hinter `retitle_version`. Ein Satz, in der Kürze der Nachbarzeilen: dass die Marke geht und der Stand bleibt, und dass es `confirm` verlangt.

Zuvor die Liste lesen:

```bash
grep -n "retitle_version\|create_version\|forget" README.md
```

Und dabei die Zweiteilung der README achten: Teil 1 kommt ohne Interna aus, Teil 2 trägt die Messwerte. Der Dienst gehört in Teil 1; die 202 Bytes gehören, wenn überhaupt, in Teil 2.

- [ ] **Step 5: Correct the note in the README that becomes false**

Nicht die Tabelle aus Schritt 4, sondern die Aufzählung »notes for scripting« darunter (~Zeile 843). Der dritte Punkt lautet heute:

> `create_version` requires a non-empty title. A version without a name is a row nobody can pick out of a list again, **and nothing in this integration deletes a tag**. `retitle_version` requires one for the same reason, so it cannot be used to take a name away.

Der fette Halbsatz wird falsch, und der Satz danach begründet sich mit ihm. Neu:

```markdown
- `create_version` requires a non-empty title. A version without a name
  is a row nobody can pick out of a list again, and leaving a field blank
  is not a way of saying anything. `retitle_version` requires one for the
  same reason, so it cannot be used to take a name away — that is what
  `remove_version` is for, and it says so and asks first.
```

*Nebenbefund in demselben Block, unabhängig von diesem Vorhaben:* Die Überschrift sagt »Three notes for scripting«, darunter stehen **vier** Punkte. Wer den Absatz ohnehin anfasst, macht »Four« daraus; wer das für eine ungefragte Stiländerung hält, lässt es und sagt es dem Nutzer.

- [ ] **Step 6: Correct the four comments in the code that excuse the gap**

Zuerst die Suche, und zwar **diese**:

```bash
grep -rn "delete a version\|delete again\|deletes it again\|deletes a tag\|put a name" README.md FAQ.md custom_components/
```

⚠️ **Nicht die naheliegende Suche.** Ein `grep` nach »nothing in this integration can delete a version again« findet **nichts**: der Satz ist über zwei Zeilen umbrochen (`nothing in this` / `# integration can delete a version again`), und `grep` liest Zeile für Zeile. Dasselbe gilt für den in `store.py`. Eine frühere Fassung dieses Schritts suchte nach `nothing.*delete a version` und meldete null Treffer — woraus ein Umsetzender geschlossen hätte, es sei nichts zu tun.

⚠️ **Und dieselbe Falle noch einmal, am 2026-09-08 im Vorflug der Umsetzung gefunden.** Das Muster oben hieß bis dahin `… \|put a name back` und traf damit **fünf** der sechs Stellen: In `FAQ.md` ist der Satz als `… would put a name` / `back.` umbrochen, in `operations.py` steht `# put a name back.` ganz auf einer Zeile. Ein Muster, das an fünf von sechs Stellen trifft, sieht wie ein funktionierendes aus — und die Schlussprüfung dieses Schritts (»dieselbe Suche noch einmal«) hätte die FAQ-Stelle nie gesehen, weder vorher noch nachher. Gekürzt auf `put a name`. **Nachgezählt und belegt:** 6 Treffer in 5 Dateien (`operations.py` trägt zwei). Wer das Muster erneut anfasst, zählt wieder nach.

Ebenso wenig erledigt **Task 1** diese Stellen: Task 1 fasst `const.py` nicht an und ändert an `store.py` nur, was um `_marked_commit` herum liegt, nicht dessen Docstring. Sie gehören hierher, und der Commit dieser Aufgabe stellt sie bereit.

**Alle vier bleiben stehen und werden umformuliert.** Was sie *begründen* — ein Schema, das einmal einen leeren Titel durchließ; eine Revision, die auf keinen Commit zeigt; die Ablehnung eines leeren Titels an zwei Türen — bleibt richtig; nur das Argument wird ein anderes.

**`const.py`**, der Block über `KEEP_AS_VERSION` (Zeilen 7–17). Der Satz endet heute mit »…, and nothing in this integration can delete a version again.«:

```python
# The shape of `keep_as_version`, in one place because it has two doors.
# The WebSocket command and the service both take it, and while it was
# written out twice they disagreed: one required a title, the other
# accepted any dict at all - so `keep_as_version: {}` with `confirm:
# true` made a real tag with an empty title. A schema stated once cannot
# drift from itself.
#
# Such a tag can be taken away since decision 18, and the schema is
# still the right place to stop it being made: a version somebody has to
# create and then remove again is a fault, not a way of working. The
# sentence here used to end "and nothing in this integration can delete
# a version again", which excused the gap instead of arguing the rule.
#
# Shaped here, never judged: an unknown level is answered by operations
# with a sentence the panel can show, and a schema that refused first
# would take that sentence away.
```

**`store.py`**, der Docstring von `_marked_commit` (~Zeile 566). Der zweite Absatz wird ersetzt; die erste Zeile und die Anführungszeichen bleiben, wie sie sind — hier vollständig, damit nichts zu raten ist:

```python
    def _marked_commit(self, revision: str | None) -> bytes:
        """The commit a version is about to be pinned to.

        Resolved here rather than left to `tag_create`, which takes any
        object at all: a blob id makes a tag that reads back as a version
        and can never be returned to. Such a tag can be taken away since
        decision 18, and it is still refused here - a version somebody
        has to create and then remove again is a fault, not a way of
        working. Refused as a ValueError, the same kind of answer a
        colliding name gives, so the one place that already catches those
        needs no second branch.
        """
```

**`operations.py`**, in `async_create_version` (~Zeile 821):

```python
        # A version is a name for a state, so one without a name is not
        # a version - it is a row somebody cannot pick out of a list
        # again, and leaving a field blank is not a way of saying
        # anything. (It used to say "and this integration has nothing
        # that deletes a tag"; since decision 18 it has, and the fence
        # stands on its own reason instead.)
```

**`operations.py`**, in `async_retitle_version` (~Zeile 904):

```python
        # The same fence `async_create_version` puts up, for the same
        # reason: a version without a name is a row nobody can pick out
        # of a list again. Emptying the field would be a way to *unname*
        # a version, and that is not what an empty field means - whoever
        # wants the version gone says so with `remove_version`, which
        # asks first. A form whose emptiness destroys something would be
        # a trap.
```

Danach dieselbe Suche noch einmal: sie darf nur noch die Stellen zeigen, die dieser Schritt neu geschrieben hat, und keinen Satz mehr, der die Lücke entschuldigt.

- [ ] **Step 7: Run the suite (the docs are read by tests too)**

```bash
python3 -m pytest tests/ -q
```

Erwartet: **510 bestanden**, unverändert gegenüber Task 3.

- [ ] **Step 8: Commit (nur nach Ansage des Nutzers)**

```bash
git add FAQ.md README.md \
        custom_components/dashboard_history/const.py \
        custom_components/dashboard_history/store.py \
        custom_components/dashboard_history/operations.py
git commit -F - <<'MSG'
Correct the sentences a removal makes false

Seven of them, in five files, and each one keeps its conclusion and
changes its argument. The FAQ refused an empty title with "unlike a
description, there is nothing that would put a name back". That reason
is gone; the refusal is not. A version with no name is a row nobody can
pick out of a list, and leaving a field blank is not a way of saying
anything.

The README said the same thing to whoever scripts this: "nothing in
this integration deletes a tag". Something does now, it asks first, and
the note says which service it is.

Four comments in the code apologised for the gap rather than arguing
the rule - two of them worded so that a grep for the phrase finds
nothing, because the sentence is wrapped across two lines. A schema
that once let an empty title through is still the right place to stop
one: a version somebody has to create and then remove again is a fault,
not a way of working.

And the FAQ's other answer grows a second half. "Put a second version
beside the first" was the whole of what to do about a number you did
not mean; taking the wrong one away is the shorter way, and where it
carried the highest number that number comes back.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
```

---

## Reihenfolge und was daran nicht verhandelbar ist

1 → 2 → 3 sind aufeinander angewiesen: die Schnittstelle braucht den Store, das Panel braucht die Schnittstelle. **4 und 5 dürfen nicht vorgezogen werden**, aber 4 muss vor der Abnahme kommen — Task 4 ist die einzige Stelle, an der die tragende Behauptung dieses Vorhabens überhaupt geprüft wird: *die Marke geht, der Stand bleibt*. Eine Umsetzung, die nach Task 3 als fertig gemeldet wird, ist nicht fertig.

## Selbstprüfung dieses Plans

**Deckung gegen Entscheidung 18:** Festlegung 1 (nur die Ref) → Task 1, Schritt 5 samt drei Tests in Schritt 1; Festlegung 2 (`_owns`) → Task 1, zwei Tests; Festlegung 3 (Nummern) → Task 1, `test_versions.py`; Festlegung 4 (Tagesmarke) → Task 3 (Dialogsatz) und Task 4 (Nachweis der Rückkehr); Festlegung 5 (`confirm` und Vorschau) → Task 2 und Task 3; Festlegung 6 (leichtgewichtige Tags) → Task 1 und Task 3. Die zwei Wege mit verschiedenen Kosten stehen im Docstring aus Task 2, Schritt 3. Die Randfälle der Spec sind einzeln in Task 1 und Task 4 abgedeckt; »Letzte Version aufgehoben« braucht keinen eigenen Schritt, weil der Leersatz in `simple.js` bereits existiert und `test_a_version_can_be_taken_away` in die Lage läuft.

**Drei Dinge, die dieser Plan bewusst *hinzunimmt* und die nicht in der Spec stehen:**

- `_version_from` als geteilter Bauplan (Task 1, Schritt 3). Grund: Es gibt jetzt zwei Leser derselben Sache, und `_version_dict` eine Schicht höher warnt in seinem eigenen Docstring genau vor der Drift, die zwei Bauplätze erzeugen.
- Der `services.py`↔`services.yaml`-Test (Task 2, Schritt 1). Grund: Ohne ihn ist die Schnittstellen-Schicht in reinem pytest unprüfbar, und ein fehlender Eintrag zeigt sich erst in den Developer Tools eines laufenden Home Assistant.
- Der Block in `look_at_panel.py` (Task 3, Schritt 9). Grund: Der Knopf ist der vierte Fall, vor dem der Kommentar in `style.js` warnt, und sein Versagen ist stille Unsichtbarkeit — kein Test in `tests/` kann das sehen, weil keiner eine Deckkraft berechnet.

Alle drei sind im jeweiligen Task begründet und im Commit-Body genannt, damit ein späterer Leser nicht rätselt, was das mit »Versionen aufheben« zu tun hatte.

---

## Nachtrag vom 2026-09-08: die Review-Runde

Der Plan lief durch zwei unabhängige Reviews, bevor eine Zeile davon umgesetzt wurde. Was sie fanden, steht hier — nicht als Buchhaltung, sondern weil zwei der Befunde eine Sorte Fehler sind, die dieses Vorhaben ein zweites Mal machen könnte.

**Zwei blockierende Befunde, die beide Reviews unabhängig fanden:**

1. **`el.shadowRoot` fehlte im Panel-Szenario.** Empirisch nachgestellt. Alle zwanzig Szenarien der Datei weisen selbst zu; das neue tat es nicht, und der Lauf wäre an der Fixture gestorben statt an einer Aussage. Verschärfend hatte der Plan an derselben Stelle eine Anmerkung, die den Umsetzenden in die falsche Datei geschickt hätte (`_PRELUDE`).
2. **Die Testzahlen waren um eins verschoben** — 10 neue Store-Fälle, nicht 11. Der Plan macht die Zahl zum Prüfstein, also hätte eine korrekte Umsetzung falsch ausgesehen.

**Ein Befund aus der Aufrufpfad-Lesung:** `async_remove_version` las die Ref auf dem Schreibpfad zweimal und fing `ValueError` nur um die erste Lesung. Das widersprach dem eigenen Docstring (»the removal is built to read one ref«) und verletzte eine Regel, die dieses Repository über sich selbst dokumentiert: in `tests/test_store.py` steht »`operations.py` catches ValueError, … and `services.py` does not«. `create_version` und `retitle_version` — die einzigen beiden anderen Store-Aufrufe, die heben können — sind ausnahmslos umschlossen. Behoben in Task 2, Schritt 3.

**Und zwei Befunde derselben Sorte, die den ganzen Aufwand wert waren:**

3. **Der Grep in Task 5 fand die Stellen nicht, die er versprach.** Beide Kommentare sind über zwei Zeilen umbrochen, und `grep` liest Zeile für Zeile. Der Plan behauptete darüber hinaus, Task 1 erledige sie, und ließ für eine der beiden die Formulierung offen. Ein Umsetzender, der dem Befehl traut, hätte geschlossen, es sei nichts zu tun.
4. **Es waren nicht zwei Stellen, sondern sechs.** Erst der berichtigte Grep fand die Notiz in der README (»nothing in this integration deletes a tag«) und zwei weitere Kommentare in `operations.py`. Die README-Notiz hatte keines der beiden Reviews von sich aus gesehen — sie kam heraus, weil der Grep repariert und dann *ausgeführt* wurde.

**Was daraus für die Umsetzung folgt, über die Berichtigungen hinaus:** Ein `grep`, der nichts findet, ist keine Abwesenheit — er ist eine Vermutung, bis er einmal an einer bekannten Fundstelle bewiesen hat, dass er trifft. Dieselbe Falle, gegen die Task 2 seinen eigenen Test baut: Der `services.py`↔`services.yaml`-Vergleich existiert, weil zwei Dateien nichts verband, und Task 5 stolperte über genau das eine Verzeichnis weiter. Wer diesen Plan ausführt und irgendwo eine Suche als Beweis benutzt, führt sie zuerst gegen eine Stelle, von der er weiß, dass sie da ist.

**Die Zählungen nach der Runde**, damit niemand sie erneut ausrechnet: Ausgangsstand **489** → Task 1 **501** → Task 2 **502** → Task 3 **510** → Task 5 **510** (unverändert, reine Prosa). `run_remove_version` bringt **zwölf** Prüfungen mit, `run_day_marks.py` kommt auf **sechs**.
