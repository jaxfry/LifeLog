import AppIntents

struct OpenLifeLogCaptureIntent: AppIntent {
    static let title: LocalizedStringResource = "Capture with LifeLog"
    static let description = IntentDescription("Open LifeLog's optional photo, audio, note, and file capture.")
    static let openAppWhenRun = true

    @MainActor
    func perform() async throws -> some IntentResult {
        LifeLogApp.sharedModel?.selectedTab = .capture
        return .result()
    }
}

struct SyncLifeLogIntent: AppIntent {
    static let title: LocalizedStringResource = "Sync LifeLog"
    static let description = IntentDescription("Reconcile the encrypted local queue with your LifeLog server.")

    @MainActor
    func perform() async throws -> some IntentResult & ProvidesDialog {
        guard let model = LifeLogApp.sharedModel else {
            return .result(dialog: "Open LifeLog once before syncing.")
        }
        await model.syncEngine.syncNow()
        await model.refreshSnapshot()
        return .result(dialog: "LifeLog sync finished. Your local queue remains safe.")
    }
}

struct ExcludeRecentLifeLogIntent: AppIntent {
    static let title: LocalizedStringResource = "Exclude Recent LifeLog Data"
    static let description = IntentDescription("Exclude unsynced observations from the last 15 minutes.")
    static let authenticationPolicy: IntentAuthenticationPolicy = .requiresLocalDeviceAuthentication

    @MainActor
    func perform() async throws -> some IntentResult & ProvidesDialog {
        await LifeLogApp.sharedModel?.excludeRecent()
        return .result(dialog: "The last 15 minutes were excluded from the local queue.")
    }
}

struct LifeLogShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: OpenLifeLogCaptureIntent(),
            phrases: ["Capture with \(.applicationName)", "Remember this with \(.applicationName)"],
            shortTitle: "Capture",
            systemImageName: "plus.circle.fill"
        )
        AppShortcut(
            intent: SyncLifeLogIntent(),
            phrases: ["Sync \(.applicationName)"],
            shortTitle: "Sync",
            systemImageName: "arrow.triangle.2.circlepath"
        )
        AppShortcut(
            intent: ExcludeRecentLifeLogIntent(),
            phrases: ["Exclude recent data from \(.applicationName)"],
            shortTitle: "Exclude recent",
            systemImageName: "eye.slash.fill"
        )
    }
}
