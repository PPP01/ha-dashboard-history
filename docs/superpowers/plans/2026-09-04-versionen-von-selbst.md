# Vorhaben H, erste Hälfte — Versionen, die von selbst entstehen (Daten)

> **Für agentische Ausführung:** ERFORDERLICHER SUB-SKILL: `superpowers:subagent-driven-development` (empfohlen) oder `superpowers:executing-plans`, Aufgabe für Aufgabe. Die Schritte tragen Checkboxen (`- [ ]`) zum Mitführen.

**Ziel:** Jedes Dashboard trägt Versionen, ohne dass jemand welche anlegt — eine beim Einrichten und eine je Tag, an dem etwas passiert ist.

**Architektur:** Vier Aufgaben, von innen nach außen. Die reine Rechnung (Tageswechsel, Titel, Markierung) kommt in `versions.py` und ist damit in reinem pytest prüfbar. Ein neues Modul `milestones.py` verdrahtet sie: Es legt beim Start den Boden und hört danach auf `EVENT_HISTORY_UPDATED`. `operations.py` reicht die Markierung als Feld nach außen. Der OptionsFlow bekommt den Schalter. **Geschrieben wird kein Dashboard** — dieses Vorhaben legt Tags an, sonst nichts.

**Technik:** Python 3.12 (Entwicklung) / 3.14 (Container), dulwich 1.2.14, pytest, Home Assistant 2026.8.3.

**Spec:** `docs/superpowers/specs/2026-08-30-dashboard-history-design.md` — Entscheidung 17 und Vorhaben H. Die Zeilen des Test-Plans, die hier eingelöst werden: »Einrichtung mit bestehenden Dashboards«, »Erster Speichervorgang eines Tages«, »Zweiter Speichervorgang desselben Tages«, »Tag ohne Speichervorgang«, »Tagesversionen abgeschaltet«.

## Der Zuschnitt, und warum er so ist

Vorhaben H enthält laut Spec vier Dinge »in einem Zug«: Initialtag, automatische Tagesversionen, Moduswechsel und die Oberfläche für beide Modi. Das ist als *Vorhaben* richtig zusammengebunden, aber als *Plan* zu viel für ein Dokument — `panel.js` allein sind 1421 Zeilen, und die Oberfläche lässt sich erst sinnvoll schreiben, wenn die Versionen, auf denen sie steht, wirklich existieren und an einer laufenden Anlage geprüft sind. Genau die Teilung, die Vorhaben G schon hatte.

**Dieser Plan ist die Datenhälfte.** Danach folgt ein zweiter, die Oberflächenhälfte:

- Moduswechsel einfach/erweitert, **im `localStorage` des Panels**, Vorgabe *einfach* — entschieden am 2026-09-04. Die Spec nennt den Modus »eine Einstellung der Oberfläche«, und dort gehört er dann auch hin: kein Backend, kein Neustart, kein zusätzlicher WebSocket-Befehl, je Person und Browser wählbar. Vorgabe *einfach*, weil Entscheidung 17 ihn zum Normalweg erklärt; der Preis ist benannt und einmalig, nämlich dass ein bestehender Nutzer nach dem Update einmal umschalten muss.
- Die zwei Ansichten in `panel.js`, Register »Änderungen«/»Versionen«, Suchfeld, »Ältere laden« auf `next_cursor`, der Vorgabewert von 50 auf 25.
- Der Rücksprung-Dialog samt der Frage, ob der jetzige Stand eine Version bekommen soll.

**Reihenfolge ist Pflicht: G, dann diese Hälfte, dann die Oberfläche.** Nicht Geschmack. Dieser Plan setzt `async_versions` in der Form voraus, die Aufgabe 4 von Vorhaben G ihm gibt (`same_as_now` je Version), und ergänzt `matching_versions` aus dessen Aufgabe 3 um ein Feld. Wer hier vor G anfängt, schreibt in Funktionen, die es noch nicht in dieser Form gibt.

## Globale Randbedingungen

Aus der Spec, für **jede** Aufgabe verbindlich:

- **Kein Systemaufruf von `git`.** Ausschließlich `dulwich`.
- **Keine Home-Assistant-Interna abfangen oder ersetzen.** Kein Monkey-Patching. Der Config-Entry-Reload und der OptionsFlow sind öffentliche APIs und ausdrücklich erlaubt.
- **`yaml_io.py`, `analyze.py`, `restore.py`, `versions.py` bleiben Home-Assistant-frei.** Aufgabe 1 erweitert `versions.py` und darf dabei nur die Standardbibliothek benutzen. `milestones.py` ist ausdrücklich **kein** Mitglied dieser Liste und darf Home Assistant importieren.
- **Blockierende Arbeit gehört in einen Executor** (`hass.async_add_executor_job`). Jeder git-Zugriff ist blockierend, das Anlegen eines Tags eingeschlossen.
- **Nichts blockiert den Start von Home Assistant.** Eine Version, die nicht entstehen konnte, ist eine fehlende Marke; ein Speichervorgang, der daran scheitert, wäre ein verlorener Stand. Jede Ausnahme in `milestones.py` wird protokolliert und verschluckt.
- **Nichts wird ohne Vorschau geschrieben** — gilt hier nicht, weil hier kein Dashboard-Stand geschrieben wird. Ein Tag ist nach Entscheidung 7 ausdrücklich ausgenommen, so wie `create_version` es schon heute ist.
- **Alles im Code ist Englisch** — Kommentare, Docstrings, Testnamen, Versionstitel, die Namen der Integrationsprüfungen, die Texte in `strings.json`. Deutsch sind nur die Prosa dieses Plans und die Abschnittsköpfe, die `main` in `run_checks.py` ausgibt.
- **Commit-Botschaften auf Englisch**, Subject im Imperativ, erster Buchstabe groß, max. 50 Zeichen, Leerzeile, Body max. 72 Zeichen pro Zeile mit dem *Warum*, Abschluss `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- **Die Oberfläche wird hier nicht angefasst.** Keine Zeile in `panel.js`.

**Tests:** `python3 -m pytest tests/ -v` — muss durchgehend grün bleiben.

**Zur Testzahl, und warum hier keine nackte steht.** `tests/test_yaml_io.py` parametrisiert über die Dashboards einer *echten* Ablage — dem Pfad aus `DASHBOARD_HISTORY_REAL_STORAGE` oder `tests/.real-storage`. Die Gesamtzahl hängt damit an der Maschine, auf der gelaufen wird, und ändert sich, sobald dort ein Dashboard dazukommt. Gemessen am 2026-09-04: derselbe Baum meldet `256 passed, 3 skipped` ohne echte Ablage und `269 passed` mit einer, in der zehn Dashboards liegen. Die Zahlen hier stehen deshalb **in der Form ohne echte Ablage** — die einzige, die auf jeder Maschine dieselbe ist, und die Form, die auch die CLAUDE.md des Projekts nennt. Wer mit echter Ablage prüft, vergleicht die **Zuwächse**, nicht die Summe.

**Ausgangsstand nach Vorhaben G: `256 passed, 3 skipped`.**

**Am 2026-09-04 im Testcontainer nachgesehen**, damit niemand es erneut ausprobieren muss:

| Frage | Antwort, gemessen an HA 2026.8.3 |
|---|---|
| `OptionsFlow.__init__` | `(self, /, *args, **kwargs)` — **kein** `config_entry`-Argument. Es gibt eine geerbte Eigenschaft `config_entry`, die den Eintrag über `hass` nachschlägt und *innerhalb* von `__init__` noch nicht verfügbar ist. Ältere Beispiele im Netz setzen `self.config_entry = entry`; das ist hier falsch. |
| `async_get_options_flow` | `(config_entry: ConfigEntry) -> OptionsFlow` |
| Config-Entry neu einrichten | `POST /api/config/config_entries/entry/{entry_id}/reload`, antwortet `{"require_restart": bool}`. Läuft `async_unload_entry` und `async_setup_entry` und **wartet auf beides** — nach der Antwort ist die Einrichtung durch. |
| OptionsFlow über HTTP | `POST /api/config/config_entries/options/flow` mit `{"handler": "<entry_id>"}`, dann `POST …/options/flow/{flow_id}` mit den Feldern. |
| Zeitzone | `homeassistant.util.dt.DEFAULT_TIME_ZONE` existiert. Es ist eine **Modulvariable**, die Home Assistant beim Start aus der Konfiguration setzt — sie muss deshalb bei jedem Aufruf gelesen und darf niemals zwischengespeichert werden. |

---

### Aufgabe 1: Der Tageswechsel und die Markierung — reine Rechnung

**Dateien:**
- Ändern: `custom_components/dashboard_history/versions.py`
- Test: `tests/test_versions.py`

**Schnittstellen:**
- Liefert, alles in `versions.py` und Home-Assistant-frei:
  - `AUTOMATIC: str` — die Markierungszeile, die eine selbsttätig angelegte Version in ihrer Beschreibung trägt.
  - `automatic_description(text: str = "") -> str` — die Beschreibung, die eine solche Version bekommt.
  - `read_description(text: str) -> tuple[str, bool]` — eine gespeicherte Beschreibung als *(was ein Mensch geschrieben hat, war es selbsttätig)*.
  - `local_day(timestamp: int, zone: tzinfo) -> date`
  - `same_day(one: int, other: int, zone: tzinfo) -> bool`
  - `day_title(timestamp: int, zone: tzinfo) -> str` — `»3 September 2026«`.

**Warum das hier liegt und nicht in `milestones.py`.** Der Modulkopf von `versions.py` nennt den Grund für seine Existenz: »eine kleine Rechnung, die auf eine Art falsch sein kann, die monatelang niemandem auffällt«. Ein Tageswechsel ist genau diese Art Rechnung — Zeitzone, Sommerzeit, Monatsnamen. Beides sind Fälle, die man nicht im Panel bemerkt und die reines pytest in Sekunden erledigt. Die harte Regel bleibt dabei wörtlich erhalten: `versions.py` importiert weiterhin nichts von Home Assistant, nur `datetime` aus der Standardbibliothek.

**Das Beispiel in der Spec ist deutsch, der Titel wird englisch.** Entscheidung 17 schreibt »3. September 2026«; hier steht `3 September 2026`. Das ist keine Abweichung im Inhalt, sondern die Sprachregel des Projekts: Ein Versionstitel steht in `git`-Tags und damit vor jedem fremden Mitwirkenden, und für die zählt Englisch. Ausdrücklich vermerkt, damit es niemand später als Tippfehler berichtigt.

**Zwei Fallen, die hier zugemacht werden.** Erstens `strftime("%B")`: Der Monatsname folgt der C-Locale des Containers, in dem Home Assistant läuft — dieselbe Version hieße auf einer Anlage »September« und auf der nächsten »Septembre«. Die Namen stehen deshalb als Tabelle im Modul. Zweitens UTC: Ein Speichervorgang um halb eins nachts in Berlin ist für den Menschen davor der nächste Tag und für UTC noch derselbe. Die Spec sagt dazu ausdrücklich »der Kalendertag in der Zeitzone, die Home Assistant selbst konfiguriert hat — nicht UTC«.

- [ ] **Schritt 1: Die fehlschlagenden Tests schreiben**

In `tests/test_versions.py` ans Ende anfügen — der Kopf des Moduls braucht zusätzlich `from datetime import datetime, timezone` und `from zoneinfo import ZoneInfo`:

```python
# -- the day a state belongs to ----------------------------------------

