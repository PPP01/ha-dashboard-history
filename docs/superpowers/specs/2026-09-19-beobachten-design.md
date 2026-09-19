# Design: Beobachten – Kennzahlen, Sensoren und ein Bericht

**Datum:** 2026-09-19
**Status:** Entwurf zum Review
**Vorhaben:** B aus dem Abschnitt »Reihenfolge der Vorhaben« der Haupt-Spec
**Integration:** `dashboard_history`
**Bindend bei Widerspruch:** die Haupt-Spec (`2026-08-30-dashboard-history-design.md`)

## Kontext & Ziel

Die Haupt-Spec vergibt an dieses Vorhaben einen Satz: »Ein Options-Flow und die **erste Entity-Plattform** dieser Integration: Repository-Größe, Zahl der erfassten Stände, Zahl der Dashboards und – der wichtigste – der Zeitpunkt der neuesten Erfassung. Bleibt der stehen, hat das Erfassen stillschweigend aufgehört; dieses Projekt hat dreimal erlebt, dass der Code richtiger war als sein eigener Bericht, und ein Wachhund dagegen ist mehr wert als eine Größenanzeige.«

Dazu kommt seit dem 2026-09-19 ein zweiter Anlass, der den Zuschnitt verändert: Die Veröffentlichung steht bevor, und die ersten Tester sollen gebeten werden, **Messwerte zurückzugeben**. Eine Anzeige in der eigenen Anlage ist dafür wertlos – es braucht eine Datei, die jemand an ein Issue hängen kann, ohne dabei die Struktur seines Zuhauses zu veröffentlichen.

Beide Anlässe hängen an derselben Rechnung, und deshalb bleiben sie in einer Spec: Die Sensoren zeigen, was der Bericht schreibt. Zwei getrennte Wege zu denselben Zahlen wären zwei Wege, die sich widersprechen können.

**Warum jetzt und nicht später:** Die Haupt-Spec macht Vorhaben C (Aufräumen) ausdrücklich von den Messwerten aus B abhängig – »B könnte nach ein paar Wochen zeigen, dass C's Löschteil nie gebraucht wird. Eine unwiderrufliche Operation zu entwerfen, bevor irgendjemand Messwerte hat, wäre in diesem Projekt der falsche Weg herum.« Ohne B gibt es diese Wochen nie, weil niemand außerhalb der Entwicklungsanlage misst.

### Verifizierte Ausgangslage (2026-09-19, am Quelltext nachgelesen)

| Feststellung | Beleg |
|---|---|
| Der Options-Flow aus B **existiert bereits** | `config_flow.py`, ein Schalter für Tagesversionen. Von B fehlt nur die Entity-Plattform. |
| Es gibt **keine** Entity-Plattform | `__init__.py` ruft `async_forward_entry_setups` an keiner Stelle |
| Es gibt **keine** Laufzeitmessung im Code | kein `perf_counter`, kein `monotonic` in `custom_components/dashboard_history/` |
| Alle bisherigen Perfzahlen stammen aus Handmessungen | Haupt-Spec, `FAQ.md`, `status.md` – jeweils im Container erhoben |
| `survey()` ist nach HEAD gecacht | `store.py:346-352`, `store.py:2003-2005` |
| Der Revisionsindex ist ebenfalls nach HEAD gecacht | `store.py:353-356` |
| Der Repo-Ordner enthält **mehr als `.git`** | `HistoryStore.path` ist ein Arbeitsverzeichnis mit `<key>.yaml` und `meta/<key>.yaml` |
| Ein Aktualisierungs-Listener hängt **nicht** am Config-Eintrag | `config_flow.py:44-47`, ausdrücklich begründet |
| `CSafeLoader` entscheidet über Faktor 8–9 beim Laden | `.claude/lessons.md`, gemessen 2026-09-11: 501 ms gegen 54,8 ms |
| Eine Anlage kann ganz ohne Packs laufen | Haupt-Spec, 2026-09-02: 42 Commits, 122 lose Objekte, kein einziger Pack |

## Nicht-Ziele (YAGNI)

- **Keine Laufzeitmessung.** Nicht wie lange ein Commit braucht, nicht wie lange das Panel auf eine Antwort wartet, nicht wie lange ein `forget` läuft. Das verlangte Instrumentierung mitten im Kern – in `store.py` und `capture.py` –, die es bewusst bis heute nicht gibt, und beantwortet eine Frage, die niemand gestellt hat. Gefragt ist »wie groß wird das«, nicht »wie schnell ist das«. Wenn die Größe-Daten der Tester später eine Laufzeitfrage aufwerfen, ist das ein eigenes Vorhaben mit eigener Begründung.
- **Keine Aufbewahrungsregel, kein Verdichten.** Das ist Vorhaben C, und es wartet laut Haupt-Spec genau auf die Zahlen, die hier entstehen. B misst, C entscheidet.
- **Kein `binary_sensor` »Erfassung ausgefallen«.** Die Haupt-Spec nennt den Zeitstempel einen Wachhund, aber ein Schwellwert dafür wäre geraten: Wer drei Wochen lang nichts an seinen Dashboards ändert, ist normal, nicht kaputt. Der stehende Zeitstempel ist das Signal; wer eine Meldung daraus will, baut sich in zwei Zeilen eine Automation.
- **Keine Arbeit an `panel.js`.** Die Kennzahlen erscheinen nicht im eigenen Panel. Die Integrationsseite und die Entwicklerwerkzeuge reichen für das, was hier gebraucht wird, und `panel.js` ist die teuerste Datei des Projekts.
- **Keine neue Option.** Der Bericht ist immer anonym; es gibt keinen Schalter, der Klarnamen einschaltet. Eine Option, deren richtige Stellung »aus« ist und die man erklären muss, ist keine Wahl, sondern eine Falle.
- **Kein eigener Dienst und kein eigener Knopf für den Bericht.** Home Assistant hat dafür den Diagnose-Download.

