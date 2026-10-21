import Foundation
import CryptoKit

public struct PublicConfigEvent: Codable, Equatable, Sendable {
    public var name: String
    public var purposes: [String]
    public var tagIds: [String]
    enum CodingKeys: String, CodingKey { case name, purposes; case tagIds = "tag_ids" }
}

public struct PublicConfig: Codable, Equatable, Sendable {
    public var schemaVersion: String
    public var kind: String
    public var containerId: String
    public var configVersion: String
    public var revisionNumber: Int
    public var publishedAt: String
    public var eventSchemaVersion: String
    public var events: [PublicConfigEvent]
    public var consentDefaults: [String: Bool]?
    public var compatibility: [String: JSONValue]?

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case kind
        case containerId = "container_id"
        case configVersion = "config_version"
        case revisionNumber = "revision_number"
        case publishedAt = "published_at"
        case eventSchemaVersion = "event_schema_version"
        case events
        case consentDefaults = "consent_defaults"
        case compatibility
    }

    public func event(named name: String) -> PublicConfigEvent? {
        events.first { $0.name == name }
    }
}

public enum ConfigError: Error, Equatable {
    case invalid(String)
    case integrityMismatch
}

public struct ConfigVerifier {
    public static func verifyIntegrity(_ data: Data) throws -> String {
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw ConfigError.invalid("config must be an object")
        }
        guard let integrity = object["integrity"] as? [String: Any],
              integrity["algorithm"] as? String == "sha256",
              let expected = integrity["digest"] as? String else {
            throw ConfigError.invalid("config is missing sha256 integrity metadata")
        }
        var unsigned = object
        unsigned.removeValue(forKey: "integrity")
        let canonical = try JSONSerialization.data(
            withJSONObject: unsigned,
            options: [.sortedKeys, .withoutEscapingSlashes]
        )
        let digest = SHA256.hash(data: canonical).map { String(format: "%02x", $0) }.joined()
        guard digest == expected else { throw ConfigError.integrityMismatch }
        return digest
    }

    public static func decode(_ data: Data) throws -> PublicConfig {
        let config = try JSONDecoder().decode(PublicConfig.self, from: data)
        guard config.schemaVersion == "1.0", config.kind == "pytagmanager.container" else {
            throw ConfigError.invalid("unsupported published configuration")
        }
        return config
    }
}
