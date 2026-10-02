# Review: Aufzeichnungslücke und »Record it now«

Geprüft wurde `main..unrecorded-live-state` mit den Commits `83b6ab6` und
`9dfdb34`. Gelesen wurden `CLAUDE.md`, der Status-Eintrag vom 2026-10-01 und
die Entscheidungen 7 und 23. Die Änderungen halten die wichtigen Grenzen ein:
Der neue WebSocket-Weg läuft über den vorhandenen Admin-Wrapper, Git-Arbeit
bleibt im Executor beziehungsweise im bestehenden Capture-Pfad, `analyze/`
bleibt HA-frei, und ein Verlaufseintrag braucht nach Entscheidung 7 kein
`confirm`.

## Kritisch

Keine Befunde.

## Wichtig

### Ein leerer Verlauf hat trotz Live-Stand keinen Reparaturweg

**Fundstelle:** `custom_components/dashboard_history/operations.py:605-610`,
`custom_components/dashboard_history/panel.js:3830-3833,4371-4377`,
`custom_components/dashboard_history/panel/simple.js:250-265`.

**Beschreibung:** `unrecorded` verlangt neben einem lesbaren Live-Stand einen
gerenderten neuesten Eintrag. Ist die allererste Aufzeichnung fehlgeschlagen,
ist `rendered` leer und das Feld deshalb `false`. Advanced zeigt dann nur »No
changes recorded for this dashboard.«. Simple zeigt »Save this as a version«;
der Klick reicht jedoch `undefined` weiter und `_createVersion()` kehrt ohne
Aktion zurück.

**Konsequenz:** Nach einem Start-Rennen oder einem Defekt bei der ersten
Erfassung besteht exakt die Lücke, für die der Knopf gedacht ist, aber es gibt
weder »Record it now« noch eine funktionierende Alternative. Der Nutzer muss
auf einen späteren Save, Neustart oder Abgleich warten.

**Vorschlag:** Einen bekannten, lesbaren Live-Stand ohne Historieneintrag als
aufzuzeichnenden Zustand modellieren (etwa eigenes Serverfeld oder
`unrecorded` auch ohne `rendered`) und beide Modi mit dem Record-Knopf
versorgen. Ein Test soll den leeren Verlauf plus vorhandene Konfiguration
durchspielen.

**Nachweis:** gelesen; die Rückgabe und der wirkungslose Button folgen direkt
aus den genannten Guards. Dieser Fall fehlt in den neuen Tests.

### Eine aktive Suche versteckt den Reparaturweg

**Fundstelle:** `custom_components/dashboard_history/panel.js:3841-3846`,
`custom_components/dashboard_history/panel/simple.js:250-256`.

**Beschreibung:** Im Advanced-Modus rendert der Query-Zweig ausschließlich
Such-Pin und Trefferzeilen; die »Right now«-Box mit `unrecorded` wird nicht
eingehängt. Im Simple-Modus beendet ein versionsloses Suchergebnis die
Darstellung direkt mit »No version matches.«. Die Anzeige für die Lücke und
»Record it now« fehlen damit in beiden Modi.

**Konsequenz:** Wer gerade sucht, kann eine erkannte Aufzeichnungslücke nicht
beheben, ohne die Suche erst manuell zu verlassen. Das widerspricht der
Anforderung, dass der Knopf bei `unrecorded` den Save-Button in beiden Modi
ersetzt.

**Vorschlag:** Die Zustandsbox unabhängig von gefilterten Zeilen darstellen
oder wenigstens den Record-Knopf im Such-Leerzustand ergänzen. Tests für
Advanced- und Simple-Suche mit `unrecorded: true` hinzufügen.

**Nachweis:** gelesen; die Query-Returns enthalten keinen Aufruf der
Right-now-Renderer.

### Der Erfolgswert kann bei einer gleichzeitigen Speicherung den falschen Live-Stand bestätigen

**Fundstelle:** `custom_components/dashboard_history/operations.py:642-659`,
`custom_components/dashboard_history/capture.py:168-173`.

**Beschreibung:** `async_record_now` liest `live` vor dem Aufruf von
`capture.async_capture()`. Capture liest die Konfiguration danach nochmals,
außerhalb seines Schreib-Locks. Ändert jemand das Dashboard in diesem Fenster,
kann Capture B aufzeichnen, während die Abschlussprüfung B mit dem zuvor
gelesenen A vergleicht. Dann meldet der Befehl fälschlich `{"recorded":
false}`. Umgekehrt kann A erfolgreich geprüft werden, obwohl der Live-Stand
inzwischen B ist und schon wieder eine Lücke besteht.

**Konsequenz:** Während »Record it now« läuft, speichert ein zweiter Browser
oder der Editor. Trotz erfolgreich erzeugtem Eintrag sieht die Person den
Fehlerbanner mit Log-Verweis; im umgekehrten Ablauf sieht sie Erfolg, die
anschließende Seite enthält aber weiterhin »not recorded«. Das trifft gerade
den explizit zu prüfenden Nebenläufigkeitsfall und macht das Ergebnis des neuen
API-Felds nicht zuverlässig.

**Vorschlag:** Nach Capture die Live-Konfiguration erneut lesen und den
neuesten Eintrag gegen diesen Stand prüfen; bei einem Wechsel während des
Vorgangs entweder den aktuellen Stand erneut aufzeichnen/prüfen oder klar als
nicht stabilen Versuch antworten. Mindestens ein kontrollierter Test muss den
Wechsel zwischen erstem Lesen und Capture abdecken.

