# Design: Änderungshistorie und Wiederherstellung für Lovelace-Dashboards

**Datum:** 2026-08-30
**Status:** Entwurf zum Review
**Projekt:** `ha-dashboard-history` — Home-Assistant-Integration, später über HACS verteilt
**Integration:** `dashboard_history`

## Kontext & Ziel

Home Assistant kennt für Dashboards nur ein Rückgängig **innerhalb der laufenden Bearbeitung**. Verlässt man den Editor, ist die Historie weg. Wer eine Karte versehentlich löscht und es später bemerkt, hat nur den Weg über ein vollständiges Backup — und selbst hineinsehen, ohne wiederherzustellen, geht nicht.

Diese Lücke ist in der Community seit Jahren belegt und unbesetzt: Es gibt Dateiversionierung für die Konfiguration, aber nichts mit Änderungsansicht in der Oberfläche und gezielter Rücknahme.

Ziel ist eine Integration, die **jede Dashboard-Änderung erfasst**, den Verlauf pro Dashboard zugänglich macht und **Verschwundenes gezielt zurückholt** — Karten, Views — sowie ganze Stände wiederherstellt. Benannte **Versionen** fassen Punkte im Verlauf zusammen, ohne die Einzeländerungen darunter zu verlieren.

Vorbild ist die Versionsansicht von TYPO3 pro Seite.

**Erst für die eigene Anlage, Veröffentlichung später.** Der Entwurf enthält deshalb keine Annahmen, die nur auf einer Installation zutreffen: kein fester Pfad, keine Abhängigkeit von einem git-Programm, kein Eingriff in Home-Assistant-Interna.

### Verifizierte Ausgangslage (2026-08-30)

| Feststellung | Beleg |
|---|---|
| Lovelace-Karten haben **keine** stabile Kennung | 661 Karten im Standard-Dashboard, 0 davon mit `id`/`unique_id` |
| Views sind über `path` identifizierbar | 28 Views, 26 mit gesetztem `path` |
| Eine reine Python-Umsetzung von git genügt | `dulwich` mit `PURE_PYTHON=1`: Commit, Verlauf, alter Dateistand, Markierung — alle vier geprüft |
| Die C-Teile von `dulwich` sind optional | reine Geschwindigkeitszugaben, kein Muss |
| Zielumgebung | HA 2026.8.3, HACS 2.0.5, Container-Python 3.14.6 |
| Größtes Dashboard | `energie_2`: 570 KB als Storage-JSON, 268 KB als YAML |
| Zahl der Dashboards | zehn registrierte, dazu das noch unbenutzte Standard-Dashboard |
| Dashboard-`id` und `url_path` sind verschieden | `id=energie_2` gegen `url_path=energie-2`; die Ablage folgt dem `url_path` |
| Commit-Dauer, gemessen an diesem Dashboard | System-`git` 15,3 ms · dulwich 30,6 ms (mit C-Teilen) · dulwich 29,5 ms (rein Python) |
| Platzbedarf, gemessen | 20 Stände desselben Dashboards: 0,54 MB mit dulwich, 0,76 MB mit System-`git` — rund 27 KB je Stand |

## Nicht-Ziele (YAGNI)

- ~~Kein Panel.~~ **Am 2026-08-30 vorgezogen** — siehe Entscheidung 9. **Kein Eintrag im ⋮-Menü**; das bleibt ein eigenes Vorhaben, siehe »Reihenfolge«.
- ~~Kein Wiederanlegen gelöschter Dashboards.~~ **Am 2026-08-30 in den Umfang genommen**, siehe Entscheidung 8.
- **Keine Einzelrücknahme von Bearbeitungen** in dieser Fassung. Das Datenmodell hält die Tür offen, gebaut wird sie später.
  - **Erkannt werden Bearbeitungen und Umsortierungen trotzdem, von Anfang an.** Das ist kein Widerspruch, sondern Voraussetzung: Hielte `analyze.py` eine bearbeitete Karte für »gelöscht und neu hinzugefügt«, böte die Oberfläche an, etwas wiederherzustellen, das gar nicht fehlt. Ein solcher Fehlalarm ist schlimmer als eine fehlende Funktion — er untergräbt das Vertrauen in genau die Meldung, derentwegen man das Werkzeug öffnet.
- **Kein »von wem«.** Home Assistant feuert `lovelace_updated` ohne Kontext, der Benutzer ist an dieser Stelle nicht mehr bekannt. Der einzige saubere Weg ist ein Beitrag an HA Core; bis dahin bleibt das Merkmal weg. Ein Abfangen des WebSocket-Befehls wird **ausgeschlossen** — es ist ein Vertrag ohne Zusicherung und träfe bei einer Veröffentlichung alle Nutzer gleichzeitig.
- **Keine Schlagwörter an Versionen.** Titel und Beschreibung genügen zunächst.
- **Keine Aufbewahrungsgrenzen.** Erst messen, wie viel Platz git tatsächlich braucht, dann entscheiden.
- **Kein Ersatz für Backups.** Die Integration sichert Dashboards, nicht die Installation.

## Architektur

### Bausteine

