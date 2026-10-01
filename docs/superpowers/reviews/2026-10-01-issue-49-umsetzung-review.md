# Review der Umsetzung: Ungespeicherte Änderungen in der Dashboard-Liste (Issue #49)

Gegenstand: Branch `issue-49-unversioned-marker`, zwei Commits von Gemini (`982cf95`, `51dee57`) gegen `main` (`df5a8e8`), nach dem Plan `plans/2026-10-01-ungespeicherte-aenderungen-in-der-liste.md` und dem Bericht `plans/2026-10-01-ungespeicherte-aenderungen-in-der-liste-umsetzung-gemini.md` (nicht committet). Reines Lese-Review: Der Branch und der Arbeitsbaum wurden nicht verändert, alle Läufe geschahen in Scratch-Kopien (`git archive`), die aufgeräumt wurden.

## Was geprüft wurde und wie

| Prüfung | Ergebnis |
|---|---|
| Zwei Commits, Reihenfolge Aufgabe 1, dann 2; keine Dateien außerhalb des Plans | bestätigt (`git diff --name-only main..HEAD`: 8 Dateien, alle im Plan genannt) |
| Commit-Messages wörtlich wie im Plan | bestätigt, maschinell verglichen, beide gleich |
| Code wörtlich wie im Plan | bestätigt: jeder Python-, JS- und CSS-Block des Plans steht in den Dateien des Branches (Block- oder Zeilenvergleich, 0 Abweichungen) |
| Jeder Commit gegen seinen eigenen Baum (`git archive` je Commit, `pytest tests/`) | `982cf95`: 1095 passed, 5 skipped. `51dee57`: 1104 passed, 5 skipped, Komplexitäts-Ratsche grün, `lint-imports` 2 kept, 0 broken |
| Mutationsprüfung der Tests (je eine Zeile kaputt gemacht, in Scratch-Kopie) | 7 von 8 Mutationen werden von `pytest` erkannt (siehe unten); die achte ist HA-gebunden und nur durch `run_checks.py` erreichbar |
| Messung neu gelaufen (40 Dashboards, 800 Änderungen, 400 Tags) | kalt 700 ms, warm 12,7 ms und 13,7 ms (Gemini: 541,6 / 15,3 / 16,3 ms); gleiche Größenordnung, unter der 100-ms-Grenze |
| Werte gegen die echte Testinstanz | 50 von 51 lebenden Dashboards stimmen mit einer unabhängigen Berechnung überein (`git`-Log je Dashboard plus Tags); die eine Abweichung ist erklärt (H3) |
| Behauptungen im Bericht | bis auf Token-Verbrauch (nicht ermittelbar, Gemini sagt es selbst) nachvollzogen; die Testzahlen weichen von meinen ab (1133 gegen 1104 passed), weil die Gesamtzahl mit den echten Dashboards der `.storage` schwankt, nur »0 failed« zählt |

Mutationen im Einzelnen: Listing ohne Rennschutz → `test_the_listing_never_mixes_names_and_counts_of_two_generations` rot. Cache abgeschaltet → `test_an_unchanged_version_is_not_read_again` rot. Besitzer des Tags ignoriert → `test_another_dashboards_version_does_not_tidy_this_one` rot. Zählung um eins verschoben → `test_a_version_on_the_newest_change_leaves_nothing_unversioned` rot. Gelöschtes Dashboard markiert → `test_a_deleted_dashboard_never_carries_the_mark` rot. Screenreader-Text entfernt → `test_the_chip_is_read_out_in_words` rot. Orange Regel entfernt → `test_the_orange_rule_comes_after_the_blue_one` rot. Server gibt für gelöschte Dashboards `> 0` zurück → **`pytest` bleibt grün** (HA-gebunden, `operations.py`); die Prüfung dafür ist `run_checks.py` (Löschfall, `unversioned == 0`) und sie lief in Geminis Bericht grün.

## Kritisch

Keine.

## Wichtig

### W1: Die Dashboard-Liste schlägt jetzt fehl, solange ein `forget` unfertig ist

**Fundstelle:** `store.py` `dashboard_listing` (Zeilen ~3541-3553), `operations.py:414-417` (`async_dashboards`), `store.py` `_retrying_a_forget_race` (Zeile ~2537).

