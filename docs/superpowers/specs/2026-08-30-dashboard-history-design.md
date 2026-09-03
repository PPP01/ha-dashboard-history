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
- **Keine Aufbewahrungsgrenzen** in dieser Fassung. Der Grundsatz »erst messen, dann entscheiden« bleibt und ist am 2026-09-02 zur Reihenfolge geworden: Vorhaben B baut die Messung ein, Vorhaben C entscheidet danach über das Aufräumen. Siehe »Reihenfolge der Vorhaben«.
- **Kein Ersatz für Backups.** Die Integration sichert Dashboards, nicht die Installation.

## Architektur

### Bausteine

| Datei | Aufgabe | Home-Assistant-frei |
|---|---|---|
| `keys.py` | Welches Dashboard welches ist, und welches fehlt | **ja** |
| `analyze.py` | Zwei Stände vergleichen und die Änderungen einordnen: Karte gelöscht, View gelöscht, bearbeitet, verschoben | **ja** |
| `restore.py` | Die Umkehrung anwenden: gelöschtes Objekt wieder einsetzen, oder einen ganzen Stand herstellen | **ja** |
| `versions.py` | Versionsnummern: einlesen, ordnen, hochzählen, Namen bilden — siehe Entscheidung 13 | **ja** |
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

Die vier oberen sind reine Logik und ohne laufendes Home Assistant prüfbar. Diese Trennung ist keine Stilfrage: Sie erlaubt, die Einordnungs-Regeln — das Herz des Projekts — in Sekunden gegen Dutzende Fälle zu testen, statt sie an einer Live-Anlage zu erproben.

### Datenmodell

- **Ein Änderungssatz ist ein Commit.** Jedes Speichern erzeugt genau einen, der die betroffene Dashboard-Datei berührt. Zeitpunkt und Dashboard stehen maschinenlesbar in der Commit-Botschaft.
- **Eine Version ist eine Markierung** (annotierte git-Markierung) mit Titel und Beschreibung. Sie **fasst nichts zusammen und löscht nichts** — sie markiert einen Punkt im Verlauf. Genau deshalb bleiben die Einzeländerungen darunter erhalten und einzeln rücknehmbar; in der Ansicht werden sie lediglich eingeklappt. **Sie gehört einem Dashboard** und heißt `<schlüssel>/v<major>.<minor>.<patch>` — siehe Entscheidung 13.
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

   **Am 2026-09-03 eingegrenzt, nicht aufgehoben (Entscheidung 15).** Der Satz oben bleibt für den allgemeinen Fall wahr. Was hinzukommt: Wo sich die Eindeutigkeit *nachweisen* lässt — der Inhalt, den eine Änderung erzeugt hat, steht heute genau einmal im Dashboard —, ist eine ersetzende Rücknahme keine Zusammenführung ohne Identitäten mehr, sondern ein bestimmter Austausch. Angeboten wird sie nur dort. Überall sonst gilt Entscheidung 4 unverändert.

5. **Die Einzelrücknahme wird später *bedingt* angeboten, nicht mit Warnhinweis.** **Eingelöst am 2026-09-03 durch Entscheidung 15.** Ob eine ersetzende Rücknahme eindeutig ist, lässt sich feststellen: Man prüft, ob eine spätere Änderung denselben Bereich angefasst hat. Das Werkzeug entscheidet also selbst und sagt entweder »zurücknehmen« oder »geht nicht, weil …, hier sind die Alternativen«. Ein Warnhinweis wäre schlechter, weil er die Entscheidung an jemanden weiterreicht, der die Verschränkung nicht sehen kann.

6. **Vollständige Stände speichern, keine reinen Deltas.** Damit ist die Einzelrücknahme später eine reine Rechenfunktion über vorhandene Daten — nachrüstbar ohne Datenmigration. git dedupliziert die Stände ohnehin.

7. **Nichts wird ohne Vorschau geschrieben.** Jede Wiederherstellung zeigt zuerst den Diff. Derselbe Grundsatz wie beim bestehenden Restore-Werkzeug.

   **Die Regel gilt für Dashboards, nicht für Beschriftungen.** *(Grenze nachgetragen am 2026-08-31.)* Ihr Zweck ist, dass niemand sein Dashboard unversehens verändert findet. Eine Beschreibung nach Entscheidung 10 verändert kein Dashboard, ist sofort und vollständig zurücknehmbar und wird von der Person geschrieben, die sie gleich danach liest. Ein Bestätigungsdialog davor wäre Zeremonie ohne Schutzwirkung — und das Gegenteil dessen, wofür die Funktion gebaut wird. Sie verlangt deshalb **kein** `confirm`. Jeder Vorgang, der einen Dashboard-Stand schreibt, verlangt es weiterhin ohne Ausnahme.

9. **Das Panel fragt nach einer Änderung — und beim Ganz-Zurück nach beiden Zuständen.** *(Der zweite Halbsatz am 2026-09-01 nachgetragen; vorher stand hier »nie nach einem Zustand«.)* *(Nachgetragen am 2026-08-30, aus der Beobachtung echter Bedienung.)*

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

   **Am 2026-09-01 zurückgenommen: das Ganz-Zurück bietet beide Stände an.** Zwei Tage vorher war ein Vorschlag des Nutzers abgelehnt worden, das Ziel auf »diesen Stand« zu *verschieben* — mit dem Argument, das hole die Falle zurück. Der Vorschlag kam wieder, diesmal als **zweiter Knopf daneben** statt als Ersatz, und damit fällt das Argument:

   - Die Falle bestand darin, *stillschweigend* das falsche Ziel zu bekommen. Bei zwei benannten Knöpfen wählt man. Das ist keine Stolperstelle mehr, sondern eine Frage.
   - Eine Zeile ist eine Änderung und liegt damit **zwischen zwei Ständen**. Wer einen Verlust sucht, will den Stand *davor*; wer einen Stand wiedererkennt, den er mochte, will den *danach*. Beide Absichten sind echt, und welche vorliegt, kann die Oberfläche nicht wissen.
   - Die scheinbare Redundanz ist der Gewinn: Zeile i »davor« und Zeile i+1 »danach« führen zum **selben** Ziel. Wer in Änderungen denkt und wer in Zuständen denkt, landen beide richtig.
   - Und das Netz ist heute ein anderes als bei Entscheidung 9: Der Dialog nennt Folgen im Klartext und in Rot, nicht mehr nur als YAML-Diff.

   Die Aufschriften heißen **»Back to the state before this change«** und **»Back to the state after this change«** — beide benennen den Gegenstand (*state*), und das Paar ist ein Gegensatz statt einer Auslassung. »before this change« gegen »this change« unterschied sich um ein Wort, und Auslassungen liest man weg. Jeder der beiden verschwindet, wenn sein Ziel der aktuelle Stand ist.

   **Was bleibt:** Die *Einzelrücknahme* (»Put back: X«) rechnet weiter mit dem Stand vor der Änderung und fragt nie nach einem Zustand. Dort ist die Absicht eindeutig — man sucht, was fehlt.

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

    **Am 2026-09-02 zurückgenommen — und die Begründung dieses Absatzes war zur Hälfte falsch.** Versionen kehren in die Oberfläche zurück, siehe Entscheidung 13. Der Satz »`resolve()` nimmt seinen Namen als Revision an« stimmte nie: Nachgemessen wirft `repo[b"v1.0.0"]` einen `KeyError`, und kein Test hat es bemerkt. Der Rest des Absatzes gilt weiter — ein Tag *kann* etwas, was eine Notiz nicht kann; es war nur nicht wahr, dass er es hier schon tat. Und das Argument »zwei Wege für dieselbe Sache« fällt, weil eine Version ab Entscheidung 13 nicht mehr einen Punkt benennt, sondern einen Stand herstellt. Das ist eine andere Sache.

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

      **Am 2026-09-02 berichtigt, und die Begründung fällt weg.** Seit Entscheidung 13 gehört eine Version einem Dashboard und heißt `<schlüssel>/vX.Y.Z`. Ein Tag im Namensraum des vergessenen Dashboards wird deshalb **gelöscht** statt verschoben. Gemessen, was das Verschieben anrichtete: Nach `forget("gone")` überlebte `gone/v1.0.0` und zeigte auf den Commit eines *fremden* Dashboards; `read_at` fand dort nichts, und ein später unter demselben `url_path` neu angelegtes Dashboard startete mit einem Phantom als »aktueller Version«. Tags außerhalb des Namensraums — auch die eines anderen, überlebenden Dashboards — wandern unverändert wie bisher.

      **Und leichtgewichtige Tags zählen mit.** Sie wurden übergangen, weil sie kein Tag-Objekt sind. Gemessen: Ein von Hand gesetzter leichtgewichtiger Tag hielt die gesamte Historie vor der Umschreibung erreichbar, `garbage_collect` kam nicht heran, und `forget` meldete dabei Erfolg — der vergessene Text stand danach weiter im Objektspeicher. Das machte die einzige unwiderrufliche Operation dieses Werkzeugs still wirkungslos. Ab hier wird **jede** Ref unter `refs/tags` behandelt, in beiden Formen.

    Ein Commit, der nichts außer diesem Dashboard berührte, verschwindet ganz statt zu einem leeren Commit zu werden; seine Kinder werden umgehängt. Ein leerer Commit wäre ein anklickbarer Stand, der nichts sagt.

    **Und »unwiederbringlich« wird wörtlich genommen.** Refs umzuschreiben macht die alten Objekte nur unerreichbar — `resolve()` findet sie weiter, der Inhalt bleibt lesbar. Es läuft deshalb `dulwich.gc.garbage_collect(prune=True, grace_period=0)`. Die Schonfrist ist bewusst Null: Die üblichen vierzehn Tage schützen Objekte, die ein anderer Schreiber gerade baut, und der einzige andere Schreiber ist dieselbe Klasse unter derselben Sperre. Ein Test prüft, dass der Text danach in keinem Blob des Objektspeichers mehr steht.

