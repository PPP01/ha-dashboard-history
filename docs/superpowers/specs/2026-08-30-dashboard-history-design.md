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
- **Kein Entfernen von Inhalt aus der Historie** — außer dem endgültigen Vergessen eines gelöschten Dashboards nach Entscheidung 12. **Am 2026-09-08 gestaffelt entschieden**, siehe Entscheidung 18: Eine Version lässt sich seither *aufheben*, ihr Stand nicht. Inhalt zu entfernen bleibt Vorhaben C, wo es zusammen mit dem Verdichten entworfen wird und nach den Messwerten aus B. Das steht hier, damit das Fehlen als Entscheidung gelesen wird und nicht als Lücke — die Frage danach kam vom Nutzer, und die Antwort war nicht »noch nicht gebaut«, sondern »nicht an dieser Stelle«.
- **Kein Ersatz für Backups.** Die Integration sichert Dashboards, nicht die Installation.

## Architektur

### Bausteine

| Datei | Aufgabe | Home-Assistant-frei |
|---|---|---|
| `keys.py` | Welches Dashboard welches ist, und welches fehlt | **ja** |
| `identity.py` | Welche Ansicht und welche Section über zwei Stände hinweg dieselbe ist — siehe Entscheidung 16 | **ja** |
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

Die fünf oberen sind reine Logik und ohne laufendes Home Assistant prüfbar. Diese Trennung ist keine Stilfrage: Sie erlaubt, die Einordnungs-Regeln — das Herz des Projekts — in Sekunden gegen Dutzende Fälle zu testen, statt sie an einer Live-Anlage zu erproben.

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

4. **Zurückgeholt wird nur, was verschwunden ist — und ganze Stände.** Das ist keine Sparmaßnahme, sondern folgt aus der Datenlage: Karten haben keine Kennung, sind also nur über ihre Position bestimmt. Eine **ersetzende** Rücknahme (»diese Bearbeitung zurück, spätere behalten«) ist deshalb eine Zusammenführung ohne Identitäten und in verschränkten Fällen nicht eindeutig. Eine **additive** Rücknahme (»das hier fehlt, setze es wieder ein«) überschreibt nichts und ist immer wohldefiniert. Und die schmerzhaften Fälle sind genau die additiven: Eine verschobene Karte schiebt man zurück, eine gelöschte ist weg. *(Ergänzt am 2026-09-04 durch Entscheidung 16: Für Ansichten und Sections — nicht für Karten — führt die Integration seither eigene Kennungen mit. Der Grundsatz dieser Entscheidung bleibt unberührt; zurückgeholt wird weiterhin nur Verschwundenes.)*

   **Am 2026-09-03 eingegrenzt, nicht aufgehoben (Entscheidung 15).** Der Satz oben bleibt für den allgemeinen Fall wahr. Was hinzukommt: Wo sich die Eindeutigkeit *nachweisen* lässt — der Inhalt, den eine Änderung erzeugt hat, steht heute genau einmal im Dashboard —, ist eine ersetzende Rücknahme keine Zusammenführung ohne Identitäten mehr, sondern ein bestimmter Austausch. Angeboten wird sie nur dort. Überall sonst gilt Entscheidung 4 unverändert.

5. **Die Einzelrücknahme wird später *bedingt* angeboten, nicht mit Warnhinweis.** **Eingelöst am 2026-09-03 durch Entscheidung 15.** Ob eine ersetzende Rücknahme eindeutig ist, lässt sich feststellen: Man prüft, ob eine spätere Änderung denselben Bereich angefasst hat. Das Werkzeug entscheidet also selbst und sagt entweder »zurücknehmen« oder »geht nicht, weil …, hier sind die Alternativen«. Ein Warnhinweis wäre schlechter, weil er die Entscheidung an jemanden weiterreicht, der die Verschränkung nicht sehen kann.

6. **Vollständige Stände speichern, keine reinen Deltas.** Damit ist die Einzelrücknahme später eine reine Rechenfunktion über vorhandene Daten — nachrüstbar ohne Datenmigration. git dedupliziert die Stände ohnehin.

7. **Nichts wird ohne Vorschau geschrieben.** Jede Wiederherstellung zeigt zuerst den Diff. Derselbe Grundsatz wie beim bestehenden Restore-Werkzeug.

   **Die Regel gilt für Dashboards, nicht für Beschriftungen.** *(Grenze nachgetragen am 2026-08-31.)* Ihr Zweck ist, dass niemand sein Dashboard unversehens verändert findet. Eine Beschreibung nach Entscheidung 10 verändert kein Dashboard, ist sofort und vollständig zurücknehmbar und wird von der Person geschrieben, die sie gleich danach liest. Ein Bestätigungsdialog davor wäre Zeremonie ohne Schutzwirkung — und das Gegenteil dessen, wofür die Funktion gebaut wird. Sie verlangt deshalb **kein** `confirm`. Jeder Vorgang, der einen Dashboard-Stand schreibt, verlangt es weiterhin ohne Ausnahme.

   **Und die Regel hat eine zweite Seite.** *(Nachgetragen am 2026-09-08.)* Sie sagt, wann `confirm` **nötig** ist — nicht, wann es allein genügt. Ein Vorgang, der keinen Dashboard-Stand schreibt, kann es trotzdem verlangen: dann, wenn er etwas wegnimmt, das die Integration nicht zurückschreiben kann. Das trifft auf `forget` nach Entscheidung 12 zu und seit Entscheidung 18 auf `remove_version`. Der Unterschied zu einer Beschreibung ist nicht die Sichtbarkeit, sondern die Umkehrbarkeit: Eine Notiz schreibt dieselbe Person in derselben Minute neu; die Worte einer aufgehobenen Version sind fort. Es gibt also **zwei** Gründe für einen Dialog, und sie sind auseinanderzuhalten — sonst wird aus »Zeremonie ohne Schutzwirkung« irgendwann das Argument, mit dem auch der Dialog vor einer Löschung fällt.

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

