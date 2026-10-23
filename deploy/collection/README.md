# Hosting the collection endpoint

This directory contains a self-hosted, continuously running collection setup.
The endpoint validates and deduplicates events and can forward them to
PyTagShield. It is not a measurement/CDP service.

## What is hosted

```
browser SDK ─┐
             ├─> https://www.example.com/collect -> PyTagManager ingest -> PyTagShield -> destinations
server code ─┘                                      (validation/dedupe)      (policy/routing)
```

Point browser and server-side events at the **same public origin/path** so they
can share the same event ID and deduplication boundary.

## 1. Install on the host

```bash
sudo useradd --system --home /opt/pytagmanager --shell /usr/sbin/nologin pytagmanager
sudo python3 -m venv /opt/pytagmanager/.venv
sudo /opt/pytagmanager/.venv/bin/pip install /path/to/PyTagManager
```

The package must be built from this repository (or installed from the published
wheel). Browser diagnostics/Playwright are not required on the collection host.

## 2. Configure

```bash
sudo install -d -m 0750 -o pytagmanager -g pytagmanager /etc/pytagmanager
sudo install -m 0640 -o root -g pytagmanager \
  deploy/collection/ingest.env.example /etc/pytagmanager/ingest.env
sudoedit /etc/pytagmanager/ingest.env
```

Store secrets outside the environment file where possible, using the
`env:`/`file:` references supported by PyTagManager. The example uses
`PYTAGSHIELD_INGEST_TOKEN` from the systemd environment.

## 3. Run under systemd

```bash
sudo install -m 0644 deploy/collection/pytagmanager-ingest.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pytagmanager-ingest
curl --fail http://127.0.0.1:8080/healthz
```

The unit binds to loopback, runs unprivileged, uses a read-only filesystem
except for the state directory, and restarts on failure.

## 4. Terminate TLS and expose same-domain paths

Use the nginx example as a starting point:

```bash
sudo install -m 0644 deploy/collection/nginx-same-domain.conf /etc/nginx/conf.d/pytagmanager.conf
sudo nginx -t && sudo systemctl reload nginx
```

Routes:

- `/collect` -> `127.0.0.1:8080/collect` (no caching)
- `/tagmanager/` -> static published CDN tree (immutable assets; latest pointer
  must not be cached)
- `/shield/` -> restrict to internal/admin networks; do not expose PyTagShield
  administration publicly

## Operational notes and limitations

- The example enables durable deduplication with `--dedupe-db` (SQLite, WAL
  mode). Claims survive restarts and are shared by collector processes on the
  same host. The store contains event ids, state and expiry only, never event
  properties.
- SQLite is a single-host store, not a distributed lock. Do not place it on an
  unsupported network filesystem. For multiple hosts, route to one collector
  or add a shared idempotency service.
- A crashed in-flight claim becomes reclaimable after
  `--dedupe-claim-ttl-seconds` (60 seconds in the example). Keep this above the
  maximum forwarding timeout.
- Without `--dedupe-db`, dedupe is in-memory and is lost on restart.
- PyTagShield 0.2.0 generates its own event ID. Direct ingestion into
  PyTagShield bypasses PyTagManager's `event_id` dedupe. Send server events
  through `/collect` when end-to-end duplicate suppression is required.
- No destination routing happens in PyTagManager. PyTagShield owns consent
  policy, minimization, destination authorization and forwarding to Meta,
  Google and other destinations.
- The endpoint acknowledges validated events even when no forwarder is
  configured; acknowledgement is not delivery proof.
- The systemd example trusts `X-Forwarded-For` only from `127.0.0.1/32` because
  nginx runs on the same host. Change `PYTAGMANAGER_TRUSTED_PROXY_CIDR` to the
  exact proxy CIDR if the proxy is remote. Do not trust forwarding headers from
  arbitrary peers; malformed or untrusted values fall back to the socket peer.
- Rate limits charge batches per event, not per HTTP request. Limits remain
  in-process and are not a distributed quota across collector replicas.
- Do not put bearer tokens, destination secrets or private keys in public config
  or SDK assets. Use environment/file references on the server.
