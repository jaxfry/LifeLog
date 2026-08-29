import CoreLocation
import Testing
@testable import LifeLog

struct PrivacyEngineTests {
    @Test func redactsSecretsBeforeQueueAdmission() {
        let engine = PrivacyEngine(rules: PrivacyRules())
        let decision = engine.process(payload: ["note": "token sk-test_12345678901234567890"])

        #expect(!decision.excluded)
        #expect(decision.payload["note"] == "token [REDACTED]")
        #expect(decision.audit.count == 1)
    }

    @Test func excludesConfiguredOriginsWithoutRetainingPayload() {
        var rules = PrivacyRules()
        rules.excludedOrigins = ["com.example.private"]
        let decision = PrivacyEngine(rules: rules).process(
            payload: ["title": "sensitive"],
            origin: "com.example.private"
        )

        #expect(decision.excluded)
        #expect(decision.payload.isEmpty)
    }

    @Test func recognizesPrivateGeofence() {
        var rules = PrivacyRules()
        rules.privateGeofences = [
            PrivateGeofence(id: UUID(), name: "Private", latitude: 49.2827, longitude: -123.1207, radiusMeters: 100)
        ]
        let engine = PrivacyEngine(rules: rules)

        #expect(engine.isPrivateLocation(CLLocation(latitude: 49.2827, longitude: -123.1207)))
        #expect(!engine.isPrivateLocation(CLLocation(latitude: 49.30, longitude: -123.12)))
    }
}
