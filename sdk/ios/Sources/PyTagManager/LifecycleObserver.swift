#if canImport(UIKit)
import Foundation
import UIKit

/// Connects PyTagManager's bounded flush to UIKit application lifecycle events.
///
/// The observer does not start or stop auto-flush. Call `startAutoFlush` from
/// the host application when continuous batching is wanted. A background flush
/// is best-effort: iOS may suspend or terminate the app before delivery ends.
@available(iOSApplicationExtension, unavailable)
public final class PyTagManagerLifecycleObserver {
    public struct Options: Sendable {
        public var flushOnDidEnterBackground: Bool
        public var flushOnWillTerminate: Bool
        public var backgroundTaskName: String

        public init(flushOnDidEnterBackground: Bool = true,
                    flushOnWillTerminate: Bool = true,
                    backgroundTaskName: String = "com.pytagmanager.flush") {
            self.flushOnDidEnterBackground = flushOnDidEnterBackground
            self.flushOnWillTerminate = flushOnWillTerminate
            self.backgroundTaskName = backgroundTaskName
        }
    }

    private final class BackgroundTaskToken {
        var identifier: UIBackgroundTaskIdentifier = .invalid
    }

    public let client: PyTagManager
    public let options: Options
    private let lock = NSLock()
    private var observers: [NSObjectProtocol] = []
    private var activeTask: BackgroundTaskToken?

    public init(client: PyTagManager, options: Options = Options()) {
        self.client = client
        self.options = options
    }

    deinit {
        stop()
    }

    public var isObserving: Bool {
        lock.lock()
        defer { lock.unlock() }
        return !observers.isEmpty
    }

    /// Registers lifecycle observers. Calling this more than once is a no-op.
    public func start() {
        lock.lock()
        guard observers.isEmpty else {
            lock.unlock()
            return
        }
        lock.unlock()

        let center = NotificationCenter.default
        var registered: [NSObjectProtocol] = []
        if options.flushOnDidEnterBackground {
            registered.append(center.addObserver(
                forName: UIApplication.didEnterBackgroundNotification,
                object: nil,
                queue: .main
            ) { [weak self] _ in
                self?.flushInBackground()
            })
        }
        if options.flushOnWillTerminate {
            registered.append(center.addObserver(
                forName: UIApplication.willTerminateNotification,
                object: nil,
                queue: .main
            ) { [weak self] _ in
                self?.flushInBackground()
            })
        }

        lock.lock()
        if observers.isEmpty {
            observers = registered
            lock.unlock()
        } else {
            lock.unlock()
            registered.forEach(center.removeObserver)
        }
    }

    public func stop() {
        lock.lock()
        let registered = observers
        observers = []
        lock.unlock()
        registered.forEach(NotificationCenter.default.removeObserver)
    }

    private func flushInBackground() {
        lock.lock()
        guard activeTask == nil else {
            lock.unlock()
            return
        }
        let token = BackgroundTaskToken()
        activeTask = token
        lock.unlock()

        token.identifier = UIApplication.shared.beginBackgroundTask(
            withName: options.backgroundTaskName
        ) { [weak self] in
            self?.end(token)
        }

        Task { [weak self] in
            guard let self else { return }
            _ = await self.client.flush()
            await MainActor.run {
                self.end(token)
            }
        }
    }

    private func end(_ token: BackgroundTaskToken) {
        lock.lock()
        let identifier = token.identifier
        token.identifier = .invalid
        if activeTask === token {
            activeTask = nil
        }
        lock.unlock()

        if identifier != .invalid {
            UIApplication.shared.endBackgroundTask(identifier)
        }
    }
}
#endif
