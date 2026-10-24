import Foundation

public struct EventSource: Codable, Equatable, Sendable {
    public var platform: String
    public var sdkName: String
    public var sdkVersion: String
    public var appVersion: String?

    enum CodingKeys: String, CodingKey {
        case platform
        case sdkName = "sdk_name"
        case sdkVersion = "sdk_version"
        case appVersion = "app_version"
    }

    public init(platform: String = "ios", sdkName: String = "pytagmanager-ios",
                sdkVersion: String = "0.1.0", appVersion: String? = nil) {
        self.platform = platform
        self.sdkName = sdkName
        self.sdkVersion = sdkVersion
        self.appVersion = appVersion
    }
}

public struct Consent: Codable, Equatable, Sendable {
    public var purposes: [String: Bool]
    public var source: String
    public var updatedAt: String?
    public var provenance: String

    enum CodingKeys: String, CodingKey {
        case purposes, source, provenance
        case updatedAt = "updated_at"
    }

    public init(purposes: [String: Bool], source: String = "sdk",
                provenance: String = "explicit", updatedAt: String? = nil) {
        self.purposes = purposes
        self.source = source
        self.provenance = provenance
        self.updatedAt = updatedAt
    }

    public var grantedPurposes: Set<String> {
        Set(purposes.filter { $0.value }.keys)
    }
}

public struct Subject: Codable, Equatable, Sendable {
    public var id: String?
    public var type: String?
    public init(id: String?, type: String? = "user") {
        self.id = id
        self.type = type
    }
}

public struct Correlation: Codable, Equatable, Sendable {
    public var correlationId: String?
    public var sessionId: String?
    public var pageId: String?
    public var requestId: String?

    enum CodingKeys: String, CodingKey {
        case correlationId = "correlation_id"
        case sessionId = "session_id"
        case pageId = "page_id"
        case requestId = "request_id"
    }

    public init(correlationId: String? = nil, sessionId: String? = nil,
                pageId: String? = nil, requestId: String? = nil) {
        self.correlationId = correlationId
        self.sessionId = sessionId
        self.pageId = pageId
        self.requestId = requestId
    }
}

public struct Event: Codable, Equatable, Sendable {
    public static let schemaVersion = "1.0"
    public var schemaVersion: String
    public var eventId: String
    public var eventName: String
    public var timestamp: String
    public var source: EventSource
    public var containerId: String
    public var consent: Consent?
    public var subject: Subject?
    public var correlation: Correlation?
    public var configVersion: String?
    public var properties: [String: JSONValue]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case eventId = "event_id"
        case eventName = "event_name"
        case timestamp, source, consent, subject, correlation, properties
        case containerId = "container_id"
        case configVersion = "config_version"
    }

    public init(eventName: String, containerId: String, source: EventSource,
                consent: Consent? = nil, subject: Subject? = nil,
                correlation: Correlation? = nil, configVersion: String? = nil,
                properties: [String: JSONValue] = [:], timestamp: Date = Date()) {
        self.schemaVersion = Event.schemaVersion
        self.eventId = UUID().uuidString.lowercased()
        self.eventName = eventName
        self.timestamp = Event.formatTimestamp(timestamp)
        self.source = source
        self.containerId = containerId
        self.consent = consent
        self.subject = subject
        self.correlation = correlation
        self.configVersion = configVersion
        self.properties = properties
    }

    public static func formatTimestamp(_ date: Date) -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter.string(from: date)
    }

    public static func parseTimestamp(_ value: String) -> Date? {
        let fractional = ISO8601DateFormatter()
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = fractional.date(from: value) { return date }
        let plain = ISO8601DateFormatter()
        plain.formatOptions = [.withInternetDateTime]
        return plain.date(from: value)
    }

    public func validate(now: Date = Date()) throws {
        let allowedTop = Set(["schema_version", "event_id", "event_name", "timestamp",
                              "source", "container_id", "consent", "subject",
                              "correlation", "config_version", "properties"])
        let encoder = JSONEncoder()
        let object = try JSONSerialization.jsonObject(with: encoder.encode(self))
        guard let dictionary = object as? [String: Any] else {
            throw EventError.invalid("event must be an object")
        }
        if let unknown = Set(dictionary.keys).subtracting(allowedTop).sorted().first {
            throw EventError.invalid("unknown field: \(unknown)")
        }
        guard schemaVersion == Event.schemaVersion else {
            throw EventError.invalid("unsupported schema_version")
        }
        guard eventId.range(of: #"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"#,
                            options: .regularExpression) != nil else {
            throw EventError.invalid("event_id must be a lowercase UUIDv4")
        }
        guard eventName.range(of: #"^[A-Za-z][A-Za-z0-9_.-]{0,63}$"#,
                              options: .regularExpression) != nil else {
            throw EventError.invalid("event_name is invalid")
        }
        guard containerId.range(of: #"^[A-Za-z][A-Za-z0-9_-]{2,63}$"#,
                                options: .regularExpression) != nil else {
            throw EventError.invalid("container_id is invalid")
        }
        guard let parsed = Event.parseTimestamp(timestamp) else {
            throw EventError.invalid("timestamp must be RFC3339 UTC")
        }
        guard abs(now.timeIntervalSince(parsed)) <= 86_400 else {
            throw EventError.invalid("timestamp is outside the 24-hour window")
        }
        guard ["web", "android", "ios", "server"].contains(source.platform) else {
            throw EventError.invalid("source.platform is invalid")
        }
        guard source.sdkName.range(of: #"^[A-Za-z][A-Za-z0-9_.-]{0,63}$"#,
                                   options: .regularExpression) != nil else {
            throw EventError.invalid("source.sdk_name is invalid")
        }
        guard source.sdkVersion.range(of: #"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?$"#,
                                      options: .regularExpression) != nil else {
            throw EventError.invalid("source.sdk_version is invalid")
        }
        let sensitive = ["password", "passwd", "secret", "token", "api_key", "apikey",
                         "private_key", "credit_card", "card_number", "cvv", "ssn",
                         "social_security", "authorization"]
        for key in properties.keys {
            let lowered = key.lowercased()
            if sensitive.contains(where: { lowered.contains($0) }) {
                throw EventError.invalid("sensitive property is not allowed: \(key)")
            }
        }
        guard let consent else { return }
        guard !consent.purposes.isEmpty, consent.purposes.count <= 32 else {
            throw EventError.invalid("consent.purposes must contain 1...32 entries")
        }
        guard ["sdk", "host", "server", "unknown"].contains(consent.source) else {
            throw EventError.invalid("consent.source is invalid")
        }
        guard ["explicit", "default", "stored", "unknown"].contains(consent.provenance) else {
            throw EventError.invalid("consent.provenance is invalid")
        }
        if let updated = consent.updatedAt, Event.parseTimestamp(updated) == nil {
            throw EventError.invalid("consent.updated_at is invalid")
        }
        let serialized = try encoder.encode(self)
        guard serialized.count <= 32_768 else {
            throw EventError.invalid("event exceeds 32 KiB")
        }
    }

    public static func parse(_ data: Data) throws -> Event {
        let allowedTop = Set(["schema_version", "event_id", "event_name", "timestamp",
                              "source", "container_id", "consent", "subject",
                              "correlation", "config_version", "properties"])
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw EventError.invalid("event must be an object")
        }
        if let unknown = Set(object.keys).subtracting(allowedTop).sorted().first {
            throw EventError.invalid("unknown field: \(unknown)")
        }
        return try JSONDecoder().decode(Event.self, from: data)
    }
}

public enum EventError: Error, Equatable {
    case invalid(String)
}
