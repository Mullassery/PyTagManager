import Foundation

public struct DebugSnapshot: Codable, Equatable, Sendable {
    public var containerId: String
    public var endpoint: String
    public var configVersion: String?
    public var configSource: String
    public var consentPurposes: [String: Bool]
    public var queueCount: Int
    public var autoFlushActive: Bool
    public var recentDiagnostics: [Diagnostic]
}

public enum TrackOutcome: Equatable, Sendable {
    case queued
    case suppressed(String)
    case invalid(String)
}

public struct FlushResult: Equatable, Sendable {
    public var sent: Int
    public var remaining: Int
    public var httpStatus: Int?
    public var error: String?
}

public enum ClientError: Error, Equatable {
    case invalidEndpoint
    case configUnavailable(String)
    case invalidResponse
}

private struct BatchEnvelope: Encodable {
    let schemaVersion: String
    let events: [Event]
    enum CodingKeys: String, CodingKey { case schemaVersion = "schema_version"; case events }
}

public final class PyTagManager {
    public let containerId: String
    public let endpoint: URL
    public let configURL: URL?
    public let store: EventStore
    private let session: URLSession
    private let sdkName: String
    private let sdkVersion: String
    private let appVersion: String?
    private let allowTrackingWithoutConfig: Bool
    private let configCacheURL: URL
    private let lock = NSLock()
    private var config: PublicConfig?
    private var configSource = "none"
    private var currentConsent: Consent?
    private var diagnostics: [Diagnostic] = []
    private var autoFlushTimer: Timer?
    private var autoFlushInterval: TimeInterval?
    private var flushInProgress = false

    public init(containerId: String, endpoint: URL, configURL: URL? = nil,
                storageDirectory: URL, session: URLSession = .shared,
                sdkVersion: String = "0.1.0", appVersion: String? = nil,
                allowTrackingWithoutConfig: Bool = true) throws {
        guard endpoint.scheme == "https" || PyTagManager.isLoopback(endpoint) else {
            throw ClientError.invalidEndpoint
        }
        self.containerId = containerId
        self.endpoint = endpoint
        self.configURL = configURL
        self.session = session
        self.sdkName = "pytagmanager-ios"
        self.sdkVersion = sdkVersion
        self.appVersion = appVersion
        self.allowTrackingWithoutConfig = allowTrackingWithoutConfig
        self.store = EventStore(directory: storageDirectory)
        self.configCacheURL = storageDirectory.appendingPathComponent("public-config.json")
    }

    private static func isLoopback(_ url: URL) -> Bool {
        guard let host = url.host else { return false }
        return host == "127.0.0.1" || host == "::1" || host == "localhost"
    }

    public func setConsent(purposes: [String: Bool], source: String = "sdk",
                           provenance: String = "explicit") {
        let consent = Consent(
            purposes: purposes,
            source: source,
            provenance: provenance,
            updatedAt: Event.formatTimestamp(Date())
        )
        lock.lock()
        currentConsent = consent
        lock.unlock()
        let withdrawn = Set(purposes.filter { !$0.value }.keys)
        if !withdrawn.isEmpty {
            store.remove { event in
                guard let granted = event.consent?.grantedPurposes else { return true }
                return !granted.isDisjoint(with: withdrawn)
            }
            record("consent_withdrawn", "Removed unsent events for withdrawn purposes.")
        }
    }

