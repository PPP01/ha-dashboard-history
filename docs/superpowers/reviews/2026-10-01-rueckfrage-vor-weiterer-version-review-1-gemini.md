# Review 1: Rückfrage vor dem Versionsdialog (Issue #51)

Geprüft wurde der Implementierungsplan `docs/superpowers/plans/2026-10-01-rueckfrage-vor-weiterer-version.md` auf Branch `issue-51-ask-before-another-version` (Commit `e21fef0`) gegen den Arbeitsbaum, die Spezifikation `docs/superpowers/specs/2026-08-30-dashboard-history-design.md`, `CLAUDE.md`, `FAQ.md` und `docs/user-guide.md`.

---

## Findings

### Kritisch
*Keine Befunde.*

### Hoch
*Keine Befunde.*

### Mittel

#### M1 — Der Ja-Pfad im Test-Szenario belegt die Rückfrage vorab nicht aussagekräftig
- **Fundstelle:** Plan, Task 1, Step 2 (`_ANOTHER_VERSION_ASKED`, Fall 3) sowie Step 3; `test_answering_yes_goes_on_to_the_create_dialog_as_before`.
- **Beschreibung:** Im Testfall 3 (`// 3. "Yes": on to the numbers and the create dialog, as before.`) ruft der Test `flow = begin("a"); await settle(); confirmBox().close("apply"); await settle();` auf. Im Ausgangszustand vor der Umsetzung öffnet `_createVersion` jedoch sofort den Versionsdialog `dialog.version`, ohne `dialog.confirm` je anzufassen. Der Aufruf `confirmBox().close("apply")` verpufft am geschlossenen Dialog wirkungslos; `versionBox().open` ist bereits wahr und `sent[0]` ist `"next_versions"`. Aus diesem Grund ist `test_answering_yes_goes_on_to_the_create_dialog_as_before` einer der 3 Tests, die bereits vor der Implementierung grün sind (PASS). Er weist somit nicht nach, dass die Antwort »Save anyway« die neu eingebaute Hürde tatsächlich überwunden hat, sondern würde auch dann bestehen, wenn `_createVersion` die Rückfrage vollständig überspringen würde.
- **Konsequenz:** Eine Regression, bei der die Rückfrage fälschlicherweise gar nicht gestellt wird (oder vorzeitig abbricht), kann durch diesen Test nicht erkannt werden.
- **Vorschlag:** Vor dem Schließen mit `"apply"` sollte explizit geprüft werden, dass die Confirm-Box tatsächlich geöffnet war (`confirmBox().open === true`). Erst danach `close("apply")` ausführen und belegen, dass die Confirm-Box geschlossen ist und der Versionsdialog sich anschließend öffnet.

#### M2 — Zeilen aus der Suche (`_searchResults`) sind im Testplan nicht abgedeckt
- **Fundstelle:** Plan, Task 1, Step 2 (`_ANOTHER_VERSION_ASKED`); `custom_components/dashboard_history/panel.js`, Methode `_changeAt`.
- **Beschreibung:** `_createVersion(which)` wird über den Klick-Handler `[data-version]` aufgerufen. Zeilen können nicht nur aus `this._changes`, sondern bei einer aktiven Suche auch aus `this._searchResults` stammen (`_changeAt` prüft `_changes` und danach `_searchResults`). Das neue Szenario `_ANOTHER_VERSION_ASKED` befüllt ausschließlich `el._changes`. Suchergebnisse, die außerhalb des geladenen 25er-Fensters liegen und bereits getaggt sind oder `same_as_now` tragen, durchlaufen denselben Code, werden aber im Testfixture nicht explizit geprüft.
- **Konsequenz:** Zwar nutzt `_createVersion` einheitlich `_changeAt(revision)`, sodass die Logik greift; der Anspruch des Plans, alle Wege zu `_createVersion` testend zu belegen, hat hier jedoch eine Lücke für Suchergebnisse.
- **Vorschlag:** Im Testfixture einen Fall ergänzen, bei dem die Revision ausschließlich in `el._searchResults` existiert (mit gesetzter Version), um zu verifizieren, dass auch über die Suchansicht die Rückfrage zuverlässig vor dem Dialog erscheint.

---

### Niedrig