13. **Versionen kehren in die Oberfläche zurück — je Dashboard, mit Versionsnummern.** *(Nachgetragen am 2026-09-02, auf Wunsch des Nutzers.)*

    Entscheidung 10 hatte sie aus der Oberfläche genommen, weil sie damals dasselbe konnten wie eine Beschreibung: einen Punkt benennen. Zwei Wege für dieselbe Sache waren ein Konzept zu viel, und das Argument war richtig. Es trägt hier nicht mehr, weil eine Version ab dieser Entscheidung etwas kann, was eine Notiz nie konnte: **einen Stand herstellen.** Nicht »dieser Punkt hieß so«, sondern »bring mich dorthin zurück, und dann wieder her«. Das ist eine andere Sache, kein zweiter Weg zur selben.

    **Zuerst eine Berichtigung, denn Entscheidung 10 stützte sich auf eine Behauptung über den Code, die nicht stimmt.** Dort steht, Tags blieben als Dienste erhalten, weil `resolve()` ihren Namen als Revision annehme. Am 2026-09-02 nachgemessen an dulwich 1.2.14: **das tut es nicht, und nie getan.** `repo[b"v1.0.0"]` wirft `KeyError`; nur der volle Pfad `refs/tags/v1.0.0` trägt, weil dulwich die Kurzform-Auflösung, die `git` gewohnheitsmäßig leistet, in `Repo.__getitem__` nicht nachbildet. Kein Test hat es bemerkt, weil der vorhandene die *Objekt-ID* des Tags auflöst und nie seinen Namen. Die README behauptete dasselbe. `_resolve` probiert deshalb ab hier die übliche Suchreihenfolge `name`, `refs/tags/name`, `refs/heads/name`. Damit ist die Adressierbarkeit erstmals wahr — und sie ist die Grundlage von allem Weiteren, denn sie macht das Zurückwechseln zu vorhandenem Code.

    **Der Namensraum ist der Dashboard-Schlüssel:** `<schlüssel>/v<major>.<minor>.<patch>`. Damit darf jedes Dashboard sein eigenes `v1.0.0` haben. Gemessen am selben Tag: Schrägstriche in Tag-Namen tragen, ebenso der Unterstrich in `_default/v1.0.0` und sogar Umlaute; Leerzeichen weist dulwich mit `RefFormatError` ab. Eine Falle wurde dabei gefunden und wird abgefangen: Ein **flacher** Tag `heizung` neben `heizung/v1.0.0` ist in git unmöglich — Ref-Datei und Ref-Verzeichnis sind derselbe Pfad. Das Anlegen prüft das vorher und lehnt ab, statt es zu erleiden. *(Am 2026-09-02 im Detail berichtigt: Die beiden Richtungen scheitern unterschiedlich. Ein flacher Tag **über** einem Namensraum wirft `IsADirectoryError` und lässt eine `.lock`-Datei zurück; ein Namensraum **unter** einem flachen Tag wirft `NotADirectoryError` und lässt keine zurück, weil schon das Anlegen der Sperrdatei scheitert. Die Prüfung deckt beide Richtungen ab, und seit demselben Tag auch Schlüssel mit mehr als einem Schrägstrich: **jeder** Präfix bis zu einem `/` ist ein möglicher Blockierer, nicht nur der erste.)*

    **Die Nummer wird gewählt, nicht getippt.** Drei Knöpfe, jeder mit der fertigen Nummer darauf — Patch, Minor, Major —, **Patch vorausgewählt**. Ohne bestehende Version stehen dort `0.0.1`, `0.1.0` und `1.0.0`. Gezählt wird immer von der **höchsten vorhandenen** Version dieses Dashboards, auch nach einem Rücksprung: So bleiben die Nummern monoton und können nie kollidieren. Der Mensch tippt nur Titel und Beschreibung. Der Grund für die Knöpfe statt eines Namensfeldes: Ein Tag-Name ist ein technisches Artefakt mit Ref-Regeln, und diese Regeln in einen Dialog durchzureichen hieße, die Ablage in die Oberfläche zu tragen. Die Wahl zwischen Patch, Minor und Major trägt dagegen eine Aussage — war das eine Korrektur oder ein Umbau?

    **Es gibt keine Ankreuzfelder, sondern einen Schnittpunkt.** Der Wunsch war, Änderungen seit der letzten Version auszuwählen und zu bündeln. Das geht nicht, und zwar nicht aus Aufwandsgründen: Jeder Commit hält den **vollständigen** Stand, der Stand nach Änderung 3 enthält die Wirkung von Änderung 2 also zwangsläufig. »3 ja, 2 nein« hieße, eine einzelne Änderung aus einem fertigen Stand herauszurechnen — eine ersetzende Rücknahme, die Entscheidung 4 mit nachgezählter Begründung ausschließt (661 Karten, 0 mit `id`). Der Stand einer Version ist deshalb immer der nach der neuesten einbezogenen Änderung. Statt Kreuzchen, die etwas versprechen, was die Ablage nicht einlösen kann, trägt jede Zeile den Knopf **»Version bis hierher«**. Der an der obersten Zeile ist das gewünschte »alles seit der letzten Version zusammenfassen« — ein Klick, an der Stelle, an der das Auge ohnehin landet.

    **Dargestellt wird im Verlauf, nicht daneben.** Oben die Änderungen seit der letzten Version, darunter jede Version als zuklappbarer Abschnitt mit ihren Änderungen darin und einem Knopf »Zurück zu v1.2.0«. Damit wird eingelöst, was das Datenmodell seit dem ersten Tag verspricht — »in der Ansicht werden sie lediglich eingeklappt« —, und es bleibt bei einem Ort. Eine zweite Ansicht wäre der Rückfall in genau das, wovor Entscheidung 10 warnt.

    **Das Zurückwechseln ist kein neuer Vorgang.** Es ist `restore_state` mit dem Versionsnamen als Revision, samt Vorschau, Klartext-Erklärung und `confirm` — die harte Regel gilt unverändert. Und es ist beliebig oft in beide Richtungen möglich: Ein Tag zeigt auf einen Commit, und dieser Commit verschwindet nicht, nur weil der Verlauf woanders weitergeht. Ein Rücksprung löscht keine Version und macht keine unerreichbar.

    **Die Rechnerei liegt in `versions.py`, Home-Assistant-frei.** Einlesen, ordnen, hochzählen, Namen bilden. Sortiert wird numerisch, nicht lexikografisch — `v1.10.0` steht über `v1.9.0`. Ein Tag, der dem Muster nicht folgt, wird beim Zählen übergangen, aber weiterhin angezeigt. Damit wächst die Riege der prüfbaren Module von drei auf vier, und zwar nach derselben Regel wie bei Entscheidung 11: Was schiefgehen kann und einen Wortlaut oder eine Zahl erzeugt, gehört dorthin, wo `pytest` hinkommt — nicht ins Panel.

    **Der Dienst `create_version` ändert seine Signatur** — `dashboard` und `level` (`patch`/`minor`/`major`, Vorgabe `patch`) statt eines freien `name`. Dazu kommt ein lesender `next_versions`, der die drei Kandidaten liefert, `versions` bekommt einen Dashboard-Filter, und `history` nennt je Änderung die Version, die auf ihr sitzt. Das ist ein Bruch an einer in der README dokumentierten Schnittstelle; er wird bewusst genommen, weil das Projekt noch nie veröffentlicht wurde und ein zweiter, gleichbedeutender Weg genau das wäre, wovor Entscheidung 10 warnt. Die Nummernbildung darf dabei **nicht** im Panel liegen — sonst stünde die eine Rechnung, die falsch sein kann, ausgerechnet dort, wo `pytest` nicht hinkommt.

    **`panel.js` wird dabei geteilt.** Sie steht bei 939 Zeilen, und Abschnitte plus Anlege-Dialog tragen sie über 1200. Die Spec verlangt vom Panel Logik-Freiheit, nicht Kürze; aber eine Datei, die niemand mehr überblickt, ist der Ort, an dem Logik unbemerkt einzieht.

    **Ergänzt am 2026-09-02, nach zwei Fragen des Nutzers.** Er hatte `v1.0.0` auf einer Revision vor dem damaligen Stand angelegt und war dann dorthin zurückgewechselt. Auf dem Schirm stand eine gekrönte Zeile ohne Versionsangabe, darunter der eingeklappte Abschnitt `v1.0.0`. Seine Fragen: *Welche Version ist das, was hier oben steht?* Und: *Lohnt an einem Stand, der 1:1 `v1.0.0` ist, eine neue Version?*

    Beide Antworten lagen im Panel bereit und wurden nicht ausgesprochen. `history` liefert je Eintrag `same_as_now` und `versions` als zwei **getrennte** Felder; die oberste Zeile sagte »current state«, der Kopf des Versions-Abschnitts sagte ebenfalls »current state« — und nichts verband die beiden. Wer wissen wollte, welche Version sein Stand hält, musste den Quelltext lesen. Genau das ist geschehen. Daraus drei Sätze, alle reine Oberfläche, keiner ändert die Ablage:

    1. **Der aktuelle Stand nennt die Version, mit der er inhaltsgleich ist** — »identical in content to v1.0.0«, nie »ist v1.0.0«. Der Unterschied ist tragend: Ein Rücksprung schreibt einen **neuen** Eintrag, der Stand ist also ein späterer, der dasselbe hält. Wer daraus »ich bin auf v1.0.0« liest, verwechselt Zustand und Eintrag — dieselbe Verwechslung, gegen die Entscheidung 9 den gekrönten Abschnitt eingeführt hat. Im selben Zug berichtigt: Der Kopf eines Versions-Abschnitts sagte flach »current state«, auch wenn die Version weiter unten saß. Er sagt jetzt »same content as now« und behält »current state« dem Fall vor, in dem die Version tatsächlich auf dem neuesten Eintrag sitzt.

    2. **Der Anlege-Dialog sagt es vor der Wahl**, wenn der gewählte Stand schon eine Version trägt oder inhaltsgleich zu einer ist. **Verweigert wird nichts:** Zwei Versionen auf einem Stand sind erlaubt, und nach einem Rücksprung kann ein zweiter Name genau das Gewollte sein. Der Punkt ist, dass es eine Entscheidung wird statt einer Überraschung. Die Grenze davon ist benannt: Die Inhaltsgleichheit wird nur für den *aktuellen* Stand angeboten, weil `same_as_now` jeden Eintrag gegen die lebende Konfiguration vergleicht und die Frage »hält dieser Eintrag, was eine Version hält« deshalb nur dort beantworten kann. Anderswo bräuchte es einen Vergleich, den das Panel nicht hat — und den es nach Entscheidung 13 auch nicht selbst anstellen dürfte.

    3. **Der Bestätigen-Dialog sagt, wohin der jetzige Stand geht.** Die zweite Frage war, ob beim Zurückwechseln nicht zwischen »exakt auschecken und alles Jüngere verlieren« und »`v1.0.0` als neuen Stand anlegen« zu wählen sei. **Die erste Möglichkeit gibt es nicht** — und das ist eine Entscheidung, keine Selbstverständlichkeit: `restore_state` schreibt das lebende Dashboard, der Stand, der dort stand, wird vorher aufgezeichnet, und außer `forget` schreibt nichts einen bestehenden Zustands-Commit um und verschiebt nichts eine bestehende Versionsmarke. (`describe` bewegt `refs/notes/commits` — das ist eine Notiz, kein Stand; die ursprüngliche Fassung dieses Satzes sagte »Refs verschiebt außer `forget` nichts« und war damit zu weit gefasst.) Die Historie wächst, sie schrumpft nie.

    **Nachtrag vom 2026-09-03: aus einer Annahme wurde eine Zusage.** »Der Rekorder hängt einen Eintrag für das an, was dort stand« war beim Schreiben dieses Absatzes keine Zusage, sondern eine Beobachtung — sie stimmte, weil der Rekorder jedes Speichern hört, und sie stimmte nicht für einen Stand, der nie gehört wurde: ein Speichern während des HA-Starts, eine von außen geschriebene Ablagedatei, ein einmal gescheiterter Rekorder. Am Prüfstand gemessen ist die Lücke selten — drei Stunden gewöhnlicher Nutzung erzeugten keine —, aber genau in ihr fällt der Stand weg, auf den man zurückwollte, und damit der ganze Zweck des Werkzeugs. Jede Operation, die einen Dashboard-Stand schreibt, zeichnet den lebenden Stand deshalb **vorher** auf und **prüft nach**, dass er der neueste Eintrag ist. Zwei Festlegungen dazu, beide begründet:

    - **Misslingt es, wird trotzdem geschrieben** und der Fehlbetrag als Hinweis mitgeteilt. Der Fall, an dem sich das entscheidet, ist der volle Datenträger: Dort liest sich alles und schreibt sich nichts, und eine verweigerte Wiederherstellung nützt in dem Moment niemandem, in dem sie am dringendsten gebraucht wird — die Momentaufnahme wäre ja ohnehin nicht zustande gekommen.
    - **Angekündigt wird sie nicht.** Das Panel liest `history_updated` als »Deine Seite ist veraltet, lies neu«. Mitten in der Operation gefeuert, baut es die Seite aus einem Verlauf, dessen neuester Eintrag der gleich überschriebene Stand ist. Diese Seite sieht **richtig** aus, und das ist schlimmer, als falsch auszusehen. In git *ist* der Unterschied echt — `checkout` gegen `revert` —, wer git kennt, muss die Frage also stellen. Dass sie hier keine zwei Antworten hat, gehört deshalb ausgesprochen statt vorausgesetzt. Weggelassen wird der Satz beim Wiederanlegen eines gelöschten Dashboards: Dort gibt es keinen jetzigen Stand zu behalten, und der Hinweis daneben sagt bereits, was stattdessen geschieht.

    Der gemeinsame Nenner, und der Grund, warum das hier steht und nicht nur im Code: **Eine Eigenschaft schützt besser als eine Warnung.** Weil die einzige zerstörende Operation `forget` heißt und auch so heißt, lässt sich über jede andere sagen: umkehrbar. Das ist mehr wert als jeder Bestätigungsdialog — aber nur, solange es jemand ausspricht. Ein zerstörendes Zurückwechseln nachzurüsten, wäre entsprechend kein neuer Knopf, sondern die Aufgabe dieser Eigenschaft.