## Architektur

### Bausteine

```
store.py     measure() -> Measurement        neu, HA-frei
                  |
report.py    report(measurement, secret, umgebung) -> dict    neu, HA-frei
                  |
        +---------+---------+
        |                   |
sensor.py            diagnostics.py
5 Entitäten          async_get_config_entry_diagnostics
über einen           (sammelt HA-Fakten ein, ruft report())
Coordinator
```

Zwei neue HA-freie Module und zwei dünne Schichten darüber. Die Regel aus `CLAUDE.md` – »`yaml_io.py`, `analyze.py`, `restore.py`, `versions.py`, `store.py` und `keys.py` bleiben frei von Home Assistant« – wird um `report.py` erweitert.

**Warum `measure()` in `store.py` liegt und nicht im Sensor:** Weil `store.py` HA-frei ist, wird die ganze Rechnerei damit in gewöhnlichem `pytest` prüfbar, ohne laufende Anlage. Läge sie im Sensor, wäre sie nur noch über `tests/integration/run_checks.py` erreichbar – und das ist der Weg, den dieses Projekt bewusst für das reserviert, was strukturell nicht anders geht.

**Warum `report.py` ein eigenes Modul ist und nicht Teil von `diagnostics.py`:** Der wichtigste Test dieses Vorhabens prüft, dass in der fertigen Datei kein Dashboard-Name, kein `url_path`, kein Titel und kein Pfad steht. Dieser Test muss in `pytest` laufen, sonst läuft er selten. Liegt der Aufbau in `diagnostics.py`, braucht er eine Anlage, und der eine Test, der diese Datei öffentlich teilbar hält, wäre der am seltensten ausgeführte im Projekt.

### Datenmodell

`Measurement`, ein eingefrorenes Dataclass neben `Survey` und `RevisionIndex`:

| Feld | Inhalt |
|---|---|
| `newest` | Zeitpunkt des jüngsten Commits, und welcher Schlüssel darin geschrieben wurde |
| `oldest` | Zeitpunkt des ältesten Commits |
| `revisions` | Zahl der Commits insgesamt |
| `live`, `gone` | Schlüssel der lebenden und der gelöschten Dashboards |
| `per_key` | je Schlüssel: Zahl der Stände, Bytes des jüngsten Stands, Zahl der Marken, erster und letzter Stand |
| `versions` | Zahl der Versionsmarken insgesamt |
| `bytes_git`, `bytes_worktree` | Plattenbedarf, getrennt |
| `loose_objects`, `packs` | Zahl der losen Objekte und der Packs |

`measure()` holt das in **einem** Durchgang: Verzeichnis-Walk, `survey()`, Revisionsindex, Marken. Dieselbe Funktion für beide Verbraucher sorgt dafür, dass Sensoren und Bericht dasselbe *bedeuten* – dass sie auch denselben *Stand* zeigen, folgt daraus noch nicht und wird in B10 geregelt.

## Schlüssel-Entscheidungen

### B1 – Fünf Sensoren, Detailzahlen als Attribute

| Entität | Zustand | Klassen | Attribute |
|---|---|---|---|
| `sensor.dashboard_history_last_capture` | Zeitstempel | `timestamp` | zuletzt geschriebenes Dashboard |
| `sensor.dashboard_history_size` | Bytes | `data_size`, `measurement` | `.git`, Arbeitskopie, lose Objekte, Packs |
| `sensor.dashboard_history_revisions` | Anzahl | `measurement` | meiste je Dashboard, Median, ältester Stand |
| `sensor.dashboard_history_dashboards` | Anzahl lebender | `measurement` | gelöschte, je gesehene gesamt, **ID-Zuordnung** (siehe B8) |
| `sensor.dashboard_history_versions` | Anzahl Marken | `measurement` | Tagesversionen an/aus |

Alle fünf tragen `entity_category: diagnostic` und hängen an einem Dienst-Gerät »Dashboard History«, damit sie auf der Integrationsseite beieinanderstehen – derselben Seite, auf der auch der Diagnose-Knopf sitzt.

**Warum Attribute und nicht mehr Entitäten:** Fünf Entitäten sind eine Geräteseite, die man liest; fünfzehn sind eine, die man überfliegt. Die Detailzahlen gehören zu ihrer Kennzahl und nicht neben sie.

**Warum `measurement` und nicht `total_increasing` bei den Ständen:** `forget` nimmt Stände weg. Ein Zähler, der laut Deklaration nur steigen kann, würde HA bei jedem `forget` einen Überlauf vortäuschen und die Langzeitstatistik verderben.

**Warum die Größe der wichtigste Sensor *nicht* ist:** Die Haupt-Spec gibt diesen Rang dem Zeitstempel, und das bleibt so. Die Größe wächst langsam und schadet niemandem; eine Erfassung, die aufgehört hat, merkt man erst, wenn man etwas zurückholen will.

### B2 – Die Größe misst den ganzen Ordner, und zwei Zahlen statt einer

`HistoryStore.path` zeigt auf `<config>/dashboard_history/`, und dort liegt neben `.git/` eine vollständige Arbeitskopie aller Dashboards als YAML. Bei 262 KiB für das größte Dashboard der Entwicklungsanlage ist das kein Rundungsfehler: Wer nur `.git` misst, unterschätzt den Plattenbedarf um genau einen kompletten Stand aller Dashboards.

**Gemessen werden zwei Größen, nicht eine:** die logische Summe der Dateilängen (`st_size`) und der tatsächlich belegte Speicher (`st_blocks * 512`). Der Unterschied ist kein Feinschliff. Am 2026-09-19 an der Prüfbank nachgemessen, getrennt nach Art der Datei:

