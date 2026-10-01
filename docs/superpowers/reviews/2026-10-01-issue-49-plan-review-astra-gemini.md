**Trifft zu:** `unversioned_counts()` liefert unter Nebenläufigkeit mit einem gleichzeitig laufenden `forget` einen falschen Wert. Für ein Dashboard, dessen neueste Änderung sowohl vor als auch nach `forget` eine Version trägt, wird fälschlicherweise ein Zähler größer als 0 (im reproduzierten Fall `1` statt `0`) zurückgegeben, und das soeben vergessene Dashboard wird weiterhin mit ungespeicherten Änderungen ausgewiesen.

### Begründung und Fundstellen

1. **Rennbedingung mit `forget` (Fundstelle: `docs/superpowers/plans/2026-10-01-ungespeicherte-aenderungen-in-der-liste.md:261-264`, künftig `custom_components/dashboard_history/store.py` nach Zeile 3443):**
   In `unversioned_counts()` erfolgen zwei getrennte, ungesperrte Lesevorgänge nacheinander:
   - Zeile 261: `index = self._revision_index(repo)`
   - Zeile 264: `marked = self._marked_revisions(repo)`
   Läuft ein `forget` (`store.py:1717` ff.) genau in diesem Zeitfenster durch:
   - `_forget` (`store.py:1935` ff.) schreibt alle Commits ab dem frühesten betroffenen Punkt mit neuen SHAs neu.
   - `_rewrite_tags` (`store.py:2342` ff.) richtet überlebende Tags atomar (`repo.refs.add_packed_refs`) auf die neuen Commit-SHAs aus.
   - `index` hält noch die alten Commit-SHAs der Vor-Rewrite-Generation, während `marked` bereits die neuen Commit-SHAs der Nach-Rewrite-Generation enthält.
   - In Zeile 268–271 schlägt `revision in carrying` für sämtliche Revisions der betroffenen Dashboards fehl. `unversioned_counts()` liefert `len(revisions)` statt `0`.
   - Da weder `_revision_index` noch `_marked_revisions` dabei eine Ausnahme werfen, greift `@_naming_a_forget_race` (`store.py:596-623`) nicht: Die Methode bemerkt das Mischen zweier Generationen nicht und gibt stillschweigend falsche Werte zurück.

2. **Abgrenzung der weiteren Punkte:**
   - **Dashboard-Schlüssel mit Schrägstrich:** Liefern keinen falschen Wert. `ref.rsplit(b"/", 1)[0].decode()` in Zeile 233 trennt exakt das Versionssegment ab (`area/dash/v1.0.0` → `area/dash`) und deckt sich mit `_owns` (`store.py:531-543`), `_versions_by_key` (`store.py:3680-3688`) sowie `_key_of` (`store.py:420-435`).
   - **Mehrere Executor-Threads:** Führen zu keiner Cache-Beschädigung. `self._tag_targets = current` (Zeile 235) ersetzt die Referenz atomar als Ganzes, ohne In-Place-Mutation.
   - **Cache-Zustand `_tag_targets`:** Hält keinen falschen Zustand auf Dauer fest. Die Schlüssel sind Git-Objekt-SHAs (`bytes`), deren Zuordnung zum Ziel-Commit (`str`) durch die Inhaltsadressierung unveränderlich ist. Da `current` bei jedem Aufruf von Grund auf aus den aktuellen `repo.refs.as_dict(b"refs/tags")` aufgebaut wird, verschwinden gelöschte oder umgeschriebene Tags sofort aus dem Cache.
   - **Entstehen/Verschwinden eines Tags:** Ein während des Aufrufs erzeugtes oder gelöschtes Tag spiegelt den linearen Stand zum Zeitpunkt des Ref-Lesens wider und beschädigt keinen Cache.

### Kürzeste Reproduktion

In einer temporären Kopie mit den Plan-Methoden aus Schritten 4 und 5 (`store.py`):

```python
from tempfile import TemporaryDirectory
from store import HistoryStore

with TemporaryDirectory() as path:
    s = HistoryStore(path)
    s.ensure()
    s.write_snapshot("gone", "a: 1\n", "gone")
    rev = s.write_snapshot("home", "a: 1\n", "home")
    s.create_version("home/v1.0.0", "First", "", rev)

    repo = s._repo()
    index = s._revision_index(repo)
    s.forget("gone")
    marked = s._marked_revisions(repo)

    counts = {
        k: next((i for i, r in enumerate(revs) if r in marked.get(k, set())), len(revs))
        for k, revs in index.by_key.items()
    }
    print(counts)  # {'gone': 1, 'home': 1}  -> home müsste 0 sein, gone existiert nicht mehr
```

### Kleinster Fix

In `unversioned_counts()` nach dem Einlesen von `_marked_revisions` validieren, dass `HEAD` noch mit `index.head` übereinstimmt und kein `forget` läuft (`store.py:2508`). Bei einer Diskrepanz `{}` antworten (entsprechend der Spezifikation für unfertigen/gelöschten Index):

```python
        marked = self._marked_revisions(repo)
        if self._resolve(repo, "HEAD") != index.head or self.forget_in_progress():
            return {}
```

Alternativ kann der Rumpf von `unversioned_counts()` über `_retrying_a_forget_race(repo, build)` (`store.py:2523`) ausgeführt werden, was eine Verallgemeinerung der Typannotation von `_retrying_a_forget_race` auf `dict[str, int]` erfordert. Die Prüfung auf `HEAD`-Gleichheit mit Rückgabe von `{}` ist die minimal-invasive Lösung, die exakt zur Best-Effort-Gruppe von `survey` und `measure` (`store.py:51-71`) passt.

ENDE DES REVIEWS
