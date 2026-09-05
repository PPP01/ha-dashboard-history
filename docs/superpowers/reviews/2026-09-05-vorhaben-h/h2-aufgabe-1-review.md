# Review Aufgabe 1: Der Rücksprung kann den jetzigen Stand markieren

Commit geprüft: `92a82ff` (einziger Commit im Diff-Paket, Basis `cbd4c07`).
Read-only im Worktree `ha-dashboard-history-h`, Branch `vorhaben-h`.

## Verdikt A — Spec-Konformität

**Erfüllt.** Alle Signaturen, Dict-Keys, Docstrings, Fehlertexte,
`services.yaml`-Text und die Commit-Message sind wörtlich aus dem Brief
übernommen; keine Umbenennungen, nichts Zusätzliches, nichts Fehlendes an
den fünf genannten Dateien. Die einzige Abweichung ist eine Ungenauigkeit,
die schon im Brief selbst angelegt ist (siehe Finding unten), keine
Implementierer-Entscheidung.

## Verdikt B — Codequalität

**Gut, passt zum Bestand.** Die Reihenfolge, auf die sich die gesamte
Korrektheit stützt, ist im vollständigen Funktionskörper nachgewiesen exakt
so, wie der Brief sie verlangt — kein früher Return, keine Exception und
kein zusätzliches `await` zwischen `_keep_the_live_state` und
`_async_keep_as_version` bzw. zwischen diesem und `async_save_config`. Der
neue Integrationscheck prüft die eigentliche Ordnungs-Eigenschaft (Tag
landet auf der *neueren* der beiden Revisionen, nicht nur „irgendein Tag
wurde erzeugt"), ist also kein Check, der auch ohne die Korrektur grün wäre.

## Prüfung der Aufrufreihenfolge in `async_restore_state` (operations.py:455–538)

Vollständig gelesen, nicht nur der Diff-Hunk.

- Der Aufruf von `_async_keep_as_version` (Zeile 514) sitzt unmittelbar nach
  dem `if missing / else`-Block, der entweder `async_create_dashboard`
  (missing-Zweig) oder `_keep_the_live_state` (else-Zweig, Zeile 510)
  ausführt, und unmittelbar vor `await async_save_config` (Zeile 527). Kein
  weiteres `await`, kein weiterer Schreibzugriff auf den Store dazwischen.
- Früher Return existiert nur *vor* diesem Block: Wenn `async_create_dashboard`
  im `missing`-Zweig eine `HomeAssistantError` wirft, kehrt die Funktion
  zurück, bevor der neue Code überhaupt erreicht wird (Zeile 499–504,
  unverändert von diesem Task). Das überspringt nichts, das bereits als
  „markiert" gelten könnte — es gibt in diesem Fall ohnehin nichts zu
  markieren.
- Für den `missing`-Zweig wird `gap` hart auf einen festen Text gesetzt,
  unabhängig von `note` — geprüft gegen `async_create_dashboard`
  (`snapshot.py:203`): Diese Funktion gibt auf dem Erfolgspfad immer `None`
  zurück und wirft sonst, `note` ist in diesem Zweig also nie ein
  aussagekräftiger Text, den man verlieren könnte. Die Bedingung
  `"..." if missing else note` ist damit korrekt, wie im Bericht des
  Implementierers selbst vermerkt.
- Wenn `_keep_the_live_state` etwas meldet (Rückgabe ≠ `None`), wird dieser
  Text unverändert als `gap` durchgereicht, `_async_keep_as_version` liefert
  sofort `{"created": None, "error": gap}` ohne `async_create_version`
  aufzurufen, und der Rücksprung läuft trotzdem bis `async_save_config`
  weiter durch. Das entspricht wörtlich der im Brief verlangten Regel
  „wenn der Stand nicht gesichert werden konnte, wird nicht markiert, der
  Rücksprung geht trotzdem durch".
- `async_create_version` (aufgerufen ohne explizite `revision`, Zeile
  445–452) fällt laut eigenem Docstring/Kommentar (operations.py:667–678)
  auf `store.list_changes(key, 1)` zurück — „die neueste aufgezeichnete
  Revision". Das ist exakt die Stelle, an der die Korrektheit hängt: Der
  Fallback wird nur dann korrekt gelesen, wenn er zwischen
  `_keep_the_live_state` (das den lebenden Stand ggf. nachträgt) und
  `async_save_config` (das den nächsten Stand schreibt) ausgeführt wird —
  und genau dort sitzt er.

Ergebnis: Die im Brief behauptete Reihenfolge stimmt mit dem geschriebenen
Code überein, Punkt für Punkt.

## Findings

- **Minor — Konflikt mit dem Plan, kein Implementierer-Fehler.**
  `operations.py:445–452` und `641–699` (`async_create_version`): Der
  Abschnitt „Schnittstellen" im Brief verspricht
  `kept_as_version: {"created": str | None, "error": str | None}` — also
  beide Schlüssel immer vorhanden. Tatsächlich liefert
  `async_create_version` auf dem Erfolgspfad nur `{"created": name}`, ganz
  ohne `"error"`-Schlüssel (bestätigt durch den tatsächlichen Lauf im
  Bericht: `kept={'created': 'dh-keep-check/v1.1.0'}`). Das ist keine
  Implementierer-Entscheidung — der Brief-Code in Schritt 3 reicht das
  Ergebnis von `async_create_version` unverändert durch, und diese
  Funktion „besteht" laut Brief unangetastet. Funktional harmlos, da
  `dict.get("error")` in beiden Fällen `None` liefert, aber ein Konsument,
  der auf das Vorhandensein des Schlüssels statt auf seinen Wert prüft,
  würde hier stolpern. Gehört, falls es behoben werden soll, in die Spec
  bzw. in `_async_keep_as_version`, das den Erfolgsfall auf
  `{"created": name, "error": None}` normalisieren müsste — nicht in
  diesen Task, ohne dass der Brief das vorsieh.

- **Minor.** `async_restore_state`s Docstring
  (`operations.py:463`, `"""Set a dashboard back to an earlier state,
  creating it if it is gone."""`) erwähnt den neuen Parameter
  `keep_as_version` nicht. Der Brief verlangt an dieser Stelle keine
  Docstring-Änderung, insofern kein Abweichen vom Auftrag — nur ein
  Lesbarkeits-Hinweis für später.

Keine Critical- oder Important-Findings. `pytest` erneut laufen lassen:
`270 passed, 3 skipped`, deckungsgleich mit dem Bericht. Keine der vier
HA-freien Kernmodule (`yaml_io.py`, `analyze.py`, `restore.py`,
`versions.py`) wurde berührt, wie vom Brief verlangt. Kein System-`git`,
kein Monkey-Patching, keine neue blockierende Arbeit außerhalb eines
Executors (nutzt die bereits vorhandenen Executor-Aufrufe in
`async_create_version`). Commit-Message: Subject 40 Zeichen (Imperativ,
großer Anfangsbuchstabe), Body-Zeilen ≤ 69 Zeichen, korrekter
`Co-Authored-By`-Abschluss — vollständig konform zum vorgeschriebenen
Format.
