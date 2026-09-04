# Komplettes Review vom 2026-09-03

Stand: `main` bei `bb1b38c` (»Say which buttons a row actually shows«), Arbeitsbaum sauber. Tests: 229 bestanden, 0 übersprungen (echter Storage vorhanden).

Vorgehen: eigene Lektüre aller Python-Module; drei parallele Reviewer für Kernmodule, HA-Seite und Panel/Integrationsskripte; jeder gewichtige Befund am Code reproduziert oder im laufenden Testcontainer (`docker exec -i dashboard-history-test python3`, HA 2026.8.3) gegen die echte HA-Quelle geprüft.

Die harten Regeln der Spec sind eingehalten: kein `git`-Systemaufruf, kein `import homeassistant` in `yaml_io`, `analyze`, `restore`, `versions`, `confirm` vor jedem Dashboard-Schreibvorgang, nur Verschwundenes wird zurückgeholt.

## CRITICAL

### C1 – Die Dienste prüfen keine Admin-Rechte

`services.py` registriert alle Dienste mit `hass.services.async_register`. Die WebSocket-Befehle tragen `require_admin`, die Dienste nicht. Verifiziert in HA 2026.8.3: `websocket_api.commands.handle_call_service` enthält keine Berechtigungsprüfung. Jeder angemeldete Nicht-Admin kann damit `restore_state` mit `confirm: true` aufrufen, über die Vorschau den vollständigen Dashboard-Inhalt lesen und mit `forget` unwiderruflich Historie löschen – obwohl Nicht-Admins in HA sonst keine Dashboards bearbeiten dürfen.

Fix: `homeassistant.helpers.service.async_register_admin_service` (kennt `supports_response`, verifiziert). Aufrufe ohne Nutzer (Automationen) bleiben erlaubt.

## WARNING

### W1 – Horizont von 1000 Commits im Store

`store.list_all_dashboards(limit=1000)` und `store.previous_change` (über `list_changes(key, limit=1000)`) laufen höchstens 1000 Commits zurück. Reproduziert: nach 1005 Speicherungen anderer Dashboards verschwindet ein gelöschtes Dashboard aus `list_all_dashboards` (und damit aus dem Panel und aus `forget`), und `previous_change` liefert für ältere Revisionen `None` – Undo und Explain behaupten dann »first recorded state«. Bei einem Commit pro Speichervorgang ist das in Monaten erreicht.

### W2 – Blockierende Arbeit auf dem Event-Loop

Nur `async_undo_change` lagert Diff und Erklärung in den Executor aus. `async_restore_deleted`, `async_restore_state`, `async_deleted_since` rufen `load`, `find_removed`, `_diff`, `explain_effect` direkt im Loop, `async_history` ruft `dump(live)`. Der Messwert im Code: 78 ms je Matching bei 1200 Karten.

### W3 – README beschreibt die Löscherkennung falsch

README, Abschnitt »If a whole dashboard is deleted«: »recorded the next time Home Assistant starts«. Seit dem Lauschen auf `panels_updated` (capture.py) geschieht das binnen `RECONCILE_DELAY` = 10 s; `run_checks.py` prüft genau das.

### W4 – Wettlauf beim Aufklappen einer Zeile im Panel

`panel.js`, `_expand`: Nach dem `await` wird nicht geprüft, ob `_open` noch dieselbe Revision ist. Zwei schnelle Klicks zeigen die Details der falschen Zeile; das boolesche `_busy` erlischt zu früh.

### W5 – Ein Fehler stoppt alle weiteren Löscherfassungen

`capture._async_record_deletions`: kein try pro Dashboard. Wirft `mark_deleted` beim ersten, bleiben die übrigen unerfasst.

### W6 – Änderungsmeldung widerspricht der Erklärung bei View-Umbenennung

`change_message` bei umbenannter leerer View: »no card changes«; mit Karten: »1 removed, 1 added«. `explain_change` sagt korrekt »the whole view … was deleted / added«. Ursache: `summarize` zählt Views nur über ihre Karten.

### W7 – Keine Übersetzungen für den Config-Flow

Weder `strings.json` noch `translations/`. Der Einrichtungsdialog zeigt rohe Schlüssel; hassfest würde das bei einer HACS-Veröffentlichung anmerken.

## NIT

