# Design: Benannte Einstellungen gezielt zurücknehmen

**Datum:** 2026-09-24
**Status:** Vom Nutzer bestätigt am 2026-09-24 – alle drei Punkte unter »Entscheidungen« abgesegnet. Bereit zur Umsetzung, sobald Vorhaben L gebaut ist
**Vorhaben:** M aus dem Abschnitt »Reihenfolge der Vorhaben« der Haupt-Spec
**GitHub-Issue:** [#28](https://github.com/PPP01/ha-dashboard-history/issues/28)
**Integration:** `dashboard_history`
**Bindend bei Widerspruch:** die Haupt-Spec (`2026-08-30-dashboard-history-design.md`), insbesondere Entscheidung 4, 11 und 15

## Kontext & Ziel

Die gezielte Rücknahme (Entscheidung 15) kennt nur Karten und ganze Ansichten. Eine Änderung, die ausschließlich etwas **außerhalb der Kartenlisten** anfasst – `show_clock_card: false` im `strategy:`-Block, das `icon` einer Ansicht, ihre `visible`-Liste –, ergibt eine leere Zuordnung, und `plan_undo` antwortet »this change did not alter any cards«. Die Erklärung darüber sagt »This change cannot be described in terms of cards«, die Zeile im Verlauf »no card changes«. Alle drei Sätze sind wörtlich wahr und helfen niemandem.

Der Grund, warum Karten den ganzen Aufwand aus Entscheidung 4, 14 und 15 brauchen – sie tragen keine Kennung –, gilt hier nicht. **Eine benannte Einstellung ist durch ihren Namen bestimmt.** `strategy.show_clock_card` ist eine Adresse, die in jedem Stand dasselbe meint. Es braucht keinen Fingerabdruck, keine Ähnlichkeit, keine Eindeutigkeitszählung, sondern eine einzige Gleichheitsprüfung: Steht an dieser Adresse heute noch, was die Änderung dort hinterlassen hat?

### Verifizierte Ausgangslage (2026-09-24, am Quelltext und an der Prüfbank nachgelesen)

| Feststellung | Beleg |
|---|---|
| `match_cards` sieht nur `view["cards"]` und `section["cards"]` | `analyze.py`, `card_containers` |
| Die frühe Verweigerung greift, wenn weder Karten noch ganze Ansichten noch ein Typwechsel vorliegen | `plan_undo`, seit #32 mit `type_changed` |
| Eine Änderung ohne Karten ergibt `_NOT_IN_CARDS` in der Erklärung und »no card changes« im Verlauf | `_explain`, `change_message` |
| Dashboard-Wurzel in der Prüfbank (13 Dashboards mit Ansichten, 1 Strategie-Dashboard) | Schlüssel `views` (13), `title` (1), `strategy` (1), `kiosk_mode` (1), `button_card_templates` (1) |
| Ansichtsschlüssel in der Prüfbank (70 Ansichten) | `title` 70, `icon` 57, `cards` 56, `type` 50, `visible` 44, `badges` 33, `path` 62, `sections` 27, `max_columns` 25, `subview` 25, `theme` 3, `layout` 2, `back_path` 1 |
| Das Panel überschreibt jede Erklärungsgruppe fest mit »In the view …« | `panel/render.js`, `renderPlain` |
| Titel und Symbol eines Dashboards (Seitenleiste) liegen **nicht** in der Konfiguration, sondern in `meta/` | Entscheidung 15, »Vier Grenzen«; `_meta_detail` |

## Nicht-Ziele (YAGNI)

- **Keine Einstellungen von Sections.** Eine Section hat keine Adresse außer ihrer Position (Entscheidung 16, nie gebaut). Ändert eine Änderung nur `column_span`, fällt sie schon an der frühen Bedingung (»did not alter any cards«); ändert sie daneben Karten, sieht die Section-Prüfung umgebaute Sections und verweigert – beides bleibt so.
- **Keine anonymen Listen als Einzelstücke.** `badges:` ist Vorhaben N (#29) und wird hier ausdrücklich ausgeschlossen, nicht behelfsweise als Ganzes behandelt.
- **Kein `meta/`.** Seitenleistentitel und -symbol eines Dashboards schreibt kein Rücknahmeweg (Entscheidung 15). Unverändert.
- **Kein generisches Zusammenführen.** Geprüft wird Gleichheit an einer Adresse, nicht ob sich zwei Änderungen an verschiedenen Unterschlüsseln »vertragen«.

## Entwurf

### 1. Was eine Einstellung ist

Zwei Arten von Behältern, beide mit Namen statt Position:

- **das Dashboard selbst** – die Wurzel der Konfiguration, ohne `views`;
- **jede Ansicht**, die in beiden verglichenen Ständen unter demselben Schlüssel steht (Pfad, sonst Position – `_views_by_key`) – ohne `cards`, `sections`, `badges`, `path` und `type`.

Warum diese fünf nicht: `cards` und `sections` sind die Kartenwelt. `badges` ist Vorhaben N. `path` *ist* der Schlüssel der Ansicht; eine Pfadänderung ist schon heute »Ansicht entfernt, Ansicht hinzugefügt«. `type` ist seit #32 eine Konvertierung und wird dort bewusst verweigert, nicht als gewöhnliche Einstellung zurückgeschrieben.

Innerhalb eines Behälters ist eine **Einstellung** ein Pfad aus Schlüsseln. Verglichen wird rekursiv, aber nur dort, wo **beide** Seiten ein Dict sind; überall sonst ist der Wert an dieser Stelle ein Blatt, auch wenn er eine Liste oder ein Dict ist. `visible: [{user: …}]` ist also ein Blatt und wird als Ganzes verglichen; `strategy.show_clock_card` ist ein Blatt unterhalb des Dicts `strategy`. Wird ein ganzer Block entfernt oder hinzugefügt, ist der Block selbst das Blatt (`strategy` entfernt), nicht jeder seiner Unterschlüssel.

Daraus folgt eine Eigenschaft, auf der die Rücknahme ruht: **Jeder Vorfahr eines Blattes existiert in beiden Ständen als Dict.** Sonst hätte die Rekursion dort nicht abgestiegen.

Eine Einstellungsänderung ist eines von drei Dingen: gesetzt (vorher nicht da), entfernt (nachher nicht da), geändert (beide da, verschieden).

### 2. Wie sie zurückgenommen wird

Für jede Einstellungsänderung `vorher → nachher` fragt `plan_undo` den heutigen Stand an derselben Adresse:

| Heute an der Adresse | Rücknahme |
|---|---|
| genau `nachher` (bzw. nicht vorhanden, wenn `nachher` »nicht vorhanden« ist) | auf `vorher` setzen bzw. entfernen |
| genau `vorher` | nichts tun – dieser Teil ist bereits zurück (wie die gelöschte Karte, die wieder da ist) |
| etwas Drittes | **ganze Rücknahme verweigert:** `the setting "…" was changed again after this` |
| ein Vorfahr fehlt oder ist kein Dict mehr | **verweigert:** `the setting "…" no longer has the "…" block it belonged to` |
| die Ansicht fehlt | **verweigert:** `the view "…" is no longer on the dashboard, so its setting "…" cannot be taken back` – ein eigener Satz; der vorhandene der Ansichtsprüfung spricht vom Entfernen einer hinzugefügten Ansicht und passt nicht (Review 2026-09-24, K7) |

Das ist Entscheidung 15 in ihrer einfachsten Form: dieselbe Frage »steht noch da, was die Änderung hinterlassen hat«, nur dass die Adresse hier ein Name ist und keine gezählte Fundstelle. »Alles oder nichts« gilt über Karten, Ansichten und Einstellungen hinweg: eine Verweigerung irgendwo verweigert den ganzen Undo.

Die Einstellungsänderungen gehen in die frühe Bedingung von `plan_undo` ein – dieselbe Stelle, an der #32 den Typwechsel eintragen musste, und aus demselben Grund: Ohne das würde »did not alter any cards« vor jeder weiteren Prüfung zuschlagen.

Die Schutzprüfungen danach bleiben in ihrer Reihenfolge. `_positions_lie` gilt auch hier – eine Einstellung einer pfadlosen Ansicht ist nur so gut adressiert wie die Ansicht selbst. Die Section-Prüfung betrifft Einstellungen nicht: Nach Vorhaben L blockiert eine seither verschobene Section nur noch Einsetzungen von Karten. **Deshalb steht M hinter L.** Vor L würde jede Section-Verschiebung irgendwo im Dashboard auch eine reine Einstellungsrücknahme verweigern – nicht falsch, aber unnötig.

### 3. Ein Schritt, der eine Einstellung schreibt

`UndoStep` bekommt zwei neue Arten, `kind="dashboard_setting"` und `kind="view_setting"`, mit `action="set"` oder `action="unset"`. Die Adresse ist der Schlüsselpfad (`location`), die Ansicht wird wie bei jedem anderen Schritt über `view_path`/`view_index` gefunden. Wie bei Kartenschritten reist mit, was heute dort erwartet wird – einschließlich der Möglichkeit »nichts«, die ein eigenes Feld braucht, weil `None` in YAML ein gültiger Wert ist (`theme: null`).

`apply_undo` wendet Einstellungsschritte **vor** allen anderen an. Sie verschieben keinen Index, und eine Ansicht, die über ihre Position gefunden wird, steht vor dem Entfernen ganzer Ansichten noch dort, wo der Plan sie gesehen hat. Jeder Schritt prüft vor dem Schreiben erneut, ob der erwartete Wert noch da ist – der Plan ist einen Augenblick älter als seine Anwendung (Entscheidung 15). Geschrieben wird eine tiefe Kopie des Wertes; ein `unset`, der einen Block leer zurücklässt, lässt den leeren Block stehen, weil `vorher` ihn so hatte (die Rekursion stieg nur ab, weil beide Seiten ein Dict waren).

`restore.py` bleibt ohne Laufzeitimport von `analyze` (siehe dessen Kopf); die paar Zeilen zum Laufen entlang eines Pfades stehen dort eigenständig.

### 4. Wörter

**Erklärung.** Jede Einstellungsänderung wird ein `Entry` mit `what="setting"` und den vorhandenen Arten `added` / `removed` / `edited`, damit die bestehende Gestaltung (`style.js` hebt »removed« und »added« hervor) und die Beruhigungszeile (»Nothing on this dashboard is deleted«) ohne Sonderfall stimmen – eine entfernte Einstellung ist etwas Entferntes. Beschriftung ist der Pfad mit Punkten (`strategy.show_clock_card`).

| | Vergangenheit (`explain_change`) | Zukunft (`explain_effect`) |
|---|---|---|
| gesetzt | `the setting "icon" was set to "mdi:home"` | `the setting "icon" comes back as "mdi:home"` |
| entfernt | `the setting "theme" was removed` | `the setting "theme" will be removed` |
| geändert | `the setting "max_columns" was changed from 3 to 4` | `the setting "max_columns" goes back to 4` |

Werte werden nur gezeigt, wenn sie kurz sind: Wahrheitswerte, Zahlen, `null`, Zeichenketten (in Anführungszeichen, gekürzt wie Kartenbeschriftungen). Listen und Dicts werden nicht ausgeschrieben – dann heißt es nur `was set` / `was changed`; der Diff darunter zeigt den genauen Wert, wie immer (Entscheidung 11).

**Reihenfolge in einer Ansichtsgruppe:** Konvertierung (#32), dann Einstellungen, dann Karten.

**Dashboard-Einstellungen** bekommen eine eigene Gruppe vor allen Ansichten. `ViewChanges` erhält dafür ein Feld `scope` (`"view"` oder `"dashboard"`), `_as_dict` reicht es durch, und `renderPlain` schreibt für `"dashboard"` »On the dashboard itself« statt »In the view …«. Ohne das stünde »In the view Dashboard« über einer Einstellung, die keine Ansicht hat. Das Feld ist additiv; der Dienst `explain` und der Bericht bekommen es mit, ohne dass ein bestehendes Feld seine Bedeutung ändert.

**Verlaufszeile.** `change_message` bekommt einen Teil `N setting(s) changed` – ein Teil für alle drei Arten, damit die Zeile nicht zur Aufzählung wird. `Summary` bekommt `settings`. Die Zählgrammatik `_COUNT` wird **im selben Zug** erweitert; sie steht absichtlich neben `change_message`, und ein Wort, das dort fehlt, ließe `_counts` die ganze Zeile als »keine erzeugte Nachricht« lesen. `message_adds` bleibt unberührt: eine gesetzte Einstellung ist kein »added« im Sinne der Put-back-Falle, weil Put back Einstellungen nie zurückholt.

Bereits geschriebene Verlaufszeilen behalten ihr »no card changes«; sie stehen in Commits und werden nicht umgeschrieben.

## Fehler- und Randfälle

| Fall | Verhalten |
|---|---|
| `show_clock_card: false` im `strategy:`-Block hinzugefügt, seither unverändert | Undo exakt: Schlüssel wird entfernt |
| Derselbe Schlüssel seither auf `true` geändert | verweigert, »changed again after this« |
| Ein *anderer* Schlüssel desselben Blocks seither geändert | exakt – die Adressen sind verschieden; genau dafür wird bis zum Blatt abgestiegen |
| Der ganze `strategy:`-Block seither entfernt | verweigert, »no longer has the "strategy" block« – nie einen halben Block neu anlegen |
| Strategie-Dashboard »übernommen« (HA ersetzt `strategy` durch `views`) | eine Einstellungsänderung (`strategy` entfernt) plus hinzugefügte Ansichten; zurücknehmbar, wenn beides noch unverändert steht, sonst verweigert – ohne Sonderregel |
| Undo an einem Strategie-Dashboard (ohne `views:`) | `apply_undo` legte bisher für seine eigene Buchführung `views: []` an – harmlos, solange nur Karten zurücknehmbar waren, denn ein Dashboard ohne Ansichten hat keine. Mit Einstellungen würde es einem Strategie-Dashboard eine leere Ansichtsliste unterschieben; `apply_undo` erfindet den Schlüssel deshalb nicht mehr (beim Planschreiben am Code gefunden) |
| `theme: null` gesetzt, wo vorher kein Schlüssel war | »gesetzt« auf `null`; die Rücknahme entfernt den Schlüssel. `null` und »nicht vorhanden« werden nie verwechselt |
| `type` einer Ansicht geändert | nicht hier; #32 verweigert |
| `path` einer Ansicht geändert | nicht hier; Ansicht entfernt / hinzugefügt |
| Einstellung einer pfadlosen Ansicht, deren Position seither wackelt | `_POSITION_REFUSAL`, unverändert |
| `column_span` einer Section geändert | nicht hier; ohne weitere Änderung fällt schon die frühe Bedingung (»this change did not alter any cards«), weil Section-Einstellungen keine Einstellungen im Sinne dieses Vorhabens sind (Review 2026-09-24, K8) |
| Riesiger Block (`button_card_templates`, Dutzende Vorlagen) | je Vorlage ein Blatt, sofern beide Seiten Dicts sind; eine Zeile je geänderter Vorlage, gedeckelt wie Karten (`_ENTRY_LIMIT`) |

## Test-Plan

**pytest (`tests/test_analyze.py`, `tests/test_restore.py`):**

- Die Einstellungsdifferenz: gesetzt / entfernt / geändert; Abstieg nur durch beidseitige Dicts; Block als Blatt, wenn eine Seite kein Dict ist; die fünf ausgeschlossenen Ansichtsschlüssel und `views` an der Wurzel; `null` gegen »nicht vorhanden«.
- `plan_undo`: jede Zeile der Tabelle in Abschnitt 2, einschließlich »anderer Schlüssel desselben Blocks seither geändert«; eine reine Einstellungsänderung passiert die frühe Bedingung; Karte und Einstellung in derselben Änderung – verweigert eines, verweigert beides.
- `apply_undo`: `set`/`unset` an der Wurzel und in einer Ansicht; erneute Prüfung beim Anwenden (seither geänderter Wert → `LookupError`); Eingabe bleibt unverändert; Einstellungsschritt vor dem Entfernen einer pfadlosen Nachbaransicht.
- Erklärung: Texte beider Zeiten, Wertdarstellung, Gruppe `scope="dashboard"` vor den Ansichten, Reihenfolge innerhalb einer Ansichtsgruppe.
- `change_message` und `_counts`: neue Teile werden gelesen, `message_adds` bleibt für sie `False`; die bestehenden Tests zu `_COUNT` bleiben grün.

**Panel (`tests/test_panel_behaviour.py`):** `renderPlain` mit einer Dashboard-Gruppe.

**Laufende Instanz (`tests/integration/run_checks.py`):** Ein Strategie-Dashboard bekommt über die API `show_clock_card: false`; der Undo ist verfügbar, schreibt, und ein erneutes Laden zeigt den Block ohne den Schlüssel. Dazu das `icon` einer Ansicht, zurückgenommen.

## Entscheidungen (am 2026-09-24 vom Nutzer bestätigt)

1. **Abstieg bis zum Blatt statt Vergleich je Schlüssel der obersten Ebene.** **Bestätigt am 2026-09-24.** Kostet etwas mehr Code, erlaubt aber, zwei unabhängige Änderungen im selben Block (`strategy`) getrennt zurückzunehmen. Mit »je oberster Schlüssel« wäre der zweite Undo verweigert, obwohl nichts mehrdeutig ist.
2. **Eine Zählstelle `N settings changed` im Verlauf** statt keiner. **Bestätigt am 2026-09-24.** Ohne sie widerspräche die Verlaufszeile (»no card changes«) nicht der Wahrheit, aber der Erklärung direkt darunter, die dann Einstellungen aufzählt – der Widerspruch zwischen Zählung und Erklärung, den `summarize` für ganze Ansichten schon einmal beseitigt hat (siehe den Kommentar dort).
3. **Die Beschriftung »On the dashboard itself«** für die neue Gruppe. Reine Wortwahl. **Bestätigt am 2026-09-24.**
