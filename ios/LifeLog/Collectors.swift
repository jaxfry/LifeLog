import AVFoundation
import Combine
@preconcurrency import CoreLocation
import CoreMotion
import EventKit
import HealthKit

private final class HealthCompletion: @unchecked Sendable {
    private let completion: HKObserverQueryCompletionHandler
    init(_ completion: @escaping HKObserverQueryCompletionHandler) { self.completion = completion }
    func call() { completion() }
}

private struct ReminderSnapshot: Sendable {
    let id: String
    let title: String
    let calendar: String
    let createdAt: Date
    let completedAt: Date?
    let isCompleted: Bool
    let priority: Int
    let due: Date?
}

@MainActor
final class LocationCollector: NSObject, ObservableObject, @preconcurrency CLLocationManagerDelegate {
    @Published private(set) var state: CapabilityState = .permissionNeeded
    @Published private(set) var lastLocation: CLLocation?

    private let manager = CLLocationManager()
    private let vault: LocalVault
    private let rules: () -> PrivacyRules
    private var requestedPrecise = false

    init(vault: LocalVault = .shared, rules: @escaping () -> PrivacyRules) {
        self.vault = vault
        self.rules = rules
        super.init()
        manager.delegate = self
        manager.activityType = .fitness
        manager.desiredAccuracy = kCLLocationAccuracyHundredMeters
        manager.distanceFilter = 100
        manager.pausesLocationUpdatesAutomatically = true
        manager.showsBackgroundLocationIndicator = false
        updateState()
    }

    func requestAndStart(precise: Bool) {
        requestedPrecise = precise
        switch manager.authorizationStatus {
        case .notDetermined: manager.requestWhenInUseAuthorization()
        case .authorizedWhenInUse: manager.requestAlwaysAuthorization()
        case .authorizedAlways: start(precise: precise)
        default: updateState()
        }
    }

    func start(precise: Bool) {
        guard [.authorizedAlways, .authorizedWhenInUse].contains(manager.authorizationStatus) else {
            updateState(); return
        }
        manager.startMonitoringVisits()
        if CLLocationManager.significantLocationChangeMonitoringAvailable() {
            manager.startMonitoringSignificantLocationChanges()
        }
        if precise, manager.authorizationStatus == .authorizedAlways {
            manager.desiredAccuracy = kCLLocationAccuracyNearestTenMeters
            manager.distanceFilter = 75
            manager.allowsBackgroundLocationUpdates = true
            manager.showsBackgroundLocationIndicator = true
            manager.startUpdatingLocation()
        } else {
            manager.stopUpdatingLocation()
            manager.allowsBackgroundLocationUpdates = false
            manager.showsBackgroundLocationIndicator = false
        }
        state = .collecting
    }

    func stop() {
        manager.stopUpdatingLocation()
        manager.stopMonitoringSignificantLocationChanges()
        manager.stopMonitoringVisits()
        state = .disabled
    }

    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        updateState()
        if manager.authorizationStatus == .authorizedWhenInUse {
            manager.requestAlwaysAuthorization()
        } else if manager.authorizationStatus == .authorizedAlways {
            start(precise: requestedPrecise)
        }
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        for location in locations where location.horizontalAccuracy >= 0 {
            lastLocation = location
            let privateLocation = PrivacyEngine(rules: rules()).isPrivateLocation(location)
            if privateLocation { continue }
            Task {
                try? await vault.append(
                    kind: .location,
                    occurredAt: location.timestamp,
                    payload: [
                        "latitude": String(location.coordinate.latitude),
                        "longitude": String(location.coordinate.longitude),
                        "horizontal_accuracy_m": String(location.horizontalAccuracy),
                        "altitude_m": String(location.altitude),
                        "speed_mps": String(max(location.speed, 0)),
                        "course_degrees": String(max(location.course, 0)),
                        "source": "core_location"
                    ],
                    origin: "core-location",
                    privacyRules: rules()
                )
            }
        }
    }

    func locationManager(_ manager: CLLocationManager, didVisit visit: CLVisit) {
        let visitLocation = CLLocation(latitude: visit.coordinate.latitude, longitude: visit.coordinate.longitude)
        guard !PrivacyEngine(rules: rules()).isPrivateLocation(visitLocation) else { return }
        let departure = visit.departureDate == .distantFuture ? nil : visit.departureDate
        Task {
            try? await vault.append(
                kind: .visit,
                occurredAt: visit.arrivalDate,
                endedAt: departure,
                payload: [
                    "latitude": String(visit.coordinate.latitude),
                    "longitude": String(visit.coordinate.longitude),
                    "horizontal_accuracy_m": String(visit.horizontalAccuracy),
                    "source": "core_location_visit"
                ],
                origin: "core-location",
                privacyRules: rules()
            )
        }
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        if (error as? CLError)?.code != .locationUnknown { state = .limited }
    }

    private func updateState() {
        switch manager.authorizationStatus {
        case .authorizedAlways: state = .collecting
        case .authorizedWhenInUse: state = .limited
        case .denied, .restricted: state = .unavailable
        case .notDetermined: state = .permissionNeeded
        @unknown default: state = .unavailable
        }
    }
}