**Nachweis:** gelesen; der Ablauf folgt direkt aus den zwei getrennten
`async_get_all_configs`-Lesungen. Der vorhandene Integrationstest verändert
die Konfiguration nicht während `record_now`.

### Ein fehlgeschlagener Versuch hinterlässt einen Event-Waiter und verschluckt danach ein Update

**Fundstelle:** `custom_components/dashboard_history/panel.js:1000-1006`,
`custom_components/dashboard_history/panel.js:1043-1053`,
`custom_components/dashboard_history/panel.js:2832-2853`.

**Beschreibung:** `_recordNow()` erzeugt immer `const recorded =
this._recorded()`. Antwortet der Server mit `recorded: false`, wird dieses
Promise weder abgewartet noch abgeräumt; `this._awaiting` bleibt bis zum
Drei-Sekunden-Timer gesetzt. Das nächste `dashboard_history_updated` löst
deshalb Zeile 1000 aus, wird als eigene Aktion behandelt und kehrt ohne
`_refreshQuietly()` zurück. Der Filter, ob das Ereignis überhaupt das gewählte
Dashboard betrifft, kommt erst danach.

**Konsequenz:** Nach einem echten Fehler (etwa `index.lock`) kann eine
unabhängige Speicherung oder ein Abgleich innerhalb von drei Sekunden die
Anzeige nicht aktualisieren. Bei einem zweiten Klick kann zusätzlich der alte
Timer den neuen Waiter mit `this._awaiting = null` vorzeitig entfernen. Das ist
ein kurzer, aber realer Stale-UI-Zustand genau im Fehlerpfad, den die Änderung
sichtbar machen soll.

**Vorschlag:** Den Waiter bei `recorded: false` explizit und nur dann
abbrechen, wenn er noch derselbe Waiter ist; `_recorded()` sollte dafür eine
Cancel-Funktion oder einen tokengebundenen Cleanup liefern. Test: fehlender
Erfolg, dann ein fremdes und ein eigenes `dashboard_history_updated` vor Ablauf
des Timers; beide dürfen keinen fremden Waiter verbrauchen oder einen nötigen
Refresh verlieren.

**Nachweis:** gelesen; die neuen Paneltests stubben `_recorded` als sofort
erfülltes Promise und können den echten Timer-/Event-Zustand daher nicht
beobachten.

## Hinweis

### Die neue Serveroperation hat außerhalb der Docker-Prüfung keine gezielte Testebene

**Fundstelle:** `custom_components/dashboard_history/operations.py:621-659`,
`tests/integration/run_checks.py:4526-4588`,
`tests/test_panel_behaviour.py:5214-5309`.

**Beschreibung:** Die Integration-Prüfung deckt den normalen Erfolg, den
gesperrten Schreibpfad und die Meldung ab. Die pytest-Tests prüfen hingegen
nur die gerenderte, gemockte WebSocket-Antwort; sie rufen
`async_record_now` nicht auf. Damit bleiben insbesondere gelöschtes Dashboard,
fehlender Capture-Recorder, kein Verlauf, Standard-Dashboard sowie die oben
beschriebene Nebenläufigkeit allein implizit durch den Code abgedeckt.

**Konsequenz:** Die eigentliche neue Operation kann in einer HA-spezifischen
Randbedingung regressieren, ohne dass der schnelle Testlauf sie findet. Die
UI-Tests mit Namen wie »recording by hand asks …« testen nur den Request des
Panels, nicht die Serverantwort oder das Recording.

**Vorschlag:** Einen kleinen HA-freien beziehungsweise mit schmalem Fake-Hass
laufenden Test ergänzen, ähnlich den vorhandenen Integrations-Hilfstests, der
die Rückgaben `false` für fehlendes Live-Dashboard/keinen Verlauf und `true`
für einen bereits aktuellen Standard-Dashboard-Eintrag sowie einen
Konfigurationswechsel während des Aufrufs prüft. Den Event-Waiter separat mit
echtem Timer/Callback testen.

**Nachweis:** gelesen. Reproduziert wurde die relevante geänderte
pytest-Teilmenge: `634 passed in 12.07s` für `test_analyze.py`,
`test_analyze_interface.py` und `test_panel_behaviour.py`. Der angeforderte
Gesamtlauf `python3 -m pytest tests/ -q -p no:cacheprovider` überschritt in
dieser Review-Umgebung dreimal die 30-Sekunden-Ausgabegrenze und lieferte kein
Endergebnis; `tests/integration/run_checks.py` wurde auftragsgemäß nicht
ausgeführt.

## Urteil

**Mergebar nach Korrekturen.** Die beabsichtigte Regel ist in Advanced- und
Simple-Modus vollständig angeschlossen: Serverfeld statt Panel-Nachbildung,
Paging-Neustart aktualisiert das Feld, Suche behält die Antwort der ersten
Seite, und gelöschte beziehungsweise nicht lesbare Dashboards werden nicht
fälschlich als Lücke markiert. Die zwei Nebenläufigkeits-/Event-Funde sollten
vor dem Merge behoben werden, weil sie den neuen Reparaturweg gerade bei einem
gleichzeitigen Speichern oder nach seinem Fehler widersprüchlich machen. Der
leere Verlauf und die Suche müssen zudem den versprochenen Reparaturweg
tatsächlich erreichbar machen.

ENDE DES REVIEWS
