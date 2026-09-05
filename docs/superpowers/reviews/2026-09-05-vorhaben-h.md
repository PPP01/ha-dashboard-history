# Vorhaben H — Umsetzung und Abschluss-Review, 2026-09-05

Stand: `main` bei `be62dc4`, Arbeitsbaum sauber. 42 Commits, vorspulend
zusammengeführt aus dem Zweig `vorhaben-h`.

Tests: `362 passed` im Hauptcheckout (mit echter Ablage), `349 passed,
3 skipped` ohne sie. Integrationsprüfungen: `131 von 131`.

Vorgehen: `superpowers:subagent-driven-development` — je Aufgabe ein
frischer Umsetzer, danach ein eigener Prüfer, dann ein Abschluss-Review
über den ganzen Zweig, in zwei Hälften geteilt. Das Rohmaterial liegt in
`2026-09-05-vorhaben-h/`.

## Was entstanden ist

**Erste Hälfte, »Versionen von selbst«.** Beim Start bekommt jedes
Dashboard eine erste Version, damit es überhaupt einen benannten Stand
gibt, auf den man zurück kann. Danach wird der letzte Stand jedes Tages
markiert. Beides läuft ohne Zutun; die Tagesmarke lässt sich in den
Optionen abschalten, der Boden nicht — ohne ihn hätte der einfache Modus
nichts anzuzeigen.

**Zweite Hälfte, »Die zwei Modi«.** Ein einfacher Modus neben dem
bisherigen, der nur die benannten Versionen zeigt. Blättern mit einem
Fenster von fünfundzwanzig. Ein Suchfeld, das je Modus durchsucht, was
der Modus zeigt — im erweiterten über die ganze Historie, serverseitig.
Ein Rücksprung, der den Stand, den er ersetzt, in derselben Bewegung als
Version behalten kann. Und Zeilen, die sich über ihre Revision
adressieren statt über ihre Position.

## Die Befunde, die etwas verändert haben

### Vorschau und Schreibvorgang meinten verschiedene Dashboards

Der einzige kritische Befund. Die Anfrage-Abschlüsse lasen
`this._selected` erst beim *Aufruf*, und sie werden zweimal aufgerufen —
einmal für die Vorschau, einmal für das Schreiben. Der Dialog erscheint
aber erst, wenn die Vorschau zurück ist; dazwischen ist die Seitenleiste
bedienbar. Wer die Vorschau eines Rücksprungs auf einem Dashboard öffnet,
in der Wartezeit ein anderes anklickt und dann bestätigt, schreibt in das
zweite mit der Revision des ersten.

Bei `_forget` — dem Verwerfen einer ganzen Historie — dieselbe Form, nur
unumkehrbar, unter einem Dialog, der das falsche Dashboard benennt.

Der Fehler war älter als dieses Vorhaben, ist hier aber breiter geworden,
weil der Rücksprung jetzt zusätzlich eine Version anlegt. Behoben wird er
dadurch, dass jeder schreibende Ablauf den Schlüssel **einmal, vor dem
ersten `await`** festhält und beide Aufrufe daraus bedient.

### Die zweite Suchstufe tat nichts

Zeilen werden über ihre Revision nachgeschlagen, und der Nachschlag sah
nur in die geladene Liste. Ein Treffer, den der Server zurückgibt, steht
dort per Definition nicht — das *ist* die Bedeutung von »die ganze
Historie durchsuchen«. Ein solcher Treffer ließ sich anklicken und tat
nichts; der Stift daneben öffnete keinen Dialog; und nichts sagte, warum.

Bemerkenswert ist der Docstring der Funktion: Er benennt ausdrücklich,
dass das Suchfeld eine zweite Liste schafft — und dann liest die Funktion
nur die erste. Kein einziger der damals 320 Tests bemerkte es; die
Behebung allein ließ alle grün.

### Die Tagesmarke verlor den Vortag

Sie nahm den zweitneuesten Eintrag als letzten Stand des vergangenen
Tages. Das stimmt nur, wenn sie einmal je Speichervorgang läuft, der
Reihe nach — und das tut sie nicht: Die Ankündigung wird bearbeitet, ohne
den Bus aufzuhalten, also starten zwei dicht aufeinanderfolgende
Speichervorgänge zwei Marken, die beide erst nach beiden Schreibvorgängen
ankommen. Beide sehen dann zwei Einträge von heute, sehen einen Tag, und
kehren zurück. Der letzte Stand von gestern, eine Zeile tiefer, wird von
niemandem je markiert — still und dauerhaft, denn kein späterer
Speichervorgang reicht dorthin zurück.