#### N1 — Differenzierung der Aufrufer von `_confirmOverride` vs. `dialog.confirm`
- **Fundstelle:** Plan, Task 1, Step 1 und Review Focus 6.
- **Beschreibung:** Der Plan spricht davon, `_confirmOverride` habe zwei Aufrufer (`_confirm` und `_openReplace`) und schließt daraus, dass `dialog.confirm` von diesen Aufrufern zurückgesetzt wird. Im Code verwendet `_openReplace` jedoch `dialog.replace` (`const retryDialog = this.shadowRoot.querySelector("dialog.replace");`). Für `dialog.confirm` gibt es im gesamten Panel daher vor dieser Änderung nur einen einzigen Aufrufer: `_confirm` (inklusive seines Retrys).
- **Konsequenz:** Keine funktionale Beeinträchtigung; die Behauptung des Plans ist für `dialog.confirm` sogar noch unkritischer als dargestellt, da es gar keine dritte Stelle gibt, die `dialog.confirm` nutzt. Die Begründung im Plan ist jedoch begrifflich ungenau.
- **Vorschlag:** Im Plan klarstellen, dass `_confirmOverride` zwar generisch für `dialog.confirm` und `dialog.replace` dient, `_askAnother` sich aber ausschließlich mit `_confirm` das Element `dialog.confirm` teilt.

#### N2 — Redundanter Aufruf von `_alreadyNamed(change)` in `_createVersion`
- **Fundstelle:** Plan, Task 1, Step 4(c); `custom_components/dashboard_history/panel.js`, `_createVersion`.
- **Beschreibung:** `_alreadyNamed(change)` wird am Anfang von `_createVersion` aufgerufen (`const named = this._alreadyNamed(change); if (named && !(await this._askAnother(named))) return;`). Später in Zeile 2827 steht unverändert `const already = this._alreadyNamed(change);`. Da `change` unverändert bleibt, liefert der zweite Aufruf exakt dasselbe Ergebnis.
- **Konsequenz:** Der Plan benennt dies unter »Minimaler Umfang« ausdrücklich als bewusst so belassen, um den Versionsdialog nicht anzufassen. Es handelt sich um eine minimale Redundanz ohne Messwert- oder Laufzeitnachteil.
- **Vorschlag:** Kann wie geplant beibehalten werden; als Notiz für ein späteres Aufräumen (z. B. bei Neugestaltung des Versionsdialogs) vormerken.

---

## Detaillierte Prüfung der Prüffragen

### 1. Anker und Behauptungen des Plans
- **Anker:** `_createVersion` (Zeile 2792), `_alreadyNamed` (Zeile 3514), `_confirmOverride` (Zeile 2201), `_answerFrom` (Zeile 2417) und `_changeAt` (Zeile 1718) existieren im Arbeitsbaum exakt mit den im Plan zitierten Codezeilen.
- **Vorkommen von `_confirmOverride`:** Ein `grep -n "_confirmOverride"` liefert exakt drei Treffer (Zeilen 2114, 2201, 2361) — die Definition und die beiden Aufrufe.
- **Standardwerte:** Die Signatur `{ title = "Write anyway?", apply = "Write anyway", cancel = "Cancel" } = {}` stellt sicher, dass die beiden bisherigen Aufrufe `this._confirmOverride(retryDialog, applied.error)` ohne dritten Parameter exakt ihre bisherigen Texte behalten.
- **Rücksetzen von `dialog.confirm`:** `_confirm` überschreibt beim Öffnen von `dialog.confirm` ausnahmslos alle Eigenschaften, die `_confirmOverride` manipuliert:
  - `h2.textContent` (durch `title`),
  - `.body.innerHTML` (durch die gerenderten Diffs/Erklärungen),
  - `.note.textContent` (durch `note`),
  - Fußnote via `this._sayFootnote(...)`,
  - `applyButton.hidden` und `applyButton.textContent` (`applyLabel`),
  - `button[value="cancel"].textContent` (`nothingToDo ? "Close" : "Cancel"`),
  - `dialog.returnValue = ""` und `_armKeep(...)`.
  Die Wiederverwendung von `dialog.confirm` durch `_askAnother` hinterlässt somit keine Spuren für nachfolgende Aktionen.