| Datei | Aufgabe | Home-Assistant-frei |
|---|---|---|
| `keys.py` | Welches Dashboard welches ist, und welches fehlt | **ja** |
| `analyze.py` | Zwei Stände vergleichen und die Änderungen einordnen: Karte gelöscht, View gelöscht, bearbeitet, verschoben | **ja** |
| `restore.py` | Die Umkehrung anwenden: gelöschtes Objekt wieder einsetzen, oder einen ganzen Stand herstellen | **ja** |
| `store.py` | Das eigene Repository: Stände ablegen, Verlauf lesen, Versionen als Markierungen | **Kern ja** |
| `capture.py` | Auf Änderungen horchen, Stand holen, ablegen | nein |
| `operations.py` | Jeder Vorgang, genau einmal — Dienste und Panel sind dünne Häute darüber | nein |
| `websocket_api.py` | Befehle, auf denen das Panel aufsetzt | nein |
| `panel.py` + `panel.js` | Die Änderungsansicht in der Seitenleiste | nein |
| `services.py` | Dieselben Fähigkeiten für die Entwicklerwerkzeuge | nein |

### Wo Entscheidungen liegen müssen

*(Nachgetragen am 2026-08-30, nach vier Befunden aus dem Live-Betrieb.)*

Alle vier Fehler, die die Live-Prüfung fand, lagen in `capture.py`,
`services.py` und `snapshot.py` — den Modulen, die Home Assistant importieren
und die deshalb **kein Test erreichen kann**. Die Suite war dabei grün, mit
über neunzig Tests. Das ist keine Frage der Aufmerksamkeit, sondern der
Struktur: Was nicht prüfbar ist, wird nicht geprüft.

Daraus folgt eine Regel, die über die Trennung selbst hinausgeht: **Nicht nur
die Kernlogik, sondern jede Entscheidung gehört in die Home-Assistant-freien
Module.** Die HA-gebundenen Module dürfen holen, weitergeben und schreiben —
entscheiden sollen sie nichts. Umgesetzt bei `analyze.change_message` (die
Meldung, die einen Fehlalarm auslieferte) und in `keys.py` (welches Dashboard
welches ist, und welches fehlt — beides hatte dort, wo es vorher lag, schon
einmal einen Fehler).

Die drei oberen sind reine Logik und ohne laufendes Home Assistant prüfbar. Diese Trennung ist keine Stilfrage: Sie erlaubt, die Einordnungs-Regeln — das Herz des Projekts — in Sekunden gegen Dutzende Fälle zu testen, statt sie an einer Live-Anlage zu erproben.

### Datenmodell

- **Ein Änderungssatz ist ein Commit.** Jedes Speichern erzeugt genau einen, der die betroffene Dashboard-Datei berührt. Zeitpunkt und Dashboard stehen maschinenlesbar in der Commit-Botschaft.
- **Eine Version ist eine Markierung** (annotierte git-Markierung) mit Titel und Beschreibung. Sie **fasst nichts zusammen und löscht nichts** — sie markiert einen Punkt im Verlauf. Genau deshalb bleiben die Einzeländerungen darunter erhalten und einzeln rücknehmbar; in der Ansicht werden sie lediglich eingeklappt.
- **Eine Datei je Dashboard.** Der Verlauf eines Dashboards ist der Verlauf seiner Datei.
- **Gespeichert wird YAML**, nicht JSON: lesbar, wenn jemand ins Repository schaut, und mit deterministischer Ausgabe. Round-Trip-Treue ist harte Bedingung — was hineingeht, muss unverändert wieder herauskommen.
- **Das Repository gehört allein der Integration** und liegt im Konfigurationsverzeichnis. Es ist ein vollwertiges git-Repository; wer will, kann hineinschauen oder es extern weiterversionieren. Die Integration hängt davon nicht ab.

### Datenfluss

```
Speichern in der Oberflaeche
  └─► HA feuert lovelace_updated
       └─► capture.py holt den Stand DIREKT vom Lovelace-Objekt im Speicher
            └─► analyze.py vergleicht mit dem letzten Commit
                 └─► store.py legt einen Commit an (nur bei echter Aenderung)

Zurueckholen
  Dienst / WebSocket-Befehl
    └─► store.py liest den alten Stand
         └─► analyze.py bestimmt, was verschwunden ist
              └─► restore.py setzt es in den AKTUELLEN Stand ein
                   └─► Vorschau als Diff
                        └─► erst nach Bestaetigung: lovelace/config/save
```

## Schlüssel-Entscheidungen

1. **Der Stand kommt aus dem Speicher, nicht aus der Datei.** Home Assistant feuert `lovelace_updated`, **bevor** `.storage` geschrieben ist — ein Skript von außen muss deshalb warten und kann bei zu kurzer Wartezeit lautlos den vorherigen Stand aufzeichnen. Eine Integration läuft *in* Home Assistant und kann die Konfiguration direkt beim Lovelace-Objekt erfragen. Damit entfällt das Wettrennen vollständig. Erweist sich der Zugriff über HA-Versionen hinweg als unzuverlässig, bleibt der Dateiweg mit Wartezeit als Rückfall — dann aber mit einer Prüfung, ob der gelesene Stand wirklich neu ist.

2. **git als Ablage, nicht selbst gebaut.** Das Vorhaben *ist* Versionsverwaltung. Deduplizierung, Komprimierung, Verlauf, Diffs und Markierungen selbst zu implementieren wäre der klassische Fehlgriff. Preis ist eine Abhängigkeit; sie ist reine Python und läuft nachweislich auch ohne ihre optionalen C-Teile.