BERLIN = ZoneInfo("Europe/Berlin")


def _at(text: str, zone=BERLIN) -> int:
    """A local wall-clock time as the epoch seconds a commit would hold."""
    return int(datetime.fromisoformat(text).replace(tzinfo=zone).timestamp())


def test_two_states_on_one_local_day_are_one_day():
    assert versions.same_day(_at("2026-09-03T08:00"), _at("2026-09-03T23:59"), BERLIN)


def test_midnight_starts_a_new_day():
    assert not versions.same_day(
        _at("2026-09-03T23:59"), _at("2026-09-04T00:01"), BERLIN
    )


def test_the_day_is_the_users_day_and_not_utc():
    # 23:30 UTC is already the next day in Berlin. Judged in UTC these two
    # states fall on one day; judged where the person lives, on two. The
    # daily version is named after the day *they* had.
    morning = _at("2026-09-03T07:00", timezone.utc)
    late = _at("2026-09-03T23:30", timezone.utc)
    assert versions.same_day(morning, late, timezone.utc)
    assert not versions.same_day(morning, late, BERLIN)


def test_the_clocks_going_forward_do_not_split_a_day():
    # 2026-03-29: Berlin skips 02:00-03:00. A day is still one day.
    assert versions.same_day(_at("2026-03-29T01:30"), _at("2026-03-29T03:30"), BERLIN)


def test_the_clocks_going_back_do_not_join_two_days():
    # 2026-10-25: Berlin lives 02:00-03:00 twice. Two days stay two.
    assert not versions.same_day(
        _at("2026-10-25T02:30"), _at("2026-10-26T02:30"), BERLIN
    )


def test_the_title_is_the_day_it_marks():
    assert versions.day_title(_at("2026-09-03T21:15"), BERLIN) == "3 September 2026"


def test_the_title_follows_the_local_day_too():
    stamp = _at("2026-09-03T22:15", timezone.utc)
    assert versions.day_title(stamp, timezone.utc) == "3 September 2026"
    assert versions.day_title(stamp, BERLIN) == "4 September 2026"


def test_the_month_is_english_whatever_the_container_thinks():
    # Deliberately not strftime("%B"), which follows the C locale of
    # whatever container Home Assistant runs in - the same tag would then
    # read differently on two installations.
    assert versions.day_title(_at("2026-01-09T12:00"), BERLIN) == "9 January 2026"
    assert versions.day_title(_at("2026-12-31T12:00"), BERLIN) == "31 December 2026"


# -- versions nobody asked for -----------------------------------------


def test_an_automatic_version_says_that_it_is_one():
    assert versions.read_description(versions.automatic_description()) == ("", True)


def test_a_persons_own_description_is_not_marked():
    assert versions.read_description("Before the heating rework") == (
        "Before the heating rework",
        False,
    )


def test_the_marker_is_never_shown_to_anybody():
    # It is bookkeeping. A list that prints its own bookkeeping is one
    # nobody trusts.
    text = versions.automatic_description("The last state of that day.")
    assert versions.read_description(text) == ("The last state of that day.", True)
    assert versions.AUTOMATIC not in versions.read_description(text)[0]


def test_an_empty_description_is_nobodys_words():
    assert versions.read_description("") == ("", False)