| | n | logisch | belegt | Verschnitt |
|---|---|---|---|---|
| lose Objekte | 18 | 9.339 B | 73.728 B | **689,5 %** |
| Packs | 2 | 6.978.309 B | 6.983.680 B | 0,1 % |
| Arbeitskopie | 92 | 555.111 B | 897.024 B | 61,6 % |
| ganzes Repository | 112 | 9.182.768 B | 9.629.696 B | 4,9 % |

Ein loses git-Objekt ist ein paar hundert Bytes groß und belegt trotzdem einen ganzen 4-KiB-Block. Über das ganze Repository gemittelt verschwindet das hinter dem Pack – aber die Zahl, an der Vorhaben C entscheidet, ist gerade die der **losen** Objekte, und dort läge `st_size` um fast das Siebenfache daneben. Bei den 122 losen Objekten ohne Pack, die die Haupt-Spec am 2026-09-02 fand, wäre ein Bericht mit nur logischer Größe für seinen eigenen Zweck unbrauchbar gewesen.

**Die Aufteilung ist damit der eigentliche Messwert.** Die Haupt-Spec fand am 2026-09-02 122 lose Objekte und keinen einzigen Pack, davon rund ein Drittel reiner Blockverschnitt. Schlichtes Zusammenfassen brachte dort 24 %, Deltas 95 % – aber kubisch teuer. Die Zahl der losen Objekte bei echten Testern, zusammen mit dem, was sie tatsächlich belegen, ist die Grundlage für die Entscheidung, ob ein `repack` genügt oder ob es eine Aufbewahrungsregel braucht.

**Der Zustand des Sensors ist die belegte Summe**, weil das die Zahl ist, die dem Plattenplatz eines Nutzers entspricht. Logisch, `.git` gegen Arbeitskopie, lose Objekte und Packs stehen in den Attributen.

Beide Zahlen kommen aus **einem** `os.lstat` je Datei – ein Verzeichnis-Walk, nicht zwei, und der belegte Wert kostet nichts zusätzlich.

**Wo `st_blocks` fehlt** – Windows kennt es nicht –, bleibt der belegte Wert `null`, und der Sensor zeigt die logische Summe. Kein Schätzen, kein Hochrechnen auf eine geratene Blockgröße: Eine fehlende Zahl ist ehrlich, eine erfundene verdirbt genau die Auswertung, für die sie erfunden wurde.

### B3 – Ein Coordinator, zwei Auslöser, alles im Executor

Ein `DataUpdateCoordinator` ruft `measure()` über `hass.async_add_executor_job` – harte Regel: Der Verzeichnis-Walk gehört nicht in die Event-Loop. Er läuft auf zwei Wegen an:

1. **`EVENT_HISTORY_UPDATED`.** Der eingebaute Debouncer des Coordinators fängt dabei ab, was ein `restore_state` an Burst erzeugt, wenn viele Dashboards in einem Zug geschrieben werden.
2. **Ein Intervall als Rückfall.** Damit die Größe auch dann stimmt, wenn außerhalb der Integration etwas aufgeräumt hat, und damit die Werte einen Neustart überstehen, an dem nichts geschrieben wird.

**Das Intervall wurde nicht geraten, sondern gemessen** – und die Messung hat die Annahme dieses Abschnitts widerlegt. Was hier ursprünglich stand, ist als Lehrstück stehengeblieben:

> »Die Hälfte der Arbeit ist bereits gecacht – `survey()` und der Revisionsindex kosten bei unverändertem HEAD nichts. Unbekannt sind genau zwei Dinge: der Verzeichnis-Walk über hunderte lose Objekte und `list_versions()` über 782 Marken.«

Von diesen drei Aussagen hielt genau eine. Gemessen am 2026-09-19 auf der Prüfbank, ein **warmes** `measure()` von 154,6 ms, aufgeschlüsselt:

| Posten | Dauer | Anteil | war hier vorhergesagt |
|---|---|---|---|
| Blob-Längen, 68 Dashboards | 67,9 ms | 44 % | **nein** |
| `commit_times`, 122 Revisionen | 45,2 ms | 29 % | **nein** |
| `_versions_by_key` | 17,9 ms | 12 % | als »kostet nichts« |
| `_measure_disk` (der Walk) | 10,0 ms | 6 % | als eine der **zwei Unbekannten** |
| `survey()` (gecacht) | 0,9 ms | 0,6 % | richtig |

**Die beiden größten Posten waren hier gar nicht bedacht.** `_bytes_of_newest_content` muss den jüngsten Blob jedes Dashboards **entpacken**, um seine Länge zu erfahren – git kennt keine Größe ohne Inhalt –, und `commit_times` lädt für zwei Revisionen je Dashboard ein Commit-Objekt. Beides skaliert mit der **Zahl der Dashboards mal ihrer Größe**, nicht mit der Zahl der Commits. `list_versions()` wiederum wurde in der Umsetzung durch `_versions_by_key` ersetzt, das nur Ref-Namen liest, und kommt im Aufrufpfad überhaupt nicht mehr vor.

**Die Zahl bleibt dennoch 15 Minuten**, und das ist kein Durchwinken. 154,6 ms sind bei einem Intervall von 15 Minuten eine Auslastung von 0,017 %, und der Posten läuft im Executor. Falsch war die Begründung, nicht die Entscheidung – und die alte Begründung hätte den nächsten Leser in die Irre geführt, der eine Verkürzung des Intervalls erwägt: Er hätte am Verzeichnis-Walk optimiert und 6 % gefunden.