13. **Versionen kehren in die Oberfläche zurück — je Dashboard, mit Versionsnummern.** *(Ergänzt am 2026-09-04 durch Entscheidung 17: Seither entstehen Versionen auch von selbst — bei der Einrichtung und beim ersten Speichervorgang eines Tages. Das Namensschema und die Infrastruktur bleiben unverändert.)* *(Nachgetragen am 2026-09-02, auf Wunsch des Nutzers.)*

    Entscheidung 10 hatte sie aus der Oberfläche genommen, weil sie damals dasselbe konnten wie eine Beschreibung: einen Punkt benennen. Zwei Wege für dieselbe Sache waren ein Konzept zu viel, und das Argument war richtig. Es trägt hier nicht mehr, weil eine Version ab dieser Entscheidung etwas kann, was eine Notiz nie konnte: **einen Stand herstellen.** Nicht »dieser Punkt hieß so«, sondern »bring mich dorthin zurück, und dann wieder her«. Das ist eine andere Sache, kein zweiter Weg zur selben.

    **Zuerst eine Berichtigung, denn Entscheidung 10 stützte sich auf eine Behauptung über den Code, die nicht stimmt.** Dort steht, Tags blieben als Dienste erhalten, weil `resolve()` ihren Namen als Revision annehme. Am 2026-09-02 nachgemessen an dulwich 1.2.14: **das tut es nicht, und nie getan.** `repo[b"v1.0.0"]` wirft `KeyError`; nur der volle Pfad `refs/tags/v1.0.0` trägt, weil dulwich die Kurzform-Auflösung, die `git` gewohnheitsmäßig leistet, in `Repo.__getitem__` nicht nachbildet. Kein Test hat es bemerkt, weil der vorhandene die *Objekt-ID* des Tags auflöst und nie seinen Namen. Die README behauptete dasselbe. `_resolve` probiert deshalb ab hier die übliche Suchreihenfolge `name`, `refs/tags/name`, `refs/heads/name`. Damit ist die Adressierbarkeit erstmals wahr — und sie ist die Grundlage von allem Weiteren, denn sie macht das Zurückwechseln zu vorhandenem Code.

    **Der Namensraum ist der Dashboard-Schlüssel:** `<schlüssel>/v<major>.<minor>.<patch>`. Damit darf jedes Dashboard sein eigenes `v1.0.0` haben. Gemessen am selben Tag: Schrägstriche in Tag-Namen tragen, ebenso der Unterstrich in `_default/v1.0.0` und sogar Umlaute; Leerzeichen weist dulwich mit `RefFormatError` ab. Eine Falle wurde dabei gefunden und wird abgefangen: Ein **flacher** Tag `heizung` neben `heizung/v1.0.0` ist in git unmöglich — Ref-Datei und Ref-Verzeichnis sind derselbe Pfad. Das Anlegen prüft das vorher und lehnt ab, statt es zu erleiden. *(Am 2026-09-02 im Detail berichtigt: Die beiden Richtungen scheitern unterschiedlich. Ein flacher Tag **über** einem Namensraum wirft `IsADirectoryError` und lässt eine `.lock`-Datei zurück; ein Namensraum **unter** einem flachen Tag wirft `NotADirectoryError` und lässt keine zurück, weil schon das Anlegen der Sperrdatei scheitert. Die Prüfung deckt beide Richtungen ab, und seit demselben Tag auch Schlüssel mit mehr als einem Schrägstrich: **jeder** Präfix bis zu einem `/` ist ein möglicher Blockierer, nicht nur der erste.)*

    **Die Nummer wird gewählt, nicht getippt.** Drei Knöpfe, jeder mit der fertigen Nummer darauf — Patch, Minor, Major —, **Patch vorausgewählt**. Ohne bestehende Version stehen dort `0.0.1`, `0.1.0` und `1.0.0`. Gezählt wird immer von der **höchsten vorhandenen** Version dieses Dashboards, auch nach einem Rücksprung: So bleiben die Nummern monoton und können nie kollidieren. *(Am 2026-09-08 zur **bedingten** Zusage geworden, siehe Entscheidung 18. Kollidieren können sie weiterhin nie — gezählt wird von dem, was da ist. Monoton bleiben sie nur, solange keine Version aufgehoben wird: Wird die höchste aufgehoben, vergibt der nächste Klick dieselbe Nummer erneut. Für den Fall, für den das Aufheben gebaut wurde — eine Version, die aus Versehen entstand —, ist das genau das Gewollte; der Preis ist, dass ein irgendwo notierter Name danach zu einem anderen Stand führt. Die Alternative wäre eine Hochwassermarke im Repository gewesen, also ein neues Stück Zustand samt Lücken in der Nummernfolge; sie ist verworfen, weil sie mehr Ablage kostet als sie Verwechslung verhindert.)* Der Mensch tippt nur Titel und Beschreibung. Der Grund für die Knöpfe statt eines Namensfeldes: Ein Tag-Name ist ein technisches Artefakt mit Ref-Regeln, und diese Regeln in einen Dialog durchzureichen hieße, die Ablage in die Oberfläche zu tragen. Die Wahl zwischen Patch, Minor und Major trägt dagegen eine Aussage — war das eine Korrektur oder ein Umbau?

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

       **Am 2026-09-08 vermerkt: diesen Vergleich gibt es jetzt.** `store.same_state(schlüssel, eine, andere)` beantwortet auf der Serverseite, ob zwei Revisionen denselben Stand eines Dashboards halten — über die Blob-Kennungen der Konfiguration, ein Tree-Zugriff je Seite, ohne dass ein Dashboard gelesen und verglichen werden muss. Gebaut wurde er für die automatische Tagesmarke (Plan »Versionen, die von selbst entstehen«, Nachtrag vom 2026-09-08); er beantwortet aber genau die Frage, die dieser Absatz als unerreichbar benannt hat. **An dieser Entscheidung ändert das nichts:** Verweigert wird weiterhin nichts, und das Panel stellt den Vergleich weiterhin nicht selbst an — er käme fertig mit den Daten, sollte der Anlege-Dialog die Inhaltsgleichheit eines Tages auch für einen *älteren* Stand aussprechen. Vermerkt wird es, damit die nächste Antwort auf diese Frage nicht eine zweite Vergleichsmethode ist. Eine Grenze bleibt und ist eine andere: Verglichen wird die Konfiguration, nicht die Metadaten — ein Speichervorgang, der nur Titel oder Symbol ändert, hält für `same_state` denselben Stand.

    3. **Der Bestätigen-Dialog sagt, wohin der jetzige Stand geht.** Die zweite Frage war, ob beim Zurückwechseln nicht zwischen »exakt auschecken und alles Jüngere verlieren« und »`v1.0.0` als neuen Stand anlegen« zu wählen sei. **Die erste Möglichkeit gibt es nicht** — und das ist eine Entscheidung, keine Selbstverständlichkeit: `restore_state` schreibt das lebende Dashboard, der Stand, der dort stand, wird vorher aufgezeichnet, und außer `forget` schreibt nichts einen bestehenden Zustands-Commit um und verschiebt nichts eine bestehende Versionsmarke. (`describe` bewegt `refs/notes/commits` — das ist eine Notiz, kein Stand; die ursprüngliche Fassung dieses Satzes sagte »Refs verschiebt außer `forget` nichts« und war damit zu weit gefasst.) Die Historie wächst, sie schrumpft nie. *(Am 2026-09-08 ein zweites Mal nachgeschärft, aus demselben Grund wie beim ersten Mal: »Die Historie wächst, sie schrumpft nie« ist eine Aussage über **Stände**, und als solche bleibt sie wahr. `remove_version` nach Entscheidung 18 verschiebt keine Versionsmarke — es nimmt eine weg, und der Commit darunter bleibt unangetastet und über seine Revision lesbar. Der Satz sagt nicht, dass die Zahl der Marken nie sinkt.)*

    **Nachtrag vom 2026-09-03: aus einer Annahme wurde eine Zusage.** »Der Rekorder hängt einen Eintrag für das an, was dort stand« war beim Schreiben dieses Absatzes keine Zusage, sondern eine Beobachtung — sie stimmte, weil der Rekorder jedes Speichern hört, und sie stimmte nicht für einen Stand, der nie gehört wurde: ein Speichern während des HA-Starts, eine von außen geschriebene Ablagedatei, ein einmal gescheiterter Rekorder. Am Prüfstand gemessen ist die Lücke selten — drei Stunden gewöhnlicher Nutzung erzeugten keine —, aber genau in ihr fällt der Stand weg, auf den man zurückwollte, und damit der ganze Zweck des Werkzeugs. Jede Operation, die einen Dashboard-Stand schreibt, zeichnet den lebenden Stand deshalb **vorher** auf und **prüft nach**, dass er der neueste Eintrag ist. Zwei Festlegungen dazu, beide begründet:

    - **Misslingt es, wird trotzdem geschrieben** und der Fehlbetrag als Hinweis mitgeteilt. Der Fall, an dem sich das entscheidet, ist der volle Datenträger: Dort liest sich alles und schreibt sich nichts, und eine verweigerte Wiederherstellung nützt in dem Moment niemandem, in dem sie am dringendsten gebraucht wird — die Momentaufnahme wäre ja ohnehin nicht zustande gekommen.
    - **Angekündigt wird sie nicht.** Das Panel liest `history_updated` als »Deine Seite ist veraltet, lies neu«. Mitten in der Operation gefeuert, baut es die Seite aus einem Verlauf, dessen neuester Eintrag der gleich überschriebene Stand ist. Diese Seite sieht **richtig** aus, und das ist schlimmer, als falsch auszusehen. In git *ist* der Unterschied echt — `checkout` gegen `revert` —, wer git kennt, muss die Frage also stellen. Dass sie hier keine zwei Antworten hat, gehört deshalb ausgesprochen statt vorausgesetzt. Weggelassen wird der Satz beim Wiederanlegen eines gelöschten Dashboards: Dort gibt es keinen jetzigen Stand zu behalten, und der Hinweis daneben sagt bereits, was stattdessen geschieht.

    Der gemeinsame Nenner, und der Grund, warum das hier steht und nicht nur im Code: **Eine Eigenschaft schützt besser als eine Warnung.** Weil die einzige zerstörende Operation `forget` heißt und auch so heißt, lässt sich über jede andere sagen: umkehrbar. Das ist mehr wert als jeder Bestätigungsdialog — aber nur, solange es jemand ausspricht. Ein zerstörendes Zurückwechseln nachzurüsten, wäre entsprechend kein neuer Knopf, sondern die Aufgabe dieser Eigenschaft.

    **Am 2026-09-17 ist an genau diesem Satz ein Loch gefunden worden — siehe »Offene Punkte«, Eintrag »Umkehrbarkeit endet an einem nie aufgezeichneten Stand«.** Der Vermerk steht hier und nicht nur dort, weil die Eigenschaft ihren Wert aus dem Ausgesprochenwerden zieht: Ein Prüfstein, dessen Ausnahme man erst am Ende des Dokuments erfährt, ist als Prüfstein unbrauchbar. Bis der offene Punkt entschieden ist, gilt der Satz mit dieser einen, benannten Einschränkung.

    *(Am 2026-09-08 eingeschränkt, und das ist der Nachtrag, der von allen zu Entscheidung 18 am meisten wiegt.* **Es sind jetzt zwei Operationen, die etwas wegnehmen, und sie sind verschieden groß.** `forget` nimmt Stände, `remove_version` nimmt eine Marke und die Worte darauf — kein Stand, keine Revision, kein Dashboard. Über jede andere Operation lässt sich weiterhin »umkehrbar« sagen. Die Eigenschaft ist also nicht gefallen, aber sie ist nicht mehr in einem Wort zu haben, und genau deshalb steht sie hier und nicht nur im Code: Der Satz »die einzige zerstörende Operation heißt `forget`« war der Prüfstein, an dem jede neue Funktion gemessen wurde. Sein Ersatz lautet: **Was einen Stand wegnimmt, heißt `forget` — und es bleibt bei dem einen.** Alles andere darf höchstens eine Beschriftung kosten, und wenn es das tut, verlangt es `confirm` (Entscheidung 7, zweite Seite).*)*

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
    | Karte **bearbeitet** (alt→neu) | `zähler[neu] == 1` | die eine Fundstelle entfernen, *alt* am alten Platz einsetzen |
    | Karte **verschoben** | `zähler[karte] == 1` | dort entfernen, am alten Platz einsetzen |
    | Karte **hinzugefügt** | `zähler[neu] == 1` | die eine Fundstelle entfernen |
    | Karte **gelöscht** | `zähler[alt] == 0` | am alten Platz einsetzen |
    | Karte gelöscht, ist aber wieder da | `zähler[alt] > 0` | nichts tun — dieser Teil ist bereits zurück |

    **Alles oder nichts.** Trifft eine dieser Bedingungen nicht zu, ist die *ganze* Rücknahme verweigert, nicht nur der eine Punkt. Ein halb zurückgenommener Stand ist einer, den niemand gewollt hat und den die Zeile daneben nicht mehr beschreibt. Die Verweigerung nennt Grund und Karte, wie Entscheidung 5 es verlangt — »geht nicht, weil …« statt eines Warnhinweises, der die Entscheidung an jemanden weiterreicht, der die Verschränkung nicht sehen kann.

    **Ganze Views nach derselben Regel, und ebenfalls über den Inhalt.** Eine View, die nur ein Stand hat, ist eine Zeile im Verlauf und nicht eine je Karte; gefragt wird bei ihr dasselbe, nur gröber. Entscheidend ist, dass auch hier der **Inhalt** zählt und nicht der `path`: Ein Pfad ist umbenennbar und wiederverwendbar. Wer nur nachsieht, ob einer vorhanden ist, meldet für eine seither umbenannte View »schon zurückgenommen« und hält eine fremde View auf demselben Pfad für die eigene — beides Sätze, die dem Dashboard widersprechen, also genau der Fehler, den diese Spec durchgehend am schwersten wiegt. Sitzt eine fremde View auf dem Pfad, wird verweigert statt eingesetzt: zwei Views auf einem Pfad sind ein kaputtes Dashboard. *(Am 2026-09-03 nach einem Review nachgezogen; die erste Fassung fragte nur nach dem Pfad.)*

    **Es gibt keinen Ersetzungsschritt — bearbeitet und verschoben sind derselbe Vorgang.** *(Am 2026-09-03 beim Bauen korrigiert; der erste Entwurf dieser Entscheidung hatte einen.)* »Die eine Fundstelle an Ort und Stelle durch *alt* ersetzen« klingt sparsamer und ist still falsch. Der Ort einer Karte wird **ohne ihren Index** festgehalten, deshalb kommt eine Karte, die in derselben Speicherung bearbeitet **und** verschoben wurde, hier als »bearbeitet« an — und eine Ersetzung am heutigen Index landet auf ihrer Nachbarin. Über 6000 erzeugte Verläufe gemessen: **48** still falsche Ergebnisse mit Ersetzung, **0** mit Entfernen + Einsetzen, bei genau gleich vielen Verweigerungen (309 zu 309). Gebaut ist deshalb die zweite Fassung, und sie ist auch die einfachere: Bearbeitung und Verschiebung brauchen keine zwei Regeln mehr, sondern eine.

    **Die Reihenfolge beim Anwenden ist Teil der Korrektheit:** erst alle Entfernungen, absteigend nach Index, dann alle Einsetzungen, aufsteigend. Andersherum verschöbe jeder Schritt die Indizes des nächsten — still, versteht sich. Karten vor Views, weil ein Kartenschritt seine View notfalls über die Position findet und ein vorher entferntes View diese Position verschiebt. Jede Entfernung prüft zusätzlich, ob das Geplante überhaupt noch dort steht: Der Plan ist einen Augenblick älter als seine Anwendung, und ein Augenblick reicht für eine Speicherung.

    **Beim Bestätigen wird neu gerechnet, nicht das Vorschauergebnis geschrieben.** Ändert jemand das Dashboard zwischen Vorschau und `confirm`, ist der Undo womöglich nicht mehr exakt; dann kommt die Verweigerung zurück statt eines Schreibvorgangs. Ohne das wäre die Beweisführung an der einen Stelle wertlos, an der sie zählt.

    **Der Undo entfernt auch.** Hat die Änderung eine Karte hinzugefügt, nimmt er sie weg — das erste Mal, dass dieses Werkzeug eine Karte löscht. Vertretbar, weil die Karte byteweise nachweislich die ist, die diese Änderung erzeugt hat, weil sie genau einmal vorkommt, und weil Entscheidung 7 unverändert gilt: Vorschau, dann `confirm: true`.

    **In der Oberfläche ist es eine Weiche, kein dritter Knopf.** Eine Zeile bietet einen Weg zurück: den Undo, wenn er exakt ist, sonst die »Put back«-Liste. *(Die Liste selbst zieht mit Vorhaben J, Entscheidung 19, hinter einen Verweis aus der Verweigerung um — die Weiche als solche bleibt: Undo, wenn exakt, sonst ein Weg zum Put-back.)* Die beiden Ganz-Stand-Knöpfe wandern hinter eine zugeklappte Zeile; »Back to the state before this change« entfällt ganz, wenn er dasselbe schriebe wie der Undo — der Server sagt das mit einem eigenen Feld, damit das Panel es nicht erraten muss. Der Anlass war eine Rückmeldung des ersten Menschen, der die beiden Knöpfe nebeneinander sah: An der obersten Zeile mit genau einer gelöschten Karte tun sie buchstäblich dasselbe, und nichts auf dem Schirm sagte, dass sie es drei Wochen später nicht mehr tun.

    **Ein Put-back-Knopf verschwindet aus genau zwei Gründen.**

    1. **Deckungsgleichheit** — der Undo holt genau dessen eine Karte und sonst nichts. Das trifft auf eine einzige Konstellation zu: eine Änderung, die genau ein Stück gelöscht hat.
    2. **Die Falle** — hat die Änderung außer dem Entfernen auch etwas **hinzugefügt**, verschwinden die Knöpfe für die Stücke, die *diese* Änderung entfernt hat. Der Grund ist gemessen: Eine Bearbeitung, die das identifizierende Feld trifft, liest sich als `1 removed, 1 added` (`markdown`, erste Textzeile geändert: `put-back-Einträge = 1`). »Put back« kann nur hinzufügen und stellt die alte Fassung **neben** die neue — ein Duplikat. Der Undo nimmt die Änderung als Einheit zurück und trifft in beiden Lesarten das Richtige.

    Was aus **späteren** Änderungen fehlt, behält seinen Knopf immer, unter einer Zeile, die das sagt. Und was Regel 2 kostet, ist begrenzt und benannt: Wer nur A zurückwill und das Hinzugefügte behalten, verliert den Knopf *an dieser Zeile* — an jeder älteren steht er weiter, weil A dort ebenfalls als fehlend geführt wird. Global geht nichts verloren.

    **Am 2026-09-12 durch Entscheidung 19 eingeschränkt, dieser Absatz bleibt als Begründung stehen.** Genau diese zeilenübergreifende Wiederkehr — ein und dieselbe fehlende Karte, mit eigenem Put-back-Knopf an jeder älteren Zeile, bis in alle Ewigkeit — erwies sich an einer echten Historie als Dutzende gleichzeitig angebotener Knöpfe unter einer einzigen, beliebigen Zeile. Mit der Umsetzung von Vorhaben J entfällt die automatisch mitlaufende Anzeige dieser Liste im Aufklappen einer Zeile; derselbe Mechanismus bleibt über den dort neu verlinkten Vergleichsmodus erreichbar — noch nicht umgesetzt, siehe `status.md`.

    **Vier Grenzen, ausdrücklich nicht geschlossen.** Beschriftungen (Titel, Symbol eines Dashboards) bleiben außen vor, weil `restore_state` sie ohnehin nicht schreibt. Die 27 merkmalslosen Karten aus Entscheidung 14 bleiben merkmalslos: Sind zwei gleich, ist der Zähler ≥ 2 und der Undo verweigert — richtig, aber dort hilft die Weiche nie. Die Duplikat-Falle bleibt bestehen, wo der Undo verweigert; dieses Vorhaben entschärft nur die Fälle, in denen es einen gibt. Und die Auswahl einzelner Stücke bleibt eine additive Sache: Wer aus einer Änderung nur eines zurückholen will, nimmt den Weg über »Put back«, nicht über den Undo — seit Vorhaben J über den Vergleichsmodus statt über die Zeile selbst, siehe Entscheidung 19.


16. **Ansichten und Sections bekommen eine Identität — in der eigenen Historie, nicht im fremden Dashboard.** *(Nachgetragen am 2026-09-04, nach dem Befund vom selben Tag: `docs/superpowers/reviews/2026-09-04-pfadlose-views-und-sections.md`.)*

    Entscheidung 4 stellt fest, dass Karten keine Kennung tragen und allein über ihre Position bestimmt sind. Eine Ebene höher gilt dasselbe, und dort ist es teurer. Eine Ansicht **ohne** URL-Pfad wird über ihre Position identifiziert, eine Section **immer** — Home Assistant gibt ihr weder Pfad noch Kennung, es gibt dort keine sichere Variante. Eine Position ist aber eine Adresse, keine Identität: Wird die Ansicht davor gelöscht oder eine neue davorgesetzt, benennt derselbe Schlüssel etwas anderes.

    Am 2026-09-04 an einer laufenden Anlage gemessen, jeder Fall bis zum Endzustand durchgeklickt: Eine gelöschte pfadlose Ansicht kam im Bestätigungsdialog überhaupt nicht vor, und das Zurücknehmen schrieb ihre Karte auf eine Ansicht, die niemand angefasst hatte. Das Löschen einer Ansicht *mit* Pfad ließ die pfadlose dahinter nachrücken — und die Rücknahme löschte sie samt Inhalt, obwohl sie an der Änderung nicht beteiligt war. Eine vor die pfadlose gesetzte neue Ansicht ließ beide verschwinden: Sie galt gleichzeitig als hinzugefügt (ihr Schlüssel war neu) und als bereits zurück (ihr Inhalt stand noch), wurde entfernt und nie wieder eingesetzt; das Dashboard war danach leer. Auf Section-Ebene landete eine zurückgeholte Karte lautlos in der falschen Section. Betroffen sind an dieser Anlage 8 von 67 Ansichten ohne Pfad und alle 80 Sections in 24 Ansichten mit Sections-Layout.

    **Das Schreiben ist bereits angehalten** — Paket 1 des Befunds verweigert, wo eine Position nicht mehr dasselbe bedeutet, ganz nach Entscheidung 4: Raten ist verboten, Verweigern erlaubt. Was fehlt, ist die Identität selbst. Ohne sie bleiben diese Rücknahmen dauerhaft verweigert, und die Historienzeile erzählt weiter »1 view removed, 2 views added« für eine Ansicht, die hinzugefügt wurde.

    **Die Kennungen gehören der Integration, nicht dem Dashboard.** Der naheliegende Weg wäre, `id`-Felder in die Dashboards des Nutzers zu schreiben; nachgemessen speichert Home Assistant sie auf Ansichten, Sections und Karten unverändert wieder aus. Er ist trotzdem verworfen. Einen Erweiterungspunkt vor dem Speichern gibt es nicht: `LovelaceStorage.async_save` schreibt die Konfiguration wörtlich durch, und das Ereignis `lovelace_updated` kommt erst danach. Bliebe, den WebSocket-Befehl zu ersetzen — was die harte Regel verbietet, weil es bei einer Veröffentlichung alle Nutzer gleichzeitig träfe — oder nach dem Ereignis zurückzuschreiben. Das verändert fremde Dashboards, erzeugt zu jedem Speichervorgang des Nutzers einen zweiten Historieneintrag, verliert das Rennen gegen einen offenen Editor (`lovelace/config/save` kennt keine Versionsprüfung, das Frontend schickt die ganze Konfiguration) und wirkt ohnehin nur nach vorn.

    **Also führt die Integration die Identitäten selbst mit,** als dritte Spur neben `<schlüssel>.yaml` und `meta/<schlüssel>.yaml`, mit jedem Stand mitcommittet:

    ```yaml
    # ids/dashboard-standard.yaml
    views:
      - id: v-7f3a
        path: home            # null bei einer Ansicht ohne URL-Pfad
        sections: [s-11c2, s-9d40]
      - id: v-2b81
        path: null
        sections: []
    ```

    Die Reihenfolge ist die Position im Stand; ein eigenes Positionsfeld gibt es deshalb nicht, denn es könnte von der Wirklichkeit abweichen. Kennungen sind bedeutungslos und nur innerhalb eines Dashboards eindeutig. `meta/` bleibt unberührt: Dort steht, was ein Dashboard *ist* — Titel, Symbol, Seitenleiste —, hier steht, was *welches* ist.

    **Zugeordnet wird beim Erfassen, in Stufen von sicher nach unsicher,** und jede Stufe vergibt nur, was die vorige offenließ: gleicher Pfad (beide gesetzt) erbt die Kennung; danach inhaltliche Gleichheit; danach hinreichende Ähnlichkeit, gemessen als Anteil gemeinsamer Karten-Fingerabdrücke mit Titelgleichheit als Zuschlag, dessen Schwelle der Plan an den echten Dashboards festlegt statt sie zu raten; alles Übrige ist neu. Zwei gleich gute Kandidaten erben **keiner** — dann greift die Verweigerung, statt zu raten. Die Zuordnung ist eindeutig: Jede alte Kennung wird höchstens einmal weitergereicht, wie es Entscheidung 14 für Karten hält. Sections werden innerhalb ihrer bereits zugeordneten Ansicht nach demselben Muster verfolgt.

    **Warum eine Ähnlichkeitszuordnung hier trägt, wo sie anderswo wackelt:** Die Historie ist lückenlos. Zwischen zwei aufeinanderfolgenden Commits liegt genau ein Speichervorgang, und der berührt fast immer nur eine Ansicht. Die Zuordnung muss also nie über drei Wochen springen, sondern immer nur über einen Schritt — und sie erbt das Ergebnis des vorigen. Die zweite Stufe, schlichte Gleichheit, erledigt dabei den Großteil aller Fälle.

    **Ohne Rückwirkung, auf Entscheidung des Nutzers vom 2026-09-04.** Der bestehende Verlauf wird **nicht** nachberechnet, obwohl es möglich wäre — jeder Zwischenstand liegt als Commit vor. Der Preis ist benannt: Alles, was vor der Einführung liegt, trägt keine Kennungen und bleibt beim heutigen Verhalten samt Verweigerung. Wo keine Kennungen vorliegen oder nur eine der beiden Seiten welche trägt, gilt genau das bisherige Verfahren — ohne Fehlermeldung und ohne Hinweis, denn es ist kein Fehler, sondern der Normalfall für alten Bestand.

    **Was ausdrücklich nicht passiert: Karten bekommen keine Kennung.** Entscheidung 14 erkennt 96 % von ihnen an ihrem Inhalt wieder, und eine Kennung je Karte hieße bei 1526 Karten grob 30 KB zusätzlich je erfasstem Stand — bei heute 28 KiB je Stand eine Verdopplung, und der Platzbedarf ist in Vorhaben C ohnehin schon ein Thema. Damit bleibt der offene Punkt D5 offen: An 27 von 484 Karten ist nichts zu erkennen, und dort unterscheidet weiterhin keine Rechnung Bearbeitung von Löschung. Das Format oben schließt eine spätere Erweiterung nicht aus; entschieden wird darüber, wenn es Messwerte aus dem Betrieb gibt, nicht vorher.

    **Ein Nebenschauplatz, der leicht übersehen wird:** `forget` schreibt die Historie um. Führt es die Kennungsspur nicht mit, reißt die Kette rückwirkend — dieselbe Falle, die bei den Beschreibungen aus Entscheidung 10 bereits einmal zugeschnappt ist.


