# Design: Parken statt verweigern – Karten in »Importierte Karten«

**Datum:** 2026-09-24
**Status:** Vom Nutzer bestätigt am 2026-09-24 – alle vier Punkte unter »Entscheidungen« abgesegnet, Punkt 3 dabei geändert. Bereit zur Umsetzung
**Vorhaben:** L aus dem Abschnitt »Reihenfolge der Vorhaben« der Haupt-Spec
**GitHub-Issue:** [#30](https://github.com/PPP01/ha-dashboard-history/issues/30)
**Integration:** `dashboard_history`
**Bindend bei Widerspruch:** die Haupt-Spec (`2026-08-30-dashboard-history-design.md`), insbesondere Entscheidung 4, 15 und 26

## Kontext & Ziel

Entscheidung 26 hat am 2026-09-23 festgelegt, *dass* die Integration eine Karte parkt, deren Platz in einer Sections-Ansicht sich nicht beweisen lässt: ans Ende der `cards:`-Liste der Ansicht, die Home Assistant als »Importierte Karten« anzeigt. Diese Spec legt fest, *wann genau* geparkt wird, was stattdessen weiter verweigert, wie es sich durch `analyze.py`, `restore.py`, `operations.py` und das Panel zieht, und was dabei an Wahrheit über den eigenen Zustand gesagt werden muss.

Entscheidung 26 wurde vor den Korrekturen vom 2026-09-23/24 geschrieben und ist an einer Stelle überholt: Sie beschreibt `_sections_lie` als Vergleich der **Titelliste**. Seit #31 vergleicht `_section_marks` jede Einstellung einer Section außer `cards`. Die Begründung von Entscheidung 26 bleibt davon unberührt; nur ihr Ausgangspunkt ist genauer geworden.

### Verifizierte Ausgangslage (2026-09-24, am Quelltext nachgelesen)

| Feststellung | Beleg |
|---|---|
| `plan_undo` verweigert **dashboardweit**, sobald `_sections_lie` für *irgendeine* Ansicht in *irgendeinem* der drei Ständepaare anschlägt | `analyze.py`, `plan_undo`: `if any(_sections_lie(one, other) for one, other in pairs)` |
| `_sections_lie` vergleicht je gemeinsamer Ansicht `_section_marks` – jede Section ohne `cards` | seit #31, `analyze.py:593` |
| Ein *Entfernen* findet seine Karte über den Fingerabdruck im heutigen Stand, gleich in welcher Section | `plan_undo`, `sole()` über `_present(current)` |
| Ein *Einsetzen* schreibt an die alte Adresse `("sections", i, "cards")`, Index `j` | `plan_undo`, `_step(old_slot, "insert", …)` |
| `apply_undo` findet die Kartenliste über `_cards_at`; fehlt die Liste, gibt es `LookupError` | `restore.py`, `_cards_for` |
| Eine Sections-Ansicht trägt in der Regel **keinen** `cards:`-Schlüssel | Prüfbank 2026-09-24: 27 Sections-Ansichten, keine mit nicht-leerer `cards:`-Liste |
| »Put back« prüft den Section-Anker nur über **Anzahl und Titel** | `restore.py`, `_anchor_holds`; `analyze.py`, `_section_anchor` |
| Titel tragen Sections praktisch nie | Prüfbank 2026-09-24: 101 Sections, Schlüssel `type` (91), `cards` (101), `column_span` (16), `title` (0) |
| HA zeigt eine nicht-leere `cards:`-Liste einer Sections-Ansicht als »Importierte Karten« an und lässt sie über weitere Speichervorgänge stehen | Entscheidung 26, im Testcontainer nachgestellt am 2026-09-23 |

Die letzte Zeile der Put-back-Befunde ist die schwerere: Mit einem Anker aus Anzahl und (fehlendem) Titel landet eine zurückgeholte Karte nach einem Tausch zweier titelloser Sections **still in der falschen Section**. `docs/limitations.md` führt das seit 2026-09-23 als eigene Zeile (»Writes into wrong section«).

## Nicht-Ziele (YAGNI)

- **Keine Identitätskette.** Entscheidung 16 bleibt entschieden und ungebaut. Parken ist ausdrücklich der Weg, der *ohne* sie auskommt.
- **Kein Parken in Masonry-, Sidebar- oder Panel-Ansichten.** Dort ist `cards:` die sichtbare Liste; die offene Frage ist dort nicht der Platz, sondern die Ansicht (Entscheidung 26, »Grenzen«).
- **Kein Parken per »Put back« in Ansichten ohne URL-Pfad.** Beim Undo ist eine pfadlose Ansicht, die bis zur Section-Prüfung kommt, von `_positions_lie` bereits als dieselbe bestätigt – dort wird geparkt wie überall (Nutzerentscheidung vom 2026-09-24, siehe »Entscheidungen«, Punkt 3). »Put back« hat diese Prüfung nicht: `reinsert` findet eine pfadlose Ansicht über ihren alten Index, ohne zu beweisen, dass dort noch dieselbe steht (bekannte Lücke, `docs/limitations.md`). Heute rettet die fehlschlagende Section-Prüfung diesen Fall zufällig in eine Verweigerung; Parken würde daraus ein mögliches Schreiben in eine fremde Ansicht machen.
- **Kein Zurückbauen einer Section-Struktur.** Hat die zurückzunehmende Änderung selbst Sections hinzugefügt, entfernt, vertauscht oder umgestellt, bleibt der Undo verweigert. Parken beantwortet »wohin mit dieser Karte«, nicht »wie sah die Ansicht aus«.
- **Keine Verfeinerung à la #33 für Sections.** Eine am Ende angehängte Section verschiebt keine davor – dieselbe Überlegung wie bei #33. Sie wird hier nicht mitgebaut; mit dem Parken kostet die Überstrenge nur noch ein Sternchen, keine Verweigerung mehr.

## Entwurf

### 1. Die Section-Prüfung wird von dashboardweit zu je Ansicht

`_sections_lie(one, other) -> bool` wird ersetzt durch eine Auskunft **je Ansichtsschlüssel**, die für jede Ansicht, die in allen drei Ständen vorkommt, eine von drei Antworten gibt:

| `before` ↔ `after` | `after`/`before` ↔ `current` | Antwort | Wirkung |
|---|---|---|---|
| gleich | gleich | **fest** | Einsetzen an der alten Adresse, wie heute |
| gleich | verschieden | **verschoben seither** | Einsetzen in Sections dieser Ansicht wird **geparkt** |
| verschieden | beliebig | **von dieser Änderung umgebaut** | `_SECTION_REFUSAL`, unverändert |

»Gleich« heißt: `_section_marks` beider Ansichten sind gleich – dieselbe Definition wie seit #31. Eine Ansicht, deren Sections sich *seither* verschoben haben, blockiert damit nicht mehr die Rücknahme einer Kartenänderung in einer **anderen** Ansicht; genau das ist der erste Satz des Issues (»an unrelated card edit in an untouched section is refused too«).

Eine Ansicht, die sich nur durch *seitherige* Section-Verschiebung auszeichnet und in der der Plan **nichts einsetzt**, braucht keine Sonderbehandlung: Entfernungen finden ihre Karte über den Fingerabdruck und adressieren sie im heutigen Stand, wo sie tatsächlich steht. Solche Rücknahmen werden damit exakt – ohne Sternchen.

Die Reihenfolge der Prüfungen in `plan_undo` bleibt: `_paths_collide` → `_positions_lie` → `_view_type_changed` → Section-Auskunft. Eine konvertierte Ansicht (#32) verweigert weiterhin vorher und aus ihrem eigenen Grund.

### 2. Was geparkt wird, und wohin

Geparkt wird genau ein Schritt-Typ: ein **Einsetzen** (`action="insert"`, `kind="card"`), dessen Adresse mit `"sections"` beginnt, in einer Ansicht mit der Antwort »verschoben seither« – mit oder ohne `path`: Eine pfadlose Ansicht, die hier ankommt, hat `_positions_lie` schon bestanden, und ein gewöhnliches Einsetzen in sie verlässt sich heute auf genau dieselbe Prüfung. Das betrifft die drei Tabellenzeilen aus Entscheidung 15, die ein Einsetzen erzeugen: bearbeitet (alt wieder einsetzen), verschoben (am alten Platz einsetzen), gelöscht (am alten Platz einsetzen).

Ein geparkter Schritt trägt statt der alten Adresse `location=("cards",)` und ein neues Feld `parked=True` an `UndoStep`. `apply_undo` schreibt ihn **nicht an einen Index**, sondern hängt ihn ans Ende der `cards:`-Liste der Ansicht an – und legt die Liste an, wenn sie fehlt oder `null` ist (dieselbe Vorsicht wie beim `sections: null`-Fall in `reinsert`). Mehrere geparkte Karten werden in der Reihenfolge ihrer alten Plätze angehängt (Section-Index, dann Kartenindex), nach allen nicht geparkten Einsetzungen in dieselbe Liste. So verschiebt kein Anhängen den Index einer gewöhnlichen Einsetzung.

Einsetzungen, deren alte Adresse bereits `("cards",)` war – eine Karte, die schon in »Importierte Karten« lag –, werden nie geparkt: Diese Liste ist keine Section und von Section-Verschiebungen nicht betroffen.

»Alles oder nichts« (Entscheidung 15) gilt unverändert für jede Bedingung, die nicht die Section betrifft: Ist eine Karte seither geändert oder doppelt, verweigert die ganze Rücknahme – geparkt wird nie *statt* einer anderen Verweigerung.

### 3. Der Plan sagt, dass er parkt

`UndoPlan` bekommt keine neue Verweigerungsform, aber eine Auskunft: die Beschriftungen aller geparkten Schritte, in Planreihenfolge. `operations.async_undo_change` gibt sie als `parked: [label, …]` zurück, **auch ohne `preview`** – die Zeile fragt den Undo bei jedem Aufklappen ab, und das Sternchen am Knopf muss dort schon stimmen, nicht erst im Dialog.

`equals_state_before` ist bei einem parkenden Undo von selbst `False`: Das Ergebnis ist nicht der Stand vor der Änderung. Der Knopf »Back to the state before this change« bleibt damit sichtbar – richtig, denn nur er stellt die exakte Anordnung wieder her.

### 4. »Put back« parkt ebenfalls – und bekommt einen ehrlichen Anker

Entscheidung 26 verlangt dasselbe Verhalten für »Put back« (heute nur noch über den Vergleichsmodus erreichbar, Entscheidung 19). Zwei Teile:

**4a. Der Anker wird zu einem Beweis.** Heute trägt ein `RemovedItem` einer Karte in einer Section den Anker `(Anzahl der Sections, title)`. Bei 0 von 101 Sections mit Titel heißt das in der Praxis: »gleiche Anzahl«. Neu trägt der Anker, was die Section damals *war*: ihre Einstellungen ohne `cards` (wie `_section_marks`) und die Karten, die nach dem Verschwinden der zurückzuholenden dort noch stehen sollten – die alte Kartenliste dieser Section ohne die Karten, die `find_removed` für genau diese Section als verschwunden meldet, und ohne die, die seit dem Stand, aus dem zurückgeholt wird, in eine andere Liste verschoben wurden (sie haben die Section rechtmäßig verlassen), in ihrer Reihenfolge. Der Anker hält, wenn die Section am selben Index heute genau diese Einstellungen hat und diese Karten **in ihrer Reihenfolge** enthält; Karten, die seither dazukamen, dürfen dazwischen stehen. War die zurückzuholende Karte allein in ihrer Section, gibt es nichts, woran sich die Section erkennen ließe – dann muss sie heute leer sein, sonst ginge jede Section mit gleichen Einstellungen (die meisten tragen nur `type: grid`) für sie durch. **Eingesetzt wird neben dem Nachbarn, nicht am alten Index:** direkt hinter dem letzten Überlebenden, der vor der Karte stand, oder direkt vor dem ersten, wenn keiner vor ihr stand. Mit Karten, die seither davor dazukamen, würde der alte Index sie sonst zwar in die richtige Section, aber weg von ihrem Nachbarn setzen *(zweite Prüfung am 2026-09-24)*. **Restlücke, benannt:** Zwei Sections ohne unterscheidende Einstellung, und der Nachbar ist seither in die andere gewandert – »Sections vertauscht« und »Nachbar hinübergezogen« ergeben dann bytegleich dieselbe Konfiguration, und die Karte geht in die Section am alten Index. Das ist die Restlücke aus #31, kein neues Loch; die strenge erste Fassung hätte hier geparkt. *(Nach dem Plan-Review vom 2026-09-24, Befund W2, vom Nutzer so festgelegt. Die erste Fassung verlangte »genau diese Karten« und hätte auch nach einer seither hinzugefügten oder in derselben Speicherung verschobenen Karte geparkt, wo das Zurückholen heute korrekt landet.)*

Das ist strenger als heute, mit Absicht und zu geringen Kosten: Hält der Anker nicht, wird nicht mehr verweigert, sondern geparkt. Der Tausch zweier titelloser Sections – bisher ein stilles Falschschreiben – wird so zu einer geparkten Karte mit Hinweis. Ein Nachbar in derselben Section, der seither bearbeitet wurde, parkt ebenfalls, obwohl die Karte vielleicht richtig gelandet wäre; das ist der Preis, und er ist sichtbar statt still. Ebenso eine seither umsortierte Section: Die Reihenfolge der verbleibenden Karten gehört zum Beweis.

**4b. Parken als Politik des Aufrufers, nicht des Werkzeugs.** `restore.reinsert` bleibt, was es ist: einsetzen oder mit `LookupError` verweigern. Dazu kommen zwei kleine Funktionen: `restore.parks(config, item) -> bool` (würde dieses Stück geparkt?) und `restore.park(config, item) -> dict` (hängt die Karte an `cards:` der Ansicht, legt die Liste bei Bedarf an). Geparkt werden darf nur eine Karte (`kind="card"`), deren Ansicht per Pfad gefunden wird und `type: sections` trägt, und nur wenn ihr Anker nicht hält oder ihre Section-Liste nicht mehr existiert. `operations._reinsertion` entscheidet und meldet `parked: [Beschriftung]` in Vorschau und Antwort. Wie beim Undo (Entscheidungen, Punkt 4) schickt der Bestätigungsaufruf mit, was die Vorschau zeigte (`expected_parked`); parkt das neu gerechnete Zurückholen anders, wird nichts geschrieben *(ergänzt am 2026-09-24 nach dem Plan-Review, Befund K1)*. Die bestehenden `reinsert`-Tests bleiben damit gültig; sie prüfen das Werkzeug, nicht die Politik.

Sections selbst (`kind="section"`) werden nie geparkt: Eine Section hat keinen Parkplatz, und ihr Beweis (`_section_gap_holds`) bleibt, wie er ist.

### 5. Wörter

**Erklärung (`_explain`):** Liegt eine Karte in einer Sections-Ansicht in `("cards",)`, heißt ihr Ort in `_section_name` künftig `the "Imported cards" area` statt `another place in this view`. Das verbessert nebenbei die Beschreibung von Konvertierungs-Überbleibseln (#32) und ist dieselbe Stelle, an der HA den Begriff zeigt.

**Knopf:** Ist der Undo exakt, heißt er wie bisher »Undo this change«. Parkt mindestens ein Schritt, heißt er »Undo this change\*«. Unter der Aktionsleiste steht dann derselbe Hinweis, den `why` heute schon für den Ersetzen-Knopf nutzt:

> \* Some cards can no longer be put back into their exact section, because the sections of this view were rearranged since. They are placed in the view's "Imported cards" area – shown in edit mode – for you to move.

**Bestätigungsdialog:** Der Einleitungssatz nennt es noch einmal ohne Sternchen und listet jede geparkte Karte:

> Puts this change back. These cards cannot go back into their exact section and are made available in "Imported cards" instead – you still have to place them: …

Der Begriff »Imported cards« steht wörtlich so da, weil es HAs eigener ist (Entscheidung 26); die Oberfläche von HA ist englisch wie die dieses Panels.

**Put back im Vergleichsmodus:** derselbe Satz im Dialog, bezogen auf die eine Karte.

## Fehler- und Randfälle

| Fall | Verhalten |
|---|---|
| Ansicht mit Pfad, Sections seither verschoben, Karte bearbeitet | bearbeitete Fassung wird entfernt, alte Fassung geparkt; Knopf mit Sternchen |
| Dieselbe Ansicht, aber die Änderung hat nur *entfernt* (Karte hinzugefügt, jetzt zurückgenommen) | exakt, ohne Sternchen – nichts wird eingesetzt |
| Unbeteiligte Ansicht mit verschobenen Sections, Änderung in einer anderen Ansicht | exakt, ohne Sternchen (bisher verweigert) |
| Die Änderung selbst hat eine Section hinzugefügt / entfernt / vertauscht | `_SECTION_REFUSAL`, unverändert |
| Ansicht ohne Pfad, Sections seither verschoben, Einsetzen nötig | Undo parkt, wenn `_positions_lie` die Ansicht bestätigt hat – sonst verweigert schon vorher `_POSITION_REFUSAL`. »Put back« parkt hier nicht und verweigert wie bisher |
| Ansicht inzwischen konvertiert | `_VIEW_TYPE_REFUSAL`, unverändert (#32) |
| Zwischen Vorschau und Bestätigen speichert jemand | beim Bestätigen neu gerechnet (Entscheidung 15); ein vorher exakter Undo kann dann parken – der Dialog zeigt die Vorschau-Antwort, das Schreiben die neue. Siehe »Entscheidungen«, Punkt 4 |
| Zwei Sections mit in allen Einstellungen gleichen Werten vertauscht, *nach* der Änderung | wird nicht als Verschiebung erkannt (Restlücke aus #31); die Karte landet am alten Index, also optisch am alten Platz, aber in der Section, die jetzt dort steht. Nicht neu, nicht verschlimmert |
| HA stellt die Anzeige »Importierte Karten« eines Tages ein | nichts geht verloren; die Karten stehen in der Konfiguration, unsichtbar. Genau dafür steht das Sternchen (Entscheidung 26) |

## Test-Plan

**pytest (`tests/test_analyze.py`, `tests/test_restore.py`):**

- Section-Auskunft je Ansicht: die drei Antworten aus der Tabelle in Abschnitt 1, jeweils mit einer unbeteiligten zweiten Ansicht, die nicht mitverweigert.
- Parken im Plan: bearbeitet, verschoben, gelöscht – je ein Fall mit `parked=True`, `location=("cards",)`; die Beschriftungen stehen in der Planauskunft.
- Geparkt auch in einer pfadlosen Ansicht, deren Position feststeht.
- Nicht geparkt: alte Adresse `("cards",)`; reine Entfernung; von der Änderung umgebaute Sections (verweigert, die bestehenden Tests zu #31 und zur eingefügten Section bleiben unverändert grün).
- `apply_undo`: legt `cards:` an, wenn sie fehlt oder `null` ist; hängt mehrere geparkte Karten in alter Reihenfolge an; eine gewöhnliche Einsetzung in dieselbe Liste landet vor ihnen an ihrem Index.
- Anker: hält bei unveränderter Section; hält nicht nach Tausch zweier titelloser Sections mit verschiedenem `column_span`; hält nicht nach bearbeitetem Nachbarn. `parks`/`park` für Karte in Sections-Ansicht mit Pfad; `parks` ist `False` für Masonry, für pfadlose Ansicht und für `kind="section"`.
- Die beiden bestehenden Tests `test_a_card_refuses_to_go_back_into_a_different_section` und `test_a_card_refuses_when_a_section_was_pushed_along` bleiben unverändert grün – sie prüfen `reinsert`, und `reinsert` verweigert weiterhin.

**Panel (`tests/test_panel_behaviour.py`):** Knopfbeschriftung mit und ohne Sternchen, Hinweiszeile, Liste der geparkten Karten im Dialog-Einleitungssatz.

**Laufende Instanz (`tests/integration/run_checks.py`):**

- Neuer Abschnitt: Sections-Ansicht, Karte bearbeiten, danach eine Section davor einfügen, Undo – Antwort mit `parked`, nach dem Bestätigen liegt die alte Fassung in `cards:` der Ansicht, und ein erneutes Laden über die API liefert sie unverändert zurück (HA hat sie beim Speichern nicht verworfen).
- Der bestehende Fall »a card whose section was pushed along is not filed in a stranger« erwartet künftig ein geparktes Stück statt eines Fehlers; unverändert bleibt die eigentliche Aussage: **nicht** in der fremden Section.

## Entscheidungen (am 2026-09-24 vom Nutzer bestätigt)

1. **Von der Änderung umgebaute Sections verweigern weiterhin** (Abschnitt 1, dritte Zeile). **Bestätigt am 2026-09-24.** Alternative wäre, auch dort zu parken und das Übrigbleiben leerer oder umgestellter Sections in Kauf zu nehmen. Verworfen, weil der Undo dann einen Stand schriebe, der keinem früheren entspricht, ohne dass ein Sternchen das Richtige sagt – das Sternchen verspricht »Karten parken«, nicht »Struktur bleibt schief«.
2. **Der Put-back-Anker wird strenger** (Abschnitt 4a). **Bestätigt am 2026-09-24.** Ein bearbeiteter Nachbar in derselben Section lässt künftig parken, wo heute an den Index geschrieben würde. *Nach dem Plan-Review am selben Tag vom Nutzer gelockert:* Seither hinzugefügte und in derselben Speicherung weggezogene Karten lassen nicht parken (Abschnitt 4a). Begründung: schließt ein bekanntes stilles Falschschreiben; der Preis ist ein sichtbares Sternchen. Wer das zu streng findet, kann auf »nur Einstellungen vergleichen« zurück – das schließt den Tausch mit verschiedenem `column_span`, nicht den mit gleichem.
3. ~~**Kein Parken in pfadlosen Ansichten.**~~ **Entschieden vom Nutzer am 2026-09-24: Der Undo parkt auch dort.** Der Ausschluss war aus dem Issue übernommen, aber unnötig – wer bis zur Section-Prüfung kommt, hat `_positions_lie` bestanden, und ein gewöhnliches Einsetzen in dieselbe Ansicht verlässt sich schon heute darauf. Für »Put back« bleibt der Ausschluss, weil `reinsert` die pfadlose Ansicht nicht beweist (siehe »Nicht-Ziele«).
4. **Vorschau exakt, Schreiben parkt** ist möglich, wenn zwischen beidem jemand speichert. **Vorschlag bestätigt am 2026-09-24.** Heute ist das Gegenstück »Vorschau exakt, Schreiben verweigert«. Vorschlag: `async_undo_change` beim Bestätigen verweigern, wenn der neu gerechnete Plan parkt, die Vorschau aber nicht geparkt hat – mit dem Satz, dass sich das Dashboard inzwischen geändert hat. Ohne das würde ein Knopf ohne Sternchen eine Karte parken. Dafür muss der Bestätigungsaufruf mitschicken, was die Vorschau zeigte (`expected_parked`); der Plan enthält es als eigenen Schritt. *Nach dem Plan-Review vom 2026-09-24 präzisiert:* Die Dienste `undo_change` und `restore_deleted` haben keine Vorschau, die sie zurückmelden könnten; sie parken deshalb nur mit ausdrücklichem `allow_parking: true` und verweigern sonst, statt ihr Versprechen »only offered when it is provably exact« still zu brechen (Befund W1). Nach der zweiten Prüfung gilt dasselbe für die WebSocket-Befehle: Fehlt `expected_parked`, wird »kein Parken erwartet« angenommen. Parken muss damit auf jedem Schreibweg angefordert werden.