3. **Kein Systemaufruf von `git`** — auch nicht als bevorzugter Weg mit der Python-Umsetzung als Rückfall.

   Ob ein `git`-Programm vorhanden ist, unterscheidet sich zwischen HA OS, Container, Core und Supervised. Aber selbst wo eines liegt, lohnt der zweite Codepfad nicht. Gemessen am größten Dashboard dieser Anlage: **15,3 ms gegen 29,5 ms je Commit** — ein Unterschied von rund 15 Millisekunden, einmal pro Speichervorgang. Beide Wege müssten ohnehin in einen Hintergrund-Thread ausgelagert werden, weil 30 ms nichts im Event-Loop verloren haben; auch dort also kein Vorteil.

   Dem stünde eine verdoppelte Verhaltensfläche gegenüber, und die Unterschiede sind real. Beim ersten Messlauf trat sofort einer zutage: **`git commit` verweigert einen leeren Commit mit Exit-Code 1, dulwich legt ihn an.** Weitere sind absehbar — eine globale `commit.gpgsign`-Einstellung ließe `git` auf eine Passphrase warten, `safe.directory` kann den Zugriff verweigern, Hooks können dazwischenfunken. Nichts davon geschieht auf der eigenen Maschine; alles davon erzeugt in fremden Installationen Fehlerberichte, die sich nicht nachstellen lassen, weil unklar bleibt, welcher Pfad gelaufen ist.

   Nebenbefund derselben Messung: **Die C-Teile von dulwich bringen keinen messbaren Gewinn** (30,6 gegen 29,5 ms). Damit ist auch die Frage nach vorkompilierten Paketen je Architektur gegenstandslos. Und dulwich erzeugt das *kleinere* Repository.

   Sollte Geschwindigkeit später doch drücken, ist die Antwort nicht ein zweiter Pfad, sondern Bündelung mehrerer Änderungen in einen Commit.

4. **Zurückgeholt wird nur, was verschwunden ist — und ganze Stände.** Das ist keine Sparmaßnahme, sondern folgt aus der Datenlage: Karten haben keine Kennung, sind also nur über ihre Position bestimmt. Eine **ersetzende** Rücknahme (»diese Bearbeitung zurück, spätere behalten«) ist deshalb eine Zusammenführung ohne Identitäten und in verschränkten Fällen nicht eindeutig. Eine **additive** Rücknahme (»das hier fehlt, setze es wieder ein«) überschreibt nichts und ist immer wohldefiniert. Und die schmerzhaften Fälle sind genau die additiven: Eine verschobene Karte schiebt man zurück, eine gelöschte ist weg.

5. **Die Einzelrücknahme wird später *bedingt* angeboten, nicht mit Warnhinweis.** Ob eine ersetzende Rücknahme eindeutig ist, lässt sich feststellen: Man prüft, ob eine spätere Änderung denselben Bereich angefasst hat. Das Werkzeug entscheidet also selbst und sagt entweder »zurücknehmen« oder »geht nicht, weil …, hier sind die Alternativen«. Ein Warnhinweis wäre schlechter, weil er die Entscheidung an jemanden weiterreicht, der die Verschränkung nicht sehen kann.

6. **Vollständige Stände speichern, keine reinen Deltas.** Damit ist die Einzelrücknahme später eine reine Rechenfunktion über vorhandene Daten — nachrüstbar ohne Datenmigration. git dedupliziert die Stände ohnehin.

7. **Nichts wird ohne Vorschau geschrieben.** Jede Wiederherstellung zeigt zuerst den Diff. Derselbe Grundsatz wie beim bestehenden Restore-Werkzeug.

   **Die Regel gilt für Dashboards, nicht für Beschriftungen.** *(Grenze nachgetragen am 2026-08-31.)* Ihr Zweck ist, dass niemand sein Dashboard unversehens verändert findet. Eine Beschreibung nach Entscheidung 10 verändert kein Dashboard, ist sofort und vollständig zurücknehmbar und wird von der Person geschrieben, die sie gleich danach liest. Ein Bestätigungsdialog davor wäre Zeremonie ohne Schutzwirkung — und das Gegenteil dessen, wofür die Funktion gebaut wird. Sie verlangt deshalb **kein** `confirm`. Jeder Vorgang, der einen Dashboard-Stand schreibt, verlangt es weiterhin ohne Ausnahme.

