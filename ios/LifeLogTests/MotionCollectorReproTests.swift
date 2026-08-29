import CoreMotion
import Testing
@testable import LifeLog

struct MotionCollectorReproTests {
    @Test @MainActor func startDoesNotTrapOnBackgroundCallbacks() async throws {
        guard CMMotionActivityManager.isActivityAvailable() else { return }
        let collector = MotionCollector(rules: { PrivacyRules() })
        collector.start()
        try await Task.sleep(for: .seconds(10))
    }
}