- Halbzustand bei Wiederherstellung eines gelöschten Dashboards, wenn `async_save_config` nach `async_create_dashboard` fehlschlägt; erneuter Aufruf repariert, die Meldung sagt das nicht.
- `limit` ohne Bereichsprüfung in Dienst und WebSocket; `services.yaml` verspricht 1–500.
- Leerer Titel bei `create_version` möglich.
- `plan_undo`/`sole()`: für eine hinzugefügte, inzwischen gelöschte Karte lautet die Begründung »was changed again«; auf der Gegenseite wird eine bereits zurückgekehrte Karte still übersprungen.
- Docstring-Widerspruch: `_file_for` verspricht, Legacy-Schlüssel mit Schrägstrich blieben löschbar; `list_all_dashboards` filtert `/` heraus, `_tree_without` kennt zwei Ebenen.
- `async_unload_entry` entfernt weder Dienste noch WebSocket-Befehle; Reload registriert statische Pfade doppelt.
- Ungetestet: YAML-1.1-Doppelgänger (`yes`, `on`, `1e3`) im Roundtrip.
- Unerreichbar, aber ungeschützt: `_meta_detail({}, …)`, negative Indizes in `_standing_there`, falsy Werte in `_weak_key`.
- `Repo`-Handles aus `_repo()` werden nie geschlossen.
- README: zweimal `### Services`. Testbench-Passwort in `run_checks.py` ohne erklärenden Kommentar.

## PRAISE

- Zwei getrennte Locks in `capture.py`, mit Messwerten begründet.
- Pfadsicherheit in zwei unabhängigen Schichten (`is_safe_key`, `_file_for`).
- `_command`-Fabrik in `websocket_api.py`: `require_admin` genau einmal, strukturell nicht vergessbar.
- `escape()` im Panel vollständig und lückenlos angewendet; keine XSS-Lücke.
- Bekannte Grenzen sind als Tests fixiert; Kommentare nennen konkrete Fehlerszenarien.

## Nachtrag 2026-09-04: Umsetzung

Behoben wurden C1 und W1–W7, testgetrieben, wo pytest hinreicht. Die Tests standen jeweils zuerst und schlugen aus dem erwarteten Grund fehl.

| Befund | Änderung | Test |
| --- | --- | --- |
| C1 | `services.py` und `debug_snapshot` registrieren über `async_register_admin_service` | `run_checks.py`: neuer Abschnitt `run_permissions` legt einen Nicht-Admin an, meldet ihn an, erwartet HTTP 401 für `history` und `restore_state`, HTTP 200 für den Admin, löscht den Nutzer wieder |
| W1 | `list_all_dashboards` ohne Obergrenze, `previous_change` über `list_changes(limit=None)`, `forget`-Zählung ohne Kappung | `test_store.py`: zwei Tests mit 1005 Roh-Commits (unter einer Sekunde, direkt in den Object-Store geschrieben) |
| W2 | `operations.py`: `_removed_since`, `_plan_undo`, `_same_as_live`, `_explain_texts` und `_preview` laufen im Executor; `load`/`dump` von Dashboard-Texten ebenso | nur über `run_checks.py` erreichbar |
| W3 | README-Absatz zur Löscherkennung: binnen etwa zehn Sekunden, kein Neustart | – |
| W4 | `panel.js`: `_expand` verwirft ein Ergebnis, wenn `_open` inzwischen eine andere Revision ist; `_busy` ist ein Zähler | `test_panel_behaviour.py`: führt `panel.js` in Node aus (DOM-Stub, `_call` durch handgesteuerte Promises ersetzt); überspringt sichtbar ohne `node` |
| W5 | `capture._async_record_deletions`: try pro Dashboard | nur über `run_checks.py` erreichbar |
| W6 | `Summary` bekommt `views_added`/`views_removed`; verschwundene Views zählen als eine View, nicht als ihre Karten; `change_message` sagt »1 view removed« | `test_analyze.py`: vier Tests |
| W7 | `strings.json` und `translations/en.json` für Schritt `user` und Abbruch `already_configured` | `test_integration_files.py` |

**Nebenbefund aus dem Prüflauf.** Während `run_checks.py` lief, lief parallel ein zweiter Lauf aus einer Codex-Sitzung gegen denselben Container. Dessen `forget` löschte und schrieb alle Tags neu, und ein `history`-Aufruf in genau diesem Fenster fiel mit `KeyError` auf ein Tag-Ref, das `as_dict` noch listete und `refs[...]` nicht mehr fand. Das ist die NIT »Lesezugriffe sind während `forget` nicht gesperrt« in Aktion. `list_versions` und `_raw_tags` überspringen ein solches Ref jetzt, wie dulwichs `as_dict` selbst; Test in `test_store.py` mit einem Phantom-Ref.