    public func configure() async throws -> PublicConfig {
        guard let configURL else {
            throw ClientError.configUnavailable("no configURL was supplied")
        }
        do {
            let (data, response) = try await session.data(from: configURL)
            guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
                throw ClientError.invalidResponse
            }
            _ = try ConfigVerifier.verifyIntegrity(data)
            let loaded = try ConfigVerifier.decode(data)
            try validateContainer(loaded)
            try? FileManager.default.createDirectory(
                at: configCacheURL.deletingLastPathComponent(),
                withIntermediateDirectories: true
            )
            try? data.write(to: configCacheURL, options: [.atomic])
            storeConfig(loaded, source: "network")
            record("config_loaded", "Loaded verified public configuration \(loaded.configVersion).")
            return loaded
        } catch {
            if let cached = try? loadCachedConfig() {
                record("config_cache_fallback", "Remote config failed; using verified cache.")
                return cached
            }
            record("config_failed", "Remote config and cache were unavailable.")
            throw ClientError.configUnavailable(String(describing: error))
        }
    }

    private func loadCachedConfig() throws -> PublicConfig {
        let data = try Data(contentsOf: configCacheURL)
        _ = try ConfigVerifier.verifyIntegrity(data)
        let loaded = try ConfigVerifier.decode(data)
        try validateContainer(loaded)
        storeConfig(loaded, source: "cache")
        return loaded
    }

    private func validateContainer(_ loaded: PublicConfig) throws {
        guard loaded.containerId == containerId else {
            throw ClientError.configUnavailable(
                "public configuration belongs to a different container"
            )
        }
    }

    @discardableResult
    public func track(_ name: String, properties: [String: JSONValue] = [:],
                      subjectId: String? = nil,
                      correlation: Correlation? = nil) -> TrackOutcome {
        lock.lock()
        let activeConfig = config
        let consent = currentConsent
        lock.unlock()
        if let eventConfig = activeConfig?.event(named: name) {
            let required = Set(eventConfig.purposes)
            let granted = consent?.grantedPurposes ?? []
            if !required.isEmpty && required.isDisjoint(with: granted) {
                record("event_suppressed", "Event \(name) lacks a granted purpose.")
                return .suppressed("required consent purpose is not granted")
            }
        } else if activeConfig != nil && !allowTrackingWithoutConfig {
            record("event_suppressed", "Event \(name) is not in the active configuration.")
            return .suppressed("event is not in the active configuration")
        }
        let event = Event(
            eventName: name,
            containerId: containerId,
            source: EventSource(platform: "ios", sdkName: sdkName,
                                sdkVersion: sdkVersion, appVersion: appVersion),
            consent: consent,
            subject: subjectId.map { Subject(id: $0) },
            correlation: correlation,
            configVersion: activeConfig?.configVersion,
            properties: properties
        )
        do {
            try event.validate()
            try store.enqueue(event)
            return .queued
        } catch {
            record("event_invalid", "Event \(name) failed local validation.")
            return .invalid(String(describing: error))
        }
    }

    @discardableResult
    public func trackScreen(_ name: String, properties: [String: JSONValue] = [:],
                            subjectId: String? = nil) -> TrackOutcome {
        var merged = properties
        merged["screen_name"] = .string(name)
        return track("screen_view", properties: merged, subjectId: subjectId)
    }

    public func startAutoFlush(interval: TimeInterval = 5) {
        stopAutoFlush()
        let boundedInterval = max(1, interval)
        let timer = Timer(timeInterval: boundedInterval, repeats: true) { [weak self] _ in
            guard let self else { return }
            Task { _ = await self.flush() }
        }
        RunLoop.main.add(timer, forMode: .common)
        lock.lock()
        autoFlushTimer = timer
        autoFlushInterval = boundedInterval
        lock.unlock()
    }

    public func stopAutoFlush() {
        lock.lock()
        let timer = autoFlushTimer
        autoFlushTimer = nil
        autoFlushInterval = nil
        lock.unlock()
        timer?.invalidate()
    }

    public var isAutoFlushActive: Bool {
        lock.lock()
        defer { lock.unlock() }
        return autoFlushInterval != nil
    }

    private func claimFlush() -> Bool {
        lock.lock()
        defer { lock.unlock() }
        guard !flushInProgress else { return false }
        flushInProgress = true
        return true
    }

    private func releaseFlush() {
        lock.lock()
        flushInProgress = false
        lock.unlock()
    }

    public func flush(maxRetries: Int = 3) async -> FlushResult {
        guard claimFlush() else {
            return FlushResult(sent: 0, remaining: store.count(), httpStatus: nil,
                               error: "flush already in progress")
        }
        defer { releaseFlush() }
        let events = Array(store.load().prefix(100))
        guard !events.isEmpty else {
            return FlushResult(sent: 0, remaining: store.count(), httpStatus: nil, error: nil)
        }
        let encoder = JSONEncoder()
        var lastStatus: Int?
        var lastError: String?
        for attempt in 0..<max(1, maxRetries) {
            let body: Data
            do {
                body = try encoder.encode(BatchEnvelope(
                    schemaVersion: Event.schemaVersion,
                    events: events
                ))
            } catch {
                record("flush_encoding_failed", "Could not encode the queued batch.")
                return FlushResult(sent: 0, remaining: store.count(), httpStatus: nil,
                                   error: "batch encoding failed")
            }
            var request = URLRequest(url: endpoint)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.setValue("pytagmanager-ios/\(sdkVersion)", forHTTPHeaderField: "User-Agent")
            request.httpBody = body
            do {
                let (data, response) = try await session.data(for: request)
                guard let http = response as? HTTPURLResponse else {
                    throw ClientError.invalidResponse
                }
                lastStatus = http.statusCode
                if (200..<300).contains(http.statusCode) {
                    let retained = removeDelivered(events, response: data)
                    return FlushResult(sent: events.count - retained,
                                       remaining: store.count(),
                                       httpStatus: http.statusCode,
                                       error: nil)
                }
                lastError = "HTTP \(http.statusCode)"
                if http.statusCode != 429 && http.statusCode < 500 { break }
            } catch {
                lastError = String(describing: error)
            }
            if attempt + 1 < maxRetries {
                let delay = UInt64(250 * (1 << attempt))
                try? await Task.sleep(nanoseconds: delay * 1_000_000)
            }
        }
        record("flush_failed", "Batch delivery did not complete.")
        return FlushResult(sent: 0, remaining: store.count(), httpStatus: lastStatus,
                           error: lastError)
    }

    @discardableResult
    private func removeDelivered(_ events: [Event], response: Data) -> Int {
        let sentIds = Set(events.map { $0.eventId })
        var retained = Set<String>()
        if let raw = try? JSONSerialization.jsonObject(with: response),
           let object = raw as? [String: Any],
           let results = object["results"] as? [[String: Any]] {
            for result in results {
                let status = result["status"] as? String ?? ""
                if status == "transient_error" || status == "rate_limited" {
                    if let id = result["event_id"] as? String { retained.insert(id) }
                }
            }
        }
        store.remove(ids: sentIds.subtracting(retained))
        return retained.count
    }

    private func storeConfig(_ loaded: PublicConfig, source: String) {
        lock.lock()
        config = loaded
        configSource = source
        lock.unlock()
    }

    public func snapshot() -> DebugSnapshot {
        lock.lock()
        let loadedConfig = config
        let source = configSource
        let consent = currentConsent
        let recent = Array(diagnostics.suffix(20))
        let autoFlush = autoFlushInterval != nil
        lock.unlock()
        return DebugSnapshot(
            containerId: containerId,
            endpoint: endpoint.absoluteString,
            configVersion: loadedConfig?.configVersion,
            configSource: source,
            consentPurposes: consent?.purposes ?? [:],
            queueCount: store.count(),
            autoFlushActive: autoFlush,
            recentDiagnostics: recent
        )
    }

    private func record(_ code: String, _ message: String,
                        metadata: [String: String] = [:]) {
        let diagnostic = Diagnostic(
            timestamp: Event.formatTimestamp(Date()),
            code: code,
            message: message,
            metadata: metadata
        )
        lock.lock()
        diagnostics.append(diagnostic)
        if diagnostics.count > 100 { diagnostics.removeFirst(diagnostics.count - 100) }
        lock.unlock()
    }
}
