import XCTest
@testable import PyTagManager

final class PyTagManagerTests: XCTestCase {
    private var tempDirectory: URL!

    override func setUp() {
        super.setUp()
        tempDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
    }

    override func tearDown() {
        try? FileManager.default.removeItem(at: tempDirectory)
        super.tearDown()
    }

    func fixture(_ name: String) throws -> Data {
        guard let url = Bundle.module.url(forResource: name, withExtension: nil, subdirectory: "Fixtures") else {
            throw XCTSkip("missing fixture \(name)")
        }
        return try Data(contentsOf: url)
    }

    func testSharedIOSFixtureValidates() throws {
        let event = try Event.parse(try fixture("ios_purchase.json"))
        let fixedNow = Event.parseTimestamp("2026-10-20T12:02:03Z")!
        try event.validate(now: fixedNow)
        XCTAssertEqual(event.eventName, "purchase")
        XCTAssertEqual(event.source.platform, "ios")
        XCTAssertEqual(event.subject?.id, "user-42")
    }

    func testUnknownFieldIsRejected() throws {
        var object = try JSONSerialization.jsonObject(with: fixture("ios_purchase.json")) as! [String: Any]
        object["unexpected"] = true
        let data = try JSONSerialization.data(withJSONObject: object)
        XCTAssertThrowsError(try Event.parse(data))
    }

    func testSensitivePropertyIsRejected() throws {
        let event = Event(
            eventName: "purchase",
            containerId: "GTM-ABC1234",
            source: EventSource(),
            properties: ["access_token": .string("not-allowed")]
        )
        XCTAssertThrowsError(try event.validate())
    }

    func testQueuePersistsAndCapsAtMaximum() throws {
        let store = EventStore(directory: tempDirectory, maxEvents: 2)
        for index in 0..<3 {
            let event = Event(
                eventName: "screen_view",
                containerId: "GTM-ABC1234",
                source: EventSource(),
                properties: ["index": .number(Double(index))]
            )
            try store.enqueue(event)
        }
        XCTAssertEqual(store.load().count, 2)
        let reloaded = EventStore(directory: tempDirectory, maxEvents: 2)
        XCTAssertEqual(reloaded.load().count, 2)
    }

    func testPythonGeneratedConfigIntegrityVerifies() throws {
        let data = try fixture("public_config.json")
        let digest = try ConfigVerifier.verifyIntegrity(data)
        XCTAssertEqual(digest.count, 64)
        let config = try ConfigVerifier.decode(data)
        XCTAssertEqual(config.containerId, "GTM-ABC1234")
        XCTAssertEqual(config.event(named: "purchase")?.purposes, ["analytics"])
        XCTAssertEqual(config.consentDefaults?["analytics"], false)
    }

    func testTamperedConfigFailsIntegrity() throws {
        var object = try JSONSerialization.jsonObject(with: fixture("public_config.json")) as! [String: Any]
        object["config_version"] = "22222222-2222-4222-8222-222222222222"
        let data = try JSONSerialization.data(withJSONObject: object)
        XCTAssertThrowsError(try ConfigVerifier.verifyIntegrity(data))
    }

    func testConsentWithdrawalDropsQueuedEvents() throws {
        let client = try PyTagManager(
            containerId: "GTM-ABC1234",
            endpoint: URL(string: "https://collect.example.test/api/v1/events")!,
            storageDirectory: tempDirectory
        )
        client.setConsent(purposes: ["analytics": true])
        XCTAssertEqual(client.track("purchase"), .queued)
        XCTAssertEqual(client.store.count(), 1)
        client.setConsent(purposes: ["analytics": false])
        XCTAssertEqual(client.store.count(), 0)
        let snapshot = client.snapshot()
        XCTAssertEqual(snapshot.consentPurposes["analytics"], false)
        XCTAssertTrue(snapshot.recentDiagnostics.contains { $0.code == "consent_withdrawn" })
    }

    func testInvalidNameIsRejectedWithoutQueueing() throws {
        let client = try PyTagManager(
            containerId: "GTM-ABC1234",
            endpoint: URL(string: "https://collect.example.test/api/v1/events")!,
            storageDirectory: tempDirectory
        )
        guard case .invalid = client.track("Bad Name") else {
            return XCTFail("expected invalid outcome")
        }
        XCTAssertEqual(client.store.count(), 0)
    }

    func testHTTPSEndpointRequiredExceptLoopback() {
        XCTAssertThrowsError(try PyTagManager(
            containerId: "GTM-ABC1234",
            endpoint: URL(string: "http://collect.example.test/api/v1/events")!,
            storageDirectory: tempDirectory
        ))
        XCTAssertNoThrow(try PyTagManager(
            containerId: "GTM-ABC1234",
            endpoint: URL(string: "http://127.0.0.1:8080/api/v1/events")!,
            storageDirectory: tempDirectory
        ))
    }
}