17. **Zwei Modi — und der einfache kennt nur Versionen.** *(Nachgetragen am 2026-09-04, auf Wunsch des Nutzers. Aus den GitHub-Issues 1 und 2, dort verschärft.)*

    Das Werkzeug zeigt heute Kurzhashes, Semver-Stufen und rohe YAML-Diffs. Für Entwickler ist das die Substanz, für die meisten Nutzer von Home Assistant eine Hürde vor einem einfachen Wunsch: **zu einem früheren Stand des Dashboards zurückkehren.** Wer darüber hinaus ein einzelnes gelöschtes Stück zurückholen will, wechselt in den erweiterten Modus — das bleibt möglich, ist aber nicht mehr der Normalweg. *(Seit Entscheidung 19: konkret in dessen Vergleichsmodus, nicht mehr am automatisch mitlaufenden Zeilen-Put-back.)*

    **Der einfache Modus ist keine aufgeräumte Fassung des erweiterten, sondern ein anderes Angebot.** Er zeigt Versionen, nicht Änderungen: Die einzelnen Speichervorgänge liegen eingeklappt unter der Version, zu der sie gehören, genau wie es die Abschnitte heute schon tun. Eine gezielte Rücknahme einzelner Schritte gibt es dort **nicht** — an ihrer Stelle steht der Hinweis, dass der erweiterte Modus sie kann. Zurückgesprungen wird nur auf ganze Versionen.

    **Damit hängt der einfache Modus vollständig an den Versionen, und die müssen halten.** Heute fällt eine Version aus der Oberfläche, sobald ihr Commit aus den neuesten fünfzig Änderungen rutscht (siehe »Offene Punkte«). Im erweiterten Modus ist das ärgerlich, weil die Änderungen darunter sichtbar bleiben. Im einfachen Modus wäre es der Totalausfall: ein Panel ohne einen einzigen Weg zurück, vorgeführt genau der Zielgruppe, die den Ausweg über den Moduswechsel nicht suchen würde. **Vorhaben G steht deshalb zwingend vor Vorhaben H.**

    **Versionen müssen auch ohne Zutun entstehen.** Ein Modus, der nur Versionen kennt, aber darauf wartet, dass jemand welche anlegt, hilft dem gedachten Nutzer nicht — er legt keine an. Zwei Quellen sorgen dafür, dass immer welche da sind:

    - **Bei der Einrichtung** bekommt jedes bestehende Dashboard ein `v1.0.0`. Das ist der Stand, auf den man zurückkann, bevor irgendetwas passiert ist.
    - **Beim ersten Speichervorgang eines Tages** bekommt der Stand **davor** eine Version. Das ist per Definition der letzte Stand des Vortags, und die Konstruktion ist bewusst so herum gewählt: Sie braucht keinen Zeitgeber und keinen Mitternachtslauf, sie überlebt eine Nacht, in der Home Assistant aus war, und »Tag« ist dabei der Kalendertag in der Zeitzone, die Home Assistant selbst konfiguriert hat — nicht UTC, weil ein Nutzer seinen Tag nicht in UTC erlebt, und sie erfüllt die Bedingung »nur wenn es Änderungen gibt« von selbst — ohne Speichervorgang gibt es keinen ersten, also keine Version. Ein Dashboard, das drei Wochen ruht, sammelt keine einundzwanzig leeren Marken.

    Für den Rücksprung ist das zugleich die richtige Bedeutung: »zurück auf den Stand, bevor ich heute angefangen habe«.

    **Benennung.** Technisch bleibt es ein Semver-Tag nach Entscheidung 13 — die Infrastruktur bleibt unangetastet. Der Titel trägt das Datum (»3. September 2026«) und ist als automatisch gesetzt gekennzeichnet, damit selbst gesetzte Meilensteine sich davon abheben. Der einfache Modus zeigt nur den Titel, der erweiterte beides.

    **Abschaltbar, in beiden Modi wirksam.** Die automatischen Tagesversionen entstehen unabhängig vom eingestellten Modus — sie sind Datengrundlage, nicht Anzeige, und ein Moduswechsel darf nicht ändern, was in der Historie entsteht. Wer seine Versionen selbst setzen will, schaltet sie im OptionsFlow ab.

    **Was beim Rücksprung mit dem aktuellen Stand geschieht.** Wird eine ältere Version aktiviert, fragt der Dialog, ob der jetzige Stand eine eigene Version bekommen soll. »Verwerfen« heißt dabei **nicht löschen, sondern nicht markieren**: Der Stand wird ohnehin vor jedem Schreibvorgang als Änderung festgehalten (`_keep_the_live_state`), er bleibt also in der Historie und ist im erweiterten Modus auffindbar — er bekommt nur kein Tag und ist damit im einfachen Modus nicht mehr zu sehen. Ein Sonder-Tag »verworfen« braucht es dafür nicht, und die harte Regel bleibt unberührt: Gelöscht wird nichts, Versionen markieren nur. *(Am 2026-09-08 ergänzt: `remove_version` nach Entscheidung 18 ist genau dieses »Verwerfen«, nachträglich. Es stellt denselben Zustand her, den man gehabt hätte — der Stand bleibt, die Marke geht —, und die harte Regel bleibt aus demselben Grund unberührt. Das ist die tragende Rechtfertigung des Aufhebens und kein Nebenbefund: Was hier als Wahl im Dialog steht, ist dieselbe Sache, die dort als Bedienung an einer Zeile steht.)* Die ganze Last trägt die Formulierung im Dialog — sie muss sagen, dass der Stand erhalten bleibt, ohne dem einfachen Modus eine Erklärung über Modi aufzubürden.

    **Eine Folge, die Vorhaben C mitträgt.** Versionen sind dort die Schutzmarke: Was ein Tag trägt, wird beim Aufräumen nie angetastet. Automatische Tagesversionen machen damit jeden Tagesendstand unantastbar. Das ist vermutlich genau richtig — Tagesstände behalten, Zwischenstände verdichten —, aber es ist eine Entscheidung, die in Vorhaben C bewusst stehen muss, statt sich dort unbemerkt zu ergeben. *(Am 2026-09-08 ergänzt: Entscheidung 18 gibt der Sache eine Rückseite. Eine **aufgehobene** Version gibt ihren Stand für das Verdichten frei. Damit ist das Aufheben der einzige Weg, auf dem eine Bedienung im Panel überhaupt Einfluss darauf nimmt, was Vorhaben C anfassen darf — und in C ist das auszusprechen, in beide Richtungen: Wer eine Tagesmarke aufhebt, weil er sie nicht braucht, macht ihren Stand antastbar; wer eine setzt, macht ihn unantastbar.)*

    **Was der einfache Modus nicht ist:** eine Einschränkung der Rechte. Beide Modi können dasselbe schreiben; der einfache bietet nur weniger davon an. Und er ist eine Einstellung der Oberfläche, keine der Erfassung — bis auf die eine Ausnahme oben, und die gilt deshalb für beide.


