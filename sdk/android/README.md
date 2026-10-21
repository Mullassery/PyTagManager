# PyTagManager Android SDK

Kotlin library for first-party event collection testing. It does not execute
remote JavaScript or browser tags, and it does not collect advertising IDs or
location by default.

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
```

## What is implemented

- Event contract validation and shared GTM-agnostic event fields.
- Public config integrity verification with a canonical JSON SHA-256 check.
- File-backed bounded queue, consent suppression and withdrawal purge.
- Blocking `flush()` plus `startAutoFlush`/`stopAutoFlush` for continuous
  batching.
- `snapshot()` for safe debugging without event properties or secrets.

## Build and test

Requirements: JDK 17 or newer (verified with JDK 21), Android SDK platform 35,
build-tools 35.0.0, and `ANDROID_HOME`/`ANDROID_SDK_ROOT` pointing at the SDK.
The committed Gradle wrapper uses Gradle 8.14.6.

```bash
cd sdk/android
./gradlew :sdk:build
```

Verified locally with `./gradlew :sdk:build`: debug and release AARs build,
lint passes, and all **28 JUnit tests** pass in both debug and release unit-test
variants (10 event contract, 5 public config, 4 queue, 9 client behavior).
Coverage includes shared fixtures, strict validation, sensitive-key rejection,
integrity verification, queue bounds, batching, retry/transient handling,
auto-flush, config cache fallback and consent withdrawal.

These are JVM unit tests against the Android API stubs. No emulator, device, or
Android Studio installation was used, so instrumentation tests and on-device
behavior remain unverified. Add the `sdk/android` module to your Gradle project.
`minSdk` is 26 and no third-party runtime dependency is required.
