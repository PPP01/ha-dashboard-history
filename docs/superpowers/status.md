# Aktueller Stand

Stand: 2026-09-22. Dieses Dokument ist der Einstiegspunkt: was gebaut ist,
was noch offen ist, welche Module es gibt. Es ersetzt nicht die Spec — die
bleibt bindend bei Widersprüchen — und nicht das Journal unter `plans/` und
`reviews/`, das chronologisch und unverändert stehen bleibt. Bei jedem
abgeschlossenen Vorhaben oder neu gefundenen Fehler hier nachziehen.

## Vorhaben, Buchstabe für Buchstabe

Die Spec vergibt seit 2026-09-02 einen Buchstaben je größerem Vorhaben
(Abschnitt »Reihenfolge der Vorhaben«). Eine Sache davor trägt keinen:

| Vorhaben | Thema | Stand | Beleg |
|---|---|---|---|
| — | Eigene Texte und Klartext (Notizen, Klartext-Beschreibungen) | Erledigt | `plans/2026-08-31-eigene-texte-und-klartext.md` |
| A | Versionen — benannte Tags je Dashboard | Erledigt (v0.3.0) | `plans/2026-09-02-versionen-pro-dashboard.md` |
| B | Beobachten — Entity-Plattform und Diagnose-Bericht (5 Sensoren für Repo-Größe, Stände, Dashboards, Versionen, Zeitstempel; downloadbarer Bericht via HA-Standardpfad; `report.py` als 7. HA-freies Modul). Der Options-Flow-Teil war bereits erledigt. | Erledigt | `plans/2026-09-19-beobachten.md` |
| C | Aufräumen — verlustfreies Verdichten, danach ggf. eine Aufbewahrungsregel | **Wartet auf Messwerte von Testern** (Vorhaben B ist bereit) | noch kein Plan |
| D | Sechs Befunde am älteren Kern (unabhängiges Review 2026-09-02) | Teilweise — Details unten | Spec, Abschnitt »Offene Punkte« |
| E | Die gezielte Rücknahme — `undo_change` für einzelne Änderungen | Erledigt (v0.3.0) | `plans/2026-09-03-gezielte-ruecknahme.md` |
| F | Die Identitätskette (3 Pakete: Verweigern statt falsch schreiben / Identität / Section als Stück) | Paket 1 erledigt (2026-09-04); Pakete 2–3 vermutlich mit den Section-Arbeiten miterledigt — im Zweifel `reviews/2026-09-04-pfadlose-views-und-sections.md` und `plans/2026-09-09-sections-zurueckholen.md` direkt prüfen | s. o. |
| G | Versionen, die halten — Übereinstimmung/Blättern jenseits der letzten 50 Änderungen | Erledigt (v0.3.0) | `plans/2026-09-04-versionen-die-halten.md` |
| H | Die zwei Modi — Tagesversionen, Moduswechsel, Oberfläche für beide Modi | Erledigt (v0.3.0) | `plans/2026-09-04-versionen-von-selbst.md`, `plans/2026-09-04-die-zwei-modi.md` |
| I | Versionen aufheben | Erledigt (v0.3.0) | `plans/2026-09-08-versionen-aufheben.md` |
| J | Der Vergleichsmodus — ersetzt das zeilenweise Put-back aus Entscheidung 15 durch den Vergleich zweier frei gewählter Stände | Erledigt | `plans/2026-09-12-vergleichsmodus.md` |
| K | Schmal bedienbar — HA-Hamburger, mitwandernde Seitenspalte, Master/Detail unterhalb eines schmalen Bandes | Erledigt | `plans/2026-09-17-schmal-bedienbar.md` |

## Laufzeit `forget` (Versionsmarken in einem Zug)

Gemessen am 2026-09-18 im Container gegen die Prüfbank (7407 Commits, 45 lebende + 25 gelöschte Dashboards, 782 Marken, 11 MB; Plan `plans/2026-09-18-versionsmarken-in-einem-zug.md`):

| Phase | vorher | nachher | Anteil nachher |
|---|---|---|---|
| Stände umschreiben | 5,9 s | 6,6 s | 45 % |
| **Versionsmarken** | **13,2 s** | **0,3 s** | **2 %** |
| Aufräumen | 4,5 s | ~6,6 s | 45 % |
| **gesamt** | **26,6 s** | **14,7 s** | |

Die Phase `versions` (»Rebuilding the version marks«) entfällt in UI und Store, da 0,3 s im selben Wimpernschlag verschwinden. Das Aufräumen (`garbage_collect`) ist nun rund die Hälfte der Wartezeit, bleibt aber vorerst ohne Zähler (Grundlage für spätere Entscheidungen, s. Plan).

## Laufzeit Messung (`report` / Sensoren)