14. **Karten werden über das ganze Dashboard zugeordnet, nicht innerhalb einer Kartenliste.** *(Nachgetragen am 2026-09-03, nach zwei Befunden eines unabhängigen Reviews.)*

    Die Zuordnung lief bisher **pro Container** — eine Kartenliste einer über `path` bestimmten View. Wer eine Karte über diese Grenze zog, hatte sie auf der alten Seite unzugeordnet und auf der neuen ebenso: Der Verlauf meldete »1 removed, 1 added« und bot die Karte zum Zurückholen an. Wer annahm, hatte sie **zweimal**. Das ist genau der Fehlalarm, den Entscheidung 4 schwerer wiegt als eine fehlende Funktion — mit einer Verdopplung obendrauf.

    Der zweite Befund saß im schwachen Schlüssel: Zwei Karten gleichen Typs auf derselben Entität, die erste gelöscht, die zweite bearbeitet. Der Durchgang nahm den **erstbesten** Treffer, verheiratete also die gelöschte Karte mit der Überlebenden und erklärte danach die Überlebende für gelöscht. Angeboten wurde die alte Fassung einer Karte, die noch da war; die wirklich gelöschte wurde nie angeboten.

    **Vier Durchgänge, und ihre Reihenfolge ist die ganze Korrektheit.**

    1. Identisch, **am selben Ort**.
    2. Identisch, **irgendwo auf dem Dashboard**. Was sich dort findet, wurde verschoben — und Verschobenes fehlt nicht.
    3. Gleicher schwacher Schlüssel, am selben Ort, **bester Treffer zuerst**.
    4. Der Rest: alt gelöscht, neu hinzugekommen.

    **Warum 1 vor 2 steht, ist kein Detail.** Wird eine Karte aus einer View gelöscht, während eine identische unberührt in einer anderen liegt, würde ein zuerst laufender globaler Durchgang die gelöschte mit der unberührten verheiraten und die Löschung spurlos verschlucken. Weil jede Karte zuerst ihren eigenen Ort beansprucht, bleibt die Löschung übrig, wo sie hingehört. Als Test festgehalten.

    **Warum »bester Treffer« und nicht »erster«:** am Beispiel gemessen. Die überlebende Karte stimmt mit ihrer eigenen alten Fassung in drei von vier Feldern überein (0,75), mit der gelöschten in zwei von fünf (0,40). Nach Ähnlichkeit absteigend gepaart, kippt die Zuordnung auf die richtige Seite. Die Ähnlichkeit zählt nur Felder oberster Ebene — ein Mensch kann die Zahl nachrechnen, und das zählt bei einem Wert, der entscheidet, welche Karte zum Zurückholen angeboten wird.

    **Die Erklärung nennt das Ziel.** Statt »tile: Temperatur wurde gelöscht« steht dort »tile: Temperatur was moved to "Küche"«. Ein Abschnitt wird über seine `heading`-Karte benannt, nicht über ein `title`-Feld: gemessen an der Anlage tragen **0 von 80** Abschnitten einen Titel, **51 von 80** eine Überschriftskarte. Wo es keinen Namen gibt, steht »another section« — erfunden wird keiner.

    **Zwei Grenzen bleiben, beide als Test festgeschrieben statt als Prosa.** Eine Karte, an der nichts zu erkennen ist — kein Entity, kein Titel, kein Text, kein benennbarer Inhalt — liest sich bei jeder Bearbeitung weiter als Löschung plus Zutat; an der Anlage sind das **27 von 484** Karten (5,6 %), vor allem `apexcharts`, `vertical-stack`, `conditional` und `bubble-card`. Und eine Karte, die im selben Speichervorgang verschoben **und** bearbeitet wird, fällt durch beide Netze: Durchgang 2 greift nicht mehr (nicht identisch), Durchgang 3 nicht (anderer Ort). Ein fünfter Durchgang mit schwacher Zuordnung über Ortsgrenzen würde das schließen und ein schlimmeres Loch öffnen — dieselbe Entität in zwei Views ist alltäglich, und die umgekehrte Verwechslung ließe eine echte Löschung verschwinden. Bewusst nicht gebaut.

    **Die exakten Durchgänge laufen über einen Fingerabdruck**, nicht über den Vergleich jedes Paares. Gemessen: bei zwölfhundert Karten 78 ms vorher, 20 ms nachher; bei hundert Karten kostet es 0,7 ms mehr, der Umschlagpunkt liegt bei etwa vierhundert. Der Weg läuft bei **jedem** Speichervorgang und bei jedem Aufklappen einer Zeile, deshalb zählt hier der schlechteste Fall und nicht der häufigste.

    **Entscheidung 4 bleibt unberührt.** Zurückgeholt wird weiterhin nur additiv und nur Verschwundenes. Geändert hat sich nicht, *was* getan wird, sondern was als verschwunden **gilt** — und das war schlicht falsch berechnet.