```

- [ ] **Schritt 2: Laufen lassen, Fehlschlag prüfen**

```bash
python3 -m pytest tests/test_versions.py -v
```

Erwartet: zwölf Fehlschläge mit `AttributeError: module 'versions' has no attribute 'same_day'` und Geschwistern davon.

- [ ] **Schritt 3: Umsetzen**

In `versions.py` den Modulkopf um die Erwähnung des Tages erweitern — der Docstring sagt heute nur »Version numbers«, und das stimmt dann nicht mehr. Die erste Zeile ersetzen:

```python
"""Version numbers and daily marks: reading, ordering, counting up.
```

Und im selben Docstring nach dem Absatz über `v1.10.0` einfügen:

```
The day a recorded state belongs to lives here for the same reason. A
calendar day is a small calculation that goes wrong quietly - a time
zone, a change of the clocks, a month name that follows whatever locale
the container was built with - and plain pytest settles all three in
under a second.
```

Die Importe oben ergänzen. **Nur die letzte Zeile ist neu** — `re` und `Iterable` stehen bereits dort; der Block ist zum Abgleich vollständig abgedruckt, nicht zum Einfügen:

```python
import re                                    # steht schon da
from collections.abc import Iterable         # steht schon da
from datetime import date, datetime, tzinfo  # neu
```

Und ans Ende der Datei anfügen:

```python
# -- versions nobody asked for -----------------------------------------

# The first line of the description an automatically made version
# carries. A marker, not a sentence: what a person gets to read is built
# from the flag this sets, so rewording it later fixes every tag that
# already exists rather than only the next one. It stays out of the
# *title*, which the simple mode shows on its own and which has room for
# the date and nothing else.
AUTOMATIC = "dashboard-history: automatic"

# Spelled out rather than left to strftime("%B"). That follows the C
# locale of whatever container Home Assistant runs in, so the same tag
# would read "September" on one installation and something else on the
# next - and a version name that depends on the machine is not a name.
_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def automatic_description(text: str = "") -> str:
    """The description an automatically made version carries."""
    return f"{AUTOMATIC}\n{text}".rstrip() if text else AUTOMATIC


def read_description(text: str) -> tuple[str, bool]:
    """A stored description as (what a person wrote, was it automatic).

    The marker is taken out rather than shown. Reported as a field, it is
    something the interface can act on; reported as prose, it is a line
    of machine talk in the middle of somebody's own words.
    """
    head, _, rest = text.partition("\n")
    if head.strip() == AUTOMATIC:
        return rest.strip(), True
    return text.strip(), False


def local_day(timestamp: int, zone: tzinfo) -> date:
    """The calendar day a recorded state falls on, where the user lives.

    Not UTC, and the design record says so in as many words. A save at
    half past midnight in Berlin is the next day to the person who made
    it and the same day to UTC; the daily version is named after the day
    *they* had.
    """
    return datetime.fromtimestamp(timestamp, zone).date()


def same_day(one: int, other: int, zone: tzinfo) -> bool:
    """Whether two recorded states fall on the same local calendar day.

    Compared as dates, not as a difference in seconds. A day is not
    86400 seconds wherever the clocks change: the Sunday in March has
    23 hours and the one in October has 25, and both are one day to
    everybody living through them.
    """
    return local_day(one, zone) == local_day(other, zone)


def day_title(timestamp: int, zone: tzinfo) -> str:
    """What an automatic daily version is called: `3 September 2026`."""
    when = datetime.fromtimestamp(timestamp, zone)
    return f"{when.day} {_MONTHS[when.month - 1]} {when.year}"
```

- [ ] **Schritt 4: Laufen lassen, Erfolg prüfen**

```bash
python3 -m pytest tests/test_versions.py -v
python3 -m pytest tests/ -q
```

Erwartet: alle grün, **`268 passed, 3 skipped`** (zwölf mehr).

- [ ] **Schritt 5: Committen**

```bash
git add custom_components/dashboard_history/versions.py tests/test_versions.py
git commit -m "$(cat <<'EOF'
Work out which day a recorded state belongs to

Decision 17 marks the state before the first change of a new day, so
something has to decide when a day ends. It lands here, beside the
version numbers, for the reason that module exists at all: this is a
small calculation that goes wrong quietly. A day is not 86400 seconds
where the clocks change, midnight is not the same moment everywhere,
and strftime would take the month name from the container's locale -
the same tag reading differently on two installations.

The marker that says a version was made automatically lives here too.
It is a field to the interface and never a line of prose in the middle
of somebody's own words.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Aufgabe 2: Die Bodenversion bei der Einrichtung

**Dateien:**
- Anlegen: `custom_components/dashboard_history/milestones.py`
- Ändern: `custom_components/dashboard_history/__init__.py`
- Ändern: `custom_components/dashboard_history/operations.py` (neu: `_version_dict`; benutzt in `async_history` und `async_versions`)
- Ändern: `custom_components/dashboard_history/services.yaml` (Beschreibung von `versions`)
- Test: `tests/integration/run_checks.py` (neue Helfer `entry_id`, `reload_entry`; neue Prüfung `run_milestones`)

**Schnittstellen:**
- Verbraucht: `versions.day_title`, `versions.automatic_description`, `versions.read_description` aus Aufgabe 1; `HistoryStore.list_dashboards()`, `list_versions(key)`, `list_changes(key, limit)`; `operations.async_create_version(hass, store, key, level, title, description, revision)`.
- Liefert: `Milestones(hass, store, entry)` mit `async_lay_the_floor() -> list[str]`. Aufgabe 3 ergänzt dieselbe Klasse um `async_arm()`, `async_disarm()` und `_async_mark_day(key)`.
- Liefert: `operations._version_dict(version) -> dict` mit `name`, `revision`, `title`, `description`, `automatic`. Jede Stelle, die eine Version nach außen gibt, benutzt ihn.

**Was der Boden ist.** Die Spec sagt: »Bei der Einrichtung bekommt jedes bestehende Dashboard ein `v1.0.0`. Das ist der Stand, auf den man zurückkann, bevor irgendetwas passiert ist.« Umgesetzt als Regel statt als einmaliger Lauf: **Jedes lebende Dashboard, das einen aufgezeichneten Stand und noch gar keine Version hat, bekommt `v1.0.0` auf seinen neuesten Stand.** Das ist von selbst wiederholbar — ein zweiter Start legt nichts an, weil dann eine Version da ist — und es erfüllt die Test-Plan-Zeile »jedes bekommt genau ein `v1.0.0`, keines zweimal« ohne ein Merkmal im Config-Entry, das irgendwann nicht mehr zum Zustand der Ablage passt. Ein Dashboard, das später angelegt wird, bekommt seinen Boden beim nächsten Start.

> **Am 2026-09-05 berichtigt: der Boden liegt auf dem *ältesten* aufgezeichneten Stand, nicht auf dem neuesten.** Der Satz oben sagte »auf seinen neuesten Stand«, und für die Einrichtung selbst ist das dasselbe — dort gibt es genau einen Eintrag, den der Startdurchlauf gerade angelegt hat. Für ein Dashboard, das *später* entsteht, ist es das nicht: Bis der nächste Start seinen Boden legt, hat es schon eine Historie, und sein neuester Stand ist das, was gerade auf dem Schirm steht. Ein »Zurück zu dieser Version«, nach dem sich nichts ändert, ist kein Angebot. Der Spec-Wortlaut — »der Stand, auf den man zurückkann, **bevor irgendetwas passiert ist**« — meint den ältesten. Der Preis ist ein vollständiger Walk über die Historie dieses einen Dashboards; er fällt genau einmal an, weil die Prüfung auf eine vorhandene Nummer davor zurückkehrt.

**Nur lebende Dashboards**, gelesen aus dem Baum an HEAD (`list_dashboards`, nicht `list_all_dashboards`). Ein gelöschtes hat diesen Baum verlassen; sein neuester Eintrag ist die Löschzeile, und dort lehnt `async_create_version` seit dem 2026-09-02 ab — es gibt keinen Stand, auf den man zurückkönnte. Die Ablehnung greift also ohnehin, aber sie hier gar nicht erst auszulösen erspart eine Warnung je gelöschtem Dashboard bei jedem Start.

**Der Titel ist auch beim Boden der Tag.** Er könnte »Before Dashboard History started« heißen, tut es aber nicht: Der einfache Modus zeigt eine Liste von Titeln, und eine Liste aus lauter Daten mit einem Satz dazwischen liest sich schlechter als eine Liste aus lauter Daten. Beide Sorten tragen dieselbe Markierung und denselben Code-Pfad; unterschieden werden sie durch die Nummer, und `v1.0.0` ist erkennbar genug.

> **Am 2026-09-05 ergänzt, weil dieser Absatz einen Fall nicht betrachtet hat.** Wenn Boden und erste Tagesmarke denselben Tag treffen, tragen sie denselben Titel — und der einfache Modus zeigt nichts als Titel. Der Fall ist nicht exotisch: frische Einrichtung, Nutzer ändert am selben Tag noch etwas, am Folgetag entsteht die Marke auf diesem zweiten Stand. Die Doppel-Prüfung über die Revision greift dort nicht, weil es zwei verschiedene Revisionen sind. Zwei optisch gleiche Zeilen mit je einem eigenen »Zurück«-Knopf sind für genau die Person unauflösbar, für die dieser Modus gebaut ist. Die Regel dahinter heißt deshalb ab hier: **ein Tag trägt höchstens eine automatische Version.** Sie steht als `versions.automatic_days` in reinem pytest und ist weiter gefasst als die Revisions-Prüfung, die sie nicht ersetzt, sondern ergänzt. Was sie kostet, ist benannt: Fällt der Boden auf denselben Tag wie das erste Tagesende, bleibt der Boden stehen und das Tagesende ungemarkt — im erweiterten Modus ist der Stand weiterhin da.

> **Am 2026-09-08 ergänzt, nach einer Beobachtung an der Anlage.** Das Dashboard `dh-move-check` trug drei automatische Versionen, von denen zwei »same state as now« zeigten und nur eine einen Knopf hatte. Ursache: Die Tagesmarke wird aus dem Kalender gerechnet, nicht aus dem Inhalt. Ein Dashboard, das geändert und zurückgeändert wird — eine Karte hin und wieder her, oder ein Prüflauf, der jede Nacht dieselbe Datei schreibt — endet jeden Tag auf dem Stand, mit dem er begann, und sammelt eine Version pro Tag, die alle dasselbe halten. Der einfache Modus lässt bei solchen Zeilen den Knopf weg, weil ein »Zurück« dort nichts ändern würde; was bleibt, ist genau die Wand aus datierten Zeilen ohne Angebot, gegen die dieser Modus gebaut ist. Dritte Regel deshalb, neben der Revision und dem Tag: **keine automatische Marke, wenn der Stand, der markiert werden soll, derselbe ist wie der der höchstnummerierten vorhandenen Version.** Verglichen wird über die Blob-Kennung der Konfiguration (`store.same_state`), nicht über den Text — git benennt einen Blob nach seinen Bytes, also ist es ein Tree-Zugriff je Seite statt zweier gelesener Dashboards.
>
> **Warum gegen die höchstnummerierte und nicht gegen alle.** Sie ist die, von der `candidates` hochzählt und die der einfache Modus in seinem Satz nennt — neben ihr wäre eine neue Marke redundant. Gegen *alle* zu vergleichen würde einen Rückgriff verschlucken: Wer auf einen alten Stand zurückgeht, hält danach etwas, das eine ältere Version schon trägt, und der Tag dieses Rückgriffs bliebe für immer ungemarkt. So bekommt er seine Marke, weil die höchste Version etwas anderes hält. Verhindert wird damit das **unmittelbare** Duplikat, nicht jedes: Ein Dashboard, das über Tage zwischen zwei Ständen pendelt, sammelt weiter eine Marke pro Tag, und jede dupliziert eine ältere Version. Diese Zeilen tragen aber einen wirksamen Knopf — was das Dashboard gerade hält, ist der jeweils andere Stand —, sind also nicht die Wand ohne Angebot, um die es hier geht. Sie mitzudrücken wäre derselbe Fehler wie der Vergleich gegen alle Versionen, von der anderen Seite. `versions.highest` beantwortet »welche ist die höchste« und liegt in reinem pytest — nicht `by_number(...)[0]`, denn diese Liste führt handgemachte Tags mit und hätte auf einem Dashboard ohne jede Nummer deren Namen zurückgegeben.
>
> **Was die Regel nicht sieht.** Verglichen wird die Konfiguration, nicht die Metadaten — ein Speichervorgang, der nur den Titel oder das Symbol ändert, gilt hier als derselbe Stand und bekommt keine Marke. Das ist Absicht und keine Lücke: Beim Wiederherstellen eines noch vorhandenen Dashboards schreibt `operations.async_restore_state` allein die Konfiguration zurück, nie die Metadaten (die werden nur beim Neuanlegen eines verschwundenen Dashboards gelesen). Eine Version auf so einem Stand könnte den alten Namen also gar nicht zurückholen; die Umbenennung selbst steht weiterhin als Zeile in der Historie.
>
> **Wie es geprüft ist.** `versions.highest` und `store.same_state` in reinem pytest, mit den Fällen unbekannte Revision, Dashboard existierte damals noch nicht, und »nur die Metadaten unterscheiden sich«. Die Verdrahtung in `_async_mark_day` liegt hinter einem Tageswechsel und ist damit aus der laufenden Instanz nicht zeigbar — dieselbe Grenze, die `run_checks.py` bei der Tagesmarke schon benennt (»no API can backdate a commit«). Sie liegt deshalb als `tests/integration/run_day_marks.py` — ein dritter Prüfweg, der im Testcontainer läuft, wo `homeassistant` existiert, aber ohne laufende Instanz: echtes Repository, echte Tags, echter Vergleich, verstellt nur die Uhr in `list_changes`. Zwei Läufe, und sie unterscheiden sich in einem einzigen Byte am Ende des markierten Tages: derselbe Verlauf, derselbe Kalender, nur der Stand, auf den der Tag ausläuft. Der erste ergibt allein `v1.0.0`, der zweite `v1.0.0` und `v1.0.1`. Damit ist es der Inhaltsvergleich, der entscheidet, und nichts sonst — ein Kontrollfall, der nichts über die Verdrahtung annimmt. Der erste Entwurf schaltete stattdessen `versions.highest` per Monkey-Patch aus; das prüft die heutige Verkabelung mit und wäre bei ihrer nächsten Umformung aus einem Grund rot geworden, der mit der Regel nichts zu tun hat. Dazu ein Wächter auf dem Log, denn `_async_mark_day` verschluckt jede Ausnahme: Bricht `store.same_state` absichtlich, so **besteht der erste Lauf weiter** — aus dem falschen Grund —, und nur der Wächter sagt es.

- [ ] **Schritt 1: Die fehlschlagende Prüfung schreiben**

In `tests/integration/run_checks.py` hinter `ensure_integration` einfügen:

```python
def entry_id(access: str) -> str:
    """This integration's config entry, by id. Empty when it has none."""
    entries = requests.get(
        f"{BASE}/api/config/config_entries/entry",
        headers={"Authorization": f"Bearer {access}"},
        timeout=30,
    ).json()
    for entry in entries:
        if entry.get("domain") == "dashboard_history":
            return entry.get("entry_id", "")
    return ""


