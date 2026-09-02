# ha-dashboard-history

Home-Assistant-Integration: Änderungshistorie und Wiederherstellung für Lovelace-Dashboards. Soll später über HACS veröffentlicht werden, wird zunächst nur auf der eigenen Anlage erprobt.

**Vor der Arbeit lesen — beide:**

- `docs/superpowers/specs/2026-08-30-dashboard-history-design.md` — der Entwurf und die *Begründungen*. Bindend bei Widersprüchen.
- `docs/superpowers/plans/2026-08-30-dashboard-history.md` — die Umsetzung in acht Tasks, mit vollständigem Code und Tests.

Umsetzung mit `superpowers:subagent-driven-development`.

## Sprache

- **Code, Kommentare, Docstrings, Dienstnamen, Log-Meldungen und README: Englisch.** Alles, was ein fremder Mitwirkender je zu sehen bekommt. Das Projekt soll veröffentlichungsfähig sein.
- **Spec, Plan, Commit-Botschaften und die Kommunikation mit dem Nutzer: Deutsch**, mit echten Umlauten (ä ö ü ß) und deutschen Anführungszeichen »…«.
- **Die globale Gedankenstrich-Regel des Entwicklers gilt hier nicht.** Geviert- und Halbgeviertstrich sind beide in Ordnung; ein vorhandener ist kein Anlass für eine Korrektur. Keine Zeit darauf verwenden.

## Harte Regeln

Diese stehen so in der Spec und sind nicht verhandelbar:

- **Kein Systemaufruf von `git`.** Ausschließlich `dulwich`. Ob ein `git`-Programm existiert, unterscheidet sich zwischen HA OS, Container, Core und Supervised. Gemessen sind es ohnehin nur 15 ms Unterschied je Speichervorgang — bei doppelter Verhaltensfläche.
- **Keine Home-Assistant-Interna abfangen oder ersetzen.** Kein Monkey-Patching von WebSocket-Befehlen oder Diensten. Das träfe bei einer Veröffentlichung alle Nutzer gleichzeitig.
- **Nichts blockiert den Start von Home Assistant.** Fehler beim Erfassen werden protokolliert und verschluckt. Eine kaputte Historie ist ärgerlich, ein kaputter HA-Start nicht.
- **`yaml_io.py`, `analyze.py` und `restore.py` bleiben Home-Assistant-frei.** Kein `import homeassistant` darin — sie sind das Herz und müssen in reinem pytest prüfbar bleiben.
- **Blockierende Arbeit gehört in einen Executor** (`hass.async_add_executor_job`). Ein Commit dauert rund 30 ms.
- **Nichts wird ohne Vorschau geschrieben.** Jeder verändernde Dienst verlangt `confirm: true` und liefert sonst nur den Diff.
- **Zurückgeholt wird nur Verschwundenes, nicht Bearbeitetes.** Der Grund steht in Entscheidung 4 der Spec: Lovelace-Karten haben keine Kennung (nachgezählt: 661 Karten, 0 mit `id`). Additive Rücknahme ist eindeutig, ersetzende nicht.

## Tests

```bash
python3 -m pytest tests/ -v
```

Die drei Home-Assistant-freien Module laufen ohne laufende Installation. `tests/conftest.py` legt das Paketverzeichnis auf `sys.path`, damit `import analyze` flach funktioniert, ohne die HA-importierende `__init__.py` auszuführen.

Einige Fälle prüfen gegen **echte** Dashboards — das ist der Unterschied zwischen vier erfundenen Karten und einigen hundert gewachsenen. Wo die liegen, steht nicht im Repository: Entweder in `DASHBOARD_HISTORY_REAL_STORAGE` oder in der nicht versionierten Datei `tests/.real-storage`, die `conftest.py` liest. Ohne beides überspringen diese Fälle sich **sichtbar** (`140 passed, 3 skipped`) statt still durchzulaufen.

## An einer echten Anlage erproben

Installiert wird über HACS als eigenes Repository: *HACS → Eigene Repositories* → `https://github.com/PPP01/ha-dashboard-history`, Kategorie Integration. Damit landet die Integration auf demselben Weg in `custom_components/`, den später jeder Nutzer geht — und nicht auf einem Sonderweg, den nur der Entwickler hat.

**Kein Symlink aus dem Arbeitsbaum.** Wird die Anlage über einen Netz-Mount erreicht (SSHFS und Ähnliches), lässt sich dort keiner anlegen, und er würde ohnehin auf der Seite aufgelöst, auf der Home Assistant läuft — den Pfad dieses Repositorys gibt es dort nicht.

Für Aktualisierungen braucht HACS echte Releases mit aufsteigender Versionsnummer. Ein Vorabversions-Suffix sortiert nach Semver **unterhalb** der Grundversion und wird nicht als Aktualisierung erkannt.

### Zuerst lokal prüfen

Vor jedem Live-Schritt gehört die Prüfung in die Wegwerf-Instanz:

```bash
docker compose -f docker/compose.yaml up -d
python3 tests/integration/run_checks.py
```

Sie treibt ein echtes Home Assistant 2026.8.3 über HTTP und WebSocket und
erreicht damit die Module, die `pytest` strukturell nicht erreicht — dort lag
jeder bisher gefundene Fehler. Aufbau und die zwei Fallen dabei:
`docker/README.md`. Konfiguration und Token liegen **außerhalb** des Repos.

⚠️ **Eine Anlage, an der etwas hängt, ist kein Testgerät.** Zwei Regeln daraus, beide teuer gelernt: **niemals während eines HA-Neustarts anpollen** — HAs IP-Ban-System sperrt sonst den eigenen Zugang — und **kein Test darf über ein Präfix löschen**, sondern nur über den genau benannten eigenen Schlüssel. Was dabei einmal schiefging, steht im Nachtrag vom 2026-09-01 im Plan.

Umgebung: HA 2026.8.3, Container-Python 3.14.6, Entwicklungsrechner Python 3.12.3.

## Git

- Commit-Format: Subject im Imperativ, erster Buchstabe groß, max. 50 Zeichen. Leerzeile. Body max. 72 Zeichen pro Zeile, begründet das *Warum*. Abschluss mit `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- Branch ist `main`, Remote ist `origin` (öffentlich auf GitHub). **Geschoben, getaggt und veröffentlicht wird nur nach ausdrücklicher Ansage des Nutzers.** Das Repository ist öffentlich lesbar: keine Pfade fremder Rechner, keine Angaben über die Anlage, an der erprobt wird, keine Zugangsdaten — auch nicht in Testdaten oder Kommentaren.
