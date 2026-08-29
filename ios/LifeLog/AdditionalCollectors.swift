import Combine
import Contacts
import Foundation
import Photos
import UIKit

@MainActor
final class DeviceStateCollector: ObservableObject {
    @Published private(set) var state: CapabilityState = .available
    private let vault: LocalVault
    private let rules: () -> PrivacyRules
    private var observers: [NSObjectProtocol] = []
    private var lastLevel: Float = -1
    private var lastState: UIDevice.BatteryState = .unknown
    private var lastLowPowerMode = false
    private var lastThermalState: ProcessInfo.ThermalState = .nominal

    init(vault: LocalVault = .shared, rules: @escaping () -> PrivacyRules) {
        self.vault = vault
        self.rules = rules
    }

    func start() {
        guard state != .collecting else { return }
        UIDevice.current.isBatteryMonitoringEnabled = true
        let names: [Notification.Name] = [
            UIDevice.batteryLevelDidChangeNotification,
            UIDevice.batteryStateDidChangeNotification,
            .NSProcessInfoPowerStateDidChange,
            Notification.Name("NSProcessInfoThermalStateDidChangeNotification")
        ]
        observers = names.map { name in
            NotificationCenter.default.addObserver(forName: name, object: nil, queue: .main) { [weak self] _ in
                Task { @MainActor in await self?.recordIfMeaningful() }
            }
        }
        state = .collecting
        Task { await recordIfMeaningful(force: true) }
    }

    func stop() {
        observers.forEach(NotificationCenter.default.removeObserver)
        observers.removeAll()
        UIDevice.current.isBatteryMonitoringEnabled = false
        state = .disabled
    }

    private func recordIfMeaningful(force: Bool = false) async {
        let device = UIDevice.current
        let level = device.batteryLevel
        let batteryState = device.batteryState
        let lowPowerMode = ProcessInfo.processInfo.isLowPowerModeEnabled
        let thermalState = ProcessInfo.processInfo.thermalState
        guard
            force || abs(level - lastLevel) >= 0.05 || batteryState != lastState
                || lowPowerMode != lastLowPowerMode || thermalState != lastThermalState
        else { return }
        lastLevel = level
        lastState = batteryState
        lastLowPowerMode = lowPowerMode
        lastThermalState = thermalState
        try? await vault.append(
            kind: .battery,
            payload: [
                "level": level < 0 ? "unknown" : String(level),
                "state": String(batteryState.rawValue),
                "low_power_mode": String(lowPowerMode),
                "thermal_state": String(thermalState.rawValue),
                "source": "ios_device"
            ],
            origin: "ios-device-state",
            privacyRules: rules()
        )
    }
}

@MainActor
final class PhotoLibraryCollector: NSObject, ObservableObject, PHPhotoLibraryChangeObserver {
    @Published private(set) var state: CapabilityState = .available
    private let vault: LocalVault
    private let rules: () -> PrivacyRules
    private var enabled = false
    private var isObservingChanges = false
    private var lastImportedAt: Date {
        get { UserDefaults.standard.object(forKey: "photo-library-cursor") as? Date ?? Date().addingTimeInterval(-24 * 60 * 60) }
        set { UserDefaults.standard.set(newValue, forKey: "photo-library-cursor") }
    }

    init(vault: LocalVault = .shared, rules: @escaping () -> PrivacyRules) {
        self.vault = vault
        self.rules = rules
        super.init()
        updateState()
    }

    deinit {
        if isObservingChanges {
            PHPhotoLibrary.shared().unregisterChangeObserver(self)
        }
    }

    func requestAndStart() async {
        enabled = true
        let authorization = await PHPhotoLibrary.requestAuthorization(for: .readWrite)
        updateState(authorization)
        if [.authorized, .limited].contains(authorization) {
            startObservingChanges()
            await scanNewAssets()
        }
    }

    func resume() async {
        enabled = true
        let authorization = PHPhotoLibrary.authorizationStatus(for: .readWrite)
        if [.authorized, .limited].contains(authorization) {
            startObservingChanges()
            await scanNewAssets()
        }
        else { updateState(authorization) }
    }

    func stop() {
        enabled = false
        if isObservingChanges {
            PHPhotoLibrary.shared().unregisterChangeObserver(self)
            isObservingChanges = false
        }
        state = .disabled
    }

    nonisolated func photoLibraryDidChange(_ changeInstance: PHChange) {
        Task { @MainActor [weak self] in
            guard self?.enabled == true else { return }
            await self?.scanNewAssets()
        }
    }

