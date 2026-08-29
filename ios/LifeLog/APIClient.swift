import Foundation

private struct BatchIngestBody: Encodable {
    let extensionID = "com.lifelog.ios"
    let payload: SignalBatchPayload
    let clientTimestamp: Date
    let clientTimezone: String

    enum CodingKeys: String, CodingKey {
        case extensionID = "extension_id"
        case payload
        case clientTimestamp = "client_timestamp"
        case clientTimezone = "client_timezone"
    }
}

private struct SignalBatchPayload: Encodable {
    let format = "lifelog.ios.signal-batch.v1"
    let events: [SignalPayload]
}

private struct SignalPayload: Encodable {
    let id: String
    let type: String
    let startTime: Date
    let endTime: Date?
    let data: [String: String]

    enum CodingKeys: String, CodingKey {
        case id, type, data
        case startTime = "start_time"
        case endTime = "end_time"
    }
}

private struct CaptureDraftBody: Encodable {
    let kind: String
    let capturedAt: Date
    let timezone: String
    let intent: String?
    let contextHints: [String: String]
    let privacy: [String: String]
    let idempotencyKey: String

    enum CodingKeys: String, CodingKey {
        case kind, timezone, intent, privacy
        case capturedAt = "captured_at"
        case contextHints = "context_hints"
        case idempotencyKey = "idempotency_key"
    }
}

private struct CaptureDetailResponse: Decodable {
    struct CaptureValue: Decodable { let id: UUID }
    struct ArtifactValue: Decodable {
        let contentHash: String
        enum CodingKeys: String, CodingKey { case contentHash = "content_hash" }
    }
    let capture: CaptureValue
    let artifacts: [ArtifactValue]?
}

private struct UploadSessionBody: Encodable {
    let filename: String
    let mimeType: String
    let totalBytes: Int64

    enum CodingKeys: String, CodingKey {
        case filename
        case mimeType = "mime_type"
        case totalBytes = "total_bytes"
    }
}

private struct UploadSessionResponse: Decodable {
    let id: UUID
    let receivedBytes: Int64
    let status: String
    let contentHash: String?

    enum CodingKeys: String, CodingKey {
        case id
        case receivedBytes = "received_bytes"
        case status
        case contentHash = "content_hash"
    }
}

struct LifeLogAPI: Sendable {
    let configuration: ClientConfiguration

    private var baseURL: URL? {
        URL(string: configuration.serverURL.trimmingCharacters(in: CharacterSet(charactersIn: "/")))
    }

    func send(_ signals: [BufferedSignal]) async throws {
        guard let earliest = signals.map(\.occurredAt).min(), !signals.isEmpty else { return }
        let events = signals.map {
            SignalPayload(
                id: $0.id.uuidString,
                type: $0.kind.rawValue,
                startTime: $0.occurredAt,
                endTime: $0.endedAt,
                data: $0.payload
            )
        }
        let body = BatchIngestBody(
            payload: SignalBatchPayload(events: events),
            clientTimestamp: earliest,
            clientTimezone: TimeZone.current.identifier
        )
        let request = try request(path: "/api/v1/ingest", method: "POST", body: body)
        _ = try await perform(request)
    }

    func createCaptureDraft(for artifact: BufferedArtifact) async throws -> UUID {
        let body = CaptureDraftBody(
            kind: serverKind(for: artifact.kind),
            capturedAt: artifact.createdAt,
            timezone: TimeZone.current.identifier,
            intent: artifact.intent,
            contextHints: artifact.context,
            privacy: [:],
            idempotencyKey: artifact.captureID.uuidString
        )
        let request = try request(path: "/api/v1/captures/drafts", method: "POST", body: body)
        let data = try await perform(request)
        return try decoder.decode(CaptureDetailResponse.self, from: data).capture.id
    }

    func createUploadSession(captureID: UUID, artifact: BufferedArtifact) async throws -> UUID {
        let body = UploadSessionBody(
            filename: artifact.originalFilename,
            mimeType: artifact.mimeType,
            totalBytes: artifact.byteCount
        )
        let request = try request(
            path: "/api/v1/captures/\(captureID)/uploads",
            method: "POST",
            body: body
        )
        let data = try await perform(request)
        return try decoder.decode(UploadSessionResponse.self, from: data).id
    }