9. **Das Panel fragt nach einer Änderung, nie nach einem Zustand.** *(Nachgetragen am 2026-08-30, aus der Beobachtung echter Bedienung.)*

   Die Dienste erwarten unter `revision` den *Zustand, gegen den verglichen wird*. Ein Mensch denkt aber in Änderungen: Soll eine Löschung zurückgenommen werden, greift er zu der Zeile, in der die Löschung steht — und das ist eine zu spät, denn gewollt ist der Zustand davor. Beim Erproben ist genau das passiert.

   Eine Warnung wäre die falsche Antwort, ein umbenanntes Feld auch. Die Oberfläche stellt die Frage schlicht nicht: Man klickt die Änderung an, und das Panel rechnet selbst aus, welcher Zustand gemeint ist. Die Stolperstelle wird nicht abgesichert, sondern entfernt.

   **Ergänzt am 2026-09-01, nach einer Beobachtung des Nutzers.** Die Regel trägt weiter, aber sie beantwortet eine Frage nicht: *Wo bin ich?* Beim Erproben lag ein Verlauf vor, in dem eine Karte mehrfach hoch und runter geschoben worden war — sieben Einträge, alle mit der Meldung »2 moved«, **jeder zweite inhaltlich identisch mit dem lebenden Dashboard**. Der Nutzer hielt Platz 2 für den aktuellen Stand, und das war nicht falsch: Er *ist* inhaltlich der aktuelle, nur nicht der neueste.

   Zwei Folgen daraus, beide ohne die Semantik anzutasten:

   1. **Der aktuelle Stand wird markiert und abgesetzt** — eigener Abschnitt »Current state« über einem Trenner »History«, Kennzeichen `current state`. Und **nachgerechnet, nicht angenommen**: Bei einer Änderung an Home Assistant vorbei ist der neueste Eintrag *nicht* der aktuelle Stand, und dann wird nichts gekrönt. Weitere Einträge mit gleichem Inhalt tragen `same as now`; das erklärt, warum eine solche Liste so gleichförmig aussieht.
   2. **Der Knopf verschwindet, wo er nichts täte.** Sein Ziel ist der Stand *vor* der Änderung; ist das der aktuelle Stand, ist er sinnlos. Bei einem Hin-und-Her-Verlauf trifft das jede zweite Zeile. Vorher erschien er dort und lieferte einen Dialog mit »No difference.« über einem aktiven »Apply« — obwohl `operations.async_restore_state` längst `note: "already identical"` zurückgab und das Panel die Angabe wegwarf. Zum vierten Mal in diesem Projekt hatte der Code recht und sein Bericht nicht.

   **Nachgeschärft am 2026-09-01, wieder auf eine Beobachtung des Nutzers.** Die Kennzeichen hießen erst `current state` und `same as now`. An einer echten Zeile las sich das so:

   ```
   dh-testlauf: 4 moved   [same as now]
   ```

   Als **ein** Satz gelesen ist das ein Widerspruch — vier Karten verschoben, und trotzdem unverändert? Nachgemessen war die Markierung korrekt: der Stand bei dieser Revision ist byte-identisch mit dem lebenden. Falsch war, dass eine Zeile **zwei Aussagen über zwei verschiedene Gegenstände** macht, ohne einen davon zu benennen: die Meldung spricht über die *Änderung*, das Kennzeichen über den *Stand danach*. Zwei einzeln wahre Aussagen ohne Bezugsrahmen sind zusammen eine falsche.

   Das Wort »state« ist deshalb tragend: `same state as now`, dazu ein Tooltip mit dem ganzen Satz. Und beim Aufklappen, wo Platz ist, steht er ausgeschrieben — mit »again«, weil das Dashboard zwischenzeitlich durchaus weg und wieder zurück gewesen sein kann.

   Beim neuesten Eintrag heißt der Knopf »Undo this change« statt »back to before this change«. Dasselbe Ziel, verständlicher formuliert, weil beim Neuesten nichts danach kommt.

   **Ausdrücklich nicht geändert:** Das Ziel bleibt der Stand *vor* der Änderung. Der Nutzer hatte »Rückgängig zu diesem Stand« vorgeschlagen, also Ziel-Semantik. Das holte die Falle zurück, die diese Entscheidung entfernt: Wer die Zeile anklickt, in der der Verlust *steht*, landete dann in dem Stand, in dem die Karte schon weg ist. Das Netz ist inzwischen stärker (die Klartext-Erklärung nennt Löschungen in Rot), aber ein Netz bleibt ein Netz.

   Daraus folgt auch, dass das Panel **keine eigene Logik** trägt. Alle Vorgänge liegen in `operations.py`; Dienste und Panel sind zwei dünne Häute über derselben Schicht. Sonst stünde das Wesentliche ausgerechnet dort, wo Home Assistant sich am häufigsten bewegt.

