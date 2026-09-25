# Aktueller Stand

Stand: 2026-09-24. Dieses Dokument ist der Einstiegspunkt: was gebaut ist,
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
| F | Die Identitätskette (3 Pakete: Verweigern statt falsch schreiben / Identität / Section als Stück) | Paket 1 erledigt (2026-09-04); Paket 3 erledigt (2026-09-09, ohne Identität, über unveränderte Nachbar-Sections); **Paket 2, die Identität selbst (Entscheidung 16), nie gebaut** – am 2026-09-23 im Code nachgeprüft | `reviews/2026-09-04-pfadlose-views-und-sections.md`, `plans/2026-09-09-sections-zurueckholen.md` |
| G | Versionen, die halten — Übereinstimmung/Blättern jenseits der letzten 50 Änderungen | Erledigt (v0.3.0) | `plans/2026-09-04-versionen-die-halten.md` |
| H | Die zwei Modi — Tagesversionen, Moduswechsel, Oberfläche für beide Modi | Erledigt (v0.3.0) | `plans/2026-09-04-versionen-von-selbst.md`, `plans/2026-09-04-die-zwei-modi.md` |
| I | Versionen aufheben | Erledigt (v0.3.0) | `plans/2026-09-08-versionen-aufheben.md` |
| J | Der Vergleichsmodus — ersetzt das zeilenweise Put-back aus Entscheidung 15 durch den Vergleich zweier frei gewählter Stände | Erledigt | `plans/2026-09-12-vergleichsmodus.md` |
| K | Schmal bedienbar — HA-Hamburger, mitwandernde Seitenspalte, Master/Detail unterhalb eines schmalen Bandes | Erledigt | `plans/2026-09-17-schmal-bedienbar.md` |
| L | Parken statt verweigern — Karten, deren Section sich seit der Änderung verschoben hat, landen in HAs »Imported cards« (Entscheidung 26, Issue #30) | **Spec vom Nutzer bestätigt am 2026-09-24, Plan bereit** | `specs/2026-09-24-importierte-karten-design.md`, `plans/2026-09-24-importierte-karten.md` |
| M | Benannte Einstellungen des Dashboards und der Ansichten gezielt zurücknehmen (Issue #28) | **Spec vom Nutzer bestätigt am 2026-09-24, Plan bereit**; setzt L voraus | `specs/2026-09-24-einstellungen-zuruecknehmen-design.md`, `plans/2026-09-24-einstellungen-zuruecknehmen.md` |
| N | Badges einer Ansicht gezielt zurücknehmen (Issue #29) | **Spec vom Nutzer bestätigt am 2026-09-24, nach Review präzisiert und bestätigt am 2026-09-25; Plan geprüft und nachgeprüft**; setzt L und M voraus | `specs/2026-09-24-badges-zuruecknehmen-design.md`, `plans/2026-09-24-badges-zuruecknehmen.md` |

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
- ~~**Ein `before`-Paginierungs-Cursor überlebt kein `forget`, das über ihn hinaus umschreibt.** *(Gefunden bei der Umsetzung von Entscheidung 24, GitHub-Issue [#26](https://github.com/PPP01/ha-dashboard-history/issues/26), dort bewusst zurückgestellt.)* `_indexed_revisions` antwortete für einen inzwischen geprunten Cursor genauso wie für einen nie gültigen: mit `[]`, ununterscheidbar von »keine ältere Historie mehr vorhanden«, obwohl darunter weiterhin Hunderte Commits unter neuen Shas stehen konnten.~~ **Behoben am 2026-09-22** (Entscheidung 25). Eine persistierte, monoton steigende `forget_generation()` und ein optionaler Parameter `before_generation` unterscheiden jetzt die beiden Fälle; `operations.async_history` startet die Seite bei einem veralteten Cursor neu und meldet `restarted: true`, statt still zu verkürzen.
- ~~**Ein Undo eines Section-Tauschs schreibt still einen falschen Stand.**~~ **Absicherung behoben am 2026-09-23** *(Gefunden am 2026-09-23, GitHub-Issue [#31](https://github.com/PPP01/ha-dashboard-history/issues/31); nur der kleine Fix aus dem Ticket, nicht die volle Lösung.)* Sections werden weiterhin nicht als Einheit abgeglichen, nur ihre Karten. Beim Tausch zweier Sections wanderten die Karten zurück, während die Einstellungen der Sections (z. B. `column_span`) an ihrer Position blieben – der Undo galt als exakt, das Ergebnis entsprach keinem früheren Stand. `_sections_lie` prüfte nur das Feld `title`, das HA für Sections nicht setzt. `_section_marks` vergleicht seither jede Section ohne `cards` als Ganzes; ein reiner Einstellungs-Tausch ohne Titel wird damit erkannt und der Undo verweigert, statt still den falschen Stand zu schreiben. **Weiterhin offen:** Derselbe Grund-Fehler lässt die Anzeige von »6 moved« Karten sprechen, wo eine Section verschoben wurde – das braucht den Abgleich von Sections als Einheit (die große Lösung), nicht nur die Absicherung. Verwandt: Entscheidung 26 (#30).
- **Behoben am 2026-09-24** (GitHub-Issue [#32](https://github.com/PPP01/ha-dashboard-history/issues/32)): Eine View-Konvertierung (z. B. masonry → sections) wurde bisher weder in der Erklärung genannt (`type` ist keine Karte, ein Save, der nur den Typ ändert, hatte nichts zum Anhängen) noch verweigerte `plan_undo` sie aus dem richtigen Grund – `_SECTION_REFUSAL` feuerte, weil die Konvertierung nebenbei eine leere Grid-Section anlegt und damit die Section-Liste verändert, nicht weil tatsächlich Sections vertauscht wurden. Im tatsächlichen HA-Verhalten (Entscheidung 26, im Testcontainer nachgestellt) bleiben dabei alle Karten unverändert in `cards:` stehen – `match_cards` sieht dann gar keine Karten-Änderung, und die frühe Verweigerung »this change did not alter any cards« griff vor jeder Section- oder Typ-Prüfung. Ein erstes Review am selben Tag fand das: Die neue Prüfung `_view_type_changed` musste deshalb zusätzlich in die frühe Bedingung selbst, nicht nur vor `_sections_lie`. Die Erklärung zeigt jetzt »the view … was converted from masonry to sections« als eigene Zeile. Verwandt: #28 (`type` bleibt deshalb bewusst außerhalb des generischen Scalar-Diffs).
- **Behoben am 2026-09-24** (GitHub-Issue [#33](https://github.com/PPP01/ha-dashboard-history/issues/33)): `_positions_lie` verglich bisher die komplette Menge der positionslosen View-Schlüssel zweier Stände – jede Abweichung, auch ein am Ende angehängter neuer View, ließ die Prüfung für *alle* Positionen scheitern, selbst für Views weit davor, die von diesem Anhängen gar nicht betroffen sein konnten. Die Prüfung vergleicht Positionen jetzt nur noch bis zur Länge des kürzeren der beiden Stände; ein Anhängen verlängert nur eine Seite und bleibt deshalb außerhalb des Vergleichs. Eine echte Einfügung oder Löschung *innerhalb* dieser gemeinsamen Länge verweigert weiterhin – ein Einfügen in der Mitte verändert die Gesamtzahl der Views genauso wie ein Anhängen, lässt sich davon aber nicht allein an der Länge unterscheiden, sondern erst daran, dass die betroffene Position innerhalb der gemeinsamen Länge inhaltlich nicht mehr passt (eigener Test dafür ergänzt). Nach demselben Gedanken, auf Hinweis des Nutzers am selben Tag ergänzt: Haben beide Stände genau **eine** Ansicht, kann sich ihre Position gar nicht verschoben haben – eine einzige pfadlose Ansicht ohne Titel wurde bis dahin bei jeder Kartenänderung verweigert, weil sich ihr Inhalt änderte und kein Titel sie wiedererkennbar machte. Verwandt: Entscheidung 16 (die nie gebaute Identitätskette), die diese Fallunterscheidung überflüssig machen würde.
- **Ein Nicht-Dict-Eintrag in `views` lenkt die gezielte Rücknahme in die falsche Ansicht.** *(Gefunden am 2026-09-24 im Plan-Review zu Vorhaben L, Befund W3, am Code nachgestellt; noch kein GitHub-Issue.)* `Slot.view_index` stammt aus `enumerate(_views_by_key(...))` und überspringt Nicht-Dict-Einträge, `restore._find_view` indiziert dagegen die rohe `views`-Liste. Steht ein solcher Eintrag vor einer pfadlosen Ansicht, landet eine zurückgenommene Karte **still in der Ansicht davor**: nachgestellt mit `views = ["junk", Erst, Home]`, Karte aus »Home« gelöscht – der Undo schreibt sie nach »Erst«, ohne Fehler. Wie oft Home Assistant so etwas überhaupt speichert, ist nicht gemessen; der Editor tut es nicht. **Vorschlag:** `Slot.view_index` als rohen Index führen, den der Schlüssel `("#", index)` ohnehin schon trägt.
- **Ein Undo meldet »already taken back«, obwohl die gelöschte Karte fehlt.** *(Gefunden am 2026-09-24 beim Schreiben der Spec zu Vorhaben N, am Code nachgestellt; noch kein GitHub-Issue.)* `plan_undo` überspringt das Wiedereinsetzen einer gelöschten Karte, sobald ihr Fingerabdruck **irgendwo** im heutigen Stand vorkommt (`if by_mark.get(fingerprint(old_slot.card)): continue`). Steht eine identische Karte unberührt auf einer anderen Ansicht, gilt die gelöschte damit als »schon zurück«: Plan ohne Schritte, `apply_undo` ändert nichts, `async_undo_change` antwortet »this change is already taken back«. Nachgestellt mit `before = {v: [X], w: [X]}`, `after = {v: [], w: [X]}` – der Plan ist leer, das Ergebnis gleich dem heutigen Stand. Das ist die Fehlerklasse, die die Spec am schwersten wiegt: ein Satz, der sagt, es sei nichts zu tun, während etwas fehlt. Nichts wird falsch geschrieben – es wird nur fälschlich nichts angeboten; der ganze Stand und der Vergleichsmodus holen die Karte weiterhin zurück. **Vorschlag:** dieselbe gezählte Regel, die Spec N für Badges festlegt – zurück ist nur, wovon es heute in der eigenen Ansicht mehr gibt als unmittelbar nach der Änderung; von mehreren gleichen Gelöschten nur alle zusammen, ist erst ein Teil zurück, wird verweigert. (Die erste Fassung dieses Vorschlags zählte auch »im ganzen Dashboard«; das Review von Plan N am 2026-09-25 hat gezeigt, dass das dieselbe Tür wieder öffnet – eine seither anderswo angelegte Kopie wäre dann »zurück«.)
- **Ein Undo entfernt eine Karte, die die Änderung nie berührt hat.** *(Gefunden am 2026-09-25 im Plan-Review zu Vorhaben N, Befund K1, an der Karten-Seite des heutigen Codes nachgestellt; noch kein GitHub-Issue.)* Für eine hinzugefügte Karte fragt `plan_undo` nur, ob ihr Fingerabdruck **heute** genau einmal im Dashboard steht – nicht, ob die Änderung auch genau eine hinterlassen hat. Nachgestellt mit `before = {a: [X], b: []}`, `after = {a: [X], b: [X]}`, heute `{a: [X], b: []}` (die hinzugefügte auf b wurde seither von Hand gelöscht): Der Undo gilt als exakt und entfernt die Karte auf **a**, die schon vor der Änderung dastand; Ergebnis `{a: [], b: []}`, kein früherer Stand. Ebenso in einer Ansicht: `before = [X]`, `after = [X, X]`, heute `[X]` → Ergebnis `[]`. Anders als der Befund davor wird hier **falsch geschrieben**, nicht nur zu wenig angeboten – die schwerere Fehlerklasse, wenn auch nur bei identischen Karten. **Vorschlag:** wie Plan N für Badges – »heute genau eine« zählt nur zusammen mit »die Änderung hat genau eine hinterlassen«, dashboardweit oder in der eigenen Ansicht; sonst verweigern.
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
