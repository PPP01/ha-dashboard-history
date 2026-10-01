# Review: Implementierungsplan zu Issue #49 (Ungespeicherte Änderungen in der Liste)

Review des Implementierungsplans `docs/superpowers/plans/2026-10-01-ungespeicherte-aenderungen-in-der-liste.md` gegen den committeten Stand von `main` (Commit `4f8fd3a`), `CLAUDE.md`, `.claude/lessons.md` und die bindende Spec `docs/superpowers/specs/2026-08-30-dashboard-history-design.md`.

## Kritisch

### Getrennte Store-Aufrufe in `operations.async_dashboards` verletzen Entscheidung 24 bei gleichzeitigem `forget`

**Fundstelle:** Plan, Aufgabe 1 Schritt 7, Zeilen 284–290; `custom_components/dashboard_history/operations.py:406-435`; bindende Spec, Entscheidung 24, `docs/superpowers/specs/2026-08-30-dashboard-history-design.md:647-670`; bestehender asynchroner Rennschutz `operations.py:600-665`.

**Beschreibung:** Der Plan ergänzt `operations.async_dashboards` um einen zweiten, separaten Executor-Aufruf:
```python
found = await hass.async_add_executor_job(store.survey)
unversioned = await hass.async_add_executor_job(store.unversioned_counts)
```
Zwischen diesen beiden Aufrufen liegt ein echter `await`-Punkt der Event-Loop. Ein nebenläufiges `forget` kann vollständig oder teilweise zwischen `store.survey` und `store.unversioned_counts` ablaufen. Bei einem `forget` werden überlebende Commits mit neuen SHAs neu geschrieben und alte Objekte sofort entfernt (`grace_period=0`).
Läuft ein `forget` in dieser Lücke durch:
1. `survey` liefert Namen und Metadaten der alten Historiengeneration (beispielsweise ein Dashboard, das gerade vergessen wird).
2. `unversioned_counts` baut den `RevisionIndex` gegen das neue `HEAD` auf, in dem dieses Dashboard gar nicht mehr existiert.
3. Die Schleife in `async_dashboards` iteriert über `found.names` (alte Generation) und weist dem vergessenen Dashboard stillschweigend `0` zu.
4. Läuft das `forget` mitten im zweiten Aufruf, wirft `unversioned_counts` entweder `KeyError` oder `MissingCommitError`. Der Dekorator `@_naming_a_forget_race` wandelt dies in `ForgetRaceError` um (`raise ForgetRaceError from err`), fängt ihn aber nicht ab. `operations.py` fängt diesen Fehler nicht ab, wodurch der WebSocket-Befehl `dashboard_history/dashboards` abstürzt.

Entscheidung 24 der bindenden Spec verbietet ausdrücklich das ungeschützte Verknüpfen mehrerer, nacheinander über `await` gelesener Store-Werte und verlangt, dass ein Lesevorgang `HEAD` vor und nach dem Lesen vergleicht, die Checkpoint-Datei prüft und bei Bewegung oder unfertigem Zustand die gesamte Sequenz wiederholt (wie in `operations._retrying_a_forget_race` für `async_search` implementiert).

**Konsequenz:** Parallele Umschreibevorgänge (`forget`) führen zu Dateninkonsistenzen (Mischung von Generationen) oder unkontrollierten Fehlern im WebSocket-Endpunkt, was gegen die Stabilitätsgarantie der Integration verstößt.

**Vorschlag:** Entweder beide Abfragen in `operations.py` über den vorhandenen Helfer `_retrying_a_forget_race` kapseln (der bei Bewegung von `HEAD` oder aktivem Checkpoint bis zu dreimal neu ansetzt), oder `survey` und `unversioned_counts` im `HistoryStore` zu einem gemeinsamen synchronen Leseaufruf bündeln, der `HEAD` vor und nach der Ausführung prüft.

---

## Wichtig

### Integrationsprüfung in `run_checks.py` beweist weder echte Zähler noch gelöschte Dashboards

**Fundstelle:** Plan, Aufgabe 1 Schritt 8, Zeilen 311–328; `tests/integration/run_checks.py:532-540`.

**Beschreibung:** Die zwei neuen Assertions in `run_checks.py` lauten:
```python
check(
    "every listed dashboard says how many changes no version carries",
    all(
        isinstance(d.get("unversioned"), int) and d["unversioned"] >= 0
        for d in listed["dashboards"]
    ),
    f"{[d.get('unversioned') for d in listed['dashboards']][:10]}",
)
check(
    "a deleted dashboard is never marked as having unversioned changes",
    all(d["unversioned"] == 0 for d in listed["dashboards"] if not d["exists"]),
)
```
Die erste Prüfung prüft lediglich, ob der Wert ein nicht-negativer Integer ist. Eine fehlerhafte Implementierung, die für jedes Dashboard fest `0` liefert, besteht diese Prüfung problemlos.
Die zweite Prüfung filtert über `if not d["exists"]`. An Zeile 534 von `run_checks.py` existiert typischerweise noch kein gelöschtes Dashboard im Test-Setup; in Python ist `all([]) == True`. Die Prüfung ist an dieser Stelle vakuos.