8. **Ein gelöschtes Dashboard wird wiederhergestellt, nicht nur betrauert.** *(Nachgetragen am 2026-08-30. Ursprünglich stand das Wiederanlegen außerhalb dieser Fassung.)*

   Das war falsch herum gedacht. Der schwerste Verlust, den dieses Werkzeug bezeugen kann, wäre dann der einzige gewesen, den es nicht rückgängig machen kann — während es für eine einzelne Karte alles bietet. Wer ein Dashboard löscht, verliert Hunderte Karten auf einmal.

   Der Preis ist bekannt und wird bewusst gezahlt: Ein Dashboard entsteht nur über die Dashboard-Sammlung von Home Assistant, und die ist kein zugesicherter Erweiterungspunkt. Deshalb gilt hier eine Trennung, die der Rest der Integration nicht braucht: **Das Dauerhafte muss gelingen, das Sofortige darf scheitern.** Registry-Eintrag und Konfiguration werden geschrieben; ob das Dashboard auch ohne Neustart in der Seitenleiste erscheint, ist Kür. Misslingt die Kür, wird das gemeldet, und ein Neustart genügt — der Verlust ist dann trotzdem behoben.

   **Am 2026-08-31 berichtigt — die Abstufung stand auf einer falschen Annahme.** Der Rückfall über eine zweite `DashboardsCollection` galt als »das Dauerhafte gelingt, das Sofortige ist Kür«. Das war falsch: Was er schrieb, war gar nicht dauerhaft *verwaltbar*.

   Die Ursache liegt in einer Zweiteilung in Home Assistant selbst. `DashboardsCollectionWebSocket` **überschreibt** `ws_list_item` und antwortet aus `LovelaceData.dashboards`; `ws_update_item` und `ws_delete_item` gehen dagegen an `self.storage_collection`, also an HAs eigenes Sammlungsobjekt. **Auflisten und Ändern lesen zwei verschiedene Quellen.** Der Rückfall füllte nur die erste — deshalb erschien das Dashboard überall, ließ sich öffnen und benutzen, und ein Umbenennen scheiterte mit »Unable to find dashboard_id«. Beobachtet wurde außerdem ein Zustand, in dem ein wiederhergestelltes Dashboard im Speicher stand und **nicht** auf der Platte; dessen Mechanismus ist nicht geklärt, ein Neustart hätte es dort verloren.

   Es gibt deshalb ab hier **einen** Weg: HAs eigenes Sammlungsobjekt. Auf 2026.8.3 liegt es nicht an `LovelaceData`, sondern ist eine lokale Variable in `lovelace.async_setup` — erreichbar über die Befehlsregistrierung, weil `ws_list_item` als *unverpackte* gebundene Methode registriert wird (nur eine `admin_only`-Sammlung legt einen Dekorator darum). Dann trägt HAs eigener Listener alles Weitere: Panel, Dashboard-Objekt und Store, alles in einem Zug und in sich stimmig.

   **Ist dieses Objekt nicht erreichbar, wird abgelehnt statt halb geschrieben.** Die Meldung nennt den Ausweg — Dashboard von Hand mit demselben `url_path` anlegen, dann erneut wiederherstellen, und die Karten kommen hinein. Ein halb wiederhergestelltes Dashboard, das gesund aussieht, ist schlechter als eine ehrliche Weigerung. Damit entfällt auch die `note`: Gelingt es, ist nichts mehr zu sagen.

   Die Lehre über die Abstufung hinaus: **Ein privater Zugriff ist nicht dadurch in Ordnung, dass er ein Ergebnis liefert.** Der Rückfall lieferte eines — es war nur nicht das, was es zu sein schien.

   Damit ein Dashboard *vollständig* wiederkehrt, werden ab dieser Fassung auch Titel, Symbol und Sichtbarkeit erfasst, nicht nur die Kartenkonfiguration. Sie liegen unter `meta/<schlüssel>.yaml` im selben Commit. Ein Dashboard mit richtigen Karten, aber falschem Namen wäre nur eine halbe Wiederherstellung.

10. **Ein eigener Text zu einer Änderung lebt als git note — und ersetzt die Versionen.** *(Nachgetragen am 2026-08-31, auf Wunsch des Nutzers.)*

    Die automatische Meldung sagt, *was* geschehen ist. Warum es geschehen ist, weiß nur der Mensch: »vor dem Umbau der Heizungskarten« findet man in einem Jahr wieder, »2 removed, 1 edited« nicht.

    Eine Commit-Botschaft nachträglich zu ändern ist dafür kein Weg. Ein Commit ist über seinen Inhalt adressiert; ihn umzuschreiben schreibt jeden Nachfolger um und macht damit genau die Revisionen ungültig, die Panel, Dienste und Antworten dieses Werkzeugs herumtragen. In einem Werkzeug, dessen Wert an der Zitierbarkeit von Revisionen hängt, wäre das die schlechteste denkbare Stelle für eine Umschreibung.

    Der Text liegt deshalb auf `refs/notes/commits`, geschrieben mit `porcelain.notes_add`. Genau dafür gibt es git notes: veränderlicher Kommentar an unveränderlichem Objekt. **Geprüft an dulwich 1.2.14 (2026-08-31):** anlegen, überschreiben und entfernen tragen, ein Commit ohne Notiz liefert `None` statt eines Fehlers, UTF-8 kommt unverfälscht zurück, und die Notiz-Commits liegen nicht in der Historie — nach zwei Notiz-Operationen führte der Walker weiterhin genau zwei Commits. Kein bestehender Lesepfad ändert sein Verhalten.

    Die beiden verworfenen Ablagen und der Grund: Eine Datei im Repository (`notes/<schlüssel>.yaml`) wäre für Hineinschauende sichtbarer, kostet aber je Notiz einen Commit **in** der Historie — Rauschen genau in der Liste, die aufgeräumt bleiben soll. Ein `Store` in `.storage` würde Beschriftung und Historie trennen: Eine eingespielte Sicherung hätte dann die eine ohne die andere.

    **Damit entfallen die Versionen als Konzept der Oberfläche.** Ein benannter Punkt ist ab hier einfach eine Änderung, der jemand einen Text gegeben hat — ein Stift an der Zeile, ein Dialog mit einem Feld, wie HAs »Umbenennen« bei einer Erweiterung. Ein leeres Feld nimmt die Beschreibung zurück. `create_version`/`versions` bleiben als **Dienste** erhalten, weil ein Tag etwas kann, was eine Notiz nicht kann: `resolve()` nimmt seinen Namen als Revision an, ein Tag ist also adressierbar. Sie rutschen in der README nach hinten. Zwei Wege in der Oberfläche für dieselbe Sache wären ein Konzept zu viel.

    Der eigene Text wird zur Überschrift der Zeile, die automatische Meldung zur grauen zweiten. Sie verschwindet nicht: Sie ist die Angabe, der man trauen kann, wenn die eigene Notiz von damals nicht mehr genug sagt.