15. **Die gezielte Rücknahme — eine Weiche, kein zusätzlicher Knopf.** *(Nachgetragen am 2026-09-03, auf Wunsch des Nutzers. Sie löst die Zusage aus Entscheidung 5 ein.)*

    Für eine **bearbeitete** Karte gab es bis hierher keinen Weg zurück. »Put back« kann nur hinzufügen und erscheint nur, wenn `find_removed` etwas meldet — bei einer Bearbeitung meldet es nichts. Bleibt der ganze Vorzustand, der alles Spätere mitnimmt. An einer echten Zeile nachgesehen: `1 edited`, darunter »Nothing from before this change is missing today«, und der einzige angebotene Knopf wirft zwei Tage Arbeit weg. Das ist keine Lücke in der Bedienung, sondern eine im Zweck.

    **Der Byte-Inhalt ist die Kennung.** Entscheidung 4 hat die ersetzende Rücknahme mit dem Argument ausgeschlossen, sie sei »in verschränkten Fällen nicht eindeutig«. Das bleibt wahr. Neu ist nur, dass die Eindeutigkeit **geprüft** wird, statt sie anzunehmen: Was die Änderung erzeugt hat, wird im heutigen Dashboard gesucht, und der Undo wird genau dann angeboten, wenn es dort **genau einmal** steht. Eine Karte, deren exakter Inhalt im ganzen Dashboard einmal vorkommt, ist eindeutig adressierbar — ganz ohne `id`-Feld, dessen Fehlen (661 Karten, 0 mit `id`) der Grund für Entscheidung 4 war.

    Einmal über den aktuellen Stand laufen und jeden Kartenrumpf über denselben Fingerabdruck verdichten, den Entscheidung 14 schon benutzt. Danach ist jede Frage eine Nachschlagung in einem Zähler:

    | Was die Änderung tat | Prüfung am heutigen Stand | Rücknahme |
    |---|---|---|
    | Karte **bearbeitet** (alt→neu) | `zähler[neu] == 1` | die eine Fundstelle durch *alt* ersetzen |
    | Karte **verschoben** | `zähler[karte] == 1` | dort entfernen, am alten Platz einsetzen |
    | Karte **hinzugefügt** | `zähler[neu] == 1` | die eine Fundstelle entfernen |
    | Karte **gelöscht** | `zähler[alt] == 0` | am alten Platz einsetzen |
    | Karte gelöscht, ist aber wieder da | `zähler[alt] > 0` | nichts tun — dieser Teil ist bereits zurück |

    **Alles oder nichts.** Trifft eine dieser Bedingungen nicht zu, ist die *ganze* Rücknahme verweigert, nicht nur der eine Punkt. Ein halb zurückgenommener Stand ist einer, den niemand gewollt hat und den die Zeile daneben nicht mehr beschreibt. Die Verweigerung nennt Grund und Karte, wie Entscheidung 5 es verlangt — »geht nicht, weil …« statt eines Warnhinweises, der die Entscheidung an jemanden weiterreicht, der die Verschränkung nicht sehen kann.

    **Die Reihenfolge beim Anwenden ist Teil der Korrektheit:** erst alle Ersetzungen (positionsneutral), dann alle Entfernungen, dann alle Einsetzungen. Andersherum verschöben die Entfernungen genau die Indizes, an denen eingesetzt werden soll.

    **Beim Bestätigen wird neu gerechnet, nicht das Vorschauergebnis geschrieben.** Ändert jemand das Dashboard zwischen Vorschau und `confirm`, ist der Undo womöglich nicht mehr exakt; dann kommt die Verweigerung zurück statt eines Schreibvorgangs. Ohne das wäre die Beweisführung an der einen Stelle wertlos, an der sie zählt.

    **Der Undo entfernt auch.** Hat die Änderung eine Karte hinzugefügt, nimmt er sie weg — das erste Mal, dass dieses Werkzeug eine Karte löscht. Vertretbar, weil die Karte byteweise nachweislich die ist, die diese Änderung erzeugt hat, weil sie genau einmal vorkommt, und weil Entscheidung 7 unverändert gilt: Vorschau, dann `confirm: true`.

    **In der Oberfläche ist es eine Weiche, kein dritter Knopf.** Eine Zeile bietet einen Weg zurück: den Undo, wenn er exakt ist, sonst die »Put back«-Liste. Die beiden Ganz-Stand-Knöpfe wandern hinter eine zugeklappte Zeile; »Back to the state before this change« entfällt ganz, wenn er dasselbe schriebe wie der Undo — der Server sagt das mit einem eigenen Feld, damit das Panel es nicht erraten muss. Der Anlass war eine Rückmeldung des ersten Menschen, der die beiden Knöpfe nebeneinander sah: An der obersten Zeile mit genau einer gelöschten Karte tun sie buchstäblich dasselbe, und nichts auf dem Schirm sagte, dass sie es drei Wochen später nicht mehr tun.

    **Ein Put-back-Knopf verschwindet aus genau zwei Gründen.**

    1. **Deckungsgleichheit** — der Undo holt genau dessen eine Karte und sonst nichts. Das trifft auf eine einzige Konstellation zu: eine Änderung, die genau ein Stück gelöscht hat.
    2. **Die Falle** — hat die Änderung außer dem Entfernen auch etwas **hinzugefügt**, verschwinden die Knöpfe für die Stücke, die *diese* Änderung entfernt hat. Der Grund ist gemessen: Eine Bearbeitung, die das identifizierende Feld trifft, liest sich als `1 removed, 1 added` (`markdown`, erste Textzeile geändert: `put-back-Einträge = 1`). »Put back« kann nur hinzufügen und stellt die alte Fassung **neben** die neue — ein Duplikat. Der Undo nimmt die Änderung als Einheit zurück und trifft in beiden Lesarten das Richtige.

    Was aus **späteren** Änderungen fehlt, behält seinen Knopf immer, unter einer Zeile, die das sagt. Und was Regel 2 kostet, ist begrenzt und benannt: Wer nur A zurückwill und das Hinzugefügte behalten, verliert den Knopf *an dieser Zeile* — an jeder älteren steht er weiter, weil A dort ebenfalls als fehlend geführt wird. Global geht nichts verloren.

    **Vier Grenzen, ausdrücklich nicht geschlossen.** Beschriftungen (Titel, Symbol eines Dashboards) bleiben außen vor, weil `restore_state` sie ohnehin nicht schreibt. Die 27 merkmalslosen Karten aus Entscheidung 14 bleiben merkmalslos: Sind zwei gleich, ist der Zähler ≥ 2 und der Undo verweigert — richtig, aber dort hilft die Weiche nie. Die Duplikat-Falle bleibt bestehen, wo der Undo verweigert; dieses Vorhaben entschärft nur die Fälle, in denen es einen gibt. Und die Auswahl einzelner Stücke bleibt eine additive Sache: Wer aus einer Änderung nur eines zurückholen will, nimmt den Weg über »Put back«, nicht über den Undo.


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
| Beschreibungen und Versionen nach einem endgültigen Löschen | Werden auf die neuen Commits übertragen. Was auf einem wegfallenden Commit lag, geht mit ihm (Beschreibung) bzw. wandert auf den nächsten überlebenden Vorfahren (Tag). **Ausgenommen seit dem 2026-09-02: Versionen im Namensraum des vergessenen Dashboards werden gelöscht**, sonst überlebte der Name des Vergessenen an einem fremden Commit |
| Leichtgewichtiger Tag beim endgültigen Löschen | Wird wie ein annotierter behandelt. Bis zum 2026-09-02 wurde er übergangen — und hielt damit die ganze Historie vor der Umschreibung erreichbar, während `forget` Erfolg meldete. Die einzige unwiderrufliche Operation dieses Werkzeugs war still wirkungslos |
| Beschreibung auf einer unbekannten Revision | Wird abgewiesen mit der Angabe, dass die Revision unbekannt ist — nicht stillschweigend an einem falschen Commit abgelegt. Dieselbe Trennung wie bei `_state_at`: eine Aussage über die Eingabe, keine über das Dashboard |
| Beschreibung auf leeren Text gesetzt | Die Notiz wird entfernt, nicht durch eine leere ersetzt. Sonst hätte eine Zeile eine unsichtbare Überschrift und die automatische Meldung wäre verdeckt |
| Änderung, die sich nicht in Karten ausdrücken lässt (nur Titel, nur Symbol, außerhalb erfasst) | Die Erklärung sagt genau das und verweist auf den Diff. Sie behauptet **nie** »nichts geändert«, solange ein Diff darunter das Gegenteil zeigt |
| Umbenannte **Ansicht** | Wird weiter nicht als solche benannt: `_views_by_key` schlüsselt auf `path`, die Karten stimmen also überein. Bekannte Lücke, durch den Rückfall der Zeile darüber nicht mehr irreführend |
| Sehr große Dashboards | `energie_2` ist 268 KB als YAML. Gemessen: 20 Stände belegen 0,54 MB, also rund 27 KB je Stand — hundert Änderungen wären knapp 3 MB. **Am 2026-09-02 an 100 Ständen desselben Dashboards bestätigt: 2833 KiB, also 28 KiB je Stand. Das Wachstum ist linear** |
| Versionsname trifft auf einen flachen Tag gleichen Namens | Wird abgelehnt. git kann `heizung` und `heizung/v1.0.0` nicht nebeneinander führen; je nach Richtung scheitert der Versuch mit `IsADirectoryError` (samt zurückbleibender `.lock`) oder `NotADirectoryError`. Geprüft werden **alle** Präfixe des Namens, nicht nur der erste — sonst greift die Prüfung bei einem Schlüssel mit mehr als einem Schrägstrich am falschen Namensraum vorbei |
| Revision, die auf keinen Commit zeigt | Wird abgelehnt. `resolve()` prüft seit dem 2026-09-02, dass am Ende ein Commit steht. Gemessen, was vorher geschah: Die SHA eines YAML-**Blobs** löste sich auf sich selbst auf, eine Version darauf wurde **angenommen** — und war für immer unbrauchbar, weil `read_at` daran mit `AttributeError: 'Blob' object has no attribute 'tree'` scheitert. Zwei Wege führten dorthin: die Blob-SHA von Hand als Revision, und ein leichtgewichtiger Tag auf einem Blob. Da Versionen nicht gelöscht werden können, wäre der Tag nicht mehr loszuwerden gewesen |
| Version auf einem Dashboard, das es nicht mehr gibt | Wird angelegt und bleibt bestehen. Das Zurückwechseln legt das Dashboard über den Weg aus Entscheidung 8 wieder an — eine Version auf einem gelöschten Dashboard ist genau der Fall, für den sich das lohnt. **Aber nicht auf der Löschzeile selbst:** Dort hat die Datei den Baum verlassen, der Stand ist also keiner, zu dem man zurückkehren könnte. Das Anlegen wird dort seit dem 2026-09-02 mit einem Satz abgelehnt statt eine Version zu erzeugen, die niemand einlösen kann. Zu markieren ist die Zeile **davor** |
| Version anlegen ohne Angabe einer Revision | Sie landet auf dem neuesten Stand **dieses Dashboards**, ausdrücklich nicht auf `HEAD`. Ein Repository hält alle Dashboards, `HEAD` ist also das zuletzt gespeicherte — gemessen am 2026-09-02: `heizung` ohne Revision zu markieren, kurz nachdem `solar` gespeichert wurde, hängt den Tag an solars Commit, und die Version erscheint in heizungs Verlauf danach nie wieder, weil `list_changes` nur dessen eigene Pfade läuft. Hat das Dashboard keinen einzigen Stand, wird abgelehnt |
| Version, deren Commit nicht im Verlauf dieses Dashboards liegt | Kann nur von Hand entstehen (Dienst mit fremder Revision). Der Dienst `versions` führt sie weiterhin auf; im Verlauf bekommt sie **keinen** Abschnitt, weil es keine Änderung gibt, über der sie stünde. Lieber unsichtbar an einer Stelle als Änderungen unter einem falschen Kopf |
| Tag, der dem Muster `vX.Y.Z` nicht folgt | Wird beim Hochzählen übergangen und trotzdem angezeigt. Ein von Hand gesetzter Tag darf die Nummernfolge nicht verschieben, aber auch nicht unsichtbar sein |
| Zurückwechseln auf eine Version, die dem aktuellen Stand entspricht | Der Knopf verschwindet, wie beim Ganz-Zurück in Entscheidung 9. Ein Knopf, der nichts tut, ist eine Frage ohne Antwort |
| Zwei Versionen auf demselben Commit | Erlaubt. Sie zeigen auf denselben Stand; der Verlauf zeigt beide Köpfe untereinander mit demselben Inhalt darunter |

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
| Versionsnummern ordnen | `v1.10.0` steht über `v1.9.0`, nicht darunter — numerisch, nicht lexikografisch |
| Die drei Kandidaten | aus `1.2.3` werden `1.2.4`, `1.3.0`, `2.0.0`; ohne Vorgänger `0.0.1`, `0.1.0`, `1.0.0` |
| Unbrauchbare Tag-Namen | werden beim Hochzählen übergangen und verschieben die Folge nicht |
| `resolve()` über einen Versions**namen** | `heizung/v1.0.0` löst auf den Commit auf — der Test, dessen Fehlen die Falschaussage in Entscheidung 10 durchgelassen hat |
| Version anlegen und zurückwechseln | Tag entsteht, `read_at` über den Namen liefert den Stand, ein Rücksprung macht keine Version unerreichbar |
| Abschnitte im Verlauf | jede Änderung landet unter genau einer Version, die neuesten über der obersten |