@MainActor
final class MotionCollector: ObservableObject {
    @Published private(set) var state: CapabilityState = .permissionNeeded
    private let activity = CMMotionActivityManager()
    private let pedometer = CMPedometer()
    private let livePedometer = CMPedometer()
    private let queue = OperationQueue()
    private let vault: LocalVault
    private let rules: () -> PrivacyRules
    private var livePedometerStarted = false
    private var lastSteps = 0
    private var lastDistance: Double?
    private var lastFloors = 0
    private var lastEnd: Date?

    init(vault: LocalVault = .shared, rules: @escaping () -> PrivacyRules) {
        self.vault = vault
        self.rules = rules
        state = CMMotionActivityManager.isActivityAvailable() ? .available : .unavailable
    }

    private var startedOnce = false
    private var activityCutoff: Date = .distantPast

    func start() {
        guard !startedOnce else { return }
        startedOnce = true
        guard CMMotionActivityManager.isActivityAvailable() else { state = .unavailable; return }
        state = .collecting
        activityCutoff = Date()
        activity.startActivityUpdates(to: queue) { @Sendable [weak self] sample in
            Self.handleActivitySample(sample, collector: self)
        }
        backfill(since: activityCutoff.addingTimeInterval(-6 * 60 * 60))
        startLivePedometer()
    }

    func stop() {
        activity.stopActivityUpdates()
        pedometer.stopUpdates()
        livePedometer.stopUpdates()
        livePedometerStarted = false
        startedOnce = false
        state = .disabled
    }

    private func startLivePedometer() {
        guard !livePedometerStarted, CMPedometer.isStepCountingAvailable() else { return }
        livePedometerStarted = true
        livePedometer.startUpdates(from: .now) { @Sendable [weak self] data, _ in
            Self.handlePedometerLiveUpdate(data, collector: self)
        }
    }

    private func ingestLiveUpdate(endDate: Date, steps: Int, distance: Double?, floors: Int) async {
        defer {
            lastEnd = endDate
            lastSteps = steps
            lastDistance = distance
            lastFloors = floors
        }
        guard let previousEnd = lastEnd else { return }
        let deltaSteps = steps - lastSteps
        guard deltaSteps > 0 else { return }
        let deltaDistance = max(distance.flatMap { value in lastDistance.map { value - $0 } } ?? 0, 0)
        let deltaFloors = max(floors - lastFloors, 0)
        try? await vault.append(
            kind: .steps,
            occurredAt: previousEnd,
            endedAt: endDate,
            payload: [
                "steps": String(deltaSteps),
                "distance_m": String(deltaDistance),
                "floors_ascended": String(deltaFloors),
                "source": "core_motion_pedometer_live"
            ],
            origin: "core-motion",
            privacyRules: rules()
        )
    }

    func backfill(since start: Date) {
        activity.queryActivityStarting(from: start, to: .now, to: queue) { @Sendable [weak self] samples, _ in
            Self.handleActivityBackfill(samples, collector: self)
        }
        guard CMPedometer.isStepCountingAvailable() else { return }
        pedometer.queryPedometerData(from: start, to: .now) { @Sendable [weak self] data, _ in
            Self.handlePedometerBackfill(data, collector: self)
        }
    }

    private nonisolated static func handleActivitySample(_ sample: CMMotionActivity?, collector: MotionCollector?) {
        guard let sample, let collector else { return }
        let startDate = sample.startDate
        let payload = Self.payload(for: sample)
        Task { @MainActor in
            guard startDate > collector.activityCutoff else { return }
            try? await collector.vault.append(
                kind: .motion,
                occurredAt: startDate,
                payload: payload,
                origin: "core-motion",
                privacyRules: collector.rules()
            )
        }
    }