**Beschreibung:** Vor der Änderung rief `async_dashboards` nur `store.survey` auf, und das antwortet auch während eines unfertigen `forget`. Jetzt läuft es über `dashboard_listing` im Rennschutz, und der vertraut einer Antwort nur, wenn HEAD stillstand **und** keine Checkpoint-Datei existiert. Solange ein `forget` läuft (bis zu rund 15 s) oder ein Checkpoint liegen geblieben ist, besteht kein Versuch die Prüfung, und nach drei Versuchen kommt `RuntimeError`. Reproduziert in einer Scratch-Kopie mit einer angelegten Checkpoint-Datei: `survey()` allein gibt `['home']` zurück, `unversioned_counts()` und `dashboard_listing()` werfen `RuntimeError: a concurrent forget kept racing this read past all 3 attempts`.

**Konsequenz:** Der WebSocket-Befehl `dashboard_history/dashboards` schlägt dann fehl, und das Panel kann seine Liste links nicht laden, obwohl die Liste vorher einfach geantwortet hat. Das trifft einen zweiten offenen Panel-Tab während eines `forget`, und es trifft jeden, dessen `forget` nach einem Absturz einen Checkpoint hinterlassen hat, den `ensure()` beim nächsten Start nicht abschließen kann (siehe die Meldungen »An interrupted forget could not be finished automatically«). Für History und Suche ist dieses Verhalten durch Entscheidung 24 gewollt; die Liste war bisher aber **kein** geschützter Lesepfad, und hier hängt sie wegen einer rein kosmetischen Zusatzanzeige (Streifen, Zahl) daran. Der Plan hat diese Folge nicht benannt; sie ist kein Fehler der Umsetzung, die dem Plan genau folgt.

**Vorschlag (eine Entscheidung des Nutzers):** Die Zähler als Best-Effort behandeln, die Liste selbst nicht. In `dashboard_listing` den geschützten Aufruf in `try/except RuntimeError` fassen und im Fehlerfall `self.survey()` mit leeren Zählern `{}` zurückgeben (keine Streifen, aber die Liste lädt wie zuvor), dazu ein Test mit angelegter Checkpoint-Datei (`store._checkpoint_path().write_text("{}")`), der genau das prüft. Die Konsistenz von Namen und Zählern bleibt erhalten, weil die Liste im Normalfall weiter aus einem Durchlauf kommt; im Fehlerfall fehlt nur die Zahl. Die Alternative ist, das jetzige Verhalten bewusst zu behalten (konsequent nach Entscheidung 24) und es im Docstring und im Journal festzuhalten.

## Hinweis

### H1: Nach der Tagesmarke kann die Zahl bis zum nächsten Ereignis zu hoch stehen (Vermutung, nicht reproduziert)

**Fundstelle:** `milestones.py` `_handle_recorded` (Zeile ~296 ff.) und `_async_mark_day`, `capture.py` `_announce`.

**Beschreibung:** Die automatische Tagesmarke wird von **demselben** Ereignis `EVENT_HISTORY_UPDATED` ausgelöst, auf das auch das Panel mit einem Neuladen der Liste reagiert, und sie setzt das Tag über mehrere Executor-Schritte erst danach. Nach dem Anlegen feuert `milestones.py` kein eigenes Ereignis. Liest das Panel die Liste vor dem Tag, zeigt das Chip beim ersten Speichern eines Tages die Zahl vor der Marke (zum Beispiel 9) statt danach (1), bis das nächste Ereignis kommt oder die Seite neu geladen wird. Die Reihenfolge ist aus dem Code abgeleitet und nicht gemessen; ob sie wirklich so verläuft, zeigt nur ein echter Tageswechsel.

**Konsequenz:** Die Farbe stimmt (das Dashboard ist so oder so orange), nur die Zahl kann kurz zu hoch sein. Die Versionsliste im selben Panel hat dasselbe Alter, es ist also kein neues Muster.

**Vorschlag:** Nichts tun, oder als eigenes Ticket: `_async_mark_day` kündigt nach einer geschriebenen Marke erneut an. Nicht in diesem Ticket.

### H2: Die Prüfungen in `run_checks.py` beweisen auf dieser Prüfbank wenig über die Rechnung

