import CryptoKit
import Combine
import Foundation

private struct VaultIndex: Codable {
    var signals: [BufferedSignal] = []
    var artifacts: [BufferedArtifact] = []
}

private struct VaultJournalEntry: Codable {
    var signals: [BufferedSignal] = []
    var artifacts: [BufferedArtifact] = []
    var removedSignalIDs: [UUID] = []
    var removedArtifactIDs: [UUID] = []
}

extension Notification.Name {
    static let lifeLogVaultChanged = Notification.Name("com.lifelog.ios.vault-changed")
}

actor LocalVault {
    static let shared = LocalVault()

    private let root: URL
    private let artifactsDirectory: URL
    private let indexURL: URL
    private let journalURL: URL
    private let encoder: JSONEncoder
    private let decoder: JSONDecoder
    private var index: VaultIndex
    private let key: SymmetricKey
    private let keyIsPersistent: Bool
    private var journalEntries = 0
    private let artifactChunkSize = 2 * 1_024 * 1_024
    private var dedupeKeys: Set<String> = []

    init(
        fileManager: FileManager = .default,
        rootURL: URL? = nil,
        encryptionKey: SymmetricKey? = nil
    ) {
        let support = fileManager.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        root = rootURL ?? support.appendingPathComponent("LifeLogVault", isDirectory: true)
        artifactsDirectory = root.appendingPathComponent("Artifacts", isDirectory: true)
        indexURL = root.appendingPathComponent("queue.index", isDirectory: false)
        journalURL = root.appendingPathComponent("queue.journal", isDirectory: false)
        encoder = JSONEncoder()
        decoder = JSONDecoder()
        encoder.dateEncodingStrategy = .iso8601
        decoder.dateDecodingStrategy = .iso8601

        try? fileManager.createDirectory(at: artifactsDirectory, withIntermediateDirectories: true)
        try? fileManager.setAttributes(
            [.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication],
            ofItemAtPath: root.path
        )

        if let encryptionKey {
            key = encryptionKey
            keyIsPersistent = true
        } else if let saved = KeychainStore.data(for: "vault-key"), saved.count == 32 {
            key = SymmetricKey(data: saved)
            keyIsPersistent = true
        } else {
            let generated = SymmetricKey(size: .bits256)
            let data = generated.withUnsafeBytes { Data($0) }
            key = generated
            keyIsPersistent = (try? KeychainStore.set(data, for: "vault-key")) != nil
        }

        if
            let encrypted = try? Data(contentsOf: indexURL),
            let box = try? AES.GCM.SealedBox(combined: encrypted),
            let clear = try? AES.GCM.open(box, using: key),
            let restored = try? decoder.decode(VaultIndex.self, from: clear)
        {
            index = restored
        } else {
            index = VaultIndex()
        }
        let replay = Self.replayJournal(
            from: journalURL,
            key: key,
            decoder: decoder,
            into: &index
        )
        journalEntries = replay.entryCount
        if replay.validBytes < replay.totalBytes,
           let handle = try? FileHandle(forWritingTo: journalURL) {
            try? handle.truncate(atOffset: UInt64(replay.validBytes))
            try? handle.synchronize()
            try? handle.close()
        }
        let referencedArtifacts = Set(index.artifacts.map(\.localFilename))
        let storedArtifacts = (try? fileManager.contentsOfDirectory(
            at: artifactsDirectory,
            includingPropertiesForKeys: nil,
            options: [.skipsHiddenFiles]
        )) ?? []
        for storedArtifact in storedArtifacts where !referencedArtifacts.contains(storedArtifact.lastPathComponent) {
            try? fileManager.removeItem(at: storedArtifact)
        }
        dedupeKeys = Set(index.signals.map(Self.dedupeKey))
    }

    func append(
        kind: SignalKind,
        occurredAt: Date = .now,
        endedAt: Date? = nil,
        payload: [String: String],
        origin: String? = nil,
        privacyRules: PrivacyRules
    ) throws {
        try append(
            [SignalObservation(
                kind: kind,
                occurredAt: occurredAt,
                endedAt: endedAt,
                payload: payload,
                origin: origin
            )],
            privacyRules: privacyRules
        )
    }

    func append(_ observations: [SignalObservation], privacyRules: PrivacyRules) throws {
        try ensureKeyAvailable()
        let engine = PrivacyEngine(rules: privacyRules)
        var added: [BufferedSignal] = []
        for observation in observations {
            let decision = engine.process(payload: observation.payload, origin: observation.origin)
            let signal = BufferedSignal(
                kind: observation.kind,
                occurredAt: observation.occurredAt,
                endedAt: observation.endedAt,
                payload: decision.payload,
                state: decision.excluded ? .excluded : .queued,
                redactionAudit: decision.audit
            )
            let dedupeKey = Self.dedupeKey(for: signal)
            guard dedupeKeys.insert(dedupeKey).inserted else { continue }
            index.signals.append(signal)
            added.append(signal)
        }
        try appendJournal(VaultJournalEntry(signals: added))
    }

    @discardableResult
    func preserveArtifact(
        sourceURL: URL,
        kind: SignalKind,
        mimeType: String,
        intent: String? = nil,
        context: [String: String] = [:],
        captureID: UUID = UUID(),
        createdAt: Date = .now
    ) throws -> BufferedArtifact {
        try ensureKeyAvailable()
        let artifactID = UUID()
        let localFilename = "\(artifactID.uuidString).artifact"
        let destination = artifactsDirectory.appendingPathComponent(localFilename, isDirectory: true)
        try FileManager.default.createDirectory(at: destination, withIntermediateDirectories: true)
        try FileManager.default.setAttributes(
            [.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication],
            ofItemAtPath: destination.path
        )
        let input = try FileHandle(forReadingFrom: sourceURL)
        defer { try? input.close() }
        var hasher = SHA256()
        var byteCount: Int64 = 0
        var chunkIndex = 0
        while let bytes = try input.read(upToCount: artifactChunkSize), !bytes.isEmpty {
            hasher.update(data: bytes)
            byteCount += Int64(bytes.count)
            let sealed = try seal(bytes)
            let chunkURL = destination.appendingPathComponent(String(format: "%08d.sealed", chunkIndex))
            try sealed.write(to: chunkURL, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
            chunkIndex += 1
        }
        let digest = hasher.finalize().map { String(format: "%02x", $0) }.joined()
        let artifact = BufferedArtifact(
            id: artifactID,
            captureID: captureID,
            kind: kind,
            createdAt: createdAt,
            localFilename: localFilename,
            originalFilename: sourceURL.lastPathComponent,
            mimeType: mimeType,
            byteCount: byteCount,
            sha256: digest,
            intent: intent,
            context: context,
            state: .queued,
            uploadedBytes: 0,
            attempts: 0,
            redactionAudit: []
        )
        index.artifacts.append(artifact)
        try journal(artifact: artifact)
        return artifact
    }

    func decryptedUploadChunk(
        for artifact: BufferedArtifact,
        offset: Int64,
        maximum: Int
    ) throws -> URL {
        guard offset >= 0, offset < artifact.byteCount, maximum > 0 else {
            throw CocoaError(.fileReadCorruptFile)
        }
        let encryptedURL = artifactsDirectory.appendingPathComponent(artifact.localFilename)
        let staging = root.appendingPathComponent("UploadChunks", isDirectory: true)
        try FileManager.default.createDirectory(at: staging, withIntermediateDirectories: true)
        let output = staging.appendingPathComponent("\(artifact.id.uuidString)-\(offset).chunk")

        var result = Data()
        result.reserveCapacity(maximum)
        var cursor = offset
        while result.count < maximum, cursor < artifact.byteCount {
            let chunkIndex = Int(cursor / Int64(artifactChunkSize))
            let position = Int(cursor % Int64(artifactChunkSize))
            let chunkURL = encryptedURL.appendingPathComponent(String(format: "%08d.sealed", chunkIndex))
            let encrypted = try Data(contentsOf: chunkURL, options: [.mappedIfSafe])
            let clear = try AES.GCM.open(AES.GCM.SealedBox(combined: encrypted), using: key)
            guard position < clear.count else { throw CocoaError(.fileReadCorruptFile) }
            let count = min(maximum - result.count, clear.count - position)
            result.append(clear[position..<(position + count)])
            cursor += Int64(count)
        }
        try result.write(to: output, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
        return output
    }

    func snapshot() -> VaultSnapshot {
        let pendingStates: Set<QueueState> = [.locallyCommitted, .redacted, .queued, .uploading, .processing, .retrying, .failed]
        return VaultSnapshot(
            signals: Array(index.signals.sorted { $0.occurredAt > $1.occurredAt }.prefix(500)),
            artifacts: Array(index.artifacts.sorted { $0.createdAt > $1.createdAt }.prefix(200)),
            totalSignalCount: index.signals.count,
            totalArtifactCount: index.artifacts.count,
            totalPendingCount: index.signals.count { pendingStates.contains($0.state) }
                + index.artifacts.count { pendingStates.contains($0.state) }
        )
    }

    func pendingSignals(limit: Int = 100) -> [BufferedSignal] {
        let now = Date()
        return index.signals.filter {
            [.queued, .retrying].contains($0.state) && ($0.nextAttemptAt ?? .distantPast) <= now
        }.prefix(limit).map { $0 }
    }

    func pendingArtifacts(limit: Int = 10) -> [BufferedArtifact] {
        let now = Date()
        return index.artifacts.filter {
            [.queued, .retrying, .uploading].contains($0.state) && ($0.nextAttemptAt ?? .distantPast) <= now
        }.prefix(limit).map { $0 }
    }

    func markSignal(_ id: UUID, state: QueueState, error: String? = nil) throws {
        guard let offset = index.signals.firstIndex(where: { $0.id == id }) else { return }
        index.signals[offset].state = state
        index.signals[offset].lastError = error
        if state == .retrying {
            index.signals[offset].attempts += 1
            index.signals[offset].nextAttemptAt = retryDate(attempt: index.signals[offset].attempts)
        }
        try journal(signal: index.signals[offset])
    }

    func markSignals(_ ids: Set<UUID>, state: QueueState, error: String? = nil) throws {
        guard !ids.isEmpty else { return }
        var changed: [BufferedSignal] = []
        for offset in index.signals.indices where ids.contains(index.signals[offset].id) {
            index.signals[offset].state = state
            index.signals[offset].lastError = error
            if state == .retrying {
                index.signals[offset].attempts += 1
                index.signals[offset].nextAttemptAt = retryDate(attempt: index.signals[offset].attempts)
            } else {
                index.signals[offset].nextAttemptAt = nil
            }
            changed.append(index.signals[offset])
        }
        try appendJournal(VaultJournalEntry(signals: changed))
    }

    func updateArtifact(_ artifact: BufferedArtifact) throws {
        guard let offset = index.artifacts.firstIndex(where: { $0.id == artifact.id }) else { return }
        index.artifacts[offset] = artifact
        try journal(artifact: artifact)
    }

    func finishBackgroundChunk(
        artifactID: UUID,
        newOffset: Int64,
        success: Bool,
        error: String?
    ) throws {
        guard let offset = index.artifacts.firstIndex(where: { $0.id == artifactID }) else { return }
        guard index.artifacts[offset].state != .excluded else { return }
        if success {
            index.artifacts[offset].uploadedBytes = newOffset
            index.artifacts[offset].state = .queued
            index.artifacts[offset].lastError = nil
            index.artifacts[offset].nextAttemptAt = nil
        } else {
            index.artifacts[offset].attempts += 1
            index.artifacts[offset].state = .retrying
            index.artifacts[offset].lastError = error
            index.artifacts[offset].nextAttemptAt = retryDate(attempt: index.artifacts[offset].attempts)
        }
        try journal(artifact: index.artifacts[offset])
    }

    func excludeRecent(minutes: Int) throws -> [BufferedArtifact] {
        let cutoff = Date().addingTimeInterval(TimeInterval(-max(minutes, 1) * 60))
        var changedSignals: [BufferedSignal] = []
        for offset in index.signals.indices where index.signals[offset].occurredAt >= cutoff {
            index.signals[offset].payload = [:]
            index.signals[offset].state = .excluded
            index.signals[offset].redactionAudit.append("user-excluded-recent-window")
            changedSignals.append(index.signals[offset])
        }
        dedupeKeys = Set(index.signals.map(Self.dedupeKey))
        var changedArtifacts: [BufferedArtifact] = []
        for offset in index.artifacts.indices
        where index.artifacts[offset].createdAt >= cutoff && index.artifacts[offset].state != .serverVerified {
            let artifact = index.artifacts[offset]
            try? FileManager.default.removeItem(at: artifactsDirectory.appendingPathComponent(artifact.localFilename))
            index.artifacts[offset].state = .excluded
            index.artifacts[offset].redactionAudit.append("user-excluded-recent-window")
            changedArtifacts.append(index.artifacts[offset])
        }
        try appendJournal(VaultJournalEntry(signals: changedSignals, artifacts: changedArtifacts))
        return changedArtifacts
    }

    func pruneVerified(olderThan cutoff: Date) throws {
        let removedSignalIDs = index.signals
            .filter { $0.state == .serverVerified && $0.occurredAt < cutoff }
            .map(\.id)
        index.signals.removeAll { $0.state == .serverVerified && $0.occurredAt < cutoff }
        let expired = index.artifacts.filter { $0.state == .serverVerified && $0.createdAt < cutoff }
        index.artifacts.removeAll { $0.state == .serverVerified && $0.createdAt < cutoff }
        if !removedSignalIDs.isEmpty || !expired.isEmpty {
            dedupeKeys = Set(index.signals.map(Self.dedupeKey))
            try appendJournal(
                VaultJournalEntry(
                    removedSignalIDs: removedSignalIDs,
                    removedArtifactIDs: expired.map(\.id)
                )
            )
            for artifact in expired {
                try? FileManager.default.removeItem(at: artifactsDirectory.appendingPathComponent(artifact.localFilename))
            }
            try compact()
        }
    }

    private func retryDate(attempt: Int) -> Date {
        let ceiling = min(pow(2, Double(attempt)) * 15, 6 * 60 * 60)
        return Date().addingTimeInterval(ceiling + Double.random(in: 0...10))
    }

    private func journal(signal: BufferedSignal) throws {
        try appendJournal(VaultJournalEntry(signals: [signal]))
    }

    private func journal(artifact: BufferedArtifact) throws {
        try appendJournal(VaultJournalEntry(artifacts: [artifact]))
    }

    private func appendJournal(_ entry: VaultJournalEntry) throws {
        try ensureKeyAvailable()
        guard
            !entry.signals.isEmpty || !entry.artifacts.isEmpty
                || !entry.removedSignalIDs.isEmpty || !entry.removedArtifactIDs.isEmpty
        else { return }
        let clear = try encoder.encode(entry)
        let encrypted = try seal(clear)
        var length = UInt32(encrypted.count).bigEndian
        let header = withUnsafeBytes(of: &length) { Data($0) }
        if !FileManager.default.fileExists(atPath: journalURL.path) {
            FileManager.default.createFile(atPath: journalURL.path, contents: nil)
            try FileManager.default.setAttributes(
                [.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication],
                ofItemAtPath: journalURL.path
            )
        }
        let handle = try FileHandle(forWritingTo: journalURL)
        defer { try? handle.close() }
        try handle.seekToEnd()
        try handle.write(contentsOf: header)
        try handle.write(contentsOf: encrypted)
        try handle.synchronize()
        journalEntries += 1
        if journalEntries >= 256 { try compact() }
        notifyChanged()
    }

    private func persistSnapshot() throws {
        let clear = try encoder.encode(index)
        let encrypted = try seal(clear)
        try encrypted.write(to: indexURL, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
    }

    private func compact() throws {
        try persistSnapshot()
        try Data().write(to: journalURL, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
        journalEntries = 0
        notifyChanged()
    }

    private static func replayJournal(
        from journalURL: URL,
        key: SymmetricKey,
        decoder: JSONDecoder,
        into index: inout VaultIndex
    ) -> (entryCount: Int, validBytes: Int, totalBytes: Int) {
        guard let data = try? Data(contentsOf: journalURL) else { return (0, 0, 0) }
        var cursor = 0
        var validBytes = 0
        var entryCount = 0
        while cursor + 4 <= data.count {
            let length = data[cursor..<(cursor + 4)].reduce(UInt32(0)) { ($0 << 8) | UInt32($1) }
            cursor += 4
            guard length > 0, cursor + Int(length) <= data.count else { break }
            let encrypted = Data(data[cursor..<(cursor + Int(length))])
            cursor += Int(length)
            validBytes = cursor
            guard
                let box = try? AES.GCM.SealedBox(combined: encrypted),
                let clear = try? AES.GCM.open(box, using: key),
                let entry = try? decoder.decode(VaultJournalEntry.self, from: clear)
            else { continue }
            for signal in entry.signals {
                if let offset = index.signals.firstIndex(where: { $0.id == signal.id }) {
                    index.signals[offset] = signal
                } else {
                    index.signals.append(signal)
                }
            }
            for artifact in entry.artifacts {
                if let offset = index.artifacts.firstIndex(where: { $0.id == artifact.id }) {
                    index.artifacts[offset] = artifact
                } else {
                    index.artifacts.append(artifact)
                }
            }
            let removedSignalIDs = Set(entry.removedSignalIDs)
            let removedArtifactIDs = Set(entry.removedArtifactIDs)
            index.signals.removeAll { removedSignalIDs.contains($0.id) }
            index.artifacts.removeAll { removedArtifactIDs.contains($0.id) }
            entryCount += 1
        }
        return (entryCount, validBytes, data.count)
    }

    private func notifyChanged() {
        Task { @MainActor in NotificationCenter.default.post(name: .lifeLogVaultChanged, object: nil) }
    }

    private func ensureKeyAvailable() throws {
        guard keyIsPersistent else { throw VaultError.keychainUnavailable }
    }

    private func seal(_ clear: Data) throws -> Data {
        guard let combined = try AES.GCM.seal(clear, using: key).combined else {
            throw CocoaError(.coderInvalidValue)
        }
        return combined
    }

    private static func dedupeKey(for signal: BufferedSignal) -> String {
        let canonicalPayload = signal.payload.sorted { $0.key < $1.key }
            .map { "\($0.key.utf8.count):\($0.key)\($0.value.utf8.count):\($0.value)" }
            .joined(separator: "|")
        let payloadHash = SHA256.hash(data: Data(canonicalPayload.utf8))
            .map { String(format: "%02x", $0) }
            .joined()
        if let stableID = signal.payload["external_id"] ?? signal.payload["healthkit_uuid"] {
            return "stable|\(signal.kind.rawValue)|\(stableID)|\(payloadHash)"
        }
        let startSecond = Int64(signal.occurredAt.timeIntervalSince1970.rounded(.down))
        let endSecond = signal.endedAt.map { Int64($0.timeIntervalSince1970.rounded(.down)) } ?? -1
        return "exact|\(signal.kind.rawValue)|\(startSecond)|\(endSecond)|\(payloadHash)"
    }
}

enum VaultError: LocalizedError {
    case keychainUnavailable

    var errorDescription: String? {
        "LifeLog could not secure its encryption key in the device Keychain."
    }
}

@MainActor
final class ConfigurationStore: ObservableObject {
    @Published var configuration: ClientConfiguration { didSet { save() } }
    @Published var privacyRules: PrivacyRules { didSet { save() } }
    private var persistedDeviceKey = ""
    private var persistedAccountToken = ""

    init() {
        let decoder = JSONDecoder()
        var restoredConfiguration = UserDefaults.standard.data(forKey: "client-configuration")
            .flatMap { try? decoder.decode(ClientConfiguration.self, from: $0) }
            ?? ClientConfiguration()
        let legacyDeviceKey = restoredConfiguration.deviceAPIKey
        let legacyAccountToken = restoredConfiguration.bearerToken
        var secretsMigrated = true
        if KeychainStore.string(for: "device-api-key") == nil, !legacyDeviceKey.isEmpty {
            do { try KeychainStore.set(legacyDeviceKey, for: "device-api-key") }
            catch { secretsMigrated = false }
        }
        if KeychainStore.string(for: "account-token") == nil, !legacyAccountToken.isEmpty {
            do { try KeychainStore.set(legacyAccountToken, for: "account-token") }
            catch { secretsMigrated = false }
        }
        restoredConfiguration.deviceAPIKey = KeychainStore.string(for: "device-api-key") ?? legacyDeviceKey
        restoredConfiguration.bearerToken = KeychainStore.string(for: "account-token") ?? legacyAccountToken
        configuration = restoredConfiguration
        persistedDeviceKey = restoredConfiguration.deviceAPIKey
        persistedAccountToken = restoredConfiguration.bearerToken
        privacyRules = UserDefaults.standard.data(forKey: "privacy-rules")
            .flatMap { try? decoder.decode(PrivacyRules.self, from: $0) }
            ?? PrivacyRules()
        var sanitized = restoredConfiguration
        sanitized.deviceAPIKey = ""
        sanitized.bearerToken = ""
        if secretsMigrated, let data = try? JSONEncoder().encode(sanitized) {
            UserDefaults.standard.set(data, forKey: "client-configuration")
        }
    }

    private func save() {
        let encoder = JSONEncoder()
        if configuration.deviceAPIKey != persistedDeviceKey {
            if (try? KeychainStore.set(configuration.deviceAPIKey, for: "device-api-key")) != nil {
                persistedDeviceKey = configuration.deviceAPIKey
            }
        }
        if configuration.bearerToken != persistedAccountToken {
            if (try? KeychainStore.set(configuration.bearerToken, for: "account-token")) != nil {
                persistedAccountToken = configuration.bearerToken
            }
        }
        var publicConfiguration = configuration
        publicConfiguration.deviceAPIKey = ""
        publicConfiguration.bearerToken = ""
        if let data = try? encoder.encode(publicConfiguration) {
            UserDefaults.standard.set(data, forKey: "client-configuration")
        }
        if let data = try? encoder.encode(privacyRules) {
            UserDefaults.standard.set(data, forKey: "privacy-rules")
        }
    }
}