    private nonisolated static func handleActivityBackfill(_ samples: [CMMotionActivity]?, collector: MotionCollector?) {
        guard let samples, let collector else { return }
        let snapshot = samples.map { (startDate: $0.startDate, payload: Self.payload(for: $0)) }
        Task { @MainActor in
            let observations = snapshot.map {
                SignalObservation(
                    kind: .motion,
                    occurredAt: $0.startDate,
                    payload: $0.payload,
                    origin: "core-motion-backfill"
                )
            }
            try? await collector.vault.append(observations, privacyRules: collector.rules())
        }
    }

    private nonisolated static func handlePedometerBackfill(_ data: CMPedometerData?, collector: MotionCollector?) {
        guard let data, let collector else { return }
        let startDate = data.startDate
        let endDate = data.endDate
        let steps = data.numberOfSteps.stringValue
        let distance = data.distance?.stringValue ?? ""
        let floors = data.floorsAscended?.stringValue ?? ""
        Task { @MainActor in
            try? await collector.vault.append(
                kind: .steps,
                occurredAt: startDate,
                endedAt: endDate,
                payload: [
                    "steps": steps,
                    "distance_m": distance,
                    "floors_ascended": floors,
                    "source": "core_motion_pedometer"
                ],
                origin: "core-motion",
                privacyRules: collector.rules()
            )
        }
    }

    private nonisolated static func handlePedometerLiveUpdate(_ data: CMPedometerData?, collector: MotionCollector?) {
        guard let data, let collector else { return }
        let endDate = data.endDate
        let steps = data.numberOfSteps.intValue
        let distance = data.distance?.doubleValue
        let floors = data.floorsAscended?.intValue ?? 0
        Task { @MainActor in
            await collector.ingestLiveUpdate(endDate: endDate, steps: steps, distance: distance, floors: floors)
        }
    }

    private nonisolated static func payload(for value: CMMotionActivity) -> [String: String] {
        let classification: String
        if value.automotive { classification = "automotive" }
        else if value.cycling { classification = "cycling" }
        else if value.running { classification = "running" }
        else if value.walking { classification = "walking" }
        else if value.stationary { classification = "stationary" }
        else { classification = "unknown" }
        return [
            "activity": classification,
            "confidence": String(value.confidence.rawValue),
            "source": "core_motion_activity"
        ]
    }
}

@MainActor
final class HealthCollector: ObservableObject {
    @Published private(set) var state: CapabilityState = HKHealthStore.isHealthDataAvailable() ? .available : .unavailable
    private let store = HKHealthStore()
    private let vault: LocalVault
    private let rules: () -> PrivacyRules
    private var observerQueries: [HKObserverQuery] = []
    private var observersStarted = false
    private let authorizationRequestedKey = "healthkit-authorization-requested"

    init(vault: LocalVault = .shared, rules: @escaping () -> PrivacyRules) {
        self.vault = vault
        self.rules = rules
        if !Self.hasHealthKitEntitlement() {
            state = .unavailable
        }
    }

    static func hasHealthKitEntitlement() -> Bool {
        #if targetEnvironment(simulator)
        return true
        #else
        guard
            let profileURL = Bundle.main.url(forResource: "embedded", withExtension: "mobileprovision"),
            let profileData = try? Data(contentsOf: profileURL),
            let profileText = String(data: profileData, encoding: .ascii),
            let startRange = profileText.range(of: "<plist"),
            let endRange = profileText.range(of: "</plist>", options: .backwards)
        else { return false }
        let plistText = String(profileText[startRange.lowerBound..<endRange.upperBound])
        guard
            let plistData = plistText.data(using: .utf8),
            let plist = try? PropertyListSerialization.propertyList(from: plistData, format: nil) as? [String: Any],
            let entitlements = plist["Entitlements"] as? [String: Any]
        else { return false }
        return (entitlements["com.apple.developer.healthkit"] as? Bool) ?? false
        #endif
    }

    func requestAndStart() async {
        guard Self.hasHealthKitEntitlement() else { state = .unavailable; return }
        guard HKHealthStore.isHealthDataAvailable() else { state = .unavailable; return }
        let read = readableTypes()
        do {
            try await store.requestAuthorization(toShare: [], read: read)
            UserDefaults.standard.set(true, forKey: authorizationRequestedKey)
            await resume()
        } catch {
            state = .permissionNeeded
        }
    }

