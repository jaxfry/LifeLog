import Foundation

private struct BackgroundChunk: Codable, Sendable {
    let artifactID: UUID
    let offset: Int64
    let byteCount: Int64
    let chunkPath: String
}

final class BackgroundUploadManager: NSObject, @unchecked Sendable {
    static let shared = BackgroundUploadManager()
    static let identifier = "com.lifelog.ios.artifact-uploads"
    private let persistenceLock = NSLock()
    private var pendingPersistence = 0
    private var persistenceWaiters: [CheckedContinuation<Void, Never>] = []

    private lazy var session: URLSession = {
        let configuration = URLSessionConfiguration.background(withIdentifier: Self.identifier)
        configuration.sessionSendsLaunchEvents = true
        configuration.waitsForConnectivity = true
        configuration.isDiscretionary = false
        configuration.timeoutIntervalForResource = 7 * 24 * 60 * 60
        return URLSession(configuration: configuration, delegate: self, delegateQueue: nil)
    }()

    private override init() {
        super.init()
        _ = session
    }

    func schedule(
        request: URLRequest,
        chunkURL: URL,
        artifactID: UUID,
        offset: Int64,
        byteCount: Int64
    ) throws {
        let metadata = BackgroundChunk(
            artifactID: artifactID,
            offset: offset,
            byteCount: byteCount,
            chunkPath: chunkURL.path
        )
        let task = session.uploadTask(with: request, fromFile: chunkURL)
        task.taskDescription = String(data: try JSONEncoder().encode(metadata), encoding: .utf8)
        task.resume()
    }

    func activeArtifactIDs() async -> Set<UUID> {
        await withCheckedContinuation { continuation in
            session.getAllTasks { tasks in
                let identifiers = Set(tasks.compactMap { task -> UUID? in
                    guard
                        let description = task.taskDescription,
                        let data = description.data(using: .utf8),
                        let metadata = try? JSONDecoder().decode(BackgroundChunk.self, from: data)
                    else { return nil }
                    return metadata.artifactID
                })
                continuation.resume(returning: identifiers)
            }
        }
    }

    func cancel(artifactIDs: Set<UUID>) async {
        guard !artifactIDs.isEmpty else { return }
        await withCheckedContinuation { continuation in
            session.getAllTasks { tasks in
                for task in tasks {
                    guard
                        let description = task.taskDescription,
                        let data = description.data(using: .utf8),
                        let metadata = try? JSONDecoder().decode(BackgroundChunk.self, from: data),
                        artifactIDs.contains(metadata.artifactID)
                    else { continue }
                    task.cancel()
                }
                continuation.resume()
            }
        }
    }

    private func beginPersistence() {
        persistenceLock.withLock { pendingPersistence += 1 }
    }

    private func endPersistence() {
        let waiters = persistenceLock.withLock { () -> [CheckedContinuation<Void, Never>] in
            pendingPersistence -= 1
            guard pendingPersistence == 0 else { return [] }
            defer { persistenceWaiters.removeAll() }
            return persistenceWaiters
        }
        waiters.forEach { $0.resume() }
    }

    private func waitForPersistence() async {
        await withCheckedContinuation { continuation in
            let resumeNow = persistenceLock.withLock { () -> Bool in
                if pendingPersistence == 0 { return true }
                persistenceWaiters.append(continuation)
                return false
            }
            if resumeNow { continuation.resume() }
        }
    }
}

extension BackgroundUploadManager: URLSessionTaskDelegate, URLSessionDelegate {
    func urlSession(
        _ session: URLSession,
        task: URLSessionTask,
        didCompleteWithError error: Error?
    ) {
        guard
            let description = task.taskDescription,
            let data = description.data(using: .utf8),
            let metadata = try? JSONDecoder().decode(BackgroundChunk.self, from: data)
        else { return }
        let status = (task.response as? HTTPURLResponse)?.statusCode
        let success = error == nil && status.map { (200..<300).contains($0) } == true
        try? FileManager.default.removeItem(atPath: metadata.chunkPath)
        beginPersistence()
        Task {
            try? await LocalVault.shared.finishBackgroundChunk(
                artifactID: metadata.artifactID,
                newOffset: metadata.offset + metadata.byteCount,
                success: success,
                error: error?.localizedDescription ?? (status.map { "Server returned HTTP \($0)." })
            )
            endPersistence()
        }
    }

    func urlSessionDidFinishEvents(forBackgroundURLSession session: URLSession) {
        Task { @MainActor in
            await waitForPersistence()
            let completion = LifeLogAppDelegate.backgroundCompletionHandlers.removeValue(forKey: Self.identifier)
            await LifeLogApp.sharedModel?.refreshSnapshot()
            await LifeLogApp.sharedModel?.syncEngine.syncNow()
            completion?()
        }
    }
}
