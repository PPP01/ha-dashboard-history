# Team memory: ha-dashboard-history

Shared knowledge that no other team member should have to rediscover
on their own. Local, personal observations don't belong here — see the
global rule for that.

## PyYAML never picks the fast parser on its own

`yaml.safe_load()` **always** uses the pure Python parser, even when
`libyaml` (the C parser) is available in the same process — PyYAML
doesn't choose automatically. Measured on 2026-09-11 in the test
container against a 262 KiB dashboard: 501 ms pure Python versus
54.8 ms via `yaml.CSafeLoader`, a factor of 8–9. Since `dfc30c1`,
`yaml_io.load()` goes through
`getattr(yaml, "CSafeLoader", yaml.SafeLoader)`, falling back to the
slow parser wherever `libyaml` is missing.

**Before using `yaml.safe_load()` or `yaml.load()` anywhere in this
project or a sibling one:** check whether `CSafeLoader` is available
and whether switching is worth it — don't assume the fast path is
already active just because `libyaml` is installed.

## libyaml's C emitter mangles emoji

The reverse move — switching to `CSafeDumper` for *writing* too — is a
trap. libyaml escapes every character above the Basic Multilingual
Plane (emoji) as `\U0001F7E2`, regardless of `allow_unicode`, and a
string holding one can then no longer use block style (`|`). Umlauts
and simple symbols like `✓` sit inside the BMP and aren't affected —
the bug only shows up with an actual emoji in the text.

Measured on 2026-09-11 against all 98 dashboards in the test bank: 4
of them came out as different bytes with the C emitter. For
`yaml_io.dump()` that's not an edge case, since determinism is the
whole point of the module — a title with an emoji is an ordinary
thing, and a faster emitter would reformat such dashboards on the next
save and write a change into the history that nobody made.

`_Dumper` in `yaml_io.py` therefore deliberately stays on
`yaml.SafeDumper` (pure Python), not `yaml.CSafeDumper`. A test
(`test_emoji_is_written_as_itself_not_escaped`) guards this; if it
goes red, `_Dumper` was given a C base class.

**Before switching any YAML *emitter* or *dumper* to a C
implementation:** check with an emoji in the text, beyond your own
test data, not just with umlauts — those pass the test unnoticed while
emoji fail.
