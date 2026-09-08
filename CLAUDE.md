# ha-dashboard-history

Home-Assistant-Integration: Änderungshistorie und Wiederherstellung für Lovelace-Dashboards. Soll später über HACS veröffentlicht werden, wird zunächst nur auf der eigenen Anlage erprobt.

**Vor der Arbeit lesen — beide:**

- `docs/superpowers/specs/2026-08-30-dashboard-history-design.md` — der Entwurf und die *Begründungen*. Bindend bei Widersprüchen.
- `docs/superpowers/plans/2026-08-30-dashboard-history.md` — die Umsetzung in acht Tasks, mit vollständigem Code und Tests.

Umsetzung mit `superpowers:subagent-driven-development`.

## Sprache

Die Regel ist **das Publikum**, nicht die Art des Dokuments: Wer nach außen liest, liest Englisch.

- **Englisch — alles, was ein fremder Mitwirkender je zu sehen bekommt.** Code, Kommentare, Docstrings, Dienstnamen, Log-Meldungen, README **und Commit-Botschaften**. Dazu jede Fläche auf GitHub: Issues, Pull Requests, Release Notes, Repository-Beschreibung, Labels.
  - **Commit-Botschaften waren bis 2026-09-02 Deutsch** — 51 davon liegen öffentlich und bleiben stehen. Sie werden **nicht** umgeschrieben: Es gibt ein Release `v0.2.0`, an dem HACS hängt. Eine Historie, die an einem Punkt die Konvention wechselt, ist ehrlicher als eine nachträglich geglättete. Der Grund für die Umstellung: In diesem Projekt tragen die Commit-Bodys das *Warum*, und in `git blame` ist das die einzige Stelle, an der ein Mitwirkender es findet.
- **Deutsch — was nach innen gehört.** Die Kommunikation mit dem Nutzer, und das Entwurfsjournal unter `docs/superpowers/` (Spec und Pläne). Mit echten Umlauten (ä ö ü ß) und deutschen Anführungszeichen »…«.
  - Das ist eine bewusste Ausnahme vom Publikums-Prinzip und **in der README ausgeschildert**, damit niemand davorsteht und rätselt. Die Begründungen leben von ihrer Formulierung; 6909 Zeilen davon zu übertragen wäre keine mechanische Aufgabe, und die README ist die Vordertür, nicht die Spec.
- **Die globale Gedankenstrich-Regel des Entwicklers gilt hier nicht.** Geviert- und Halbgeviertstrich sind beide in Ordnung; ein vorhandener ist kein Anlass für eine Korrektur. Keine Zeit darauf verwenden.

## Harte Regeln

Diese stehen so in der Spec und sind nicht verhandelbar:

- **Kein Systemaufruf von `git`.** Ausschließlich `dulwich`. Ob ein `git`-Programm existiert, unterscheidet sich zwischen HA OS, Container, Core und Supervised. Gemessen sind es ohnehin nur 15 ms Unterschied je Speichervorgang — bei doppelter Verhaltensfläche.
- **Keine Home-Assistant-Interna abfangen oder ersetzen.** Kein Monkey-Patching von WebSocket-Befehlen oder Diensten. Das träfe bei einer Veröffentlichung alle Nutzer gleichzeitig.
- **Nichts blockiert den Start von Home Assistant.** Fehler beim Erfassen werden protokolliert und verschluckt. Eine kaputte Historie ist ärgerlich, ein kaputter HA-Start nicht.
- **`yaml_io.py`, `analyze.py`, `restore.py` und `versions.py` bleiben Home-Assistant-frei.** Kein `import homeassistant` darin — sie sind das Herz und müssen in reinem pytest prüfbar bleiben.
- **Blockierende Arbeit gehört in einen Executor** (`hass.async_add_executor_job`). Ein Commit dauert rund 30 ms.
- **Nichts wird ohne Vorschau geschrieben.** Jeder Dienst, der einen *Dashboard-Stand* schreibt, verlangt `confirm: true` und liefert sonst nur den Diff. Ausgenommen sind `describe` und `create_version`: Das eine schreibt eine Notiz, das andere einen Tag — kein Dashboard ändert sich, und ein Bestätigungsdialog davor wäre Zeremonie ohne Schutzwirkung (Entscheidung 7 der Spec, Grenze vom 2026-08-31).
- **Zurückgeholt wird nur Verschwundenes, nicht Bearbeitetes.** Der Grund steht in Entscheidung 4 der Spec: Lovelace-Karten haben keine Kennung (nachgezählt: 661 Karten, 0 mit `id`). Additive Rücknahme ist eindeutig, ersetzende nicht.

## Tests

```bash
python3 -m pytest tests/ -v
```

Die vier Home-Assistant-freien Module laufen ohne laufende Installation. `tests/conftest.py` legt das Paketverzeichnis auf `sys.path`, damit `import analyze` flach funktioniert, ohne die HA-importierende `__init__.py` auszuführen.

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

Ein dritter Weg, für das Wenige, das zwischen den beiden anderen liegt:

```bash
docker exec -i dashboard-history-test python3 - < tests/integration/run_day_marks.py
```

Er läuft **im** Container, wo `homeassistant` existiert, aber **ohne** laufende
Instanz — für Code, den `pytest` nicht importieren kann und den `run_checks.py`
nicht auslösen kann, weil kein API einen Commit rückdatiert. Er baut ein echtes
Repository und verstellt allein die Uhr an der Stelle, an der die
Kalenderrechnung sie liest. Nur so weit tragfähig, wie das gefälschte Stück
klein bleibt; wächst es, ist der Fall bei `run_checks.py` besser aufgehoben.
Über `stdin`, weil nur `custom_components/` in den Container gemountet ist.

⚠️ **Eine Anlage, an der etwas hängt, ist kein Testgerät.** Zwei Regeln daraus, beide teuer gelernt: **niemals während eines HA-Neustarts anpollen** — HAs IP-Ban-System sperrt sonst den eigenen Zugang — und **kein Test darf über ein Präfix löschen**, sondern nur über den genau benannten eigenen Schlüssel. Was dabei einmal schiefging, steht im Nachtrag vom 2026-09-01 im Plan.

Umgebung: HA 2026.8.3, Container-Python 3.14.6, Entwicklungsrechner Python 3.12.3.

## Git

- Commit-Format: **Englisch** (siehe »Sprache«). Subject im Imperativ, erster Buchstabe groß, max. 50 Zeichen. Leerzeile. Body max. 72 Zeichen pro Zeile, begründet das *Warum*. Abschluss mit `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- Branch ist `main`, Remote ist `origin` (öffentlich auf GitHub). **Geschoben, getaggt und veröffentlicht wird nur nach ausdrücklicher Ansage des Nutzers.** Das Repository ist öffentlich lesbar: keine Pfade fremder Rechner, keine Angaben über die Anlage, an der erprobt wird, keine Zugangsdaten — auch nicht in Testdaten oder Kommentaren.
