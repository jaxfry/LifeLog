import SwiftUI

@main
struct LifeLogApp: App {
    @UIApplicationDelegateAdaptor(LifeLogAppDelegate.self) private var appDelegate
    @StateObject private var model: AppModel
    static weak var sharedModel: AppModel?
    @Environment(\.scenePhase) private var scenePhase

    init() {
        let value = AppModel()
        _model = StateObject(wrappedValue: value)
        Self.sharedModel = value
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(model)
                .environmentObject(model.configurationStore)
                .preferredColorScheme(.dark)
                .task { model.start() }
                .onChange(of: scenePhase) { _, phase in model.handleScenePhase(phase) }
        }
    }
}
