import BackgroundTasks
import Combine
import Foundation
import Network

@MainActor
final class SyncEngine: ObservableObject {
    @Published private(set) var isOnline = true
    @Published private(set) var isSyncing = false
    @Published private(set) var lastSyncAt: Date?
    @Published private(set) var lastError: String?

    private let vault: LocalVault
    private let configurationStore: ConfigurationStore
    private let monitor = NWPathMonitor()
    private var isExpensiveNetwork = false
    private var vaultObserver: AnyCancellable?
    private var started = false
    private var lastPathSignature: String?
    private var needsAnotherPass = false

    init(vault: LocalVault = .shared, configurationStore: ConfigurationStore) {
        self.vault = vault
        self.configurationStore = configurationStore
        monitor.pathUpdateHandler = { @Sendable [weak self] path in
            Task { @MainActor in
                self?.isOnline = path.status == .satisfied
                self?.isExpensiveNetwork = path.isExpensive
                await self?.recordNetworkTransition(path)
                if path.status == .satisfied { await self?.syncNow() }
            }
        }
        monitor.start(queue: DispatchQueue(label: "com.lifelog.ios.network"))
    }

    private func recordNetworkTransition(_ path: NWPath) async {
        guard
            configurationStore.configuration.automaticCollectionEnabled,
            configurationStore.configuration.enabledCapabilities.contains("device")
        else { return }
        let interfaces = [NWInterface.InterfaceType.wifi, .cellular, .wiredEthernet, .other]
            .filter(path.usesInterfaceType)
            .map { String(describing: $0) }
            .joined(separator: ",")
        let signature = "\(path.status)-\(interfaces)-\(path.isExpensive)-\(path.isConstrained)"
        guard signature != lastPathSignature else { return }
        lastPathSignature = signature
        try? await vault.append(
            kind: .connectivity,
            payload: [
                "status": String(describing: path.status),
                "interfaces": interfaces,
                "expensive": String(path.isExpensive),
                "constrained": String(path.isConstrained),
                "source": "network_framework"
            ],
            origin: "ios-network",
            privacyRules: configurationStore.privacyRules
        )
    }

    func start() {
        guard !started else { return }
        started = true
        vaultObserver = NotificationCenter.default.publisher(for: .lifeLogVaultChanged)
            .debounce(for: .seconds(15), scheduler: RunLoop.main)
            .sink { [weak self] _ in
                Task { @MainActor in await self?.syncNow() }
            }
        Task { await syncNow() }
    }

