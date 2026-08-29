import CoreLocation
import Foundation

struct PrivacyDecision: Sendable {
    let excluded: Bool
    let payload: [String: String]
    let audit: [String]
}

struct PrivacyEngine: Sendable {
    let rules: PrivacyRules

    private static let secretPatterns = [
        #"(?i)\b(?:sk|pk|api)[-_][a-z0-9_-]{16,}\b"#,
        #"(?i)\bBearer\s+[a-z0-9._~+/-]{12,}=*"#,
        #"(?i)\b(?:password|passwd|pwd)\s*[:=]\s*\S+"#
    ]
    private static let financialPatterns = [
        #"\b(?:\d[ -]*?){13,19}\b"#,
        #"\b\d{6,17}\b"#
    ]
    private static let emailPatterns = [#"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"#]

    func process(payload: [String: String], origin: String? = nil) -> PrivacyDecision {
        if let origin, rules.excludedOrigins.contains(origin) {
            return PrivacyDecision(excluded: true, payload: [:], audit: ["excluded-origin:\(origin)"])
        }
        var result = payload
        var audit: [String] = []
        let patterns =
            (rules.redactSecrets ? Self.secretPatterns : [])
            + (rules.redactFinancialNumbers ? Self.financialPatterns : [])
            + (rules.redactEmailAddresses ? Self.emailPatterns : [])
            + rules.customPatterns
        for key in result.keys.sorted() {
            guard var value = result[key] else { continue }
            for (index, pattern) in patterns.enumerated() {
                guard let expression = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]) else { continue }
                let range = NSRange(value.startIndex..., in: value)
                let replaced = expression.stringByReplacingMatches(
                    in: value,
                    range: range,
                    withTemplate: "[REDACTED]"
                )
                if replaced != value {
                    value = replaced
                    audit.append("redacted:\(key):rule-\(index)")
                }
            }
            result[key] = value
        }
        return PrivacyDecision(excluded: false, payload: result, audit: audit)
    }

    func isPrivateLocation(_ location: CLLocation) -> Bool {
        rules.privateGeofences.contains { fence in
            location.distance(from: CLLocation(latitude: fence.latitude, longitude: fence.longitude))
                <= fence.radiusMeters
        }
    }
}