def reload_entry(access: str) -> bool:
    """Set the integration up again, without restarting Home Assistant.

    The supported way to run `async_setup_entry` a second time, which is
    where the first versions are made. A full restart would do it too and
    is deliberately not used: polling an instance through its restart is
    what gets the caller shut out by Home Assistant's own IP ban, and
    this project learned that the expensive way.

    The call waits for the whole setup, and the setup makes a pass over
    every dashboard - about twenty seconds on a grown bench.
    """
    identifier = entry_id(access)
    if not identifier:
        return False
    answer = requests.post(
        f"{BASE}/api/config/config_entries/entry/{identifier}/reload",
        headers={"Authorization": f"Bearer {access}"},
        timeout=300,
    )
    return answer.ok and answer.json().get("require_restart") is False
```

Und ans Ende der Prüfungen, vor `def _drop_first_card`:

```python
async def run_milestones(access: str) -> None:
    """The versions nobody asked for.

    Out of pytest's reach twice over: the floor is laid while the
    integration sets itself up, and `milestones` imports Home Assistant.
    So it is driven the way a person would - make a dashboard, set the
    integration up again, and look at what is there.

    Runs after every check that examines state it built up earlier, and
    that is on purpose: it sets the integration up again, and doing that
    in the middle would pull the ground out from under those. Checks
    added after this one may assume a freshly set-up integration.
    """
    key = "dh-floor-check"
    async with Socket(access) as socket:
        listed = (await socket.call("lovelace/dashboards/list")) or []
        if not any(entry.get("url_path") == key for entry in listed):
            await socket.call(
                "lovelace/dashboards/create", url_path=key, title="DH Floor"
            )
            await asyncio.sleep(4)
        await socket.call(
            "lovelace/config/save",
            url_path=key,
            config={"views": [{"path": "p", "title": "Floor", "cards": []}]},
        )
        await _wait_until_recorded(socket, key)

    if not check("the integration can be set up again", reload_entry(access)):
        return
    if not check("and it comes back", wait_for_integration(access)):
        return

    async with Socket(access) as socket:
        found = (await socket.call("dashboard_history/versions", dashboard=key))[
            "versions"
        ]
        names = [v["name"].split("/")[-1] for v in found]
        # Exactly one, on every run: the first setup makes it, and every
        # later one finds it already there and leaves it alone. That is
        # the "and none of them twice" half of the promise.
        check(
            "a dashboard without versions is given v1.0.0 when the integration starts",
            names == ["v1.0.0"],
            str(names),
        )
        check(
            "and it says that nobody asked for it",
            bool(found) and found[0].get("automatic") is True,
            str(found[:1]),
        )
        check(
            "and it is called after the day it marks",
            bool(found)
            and bool(re.fullmatch(r"\d{1,2} [A-Z][a-z]+ \d{4}", found[0]["title"])),
            found[0]["title"] if found else "",
        )
```

Und in `main` ganz am Ende registrieren, hinter dem Positions-Block:

```python
    print("\n  -- Versionen, die von selbst entstehen --")
    asyncio.run(run_milestones(access))