11. **Der Diff bekommt eine Erklärung darüber — und ihre Worte entstehen in `analyze.py`.** *(Nachgetragen am 2026-08-31, auf Wunsch des Nutzers.)*

    Ein Unified-Diff über YAML ist für die meisten Menschen keine Antwort auf »was passiert mit meinem Dashboard«. Er bleibt, weil er die genaue Auskunft ist; er bekommt aber eine benannte, nach Ansicht gruppierte Zusammenfassung darüber. Namen, nicht Zahlen: »2 Karten« beruhigt niemanden, »Wohnzimmer Temperatur« schon. `_describe` und `_match_cards` können das bereits — die Erklärung ist keine neue Einordnung, sondern eine zweite Ausgabe der bestehenden.

    Zwei Eingänge über einem Motor, weil derselbe Sachverhalt in zwei Zeitformen gebraucht wird: `explain_change(alt, neu)` für den Verlauf (»was ist damals passiert«) und `explain_effect(jetzt, ziel)` für den Bestätigungsdialog (»was wird passieren«). Gleiche Struktur, zwei Wortlisten.

    Dass der **Wortlaut** dort entsteht und nicht im Panel, folgt aus dem Abschnitt »Wo Entscheidungen liegen müssen« — und aus der Erfahrung: Dreimal war in diesem Projekt der Code richtiger als sein eigener Bericht (der Fehlalarm »changed outside Home Assistant«, das irreführende »does not exist at«, das verschwiegene Rest beim Wiederanlegen). Wortlaut, der schiefgehen kann, gehört dorthin, wo `pytest` hinkommt.

    **Findet die Erklärung nichts zu benennen, behauptet sie nicht »nichts geändert«.** Sie sagt, dass diese Änderung sich nicht in Karten ausdrücken lässt, und verweist auf den Diff. Sonst widerspräche die Zusammenfassung dem Diff unmittelbar darunter, der den Unterschied sichtbar zeigt — und eine Zusammenfassung, die man beim Hinsehen widerlegt, ist schlimmer als keine.

    Der Diff steht in einem `<details>`, standardmäßig zu. Ob er offen oder zu startet, wird später einstellbar; der Platz dafür ist ein Options-Flow der Integration.

12. **Ein gelöschtes Dashboard kann endgültig vergessen werden — und nur ein gelöschtes.** *(Nachgetragen am 2026-09-01, auf Wunsch des Nutzers.)*

    Die Kehrseite von Entscheidung 8: Eine gelöschte Historie bleibt für immer auffindbar, und das ist richtig — aber nach genug Jahren ist die Liste überwiegend Grabsteine. Zwei Antworten darauf, und die erste ist die wichtigere.

    **Erstens werden gelöschte Dashboards eingeklappt**, nicht versteckt: lebende oben, darunter ein zusammengeklappter Abschnitt »Deleted (N)«. Reine Darstellung, nichts wird angetastet. Das Panel öffnet ab hier auf einem *lebenden* Dashboard; vorher wählte es das erste gelöschte, was bei einem Dutzend davon einen beliebigen Grabstein trifft.

    **Zweitens gibt es ein echtes Löschen.** Das ist die einzige unumkehrbare Operation dieser Integration, in einem Werkzeug gegen das Verschwinden von Dingen — deshalb dreifach eingezäunt: nur an einem Dashboard, das Home Assistant nicht mehr hat (`is_absent` antwortet `False`, wenn HA nicht befragbar ist, verweigert also im Zweifel); nur mit `confirm`; und mit einer Vorschau, die *zählt*, statt einen Diff zu zeigen — der Diff einer Löschung wäre die ganze Historie.

    **Der Preis ist benannt, nicht versteckt:** git kann nur wirklich löschen, indem es die Historie neu schreibt. Damit ändern sich alle Revisionen ab dem ersten betroffenen Commit. Daran hängen zwei Dinge, die sonst lautlos verschwinden würden:

    - **Beschreibungen** sind git notes, adressiert über den Commit-Hash. Sie werden vor der Umschreibung gelesen und auf die neuen Commits zurückgeschrieben. Eine Beschreibung auf einem Commit, der wegfällt, geht mit ihm — sie beschrieb einen Stand, den es nicht mehr gibt, und eine Beschreibung am falschen Stand ist schlechter als keine.
    - **Benannte Versionen** sind Tags. Sie werden mit ihrer ursprünglichen Botschaft und Zeit neu gebaut. Ein Tag auf einem wegfallenden Commit wandert auf den nächsten überlebenden Vorfahren, weil eine Version einen *Zeitpunkt der ganzen Historie* markiert und nicht ein Dashboard.

    Ein Commit, der nichts außer diesem Dashboard berührte, verschwindet ganz statt zu einem leeren Commit zu werden; seine Kinder werden umgehängt. Ein leerer Commit wäre ein anklickbarer Stand, der nichts sagt.

    **Und »unwiederbringlich« wird wörtlich genommen.** Refs umzuschreiben macht die alten Objekte nur unerreichbar — `resolve()` findet sie weiter, der Inhalt bleibt lesbar. Es läuft deshalb `dulwich.gc.garbage_collect(prune=True, grace_period=0)`. Die Schonfrist ist bewusst Null: Die üblichen vierzehn Tage schützen Objekte, die ein anderer Schreiber gerade baut, und der einzige andere Schreiber ist dieselbe Klasse unter derselben Sperre. Ein Test prüft, dass der Text danach in keinem Blob des Objektspeichers mehr steht.