Gemessen am 2026-09-19 im Container gegen die Prüfbank (7518 Commits, 68 Dashboards [42 lebend, 26 gelöscht], 793 Marken, 9.182.768 Bytes logisch / 9.629.696 Bytes belegt; Plan `plans/2026-09-19-beobachten.md`, Spec-Abschnitt »Was gemessen wurde« und B3):

- **Kaltstart (erster Lauf):** 6.981 ms (unkritisch, erster Refresh wird laut B4 nicht abgewartet)
- **Warm (wiederkehrende Messung, HEAD unverändert):** 154,6 ms
- **Auslastung im Executor:** 0,017 % bei `MEASURE_INTERVAL = timedelta(minutes=15)` (154,6 ms / 900 s)
- **Aufschlüsselung warm:** Blob-Längen ermitteln 44 %, `commit_times` 29 %, `_versions_by_key` 12 %, Verzeichnis-Walk (`_measure_disk`) 6 % (Details siehe Spec B3)


## Bekannte offene Punkte

Aus der Spec, Abschnitt »Offene Punkte« (dort mit vollem Messbefund). Bei
Zweifeln über den aktuellen Stand zählt der Code, nicht diese Zeile.

- ~~**Umkehrbarkeit endet an einem nie aufgezeichneten Stand.** *(Gefunden am
  2026-09-17.)* Misslingt das Nachtragen des lebenden Stands, wird trotzdem
  geschrieben, und ein Stand, den der Rekorder nie gehört hat, ist damit fort.
  Betrifft Entscheidung 13, nicht Vorhaben K.~~ **Behoben am 2026-09-22**
  (Entscheidung 23, GitHub-Issue #18). Ein neuer Parameter
  `override_unrecorded_state` (Vorgabe `false`) an den drei Aufrufern von
  `_keep_the_live_state` kehrt die Festlegung vom 2026-09-03 um: Ohne ihn
  wird nicht mehr geschrieben, wenn der lebende Stand nicht vorher gesichert
  werden konnte — vorher wurde trotzdem geschrieben, mit einem Hinweis, der
  das Panel erst nach dem Schreiben erreichte. Der alte Notausgang bleibt,
  jetzt ausdrücklich statt stillschweigend: Wer ihn setzt, bekommt exakt das
  frühere Verhalten für diesen einen Aufruf.

- ~~**D1 — Ein unterbrochenes `forget` ist nicht wiederaufnehmbar.**~~
  **Behoben am 2026-09-21** (Entscheidung 21, GitHub-Issue #22; nach zwei
  externen Reviews am selben Tag an fünf Stellen nachgeschärft, s. Spec —
  das zweite fand, dass `HistoryStore` keine Sperre über mehrere Instanzen
  desselben Pfads teilt, was ein Neuladen mitten in einem laufenden
  `forget` gefährlich machte).
  `HistoryStore._forget` schreibt HEAD,
  Notizen und Tags nacheinander um, ohne vorbereiteten Ersatz-Ref; bricht
  es zwischen den Schritten ab, war ein zweiter Lauf nutzlos und
  Beschreibungen eines noch lebenden Dashboards konnten verloren gehen.
  Behoben durch einen Checkpoint der Zielwerte (neue Zweigspitze, fertige
  Notizen- und Tag-Zuordnung, Schlüssel), geschrieben bevor irgendein Ref
  sich bewegt; jeder Schreibpfad verweigert sich, solange er offen ist —
  nicht nur einmal pro Prozess, sonst könnte ein Nachholen zwischen Absturz
  und Neustart entstandene, fremde Historie zurückrollen. Die eigentliche
  Reparatur läuft im bestehenden Hintergrund-Task vor dem Öffnungslauf,
  nicht im awaited `store.ensure()`. Heilt sich beim nächsten
  Home-Assistant-Start selbst, ohne einen zweiten `forget`-Aufruf.
- ~~**`_finish_forget`s Aufräumen prunte auch einen vorgemerkten, aber
  unbeteiligten Speicherstand.**~~ **Behoben am 2026-09-21** (Entscheidung
  22, GitHub-Issue #25 — beim Review von Entscheidung 21 gefunden und dort
  bewusst zurückgestellt, siehe Spec). `garbage_collect(prune=True,
  grace_period=0)` prüfte Erreichbarkeit nur über `repo.refs`, nie über
  den Index: Blieb ein `write_snapshot` nach `porcelain.add`, aber vor
  `porcelain.commit` stecken, konnte ein völlig unbeteiligtes `forget`
  dessen vorgemerktes Blob prunen — und weil `porcelain.commit` immer den
  ganzen Index committet, riss der nächste erfolgreiche Speichervorgang
  eines dritten Dashboards den toten Verweis dann unbemerkt mit in seinen
  eigenen Baum. `_garbage_collect_protecting_index` schützt seither jedes
  vom Index noch referenzierte Blob, beim losen Löschen wie beim Repack.
- **D3 — Löschen und schnelles Wiederanlegen desselben `url_path`
  verschmelzen zwei Dashboards.** Die zehnsekündige Entprellung verwirft
  den Zwischenzustand »gelöscht«. In dieser Runde nicht erneut am Code
  geprüft — Stand laut Spec weiterhin offen.
- **D6 — Die 1000-Commit-Grenze lässt alte gelöschte Dashboards
  verschwinden.** *(In der Spec noch als offen markiert — beim Nachlesen
  am 2026-09-12 stellt sich heraus: **im Code bereits behoben.**
  `HistoryStore._built_index` liest laut eigenem Docstring »die ganze
  Historie, nicht die neuesten tausend Commits« (`store.py:1307-1314`),
  genau die dort beschriebene Lücke wird namentlich als Grund genannt.
  Ein Beispiel dafür, dass der Code der Spec schon vorausgelaufen ist —
  die Spec selbst braucht hier noch das Durchstreichen.)*
- **Eine Löschzeile ist als solche nicht erkennbar.** `history` liefert
  kein Merkmal, das eine Löschung als solche kennzeichnet; das Panel
  erkennt sie nur am Text der automatischen Meldung. Bewusst nicht mehr
  in einer der bisherigen Fassungen gebaut.
- **D5 — 27 von 484 Karten ohne erkennbares Muster**, wo keine Rechnung
  Bearbeitung von Löschung unterscheiden kann. Das ist eine benannte
  Grenze, keine Aufgabe: siehe Spec, »Was ausdrücklich nicht passiert«.

## Modul-Übersicht

`custom_components/dashboard_history/`, nach Aufgabe geordnet. Die sieben
mit ✓ müssen HA-frei bleiben (siehe CLAUDE.md, »Harte Regeln«) und sind es
laut Grep auch (Stand 2026-09-19).

| Datei | Aufgabe |
|---|---|
| `yaml_io.py` ✓ | Deterministisches Lesen/Schreiben von Dashboard-YAML |
| `analyze.py` ✓ | Erkennt, was sich zwischen zwei Ständen geändert hat; plant Undo |
| `restore.py` ✓ | Setzt Verschwundenes additiv wieder ein |
| `versions.py` ✓ | Versionsnummern und Tagesmarken: lesen, ordnen, hochzählen |
| `keys.py` ✓ | Welcher Dashboard-Schlüssel gültig/gelöscht ist |
| `store.py` ✓ | Das Git-Repository selbst: Commits, Tags, Notizen, Indizes |
| `report.py` ✓ | Erzeugt den anonymisierten Diagnose-Bericht (reine Zahlen, keine Dashboard-Inhalte) |
| `capture.py` | Hört auf `lovelace_updated`, liest den Stand aus dem Speicher |
| `snapshot.py` | Liest Dashboard-Konfigurationen direkt aus Home Assistant |
| `milestones.py` | Legt automatische Tages-/Initial-Versionen an |
| `operations.py` | Bündelt alle Operationen; einzige Stelle mit `confirm`-Logik |
| `services.py` | Dienste für Entwicklertools — dünne Haut über `operations.py` |
| `websocket_api.py` | WebSocket-Befehle fürs Panel — dieselbe dünne Haut |
| `panel.py` | Registriert das Sidebar-Panel (`panel_custom`) |
| `panel.js` | Die eigentliche Panel-Oberfläche (Vanilla JS, kein Bauschritt) |
| `config_flow.py` | Einrichtung: eine Bestätigung, ein Schalter danach |
| `const.py` | Konstanten |
| `coordinator.py` | DataUpdateCoordinator für periodische Messung (15 min) und Event-Entprellung |
| `sensor.py` | Fünf Diagnose-Sensoren (Größe, Stände, Dashboards, Versionen, Zeitstempel) |
| `diagnostics.py` | Downloadbarer Diagnose-Bericht über Home Assistants Standardpfad |
| `__init__.py` | Einstiegspunkt der Integration |

## Wie man sich im Journal orientiert

- `specs/` — der Entwurf mit Begründungen. Bindend bei Widersprüchen, wird
  fortlaufend um neue Entscheidungen und Vorhaben ergänzt statt neu
  geschrieben.
- `plans/` — ein Umsetzungsplan je Vorhaben, datiert. Realisierte
  Task-Listings zeigen den Stand *zum Zeitpunkt des Plans*; maßgeblich
  bleibt der Code.
- `reviews/` — unabhängige Nachprüfungen und Audits, teils mit eigenem
  Unterordner samt Ledger-Dateien für größere Vorhaben.

Chronologisch lesen, bei Bedarf jüngste zuerst; die Dateinamen tragen das
Datum.