### 2. Prüfung der Tests und Testausführung
- **Verhalten der neuen Tests vor Umsetzung:** In einer isolierten Scratch-Kopie (`git archive HEAD | tar -x`) schlagen ohne die Code-Änderung exakt **6 Tests fehl** und **3 Tests bestehen** (wie oben unter M1 analysiert).
- **Verhalten nach Umsetzung:** Alle **9 Tests bestehen** fehlerfrei.
- **Bestehende Tests:** Ohne Anpassung von `_PENDING_CHANGES` (`dialogFor`) brechen genau die beiden im Plan genannten Tests mit einem Node-Timeout/ERROR ab (`test_the_version_dialog_shows_its_own_pending_changes` und `test_the_version_dialog_uses_singular_wording_for_one_change`), weil `dialogFor("a")` an der neuen Rückfrage hängen bleibt.
- **Gesamtsuite:** Mit der im Plan beschriebenen Anpassung von `dialogFor` läuft die gesamte Testsuite ohne einen einzigen Fehler durch: **1132 passed, 5 skipped, 0 failed**. Es bricht kein weiterer bestehender Test.
- **Code-Metriken:** `tools/complexity_ratchet.py` meldet `20 known values, none grew`. `lint-imports` meldet `Contracts: 2 kept, 0 broken`.

### 3. Verhalten im echten Browser vs. Node-Stand-in
- **Escape-Verhalten:** Gemäß HTMLDialogElement-Spezifikation feuert Escape das `cancel`-Event und schließt den Dialog, ohne den Wert von `dialog.returnValue` zu verändern. Da `_confirmOverride` unmittelbar vor `dialog.showModal()` explizit `dialog.returnValue = ""` setzt, bleibt der Wert nach Escape leer (`""`). Der Vergleich `(await this._answerFrom(dialog)) === "apply"` evaluiert sauber zu `false`.
- **Klick auf Cancel:** Der Cancel-Button hat `value="cancel"`. Der native Click-Handler ruft `element.close("cancel")` auf; der Rückgabewert ist `"cancel" !== "apply"`, evaluiert zu `false`.
- **Klick auf Save anyway:** Der Apply-Button hat `value="apply"`. Der Click-Handler ruft `element.close("apply")` auf; der Rückgabewert ist `"apply" === "apply"`, evaluiert zu `true`.
- **Rendern bei offenem Dialog (`_renderOwed`):** Wird `_render()` aufgerufen, während `dialog.confirm` offen ist, erkennt `this.shadowRoot.querySelector("dialog[open]")` den modalen Dialog und setzt `this._renderOwed = true`, ohne das DOM neu aufzubauen. Beim Schließen des Dialogs führt `_answerFrom` das nachzuholende Rendern aus (`if (this._renderOwed) this._render();`), bevor der Rückgabewert resolved wird. Danach holt `_createVersion` die Referenz auf `dialog.version` frisch aus `this.shadowRoot`. Es gibt weder DOM-Abriss noch Deadlocks.
- **Keine Kollision mit `_onRecorded`:** Während ein Dialog offen ist, bricht `_onRecorded` in Zeile 999 sofort ab (`if (this.shadowRoot?.querySelector("dialog[open]")) return;`). Ein konkurrierendes Aktualisieren der Historie findet nicht statt.

### 4. Zustände und Randfälle
- **Doppelklick-Schutz:** Der Einstieg in `_createVersion` bis zu `dialog.showModal()` in `_confirmOverride` ist vollständig synchron (kein `await` vor `showModal()`). Im Browser wird der modale Dialog im selben Task geöffnet; dadurch wird der gesamte Hintergrund sofort `inert`. Ein zweiter Klick kann den Hintergrundbutton nicht mehr treffen.
- **Suche:** Bei aktiver Suche liefert `_changeAt(revision)` den Change aus `_searchResults`. `_alreadyNamed(change)` ermittelt Versionen und Übereinstimmungen identisch; der Dialog wird korrekt vorgeschaltet.
- **Vergleichsmodus / Moduswechsel:** Beide Modi verändern weder die Semantik von `_createVersion` noch die Erreichbarkeit. Im einfachen Modus wird der Button bei bereits benanntem Stand gar nicht erst angeboten (`panel/simple.js:358`); im erweiterten Modus fragt »Save this as another version« wie beabsichtigt.
- **Mehrere Versionen:** `_alreadyNamed` formatiert Listen über `someNames(names)` (z. B. `v1.0.0 and v1.0.1` oder `v1.0.0 and 2 more`). Der Fragesatz bleibt grammatikalisch korrekt.
- **Nicht vorhandene/nicht geladene Daten:** `if (!change) return;` sichert ab, falls eine Revision nicht existiert. Solange Versionen laden, unterbindet der Ladestatus Fehleingaben.
- **Banner hinter einem Tag:** Die Beschreibung im Plan ist zutreffend: Wenn der neueste Eintrag getaggt ist, die Live-Konfiguration aber abweicht und zufällig einer älteren Version gleicht, bezieht sich `_alreadyNamed(change)` auf die Version des neuesten Eintrags und nicht auf den Live-Stand. Dies ist eine bekannte, praktisch kaum auftretende Randbedingung und im Rahmen von #51 bewusst ausgeklammert.

