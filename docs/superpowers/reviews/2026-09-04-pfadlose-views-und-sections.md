# Befund vom 2026-09-04: Position als Identität

Stand: `main` bei `bb1b38c`, Arbeitsbaum mit unveröffentlichten Änderungen. Tests: 251 bestanden.

Auslöser war eine externe Meldung (Gemini) über Ansichten ohne URL-Pfad. Der Kern der Meldung ist bestätigt; die Prüfung hat den Befund allerdings in zwei Richtungen erweitert, die dort nicht vorkamen: Sections sind ebenso betroffen und in Teilen schlimmer, und der ursprünglich beschriebene Weg über `find_removed`/`reinsert` verhält sich anders als gemeldet.

Vorgehen: alle Fälle am Code reproduziert (`repro2.py`, `repro_sections.py`, `repro_putback.py`), die drei View-Fälle zusätzlich im laufenden Testcontainer (HA 2026.8.3) über WebSocket durchgeklickt – aufgebaut, Vorschau gelesen, bestätigt, Endzustand gemessen. Praxiszahlen aus den echten Dashboards.

## Gemeinsame Ursache

An zwei Stellen dient eine Position als Identität:

- `analyze._views_by_key` – eine Ansicht ohne `path` bekommt den Schlüssel `("#", index)`.
- `analyze.card_containers` – eine Section wird als `("sections", index, "cards")` adressiert. Sections haben in Home Assistant **grundsätzlich** keinen Pfad und keine Kennung; hier gibt es keine sichere Variante.

Verschiebt sich die Position, bezeichnet derselbe Schlüssel ein anderes Objekt. Der Code kennt die Schwäche – der Kommentar in `plan_undo` sagt »a view without one is keyed by its position« –, die Schutzklauseln dort prüfen daraufhin den *Inhalt* der Ansicht statt ihres Schlüssels, was in Fall C1-D einen zweiten Fehler erzeugt.

Praxisrelevanz, an den echten Dashboards gezählt: **8 von 67 Ansichten ohne Pfad** in sechs Dashboards, **24 von 67 Ansichten mit Sections-Layout, 80 Sections insgesamt**. Ein Dashboard trägt zwei pfadlose Ansichten mit demselben Titel »Home« – der naheliegende Ersatzschlüssel Titel trägt also nicht.

## CRITICAL

### C1 – Undo schreibt bei pfadlosen Ansichten stumm den falschen Stand

Drei Varianten, alle im laufenden HA bestätigt und mit `confirm: true` bis zum Endzustand durchgeführt.

**C1-A – die gelöschte Ansicht kommt im Dialog nicht vor.** Zwei pfadlose Ansichten »Home« und »Wetter«, der Nutzer löscht »Home«. Beide tragen nacheinander den Schlüssel `("#", 0)`, die Änderung wird als Kartentausch *innerhalb* einer Ansicht gelesen.

- Dialog: »markdown: Wetter will be deleted« / »markdown: Licht comes back«
- Ergebnis: »Home« bleibt fort, die Wetter-Karte ist durch die Licht-Karte ersetzt.

Der einzige Satz, der auffallen müsste, sagt genau das, was der Nutzer wollte. Die betroffene Ansicht wird nicht genannt.

**C1-B – die pfadlose Ansicht ist unbeteiligt und verschwindet.** Ansichten `a`, `b`, »Home« (pfadlos, Position 2). Der Nutzer löscht `b`, »Home« rückt auf Position 1 – mehr passiert nicht.

- Dialog: »the whole view "Home" will be deleted« / »the whole view "Gaeste" comes back«
- Ergebnis: `b` ist zurück, »Home« samt Inhalt fort.

**C1-D – zwei Ansichten hinein, null heraus.** Eine pfadlose Ansicht »Home«, davor wird »Neu« gesetzt. »Home« gilt gleichzeitig als hinzugefügt (Schlüssel `("#", 1)` ist in `before` unbekannt) und als bereits zurück (`any(standing == view)` trifft zu) – sie wird entfernt und nicht wieder eingesetzt.

- Ergebnis: `views: []`, leeres Dashboard.

Auslösend ist in allen drei Fällen eine gewöhnliche Bedienhandlung. C1-B braucht nicht einmal eine Berührung der pfadlosen Ansicht.

### C2 – »Put it back« legt Karten stumm in die falsche Section

`restore._cards_at` läuft `("sections", index, "cards")` im *aktuellen* Stand ab. Zeigt der Index auf eine existierende, aber andere Section, gibt es keine Warnung.