**Wer dieses Intervall künftig ändern will**, misst zuerst die Blob-Längen. Dort liegt die Hälfte, dort wächst es mit der Anlage, und dort läge auch die Abhilfe – eine Größe je Blob-ID zu merken, die inhaltsadressiert und damit unveränderlich ist. Nicht gebaut, weil 155 ms alle 15 Minuten keinen Anlass geben; benannt, damit niemand erst wieder messen muss.

### B4 – Der Start bleibt unangetastet, und das Entladen räumt auf

`async_forward_entry_setups(entry, ["sensor"])` kommt in `async_setup_entry`, aber auf den ersten Refresh wird **nicht gewartet** – `async_config_entry_first_refresh` wäre hier falsch. Der Grund steht schon im Code: Der Eröffnungsdurchgang wurde am 2026-09-07 aus demselben Grund in ein Hintergrundtask verschoben, weil er 6,2 s eines 7,3 s langen Setups kostete und Home Assistant »Waiting for integrations to complete setup« protokollierte (`__init__.py:60-73`).

Sensoren, die eine Minute lang `unknown` zeigen, sind harmlos. Ein Start, der auf einen Verzeichnis-Walk wartet, verletzt die harte Regel »Nichts blockiert den Start von Home Assistant«.

**Und die Gegenrichtung, die der erste Entwurf vergessen hatte.** Dies ist die erste Entity-Plattform dieser Integration, also gibt es bisher auch keinen Abbau dafür. `async_unload_entry` entfernt heute das Panel, nimmt die Laufzeitdaten aus `hass.data` und hält Marker und Rekorder an – eine Plattform entlädt es nicht, weil es nie eine gab. Ohne Ergänzung hängen nach einem Reload Entitäten und ein Ereignis-Listener am alten Store, und der Coordinator misst weiter gegen ein `HistoryStore`-Objekt, das niemand mehr benutzt.

Verbindlich für die Umsetzung:

1. `async_unload_entry` ruft `await hass.config_entries.async_unload_platforms(entry, ["sensor"])` und räumt **nur bei Erfolg** weiter auf. Die Reihenfolge ist nicht beliebig: Die Entitäten lesen aus `hass.data`, also müssen sie fort sein, bevor der Eintrag dort verschwindet.
2. Der Listener auf `EVENT_HISTORY_UPDATED` wird über `entry.async_on_unload(hass.bus.async_listen(...))` angemeldet, damit sein Abmelden nicht an einer zweiten Stelle von Hand nachgezogen werden muss.
3. Ein laufender Refresh darf das Entladen nicht aufhalten. Kommt er nach dem Entladen zurück, findet er einen Coordinator ohne Entitäten vor und läuft ins Leere – das ist in Ordnung, ein Fehler daraus wäre es nicht.

### B5 – Der Bericht ist eine HA-Diagnosedatei

`diagnostics.py` mit `async_get_config_entry_diagnostics`. Der Tester klickt auf der Integrationsseite »Diagnose herunterladen« und bekommt eine JSON-Datei, die er an ein GitHub-Issue hängen kann.

**Gegen einen eigenen Dienst mit Antwortdaten:** Der ließe sich nur in den Entwicklerwerkzeugen aufrufen, und der Tester müsste die Antwort aus einem Ausgabefeld herauskopieren. Eine Datei ist das, was an ein Issue gehängt wird.

**Gegen einen Knopf im Panel:** Panel-Arbeit plus WebSocket-Befehl plus Download-Logik für einen Weg, den Home Assistant fertig mitbringt und den Tester von anderen Integrationen kennen.

### B6 – Additiv gebaut, und ehrlich über den Umschlag, den HA darumlegt

Der Bericht besteht aus **zwei Teilen, von denen dieses Vorhaben nur einen schreibt.**

**Der Teil, den diese Integration schreibt** (`data` in der Datei): `report()` baut ihn Feld für Feld aus dem, was namentlich aufgeführt ist. Home Assistant bietet `async_redact_data` an, um Felder nachträglich zu schwärzen – das ist hier der falsche Weg herum. Wer alles einsammelt und dann streicht, veröffentlicht beim nächsten neuen Feld genau das, woran niemand gedacht hat; die Schwärzliste ist immer einen Schritt hinter dem Datenmodell. Was nicht aufgeführt ist, existiert in diesem Teil nicht. Insbesondere **nicht**: `url_path`, Dashboard-Titel, Icons, Ansichtsnamen, Kartentexte, Notizen, Versionstitel, Dateipfade, Entity-IDs, die Konfigurationsadresse.

**Der Teil, den Home Assistant beilegt** – und der ursprüngliche Entwurf dieser Spec hat ihn schlicht übersehen. Am 2026-09-19 im Quelltext von HA 2026.8.3 nachgelesen (`homeassistant/components/diagnostics/__init__.py`, `_async_get_json_file_response`): Die heruntergeladene Datei ist nicht das, was `async_get_config_entry_diagnostics` zurückgibt, sondern ein Umschlag darum:

| Block | Inhalt |
|---|---|
| `home_assistant` | Systeminformationen aus `helpers/system_info.py` – darunter `os_name`, `os_version`, `arch`, `python_version`, `installation_type`, `run_as_root` und **`timezone`** |
| `custom_components` | **jede installierte Custom-Integration** mit Version, Dokumentations-URL und Requirements |
| `integration_manifest` | das Manifest dieser Integration |
| `setup_times` | wie lange das Einrichten dieser Integration gedauert hat |
| `data` | was `report()` gebaut hat |

**Zwei Folgerungen daraus, und beide ändern etwas.**