    func resume() async {
        guard Self.hasHealthKitEntitlement() else { state = .unavailable; return }
        guard !observersStarted else { return }
        guard UserDefaults.standard.bool(forKey: authorizationRequestedKey) else { state = .permissionNeeded; return }
        observersStarted = true
        state = .collecting
        for type in readableTypes() {
            try? await store.enableBackgroundDelivery(for: type, frequency: .hourly)
            let identifier = type.identifier
            let query = HKObserverQuery(sampleType: type, predicate: nil) { @Sendable [weak self] _, completion, _ in
                Self.handleObserverUpdate(completion: completion, typeIdentifier: identifier, collector: self)
            }
            observerQueries.append(query)
            store.execute(query)
            await fetchRecent(type)
        }
    }

    func stop() async {
        for query in observerQueries { store.stop(query) }
        observerQueries.removeAll()
        for type in readableTypes() { try? await store.disableBackgroundDelivery(for: type) }
        observersStarted = false
        state = .disabled
    }

    private nonisolated static func handleObserverUpdate(
        completion: @escaping HKObserverQueryCompletionHandler,
        typeIdentifier: String,
        collector: HealthCollector?
    ) {
        let completionBox = HealthCompletion(completion)
        Task { @MainActor in
            guard let collector else { completionBox.call(); return }
            if let currentType = collector.readableTypes().first(where: { $0.identifier == typeIdentifier }) {
                await collector.fetchRecent(currentType)
            }
            completionBox.call()
        }
    }

    private func readableTypes() -> Set<HKSampleType> {
        var result: Set<HKSampleType> = []
        [HKQuantityTypeIdentifier.stepCount, .heartRate, .activeEnergyBurned, .distanceWalkingRunning]
            .compactMap { HKObjectType.quantityType(forIdentifier: $0) }
            .forEach { result.insert($0) }
        if let sleep = HKObjectType.categoryType(forIdentifier: .sleepAnalysis) { result.insert(sleep) }
        result.insert(HKObjectType.workoutType())
        return result
    }

    private func fetchRecent(_ type: HKSampleType) async {
        let cursorKey = "healthkit-cursor-\(type.identifier)"
        let cursor = UserDefaults.standard.object(forKey: cursorKey) as? Date
        let predicate = HKQuery.predicateForSamples(
            withStart: cursor?.addingTimeInterval(-5 * 60) ?? Date().addingTimeInterval(-24 * 60 * 60),
            end: nil,
            options: .strictStartDate
        )
        let descriptor = HKSampleQueryDescriptor(
            predicates: [.sample(type: type, predicate: predicate)],
            sortDescriptors: [SortDescriptor(\.startDate, order: .reverse)],
            limit: 500
        )
        guard let samples = try? await descriptor.result(for: store) else { return }
        var newest = cursor ?? .distantPast
        var observations: [SignalObservation] = []
        for sample in samples {
            newest = max(newest, sample.endDate)
            var payload = [
                "healthkit_uuid": sample.uuid.uuidString,
                "sample_type": sample.sampleType.identifier,
                "source": sample.sourceRevision.source.name
            ]
            if let quantity = sample as? HKQuantitySample {
                payload["value"] = String(quantity.quantity.doubleValue(for: preferredUnit(for: quantity.quantityType)))
                payload["unit"] = preferredUnit(for: quantity.quantityType).unitString
            } else if let category = sample as? HKCategorySample {
                payload["value"] = String(category.value)
            } else if let workout = sample as? HKWorkout {
                payload["activity_type"] = String(workout.workoutActivityType.rawValue)
                payload["duration_seconds"] = String(workout.duration)
            }
            observations.append(
                SignalObservation(
                    kind: .health,
                    occurredAt: sample.startDate,
                    endedAt: sample.endDate,
                    payload: payload,
                    origin: "healthkit"
                )
            )
        }
        do {
            try await vault.append(observations, privacyRules: rules())
            if newest > .distantPast { UserDefaults.standard.set(newest, forKey: cursorKey) }
        } catch {
            return
        }
    }

