# Design: Badges einer Ansicht gezielt zurücknehmen

**Datum:** 2026-09-24
**Status:** Vom Nutzer bestätigt am 2026-09-24 – alle drei Punkte unter »Entscheidungen« abgesegnet. Bereit zur Umsetzung, sobald die Vorhaben L und M gebaut sind. Nach dem Review vom 2026-09-25 präzisiert: beide Stufen und die »schon zurück«-Zählung vergleichen mit dem Stand unmittelbar nach der Änderung, gezählt wird nur in der eigenen Ansicht, und von mehreren gleichen Gelöschten gelten nur alle oder keine als zurück (Abschnitt 2) – vom Nutzer bestätigt am 2026-09-25
**Vorhaben:** N aus dem Abschnitt »Reihenfolge der Vorhaben« der Haupt-Spec
**GitHub-Issue:** [#29](https://github.com/PPP01/ha-dashboard-history/issues/29)
**Integration:** `dashboard_history`
**Bindend bei Widerspruch:** die Haupt-Spec (`2026-08-30-dashboard-history-design.md`), insbesondere Entscheidung 4, 14 und 15

## Kontext & Ziel

Die `badges:`-Liste einer Ansicht steht neben `cards:` und ist für die gezielte Rücknahme unsichtbar: `card_containers` zählt sie nicht auf, eine Änderung, die nur eine Badge hinzufügt, landet bei »this change did not alter any cards«. Eine Badge *in* einer Karte (etwa die `badges:` einer `heading`-Karte) ist davon nicht betroffen – sie gehört zum Rumpf ihrer Karte und reist mit ihr.

Anders als die benannten Einstellungen aus Vorhaben M haben Badges **keinen Namen**. Sie sind anonyme Listeneinträge ohne `id` – dasselbe Problem, das Entscheidung 4 für Karten beschreibt. Deshalb ist die Antwort hier nicht die einfache Pfadgleichheit aus M, sondern dieselbe Maschinerie wie für Karten: Zuordnung über den Inhalt (Entscheidung 14) und der Beweis »steht genau einmal da« (Entscheidung 15).

### Verifizierte Ausgangslage (2026-09-24, am Quelltext und an der Prüfbank nachgelesen)

| Feststellung | Beleg |
|---|---|
| `card_containers` liefert nur `("cards",)` und `("sections", i, "cards")` | `analyze.py:101` |
| Die ganze Zuordnung (`_slots`, `match_cards`, `_present`) hängt an `card_containers` | `analyze.py` |
| `_describe`, `_weak_key`, `fingerprint`, `_similarity` nehmen beliebige Werte an, nicht nur Dicts; `_weak_key` gibt für Nicht-Dicts `None` zurück | am Quelltext gelesen, `analyze.py:158–226` |
| Badges in der Prüfbank | 23 Badges in 8 von 70 Ansichten; `badges:`-Schlüssel an 33 Ansichten, davon 25 leer |
| Badge-Typen | `entity` 12, `custom:mushroom-template-badge` 8, ohne `type` 3 (alte Form `{entity, icon, name}` bzw. `{entity}`); keine als bloße Zeichenkette |
| Badge gleich einer Karte (gleicher Fingerabdruck) | **0** – aber möglich, denn `type: entity` gibt es als Karte wie als Badge |
| Mehrfach vorkommende Badges **je Dashboard** | 6 von 23 Badges gehören zu 3 Gruppen gleicher Badges – **alle über Ansichten hinweg**, keine innerhalb einer Ansicht |

Die letzte Zeile entscheidet über den Zuschnitt: Dieselbe Status-Badge auf mehreren Ansichten ist ein gewöhnliches Muster. Eine Eindeutigkeitsprüfung über das ganze Dashboard, wie sie Karten bekommen, würde bei gut einem Viertel aller Badges verweigern, ohne dass irgendetwas mehrdeutig wäre.

## Nicht-Ziele (YAGNI)

- **Kein »Put back« für Badges.** Das Issue betrifft die gezielte Rücknahme. Eine gelöschte Badge bleibt über den ganzen Stand oder den Vergleichsmodus im Diff sichtbar; ein eigener Put-back-Weg ist ein eigenes Vorhaben, falls ihn jemand vermisst.
- **Keine Badges in Sections.** Home Assistant kennt Badges auf Ansichtsebene und in Karten, nicht auf Section-Ebene.
- **Keine Änderung an der Kartenzählung.** Die zweistufige Eindeutigkeit unten gilt für Badges. Ob Karten sie auch bekommen sollten, ist eine eigene Frage mit eigenen Messwerten.

## Entwurf

### 1. Badges sind eine zweite, getrennte Welt derselben Maschinerie

`card_containers` bekommt eine Schwester, `badge_containers(view)`, die genau `("badges",)` liefert, wenn `view["badges"]` eine Liste ist. `match_cards` wird intern zu einer Zuordnung über eine übergebene Behälterfunktion verallgemeinert; `match_cards(old, new)` behält Signatur und Verhalten, `match_badges(old, new)` ist dieselbe Zuordnung über `badge_containers`.

**Die beiden Welten werden nie gemischt.** Keine Karte wird einer Badge zugeordnet, keine Badge zählt bei der Eindeutigkeit einer Karte mit und umgekehrt. Der Grund ist nicht theoretisch: `{type: entity, entity: sun.sun}` ist eine gültige Karte und eine gültige Badge. In einer gemeinsamen Welt würde Durchgang 2 der Zuordnung (»identisch, irgendwo«) eine gelöschte Karte als »in die Badges verschoben« lesen, und jede Eindeutigkeitsprüfung zählte Fremde mit.

### 2. Rücknahme nach Entscheidung 15 – mit einer zweistufigen Eindeutigkeit

Die Tabelle aus Entscheidung 15 gilt unverändert, mit `badges` statt Kartenliste: bearbeitet (neu entfernen, alt am alten Platz einsetzen), verschoben (dort entfernen, am alten Platz einsetzen), hinzugefügt (entfernen), gelöscht (am alten Platz einsetzen, es sei denn, sie ist schon wieder da). »Alles oder nichts« gilt über Karten, Badges, Einstellungen (M) und Ansichten hinweg.

Die Frage »steht, was die Änderung hinterlassen hat, genau einmal da?« wird in zwei Stufen beantwortet:

1. **Die Änderung hat im ganzen Dashboard genau eine solche Badge hinterlassen, und heute steht genau eine da** → diese Fundstelle. Das deckt auch eine Badge, die seither in eine andere Ansicht verschoben wurde.
2. **In der Ansicht, in der die Änderung sie hinterlassen hat, stand damals genau eine und steht heute genau eine** → diese Fundstelle. Die übrigen sind dieselbe Badge auf anderen Ansichten, also andere Badges; die Ansicht selbst ist über ihren Pfad oder über die Positionsprüfung (`_positions_lie`) bestimmt.
3. Sonst verweigert: steht in der eigenen Ansicht heute weniger davon als damals, »changed again after this«; sonst mehrdeutig (»N badges now look exactly like …«).

Beide Stufen vergleichen den heutigen Stand mit dem unmittelbar nach der Änderung, nicht nur den heutigen allein. »Heute genau eine« ist kein Beweis, wenn die Änderung mehrere hinterlassen hat: Die einzige Überlebende kann die sein, die schon vorher dastand, und ein Undo würde dann eine Badge entfernen, die die Änderung nie berührt hat (Review vom 2026-09-25, K1).

Stufe 2 ist kein Raten: Sie beantwortet genau die Frage, die Entscheidung 15 stellt, nur an der Stelle, an der die Änderung die Badge hinterlassen hat, statt über das ganze Dashboard.

**»Gelöscht, ist aber wieder da« wird gezählt, nicht nachgeschlagen.** Eine gelöschte Badge gilt als bereits zurück, wenn sie heute in der Ansicht, aus der sie gelöscht wurde, **öfter** vorkommt als unmittelbar nach der Änderung. Hat die Änderung mehrere gleiche aus derselben Ansicht gelöscht, gelten sie nur alle zusammen als zurück. Ist erst ein Teil wieder da, wird verweigert: Welche Plätze die zurückgekehrten eingenommen haben, steht in keinem Stand, und einen zu wählen wäre geraten (Nachprüfung vom 2026-09-25). Gezählt wird nur in der eigenen Ansicht, nicht im ganzen Dashboard: Eine Kopie, die seither auf einer anderen Ansicht dazukam, ist ebenso wenig die gelöschte wie eine, die dort immer stand. Der Preis ist bewusst gewählt: Wer eine gelöschte Badge von Hand auf einer *anderen* Ansicht neu angelegt hat, bekommt sie bei der Rücknahme zusätzlich am alten Platz zurück – die additive Antwort aus Entscheidung 4, ehrlicher als ein »nichts zu tun«, das nicht stimmt (Review vom 2026-09-25, K2 und K3). Bloßes Vorhandensein reicht nicht: Die Kopie derselben Badge auf einer anderen Ansicht war nie weg und ist nicht die gelöschte, die zurückkam. Genau diese Verwechslung steckt im **bestehenden Karten-Undo** – beim Schreiben dieser Spec am Code nachgewiesen und in `status.md` als eigener Befund vom 2026-09-24 festgehalten: Wird eine Karte aus einer Ansicht gelöscht, während eine identische auf einer anderen unberührt steht, antwortet der Undo »this change is already taken back«. Für Badges, bei denen Kopien über Ansichten der gemessene Normalfall sind, würde dieselbe Regel regelmäßig zuschlagen; sie wird hier deshalb gleich richtig gebaut. Die Karten-Seite ist nicht Teil dieses Vorhabens.

### 3. Schritte und Anwendung

`UndoStep` bekommt `kind="badge"` mit `location=("badges",)`. `apply_undo` behandelt Badge-Schritte beim Entfernen und Einsetzen genauso wie Kartenschritte – absteigend entfernen, aufsteigend einsetzen; Listen verschiedener Welten beeinflussen sich dabei nicht. Beim Einsetzen legt `apply_undo` die `badges:`-Liste an, wenn sie fehlt oder `null` ist (dieselbe Vorsicht wie bei `sections: null` in `reinsert` und bei `cards:` in Vorhaben L).

### 4. Wörter

**Erklärung.** Jede Badge-Änderung wird ein `Entry` mit `what="badge"` und den Arten `added` / `removed` / `edited` / `moved`. Beschriftung über `_describe` (»entity: sun.sun«, für die alte Form ohne `type` »card: …« – siehe »Entscheidungen«, Punkt 3). Texte, damit eine Badge nicht wie eine Karte klingt:

| Was die Änderung tat | Vergangenheit (`explain_change`) | Zukunft – Vorschau ihrer Rücknahme (`explain_effect`) |
|---|---|---|
| hinzugefügt | `the badge entity: sun.sun was added` | `the badge entity: sun.sun will be deleted` |
| gelöscht | `the badge entity: sun.sun was deleted` | `the badge entity: sun.sun comes back` |
| bearbeitet | `the badge entity: sun.sun was changed` | `the badge entity: sun.sun goes back to how it was` |
| verschoben | `the badge entity: sun.sun was moved` / `… was moved to "Küche"` | `… moves back to where it was` / `… moves back to "Küche"` |

**Reihenfolge in einer Ansichtsgruppe:** Konvertierung (#32), Einstellungen (M), Badges, Karten – von oben nach unten, wie HA sie auf dem Schirm zeigt.

**Verlaufszeile.** Ein Teil `N badge(s) changed` in `change_message`, `Summary` bekommt `badges`, `_COUNT` wird im selben Zug erweitert (dieselbe Begründung wie in M). `message_adds` bleibt unberührt – Badges werden nie per Put back zurückgeholt, also gibt es keine Falle, vor der sie warnen müssten.

## Fehler- und Randfälle

| Fall | Verhalten |
|---|---|
| Badge `sun.sun` hinzugefügt, seither unverändert | Undo exakt: entfernt |
| Dieselbe Badge steht außerdem auf zwei anderen Ansichten | exakt über Stufe 2 |
| Badge seither in eine andere Ansicht verschoben, dort einzig | exakt über Stufe 1 |
| Badge seither bearbeitet | verweigert, »changed again after this« |
| Zwei gleiche Badges in derselben Ansicht | verweigert, mehrdeutig (in der Prüfbank nicht vorhanden) |
| Badge aus Ansicht A gelöscht, dieselbe Badge steht unberührt auf Ansicht B | wird in A wieder eingesetzt – die Kopie auf B zählt nicht als »schon zurück« |
| Badge gelöscht und seither in A von Hand wieder angelegt | nichts zu tun, »already taken back« |
| Badge aus A gelöscht, seither unabhängig eine gleiche auf C angelegt, A weiterhin ohne | wird in A wieder eingesetzt; die auf C bleibt |
| Zwei gleiche Badges aus A gelöscht, seither eine wieder angelegt | verweigert, »only some of the copies … are back« – welcher Platz noch fehlt, ist nicht zu beweisen (auf der Prüfbank: 0 gleiche Badges in einer Ansicht) |
| Badge aus A und aus B gelöscht, seither nur in A wieder angelegt | wird in B eingesetzt; A gilt als zurück |
| Badge auf B hinzugefügt, während dieselbe auf A schon stand; seither die auf B von Hand gelöscht | verweigert, »changed again after this« – die auf A wird nicht angefasst |
| Badge und identische `entity`-Karte im selben Dashboard | getrennte Welten; keine Zuordnung über die Grenze, keine gegenseitige Mehrdeutigkeit |
| Badge als bloße Zeichenkette (alte HA-Form, `- sun.sun`) | funktioniert: Fingerabdruck und Beschriftung arbeiten mit Zeichenketten; die Beschriftung ist die Zeichenkette selbst. Weil `_weak_key` sie nicht benennt, wird eine geänderte Zeichenkette als »gelöscht + hinzugefügt« gelesen, nie als »bearbeitet« – die Rücknahme ist trotzdem exakt, sie hat dann eben zwei Schritte |
| Ansicht ohne `badges:`, Undo setzt eine ein | Liste wird angelegt |
| Badge einer pfadlosen Ansicht, deren Position seither wackelt | `_POSITION_REFUSAL`, unverändert |
| Badge in einer `heading`-Karte | Teil der Karte, unverändert wie heute |

## Test-Plan

**pytest (`tests/test_analyze.py`, `tests/test_restore.py`):**

- `match_badges`: hinzugefügt, gelöscht, bearbeitet, innerhalb der Liste und zwischen Ansichten verschoben; `match_cards` unverändert (alle bestehenden Tests bleiben grün); eine `entity`-Badge und eine gleiche `entity`-Karte werden nie einander zugeordnet.
- `plan_undo`: jede Zeile der Tabelle oben, insbesondere Stufe 1, Stufe 2 und der mehrdeutige Fall; Badge und Karte in derselben Änderung.
- `apply_undo`: Einsetzen legt `badges:` an; Entfernen und Einsetzen in derselben Liste in richtiger Reihenfolge; Eingabe bleibt unverändert.
- Erklärung und Verlaufszeile: Texte, Reihenfolge in der Gruppe, `_counts` liest `N badges changed`.

**Laufende Instanz (`tests/integration/run_checks.py`):** Eine Badge über die API hinzufügen, auf einer zweiten Ansicht dieselbe Badge stehen lassen, Undo – verfügbar, schreibt, die zweite Ansicht behält ihre.

## Entscheidungen (am 2026-09-24 vom Nutzer bestätigt)

1. **Zweistufige Eindeutigkeit** statt der dashboardweiten Zählung, die Karten haben. **Bestätigt am 2026-09-24.** Begründet mit der Messung oben (6 von 23 Badges sind Kopien über Ansichten hinweg, 0 innerhalb einer Ansicht). Mit der Kartenregel wäre der Undo für diese Badges immer verweigert.
2. **Ein Zählteil `N badges changed`** statt vier (`added`/`removed`/…). **Bestätigt am 2026-09-24.** Hält die Verlaufszeile kurz; die Erklärung darunter nennt die Einzelheiten.
3. **Beschriftung der alten Badge-Form ohne `type`.** **Bestätigt am 2026-09-24**, umgesetzt im Plan als Parameter `fallback` an `_describe`. `_describe` setzt dann »card« als Art ein (»card: sun.sun«). Vorschlag: für Badges »badge« als Ersatz – ein zusätzlicher Parameter an `_describe`, oder eine kleine eigene Funktion daneben. Reine Wortfrage, aber sichtbar.
