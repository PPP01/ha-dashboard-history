# Design: `analyze.py` aufteilen

**Datum:** 2026-09-27
**Status:** Entwurf, zweite Fassung. Die erste Fassung (neun Module, ein Unterpaket `undo/` mit neun Dateien, eigene AST-Tests) wurde von Terra, Astra und Gemini geprüft; ihre Befunde sind hier eingearbeitet. Auf Wunsch des Nutzers danach **verschlankt** (siehe »Warum diese Fassung schlanker ist«). Terra-, Astra- und Gemini-Review der zweiten Fassung am 2026-09-27 eingearbeitet (Entscheidungen 5, 7 und 14, Abschnitte 1–4). **Vom Nutzer am 2026-09-27 freigegeben**, einschließlich der begründeten Zurückweisungen und der beiden neuen Entwicklungswerkzeuge.
**Vorhaben:** P aus dem Abschnitt »Reihenfolge der Vorhaben« der Haupt-Spec
**GitHub-Issue:** [#41](https://github.com/PPP01/ha-dashboard-history/issues/41)
**Integration:** `dashboard_history`
**Bindend bei Widerspruch:** die Haupt-Spec (`2026-08-30-dashboard-history-design.md`), insbesondere Entscheidung 4 und 15, sowie die Specs zu L, M, N und O, deren Regeln `plan_undo` heute trägt

## Kontext & Ziel

`analyze.py` ist in vier Wochen von 550 auf 2442 Zeilen gewachsen. Das allein wäre in Python kein Problem – die Standardbibliothek hat Module dieser Größe (`argparse.py` 2677, `typing.py` 3460 Zeilen), und die Funktionen in `analyze.py` sind überwiegend klein und rein. Das eigentliche Problem ist eine einzige Funktion: `plan_undo` umfasst 430 Zeilen und hat eine zyklomatische Komplexität von **54**, bei einer üblichen Grenze von 10. Jedes der Vorhaben L, M, N und O hat dort einen weiteren Block angebaut.

Das Vorhaben hat drei Ziele, in dieser Rangfolge:

1. **Eine Wache gegen erneutes Zuwachsen.** Ein Linter mit Komplexitätsgrenzen und ein Vertrag über erlaubte Importe, beide in der CI. Ohne Wache wächst ein einmal aufgeräumter Code wieder zu – das war der Anlass.
2. **`plan_undo` zerlegen** in einen Planer je Art (Sections, Einstellungen, Karten, Badges, Ansichten) und einen Kombinierer, der die Reihenfolge ausdrücklich festhält.
3. **`analyze.py` in fünf Module teilen**, entlang von Grenzen, die im Code schon erkennbar sind.

Alles **verhaltensneutral**: Für jede Eingabe liefert jede öffentliche Funktion byte-gleich dasselbe Ergebnis wie vorher, einschließlich der Reihenfolge der Schritte und des Wortlauts jeder Verweigerung.

**Ausdrücklich nicht Teil der Verhaltensneutralität** sind Klassenmetadaten, die ein Umzug zwangsläufig ändert: `__module__` (aus `analyze` wird etwa `analyze.model`), damit der `repr` der *Klasse* und die Bytes einer `pickle`-Serialisierung (Astra, zweite Runde). Der `repr` einer *Instanz* bleibt gleich. Nichts im Projekt liest diese Metadaten: kein `pickle`, kein `__module__`, kein `__qualname__` in `custom_components/` oder `tests/`, und jedes `!r` in einer Meldung formatiert Feldwerte, keine Klassen (Grep, 2026-09-27). Zudem ist `__module__` schon heute nicht stabil – in pytest heißt das Modul `analyze`, in Home Assistant `custom_components.dashboard_history.analyze`.

### Verifizierte Ausgangslage (2026-09-27, am Quelltext nachgeprüft)

| Feststellung | Beleg |
|---|---|
| `analyze.py`: 2442 Zeilen, 95 Namen auf oberster Ebene – 68 Funktionen, 14 Klassen, 13 Konstanten. Die Klassen sind 13 Datenklassen und ein `NamedTuple` (`_SectionAnchor`); drei tragen Methoden, die Hilfen aus dem Modul aufrufen: `Matching` (`same_place` ruft `_translated` und `_place`; `loose_removed`, `loose_added`), `SectionMatching` (`views`), `UndoPlan` (Property `parked`) | AST-Auswertung; `analyze.py:25`, `:311-320`, `:336-348`, `:399-402`; von Terra und Gemini unabhängig bestätigt |
| `plan_undo` Zeilen 1490–1919, 430 Zeilen; danach `_explain` 156, `_plan_sections` 98, `find_removed` 87 | AST-Auswertung; von Gemini bestätigt |
| Wachstum: 550 (`a53a5eb`, 2026-08-31) → 1102 (`4ef2536`, 09-04) → 1282 (`7dc654d`, 09-12) → 1664 (`54f6b9e`, 09-25) → 2442 (`38def42`, 09-26) | `git show <commit>:…/analyze.py \| wc -l`; die Commits nach Gemini, die die Zahl jeweils zuerst erreichten |
| Abdeckung Zeilen + Zweige 97 %; in `plan_undo` 2 Zeilen und 3 Zweige ungedeckt (1630, 1850; 1571→1560, 1629→1630, 1849→1850); 229 Tests in `test_analyze.py`; Gesamtlauf 968 passed, 2 skipped | `coverage 7.16.2` mit `--cov-branch`; von Gemini bestätigt |
| **Komplexität** (`ruff 0.16.9`, Regeln `C901`, `PLR0912`, `PLR0915`, Standardgrenzen 10 / 12 / 50): 15 Funktionen im ganzen Paket reißen eine Grenze. Mit Abstand am schlimmsten `plan_undo` (Komplexität 54, 40 Zweige, 128 Anweisungen), dann `_explain` (29, 26, 63). Die übrigen 13 liegen knapp darüber (11–18): `_match_slots`, `_pair_view_sections`, `_plan_sections` in `analyze.py`; `async_compare`, `async_restore_state`, `async_undo_change` in `operations.py`; `reinsert`, `apply_undo` in `restore.py`; `async_register` in `services.py`; `_walked_changes`, `_resolve`, `survey`, `_read_checkpoint` in `store.py` | `ruff check custom_components/ --isolated --select C901,PLR0912,PLR0915`, am 2026-09-27 in einer Wegwerf-Umgebung |
| Das Projekt hat **keinen Linter** und keine Datei `pyproject.toml`. Die CI (`.github/workflows/test.yml`) installiert `pytest pyyaml "dulwich==1.2.14"` und führt pytest unter Python 3.12 und 3.13 aus | Dateisystem, `test.yml` |
| Kein Test ersetzt etwas in `analyze` per `monkeypatch` oder `mock.patch` | Grep über `tests/`; von Gemini bestätigt |
| Tests greifen auf 25 Namen zu, davon 10 private. Öffentlich: `RemovedItem`, `UndoPlan`, `UndoStep`, `card_containers`, `change_message`, `explain_change`, `explain_effect`, `find_removed`, `match_badges`, `match_cards`, `match_sections`, `message_adds`, `plan_undo`, `setting_changes`, `summarize`. Privat: `_ABSENT`, `_ENTRY_LIMIT`, `_POSITION_REFUSAL`, `_SECTIONS_AND_CARDS_REFUSAL`, `_counts`, `_describe`, `_moved`, `_pair_sections`, `_plan_sections`, `_views_by_key` | AST-Auswertung über `tests/`; von Terra und Gemini unabhängig bestätigt |
| Aufrufer im Code: `operations.py` (`explain_change`, `explain_effect`, `find_removed`, `message_adds`, `plan_undo`, `same_config`), `capture.py` (`change_message`); `restore.py` nur unter `TYPE_CHECKING` (`RemovedItem`, `UndoPlan`, `UndoStep`). Zusammen mit den Tests: 26 Namen | Grep und AST; von Terra und Gemini bestätigt |
| **Die Reihenfolge, in der `plan_undo` verweigert, ist nicht die, in der es Schritte ausgibt.** Geprüft wird: Vorprüfungen, Sections, Einstellungen, Karten, Badges, Ansichten, dann die Querprüfung Sections-gegen-Karten. Ausgegeben wird: Einstellungen, Karten (geparkte sortiert ans Ende der Karten), Badges, Ansichten, Sections. Die erste Verweigerung gewinnt | `plan_undo`, Zeilen 1538–1919; von allen drei Reviews bestätigt |
| **Die Schrittreihenfolge ist über Artgrenzen hinweg beobachtbar.** `apply_undo` sortiert Entfernungen von Karten und Badges gemeinsam nach `-index`, nicht geparkte Einsetzungen von Ansichten, Karten und Badges gemeinsam nach `index`, jeweils mit stabilem `sorted`; bei gleichem Index entscheidet die Plan-Reihenfolge. Geparkte Karten werden in Plan-Reihenfolge angehängt | `restore.py:497-500`, `:524-525` und die Schleife über geparkte Schritte |
| Kein Generator für Änderungshistorien im Repo; `.real-storage` enthält je Dashboard **einen** Stand | Grep; `conftest.py`, `REAL_DASHBOARDS` |
| Ein Paket hat Vorrang vor einer gleichnamigen `.py`-Datei im selben Verzeichnis | nachgestellt unter Python 3.12.3 und 3.14.6; von Gemini bestätigt |
| `import-linter 2.15` prüft Importverträge statisch, ohne dass `homeassistant` installiert sein muss, und findet auch **transitive** Importe (`operations → const → homeassistant`). Ein Schichtenvertrag mit gleichrangigen, voneinander unabhängigen Modulen (`explain \| undo`) bricht bei einem Seitwärts- und einem Aufwärtsimport und hält bei einem Abwärtsimport | an einem Wegwerf-Paket und am echten Paket nachgestellt, 2026-09-27 |

## Nicht-Ziele (YAGNI)

- **Keine Verhaltensänderung,** auch keine »offensichtlich richtige«. Ein beim Umbau gefundener Fehler wird ein Issue und ein eigener Commit außerhalb von P.
- **Keine Stilregeln.** `ruff` prüft in diesem Vorhaben ausschließlich Komplexität (`C901`, `PLR0912`, `PLR0915`) – keine Formatierung, keine Namenskonventionen, keine Importsortierung. Der Code wird nicht umformatiert.
- **Kein Abbau der übrigen 14 Ausreißer.** Sie stehen in der Baseline (Abschnitt 1) und dürfen nicht wachsen, werden aber nicht umgebaut. `_explain` gehört zu [#37](https://github.com/PPP01/ha-dashboard-history/issues/37), die Funktionen in `store.py` zu [#42](https://github.com/PPP01/ha-dashboard-history/issues/42).
- **Keine Zusammenlegung von Karten- und Badge-Logik** (`sole`/`sole_badge`, `card_came_back`/`came_back`). Das ist eine Logikänderung und gehört zu #37 oder einem Nachfolger.
- **Kein Umbau von `store.py`, `operations.py`, `restore.py` oder `panel.js`.**
- **Keine Umbenennung,** keine Klassenhierarchie für Planer, keine Beschleunigung. Jeder Name behält seinen Namen; über `analyze` direkt erreichbar bleiben die 26 der erklärten Schnittstelle (Abschnitt 2).

## Entwurf

Drei Teile, jeder in kleinen, einzeln prüfbaren Commits: **P1** die Wache, **P2** das Paket (reiner Umzug), **P3** die Planer (Umstrukturierung).

### 1. Die Wache (P1)

**Eine neue Datei `pyproject.toml`**, ausschließlich mit Werkzeugkonfiguration (kein `[project]`, kein Build-System – die Integration wird weiterhin über HACS verteilt, nicht als Python-Paket).

**`ruff`**, nur mit den drei Komplexitätsregeln und ihren Standardgrenzen:

- `C901` – zyklomatische Komplexität höchstens 10
- `PLR0912` – höchstens 12 Zweige je Funktion
- `PLR0915` – höchstens 50 Anweisungen je Funktion

Geprüft wird `custom_components/dashboard_history/`, nicht `tests/`.

**Die 15 heutigen Ausreißer stehen in einer Baseline, nicht in `noqa`-Kommentaren** (Terra, zweite Runde, Hoch 1). Eine Datei `tools/complexity-baseline.json` hält für jeden Ausreißer Datei, Funktionsname, Regel und heutigen Messwert fest – 23 Einträge für 15 Funktionen (`plan_undo` etwa mit `C901: 54`, `PLR0912: 40`, `PLR0915: 128`). Ein kleines Skript `tools/complexity_ratchet.py` ruft `ruff check --ignore-noqa --output-format json`, ordnet jede Meldung über die Zeile der `def` ihrem Funktionsnamen zu (per AST der betroffenen Datei, weil `PLR0912`/`PLR0915` den Namen nicht mitliefern) und vergleicht mit der Baseline. Es schlägt fehl, wenn

- eine Meldung für eine Funktion auftaucht, die nicht in der Baseline steht – **eine neue oder eine bisher gesunde Funktion reißt die Grenze**,
- ein Messwert über seinem Baseline-Wert liegt – **ein Ausreißer ist weiter gewachsen**,
- ein Messwert unter seinem Baseline-Wert liegt oder ein Eintrag gar nicht mehr gemeldet wird – dann muss die Baseline im selben Commit gesenkt werden. So sinkt die Grenze mit jeder Verbesserung mit und kann nie wieder auf den alten Wert steigen.

`--ignore-noqa` sorgt dafür, dass ein Kommentar im Code nichts daran ändert. Eine Ausnahme ist damit immer eine sichtbare Änderung an der Baseline-Datei und fällt im Review auf. Nebenbei entfallen alle Änderungen an `operations.py`, `restore.py`, `services.py` und `store.py`: Die Wache kommt ohne ein Zeichen in diesen Dateien aus. Jeder Baseline-Eintrag nennt das Issue, das ihn abbauen soll: `plan_undo` und `_plan_sections` #41, `_explain` #37, die vier in `store.py` #42, die übrigen ein neu anzulegendes Sammel-Issue.

**`import-linter`** mit zwei Verträgen:

- **HA-Freiheit** (`forbidden`): Die sieben Kernmodule – `yaml_io`, `analyze` (nach P2 das Paket mit allen Teilmodulen), `restore`, `versions`, `store`, `report`, `keys` – importieren `homeassistant` weder direkt noch transitiv. Das macht die harte Regel aus `CLAUDE.md` zum ersten Mal prüfbar.
- **Schichten in `analyze`** (`layers`): kommt mit P2 dazu, siehe Abschnitt 2.

**CI:** ein zusätzlicher Job in `test.yml`, der `ruff` und `import-linter` in festen Versionen installiert (`ruff==0.16.9`, `import-linter==2.15` – gepinnt wie `dulwich`, damit eine neue Werkzeugversion keinen grünen Stand rot färbt) und `tools/complexity_ratchet.py` sowie `lint-imports` ausführt. Lokal dieselben Befehle; `docs/development.md` nennt sie.

### 2. Das Paket (P2)

`analyze.py` wird ein Paket `analyze/` mit fünf Modulen. Die Zuordnung ist **vollständig** – jeder der 95 Namen auf oberster Ebene steht genau einmal hier – und **maschinell geprüft**: Eine AST-Auswertung aller Namensverweise, Methodenrümpfe und Standardwerte von Parametern eingeschlossen, findet keine Kante zu einer gleichen oder höheren Schicht (2026-09-27).

| Schicht | Modul | Namen | Zeilen (nur Definitionen, ohne Kopf und Leerzeilen) |
|---|---|---|---|
| 0 | `model.py` | *Typen:* `_SectionAnchor`, `RemovedItem`, `Summary`, `Entry`, `ViewChanges`, `Explanation`, `Slot`, `SectionMatching`, `Matching`, `UndoStep`, `UndoPlan`, `SectionSlot`, `SectionPair`, `SettingChange`, `_ABSENT`, `_place`, `_translated`. *Lesen:* `card_containers`, `badge_containers`, `_views_by_key`, `_by_position`, `_own`, `_section_list`, `fingerprint`, `same_config`, `_view_name`. *Benennen:* `_LABEL_LIMIT`, `_shorten`, `_first_line`, `_first_entity`, `_inner_card`, `_weak_key`, `_describe`, `_section_title` | 459 |
| 1 | `matching.py` | *Sections:* `_pair_view_sections`, `_pair_sections`, `_moved`, `_count_places`, `_whole`, `_settle_sections`, `_positions_lie`, `_paths_collide`, `_section_marks`, `_same_marks`, `_section_drift`, `_section_anchor`, `_view_type`, `_view_type_changed`. *Karten und Badges:* `_slots`, `_similarity`, `_unpaired`, `match_cards`, `match_sections`, `_match_slots`, `match_badges`, `_reordered`. *Einstellungen:* `_NOT_VIEW_SETTINGS`, `_same`, `_setting_leaves`, `setting_changes`, `_setting_at` | 612 |
| 2 | `removed.py` | `find_removed` (»Put back«) | 87 |
| 3 | `explain.py` | `summarize`, `_PAST`, `_FUTURE`, `_ENTRY_LIMIT`, `_NOTHING_LOST`, `_NOT_IN_CARDS`, `_entry`, `_value_text`, `_setting_entry`, `_section_setting_changes`, `_capped`, `_section_name`, `_where`, `_explain`, `explain_change`, `explain_effect`, `_meta_detail`, `_views`, `_sections_part`, `change_message`, `_COUNT`, `_counts`, `message_adds` | 468 |
| 3 | `undo.py` | `_POSITION_REFUSAL`, `_SECTIONS_AND_CARDS_REFUSAL`, `_VIEW_TYPE_REFUSAL`, `_DUPLICATE_PATH_REFUSAL`, `_present`, `_group_by_mark`, `_in_view`, `_step`, `_plan_sections`, `plan_undo` – nach P3 zusätzlich der Kontext, die Vorprüfungen, die Planer und der Kombinierer | 584 |

Abhängigkeiten, gemessen: `matching → model`; `removed → matching, model`; `explain → matching, model`; `undo → matching, model`. `explain` und `undo` stehen auf derselben Schicht und importieren einander nicht.

**Warum `_place` und `_translated` in `model.py` stehen:** `Matching.same_place` ruft sie, und eine Methode löst ihre Namen im Modul der Klasse auf, nicht in dem des Aufrufers. Lägen sie eine Schicht höher, müsste `model.py` nach oben importieren – oder `same_place` scheiterte erst beim ersten Aufruf mit `NameError`, nicht beim Import (Terra, Kritisch 2; Gemini, Hoch 1).

**Der Schichtenvertrag** in `pyproject.toml` hält genau diese Tabelle fest: `explain | undo` über `removed` über `matching` über `model`. `removed` steht über `matching`, weil es `match_cards` braucht; `explain` und `undo` brauchen `removed` nicht, dürften es aber. Weil die Module in einem Unterpaket liegen, braucht der Vertrag `containers`; ohne sucht `import-linter` die Schichten direkt unter `custom_components.dashboard_history` und bricht mit »Missing layer« ab (Gemini, zweite Runde, Hoch 2). In TOML stehen Verträge als Array von Tabellen (Gemini, Niedrig 6). Beide Verträge zusammen, an einer Attrappe mit fünf Modulen von Gemini und am echten Paket (HA-Freiheit) vom Assistenten nachgeprüft:

```toml
[tool.importlinter]
root_package = "custom_components.dashboard_history"
include_external_packages = true

[[tool.importlinter.contracts]]
name = "The core modules stay free of Home Assistant"
type = "forbidden"
source_modules = [
    "custom_components.dashboard_history.yaml_io",
    "custom_components.dashboard_history.analyze",
    "custom_components.dashboard_history.restore",
    "custom_components.dashboard_history.versions",
    "custom_components.dashboard_history.store",
    "custom_components.dashboard_history.report",
    "custom_components.dashboard_history.keys",
]
forbidden_modules = ["homeassistant"]

[[tool.importlinter.contracts]]
name = "analyze is layered"
type = "layers"
containers = ["custom_components.dashboard_history.analyze"]
layers = [
    "explain | undo",
    "removed",
    "matching",
    "model",
]
```

`lint-imports` fügt das Arbeitsverzeichnis selbst zu `sys.path` hinzu; aus der Repository-Wurzel aufgerufen läuft es lokal und in der CI gleich. `custom_components/` hat keine `__init__.py` und muss auch keine bekommen – mit einer bräche die Importanalyse ab (Gemini, Schwerpunkt 2).

**Imports innerhalb des Pakets sind relativ** (`from .model import Slot`). Das funktioniert flach in pytest (`analyze` ist dort ein Paket auf oberster Ebene) und als `custom_components.dashboard_history.analyze` in Home Assistant; `restore.py` bleibt ohne Laufzeitimport aus `analyze` (Gemini, Schwerpunkt 3, bestätigt). Kein Import innerhalb einer Funktion, um einen Kreis zu umgehen.

**`analyze/__init__.py`** enthält keine Logik und exportiert genau die 26 Namen, die Code und Tests heute über `analyze` erreichen (Ausgangslage) – nicht alle 95. Diese 26 sind damit die **erklärte Schnittstelle** des Pakets. Alle übrigen Namen behalten ihren Namen und bleiben über ihr Modul erreichbar (`analyze.model.fingerprint`), nur nicht mehr über `analyze` direkt. Das ist kein Bruch für Dritte: `analyze` ist ein internes Modul einer Home-Assistant-Integration, keine Bibliothek, und niemand außerhalb dieses Repositorys importiert es (Terra, zweite Runde, Niedrig 1).

**Ein kleiner Test hält die Schnittstelle fest** (Terra, zweite Runde, Mittel 3): `set(analyze.__all__)` ist genau die Menge der 26 Namen, und jeder davon ist über `analyze` auflösbar. Die bestehenden Tests prüfen das nicht – sie greifen per Attribut zu (`analyze.plan_undo`), und ein fehlender Eintrag in `__all__` fiele dabei nicht auf.

**Reihenfolge im Plan:** zuerst `git mv analyze.py analyze/__init__.py` ohne inhaltliche Änderung, dann die Module von unten nach oben herauslösen, eines je Commit. Der Schichtenvertrag kommt mit dem ersten herausgelösten Modul in die Konfiguration.

### 3. Die Planer (P3)

`plan_undo(before, after, current) -> UndoPlan` behält Signatur, Docstring und Rückgabe. Innen wird es zum Kombinierer. Alles bleibt in `undo.py` – eine Datei, nicht ein Unterpaket.

**Der Kontext.** Ein Objekt `UndoContext` hält `before`, `after`, `current` und alles, was heute oben in `plan_undo` oder zwischen den Blöcken berechnet und von mehreren Arten gelesen wird (`matching`, `badge_matching`, `old_views`, `new_views`, `now_views`, `now_index`, `shifted`, `settings`, `by_mark`, `card_then`, `badge_now`, `badge_then`, `now_places`). Abgeleitete Werte werden erst beim ersten Zugriff berechnet und dann gemerkt – so rechnet der Kontext bis zur ersten Verweigerung nichts, was heute nicht auch gerechnet würde.

**Vorprüfungen** und **Planer**, jede eine Funktion mit demselben Vertrag: Sie bekommt den Kontext und gibt entweder eine Verweigerung (Text) oder ein Tupel von Schritten zurück.

| | Stufe | heutige Stelle |
|---|---|---|
| V1 | nichts geändert → »this change did not alter any cards« | 1524–1538 |
| V2 | ein Pfad benennt zwei Ansichten → `_DUPLICATE_PATH_REFUSAL` | 1542 |
| V3 | Positionen stimmen nicht überein → `_POSITION_REFUSAL` | 1548 |
| V4 | Ansichtstyp geändert → `_VIEW_TYPE_REFUSAL` | 1553 |
| | Planer `sections` – je Ansicht mit Section-Ereignis, nach `str(key)` sortiert | 1555–1572 |
| | Planer `settings` | 1574–1612 |
| | Planer `cards` – bearbeitet/verschoben, hinzugekommen, gelöscht; geparkte Einsetzungen sortiert am Ende der Karten-Schritte | 1614–1742 |
| | Planer `badges` | 1744–1825 |
| | Planer `views` – erst hinzugekommene, dann entfernte Ansichten | 1827–1908 |
| Q1 | ein `sections_list`-Schritt und ein Karten-Schritt in derselben Ansicht → `_SECTIONS_AND_CARDS_REFUSAL`. Liest die Ergebnisse zweier Planer und gehört deshalb dem Kombinierer | 1910–1917 |

Innerhalb eines Planers bleibt die heutige Reihenfolge der Prüfungen und der erzeugten Schritte erhalten.

**Q1 hat einen anderen Vertrag als die übrigen Stufen** (Gemini, zweite Runde, Mittel 5): Es bekommt nicht den Kontext, sondern die schon gesammelten Schritte der Planer `sections` und `cards`, und gibt eine Verweigerung oder nichts zurück. Der Kombinierer ruft es nach dem letzten Planer auf. In der Prüfreihenfolge steht es trotzdem, weil seine Verweigerung dort ihren Rang hat – nach jeder Verweigerung eines Planers.

**Hilfsfunktionen stehen auf Modulebene, nicht im Planer** (Gemini, zweite Runde, Hoch 1). `ruff` rechnet die Komplexität einer verschachtelten Funktion der äußeren zu, und zwar vollständig plus eins für das `def` – nachgemessen an einem kleinen Beispiel und an den künftigen Planern (2026-09-27): Mit ihren heutigen inneren Funktionen läge `cards` bei 17, `badges` bei 15; `cards` ohne sie bei 9. Die sieben inneren Funktionen aus `plan_undo` – `sole`, `put_back`, `card_came_back`, `parked_order`, `sole_badge`, `came_back`, `badge_label` – werden deshalb Funktionen auf oberster Ebene von `undo.py`. Was sie heute aus dem umgebenden Rumpf lesen (`by_mark`, `card_then`, `badge_now`, `badge_then`, `shifted`), bekommen sie als Parameter oder aus dem Kontext. Wo sie heute in eine äußere Liste schreiben (`put_back` hängt an `steps` oder `parked` an), geben sie ihr Ergebnis zurück, und der Planer hängt es an derselben Stelle an wie heute. Das ist die einzige Stelle in P3, an der sich die Form des Codes über das bloße Herauslösen hinaus ändert – und genau dafür ist der Vergleich alt gegen neu da.

**Zwei Reihenfolgen, beide ausdrücklich.** Der Kombinierer führt zwei feste Tupel nebeneinander, jedes mit einem Kommentar, der den Grund nennt:

- **Prüfreihenfolge** – `V1, V2, V3, V4, sections, settings, cards, badges, views, Q1`. Die erste Verweigerung wird zurückgegeben.
- **Ausgabereihenfolge** – `settings, cards, badges, views, sections`.

Die Gründe stehen heute verstreut in `plan_undo` (Pfad vor jedem Paarvergleich, Typ vor Drift, Sections zuerst geprüft und zuletzt geschrieben). Ein neues Vorhaben trägt seinen Planer in **beide** Tupel ein und muss dabei entscheiden, wo er hingehört.

**Komplexität.** Nach P3 sind die drei Baseline-Einträge von `plan_undo` gestrichen, und keiner der neuen Planer und keine der neuen Vorprüfungen steht in der Baseline. Reißt ein Planer die Grenze, wird er innerhalb von `undo.py` weiter in Hilfsfunktionen zerlegt, nicht in die Baseline aufgenommen. `_plan_sections` zieht unverändert mit und behält seinen Eintrag.

### 4. Die Abnahme

**P1 und P2** verschieben Code, ohne ihn zu ändern. Dafür reichen die vorhandenen 229 Tests bei 97 % Abdeckung, der Schichtenvertrag und `run_checks.py` – kein Test ersetzt etwas per `monkeypatch`, und ein fehlender Export fällt als `AttributeError` auf genau diesen Namen auf.

**P3** strukturiert Logik um, und dort reicht das nicht: Kaum ein Test prüft die Reihenfolge aller Schritte eines Plans oder welche von zwei zutreffenden Verweigerungen gewinnt – genau das, was P3 umstellt. Dafür ein **Vergleich alt gegen neu**:

**Werkzeug.** Ein Skript lädt in einem Prozess zwei Fassungen des **ganzen Pakets**: das Paket `analyze/` im Stand des Commits, der P2 abschließt, und das Paket aus dem Arbeitsbaum. Die alte Fassung wird **mit `dulwich`** aus diesem Commit gelesen (harte Regel »No shelling out to `git`«, Terra, zweite Runde, Hoch 2), in ein temporäres Verzeichnis geschrieben und dort unter einem eigenen Paketnamen importiert (etwa `analyze_before_p3`). Das ganze Paket, nicht nur `undo.py`: Nach P2 importiert `undo.py` relativ aus `.model` und `.matching`, und einzeln geladen fände es diese nicht – oder, mit den Modulen aus dem Arbeitsbaum daneben, einen gemischten Stand (Terra, zweite Runde, Mittel 1). Die Commit-ID steht als Konstante im Werkzeug; sie wird im ersten Commit von P3 eingetragen, sobald der Abschluss-Commit von P2 existiert. Beide Fassungen bekommen dieselben Eingaben, verglichen werden `plan_undo` und `restore.apply_undo` über den jeweiligen Plan. **Es werden keine Ergebnisse gespeichert** – nichts aus echten Dashboards landet im öffentlichen Repo, und es gibt keine Referenzdateien, die veralten.

**Strenger Vergleich** über eine kanonische Form, weil die Klassen beider Fassungen verschiedene Typen sind: `True` ist nicht `1`, Reihenfolge zählt, Datenklassen mit Feldnamen, `_ABSENT` über seinen Namen, eine Ausnahme über Typ und Text, `UndoPlan` einschließlich `parked`.

**Eingaben, in drei Gruppen:**

1. **Vorrangfälle, konstruiert.** Für jedes Paar von Stufen der Prüfreihenfolge, die für dieselbe Eingabe beide verweigern können, mindestens ein kleines Dashboard, bei dem beide es tun. Der erste Fall steht wörtlich fest (Astra, ausgeführt und am heutigen Code nachgerechnet): `before` = eine Ansicht `{path: a, type: masonry, cards: []}`, `after` = `current` = zwei Ansichten `{path: a, type: sections, cards: []}`. V2 und V4 treffen beide zu, heute gewinnt `_DUPLICATE_PATH_REFUSAL`; eine Fassung, die V4 zuerst prüft, liefert `_VIEW_TYPE_REFUSAL` und erreicht trotzdem beide Texte, jeden in seinem Einzelfall. Paare, die sich nicht gemeinsam herstellen lassen, benennt der Plan einzeln mit Grund.
2. **Erzeugte Historien.** Ein Generator mit festem Startwert baut Tripel (`before`, `after`, `current`) durch zufällige Änderungen – Karten, Sections, Einstellungen, Badges, Ansichten, identische Kopien, Pfadkollisionen, Typkonvertierungen – aus den synthetischen Fällen der Tests und, wenn vorhanden, den echten Dashboards aus `.real-storage`. Einige tausend Tripel über mehrere Startwerte. Darunter gezielt Fälle, in denen Schritte verschiedener Arten denselben Index tragen (Terra, Mittel 4).
3. **Die Prüfbank im Container,** optional vor dem letzten Commit von P3: aufeinanderfolgende Commits eines Dashboards als (`i`, `i+1`, `i+k`), nach dem Muster von `run_day_marks.py`.

**Reichweite messen.** Sobald die Stufen als eigene Funktionen existieren, ruft das Werkzeug jede einzeln auf und notiert, welche für eine Eingabe verweigern würden. Abnahme: Jeder Verweigerungstext wird erreicht, und jedes gemeinsam herstellbare Paar kommt in mindestens einer Eingabe vor. Das Orakel bleibt die alte Fassung.

**Laufzeit.** Das Werkzeug misst nebenbei die Summe der Laufzeiten von `plan_undo` alt und neu; neu höchstens 110 % von alt.

**Nachprüfbar auch danach** (Terra, zweite Runde, Mittel 2). Startwerte, Mindestanzahl der Tripel und die Pflichtfälle stehen fest im Werkzeug, nicht in einer Kommandozeile. Jeder Lauf gibt eine **Zusammenfassung ohne Dashboard-Inhalte** aus: Startwerte, Zahl der Tripel je Gruppe, Zahl der Abweichungen, die Liste der erreichten Verweigerungstexte als Vorlagen (mit `{…}` für eingesetzte Teile), die Matrix der abgedeckten Vorrang-Paare, die Laufzeiten. Die Zusammenfassung des letzten Laufs vor dem Entfernen kommt als Nachtrag in den Plan von P – das Journal ist dafür der Ort, und es enthält dann nur Zahlen und Namen, keine Karte eines echten Dashboards.

**Lebensdauer.** Das Werkzeug liegt während P3 unter `tests/equivalence/` (nicht von pytest eingesammelt). Der letzte Commit von P entfernt es und tut sonst nichts; es läuft ein letztes Mal unmittelbar davor. Die Git-Historie behält es, die Zusammenfassung steht im Journal.

## Fehler- und Randfälle

| Fall | Umgang |
|---|---|
| Ein HACS-Update lässt die alte `analyze.py` neben `analyze/` liegen | Das Paket hat Vorrang (Ausgangslage). Im Plan einmal im Container nachgeprüft |
| Home Assistant lädt ein Unterpaket einer Custom Integration | Nach P2 mit `run_checks.py` im Container nachgeprüft, nicht angenommen |
| `hassfest` oder die HACS-Validierung stören sich an `pyproject.toml` | Nach P1 prüft die CI beide (`validate.yml`); schlagen sie an, liegt die Konfiguration stattdessen in `ruff.toml` und `.importlinter` |
| Eine neue `ruff`-Version zählt Komplexität anders | Version in der CI gepinnt; ein Update ist ein eigener Commit, der die Baseline bei Bedarf im selben Zug neu misst |
| Eine Funktion wird umbenannt oder verschoben, die in der Baseline steht | Die Sperrklinke meldet einen verschwundenen und einen neuen Eintrag; der Commit trägt die Baseline mit um, der Wert darf dabei nicht steigen. P2 tut das für die fünf Einträge aus `analyze.py` |
| Der Umbau findet einen echten Fehler in `plan_undo` | Nicht im Umbau beheben. Issue schreiben; der Vergleich alt gegen neu muss für diesen Fall gleich bleiben |

## Test-Plan

- **Nach jedem Commit:** `python3 -m pytest tests/ -v` mit 0 failed, `tools/complexity_ratchet.py` und `lint-imports` grün.
- **Neu:** der Schnittstellentest für `analyze.__all__` (Abschnitt 2), und die Sperrklinke selbst mit je einem Fall für ihre drei Fehlerarten (neue Funktion über der Grenze, gewachsener Ausreißer, gesunkener Wert ohne gesenkte Baseline), an einer kleinen Attrappe, nicht am echten Code.
- **Während P3 zusätzlich:** das Werkzeug aus Abschnitt 4 mit 0 Abweichungen, bis auf den letzten Commit, der es entfernt.
- **Nach P2 und am Ende:** `tests/integration/run_checks.py` gegen den Testcontainer.
- **Kein bestehender Test wird geändert.** Muss einer geändert werden, weil er einen privaten Namen erwartet, den es nicht mehr gibt, ist das ein Export-Fehler.

## Erfolgskriterien

1. Die Sperrklinke über `ruff` (Komplexität) und `import-linter` (HA-Freiheit, Schichten) laufen in der CI und sind grün; im Code steht kein `noqa` für die drei Komplexitätsregeln.
2. `plan_undo` steht nicht mehr in der Baseline, kein neuer Planer und keine Vorprüfung steht darin. Die Baseline sinkt von 23 Einträgen für 15 Funktionen auf 20 für 14; kein verbliebener Wert ist gestiegen.
3. Kein Modul in `analyze/` ist länger als 900 Zeilen (physisch, mit Kopf, Imports und Leerzeilen).
4. Prüf- und Ausgabereihenfolge stehen als zwei Tupel mit Begründung in `undo.py`.
5. Vergleich alt gegen neu: 0 Abweichungen, jeder Verweigerungstext erreicht, jedes gemeinsam herstellbare Vorrang-Paar abgedeckt, Laufzeit höchstens 110 %.
6. `pytest` 0 failed; `run_checks.py` grün; kein bestehender Test geändert.

## Dokumentation

- Haupt-Spec: Buchstabe P im Abschnitt »Reihenfolge der Vorhaben«; die Stellen mit Gegenwartsbezug (Modultabelle Zeile 55, Ablaufdiagramme Zeilen 99 und 105) auf `analyze/` umstellen. Historische Stellen – Entscheidung 11, die Nachträge zu E, F, J, K – bleiben, wie sie sind.
- `CLAUDE.md`: in »Hard rules« `analyze/` statt `analyze.py`, mit Verweis auf den `import-linter`-Vertrag, der die Regel jetzt prüft; in »Tests« die beiden neuen Befehle.
- `docs/superpowers/status.md`: Zeile P; Modul-Übersicht mit dem Paket.
- `docs/development.md` (Diagramm, Modulliste, Befehle) und `docs/how-it-works.md`, wo sie `analyze.py` nennen.

## Warum diese Fassung schlanker ist

Die erste Fassung war durch zwei Review-Runden gewachsen: neun Module plus ein Unterpaket mit neun Dateien, ein selbstgebauter AST-Schichtentest, ein selbstgebauter HA-Freiheits-Test, ein Äquivalenzwerkzeug für jeden Commit mit 20 000 Tripeln. Jede Ergänzung schloss eine echte Lücke, aber das Ganze war einem Umbau, der am Ende nichts ändern soll, nicht mehr angemessen – und in Python unüblich: Die Einheit ist dort das Modul, und viele kleine Dateien je Aufgabe gelten eher als Java-Stil (»Flat is better than nested«). Der Nutzer fragte nach, was ein erfahrener Python-Entwickler tun würde; die Antwort ist diese Fassung:

- **Fünf Module statt 18 Dateien.** Die kreisfreie Zuordnung aus der ersten Fassung bleibt gültig; benachbarte Schichten sind zusammengelegt (0–2 zu `model`, 3–5 zu `matching`), was keine Kante umdreht.
- **Standardwerkzeuge statt eigener Tests.** `ruff` und `import-linter` sind in Python die üblichen Werkzeuge für genau diese Fragen, laufen in der CI und prüfen dauerhaft – die eigenen Tests hätten nur den Umbau abgesichert, nicht die Zeit danach. `import-linter` findet zudem transitive Importe, was der eigene AST-Test nicht konnte.
- **Die Wache zuerst.** Sie ist der Teil, der den Anlass (»wird mit jeder Änderung länger«) dauerhaft behebt.
- **Der Vergleich alt gegen neu nur für P3,** wo Logik umgestellt wird. Für reines Verschieben genügen die vorhandenen Tests.

## Entscheidungen (vom Assistenten vorgeschlagen, vom Nutzer am 2026-09-27 freigegeben)

1. **Erst Spec, dann Plan.** P3 legt fest, wie Verweigerungen über Planergrenzen hinweg Vorrang haben – Domänenwissen (welchen Grund die Nutzer:innen sehen), das heute in der Zeilenreihenfolge einer Funktion steckt.
2. **Zwei getrennte Reihenfolgen statt einer.** Vereinheitlichen änderte entweder, welche Verweigerung gewinnt, oder die Reihenfolge der Schritte – beides ist beobachtbar.
3. **Planer als Funktionen über einem Kontextobjekt, keine Klassen.** Das Modul ist durchgehend funktional geschrieben, die Planer haben keinen eigenen Zustand. So hält es auch das Standardwerk zu DDD in Python (Percival/Gregory, »Architecture Patterns with Python«): Dataclasses und Funktionen, keine Hierarchien.
4. **Karten und Badges bleiben getrennt.** Umzug und Logikänderung im selben Vorhaben würden die Abnahme schwächen: Eine Abweichung wäre nicht mehr eindeutig ein Umzugsfehler.
5. **Fünf Module, `undo.py` als eine Datei.** Siehe oben. Die Zeilenspalte in Abschnitt 2 zählt nur die Spannen der Definitionen; mit Kopf, Imports und den zwei Leerzeilen zwischen Definitionen ist `matching.py` schon nach P2 rund 680 Zeilen lang, und `undo.py` wächst in P3 durch Kontext, Vorprüfungen, Tupel und die herausgehobenen Hilfsfunktionen auf geschätzt 800–880 (Gemini, zweite Runde, Hoch 3). Die Grenze liegt deshalb bei 900 physischen Zeilen, nicht bei den 650 der ersten Überlegung. In Python ist das eine übliche Modulgröße; die eigentliche Wache ist die Komplexität je Funktion, nicht die Dateilänge. Überschreitet `undo.py` die Grenze, meldet der Plan das, statt die Datei stillschweigend weiter zu teilen – der natürliche nächste Schritt wäre dann ein Modul je Planer.
6. **`ruff` nur mit Komplexitätsregeln.** Stil- und Formatregeln hätten Änderungen in fast jeder Datei zur Folge – Stiländerungen gibt es in diesem Projekt nur auf ausdrücklichen Wunsch.
7. **Standardgrenzen, bestehende Ausreißer in einer Baseline mit Sperrklinke** (Terra, zweite Runde, Hoch 1). Die erste Überlegung waren `noqa`-Kommentare mit Issue-Verweis; Terra zeigte, dass ein ausgenommener Ausreißer dahinter unbegrenzt weiter wachsen kann und ein neues `noqa` genauso durch die CI kommt. Die Baseline mit `--ignore-noqa` schließt beides und fasst nebenbei keine der Altdateien an. Verworfen: die Grenzen so hoch zu setzen, dass heute nichts anschlägt – bei einer Komplexität von 54 als Maßstab wäre die Wache wirkungslos. Verworfen auch, ganze Dateien auszunehmen: Dann wüchse gerade `store.py` unbewacht weiter.
8. **Konfiguration in `pyproject.toml`,** der üblichen zentralen Stelle, ohne `[project]`-Tabelle. Fallback auf `ruff.toml` und `.importlinter`, falls `hassfest` oder HACS sich daran stören.
9. **Werkzeugversionen gepinnt,** wie `dulwich` in derselben CI.
10. **Vergleich alt gegen neu im selben Prozess, keine gespeicherten Referenzen** – ein klassischer Golden Master brächte private Dashboard-Inhalte ins öffentliche Repo.
11. **Vorrangfälle konstruiert und gemessen** (Terra, Kritisch 1; Astra). Zwei unabhängige Reviews zeigten dieselbe Lücke: »jeder Verweigerungstext erreicht« belegt nicht, welcher von zwei gleichzeitig zutreffenden gewinnt. Gemessen wird erst, wenn die Stufen einzeln aufrufbar sind; in der heutigen Funktion verdeckt die erste Verweigerung jede weitere. Nicht übernommen: zusätzlich zu prüfen, dass spätere Berechnungen nach einer Verweigerung ausbleiben – die Stufen sind reine Funktionen, das ist von außen nicht beobachtbar und fällt unter die Laufzeitgrenze.
12. **`__init__` exportiert die 26 heute erreichten Namen, nicht alle 95** – das hielte private Helfer dauerhaft an einer öffentlichen Stelle fest.
13. **Buchstabe P.** Mehrere Commits, ein Plan und externe Reviews – dieselben Gründe wie bei L bis O.
14. **Klassenmetadaten liegen außerhalb der Verhaltensneutralität** (Astra, zweite Runde). Astra zeigte ausgeführt, dass sich `__module__`, der `repr` der Klasse und die `pickle`-Bytes von `UndoPlan` durch den Umzug ändern, und bot zwei Wege an: einen Test `analyze.UndoPlan.__module__ == "analyze"` oder eine ausdrückliche Ausnahme. Gewählt: die Ausnahme. Der Test hielte einen Wert fest, der nur in pytest gilt – in Home Assistant lautet er schon heute anders – und ließe sich nach dem Umzug nur durch eine künstliche Zuweisung von `__module__` grün halten, die genau die Ehrlichkeit untergräbt, um die es geht. Nichts im Projekt liest die Metadaten (Abschnitt »Kontext & Ziel«). Falls je etwas persistiert wird, das Klassen aus `analyze` enthält, ist diese Entscheidung neu zu prüfen.

### Abgleich mit den Reviews der ersten Fassung

*Erste Fassung (Terra, Astra, Gemini):* Übernommen und in dieser Fassung enthalten: Terra Kritisch 1 und 2, Hoch 3 (teilweise), Hoch 4 (als Vergleich über `UndoPlan` samt `parked`; die Methoden von `Matching` fallen weg, weil nur noch `undo.py` verglichen wird und `Matching` in P3 nicht umgebaut wird), Mittel 1–6, Niedrig 1; Astra (Pflichtfall V2 gegen V4); Gemini Hoch 1 (identisch mit Terra Kritisch 2), Mittel 2 (Zählung), Niedrig 1 (Commit-Daten).

Zurückgewiesen aus der ersten Fassung: Terra Hoch 1 (»`same_config` ruft `fingerprint` aus `matching.py`«) – `fingerprint` stand schon in der ersten Fassung auf derselben Schicht wie `same_config`. Aus Terra Hoch 3 der Teil »`SettingChange` fehlt« – es stand in der Liste.

*Terra, zweite Fassung (2026-09-27):* kein kritischer Befund. Übernommen: Hoch 1 (Baseline mit Sperrklinke statt `noqa`, Entscheidung 7), Hoch 2 (`dulwich` statt `git show` im Werkzeug – die harte Regel zielt auf die Laufzeit der Integration, gilt aber wörtlich, und `dulwich` kostet hier nichts), Mittel 1 (ganzes Paket aus dem Abschluss-Commit von P2 laden), Mittel 2 (feste Startwerte, Zusammenfassung ohne Inhalte ins Journal), Mittel 3 (Schnittstellentest). Niedrig 1 übernommen als Klarstellung, nicht als Vorschlag: Die 26 Namen sind die erklärte Schnittstelle; Kompatibilitäts-Re-Exporte aller 95 Namen werden **nicht** angelegt, weil `analyze` kein Bibliotheksmodul ist und niemand außerhalb des Repositorys es importiert.

*Astra, zweite Fassung (2026-09-27):* »trifft zu« – `__module__`, Klassen-`repr` und `pickle`-Bytes ändern sich durch den Umzug. Bestätigt, aber als ausdrückliche Ausnahme behandelt statt mit dem vorgeschlagenen Test (Entscheidung 14). Die im Prompt genannten weiteren Kandidaten – doppelt geladene Module mit zwei Identitäten von `_ABSENT`, Reihenfolge der Konstantenberechnung beim Import – hat Astra nicht als zutreffend gemeldet.

*Gemini, zweite Fassung (2026-09-27):* Übernommen: Hoch 1 (verschachtelte Hilfsfunktionen zählen in `C901` zur äußeren Funktion – selbst nachgemessen, `cards` 17 und `badges` 15; die sieben inneren Funktionen gehen auf Modulebene, Abschnitt 3), Hoch 2 und Niedrig 6 (`containers` im Schichtenvertrag, TOML-Struktur – jetzt als vollständiges Beispiel in Abschnitt 2), Hoch 3 (Zeilengrenze 900 statt 650, Entscheidung 5), Mittel 5 (Q1 bekommt die gesammelten Schritte, nicht den Kontext). Hoch 4 (`git show`, relative Imports) war schon nach Terras zweiter Runde behoben; Gemini hatte offenbar den Stand davor gelesen. Bestätigt, ohne Änderung: `pyproject.toml` stört weder `hassfest` (im offiziellen Container nachgeprüft) noch die HACS-Validierung noch die Installation über HACS, die nur `custom_components/<domain>/` kopiert; `import-linter` liest `[tool.importlinter]` aus `pyproject.toml`; die 15 Ausreißer und ihre Werte.

Zurückgewiesen: Niedrig 7 (alle öffentlich wirkenden Typen wie `Slot`, `Matching`, `fingerprint` in `__all__` aufnehmen). `__all__` beschreibt, was tatsächlich über `analyze` genutzt wird, nicht, was nach einer Konvention öffentlich aussieht; die übrigen Namen bleiben über ihr Modul erreichbar. Ein Name kommt dazu, sobald ein Aufrufer ihn braucht – vorher wäre es eine Schnittstelle ohne Nutzer (Entscheidung 12, Terra zweite Runde Niedrig 1).

Aus der ersten Fassung durch die Verschlankung gegenstandslos: Terra Hoch 2 (erste Runde) und Gemini Mittel 1 (Grenzen eines Laufzeit-Importtests – ersetzt durch `import-linter`); Gemini Hoch 2 (`_section_title` ruft `_shorten` aus einer höheren Schicht – beide liegen jetzt in `model.py`; schon in der Terra-Überarbeitung war `_section_title` nach `describe` gewandert).
