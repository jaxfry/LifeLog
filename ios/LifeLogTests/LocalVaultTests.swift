import CryptoKit
import Foundation
import Testing
@testable import LifeLog

struct LocalVaultTests {
    @Test func journalSurvivesRelaunchWithoutRewritingSnapshot() async throws {
        let root = temporaryRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let timestamp = Date(timeIntervalSince1970: 1_700_000_000)
        let key = SymmetricKey(size: .bits256)
        let vault = LocalVault(rootURL: root, encryptionKey: key)

        try await vault.append(
            kind: .note,
            occurredAt: timestamp,
            payload: ["text": "durable"],
            privacyRules: PrivacyRules()
        )

        let reopened = LocalVault(rootURL: root, encryptionKey: key)
        let snapshot = await reopened.snapshot()
        #expect(snapshot.signals.count == 1)
        #expect(snapshot.signals.first?.payload["text"] == "durable")
    }

    @Test func incompleteJournalTailIsRepairedBeforeNewCaptures() async throws {
        let root = temporaryRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let key = SymmetricKey(size: .bits256)
        let first = LocalVault(rootURL: root, encryptionKey: key)
        try await first.append(kind: .note, payload: ["text": "first"], privacyRules: PrivacyRules())
        let journal = root.appendingPathComponent("queue.journal")
        let handle = try FileHandle(forWritingTo: journal)
        try handle.seekToEnd()
        try handle.write(contentsOf: Data([0, 0, 1]))
        try handle.close()

        let repaired = LocalVault(rootURL: root, encryptionKey: key)
        try await repaired.append(kind: .note, payload: ["text": "second"], privacyRules: PrivacyRules())
        let reopened = LocalVault(rootURL: root, encryptionKey: key)

        #expect(await reopened.snapshot().signals.count == 2)
    }

    @Test func largeArtifactsEncryptAndDecryptInBoundedChunks() async throws {
        let root = temporaryRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let source = root.deletingLastPathComponent().appendingPathComponent("source-\(UUID().uuidString).bin")
        defer { try? FileManager.default.removeItem(at: source) }
        let clear = Data(repeating: 0xA5, count: 5 * 1_024 * 1_024 + 17)
        try clear.write(to: source)
        let vault = LocalVault(rootURL: root, encryptionKey: SymmetricKey(size: .bits256))

        let artifact = try await vault.preserveArtifact(
            sourceURL: source,
            kind: .file,
            mimeType: "application/octet-stream"
        )
        var restored = Data()
        var offset: Int64 = 0
        while offset < artifact.byteCount {
            let chunk = try await vault.decryptedUploadChunk(
                for: artifact,
                offset: offset,
                maximum: 2 * 1_024 * 1_024
            )
            let bytes = try Data(contentsOf: chunk)
            restored.append(bytes)
            offset += Int64(bytes.count)
            try? FileManager.default.removeItem(at: chunk)
        }

        #expect(restored == clear)
        #expect(artifact.byteCount == Int64(clear.count))
    }

    @Test func stableExternalRecordsAreNotDuplicated() async throws {
        let root = temporaryRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let vault = LocalVault(rootURL: root, encryptionKey: SymmetricKey(size: .bits256))
        let payload = ["external_id": "contact-1", "name": "Taylor"]

        try await vault.append(kind: .contact, occurredAt: .now, payload: payload, privacyRules: PrivacyRules())
        try await vault.append(
            kind: .contact,
            occurredAt: Date().addingTimeInterval(30),
            payload: payload,
            privacyRules: PrivacyRules()
        )

        #expect(await vault.snapshot().signals.count == 1)
    }

    private func temporaryRoot() -> URL {
        FileManager.default.temporaryDirectory.appendingPathComponent("LifeLogVaultTests-\(UUID().uuidString)")
    }
}
