**Trifft zu:** `unversioned_counts()` kann während eines gleichzeitigen `forget` einen falschen Wert liefern. Reproduziert wurde `1` statt `0` für ein Dashboard, dessen neueste Änderung sowohl vor als auch nach `forget` eine Version trägt. Dafür braucht es weder einen beschädigten Tag-Cache noch einen Fehler bei Schrägstrichen.

**Fundstellen und Ursache:** Im Plan `docs/superpowers/plans/2026-10-01-ungespeicherte-aenderungen-in-der-liste.md:261` wird zuerst der `RevisionIndex` festgehalten; erst in Zeile 264 werden die Tag-Ziele gelesen. `store.py:1779` setzt bei `forget` zwar `self._index = None`, entwertet aber nicht das bereits lokal gehaltene Index-Objekt. `_forget` baut überlebende Commits mit neuen Bäumen beziehungsweise Eltern neu (`custom_components/dashboard_history/store.py:1935` ff.); `_planned_tag_changes` richtet die überlebenden Tags auf die neuen Commit-SHAs aus (`store.py:2315` ff.). Läuft dieser Umbau zwischen beiden Lesungen vollständig durch, vergleicht der Zähler alte Commit-SHAs mit neuen Tag-Zielen. Keine davon passt; er zählt alle alten Revisionen als unversioniert. `_naming_a_forget_race` prüft erfolgreiche Antworten ausdrücklich nicht und wiederholt nichts (`store.py:596-621`). Der Fehler liegt somit bereits innerhalb der neuen Store-Methode.

Die Annahme »`forget` löscht alle Tags und schreibt sie neu« beschreibt den aktuellen Code nicht genau: `_rewrite_tags` verwendet einen Batch-Aufruf `repo.refs.add_packed_refs(changed)` (`store.py:2342-2365`). Der reproduzierte Fehler benötigt kein Fenster ohne Tags; ein vollständig abgeschlossener Umbau zwischen Index- und Ref-Lesung genügt.

**Abgrenzung der übrigen genannten Fälle:** `_tag_targets` speichert ausschließlich Objekt-SHA → Ziel-SHA. Dasselbe unveränderliche Objekt bekommt dadurch kein falsches Ziel. Zwei Leser können mit ihrer abschließenden Dictionary-Zuweisung Cache-Einträge des anderen verdrängen; die nächste Abfrage löst fehlende Einträge erneut auf. Sie liest stets die aktuellen Refs und zählt keine nur noch im Cache vorhandenen Tags (Plan:218-235). Ein normales Anlegen oder Entfernen eines Tags zwischen Index- und Ref-Lesung verändert den Index nicht und wird nach dem beim Ref-Lesen beobachteten Zustand gezählt (`store.py:1342-1365`, `store.py:1607-1613`). Das ist keine Zusage eines atomaren Schnappschusses über beliebig viele gleichzeitige Ref-Änderungen. Ein dauerhaft durch `_tag_targets` festgehaltener falscher Wert ergibt sich aus diesen Abläufen nicht; im reproduzierten Fall korrigiert der nächste Aufruf die Antwort.

Schlüssel mit Schrägstrich werden korrekt zugeordnet: `ref.rsplit(b"/", 1)[0]` im Plan:233 entspricht für einen Tag mit letztem Namenssegment der Eigentumsprüfung `_owns` (`store.py:531-543`) und `_versions_by_key` (`store.py:3683-3690`). `foo/bar/v1.0.0` gehört zu `foo/bar`, nicht zu `foo`. Mit beiden Schlüsseln im temporären Repository reproduziert: `foo/bar` wurde korrekt mit `0`, das unversionierte `foo` mit `1` gezählt.

**Kürzeste Reproduktion:** In einer temporären Kopie `HistoryStore` um exakt das Attribut und die beiden Methoden aus Aufgabe 1, Schritten 4 und 5, ergänzen. Dann folgenden Ablauf ausführen. Der einmalige Hook erzwingt deterministisch dieselbe Unterbrechung wie ein zweiter Executor-Thread nach der Index-Lesung; `forget` selbst bleibt unverändert.

```python
from tempfile import TemporaryDirectory
from store import HistoryStore

with TemporaryDirectory() as path:
    s = HistoryStore(path)
    s.write_snapshot("gone", "a: 1\n", "gone")
    rev = s.write_snapshot("home", "a: 1\n", "home")
    s.create_version("home/v1.0.0", "First", "", rev)
    s.mark_deleted("gone", "deleted")
    original = s._marked_revisions

    def interleaved(repo):
        s._marked_revisions = original
        s.forget("gone")
        return original(repo)

    s._marked_revisions = interleaved
    print(s.unversioned_counts())  # {'gone': 2, 'home': 1}
    print(s.unversioned_counts())  # {'home': 0}
```

Beide Ausgaben wurden mit den unveränderten Methoden aus dem Plan und einer Kopie des tatsächlichen Store-Codes gemessen. Zusätzlich wurde der Ablauf mit einem echten Reader-Thread, zwei `threading.Event`-Schranken und `forget` im anderen Thread reproduziert. Alle temporären Kopien wurden anschließend gelöscht.

**Kleinster Fix:** Den gesamten bisherigen Methodenkörper als innere Funktion `build()` ausführen und ihn über den vorhandenen Store-Helfer `_retrying_a_forget_race(repo, build)` zurückgeben (`store.py:2520-2588`). Jeder Versuch muss Index und Refs erneut lesen; das `_repo()` des bisherigen Körpers kann dabei in `build()` bleiben. Der Helfer prüft auch erfolgreiche Antworten auf unverändertes HEAD und einen fehlenden Forget-Checkpoint und wiederholt bei einem Umbau den gesamten Aufbau. Seine derzeit auf `list[Change]` festgelegten Typannotationen müssen für den zusätzlichen Rückgabetyp `dict[str, int]` verallgemeinert werden. `_tag_targets` braucht keine zusätzliche Invalidierung. Mit genau dieser Wiederholung liefert dieselbe Reproduktion bereits beim ersten Aufruf `{'home': 0}`; auch das wurde in der temporären Kopie geprüft.

ENDE DES REVIEWS