Die Home-Assistant-freien Module laufen in reinem pytest, ohne laufende Installation.

## Reihenfolge der Vorhaben

1. **Diese Fassung — die Integration und das Panel.** Erfassen, Verlauf, Zurückholen, Versionen; bedienbar über Dienste *und* über die Änderungsansicht in der Seitenleiste. Das Panel war ursprünglich Stufe 2 und wurde am 2026-08-30 vorgezogen, nachdem sich die Dienste an der Anlage bewährt hatten. Es nutzt `panel_custom`, den offiziell unterstützten Erweiterungspunkt, und ist immer erreichbar — auch außerhalb des Bearbeitungsmodus.
2. **Der Eintrag im ⋮-Menü.** Eine Abkürzung ohne offiziellen Haken, gebaut wie `kiosk-mode` es tut. Sie **darf still ausfallen**: Findet sie ihren Platz nicht, protokolliert sie das und tut sonst nichts. Sie ist nie der einzige Zugang.

Erst wenn sich Stufe 1 in der eigenen Anlage bewährt hat, wird über die Veröffentlichung entschieden.

### Nachgetragen am 2026-09-02: A, B, C

Aus einem Gespräch über Versionen wurden vier Vorhaben. In eine Spec gepresst ergäbe das ein Bauwerk, bei dem am Ende niemand mehr weiß, welcher Teil welches Problem löst. Sie werden deshalb einzeln entworfen, geplant und gebaut — **in dieser Reihenfolge, weil sie vom Messen zum Löschen führt und nicht umgekehrt.**