**Fundstelle:** `tests/integration/run_checks.py` (neue Prüfungen in `run_remove_version`); Bericht, Abschnitt 5.

**Beschreibung:** Die Prüfung »taking the version away counts the changes in front of the next one« lief mit `0 vs 0`, die davor mit `0`: Auf dem Ziel-Dashboard der Bank sitzt schon eine andere Version auf dem neuesten Stand, deshalb ändert das Anlegen und Entfernen einer Version den Wert nie. Beide Prüfungen sind damit richtig, aber nicht unterscheidend: Eine Implementierung, die für dieses Dashboard immer 0 liefert, bestünde sie. Der Löschfall (`unversioned == 0` für das gelöschte Dashboard) ist dagegen echt und unterscheidend (ohne `else 0` käme `> 0`).

**Konsequenz:** Die Rechnung selbst ist durch die Python-Tests und meinen unabhängigen Vergleich abgedeckt, nicht durch `run_checks.py`. Kein Mangel, aber der Beweis liegt woanders, als der Plan nahelegt.

**Vorschlag:** Optional später eine unterscheidende Prüfung (Version auf einem älteren Stand anlegen und den erwarteten Wert dafür prüfen). Nicht nötig, um das Ticket zu schließen.

### H3: Die Zahl zählt auch Umbenennungen und Löschungen im Verlauf (stimmt mit der Historienliste überein)

**Fundstelle:** `store.py` `_touched` (Zeile ~454), `_count_unversioned`.

**Beschreibung:** Der Index ordnet einem Dashboard auch Commits zu, die nur dessen `meta/<key>.yaml` ändern (Umbenennungen) und seine Löschungen und Neuaufzeichnungen. Bei meinem Gegenrechner zeigte sich das: `dh-probe-check` meldet 7, eine Berechnung nur über `<key>.yaml` ergibt 5. Mit `meta/<key>.yaml` dazu steht die neueste getaggte Änderung genau an Position 7 (zwei Umbenennungen davor). Der Server ist damit richtig; mein Gegenrechner hatte die Definition zu eng gefasst.

**Konsequenz:** Die Zahl entspricht den Zeilen, die die Historienliste oberhalb der neuesten Version zeigt. Wer »Änderungen« als »Karten bearbeitet« liest, kann sich über einen Zähler wundern, der Umbenennungen mitzählt. Dazu passt der Hinweis des Plans, dass es aufgezeichnete Änderungen sind und keine Netto-Unterschiede.

**Vorschlag:** Nichts ändern. Beim Release in den Notizen kurz sagen, was der Zähler zählt.

### H4: Der Umsetzungsbericht und das Gerüst

**Beschreibung:** Gemini hat alles geliefert, was der Prompt verlangte (Status, Commits, Testläufe, Mutationsprüfung, Messzahlen, Containerlauf, Abweichungen »keine«, Anhaltepunkte »keine«, Aufwand). Aufwand: 08:53:16 bis 09:16:06, rund 23 Minuten; Token oder Kontingent: nicht ermittelbar (die Umgebung zeigt keine Zähler). Die Berichtsdatei liegt unversioniert neben dem Plan und gehört nicht in den Commit-Verlauf des Tickets. Die Commits tragen keine Attributionszeile, so wie der Plan es vorsah.

**Konsequenz / Vorschlag:** Keine Änderung nötig.

## Offen (kann nur der Nutzer)

Sichtprüfung im Browser (Aufgabe 3, Schritt 4): oranger Streifen und Chip in Simple und Advanced, Streifen bleibt bei Auswahl orange, nach »Save this as a version« verschwinden beide ohne Neuladen, schmales Fenster unter 560 px, dunkles Theme. Diese Review hat sie nicht durchgeführt.

## Urteil

**Umsetzbar nach einer Entscheidung zu W1.** Die Umsetzung folgt dem Plan wörtlich, beide Commits sind einzeln gegen ihren eigenen Baum grün, die Tests sind aussagekräftig (7 von 8 Mutationen erkannt, die achte durch `run_checks.py` abgedeckt), und die Zahlen stimmen mit einer unabhängigen Berechnung gegen die echte Testinstanz überein. Vor einem Merge sollte der Nutzer W1 entscheiden (Best-Effort für die Zähler oder bewusst streng), und die Sichtprüfung steht aus. Alles andere sind Hinweise ohne Änderungsbedarf in diesem Ticket.

