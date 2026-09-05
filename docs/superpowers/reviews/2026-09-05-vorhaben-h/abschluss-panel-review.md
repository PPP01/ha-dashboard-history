# Abschluss-Review: die Panel-Hälfte von `vorhaben-h`

Gelesen ausschließlich lesend im Worktree `ha-dashboard-history-h`, Branch
`vorhaben-h`, Stand `2fd5223`. Grundlage: `final-panel.diff`, die Dateien in
ihrer Endfassung, die Spec (`docs/superpowers/specs/2026-08-30-…`) und
punktuell Aufgabe 8 des Plans.

`python3 -m pytest tests/test_panel_behaviour.py tests/test_panel_assets.py -q`
→ **45 passed**. Jede Aussage unten, die eine Abfolge behauptet, ist im Node in
genau dieser Abfolge nachgestellt worden; die Ausgaben stehen jeweils dabei.

---

## Was geprüft wurde und in Ordnung ist

Damit das Fix-Budget nicht auf Erfundenes geht, zuerst die harten Regeln, die
**halten**:

- **Nichts über die eigene Anlage im Repository.** Der Diff enthält keinen
  fremden Pfad, keine IP, kein Token, keinen Dashboard-Namen aus einem echten
  System. Die Testschlüssel heißen `dash`, `a-dash`, `b-dash`. Geprüft mit
  Mustern über alle `+`-Zeilen für `/home/`, `/config/`, `C:\`, `sshfs`,
  `192.168.`, `10.x`, `.local`, `nabu casa`, `token`, `password`, `secret`,
  `api_key`.
- **Alles Lesbare ist Englisch.** Keine deutsche Zeile in JS oder Tests; die
  einzigen Nicht-ASCII-Zeichen sind `…`, `—`, `·`, `✎` in Oberflächentexten.
- **Additive Rücknahme.** Nichts in dieser Hälfte bietet eine ersetzende
  Rücknahme an; `_restoreItem` bleibt bei `previous` + `position`.
- **`returnValue` leckt nicht.** Alle vier Dialoge setzen `returnValue = ""`
  vor `showModal()`; abgebrochen wird nichts geschrieben; ein unterdrücktes
  Keep-Angebot schickt keine Nutzlast (`_keepChoice()` wird nur bei
  `keepable` überhaupt gerufen). Alle drei sind zusätzlich durch Tests
  gedeckt, die fallen können.
- **Escaping.** Jede Interpolation von Server- oder Nutzerdaten läuft durch
  `escape()`. Kein XSS-Pfad gefunden — auch nicht über `_alreadyNamed`, dessen
  Rückgabe an beiden Verwendungsstellen erneut escaped wird.
- **`panel.py` trägt die Teilung mit.** `_PARTS.rglob("*.js")` nimmt die drei
  neuen Dateien automatisch in Fingerabdruck und statischen Pfad; kein
  Cache-Loch.
- **Das Adressieren über Revisionen ist konsequent durchgezogen.** `_changeAt`
  fragt beide Listen, `_madeSince` gibt `null` statt einer geratenen Zahl,
  `_renderSetBack` verträgt einen Vorgänger außerhalb des Fensters. Der eine
  Ort, an dem noch eine Position steht — `this._changes[1].revision` im
  „Bring it back"-Banner — war vorher schon so und ist dort richtig.

---

## Critical

### C1 — Eine Vorschau gilt für das Dashboard, das beim **Bestätigen** ausgewählt ist

`panel.js:1061–1099` (`_restoreItem`, `_restoreState`, `_undoChange`),
`panel.js:1013–1054` (`_forget`), `panel.js:983–991` (`_createVersion`).

Die Anfrage-Closures lesen `this._selected` **zum Aufrufzeitpunkt**:

```
_undoChange(revision) {
  this._confirm("Undo this change", (confirm) => [
    "undo_change", { dashboard: this._selected, revision, confirm },
  ]);
}
```

`request(false, null)` läuft sofort — mit dem richtigen Dashboard.
`request(true, keep)` läuft **nachdem der Dialog geschlossen wurde**. Zwischen
Klick und `showModal()` ist die Seitenleiste voll bedienbar: Der Dialog ist
noch nicht offen, es gibt keinen Hinweis, dass gleich einer kommt, und die
einzige Rückmeldung ist ein kleines „working…" in der Leiste. `_select` setzt
`this._selected` sofort synchron.

Abfolge, im Node nachgestellt:

1. `kitchen` ausgewählt, Zeile aufgeklappt, „Back to the state after this
   change" geklickt → Vorschau `{dashboard: "kitchen", revision: "b",
   confirm: false}` geht raus.
2. Während die Vorschau unterwegs ist, klickt die Person `garden` in der
   Seitenleiste.
3. Kitchens Vorschau kommt an, der Modal öffnet — mit **Kitchens** Diff und
   Kitchens Titel.
4. Apply → `{dashboard: "garden", revision: "b", confirm: true,
   keep_as_version: {level: "patch", title: "5 September 2026"}}`.

`garden` wird also auf einen Stand geschrieben, dessen Diff niemand gesehen
hat, und bekommt obendrein eine Version. Das ist genau die harte Regel
„nichts wird ohne Vorschau geschrieben", gebrochen — die Vorschau war echt,
sie galt nur für etwas anderes.

`_forget` ist derselbe Fehler mit unumkehrbarem Ausgang. Der Dialog baut
seinen Text aus einem oben gemerkten `dashboard` (Zeile 1014) und sagt
wörtlich „This throws away the recorded history of **Kitchen**". Der
bestätigende Aufruf liest `this._selected` erneut:

```
FORGET written to : [{"type":"forget","extra":{"dashboard":"garden","confirm":true}}]
```

Gelöscht wird die vollständige Historie von `garden`, nach einem Dialog, der
`Kitchen` nennt und in Fettschrift „It cannot be undone" sagt.

`_createVersion` teilt den Fehler in milderer Form: `next_versions` fragt für
A, `create_version` schreibt eine Version mit A's Revision in B's Namensraum.

**Herkunft:** Der Fehler steht so schon auf `main` (`git show
main:…/panel.js`, Zeilen 662/699/723/731) — er ist **nicht** von diesem
Branch eingeführt. Dieser Branch verschlimmert ihn an einer Stelle: Seit
Aufgabe 6 hängt `keep_as_version` mit an der bestätigenden Anfrage, es wird
also zusätzlich eine Version am falschen Dashboard erzeugt. Da diese Hälfte
vor einer öffentlichen Veröffentlichung steht, bleibt die Einstufung
Critical, aber mit dieser Ehrlichkeit versehen: es ist Altlast, die dieses
Review findet, nicht Neuschaden.

**Reparatur:** In `_confirm`, `_forget` und `_createVersion` `const asked =
this._selected` **vor** dem ersten `await` festhalten und in beiden Closures
verwenden; zusätzlich der Vorschau-`_guard` in `_confirm` ein `stillWanted`
mitgeben (heute hat es keins, weshalb auch ein **spätes Scheitern** der
Vorschau seinen Banner über das inzwischen gewählte Dashboard legt). Sauberer
noch: den Dialog abbrechen, wenn sich die Auswahl zwischenzeitlich geändert
hat — das ist genau der Dienst, den `_claim` überall sonst schon leistet.

Kein Test deckt diesen Pfad ab; alle Keep-Szenarien halten `el._selected`
konstant.

---

## Important

### I1 — Vom einfachen in den erweiterten Modus mit stehender Suche: „Nothing matches.", ohne je gefragt zu haben

`panel.js:184–193` (`_setMode`) zusammen mit `panel.js:590–595` (`_shown`).

`_setMode` schaltet um und rendert. Es stößt `_search` nicht neu an. Der
einfache Modus hat aber nie den Server gefragt (`_search` kehrt bei
`this._mode === "simple"` in der ersten Bedingung zurück und lässt `_found`
auf `null`). Nach dem Wechsel gilt: Query steht, `_localMatches()` leer,
`_found === null` → `_shown()` liefert `[]` → `_renderMain` schreibt
`Nothing matches.`, und `_searchNote()` schweigt, weil es `_found === null`
korrekt als „nie gefragt" behandelt.

Nachgestellt:

```
A simple  : {"hits":["dash/v1.0.0"],"asked":[],"note":"1 of 1 versions."}
A advanced: {"shown":[],"asked":[],"note":"","query":"winter","found":null}
```

Aus Nutzersicht: „winter" findet im einfachen Modus eine Version; ein Klick
auf „Advanced view", um die zugehörigen Änderungen zu sehen, beantwortet
dieselbe Frage mit „Nothing matches." und einem leeren Hinweisfeld. Erst ein
weiterer Tastendruck im Feld bringt die Suche in Gang.

### I2 — Ein Refresh mitten in der Serversuche verwirft die Antwort und lässt „Nothing matches." stehen

`panel.js:520` (`_search` beansprucht den Slot `changes`) gegen
`panel.js:308` (`_refresh` beansprucht denselben).

`_refreshQuietly` läuft bei **jedem** `dashboard_history_updated`-Ereignis für
das gewählte Dashboard, und der Neuladen-Knopf tut dasselbe. Beides entzieht
der laufenden Suche ihr Ticket. Die Suche prüft `mine()` und steigt aus —
richtig, was das Schreiben angeht, aber `_found` bleibt `null`, `_searching`
ist bereits gelöscht, und niemand startet die Suche neu.

Nachgestellt (der Server hätte 30 Treffer geliefert):

```
search asked: [ 'search' ]  searching: true  note: "Searching the whole history…"
AFTER: query="winter" found=null shown=0 note="" searching=false
```

Aus Nutzersicht: Man tippt eine Suche, im selben Moment speichert jemand ein
Dashboard — und die Seite behauptet dauerhaft, es gebe keinen Treffer, obwohl
30 existieren. Das ist exakt die unsichtbare Lücke, gegen die die zweistufige
Suche laut ihrem eigenen Kommentar (`panel.js:494–506`) angetreten ist.

Nebenbefund derselben Stelle: `_refresh` setzt `_changes` neu, lässt `_found`
aber stehen. Nach einem Refresh mit abgeschlossener Suche zeigt die Liste
Treffer aus der Zeit **vor** dem Refresh.

### I3 — Während die Suche läuft, sagt die Seite gleichzeitig „es sucht" und „nichts gefunden"

`panel.js:1445–1449`.

`_shown()` liefert `[]`, solange `_found` noch `null` ist. `_renderMain`
schreibt daraufhin `Nothing matches.`, während `_renderSearch` darüber
`Searching the whole history…` anzeigt.

```
running | note: "Searching the whole history…" | main: <p class="empty muted">Nothing matches.</p>
```

Der Lauf kostet laut `store.py:779` „roughly half a second per thousand
commits". Auf einer gewachsenen Historie steht dieser Widerspruch also
Sekunden.

**I1, I2, I3 und der Ein-Zeichen-Fall unten haben eine Wurzel:** `_shown()`
kann „noch nicht gefragt" (`_found === null`) nicht von „gefragt, nichts
gefunden" (`_found === []`) unterscheiden und beantwortet beides mit einer
leeren Liste. `_searchNote()` unterscheidet sehr wohl — sagt im ersten Fall
aber nichts, was den Leerlauf nur stiller macht. Eine Reparatur an dieser
einen Stelle (`_shown()` gibt bei `_found === null` „unbekannt" statt „leer"
zurück, und `_renderMain` schreibt dann keinen Absolutsatz) räumt alle vier
ab.

Ein-Zeichen-Fall zum Beleg — `panel.js:514` (`text.trim().length < 2`):

```
asked: []  found: null  note: ""  main: <p class="empty muted">Nothing matches.</p>
```

Eine einbuchstabige Suche ohne lokalen Treffer meldet „nichts gefunden",
obwohl niemand gefragt wurde, und nichts sagt warum.

### I4 — Ein `_render()` zerstört einen offenen Dialog; `_confirm` hängt danach für immer

`panel.js:1546–1548` (`this.shadowRoot.innerHTML = …`) gegen
`panel.js:757–762` (`showModal()` + `await` auf `close`).

Ein Render wirft den kompletten Shadow-DOM weg, den offenen `<dialog>`
eingeschlossen. Ein aus dem Dokument entferntes `<dialog>` feuert **kein**
`close`; der `once`-Listener sitzt auf einem abgehängten Element. Das
`await` in `_confirm` löst nie auf, und auf dem Bildschirm verschwindet der
Bestätigungsdialog wortlos.

`_onRecorded` ist gegen diesen Fall abgesichert (`panel.js:264` prüft
`dialog[open]`) — sonst nichts. Dieser Branch fügt zwei neue Renderquellen
hinzu, die genau in dieses Fenster fallen:

- **`_loadOlder`**: „Load older changes" drücken, dann — die alte Liste steht
  ja noch und ist klickbar — „Undo this change" auf einer Zeile darüber.
  Kommt die Vorschau zuerst, öffnet der Modal; trifft danach die ältere Seite
  ein, feuert `_guard`s `finally` ein `_render()` und der Dialog ist weg.
- **`_search`**: Die Serversuche rendert bei Start (`panel.js:523`), bei
  `_guard`-Ein- und -Austritt und bei der Antwort (`panel.js:542`) — über
  eine halbe Sekunde je tausend Commits hinweg, während die ganze Liste
  bedienbar bleibt.

Aus Nutzersicht: Der Bestätigungsdialog für eine Rückstellung verschwindet
mitten in der Entscheidung, ohne Meldung. Geschrieben wird nichts — das ist
die gute Nachricht —, aber es fällt in die Kategorie „Fehler, der still
bleibt": Nichts sagt, dass die Aktion abgebrochen wurde.

Strukturell für die Tests unerreichbar: Jedes Szenario stubbt
`el._render = () => {}`.

### I5 — Der einfache Modus behauptet unter einer Suche etwas Falsches über den aktuellen Stand

`panel.js:1440` (`versions: this._matchingVersions()`) mit `simple.js:45–48`.

`renderSimple` bekommt die **gefilterte** Versionsliste und leitet daraus den
„Right now"-Satz ab. Der Satz beschreibt aber nicht die Trefferliste, sondern
das Dashboard.

```
ohne Query : The dashboard is in the state of Kitchen rebuild.
mit "autumn": The dashboard has changed since the last version was saved.
```

Aus Nutzersicht: Das Dashboard steht exakt auf v1.2.0 „Kitchen rebuild". Man
tippt „autumn" ins Suchfeld, und die Kopfzeile behauptet, seit der letzten
Version habe sich etwas geändert. Das ist zugleich die einzige Stelle, an der
diese Hälfte die Regel „welche Versionen den aktuellen Stand halten, weiß der
Server" durch eine eigene Rechnung über eine Anzeigeliste unterläuft — der
Server hat `same_as_now` korrekt geliefert, der Filter hat die Zeile nur aus
der Summe entfernt.

Reparatur: `renderSimple` braucht beides — die vollständige Liste für den
Kopf, die gefilterte für die Zeilen.

### I6 — Der einfache Modus nennt eine Änderungszahl, die das geladene Fenster ist

`simple.js:55–64`.

`inside` wird aus `changes` gebildet, also aus den geladenen 25. Das
Zusammenklappen beschriftet sich aber absolut:

```
folds rendered: [ '<summary>25 changes in this version' ]
```

Für eine Version, die 100 Änderungen umspannt. Und liegt der Commit der
Version gar nicht mehr im Fenster (`start < 0`), fehlt das Zusammenklappen
kommentarlos ganz. Der einfache Modus hat kein „Load older", die Zahl kann
also nie richtig werden.

Das steht gegen die projekteigene Regel in `rows.js:47–49`: „a summary which
omits without saying so is worse than a long one". Entweder die Zahl vom
Server holen oder die Beschriftung ehrlich machen („25 loaded changes").

Im erweiterten Modus hat `versionHead` (`rows.js:76`, `count =
section.rows.length`) dasselbe Problem. Dort ist es Altlast — aber durch
`PAGE = 25` statt vorher 50 trifft es jetzt doppelt so oft.

### I7 — Jedes Schreiben aus einem Suchtreffer wirft die Suche weg

`panel.js:895` (`_describe`), `panel.js:1005` (`_createVersion`),
`panel.js:805` (`_confirm`) — alle drei enden auf
`await this._select(this._selected)`, und `_select` setzt `_query = ""`,
`_found = null`, `_cursor = null`, `_open = null`.

```
nach dem Beschreiben eines gefundenen Treffers -> query: ""  found: null  shown: ["a"]
```

Aus Nutzersicht: Commit `2fd5223` hat gerade erst dafür gesorgt, dass eine vom
Server gefundene Zeile überhaupt geöffnet und beschriftet werden kann. Wer
das tut, landet danach auf der ungefilterten ersten Seite mit leerem
Suchfeld — und muss die Suche für jeden weiteren Treffer neu tippen. Das
gewünschte Verhalten ist ein Neuladen, das den Suchzustand behält (die Suche
gehört zum Dashboard, und das hat nicht gewechselt).

### I8 — `simple.js` und `rows.js` haben überhaupt keinen Verhaltenstest

`tests/test_panel_behaviour.py` fasst `renderSimple`, `renderRow`,
`versionHead`, `sections` und `someNames` an keiner Stelle an;
`tests/test_panel_assets.py` prüft nur Backticks, `${` und die Dateiliste.
Geprüft mit Grep über beide Testdateien.

Der einfache Modus ist seit Entscheidung 17 der **Vorgabemodus** für jeden
neuen Nutzer, und seine gesamte Darstellung ist unbelegt. I5 und I6 leben
genau in dieser Lücke — beide sind reine Renderfehler, beide wären von einem
einzigen `renderSimple`-Szenario gefallen. `sections()` ist zudem reine Logik
mit einer Schnittkante und ebenfalls ungetestet (Altlast: war vor der
Teilung genauso ungetestet).

---

## Minor

### M1 — Der Fokus springt bei jedem Render ins Suchfeld

`panel.js:1673–1678`. `if (this._query) find.focus();` plus
`setSelectionRange(len, len)` läuft bei **jedem** Render, nicht nur bei
Tastendrücken. Eine Zeile aufklappen rendert (über `_guard`) zweimal — der
Cursor landet im Suchfeld statt in der Liste, und wer den Suchbegriff in der
Mitte korrigieren wollte, findet den Cursor nach einem eintreffenden Ereignis
am Ende wieder.

### M2 — Ein Netzfehler beim Detail liest sich als Verweigerung

`panel.js:684–689` (`_take(null)`) mit `panel.js:1280–1281`. Schlägt
`_detailFor` fehl, ist `this._undo` `null`, und die Zeile schreibt „This
change cannot be taken back exactly: no reason given." Ein Bannerfehler steht
zwar oben, aber der Satz in der Zeile behauptet etwas über die Änderung, das
er nicht wissen kann.

### M3 — Ein Test trägt einen Namen für eine Bedingung, die nachweislich nichts tut

`test_the_same_failure_is_not_reported_twice` prüft die Wirkung der
`||`-Reihenfolge, nicht die der Bedingung `failed !== applied?.note`. Der
Code sagt das selbst (`panel.js:783–788`: „Removing this condition changes no
outcome (measured)"). Der Test kann fallen — nur nicht für das, was sein Name
verspricht. Der Kommentar ist ehrlicher als der Testname; ein Satz im Test,
der auf die Reihenfolge zeigt, würde das aufheben.

### M4 — Der Entprell-Timer überlebt das Verlassen des Panels

`panel.js:245–250`. `disconnectedCallback` ruft nur `_unlisten()`.
`clearTimeout(this._typing)` steht ausschließlich in `_select`. Ein
Tastendruck 400 ms vor dem Verlassen löst also einen Lauf über die ganze
Historie für eine Seite aus, auf der niemand mehr ist. Commit `7d37e9c` („Let
an unload cancel a mark in flight") zeigt, dass dieser Fall dem Projekt sonst
wichtig ist.

### M5 — `_createVersion` vertraut darauf, dass alle drei Stufen kommen

`panel.js:987`: `candidates[level].split("/").pop()` wirft, wenn der Server
eine Stufe ausließe. Überall sonst in der Datei steht ein `?.` oder ein
`|| ""`.

---

## Was Plan oder Spec vorgeben und was ich trotzdem für einen Mangel halte

### P1 — Die Trefferregel liegt zur Hälfte im Panel

Aufgabe 8 des Plans schreibt es ausdrücklich vor: „Die erste filtert, was das
Panel schon geladen hat" und „Die lokale Stufe sucht dasselbe wie die
entfernte." Umgesetzt in `_wordsOf`/`_localMatches` (`panel.js:545–565`) und
`_matchingVersions` (`panel.js:574–583`), gespiegelt gegen
`store.search_changes` (`store.py:743–793`).

Das ist eine Regel darüber, *was als Treffer zählt*, in doppelter Ausführung —
und die harte Regel der Spec sagt, genau das gehöre auf den Server. Die
Begründung des Plans (kein Netz für den häufigen Fall) ist gut, und der
`_searchNote`-Text ist ehrlich („1 of the 25 loaded entries"), also fällt
niemand in eine unsichtbare Lücke. Trotzdem:

- **Die zwei Fassungen weichen schon heute ab**, wenn auch harmlos: Der Server
  benutzt `casefold()`, das Panel `toLowerCase()`. Für „ß"/„ss" heißt das, dass
  die lokale Stufe verfehlt, wo die entfernte träfe — glücklicherweise die
  ungefährliche Richtung, weil ein lokaler Fehlschlag eskaliert.
- **Nichts hält die beiden zusammen.** Es gibt keinen Test, der die vier
  durchsuchten Felder auf beiden Seiten vergleicht — anders als beim
  Ereignisnamen, für den `test_panel_assets.py` genau so einen Wächter hat.
  Ein solcher Wächter wäre hier billig und würde die Doppelung erträglich
  machen.

Auch die Untergrenze von zwei Zeichen (`panel.js:514`) ist eine
panelseitige Regel darüber, was durchsuchbar ist; ihr sichtbares Ergebnis ist
das falsche „Nothing matches." aus I3.

### P2 — Altlast, nicht von diesem Branch, aber im Widerspruch zur Spec

`panel.js:1226`: `const added = /\d+ added/.test(change.message || "")` liest
den **generierten** Meldungstext aus. Die Spec nennt das an Zeile 591
wörtlich „Textschnüffelei ist genau die Logik, die dort nicht liegen darf" und
benennt den sauberen Weg (ein Merkmal je Änderung in `history`). Dieser
Branch hat die Zeile nur von `this._changes[index]` auf `change` umgestellt
(`final-panel.diff:947–948`), also nicht eingeführt — der offene Punkt der
Spec bleibt aber offen und trifft jetzt zusätzlich Zeilen, die aus der Suche
kommen.

---

## Zu den Tests im Einzelnen

Was zum Roten bringen würde, geprüft an jedem neuen Fall:

| Test | fällt, wenn … |
|---|---|
| `…older_entries_are_appended…` | `_loadOlder` ersetzt statt anzuhängen |
| `…asked_for_by_cursor` | `before`/`limit` fehlen oder ein Offset genommen wird |
| `…end_of_the_history_is_remembered` | `next_cursor` nicht übernommen wird |
| `…another_dashboard_starts_at_the_top_again` | `this._cursor = null` aus `_select` entfällt → `leaked` wird 1 |
| die drei Modus-Fälle | Vorgabe, Merken oder Rückfall auf Unbekanntes ändert sich |
| `…fetches_its_versions_too` | `versions` wird nicht mitgefragt |
| `…matching_version_below_the_window…` | `matching_versions` wird wieder selbst gerechnet — echte Negativkontrolle |
| `…refresh_asks_for_both_and_starts_at_the_top` | Seiten werden angestückelt oder nur eine Antwort erneuert |
| `…open_row_survives_a_refresh_that_moved_it` | Adressierung fällt auf den Index zurück |
| die sieben Keep-Fälle | Vorschau-Reihenfolge, Häkchenvorgabe, Nutzlast oder Escape-Verhalten kippt |
| `…could_not_be_kept_is_said_out_loud` | der stille Pfad wird wieder still |
| `…found_row_can_be_opened` / `…described` | `_changeAt` fragt wieder nur `_changes` |
| `…older_answer_does_not_blank_the_note` | `_searchRuns` entfällt |
| die sechs Suchfälle | Stufenreihenfolge, durchsuchte Felder oder der Reset bei Dashboardwechsel ändern sich |

**Nicht fallen könnende Tests: keine mehr gefunden.** Der einzige Vorbehalt
ist M3 — ein Test, der fallen kann, aber für etwas anderes als seinen Namen.
Die Kontrollfälle (`…ordinary_restore_still_offers_to_keep`,
`…the_parts_are_found_at_all`) sind vorhanden und tun ihre Arbeit.

**Ohne jede Abdeckung:** `simple.js` und `rows.js` komplett (I8), `_setMode`
mit stehender Suche (I1), Refresh gegen laufende Suche (I2), der
Dashboardwechsel zwischen Vorschau und Bestätigung (C1), sowie —
strukturell unerreichbar, weil `_render` überall gestubbt ist — alles, was
mit dem Neuaufbau des Shadow-DOM zu tun hat (I4).

---

## Empfehlung

**Nicht ohne C1 mergen.** Die Reparatur ist klein (eine festgehaltene
Variable an drei Stellen, plus ein `stillWanted` an der Vorschau) und der
Schadensfall — eine unwiderrufliche `forget` auf dem falschen Dashboard nach
einem Dialog, der das richtige nennt — ist der teuerste, den dieses Projekt
hat.

I1 bis I3 lohnen sich zusammen, weil sie eine gemeinsame Wurzel haben und
eine Änderung an `_shown()`/`_renderMain` alle drei erledigt. I5 und I6 sind
zwei kurze Änderungen in `simple.js`, und I8 ist der Test, der beide gefunden
hätte — der Vorgabemodus ohne einen einzigen Rendertest zu veröffentlichen,
ist die auffälligste Lücke dieser Hälfte.

Alles andere kann warten. Die Teilung selbst, das Blättern, das Adressieren
über Revisionen und die Keep-Mechanik sind sauber gebaut, gut begründet und
ordentlich belegt.
