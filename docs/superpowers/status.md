# Aktueller Stand

Stand: 2026-09-12. Dieses Dokument ist der Einstiegspunkt: was gebaut ist,
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
| B | Beobachten — Options-Flow und Entity-Plattform (Repo-Größe, Zahl der Stände/Dashboards, letzte Erfassung) | **Nicht begonnen** | noch kein Plan |
| C | Aufräumen — verlustfreies Verdichten, danach ggf. eine Aufbewahrungsregel | **Nicht begonnen**, wartet laut Spec auf Messwerte aus B | noch kein Plan |
| D | Sechs Befunde am älteren Kern (unabhängiges Review 2026-09-02) | Teilweise — Details unten | Spec, Abschnitt »Offene Punkte« |
| E | Die gezielte Rücknahme — `undo_change` für einzelne Änderungen | Erledigt (v0.3.0) | `plans/2026-09-03-gezielte-ruecknahme.md` |
| F | Die Identitätskette (3 Pakete: Verweigern statt falsch schreiben / Identität / Section als Stück) | Paket 1 erledigt (2026-09-04); Pakete 2–3 vermutlich mit den Section-Arbeiten miterledigt — im Zweifel `reviews/2026-09-04-pfadlose-views-und-sections.md` und `plans/2026-09-09-sections-zurueckholen.md` direkt prüfen | s. o. |
| G | Versionen, die halten — Übereinstimmung/Blättern jenseits der letzten 50 Änderungen | Erledigt (v0.3.0) | `plans/2026-09-04-versionen-die-halten.md` |
| H | Die zwei Modi — Tagesversionen, Moduswechsel, Oberfläche für beide Modi | Erledigt (v0.3.0) | `plans/2026-09-04-versionen-von-selbst.md`, `plans/2026-09-04-die-zwei-modi.md` |
| I | Versionen aufheben | Erledigt (v0.3.0) | `plans/2026-09-08-versionen-aufheben.md` |

## Bekannte offene Punkte

Aus der Spec, Abschnitt »Offene Punkte« (dort mit vollem Messbefund). Bei
Zweifeln über den aktuellen Stand zählt der Code, nicht diese Zeile.

- **D1 — Ein unterbrochenes `forget` ist nicht wiederaufnehmbar.**
  `HistoryStore._forget` (`store.py:879`) schreibt HEAD, Notizen und Tags
  nacheinander um, ohne vorbereiteten Ersatz-Ref; bricht es zwischen den
  Schritten ab, ist ein zweiter Lauf nutzlos und Beschreibungen eines noch
  lebenden Dashboards können verloren gehen. **Beim Nachlesen am
  2026-09-12 bestätigt: Struktur noch wie im Befund beschrieben, weiterhin
  offen.**
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

`custom_components/dashboard_history/`, nach Aufgabe geordnet. Die sechs
mit ✓ müssen HA-frei bleiben (siehe CLAUDE.md, »Harte Regeln«) und sind es
laut Grep auch (Stand 2026-09-12).

| Datei | Aufgabe |
|---|---|
| `yaml_io.py` ✓ | Deterministisches Lesen/Schreiben von Dashboard-YAML |
| `analyze.py` ✓ | Erkennt, was sich zwischen zwei Ständen geändert hat; plant Undo |
| `restore.py` ✓ | Setzt Verschwundenes additiv wieder ein |
| `versions.py` ✓ | Versionsnummern und Tagesmarken: lesen, ordnen, hochzählen |
| `keys.py` ✓ | Welcher Dashboard-Schlüssel gültig/gelöscht ist |
| `store.py` ✓ | Das Git-Repository selbst: Commits, Tags, Notizen, Indizes |
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
