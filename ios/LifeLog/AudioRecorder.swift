@preconcurrency import AVFoundation
import Combine
import Foundation
import UIKit

@MainActor
final class AudioRecorder: NSObject, ObservableObject, @preconcurrency AVAudioRecorderDelegate {
    @Published private(set) var isRecording = false
    @Published private(set) var startedAt: Date?
    @Published private(set) var duration: TimeInterval = 0
    @Published private(set) var bookmarks: [TimeInterval] = []
    @Published private(set) var lastError: String?

    private let vault: LocalVault
    private var recorder: AVAudioRecorder?
    private var timer: Timer?
    private var recordingURL: URL?
    private var recordingSessionID: UUID?
    private var segmentIndex = 0
    private var segmentTasks: [Task<Bool, Never>] = []
    private let segmentDuration: TimeInterval = 5 * 60

    init(vault: LocalVault = .shared) {
        self.vault = vault
        super.init()
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(interrupted(_:)),
            name: AVAudioSession.interruptionNotification,
            object: nil
        )
        Task { await recoverInterruptedRecordings() }
    }

    func start(context: [String: String] = [:]) async {
        guard !isRecording else { return }
        let allowed = await AVAudioApplication.requestRecordPermission()
        guard allowed else { lastError = "Microphone permission is required."; return }
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playAndRecord, mode: .spokenAudio, options: [.allowBluetoothHFP, .defaultToSpeaker])
            try session.setActive(true, options: .notifyOthersOnDeactivation)
            recordingSessionID = UUID()
            segmentIndex = 0
            segmentTasks = []
            startedAt = .now
            bookmarks = []
            duration = 0
            isRecording = true
            lastError = nil
            UserDefaults.standard.set(context, forKey: "active-recording-context")
            UserDefaults.standard.set(recordingSessionID?.uuidString, forKey: "active-recording-session-id")
            UserDefaults.standard.set(startedAt, forKey: "active-recording-started-at")
            try beginSegment()
            timer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in
                Task { @MainActor in
                    guard let self, let startedAt = self.startedAt else { return }
                    self.duration = Date().timeIntervalSince(startedAt)
                }
            }
        } catch {
            isRecording = false
            lastError = error.localizedDescription
            try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        }
    }

    func addBookmark() {
        guard isRecording else { return }
        bookmarks.append(duration)
        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
    }

    func stop() async {
        guard isRecording else { return }
        if let startedAt { duration = Date().timeIntervalSince(startedAt) }
        let finalURL = recordingURL
        let finalSegment = segmentIndex
        let finalSessionID = recordingSessionID
        let captureStartedAt = startedAt
        isRecording = false
        recorder?.stop()
        timer?.invalidate()
        timer = nil
        guard let finalURL, let finalSessionID else { return }
        var context = UserDefaults.standard.dictionary(forKey: "active-recording-context") as? [String: String] ?? [:]
        context["duration_seconds"] = String(duration)
        context["bookmarks_seconds"] = bookmarks.map { String(format: "%.2f", $0) }.joined(separator: ",")
        do {
            try await preserveSegment(
                finalURL,
                index: finalSegment,
                context: context,
                isFinal: true,
                sessionID: finalSessionID,
                capturedAt: captureStartedAt ?? .now
            )
            var earlierSegmentsSafe = true
            for task in segmentTasks {
                if await !task.value { earlierSegmentsSafe = false }
            }
            if earlierSegmentsSafe {
                clearRecoveryMarker()
            } else {
                lastError = "One recording segment remains safe locally and will be recovered automatically."
            }
            try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        } catch {
            lastError = "The recording remains safe on this iPhone and will be recovered automatically."
        }
    }

    func audioRecorderDidFinishRecording(_ recorder: AVAudioRecorder, successfully flag: Bool) {
        guard isRecording else { return }
        guard flag else {
            isRecording = false
            timer?.invalidate()
            timer = nil
            lastError = "Audio recording was interrupted by the system."
            return
        }
        let completedURL = recorder.url
        let completedIndex = segmentIndex
        guard let completedSessionID = recordingSessionID else { return }
        let captureStartedAt = startedAt ?? .now
        let context = UserDefaults.standard.dictionary(forKey: "active-recording-context") as? [String: String] ?? [:]
        do {
            segmentIndex += 1
            try beginSegment()
            segmentTasks.append(Task(priority: .utility) { [weak self] in
                guard let self else { return false }
                do {
                    try await self.preserveSegment(
                        completedURL,
                        index: completedIndex,
                        context: context,
                        isFinal: false,
                        sessionID: completedSessionID,
                        capturedAt: captureStartedAt
                    )
                    return true
                } catch {
                    return false
                }
            })
        } catch {
            isRecording = false
            timer?.invalidate()
            timer = nil
            lastError = "Recording stopped because the next safe segment could not begin."
        }
    }

    func audioRecorderEncodeErrorDidOccur(_ recorder: AVAudioRecorder, error: Error?) {
        lastError = error?.localizedDescription ?? "Audio encoding stopped unexpectedly."
    }

    @objc private func interrupted(_ notification: Notification) {
        guard
            let raw = notification.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt,
            let type = AVAudioSession.InterruptionType(rawValue: raw)
        else { return }
        if type == .began {
            recorder?.pause()
        } else if
            isRecording,
            let recorder,
            let rawOptions = notification.userInfo?[AVAudioSessionInterruptionOptionKey] as? UInt,
            AVAudioSession.InterruptionOptions(rawValue: rawOptions).contains(.shouldResume)
        {
            recorder.record(forDuration: max(segmentDuration - recorder.currentTime, 1))
        }
    }

    private func beginSegment() throws {
        let directory = try recordingsDirectory()
        let sessionID = recordingSessionID ?? UUID()
        recordingSessionID = sessionID
        let url = directory.appendingPathComponent(
            "recording-\(sessionID.uuidString)-\(String(format: "%05d", segmentIndex)).m4a"
        )
        let value = try AVAudioRecorder(url: url, settings: [
            AVFormatIDKey: Int(kAudioFormatMPEG4AAC),
            AVSampleRateKey: 32_000,
            AVNumberOfChannelsKey: 1,
            AVEncoderAudioQualityKey: AVAudioQuality.medium.rawValue,
            AVEncoderBitRateKey: 64_000
        ])
        value.delegate = self
        value.isMeteringEnabled = true
        value.prepareToRecord()
        guard value.record(forDuration: segmentDuration) else { throw AudioError.couldNotStart }
        recorder = value
        recordingURL = url
    }

    private func preserveSegment(
        _ url: URL,
        index: Int,
        context: [String: String],
        isFinal: Bool,
        sessionID: UUID,
        capturedAt: Date
    ) async throws {
        var segmentContext = context
        segmentContext["recording_session_id"] = sessionID.uuidString
        segmentContext["segment_index"] = String(index)
        segmentContext["final_segment"] = String(isFinal)
        _ = try await vault.preserveArtifact(
            sourceURL: url,
            kind: .audio,
            mimeType: "audio/mp4",
            intent: "recording",
            context: segmentContext,
            captureID: sessionID,
            createdAt: capturedAt
        )
        try? FileManager.default.removeItem(at: url)
    }

    private func recordingsDirectory() throws -> URL {
        let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        let directory = support.appendingPathComponent("LifeLogVault/PendingRecordings", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try FileManager.default.setAttributes(
            [.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication],
            ofItemAtPath: directory.path
        )
        return directory
    }

    private func recoverInterruptedRecordings() async {
        guard !isRecording, let directory = try? recordingsDirectory() else { return }
        let files = (try? FileManager.default.contentsOfDirectory(
            at: directory,
            includingPropertiesForKeys: [.fileSizeKey],
            options: [.skipsHiddenFiles]
        )) ?? []
        let recoveredSessionID = UserDefaults.standard.string(forKey: "active-recording-session-id").flatMap(UUID.init)
        var allRecovered = true
        for file in files where file.pathExtension == "m4a" {
            let size = (try? file.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0
            guard size > 1_024 else { try? FileManager.default.removeItem(at: file); continue }
            var context = UserDefaults.standard.dictionary(forKey: "active-recording-context") as? [String: String] ?? [:]
            context["recovered_after_interruption"] = "true"
            do {
                _ = try await vault.preserveArtifact(
                    sourceURL: file,
                    kind: .audio,
                    mimeType: "audio/mp4",
                    intent: "recovered_recording",
                    context: context,
                    captureID: recoveredSessionID ?? UUID(),
                    createdAt: UserDefaults.standard.object(forKey: "active-recording-started-at") as? Date ?? .now
                )
                try? FileManager.default.removeItem(at: file)
            } catch {
                allRecovered = false
                lastError = "A recording is safe locally and will be recovered when storage is available."
            }
        }
        if !files.isEmpty, allRecovered { clearRecoveryMarker() }
    }

    private func clearRecoveryMarker() {
        UserDefaults.standard.removeObject(forKey: "active-recording-context")
        UserDefaults.standard.removeObject(forKey: "active-recording-started-at")
        UserDefaults.standard.removeObject(forKey: "active-recording-session-id")
    }
}

enum AudioError: LocalizedError {
    case couldNotStart
    var errorDescription: String? { "The audio recorder could not start." }
}