    private func preferredUnit(for type: HKQuantityType) -> HKUnit {
        switch type.identifier {
        case HKQuantityTypeIdentifier.heartRate.rawValue: HKUnit.count().unitDivided(by: .minute())
        case HKQuantityTypeIdentifier.activeEnergyBurned.rawValue: .kilocalorie()
        case HKQuantityTypeIdentifier.distanceWalkingRunning.rawValue: .meter()
        default: .count()
        }
    }
}

@MainActor
final class ScheduleCollector: ObservableObject {
    @Published private(set) var calendarState: CapabilityState = .available
    @Published private(set) var reminderState: CapabilityState = .available
    private let store = EKEventStore()
    private let vault: LocalVault
    private let rules: () -> PrivacyRules
    private var observer: NSObjectProtocol?
    private var enabled = false

    init(vault: LocalVault = .shared, rules: @escaping () -> PrivacyRules) {
        self.vault = vault
        self.rules = rules
        observer = NotificationCenter.default.addObserver(
            forName: .EKEventStoreChanged,
            object: store,
            queue: .main
        ) { [weak self] _ in Task { @MainActor in
            guard self?.enabled == true else { return }
            await self?.refresh()
        } }
    }

    func requestAndStart() async {
        enabled = true
        do {
            calendarState = try await store.requestFullAccessToEvents() ? .collecting : .permissionNeeded
            reminderState = try await store.requestFullAccessToReminders() ? .collecting : .permissionNeeded
            await refresh()
        } catch {
            calendarState = .permissionNeeded
            reminderState = .permissionNeeded
        }
    }

    func resume() async {
        enabled = true
        if EKEventStore.authorizationStatus(for: .event) == .fullAccess { calendarState = .collecting }
        if EKEventStore.authorizationStatus(for: .reminder) == .fullAccess { reminderState = .collecting }
        await refresh()
    }

    func stop() {
        enabled = false
        calendarState = .disabled
        reminderState = .disabled
    }

    func refresh() async {
        if EKEventStore.authorizationStatus(for: .event) == .fullAccess {
            let start = Date().addingTimeInterval(-24 * 60 * 60)
            let end = Date().addingTimeInterval(14 * 24 * 60 * 60)
            let events = store.events(matching: store.predicateForEvents(withStart: start, end: end, calendars: nil))
            let observations = events.map { event in
                SignalObservation(
                    kind: .calendar,
                    occurredAt: event.startDate,
                    endedAt: event.endDate,
                    payload: [
                        "external_id": event.eventIdentifier ?? "",
                        "title": event.title ?? "Untitled event",
                        "location": event.location ?? "",
                        "calendar": event.calendar.title,
                        "availability": String(event.availability.rawValue),
                        "revision": event.lastModifiedDate?.ISO8601Format() ?? ""
                    ],
                    origin: "eventkit-calendar"
                )
            }
            try? await vault.append(observations, privacyRules: rules())
        }
        if EKEventStore.authorizationStatus(for: .reminder) == .fullAccess {
            let predicate = store.predicateForReminders(in: nil)
            store.fetchReminders(matching: predicate) { @Sendable [weak self] values in
                Self.handleReminders(values, collector: self)
            }
        }
    }

    private nonisolated static func handleReminders(_ values: [EKReminder]?, collector: ScheduleCollector?) {
        guard let collector else { return }
        let snapshots = (values ?? []).map {
            ReminderSnapshot(
                id: $0.calendarItemIdentifier,
                title: $0.title,
                calendar: $0.calendar.title,
                createdAt: $0.creationDate ?? .now,
                completedAt: $0.completionDate,
                isCompleted: $0.isCompleted,
                priority: $0.priority,
                due: $0.dueDateComponents?.date
            )
        }
        Task { @MainActor in
            await collector.ingest(reminders: snapshots)
        }
    }

    private func ingest(reminders: [ReminderSnapshot]) async {
        let observations = reminders.map { reminder in
            SignalObservation(
                kind: .reminder,
                occurredAt: reminder.createdAt,
                endedAt: reminder.completedAt,
                payload: [
                    "external_id": reminder.id,
                    "title": reminder.title,
                    "calendar": reminder.calendar,
                    "completed": String(reminder.isCompleted),
                    "priority": String(reminder.priority),
                    "due": reminder.due?.ISO8601Format() ?? ""
                ],
                origin: "eventkit-reminders"
            )
        }
        try? await vault.append(observations, privacyRules: rules())
    }
}