    func uploadState(captureID: UUID, uploadID: UUID) async throws -> UploadState {
        let request = try request(
            path: "/api/v1/captures/\(captureID)/uploads/\(uploadID)",
            method: "GET"
        )
        let data = try await perform(request)
        let response = try decoder.decode(UploadSessionResponse.self, from: data)
        return UploadState(
            receivedBytes: response.receivedBytes,
            status: response.status,
            contentHash: response.contentHash
        )
    }

    func completeUpload(captureID: UUID, uploadID: UUID, expectedHash: String) async throws {
        let request = try request(
            path: "/api/v1/captures/\(captureID)/uploads/\(uploadID)/complete",
            method: "POST"
        )
        let detail = try decoder.decode(CaptureDetailResponse.self, from: try await perform(request))
        guard detail.artifacts?.contains(where: { $0.contentHash == expectedHash }) == true else {
            throw APIError.integrityMismatch
        }
    }

    func cancelCapture(_ captureID: UUID) async throws {
        let request = try request(path: "/api/v1/captures/\(captureID)/cancel", method: "POST")
        _ = try await perform(request)
    }

    func uploadRequest(captureID: UUID, uploadID: UUID, offset: Int64) throws -> URLRequest {
        var request = try request(
            path: "/api/v1/captures/\(captureID)/uploads/\(uploadID)",
            method: "PUT"
        )
        request.setValue(String(offset), forHTTPHeaderField: "Upload-Offset")
        request.setValue("application/octet-stream", forHTTPHeaderField: "Content-Type")
        return request
    }

    func chat(message: String, history: [[String: String]]) async throws -> String {
        struct ChatBody: Encodable {
            let message: String
            let history: [[String: String]]
            let timezone: String
        }
        struct ChatResponse: Decodable { let response: String }
        guard !configuration.bearerToken.isEmpty else {
            throw APIError.message("Add an account token in Settings to use Assistant.")
        }
        var request = try request(
            path: "/api/v1/ai/chat",
            method: "POST",
            body: ChatBody(message: message, history: history, timezone: TimeZone.current.identifier)
        )
        request.setValue("Bearer \(configuration.bearerToken)", forHTTPHeaderField: "Authorization")
        return try decoder.decode(ChatResponse.self, from: try await perform(request)).response
    }

    private var encoder: JSONEncoder {
        let value = JSONEncoder()
        value.dateEncodingStrategy = .iso8601
        return value
    }

    private var decoder: JSONDecoder {
        let value = JSONDecoder()
        value.dateDecodingStrategy = .iso8601
        return value
    }

    private func request(path: String, method: String) throws -> URLRequest {
        guard let url = baseURL?.appending(path: path) else { throw APIError.invalidServerURL }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = 60
        request.setValue(configuration.deviceAPIKey, forHTTPHeaderField: "X-API-Key")
        return request
    }

    private func request<T: Encodable>(path: String, method: String, body: T) throws -> URLRequest {
        var value = try request(path: path, method: method)
        value.setValue("application/json", forHTTPHeaderField: "Content-Type")
        value.httpBody = try encoder.encode(body)
        return value
    }

    private func perform(_ request: URLRequest) async throws -> Data {
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            let message = String(data: data, encoding: .utf8) ?? "Server rejected the request."
            throw APIError.message(message)
        }
        return data
    }

    private func serverKind(for kind: SignalKind) -> String {
        switch kind {
        case .audio: "audio"
        case .photo: "photo"
        case .note: "note"
        default: "file"
        }
    }
}

enum APIError: LocalizedError {
    case invalidServerURL
    case integrityMismatch
    case message(String)

    var errorDescription: String? {
        switch self {
        case .invalidServerURL: "The LifeLog server URL is invalid."
        case .integrityMismatch: "The server copy did not match the encrypted local original. Upload stopped safely."
        case .message(let value): value
        }
    }
}

struct UploadState: Sendable {
    let receivedBytes: Int64
    let status: String
    let contentHash: String?
}