    func syncNow() async {
        guard isOnline else { return }
        if isSyncing {
            needsAnotherPass = true
            return
        }
        let configuration = configurationStore.configuration
        guard !configuration.deviceAPIKey.isEmpty else { return }
        guard configuration.uploadOnCellular || !isExpensiveNetwork else { return }
        isSyncing = true
        defer {
            isSyncing = false
            if needsAnotherPass {
                needsAnotherPass = false
                Task { await syncNow() }
            }
        }
        let api = LifeLogAPI(configuration: configuration)

        let signals = await vault.pendingSignals(limit: 100)
        guard !Task.isCancelled else { return }
        if !signals.isEmpty {
            do {
                try await api.send(signals)
                try await vault.markSignals(Set(signals.map(\.id)), state: .serverVerified)
                lastError = nil
            } catch {
                lastError = error.localizedDescription
                try? await vault.markSignals(
                    Set(signals.map(\.id)),
                    state: .retrying,
                    error: error.localizedDescription
                )
            }
        }

        let activeBackgroundUploads = await BackgroundUploadManager.shared.activeArtifactIDs()
        let pendingArtifacts = await vault.pendingArtifacts()
        var activeCaptureIDs = Set(
            pendingArtifacts
                .filter { $0.state == .uploading && activeBackgroundUploads.contains($0.id) }
                .map(\.captureID)
        )
        var availableUploadSlots = max(2 - activeBackgroundUploads.count, 0)
        for var artifact in pendingArtifacts {
            guard !Task.isCancelled else { return }
            if artifact.state == .uploading, activeBackgroundUploads.contains(artifact.id) { continue }
            if activeCaptureIDs.contains(artifact.captureID) { continue }
            if availableUploadSlots == 0 { break }
            if artifact.state == .uploading { artifact.state = .queued }
            do {
                if artifact.serverCaptureID == nil {
                    artifact.serverCaptureID = try await api.createCaptureDraft(for: artifact)
                    try await vault.updateArtifact(artifact)
                }
                guard let captureID = artifact.serverCaptureID else { continue }
                if artifact.serverUploadID == nil {
                    artifact.serverUploadID = try await api.createUploadSession(
                        captureID: captureID,
                        artifact: artifact
                    )
                    try await vault.updateArtifact(artifact)
                }
                guard let uploadID = artifact.serverUploadID else { continue }
                let uploadState = try await api.uploadState(captureID: captureID, uploadID: uploadID)
                let serverOffset = uploadState.receivedBytes
                artifact.uploadedBytes = serverOffset
                if uploadState.status == "complete" {
                    guard uploadState.contentHash == artifact.sha256 else { throw APIError.integrityMismatch }
                    artifact.state = .serverVerified
                    try await vault.updateArtifact(artifact)
                    continue
                }
                if serverOffset >= artifact.byteCount {
                    try await api.completeUpload(
                        captureID: captureID,
                        uploadID: uploadID,
                        expectedHash: artifact.sha256
                    )
                    artifact.state = .serverVerified
                    try await vault.updateArtifact(artifact)
                    continue
                }
                let chunkURL = try await vault.decryptedUploadChunk(
                    for: artifact,
                    offset: serverOffset,
                    maximum: 2 * 1_024 * 1_024
                )
                let chunkSize = (try FileManager.default.attributesOfItem(atPath: chunkURL.path)[.size] as? NSNumber)?.int64Value ?? 0
                var request = try api.uploadRequest(captureID: captureID, uploadID: uploadID, offset: serverOffset)
                request.setValue(String(chunkSize), forHTTPHeaderField: "Content-Length")
                request.allowsCellularAccess = configuration.uploadOnCellular
                try BackgroundUploadManager.shared.schedule(
                    request: request,
                    chunkURL: chunkURL,
                    artifactID: artifact.id,
                    offset: serverOffset,
                    byteCount: chunkSize
                )
                availableUploadSlots -= 1
                activeCaptureIDs.insert(artifact.captureID)
                artifact.state = .uploading
                try await vault.updateArtifact(artifact)
            } catch {
                artifact.attempts += 1
                if let apiError = error as? APIError, case .integrityMismatch = apiError {
                    artifact.state = .failed
                } else {
                    artifact.state = .retrying
                }
                artifact.lastError = error.localizedDescription
                lastError = error.localizedDescription
                artifact.nextAttemptAt = Date().addingTimeInterval(
                    min(pow(2, Double(artifact.attempts)) * 15, 21_600)
                )
                try? await vault.updateArtifact(artifact)
            }
        }
        lastSyncAt = .now
        let retention = max(configuration.keepOriginalDays, 1)
        try? await vault.pruneVerified(olderThan: Date().addingTimeInterval(TimeInterval(-retention * 86_400)))
        scheduleProcessingTask()
    }

    func handleBackgroundProcessing(_ task: BGProcessingTask) {
        scheduleProcessingTask()
        let work = Task {
            await syncNow()
            if !Task.isCancelled { task.setTaskCompleted(success: true) }
        }
        task.expirationHandler = {
            work.cancel()
            task.setTaskCompleted(success: false)
        }
    }

    func scheduleProcessingTask() {
        let request = BGProcessingTaskRequest(identifier: "com.lifelog.ios.processing")
        request.requiresNetworkConnectivity = true
        request.requiresExternalPower = false
        request.earliestBeginDate = Date(timeIntervalSinceNow: 15 * 60)
        BGTaskScheduler.shared.cancel(taskRequestWithIdentifier: request.identifier)
        try? BGTaskScheduler.shared.submit(request)
    }
}