*Erstens, das Versprechen wird kleiner und stimmt dafür.* Diese Spec kann nicht zusagen, dass in der Datei keine Zeitzone steht – sie steht darin, und `custom_components` ist ein Fingerabdruck der Anlage, der über Dashboard-Namen hinausgeht: Wer welche Integrationen installiert hat, sagt, welche Geräte und Dienste bei ihm stehen. Zugesagt wird deshalb genau das, was zugesagt werden kann: **Der `data`-Block verrät nichts über die Dashboards dieser Anlage.** Der Umschlag ist derselbe, den jeder Diagnose-Download jeder Integration trägt, und wer je einen HA-Fehlerbericht eingereicht hat, hat ihn schon einmal verschickt. Die README sagt das beim Bitten um Messwerte in einem Satz, statt es den Tester selbst herausfinden zu lassen.

*Zweitens, die Umgebungsfelder aus B9 werden fast alle überflüssig*, weil der Umschlag sie bereits trägt. Siehe dort.

**Der Test muss beide Teile treffen.** Ein `pytest`-Fall über `report()` allein kann den Umschlag nicht sehen – er existiert dort nicht. Deshalb wird in `run_checks.py` zusätzlich die **tatsächlich heruntergeladene Datei** geholt und darauf geprüft, dass kein Dashboard-Schlüssel der Anlage darin vorkommt.

### B7 – Dashboard-IDs aus einem Installations-Secret

Jede Zeile je Dashboard trägt eine ID statt eines Namens:

```json
"dashboards": [
  {"id": "a3f81c92", "revisions": 612, "bytes": 268341, "versions": 41,
   "first": "2026-03-02", "last": "2026-09-18"},
  {"id": "7b40e115", "revisions": 8, "bytes": 4012, "versions": 2,
   "first": "2026-03-02", "last": "2026-04-11", "gone": true}
]
```

Die ID ist `hmac(secret, schlüssel, sha256)`, die ersten 8 Hex-Zeichen.

**Warum ein Secret und kein blanker Hash:** Dashboard-Namen sind kurz und alltäglich. Ein Wörterbuch über `wohnzimmer`, `energie`, `garten`, `heizung` löst einen ungesalzenen Hash in Sekunden auf – ein solcher Hash würde eine Unumkehrbarkeit behaupten, die er nicht hat.

**Warum ein Secret und keine laufende Nummer:** Eine Nummer in der Reihenfolge des Auftauchens wäre ebenso unauflösbar, aber sie ist keine Kennung, über die man reden kann, und sie verschiebt sich, sobald ein `forget` ein Dashboard aus der Historie nimmt. Eine ID soll über Berichte hinweg dieselbe bleiben, damit ein zweiter Bericht desselben Testers zeigt, welches Dashboard gewachsen ist.

**Warum `hmac` und nicht `sha256(feld + secret)`:** Es gibt für genau diese Konstruktion ein fertiges Primitiv in der Standardbibliothek – eine Zeile, dieselbe Länge, und niemand muss später über Reihenfolge und Trennzeichen zwischen Feld und Secret nachdenken.

**Wo das Secret liegt: in `entry.data`**, also in `.storage/core.config_entries`, wo Home Assistant Zugangsdaten ohnehin hält. Erzeugt mit `secrets.token_hex(16)`, beim ersten Bedarf statt im Config-Flow – so braucht die bestehende Installation keine Migration und `VERSION = 1` bleibt, wie es ist. Das Schreiben über `async_update_entry` löst hier kein Neuladen aus, weil an diesem Eintrag bewusst kein Aktualisierungs-Listener hängt (`config_flow.py:44-47`).

**Wo es ausdrücklich nicht liegt: im Repo-Ordner.** Der erste Entwurf begründete das damit, eine dort abgelegte Datei lande beim nächsten `write_snapshot` im Commit. **Das ist nachgeprüft falsch:** `write_snapshot` staged ausdrückliche Pfade (`store.py:438`), `mark_deleted` ebenso (`store.py:486`), und ein zweiter Suchlauf über `stage`, `add(`, `do_commit` und `open_index` findet keine weitere Staging-Stelle im Store. Eine fremde Datei dort würde nicht mitcommittet.

Der Ort bleibt trotzdem falsch, aus zwei Gründen, die tragen: Der Repo-Ordner ist das eine Verzeichnis, in das die README ausdrücklich hineinzuschauen einlädt – ein Geheimnis gehört nicht dorthin, wo zum Nachsehen aufgefordert wird. Und er ist als Ganzes kopierbar: Wer sein Repository weitergibt, um an einem Fehler mitzuhelfen, gibt die Datei mit weiter, und von da an sind seine IDs auflösbar. `entry.data` ist der Ort, an dem Home Assistant Geheimnisse hält, und der Ort, den niemand versehentlich verschickt.

**Kollisionen:** Bei 50 Dashboards liegt die Wahrscheinlichkeit zweier gleicher 8-Hex-IDs bei rund 3 zu 10 Millionen. Tritt sie ein, wird die Länge auf 12 Zeichen erhöht – nicht vorab auf Verdacht.

**Zwei Grenzen, benannt statt verschwiegen:**

- **IDs sind je Anlage eigen.** Dasselbe Dashboard hat bei zwei Testern zwei IDs. Das ist der Zweck, heißt aber: Berichte verschiedener Leute lassen sich nicht übereinanderlegen.
- **Ein Neuaufsetzen der Integration erzeugt neue IDs.** Wer sie entfernt und neu hinzufügt, bekommt ein neues Secret. Die Historie im Repo überlebt das, die IDs nicht. Stabil ist »solange installiert«, nicht »für immer«.

### B8 – Nachgeschlagen wird über ein Sensor-Attribut

Damit ein Gespräch über »Dashboard `a3f81c92`« möglich ist, muss der Tester seine eigene ID auflösen können. Die Zuordnung ID → Dashboard hängt als Attribut am Sensor »Dashboards« – für **jedes je gesehene** Dashboard, auch die gelöschten, denn auch die haben eine Zeile im Bericht und gerade über die wird man reden.

