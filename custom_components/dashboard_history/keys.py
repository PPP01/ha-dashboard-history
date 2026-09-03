"""Which dashboard is which, and which one is gone.

Small decisions, kept here rather than where they are used, because where
they were used no test could reach them. Both of the rules below had
already been wrong once inside the Home-Assistant-bound modules: the
storage-key mapping confused a dashboard's id with its url_path, and the
deletion rule is one where a mistake is not a wrong number but a wiped
history.

Home-Assistant-free on purpose, and deliberately without imports of its
own - the test suite loads these modules flat, where a relative import
would not resolve.
"""

from __future__ import annotations

from collections.abc import Iterable

# Home Assistant's own storage keys for dashboards.
_DEFAULT_STORAGE_KEY = "lovelace"
_STORAGE_KEY_TEMPLATE = "lovelace.{}"


def storage_keys(
    items: Iterable[dict] | None, default_key: str
) -> list[tuple[str, str]]:
    """Pairs of (our key, Home Assistant's storage key) for every dashboard.

    The two are not the same string. Measured on a real installation: a
    dashboard whose url_path is "energie-2" is stored under the id
    "energie_2". Our own key follows the url_path, because that is what
    people see and type; the storage key follows the id, because that is
    where the file is. Mixing them up files one dashboard under two names
    and forks its history without a word.
    """
    pairs = [(default_key, _DEFAULT_STORAGE_KEY)]
    for item in items or []:
        url_path = item.get("url_path")
        identifier = item.get("id")
        if not url_path or not identifier:
            continue
        pairs.append((url_path, _STORAGE_KEY_TEMPLATE.format(identifier)))
    return pairs


def is_safe_key(key) -> bool:
    """Whether a key may be turned into a file name and a tag prefix.

    A dashboard key becomes both: `<key>.yaml` in the store, and the
    first segment of a version's tag, `<key>/v1.0.0`. So it has to be one
    ordinary path segment and nothing else. Measured before this rule
    existed: a dashboard registered over the API under the url_path
    "../weiter-weg" was recorded to a file *outside* the repository this
    integration owns, where nothing reads it back and nothing removes it.

    Nothing legitimate is turned away by this. Home Assistant's own
    frontend accepts letters, digits, `-` and `_` in a url_path and
    nothing more, and demands a `-` on top of that. A dashboard
    registered with a slash over the API is a ghost either way: the
    frontend looks a panel up by the *first* path segment alone, so the
    thing answers 404 and no browser ever reaches it. Refusing to record
    a ghost costs nobody anything; recording it costs a stray file and a
    tag namespace that two dashboards share.

    A rule, then, and not a repair: the answer is no history rather than
    a history somewhere else.
    """
    if not isinstance(key, str) or not key:
        return False
    if key in (".", ".."):
        return False
    if "/" in key or "\\" in key:
        return False
    # A control character would break the tag name it is put into and
    # split the log line it is reported in. Nothing means one.
    return not any(ch < " " or ch == "\x7f" for ch in key)


def deletions_to_record(
    tracked: Iterable[str], known: set[str] | None
) -> list[str]:
    """Which dashboards to record as deleted.

    `known` is None when Home Assistant could not be asked at all. Then
    nothing is recorded: turning "I could not look" into "all of them are
    gone" would mark every dashboard deleted in one pass.
    """
    if known is None:
        return []
    return sorted(set(tracked) - set(known))


def is_live(key: str, tracked: Iterable[str], known: set[str] | None) -> bool:
    """Whether a dashboard is there now, as opposed to merely recorded.

    Same reasoning as above in the other direction: if Home Assistant
    cannot be asked, nothing is declared gone.
    """
    if key not in set(tracked):
        return False
    return known is None or key in known


def is_absent(key: str, known: set[str] | None) -> bool:
    """Whether Home Assistant no longer has this dashboard at all.

    A different question from `is_live`, and the difference matters. This
    one ignores whether we ever recorded the dashboard: a live dashboard
    that was never captured is *not* absent, and treating it as absent
    would try to create one that already exists.

    False when Home Assistant cannot be asked. Declining to create a
    dashboard that is genuinely gone is a disappointment; creating one
    that is already there is a mess.
    """
    return known is not None and key not in known
