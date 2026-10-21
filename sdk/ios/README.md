# PyTagManager iOS SDK

Foundation-only Swift package for first-party event collection testing. It does
not execute remote JavaScript, does not load browser tags, and does not collect
advertising identifiers or location by default.

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
```

## What works

- Strict event-contract validation and shared fixtures.
- Verified public-config integrity using the same SHA-256/canonical JSON check as
  the Python publisher.
- Persistent bounded queue, consent-aware suppression and withdrawal purge.
- Bounded `flush()` retries and `startAutoFlush(interval:)` for continuous
  batching.
- Overlapping flushes are rejected instead of sending the same queued batch
  twice.
- Loaded public config must match the client's `containerId`.
- `snapshot()` returns safe diagnostics: endpoint, config version/source,
  consent purposes, queue depth, auto-flush state and recent diagnostics,
  without event properties or secrets.

## UIKit lifecycle integration

`PyTagManagerLifecycleObserver` flushes on `didEnterBackground` and
`willTerminate` by default, using a bounded iOS background task:

```swift
let lifecycle = PyTagManagerLifecycleObserver(client: client)
lifecycle.start()

// On teardown, if the host owns the observer's lifetime:
lifecycle.stop()
```

The observer does **not** start or stop auto-flush. Call
`client.startAutoFlush(interval:)` separately when continuous batching is
wanted. Background delivery is best-effort: iOS can suspend or terminate an app
before the request completes. Do not treat a background flush as guaranteed
delivery. `PyTagManagerLifecycleObserver` is unavailable in app extensions.

## Verification status

`swift build --package-path sdk/ios` succeeds and
`swift run --package-path sdk/ios PyTagManagerChecks` passes **19 executable
checks**, including config cache fallback, container mismatch rejection,
transient-event retention, and overlapping-flush prevention.

The XCTest target now covers shared fixtures, queue persistence, consent
withdrawal, transport behavior, auto-flush state and—on iOS—lifecycle observer
start/stop. `swift test` cannot run with only Apple Command Line Tools installed
because XCTest is part of Xcode. A macOS GitHub Actions job runs `swift test`,
but the UIKit lifecycle start/stop test requires an iOS simulator destination.
Neither XCTest result is verified locally; run the target in Xcode or CI before
claiming it passed.

Android/iOS SDKs are debugging tools for event flow, not a measurement or
attribution product.