18. **Eine Version lässt sich aufheben — die Marke, nicht der Stand.** *(Nachgetragen am 2026-09-08, auf Wunsch des Nutzers.)*

    Die Frage kam in drei Teilen, und die Antwort hängt daran, dass es **drei verschiedene Fragen** sind. Sie auseinanderzuhalten ist der Ertrag dieser Entscheidung; zusammengelegt hätten sie ein Vorhaben ergeben, das drei Probleme halb löst.

    **Erstens, die Größe des Repositorys: dafür nicht.** Gemessen am 2026-09-08 mit dulwich 1.2.14: Eine **Version** kostet rund **202 Bytes** — Tag-Objekt und Ref-Datei zusammen, bei Titel und zweizeiliger Beschreibung. Hundert Versionen sind 20 KiB.

    Daneben, damit die Zahl eine Größe hat: Im selben Wegwerf-Repository, an einer 22 KiB großen Dashboarddatei mit einer Zeile Unterschied je Speichervorgang, kostete ein **Stand** rund 2500 Bytes — die Stände sind sich fast gleich, und zlib komprimiert jeden davon einzeln. An der echten Anlage sind es 28 KiB je Stand bei 262 KiB Dashboardgröße (Vorhaben C, 2026-09-02). Die zwei Zahlen widersprechen sich nicht, sie messen verschiedene Dashboards; für diese Entscheidung zählt nur das **Verhältnis**, und es liegt zwischen 1:12 und 1:140. Wer das Repository über die Versionen aufräumen will, schraubt die Kennzeichenhalterung ab, um Platz im Kofferraum zu schaffen. Für die Größe bleiben Vorhaben B und C zuständig, in der Reihenfolge, die dort begründet ist.

    **Zweitens, »das will ich nie wiedersehen«: doppeldeutig, und an der Doppeldeutigkeit hängt der ganze Aufwand.** Soll die *Zeile* aus der Liste — dann genügt die Marke, und der Stand bleibt im erweiterten Modus auffindbar. Soll der *Inhalt* aus dem Repository — dann ist es eine Umschreibung der Historie, dieselbe Klasse wie `forget`, samt dessen offenen Punkten. **Entschieden ist gestaffelt:** die Marke jetzt, der Inhalt bleibt Vorhaben C. Das ist ausdrücklich keine Vertagung aus Aufwandsgründen, sondern die Weigerung, eine zweite unwiderrufliche Operation zu bauen, bevor irgendwer Messwerte hat — dasselbe Argument, das am 2026-09-02 die Reihenfolge B vor C erzwungen hat.

    **Drittens, der Fall, der es ausgelöst hat.** Am 2026-09-08 waren auf dem Prüf-Dashboard `dh-probe` versehentlich inhaltlich identische Versionen entstanden. Das Entstehen ist inzwischen weitgehend verhindert; die Versionen blieben, und es gab keinen Weg, sie loszuwerden. Das ist ein reines Marken-Problem: Der Inhalt darunter ist nicht peinlich, er ist bloß mehrfach benannt. Der Code sagt die Lücke an zwei Stellen selbst — »nothing in this integration can delete a version again« in `const.py` und »a version, unlike a description, has nothing that deletes it again« in `store.py`. Beides sind Kommentare, die eine Auslassung *entschuldigen*, statt eine Entscheidung zu begründen. In diesem Repository ist das ein Befund.

    **Die tragende Rechtfertigung steht bereits in Entscheidung 17:** »Verwerfen heißt nicht löschen, sondern nicht markieren.« Ein Rücksprung, bei dem man »verwerfen« wählt, lässt den Stand in der Historie und gibt ihm nur kein Tag. `remove_version` stellt genau diesen Zustand nachträglich her. Es ist damit keine neue Eigenschaft des Werkzeugs, sondern eine bestehende, die bisher nur zu einem einzigen Zeitpunkt erreichbar war — im Dialog, in der Sekunde der Entscheidung.

    **Der Name ist `remove_version`, nicht `delete_version`.** Das Zweite versprach den Inhalt mit, und den nimmt diese Operation ausdrücklich nicht.

    **Sechs Festlegungen, jede mit ihrem Grund:**

    1. **Nur die Ref.** `del refs/tags/<name>`, sonst nichts: keine Umschreibung, kein `garbage_collect`, keine Revision ändert sich, keine Notiz wird angefasst. Das alte Tag-Objekt bleibt als loses Objekt liegen — dieselbe Abwägung, die das Umbenennen schon getroffen hat: ein Durchlauf des Objektspeichers je Bedienung wäre teurer als 200 Bytes, und `forget`s `garbage_collect` holt sie ohnehin.
    2. **`_owns` ist der Zaun.** Ohne ihn nimmt ein Befehl mit bloßem Ref-Namen jedes Tag im Repository weg. Der Zaun kennt Schlüssel mit Schrägstrich; das ist am 2026-09-04 gemessen worden, als `forget("foo")` das Tag von `foo/bar` mitnahm.
    3. **Nummern werden wiederverwendet.** `versions.py` bleibt unverändert — kein neues Stück Zustand im Repository. Die Folge steht bei Entscheidung 13.
    4. **Automatische Tagesmarken sind aufhebbar, und eine kann zurückkommen.** Betrifft sie den Tag, den der nächste Speichervorgang abschließen würde, macht die Automatik sie neu — sie tut dann, was sie verspricht, denn der Tag trägt tatsächlich keine Marke. Das wird **ausgesprochen und nicht verhindert**: Ein Grabstein je Tag wäre ein weiteres Stück Zustand, das `forget` mitschreiben muss, für ein Fenster von höchstens einem Tag. Wer keine Tagesmarken will, hat den Schalter im Options-Flow, und der ist der richtige Ort.

        **Am 2026-09-09 präzisiert, weil der Dialog es falsch sagte.** »Betrifft sie den Tag, den der nächste Speichervorgang abschließen würde« ist die Bedingung — und der Panel-Text hatte sie zu einer Behauptung gemacht: *jede* automatische Version bekam den Satz, sie werde beim nächsten Speichern neu angelegt. Am `dh-probe` aufgefallen, an einer Marke vom 7. September, hinter der sieben Stände vom 8. September liegen: Sie kommt **nie** zurück.

        **Die Bedingung wird nicht nachgebildet, sondern ausgeführt.** Das ist der eigentliche Ertrag, und er kostete zwei Anläufe. Der erste formulierte die Regel neu — »kommt zurück, solange kein Stand auf einem späteren Kalendertag liegt« — und war im **häufigsten Fall falsch**: Die Marke für *gestern* entsteht beim ersten Speichern *heute*, es liegen also längst Stände von heute dahinter, und der Satz sagte »dauerhaft«, während das nächste Speichern sie zurückbringt. Der Beweis lag seit Monaten in der eigenen Testreihe (`test_a_burst_of_saves_does_not_hide_the_day_before`): Weitere Stände am heutigen Tag schieben das Fenster **nicht** über den Vortag hinaus.

        Also führt `versions.would_be_marked_again` die Regel aus, statt über sie zu reden: einen Speichervorgang zum Zeitpunkt *jetzt* vorn ans Fenster setzen, das Fenster auf `RECENT_STATES` kürzen, `end_of_previous_day` fragen — dieselbe Funktion, die auch markiert — und prüfen, ob die gefundene Revision die aufgehobene ist. **Eine Vorhersage, die eine Regel nachrechnet, kann sich über sie irren; eine, die sie laufen lässt, nicht.** Dasselbe Prinzip wie »ein Bauplan, zwei Leser« bei `_version_from`.

        Drei Dinge fallen damit von selbst richtig aus, die eine Nachbildung einzeln hätte treffen müssen: das `RECENT_STATES`-Fenster (ist der Tag herausgefallen, verweigert `end_of_previous_day` dort wie hier), ein Tag mit mehreren Ständen (markiert wird sein *letzter*, eine Marke auf einem früheren ist also nicht die, die entstünde), und ein Tag, der *heute* ist (nichts abzuschließen, keine Marke). Deshalb liegt das Fenster jetzt in `versions.py` bei der Regel, die es begrenzt, und `milestones.py` liest es von dort — eine Vorhersage mit anderer Fenstergröße widerspräche der Regel genau am Rand.

        Die Rechnung liegt in `versions.py`, Home-Assistant-frei, aus demselben Grund wie `day_is_marked` daneben: ein Kalendervergleich, der still falsch sein kann, gehört dorthin, wo `pytest` hinkommt — und im zweiten Anlauf war es genau eine vierzeilige pytest-Prüfung, die den Fehler festnagelt.

        **Was von der Stabilität bleibt, in eine Richtung:** *Falsch* ist dauerhaft — heute rückt nur vor, ein zurückgefallener Tag kann nicht wieder der werden, den ein Speichern abschließt. *Wahr* ist eine Aussage über jetzt und verfällt zur nächsten Mitternacht. Deshalb spricht der Dialog vom **nächsten Speichern** und nicht von irgendeinem Tag.

        **Was sie nicht beantwortet, benannt statt verschwiegen:** `_async_mark_day` hat drei Verweigerungen, und dies ist die kalendarische. Trägt der Tag noch eine zweite automatische Marke, oder hält die höchste Version genau den Stand, der markiert würde, entsteht auch dann keine neue. Die Antwort **überwarnt** also im Randfall — sie sagt »kommt zurück«, wo es doch nicht geschieht. Das ist die richtige Richtung für einen Bestätigungsdialog: zu viel Warnung ist ärgerlich, zu wenig ist eine Falle.
    5. **`confirm` ist verlangt, und die Vorschau zeigt Worte statt Zahlen.** Ohne `confirm` antwortet der Vorgang mit Name, Titel, Beschreibung, Revision, ob die Version automatisch entstand, ob sie die höchste Nummer trägt und — seit dem 2026-09-09 — ob sie als Tagesmarke zurückkäme (`returns`, siehe Festlegung 4). Der letzte Punkt ist der nützlichste Satz im Dialog — er beantwortet den Fall, der die Sache ausgelöst hat: die Nummer kommt frei. Kein Diff, denn es ändert sich kein Dashboard. Warum `confirm` trotzdem: siehe die zweite Seite von Entscheidung 7.
    6. **Ein handgemachter leichtgewichtiger Tag im Namensraum lässt sich aufheben** — anders als umbenennen. Beim Umbenennen war der Grund ein besonderer: Ein Tag mit Botschaft zurückzugeben, wo jemand einen ohne gesetzt hat, heißt eine andere Art Tag zurückzugeben. Beim Aufheben gibt es nichts zurückzugeben, der Grund überträgt sich also nicht. Dagegen überträgt sich der andere: Dieses Dokument hält bei Entscheidung 12 fest, wie das Übergehen leichtgewichtiger Tags `forget` **still wirkungslos** machte. Und es käme eine zweite Folge hinzu — ein von Hand gesetztes `heizung/v1.0.0` zählt beim Hochzählen mit und würde als Unaufhebbares eine Nummer für immer belegen, während Festlegung 3 gerade sagt, dass Nummern zurückkommen.

    **Zwei Wege mit verschiedenen Kosten, und das ist Absicht.** Die Vorschau darf sich umsehen — einmal die Versionen des Dashboards auflisten, um »trägt die höchste Nummer« zu beantworten; ein Dialog, der sich öffnet, hat 35 ms. Das Aufheben selbst liest nur die eine Ref. Der Einwand, der das Umbenennen von der Auflistung weggeführt hat, galt dem Herumschauen **um einen Schreibvorgang**, nicht dem Herumschauen an sich. Das gehört in den Docstring, sonst räumt es jemand später »auf«.

    **Was Entscheidung 18 nicht ist:** ein Weg, Stände loszuwerden. Wer das sucht, findet es in Vorhaben C oder in `forget` — und `forget` bleibt die **einzige** Operation, die einen Stand wegnimmt.

19. **Das zeilenweise Put-back verschwindet — ein bewusster Vergleichsmodus tritt an seine Stelle.** *(Nachgetragen am 2026-09-12, auf Wunsch des Nutzers. Am 2026-09-12 nach einem unabhängigen Review einer Parallel-Session an drei Stellen nachgeschärft — Fundstellen 1–4 unten sind dessen Handschrift, nicht nachträglich verwischt.)*

    Seit Entscheidung 15 zeigt jede Zeile mit Vorgänger, was zwischen ihrem Vorgänger-Stand und dem **heutigen** Live-Zustand verschwunden und noch nicht zurückgeholt ist — unabhängig davon, welche der dazwischenliegenden Änderungen es tatsächlich entfernt hat. Am Dashboard »Standard« beobachtet: Eine einzelne, alte Zeile zeigte zwölf einzelne Put-back-Knöpfe für Karten, die zwölf verschiedene, spätere Änderungen entfernt hatten.

    **Der Mechanismus, nicht die Messung, trägt die Entscheidung.** Home Assistants Lovelace-Editor speichert jede Entfernung im gewöhnlichen Bedienfluss sofort einzeln — mehrere Karten verschwinden nur dann in *einem* Speichervorgang, wenn jemand roh am YAML arbeitet oder wenn diese Integration selbst einen ganzen Stand über `restore_state` zurückschreibt (dort kann ein einziger Commit beliebig viele Karten wegnehmen). Innerhalb einer gewöhnlichen Bedienung ist eine einzelne Änderung damit fast immer eine einzelne Karte, und der Vorteil, mehrere in einer Änderung entfernte Karten einzeln auswählen zu können, entsprechend selten gefragt. **Die Messung bestätigt das, sie begründet es nicht:** An der kompletten Historie aller elf realen Dashboards der Testanlage kommt ein Speichervorgang mit zwei oder mehr entfernten Karten in zehn davon kein einziges Mal vor; im elften (`allgemein-strom`) sind es fünf von rund dreihundert Löschungs-Commits, und in allen fünf steht dieselbe schwache Karte (`tile: Dieser Monat`, ohne Entity oder Titel) neben einer jeweils anderen — eher eine Umgestaltung dieser einen Ansicht als eine bewusst gleichzeitige Doppel-Löschung.

    **Das ist aber nicht der einzige Zweck des heutigen Put-back-Blocks, und der zweite bleibt.** Entscheidung 15 macht ihn zur *Rückfallseite einer Weiche*: »Eine Zeile bietet einen Weg zurück: den Undo, wenn er exakt ist, sonst die Put-back-Liste.« Der Undo verweigert in mehreren real gebauten Fällen strukturell, nicht nur gelegentlich — am klarsten bei einer gelöschten Section, die keinen Pfad zur Wiedererkennung trägt (README, »Deleting a whole section comes back through Put back … Undo this change declines either way«). Dort ist der Put-back-Block heute die *einzige* Alternative, die Entscheidung 5 verspricht (»geht nicht, weil …, hier sind die Alternativen«). Ihn ersatzlos zu streichen ließe an genau diesen Zeilen nur noch die nackte Verweigerung stehen — ein Rückschritt hinter Entscheidung 5, nicht bloß der Wegfall einer selten genutzten Funktion.

    **Entschieden, mit dieser Ergänzung:** Das zeilenweise Aufklappen (`_renderDetail` in `panel.js`) verliert den `deleted_since`-Block als *automatisch mitlaufende Anzeige* — keine Überschrift, keine Zeile je fehlender Karte, kein Knopf, der einfach unter der Erklärung erscheint. Verweigert der Undo einer Zeile, nennt die Verweigerung ab sofort nicht nur den Grund, sondern bietet einen Weg zum Vergleichsmodus an, vorbelegt mit dem Vorgänger-Stand dieser Zeile und »Aktueller Zustand« — derselbe Put-back also, nur hinter einem Klick statt automatisch sichtbar. Übrig bleibt im Aufklappen selbst: Erklärung, technischer Diff, »Undo this change« (mit der Verweigerung samt diesem Verweis, wenn es nicht anders geht), »Set Back« und Versionsknöpfe.

    **Der Mechanismus selbst wird nicht verworfen, nur umgehängt.** `deleted_since` und `restore_deleted` bleiben unverändert bestehen und bekommen einen neuen, bewussten Einstieg: einen **Vergleichsmodus**, ausschließlich im erweiterten Modus — der einfache Modus aus Entscheidung 17 zeigt ohnehin keine einzelnen Änderungen, nur Versionen, und die gezielte Einzelrücknahme bleibt dort weiterhin ausgeschlossen. Aktiviert, bekommt jede Zeile der Historie — jede Änderung, jede benannte Version — eine Checkbox, dazu ein zusätzlicher, fest oben stehender Eintrag »Aktueller Zustand«, getrennt von der jeweils neuesten Zeile (dieselbe Unterscheidung wie in Entscheidung 9: die neueste Zeile *ist* nicht zwangsläufig der aktuelle Zustand). Zwei ausgewählt, öffnet sich ein Dialog mit dem vollständigen Unterschied zwischen genau diesen beiden, beliebig weit auseinanderliegenden Ständen — nicht nur Löschungen, sondern alles, was `explain_change` unterscheidet. Ist eine der beiden Seiten »Aktueller Zustand«, kommt zusätzlich die Put-back-Liste dazu, mit denselben, unveränderten Aufrufen wie heute. Sind beide Seiten historisch, bleibt der Dialog rein informativ — Put-back schreibt weiterhin ausschließlich in den lebenden Zustand, nie in einen anderen historischen Stand.

    **Eine Zeilen-Checkbox meint den Stand danach — dieselbe Revision, die der Rest des Werkzeugs schon überall meint.** Nicht den Stand davor: Eine Revision *ist* im ganzen Projekt der Stand nach der Änderung, die sie erzeugt hat (`restore_state`, `create_version`, jede Adressierung). Wer sehen will, was eine bestimmte Löschung seither hat verschwinden lassen, kreuzt bewusst die *vorherige* Zeile an, nicht die Löschzeile selbst — die Löschzeile enthält das Gelöschte bereits nicht mehr, ein Vergleich mit ihr als einer Seite fände es also nicht. Genau die Stolperstelle, die Entscheidung 9 für den Ganz-Zurück-Fall entfernt hat (»eine zu spät«), kehrt hier sonst zurück. Der Dialog nennt deshalb zu jeder Seite explizit Datum und die automatische Meldung des gewählten Standes (»Stand nach ›2 removed‹ vom …«), damit nie erraten werden muss, welche der beiden Zeilen tatsächlich gewählt wurde.

    **»Aktueller Zustand« ist keine Revision, und das bleibt beim Aufruf sichtbar.** `_explain_texts` (in `operations.py`) ist bereits vollständig revisionsunabhängig — es kennt nur zwei YAML-Texte, keine Vorgänger-Beziehung. Für eine echte Revision liefert `store.read_at` diesen Text unverändert wie heute; für »Aktueller Zustand« gibt es keinen Commit, nur das Dict aus `async_get_config`, das wie in `_preview` erst über `dump()` zu Text wird. Die neue, dünne `async_compare`-Operation nimmt deshalb zwei *optionale* Revisionen entgegen, nicht zwei Pflicht-Revisionen — fehlt eine Seite, ist damit ausdrücklich der Live-Zustand gemeint, nicht ein drittes, verstecktes Sonderformat.

    Diese Entscheidung deckt ausschließlich den Vergleich zweier Stände ab.

    **Umgesetzt.** *(Nachgetragen am 2026-09-17 — bis dahin stand hier »steht noch aus«, was seit der Umsetzung von Vorhaben J falsch war und beim Review dieses Datums auffiel.)* `async_compare` steht in `operations.py`, der WebSocket-Befehl in `websocket_api.py`, der Auswahl-Zustand als `_compareMode`/`_compareSelection` in `panel.js`; der Plan dazu ist `plans/2026-09-12-vergleichsmodus.md`. Der zeilenweise Put-back-Block ist aus `_renderDetail` verschwunden, wie dieser Absatz es verlangt.