**Zweiter Nebenbefund.** Die Prüfung »a deletion is explained rather than reported as an error« nahm das erste gelöschte Dashboard der Liste. Seit die Liste nicht mehr nach 1000 Commits endet, ist das `dh-empty-review`, eine Sonde ohne Views, für die »cannot be described in terms of cards« die Wahrheit ist. Die Prüfung fragt jetzt jedes gelöschte Dashboard: keines darf mit einem Fehler antworten, mindestens eines muss die verlorene View nennen.

**Dritter Nebenbefund.** Die Prüfung »a rename is recorded and named« schlief nach der Umbenennung fest 15 s. Der Abgleich startet 10 s danach und braucht auf dieser Bank für 18 Dashboards rund 10 s unter dem Schreib-Lock (neue Debug-Zeile `Recording (reconcile): looked at …, wrote …` in `capture._async_write`), sodass der Umbenennungs-Commit mal knapp vor, mal knapp nach der Prüfung landete – ein Fehlschlag in drei Läufen. Die Prüfung pollt jetzt bis zu 45 s (`_wait_for_newest`). Der Code selbst war korrekt.

Daraus eine Beobachtung, nicht umgesetzt: `capture._write_one` ruft je Dashboard `_has_history` (ein `notes_list` plus ein pfadgefilterter Walk) nur, um zu entscheiden, ob `read_at(HEAD)` gelesen wird – das aber ohnehin `None` liefert, wenn nichts da ist. Der Aufruf ist redundant und der teurere Teil des Abgleichs. Ein Kandidat für die nächste Runde.

**Ergebnis der Prüfläufe.** pytest: 241 bestanden, 0 übersprungen. `run_checks.py` gegen HA 2026.8.3 im Container: 104 von 104, darunter die drei neuen Berechtigungsprüfungen.

Nicht angefasst (NITs): siehe oben. Insbesondere die fehlende Abmeldung in `async_unload_entry` und die Bereichsprüfung für `limit`.

## Erneutes Review 2026-09-04

Ein Reviewer hat den uncommitteten Diff gegen dieses Dokument geprüft und für jeden Punkt einzeln entschieden: C1 und W1–W7 gelten als behoben, der Nebenbefund zu verschwundenen Tag-Refs als korrekt umgesetzt. Urteil: Freigeben.

Zwei NITs aus dem erneuten Review, beide anschließend noch behoben:

- `_pad_history` in `test_store.py` schrieb fest auf `refs/heads/master`; jetzt folgt es `HEAD`, wie `_point_head` im Store.
- `async_undo_change` parste `before_text` zweimal (für den Plan und für `equals_state_before`); `_plan_undo` liefert das geparste `before` jetzt mit.

Danach: pytest 241 bestanden. Der Executor-Umbau in `async_undo_change` ist durch `run_checks.py` (Abschnitt »Eine Aenderung gezielt zuruecknehmen«, 104/104 im Lauf davor) abgedeckt; die letzte Änderung dort betrifft nur die Rückgabeform von `_plan_undo`.

Offen bleiben die NITs des ursprünglichen Reviews und die Beobachtung zu `_has_history` im Nachtrag. Nichts davon ist committet; das entscheidet der Nutzer.

## Prüfung des Codex-Reviews 2026-09-04

Ein paralleles Review aus einer Codex-Sitzung meldete fünf offene Punkte. Alle fünf sind am Code nachvollzogen; die Einordnung weicht teils ab.