Damit bleibt sie vollständig lokal: Sensor-Attribute stehen in *Entwicklerwerkzeuge → Zustände* und wandern in keine Diagnosedatei. Es braucht keinen neuen Dienst und keine Panel-Arbeit.

**Die Alternative und warum sie draußen bleibt:** Die ID neben jedem Dashboard im Panel anzuzeigen wäre bequemer und teurer – Arbeit an `panel.js`, der größten Datei des Projekts, für einen Weg, den man je Tester einmal geht. Wenn sich das Nachschlagen in der Praxis als zu umständlich erweist, ist das ein eigenes, kleines Vorhaben.

### B9 – Zwei Umgebungsfelder, und nur zwei

Der ursprüngliche Entwurf ließ den Bericht Integrations-Version, HA-Version, Installationsart, Python-Version und Architektur melden. Das ist doppelt: Der Umschlag aus B6 trägt all das bereits, teils genauer (`installation_type` unterscheidet OS, Container, Core, Supervised und »Unsupported Third Party Container«, was von Hand niemand so sauber hinbekäme). Doppelt gemeldete Werte sind Werte, die sich widersprechen können.

Übrig bleiben zwei Felder, die Home Assistant nicht liefert und ohne die **keine** andere Zahl lesbar ist:

- **Ob `yaml.CSafeLoader` vorhanden ist.** `.claude/lessons.md` hält fest, gemessen am 2026-09-11: 501 ms rein Python gegen 54,8 ms über `CSafeLoader`, Faktor 8–9 an einem 262 KiB großen Dashboard. Ein Tester ohne `libyaml` meldet Zahlen aus einer anderen Welt, und ohne dieses Feld rätselt man daran herum.
- **Die tatsächlich geladene `dulwich`-Version.** Das Manifest im Umschlag nennt nur die *geforderte* (`dulwich==1.2.14`); was im Prozess wirklich liegt, kann davon abweichen, und an ihr hängt die ganze Pack- und Delta-Rechnerei, auf der Vorhaben C aufbaut.

### B10 – Der Bericht misst neu, und die Sensoren erben denselben Stand

Dieselbe Messfunktion allein macht noch keine gemeinsamen Zahlen. Misst der Download eigenständig, zeigen die Sensoren daneben womöglich den vorherigen Stand; nimmt er stumm den Coordinator-Cache, kann die Datei beliebig alt sein, ohne dass jemand es sieht.

Verbindlich:

1. **Der Download stößt `await coordinator.async_refresh()` an** – die ungebremste Form, nicht `async_request_refresh`, dessen Debouncer hier nur Verzögerung wäre. Ein Diagnose-Download ist ein seltener, bewusster Griff; ein Verzeichnis-Walk dafür ist bezahlbar.
2. **Danach liest er `coordinator.data`** – dasselbe Objekt, aus dem im selben Moment die Entitäten geschrieben werden. Damit zeigen die Sensoren nach dem Download genau das, was in der Datei steht, und das ist die einzige Reihenfolge, in der die Zusage »beide zeigen dasselbe« überhaupt stimmt.
3. **`measured_at` steht in der Datei**, als UTC-Zeitstempel der Messung, aus der sie gebaut wurde. Ohne dieses Feld ist jede Aussage über die Aktualität eine Behauptung.
4. **Scheitert der Refresh**, wird der letzte erfolgreiche Stand geschrieben und die Datei trägt `"stale": true` – mit dem `measured_at`, das zu diesem Stand gehört, nicht mit der Uhrzeit des Downloads. Ein Bericht mit erkennbar altem Messstand ist brauchbar; einer, der Alter verschweigt, ist schlimmer als keiner.
5. **Gab es noch nie eine erfolgreiche Messung** – Download unmittelbar nach dem Start, bevor der erste Refresh durch ist –, sind `totals` und `dashboards` leer, `measured_at` ist `null` und `stale` ist `true`. Die Datei entsteht trotzdem: Sie trägt dann immer noch den Umschlag und die zwei Umgebungsfelder, und die beantworten bei einem Tester, bei dem gar nichts läuft, oft schon die eigentliche Frage.

## Der Vertrag des Berichts

Der erste Entwurf verlangte im Testplan »alle vier Blöcke« und definierte sie nirgends. Hier stehen sie, vollständig, mit Typen und Einheiten – das ist der Gegenstand, gegen den geprüft wird.

Dies ist der `data`-Block; darum liegt der Umschlag aus B6.

```json
{
  "schema": 1,
  "measured_at": "2026-09-19T12:03:21+00:00",
  "stale": false,
  "environment": {
    "dulwich": "1.2.14",
    "yaml_c_loader": true
  },
  "settings": {
    "daily_versions": true
  },
  "totals": {
    "dashboards_live": 45,
    "dashboards_gone": 25,
    "dashboards_ever": 70,
    "revisions": 7407,
    "versions": 782,
    "oldest": "2026-03-02",
    "newest": "2026-09-18",
    "bytes_logical": 9182768,
    "bytes_allocated": 9629696,
    "bytes_git_logical": 8627657,
    "bytes_worktree_logical": 555111,
    "loose_objects": 18,
    "packs": 1
  },
  "dashboards": [
    {"id": "a3f81c92", "revisions": 612, "bytes": 268341, "versions": 41,
     "first": "2026-03-02", "last": "2026-09-18", "gone": false},
    {"id": "7b40e115", "revisions": 8, "bytes": 4012, "versions": 2,
     "first": "2026-03-02", "last": "2026-04-11", "gone": true}
  ]
}
```

**Regeln, die das Beispiel nicht von allein sagt:**

