# Review: Startdauer als Diagnose-Sensor

Geprüft gegen Arbeitsbaum/`main` bei `5004421`. Der verlinkte
Issue-Kommentar war nicht nötig; die Messpunktentscheidung wurde gegen den
Code geprüft.

## Kritisch

Keine Befunde dieser Schwere.

## Hoch

### Der Opening pass baut den Index nicht zuverlässig

- **Fundstelle:** Plan:15, 328–350 und 731; `capture.py`:353–374;
  `store.py`:2403–2446, 2695–2735, 3404–3434 und 3588–3610;
  `operations.py`:407–419.
- **Beschreibung:** Die Schlussfolgerung aus `_write_one`/`_has_history`
  gilt nicht auf einer frischen Historie mit genau einem Dashboard.
  `_has_history()` läuft dort vor dem ersten `write_snapshot()`. Es gibt
  noch kein `HEAD`, daher liefert `list_changes()` leer zurück, ohne
  `_revision_index()` und damit ohne `_timed_build()` aufzurufen. Erst der
  Schreibvorgang erzeugt HEAD, danach gibt es in diesem Pass keinen zweiten
  `_has_history()`-Aufruf. Auch ein Pass ohne aktuelle Konfigurationen
  baut keinen Index. Die Dashboard-Liste des Panels ruft später
  `dashboard_listing()` und damit `survey()` auf; genau dort kann der volle
  Index erst entstehen.
- **Konsequenz:** Der Sensor meldet im frischesten und einfachsten Fall
  eine abgeschlossene Startdauer und `index_build: null`, obwohl das Öffnen
  des Panels noch den teuren Indexbau auslösen kann. Die zentrale Aussage,
  das Passende sei eine obere Grenze für die Listen-Wartezeit, ist falsch.
- **Vorschlag:** Den Hintergrundpfad vor dem Zeitstempel ausdrücklich
  `store.survey()` im Executor ausführen lassen (nur nach erfolgreichem
  Recording) und erst danach die Dauer setzen; dabei den leeren HEAD als
  bewusst indexlosen, schnellen Fall behandeln. Alternativ die Semantik
  auf »Dauer bis Abschluss des Opening pass« beschränken und weder
  Nutzbarkeit noch Panel-Wartezeit behaupten. Ergänzende Tests müssen eine
  neue Historie mit genau einem Dashboard sowie keinen aktuellen
  Dashboards abdecken.

### Ein normal zurückkehrender Opening pass ist kein Nachweis einer nutzbaren Historie

- **Fundstelle:** Plan:29–33 und 340–350; `__init__.py`:63–73,
  126–134; `capture.py`:175–211 und 213–277; `store.py`:1276–1289.
- **Beschreibung:** Der vorgeschlagene `else`-Zweig wertet allein das
  Ausbleiben einer Ausnahme aus `async_opening_pass()` als Erfolg. Das ist
  im bestehenden Code kein Erfolgsindikator: Fehler beim Lesen der
  Dashboard-Konfiguration werden geloggt und als `None` beantwortet;
  Fehler je Dashboard-Schreibvorgang werden geloggt und übersprungen.
  Auch ein gescheitertes `store.ensure()` wird in `async_setup_entry()`
  geschluckt. Somit kann der Pass normal zurückkehren, obwohl nichts
  aufgezeichnet und die Historie nicht verwendbar ist.
- **Konsequenz:** Anders als Plan:32 behauptet, zeigt der Sensor gerade
  bei einem nicht fertig nutzbaren Start eine plausible Zahl statt
  `unknown`. Das verschleiert einen Diagnosefall.
- **Vorschlag:** `HistoryCapture.async_opening_pass()` muss ein
  explizites, aussagekräftiges Ergebnis liefern (etwa: Konfigurationen
  gelesen, Repository schreibbar, anschließender Index/Survey erfolgreich),
  oder eine eigene Readiness-Prüfung muss vor dem Setzen der Felder laufen.
  Nur bei diesem Ergebnis setzen; Fehler beim Konfigurationslesen,
  `ensure` und mindestens ein Schreibfehler müssen als Tests abgedeckt
  werden.

### Der Berichtsvertrag bleibt nach dem Nachtrag widersprüchlich

