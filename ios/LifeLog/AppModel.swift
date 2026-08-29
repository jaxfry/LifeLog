import BackgroundTasks
import Combine
import CoreMotion
import Foundation
import UIKit
import SwiftUI

@MainActor
final class AppModel: ObservableObject {
    let configurationStore: ConfigurationStore
    let syncEngine: SyncEngine
    let location: LocationCollector
    let motion: MotionCollector
    let health: HealthCollector
    let schedule: ScheduleCollector
    let audio: AudioRecorder
    let photos: PhotoLibraryCollector
    let contacts: ContactsCollector
    let deviceState: DeviceStateCollector

    @Published private(set) var snapshot = VaultSnapshot(signals: [], artifacts: [])
    @Published var selectedTab: AppTab = .today
    @Published var showingQueue = false
    @Published var showingPrivacy = false
    @Published var lastCaptureError: String?

    private let vault = LocalVault.shared
    private var vaultObserver: AnyCancellable?
    private var collectorObservers: Set<AnyCancellable> = []
    private var started = false

    init() {
        let store = ConfigurationStore()
        configurationStore = store
        syncEngine = SyncEngine(configurationStore: store)
        location = LocationCollector(rules: { store.privacyRules })
        motion = MotionCollector(rules: { store.privacyRules })
        health = HealthCollector(rules: { store.privacyRules })
        schedule = ScheduleCollector(rules: { store.privacyRules })
        audio = AudioRecorder()
        photos = PhotoLibraryCollector(rules: { store.privacyRules })
        contacts = ContactsCollector(rules: { store.privacyRules })
        deviceState = DeviceStateCollector(rules: { store.privacyRules })
        if store.configuration.automaticCollectionEnabled, store.configuration.enabledCapabilities.isEmpty {
            store.configuration.enabledCapabilities = [
                "location", "motion", "health", "calendar", "reminders", "photos", "contacts", "device"
            ]
        }
        [
            location.objectWillChange, motion.objectWillChange, health.objectWillChange,
            schedule.objectWillChange, audio.objectWillChange, photos.objectWillChange,
            contacts.objectWillChange, deviceState.objectWillChange, store.objectWillChange,
            syncEngine.objectWillChange
        ].forEach { publisher in
            publisher.sink { [weak self] _ in self?.objectWillChange.send() }
                .store(in: &collectorObservers)
        }
    }

    func start() {
        guard !started else { return }
        started = true
        if configurationStore.configuration.automaticCollectionEnabled {
            let enabled = configurationStore.configuration.enabledCapabilities
            if enabled.contains("device") { deviceState.start() }
            if enabled.contains("location") {
                location.start(precise: configurationStore.configuration.preciseLocationMode)
            }
            if enabled.contains("motion"), CMMotionActivityManager.authorizationStatus() == .authorized {
                motion.start()
            }
            Task {
                if enabled.contains("health") { await health.resume() }
                if !enabled.isDisjoint(with: ["calendar", "reminders"]) { await schedule.resume() }
                if enabled.contains("photos") { await photos.resume() }
                if enabled.contains("contacts") { await contacts.resume() }
            }
        }
        syncEngine.start()
        vaultObserver = NotificationCenter.default.publisher(for: .lifeLogVaultChanged)
            .debounce(for: .milliseconds(150), scheduler: RunLoop.main)
            .sink { [weak self] _ in
                Task { @MainActor in await self?.refreshSnapshot() }
            }
        Task { await refreshSnapshot() }
    }

    func handleScenePhase(_ phase: ScenePhase) {
        switch phase {
        case .active:
            Task {
                await refreshSnapshot()
                await syncEngine.syncNow()
                if configurationStore.configuration.automaticCollectionEnabled {
                    let enabled = configurationStore.configuration.enabledCapabilities
                    if enabled.contains("photos") { await photos.resume() }
                    if !enabled.isDisjoint(with: ["calendar", "reminders"]) { await schedule.resume() }
                }
            }
        case .background:
            syncEngine.scheduleProcessingTask()
        default:
            break
        }
    }

    func enableAutomaticCollection() async {
        configurationStore.configuration.automaticCollectionEnabled = true
        configurationStore.configuration.enabledCapabilities.insert("device")
        deviceState.start()
        await refreshSnapshot()
    }

    func toggleCapability(_ id: String) async {
        configurationStore.configuration.automaticCollectionEnabled = true
        if isCapabilityEnabled(id) {
            switch id {
            case "location": location.stop()
            case "motion": motion.stop()
            case "health": await health.stop()
            case "calendar", "reminders":
                schedule.stop()
                configurationStore.configuration.enabledCapabilities.remove("calendar")
                configurationStore.configuration.enabledCapabilities.remove("reminders")
            case "photos": photos.stop()
            case "contacts": contacts.stop()
            case "device": deviceState.stop()
            default: break
            }
            configurationStore.configuration.enabledCapabilities.remove(id)
            return
        }
        configurationStore.configuration.enabledCapabilities.insert(id)
        switch id {
        case "location": location.requestAndStart(precise: configurationStore.configuration.preciseLocationMode)
        case "motion": motion.start()
        case "health": await health.requestAndStart()
        case "calendar", "reminders":
            configurationStore.configuration.enabledCapabilities.insert("calendar")
            configurationStore.configuration.enabledCapabilities.insert("reminders")
            await schedule.requestAndStart()
        case "photos": await photos.requestAndStart()
        case "contacts": await contacts.requestAndStart()
        default: break
        }
        await refreshSnapshot()
    }