```

- [ ] **Schritt 2: Laufen lassen, Fehlschlag prüfen**

```bash
python3 -c "
import asyncio, sys, pathlib
sys.path.insert(0, str(pathlib.Path('tests/integration').resolve()))
import run_checks as rc
asyncio.run(rc.run_milestones(rc.token()))
"
```

Erwartet: Die Einrichtung gelingt, aber `a dashboard without versions is given v1.0.0` meldet `FAIL` mit `[]` — es entsteht nichts.

- [ ] **Schritt 3: Umsetzen**

`custom_components/dashboard_history/milestones.py` neu anlegen:

```python
"""Versions that appear without anybody having asked for one.

Decision 17 makes the simple mode show versions and nothing else, and a
mode that shows only versions is no use on a dashboard that has none.
The person it is built for is exactly the person who will never make
one, so two kinds appear by themselves:

* **A floor**, for every live dashboard that has a recorded state and no
  version at all. That is the state to come back to before anything has
  happened.
* **A day mark**, on the state that was there before the first change of
  a new day - by definition the last state of the day before.

Nothing in here may raise into Home Assistant. A version that could not
be made is a mark that is missing; a save that failed because of it
would be a state that is gone.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.util import dt as dt_util

from . import operations
from . import versions as versioning
from .store import Change, HistoryStore

_LOGGER = logging.getLogger(__name__)


class Milestones:
    """Makes the versions nobody asked for."""

    def __init__(
        self, hass: HomeAssistant, store: HistoryStore, entry: ConfigEntry
    ) -> None:
        self._hass = hass
        self._store = store
        # The entry itself, never a copy of its options: Home Assistant
        # replaces the options object when somebody changes them, so
        # holding the entry means a change takes effect at the next save
        # instead of at the next restart. No update listener, and
        # deliberately none - reloading would restart the recorder and
        # cost a full pass over every dashboard for the sake of a
        # checkbox.
        self._entry = entry
        self._unsubscribe = None

    # -- the floor -----------------------------------------------------

    async def async_lay_the_floor(self) -> list[str]:
        """Give every live dashboard without a version its `v1.0.0`.

        Written as a rule rather than as a one-off, so it is idempotent
        by construction: a dashboard that already has a version is
        skipped, a second start makes nothing, and one created later
        gets its floor at the next start. A flag in the config entry
        would have been the alternative, and it would drift away from
        what the repository actually holds.

        Live dashboards only, read from the tree at HEAD. A deleted one
        has left that tree; its newest entry is the deletion, and there
        is no state there to come back to - `async_create_version`
        refuses it, and not asking saves a warning per deleted dashboard
        on every single start.
        """
        made: list[str] = []
        try:
            live = await self._hass.async_add_executor_job(
                self._store.list_dashboards
            )
        except Exception:  # noqa: BLE001 - a missing mark, never a broken start
            _LOGGER.exception("Could not list the dashboards to give a version to")
            return made
        for key in live:
            name = await self._async_floor_for(key)
            if name is not None:
                made.append(name)
        if made:
            _LOGGER.info("Made a first version: %s", ", ".join(made))
        return made

    async def _async_floor_for(self, key: str) -> str | None:
        """One dashboard's floor, or None if it needs none and if it fails.

        One dashboard at a time, each in its own guard: the same shape
        `capture._async_write` uses, and for the same reason - a failure
        on the first must not cost the rest.
        """
        try:
            if await self._hass.async_add_executor_job(
                self._store.list_versions, key
            ):
                return None
            newest = await self._hass.async_add_executor_job(
                self._store.list_changes, key, 1
            )
            if not newest:
                # Nothing recorded yet. Nothing to mark, and nothing wrong:
                # a dashboard that has never been saved has no state.
                return None
            return await self._async_make(key, "major", newest[0])
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Could not make the first version of %s", key)
            return None
```

> **Diese Auflistung ist der Stand, nach dem gebaut wurde, und an zwei Stellen nicht mehr der Code.** Beide Änderungen sind oben begründet: Der Boden liegt auf dem **ältesten** Eintrag (`list_changes(key, None)`, dann `[-1]`) statt auf dem neuesten, und die Prüfung »hat schon eine Version« fragt nach einer *nummerierten* (`versions.latest`) statt nach irgendeinem Tag. Wer den Code lesen will, liest `milestones.py`; wer wissen will, warum er so aussieht, liest hier weiter.

```python

    # -- making one ----------------------------------------------------

    async def _async_make(
        self, key: str, level: str, change: Change
    ) -> str | None:
        """Mark one recorded state, through the fence a person goes through.

        `operations.async_create_version` rather than the store directly:
        that is where the refusals live - an unknown revision, a state
        that is not in the tree, a name git cannot hold beside the others
        - and a second way in would be a second set of them to keep
        right.

        The time zone is read here, at every call. `DEFAULT_TIME_ZONE` is
        a module variable that Home Assistant fills in from the user's
        configuration while it starts; held on to, it would be whatever
        it was when this object was built.
        """
        zone = dt_util.DEFAULT_TIME_ZONE
        answer = await operations.async_create_version(
            self._hass,
            self._store,
            key,
            level=level,
            title=versioning.day_title(change.timestamp, zone),
            description=versioning.automatic_description(),
            revision=change.revision,
        )
        created = answer.get("created")
        if created is None:
            # An answer, not a crash - that operation reports every
            # refusal this way. Debug rather than warning: the ordinary
            # case here is a dashboard whose newest entry is its own
            # deletion, and that is not a fault.
            _LOGGER.debug("No automatic version for %s: %s", key, answer.get("error"))
            return None
        return created
```

In `operations.py` den Helfer einfügen — direkt hinter `_same_as_live`. **Nicht hinter `_by_number`:** Das ist am 2026-09-04 mit `9e1558e` nach `versions.py` gezogen und heißt dort `versioning.by_number`; in `operations.py` gibt es den Namen nicht mehr.

```python
def _version_dict(version) -> dict:
    """One version as plain data, with its marker read rather than shown.

    Every place that hands a version outside goes through here, so the
    panel sees one shape - and so `automatic` cannot be present in one
    answer and missing from the next, which is the kind of difference a
    frontend quietly renders as False.
    """
    description, automatic = versioning.read_description(version.description)
    return {
        "name": version.name,
        "revision": version.revision,
        "title": version.title,
        "description": description,
        "automatic": automatic,
    }
```

In `async_history` den `marks`-Aufbau ersetzen:

```python
    marks: dict[str, list[dict]] = {}
    for version in versions:
        marks.setdefault(version.revision, []).append(_version_dict(version))
```

und die Bildung von `matching_versions` aus Vorhaben G, Aufgabe 3:

```python
    matching_versions = [
        _version_dict(v)
        for v in versioning.by_number(key, versions)
        if v.revision in same
    ]
```

In `async_versions` die Liste im `return` ersetzen:

```python
        "versions": [
            {**_version_dict(v), "same_as_now": v.revision in same} for v in found
        ]
```

In `services.yaml` die Beschreibung von `versions` um einen Halbsatz ergänzen, damit der Dienst sagt, was er jetzt mitliefert:

```yaml
versions:
  name: Versions
  description: >-
    The named points in the history. Give a dashboard to see only its
    own, ordered by version number, each saying whether it is the state
    the dashboard holds right now and whether it was made automatically.
```

In `__init__.py` drei Stellen, in dieser Reihenfolge. Erstens der Import, hinter `from .capture import HistoryCapture`:

```python
from .milestones import Milestones
```

Zweitens die ersten Zeilen von `async_setup_entry` ersetzen — die drei bestehenden Zeilen `store = …`, `capture = …`, `hass.data[DOMAIN] = …`:

```python
    store = HistoryStore(Path(hass.config.path(REPO_DIRNAME)))
    capture = HistoryCapture(hass, store)
    milestones = Milestones(hass, store, entry)
    hass.data[DOMAIN] = {
        "store": store,
        "capture": capture,
        "milestones": milestones,
    }
```

Drittens, **nach** dem bestehenden `try`-Block um `store.ensure` und `capture.async_start` und vor dem abschließenden `_LOGGER.debug`, ein zweiter Block:

```python
    # Its own guard, separate from the recorder's: a repository that
    # could not be created leaves nothing to mark, but a recorder that
    # started perfectly well must not lose its versions because one
    # dashboard's tag failed.
    try:
        await milestones.async_lay_the_floor()
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Dashboard History could not make its first versions")
```

- [ ] **Schritt 4: Laufen lassen, Erfolg prüfen**

```bash
python3 -m pytest tests/ -q
docker compose -f docker/compose.yaml restart homeassistant
python3 tests/integration/run_checks.py
```

Erwartet: pytest unverändert (`268 passed, 3 skipped`) — diese Aufgabe legt keinen pytest-Fall dazu —, alle Integrationsprüfungen bestanden, die drei neuen darunter. Danach ein **zweiter** vollständiger Lauf ohne Neustart dazwischen — er muss erneut `["v1.0.0"]` melden und nicht `["v1.0.0", "v1.0.1"]`. Das ist die Probe auf »keines zweimal«.

- [ ] **Schritt 5: Committen**

```bash
git add custom_components/dashboard_history/milestones.py \
        custom_components/dashboard_history/__init__.py \
        custom_components/dashboard_history/operations.py \
        custom_components/dashboard_history/services.yaml \
        tests/integration/run_checks.py
git commit -m "$(cat <<'EOF'
Give every dashboard a version to come back to

The simple mode of decision 17 shows versions and nothing else, and the
person it is built for is the one who will never make one. A dashboard
with no versions would meet them as a panel with no way back at all.

Written as a rule and not as a one-off: a live dashboard with a
recorded state and no version gets v1.0.0. A second start finds it
there and leaves it alone, a dashboard made later gets its floor at the
next start, and nothing has to remember whether the job was already
done - a flag in the config entry would drift away from what the
repository holds.

Every version now leaves through one function, so the flag saying
nobody asked for it cannot be in one answer and missing from the next.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Aufgabe 3: Die Tagesversion beim ersten Speichern eines Tages

**Dateien:**
- Ändern: `custom_components/dashboard_history/const.py` (neu: `OPTION_DAILY_VERSIONS`)
- Ändern: `custom_components/dashboard_history/milestones.py` (`async_arm`, `async_disarm`, `_handle_recorded`, `_async_mark_day`)
- Ändern: `custom_components/dashboard_history/__init__.py` (scharfschalten, und beim Entladen wieder abschalten)
- Test: `tests/integration/run_checks.py` (neuer Helfer `_versions_settled`; `run_milestones` erweitern)

**Schnittstellen:**
- Verbraucht: `versions.same_day` und `versions.day_title` aus Aufgabe 1, `Milestones._async_make` aus Aufgabe 2, `EVENT_HISTORY_UPDATED` aus `const.py`.
- Liefert: `Milestones.async_arm()` und `Milestones.async_disarm()`, beide `@callback`. Nach `async_arm()` bekommt der Stand vor der ersten aufgezeichneten Änderung eines neuen Tages eine Version — auf Patch-Ebene, **außer** das Dashboard hat noch gar keine; dann auf Major-Ebene.

**Die Konstruktion, und warum sie herum ist, wie sie ist.** Nicht »um Mitternacht eine Version anlegen«, sondern »beim ersten Eintrag eines neuen Tages den Stand davor markieren«. Die Spec begründet es: kein Zeitgeber, kein Mitternachtslauf, sie übersteht eine Nacht mit ausgeschaltetem Home Assistant, und die Bedingung »nur wenn es Änderungen gibt« erfüllt sich von selbst. Ein Dashboard, das drei Wochen ruht, sammelt keine einundzwanzig leeren Marken — es bekommt eine, und die trägt den Tag, an dem zuletzt etwas passiert ist.

**Warum `EVENT_HISTORY_UPDATED` und nicht `lovelace_updated`.** Das eigene Ereignis wird gefeuert, *nachdem* der Commit geschrieben ist, und es nennt die Dashboards, die sich wirklich geändert haben. `lovelace_updated` kommt davor — dieselbe Falle, die in `const.py` schon für das Panel beschrieben ist. Ein angenehmer Nebeneffekt: Der Schnappschuss unmittelbar vor einer Wiederherstellung läuft mit `announce=False` und kommt hier deshalb gar nicht an. Das ist richtig so; über diesen Stand fragt in der zweiten Hälfte der Rücksprung-Dialog selbst.

**Warum erst nach dem Boden scharf.** `versioning.candidates` zählt vom höchsten vorhandenen Stand hoch. Auf einem Dashboard ganz ohne Versionen wäre die erste Patch-Version `v0.0.1`, nicht `v1.0.1` — der Boden muss also liegen, bevor irgendeine Tagesmarke entstehen kann. Der Startdurchlauf des Rekorders hat sein Ereignis gefeuert, bevor `async_start()` überhaupt zurückkommt; wer danach scharfschaltet, kann von ihm nichts mehr abbekommen. Damit ist die Reihenfolge in `async_setup_entry` die ganze Absicherung, und sie ist in einem Satz erklärbar: **der erste Durchlauf legt den Boden, alles danach darf Tage markieren.**

Der Preis ist benannt: Eine Änderung, die an Home Assistant vorbei passiert ist und beim Start eingesammelt wird, markiert ihren Tag nicht. Beim *nächsten* Speichern liegt der Vorgängerstand dann schon in diesem Lauf, und der Tag davor bleibt unmarkiert. Das betrifft nur Anlagen, die zwischen zwei Starts von außen bearbeitet werden.

**Patch-Ebene — mit einer Ausnahme, die ein Loch schließt.** Automatische Marken sind der kleinste Schritt und lassen Minor und Major dem Menschen. Nach dem Boden `v1.0.0` heißen sie `v1.0.1`, `v1.0.2` und so fort; wer selbst einen Meilenstein setzt, greift zu `v1.1.0` und hebt sich damit auch in der Nummer ab.

Die Ausnahme betrifft ein Dashboard, das **im laufenden Betrieb** angelegt wurde: Der Boden wird beim Einrichten gelegt, und dieses Dashboard gab es da noch nicht. Läuft Home Assistant über den Tageswechsel durch, wäre seine allererste Version eine Tagesmarke auf Patch-Ebene — und `candidates` zählt vom höchsten vorhandenen Stand hoch, bei keinem vorhandenen also auf `v0.0.1`. Nachgemessen am 2026-09-04: `candidates("home", [])` liefert `{'patch': 'home/v0.0.1', 'minor': 'home/v0.1.0', 'major': 'home/v1.0.0'}`. Der nächste Start fände dann eine Version vor, ließe das Dashboard in Ruhe — und es bliebe für immer auf der `v0.0.x`-Schiene. Deshalb: **Hat ein Dashboard noch keine Version, entsteht die erste auf Major-Ebene**, also als `v1.0.0`. Der markierte Stand ist der letzte des Vortags, und genau das ist ein Boden.

- [ ] **Schritt 1: Die fehlschlagende Prüfung schreiben**

In `tests/integration/run_checks.py` und hinter `_wait_for_history_to_move`:

```python
async def _versions_settled(socket, key: str, seconds: float = 20) -> list:
    """The versions of `key`, once two reads in a row agree.

    A daily version is written by a task the recorder's announcement
    starts, so it lands shortly *after* the change that caused it is
    readable. Counting versions straight after a save would race that
    task. Two equal reads are the cheapest honest answer to "is it
    finished"; a fixed sleep would be a guess, and this file has paid for
    guesses before.
    """
    seen: list | None = None

    async def fetch():
        nonlocal seen
        now = [
            v["name"]
            for v in (
                await socket.call("dashboard_history/versions", dashboard=key)
            )["versions"]
        ]
        settled = seen is not None and seen == now
        seen = now
        return now, settled

    found, _ = await _wait_for(fetch, lambda pair: pair[1], seconds)
    return found
```

Und ans Ende von `run_milestones` anfügen:

```python
        # The day mark, in the one direction a running instance can be
        # made to show. Two changes in a row, and the second is measured:
        # its predecessor was recorded minutes ago, so it is certainly
        # from today whatever day the bench happens to run on. That the
        # *other* direction works - a predecessor from an earlier day
        # does get a mark - is settled in pytest, on `versions.same_day`.
        # No API can backdate a commit, so it cannot be shown from here,
        # and pretending otherwise with a sleep would be worse than
        # saying it plainly.
        async def save(title: str) -> None:
            await socket.call(
                "lovelace/config/save",
                url_path=key,
                config={"views": [{"path": "p", "title": title, "cards": []}]},
            )
            await _wait_until_recorded(socket, key)

        await save("Floor A")
        settled = await _versions_settled(socket, key)
        await save("Floor B")
        again = await _versions_settled(socket, key)
        check(
            "a second change on the same day adds no further version",
            again == settled,
            f"{settled} -> {again}",
        )
```

- [ ] **Schritt 2: Laufen lassen, Fehlschlag prüfen**

```bash
python3 -c "
import asyncio, sys, pathlib
sys.path.insert(0, str(pathlib.Path('tests/integration').resolve()))
import run_checks as rc
asyncio.run(rc.run_milestones(rc.token()))
"
```

Erwartet: **Diese Prüfung besteht bereits** — es entsteht ja noch gar keine Tagesversion, also kann auch keine zu viel entstehen. Das ist der ehrliche Zustand: Sie ist eine Absicherung gegen die Umsetzung von Schritt 3, keine Prüfung, die vorher rot ist. Rot ist an dieser Aufgabe nur, was pytest in Aufgabe 1 bereits abgedeckt hat. Wer hier einen Fehlschlag erwartet, sucht vergebens; die Prüfung wird interessant, sobald Schritt 3 steht.

- [ ] **Schritt 3: Umsetzen**

In `const.py` ans Ende anfügen:

```python
# Whether a version is made for the state at the end of each day. On by
# default: the simple mode of decision 17 shows nothing but versions, and
# an installation that has to be configured before it works is one that
# does not work. Switched off by people who keep their own milestones.
OPTION_DAILY_VERSIONS = "daily_versions"
```

In `milestones.py` die Importe ergänzen — `asyncio` kommt erst jetzt dazu, weil erst diese Aufgabe eine Sperre braucht:

```python
import asyncio
import logging
```

```python
from .const import EVENT_HISTORY_UPDATED, OPTION_DAILY_VERSIONS
```

Im `__init__` eine Sperre ergänzen, direkt hinter `self._unsubscribe = None`:

```python
        # One day mark at a time. Two changes arriving close together
        # would otherwise both read the same predecessor, both find it
        # unmarked, and both tag it - two versions on one state, one
        # second apart, neither of them wrong on its own.
        self._marking = asyncio.Lock()
```

Und ans Ende der Klasse anfügen:

```python
    # -- the day mark --------------------------------------------------

    @callback
    def async_arm(self) -> None:
        """Start marking the end of a day when the history grows.

        Armed *after* the floor is laid, and that order is the whole
        reason this is a call of its own. `candidates` counts up from the
        highest version that exists, so on a dashboard with none the
        first automatic version would be `v0.0.1` rather than `v1.0.1`.
        The recorder's opening pass has already announced itself by the
        time `async_start` returns, so nothing it recorded can reach
        here - the first pass lays the floor, everything after it may
        raise day marks.

        `EVENT_HISTORY_UPDATED` rather than `lovelace_updated`: it is
        fired once the commit exists and it names the dashboards that
        actually changed. The snapshot taken just before a restore is
        recorded with `announce=False` and so never arrives here, which
        is right - the dialog in front of a restore asks about that state
        itself.
        """
        if self._unsubscribe is not None:
            return
        self._unsubscribe = self._hass.bus.async_listen(
            EVENT_HISTORY_UPDATED, self._handle_recorded
        )

    @callback
    def async_disarm(self) -> None:
        """Stop listening."""
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

    @callback
    def _handle_recorded(self, event: Event) -> None:
        """React without holding up the bus, or the recorder's write lock.

        The event is fired from inside the recorder's write section. Doing
        git work here would run it under a lock this module has no
        business holding - the same reason `capture._handle_event` hands
        its work to a task rather than doing it where it stands.
        """
        for key in event.data.get("dashboards") or []:
            self._hass.async_create_task(self._async_mark_day(key))

    async def _async_mark_day(self, key: str) -> None:
        """Mark the state that was there before this new day started."""
        try:
            async with self._marking:
                if not self._entry.options.get(OPTION_DAILY_VERSIONS, True):
                    return
                newest = await self._hass.async_add_executor_job(
                    self._store.list_changes, key, 2
                )
                if len(newest) < 2:
                    # The first state this dashboard ever had. There is
                    # nothing before it, so there is no day to close.
                    return
                current, previous = newest
                zone = dt_util.DEFAULT_TIME_ZONE
                if versioning.same_day(previous.timestamp, current.timestamp, zone):
                    return
                found = await self._hass.async_add_executor_job(
                    self._store.list_versions, key
                )
                # Already marked, by a person or by an earlier run of
                # this. Without the check a dashboard saved twice across
                # one midnight would collect a second tag on the same
                # state, and the numbering would count on regardless.
                if any(v.revision == previous.revision for v in found):
                    return
                # A dashboard created while Home Assistant was running
                # has never had a floor laid - `async_lay_the_floor` ran
                # at setup, and this one did not exist then. Its first
                # automatic version is therefore made at major level, so
                # that it is `v1.0.0` and not `v0.0.1`: `candidates`
                # counts up from the highest version there is, and with
                # none there is the patch candidate is v0.0.1. A later
                # start would then find a version, leave the dashboard
                # alone, and strand it on the v0.0.x track for good.
                # What is being marked is the last state of the day
                # before, which is exactly what a floor is anyway.
                level = "patch" if found else "major"
                name = await self._async_make(key, level, previous)
                if name is not None:
                    _LOGGER.info("Marked the end of a day with %s", name)
        except Exception:  # noqa: BLE001 - a missing mark, never a lost save
            _LOGGER.exception("Could not make the daily version of %s", key)
```

In `__init__.py` hinter dem Boden-Block scharfschalten:

```python
    # Only now, and see `async_arm` for why: before the floor is laid,
    # the first automatic version of a dashboard would be numbered
    # v0.0.1 instead of v1.0.1.
    milestones.async_arm()
```

Und in `async_unload_entry`, vor dem Anhalten des Rekorders:

```python
    if data and (milestones := data.get("milestones")) is not None:
        milestones.async_disarm()
```

- [ ] **Schritt 4: Laufen lassen, Erfolg prüfen**

```bash
python3 -m pytest tests/ -q
docker compose -f docker/compose.yaml restart homeassistant
python3 tests/integration/run_checks.py
```

Erwartet: pytest unverändert (`268 passed, 3 skipped`), alle Integrationsprüfungen bestanden. Zusätzlich im Protokoll nachsehen, dass nichts still scheitert:

```bash
docker compose -f docker/compose.yaml logs homeassistant --since 10m | grep -i "dashboard_history.milestones"
```

Erwartet: Zeilen der Form `Made a first version: …`, keine `Could not …`.

- [ ] **Schritt 5: Committen**

```bash
git add custom_components/dashboard_history/const.py \
        custom_components/dashboard_history/milestones.py \
        custom_components/dashboard_history/__init__.py \
        tests/integration/run_checks.py
git commit -m "$(cat <<'EOF'
Mark the state a day ended on

A mode that shows only versions needs versions to keep appearing, and
the person it is built for will not make them. So the first change of a
new day marks the state before it - which is the last state of the day
before.

This way round on purpose: it needs no timer and no run at midnight, it
survives a night with Home Assistant switched off, and "only when
something changed" follows from it rather than having to be checked. A
dashboard that rests for three weeks collects one mark, not twenty-one.

Armed only after the floor is laid. Numbering counts up from the
highest version there is, so without a floor the first automatic
version of a dashboard would be v0.0.1 rather than v1.0.1.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Aufgabe 4: Der Schalter, der die Tagesversionen abstellt

**Dateien:**
- Ändern: `custom_components/dashboard_history/config_flow.py`
- Ändern: `custom_components/dashboard_history/strings.json`
- Ändern: `custom_components/dashboard_history/translations/en.json`
- Test: `tests/test_integration_files.py` (zwei Fälle für den neuen Abschnitt)
- Test: `tests/integration/run_checks.py` (neuer Helfer `daily_versions_switch`, neue Prüfung `run_daily_switch`)

**Schnittstellen:**
- Verbraucht: `OPTION_DAILY_VERSIONS` aus Aufgabe 3, gelesen von `Milestones._async_mark_day`.
- Liefert: `DashboardHistoryOptionsFlow` mit einem Schritt `init` und einem Feld `daily_versions: bool`, Vorgabe `True`. Erreichbar über `DashboardHistoryConfigFlow.async_get_options_flow`.

**Kein Update-Listener, und das ist die Entscheidung.** Der übliche Weg wäre `entry.add_update_listener(...)` mit einem Reload darin. Hier nicht: Ein Reload hält den Rekorder an und startet ihn neu, was einen vollständigen Durchlauf über alle Dashboards kostet — rund zwanzig Sekunden auf dem Prüfstand. Für einen Haken ist das eine absurde Rechnung. `Milestones` hält stattdessen den Config-Entry selbst und liest `entry.options` bei jedem Speichervorgang neu; Home Assistant tauscht das Options-Objekt am Eintrag aus, der Schalter wirkt also ab dem nächsten Speichervorgang und ohne Neustart.

**Der Boden bleibt vom Schalter unberührt.** Abgeschaltet werden die *Tages*versionen; die eine Bodenversion ist die Voraussetzung dafür, dass der einfache Modus überhaupt etwas anzeigen kann, und sie entsteht genau einmal je Dashboard. Wer sie nicht will, benutzt den erweiterten Modus, in dem sie nicht stört. Das ist eine Auslegung, keine wörtliche Vorgabe der Spec — dort steht nur »Wer seine Versionen selbst setzen will, schaltet sie im OptionsFlow ab«, und »sie« sind im Satz davor die automatischen Tagesversionen.

**Eine benannte Grenze für später.** `async_create_entry(title="", data=user_input)` ersetzt die Optionen vollständig. Solange es diese eine gibt, ist das gleichbedeutend — das Feld ist `vol.Required` mit Vorgabe, steht also immer in `user_input`. Wer in Vorhaben B oder C eine **zweite** Option ergänzt, muss hier auf `data={**self.config_entry.options, **user_input}` umstellen, sonst löscht das Formular die Optionen, die es nicht anzeigt. Bewusst noch nicht eingebaut: Ein Zusammenführen von Optionen, die es nicht gibt, wäre Vorrat, und diese Datei wird ohnehin angefasst, sobald die zweite dazukommt.

**Die Falle mit `OptionsFlow.__init__`.** Am 2026-09-04 im Container nachgesehen: Der Konstruktor nimmt kein `config_entry` entgegen, und `self.config_entry` ist eine geerbte Eigenschaft, die den Eintrag über `hass` nachschlägt — *innerhalb* von `__init__` wirft sie. Alle älteren Beispiele setzen `self.config_entry = config_entry` im Konstruktor; das ist hier falsch und stirbt entweder sofort oder beim Deprecation-Lauf.

- [ ] **Schritt 1: Die fehlschlagenden Tests und die fehlschlagende Prüfung schreiben**

`tests/test_integration_files.py` prüft, was Home Assistant liest, bevor eine Zeile dieses Codes läuft — und dass `translations/en.json` und `strings.json` nicht auseinanderlaufen. Der neue Abschnitt gehört unter dieselbe Aufsicht. Ans Ende der Datei anfügen:

```python
def test_the_options_step_has_words():
    # Without them the switch appears in the interface as the bare word
    # "daily_versions", and hassfest - which HACS runs on a published
    # integration - reports the gap.
    step = _strings()["options"]["step"]["init"]
    assert step["title"] and step["description"]


def test_the_switch_says_what_it_does_and_what_it_does_not():
    # The explanation carries the sentence that matters: nothing is
    # deleted either way. A switch about versions on a tool whose whole
    # promise is that nothing is lost has to say so where it is read.
    step = _strings()["options"]["step"]["init"]
    assert step["data"]["daily_versions"]
    assert "deleted" in step["data_description"]["daily_versions"]
```

In `tests/integration/run_checks.py` hinter `reload_entry` einfügen:

```python
def daily_versions_switch(access: str, enabled: bool) -> tuple[bool, list]:
    """Set the switch the way a person does, and report what was offered.

    Driven over the options flow rather than by writing the entry:
    whether the form exists at all, and whether it accepts this field, is
    exactly what is being checked.
    """
    headers = {"Authorization": f"Bearer {access}"}
    identifier = entry_id(access)
    if not identifier:
        return False, []
    started = requests.post(
        f"{BASE}/api/config/config_entries/options/flow",
        headers=headers,
        json={"handler": identifier, "show_advanced_options": False},
        timeout=60,
    )
    started.raise_for_status()
    step = started.json()
    offered = step.get("data_schema") or []
    done = requests.post(
        f"{BASE}/api/config/config_entries/options/flow/{step['flow_id']}",
        headers=headers,
        json={"daily_versions": enabled},
        timeout=60,
    )
    done.raise_for_status()
    return done.json().get("type") == "create_entry", offered
```

Und hinter `run_milestones` die Prüfung:

```python
async def run_daily_switch(access: str) -> None:
    """The switch that stops the automatic daily versions.

    What it does on a day boundary cannot be shown here, for the reason
    named in `run_milestones`. What can be shown is everything else: that
    the form exists, that it offers this one field, that it takes both
    answers, and that the recording carries on regardless - because the
    switch deliberately triggers no reload.
    """
    off, offered = daily_versions_switch(access, False)
    check("the options offer the daily versions as a switch",
          any(field.get("name") == "daily_versions" for field in offered),
          str([field.get("name") for field in offered]))
    check("turning the daily versions off is accepted", off)

    on, _ = daily_versions_switch(access, True)
    check("and turning them back on is accepted", on)

    # Left switched on, and checked rather than assumed: every later run
    # of this file expects the ordinary behaviour, and a bench left in a
    # configuration nobody chose is how a check starts failing for
    # reasons that have nothing to do with it.
    async with Socket(access) as socket:
        answer = await socket.call("dashboard_history/dashboards")
    check(
        "and the integration is still answering afterwards",
        bool(answer.get("dashboards")),
        str(len(answer.get("dashboards") or [])),
    )
```

Und in `main`, direkt hinter `run_milestones`:

```python
    print("\n  -- Der Schalter fuer die Tagesversionen --")
    asyncio.run(run_daily_switch(access))
```

- [ ] **Schritt 2: Laufen lassen, Fehlschlag prüfen**

```bash
python3 -m pytest tests/test_integration_files.py -v
```

Erwartet: zwei Fehlschläge mit `KeyError: 'options'`.

```bash
python3 -c "
import asyncio, sys, pathlib
sys.path.insert(0, str(pathlib.Path('tests/integration').resolve()))
import run_checks as rc
asyncio.run(rc.run_daily_switch(rc.token()))
"
```

Erwartet: ein Traceback aus `requests` — `raise_for_status` auf eine 404 oder 400, weil die Integration keinen OptionsFlow anbietet. `Socket.call` ist hier nicht beteiligt; der Fehlschlag kommt aus dem ersten HTTP-Aufruf.

- [ ] **Schritt 3: Umsetzen**

`config_flow.py` vollständig ersetzen:

```python
"""Config flow: one confirmation, and one switch afterwards."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback

