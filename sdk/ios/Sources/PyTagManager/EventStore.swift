import Foundation

public struct Diagnostic: Codable, Equatable, Sendable {
    public var timestamp: String
    public var code: String
    public var message: String
    public var metadata: [String: String]
}

public final class EventStore {
    public let directory: URL
    public let maxEvents: Int
    private let fileURL: URL
    private let lock = NSLock()

    public init(directory: URL, maxEvents: Int = 1_000) {
        self.directory = directory
        self.maxEvents = maxEvents
        self.fileURL = directory.appendingPathComponent("events.json")
    }

    public func load() -> [Event] {
        lock.lock()
        defer { lock.unlock() }
        guard let data = try? Data(contentsOf: fileURL) else { return [] }
        return (try? JSONDecoder().decode([Event].self, from: data)) ?? []
    }

    @discardableResult
    public func enqueue(_ event: Event) throws -> Int {
        lock.lock()
        defer { lock.unlock() }
        var events = loadUnlocked()
        events.append(event)
        if events.count > maxEvents {
            events.removeFirst(events.count - maxEvents)
        }
        try saveUnlocked(events)
        return events.count
    }

    public func remove(ids: Set<String>) {
        lock.lock()
        defer { lock.unlock() }
        var events = loadUnlocked()
        events.removeAll { ids.contains($0.eventId) }
        try? saveUnlocked(events)
    }

    public func remove(where predicate: (Event) -> Bool) {
        lock.lock()
        defer { lock.unlock() }
        var events = loadUnlocked()
        events.removeAll(where: predicate)
        try? saveUnlocked(events)
    }

    public func count() -> Int {
        lock.lock()
        defer { lock.unlock() }
        return loadUnlocked().count
    }

    private func loadUnlocked() -> [Event] {
        guard let data = try? Data(contentsOf: fileURL) else { return [] }
        return (try? JSONDecoder().decode([Event].self, from: data)) ?? []
    }

    private func saveUnlocked(_ events: [Event]) throws {
        try FileManager.default.createDirectory(
            at: directory, withIntermediateDirectories: true
        )
        let data = try JSONEncoder().encode(events)
        try data.write(to: fileURL, options: [.atomic])
    }
}
