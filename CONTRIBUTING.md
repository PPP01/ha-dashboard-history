# Contributing

I’m building this project entirely on my own, mostly late in the evenings, and I genuinely appreciate any help. Here is what actually makes a difference.

First off: any feedback is welcome. Whether you love the integration, think it’s complete rubbish, or have concrete ideas for improvement - don’t hold back.

## Help me understand what real dashboards look like

Right now, I only have my own setup to benchmark design decisions against. My HA installation isn’t small - it packs plenty of integrations, entities, custom cards, and sees heavy daily use (and abuse for testing) - but it’s still just one machine.

I’d like to see real-world numbers from other installations. To make the right architectural calls, I need your data - just kidding, no panic. ;-) I’m solely interested in operational metrics from the integration itself:

- Counts of dashboards and recorded revisions
- Repository and individual history file sizes
- Age and timespan of the history
- Startup timing and execution overhead

This is where you can lend a huge hand. The integration can generate an **anonymized diagnostics report** via:  
**Settings → Devices & Services → Dashboard History → ⋮ → Download diagnostics**.

The part this integration writes contains raw counts and sizes, and strictly nothing about what is actually inside your dashboards. No dashboard names, no card configs, no entity IDs, and no titles. That promise is backed by automated tests (`tests/test_report.py`), not just empty words in a README.

One thing to know before you post it: Home Assistant wraps its own envelope around that part. It lists your Home Assistant version, installation type and time zone, and **every custom integration you have installed**. That envelope is outside what this integration controls, so have a look at the file and remove anything you would rather not publish.

If you’re willing to share yours, please [open an issue with the "Share diagnostics" template](https://github.com/PPP01/ha-dashboard-history/issues/new?template=diagnostics_report.yml) - anytime, whether everything is running smoothly or not. It’s genuinely the single most useful thing you can send my way.

## Found a bug, or have an idea?

Please [open an issue](https://github.com/PPP01/ha-dashboard-history/issues/new/choose). Bug reports and feature ideas are very welcome, even quick or half-baked ones. "This confused me" or "it would be nice if…" is a perfectly valid issue. I read every single one myself.

A few details that make a report easier to triage (none strictly required):

- What you expected to happen, and what happened instead.
- Whether it occurred once or happens reliably every time.
- Your Home Assistant version and how you installed the integration (HACS or manual).

If it’s a straightforward code bug, the diagnostics report won’t tell me much - a clear description of steps to reproduce is far more valuable. However, if the issue seems tied to dashboard scale (sheer size, card volume, deep commit history), attaching the report helps tremendously.

**A quick word on privacy:**  
Please be cautious when sharing data. In most bug reports, your personal entities, device names, or IP addresses are completely irrelevant. Once you post screenshots or raw logs publicly on GitHub, the whole internet can read them. Please blur or redact sensitive details beforehand.

## Running on an installation type I can’t test locally?

I develop and test against Home Assistant Container in a throwaway instance I can tear down and rebuild at will (see [`docs/development.md`](docs/development.md)). My own daily-use installation runs HA OS with HACS, but that's production - I'm not deliberately breaking things there the way I can in the throwaway instance.

I don't run Supervised or a bare Core environment at all, so I genuinely don’t know how the integration behaves on those until someone tells me. If you're running Supervised or Core - or you hit something on HA OS that a disposable test instance wouldn't show - that report is gold, just be sure to mention which setup you're on.

## If it’s useful to you

If Dashboard History makes your life easier, or simply takes the anxiety out of editing your Lovelace dashboards, I’d really appreciate a star on GitHub. Doesn’t cost you anything and puts a smile on my face. ;-)

Thank you for giving it a spin and for any feedback you share.