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
| `analyze.py` | Zwei Stände vergleichen und die Änderungen einordnen: Karte gelöscht, View gelöscht, bearbeitet, verschoben | **ja** |
| `restore.py` | Die Umkehrung anwenden: gelöschtes Objekt wieder einsetzen, oder einen ganzen Stand herstellen | **ja** |
| `store.py` | Das eigene Repository: Stände ablegen, Verlauf lesen, Versionen als Markierungen | **Kern ja** |
| `capture.py` | Auf Änderungen horchen, Stand holen, ablegen | nein |
| `operations.py` | Jeder Vorgang, genau einmal — Dienste und Panel sind dünne Häute darüber | nein |
| `websocket_api.py` | Befehle, auf denen das Panel aufsetzt | nein |
| `panel.py` + `panel.js` | Die Änderungsansicht in der Seitenleiste | nein |
| `services.py` | Dieselben Fähigkeiten für die Entwicklerwerkzeuge | nein |

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

9. **Das Panel fragt nach einer Änderung, nie nach einem Zustand.** *(Nachgetragen am 2026-08-30, aus der Beobachtung echter Bedienung.)*

   Die Dienste erwarten unter `revision` den *Zustand, gegen den verglichen wird*. Ein Mensch denkt aber in Änderungen: Soll eine Löschung zurückgenommen werden, greift er zu der Zeile, in der die Löschung steht — und das ist eine zu spät, denn gewollt ist der Zustand davor. Beim Erproben ist genau das passiert.

   Eine Warnung wäre die falsche Antwort, ein umbenanntes Feld auch. Die Oberfläche stellt die Frage schlicht nicht: Man klickt die Änderung an, und das Panel rechnet selbst aus, welcher Zustand gemeint ist. Die Stolperstelle wird nicht abgesichert, sondern entfernt.

   Daraus folgt auch, dass das Panel **keine eigene Logik** trägt. Alle Vorgänge liegen in `operations.py`; Dienste und Panel sind zwei dünne Häute über derselben Schicht. Sonst stünde das Wesentliche ausgerechnet dort, wo Home Assistant sich am häufigsten bewegt.

8. **Ein gelöschtes Dashboard wird wiederhergestellt, nicht nur betrauert.** *(Nachgetragen am 2026-08-30. Ursprünglich stand das Wiederanlegen außerhalb dieser Fassung.)*

   Das war falsch herum gedacht. Der schwerste Verlust, den dieses Werkzeug bezeugen kann, wäre dann der einzige gewesen, den es nicht rückgängig machen kann — während es für eine einzelne Karte alles bietet. Wer ein Dashboard löscht, verliert Hunderte Karten auf einmal.

   Der Preis ist bekannt und wird bewusst gezahlt: Ein Dashboard entsteht nur über die Dashboard-Sammlung von Home Assistant, und die ist kein zugesicherter Erweiterungspunkt. Deshalb gilt hier eine Trennung, die der Rest der Integration nicht braucht: **Das Dauerhafte muss gelingen, das Sofortige darf scheitern.** Registry-Eintrag und Konfiguration werden geschrieben; ob das Dashboard auch ohne Neustart in der Seitenleiste erscheint, ist Kür. Misslingt die Kür, wird das gemeldet, und ein Neustart genügt — der Verlust ist dann trotzdem behoben.

   Damit ein Dashboard *vollständig* wiederkehrt, werden ab dieser Fassung auch Titel, Symbol und Sichtbarkeit erfasst, nicht nur die Kartenkonfiguration. Sie liegen unter `meta/<schlüssel>.yaml` im selben Commit. Ein Dashboard mit richtigen Karten, aber falschem Namen wäre nur eine halbe Wiederherstellung.

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