20. **Das Panel wird schmal bedienbar — gemessen an sich selbst, nicht am Fenster.** *(Nachgetragen am 2026-09-17, auf Wunsch des Nutzers. Anlass war ein Screenshot vom Handy, kein Review.)*

    **Der Befund, in den Worten dessen, der es versucht hat:** »Am Handy ist es nahezu unbedienbar.« Drei Beobachtungen, und jede hat eine Ursache im Code, keine im Geschmack:

    1. **Das echte Home-Assistant-Menü ist nicht mehr erreichbar.** Home Assistant blendet unterhalb von 870 px seine Seitenleiste aus und **erwartet, dass die Seite selbst den Hamburger stellt** — jede eingebaute HA-Seite tut das. Dieses Panel hat einen eigenen Balken gebaut und keinen hineingestellt. Wer es auf dem Handy öffnet, kommt ohne Zurück-Geste des Browsers nicht mehr heraus.
    2. **Die Dashboard-Liste bleibt gleich breit.** `.side` steht auf `flex: 0 0 280px` — »nie schrumpfen«. In einem Flex-Container gewinnt das gegen den Viewport: nicht die Spalte wird kürzer, der Container wird breiter als das Fenster.
    3. **Der Inhalt wird sehr schmal.** Folge von 2, plus eine zweite, unabhängige Ursache: `.search` ist eine Flex-Zeile **ohne** `flex-wrap` und trägt im erweiterten Modus bis zu vier Dinge nebeneinander — Suchfeld, »Compare mode«, Ergebnis-Notiz, »Search the whole history«.

    **Was Home Assistant dafür vorsieht, am 2026-09-17 im Frontend-Bündel der Testinstanz (2026.8.3) nachgelesen, nicht vermutet:** `ha-panel-custom` setzt auf dem Custom-Element die Properties `panel`, `hass`, `narrow` und `route` und hält sie über dieselbe Funktion aktuell. `narrow` hängt an der Media-Query `(max-width: 870px)`. Der Hamburger ist kein Import, sondern ein Ereignis: `ha-menu-button` feuert `hass-toggle-menu`, und `home-assistant-main` hört darauf an sich selbst. Die Sichtbarkeitsregel dieses Knopfes lautet dort, wörtlich übersetzt: zeigen, wenn `narrow || dockedSidebar === "always_hidden"` (und kein Kiosk-Modus). **Das Panel liest heute nur `hass`** — `narrow` kommt an und fällt auf den Boden.

    **Festlegung 1: Der Hamburger ist ein eigener Knopf, der das Ereignis feuert.** Nicht `<ha-menu-button>`. Zwei Gründe: Das Panel benutzt bewusst keine Home-Assistant-Komponenten, sondern reines Shadow-DOM — und `ha-menu-button` liegt in einem nachgeladenen Frontend-Bündel, dessen Verfügbarkeit auf einer Custom-Panel-Seite nichts zusichert. Ein `CustomEvent("hass-toggle-menu", { bubbles: true, composed: true })` hängt von keinem Bündel ab. Die Sichtbarkeitsregel wird von Home Assistant übernommen, nicht neu erfunden.

    **Festlegung 2: Gemessen wird die Breite des Panels, nicht die des Fensters.** Das sind zwei verschiedene Fragen, die versehentlich zu einer werden: »Ist Home Assistants Seitenleiste versteckt?« entscheidet über den Hamburger und wird von `narrow` beantwortet. »Wieviel Platz habe ich?« entscheidet über die Zahl der Spalten — und darauf antwortet `narrow` falsch. Bei 900 px Fensterbreite ist `narrow` unwahr, Home Assistant dockt seine 256 px breite Leiste an, und das Panel hat real rund 640 px. Eine Media-Query im Panel misst trotzdem das Fenster und sagt »breit«. Deshalb `container-type: inline-size` auf dem Host und `@container`-Bänder darauf: eine feste Spalte, solange reichlich Platz ist, darunter eine mitwandernde, und ganz unten eine Spalte. **Die Schwellenwerte selbst stehen bewusst nicht in dieser Entscheidung**, sondern im Plan — sie werden an Aufnahmen festgezurrt, nicht am Schreibtisch gewählt, und ihre Zahlen tragen keine Aussage, die hier zu begründen wäre. Die Höhe bleibt davon unberührt: Containment auf der Inline-Achse ändert nichts daran, dass der Host sich an seinem Inhalt misst — eine Eigenschaft, auf die dieses Stylesheet an mehreren Stellen ausdrücklich baut.

    **Die Richtung des Rückfalls ist Teil der Festlegung.** Das Basis-CSS bleibt die heutige Zweispaltigkeit; die Container-Queries verengen sie nur. Ein Browser, der `@container` nicht kennt, bekommt damit genau das, was er heute bekommt — kein Rückschritt, nur kein Fortschritt. Die umgekehrte Anordnung (einspaltig als Basis, zweispaltig per Query) hätte denselben Browser auf ein Handy-Layout am Desktop festgenagelt.

    **Festlegung 3: Unterhalb des schmalen Bandes eine Spalte, Master/Detail.** Entweder die Dashboard-Liste oder der Verlauf, nie beides, mit einem »‹« im Balken zurück zur Liste. Das ist wörtlich, was Home Assistant in `/config` tut — die Geste sitzt bei jedem HA-Nutzer schon. **Zwei naheliegende Alternativen sind verworfen, und der Grund liegt an den Daten, nicht am Geschmack:**

    - *Die Liste als Schublade über dem Inhalt* hätte den Vorteil, dass ein Dashboard-Wechsel von überall ein einziger Tipper bleibt. Sie scheitert am Balken: links stünde dann der HA-Hamburger und direkt daneben ein zweiter, fast gleich aussehender Knopf für eine zweite Schublade, die etwas anderes öffnet. Dazu ist beim ersten Betreten noch nichts gewählt, die Hauptspalte also leer, und der einzige Weg weiter versteckt sich hinter einem der beiden Knöpfe.
    - *Die Auswahl als Aufklappmenü im Balken* scheitert daran, dass die Seitenspalte keine Liste ist, sondern drei: die Dashboards der Seitenleiste, dann die Klappabschnitte »Not in the sidebar« und »Deleted«. An der Anlage, an der der Befund entstand, sind das 12 + 33 + 29 = 74 Einträge mit Zuständen. Ein natives Auswahlmenü trägt das nicht.

    **Das Panel ist ein Leseinstrument, und daran entscheidet sich die Wahl.** Man kommt an, weil ein bestimmtes Dashboard sich geändert hat, bleibt dort und geht wieder. Die Schublade wäre für Vielwechsler besser, Master/Detail ist für Leser besser — und für die ist es gebaut.

    **Festlegung 4: CSS entscheidet, JavaScript zeichnet beides.** Der schmale Zustand ist ein Feld `_pane` (`"list"` | `"detail"`), das als Attribut am Layout landet; welche Spalte verschwindet, sagt eine `@container`-Regel. JavaScript erfährt nie, wie breit es ist. Der Grund ist nicht Eleganz, sondern eine gemessene Eigenschaft dieses Panels: `_render()` ersetzt den **kompletten** Shadow-Root und muss Scrollposition im Diff und Fokus im Suchfeld eigens wieder zurücksetzen. Ein `ResizeObserver`, der ein `_wide` setzt, würde das beim Drehen des Handys und bei jedem Ziehen am Fensterrand auslösen — Dauerfeuer auf genau den Pfad, der am teuersten und am empfindlichsten ist. Der Weg über CSS kostet null Renders.

    **`_pane` fasst die Auswahl nicht an, und die Übergänge sind abschließend festgelegt.** *(Dieser Absatz ist am 2026-09-17 nach einem Review erweitert worden: Die erste Fassung nannte nur die beiden Zustände und versprach die sofortige Rückkehr — den Anfangszustand und das Zusammenspiel mit der Auswahl ließ sie offen, und das Versprechen war mit dem heutigen `_select` nicht einlösbar.)*

    Eine Regel trägt alle Fälle: **`_pane` wird `"detail"` ausschließlich durch das bewusste Antippen einer Dashboard-Zeile.** Jeder andere Weg, auf dem `_selected` einen Wert bekommt, lässt es auf `"list"`. Daraus folgt für die drei Stellen, an denen das heute geschieht:

    - **Anfangszustand: die Liste, obwohl bereits ein Dashboard gewählt ist.** `_loadDashboards()` wählt von sich aus die erste lebende Zeile. Am breiten Schirm ist das richtig — man sieht Liste *und* einen Verlauf statt einer leeren Spalte. Am schmalen wäre es falsch: Der Blick landete in einem Dashboard, das niemand gewählt hat, und die Liste, die die eigentliche Antwort auf »wo bin ich« ist, wäre unsichtbar. Die Vorauswahl bleibt trotzdem bestehen und ist kein verschwendeter Abruf, sondern die Voraussetzung dafür, dass der erste Tipper auf genau diese Zeile ohne Warten öffnet.
    - **Rückkehr zum bereits gewählten Dashboard darf nicht durch `_select` laufen.** `_select(key)` räumt heute bedingungslos auf — Suchwort, Vergleichsmodus und -auswahl, offene Zeile, Detail-Zwischenspeicher, geladene Versionen — und fragt Verlauf und Versionen neu ab, auch wenn `key` bereits `_selected` ist. Über diesen Weg wäre »zurück, dann wieder hinein« kein Umschalten, sondern ein Neustart, und die zugesagte sofortige Rückkehr eine Unwahrheit. Ein Tipper auf die **bereits gewählte** Zeile setzt deshalb nur `_pane` und zeichnet neu; `_select` läuft nur noch für einen echten Wechsel. **Das ändert auch das Verhalten am breiten Schirm**, und zwar bewusst: Ein Klick auf die schon markierte Zeile lädt dort heute alles neu und verwirft dabei ein eingetipptes Suchwort. Künftig tut er nichts. Neu laden bleibt der Knopf, der genau so heißt.
    - **Nach dem Vergessen des gewählten Dashboards: zurück auf die Liste.** `_forget` setzt `_selected` auf `null` und ruft `_loadDashboards()`, das wieder von sich aus die erste Zeile wählt. Am schmalen Schirm stünde man danach ohne eigenes Zutun im Verlauf eines *anderen* Dashboards — mit einem Titel im Balken, der stimmt, und einem Inhalt, den niemand angefordert hat. Das ist genau die Sorte Bildschirm, die richtig aussieht und es nicht ist, vor der Entscheidung 13 an anderer Stelle warnt. Die Regel oben deckt den Fall bereits ab, weil diese Auswahl nicht aus einem Tipper stammt; er steht hier trotzdem namentlich, damit er beim Bauen nicht übersehen wird.

    **Der Wechsel breit ⇄ schmal wirft nichts weg.** `_pane` wird ausschließlich von CSS gelesen; wer ein Fenster aufzieht, sieht wieder beide Spalten, und wer es zusammenschiebt, landet in dem Zustand, den sein letzter Tipper gesetzt hat. Suchwort, Vergleichsauswahl und offene Zeile hängen an keinem der beiden Wege und überleben den Wechsel deshalb von selbst — das ist die zweite Zusage aus Festlegung 4 und zugleich ihr Prüfstein.

    **Festlegung 5: Der Balken darf umbrechen, statt Inhalte zu verlieren.** Im schmalen Band steht in der ersten Zeile `☰ ‹ Titel ⟳` und in der zweiten der Simple/Advanced-Schalter. Die Alternative wäre gewesen, den Schalter für schmale Schirme wegzulassen oder ihn in die Inhaltsspalte zu verschieben; das Erste nimmt dem Handy einen der beiden Modi, das Zweite verlangt entweder doppeltes Markup mit kollidierenden Radio-Namen oder ein Messen in JavaScript, das Festlegung 4 gerade vermeidet. **Damit fällt die feste `height: 56px` des Balkens** und mit ihr `.layout { height: calc(100% - 56px) }`. Die Zeile ist ohnehin schon wirkungslos — der lange Kommentar direkt darunter sagt, warum: Der Host misst sich an seinem Inhalt, nicht am Fenster, und keine der beiden Spalten hält je mehr, als hineinpasst. Ersetzt wird sie durch eine Flex-Spalte auf dem Host. Das ist eine Aufräumarbeit, aber keine beiläufige: Ohne sie ist ein umbrechender Balken nicht sicher zu haben.

    **Festlegung 6: Die Suchzeile bricht um, und das Feld gibt nach.** *(Am 2026-09-17 nach einem Review ergänzt: Der Befund oben nennt `.search` als eigenständige, von der Seitenspalte unabhängige Ursache — und keine der ursprünglichen Festlegungen hat sie behoben. Master/Detail verbreitert die Inhaltsspalte, es ändert aber nichts daran, dass vier nebeneinander gesetzte Elemente ohne `flex-wrap` mehr Platz verlangen, als eine Zeile hat.)* `.search` bekommt `flex-wrap: wrap`; im schmalen Band nimmt das Suchfeld eine eigene Zeile und gibt seine Deckelung auf 420 px auf. Die Deckelung bleibt oberhalb bestehen: Sie existiert laut Kommentar, damit einfacher und erweiterter Modus dieselbe Zeilenform haben, und dieser Grund verschwindet, sobald ohnehin jedes Element eine eigene Zeile bekommt.

    **Das Abnahmekriterium dazu ist hart und gilt für beide Modi:** Bei 360 px sind **alle** Suchbedienelemente erreichbar — Feld, »Compare mode«, die Ergebnis-Notiz und »Search the whole history«. Der erweiterte Modus ist der Prüffall, weil nur dort alle vier zugleich auftreten können.

    *(Am 2026-09-17 nachgeschärft, nachdem die erste Fassung »ohne waagerechtes Scrollen der Seite« sagte und damit zu wenig verlangte.* **»Erreichbar« ist nicht dasselbe wie »die Seite scrollt nicht«.** `.main` trägt `overflow-y: auto`, und CSS hebt die waagerechte Achse mit auf `auto` — zu breiter Inhalt scrollt dann in der Spalte und erreicht das Dokument nie. Bei 390 px im erweiterten Modus gemessen: Die Seite scrollte **nicht**, und trotzdem stand `.main` 179 px breit um 440 px Inhalt, mit fünf Elementen jenseits der rechten Kante. Das Kriterium ist deshalb, dass die Inhaltsspalte selbst nichts abschneidet — `scrollWidth` gleich `clientWidth` — und nicht, dass das Dokument stillhält. Gemessen wird es an **einer** Spalte: Mit zweien bleiben bei 360 px rund 149 px übrig, und dort passt keine Suchzeile hinein, gleich wie sie umbricht.*)

    **Festlegung 7: Tippziele wachsen nach Berührung, nicht nach Breite.** Der Reload-Knopf ist heute rechnerisch knapp 30 px hoch (`line-height: 1.2` auf `font-size: 18px`, dazu 6 px Polsterung und 2 px Rahmen) — etwa zwei Drittel eines brauchbaren Ziels. Er und die Klapp-Zusammenfassungen der Seitenspalte wachsen im bereits vorhandenen `@media (hover: none)`-Block, nicht im `@container`-Band. Ein Handy im Querformat ist breit und trotzdem ein Finger; ein schmales Browserfenster am Desktop ist schmal und trotzdem eine Maus. Die Breite ist hier das falsche Merkmal.

    **Was diese Entscheidung nicht ist:** eine zweite, eigene Handy-Oberfläche. Es gibt eine Oberfläche, die von rund 360 bis 2560 px durchgehend funktioniert, und keinen »Mobil-Modus«. Weder kommt etwas auf schmalen Schirmen hinzu, noch fällt etwas weg: Was am Desktop geht, geht am Handy — dieselben Zeilen, dieselben Dialoge, derselbe Vergleichsmodus. Die Dialoge sind dafür bereits auf die Fensterbreite gedeckelt — `min(900px, 92vw)` für alle, `min(640px, 92vw)` für die beiden, die der Redesign geformt hat —, und der Vergleichsmodus zeigt einspaltige Prosa mit einem Diff darunter, kein zweispaltiges Raster. Der einzige Rest, der breit bleiben **darf**, ist der technische Diff im Monospace — er ist ohnehin der einzige echte innere Scrollbereich dieses Panels.

    **Wie es belegt wird.** *(Am 2026-09-17 nach einem Review erweitert: Die erste Fassung verlangte Aufnahmen und eine Handprüfung von Menü und Tippverhalten. Aufnahmen belegen Zustände, nicht Übergänge — und gerade die Übergänge sind an Master/Detail das Neue.)* Weder `pytest` noch `run_checks.py` sehen ein Layout.

    **Aufnahmen** über `tools/capture_demo_screenshots.py`, das die Fenstermaße bereits über CDP setzt (`Emulation.setDeviceMetricsOverride`) und dieselbe Stelle auch mit 390 × 844 bedient: Liste und Verlauf, hell und dunkel. Dazu ausdrücklich **eine Aufnahme bei 900 px mit angedockter HA-Seitenleiste** — genau der Fall, den eine Media-Query falsch beantwortet hätte und an dem Festlegung 2 steht oder fällt.

    **Übergänge, von Hand in der Wegwerf-Instanz, jeder einzeln benannt**, weil kein Bild sie zeigt:

    1. Liste → Detail → Liste → **dasselbe** Dashboard erneut. Verlauf steht sofort, kein erneuter Abruf, kein Flackern (Festlegung 4, zweiter Spiegelstrich).
    2. Breit ⇄ schmal ziehen, während ein **Suchwort** eingetippt und eine **Vergleichsauswahl** halb gesetzt ist. Beides überlebt beide Richtungen.
    3. Fokus und Scrollposition nach der Rückkehr aus der Liste — dieselben zwei Dinge, die `_render()` ohnehin eigens wiederherstellen muss.
    4. Das Home-Assistant-Menü: geht auf, und die Seitenleiste führt aus dem Panel heraus.
    5. Vergessen des gerade angesehenen Dashboards am schmalen Schirm: landet auf der Liste, nicht im Verlauf eines anderen (Festlegung 4, dritter Spiegelstrich).

    **Und eine Falle, die beim Review vermutet und beim Nachmessen umgedreht wurde.** Die Vermutung lautete: `capture_demo_screenshots.py` setzt `"mobile": False`, also greift `@media (hover: none)` nicht, und die Tippziele aus Festlegung 7 blieben unbelegt. Am 2026-09-17 in headless Chrome gemessen (`google-chrome --headless=new`, Seite mit Viewport-Meta wie das HA-Frontend) ist es **genau andersherum**:

    | Konfiguration | `(hover: none)` | `(pointer: coarse)` |
    |---|---|---|
    | nichts gesetzt | **wahr** | falsch |
    | `setDeviceMetricsOverride` 390 × 844, `mobile: false` | wahr | falsch |
    | dasselbe mit `mobile: true` | wahr | falsch |
    | dazu `Emulation.setTouchEmulationEnabled` | wahr | **wahr** |
    | `Emulation.setEmulatedMedia` mit `hover`/`pointer` | wahr | falsch |
    | Start mit `--blink-settings=availableHoverTypes=2,primaryHoverType=2,availablePointerTypes=4,primaryPointerType=4` | **falsch** | falsch |

    **Headless Chrome hat gar kein hoverfähiges Zeigegerät**, `(hover: none)` trifft also immer zu. Nicht der Berührungszweig fehlt in den heutigen Aufnahmen — der **Desktop**-Zweig fehlt. Dass das bisher niemandem auffiel, liegt daran, dass in diesem Block heute nur `.pen { opacity: 1 }` steht. Mit Festlegung 7 kommen vergrößerte Tippziele hinzu, und dann zeigte jede angeblich am Desktop aufgenommene Abbildung Finger-Maße.

    **Vier Folgerungen für den Plan, alle gemessen und keine gewählt:**

    1. Der Desktop-Zweig ist nur über eine **Startoption** erreichbar (`--blink-settings=…` oben), nicht über CDP. Sie gehört in den Chrome-Start des Aufnahme-Werkzeugs — dadurch werden auch die **bestehenden** Abbildungen erstmals richtig.
    2. `Emulation.setEmulatedMedia` nimmt `hover` und `pointer` entgegen und **bewirkt nichts**. Sackgasse, namentlich vermerkt, damit sie nicht ein zweites Mal probiert wird.
    3. Der Berührungszweig kommt über `Emulation.setTouchEmulationEnabled` — und der überschreibt die Startoption, so dass **beide Zweige in einem einzigen Chrome-Lauf** erreichbar sind.
    4. **Das Abschalten wirkt nicht sofort:** Nach `setTouchEmulationEnabled: false` bleibt `(hover: none)` in der laufenden Seite wahr; erst ein Seitenwechsel stellt den Desktop-Zweig wieder her. Die Aufnahmen sind deshalb zu ordnen — erst alle Desktop-Bilder, dann die Berührungs-Bilder —, oder es ist neu zu laden.

    Der Nachweis bleibt derselbe, er wird jetzt nur in beide Richtungen geführt: `matchMedia("(hover: none)").matches` muss in der aufgenommenen Seite den erwarteten Wert liefern — `false` für eine Desktop-Abbildung, `true` für eine Handy-Abbildung. Ohne diesen Nachweis gilt keine der beiden als Beleg.

    **Steht noch aus.** Diese Entscheidung ist getroffen, nicht umgesetzt. Der aktuelle Stand steht in `status.md`.

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
| Revision, die auf keinen Commit zeigt | Wird abgelehnt. `resolve()` prüft seit dem 2026-09-02, dass am Ende ein Commit steht. Gemessen, was vorher geschah: Die SHA eines YAML-**Blobs** löste sich auf sich selbst auf, eine Version darauf wurde **angenommen** — und war für immer unbrauchbar, weil `read_at` daran mit `AttributeError: 'Blob' object has no attribute 'tree'` scheitert. Zwei Wege führten dorthin: die Blob-SHA von Hand als Revision, und ein leichtgewichtiger Tag auf einem Blob. Bis zum 2026-09-08 wäre der Tag nicht mehr loszuwerden gewesen, weil Versionen nicht aufgehoben werden konnten; seit Entscheidung 18 ginge er. Die Ablehnung bleibt trotzdem richtig — eine Version, die man erst anlegen und dann aufheben muss, ist ein Fehler und keine Bedienung |
| Version auf einem Dashboard, das es nicht mehr gibt | Wird angelegt und bleibt bestehen. Das Zurückwechseln legt das Dashboard über den Weg aus Entscheidung 8 wieder an — eine Version auf einem gelöschten Dashboard ist genau der Fall, für den sich das lohnt. **Aber nicht auf der Löschzeile selbst:** Dort hat die Datei den Baum verlassen, der Stand ist also keiner, zu dem man zurückkehren könnte. Das Anlegen wird dort seit dem 2026-09-02 mit einem Satz abgelehnt statt eine Version zu erzeugen, die niemand einlösen kann. Zu markieren ist die Zeile **davor** |
| Version anlegen ohne Angabe einer Revision | Sie landet auf dem neuesten Stand **dieses Dashboards**, ausdrücklich nicht auf `HEAD`. Ein Repository hält alle Dashboards, `HEAD` ist also das zuletzt gespeicherte — gemessen am 2026-09-02: `heizung` ohne Revision zu markieren, kurz nachdem `solar` gespeichert wurde, hängt den Tag an solars Commit, und die Version erscheint in heizungs Verlauf danach nie wieder, weil `list_changes` nur dessen eigene Pfade läuft. Hat das Dashboard keinen einzigen Stand, wird abgelehnt |
| Version, deren Commit nicht im Verlauf dieses Dashboards liegt | Kann nur von Hand entstehen (Dienst mit fremder Revision). Der Dienst `versions` führt sie weiterhin auf; im Verlauf bekommt sie **keinen** Abschnitt, weil es keine Änderung gibt, über der sie stünde. Lieber unsichtbar an einer Stelle als Änderungen unter einem falschen Kopf |
| Tag, der dem Muster `vX.Y.Z` nicht folgt | Wird beim Hochzählen übergangen und trotzdem angezeigt. Ein von Hand gesetzter Tag darf die Nummernfolge nicht verschieben, aber auch nicht unsichtbar sein |
| Zurückwechseln auf eine Version, die dem aktuellen Stand entspricht | Der Knopf verschwindet, wie beim Ganz-Zurück in Entscheidung 9. Ein Knopf, der nichts tut, ist eine Frage ohne Antwort |
| Zwei Versionen auf demselben Commit | Erlaubt. Sie zeigen auf denselben Stand; der Verlauf zeigt beide Köpfe untereinander mit demselben Inhalt darunter |
| Version aufheben, die einem anderen Dashboard gehört | Wird abgewiesen. `_owns` ist der Zaun, und er kennt Schlüssel mit Schrägstrich: `dh-slash/check` beansprucht nicht `dh-slash/check/tief/v1.0.0` |
| Version aufheben, die es nicht gibt | Wird abgewiesen, mit dem Namen. Dieselbe Trennung wie bei der Beschreibung auf einer unbekannten Revision: eine Aussage über die Eingabe, keine über das Dashboard |
| Version aufheben ohne `confirm` | Antwortet mit Name, Titel, Beschreibung, Revision, ob sie automatisch entstand und ob sie die höchste Nummer trägt. Kein Diff — es ändert sich kein Dashboard; die Vorschau zeigt, was an *Worten* verloren geht |
| Version aufheben, wenn es kein Repository gibt | Antwortet »unbekannte Version«, statt eines anzulegen. Der Vorgang kann nur Bestehendes ändern; ein leeres Repository dafür zu erzeugen, hieße eine Historie hinterlassen, die niemand wollte |
| Handgemachter leichtgewichtiger Tag im Namensraum | Kann aufgehoben werden, obwohl er nicht umbenannt werden kann. Die Begründung steht bei Entscheidung 18, Festlegung 6 — und der zweite Grund ist die Nummer, die er sonst für immer belegt |
| Aufgehobene automatische Tagesmarke | Kann zurückkommen, und das ist gewollt: Betrifft sie den Tag, den der nächste Speichervorgang abschließen würde, macht die Automatik sie neu. Der Dialog sagt es vorher. Ältere Tage sind nicht betroffen, weil `end_of_previous_day` nur den jüngsten früheren Tag im Fenster findet |
| Letzte Version eines Dashboards aufgehoben | Erlaubt. Der einfache Modus zeigt dann seinen Leersatz (»This dashboard has no versions yet«) statt einer leeren Liste — der Satz war schon da, weil ein Dashboard vor seiner ersten Version denselben Zustand hat |
| Höchste Version aufgehoben | Die Nummer kommt frei und wird beim nächsten Klick erneut vergeben. Ausgesprochen im Dialog, weil es der Fall ist, für den das Aufheben gebaut wurde. Wer sie notiert hatte, findet danach einen anderen Stand — siehe Entscheidung 13 |
| Vergleichsmodus: zwei inhaltsgleiche Stände gewählt (Entscheidung 19) | Der Dialog sagt es direkt (»Kein Unterschied zwischen diesen beiden Ständen«) statt eines leeren Diffs. Sind beide Seiten echte Revisionen, entscheidet `store.same_state` — nicht über eine zweite Vergleichsmethode, Entscheidung 13 verlangt genau das. Ist eine Seite »Aktueller Zustand«, hat `same_state` nichts zum Vergleichen (kein Commit); dort entscheidet die Textgleichheit der bereits gedumpten Stände, was denselben, längst berechneten Diff liest statt eine dritte Methode einzuführen |
| Vergleichsmodus: eine Seite ist die Löschzeile eines gelöschten Dashboards | Der Vergleich selbst bleibt möglich, weil `_explain_texts` mit einer fehlenden Seite umgehen kann. »Aktueller Zustand« wird für ein aktuell nicht existierendes Dashboard gar nicht erst als Auswahl angeboten — nichts, wogegen verglichen werden könnte, und Put-back schreibt ohnehin nur in einen lebenden Zustand |
| Vergleichsmodus: Undo einer Zeile verweigert | Die Verweigerung nennt den Grund und bietet zusätzlich einen vorbelegten Sprung in den Vergleichsmodus an (Vorgänger-Stand dieser Zeile plus »Aktueller Zustand«) — dieselbe Put-back-Liste, die bis Vorhaben J automatisch unter der Zeile stand, jetzt hinter einem Klick. Ohne diesen Verweis stünde an einer gelöschten Section (README, »Deleting a whole section«) nur noch die nackte Verweigerung, ein Rückschritt hinter Entscheidung 5 |
| Vergleichsmodus: Auswahl über eine Seite hinweg, während neu geladen wird (Entscheidung 17/G) | Ein Refresh leert `_detailCache` und springt auf Seite 1; eine Auswahl, deren Zeile dadurch nicht mehr geladen ist, bleibt über ihre Revision gültig — der Vergleich braucht keine geladene Zeile, nur eine auflösbare Revision |
| Vergleichsmodus gegen »Aktueller Zustand«, Live-Zustand ändert sich zwischen Auswahl und Put-back | Put-back rechnet beim Bestätigen neu, wie jeder Undo und jedes Put-back schon heute (Entscheidung 15) — der bereits offene Dialog zeigt weiterhin den Stand von der Auswahl, nur der Schreibvorgang selbst prüft sich neu |

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
| Position lügt: Ansicht ohne Pfad, davor gelöscht oder eingefügt | die Rücknahme verweigert, statt einen falschen Stand zu schreiben — die drei am 2026-09-04 gemessenen Fälle |
| Position lügt: Section verschoben | dieselbe Verweigerung, und keine Karte landet in einer fremden Section |
| Kennungen vergeben: unveränderte Ansicht | erbt ihre Kennung, auch ohne Pfad und über eine Verschiebung hinweg |
| Kennungen vergeben: bearbeitete Ansicht | erbt sie ebenfalls, statt als gelöscht plus hinzugefügt zu gelten |
| Kennungen vergeben: zwei gleich gute Kandidaten | keiner erbt, die Rücknahme verweigert — geraten wird nicht |
| Kennungen vergeben: dieselbe Kennung nie zweimal | die Zuordnung ist eindeutig, wie bei den Karten in Entscheidung 14 |
| Stand ohne Kennungen | fällt auf das Verhalten vor Entscheidung 16 zurück, ohne Fehler und ohne Hinweis |
| Nur eine Seite trägt Kennungen | ebenso — der Rückfall gilt für das Paar, nicht je Stand |
| `forget` über ein Dashboard mit Kennungen | die Kennungsspur wird mitgeschrieben, die Kette reißt nicht rückwirkend |
| Übereinstimmende Version außerhalb des Fensters | die Plakette bleibt sichtbar, auch wenn der Tag-Commit nicht geladen ist |
| Blättern, während gespeichert wird | der Commit-Zeiger verrutscht nicht, keine Änderung erscheint doppelt oder fällt aus |
| Einrichtung mit bestehenden Dashboards | jedes bekommt genau ein `v1.0.0`, keines zweimal |
| Erster Speichervorgang eines Tages | der Stand davor bekommt die Tagesversion, mit Datum im Titel und als automatisch gekennzeichnet |
| Zweiter Speichervorgang desselben Tages | keine weitere Tagesversion |
| Tag ohne Speichervorgang | keine Version — eine ruhende Woche erzeugt keine sieben Marken |
| Tagesversionen abgeschaltet | es entsteht keine, und der Rest der Erfassung bleibt unverändert |
| Rücksprung mit »verwerfen« | der bisherige Stand bleibt als Änderung lesbar und trägt nur kein Tag |
| Rücksprung mit »behalten« | er trägt eine Version, bevor der ältere Stand geschrieben wird |
| Version aufheben | der Tag ist fort, der Commit darunter über seine Revision **weiterhin lesbar**, HEAD unverändert, die Notizen unberührt — die Festlegung »nur die Ref« als Nachweis statt als Behauptung |
| Version aufheben: der Zaun | ein fremdes Dashboard, ein unbekannter Name, ein Schlüssel mit Schrägstrich und ein fehlendes Repository werden abgewiesen, jeder mit seinem eigenen Satz |
| Version aufheben: leichtgewichtiger Tag | wird aufgehoben, während derselbe Tag nicht umbenannt werden kann. Die beiden Sichtbarkeitsregeln der Oberfläche gehören mitgeprüft — sie sind verwechselbar |
| Freigewordene Nummer | `candidates` bietet sie wieder an. Reines `versions.py`, kein Produktionscode ändert sich dafür; der Test hält die bedingte Zusage aus Entscheidung 13 fest |
| Aufgehobene Tagesmarke, Uhr weitergedreht | sie wird neu gemacht. Nur im Container ohne laufende Instanz erreichbar, weil kein API einen Commit rückdatiert — derselbe dritte Weg, für den `run_day_marks.py` gebaut wurde |
| Version aufheben am laufenden Home Assistant | ohne `confirm` kommen die Worte, mit `confirm` ist die Version fort und die Liste danach kennt sie nicht mehr. Die Prüfung legt ihre eigene Version an und hebt sie wieder auf, lässt die Prüfbank also so zurück, wie sie sie fand |
| Vergleich zweier beliebiger, nicht benachbarter Stände (Entscheidung 19) | liefert dieselbe Erklärung/denselben Diff wie ein einzelner Schritt, nur über die zwei gewählten Stände statt über Vorgänger und Nachfolger |
| Vergleich, bei dem eine Seite »Aktueller Zustand« ist | bietet zusätzlich die Put-back-Liste, mit denselben Positionen und demselben Ergebnis wie heute an der Zeile |
| Vergleich zweier historischer Stände, keiner ist »Aktueller Zustand« | bietet keinen Put-back an, rein informativ |
| Zeilen-Checkbox im Vergleichsmodus | wählt den Stand **nach** der jeweiligen Änderung — dieselbe Revision, die auch `restore_state` und `create_version` adressieren, nicht den Stand davor |
| Verweigerter Undo verlinkt in den Vergleichsmodus | die Verweigerung bietet den Sprung mit Vorgänger-Stand und »Aktueller Zustand« vorbelegt an — geprüft an der gelöschten Section, dem Fall aus dem README, an dem Undo strukturell nie greift |

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

