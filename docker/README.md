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

The bind mount is the point. On the production installation it is
impossible: the mount there is SSHFS, which refuses to create symlinks, and
a symlink would be resolved on the Home Assistant side where this
repository's path does not exist. Hence HACS there — and this here.

## Two traps, both hit while setting this up

**Docker's bridge network had no outbound route** on the machine this was
built on. The image pulled fine, because that goes through the Docker
daemon on the host network, but nothing inside a container could reach the
internet — so Home Assistant could not install `dulwich`, and setting the
integration up timed out. `net.ipv4.ip_forward` was on; the NAT rules were
missing. Diagnosis, if it happens again:

```bash
docker run --rm --network bridge <image> python -c \
  "import socket; socket.create_connection(('151.101.128.223',443),6)"
docker run --rm --network host   <image> python -c \
  "import socket; socket.create_connection(('151.101.128.223',443),6)"
```

Bridge failing while host succeeds is the signature.

**The requirement therefore has to be pre-installed**, and it has to land
where Home Assistant looks. Not flat in `deps/`:

```bash
# Wrong: pip --target puts it in /config/deps/dulwich
# Right: Home Assistant expects the user-site layout
docker exec dashboard-history-test env PYTHONUSERBASE=/config/deps \
  python -m pip install --user dulwich==1.2.14
```

Ask the instance itself rather than guessing the path:

```bash
docker exec dashboard-history-test env PYTHONUSERBASE=/config/deps \
  python -c "import site; print(site.getusersitepackages())"
```

## What this does not replace

Acceptance on the real installation. This is where defects are found
cheaply; production is where a version is accepted. There the dashboards
are 262 KB, other integrations reach into the same Lovelace internals, and
the timing is real. Two different jobs.

Not reproducible here at all: Supervisor and add-on behaviour, and the HACS
installation path itself.