| Regel | |
|---|---|
| `schema` | Ganzzahl, steigt bei jeder Änderung an der Form. Berichte aus verschiedenen Fassungen landen im selben Issue-Verlauf und müssen unterscheidbar bleiben. |
| `measured_at` | UTC, ISO 8601, oder `null`, wenn nie erfolgreich gemessen wurde. Die einzige Uhrzeit im ganzen Bericht. |
| `stale` | `true`, wenn die Zahlen aus einer früheren Messung stammen (siehe B10). |
| alle `bytes_*` | Ganzzahlen, **Bytes**, nie KiB oder MB. Umrechnen darf die Auswertung. |
| `bytes_allocated` | `null` auf Plattformen ohne `st_blocks` (siehe B2). Alle anderen Zahlfelder sind nie `null`. |
| alle Datumsangaben | **tagesgenau**, `YYYY-MM-DD`, UTC. Auch `newest`, obwohl der Sensor lokal den vollen Zeitstempel führt: Eine Uhrzeit sagt über die Größe nichts und über die Gewohnheiten des Testers einiges. |
| `oldest`, `newest` | `null` bei leerer Historie. |
| `dashboards` | absteigend nach `revisions`; leere Liste bei leerer Historie. |
| `dashboards_ever` | `dashboards_live + dashboards_gone`, ausgeschrieben statt errechnet – damit eine Unstimmigkeit im Bericht sichtbar wird, statt sich wegzukürzen. |

**`bytes` bei einem gelöschten Dashboard – der Fall, den der erste Entwurf offenließ.** »Bytes des jüngsten Stands« ist dort sinnlos: Der jüngste Commit eines gelöschten Dashboards ist der **Löschcommit**, und der enthält gerade keinen YAML-Inhalt mehr. `bytes` meint deshalb überall dasselbe und wird so definiert: **die Länge des jüngsten Stands, der Inhalt hatte.** Für ein lebendes Dashboard ist das der Stand an HEAD, für ein gelöschtes der Stand unmittelbar vor seiner Löschung – also genau die Größe, die eine Wiederherstellung zurückbrächte.

`last` bleibt davon unberührt und meint weiterhin den jüngsten Commit, **der es berührt hat** – bei einem gelöschten Dashboard also den Tag der Löschung. Die beiden Felder beantworten verschiedene Fragen (»wie groß war es« gegen »wann ist zuletzt etwas passiert«), und sie an derselben Revision festzumachen würde eine davon falsch beantworten.

**Was nicht im Bericht steht und auch nicht hineingehört:** Namen jeder Art, Pfade, Ansichts- und Kartenzahlen, Notizen, Versionstitel. Die Zahl der Views wäre verlockend und ist eine Beschreibung der Wohnung.

## Fehler- und Randfälle

- **Ein Repository, das es noch nicht gibt.** Auf einer frischen Anlage läuft die Entity-Plattform los, bevor der Eröffnungsdurchgang etwas geschrieben hat. `measure()` gibt ein leeres `Measurement` zurück; die Sensoren stehen auf 0 beziehungsweise `unknown`, nicht auf »nicht verfügbar«. Null erfasste Stände ist eine Antwort, kein Fehler.
- **Ein laufendes `forget`.** Das schreibt bis zu 15 s lang die Historie um. `measure()` kann dabei auf einen Stand treffen, der gerade verschwindet. `survey()` behandelt genau diesen Fall bereits und schluckt ihn mit Begründung (`store.py:2040-2045`, »Seen by the walk, pruned before the read«). `measure()` tut dasselbe: eine Zahl, die eine Sekunde lang danebenliegt, ist besser als ein Sensor, der wirft.
- **Ein Verzeichnis-Walk, der auf eine verschwindende Datei trifft.** `garbage_collect` räumt lose Objekte weg, während gemessen wird. Ein `FileNotFoundError` je Eintrag wird übersprungen, nicht gemeldet.
- **`measure()` wirft.** Der Coordinator behält den letzten Wert und meldet die Entitäten als nicht verfügbar. Nichts davon darf die Erfassung oder den Start berühren – dieselbe harte Regel wie überall.
- **Ein Dashboard ohne lesbare Metadaten.** Fällt in `per_key` nicht aus, sondern trägt seine Zahlen ohne Namen. Für den Bericht macht es ohnehin keinen Unterschied, weil dort kein Name steht.

## Test-Plan

**In `pytest`, ohne laufende Anlage** – weil `measure()` und `report()` HA-frei sind:

- `measure()` gegen ein frisch angelegtes Repository: leer, und kein Werfen.
- `measure()` gegen eine gebaute Historie: Zahl der Stände, lebende und gelöschte Dashboards, erster und letzter Zeitpunkt.
- **Größe, beide Zahlen.** Logische Summe gegen bekannte Dateilängen; belegte Summe gegen `st_blocks`, und gegen eine Datei von einem Byte, deren belegter Wert ein ganzer Block sein muss. Lose Objekte und Packs vor und nach einem `repack`.
- **`bytes` bei einem gelöschten Dashboard.** Ein Dashboard mit Inhalt anlegen, ändern, löschen – `bytes` muss die Länge des Stands *vor* der Löschung sein, nicht 0 und nicht die des Löschcommits. Der Fall, den der erste Entwurf offenließ, und deshalb der Test, der ihn festnagelt.
- **Der Datenschutz-Test über `report()`.** Gegen eine Historie aus echten Dashboard-Schlüsseln, und der fertige `data`-Block wird rekursiv durchsucht: Taucht ein Schlüssel, ein Titel, ein Icon oder ein Pfad darin auf, ist der Test rot.
- **Der Vertrag.** Jedes Feld aus »Der Vertrag des Berichts« ist vorhanden und hat den festgelegten Typ; `dashboards_ever` stimmt mit der Summe der beiden anderen überein; alle Datumsfelder sind tagesgenau und enthalten kein `T`.
- Die leere Historie: `measured_at` `null`, `stale` `true`, `totals` und `dashboards` leer – und der Bericht entsteht trotzdem.
- IDs: gleicher Schlüssel und gleiches Secret ergeben dieselbe ID; gleiches Secret und anderer Schlüssel eine andere; anderes Secret eine andere für denselben Schlüssel.

