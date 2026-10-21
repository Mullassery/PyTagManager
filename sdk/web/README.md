# PyTagManager Web SDK

Version `0.1.0`. The SDK collects declarative events, applies the published
container's event allowlist and consent purposes locally, and posts batches to
a configured collection endpoint. It does **not** evaluate or execute remote
JavaScript, and it never sends events directly to vendor destinations.

```html
<script
  src="https://cdn.example.com/pytagmanager/sdk/web/0.1.0/pytagmanager.js"
  defer
></script>
<script>
  window.addEventListener("DOMContentLoaded", function () {
    var client = PyTagManager.init({
      containerId: "GTM-ABC1234",
      endpoint: "https://collect.example.com/api/v1/events",
      configUrl:
        "https://cdn.example.com/pytagmanager/containers/CONTAINER_KEY/environments/production/latest.json"
    });
    client.setConsent({ analytics: true }, { source: "host", provenance: "explicit" });
    client.pageView();
    client.track("add_to_cart", { value: 19.99, currency: "USD" });
  });
</script>
```

The CDN path above is illustrative; use the URLs returned by
`pytagmanager cdn publish`.

## Behavior

- Config is fetched asynchronously and cached locally. Immutable revision
  configs include a SHA-256 self-checksum; verification fails closed when
  WebCrypto is available.
- The event allowlist and purpose requirements come from the published
  config. Unknown events and denied consent purposes are not queued.
- Sensitive property names (for example `user_email`, `password`, `card_number`)
  are rejected. Hashed forms such as `email_sha256` are allowed.
- Batches retry transient failures with bounded exponential backoff and
  jitter. The server performs deduplication using `event_id`; this client is
  not exactly-once.
- Queue persistence is **off by default** because queued events can contain
  personal data. Enable `persistQueue: true` only after reviewing your
  retention and consent requirements.
- SPA page views are opt-in: call `client.startAutoPageViews()` or pass
  `autoPageViews: true`. It observes `pushState`, `replaceState`, and
  `popstate`, and skips duplicate paths.
- `allowInsecure: true` allows HTTP only for loopback test endpoints. Production
  endpoints must use HTTPS.

## Debugging

`client.getDiagnostics()` returns counters only. `client.debugSnapshot()` adds
the container id, endpoint, config version/source, consent purposes and current
queue depth. It does not include event properties or credentials. Pair it with
`GET /healthz` on the collection endpoint to distinguish configuration,
consent, queueing and forwarding failures.

## Development

```bash
cd sdk/web
npm test
npm run build
```

`dist/pytagmanager.js` is a plain JavaScript bundle (not minified) plus a
generated SHA-256 file. No runtime dependencies are required.