- **A — Versionen.** Entscheidung 13. Diese Spec, ein eigener Plan.
- **B — Beobachten.** Ein Options-Flow und die **erste Entity-Plattform** dieser Integration: Repository-Größe, Zahl der erfassten Stände, Zahl der Dashboards und — der wichtigste — der Zeitpunkt der neuesten Erfassung. Bleibt der stehen, hat das Erfassen stillschweigend aufgehört; dieses Projekt hat dreimal erlebt, dass der Code richtiger war als sein eigener Bericht, und ein Wachhund dagegen ist mehr wert als eine Größenanzeige. Eigene Spec.
- **C — Aufräumen.** Zuerst das **verlustfreie** Verdichten, danach — und nur, falls die Messwerte aus B es rechtfertigen — eine Aufbewahrungsregel. Eigene Spec.

**Warum diese Reihenfolge und nicht die bequeme:** B könnte nach ein paar Wochen zeigen, dass C's Löschteil nie gebraucht wird. Eine unwiderrufliche Operation zu entwerfen, bevor irgendjemand Messwerte hat, wäre in diesem Projekt der falsche Weg herum.

**Was für C bereits gemessen ist** (2026-09-02, dulwich 1.2.14, am echten `energie-2.yaml` mit 262 KiB):

| Befund | Wert |
|---|---|
| Repository der Anlage | 42 Commits, 122 lose Objekte, **kein einziger Pack** |
| Kosten je Stand | 28 KiB, linear |
| 100 Stände lose | 2833 KiB — davon rund ein Drittel reiner Blockverschnitt |
| `porcelain.repack()` | fasst nur lose Objekte zusammen, **ohne Deltas** (Quelltext gelesen) |
| `object_store.repack()` — der von `garbage_collect` und damit von `forget()` benutzte Weg | konsolidiert alles in einen Pack, ebenfalls **ohne Deltas**: `pack_objects_to_data` setzt `deltify=None` auf `False` |
| Gewinn des schlichten Zusammenfassens | 24 % Plattenplatz, hunderte Dateien werden zwei |
| Gewinn mit Deltas | **95 %** — 120 Objekte schrumpfen von 1109 KiB auf 52 KiB |
| Kosten mit Deltas | 30 Objekte 0,7 s · 60 Objekte 9,2 s · 120 Objekte 77 s. Grob kubisch |
| `delta_window_size` | **wirkungslos.** Fenster 1 löst dieselben 435 `create_delta`-Aufrufe aus wie Fenster 10; alle fünf Messungen ergaben 52 KiB und ~73 s |
| Wo die Zeit steckt | 9,785 von 9,798 s in 435 `create_delta`-Aufrufen à 22 ms. Die Rust-Erweiterung ist vorhanden und wird benutzt |
| `git repack -ad` zum Vergleich | 100 Commits auf 185 KiB in 0,1 s |
| Unschädlichkeit des Packens | nachgemessen: abgekürzte Hashes (`iter_prefix`), `resolve`, `read_at` und `list_changes` überstehen es unverändert. **Keine Revision wird ungültig** |

**Empfehlung für C, aus diesen Zahlen:** das schlichte Zusammenfassen bauen, das Delta-Packen nicht. Nicht wegen der Laufzeit allein, sondern wegen einer Falle: Delta-gepackte Objekte werden von jedem späteren `repack()` wieder auseinandergezogen, weil dessen Pfad `deltify=False` benutzt. Eine Optimierung, die sich selbst unbemerkt zurücknimmt, ist in diesem Projekt disqualifiziert. Der Vorbehalt bleibt bestehen, falls dulwich den Fensterregler repariert.

**Und was in C ausdrücklich nicht passiert:** Änderungen unter einer Version zu **verschmelzen**. Das war der ursprüngliche Vorschlag und ist verworfen — nicht nur, weil es die Einzelrücknahme, die Beschreibungen aus Entscheidung 10 und jede herumgereichte Revision kostete, sondern weil es sich nicht einmal rechnet: Zehn verschmolzene Stände à 28 KiB wären 280 KiB, der vollständige, richtig gepackte Verlauf derselben hundert Änderungen 185 KiB. **Verdichten schlägt Verschmelzen, wirtschaftlich und nicht nur moralisch.** Die Rolle der Versionen beim Aufräumen ist daher die umgekehrte: Sie sind die **Schutzmarke** — was einen Tag oder eine eigene Beschreibung trägt, wird nie angetastet.

### Nachgetragen am 2026-09-03: E

