# A throwaway Home Assistant for testing

The plain test suite (`python3 -m pytest tests/`) covers the modules that
know nothing about Home Assistant. Everything else — `capture.py`,
`services.py`, `snapshot.py`, `operations.py`, `websocket_api.py`,
`panel.py` — cannot be reached that way, and **every defect found in this
project so far has been in exactly those modules**, while the suite stayed
green through all of them.

This instance closes that gap. It is disposable: delete dashboards, restart
it twenty times, break the configuration.

```bash
docker compose -f docker/compose.yaml up -d
python3 tests/integration/run_checks.py
```

The checks create an owner account on the first run and keep a long-lived
token beside the instance's configuration.

## Where things live

| What | Where | Why |
| --- | --- | --- |
| Compose file | `docker/compose.yaml` | Versioned; holds no secrets |
| Configuration, `.storage`, token | `../ha-dashboard-history-test/` | **Outside this repository.** This repo is public and the token is a bearer credential |
| The integration | Bind-mounted from the working tree | Edit, restart the container, test. Ten seconds |

The bind mount is the point. On a real installation reached over a network
mount it is impossible: SSHFS and its kin refuse to create symlinks, and a
symlink would be resolved on the Home Assistant side, where this
repository's path does not exist. Hence HACS there — and this here.

## The trap this hit, and its actual cause

**Containers had no outbound route on the machine this was built on.** The
image pulled fine — that goes through the Docker daemon on the host network
— but nothing inside a container reached the internet, so Home Assistant
could not install `dulwich` and setting the integration up timed out.

The cause was one line in `/etc/docker/daemon.json`:

```json
{ "iptables": false }
```

With that, Docker creates no iptables rules at all: no `DOCKER` chains and,
crucially, no MASQUERADE for the bridge subnets. What made it confusing is
that **inbound port publishing still worked**, because Docker falls back to
its userland proxy for that. Published ports and outbound NAT are two
different mechanisms and only one was missing.

The fix is to let Docker manage iptables again:

```bash
sudo cp /etc/docker/daemon.json /etc/docker/daemon.json.bak
sudo rm /etc/docker/daemon.json      # "iptables": true is the default
sudo systemctl restart docker
```

Then check, and mind the restart policies — containers set to `no` do not
come back by themselves:

```bash
sudo iptables -t nat -S | grep MASQUERADE     # one line per bridge subnet
docker run --rm alpine sh -c "wget -qO- https://pypi.org/simple/ >/dev/null && echo ok"
```

Docker 29 leaves the `FORWARD` policy on `ACCEPT` and works through its own
`DOCKER-USER` / `DOCKER-FORWARD` chains, so this did not disturb a VPN
connection on the same host. Older versions flipped that policy to `DROP`;
if this machine ever runs one, check the VPN afterwards.

**Do not try to pre-install the requirement into `/config/deps`.** That was
the first attempt here and it is a dead end: Home Assistant Container runs
as root outside a virtualenv and installs requirements into the image's own
`site-packages`, not into `deps`. Which also means the installation lives
inside the container — recreate it and Home Assistant installs again on the
next start, so the network has to work.

## One more thing about this machine

WSL runs in `networkingMode=bridged` here, so this machine has a real
address on the LAN. Anything bound to `0.0.0.0` is reachable from the whole
network, which is why the compose file publishes to `127.0.0.1` and why
that detail is not cosmetic. Home Assistant's own `http: server_host:`
setting did *not* take effect in this container; Docker's port binding did.

## What this does not replace

Acceptance on the real installation. This is where defects are found
cheaply; production is where a version is accepted. There the dashboards
are 262 KB, other integrations reach into the same Lovelace internals, and
the timing is real. Two different jobs.

Not reproducible here at all: Supervisor and add-on behaviour, and the HACS
installation path itself.