from .const import DOMAIN, OPTION_DAILY_VERSIONS


class DashboardHistoryConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set the integration up from the user interface."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the single setup step."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is None:
            return self.async_show_form(step_id="user")
        return self.async_create_entry(title="Dashboard History", data={})

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """The one thing there is to configure."""
        return DashboardHistoryOptionsFlow()


class DashboardHistoryOptionsFlow(OptionsFlow):
    """Whether versions are made without being asked for.

    No `__init__`, and that is not an omission. Since Home Assistant
    2024.11 the base class takes no config entry and offers
    `self.config_entry` as a property that looks it up through `hass` -
    which is not available inside `__init__` at all. Measured against
    2026.8.3 on 2026-09-04, because every older example on the internet
    assigns it there.
    """

    async def async_step_init(self, user_input=None):
        """Show the switch, and remember what it was set to."""
        if user_input is not None:
            # No update listener behind this, deliberately. Reloading the
            # entry would stop and restart the recorder, and its opening
            # pass over every dashboard takes about twenty seconds - an
            # absurd price for a checkbox. `Milestones` holds the entry
            # and reads its options at every save instead, so this takes
            # effect at the next one.
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        OPTION_DAILY_VERSIONS,
                        default=self.config_entry.options.get(
                            OPTION_DAILY_VERSIONS, True
                        ),
                    ): bool
                }
            ),
        )