**Konsequenz:** Ein fehlerhafter Server, der immer `0` liefert oder für gelöschte Dashboards falsche Werte weitergibt, würde in der CI und lokal als erfolgreich gemeldet.

**Vorschlag:** Die Prüfung für gelöschte Dashboards dorthin verlegen, wo `run_checks.py` tatsächlich ein Dashboard löscht (um Zeile ~747), und dort prüfen, dass `d["unversioned"] == 0` gilt. Für lebende Dashboards einen Schritt einfügen, der eine neue Änderung schreibt und verifiziert, dass `unversioned` mindestens `1` beträgt, sowie nach Erstellung einer Version auf `0` zurückkehrt.

### Screenreader-Ausgabe (`.sr`) ist im Test-Harness ungetestet

**Fundstelle:** Plan, Aufgabe 2 Schritt 1, Zeilen 408–410, und Schritt 3, Zeilen 491–495; `custom_components/dashboard_history/panel.js:3203-3210`; `tests/test_panel_behaviour.py`.

**Beschreibung:** Der Code in `_renderDashboard` erzeugt barrierefreie Texte für Screenreader:
```javascript
<span class="pending" title="${pending} ...">${pending}<span class="sr"> ${pending === 1 ? "change" : "changes"} not saved as a version yet</span></span>
```
Der im Plan vorgeschlagene Test-Parser in `_UNTIDY_SIDE` extrahiert jedoch nur:
```javascript
chip: (/<span class="pending"[^>]*>(\d+)/.exec(part) || [])[1] || null,
title: (/<span class="pending" title="([^"]*)"/.exec(part) || [])[1] || null,
```
Es gibt keinen Test, der prüft, ob das Element `<span class="sr">` überhaupt vorhanden ist oder den korrekten Inhalt trägt.

**Konsequenz:** Sollte ein Refactoring das `<span class="sr">` versehentlich entfernen oder den Text beschädigen, blieben alle Tests in `test_panel_behaviour.py` grün. Die Barrierefreiheit wäre unbemerkt gebrochen.

**Vorschlag:** Den Extractor in `_UNTIDY_SIDE` um `sr: (/<span class="sr">([^<]*)<\/span>/.exec(part) || [])[1] || null` erweitern und mit entsprechenden Assertions (`assert untidy_side["many"]["sr"] == " 3 changes not saved as a version yet"`) absichern.

### Ungetesteter Randzustand: Initialisiertes, aber noch leeres Repository

**Fundstelle:** Plan, Aufgabe 1 Schritt 2, Zeilen 93–95, und Schritt 5, Zeilen 258–263; `custom_components/dashboard_history/store.py:258-272`.

**Beschreibung:** Der Plan testet mit `test_a_store_without_a_repository_answers_nothing` den Fall, dass kein `.git`-Verzeichnis existiert. Im Code von `unversioned_counts` gibt es jedoch zwei Abbruchbedingungen:
```python
repo = self._repo()
if repo is None:
    return {}
index = self._revision_index(repo)
if index is None:
    return {}
```
Wenn ein Store mit `store.ensure()` initialisiert wurde, aber noch kein Snapshot geschrieben wurde, existiert `repo`, aber `HEAD` ist noch ungeboren (`_resolve(repo, "HEAD") is None`), sodass `_revision_index` `None` zurückgibt. Dieser Zustand wird in `tests/test_unversioned.py` nicht getestet.

**Konsequenz:** Die Zusicherung, dass ein Repository ohne Commits sauber mit `{}` antwortet, ist nicht durch Tests abgedeckt.

**Vorschlag:** Einen Test `test_an_empty_store_answers_nothing(store)` ergänzen, der auf dem frischen Fixture-Store (nach `ensure()`, vor erstem `write_snapshot`) `store.unversioned_counts() == {}` prüft.

---

## Hinweis

### Platzierung der CSS-Tests in `test_panel_behaviour.py` statt `test_panel_assets.py`

**Fundstelle:** Plan, Aufgabe 2 Schritt 1, Zeilen 456–473, und Schritt 6, Zeilen 541–546; `tests/test_panel_behaviour.py`; `tests/test_panel_assets.py`.

**Beschreibung:** Die beiden Tests `test_the_orange_rule_comes_after_the_blue_one` und `test_the_orange_stripe_is_the_colour_the_current_state_wears` prüfen statische Zeichenketten im Stylesheet `style.js`. Entsprechend der Architektur des Repositories gehören statische Asset- und Stylesheet-Prüfungen in `tests/test_panel_assets.py`, während `tests/test_panel_behaviour.py` das funktionale DOM-/Laufzeitverhalten im Node-Harness testet. Zudem führt Schritt 5 zwar `test_panel_assets.py` aus, Schritt 6 committet aber nur `test_panel_behaviour.py`.

