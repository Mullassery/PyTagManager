# Getting Started

PyTagManager is a debugging tool for Google Tag Manager. It combines website
discovery, GTM container inspection and real-browser runtime evidence so you can
explain why a tag, trigger, variable or event is not behaving as expected.

PyTagManager does **not** replace GTM and does not require GTM Preview to be the
only source of truth. It never modifies production automatically.

## 1. Install the CLI

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install pytagmanager
```

Browser diagnostics need the optional extras:

```bash
pip install 'pytagmanager[diagnostics]'
playwright install chromium
```

The published wheel is macOS arm64 plus an sdist. Other platforms build from
source and need a Rust toolchain. See the main README for current install
caveats.

## 2. Start with the GTM container

GTM container exports can be JSON or YAML. Export a container from GTM, then:

```bash
# Human-readable deterministic findings.
pytagmanager gtm inspect gtm-container.yaml

# Machine-readable report for CI or an issue.
pytagmanager gtm inspect gtm-container.yaml --format json -o gtm-findings.json
```

`gtm inspect` checks for things such as:

- tags with no firing trigger;
- dangling trigger references;
- duplicate tag/trigger names;
- `{{variable}}` references that are not defined;
- GA4 event tags missing an event name;
- duplicate GA4 event delivery on the same trigger set;
- the same measurement ID configured on multiple tags;
- unused triggers and paused tags.

These are deterministic findings with evidence and a remediation hint, not
claims that GTM itself is broken. A container snapshot is a configuration
observation; runtime behavior still needs browser evidence.

GTM import/export in PyTagManager is intentionally reviewable:

```bash
# Export a managed revision as a GTM-compatible snapshot.
pytagmanager gtm export GTM-ABC1234 --output gtm-review.yaml --format yaml

# Import a snapshot as a draft revision (never activated automatically).
pytagmanager gtm import gtm-container.yaml GTM-ABC1234 --json
```

Unsupported GTM trigger conditions or variable types are reported as warnings
instead of being silently reinterpreted.

## 3. Inspect the website and page code

MudFish-powered crawling finds pages and code evidence across an authorized
domain:

```bash
pytagmanager crawl https://example.com --max-pages 50
pytagmanager crawl https://example.com --render --sniff-analytics --max-pages 50
pytagmanager scan-tags https://example.com
pytagmanager dictionary https://example.com --max-pages 20 --format json
```

Use `--render` for client-rendered pages so the DOM and scripts seen by a real
browser are inspected, not just the initial HTML response. `scan-tags` reports
observable analytics/GTM signals; `dictionary` inventories dataLayer, cookies
and browser-storage variables.

## 4. Reproduce the behavior in a real browser

```bash
# Auto-derive interactions and diagnose a whole site.
pytagmanager diagnose https://example.com --max-pages 20

# Or test a specific journey.
pytagmanager diagnose https://example.com/checkout --scenario purchase.yml --format json

# Site-wide consistency and history.
pytagmanager diagnose https://example.com --site-wide --max-pages 100
pytagmanager diagnose https://example.com --site-wide --history health.json
```

The evidence chain is:

```
interaction -> DOM/JS -> dataLayer -> GTM trigger -> GTM tag -> network request
            -> analytics ingestion (when configured) -> diagnosis
```

Findings carry severity and confidence separately. A static observation is not
reported as a confirmed runtime defect.

## 5. Publish public configuration when testing SDK event flow

This is secondary integration tooling, not a measurement product.

```bash
pytagmanager cdn publish GTM-ABC1234 Production --root ./cdn --json
pytagmanager cdn verify --root ./cdn
```

The published tree contains immutable public configuration, a mutable latest
pointer, Web SDK assets and cache headers. It never contains destination
credentials, tag parameters or secret references.

## 6. Web SDK

```html
<script src="https://cdn.example.com/sdk/web/0.1.0/pytagmanager.js" defer></script>
<script>
  var client = PyTagManager.init({
    containerId: "GTM-ABC1234",
    endpoint: "https://www.example.com/collect",
    configUrl: "https://cdn.example.com/containers/CONTAINER_KEY/environments/production/latest.json"
  });
  client.setConsent({ analytics: true }, { source: "host", provenance: "explicit" });
  client.pageView();
  client.track("add_to_cart", { value: 19.99, currency: "USD" });
</script>
```

Use `client.debugSnapshot()` and `GET /healthz` to distinguish configuration,
consent, queueing, delivery and forwarding failures. See
[`sdk/web/README.md`](../sdk/web/README.md).

## 7. iOS SDK

Add the local Swift package from `sdk/ios` in Xcode, or depend on it from another
Swift package:

```swift
.package(path: "../PyTagManager/sdk/ios")
```

```swift
import PyTagManager