- **E — Die gezielte Rücknahme.** Entscheidung 15, diese Spec, ein eigener Plan. Sie ist die Einlösung von Entscheidung 5 und steht **vor** B und C: Sie berührt `analyze.py` und `restore.py`, also denselben Kern, den Entscheidung 14 gerade umgebaut hat, und je länger dazwischen liegt, desto weniger trägt das frische Wissen darüber. B und C fassen den Kern nicht an und verlieren durch Warten nichts.

  Nicht Teil von E, obwohl beim Entwerfen gefunden und darum unter »Offene Punkte« festgehalten: die beiden Fenster-Fehler (Version außerhalb der neuesten 50, Dashboard außerhalb der letzten 1000 Commits). Sie liegen in `operations.py` und `store.py`, haben mit der Zuordnung nichts zu tun, und sie in E hineinzuziehen hieße, ein Vorhaben mit zwei unabhängigen Begründungen zu bauen.

## Offene Punkte

- ~~**Zugriff auf das Lovelace-Objekt im Speicher** ist noch nicht praktisch verifiziert.~~ **Erledigt am 2026-08-30.** An einer laufenden Anlage bestätigt: `debug_snapshot` meldet alle zehn Dashboards, die Warnung »Lovelace data not available in the expected shape« erscheint **nicht**, der Rückfall bleibt ungenutzt. Ein neu angelegtes Dashboard war sechs Sekunden später als Commit da — ohne jede Wartezeit. **Entscheidung 1 trägt.**
- **Sechs Befunde am älteren Kern, von einem unabhängigen Review am 2026-09-02 gefunden.** Keiner stammt aus Entscheidung 13; sie lagen vorher da und brauchen eigene Entwurfsarbeit. Zusammen sind sie ein **Vorhaben D**, und mehrere wiegen schwerer als alles, was dieses Vorhaben zu reparieren hatte:

  1. **Ein unterbrochenes `forget` ist nicht wiederaufnehmbar und verliert fremde Beschreibungen.** HEAD, Notizen und Tags werden nacheinander umgeschrieben, ohne vorbereiteten Ersatz-Ref. Bricht es zwischen `_point_head` und `_rewrite_notes` ab, ist das vergessene Dashboard bereits aus HEAD verschwunden, ein zweiter Lauf liefert `0` und kann nichts reparieren, und die Beschreibungen eines **lebenden** Dashboards fehlen danach. Echter Metadatenverlust an unbeteiligten Daten, in der einzigen unwiderruflichen Operation.
  2. ~~**Dashboard-Schlüssel mit Schrägstrich werden erfasst, aber aus allen Übersichten verloren.**~~ **Erledigt am 2026-09-03 — und anders, als der Befund vorschlug: als Regel, nicht als Reparatur.** Der ursprüngliche Wortlaut: Geschrieben wird der Schlüssel als Pfad, gelesen und aufgelistet wird eine Datei der obersten Ebene; nachgemessen an HA 2026.8.3 wurde `url_path="dh-slash/check"` angenommen, die Historie entstand, `dashboards` führte sie nicht auf.

     **Die Frage, die vorher niemand gestellt hatte, war, ob so ein Dashboard überhaupt existiert.** Am Prüfstand nachgemessen: Die API nimmt die Anmeldung an und schreibt einen Datensatz — **erreichbar ist das Ergebnis nicht.** `IndexView.resolve` (`frontend/__init__.py:812`) sucht das Panel allein über das *erste* Pfadsegment; `energie-x/growatt` antwortet mit 404, und `energie-x` ebenso. Die Oberfläche lässt einen solchen `url_path` gar nicht eintragen: erlaubt sind Buchstaben, Ziffern, `-` und `_`, und ein `-` ist Pflicht — nachgeprüft an einem neu angelegten Dashboard, das sich nicht auf `hurz`, `hurz-` oder `hurz_` umbenennen ließ, sondern `a-hurz` werden musste. Was ein solcher Datensatz erzeugt, ist ein **Geist**: kein Browser kommt hin.

     Damit ist der saubere Weg nicht, `dashboards` das Verschachtelte lesen zu lehren, sondern **einen solchen Schlüssel nicht aufzuzeichnen**. `keys.is_safe_key` verlangt ein einzelnes gewöhnliches Pfadsegment, `capture` sortiert alles andere mit einer Warnung *unter Nennung des Schlüssels* aus — ein Dashboard ohne Historie darf nicht schweigend eines ohne Historie bleiben. Nichts Rechtmäßiges wird abgewiesen. Der Nebengewinn liegt auf der Tag-Seite: `<key>/v1.0.0` kann jetzt nur noch **einen** Schrägstrich tragen, womit die Präfixprüfungen in `store.py` (`_rewrite_tags`, `list_versions`) durch einen Schlüssel nicht mehr zu täuschen sind. Sie bleiben deshalb **absichtlich unverändert**; ein von Hand gesetzter Tag mit mehr Segmenten täuscht sie weiterhin, aber das ist Handarbeit an der Ablage und keine Nutzerhandlung.

     **Was einmal aufgezeichnet wurde, bleibt erreichbar** — und das ist keine Vorsichtsformel: Im Prüfstand-Store liegen drei solche Verzeichnisse (`dh-slash`, `energie-x`, `zz-slash`). Die Grenze im Store prüft darum **nicht die Schlüsselregel nach**, sondern nur, dass eine Datei *innerhalb* der Ablage liegt. Ein verschachtelter Altbestand bleibt damit lesbar und löschbar, statt in einer Historie festzusitzen, die keine Operation mehr beenden kann.
  3. **Löschen und schnelles Wiederanlegen desselben `url_path` verschmelzen zwei Dashboards.** Die Entprellung von zehn Sekunden verwirft den Zwischenzustand »gelöscht« vollständig, und damit die Trennlinie, auf die sich Entscheidung 12 ausdrücklich verlässt. Ein fremdes Dashboard erbt die alte Historie und bekommt daraus alte Karten zur Wiederherstellung angeboten.
  4. ~~**Eine Karte zwischen Views oder Abschnitten zu verschieben, wird als Löschung angeboten.**~~ **Erledigt am 2026-09-03, Entscheidung 14.** Die Zuordnung greift nur innerhalb derselben Container-Position. Bestätigt jemand die vermeintliche Wiederherstellung, wird eine noch vorhandene Karte **verdoppelt**.
  5. **Mehrdeutige schwache Schlüssel: am 2026-09-03 erledigt (Entscheidung 14, Zuordnung nach bester Ähnlichkeit). Fehlende bleiben offen** — und zwar als benannte Grenze, nicht als Versäumnis: An 27 von 484 Karten ist nichts zu erkennen, und keine Rechnung kann dort Bearbeitung von Löschung unterscheiden. Der ursprüngliche Befund lautete: Zwei Karten mit gleicher `type`/`entity`: Die erste wird gelöscht, die zweite bearbeitet — angeboten und zurückgeholt wird die alte Fassung der *vorhandenen*, während die wirklich gelöschte verloren bleibt. Das ist der Fehlalarm, den Entscheidung 4 als schlimmer einstuft als eine fehlende Funktion, mit Datenverlust obendrauf.
  6. **Die 1000-Commit-Grenze lässt alte gelöschte Dashboards verschwinden.** `list_all_dashboards` und die Vorschau von `forget` haben undokumentierte harte Grenzen. Nach tausend Commits anderer Dashboards führt die Liste das alte gelöschte nicht mehr, `forget` meldet »no history«, und die Sicherheitsvorschau unterschätzt Anzahl, Zeitraum und Beschreibungen.

     **Am 2026-09-03 am Prüfstand nachgemessen, und es ist schlimmer als notiert: Es trifft auch *lebende* Dashboards.** `async_dashboards` bildet seine Liste allein über `list_all_dashboards()`; `list_dashboards()` — der HEAD-Baum, in dem alle stehen — wird nur zum Setzen des `exists`-Kennzeichens benutzt. Ein Dashboard, das im aktuellen Stand liegt, dessen letzte Änderung aber jenseits des Fensters liegt, fällt damit ganz aus der Seitenleiste. Gemessen: 1052 Commits in der Ablage, neun echte Dashboards zuletzt geändert bei Commit 1034 bis 1051 — alle neun aus der Liste verschwunden, während zwanzig Wegwerf-Dashboards der Prüfläufe stehenblieben. Für einen Nutzer heißt das: **Ein Dashboard, das er ein Jahr nicht anfasst, verschwindet aus dem Werkzeug.** Die Behebung ist eine Zeile — die Namensmenge beginnt beim HEAD-Baum, der Lauf durch die Historie fügt nur noch die gelöschten hinzu, also genau das, was der Docstring als seinen Zweck nennt.

