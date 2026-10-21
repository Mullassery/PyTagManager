import Foundation
import PyTagManager

final class CheckURLProtocol: URLProtocol {
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
        guard let handler = CheckURLProtocol.handler() else {
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

func runTransportChecks(expect: (Bool, String) -> Void) async {
    let root = FileManager.default.temporaryDirectory
        .appendingPathComponent("pytagmanager-checks-\(UUID().uuidString)", isDirectory: true)
    defer { try? FileManager.default.removeItem(at: root) }

    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [CheckURLProtocol.self]
    let session = URLSession(configuration: configuration)

    func fixture(_ name: String) -> Data? {
        guard let url = Bundle.module.url(forResource: name, withExtension: nil,
                                          subdirectory: "Fixtures") else { return nil }
        return try? Data(contentsOf: url)
    }

    func client(containerId: String = "GTM-ABC1234",
                storage: URL) throws -> PyTagManager {
        try PyTagManager(
            containerId: containerId,
            endpoint: URL(string: "https://collect.example.test/api/v1/events")!,
            configURL: URL(string: "https://cdn.example.test/public-config.json"),
            storageDirectory: storage,
            session: session
        )
    }

    let config = fixture("public_config.json") ?? Data()
    CheckURLProtocol.setHandler { request in
        let response = HTTPURLResponse(url: request.url!, statusCode: 200,
                                       httpVersion: nil, headerFields: nil)!
        return (response, config)
    }

    do {
        let mismatch = try client(containerId: "GTM-OTHER1",
                                  storage: root.appendingPathComponent("mismatch"))
        _ = try await mismatch.configure()
        expect(false, "config container mismatch is rejected")
    } catch ClientError.configUnavailable {
        expect(true, "config container mismatch is rejected")
    } catch {
        expect(false, "config container mismatch produces the expected error")
    }

    do {
        let cacheDir = root.appendingPathComponent("cache")
        let first = try client(storage: cacheDir)
        let loaded = try await first.configure()
        expect(loaded.configVersion == "11111111-1111-4111-8111-111111111111",
               "transport config loads")
        CheckURLProtocol.setHandler { _ in throw URLError(.notConnectedToInternet) }
        let second = try client(storage: cacheDir)
        _ = try await second.configure()
        expect(second.snapshot().configSource == "cache",
               "verified config cache fallback")
    } catch {
        expect(false, "config cache fallback completed without error")
    }

    do {
        let flushClient = try client(storage: root.appendingPathComponent("flush"))
        flushClient.setConsent(purposes: ["analytics": true])
        _ = flushClient.track("purchase")
        _ = flushClient.track("add_to_cart")
        let queued = flushClient.store.load()
        CheckURLProtocol.setHandler { request in
            let body: [String: Any] = [
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
        let result = await flushClient.flush()
        expect(result.sent == 1 && result.remaining == 1,
               "flush retains transient events")
        expect(flushClient.store.load().first?.eventId == queued[1].eventId,
               "flush retries the correct event")
    } catch {
        expect(false, "flush checks completed without error")
    }

    do {
        let concurrent = try client(storage: root.appendingPathComponent("concurrent"))
        concurrent.setConsent(purposes: ["analytics": true])
        _ = concurrent.track("purchase")
        CheckURLProtocol.setHandler { request in
            Thread.sleep(forTimeInterval: 0.2)
            let response = HTTPURLResponse(url: request.url!, statusCode: 202,
                                           httpVersion: nil, headerFields: nil)!
            return (response, Data("{}".utf8))
        }
        async let first = concurrent.flush()
        try? await Task.sleep(nanoseconds: 50_000_000)
        let second = await concurrent.flush()
        let firstResult = await first
        expect(firstResult.sent == 1, "first concurrent flush sends")
        expect(second.error == "flush already in progress",
               "overlapping flush is rejected")
        expect(CheckURLProtocol.countRequests() == 1,
               "overlapping flush does not send twice")
    } catch {
        expect(false, "concurrent flush checks completed without error")
    }

    let auto = try? client(storage: root.appendingPathComponent("auto"))
    if let auto {
        auto.startAutoFlush(interval: 60)
        expect(auto.snapshot().autoFlushActive, "auto-flush state is visible")
        auto.stopAutoFlush()
        expect(!auto.snapshot().autoFlushActive, "auto-flush state clears")
    }
}