- **Fundstelle:** Plan:23, 610–645 und 723–734;
  `docs/superpowers/specs/2026-09-19-beobachten-design.md`:284–331.
- **Beschreibung:** Der bindende Vertrag enthält weiterhin das vollständige
  JSON-Beispiel mit `"schema": 1` und keinen `startup`-Block. Außerdem
  sagt seine Regeltabelle, außer `bytes_allocated` seien Zahlen nie `null`.
  Der Plan fügt nur am Dateiende einen Nachtrag an, der `schema` 2 und zwei
  nullable Startzahlen festlegt. Damit stehen zwei einander widersprechende
  Verträge in derselben bindenden Spec. Der B1-Abschnitt selbst bleibt
  ebenfalls mit Tabelle und Begründung auf fünf Sensoren stehen.
- **Konsequenz:** Implementierende und spätere Reviews können sich
  begründet auf die alte, vollständigere Vertragsdefinition berufen;
  eine Schema-2-Datei mit `null` ist dann formal vertragswidrig.
- **Vorschlag:** Den Vertrag direkt aktualisieren oder im Nachtrag einen
  ausdrücklich ersetzenden Abschnitt aufnehmen: JSON-Beispiel mit
  `schema: 2` und `startup`, Tabelleneintrag für beide nullable
  Sekundenwerte, B1-Tabelle/Anzahl sowie die Testplan-Sätze zu sechs
  Entitäten und Reload anpassen.

## Mittel

### Der neue Integrationscheck widerspricht dem eigenen Null-Fall und ist zeitlich flakey

- **Fundstelle:** Plan:33, 193–215, 552–580; `sensor.py`:163–181;
  `store.py`:2718–2720.
- **Beschreibung:** `check_startup_time()` verlangt immer
  `index is not None`, während Plan:33 und Task 3 für eine leere Historie
  ausdrücklich `index_build: null` verlangen. Darüber hinaus verlangt der
  Check nach einer Rundung auf eine Zehntelsekunde `seconds > 0`. Ein
  zulässiger sehr schneller Pass wird jedoch als `0.0` dargestellt und
  würde fälschlich fehlschlagen.
- **Konsequenz:** Der vorgeschriebene Test kann bei einem legitimen leeren
  Start rot werden und deckt den vorgesehenen `null`-Vertrag nicht ab.
- **Vorschlag:** `seconds is not None and seconds >= 0` prüfen. Die
  Schranke nur prüfen, falls `index is not None`; dann
  `0 <= index <= seconds + 0.1`. Einen Container- oder gezielten Test für
  den nullbaren Index ergänzen.

### Der Container-Test prüft den Schemawechsel nicht vollständig

- **Fundstelle:** Plan:665–685; `tests/integration/run_checks.py`:5060–5064.
- **Beschreibung:** Task 3 lässt den Check »the report carries all four
  blocks« unverändert. Seine Teilmengenprüfung bleibt trotz fehlendem
  `startup` und trotz falschem Schema grün. Auch der in Plan:682 verwendete
  Suchausdruck enthält noch `four blocks`.
- **Konsequenz:** Der Live-Test beweist weder den neuen Block noch
  `schema == 2`; ein späterer Rückfall kann unbemerkt bleiben.
- **Vorschlag:** Den Check auf die exakte erwartete Schlüsselsatzmenge
  einschließlich `startup` ändern, `body["schema"] == 2` prüfen und die
  Struktur/Nullbarkeit von `startup` prüfen. Die Bezeichnung und den
  grep-Ausdruck auf fünf Blöcke aktualisieren.

### B1-Eigenschaften des sechsten Sensors werden nicht getestet

- **Fundstelle:** Plan:386–462; Spec B1:85–97 und Testplan:361–367;
  `sensor.py`:139–160; `tests/integration/run_checks.py`:4806–4833,
  5020–5025.
- **Beschreibung:** Die Implementierung setzt zwar `DIAGNOSTIC` und teilt
  per Helfer das Dienst-Gerät, der angegebene Container-Test kontrolliert
  jedoch nur Unique-ID-Schlüssel und Anzahl. Er prüft weder
  `entity_category: diagnostic` noch die gemeinsame Gerätezuordnung des
  neuen Sensors.
