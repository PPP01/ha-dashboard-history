# Review der Doku vor der Veröffentlichung (2026-10-03)

Gelesen und gegen den Code abgeglichen: `README.md`, `FAQ.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, `docs/user-guide.md`, `docs/how-it-works.md`, `docs/limitations.md`, `docs/services.md`, `docs/ai-agents.md`, `docs/development.md`, `docker/README.md`, Issue-Templates, `manifest.json`, `hacs.json`, `services.yaml`, `strings.json`, Panel-Texte (`panel.js`, `panel/*.js`), Screenshots. Rein lesend; Befunde wo möglich empirisch (`analyze` in Plain-Python) nachgestellt. Das Journal (`plans/`, `reviews/`, `specs/`) wurde nicht durchgelesen.

## Kritisch

**K1 – Release und Doku passen nicht zusammen.** Die letzte Version ist v0.10.2 (2026-09-30, `manifest.json` ebenso). Seit dem Tag sind 40+ Commits dazugekommen, die Doku beschreibt sie aber schon: »Save this as another version« samt Rückfrage (#50/#51), »not recorded« / »Record it now« (#51), orange Zähler in der Dashboard-Liste (#49), sechster Sensor »Startup time« (#52), Neuladen nach Verbindungsverlust. Gegenprobe: `git show v0.10.2:…/panel.js` enthält »another version« nicht. Wer per HACS installiert, bekommt v0.10.2 und liest eine Anleitung für eine andere Version. `CHANGELOG.md` hat keinen Eintrag dafür (v0.8.0 spricht noch von »Five new sensors«). → Vor der Ankündigung v0.10.3 bzw. v0.11.0 mit Changelog-Eintrag veröffentlichen (Version in `manifest.json`).

**K2 – Die Limitations-Tabelle widerspricht sich und dem Code.** Nachgestellt mit `analyze.explain_change` / `plan_undo`:
- Zeile »Section renamed – `no card changes` – Refuses«: Der Eintrag lautet jetzt `section "X": the setting "title" was changed …`, Undo ist nicht blockiert.
- Zeile »Whole section deleted – Cards named one by one – Refuses«: Eintrag ist `section 2 was removed` (eine Zeile), Undo nicht blockiert. Dieselbe Aussage steht im Anhang (»the entry still lists the cards one by one«, Tabelle »Works, and works exactly«, letzte Zeile) und ist dort ebenfalls falsch.
- Zeile »Section added – Refuses«: Undo nicht blockiert.
- Zeile »Titled sections reordered – Refuses«: Eintrag `section "C" was moved`, Undo nicht blockiert.
- Dieselbe Tabelle führt weiter unten »Section added or deleted whole … Exact« und »Sections swapped … Exact« – die alten Zeilen (vor 2026-09-26) widersprechen also den neuen auf derselben Seite.
- Der Text nach der Tabelle »Refuses, honestly«: »A refusal is the correct outcome for all five« – die Tabelle hat drei Zeilen. Der Absatz »Writes something nobody asked for – four cases, plus one that was closed. A fifth was found …« ist nicht mehr nachvollziehbar (vier Fälle, einer geschlossen, einer »fifth«, danach noch ein zweiter »Closed«-Absatz).
→ Tabelle und Anhang gegen den heutigen Stand neu schreiben, nicht fortschreiben. Das ist die Seite, an der Forenleser Fehler finden und den Eindruck von »unzuverlässiger Doku« bekommen.

**K3 – `how-it-works.md` §2 »Why this is currently a problem« ist veraltet und widerspricht sich.** Der erste Punkt sagt, ein als Block verschobener Abschnitt werde als N Karten-Verschiebungen gemeldet, »still open« – der zweite Punkt im selben Absatz sagt, seit 2026-09-26 würden Sections als Blöcke gematcht. Empirisch: Vertauschen zweier Sections liefert `section 2 was moved` (eine Zeile). Der Abschnitt (Überschrift, Zeitform, Datumsangaben »narrowed on 2026-09-24«) liest sich wie ein Journal-Eintrag, nicht wie eine Erklärung.

**K4 – CONTRIBUTING/Issue-Templates versprechen mehr Anonymität, als der Download hält.** Gesagt wird: »anonymized diagnostics report … strictly nothing about what is actually inside your dashboards«; die Nutzer sollen die Datei in ein **öffentliches** GitHub-Issue ziehen. Der `data`-Block ist tatsächlich sauber (HMAC-IDs, Tagesdatum, `test_no_dashboard_name_survives_into_the_report`). Aber `report.py` sagt selbst, dass Home Assistant einen Umschlag darum legt (Systeminfo inkl. Zeitzone, **jede installierte Custom Integration**, Manifest) – außerhalb des Versprechens. Das steht nirgends in CONTRIBUTING, im Template oder im Bug-Template (»Drag the downloaded file in here«). → Satz ergänzen: Datei vor dem Posten ansehen; der HA-Umschlag listet Version, Zeitzone und installierte Custom Integrations.

## Wichtig

**W1 – Falsche Button-/Dialogtexte im User Guide** (gegen `panel.js` / `panel/*.js` geprüft):
- »Go back to this version« → Button heißt **»Back to this version«** (`panel/simple.js:437`).
- Replace-Dialog: »(•) Before this change / After this change« → **»State before this change« / »State after this change«** (auch im Screenshot `03-replace-dialog-light.png`).
- Der Replace-Dialog heißt in der Aktionsleiste »Replace the whole dashboard…«, im Guide ohne Auslassungspunkte – harmlos, aber uneinheitlich (README mit, Guide ohne).
- Der Guide enthält rohes HTML als Fließtext: `<summary><span class="glyph">&lt;/&gt;</span> Technical details</summary>` – für Leser Unsinn; ein Satz (»ein Aufklapper **Technical details**«) genügt.

**W2 – »Initial baseline« existiert nicht.** User Guide: »`v1.0.0` (Initial baseline): created the first time Dashboard History encounters a dashboard«. Im Code (`milestones.py::_async_floor_for`) bekommt die automatische v1.0.0 denselben Titel wie eine Tagesmarke (`day_title`, z. B. »3 September 2026«) und markiert den **ältesten** aufgezeichneten Stand, wenn das Dashboard beim Start noch keine Version hat. Beschreibung angleichen.

**W3 – »Six core modules« ist falsch, es sind sieben.** README (»Six core modules carry no `import homeassistant`«) und `docs/development.md` (»The following six modules«, Diagramm ohne `report.py`). `pyproject.toml` (Import-Contract), `CLAUDE.md` und `status.md` nennen sieben (`report.py` fehlt in der Aufzählung).

**W4 – README: »complete 14-situation empirical matrix«.** Die Tabelle in `limitations.md` hat 19 Zeilen (mit Zusatz-Zeilen »…and was edited« usw.). Zahl streichen oder korrigieren.

**W5 – Uneinheitliche Messwerte ohne Datierung.** Karten: »661 cards, 0 with an id« (FAQ) gegenüber »1,523 cards … eleven dashboards« (how-it-works, limitations); Sections: »0 of 80« (how-it-works) gegenüber »0 of 101« (limitations); Dashboards der Messinstallation 11 / 70 / 68 / 98 (`FAQ`, `CHANGELOG`, Memory). Vermutlich verschiedene Zeitpunkte bzw. oberste Ebene gegenüber verschachtelt – aus der Doku nicht ersichtlich. Entweder je Aussage Datum/Bezug nennen oder auf einen Stand vereinheitlichen.

**W6 – Verweise auf nie getaggte Versionen.** FAQ und CHANGELOG nennen v0.7.1 und v0.8.0; Tags/Releases gibt es nur für v0.7.0 und v0.8.1 (`git tag`). Ein Leser, der »Until v0.8.0 …« nachschlägt, findet kein Release.

**W7 – Interna-Nähe in Nutzerdoku.** Datierte Journal-Sätze (»Since 2026-09-25 …«, »Fixed 2026-09-24 … `_SECTION_REFUSAL` fired …«, `_sections_lie`, »Decision 26 in the design journal«) und Issue-Nummern stehen quer durch `how-it-works.md` und `limitations.md`. Für eine Forenankündigung wirkt das wie ein Changelog, nicht wie Doku; außerdem sind es die Stellen, die am schnellsten veralten (K2, K3).

## Hinweis

- **README-Lücken:** Sensoren (jetzt sechs) und der Diagnosebericht kommen in README, User Guide und `services.md` nicht vor, nur im CHANGELOG und in CONTRIBUTING. Der orange Zähler/Streifen der Dashboard-Liste (#49, im Screenshot zu sehen) fehlt im Abschnitt »Current state indicators«.
- **`services.md`:** Die Felder `override_unrecorded_state`, `allow_parking`, `limit`, `name` (bei `retitle_version`/`remove_version`) und `expected_parked` sind nicht erwähnt. Die 16 Aktionen stimmen mit `services.yaml`/`services.py` überein; Beispiel 3 (`restore_state` bringt ein gelöschtes Dashboard zurück) stimmt laut `services.yaml`.
- **`development.md` §5:** »generated automatically using Playwright« – das Skript nutzt `google-chrome` headless (`shutil.which("google-chrome")`) und `websockets`, nicht Playwright; und die Chrome-Voraussetzung fehlt.
- **Version-Floor 2024.11:** Nur gegen 2026.8.3 getestet (Docker). Die Aussage »2024.11 or newer« ist abgeleitet, nicht geprüft. Entweder so benennen (»nicht darunter getestet«) oder einmal gegen 2024.11 laufen lassen.
- **»mathematical proofs« / »strict mathematical proof«** (README, how-it-works): Überhöhung; »exakter Nachweis über Byte-Gleichheit« trägt genauso und lädt weniger zum Widerspruch ein. Außerdem fehlt in how-it-works, dass vor den vier Durchgängen jetzt Sections gematcht werden und Pass 3 um Text-Umbenennung und Entity-Tausch ergänzt wurde (v0.10.0/v0.10.1).
- **HACS-Rendering (nicht geprüft):** `render_readme: true` mit `<picture>`/`<source>` und relativen Bildpfaden – HACS zeigt die README in HAs Markdown-Renderer; ob Bilder dort erscheinen, vor der Ankündigung einmal in HACS ansehen.
- **FAQ-Ton:** Absatz »Mine were not! :-(« enthält »shit«, typografische Apostrophe und einen ungewrappten Block (der Rest ist umbrochen). Nicht falsch, aber für eine Forenankündigung bewusst entscheiden. Ebenso: persönliche Messwerte (Proxmox, 7403 Commits, 8244 Zeilen) stehen in einem öffentlichen Repo – `CLAUDE.md` sagt »no details about the installation it's tried on«; Zahlen ohne Hostdetails sind vermutlich gemeint, bitte bewusst gegenlesen.
- **FAQ:** Aussage, HAs Backup nehme `dashboard_history` mit (Ausschlussliste) – nicht gegen HA geprüft.
- **Verwaiste Bilder:** neun Dateien in `docs/images/` sind nirgends verlinkt (`03-restore-dialog-light`, `03c-put-back-dialog-*`, `07-restore-dialog-dark`, `07c-…`, `09-narrow-*`, `10-narrow-*`, `11-docked-sidebar-900`).
- **`status.md`:** Kopfzeile »Stand: 2026-09-29«, Inhalt reicht bis 2026-10-02 (Journal, deutsch, nicht Nutzerdoku).
- **In Ordnung befunden:** alle relativen Links und Anker in den Markdown-Dateien; 16 Aktionen; Admin-Pflicht; 10-s-Entprellung; `/config/dashboard_history`; 25 Einträge pro Seite; Option »Mark the state at the end of each day«; Panel-Texte »Not in the sidebar (N)«, »Deleted (N)«, »Bring it back«, »Forget for good«, »Record it now«, »same state as now«, »Right now«; Screenshots entsprechen der aktuellen Oberfläche.

## Urteil

**Umsetzbar nach Korrekturen.** Vor der Ankündigung zwingend: K1 (Release + Changelog), K2/K3 (Abschnitts-Aussagen in `limitations.md` und `how-it-works.md` auf den heutigen Stand), K4 (Hinweis zum HA-Umschlag), dazu die Textkorrekturen aus W1–W4. Der Rest kann danach oder bewusst bleiben.

## Nachtrag 2026-10-04

- **K1 entfällt:** Das Release mit dem aktuellen Stand war ohnehin geplant (v0.11.0); die Doku beschreibt den Stand, der veröffentlicht wird. Übrig blieb nur der fehlende CHANGELOG-Eintrag.
- **Umgesetzt (uncommittet):** K2 (Tabelle und Anhang in `limitations.md` neu gegen den Code nachgestellt), K3 (`how-it-works.md` §2 als »How sections are handled« neu), K4 (Hinweis zum HA-Umschlag in `CONTRIBUTING.md` und beiden Issue-Templates), W1–W4, CHANGELOG v0.11.0, `manifest.json` auf 0.11.0, dazu das Playwright/Chrome-Detail aus den Hinweisen und ein Absatz zum orangen Zähler im User Guide.
- **Bewusst offen:** W5 (uneinheitliche Messwerte), W6 (nie getaggte v0.7.1/v0.8.0), W7 (Journal-Datierungen in der Nutzerdoku), `services.md`-Felder, README-Hinweis auf Sensoren/Diagnosebericht, FAQ-Ton, verwaiste Bilder, HACS-Rendering.