Sie sucht jetzt den Tagesübergang, statt ihn an einer festen Stelle zu
vermuten.

### Die Suche fand die eigene Buchführung

Eine automatisch angelegte Version trägt in ihrer Beschreibung die
Markierung `dashboard-history: automatic`. Die Suche las die Beschreibung
roh — und die Markierung besteht aus Wörtern. Wer `auto`, `dash`,
`history` oder `dashboard` eintippte, bekam jede automatische Version als
Treffer, für einen Satz, den niemand geschrieben hat und den niemand zu
sehen bekommt. Jeder andere Ausgang aus dem Modul entfernt die Markierung
vorher; die Suche war der eine, der es nicht tat.

### Ein Feld, zweimal geformt

`keep_as_version` wurde im WebSocket-Befehl und im Dienst getrennt
geprüft, und die beiden Prüfungen waren nicht dieselbe: Der Dienst nahm
jedes beliebige Dict. Damit legte `keep_as_version: {}` zusammen mit
`confirm: true` ein echtes Tag mit leerem Titel an — und Versionen kann
diese Integration nicht wieder löschen.

Behoben nicht an der Abweichung, sondern an der Ursache: Das Schema steht
jetzt einmal in `const.py`, wo beide Türen ohnehin hineinsehen. Zwei
Kopien können nicht auseinanderlaufen, wenn es nur eine gibt.

## Das Muster, das mehr wert war als jeder Einzelbefund

Vier Tests auf diesem Zweig konnten nicht fehlschlagen. Sie waren grün,
sahen aus wie Absicherung und prüften nichts.

Gefunden wurden sie alle durch dieselbe Frage, die ab Aufgabe 4 in jeden
Auftrag ging: *Was müsste ich kaputt machen, damit dieser Test rot wird?*
Zweimal hat der Umsetzer die Antwort selbst gegeben, unaufgefordert und
gemessen, statt sie zu verschweigen — das waren die nützlichsten Zeilen
in allen Berichten.

Daraus wurde eine Regel für den Rest der Arbeit: Jeder neue Fall wird
belegt, indem der Fehler wieder eingesetzt und der Test rot gesehen wird.
Bei der Behebung des kritischen Befundes lautete die Zwischenbilanz
einmal wörtlich: »Die Reparatur erreicht fünf von fünf, die Messung
erreicht zwei von fünf.« An sechs Stellen ließ sich die Absicherung
rückgängig machen, ohne dass ein Test rot wurde — heute kein Fehler,
morgen die Garantie für einen. Inzwischen ist das eine Tabelle, in der
jede der sechs Rückabwicklungen einen namentlich benannten Fall rot
macht.

Beim Messen fiel nebenbei auf, dass einer der **neuen** Testläufe grün
war und dabei schon in seiner ersten Zeile stehenblieb. Gefunden hat das
nicht ein Prüfer, sondern die Messung selbst.

## Was der Plan selbst falsch hatte

Sechs Stellen, alle im selben Muster: Die Prosa des Plans sagte eine
Testzahl voraus, die sein eigener wörtlich vorgegebener Code-Block nicht
ergibt. Dreimal war die Zahl um eins zu niedrig. Die Umsetzer haben
jedes Mal den Block geliefert und die Abweichung gemeldet — richtig
entschieden: Die Zahl ist die Vorhersage, der Block ist die Anforderung.

Dazu fünfmal ein verlorener Absatz. Der Plan schreibt umgezogenen Code
wörtlich aus, damit er kopiert werden kann, und beim Abschreiben sind
Begründungen verlorengegangen — unter anderem die drei, die zusammen
*eine* redaktionelle Entscheidung tragen: eine Formulierung für einen
Sachverhalt, an den drei Stellen, die ihn aussprechen. Genau das
zerstreut eine Aufteilung in Teildateien. Alle sind zurückgeholt, im Code
und im Plan.

## Was bewusst nicht behoben wurde

- **Die Zeitzone im vorgeschlagenen Versionstitel.** Python rechnet in
  der Zone der Anlage, JavaScript in der des Browsers. Um Mitternacht
  herum, von weit weg, schlägt der Dialog einen Titel mit dem falschen
  Tag vor. Der Wert ist ein *Vorschlag*, sichtbar und änderbar, nie etwas
  ungesehen Geschriebenes; die Alternative wäre ein Serveraufruf vor
  jedem Dialog für eine Vorbelegung.