## Fehler- und Randfälle

| Fall | Verhalten |
|---|---|
| Zwei Speichervorgänge kurz hintereinander | Zwei Commits. Kein Entprellen nötig, weil es kein Dateirennen gibt. Der git-Index verträgt aber keine zwei Schreiber gleichzeitig — gemessen kam von acht parallelen Commits genau einer an, die übrigen scheiterten an `FileLocked`. Die Ablage serialisiert deshalb intern |
| Speichern ohne inhaltliche Änderung | Kein Commit |
| Wohin mit einer zurückgeholten Karte? | An ihre alte Position, falls der View noch so viele Karten hat, sonst ans Ende — immer mit Vorschau |
| Änderung an Home Assistant vorbei (Backup eingespielt, `.storage` von Hand bearbeitet) | Beim Start Abgleich gegen den letzten Commit; bei Abweichung ein Commit »außerhalb erfasst«. Eine unsichtbare Lücke wäre schlimmer als keine Historie, weil man ihr vertraut |
| Erststart | Ein Commit mit dem Ist-Zustand aller Dashboards als Nullpunkt |
| Repository fehlt oder ist beschädigt | Neu anlegen, protokollieren, weiterarbeiten |
| Fehler beim Erfassen | Wird protokolliert und darf **niemals** den Start von Home Assistant aufhalten oder ein Speichern verhindern |
| Dashboard gelöscht | Beim nächsten Abgleich als Commit »dashboard deleted« festgehalten. Die Datei verlässt den Baum, wie eine gelöschte Datei es in git tut — jeder frühere Stand bleibt über seine Revision lesbar, und die Löschung erscheint im Verlauf **dieses** Dashboards statt nirgends. Home Assistant meldet eine Dashboard-Löschung mit keinem Ereignis, sie fällt deshalb erst beim Vergleich auf. Ein fehlender *Konfigurationsstand* zählt ausdrücklich **nicht** als Löschung — ein nie gespeichertes Dashboard hat auch keinen. **Das Wiederanlegen gehört zu dieser Fassung** — siehe Entscheidung 8 |
| Ein anderes Dashboard bekommt später denselben `url_path` | Der Löschvermerk zieht die Trennlinie: Da HEAD die Datei nicht mehr führt, beginnt das neue Dashboard ein eigenes Kapitel, statt einen riesigen Diff gegen einen Fremden zu erzeugen |
| Wiederanlegen, wenn HAs Sammlung unerreichbar ist | Wird **abgelehnt** mit einer Meldung, die den Weg von Hand nennt. Nicht halb geschrieben: Auflisten und Ändern lesen in HA zwei verschiedene Quellen, und wer nur die erste füllt, erzeugt ein Dashboard, das gesund aussieht und nicht verwaltbar ist |
| Verlauf, der zwischen zwei Ständen hin und her geht | Mehrere Einträge sind inhaltlich identisch und heißen gleich. Der aktuelle Stand wird markiert (`current state`, nachgerechnet gegen den lebenden Stand), inhaltsgleiche Einträge tragen `same as now`, und der Zurück-Knopf verschwindet dort, wo sein Ziel der aktuelle Stand ist |
| Endgültiges Löschen an einem lebenden Dashboard | Wird abgewiesen. Nur ein Dashboard, das Home Assistant nicht mehr hat, kann vergessen werden — und wenn HA nicht befragbar ist, wird ebenfalls abgewiesen |
| Endgültiges Löschen ohne `confirm` | Antwortet mit der Zahl der Stände, dem Zeitraum und wie viele davon eine eigene Beschreibung tragen. Kein Diff: der einer Löschung wäre die ganze Historie |
| Beschreibungen und Versionen nach einem endgültigen Löschen | Werden auf die neuen Commits übertragen. Was auf einem wegfallenden Commit lag, geht mit ihm (Beschreibung) bzw. wandert auf den nächsten überlebenden Vorfahren (Tag) |
| Beschreibung auf einer unbekannten Revision | Wird abgewiesen mit der Angabe, dass die Revision unbekannt ist — nicht stillschweigend an einem falschen Commit abgelegt. Dieselbe Trennung wie bei `_state_at`: eine Aussage über die Eingabe, keine über das Dashboard |
| Beschreibung auf leeren Text gesetzt | Die Notiz wird entfernt, nicht durch eine leere ersetzt. Sonst hätte eine Zeile eine unsichtbare Überschrift und die automatische Meldung wäre verdeckt |
| Änderung, die sich nicht in Karten ausdrücken lässt (nur Titel, nur Symbol, außerhalb erfasst) | Die Erklärung sagt genau das und verweist auf den Diff. Sie behauptet **nie** »nichts geändert«, solange ein Diff darunter das Gegenteil zeigt |
| Umbenannte **Ansicht** | Wird weiter nicht als solche benannt: `_views_by_key` schlüsselt auf `path`, die Karten stimmen also überein. Bekannte Lücke, durch den Rückfall der Zeile darüber nicht mehr irreführend |
| Sehr große Dashboards | `energie_2` ist 268 KB als YAML. Gemessen: 20 Stände belegen 0,54 MB, also rund 27 KB je Stand — hundert Änderungen wären knapp 3 MB |