| Codex | Befund | Bewertung | Stand |
| --- | --- | --- | --- |
| Hoch | `forget("foo")` löscht `foo/bar/v1.0.0` und `list_versions("foo")` listet es, weil `startswith("foo/")` den Legacy-Schlüssel `foo/bar` als Namensraum von `foo` liest | Reproduziert. Vorbestehend, nicht durch die Umsetzung eingeführt. Trifft nur Schlüssel mit Schrägstrich, die `is_safe_key` seit ihrer Einführung abweist und die `list_all_dashboards` nicht einmal listet (Docstring-Widerspruch, im ursprünglichen Review als NIT). Irreversibel, darum WARNING statt NIT; Fix billig: das Ref gehört zu `key`, wenn der Rest nach `key/` keinen weiteren `/` enthält | behoben: `_owns()` in `store.py`, genutzt von `_rewrite_tags` und `list_versions`; zwei Tests |
| Mittel | `OSError` aus `store.read_at` in `_keep_the_live_state` bricht die Wiederherstellung ab | Korrekt, der Verifikationszugriff steht außerhalb des `try` und widerspricht dem Docstring (»it never refuses«). Vorbestehend. NIT bis WARNING | behoben: Prüfung im `try`, Fehler wird zur Notiz |
| Mittel | `current={}` wird vor dem Überschreiben nicht gesichert (`if not current`) | Korrekt, aber konstruiert: ein leeres `{}` entsteht nur über die API, die Oberfläche schreibt `{"views": []}`. Die Aufrufer verschleifen zudem `None` und `{}` per `or {}`. NIT | behoben: Aufrufer reichen den rohen Stand (`None` oder Dict) durch, `_keep_the_live_state` unterscheidet `None` von `{}` |
| Mittel | Panel: verspäteter Fehler eines veralteten Aufrufs setzt den Fehlerbanner; A→B→A lässt die erste A-Antwort die zweite überschreiben | Korrekt, beides. `_guard` schreibt `_error` vor dem Stale-Check, und die Revisionsprüfung unterscheidet zwei Aufrufe derselben Zeile nicht. W4 damit nur teilweise behoben; Fix: Aufrufgeneration in `_guard`, die Daten und Fehler zuordnet | behoben: `_guard(work, stillWanted)` zeigt einen Fehler nur, wenn der Aufruf noch gewollt ist; `_select` und `_expand` führen Tickets; zwei weitere Node-Tests |
| Mittel | `dashboard_history/dashboards` dauert 15,56 s auf 1.457 Commits / 39 Schlüsseln | Reproduziert: 0,67 s für den unbegrenzten Walk, 8,27 s für 22 serielle `last_known_meta`-Aufrufe (je ein pfadgefilterter Walk plus `notes_list`). Folge der W1-Korrektur: die Liste zeigt jetzt alle gelöschten Dashboards, und jedes kostet einen eigenen Walk. WARNING, wichtigster der fünf Punkte. Fix: die letzten Metadaten gelöschter Dashboards im selben Walk einsammeln (der alte Blob von `meta/<key>.yaml` an dem Commit, der ihn entfernt) | behoben: `store.survey()` liefert Namen und letzte Metadaten aus einem Walk, `async_dashboards` nutzt es; `list_all_dashboards` ist ein Wrapper; drei Tests |

Codex' Gesamtlauf mit 102/104 deckt sich mit dem hier dokumentierten Debounce-Fall der Lebenszyklus-Prüfung; die Prüfung pollt inzwischen.

**Beim Prüflauf danach gefunden:** eine Speicherung während des Startdurchlaufs ging verloren. `capture.async_start` erfasste erst alle Dashboards (rund 20 s auf der Bank) und registrierte die Listener erst danach; eine Speicherung in diesem Fenster war weder im Durchlauf, der die Konfigurationen schon gelesen hatte, noch hörte sie jemand. Reproduziert, weil `run_checks.py` unmittelbar nach dem Neustart eine Karte entfernte. Reihenfolge jetzt umgekehrt: erst hören, dann der Durchlauf; die gehörte Speicherung wartet hinter dem Schreib-Lock und wird danach erfasst. Die Prüfung »the deletion was recorded with a summary« pollt jetzt statt drei Sekunden zu schlafen, und die Vorschau-Prüfung stürzt bei einer Fehlerantwort nicht mehr mit `KeyError` ab. Nebenbei: Die WSL-Uhr sprang während der Arbeit um fünf Stunden; das ist nur für die Lesbarkeit der Logs relevant.

Die Prüfung »no bogus 'changed outside Home Assistant' on a first run« fragte alle fünfzig Einträge; die berechtigte Meldung zur verlorenen Speicherung hätte sie wochenlang scheitern lassen. Sie fragt jetzt nur den neuesten Eintrag, den einzigen, den ein Startdurchlauf schreibt.

**Ergebnis nach den Codex-Punkten.** pytest: 248 bestanden, 0 übersprungen. `run_checks.py` gegen HA 2026.8.3: 104 von 104. Weiterhin nichts committet.

## Aufräumen 2026-09-04 (`/simplify`)

Vier Reviewer (Wiederverwendung, Vereinfachung, Effizienz, Ebene) über den uncommitteten Diff; die Befunde dedupliziert und umgesetzt:

- **Store.** `_each_tag(repo)` ist der eine Tag-Iterator mit dem KeyError-Überspringen; `_raw_tags` und `list_versions` nutzen ihn. `previous_change` läuft vom Commit selbst aus, pfadgefiltert, zwei Einträge tief, statt die ganze Dashboard-Historie zu materialisieren; ein fremder Commit ergibt weiterhin `None` (Test). `matching_revisions` vergleicht Blob-Ids statt fünfzig Blobs zu lesen. `survey` ist in `_walk_history` (ein Walk) und eine HEAD-Lesephase geteilt, liefert jetzt auch `live` und die Metadaten lebender Dashboards, und ist nach HEAD gecacht, weil das Panel bei jeder erfassten Änderung fragt; `list_all_dashboards` nimmt nur den Walk. `last_known_meta` ist entfallen, `async_restore_state` fragt `survey`.
- **Operations.** `yaml_io.load_state` entscheidet an einer Stelle, was ein leerer oder fehlender Text bedeutet (fünf Schreibweisen vorher). `_preview` gibt den Dump des Live-Stands mit zurück, `_keep_the_live_state` nimmt den Text und dumpt nicht noch einmal. `restore_deleted` und `restore_state` brauchen je einen Executor-Sprung (`_reinsertion`, `_target_and_preview`). `async_history` holt Änderungen und Versionen nebeneinander. `async_dashboards` hat keinen `await` mehr in der Schleife.
- **Dienste.** `debug_snapshot` steht in der Tabelle von `services.async_register`; jede Regel der Tabelle erreicht ihn ohne zweite Stelle.
- **Erfassung.** Nur der Speicher-Listener steht vor dem Startdurchlauf; der Panel-Listener kommt danach, damit der Start-Burst von `panels_updated` keinen zweiten vollen Durchlauf hinter den ersten stellt.
- **Panel.** Ein Mechanismus statt drei: `_claim(slot)` vergibt Tickets für die Slots `changes` und `detail`; `_select`, `_expand` und `_refresh` nutzen ihn, das Schließen einer Zeile beansprucht den Slot ebenfalls.
- **Prüfskript.** `_wait_for(fetch, accept, seconds)` ist die eine Schleife; darauf `_wait_for_newest`, `_wait_for_history_to_move`, `_wait_for_store_entry`, `_wait_for_store_absence`. Alle Warte-dann-lesen-Stellen nach einem Abgleich pollen jetzt; nur die Beruhigungspause am Ende bleibt. `_exchange_code` tauscht den Auth-Code an einer Stelle.
- **Tests.** `conftest.PACKAGE` statt vier Pfadausdrücken; Node-Vorspann und -Runner einmal; Kommentare, die Messwerte aus den Docstrings wiederholten, verweisen jetzt dorthin.

Bewusst nicht umgesetzt: den Startdurchlauf aus `async_setup_entry` in eine Hintergrundaufgabe zu lösen (ändert das Fehlerverhalten des Setups; eigene Entscheidung), einen inkrementellen Walk ab dem letzten HEAD (der Cache reicht, solange HEAD zwischen zwei Panel-Anfragen selten wechselt), `versions.owner()` als gemeinsamer Namensraum-Begriff (drei Stellen, alle klein).

**Beim Prüflauf nach dem Aufräumen gefunden, und der schwerste Fehler dieses Tages:** `forget` schrieb die Commits um und entfernte die Objekte, ließ die zwei Dateien des Dashboards aber im Git-Index und im Arbeitsbaum stehen. Der nächste Commit irgendeines Dashboards baute seinen Tree aus diesem Index und verwies damit auf Blobs, die es nicht mehr gab: `survey` und jeder Lesezugriff auf diesen Pfad brachen mit `KeyError` ab, und das gelöschte Dashboard stand wieder in HEAD. Ausgelöst wird das, wenn `forget` läuft, bevor der Rekorder die Löschung geschrieben hat – und genau das erlaubt die Operationsschicht, weil sie Home Assistant fragt, ob das Dashboard weg ist, und nicht den Rekorder, ob die Löschung erfasst ist. Vorbestehend seit `forget`; sichtbar wurde es erst, weil die Prüfung nach dem Aufräumen früher als vorher forderte. `_drop_from_index` räumt jetzt beides mit auf; Test in `test_store.py`. Die Prüfung wartet nun auf die erfasste Löschung, bevor sie vergisst. Das Bench-Repository trug den Schaden schon und wurde im Container repariert.

**Ergebnis nach dem Aufräumen.** pytest: 251 bestanden, 0 übersprungen. `run_checks.py` gegen HA 2026.8.3: 104 von 104.
