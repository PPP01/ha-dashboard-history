# Arbeitsprotokoll zu Vorhaben H

Was hier liegt, ist das Rohmaterial: die beiden Ledger, mit denen die
Umsetzung gesteuert wurde, die acht Aufgaben-Reviews der zweiten Hälfte,
die beiden Abschluss-Reviews samt Behebung, Nachprüfung und Absicherung,
und die Berichte der zwei Vereinfachungsläufe.

**Die Zusammenfassung steht eine Ebene höher**, in
`2026-09-05-vorhaben-h.md`. Wer wissen will, was entschieden wurde und
warum, liest die. Wer wissen will, *woran* es entschieden wurde — welche
Messung, welcher Befund, welcher Gegenbeweis —, findet es hier.

## Warum das englisch ist, obwohl `docs/superpowers/` deutsch ist

Die Sprachregel des Projekts richtet sich nach dem Publikum, und das
Entwurfsjournal — Spec und Pläne — ist nach innen gerichtet und deshalb
deutsch. Diese Dateien sind ein dritter Fall: Sie sind während der Arbeit
von Prüf- und Umsetzungsläufen erzeugt worden, die auf demselben Code
arbeiten, den sie beschreiben, und dieser Code ist englisch. Sie zu
übersetzen hieße, jeden zitierten Bezeichner, jede Fehlermeldung und
jeden Kommentar aus dem Zusammenhang zu reißen, in dem er nachprüfbar
ist.

Sie sind darum unverändert übernommen. Das ist eine bewusste Ausnahme,
und sie steht hier, damit niemand davorsteht und rätselt — nach demselben
Muster, mit dem die README die umgekehrte Ausnahme ausschildert.

## Was nicht übernommen wurde, und warum

- **Die Aufgaben-Briefs** (216 KB). Wörtliche Auszüge aus
  `docs/superpowers/plans/`. Der Plan liegt im Repository; eine zweite
  Kopie desselben Textes ist eine zweite Stelle, an der er veralten kann.
- **Die Diff-Pakete** (660 KB). Zusammenstellungen aus `git log`,
  `git diff --stat` und `git diff -U10` für je eine Aufgabe. Aus der
  Historie jederzeit neu erzeugbar; die Commit-Bereiche stehen in den
  Ledgern.
- **Die Umsetzungsberichte je Aufgabe.** Was daran zählte — eine
  gefundene Ungereimtheit im Plan, ein Test, der nicht fehlschlagen
  konnte, eine bewusste Abweichung vom Buchstaben — ist im jeweiligen
  Ledger-Eintrag als Urteil festgehalten, mit Begründung und mit dem, was
  es kostet, wenn das Urteil falsch war.