```

In `strings.json` **und** wortgleich in `translations/en.json` den Abschnitt `options` neben `config` einfügen:

```json
  "options": {
    "step": {
      "init": {
        "title": "Dashboard History",
        "description": "A version marks a state you can come back to by name.",
        "data": {
          "daily_versions": "Mark the state at the end of each day"
        },
        "data_description": {
          "daily_versions": "On the first change of a new day, the state that was there before it is marked as a version, named after the day it belongs to. Turn this off to keep only the versions you make yourself. Nothing is deleted either way: every state stays in the history, marked or not."
        }
      }
    }
  }
```

- [ ] **Schritt 4: Laufen lassen, Erfolg prüfen**

```bash
python3 -m pytest tests/ -q
docker compose -f docker/compose.yaml restart homeassistant
python3 tests/integration/run_checks.py
```

Erwartet: **`270 passed, 3 skipped`** (zwei mehr), alle Integrationsprüfungen ebenso. Dass `strings.json` und `translations/en.json` nicht auseinandergelaufen sind, prüft `test_the_english_translation_is_the_strings_file` bereits — es vergleicht die beiden Dateien vollständig, ein von Hand kopierter Abschnitt mit einem Tippfehler fällt dort auf.

Und zuletzt in der Oberfläche nachsehen, dass der Schalter dort auch wirklich steht und seinen Text trägt: *Einstellungen → Geräte & Dienste → Dashboard History → Konfigurieren*.

- [ ] **Schritt 5: Committen**

```bash
git add custom_components/dashboard_history/config_flow.py \
        custom_components/dashboard_history/strings.json \
        custom_components/dashboard_history/translations/en.json \
        tests/test_integration_files.py \
        tests/integration/run_checks.py