let client = try PyTagManager(
    containerId: "GTM-ABC1234",
    endpoint: URL(string: "https://www.example.com/collect")!,
    configURL: URL(string: "https://cdn.example.com/containers/KEY/environments/production/latest.json")!,
    storageDirectory: FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
)

try await client.configure()
client.setConsent(purposes: ["analytics": true])
client.trackScreen("Checkout")
client.track("purchase", properties: ["value": .number(42.5), "currency": .string("EUR")])
client.startAutoFlush(interval: 10)

let lifecycle = PyTagManagerLifecycleObserver(client: client)
lifecycle.start()

// Safe debugging: no event properties or credentials.
let snapshot = client.snapshot()
```

The lifecycle observer flushes on background/termination using a bounded
background task; delivery is best-effort and the observer does not start
auto-flush. The Swift package builds with the current Apple Command Line Tools
and passes 19 executable checks. XCTest execution needs Xcode; a macOS CI job is
defined but not locally verified. See [`sdk/ios/README.md`](../sdk/ios/README.md).

## 8. Android SDK

The Android library is in `sdk/android`. It requires JDK 17+ (verified with
JDK 21), Android SDK platform 35 and build-tools 35.0.0. Add the module to a
Gradle project, or build it directly with the committed wrapper:

```kotlin
val client = PyTagManager(
    context = applicationContext,
    containerId = "GTM-ABC1234",
    endpoint = URL("https://www.example.com/collect"),
    configUrl = URL("https://cdn.example.com/containers/KEY/environments/production/latest.json"),
)

client.configure()
client.setConsent(mapOf("analytics" to true))
client.trackScreen("Checkout")
client.track("purchase", JSONObject().put("value", 42.5).put("currency", "EUR"))
client.startAutoFlush(intervalSeconds = 15)
val snapshot = client.snapshot()
```

```bash
cd sdk/android
./gradlew :sdk:build
```

`./gradlew :sdk:build` passes locally, including Android lint and 28 JUnit tests
in the debug and release unit-test variants. These are JVM tests; emulator and
on-device instrumentation tests have not been run. See
[`sdk/android/README.md`](../sdk/android/README.md).

## 9. Host a collection endpoint continuously

The collection endpoint is intended for same-domain, first-party event flow. It
validates and deduplicates events; PyTagShield performs server policy and
destination forwarding.

Development:

```bash
pytagmanager serve-ingest \
  --host 127.0.0.1 \
  --port 8080 \
  --path /collect \
  --container GTM-ABC1234 \
  --dedupe-db /var/lib/pytagmanager/dedupe.sqlite3 \
  --pytagshield-url https://shield.internal.example \
  --pytagshield-token-ref env:PYTAGSHIELD_INGEST_TOKEN
```

`GET /healthz` reports limits, the dedupe backend and whether forwarding is
configured. `POST /collect` accepts one event or a batch. The endpoint does not expose secrets or
echo event properties.

For a persistent deployment, use the systemd unit and reverse-proxy examples in
[`deploy/collection`](../deploy/collection/README.md). Terminate TLS at the
proxy, keep the collection upstream on loopback, and expose one public origin
such as `https://www.example.com/collect` so browser and server-side events use
the same event ID and deduplication boundary.

## 10. Same-domain GTM, PyTagShield, and destination flow

Recommended public origin layout:

```
https://www.example.com
  /tagmanager/*   -> static CDN/cache for SDK assets and public config
  /collect        -> PyTagManager validation + idempotency
  /shield/*       -> internal/admin-only PyTagShield routes
```

Browser SDK events and server-side events should use the same `/collect`
endpoint and supply the same `event_id` when they represent the same logical
event. The collection service suppresses duplicates before forwarding. Eligible
events are then forwarded to PyTagShield, which applies consent/policy and
forwards to Meta, Google and other configured destinations.

Use `--dedupe-db` to persist dedupe claims across restarts and share them across
collector processes on one host. Without it, dedupe is in-memory. SQLite dedupe
is not a distributed lock for multiple hosts.

Important limitation: PyTagShield 0.2.0 generates its own server-side event ID.
Direct ingestion into PyTagShield bypasses PyTagManager's `event_id` dedupe.
Do not claim end-to-end deduplication unless both client and server paths go
through `/collect` or a shared idempotency layer is added. This is documented in
[`docs/architecture/multiplatform-extension.md`](architecture/multiplatform-extension.md).

## Where to go next

- [`docs/VISION.md`](VISION.md) — product positioning and principles.
- [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — implementation capability table.
- [`docs/architecture/multiplatform-extension.md`](architecture/multiplatform-extension.md) — SDK/CDN/collection contracts and exact verification status.
- [`docs/implementation-roadmap.md`](implementation-roadmap.md) — control-plane and integration history.
