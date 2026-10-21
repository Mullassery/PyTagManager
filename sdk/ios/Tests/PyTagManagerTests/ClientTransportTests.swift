import XCTest
@testable import PyTagManager

final class MockURLProtocol: URLProtocol {
    typealias Handler = (URLRequest) throws -> (HTTPURLResponse, Data)

    private static let lock = NSLock()
    private static var storedHandler: Handler?
    private(set) static var requestCount = 0

    static func setHandler(_ handler: Handler?) {
        lock.lock()
        storedHandler = handler
        requestCount = 0
        lock.unlock()
    }

    static func countRequests() -> Int {
        lock.lock()
        defer { lock.unlock() }
        return requestCount
    }

    private static func handler() -> Handler? {
        lock.lock()
        defer { lock.unlock() }
        requestCount += 1
        return storedHandler
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let handler = MockURLProtocol.handler() else {
            client?.urlProtocol(self, didFailWithError: URLError(.unknown))
            return
        }
        do {
            let (response, data) = try handler(request)
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {}
}

final class ClientTransportTests: XCTestCase {
    private var tempDirectory: URL!
    private var session: URLSession!

    override func setUp() {
        super.setUp()
        tempDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MockURLProtocol.self]
        session = URLSession(configuration: configuration)
        MockURLProtocol.setHandler(nil)
    }

    override func tearDown() {
        MockURLProtocol.setHandler(nil)
        session.invalidateAndCancel()
        try? FileManager.default.removeItem(at: tempDirectory)
        super.tearDown()
    }

    private func fixture(_ name: String) throws -> Data {
        guard let url = Bundle.module.url(forResource: name, withExtension: nil,
                                          subdirectory: "Fixtures") else {
            throw XCTSkip("missing fixture \(name)")
        }
        return try Data(contentsOf: url)
    }

    private func client(containerId: String = "GTM-ABC1234") throws -> PyTagManager {
        try PyTagManager(
            containerId: containerId,
            endpoint: URL(string: "https://collect.example.test/api/v1/events")!,
            configURL: URL(string: "https://cdn.example.test/public-config.json"),
            storageDirectory: tempDirectory,
            session: session
        )
    }

    func testConfigureRejectsConfigurationForAnotherContainer() async throws {
        let config = try fixture("public_config.json")
        MockURLProtocol.setHandler { request in
            let response = HTTPURLResponse(url: request.url!, statusCode: 200,
                                           httpVersion: nil, headerFields: nil)!
            return (response, config)
        }
        let client = try client(containerId: "GTM-OTHER1")
        do {
            _ = try await client.configure()
            XCTFail("expected container mismatch")
        } catch ClientError.configUnavailable {
            XCTAssertEqual(client.snapshot().configSource, "none")
        }
    }

    func testConfigureUsesVerifiedCacheWhenRemoteFails() async throws {
        let config = try fixture("public_config.json")
        MockURLProtocol.setHandler { request in
            let response = HTTPURLResponse(url: request.url!, statusCode: 200,
                                           httpVersion: nil, headerFields: nil)!
            return (response, config)
        }
        let first = try client()
        let loaded = try await first.configure()
        XCTAssertEqual(loaded.containerId, "GTM-ABC1234")
        XCTAssertEqual(first.snapshot().configSource, "network")

        MockURLProtocol.setHandler { _ in throw URLError(.notConnectedToInternet) }
        let second = try client()
        let cached = try await second.configure()
        XCTAssertEqual(cached.configVersion, loaded.configVersion)
        XCTAssertEqual(second.snapshot().configSource, "cache")
    }

    func testFlushRetainsOnlyTransientEvents() async throws {
        let client = try client()
        client.setConsent(purposes: ["analytics": true])
        XCTAssertEqual(client.track("purchase"), .queued)
        XCTAssertEqual(client.track("add_to_cart"), .queued)
        let queued = client.store.load()
        XCTAssertEqual(queued.count, 2)

        MockURLProtocol.setHandler { request in
            XCTAssertEqual(request.httpMethod, "POST")
            let body = [
                "results": [
                    ["event_id": queued[0].eventId, "status": "accepted"],
                    ["event_id": queued[1].eventId, "status": "transient_error"],
                ],
            ]
            let data = try JSONSerialization.data(withJSONObject: body)
            let response = HTTPURLResponse(url: request.url!, statusCode: 202,
                                           httpVersion: nil, headerFields: nil)!
            return (response, data)
        }

        let result = await client.flush()
        XCTAssertEqual(result.sent, 1)
        XCTAssertEqual(result.remaining, 1)
        XCTAssertEqual(result.httpStatus, 202)
        XCTAssertEqual(client.store.load().first?.eventId, queued[1].eventId)
    }

    func testConcurrentFlushIsRejectedInsteadOfSendingTwice() async throws {
        let client = try client()
        client.setConsent(purposes: ["analytics": true])
        XCTAssertEqual(client.track("purchase"), .queued)
        MockURLProtocol.setHandler { request in
            Thread.sleep(forTimeInterval: 0.2)
            let response = HTTPURLResponse(url: request.url!, statusCode: 202,
                                           httpVersion: nil, headerFields: nil)!
            return (response, Data("{}".utf8))
        }

        async let first = client.flush()
        try await Task.sleep(nanoseconds: 50_000_000)
        let second = await client.flush()
        let firstResult = await first
        XCTAssertEqual(firstResult.sent, 1)
        XCTAssertEqual(second.error, "flush already in progress")
        XCTAssertEqual(MockURLProtocol.countRequests(), 1)
    }

    func testAutoFlushStateIsVisibleInSnapshot() throws {
        let client = try client()
        XCTAssertFalse(client.isAutoFlushActive)
        client.startAutoFlush(interval: 60)
        XCTAssertTrue(client.isAutoFlushActive)
        XCTAssertTrue(client.snapshot().autoFlushActive)
        client.stopAutoFlush()
        XCTAssertFalse(client.isAutoFlushActive)
        XCTAssertFalse(client.snapshot().autoFlushActive)
    }

    #if canImport(UIKit)
    @available(iOSApplicationExtension, unavailable)
    func testLifecycleObserverStartAndStopAreIdempotent() throws {
        let client = try client()
        let observer = PyTagManagerLifecycleObserver(client: client)
        XCTAssertFalse(observer.isObserving)
        observer.start()
        observer.start()
        XCTAssertTrue(observer.isObserving)
        observer.stop()
        observer.stop()
        XCTAssertFalse(observer.isObserving)
    }
    #endif
}