## Test-Plan

Herzstück sind die Einordnungs-Tests — von ihnen hängt alles ab.

| Test | Sichert ab |
|---|---|
| Karte gelöscht | wird als Löschung erkannt, mit Position und vollständigem Objekt |
| View gelöscht | ebenso, über den `path` |
| Karte bearbeitet | wird als Bearbeitung erkannt, **nicht** als Löschung plus Hinzufügung |
| Karten umsortiert | wird als Umsortierung erkannt, nicht als mehrfache Löschung |
| Mehrere Änderungen in einem Speichervorgang | alle einzeln erkannt |
| Umkehrung einer Löschung | setzt genau das fehlende Objekt ein, lässt alles andere unberührt |
| Umkehrung bei geschrumpftem View | fügt ans Ende an, statt zu scheitern |
| Round-Trip | Konfiguration → YAML → Konfiguration ist verlustfrei |
| Determinismus | zweimal ablegen ergibt denselben Inhalt, also keinen Commit |
| Realdaten | zehn echte Dashboards durch den Round-Trip |
| Speicheroperationen | Commit, Verlauf, alter Stand, Markierung gegen Wegwerf-Verzeichnisse |
| Beschreibung anlegen, überschreiben, leeren | Notiz erscheint im Verlauf, ersetzt sich, verschwindet restlos — und der Commit bleibt derselbe |
| Beschreibung auf unbekannter Revision | wird abgewiesen, statt irgendwo zu landen |
| Erklärung einer Löschung, Hinzufügung, Bearbeitung, Umsortierung | benennt die Karte und die Ansicht, in beiden Zeitformen |
| Erklärung ohne benennbare Änderung | verweist auf den Diff, behauptet nicht »nichts geändert« |
| Erklärung an Realdaten | die Formulierungen hängen an 1526 echten Karten, nicht an erfundenen |

Die drei Home-Assistant-freien Module laufen in reinem pytest, ohne laufende Installation.

## Reihenfolge der Vorhaben

1. **Diese Fassung — die Integration und das Panel.** Erfassen, Verlauf, Zurückholen, Versionen; bedienbar über Dienste *und* über die Änderungsansicht in der Seitenleiste. Das Panel war ursprünglich Stufe 2 und wurde am 2026-08-30 vorgezogen, nachdem sich die Dienste an der Anlage bewährt hatten. Es nutzt `panel_custom`, den offiziell unterstützten Erweiterungspunkt, und ist immer erreichbar — auch außerhalb des Bearbeitungsmodus.
2. **Der Eintrag im ⋮-Menü.** Eine Abkürzung ohne offiziellen Haken, gebaut wie `kiosk-mode` es tut. Sie **darf still ausfallen**: Findet sie ihren Platz nicht, protokolliert sie das und tut sonst nichts. Sie ist nie der einzige Zugang.

Erst wenn sich Stufe 1 in der eigenen Anlage bewährt hat, wird über die Veröffentlichung entschieden.

## Offene Punkte

- ~~**Zugriff auf das Lovelace-Objekt im Speicher** ist noch nicht praktisch verifiziert.~~ **Erledigt am 2026-08-30.** An der eigenen Anlage bestätigt: `debug_snapshot` meldet alle zehn Dashboards, die Warnung »Lovelace data not available in the expected shape« erscheint **nicht**, der Rückfall bleibt ungenutzt. Ein neu angelegtes Dashboard war sechs Sekunden später als Commit da — ohne jede Wartezeit. **Entscheidung 1 trägt.**
- **Platzbedarf über sehr lange Zeiträume.** Für zwanzig Stände gemessen (27 KB je Stand); ob das über tausend Stände linear bleibt oder git dann besser packt, ist offen. Erst relevant, wenn eine Aufbewahrungsgrenze zur Debatte steht.
- ~~**Einordnung umsortierter Karten**~~ **An echten Daten entschieden am 2026-08-30.** Zwei Befunde:

  1. *Verschiebungen werden relativ gemessen, nicht absolut.* Ein Vergleich roher Positionen erklärte jede Karte hinter einer Löschung zur Verschiebung — auf großen Views zwanzig Meldungen Rauschen um die eine, auf die es ankommt. Gezählt wird jetzt der Rang unter den Überlebenden: Eine Löschung allein erzeugt **keine** Verschiebung, ein Tausch weiterhin zwei.
  2. *Die schwache Zuordnung reichte bei weitem nicht weit genug.* Sie kannte nur `entity`, `title` und `name` — die trägt auf dieser Anlage nur **57 % der 1526 Karten**. Alle übrigen lösten beim Bearbeiten einen Fehlalarm aus: gemeldet als gelöscht **und** neu angelegt, obwohl sie unverändert dastanden. Genau der Fall, den dieses Dokument oben als schlimmer bezeichnet als eine fehlende Funktion. Die Zuordnung greift jetzt zusätzlich auf `heading`, die erste Entität einer Entitätenliste, die erste Textzeile und die benennbare Karte innerhalb eines Containers zu — damit **96 %**. Eine Ähnlichkeitsbewertung braucht es dafür nicht.