- ~~**Ein Schlüssel mit `..` schreibt außerhalb der eigenen Ablage.**~~ **Am 2026-09-03 gefunden und am selben Tag geschlossen.** Am Prüfstand gemessen: Ein über die API unter dem `url_path` `../weiter-weg` angemeldetes Dashboard wurde **neben** das Repository geschrieben, das die Integration führt — dorthin, wo nichts es zurückliest und nichts es aufräumt. Geschlossen durch zwei voneinander unabhängige Prüfungen, und ausdrücklich nicht durch dieselbe zweimal: `keys.is_safe_key` entscheidet, was überhaupt ein Schlüssel werden darf; `HistoryStore._file_for` entscheidet die einzige Frage, die an der Grenze zählt — bleibt die Datei innerhalb der Ablage. Die zweite hält, auch wenn ein späterer Aufrufer die erste vergisst, und sie ist bewusst **nicht** strenger als das (siehe D2, letzter Absatz).

- ~~**Zwei Speichervorgänge kurz hintereinander kehren die Historie um und beschreiben sich gegenseitig falsch.**~~ **Am 2026-09-03 gemessen und geschlossen.** Der Rekorder las die lebende Konfiguration und baute seine Commit-Botschaft in zwei getrennten Schritten; bei zwei Vorgängen kurz hintereinander lasen beide, dann schrieben beide, und wer zuletzt schrieb, verglich seinen *älteren* Stand gegen ein HEAD, das schon der neuere war. Gemessen an sieben Speichervorgängen: Die Kette kam als `1,2,3,4,6,5,7` heraus, und ein Eintrag behauptete »changed outside Home Assistant« über ein Speichern, das Home Assistant selbst gerade gemacht hatte. Das Fenster ist rund 30 ms breit, 3 von 3 Versuchen trafen es. **Der erste Behebungsversuch war eine einzige Sperre über Lesen und Schreiben — und der war schlimmer als der Fehler.** Er ist am Prüfstand durchgefallen, dreimal an denselben vier Prüfungen, und die Messung sagt, warum: Ein Abgleich über die gewachsene Ablage hielt die Sperre **16,6 s**, ein Speichervorgang wartete **7,2 s** darauf, und als er endlich lesen durfte, war das Dashboard gelöscht — er schrieb nichts, und dieser Stand ist endgültig weg. Eine Sperre, die das Lesen einschließt, verschluckt genau das, was sie schützen soll.

  Behoben ist es mit **zwei Sperren, je eine Aufgabe**. Die *Schreibsperre* umfasst HEAD-Abfrage, Botschaft und Commit als einen Abschnitt — sie stellt die Reihenfolge her und macht die Botschaft wahr. Die *Lesesperre* hält nur das Befragen von Home Assistant zusammen, fasst kein git an und ist in Millisekunden fertig; wer danach auf die Schreibsperre wartet, wartet **mit dem Zustand in der Hand**. Die Ordnung bleibt trotzdem die des Lesens, weil jeder Vorgang die Lesesperre verlässt und die Schreibsperre betritt, ohne dazwischen etwas abzuwarten. Der Merksatz, der die Aufteilung trägt: **Ein langsames Schreiben verzögert die Historie, ein langsames Lesen zerstört sie.** Nachgemessen mit der neuen Bauform: sieben Speichervorgänge, Kette 1…7, jede Botschaft »1 added«, und die vier Prüfungen bestehen wieder — zweimal hintereinander, das zweite Mal unter genau dem Anfangszustand, unter dem sie zuvor durchfielen.

  Das ist zugleich **Voraussetzung für Vorhaben E**: `store.previous_change` läuft die Elternkette, und aus einer verkehrten Kette bekäme eine gezielte Rücknahme den falschen Vorzustand — sie würde eine Karte entfernen, die nie hinzukam, und eine wieder einsetzen, die längst steht.

- **Eine Version außerhalb der neuesten 50 Änderungen wird unsichtbar — Marke ohne Haltbarkeit.** *(Am 2026-09-03 am Prüfstand gemessen.)* `async_history` hängt Versionen über `marks.get(c.revision, [])` an Änderungen, und im Panel kommt *alles* über Versionen aus diesem einen Feld: Abschnittsköpfe, die Plakette »current state«, der Chip »same state as v1.0.0«. Fällt der Commit einer Version aus den neuesten 50 Änderungen, existiert sie für die Oberfläche nicht mehr. Belegt an `dh-probe`: Der Tag `dh-probe/v0.0.1` liegt unversehrt in der Ablage, sein Stand ist lesbar und **byteweise gleich dem aktuellen** — und trotzdem zeigt das Panel weder die Version noch den Hinweis auf die Übereinstimmung. Für einen Nutzer: Version setzen, fünfzigmal speichern, Version weg. Eine Marke, die verschwindet, ist keine. Die Plakette ist exakt zu reparieren (Übereinstimmung gegen *alle* Versionen prüfen statt gegen die sichtbaren); die Version wieder im Verlauf zu zeigen heißt, Commits von außerhalb des Fensters hereinzuholen, und bei 146 Versionen wäre das eine Wand aus Zeilen — das braucht einen eigenen kleinen Entwurf.

- **Eine Löschzeile ist als solche nicht erkennbar — und zwei Knöpfe stolpern darüber.** *(Aufgeworfen am 2026-09-02 vom Abschluss-Review.)* `history` sagt nicht, welche Änderung eine Löschung ist; das Panel kann es nur am generierten Meldungstext ablesen, und Textschnüffelei ist genau die Logik, die dort nicht liegen darf. Zwei Stellen leiden darunter: »Version bis hierher« auf der Löschzeile eines gelöschten Dashboards wird jetzt abgelehnt (siehe Randfälle), aber erst *nachdem* geklickt wurde; und »Back to the state after this change« wird dort ebenfalls angeboten, obwohl `restore_state` nur »did not exist at« antworten kann. Der saubere Weg ist ein Merkmal je Änderung in `history` — eine kleine Ergänzung, die beide Knöpfe vorher verschwinden ließe. Bewusst nicht mehr in dieser Fassung gebaut: Sie kam nach dem Abschluss-Review auf, und die Ablehnung ist heute wenigstens ehrlich statt still falsch.
- ~~**Platzbedarf über sehr lange Zeiträume.**~~ **Am 2026-09-02 gemessen, mit einer unerwarteten Antwort.** Über hundert Stände bleibt es linear (28 KiB je Stand) — die Vermutung, git packe dann von selbst besser, ist **falsch**: dulwich packt überhaupt nie. Das Repository der Anlage führte nach zwei Tagen 122 lose Objekte und keinen einzigen Pack, denn `porcelain.commit` schreibt lose Objekte und dulwich kennt keine selbsttätige Bereinigung. Sämtliche Zahlen stehen unter »Reihenfolge der Vorhaben«; gehandelt wird in Vorhaben C.
- ~~**Einordnung umsortierter Karten**~~ **An echten Daten entschieden am 2026-08-30.** Zwei Befunde:

  1. *Verschiebungen werden relativ gemessen, nicht absolut.* Ein Vergleich roher Positionen erklärte jede Karte hinter einer Löschung zur Verschiebung — auf großen Views zwanzig Meldungen Rauschen um die eine, auf die es ankommt. Gezählt wird jetzt der Rang unter den Überlebenden: Eine Löschung allein erzeugt **keine** Verschiebung, ein Tausch weiterhin zwei.
  2. *Die schwache Zuordnung reichte bei weitem nicht weit genug.* Sie kannte nur `entity`, `title` und `name` — die trägt auf dieser Anlage nur **57 % der 1526 Karten**. Alle übrigen lösten beim Bearbeiten einen Fehlalarm aus: gemeldet als gelöscht **und** neu angelegt, obwohl sie unverändert dastanden. Genau der Fall, den dieses Dokument oben als schlimmer bezeichnet als eine fehlende Funktion. Die Zuordnung greift jetzt zusätzlich auf `heading`, die erste Entität einer Entitätenliste, die erste Textzeile und die benennbare Karte innerhalb eines Containers zu — damit **96 %**. Eine Ähnlichkeitsbewertung braucht es dafür nicht.