    func isCapabilityEnabled(_ id: String) -> Bool {
        configurationStore.configuration.enabledCapabilities.contains(id)
    }

    func canToggleCapability(_ id: String) -> Bool {
        ["location", "motion", "health", "calendar", "reminders", "photos", "contacts", "device"].contains(id)
    }

    @discardableResult
    func saveNote(_ text: String) async -> Bool {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return false }
        do {
            try await vault.append(
                kind: .note,
                payload: ["text": trimmed, "source": "ios_quick_note"],
                origin: "lifelog-note",
                privacyRules: configurationStore.privacyRules
            )
            await refreshSnapshot()
            await syncEngine.syncNow()
            return true
        } catch {
            lastCaptureError = "The note could not be made safe locally: \(error.localizedDescription)"
            return false
        }
    }

    @discardableResult
    func preserveImportedFile(_ url: URL, kind: SignalKind, mimeType: String) async -> Bool {
        let accessed = url.startAccessingSecurityScopedResource()
        defer { if accessed { url.stopAccessingSecurityScopedResource() } }
        do {
            _ = try await vault.preserveArtifact(
                sourceURL: url,
                kind: kind,
                mimeType: mimeType,
                intent: "user_import"
            )
            await refreshSnapshot()
            await syncEngine.syncNow()
            return true
        } catch {
            lastCaptureError = "The file could not be made safe locally: \(error.localizedDescription)"
            return false
        }
    }

    func excludeRecent() async {
        do {
            let artifacts = try await vault.excludeRecent(minutes: 15)
            await BackgroundUploadManager.shared.cancel(artifactIDs: Set(artifacts.map(\.id)))
            let api = LifeLogAPI(configuration: configurationStore.configuration)
            for captureID in Set(artifacts.compactMap(\.serverCaptureID)) {
                try? await api.cancelCapture(captureID)
            }
            await refreshSnapshot()
        } catch {
            lastCaptureError = "The recent buffer could not be updated: \(error.localizedDescription)"
        }
    }

    func addCurrentPrivatePlace(name: String) {
        guard let current = location.lastLocation else { return }
        configurationStore.privacyRules.privateGeofences.append(
            PrivateGeofence(
                id: UUID(),
                name: name.isEmpty ? "Private place" : name,
                latitude: current.coordinate.latitude,
                longitude: current.coordinate.longitude,
                radiusMeters: 100
            )
        )
    }

    func refreshSnapshot() async {
        snapshot = await vault.snapshot()
    }

    func reportCaptureError(_ message: String) {
        lastCaptureError = message
    }

    var capabilities: [CapabilityStatus] {
        [
            CapabilityStatus(id: "location", name: "Location & visits", detail: "Significant changes, visits, and optional precise background trails", symbol: "location.fill", state: location.state),
            CapabilityStatus(id: "motion", name: "Motion & steps", detail: "Walking, cycling, running, driving, stationary time, and backfill", symbol: "figure.walk.motion", state: motion.state),
            CapabilityStatus(id: "health", name: "Health", detail: HealthCollector.hasHealthKitEntitlement() ? "Sleep, workouts, steps, heart rate, distance, and energy" : "Needs the HealthKit entitlement; this sideloaded build does not have it", symbol: "heart.fill", state: health.state),
            CapabilityStatus(id: "calendar", name: "Calendar", detail: "Events and planned-versus-actual context", symbol: "calendar", state: schedule.calendarState),
            CapabilityStatus(id: "reminders", name: "Reminders", detail: "Commitments, due dates, and completion changes", symbol: "checklist", state: schedule.reminderState),
            CapabilityStatus(id: "audio", name: "Background audio", detail: "Continues while locked after you explicitly begin recording", symbol: "waveform", state: .available),
            CapabilityStatus(id: "photos", name: "Photo library", detail: "New photo/video metadata, capture time, dimensions, and approved location", symbol: "photo.on.rectangle", state: photos.state),
            CapabilityStatus(id: "contacts", name: "Contacts", detail: "User-approved identity resolution without making Contacts source truth", symbol: "person.2.fill", state: contacts.state),
            CapabilityStatus(id: "device", name: "Device context", detail: "Battery, charging, low-power mode, thermal state, and network transitions", symbol: "iphone.gen3", state: deviceState.state),
            CapabilityStatus(id: "screen-time", name: "Screen Time", detail: "Requires Apple's Family Controls entitlement even when sideloaded", symbol: "hourglass", state: .limited)
        ]
    }
}

enum AppTab: Hashable { case today, capture, assistant, sources, settings }

final class LifeLogAppDelegate: NSObject, UIApplicationDelegate {
    static var backgroundCompletionHandlers: [String: () -> Void] = [:]

    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        BGTaskScheduler.shared.register(forTaskWithIdentifier: "com.lifelog.ios.processing", using: nil) { task in
            Task { @MainActor in
                guard let processing = task as? BGProcessingTask,
                      let model = LifeLogApp.sharedModel else {
                    task.setTaskCompleted(success: false)
                    return
                }
                model.syncEngine.handleBackgroundProcessing(processing)
            }
        }
        return true
    }

    func application(
        _ application: UIApplication,
        handleEventsForBackgroundURLSession identifier: String,
        completionHandler: @escaping () -> Void
    ) {
        _ = BackgroundUploadManager.shared
        Self.backgroundCompletionHandlers[identifier] = completionHandler
    }
}