### Nachgetragen am 2026-09-04: F

- **F — Die Identitätskette.** Entscheidung 16, diese Spec, ein eigener Plan. Sie steht **vor** B und C und nach dem bereits umgesetzten Paket 1 des Befunds vom 2026-09-04. Der Grund ist derselbe wie bei E: Sie fasst `analyze.py`, `restore.py`, `capture.py` und `store.py` an — denselben Kern, den Entscheidung 14, Entscheidung 15 und Paket 1 nacheinander umgebaut haben. Je länger dazwischen liegt, desto weniger trägt das frische Wissen darüber.

  **Drei Pakete, in dieser Reihenfolge, und nur das erste ist fertig:**

  1. **Verweigern statt stumm falsch schreiben.** *(Erledigt am 2026-09-04.)* `analyze` prüft für jedes Ständepaar, das eine Rücknahme liest oder beschreibt, ob eine positionsbasierte Adresse in beiden dasselbe meint; `restore` verweigert, bevor eine Karte in eine fremde Section wandert. Neun pytest-Fälle, sieben Prüfungen am laufenden Home Assistant.
  2. **Die Identitätskette.** Entscheidung 16.
  3. **Die Section als eigenes Stück.** `find_removed` und `reinsert` kennen heute nur ganze Ansichten und einzelne Karten. Wird eine Section gelöscht, werden ihre Karten **einzeln** zum Zurückholen angeboten, und jede einzelne verweigert — es gibt keinen Weg zurück, obwohl der vollständige Inhalt in der Historie liegt. Das braucht `kind="section"` auf beiden Seiten, baut auf Paket 2 auf und ist ohne dessen Identität nicht sinnvoll: `reinsert` wüsste sonst nicht, wohin die Section gehört.

  **Was F nicht ist:** eine Reparatur der Karten-Zuordnung. Die liegt bei Entscheidung 14 und bleibt dort.


