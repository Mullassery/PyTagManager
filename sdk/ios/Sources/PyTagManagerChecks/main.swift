import Foundation
import PyTagManager

var checks = 0
var failures: [String] = []

func expect(_ condition: @autoclosure () -> Bool, _ message: String) {
    checks += 1
    if !condition() { failures.append(message) }
}

func fixture(_ name: String) throws -> Data {
    guard let url = Bundle.module.url(forResource: name, withExtension: nil, subdirectory: "Fixtures") else {
        throw ClientError.invalidResponse
    }
    return try Data(contentsOf: url)
}

do {
    let event = try Event.parse(fixture("ios_purchase.json"))
    let fixedNow = Event.parseTimestamp("2026-10-20T12:02:03Z")!
    try event.validate(now: fixedNow)
    expect(event.eventName == "purchase", "iOS fixture event name")
    expect(event.subject?.id == "user-42", "iOS fixture subject")

    let configData = try fixture("public_config.json")
    let digest = try ConfigVerifier.verifyIntegrity(configData)
    let config = try ConfigVerifier.decode(configData)
    expect(digest.count == 64, "config digest length")
    expect(config.event(named: "purchase")?.purposes == ["analytics"], "config event purposes")
    expect(config.consentDefaults?["analytics"] == false, "config consent default")

    let directory = FileManager.default.temporaryDirectory
        .appendingPathComponent(UUID().uuidString, isDirectory: true)
    defer { try? FileManager.default.removeItem(at: directory) }
    let store = EventStore(directory: directory, maxEvents: 2)
    for index in 0..<3 {
        try store.enqueue(Event(
            eventName: "screen_view",
            containerId: "GTM-ABC1234",
            source: EventSource(),
            properties: ["index": .number(Double(index))]
        ))
    }
    expect(store.load().count == 2, "queue cap")

    let client = try PyTagManager(
        containerId: "GTM-ABC1234",
        endpoint: URL(string: "https://collect.example.test/api/v1/events")!,
        storageDirectory: directory
    )
    client.setConsent(purposes: ["analytics": true])
    expect(client.track("purchase") == .queued, "track queued")
    client.setConsent(purposes: ["analytics": false])
    expect(client.store.count() == 0, "withdrawal purges queued events")
    expect(client.snapshot().recentDiagnostics.contains { $0.code == "consent_withdrawn" },
           "diagnostic recorded")
} catch {
    failures.append("unexpected error: \(error)")
}

await runTransportChecks(expect: { condition, message in expect(condition, message) })

if failures.isEmpty {
    print("PASS \(checks) Swift checks")
} else {
    for failure in failures { print("FAIL \(failure)") }
    exit(1)
}