git commit -m "$(cat <<'EOF'
Let the daily versions be switched off

They are on by default, because an installation that has to be
configured before it works is one that does not work. But somebody who
keeps their own milestones does not want a mark for every day on top of
them, and the design record says so.

No update listener behind the switch. Reloading the entry would stop
and restart the recorder, whose opening pass over every dashboard takes
about twenty seconds - an absurd price for a checkbox. The entry itself
is held instead and its options are read at every save, so the switch
takes effect at the next one.

The options flow takes no config entry in its constructor and must not
assign one: since 2024.11 that is an inherited property, and it raises
inside __init__. Verified against 2026.8.3 rather than copied from an
older example.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Wenn alles vier steht

`python3 -m pytest tests/ -v` (`270 passed, 3 skipped` ohne echte Ablage — siehe die Vorbemerkung zur Testzahl) und `python3 tests/integration/run_checks.py` müssen beide vollständig grün sein, und ein **zweiter** vollständiger Lauf direkt hinterher ebenso — er ist die Probe darauf, dass nichts doppelt entsteht. Danach gilt:

- Jedes lebende Dashboard trägt mindestens eine Version, und der einfache Modus hat etwas zu zeigen.
- Der Stand am Ende eines Tages, an dem etwas passiert ist, trägt eine Marke mit dem Datum im Titel.
- Jede Version sagt über `automatic`, ob jemand sie gesetzt hat.
- Wer das nicht will, schaltet es unter *Konfigurieren* ab, ohne Neustart.

**Was hier bewusst nicht passiert** und in die zweite Hälfte gehört: der Moduswechsel und seine Ablage im `localStorage`, die zwei Ansichten, Register, Suchfeld, »Ältere laden« auf `next_cursor`, der Vorgabewert von 50 auf 25, der Rücksprung-Dialog mit der Frage nach einer Version für den jetzigen Stand — und jede Zeile in `panel.js`.

## Vier benannte Grenzen

Damit sie nicht später als Versäumnis gelesen werden:

1. **Der Tageswechsel ist an der laufenden Anlage nur in eine Richtung prüfbar.** Dass eine zweite Änderung desselben Tages keine zweite Marke erzeugt, prüft `run_milestones`. Dass eine Änderung am Folgetag eine erzeugt, prüft nur pytest an `versions.same_day` — keine API kann einen Commit rückdatieren, und ein Prüflauf, der auf Mitternacht wartet, ist keiner. Die Verdrahtung dazwischen ist absichtlich so dünn wie möglich gehalten: zwei Store-Abfragen, ein Vergleich, ein Aufruf.
2. **Eine Änderung an Home Assistant vorbei wird beim Start eingesammelt, und dieser Eintrag trägt die Schreibzeit des Rekorders.** Der Tag, an dem tatsächlich gearbeitet wurde, ist damit nicht mehr rekonstruierbar; markiert wird der Tag des Starts. *(Am 2026-09-05 enger gefasst. Ursprünglich stand hier, der Tag werde »gar nicht markiert« — das galt für das damalige Zwei-Einträge-Fenster. Mit dem Rückwärtslauf aus Grenze 3 findet der nächste Speichervorgang den Vortag doch, nur eben unter dem Datum, unter dem er aufgezeichnet wurde.)* Ebenfalls hierher gehört ein schmales Fenster beim Start selbst: Der Rekorder ist ab `capture.async_start()` scharf, `Milestones` erst nach dem Boden-Durchlauf. Eine Speicherung dazwischen wird aufgezeichnet, aber nicht als Tagesende betrachtet.

3. **~~Zwei Speichervorgänge im Millisekundenabstand über einen Tageswechsel können die Marke ganz verlieren.~~ Am 2026-09-05 geschlossen; was bleibt, ist enger.** Gefunden beim Review von Aufgabe 3, behoben in `9be8aad` und beim Gesamtreview desselben Tages als noch offen dokumentiert vorgefunden — dieser Absatz ist die Berichtigung. `_async_mark_day` liest nicht mehr zwei Einträge, sondern `_RECENT = 20`, und geht sie rückwärts durch, bis einer auf einem anderen Tag liegt. Ein Schwarm von Speichervorgängen verdeckt den Vortag damit nicht mehr. Die Rechnung dazu ist als `versions.end_of_previous_day` in reinem pytest geprüft, einschließlich des Falls, an dem die alte Fassung scheiterte.

   **Was bleibt:** Landen mehr als zwanzig Speichervorgänge, seit ein Tag zu Ende ging, ist dieser Stand aus dem Fenster gerutscht und wird nie markiert — still und dauerhaft, wie vorher, nur zehnmal seltener. Seit dem 2026-09-05 sagt es wenigstens eine `debug`-Zeile, wenn das Fenster voll ausgeschöpft war. Der Ausweg wäre derselbe wie vorher: das Ereignis seine eigene Revision mittragen zu lassen. Er verbreitert die Schnittstelle zwischen Rekorder und `milestones.py` für einen Fall, den niemand gemeldet hat, und bleibt deshalb ungegangen.

4. **Für die Tags selbst gibt es keine Aufbewahrungsregel, und das ist bisher nirgends gesagt worden.** *(Nachgetragen am 2026-09-05, gefunden beim Gesamtreview.)* Dieses Vorhaben legt je Dashboard und Tag einen Tag an, ohne Obergrenze; nach einem Jahr sind es bei zehn Dashboards rund 3 650. `store.list_versions(key)` lud dafür bis zum 2026-09-05 **jedes** Tag-Objekt der Ablage und filterte erst danach — gemessen 1,9 ms bei zehn Tags, 492 ms bei 3 650. Der Filter liegt seither vor dem Laden (`_each_tag(repo, key)`), was denselben Fall auf 132 ms bringt. Der Rest wächst weiter mit der Zahl der Tags **dieses** Dashboards, und das ist ehrliche Arbeit. Eine Regel, die alte automatische Marken ausdünnt, gibt es nicht und ist bewusst nicht Teil dieses Vorhabens — sie hieße, Historie zu löschen, und dieses Projekt hat sich darauf festgelegt, dass die Historie wächst und nie schrumpft. Wer sie will, braucht einen eigenen Entwurf.