### Nachgetragen am 2026-09-04: G und H

Aus zwei GitHub-Issues, und die Reihenfolge zwischen ihnen ist keine Geschmacksfrage.

- **G — Versionen, die halten.** *(Issue 1.)* Heute liefert `async_history` fünfzig Änderungen, und das Panel bezieht Versionen ausschließlich aus diesem Fenster. Eine Version außerhalb davon existiert für die Oberfläche nicht: kein Abschnitt, keine Plakette, kein Rücksprung. Das ist kein Anzeigefehler, sondern eine Marke ohne Haltbarkeit. G bringt die Übereinstimmungsprüfung auf die Serverseite (`matching_versions`, unabhängig vom Fenster), führt eine Blätterung über einen Commit-Zeiger statt über Zahlen ein — ein Zähler verrutscht, wenn während des Blätterns gespeichert wird — und macht die Versionen eines Dashboards als eigene Abfrage verfügbar.

  **Die Oberflächenhälfte des Issues wird nicht hier gebaut.** Register und Suchfeld gehören in die Oberfläche, die H ohnehin neu ordnet; sie zuerst zu bauen hieße, `panel.js` zweimal umzubauen — die Datei, in der bisher die meisten Oberflächenfehler saßen.

- **H — Die zwei Modi.** *(Issue 2, verschärft.)* Entscheidung 17. Enthält den Initialtag, die automatischen Tagesversionen, den Moduswechsel und die Oberfläche für beide Modi in einem Zug.

**Wo F dabei bleibt:** hinter H (Fortsetzung unten bei I). Die Identitätskette dient der gezielten Rücknahme einzelner Stücke — die es im einfachen Modus gar nicht gibt. Für den erweiterten Modus ist der Schaden durch Paket 1 bereits angehalten, es steht also nichts unter Druck. Wird der einfache Modus der Normalfall, sinkt F's Reichweite ohnehin auf die Nutzer, die bewusst gewechselt haben.


### Nachgetragen am 2026-09-08: I

- **I — Versionen aufheben.** Entscheidung 18, diese Spec, ein eigener Plan. Der Buchstabe ist I und nicht D: **D** trägt seit dem 2026-09-02 die sechs Befunde am älteren Kern (siehe »Offene Punkte«) und bleibt vergeben.

  **Wo I steht: vor D, vor B und C, hinter allem Gebauten.** Drei Gründe, und der erste ist der schwächste:

  1. Es ist klein. `store`, `operations`, zwei Schnittstellen, eine Steuerung im Panel, und in der Mitte eine gelöschte Ref. Das Muster liegt fertig beim Umbenennen, an dem sich der Zaun, die Ablehnungssätze und die Docstring-Form ablesen lassen.
  2. Es ist die einzige Stelle, an der die Bedienung heute in eine Sackgasse führt: Eine Version, die aus Versehen entstand, bleibt für immer stehen. Alles andere im Werkzeug ist umkehrbar oder wiederholbar.
  3. **Es räumt eine Zusage auf, bevor C sie erbt.** Versionen sind in C die Schutzmarke. Solange sich keine aufheben lässt, ist jede versehentliche Version ein dauerhaft geschützter Stand — und C müsste eine Aufbewahrungsregel gegen einen Bestand entwerfen, der Marken enthält, die niemand wollte.

  **Was I nicht enthält**, ausdrücklich und mit dem Grund dazu: das Entfernen von *Inhalt*. Der Wunsch danach war Teil derselben Frage, und die gestaffelte Antwort steht bei Entscheidung 18. Es zusammen zu bauen hieße, eine zweite unwiderrufliche Operation zu entwerfen, bevor die Messwerte aus B vorliegen — und mit `forget` liegt bereits eine da, deren offene Punkte in diesem Dokument unter Nummer 1 stehen.

### Nachgetragen am 2026-09-12: J

- **J — Der Vergleichsmodus.** Entscheidung 19, diese Spec, eigener Plan folgt. Ersetzt das zeilenweise Put-back aus Entscheidung 15 durch den bewussten Vergleich zweier frei gewählter Stände — eine neue, dünne Operation `compare` plus ein neuer Auswahl-Zustand im Panel. `deleted_since` und `restore_deleted` bleiben unverändert und werden nur an den neuen Einstieg umgehängt; `analyze.py` und `restore.py` bleiben ganz unberührt.

  **Wo J steht:** unabhängig von B, C und D — betrifft weder Repository-Größe noch den älteren Kern aus dem Review vom 2026-09-02. Mit F teilt sich J eine Oberfläche, nicht eine Logik: F's Pakete 2/3 ändern nichts an `analyze.py`/`restore.py`, das J anfasst, aber der einzige heutige Weg zurück bei einer gelöschten Section — der Put-back-Block, README »Deleting a whole section« — zieht mit J vom automatisch sichtbaren Zeilen-Block in den per Verweigerung verlinkten Vergleichsmodus um. Wer F's Pakete 2/3 plant, sollte diesen Umzug kennen, nicht nur die Zuordnungslogik.

### Nachgetragen am 2026-09-17: K

- **K — Schmal bedienbar.** Entscheidung 20, diese Spec, eigener Plan folgt. Das Panel bekommt den Home-Assistant-Hamburger, eine Seitenspalte, die mitwandert, und unterhalb eines schmalen Bandes Master/Detail statt zweier Spalten. Gemessen wird dabei die Breite des Panels, nicht die des Fensters.

  **Wo K steht: vor B, C und D, hinter allem Gebauten.** Der Grund ist nicht Größe, sondern Art des Schadens. B und C sind Ausbau, D sind Befunde an Randfällen — K ist der einzige offene Punkt, an dem eine vorhandene, fertige Funktion auf einem gewöhnlichen Gerät **gar nicht** erreichbar ist. Home Assistant hat eine Begleit-App und ist darauf ausgelegt, vom Handy aus bedient zu werden — jede eingebaute Seite stellt dort ihren Hamburger. Ein Panel, aus dem man ohne die Zurück-Geste des Browsers nicht mehr herauskommt, ist an dieser Stelle kein Randfall, sondern eine Sackgasse.

  **K fasst keine Logik an.** Nichts an `store.py`, `analyze.py`, `restore.py`, `operations.py` oder den beiden Schnittstellen. Berührt werden `panel/style.js`, `panel.js` und `tools/capture_demo_screenshots.py`. Das ist der zweite Grund, es vorzuziehen: Es kollidiert mit keinem der anderen Vorhaben und kann zwischen ihnen stehen, ohne etwas zu blockieren.

  **Was K nicht enthält**, mit dem Grund dazu: eine eigene Oberfläche für Handys. Es gibt eine, die überall funktioniert — siehe Entscheidung 20, »Was diese Entscheidung nicht ist«. Eine zweite hieße, jede spätere Änderung am Panel zweimal zu bauen und zweimal zu belegen, und genau davor hat sich dieses Projekt bei den zwei Modi (Entscheidung 17) bereits gehütet: Simple und Advanced sind zwei Sichten auf dieselbe Oberfläche, nicht zwei Oberflächen.

## Offene Punkte

