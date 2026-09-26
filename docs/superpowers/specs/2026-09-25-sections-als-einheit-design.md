# Design: Sections als Einheit

**Datum:** 2026-09-25, überarbeitet 2026-09-26 nach vier Runden externem Review und dem Plan-Review
**Status:** Entwurf – im Dialog am 2026-09-25 abschnittsweise bestätigt, externe Reviews (Terra; dann Astra und Gemini; dann zwei Bestätigungsrunden mit Codex und Gemini) am 2026-09-26 eingearbeitet, schriftliche Freigabe steht aus
**Vorhaben:** O aus dem Abschnitt »Reihenfolge der Vorhaben« der Haupt-Spec
**GitHub-Issue:** [#31](https://github.com/PPP01/ha-dashboard-history/issues/31)
**Integration:** `dashboard_history`
**Bindend bei Widerspruch:** die Haupt-Spec (`2026-08-30-dashboard-history-design.md`), insbesondere Entscheidung 4, 15 und 26, sowie die Spec zu Vorhaben L (`2026-09-24-importierte-karten-design.md`)

## Kontext & Ziel

Eine Section trägt keine Kennung, und die Integration kennt sie bis heute nur als Index: Eine Karte in einer Section sitzt an `("sections", i, "cards")`, und `_place` vergleicht genau diesen Index. Verschiebt jemand eine unveränderte Section, hat für `match_cards` jede ihrer Karten den Platz gewechselt. Issue #31 beschreibt zwei Folgen: Das Undo schrieb einen Stand, den es nie gab, und die Anzeige beschreibt etwas, das nicht passiert ist.

Die erste Folge ist inzwischen geschlossen, die zweite nicht. Ziel dieses Vorhabens ist, Sections **von außen nach innen** zuzuordnen, so wie das Issue es vorschlägt: erst die Sections als ganze Blöcke, dann die Karten. Eine Section, die verschoben wurde, hinzukam, verschwand oder deren eigene Einstellungen sich änderten, wird als genau das erkannt, benannt, gezählt und exakt zurückgenommen.

### Verifizierte Ausgangslage (2026-09-25, am Quelltext und im Testcontainer nachgeprüft)

| Feststellung | Beleg |
|---|---|
| Undo schreibt keinen falschen Stand mehr: `_section_marks` vergleicht jede Section-Einstellung außer `cards`, nicht mehr nur `title`. Hat die Änderung Sections umgebaut, verweigert `plan_undo` mit `_SECTIONS_REBUILT_REFUSAL` | `analyze.py`, `_section_marks`, `_section_drift`; der »Until then«-Fallback aus #31, mit Vorhaben L gekommen |
| `_sections_lie`, das das Issue nennt, gibt es nicht mehr | ersetzt durch `_section_drift` (Vorhaben L) |
| Karten einer Section werden über den Index adressiert; `_place(slot) = (view_key, location)` | `analyze.py`, `card_containers`, `_place` |
| Zwei vertauschte Sections mit gleichen Einstellungen erscheinen als N Karten-Bewegungen | Testcontainer, Dashboard `test_2`, Ansicht `a2`, Commit `3c386398`: Zeile »test-2: 5 moved«, fünf Einträge »… was moved to (another) section« |
| Das Undo desselben Falls ist mit heutigem Code **nicht** verweigert, sondern exakt, aber in 10 Schritten (5× entfernen + einsetzen) | nachgerechnet mit `plan_undo` am 2026-09-25; die Ambiguitäts-Meldung im Panel stammte aus Code vor dem #36-Fix, den der laufende HA-Prozess noch geladen hatte |
| Eine verschwundene Section wird bei »Put back« schon heute als ein Stück angeboten, aber nur, wenn genau eine verschwand und jede ihrer Karten unter denen ist, die das Matching aufgegeben hat | `find_removed`, `_sections_gone` (Vorhaben F, Paket 3) |
| `setting_changes` sieht Section-Einstellungen nicht: `sections` steht in `_NOT_VIEW_SETTINGS` | `analyze.py` |
| `_section_marks` vergleicht mit Python-`==`, nicht streng: `column_span: 1` und `column_span: true` gälten als gleiche Einstellung – dieselbe Lücke wie #28 bei Karten, nur noch nicht geschlossen | `analyze.py`, `_section_marks`; Terra-Review 2026-09-26, Mittel 4 |
| Das Panel nutzt von einem Erklärungseintrag nur `kind` (CSS-Klasse) und `text` | `panel/render.js:52` |
| Prüfbank: 27 Sections-Ansichten, 102 Sections; Schlüssel `cards` (102), `type` (92), `column_span` (16), `title` (0); 72 beginnen mit einer `heading`-Karte; 1 leer; **0 doppelte Sections innerhalb einer Ansicht** | Prüfbank 2026-09-25 |

Die letzte Zeile trägt die Identitätsregel dieses Vorhabens: Exakte Gleichheit reicht in der Praxis, um eine Section in ihrer Ansicht eindeutig zu finden.

## Nicht-Ziele (YAGNI)

- **Keine Identitätskette.** Entscheidung 16 bleibt ungebaut. Die Zuordnung arbeitet nur mit exakter Gleichheit zwischen zwei Ständen.
- **Keine Ähnlichkeits-Zuordnung von Sections.** Eine Section, die im selben Save verschoben *und* bearbeitet wurde, erzeugt kein Section-Ereignis für die Anzeige (Abschnitt 1) – ihre Karten werden dort weiterhin einzeln erklärt, wie heute. Ihr *Undo* verweigert jedoch für die ganze Ansicht (Abschnitt 4, »Kein Rest darf bleiben« – dritte Korrekturrunde 2026-09-26, nach einem weiteren Codex-Fund zu einer schwächeren Zwischenfassung dieser Regel). Praktisch kommt der Fall kaum vor: HA speichert in Sections-Ansichten jede Operation sofort.
- **Sections, die zwischen Ansichten wandern,** bleiben »hier verschwunden, dort hinzugekommen«.
- **Keine Änderung am Karten-Undo in seither verschobenen Sections.** Vorhaben L parkt dort weiter. Die neue Zuordnung könnte die Adresse künftig übersetzen statt zu parken; das ist ein mögliches Folge-Vorhaben, nicht Teil von O.
- **Keine Änderung an `_reordered` für Karten.** Die Zählung bewegter *Karten* bleibt, wie sie ist; die kleinste-Bewegungen-Regel gilt nur für Sections.
- **Kein Schalter für die Beweisregel.** Siehe »Entscheidungen«, Punkt 3.
- **Masonry-, Sidebar- und Panel-Ansichten** sind nicht betroffen; sie haben keine Sections.

## Entwurf

Drei Pakete, jedes für sich committbar und prüfbar: **O1** Zuordnung und Anzeige (rein lesend), **O2** Undo, **O3** Put-back-Anker.

### 1. Die Zuordnung: `match_sections` (O1)

Neue Funktion `match_sections(old, new) -> SectionMatching` in `analyze.py`. Sie läuft je Ansicht, die in beiden Ständen unter demselben Schlüssel vorkommt, über deren `sections`-Liste. Eine Section wird über den Fingerabdruck ihres ganzen Inhalts verglichen (`fingerprint`, also streng, `1` ≠ `True`); »eigene Einstellungen« (alles außer `cards`) werden ebenfalls über ihren Fingerabdruck verglichen, nicht mehr mit `==`. `_section_marks` selbst wird auf diesen strengen Vergleich umgestellt (Terra-Review 2026-09-26, Mittel 4) – das schließt für Sections dieselbe Lücke, die #28 für Karten schon geschlossen hat, und `_section_drift` (Vorhaben L) erbt die Schärfung, ohne dass sich an seiner Signatur etwas ändert.

Durchgänge, in dieser Reihenfolge:

1. **Identisch, gleicher Index.** Der Normalfall.
2. **Identisch, anderer Index derselben Ansicht.** Eine verschobene Section, oder eine, die durch Löschen oder Einfügen davor nachgerückt ist. Bei mehreren Kandidaten der erste freie in Schreibreihenfolge (Sections in aufsteigender neuer Position durchsucht, für jede alte Section in aufsteigender alter Position). Zwei bytegleiche Sections austauschbar zu behandeln ändert nichts am Ergebnis: Da beide Seiten exakt gleich sind, schreibt jede Zuordnung zwischen ihnen dieselben Bytes zurück; ambig ist höchstens die Beschriftung (»diese oder jene Section bewegt«), nie der geschriebene Zustand. Der Schreibpfad (Abschnitt 4) verlässt sich ohnehin nicht auf diese Paarung, sondern weist Eindeutigkeit im jeweils maßgeblichen Stand selbst noch einmal nach.
3. **Gleicher Index, gleiche Karten, andere eigene Einstellungen** → Einstellungen geändert. »Gleiche Karten« heißt: Fingerabdruck der `cards`-Liste gleich.
4. **Gleicher Index, gleiche eigene Einstellungen, andere Karten** → dieselbe Section, Änderungen darin. Das ist der häufigste Save überhaupt (Karte darin bearbeitet) und entspricht dem heutigen Verhalten: keine neue Zeile, keine neuen Schritte, die Karten laufen normal durchs Karten-Matching.

**Kein fünfter Durchgang, der rät.** Was nach 1–4 übrig bleibt, wird **nicht** pauschal als »verschwunden« bzw. »hinzugekommen« gemeldet (frühere Fassung dieser Spec tat das und geriet dadurch in Widerspruch zu Abschnitt 4 – Terra-Review 2026-09-26, Kritisch 2: Eine Section, die im selben Save verschoben *und* bearbeitet wurde, wäre so als Section-Ereignis *und* ihre einzelnen Karten gleichzeitig als Karten-Ereignis gemeldet worden, und §4 verweigert genau diese Mischung wieder). Stattdessen gilt für den Rest dieselbe Probe wie für das bestehende `_sections_gone` (Vorhaben F, Paket 3), auf `match_sections`' eigene Größenordnung gehoben:

- **Verschwunden** wird eine übrig gebliebene alte Section nur gemeldet, wenn die Ansicht dabei genau eine Section weniger hat als vorher **und** jede ihrer Karten unter denen ist, die auch das Karten-Matching aufgegeben hat (nicht anderswo wiedergefunden wurden). Eine leere Section wird nie gemeldet – ohne Karten gibt es nichts, woran sich der Verlust beweisen ließe, und jede leere Section einer geschrumpften Ansicht sähe sonst gleich verloren aus.
- **Hinzugekommen** wird eine übrig gebliebene neue Section symmetrisch nur gemeldet, wenn die Ansicht genau eine Section mehr hat als vorher und jede ihrer Karten unter denen ist, die das Matching als neu übrig gelassen hat.
- **In jedem anderen Fall** – mehrere übrig gebliebene Sections, eine übrig gebliebene Section mit Karten, die auch anderswo herkommen oder hingehen, oder eine verschoben-und-bearbeitete Section – wird **kein Section-Ereignis** gemeldet. Die Section ist dann so, als gäbe es `match_sections` nicht: ihre Karten laufen unverändert durch die vier Durchgänge von `match_cards`, mit dem Index, den sie tatsächlich haben. Das ist dieselbe benannte Lücke, die »Nicht-Ziele« schon für den Fall »verschoben und bearbeitet« nennt, jetzt nur für jeden unbeweisbaren Rest verallgemeinert statt nur für diesen einen Fall.

**Verschoben** ist nicht jede gepaarte Section (Durchgänge 1–4), deren Index sich geändert hat. Unter den gepaarten Sections einer Ansicht gilt die längste Teilfolge, die ihre Reihenfolge von alt nach neu behält, als stehen geblieben; alle anderen gelten als verschoben. Bestimmt wird sie über die längste steigende Teilfolge (LIS) der neuen Indizes, gelesen in aufsteigender alter Reihenfolge; bei mehreren gleich langen Teilfolgen gewinnt die, deren erstes Element den kleinsten alten Index hat, danach bei erneutem Gleichstand den kleinsten neuen Index. So zählt ein Tausch zweier Sections als **eine** Bewegung, »erste von fünf ans Ende« ebenfalls als eine, und Nachrücken nach einem Löschen als keine.

`SectionMatching` trägt je Ansicht: `removed` und `added` (Section-Slots, nur die bewiesenen, s. o.), `moved` und `settings_changed` (Paare alt/neu, aus den Durchgängen 1–4), und eine Übersetzung **alter Index → neuer Index** für jede gepaarte Section (Durchgänge 1–4).

**Warum »gleicher Index« in Durchgang 3/4 kein Raten ist:** Die Haupt-Spec hält fest, dass eine Position eine Adresse ist, keine Identität (Entscheidung 4, `_positions_lie`) – aber sie behandelt eine Ansichts-Position trotzdem als Identität, *solange nichts sie widerlegt* (dieselbe Ansicht an derselben Stelle, mit gleichem Inhalt oder gleichem Titel). Durchgang 3/4 folgen demselben Muster für Sections: Nur wenn eine Section unter keiner stärkeren Probe (bytegleich anderswo, Durchgang 1/2) einer Bewegung zugeordnet werden kann, gilt ihr Index als das, was von ihrer Identität übrig ist – ausdrücklich ein Fallback für den unauffälligen Fall, keine Behauptung für den auffälligen (Terra-Review 2026-09-26, Hoch 1).

### 2. Karten innerhalb zugeordneter Sections (O1)

`match_cards` nimmt die Übersetzung aus `match_sections` entgegen. Der Platz einer alten Karte in einer gepaarten Section wird übersetzt: `("sections", i, "cards")` wird zu `("sections", neu(i), "cards")`, bevor Durchgang 1 (»identisch, am selben Platz«) und Durchgang 3 (»schwacher Schlüssel, am selben Platz«) vergleichen. Karten einer verschobenen Section finden ihren Partner dadurch in Durchgang 1 und erscheinen nicht mehr als Bewegung.

Überall, wo heute `_place(was) != _place(now)` über »an eine andere Stelle bewegt« entscheidet (`_explain`, `find_removed`, `_reordered`), gilt der übersetzte Platz.

**Karten von Sections ohne Section-Ereignis laufen weiter durch alle vier Durchgänge, unverändert.** Das betrifft sowohl bewiesen hinzugekommene/verschwundene Sections (Abschnitt 1) als auch jeden unbeweisbaren Rest. HA kann etwa eine Karte in einem einzigen Save in eine neu angelegte Section ziehen (bestehender Test `test_a_card_moved_into_a_new_section_is_not_a_deletion_at_all`); findet eine solche Karte einen Partner an anderer Stelle, ist sie eine Bewegung wie heute. Nur Karten einer *bewiesen* hinzugekommenen oder verschwundenen Section, die **keinen** Partner finden, werden in den Section-Eintrag eingerechnet und nicht einzeln gemeldet, so wie die Karten einer ganzen hinzugekommenen oder verschwundenen Ansicht. Eine Section ohne Section-Ereignis erzeugt keinen solchen Sammel-Eintrag; ihre Karten werden einzeln gemeldet, wie es das Karten-Matching ohnehin tut.

`Matching` bekommt ein Feld `sections: SectionMatching`. `match_badges` ist nicht betroffen: Badges liegen nie in Sections.

### 3. Anzeige (O1)

**Namensregel für eine Section**, eine für alle Stellen: `heading` der ersten Karte – nur wenn diese Karte `type: heading` trägt und ihr `heading`-Feld ein nichtleerer String ist, wie `_section_name` es heute schon prüft (Terra-Review 2026-09-26, Niedrig 1: eine gewöhnliche Karte mit einem zufälligen `heading`-Feld zählt nicht) –, sonst `title`, sonst die Position, einsbasiert (»section 2«). `_section_name` (heute: nur `heading`) und `_section_label` (heute: nur `title`) folgen danach derselben Regel.

**Erklärung (`_explain`)**, neue Einträge je Ansicht, mit vorhandenen `kind`-Werten, damit das Panel nichts Neues lernen muss:

| Fall | `kind` | Text (Vergangenheit) |
|---|---|---|
| verschoben | `moved` | `section "X" was moved` |
| hinzugekommen | `added` | `section "X" was added` |
| verschwunden | `removed` | `section "X" was removed` |
| Einstellung geändert | `edited` | `section "X": the setting "column_span" was changed from 1 to 2` – der Satz aus Vorhaben M, mit dem Section-Namen davor, einschließlich »set« und »removed« |

Die Zukunftsform für `explain_effect` folgt dem Muster der vorhandenen Tabellen `_PAST`/`_FUTURE`. Section-Einträge stehen in einer Ansicht vor den Karten-Einträgen, nach einer Konvertierung (#32).

**Zeile in der Historie (`change_message`):** neue Teile `N section(s) moved`, `N section(s) added`, `N section(s) removed`. Geänderte Section-Einstellungen zählen unter `setting(s) changed`. `_COUNT` wird um die drei Section-Teile erweitert. `message_adds` erkennt `section(s) added` als hinzugefügt: Eine Section, die dazukam, bleibt beim Put-back genauso stehen wie eine Karte. `summarize` zählt entsprechend.

**Alte Einträge:** Die Historie ist unveränderlich. Ein alter Commit behält seine Zeile (etwa »5 moved«), seine Erklärung wird aber live berechnet und zeigt künftig die Section-Bewegung. Diese Abweichung wird hingenommen (»Entscheidungen«, Punkt 4).

### 4. Undo (O2)

**Korrigiert 2026-09-26, zweite Runde.** Die erste Fassung dieses Abschnitts plante Section-Bewegungen, -Einfügungen und -Einstellungsänderungen als unabhängige Schritte mit je einem eigenen, statisch berechneten Index. Sowohl Astra als auch Gemini fanden dieselbe Lücke, unabhängig voneinander und mit ausführbaren Gegenbeispielen: Teilen sich mehrere einzusetzende Sections denselben Nachbarn (weil sie als zusammenhängender Block verschoben wurden), bekommen sie identische statische Indizes, und das nacheinander ausgeführte Einsetzen verschiebt sie gegenseitig in eine Reihenfolge, die es nie gab – ohne dass irgendeine Verweigerung greift. Astras Beispiel (`AXYZBWCD` → `ABCDWZYX`, alle vier Sections `X Y Z W` als Block bewegt) rekonstruiert so `AZWYXBCD` statt des Ausgangszustands. Das ist derselbe Fehlertyp wie in #31 gemeldet – ein still geschriebener Stand, den es nie gab –, nur durch diese Spec selbst neu erzeugt.

**Fix: kein Index mehr, der sich mit anderen Schritten verrechnen könnte.** Statt dreier Schritt-Arten mit eigener Adress-Arithmetik ersetzt genau **ein** Schritt pro betroffener Ansicht deren gesamte `sections`-Liste auf einmal. Es gibt dann nichts mehr, was sich gegenseitig verschieben kann, weil es nur noch einen Schreibvorgang gibt.

**Neue Schritt-Art an `UndoStep`:** `kind="sections_list"`, `action="set"`; `location=()`, `expect` = die heutige `sections`-Liste der Ansicht (vollständig, für den Steht-das-noch-Vergleich), `payload` = die rekonstruierte Zielliste. Kein `kind="section"` und kein `kind="section_setting"` mehr – beide entfallen zugunsten dieses einen Schritts. Es wird nicht geparkt: Für Sections gibt es kein »Imported sections«.

**Die Zielliste wird durch einen Merge gebaut, nicht durch Einzel-Indizes.** `plan_undo` durchläuft `before`s `sections`-Liste dieser Ansicht einmal, von vorn nach hinten, und ordnet jeder Position eine von zwei Herkünften zu:

- **Überlebend** (Durchgang 1 oder 3 aus Abschnitt 1: bytegleich am selben Index, oder nur die eigenen Einstellungen geändert): Inhalt = die heutigen Karten dieser Section (nicht `before`s Karten – ein späterer, unabhängiger Kartenedit in dieser Section soll erhalten bleiben) plus, bei einer Einstellungsänderung, `before`s Einstellungen statt der heutigen.
- **Wiederherzustellend** (verschoben, Durchgang 2, oder verschwunden, die `_sections_gone`-Probe aus Abschnitt 1): Inhalt = die heute gefundene, bewiesen bytegleiche Fassung (verschoben) oder `before`s eigene Fassung (verschwunden, existiert heute nicht).

Eine Durchgang-4-Section (nur Karten anders, Einstellungen gleich – der häufigste Fall, eine Karte darin bearbeitet) ist bewusst **kein** Überlebender in diesem Sinn: Ihre Karten wurden von der Änderung selbst berührt und laufen deshalb durchs gewöhnliche Karten-Undo, adressiert am heutigen Index. Trägt dieselbe Ansicht daneben einen `sections_list`-Schritt, kollidiert das über die Mischungs-Verweigerung weiter unten – dieselbe, bereits vor dieser Korrektur bestehende Einschränkung, nicht neu dadurch entstanden.

Eine hinzugekommene Section (bewiesen, Abschnitt 1) taucht in `before` gar nicht auf und fällt beim Durchlaufen automatisch heraus – nichts muss sie eigens entfernen. Das Ergebnis dieses einen Durchlaufs *ist* die Zielliste, in `before`s Reihenfolge, ohne dass irgendein Index einzeln berechnet oder mit einem anderen Schritt verrechnet werden müsste. Nachgerechnet an Astras Beispiel: Überlebende A, B, C, D an ihren Plätzen, X, Y, Z, W an ihren `before`-Plätzen eingereiht – das Ergebnis ist exakt `A X Y Z B W C D`, unabhängig davon, wie viele Sections sich einen Nachbarn teilen.

**Beweis je Section, unverändert streng, jetzt Teil eines Merges statt eines Einzelschritts:**

- **Hinzugekommen (fällt beim Merge aus der Zielliste heraus):** dieselbe zweistufige Probe wie bei Verschoben – die Section steht heute genau einmal, bytegleich mit ihrer Fassung nach der Änderung, **und** stand nach der Änderung dort genau einmal. Ohne diesen Beweis dürfte der Merge sie nicht stillschweigend weglassen: Sie könnte seither unabhängig weiterbearbeitet worden sein, und der Merge würde diese spätere Bearbeitung mit löschen, ohne dass eine Verweigerung das bemerkt (Codex-Review 2026-09-26, Frage 3 – in der ersten Fassung dieses Abschnitts, vor dem Merge-Umbau, stand dieser Beweis noch gemeinsam mit dem für Verschoben; beim Umbau auf den atomaren Schritt ging er für diesen Fall verloren).
- **Verschoben:** dieselbe Probe – die Section steht heute genau einmal, bytegleich mit ihrer Fassung nach der Änderung, **und** stand nach der Änderung dort genau einmal. Zweistufig wie `sole` seit #36, hier innerhalb der Ansicht.
- **Verschwunden:** die `_sections_gone`-Probe aus Abschnitt 1 (genau eine fehlt, jede ihrer Karten unter denen, die das Matching aufgegeben hat).
- **Einstellung geändert:** die Section steht heute genau einmal bytegleich mit ihrer Fassung nach der Änderung da (Einstellungen *und* Karten – ist seither auch nur eine Karte darin anders, ist das »seither geändert«, nicht mehr diese Probe).
- **Neu, für den Merge selbst nötig – die Überlebenden-Teilfolge:** Die Folge der überlebenden (unbewegten) Sections muss zwischen dem Stand nach der Änderung und dem heutigen Stand **identisch** sein – dieselben Sections, in derselben Reihenfolge. Ohne diese Probe könnte jemand die Überlebenden nach der Änderung selbst noch einmal umsortiert haben, und der Merge schriebe das still zurück auf `before`s Reihenfolge, statt es unangetastet zu lassen. Das ersetzt die frühere Nachbar-Suche »nächster nicht selbst eingesetzter Nachbar« vollständig – ein Nachbar musste dort gesucht werden, weil jede Section einzeln adressiert wurde; jetzt steht die ganze Reihenfolge auf einmal fest oder wird auf einmal verweigert. **Höchstens eine** Section darf seither bearbeitet worden sein: Nur dann ist ihre Identität erzwungen, weil alle anderen bytegleich an ihrem Platz stehen. Bei zwei oder mehr wäre die Zuordnung per Index geraten (Entscheidung 14).
- **Neu, für den Schreibschritt nötig:** `sections` muss vor der Änderung und heute eine echte Liste sein. Fehlt der Schlüssel oder ist er `null`, wird verweigert – der Schritt vergleicht und schreibt Rohwerte.

**Neue Verweigerungen**, als Sätze, die ein Mensch lesen kann:

- Eine beteiligte Section ist seither geändert oder nicht mehr eindeutig: `the section "X" was changed again after this, so there is no exact version left to take back` bzw. `N sections now look exactly like section "X", so an exact undo cannot tell them apart`.
- Die Überlebenden sind seither selbst umsortiert, ergänzt oder verkleinert worden: `the other sections of view X were rearranged since, so there is no telling where these go back`.
- **Kein Rest darf bleiben.** Nach Durchgang 1–4 und der `_sections_gone`-Probe (Abschnitt 1) bleibt in jeder Ansicht eine Menge unerklärter alter und eine Menge unerklärter neuer Sections übrig – im Normalfall beide leer. Ist **irgendeine der beiden Mengen nicht leer**, wird das Undo für die ganze Ansicht verweigert: `the sections of view X changed in a way this undo cannot account for, so it refuses rather than guess`. Kein Rückfall auf das gewöhnliche Karten-Undo mehr für diesen Fall – auch nicht, wenn die Mengen gleich groß sind oder ihre Einstellungen übereinstimmen.

  **Dritte Korrekturrunde (2026-09-26).** Eine Zwischenfassung erlaubte den Rückfall, wenn beide Restmengen gleich groß waren und ihre Einstellungen übereinstimmten. Ein zweites Gegenbeispiel von Codex zu genau dieser Fassung erwies sich bei eigener Nachrechnung als **nicht zutreffend**: In seinem Beispiel (`A` verliert seine einzige Karte, eine gleich eingestellte Section `T` verschwindet leer, eine neue gleich eingestellte Section `U` erhält genau diese Karte) laufen `T` und `U` am selben Index mit gleichen Einstellungen – das ist exakt Durchgang 4, der *vor* der »Kein Rest«-Prüfung greift und die beiden schon dort als eine Section mit reinem Karten-Edit erklärt; es entsteht also gar kein Rest. Bei der eigenen Suche nach einem *tatsächlich* tragfähigen Gegenbeispiel zeigte sich aber, dass die Grundidee trotzdem nicht robust zu retten ist: Bei zwei *unabhängigen*, gleichzeitigen »verschoben und bearbeitet«-Fällen in derselben Ansicht ist weder eine reihenfolge-sensitive noch eine mengenbasierte Prüfung der Einstellungsfolgen beider Restmengen gegen Verwechslung abgesichert, ohne eine echte Section-Identität (Entscheidung 16) zu unterstellen. Die einzige Fassung, die dabei nie rät, ist die jetzige: kein Rest, keine Ausnahme.

  **Konsequenz für den zuvor gemeinten Fall »verschoben und bearbeitet«** (Abschnitt 1, Nicht-Ziele): Er fällt jetzt ebenfalls unter diese Verweigerung, statt durchs gewöhnliche Karten-Undo zu laufen. Für die *Anzeige* (Abschnitt 1, `_explain`) ändert sich nichts – die Karten werden weiterhin einzeln erklärt, wie gehabt; nur das *Undo* verweigert jetzt zusätzlich für die ganze Ansicht. Das ist strenger als in der vorigen Fassung dieser Spec, mit Absicht: Die HA-Praxis speichert diesen Fall laut Ausgangslage ohnehin fast nie in einem Save, und Entscheidung 4 verlangt Verweigerung, sobald nicht mehr bewiesen, sondern nur noch plausibel gemacht werden kann.
- **Ein `sections_list`-Schritt und ein Karten-Schritt in derselben Ansicht:** verweigert. Ein `sections_list`-Schritt ersetzt die *ganze* Liste; ein Karten-Schritt für eine andere Section derselben Ansicht würde gegen eine Liste schreiben, die der `sections_list`-Schritt gerade schon ersetzt hat oder gleich ersetzt. Kommt praktisch nicht vor: Eine Section ohne eigenes Ereignis (Abschnitt 1) erzeugt gar keinen `sections_list`-Schritt, und die einzigen sonst denkbaren Kandidaten – Karte in neu angelegte Section gezogen, zwei Sections gleichzeitig verschwunden – verweigert schon der Section-Anzahl-Abgleich davor.

`_SECTIONS_REBUILT_REFUSAL` entfällt: Jede Section-Änderung ist jetzt entweder durch den `sections_list`-Schritt abgedeckt oder durch einen der Sätze oben verweigert. `_VIEW_TYPE_REFUSAL` (#32) bleibt davor und unverändert. `_section_drift` behält nur die Auskunft `shifted` (»seither verschoben«) für das Parken aus Vorhaben L; welche Ansichten die Änderung selbst umgebaut hat, sagt künftig `match_sections`.

**`apply_undo`**, erweitert, nicht umgebaut:

1. Einstellungen (Dashboard, Ansicht). Sie verschieben keinen Index.
2. Karten entfernen, höchster Index zuerst (nur in Ansichten ohne `sections_list`-Schritt, s. o.).
3. **`sections_list`-Schritte**, je Ansicht: `expect` gegen die heutige Liste prüfen, sonst `LookupError`; dann die ganze Liste durch `payload` ersetzen. Unabhängig voneinander je Ansicht, keine Reihenfolge zwischen ihnen nötig.
4. Ansichten entfernen, dann einsetzen.
5. Karten einsetzen, dann Geparktes (nur in Ansichten ohne `sections_list`-Schritt).

Der Vergleich in Schritt 3 geht über das vorhandene `_same_value`, damit `1` und `True` nicht als gleich gelten (#28). `restore.py` bleibt ohne Import von `analyze` zur Laufzeit; die Zielliste selbst bringt `plan_undo` bereits vollständig gebaut mit, `apply_undo` baut nichts nach.

**Test, der den ursprünglichen Fehler direkt nachstellt:** Astras `A X Y Z B W C D` → `A B C D W Z Y X`-Beispiel, wörtlich, als eigener Test – `apply_undo(...) == before`, nicht nur die Schrittzahl. Dazu eine Variante, bei der zusätzlich eine der Überlebenden-Sections (`B`) nach der Änderung noch einmal umsortiert wurde: muss die neue Überlebenden-Teilfolge-Probe verweigern.

**Aufrufer:** `operations.async_undo_change` prüft nach dem Anwenden ohnehin, ob das Ergebnis dem Stand vor der Änderung entspricht. Das bleibt der letzte Beweis und ändert sich nicht.

### 5. Put-back-Anker: Parken statt Raten (O3)

Die in Vorhaben L benannte Restlücke, genauer nachgeprüft am 2026-09-25: Sections A = [X, Y] und B = [], gleiche eigene Einstellungen. X wird gelöscht, danach werden die Sections vertauscht, heute also [] und [Y]. Genau dieselbe Konfiguration entsteht, wenn Y nach B gezogen wird. Beide Deutungen sind bytegleich; **auch `match_sections` kann sie nicht unterscheiden**, weil es nichts zu unterscheiden gibt. Heute gilt Y als »rechtmäßig weggezogen«, der Anker verlangt nur eine leere Section am alten Index, findet sie, und X landet dort. In der Tausch-Deutung ist das die falsche Section.

Der ehrliche Ausweg ist, nicht zu raten, sondern zu parken:

- `_SectionAnchor` bekommt ein Feld `departed`: die Karten, die im Stand, aus dem zurückgeholt wird, neben der zurückzuholenden in ihrer Section standen und seither in eine andere Liste **derselben Ansicht** gewandert sind (heute schon als »weggezogen« aus den Überlebenden herausgerechnet).
- `_anchored_index` in `restore.py` prüft zusätzlich: Steht eine Karte aus `departed` heute in einer *anderen* Section dieser Ansicht, deren eigene Einstellungen gleich denen des Ankers sind, dann passen »vertauscht« und »hinübergezogen« gleichermaßen. Der Anker gilt als nicht belegt, und die Karte wird geparkt (Mechanik aus Vorhaben L, unverändert). **Mehrdeutig zugunsten des Parkens:** Kommen für eine Karte aus `departed` mehrere gleich aussehende Kandidaten infrage – etwa zwei Karten mit identischem Fingerabdruck, von denen nur geraten werden könnte, welche tatsächlich weggezogen ist –, gilt der Anker ebenfalls als nicht belegt (Terra-Review 2026-09-26, Hoch 2). Diese Suche läuft wie die bestehende Überlebenden-Suche in `_anchored_index` über einfache Gleichheit, nicht über einen Fingerabdruck – `restore.py` hat zur Laufzeit keinen Zugriff auf `analyze.fingerprint` –, und erbt damit dieselbe, schon heute akzeptierte Unschärfe bei mehreren gleichen Karten; neu ist nur, dass diese Unschärfe hier zum sicheren Ausgang (parken) statt zum riskanten (an einen geratenen Index einsetzen) führt.
- In allen anderen Fällen verhält sich der Anker wie heute, einschließlich »neben dem Nachbarn einsetzen«.

Der Preis: Wer Y wirklich nur hinübergezogen hat, bekommt X geparkt statt direkt eingesetzt, mit Sternchen und Hinweis. Das ist sichtbar statt still, genau die Abwägung aus Vorhaben L.

## Fehler- und Randfälle

| Fall | Verhalten |
|---|---|
| Zwei Sections mit gleichen Einstellungen vertauscht (der Fall aus `test_2`) | »1 section moved«, ein Eintrag; Undo als ein `sections_list`-Schritt, Ergebnis gleich dem Stand vorher |
| Zwei Sections mit verschiedenem `column_span` vertauscht (der Fall aus #31) | wie oben; bisher verweigert |
| Erste von fünf Sections ans Ende | »1 section moved« |
| Section gelöscht, die anderen rücken nach | »1 section removed«, keine Bewegung; Undo setzt sie hinter ihrem alten Vorgänger wieder ein |
| Section hinzugefügt (HA legt leere Grid-Section oder eine mit »Neuer Abschnitt«-Überschrift an) | »1 section added«; Undo entfernt sie, wenn sie heute genau einmal und unverändert dasteht |
| Karte in eine neu angelegte Section gezogen | kein Section-Ereignis (die Karte ist nachweislich woanders hergekommen, nicht neu); Anzeige zeigt eine gewöhnliche Kartenbewegung; Undo verweigert trotzdem – der Section-Anzahl-Abgleich (Abschnitt 4) sieht eine unerklärte Section mehr in der Ansicht, wie heute |
| Section-Einstellung geändert, Section sonst gleich | ein Eintrag mit altem und neuem Wert; Undo setzt ihn zurück |
| Seither eine Karte in einer *anderen* Section derselben Ansicht bearbeitet | Undo der Section-Änderung geht weiter exakt durch |
| Seither Karten in *zwei oder mehr* anderen Sections derselben Ansicht bearbeitet | verweigert: welche Section welche ist, lässt sich per Index nicht mehr beweisen – sie könnten seither auch vertauscht worden sein (Entscheidung 14) |
| Seither eine Karte in der *beteiligten* Section bearbeitet | verweigert: seither geändert |
| `sections` fehlt oder ist `null`, vor der Änderung oder heute | verweigert: ein exakter Stand davor ließe sich nicht schreiben |
| Zwei byte-gleiche Sections in einer Ansicht (in der Prüfbank: keine) | Zuordnung paart sie in Schreibreihenfolge, für das Ergebnis folgenlos (Abschnitt 1); ein Undo, das eine davon *entfernen* müsste, verweigert trotzdem als mehrdeutig – die Probe in Abschnitt 4 ist unabhängig von dieser Paarung und verlangt Eindeutigkeit im maßgeblichen Stand selbst |
| Section verschoben und im selben Save bearbeitet (mit oder ohne zusätzliche Einstellungsänderung) | kein Section-Ereignis für die Anzeige, Karten dort weiterhin einzeln erklärt; Undo verweigert für die ganze Ansicht – »Kein Rest darf bleiben« (dritte Korrekturrunde 2026-09-26, nach zwei Codex-Funden zu schwächeren Zwischenfassungen dieser Regel) |
| Zwei Sections verschwinden gleichzeitig, oder eine verschwindet und ihre Karten verteilen sich auf mehrere andere | kein Section-Ereignis (die `_sections_gone`-Probe verlangt genau eine); Anzeige zeigt gewöhnliche Kartenbewegungen; Undo verweigert – ein nicht-leerer Rest auf der alten Seite |
| Eine hinzugekommene Section wurde seither unabhängig weiterbearbeitet (Codex-Review 2026-09-26, Frage 3) | Undo verweigert – der Hinzugekommen-Beweis (Abschnitt 4) verlangt bytegleich mit der Fassung nach der Änderung; der Merge darf sie sonst nicht stillschweigend weglassen |
| Ansicht inzwischen konvertiert | `_VIEW_TYPE_REFUSAL`, unverändert (#32) |
| Ansicht ohne Pfad, Position verschoben | `_POSITION_REFUSAL`, unverändert, vor jeder Section-Prüfung |
| Put-back, Nachbar seither in eine gleich eingestellte andere Section gewandert | geparkt (O3); bisher still in die Section am alten Index |
| Put-back, mehrere gleich aussehende Kandidaten für den weggezogenen Nachbarn | geparkt (O3, Terra-Review 2026-09-26, Hoch 2); nicht geraten |

## Test-Plan

**pytest (`tests/test_analyze.py`, `tests/test_restore.py`):**

- `match_sections`: jeder der vier Durchgänge einzeln; Nachrücken nach Löschen ist keine Bewegung; Tausch zweier Sections ist eine Bewegung; »erste von fünf ans Ende« ist eine Bewegung; zwei byte-gleiche Sections erzeugen dasselbe Ergebnis unabhängig von der Paarung; »verschoben und bearbeitet« erzeugt kein Section-Ereignis; zwei gleichzeitig verschwundene Sections erzeugen kein Section-Ereignis (die `_sections_gone`-Probe verlangt genau eine); Ansichten ohne Sections und Ansichten nur in einem Stand bleiben außen vor; der LIS-Algorithmus mit seinem Tie-Break liefert bei mehreren gleich langen Teilfolgen deterministisch dasselbe Ergebnis, geprüft mit einem Fall, der zwei gleich lange Kandidaten-Teilfolgen zulässt.
- `_section_marks`: `column_span: 1` gegen `column_span: true` gilt jetzt als verschieden (Regressionstest zur bisherigen `==`-Lücke).
- `match_cards` mit Übersetzung: Karten einer verschobenen Section sind nicht bewegt; eine Karte, die *innerhalb* einer verschobenen Section umsortiert wurde, ist weiter bewegt; eine Karte in eine neue Section gezogen bleibt eine Bewegung (bestehender Test unverändert grün); Karten einer gelöschten Section werden nicht einzeln gemeldet.
- Anzeige: die vier Eintragsarten; die Namensregel (`heading` → `title` → Position); die Zeile in der Historie; `_COUNT` und `message_adds` mit den neuen Teilen.
- Undo: der `test_2`-Fall (2 Schritte, Ergebnis gleich vorher); der `column_span`-Fall aus #31 (bisher verweigert, jetzt exakt); Section hinzugekommen, verschwunden, Einstellung geändert; »verschoben und bearbeitet«.
- Beweisregel: eine fremde Section seither geändert blockiert nicht; zwei fremde Sections seither geändert *und* vertauscht blockieren (Entscheidung 14); beteiligte Section seither geändert blockiert; Section- und Karten-Schritte in derselben Ansicht werden verweigert. (Die früheren Nachbar-Proben entfallen mit dem atomaren Schritt aus Entscheidung 11.)
- »Kein Rest darf bleiben«: eine Karte in eine neu angelegte Section gezogen verweigert (nicht-leerer Rest auf der neuen Seite); zwei Sections verschwinden gleichzeitig verweigert (nicht-leerer Rest auf der alten Seite); eine Section verschoben und im selben Save bearbeitet verweigert ebenfalls, auch wenn ihre Einstellungen unverändert blieben (Codex-Review 2026-09-26, zweiter Fund zur vorigen, schwächeren Fassung dieser Regel) – dasselbe Verhalten unabhängig davon, ob zusätzlich Einstellungen geändert wurden; ein durchgang-2-Vertausch mit zufällig gleichen Einstellungen (Codex' eigenes Gegenbeispiel dazu, bei eigener Nachrechnung nicht zutreffend) bleibt korrekt ohne Rest, weil Durchgang 2 vorher greift.
- Hinzugekommen-Beweis beim Merge (Codex-Review 2026-09-26, Frage 3): eine bewiesen hinzugekommene Section, seither unangetastet, wird beim Merge korrekt weggelassen; dieselbe Section, seither unabhängig weiterbearbeitet (eine ihrer Karten geändert), verweigert statt die Bearbeitung stillschweigend zu löschen.
- `apply_undo`/Merge (Abschnitt 4, nach der Korrektur vom 2026-09-26): Astras `A X Y Z B W C D`-Beispiel wörtlich, `apply_undo(...) == before`; dieselbe Konfiguration mit einer seither umsortierten Überlebenden-Section (verweigert, neue Probe); eine Rotation dreier Sections plus einer zusätzlich entfernten vierten; `LookupError`, wenn `expect` nicht mehr zur heutigen Liste passt; `1` gegen `True` in einer Section-Einstellung, über den Merge zurückgesetzt.
- O3: der Lückenfall aus Abschnitt 5 parkt; der normale Anker-Fall setzt weiter neben dem Nachbarn ein; ein weggezogener Nachbar in einer Section mit *anderen* Einstellungen parkt nicht; mehrere gleich aussehende Kandidaten für den weggezogenen Nachbarn parken statt zu raten.
- Echte Dashboards (Prüfbank): `match_sections(d, d)` paart jede Section in Durchgang 1, ohne Bewegung; »0 failed«.

**Bestehende Tests, die bewusst geändertes Verhalten festhalten** und im Plan einzeln umgeschrieben werden, mit Begründung statt stillschweigend: `test_undo_refuses_when_a_section_was_inserted_before_another`, `test_undo_refuses_when_two_untitled_sections_swap_settings`, `test_a_change_that_rebuilt_the_sections_says_so`. Der Plan prüft per Suche, ob weitere Tests `_SECTIONS_REBUILT_REFUSAL` oder den Text »rearranged the sections« erwarten, auch in `tests/integration/run_checks.py`.

**Bestehende Tests, unverändert grün, gegengeprüft (Terra-Review 2026-09-26, Niedrig 2/3):** `test_a_card_moved_into_a_new_section_is_not_a_deletion_at_all` bleibt gültig – die neue Section-Zuordnung ändert nichts an `0 removed, 0 added, 1 moved`, weil die neu angelegte Section ohne Beweis (nur eine Karte, kein zweiter Bezugspunkt) kein Section-Ereignis erzeugt und ihre Karte deshalb weiter normal gematcht wird. Ebenso unverändert gültig bleiben `reinsert`-Tests wie `test_a_card_refuses_to_go_back_into_a_different_section`, weil sie das Werkzeug prüfen, nicht die Politik, wann geparkt wird.

**Laufende Instanz (`tests/integration/run_checks.py`):** Zwei Sections einer Ansicht per WebSocket vertauschen. Erwartet: Zeile mit »1 section moved«, Undo ohne Verweigerung, nach dem Bestätigen liefert ein erneutes Laden über die API exakt den Stand davor. Zweiter Fall: Section hinzufügen und per Undo wieder entfernen.

## Erfolgskriterien

1. Der Fall aus `test_2`, Ansicht `a2`, erscheint als »1 section moved« mit einem Eintrag, und das Undo stellt exakt den Stand davor her.
2. Der `column_span`-Fall aus #31 ist exakt rückgängig zu machen statt verweigert.
3. `pytest` meldet 0 failed, `run_checks.py` ist grün, `restore.py` importiert `analyze` weiterhin nicht zur Laufzeit, die sieben Kernmodule bleiben ohne Home Assistant.
4. Jeder bestehende Test, der altes Verhalten festhält, ist im Plan benannt und begründet geändert.
5. Astras `A X Y Z B W C D`-Gegenbeispiel liefert `apply_undo(...) == before`.

## Dokumentation

- Haupt-Spec, Abschnitt »Reihenfolge der Vorhaben«: Buchstabe O mit Verweis auf diese Spec.
- `docs/superpowers/status.md`: Zeile O in der Tabelle, Eintrag zu #31 nach dem Muster der Einträge zu #32–#36.
- `docs/limitations.md`: der Absatz zu #31 und die Zeile zur Anker-Restlücke aus L.

## Entscheidungen (im Dialog am 2026-09-25 vom Nutzer bestätigt)

1. **Voller Umfang:** verschobene, hinzugekommene, verschwundene Sections und geänderte Section-Einstellungen, jeweils Anzeige und Undo, dazu die Anker-Lücke aus L. Alternativen waren »nur Anzeige« und »ohne Anker«.
2. **Ansatz: Section-Vorlauf in `match_cards`, exakte Identität, drei Pakete O1–O3.** Verworfen: ein Nachlauf, der bewegte Karten nachträglich zu Sections zusammenfasst (baut auf einer Paarung auf, die schon falsch sein kann, und gibt dem Undo keine Einheit), und eine synthetische Section-Identität (Entscheidung 16, für dieses Ziel überdimensioniert).
3. **Beweisregel: beteiligt und Nachbar, exakt und genau einmal – ohne Schalter.** Der Nutzer fragte nach einem Schalter »streng / locker«. Verworfen, weil die Korrektheitsfrage dann beim Nutzer läge, der nicht beurteilen kann, wann »locker« falsch schreibt, weil Entscheidung 4 Raten unabhängig von einer Einstellung ausschließt und weil jede Section-Prüfung doppelt getestet werden müsste. Der Mittelweg deckt den häufigen Fall ab (seither eine Karte in einer anderen Section bearbeitet) und rät trotzdem nie. Verworfen auch die strenge Fassung »ganze Ansicht unverändert«: einfacher, verweigert aber genau diesen häufigen Fall.
4. **Alte Zeilen in der Historie bleiben, wie sie sind;** ihre Erklärung wird live neu berechnet und kann von der Zeile abweichen (»5 moved« über »section … was moved«). Hingenommen; die Alternative, alte Erklärungen einzufrieren, wäre deutlich aufwändiger.
5. **Die Anker-Lücke wird durch Parken geschlossen, nicht durch Zuordnung.** Die Zuordnung kann den Fall nicht lösen, weil beide Deutungen bytegleich sind (Abschnitt 5). Bei der Umfangsfrage hieß die Option noch »nutzt die Section-Zuordnung«; das hat sich beim Nachprüfen als nicht machbar erwiesen, und dieser Punkt ersetzt es.
6. **Kein fünfter, ratender Durchgang.** Externes Review durch Terra (2026-09-26) fand einen echten Widerspruch: Die ursprüngliche Fassung meldete jede unter Durchgang 1–4 nicht erklärbare Section pauschal als »verschwunden plus hinzugekommen«, während §4 gleichzeitig Section-Schritte und Karten-Schritte in derselben Ansicht verweigert – eine verschoben-und-bearbeitete Section hätte beides gleichzeitig erzeugt. Ersetzt durch die auf `_sections_gone` gestützte Probe (Abschnitt 1): nur genau eine verschwundene bzw. hinzugekommene Section mit vollständig erklärten Karten wird gemeldet, alles andere fällt ohne Section-Ereignis auf das bestehende Karten-Matching zurück. Verworfen: die ursprüngliche Pauschal-Meldung, weil sie riet, wo kein Beweis war.
7. **Mehrdeutigkeit beim O3-Anker kippt zum Parken, nicht zum Raten.** Terra-Review, Hoch 2: Mehrere gleich aussehende Kandidaten für eine weggezogene Nachbar-Karte hätten sonst einen Anker als belegt gelten lassen können, obwohl nicht feststeht, welcher Kandidat gemeint ist. Ergänzt in Abschnitt 5.
8. **`_section_marks` wird auf strenge Fingerprint-Gleichheit umgestellt**, obwohl aus Vorhaben L, nicht ursprünglich Teil von O. Bestätigt im Dialog nach dem Terra-Review (Mittel 4): O baut seine eigene Zuordnung ohnehin auf strenger Gleichheit auf, und `_section_drift` (Parken aus L) über dieselbe Funktion inkonsequent bei `==` zu belassen wäre dieselbe Lücke wie #28, nur unrepariert liegen gelassen. Alternative (eigenes Ticket, unangetastet lassen) verworfen, weil der Aufwand mit einer Funktion, die O ohnehin überall anfasst, gering ist.
9. **Determinismus der Bewegungs-Erkennung vollständig festgeschrieben** (LIS über die neuen Indizes, Tie-Break über kleinsten alten dann kleinsten neuen Index), statt nur als Prinzip benannt (Terra-Review, Mittel 1). Ebenso die `section_setting`-Verdrahtung in `restore.py` (Mittel 2) und die Einfüge-Invariante bei mehreren Section-Schritten (Mittel 3) – beides war zuvor nur als Absicht, nicht als Rechenvorschrift formuliert.
10. **Section-Anzahl-Abgleich als eigene Verweigerung ergänzt (§4).** Beim Gegenlesen nach der Terra-Korrektur (Punkt 6) selbst gefunden, nicht Teil des externen Reviews: Ohne diesen Abgleich hätte eine Karte, die HA in eine frisch angelegte Section zieht, kein Section-Ereignis mehr erzeugt (ihre Karte ist nicht unmatched-neu) und wäre vom gewöhnlichen Karten-Undo zurückgeholt worden – und hätte dabei eine leere Section zurückgelassen, die im Stand davor nicht existierte. Derselbe Fehlertyp wie in #31 gemeldet, nur an neuer Stelle durch die Kritisch-2-Korrektur selbst eingeführt. Verworfen: den Fall stillschweigend hinzunehmen, weil er in der Prüfbank kaum vorkommt – widerspräche Entscheidung 4 trotzdem.
11. **Drei Section-Schritt-Arten durch einen atomaren `sections_list`-Schritt je Ansicht ersetzt (§4, zweite Korrektur vom 2026-09-26).** Zwei unabhängige externe Reviews (Astra und, separat beauftragt, Gemini) fanden denselben Fehler mit je einem eigenen, ausführbaren Gegenbeispiel: Teilen sich mehrere einzusetzende Sections denselben Nachbarn oder verschieben sich mehrere zugleich, verrechnet die statische Index-Berechnung sich selbst falsch und schreibt einen Stand, den es nie gab – exakt der Fehlertyp aus #31, nur an neuer Stelle. Verworfen: nur die Index-Arithmetik zu flicken (Astras und Geminis eigener Formulierungsvorschlag) – bewusst zugunsten des atomaren Ersatzes, der die ganze Fehlerklasse (jede Form von sich gegenseitig verschiebenden Einzelindizes) ausschließt statt sie Fall für Fall nachzubessern, auf ausdrücklichen Wunsch des Nutzers nach Vorlage beider Optionen.
12. **Hinzugekommen-Beweis beim Merge ergänzt (§4, dritte Korrektur vom 2026-09-26, erster Teil).** Bestätigungsrunde: Ein Codex-Review deckte eine Lücke auf, die erst durch die zweite Korrektur (Punkt 11) selbst entstanden war, während ein parallel beauftragtes Gemini-Review sie übersah (es rechnete nur die ursprünglichen Beispiele nach, suchte nicht adversarisch nach neuen). Der Hinzugekommen-Beweis fehlte schlicht – ein Beweis, den die allererste Fassung dieses Abschnitts noch hatte (gemeinsam mit »Verschoben« formuliert) und der beim Umbau auf den atomaren Merge (Punkt 11) versehentlich wegfiel.
13. **»Kein Rest darf bleiben« ersetzt die Einstellungsfolge-Probe (§4, dritte Korrektur, zweiter Teil).** Dieselbe Bestätigungsrunde brachte zunächst eine schwächere Zwischenfassung hervor: Rückfall auf gewöhnliches Karten-Undo erlaubt, wenn die unerklärten Restmengen gleich groß sind *und* ihre Einstellungen übereinstimmen. Ein zweites Codex-Gegenbeispiel dazu erwies sich bei eigener Nachrechnung als nicht zutreffend (der konkrete Fall lief über Durchgang 2, nicht über einen Rest) – die eigene, weitergehende Suche nach einem tragfähigen Gegenbeispiel zeigte aber, dass die Grundidee selbst brüchig ist: Bei zwei gleichzeitigen, unabhängigen »verschoben und bearbeitet«-Fällen in einer Ansicht lässt sich weder reihenfolge- noch mengenbasiert beweisen, welche Einstellungsfolge zu welchem Rest gehört, ohne eine Section-Identität (Entscheidung 16) zu unterstellen. Verworfen zugunsten der einfachsten, unangreifbaren Regel: jeder nicht-leere Rest verweigert, ausnahmslos. Preis: Der ursprünglich in Entscheidung 6 vorgesehene Rückfall für »verschoben und bearbeitet« entfällt – dieser Fall verweigert jetzt ebenfalls. Angenommen trotz des damit verbundenen Verhaltensverlusts, weil Entscheidung 4 in einem Zielkonflikt zwischen »seltener Rückfall« und »nie raten« eindeutig für Letzteres entscheidet, und weil dieser Fall laut Ausgangslage ohnehin praktisch nie vorkommt.
14. **Höchstens eine seither bearbeitete Section; `sections` muss eine echte Liste sein (§4, nach dem Plan-Review vom 2026-09-26).** Astra zeigte am konkreten Plan-Code mit einem ausgeführten Beispiel: Wurden seit der Änderung zwei überlebende Sections bearbeitet *und* vertauscht, paart Durchgang 4 sie per Index trotzdem als »an Ort und Stelle bearbeitet«, und der Merge schreibt still eine Reihenfolge, die es nie gab. Die Überlebenden-Probe erlaubt deshalb höchstens ein Paar aus Durchgang 3 oder 4 – dann ist dessen Identität durch Ausschluss erzwungen. Das ist strenger als der Wortlaut von Entscheidung 3 (»alle anderen Sections dürfen sich seither beliebig geändert haben«); eine Kartenänderung seither in *einer* anderen Section geht weiter durch. Terra zeigte außerdem, dass eine fehlende oder `null`-Section-Liste sich nicht exakt zurückschreiben lässt, weil die Zuordnung sie als `[]` liest; verworfen wurde, Rohwerte samt eines neuen Abwesenheits-Markers durch `restore` zu reichen, zugunsten einer Verweigerung für diesen handeditierten Randfall.

*Am 2026-09-25 beim Ausformulieren entschieden, seither nicht mehr strittig:* die Regel »kleinste Zahl von Bewegungen« für verschobene Sections (Abschnitt 1) statt der Rangfolge-Regel aus `_reordered`, und dass Karten ganz hinzugekommener Sections doch durch das Karten-Matching laufen (Abschnitt 2), weil HA eine Karte in einem Save in eine neue Section ziehen kann. Beide sind mit Punkt 6 verschmolzen: die zweite Regel gilt jetzt für *jede* Section ohne bewiesenes Section-Ereignis, nicht mehr nur für neu angelegte.