- **Konsequenz:** Ein Fehler im neuen, von `HistoryReading` getrennten
  Entitätspfad verletzt B1, ohne dass die geplante Prüfung ihn bemerkt.
- **Vorschlag:** Über Entity- und Device-Registry den neuen Sensor gegen
  eine bestehende Reading-Entität vergleichen und zusätzlich
  `entity_category` prüfen. Wenn die Registry-Antwort das Feld nicht
  liefert, die geeignete HA-Registry-API im vorhandenen Socket-Helfer
  ergänzen.

### Für die neue Store-Semantik fehlt der relevante End-to-End-Test

- **Fundstelle:** Plan:67–85 und 138–141; `store.py`:2738–2757,
  2790–2854; `capture.py`:95–114.
- **Beschreibung:** Die zwei neuen Unit-Tests zeigen nur, dass ein
  beliebiger voller Bau eine Dauer speichert und eine normale
  Index-Erweiterung sie nicht überschreibt. Sie zeigen nicht, dass der
  Wert des *Opening pass* zu der Startdauer gehört, nicht nach einem
  späteren Neubau überschrieben wird und im Ein-Dashboard-Frischfall
  korrekt behandelt wird.
- **Konsequenz:** Gerade der vom Plan als zentral bezeichnete
  Messpunkt bleibt ungetestet; die vorhandenen Tests könnten bei einer
  semantisch falschen Verkabelung alle grün sein.
- **Vorschlag:** Nach Korrektur des Messpunkts einen Integrationstest mit
  frischer Ein-Dashboard-Historie und einen Test für einen erzwungenen
  späteren `_extended_index`-Fehlschlag/Neubau ergänzen. Der Test muss den
  beim Opening gesnapshotteten Wert gegen den späteren Storewert abgrenzen.

## Niedrig

### Die optionale Mehrversions-Prüfung ist nicht reproduzierbar formuliert

- **Fundstelle:** Plan:738–746; `CLAUDE.md`:65–67.
- **Beschreibung:** Die Befehle referenzieren feste, nicht versionierte
  lokale Pfade `~/venvs/dh313/bin/python` und `~/venvs/dh314/bin/python`.
  Der anschließende Hinweis »optional« entschärft die Ausführung, macht den
  Plan aber nicht aus dem committed state reproduzierbar.
- **Konsequenz:** Eine umsetzende Person kann die genannten Prüfungen
  nicht ausführen, ohne die Autorenumgebung zu erraten; CI-Abdeckung wird
  nur behauptet, nicht als konkrete Alternative angegeben.
- **Vorschlag:** Die zwei Zeilen durch einen dokumentierten optionalen
  Ablauf ersetzen (z. B. venv außerhalb des Repos mit der gewünschten
  Python-Version anlegen und `python -m pytest …`), oder sie ganz dem
  CI-Schritt überlassen. Die Docker-Schritte selbst sind hinsichtlich
  Compose-Projekt und Containername durch `docker/compose.yaml` und
  `docker/README.md` ausreichend herleitbar; deren externe Konfiguration
  ist dort bewusst dokumentiert.

## Positiv geprüft

Die zitierten alten Stellen für Konstruktor, `_timed_build`,
`_write_one`/`_has_history`, Sensor-Docstrings, Übersetzungsblock und
Statuszeile stimmen mit dem Arbeitsbaum überein. Alle aktuellen
Produktivaufrufe von `report.build` (nur `diagnostics.py`:39) und alle
direkten Testaufrufe (`tests/test_report.py`:34, 71, 82) sind im Plan für
die neue Signatur erfasst. Die vorgeschlagenen HA-Imports und
Sensor-Attribute erscheinen mit den im Arbeitsbaum verwendeten Mustern
vereinbar; eine eigenständige Laufzeitprüfung gegen HA 2024.11 wurde nicht
durchgeführt und bleibt daher eine Annahme.

**Gesamturteil:** nicht umsetzbar in dieser Fassung; Messpunkt, Erfolgsdefinition und Berichtsvertrag müssen vor der Umsetzung korrigiert werden.
ENDE DES REVIEWS