- **Umkehrbarkeit endet an einem nie aufgezeichneten Stand.** *(Gefunden am 2026-09-17 bei einem Review von Entscheidung 20. Betrifft Entscheidung 13, nicht Vorhaben K — K fasst `operations.py` nicht an.)* Hört der Rekorder einen Speichervorgang nicht — gespeichert während des HA-Starts, Ablagedatei von außen bearbeitet, Rekorder einmal gescheitert —, steht der Stand auf dem Dashboard in keinem Commit. Jede schreibende Operation versucht ihn vorher nachzutragen (`_keep_the_live_state`, `operations.py:235`), und das gelingt fast immer. **Gelingt es nicht, wird trotzdem geschrieben** (Festlegung vom 2026-09-03, oben bei Entscheidung 13), und dieser Stand ist damit endgültig fort. Der Hinweis darauf erreicht das Panel erst *nach* dem Schreiben (`panel.js:1650`). Es müssen zwei seltene Dinge zusammentreffen — eine Lücke im Verlauf und ein in diesem Moment nicht schreibbares Repository —, aber solange es möglich ist, stimmt der Satz »über jede Operation außer `forget` lässt sich sagen: umkehrbar« nicht.

  **Drei Wege liegen ausgearbeitet vor, keiner ist gewählt:** (1) *Vorher warnen* — der Vorschau-Zweig hat `live_text` bereits in der Hand (`operations.py:625`), ein Vergleich gegen `HEAD` kostet einen Aufruf, und der Bestätigungsdialog könnte es sagen, bevor geklickt wird; Schreibverhalten unverändert. (2) *Gar nicht erst schreiben*, außer bei ausdrücklicher Freigabe — kehrt die Festlegung von 2026-09-03 um und behält ihren Notausgang. (3) *Nur die Zusage einschränken* — kein Code, dafür ein Vorbehalt, der in jedem Dialog steht und deshalb überlesen wird.

  **Stand der Willensbildung (2026-09-17):** GitHub-Issue [#18](https://github.com/PPP01/ha-dashboard-history/issues/18). Der Nutzer tendiert zu (2) und hat die Entscheidung ausdrücklich vertagt — das Problem ist dokumentiert, nicht dringend. Festgehalten, damit die Tendenz nicht verlorengeht und der nächste, der hier liest, nicht bei null anfängt.

- ~~**Zugriff auf das Lovelace-Objekt im Speicher** ist noch nicht praktisch verifiziert.~~ **Erledigt am 2026-08-30.** An einer laufenden Anlage bestätigt: `debug_snapshot` meldet alle zehn Dashboards, die Warnung »Lovelace data not available in the expected shape« erscheint **nicht**, der Rückfall bleibt ungenutzt. Ein neu angelegtes Dashboard war sechs Sekunden später als Commit da — ohne jede Wartezeit. **Entscheidung 1 trägt.**
- **Sechs Befunde am älteren Kern, von einem unabhängigen Review am 2026-09-02 gefunden.** Keiner stammt aus Entscheidung 13; sie lagen vorher da und brauchen eigene Entwurfsarbeit. Zusammen sind sie ein **Vorhaben D**, und mehrere wiegen schwerer als alles, was dieses Vorhaben zu reparieren hatte:

  1. **Ein unterbrochenes `forget` ist nicht wiederaufnehmbar und verliert fremde Beschreibungen.** HEAD, Notizen und Tags werden nacheinander umgeschrieben, ohne vorbereiteten Ersatz-Ref. Bricht es zwischen `_point_head` und `_rewrite_notes` ab, ist das vergessene Dashboard bereits aus HEAD verschwunden, ein zweiter Lauf liefert `0` und kann nichts reparieren, und die Beschreibungen eines **lebenden** Dashboards fehlen danach. Echter Metadatenverlust an unbeteiligten Daten, in der einzigen unwiderruflichen Operation.
  2. ~~**Dashboard-Schlüssel mit Schrägstrich werden erfasst, aber aus allen Übersichten verloren.**~~ **Erledigt am 2026-09-03 — und anders, als der Befund vorschlug: als Regel, nicht als Reparatur.** Der ursprüngliche Wortlaut: Geschrieben wird der Schlüssel als Pfad, gelesen und aufgelistet wird eine Datei der obersten Ebene; nachgemessen an HA 2026.8.3 wurde `url_path="dh-slash/check"` angenommen, die Historie entstand, `dashboards` führte sie nicht auf.

     **Die Frage, die vorher niemand gestellt hatte, war, ob so ein Dashboard überhaupt existiert.** Am Prüfstand nachgemessen: Die API nimmt die Anmeldung an und schreibt einen Datensatz — **erreichbar ist das Ergebnis nicht.** `IndexView.resolve` (`frontend/__init__.py:812`) sucht das Panel allein über das *erste* Pfadsegment; `energie-x/inverter` antwortet mit 404, und `energie-x` ebenso. Die Oberfläche lässt einen solchen `url_path` gar nicht eintragen: erlaubt sind Buchstaben, Ziffern, `-` und `_`, und ein `-` ist Pflicht — nachgeprüft an einem neu angelegten Dashboard, das sich nicht auf `attic`, `attic-` oder `attic_` umbenennen ließ, sondern `a-attic` werden musste. Was ein solcher Datensatz erzeugt, ist ein **Geist**: kein Browser kommt hin.

     Damit ist der saubere Weg nicht, `dashboards` das Verschachtelte lesen zu lehren, sondern **einen solchen Schlüssel nicht aufzuzeichnen**. `keys.is_safe_key` verlangt ein einzelnes gewöhnliches Pfadsegment, `capture` sortiert alles andere mit einer Warnung *unter Nennung des Schlüssels* aus — ein Dashboard ohne Historie darf nicht schweigend eines ohne Historie bleiben. Nichts Rechtmäßiges wird abgewiesen. Der Nebengewinn liegt auf der Tag-Seite: `<key>/v1.0.0` kann jetzt nur noch **einen** Schrägstrich tragen, womit die Präfixprüfungen in `store.py` (`_rewrite_tags`, `list_versions`) durch einen Schlüssel nicht mehr zu täuschen sind. Sie bleiben deshalb **absichtlich unverändert**; ein von Hand gesetzter Tag mit mehr Segmenten täuscht sie weiterhin, aber das ist Handarbeit an der Ablage und keine Nutzerhandlung.

     **Was einmal aufgezeichnet wurde, bleibt erreichbar** — und das ist keine Vorsichtsformel: Im Prüfstand-Store liegen drei solche Verzeichnisse (`dh-slash`, `energie-x`, `zz-slash`). Die Grenze im Store prüft darum **nicht die Schlüsselregel nach**, sondern nur, dass eine Datei *innerhalb* der Ablage liegt. Ein verschachtelter Altbestand bleibt damit lesbar und löschbar, statt in einer Historie festzusitzen, die keine Operation mehr beenden kann.
  3. **Löschen und schnelles Wiederanlegen desselben `url_path` verschmelzen zwei Dashboards.** Die Entprellung von zehn Sekunden verwirft den Zwischenzustand »gelöscht« vollständig, und damit die Trennlinie, auf die sich Entscheidung 12 ausdrücklich verlässt. Ein fremdes Dashboard erbt die alte Historie und bekommt daraus alte Karten zur Wiederherstellung angeboten.
  4. ~~**Eine Karte zwischen Views oder Abschnitten zu verschieben, wird als Löschung angeboten.**~~ **Erledigt am 2026-09-03, Entscheidung 14.** Die Zuordnung greift nur innerhalb derselben Container-Position. Bestätigt jemand die vermeintliche Wiederherstellung, wird eine noch vorhandene Karte **verdoppelt**.
  5. **Mehrdeutige schwache Schlüssel: am 2026-09-03 erledigt (Entscheidung 14, Zuordnung nach bester Ähnlichkeit). Fehlende bleiben offen** — und zwar als benannte Grenze, nicht als Versäumnis: An 27 von 484 Karten ist nichts zu erkennen, und keine Rechnung kann dort Bearbeitung von Löschung unterscheiden. Der ursprüngliche Befund lautete: Zwei Karten mit gleicher `type`/`entity`: Die erste wird gelöscht, die zweite bearbeitet — angeboten und zurückgeholt wird die alte Fassung der *vorhandenen*, während die wirklich gelöschte verloren bleibt. Das ist der Fehlalarm, den Entscheidung 4 als schlimmer einstuft als eine fehlende Funktion, mit Datenverlust obendrauf.
  6. ~~**Die 1000-Commit-Grenze lässt alte gelöschte Dashboards verschwinden.**~~ **Erledigt — beim Nachlesen am 2026-09-12 im Code bestätigt; das genaue Datum der Behebung selbst ist nicht überliefert, hier also nachgetragen statt zeitgleich vermerkt.** Der ursprüngliche Befund: `list_all_dashboards` und die Vorschau von `forget` hatten undokumentierte harte Grenzen. Nach tausend Commits anderer Dashboards führte die Liste das alte gelöschte nicht mehr, `forget` meldete »no history«, und die Sicherheitsvorschau unterschätzte Anzahl, Zeitraum und Beschreibungen.

     **Am 2026-09-03 am Prüfstand nachgemessen, und es war schlimmer als notiert: Es traf auch *lebende* Dashboards.** `async_dashboards` bildete seine Liste allein über `list_all_dashboards()`; `list_dashboards()` — der HEAD-Baum, in dem alle stehen — wurde nur zum Setzen des `exists`-Kennzeichens benutzt. Ein Dashboard, das im aktuellen Stand lag, dessen letzte Änderung aber jenseits des Fensters lag, fiel damit ganz aus der Seitenleiste. Gemessen: 1052 Commits in der Ablage, neun echte Dashboards zuletzt geändert bei Commit 1034 bis 1051 — alle neun aus der Liste verschwunden, während zwanzig Wegwerf-Dashboards der Prüfläufe stehenblieben. Für einen Nutzer hieß das: Ein Dashboard, das er ein Jahr nicht anfasst, verschwindet aus dem Werkzeug.

     **Behoben genau so, wie hier vorgeschlagen.** `HistoryStore._built_index` (`store.py:1307`) liest laut eigenem Docstring »die ganze Historie, nicht die neuesten tausend Commits« und nennt die hier beschriebene Lücke — ein vor tausend Speichervorgängen gelöschtes Dashboard verließe sonst stillschweigend die Liste und ließe sich nicht mehr vergessen — wörtlich als Grund dafür. Die Namensmenge beginnt beim HEAD-Baum (`list_dashboards()`), der Lauf durch die Historie (`_revision_index`) fügt nur noch die gelöschten hinzu.

- ~~**Ein Schlüssel mit `..` schreibt außerhalb der eigenen Ablage.**~~ **Am 2026-09-03 gefunden und am selben Tag geschlossen.** Am Prüfstand gemessen: Ein über die API unter dem `url_path` `../weiter-weg` angemeldetes Dashboard wurde **neben** das Repository geschrieben, das die Integration führt — dorthin, wo nichts es zurückliest und nichts es aufräumt. Geschlossen durch zwei voneinander unabhängige Prüfungen, und ausdrücklich nicht durch dieselbe zweimal: `keys.is_safe_key` entscheidet, was überhaupt ein Schlüssel werden darf; `HistoryStore._file_for` entscheidet die einzige Frage, die an der Grenze zählt — bleibt die Datei innerhalb der Ablage. Die zweite hält, auch wenn ein späterer Aufrufer die erste vergisst, und sie ist bewusst **nicht** strenger als das (siehe D2, letzter Absatz).

- ~~**Zwei Speichervorgänge kurz hintereinander kehren die Historie um und beschreiben sich gegenseitig falsch.**~~ **Am 2026-09-03 gemessen und geschlossen.** Der Rekorder las die lebende Konfiguration und baute seine Commit-Botschaft in zwei getrennten Schritten; bei zwei Vorgängen kurz hintereinander lasen beide, dann schrieben beide, und wer zuletzt schrieb, verglich seinen *älteren* Stand gegen ein HEAD, das schon der neuere war. Gemessen an sieben Speichervorgängen: Die Kette kam als `1,2,3,4,6,5,7` heraus, und ein Eintrag behauptete »changed outside Home Assistant« über ein Speichern, das Home Assistant selbst gerade gemacht hatte. Das Fenster ist rund 30 ms breit, 3 von 3 Versuchen trafen es. **Der erste Behebungsversuch war eine einzige Sperre über Lesen und Schreiben — und der war schlimmer als der Fehler.** Er ist am Prüfstand durchgefallen, dreimal an denselben vier Prüfungen, und die Messung sagt, warum: Ein Abgleich über die gewachsene Ablage hielt die Sperre **16,6 s**, ein Speichervorgang wartete **7,2 s** darauf, und als er endlich lesen durfte, war das Dashboard gelöscht — er schrieb nichts, und dieser Stand ist endgültig weg. Eine Sperre, die das Lesen einschließt, verschluckt genau das, was sie schützen soll.

  Behoben ist es mit **zwei Sperren, je eine Aufgabe**. Die *Schreibsperre* umfasst HEAD-Abfrage, Botschaft und Commit als einen Abschnitt — sie stellt die Reihenfolge her und macht die Botschaft wahr. Die *Lesesperre* hält nur das Befragen von Home Assistant zusammen, fasst kein git an und ist in Millisekunden fertig; wer danach auf die Schreibsperre wartet, wartet **mit dem Zustand in der Hand**. Die Ordnung bleibt trotzdem die des Lesens, weil jeder Vorgang die Lesesperre verlässt und die Schreibsperre betritt, ohne dazwischen etwas abzuwarten. Der Merksatz, der die Aufteilung trägt: **Ein langsames Schreiben verzögert die Historie, ein langsames Lesen zerstört sie.** Nachgemessen mit der neuen Bauform: sieben Speichervorgänge, Kette 1…7, jede Botschaft »1 added«, und die vier Prüfungen bestehen wieder — zweimal hintereinander, das zweite Mal unter genau dem Anfangszustand, unter dem sie zuvor durchfielen.

  Das ist zugleich **Voraussetzung für Vorhaben E**: `store.previous_change` läuft die Elternkette, und aus einer verkehrten Kette bekäme eine gezielte Rücknahme den falschen Vorzustand — sie würde eine Karte entfernen, die nie hinzukam, und eine wieder einsetzen, die längst steht.

- **Eine Version außerhalb der neuesten 50 Änderungen wird unsichtbar — Marke ohne Haltbarkeit.** *(Adressiert von Vorhaben G, Issue 1. Mit Entscheidung 17 wird daraus ein Sperrgrund: Der einfache Modus kennt nur Versionen, und was er nicht sieht, gibt es für ihn nicht.)* *(Am 2026-09-03 am Prüfstand gemessen.)* `async_history` hängt Versionen über `marks.get(c.revision, [])` an Änderungen, und im Panel kommt *alles* über Versionen aus diesem einen Feld: Abschnittsköpfe, die Plakette »current state«, der Chip »same state as v1.0.0«. Fällt der Commit einer Version aus den neuesten 50 Änderungen, existiert sie für die Oberfläche nicht mehr. Belegt an `dh-probe`: Der Tag `dh-probe/v0.0.1` liegt unversehrt in der Ablage, sein Stand ist lesbar und **byteweise gleich dem aktuellen** — und trotzdem zeigt das Panel weder die Version noch den Hinweis auf die Übereinstimmung. Für einen Nutzer: Version setzen, fünfzigmal speichern, Version weg. Eine Marke, die verschwindet, ist keine. Die Plakette ist exakt zu reparieren (Übereinstimmung gegen *alle* Versionen prüfen statt gegen die sichtbaren); die Version wieder im Verlauf zu zeigen heißt, Commits von außerhalb des Fensters hereinzuholen, und bei 146 Versionen wäre das eine Wand aus Zeilen — das braucht einen eigenen kleinen Entwurf.

- **Eine Löschzeile ist als solche nicht erkennbar — und zwei Knöpfe stolpern darüber.** *(Aufgeworfen am 2026-09-02 vom Abschluss-Review.)* `history` sagt nicht, welche Änderung eine Löschung ist; das Panel kann es nur am generierten Meldungstext ablesen, und Textschnüffelei ist genau die Logik, die dort nicht liegen darf. Zwei Stellen leiden darunter: »Version bis hierher« auf der Löschzeile eines gelöschten Dashboards wird jetzt abgelehnt (siehe Randfälle), aber erst *nachdem* geklickt wurde; und »Back to the state after this change« wird dort ebenfalls angeboten, obwohl `restore_state` nur »did not exist at« antworten kann. Der saubere Weg ist ein Merkmal je Änderung in `history` — eine kleine Ergänzung, die beide Knöpfe vorher verschwinden ließe. Bewusst nicht mehr in dieser Fassung gebaut: Sie kam nach dem Abschluss-Review auf, und die Ablehnung ist heute wenigstens ehrlich statt still falsch.
- ~~**Platzbedarf über sehr lange Zeiträume.**~~ **Am 2026-09-02 gemessen, mit einer unerwarteten Antwort.** Über hundert Stände bleibt es linear (28 KiB je Stand) — die Vermutung, git packe dann von selbst besser, ist **falsch**: dulwich packt überhaupt nie. Das Repository der Anlage führte nach zwei Tagen 122 lose Objekte und keinen einzigen Pack, denn `porcelain.commit` schreibt lose Objekte und dulwich kennt keine selbsttätige Bereinigung. Sämtliche Zahlen stehen unter »Reihenfolge der Vorhaben«; gehandelt wird in Vorhaben C.
- ~~**Einordnung umsortierter Karten**~~ **An echten Daten entschieden am 2026-08-30.** Zwei Befunde:

  1. *Verschiebungen werden relativ gemessen, nicht absolut.* Ein Vergleich roher Positionen erklärte jede Karte hinter einer Löschung zur Verschiebung — auf großen Views zwanzig Meldungen Rauschen um die eine, auf die es ankommt. Gezählt wird jetzt der Rang unter den Überlebenden: Eine Löschung allein erzeugt **keine** Verschiebung, ein Tausch weiterhin zwei.
  2. *Die schwache Zuordnung reichte bei weitem nicht weit genug.* Sie kannte nur `entity`, `title` und `name` — die trägt auf dieser Anlage nur **57 % der 1526 Karten**. Alle übrigen lösten beim Bearbeiten einen Fehlalarm aus: gemeldet als gelöscht **und** neu angelegt, obwohl sie unverändert dastanden. Genau der Fall, den dieses Dokument oben als schlimmer bezeichnet als eine fehlende Funktion. Die Zuordnung greift jetzt zusätzlich auf `heading`, die erste Entität einer Entitätenliste, die erste Textzeile und die benennbare Karte innerhalb eines Containers zu — damit **96 %**. Eine Ähnlichkeitsbewertung braucht es dafür nicht.