- **Der doppelte Anfrage-Versand bei hastigem Doppelklick auf »Ältere
  laden«.** Der Zustand bleibt korrekt. Jede andere abgesicherte Aktion
  in derselben Datei verhält sich genauso; diese eine zu ändern machte
  sie zur Ausnahme.
- **Die fehlende Aufklappzahl im einfachen Modus**, wo der eigene Commit
  einer Version unterhalb des geladenen Fensters liegt. Eine fehlende
  Angabe behauptet nichts, eine falsche behauptet etwas Unwahres. Im
  erweiterten Modus bleibt die Zahl, denn dort kann »Ältere laden« sie
  wahr machen.
- **Der Hinweistext nach dem Bestätigen** kann auf einem Dashboard
  landen, zu dem inzwischen gewechselt wurde. Eine Meldung am falschen
  Ort, kein Schreibvorgang am falschen Ort — und unverändert gegenüber
  vorher.

## Zwei Vereinfachungsläufe

Nach jeder Hälfte ging ein Vereinfacher über den frischen Code, mit einer
Verbotsliste: nichts umbenennen, was ein Test erreicht, keine Teildatei
zusammenlegen, und sechs namentlich genannte Stellen nicht anfassen, die
*aussehen* wie Umständlichkeit und in Wahrheit je einen konkreten Fehler
schließen.

Der zweite Lauf fasste vier Redewendungen zusammen: `v1.2.0` aus
`home/v1.2.0` stand an acht Stellen, Banner-setzen-und-zeichnen an
sieben, die drei Felder einer offenen Zeile an drei, und elf
Klick-Behandlungen trugen je ihr eigenes `querySelectorAll`. Dazu ein
Angebot, das zweimal im Quelltext stand — zwei Kopien eines Angebots
driften, bis sie Verschiedenes sagen, wovon dieser Zweig sich dreimal
überzeugt hat.

Aufschlussreich ist, was er *nicht* zusammengefasst hat: Die
`same`-Berechnung in `async_history` und `async_search` sieht geteilt
aus und ist es nicht — die eine faltet Versions-Revisionen absichtlich in
den Vergleich, die andere nicht. Zwei Dinge, die einander ähneln, sind
keine Doppelung.

## Ein Nachtrag vom Abschluss selbst

Nach dem Zusammenführen musste der Testcontainer neu erstellt werden, weil
er am Pfad des entfernten Worktrees hing. Der Prüflauf danach kam rot
zurück — vier von 131 —, und der Code war beweisbar byte-identisch mit
dem Stand, der Minuten vorher `131 von 131` ergeben hatte.

Die Ursache stand in der Zeile *vor* dem ersten Fehlschlag: Der neueste
Eintrag lautete schon vor dem Prüfschritt `allgemein-strom: 1 added` und
danach unverändert genauso. Der Speichervorgang der Prüfung war gar nicht
aufgezeichnet worden. Gestartet worden war der Lauf, sobald Home
Assistant auf HTTP antwortete — da lief der Eröffnungsdurchgang des
Rekorders noch.

Der Schaden war echt und nicht bloß eine rote Zeile: Die Prüfung hatte
eine Karte entfernt und scheiterte, bevor sie sie zurücklegen konnte. Der
Prüfstand blieb eine Karte ärmer, und die beiden Folgeläufe fanden keine
Liste mehr mit mehr als einer Karte. Zurückgeholt wurde sie mit dem
Werkzeug, um das es hier geht: `deleted_since` benannte sie, die Vorschau
zeigte genau eine additive Einfügung, das Schreiben setzte sie an ihre
Position.

Interessant ist, wo die Lehre schon stand. Der Docstring von
`wait_for_integration` in `run_checks.py` formuliert sie wörtlich: »A
readiness signal has to be the thing the checks depend on, not the
nearest thing answering.« Genau derselbe Fehler, eine Ebene tiefer —
registrierte Dienste sind nicht dasselbe wie eine Historie, die
stillsteht, und die Prüfungen hängen an der Historie. Der Prüflauf wartet
jetzt darauf, dass sich die neueste Revision des Prüf-Dashboards sechs
Sekunden lang nicht mehr bewegt. Belegt am Kaltstart: Container
vollständig neu erstellt, Lauf sofort danach, `131 von 131`.