| Situation | Verhalten |
| --- | --- |
| Karte gelöscht, Section bleibt | korrekt |
| Erste von zwei Sections gelöscht | Karte landet stumm in der falschen Section |
| Section davor eingefügt | Karte landet stumm in der falschen Section |
| Section gelöscht, Index zeigt ins Leere | `LookupError`, korrekt verweigert |

Dieselbe Adressierung nutzt `plan_undo`: Wird eine Section vor eine bestehende gesetzt, zieht das Undo die Karte in die neue Section und lässt die ursprüngliche leer zurück (`repro_sections.py`, S2).

Der `LookupError` ist der gutartige Ausgang. Er erscheint nur, wenn die Zahl der Sections geschrumpft ist; die stummen Fälle sehen nach einem gelungenen Vorgang aus.

## WARNING

### W1 – Gelöschte Section: »Put it back« ist eine Sackgasse

`find_removed` kennt nur `kind="view"` und `kind="card"`. Wird eine ganze Section gelöscht, werden ihre Karten **einzeln** zum Zurückholen angeboten, und jede einzelne verweigert mit

```text
the card list this card belonged to no longer exists (location=('sections', 0, 'cards'))
```

Die Section selbst wird nie als wiederherstellbares Element angeboten. Es gibt damit keinen Weg zurück – weder über »put it back« noch über einen Undo-Schritt –, obwohl der vollständige Inhalt in der Historie liegt. Das Panel bietet dabei Knöpfe an, die zuverlässig fehlschlagen.

### W2 – Ein wiederverwendeter Pfad überschreibt eine fremde Ansicht

Ansicht mit Pfad `a` gelöscht, neue Ansicht mit demselben Pfad angelegt: Der Vergleich liest das als Kartenänderung innerhalb `a`, das Undo schreibt die alten Karten in die neue Ansicht (`repro_sections.py`, P2). Ein Pfad ist zu einem Zeitpunkt eindeutig, über die Historie hinweg nicht.

Die Klausel »a different view now sits at …« in `plan_undo` fängt das nicht ab – sie greift nur im View-Insert-Zweig, nicht beim Kartenvergleich.

### W3 – Die Vorschau trägt weniger, als sie scheint

Der YAML-Diff ist wahrheitsgetreu, steht im Panel aber hinter einem standardmäßig zugeklappten `<details>` (`panel.js`, `_confirm`). Offen sichtbar ist nur der Klartext aus `explain_effect` – der in C1-A die betroffene Ansicht nicht nennt – und daneben der beruhigende Satz »What the dashboard holds now is not lost«.

Der Satz stimmt: `_keep_the_live_state` sichert den Live-Stand vor jedem Undo, und `restore_state` holt ihn vollständig zurück (nachgemessen, auch für das leere Dashboard aus C1-D). Das Netz ist damit die Historie, nicht die Vorschau – es setzt aber voraus, dass jemand den Fehler bemerkt.

### W4 – Doppelte Pfade lassen eine Ansicht verschwinden

Home Assistant erzwingt die Eindeutigkeit von `view.path` nicht im Backend; über die API gespeichert kommt `['doppelt', 'doppelt']` anstandslos durch. `dict(_views_by_key(...))` behält dann nur die letzte – die erste Ansicht ist für die gesamte Analyse unsichtbar. In den echten Dashboards kommt das nicht vor, der visuelle Editor verhindert es vermutlich. Randfall, hier notiert, damit »Pfad = Identität« nicht als Garantie gelesen wird.

## Nicht betroffen

Geprüft und in Ordnung:

- **Pfadtausch zwischen zwei Ansichten mit Pfad** – die Karten landen korrekt; das Kartenmatching trägt (`repro_sections.py`, P1). Die Titel bleiben getauscht, das ist die bekannte Grenze »Undo arbeitet nie auf View-Labels«, kein neuer Befund.
- **Karte gelöscht bei stabiler Struktur**, mit und ohne Sections – korrekt.
- **Bestehender Testfall** `test_views_without_a_path_are_handled` – deckt den stationären Fall ab und ist richtig. Die Lücke ist das Nachrücken, nicht der fehlende Pfad.

## Korrekturen an der ursprünglichen Meldung

- Die dort abgedruckte »tatsächliche Ausgabe« kann so nicht entstanden sein: `from custom_components.dashboard_history.analyze import …` lädt `__init__.py` und scheitert mit `ModuleNotFoundError: No module named 'homeassistant'`. Inhaltlich trifft sie den Fall dennoch.
- »`explain_change` erkennt die Löschung nicht« ist ungenau: Es erkennt *eine* View-Löschung und benennt die falsche.
- »Es existiert kein Testfall für pfadlose Ansichten« ist falsch (siehe oben).
- Der Lösungsvorschlag »Titel als Ersatzschlüssel« trägt nicht (zwei »Home« in einem echten Dashboard).
- Nicht erwähnt und schwerer: C1-B, C1-D, C2 und W1.