**Konsequenz:** Aufweichung der sauberen Trennung zwischen Asset-Prüfung und Verhaltensprüfung.

**Vorschlag:** Die beiden CSS-Tests in `tests/test_panel_assets.py` einfügen und diese Datei im Commit für Aufgabe 2 stagen.

### Zweifel an der Namensform von `remove_version` im Plan ist unbegründet

**Fundstelle:** Plan, Aufgabe 1 Schritt 3, Zeilen 178–179; `custom_components/dashboard_history/store.py:1505-1507, 1554`.

**Beschreibung:** Der Plan enthält die Bemerkung: »Falls remove_version(key, name) einen anderen Namensbezug erwartet (...), die Namensform aus dem vorhandenen Test tests/test_store.py übernehmen (...), nicht raten.«
Die Prüfung des tatsächlichen Codes zeigt: `_tag_at_locked(repo, key, name)` prüft `if not _owns(name.encode("utf-8"), key): raise ValueError(...)`. Da `_owns` verlangt, dass der Name mit `${key}/` beginnt, ist die im vorgeschlagenen Test verwendete Form `store.remove_version("home", "home/v1.0.0")` bereits zwingend und exakt die richtige.

**Konsequenz:** Der Zweifel im Plan ist unbegründet; die bedingte Anweisung kann bei einem ausführenden Agenten zu unnötigem Zögern oder falschen Anpassungen führen.

**Vorschlag:** Den Hinweis im Plan streichen oder als verifiziert kennzeichnen.

### Cache-Verhalten von `_tag_targets` ist funktional korrekt, aber ohne Regressionstest

**Fundstelle:** Plan, Aufgabe 1 Schritt 4, Zeilen 184–195, und Schritt 5, Zeilen 215–236; `custom_components/dashboard_history/store.py`.

**Beschreibung:** Der In-Memory-Cache `_tag_targets` bildet Tag-SHAs auf Commit-SHAs ab. Die empirische Messung im Rahmen dieses Reviews bestätigt die Wirksamkeit: Bei 400 Tags sinkt die Laufzeit von ~524 ms (kalt, inkl. Indexbau) auf ~15 ms (warm, reiner Ref-Scan via `as_dict`). Da Tag-SHAs kryptografisch an den Inhalt gebunden sind, können Einträge nie veralten. Gelöschte Tags fallen beim Neuaufbau von `current` automatisch weg. Allerdings prüft keiner der Unit-Tests explizit, ob bei wiederholtem Aufruf keine erneute Auflösung via `repo[sha]` stattfindet.

**Konsequenz:** Ein künftiges Refactoring könnte den Cache versehentlich deaktivieren, ohne dass ein Test fehlschlägt.

**Vorschlag:** Einen kleinen Test ergänzen, der verifiziert, dass für unveränderte Tags nach dem ersten Aufruf kein Objektzugriff mehr auf Dulwichs Objektspeicher erfolgt.

---

## Urteil

Der Plan ist **umsetzbar nach Korrekturen**.

Die Analyse gegen den Code zeigt, dass die grundlegende Architektur stimmig ist:
1. Alle harten Vorgaben aus `CLAUDE.md` (kein Aufruf der `git`-CLI, Home-Assistant-Freiheit des Kerns `store.py`, Ausführung im Executor, Dulwich-Verwendung, keine Backticks/Substitutionen in `style.js`, Einhaltung der Komplexitäts-Ratsche und `lint-imports`) werden eingehalten.
2. Die CSS-Spezifitätsüberlegung (`.dash.untidy` nach `.dash[aria-current="true"]` mit identischer Spezifität `(0, 2, 0)`) ist mathematisch exakt und sorgt dafür, dass das ausgewählte ungespeicherte Dashboard orange umrandet bleibt und gleichzeitig den grauen Hintergrund behält.
3. Die Ref-Aufspaltung (`rsplit(b"/", 1)`) harmoniert mit `_versions_by_key` und unterstützt auch Legacy-Schlüssel mit Schrägstrichen.

Vor Beginn der Implementierung muss jedoch der kritische Befund behoben werden: Das getrennte Lesen von `survey` und `unversioned_counts` in `operations.async_dashboards` muss gegen parallele `forget`-Vorgänge gemäß Entscheidung 24 abgesichert werden (idealerweise über den vorhandenen Helfer `_retrying_a_forget_race`). Zudem sollten die Tests für Barrierefreiheit (`.sr`) und der Integrationscheck in `run_checks.py` nachgeschärft werden.

ENDE DES REVIEWS
