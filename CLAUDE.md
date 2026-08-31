# ha-dashboard-history

Home-Assistant-Integration: Änderungshistorie und Wiederherstellung für Lovelace-Dashboards. Soll später über HACS veröffentlicht werden, wird zunächst nur auf der eigenen Anlage erprobt.

**Vor der Arbeit lesen — beide:**

- `docs/superpowers/specs/2026-08-30-dashboard-history-design.md` — der Entwurf und die *Begründungen*. Bindend bei Widersprüchen.
- `docs/superpowers/plans/2026-08-30-dashboard-history.md` — die Umsetzung in acht Tasks, mit vollständigem Code und Tests.

Umsetzung mit `superpowers:subagent-driven-development`.

## Sprache

- **Code, Kommentare, Docstrings, Dienstnamen, Log-Meldungen und README: Englisch.** Alles, was ein fremder Mitwirkender je zu sehen bekommt. Das Projekt soll veröffentlichungsfähig sein.
- **Spec, Plan, Commit-Botschaften und die Kommunikation mit dem Nutzer: Deutsch**, mit echten Umlauten (ä ö ü ß) und deutschen Anführungszeichen »…«.
- **Die globale Regel zum Gedankenstrich gilt hier nicht.** Geviert- und Halbgeviertstrich sind beide in Ordnung; ein vorhandener ist kein Anlass für eine Korrektur. Keine Zeit darauf verwenden.

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

## Live erproben

Die eigene Home-Assistant-Installation liegt unter `/path/to/home-assistant/` (per SSHFS gemountet, Änderungen wirken sofort). Zum Erproben wird die Integration über HACS als eigenes Repository installiert: *HACS → Eigene Repositories* → `https://github.com/PPP01/ha-dashboard-history`, Kategorie Integration. Damit landet sie auf demselben Weg in `custom_components/`, den später jeder Nutzer geht.

**Kein Symlink.** Der Mount ist SSHFS, und ein Symlink würde dort aufgelöst, wo Home Assistant läuft — den Pfad dieses Repositorys gibt es auf der Anlage nicht. Nachgeprüft: Unter dem Mount ist kein einziger Symlink sichtbar, und das Anlegen scheitert bereits am SFTP-Dienst.

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

⚠️ **Das ist eine echte Anlage.** Daran hängt Haustechnik. Vor Live-Schritten die Merker in `/path/to/home-assistant/.claude/lessons.md` lesen — insbesondere: **niemals während eines HA-Neustarts anpollen** (IP-Ban-System), und `custom_components/` ist dort nicht versioniert.

Umgebung: HA 2026.8.3, Container-Python 3.14.6, Entwicklungsrechner Python 3.12.3.

## Git

- Commit-Format: Subject im Imperativ, erster Buchstabe groß, max. 50 Zeichen. Leerzeile. Body max. 72 Zeichen pro Zeile, begründet das *Warum*. Abschluss mit `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- Branch ist `main`. Kein Remote — auf GitHub geschoben wird erst nach ausdrücklicher Ansage des Nutzers.