---

## Nachtrag: nach dem Review geändert (2026-10-01)

Dieses Review bewertet den Stand der Commits `982cf95` und `51dee57`. Danach kamen zwei Commits dazu, die zwei Dinge dieses Reviews betreffen. Der Text oben bleibt unverändert, so wie er geschrieben wurde.

### W1 neu eingeordnet und behoben (`b7206a3`)

Der Nutzer wies darauf hin, dass das Panel während eines `forget` ohnehin gesperrt ist. Das stimmt für den Hauptpfad (`panel.js` `_onForgetting`, `_forgetting`): Der Tab, der das `forget` startet, stellt bis zur Rückkehr keine Listenabfrage, und ein zuschauender Tab verschluckt die Fehler seiner stillen Aktualisierungen. Übrig bleiben zwei Randfälle (eine Seite, die mitten in einem `forget` neu geladen wird, und ein nach einem Absturz liegen gebliebener Checkpoint). W1 gehört deshalb nicht unter »Wichtig«, sondern unter »Hinweis mit Entscheidung«. Entschieden wurde für den Best-Effort-Zähler: `dashboard_listing` fängt den `RuntimeError` des Rennschutzes ab und antwortet mit den Namen und ohne Zähler, die Liste lädt also weiter. Der Test `test_an_unfinished_forget_costs_the_listing_its_counts_not_its_names` war vor der Änderung rot (`RuntimeError` aus der Liste) und ist danach grün.

### Die Regel selbst war falsch und ist geändert (`fe87406`)

Beim Ansehen der Testinstanz fiel dem Nutzer auf, dass links viele Dashboards orange waren, während die Karte »Right now« rechts blau stand (»same state as v0.0.4«). Ursache: Der Plan und dieses Review gingen davon aus, dass Streifen und Karte »dieselbe Frage« stellen. Das stimmt nicht. Die Karte ist blau, wenn der aktuelle Inhalt **byte-gleich dem einer Version** ist, auch nach Änderungen dazwischen (Karte hinaus und wieder zurück, Rollback). Die ursprüngliche Regel fragte nur, ob die **neueste Änderung** ein Tag trägt. Auf der Prüfbank waren 18 von 29 markierten Dashboards von dieser Art.

Die Regel lautet jetzt: Ein Dashboard, dessen neuester Stand byte-gleich dem Stand einer **seiner eigenen** Versionen ist, zählt 0. Verglichen wird per Blob-ID, jede Abfrage wird gecacht. Nach der Änderung (alle selbst gemessen, im Container und mit `git` gegengerechnet):

| Messung | Ergebnis |
|---|---|
| Markierte lebende Dashboards der Prüfbank | 11 statt 29 (von 51) |
| Server gegen unabhängige Berechnung per `git` | 51 von 51 gleich, 0 Abweichungen |
| Kosten im HA-Container (12.029 Commits, 704 Tags) | erster Lauf der Blob-Abfragen 104 ms, jeder weitere 30 ms |
| Tests | 1139 passed, 2 skipped; Ratsche und `lint-imports` grün |

**Warum die vier Plan-Reviews und dieses Review das nicht fanden:** Alle prüften den Plan gegen den Code und den Code gegen den Plan. Keiner verglich das Verhalten mit dem, was das Panel an anderer Stelle sagt (die Karte), und keiner betrachtete einen Bestand mit Rollbacks. Gefunden hat es die Sichtprüfung an einem echten, gewachsenen Bestand. Für künftige Reviews: Wo eine neue Anzeige eine bestehende Aussage des Panels wiederholt, gehört der Vergleich beider an echten Daten zur Prüfung.

### Urteil nach den Nachträgen

**Umsetzbar.** W1 ist behoben, die Regel stimmt jetzt mit der Karte überein. Offen: Die Sichtprüfung im Browser mit der neuen Regel (Simple und Advanced, Auswahl, Speichern, schmales Fenster, dunkles Theme) und ein Lauf von `run_checks.py` im Testcontainer für die zwei Folgecommits, den ich nicht wiederholt habe.

ENDE DES REVIEWS