## Vorgehen

Drei Pakete, in dieser Reihenfolge:

1. **Verweigern statt stumm falsch schreiben** – für Ansichten und Sections. Sobald eine positionsbasierte Adresse im Spiel ist und die Struktur sich verschoben hat, `UndoPlan(blocked=…)` beziehungsweise `LookupError`. Klein, deckt C1 und C2 sofort ab und entspricht Entscheidung 4 der Spec: raten ist verboten, verweigern erlaubt. Heilt die falschen Historientexte nicht. **Erledigt am 2026-09-04**, siehe unten.
2. **Identitätskette in der eigenen Historie** – bei jedem erfassten Speichervorgang Ansichten und Sections dem Vorgänger zuordnen (Pfad, dann identischer Inhalt, dann Ähnlichkeit, sonst neu) und die Zuordnung als dritte Spur neben `<key>.yaml` und `meta/<key>.yaml` mitcommitten. `analyze` bekommt sie als optionalen Parameter gereicht und bleibt Home-Assistant-frei; ohne Karte gilt das heutige Verhalten. Rückwirkend berechenbar, weil jeder Zwischenstand als Commit vorliegt. Behebt C1, C2, W2 und die falschen Historientexte.
3. **Sections als eigene Granularität** – `kind="section"` in `find_removed` und `reinsert`, analog zu `kind="view"`. Behebt W1, setzt Paket 2 voraus.

Paket 2 berührt die Spec: Entscheidung 4 argumentiert mit »Lovelace-Karten haben keine Kennung«. Dass die Integration sich selbst welche führt, ohne fremde Dashboards zu verändern, gehört dort begründet.

Nicht weiterverfolgt, weil die Spec es ausschließt: Kennungen in die Dashboards des Nutzers schreiben. Home Assistant bietet keinen Erweiterungspunkt vor dem Speichern – `LovelaceStorage.async_save` schreibt die Konfiguration wörtlich durch, das Event `lovelace_updated` kommt danach. Möglich wäre nur, den WebSocket-Befehl zu ersetzen (verboten) oder nach dem Event zurückzuschreiben (verändert fremde Dashboards, verdoppelt die Historie, verliert das Rennen gegen einen offenen Editor, wirkt nur nach vorn). Dass Home Assistant `id`-Felder auf Views, Sections und Karten unverändert speichert, ist geprüft und stimmt – es ändert an der Abwägung nichts.

## Stand vom 2026-09-04: Paket 1 ist umgesetzt

C1 und C2 schreiben nicht mehr. Beide Wege verweigern, statt still den falschen Stand zu setzen:

- `analyze._positions_lie` prüft für jedes Ständepaar, das `plan_undo` liest oder beschreibt (`before`/`after`, `before`/`current`, `after`/`current`), ob ein positionsbasierter Schlüssel in beiden dieselbe Ansicht meint. Verlässlich ist er nur bei gleicher Schlüsselmenge und gleichem Inhalt beziehungsweise gleichem, gesetztem Titel.
- `analyze._sections_lie` macht dasselbe eine Ebene tiefer über die Titelfolge der Sections – ohne die Ausnahme für Pfade, weil eine Section nie einen hat.
- `RemovedItem.anchor` merkt sich `(Anzahl der Sections, Titel)` der Section, aus der eine Karte stammt; `restore._anchor_holds` verweigert, bevor sie in eine fremde Section wandert. Die Prüfung sitzt beim Schreiben, weil dort nur das einzelne Element ankommt – anders als beim Undo, dessen Plan ohnehin vor jedem Schreibvorgang neu berechnet wird.

Belegt: 260 pytest-Fälle (251 vorher, neun neue, jeder zuerst rot gesehen) und sieben Prüfungen in `run_checks.run_positions`, die alle fünf gemessenen Schadensfälle sowie zwei Kontrollfälle gegen ein laufendes Home Assistant treiben.

Zwei Grenzen, beide bewusst und im Code vermerkt:

- Titellose Sections in einer umsortierten Ansicht bleiben unerkannt. Ein Titel ist alles, was es heute an Wiedererkennung gibt.
- Eine **hinzugefügte** pfadlose Ansicht führt zur Verweigerung, obwohl ihre Nachbarn noch stimmen. Die Regel ist an dieser Stelle strenger als nötig; Paket 2 hebt das auf.

W1 bis W4 sind unverändert offen. Die falschen Historientexte aus C1 ebenfalls: Verweigern hält das Schreiben an, es korrigiert nicht, was die Zeile erzählt.