    func scanNewAssets() async {
        let authorization = PHPhotoLibrary.authorizationStatus(for: .readWrite)
        guard [.authorized, .limited].contains(authorization) else { updateState(authorization); return }
        state = .collecting
        let options = PHFetchOptions()
        options.predicate = NSPredicate(format: "creationDate > %@", lastImportedAt as NSDate)
        options.sortDescriptors = [NSSortDescriptor(key: "creationDate", ascending: true)]
        options.fetchLimit = 250
        let assets = PHAsset.fetchAssets(with: options)
        var newest = lastImportedAt
        var observations: [SignalObservation] = []
        assets.enumerateObjects { [weak self] asset, _, _ in
            guard let self else { return }
            let created = asset.creationDate ?? .now
            newest = max(newest, created)
            var payload: [String: String] = [
                "local_identifier": asset.localIdentifier,
                "media_type": String(asset.mediaType.rawValue),
                "media_subtypes": String(asset.mediaSubtypes.rawValue),
                "pixel_width": String(asset.pixelWidth),
                "pixel_height": String(asset.pixelHeight),
                "duration_seconds": String(asset.duration),
                "favorite": String(asset.isFavorite),
                "source": "photo_library"
            ]
            if let location = asset.location, !PrivacyEngine(rules: self.rules()).isPrivateLocation(location) {
                payload["latitude"] = String(location.coordinate.latitude)
                payload["longitude"] = String(location.coordinate.longitude)
            }
            observations.append(
                SignalObservation(
                    kind: .photoLibrary,
                    occurredAt: created,
                    payload: payload,
                    origin: "photo-library"
                )
            )
        }
        do {
            try await vault.append(observations, privacyRules: rules())
        } catch {
            return
        }
        lastImportedAt = newest
    }

    private func updateState(_ value: PHAuthorizationStatus? = nil) {
        switch value ?? PHPhotoLibrary.authorizationStatus(for: .readWrite) {
        case .authorized: state = enabled ? .collecting : .available
        case .limited: state = enabled ? .limited : .available
        case .notDetermined: state = .permissionNeeded
        case .denied, .restricted: state = .unavailable
        @unknown default: state = .unavailable
        }
    }

    private func startObservingChanges() {
        guard !isObservingChanges else { return }
        PHPhotoLibrary.shared().register(self)
        isObservingChanges = true
    }
}

@MainActor
final class ContactsCollector: ObservableObject {
    @Published private(set) var state: CapabilityState = .available
    private let store = CNContactStore()
    private let vault: LocalVault
    private let rules: () -> PrivacyRules
    private var observer: NSObjectProtocol?
    private var enabled = false

    init(vault: LocalVault = .shared, rules: @escaping () -> PrivacyRules) {
        self.vault = vault
        self.rules = rules
        observer = NotificationCenter.default.addObserver(
            forName: .CNContactStoreDidChange,
            object: nil,
            queue: .main
        ) { [weak self] _ in Task { @MainActor in
            guard self?.enabled == true else { return }
            await self?.refresh()
        } }
        updateState()
    }

    func requestAndStart() async {
        enabled = true
        do {
            state = try await store.requestAccess(for: .contacts) ? .collecting : .permissionNeeded
            if state == .collecting { await refresh() }
        } catch { state = .permissionNeeded }
    }

    func resume() async {
        enabled = true
        if CNContactStore.authorizationStatus(for: .contacts) == .authorized { await refresh() }
        else { updateState() }
    }

    func stop() {
        enabled = false
        state = .disabled
    }

    func refresh() async {
        guard CNContactStore.authorizationStatus(for: .contacts) == .authorized else { updateState(); return }
        state = .collecting
        let keys: [CNKeyDescriptor] = [
            CNContactIdentifierKey as CNKeyDescriptor,
            CNContactGivenNameKey as CNKeyDescriptor,
            CNContactFamilyNameKey as CNKeyDescriptor,
            CNContactOrganizationNameKey as CNKeyDescriptor,
            CNContactEmailAddressesKey as CNKeyDescriptor,
            CNContactPhoneNumbersKey as CNKeyDescriptor
        ]
        let request = CNContactFetchRequest(keysToFetch: keys)
        var observations: [SignalObservation] = []
        do {
            try store.enumerateContacts(with: request) { contact, _ in
                let name = [contact.givenName, contact.familyName].filter { !$0.isEmpty }.joined(separator: " ")
                observations.append(
                    SignalObservation(
                        kind: .contact,
                        payload: [
                            "external_id": contact.identifier,
                            "name": name,
                            "organization": contact.organizationName,
                            "emails": contact.emailAddresses.map { $0.value as String }.joined(separator: ","),
                            "phones": contact.phoneNumbers.map { $0.value.stringValue }.joined(separator: ","),
                            "source": "contacts"
                        ],
                        origin: "contacts"
                    )
                )
            }
            try await vault.append(observations, privacyRules: rules())
        } catch {
            state = .limited
        }
    }

    private func updateState() {
        switch CNContactStore.authorizationStatus(for: .contacts) {
        case .authorized: state = .collecting
        case .notDetermined: state = .permissionNeeded
        case .denied, .restricted: state = .unavailable
        case .limited: state = .limited
        @unknown default: state = .unavailable
        }
    }
}