**In `tests/integration/run_checks.py`, gegen eine laufende Anlage** – weil es strukturell nicht anders geht:

- Die fünf Entitäten entstehen, tragen `diagnostic` und hängen am selben Gerät.
- Der Zeitstempel rückt nach einer erfassten Änderung vor.
- **Der Datenschutz-Test an der heruntergeladenen Datei.** Die Datei wirklich über `/api/diagnostics/config_entry/<id>` holen und darin nach den Dashboard-Schlüsseln der Anlage suchen. Der `pytest`-Fall oben kann den Umschlag aus B6 nicht sehen – er existiert dort nicht –, und der Umschlag ist genau das, was der erste Entwurf übersehen hat. Ein Test, der nur das prüft, was man selbst gebaut hat, hätte diesen Fehler nicht gefunden.
- **Sensoren und Bericht zeigen denselben Stand** (B10): Nach dem Download stimmen die Entitätszustände mit den Zahlen in der Datei überein.
- **Ein Reload.** Den Config-Eintrag neu laden und danach prüfen: weiterhin genau fünf Entitäten, keine verwaisten, und der Zeitstempel rückt nach der nächsten Änderung immer noch vor – also hängt kein zweiter Listener am alten Store (B4).
- **Das Secret entsteht beim ersten Bedarf und bleibt dann gleich.** Ausdrücklich nicht »beim ersten Bericht«: Die ID-Zuordnung am Sensor braucht es schon beim ersten Refresh, also lange vor jedem Download. Geprüft wird, dass es nach dem ersten Refresh da ist und nach dem Download dasselbe ist.

## Was gemessen wurde

Erhoben am 2026-09-19 im Test-Container, auf der Prüfbank mit **7518 Commits, 68 Dashboards (42 lebend, 26 gelöscht), 793 Marken, 9.182.768 Bytes logisch und 9.629.696 Bytes belegt.** Die Zahlen weichen von denen ab, die in dieser Spec sonst genannt sind (7407 Commits, 70 Dashboards, 11 MB) – die Prüfbank verändert sich mit jedem Lauf von `run_checks.py`, das dort Dashboards anlegt, ändert und löscht. Für die Größenordnung ist das ohne Belang, für die Nachvollziehbarkeit einer einzelnen Zahl nicht: Wer nachmisst, misst gegen eine andere Bank.

| Frage | Antwort | Folge |
|---|---|---|
| Dauer eines **warmen** `measure()` | **154,6 ms** (ein zweiter Lauf 193 ms – die Streuung ist Cache-Verhalten des Containers) | Intervall bleibt bei 15 Minuten. Auslastung 0,017 %. |
| Dauer eines **kalten** `measure()` | 6.981 ms | Unkritisch, weil der erste Refresh laut B4 nicht abgewartet wird. Er trifft genau die Situation, für die B4 geschrieben wurde. |
| Dauer des Verzeichnis-Walks | 10,0 ms | 6 % des warmen Werts – **nicht** der Posten, für den ihn B3 gehalten hat. |
| Dauer von `list_versions()` über 793 Marken | 169,2 ms | Ohne Belang für `measure()`: Der Aufrufpfad benutzt `_versions_by_key`, das nur Ref-Namen liest (17,9 ms). Die Messung belegt, dass sich das Ersetzen gelohnt hat. |
| Wo die Zeit **wirklich** steckt | Blob-Längen 67,9 ms, `commit_times` 45,2 ms | In B3 aufgeschlüsselt. Beide waren in der ursprünglichen Fassung dieser Spec nicht bedacht. |

**Wie diese Korrektur zustande kam**, weil der Weg dorthin mehr wert ist als die Zahl: Die Messung lief im Rahmen des Implementierungsplans, und dessen Aufgabe 4 trug den Satz »Weicht eine Zahl stark von der Erwartung ab, stimmt eine Annahme nicht mehr: dann anhalten, nicht die Schwelle anpassen.« Genau das trat ein. Ein Review verweigerte dreimal die Freigabe, weil die Messwerte eingetragen, die widerlegte Begründung in B3 aber stehen geblieben war. Das Anhalten war richtig: Eine Spec, deren Zahl stimmt und deren Begründung nicht, ist schlimmer als eine ohne Zahl – sie schickt den nächsten Leser an die falsche Stelle.

## Offene Punkte

- **Der Bericht sagt nichts über den Aufbau der Dashboards**, nur über die Bytes ihres jüngsten Stands mit Inhalt. Ob ein Dashboard aus vielen kleinen Views oder wenigen großen besteht, bleibt unsichtbar. Bewusst: Die Frage, auf die C wartet, ist »wie viel Platz«, nicht »wie gebaut«.
- **Der Umschlag lässt sich nicht beschneiden.** `custom_components` und `timezone` kommen von Home Assistant und stehen in jeder Diagnosedatei jeder Integration; diese Integration kann sie nicht entfernen, ohne den Standardweg zu verlassen. Ob das für alle Tester annehmbar ist, ist unbelegt. Falls jemand es ablehnt, wäre die Antwort kein zweiter Ausgabeweg, sondern der Hinweis, dass er den `data`-Block von Hand herauskopieren und allein schicken kann – der trägt alles, worauf es hier ankommt.
- **Ob Tester den Diagnose-Knopf finden**, ist unbelegt. Falls nicht, ist die Antwort ein Satz in der README mit einem Bild, kein zweiter Ausgabeweg.
