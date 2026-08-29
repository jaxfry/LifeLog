import Foundation

enum SignalKind: String, Codable, CaseIterable, Sendable {
    case location
    case visit
    case motion
    case steps
    case health
    case calendar
    case reminder
    case connectivity
    case battery
    case power
    case audio
    case note
    case photo
    case photoLibrary = "photo_library"
    case contact
    case bluetooth
    case file
}

enum QueueState: String, Codable, Sendable {
    case locallyCommitted
    case redacted
    case queued
    case uploading
    case serverVerified
    case processing
    case ready
    case retrying
    case excluded
    case failed
}

struct BufferedSignal: Identifiable, Codable, Sendable, Hashable {
    let id: UUID
    let kind: SignalKind
    let occurredAt: Date
    var endedAt: Date?
    var payload: [String: String]
    var state: QueueState
    var attempts: Int
    var nextAttemptAt: Date?
    var lastError: String?
    var redactionAudit: [String]

    init(
        id: UUID = UUID(),
        kind: SignalKind,
        occurredAt: Date = .now,
        endedAt: Date? = nil,
        payload: [String: String],
        state: QueueState = .locallyCommitted,
        attempts: Int = 0,
        nextAttemptAt: Date? = nil,
        lastError: String? = nil,
        redactionAudit: [String] = []
    ) {
        self.id = id
        self.kind = kind
        self.occurredAt = occurredAt
        self.endedAt = endedAt
        self.payload = payload
        self.state = state
        self.attempts = attempts
        self.nextAttemptAt = nextAttemptAt
        self.lastError = lastError
        self.redactionAudit = redactionAudit
    }
}

struct SignalObservation: Sendable {
    let kind: SignalKind
    let occurredAt: Date
    let endedAt: Date?
    let payload: [String: String]
    let origin: String?

    init(
        kind: SignalKind,
        occurredAt: Date = .now,
        endedAt: Date? = nil,
        payload: [String: String],
        origin: String? = nil
    ) {
        self.kind = kind
        self.occurredAt = occurredAt
        self.endedAt = endedAt
        self.payload = payload
        self.origin = origin
    }
}

struct BufferedArtifact: Identifiable, Codable, Sendable, Hashable {
    let id: UUID
    let captureID: UUID
    let kind: SignalKind
    let createdAt: Date
    let localFilename: String
    let originalFilename: String
    let mimeType: String
    let byteCount: Int64
    let sha256: String
    var intent: String?
    var context: [String: String]
    var state: QueueState
    var serverCaptureID: UUID?
    var serverUploadID: UUID?
    var uploadedBytes: Int64
    var attempts: Int
    var nextAttemptAt: Date?
    var lastError: String?
    var redactionAudit: [String]
}

struct VaultSnapshot: Sendable {
    let signals: [BufferedSignal]
    let artifacts: [BufferedArtifact]
    let totalSignalCount: Int
    let totalArtifactCount: Int
    private let totalPendingCount: Int

    init(
        signals: [BufferedSignal],
        artifacts: [BufferedArtifact],
        totalSignalCount: Int? = nil,
        totalArtifactCount: Int? = nil,
        totalPendingCount: Int? = nil
    ) {
        self.signals = signals
        self.artifacts = artifacts
        self.totalSignalCount = totalSignalCount ?? signals.count
        self.totalArtifactCount = totalArtifactCount ?? artifacts.count
        self.totalPendingCount = totalPendingCount ?? (
            signals.filter { ![.serverVerified, .ready, .excluded].contains($0.state) }.count
                + artifacts.filter { ![.serverVerified, .ready, .excluded].contains($0.state) }.count
        )
    }

    var pendingCount: Int {
        totalPendingCount
    }
}

enum CapabilityState: String, Sendable {
    case collecting = "Collecting"
    case available = "Available"
    case permissionNeeded = "Needs permission"
    case limited = "Limited by iOS"
    case unavailable = "Unavailable"
    case disabled = "Off"
}

struct CapabilityStatus: Identifiable, Sendable {
    let id: String
    let name: String
    let detail: String
    let symbol: String
    var state: CapabilityState
}

struct ClientConfiguration: Codable, Sendable {
    var serverURL: String = "http://lifelog.local:8000"
    var deviceAPIKey: String = ""
    var bearerToken: String = ""
    var uploadOnCellular = true
    var preciseLocationMode = false
    var keepOriginalDays = 7
    var automaticCollectionEnabled = false
    var enabledCapabilities: Set<String> = []

    enum CodingKeys: String, CodingKey {
        case serverURL, deviceAPIKey, bearerToken, uploadOnCellular, preciseLocationMode
        case keepOriginalDays, automaticCollectionEnabled, enabledCapabilities
    }

    init() {}

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        serverURL = try values.decodeIfPresent(String.self, forKey: .serverURL) ?? "http://lifelog.local:8000"
        deviceAPIKey = try values.decodeIfPresent(String.self, forKey: .deviceAPIKey) ?? ""
        bearerToken = try values.decodeIfPresent(String.self, forKey: .bearerToken) ?? ""
        uploadOnCellular = try values.decodeIfPresent(Bool.self, forKey: .uploadOnCellular) ?? true
        preciseLocationMode = try values.decodeIfPresent(Bool.self, forKey: .preciseLocationMode) ?? false
        keepOriginalDays = try values.decodeIfPresent(Int.self, forKey: .keepOriginalDays) ?? 7
        automaticCollectionEnabled = try values.decodeIfPresent(Bool.self, forKey: .automaticCollectionEnabled) ?? false
        enabledCapabilities = try values.decodeIfPresent(Set<String>.self, forKey: .enabledCapabilities) ?? []
    }
}

struct PrivacyRules: Codable, Sendable {
    var redactSecrets = true
    var redactFinancialNumbers = true
    var redactEmailAddresses = false
    var excludedOrigins: Set<String> = []
    var customPatterns: [String] = []
    var privateGeofences: [PrivateGeofence] = []
}

struct PrivateGeofence: Identifiable, Codable, Sendable, Hashable {
    let id: UUID
    var name: String
    var latitude: Double
    var longitude: Double
    var radiusMeters: Double
}