### 5. Widerspruchsfreiheit und Projektregeln
- **Spec Entscheidung 7:** Die bindende Regel, dass `create_version` kein Service-`confirm` im Backend benötigt, bleibt unberührt. Das Backend-Kommando verändert keinen Dashboard-Zustand. Die vorgeschlagene Abfrage ist eine reine Absicherung der UI-Bedienung im Frontend.
- **Texte:** Die Formulierungen für `FAQ.md` und `docs/user-guide.md` stimmen exakt mit dem Verhalten überein (Hinweis auf die einmalige Rückfrage im erweiterten Modus).
- **Commit-Format & Struktur:**
  - Commit 1 (Plan): bereits auf Branch vorhanden (`[51] Add the plan for #51`).
  - Commit 2 (Task 1): Subject 39 Zeichen (<= 50), Body mit Erläuterung des Warums, Zeilen <= 72 Zeichen, Referenz `Refs #51.`.
  - Commit 3 (Task 2): Subject 49 Zeichen (<= 50), Body <= 72 Zeichen, `Closes #51.`.
  Insgesamt genau 3 Commits auf dem Feature-Branch, vollständig konform mit `CLAUDE.md`.

---

## Urteil

**Umsetzbar nach Korrekturen.**
Der Plan ist architektonisch sauber, minimal-invasiv und handwerklich präzise. Vor der finalen Umsetzung sollten die Test-Lücken M1 (belastbarer Ja-Pfad) und M2 (Absicherung über `_searchResults`) im Test-Szenario geschlossen werden.

---

## Nachweislich ausprobiert

- Temporäre Scratch-Kopie via `git archive HEAD | tar -x -C /tmp/review-issue-51-test` angelegt.
- Test-Fixture aus Task 1, Step 2 in `tests/test_panel_behaviour.py` eingefügt und ausgeführt: exakt **6 failed, 3 passed** bestätigt.
- Code-Änderungen in `custom_components/dashboard_history/panel.js` eingespielt: alle **9 neuen Tests passed**.
- Vollständigen Behaviour-Testlauf ohne Anpassung von `_PENDING_CHANGES` ausgeführt: exakt die prognostizierten **2 ERRORs** reproduziert.
- Anpassung von `_PENDING_CHANGES` in `test_panel_behaviour.py` durchgeführt: `tests/test_panel_behaviour.py` mit **317 passed** erfolgreich.
- Gesamte Testsuite im Scratch-Verzeichnis ausgeführt: **1132 passed, 5 skipped, 0 failed**.
- Qualitäts-Tools verifiziert: `python3 tools/complexity_ratchet.py` (**20 known values, none grew**) und `lint-imports` (**2 kept, 0 broken**).
- Scratch-Kopie nach Abschluss vollständig gelöscht.

## Nur gelesen / theoretisch geprüft

- `docs/superpowers/specs/2026-08-30-dashboard-history-design.md` (Entscheidungen 7, 9, 15, 17, 18, 19).
- `CLAUDE.md`, `FAQ.md`, `docs/user-guide.md`, `panel/dialogs.js`, `panel/rows.js`, `panel/simple.js`.
- HTMLDialogElement-Spezifikation bezüglich Escape/`cancel`-Event/`returnValue`.
- Kein Start einer Live-Home-Assistant-Instanz oder eines Docker-Containers.

ENDE DES REVIEWS