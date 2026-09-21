# Umsetzungsplan: Selbstheilung bei unlesbarer Checkpoint-Datei in `repair_pending_forget`

> **Kontext & Bezug:**
> - GitHub-Issue: [#23](https://github.com/PPP01/ha-dashboard-history/issues/23) (*repair_pending_forget never recovers from an unreadable checkpoint file*)
> - Entwurfsentscheidung: `docs/superpowers/specs/2026-08-30-dashboard-history-design.md`, Entscheidung 21 (resumable forget)
> - Vorgängerplan: `docs/superpowers/plans/2026-09-21-resumable-forget.md` (Issue #22)

---

## 1. Problem & Befund

In GitHub Issue #23 wurde während des Reviews der Implementierung von Issue #22 ein Randfall identifiziert:

`_read_checkpoint` in `custom_components/dashboard_history/store.py` liest `.git/dashboard_history_forget.json` ungeprüft über `json.loads(path.read_text(...))` und greift direkt auf die Schlüssel zu (`payload["key"]`, `payload["head"]`, `payload["notes"]`, `payload["tags"]`).

Trifft `repair_pending_forget()` auf eine unlesbare oder fehlerhafte Datei:

| Checkpoint-Inhalt | Ausnahme in `repair_pending_forget` |
|---|---|
| abgeschnitten (z. B. durch Stromausfall mitten im Schreiben) | `json.JSONDecodeError` |
| 0 Bytes (leere Datei) | `json.JSONDecodeError` |
| `{}` (valides JSON, falsche Struktur / fehlende Schlüssel) | `KeyError: 'head'` |
| ungültige Typen (z. B. `[]` oder `head: 123`) | `TypeError` / `AttributeError` |

In all diesen Fällen propagiert die Ausnahme aus `repair_pending_forget()` heraus. In `__init__.py:126` fängt der Hintergrund-Task `_async_open` die Ausnahme zwar ab und loggt sie, **die Checkpoint-Datei wird jedoch nicht gelöscht**.

Weil alle Schreiboperationen (`write_snapshot`, `mark_deleted`, `create_version`, `retitle_version`, `remove_version`, `set_description`, `forget`) über `_refuse_if_forget_pending()` abfragen, ob die Datei existiert (`self._checkpoint_path().exists()`), führt dies zu einer **dauerhaften Blockade aller Schreibvorgänge**:
- Jeder Schreibaufruf wirft `ValueError("Dashboard History cannot write right now: an earlier forget did not finish and left a checkpoint behind ... Restart Home Assistant - the interrupted rewrite finishes automatically before recording resumes.")`.
- Ein Neustart von Home Assistant wiederholt denselben fehlschlagenden Reparaturversuch, der Checkpoint bleibt liegen, und das gegebene Versprechen kann niemals eingelöst werden.

---

## 2. Entwurfsentscheidung: Ergänzung zu Entscheidung 21 (Korrektur 6)

In `docs/superpowers/specs/2026-08-30-dashboard-history-design.md` wird Entscheidung 21 um **Korrektur 6** ergänzt (als durchgehender Fließtext im Stil der Korrekturen 1–5):

> **Korrektur 6: Ein unlesbarer Checkpoint kann nicht wiederholt werden und darf die Integration nicht dauerhaft lahmlegen — ein transienter Lesefehler darf ihn aber nicht vernichten (Issue #23).**
> Der Schreibschutz aus Korrektur 1 (`_refuse_if_forget_pending`) schützt einen *vorhandenen, ausführbaren* Plan davor, durch neuere Schreibvorgänge überrollt oder verfälscht zu werden, bevor die Reparatur ihn abarbeiten konnte. Ist der Checkpoint jedoch inhaltlich nachweislich korrupt (abgeschnittene Datei durch Stromausfall, 0-Byte-Datei, ungültiges UTF-8 oder fehlende Pflichtschlüssel wie `key`, `head`, `notes` oder `tags`), existiert kein ausführbarer Plan mehr. Ein Raten oder halbes Ausführen scheidet aus: Ohne den Schlüssel ist nicht einmal bekannt, welches Dashboard vergessen werden sollte. Einen nachweislich korrupten Checkpoint liegenzulassen, verwandelt den beabsichtigten Selbstheilungs-Mechanismus in ein dauerhaftes »Bricking« der Integration, weil jede Schreiboperation dauerhaft mit dem uneinlösbaren Hinweis auf einen Neustart abgewiesen wird.
>
> Streng davon zu trennen ist ein reiner I/O- oder Lesefehler (`OSError`, z. B. `PermissionError`): Er beweist nicht, dass der Inhalt beschädigt ist, sondern nur, dass er im Moment nicht gelesen werden kann. Dieselbe Logik wie in Korrektur 5 (»Sperrdatei existiert« beweist nie »Besitzer ist tot«) gilt hier spiegelverkehrt: Ein vorübergehender Lesefehler beweist nicht »Plan ist korrupt«, und die Datei wegzulöschen würde einen möglicherweise intakten Wiederaufnahmeplan vernichten.
>
> `_read_checkpoint` trennt daher sauber: Bei Inhalts- und Schemafehlern (`json.JSONDecodeError`, `UnicodeDecodeError`, `KeyError`, `TypeError`, `ValueError`, `AttributeError`) wird der Fund mit Traceback per `_LOGGER.exception` gemeldet und die unbrauchbare Datei gelöscht (`path.unlink(missing_ok=True)`, gegen `OSError` abgesichert). Bei einem reinen `OSError` beim Lesen wird ebenfalls geloggt, die Datei bleibt jedoch unberührt stehen, damit der Schreibschutz aktiv bleibt, bis das Rechte- oder Dateisystemproblem behoben ist. In beiden Fällen antwortet die Methode mit `None`, sodass `repair_pending_forget` ohne unbehandelte Ausnahme zurückkehrt.

---

## 3. Betroffene Dateien & Änderungen

### 3.1. `docs/superpowers/specs/2026-08-30-dashboard-history-design.md`
- Ergänzung von Entscheidung 21 um den Abschnitt **Korrektur 6** im bestehenden Fließtext-Stil.

### 3.2. `custom_components/dashboard_history/store.py`
- Aktualisierung von `_read_checkpoint(self)`:
  - Unterscheidung zwischen Lese-I/O-Fehlern (`OSError`) und Inhalts-/Strukturfehlern (`UnicodeDecodeError`, `json.JSONDecodeError`, `KeyError`, `TypeError`, `ValueError`, `AttributeError`).
  - `_LOGGER.exception(...)` mit vollem Traceback statt `_LOGGER.error(...)`.
  - Bei Inhaltsfehlern: Löschung via `path.unlink(missing_ok=True)` in einem eigenen `try/except OSError`-Block abgesichert.
  - Bei `OSError` beim Lesen: Datei stehen lassen, `_LOGGER.exception`, `return None`.

### 3.3. `tests/test_store.py`
- Ergänzung von vier Tests nach TDD:
  1. `test_repair_recovers_from_truncated_checkpoint_file(store, caplog)`:
     Schreibt unvollständiges JSON (`'{"key": "gone", "head":'`), ruft `repair_pending_forget()`, prüft `not checkpoint.exists()`, prüft Exception-Logging, prüft erfolgreichen Folgeschreibvorgang (`write_snapshot`).
  2. `test_repair_recovers_from_empty_checkpoint_file(store, caplog)`:
     Schreibt leere Datei (`""`), ruft `repair_pending_forget()`, prüft Löschung, Exception-Logging und Folgeschreibvorgang.
  3. `test_repair_recovers_from_malformed_checkpoint_shape(store, caplog)`:
     Schreibt `{}` (oder `[]`), ruft `repair_pending_forget()`, prüft Löschung, Exception-Logging und Folgeschreibvorgang.
  4. `test_repair_leaves_checkpoint_intact_on_read_os_error(store, monkeypatch, caplog)`:
     Simuliert `OSError` bei `read_text`. Prüft, dass die Checkpoint-Datei **nicht** gelöscht wird, Exception geloggt wird und nachfolgende Schreiboperationen durch `_refuse_if_forget_pending` weiterhin abgewiesen werden.

---

## 4. TDD-Schritte

### Schritt 1: Tests schreiben
In `tests/test_store.py` die vier Testfunktionen direkt nach `test_repair_clears_a_stale_object_lock` einfügen.

### Schritt 2: Test-Fehlschlag verifizieren
```bash
python3 -m pytest tests/test_store.py -k "repair_recovers_from or checkpoint_intact_on_read_os_error" -v
```
**Erwartung:** Tests schlagen mit `JSONDecodeError`, `KeyError` bzw. `OSError` fehl.

### Schritt 3: Spezifikation & Code implementieren
1. `docs/superpowers/specs/2026-08-30-dashboard-history-design.md` mit Korrektur 6 aktualisieren.
2. `custom_components/dashboard_history/store.py:633-651` anpassen:
```python
    def _read_checkpoint(
        self,
    ) -> tuple[str, bytes | None, dict[bytes, bytes], dict[bytes, bytes | None]] | None:
        """The inverse of `_write_checkpoint`, or `None` if there is none.

        If the checkpoint file exists but cannot be parsed or lacks the
        required shape, it is logged with a traceback and deleted: an
        unreadable plan cannot be finished automatically, and leaving it
        in place would permanently disable all writes across restarts
        (issue #23).

        A pure I/O error (`OSError`, e.g. permission denied) is kept
        strictly apart from content corruption: it does not prove the
        plan is broken, only that it cannot be read right now. In that
        case the file is left untouched so the write guard remains in
        place until the filesystem issue is resolved.
        """
        path = self._checkpoint_path()
        if not path.exists():
            return None
        try:
            raw = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            _LOGGER.exception(
                "Removed corrupt forget checkpoint with invalid encoding %s: %s. "
                "An interrupted forget could not be finished automatically.",
                path,
                exc,
            )
            try:
                path.unlink(missing_ok=True)
            except OSError:
                _LOGGER.exception("Could not remove corrupt checkpoint %s", path)
            return None
        except OSError:
            _LOGGER.exception(
                "Could not read forget checkpoint %s due to an I/O error; "
                "leaving file in place to avoid losing a pending plan",
                path,
            )
            return None

        try:
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError(f"expected dict, got {type(payload).__name__}")
            key = payload["key"]
            if not isinstance(key, str):
                raise ValueError("key must be a string")
            head_val = payload["head"]
            if head_val is not None and not isinstance(head_val, str):
                raise ValueError("head must be a string or None")
            head = head_val.encode() if head_val is not None else None
            notes_val = payload["notes"]
            if not isinstance(notes_val, dict):
                raise ValueError("notes must be a dict")
            notes = {
                sha.encode(): text.encode("utf-8")
                for sha, text in notes_val.items()
            }
            tags_val = payload["tags"]
            if not isinstance(tags_val, dict):
                raise ValueError("tags must be a dict")
            tags = {
                ref.encode("utf-8", "surrogateescape"): (
                    sha.encode() if sha is not None else None
                )
                for ref, sha in tags_val.items()
            }
            return key, head, notes, tags
        except (
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
            AttributeError,
        ) as exc:
            _LOGGER.exception(
                "Removed unreadable forget checkpoint %s: %s. An "
                "interrupted forget could not be finished automatically.",
                path,
                exc,
            )
            try:
                path.unlink(missing_ok=True)
            except OSError:
                _LOGGER.exception("Could not remove unreadable checkpoint %s", path)
            return None
```

### Schritt 4: Tests ausführen & verifizieren
1. Gezielte Tests ausführen:
   ```bash
   python3 -m pytest tests/test_store.py -k "repair_recovers_from or checkpoint_intact_on_read_os_error" -v
   ```
   **Erwartung:** 4 passed.
2. Gesamte Testsuite ausführen:
   ```bash
   python3 -m pytest tests/ -v
   ```
   **Erwartung:** 718 passed, 1 skipped.

### Schritt 5: Review & Commit
Änderungen dem Nutzer vorzeigen (`git diff`) und Bestätigung einholen.

**Geplante Commit-Nachricht:**
```text
Recover from an unreadable forget checkpoint during repair

_read_checkpoint previously indexed straight into json.loads output.
A truncated file (from power loss), an empty file, or a malformed
payload crashed repair_pending_forget with unhandled JSONDecodeError
or KeyError. Because _async_open swallowed the error without deleting
the checkpoint, _refuse_if_forget_pending kept refusing every write
permanently across restarts with an unfulfillable restart promise.

_read_checkpoint now validates the checkpoint structure, catches
decoding and schema errors, logs an error, and deletes the unreadable
checkpoint file so writing resumes safely (decision 21, correction 6).
Pure I/O errors (OSError) leave the file untouched to prevent
destroying a plan on transient filesystem errors.

Closes #23.
```
