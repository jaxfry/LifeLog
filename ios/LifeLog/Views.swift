import PhotosUI
import SwiftUI
import UniformTypeIdentifiers
@preconcurrency import VisionKit

private let lifeLogPurple = Color(red: 0.52, green: 0.38, blue: 1.0)
private let lifeLogPink = Color(red: 0.95, green: 0.35, blue: 0.55)
private let lifeLogGreen = Color(red: 0.35, green: 0.87, blue: 0.56)

struct RootView: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        TabView(selection: $model.selectedTab) {
            TodayView().tag(AppTab.today).tabItem { Label("Today", systemImage: "circle.grid.cross") }
            CaptureView().tag(AppTab.capture).tabItem { Label("Capture", systemImage: "plus.circle.fill") }
            AssistantView().tag(AppTab.assistant).tabItem { Label("Ask", systemImage: "sparkles") }
            SourcesView().tag(AppTab.sources).tabItem { Label("Signals", systemImage: "wave.3.right") }
            SettingsView().tag(AppTab.settings).tabItem { Label("You", systemImage: "person.crop.circle") }
        }
        .tint(lifeLogPurple)
        .sheet(isPresented: $model.showingQueue) { QueueView() }
        .sheet(isPresented: $model.showingPrivacy) { PrivacyView() }
        .alert(
            "LifeLog needs attention",
            isPresented: Binding(
                get: { model.lastCaptureError != nil },
                set: { if !$0 { model.lastCaptureError = nil } }
            )
        ) {
            Button("OK") { model.lastCaptureError = nil }
        } message: {
            Text(model.lastCaptureError ?? "The capture remains available to try again.")
        }
    }
}

struct TodayView: View {
    @EnvironmentObject private var model: AppModel
    @EnvironmentObject private var store: ConfigurationStore

    private var recent: [BufferedSignal] { Array(model.snapshot.signals.prefix(25)) }
    private var collectingCount: Int { model.capabilities.filter { $0.state == .collecting }.count }

    var body: some View {
        NavigationStack {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 22) {
                    header
                    ambientStatus
                    if model.audio.isRecording { activeRecording }
                    timeline
                }
                .padding(.horizontal, 20)
                .padding(.bottom, 28)
            }
            .background(Color.black)
            .toolbar(.hidden, for: .navigationBar)
            .refreshable {
                await model.refreshSnapshot()
                await model.syncEngine.syncNow()
            }
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 13) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(Date.now.formatted(.dateTime.weekday(.wide).month(.abbreviated).day()))
                        .font(.caption.weight(.bold)).foregroundStyle(.secondary).textCase(.uppercase)
                    Text("Life, captured\nautomatically.")
                        .font(.system(size: 38, weight: .bold, design: .rounded)).tracking(-1.2)
                }
                Spacer()
                Button { model.showingPrivacy = true } label: {
                    Image(systemName: "hand.raised.fill")
                        .font(.system(size: 16, weight: .semibold))
                        .frame(width: 42, height: 42)
                        .background(.thinMaterial, in: Circle())
                }
                .accessibilityLabel("Privacy controls")
            }
            Button { model.showingQueue = true } label: {
                HStack(spacing: 8) {
                    Circle().fill(syncIndicatorColor).frame(width: 7, height: 7)
                    Text(queueLabel).font(.caption.weight(.semibold))
                    Image(systemName: "chevron.right").font(.caption2.weight(.bold))
                }
                .foregroundStyle(syncIndicatorColor)
                .padding(.horizontal, 12).padding(.vertical, 9)
                .background(syncIndicatorColor.opacity(0.12), in: Capsule())
            }
        }
        .padding(.top, 12)
    }

    private var queueLabel: String {
        if store.configuration.deviceAPIKey.isEmpty { return "Not paired · captures stay on this iPhone" }
        if !model.syncEngine.isOnline { return "Offline · everything safe on iPhone" }
        if model.snapshot.pendingCount > 0 { return "Safe · \(model.snapshot.pendingCount) syncing" }
        return "Everything safe and synced"
    }

    private var syncIndicatorColor: Color {
        store.configuration.deviceAPIKey.isEmpty || !model.syncEngine.isOnline ? .orange : lifeLogGreen
    }

    private var ambientStatus: some View {
        HStack(spacing: 18) {
            ZStack {
                Circle().stroke(.white.opacity(0.08), lineWidth: 8)
                Circle().trim(from: 0, to: min(Double(collectingCount) / Double(max(model.capabilities.count, 1)), 1))
                    .stroke(
                        AngularGradient(colors: [lifeLogPurple, lifeLogPink, lifeLogGreen], center: .center),
                        style: StrokeStyle(lineWidth: 8, lineCap: .round)
                    )
                    .rotationEffect(.degrees(-90))
                Image(systemName: "wave.3.right").font(.title2.weight(.semibold))
            }
            .frame(width: 78, height: 78)
            VStack(alignment: .leading, spacing: 5) {
                Text(store.configuration.automaticCollectionEnabled ? "Ambient collection is on" : "Automatic collection is ready").font(.headline)
                Text(store.configuration.automaticCollectionEnabled ? "\(collectingCount) automatic signals active" : "Enable once, then LifeLog keeps collecting")
                    .font(.subheadline).foregroundStyle(.secondary)
                if store.configuration.automaticCollectionEnabled {
                    Text("Tap Signals to control each source").font(.caption).foregroundStyle(.tertiary)
                } else {
                    Button("Turn on LifeLog") { Task { await model.enableAutomaticCollection() } }
                        .font(.caption.weight(.bold)).foregroundStyle(lifeLogGreen)
                }
            }
            Spacer()
        }
        .padding(17)
        .background(
            LinearGradient(colors: [lifeLogPurple.opacity(0.2), Color.white.opacity(0.04)], startPoint: .topLeading, endPoint: .bottomTrailing),
            in: RoundedRectangle(cornerRadius: 24, style: .continuous)
        )
        .overlay(RoundedRectangle(cornerRadius: 24).stroke(.white.opacity(0.09)))
    }

    private var activeRecording: some View {
        Button { model.selectedTab = .capture } label: {
            HStack(spacing: 13) {
                Image(systemName: "waveform.circle.fill").font(.largeTitle).foregroundStyle(lifeLogPink)
                VStack(alignment: .leading) {
                    Text("Audio recording").font(.headline)
                    Text("\(model.audio.duration.formattedDuration) · continues with screen locked")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Image(systemName: "chevron.right")
            }
            .padding(16).background(.thinMaterial, in: RoundedRectangle(cornerRadius: 20))
        }.buttonStyle(.plain)
    }

    private var timeline: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack { Text("Today").font(.title2.bold()); Spacer(); Text("Observed locally").font(.caption).foregroundStyle(.secondary) }
                .padding(.bottom, 12)
            if recent.isEmpty {
                ContentUnavailableView(
                    "Your timeline is warming up",
                    systemImage: "sparkles",
                    description: Text("Enable signals once. LifeLog will quietly reconstruct the day as observations arrive.")
                ).frame(height: 260).frame(maxWidth: .infinity)
            } else {
                ForEach(recent) { signal in TimelineRow(signal: signal) }
            }
        }
    }
}

private struct TimelineRow: View {
    let signal: BufferedSignal
    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Text(signal.occurredAt.formatted(date: .omitted, time: .shortened))
                .font(.caption.monospacedDigit()).foregroundStyle(.secondary).frame(width: 48, alignment: .leading)
            VStack(spacing: 0) {
                Circle().fill(color).frame(width: 10, height: 10)
                Rectangle().fill(.white.opacity(0.1)).frame(width: 1, height: 54)
            }
            VStack(alignment: .leading, spacing: 4) {
                Text(title).font(.subheadline.weight(.semibold))
                Text(detail).font(.caption).foregroundStyle(.secondary).lineLimit(2)
                Label("Observed · \(signal.kind.rawValue)", systemImage: "circle.fill")
                    .font(.caption2).foregroundStyle(color)
            }
            Spacer()
        }
        .padding(.vertical, 5)
    }

    private var title: String {
        switch signal.kind {
        case .location: "Location changed"
        case .visit: "Visit detected"
        case .motion: (signal.payload["activity"] ?? "Motion").capitalized
        case .steps: "Movement summary"
        case .health: signal.payload["sample_type"]?.components(separatedBy: ".").last ?? "Health update"
        case .calendar: signal.payload["title"] ?? "Calendar event"
        case .reminder: signal.payload["title"] ?? "Reminder"
        case .connectivity: "Connectivity changed"
        case .battery: "Device state"
        case .audio: "Audio recording"
        case .note: "Quick note"
        case .photo: "Photo"
        case .photoLibrary: "New photo-library item"
        case .contact: "Contact updated"
        case .bluetooth: "Accessory nearby"
        case .file: "Imported file"
        case .power: "Power state"
        }
    }

    private var detail: String {
        if signal.kind == .note { return signal.payload["text"] ?? "Saved note" }
        if signal.kind == .calendar { return signal.payload["location"].flatMap { $0.isEmpty ? nil : $0 } ?? signal.payload["calendar"] ?? "" }
        return signal.payload.filter { $0.key != "source" }.prefix(3).map { "\($0.key.replacingOccurrences(of: "_", with: " ")): \($0.value)" }.joined(separator: " · ")
    }

    private var color: Color {
        signal.state == .excluded ? .secondary : (signal.redactionAudit.isEmpty ? lifeLogGreen : .orange)
    }
}

struct CaptureView: View {
    @EnvironmentObject private var model: AppModel
    @State private var note = ""
    @State private var photoItem: PhotosPickerItem?
    @State private var showingFiles = false
    @State private var showingScanner = false
    @FocusState private var noteFocused: Bool

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Capture").font(.system(size: 38, weight: .bold, design: .rounded))
                        Text("Optional, deliberate moments alongside automatic collection.").foregroundStyle(.secondary)
                    }
                    audioPanel
                    notePanel
                    HStack(spacing: 12) {
                        captureButton("Scan", icon: "doc.viewfinder") { showingScanner = true }
                        PhotosPicker(selection: $photoItem, matching: .images) {
                            VStack(spacing: 10) {
                                Image(systemName: "photo").font(.title2)
                                Text("Photo").font(.caption.weight(.semibold))
                            }
                            .frame(maxWidth: .infinity).padding(.vertical, 20)
                            .background(.white.opacity(0.06), in: RoundedRectangle(cornerRadius: 20))
                        }
                        captureButton("Files", icon: "folder") { showingFiles = true }
                    }
                    Text("Nothing here requires choosing a Life Area, source, or category. Originals are encrypted locally first; classification happens later.")
                        .font(.caption).foregroundStyle(.tertiary).padding(.horizontal, 4)
                }.padding(20)
            }.background(Color.black).toolbar(.hidden, for: .navigationBar)
        }
        .fileImporter(isPresented: $showingFiles, allowedContentTypes: [.item]) { result in
            if case .success(let url) = result {
                Task { await model.preserveImportedFile(url, kind: .file, mimeType: UTType(filenameExtension: url.pathExtension)?.preferredMIMEType ?? "application/octet-stream") }
            }
        }
        .sheet(isPresented: $showingScanner) { DocumentScanner { urls in
            for url in urls { Task { await model.preserveImportedFile(url, kind: .photo, mimeType: "image/jpeg") } }
        }}
        .onChange(of: photoItem) { _, item in
            Task {
                guard let data = try? await item?.loadTransferable(type: Data.self) else {
                    model.reportCaptureError("The selected photo could not be read.")
                    return
                }
                let url = FileManager.default.temporaryDirectory.appendingPathComponent("photo-\(UUID().uuidString).jpg")
                do { try data.write(to: url, options: .atomic) }
                catch { model.reportCaptureError("The selected photo could not be staged safely."); return }
                await model.preserveImportedFile(url, kind: .photo, mimeType: "image/jpeg")
            }
        }
    }

    private var audioPanel: some View {
        VStack(spacing: 20) {
            ZStack {
                Circle().fill(LinearGradient(colors: [lifeLogPurple, lifeLogPink], startPoint: .topLeading, endPoint: .bottomTrailing)).frame(width: 94, height: 94)
                Image(systemName: model.audio.isRecording ? "stop.fill" : "waveform").font(.system(size: 34, weight: .semibold))
            }
            Text(model.audio.isRecording ? model.audio.duration.formattedDuration : "Record audio")
                .font(.title2.bold()).monospacedDigit()
            Text(model.audio.isRecording ? "Safe on this iPhone · recording continues in the background" : "For a class, meeting, voice note, or anything worth hearing again")
                .font(.subheadline).foregroundStyle(.secondary).multilineTextAlignment(.center)
            if let error = model.audio.lastError {
                Label(error, systemImage: "exclamationmark.triangle.fill")
                    .font(.caption).foregroundStyle(.orange).multilineTextAlignment(.center)
            }
            if model.audio.isRecording {
                HStack(spacing: 12) {
                    Button { model.audio.addBookmark() } label: { Label("Bookmark", systemImage: "bookmark.fill").frame(maxWidth: .infinity) }.buttonStyle(.bordered)
                    Button { Task { await model.audio.stop(); await model.refreshSnapshot() } } label: { Text("Finish").frame(maxWidth: .infinity) }.buttonStyle(.borderedProminent).tint(lifeLogPink)
                }
            } else {
                Button { Task { await model.audio.start() } } label: { Text("Record").frame(maxWidth: .infinity) }.buttonStyle(.borderedProminent).tint(lifeLogPurple)
            }
        }
        .padding(22).frame(maxWidth: .infinity)
        .background(LinearGradient(colors: [lifeLogPurple.opacity(0.2), .white.opacity(0.04)], startPoint: .topLeading, endPoint: .bottomTrailing), in: RoundedRectangle(cornerRadius: 28))
    }

    private var notePanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Quick note", systemImage: "text.cursor").font(.headline)
            TextEditor(text: $note).focused($noteFocused).frame(minHeight: 90).scrollContentBackground(.hidden)
                .padding(10).background(.black.opacity(0.2), in: RoundedRectangle(cornerRadius: 14))
            Button("Save note") {
                let value = note
                noteFocused = false
                Task { if await model.saveNote(value) { note = "" } }
            }
                .buttonStyle(.borderedProminent).tint(lifeLogPurple).disabled(note.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        }.padding(18).background(.white.opacity(0.055), in: RoundedRectangle(cornerRadius: 22))
    }

    private func captureButton(_ title: String, icon: String, action: @escaping () -> Void) -> some View {
        Button(action: action) { captureButtonLabel(title, icon: icon) }
    }
    private func captureButtonLabel(_ title: String, icon: String) -> some View {
        VStack(spacing: 10) { Image(systemName: icon).font(.title2); Text(title).font(.caption.weight(.semibold)) }
            .frame(maxWidth: .infinity).padding(.vertical, 20).background(.white.opacity(0.06), in: RoundedRectangle(cornerRadius: 20))
    }
}

struct QueueView: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        NavigationStack {
            List {
                Section {
                    Label(connectionLabel, systemImage: connectionSymbol)
                        .foregroundStyle(connectionColor)
                    Text("\(model.snapshot.pendingCount) items waiting. Every item shown here is already encrypted and safe on this iPhone.").font(.subheadline).foregroundStyle(.secondary)
                    if let error = model.syncEngine.lastError {
                        Label(error, systemImage: "exclamationmark.triangle.fill")
                            .font(.caption).foregroundStyle(.orange)
                    }
                    Button("Sync now") { Task { await model.syncEngine.syncNow(); await model.refreshSnapshot() } }
                }
                Section("Signals") { ForEach(model.snapshot.signals.prefix(100)) { QueueSignalRow(signal: $0) } }
                Section("Files & recordings") { ForEach(model.snapshot.artifacts) { QueueArtifactRow(artifact: $0) } }
            }
            .navigationTitle("Safe & syncing")
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
        }
    }


    private var connectionLabel: String {
        if model.configurationStore.configuration.deviceAPIKey.isEmpty { return "Server not paired" }
        return model.syncEngine.isOnline ? "Connected" : "Offline"
    }

    private var connectionSymbol: String {
        model.configurationStore.configuration.deviceAPIKey.isEmpty
            ? "iphone.slash" : (model.syncEngine.isOnline ? "checkmark.icloud.fill" : "icloud.slash.fill")
    }

    private var connectionColor: Color {
        model.configurationStore.configuration.deviceAPIKey.isEmpty || !model.syncEngine.isOnline ? .orange : lifeLogGreen
    }
}

private struct QueueSignalRow: View {
    let signal: BufferedSignal
    var body: some View { HStack { Image(systemName: signal.kind.symbol).foregroundStyle(lifeLogPurple); VStack(alignment: .leading) { Text(signal.kind.rawValue.capitalized); Text(signal.occurredAt.formatted()).font(.caption).foregroundStyle(.secondary) }; Spacer(); Text(signal.state.label).font(.caption).foregroundStyle(.secondary) } }
}
private struct QueueArtifactRow: View {
    let artifact: BufferedArtifact
    var body: some View { HStack { Image(systemName: artifact.kind.symbol).foregroundStyle(lifeLogPink); VStack(alignment: .leading) { Text(artifact.originalFilename); ProgressView(value: Double(artifact.uploadedBytes), total: Double(max(artifact.byteCount, 1))) }; Text(artifact.state.label).font(.caption).foregroundStyle(.secondary) } }
}

struct PrivacyView: View {
    @EnvironmentObject private var model: AppModel
    @EnvironmentObject private var store: ConfigurationStore
    @Environment(\.dismiss) private var dismiss
    @State private var newOrigin = ""
    @State private var newPattern = ""
    @State private var privatePlaceName = ""
    var body: some View {
        NavigationStack {
            Form {
                Section("Before anything uploads") {
                    Toggle("Secrets and API keys", isOn: $store.privacyRules.redactSecrets)
                    Toggle("Financial numbers", isOn: $store.privacyRules.redactFinancialNumbers)
                    Toggle("Email addresses", isOn: $store.privacyRules.redactEmailAddresses)
                    Text("Text observations are redacted before they enter the queue. Files and recordings are encrypted locally; exclusions can prevent their upload, but binary content is not silently rewritten.").font(.caption).foregroundStyle(.secondary)
                }
                Section("Excluded origins") {
                    ForEach(store.privacyRules.excludedOrigins.sorted(), id: \.self) { Text($0) }
                        .onDelete { offsets in
                            let values = store.privacyRules.excludedOrigins.sorted()
                            for offset in offsets { store.privacyRules.excludedOrigins.remove(values[offset]) }
                        }
                    HStack { TextField("Bundle ID or source", text: $newOrigin).textInputAutocapitalization(.never); Button("Add") { if !newOrigin.isEmpty { store.privacyRules.excludedOrigins.insert(newOrigin); newOrigin = "" } } }
                }
                Section("Private places") {
                    ForEach($store.privacyRules.privateGeofences) { $place in
                        VStack(alignment: .leading) {
                            Text(place.name)
                            Stepper("Pause within \(Int(place.radiusMeters)) m", value: $place.radiusMeters, in: 25...2_000, step: 25)
                                .font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    .onDelete { store.privacyRules.privateGeofences.remove(atOffsets: $0) }
                    HStack {
                        TextField("Name this place", text: $privatePlaceName)
                        Button("Use current") { model.addCurrentPrivatePlace(name: privatePlaceName); privatePlaceName = "" }
                            .disabled(model.location.lastLocation == nil)
                    }
                }
                Section("Custom redaction") {
                    ForEach(store.privacyRules.customPatterns, id: \.self) { Text($0).font(.caption.monospaced()) }
                        .onDelete { store.privacyRules.customPatterns.remove(atOffsets: $0) }
                    HStack { TextField("Regular expression", text: $newPattern).textInputAutocapitalization(.never); Button("Add") { if (try? NSRegularExpression(pattern: newPattern)) != nil { store.privacyRules.customPatterns.append(newPattern); newPattern = "" } } }
                }
                Section("Emergency control") {
                    Button("Exclude the last 15 minutes", role: .destructive) { Task { await model.excludeRecent() } }
                    Text("Removes unsynced payloads from the recent local buffer and records only that you excluded the period.").font(.caption).foregroundStyle(.secondary)
                }
                Section("Local originals") { Stepper("Keep verified originals for \(store.configuration.keepOriginalDays) days", value: $store.configuration.keepOriginalDays, in: 1...365) }
            }
            .navigationTitle("Privacy on device")
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
        }
    }
}

struct SourcesView: View {
    @EnvironmentObject private var model: AppModel
    var body: some View {
        NavigationStack {
            List {
                Section {
                    Button { Task { await model.enableAutomaticCollection() } } label: {
                        HStack { VStack(alignment: .leading) { Text("Turn on LifeLog").font(.headline); Text("Then enable each signal you want once; collection remains automatic").font(.caption).foregroundStyle(.secondary) }; Spacer(); Image(systemName: "arrow.right.circle.fill").font(.title2).foregroundStyle(lifeLogPurple) }
                    }
                }
                Section("Automatic signals") {
                    ForEach(model.capabilities) { capability in
                        let enabled = model.isCapabilityEnabled(capability.id)
                        Button { Task { await model.toggleCapability(capability.id) } } label: { HStack(spacing: 13) {
                            Image(systemName: capability.symbol).frame(width: 30).foregroundStyle(capability.state == .collecting ? lifeLogGreen : lifeLogPurple)
                            VStack(alignment: .leading, spacing: 3) { Text(capability.name); Text(capability.detail).font(.caption).foregroundStyle(.secondary) }
                            Spacer(); Text(enabled ? "On" : capability.state.rawValue).font(.caption2.weight(.semibold)).foregroundStyle(enabled ? lifeLogGreen : .secondary)
                        }.padding(.vertical, 5) }
                        .buttonStyle(.plain)
                        .disabled(!model.canToggleCapability(capability.id))
                    }
                }
                Section("Operating-system boundary") {
                    Text("Sideloading removes App Store review, not iOS sandboxing. Background delivery is system-scheduled. Audio continues in the background only after an explicit recording begins. Screen Time data still requires Apple's Family Controls entitlement.").font(.caption).foregroundStyle(.secondary)
                }
            }.navigationTitle("Signals")
        }
    }
}

struct AssistantView: View {
    @EnvironmentObject private var model: AppModel
    @EnvironmentObject private var store: ConfigurationStore
    @State private var input = ""
    @State private var turns: [(role: String, content: String)] = []
    @State private var thinking = false
    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                ScrollView {
                    LazyVStack(spacing: 14) {
                        if turns.isEmpty {
                            ContentUnavailableView("Ask across your life", systemImage: "sparkles", description: Text("LifeLog retrieves relevant memories automatically and cites its evidence."))
                                .padding(.top, 90)
                        }
                        ForEach(Array(turns.enumerated()), id: \.offset) { _, turn in
                            HStack { if turn.role == "user" { Spacer(minLength: 40) }; Text(turn.content).textSelection(.enabled).padding(14).background(turn.role == "user" ? lifeLogPurple : .white.opacity(0.07), in: RoundedRectangle(cornerRadius: 18)); if turn.role != "user" { Spacer(minLength: 25) } }
                        }
                        if thinking { ProgressView().padding() }
                    }.padding()
                }
                HStack(spacing: 10) {
                    TextField("Ask LifeLog anything…", text: $input, axis: .vertical).lineLimit(1...5).padding(12).background(.white.opacity(0.07), in: RoundedRectangle(cornerRadius: 16))
                    Button { send() } label: { Image(systemName: "arrow.up").font(.headline).frame(width: 42, height: 42).background(lifeLogPurple, in: RoundedRectangle(cornerRadius: 15)) }.disabled(input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || thinking)
                }.padding()
            }.navigationTitle("Ask")
        }
    }

    private func send() {
        let question = input.trimmingCharacters(in: .whitespacesAndNewlines)
        let history = turns.suffix(12).map { ["role": $0.role, "content": $0.content] }
        turns.append(("user", question)); input = ""; thinking = true
        Task {
            do { turns.append(("assistant", try await LifeLogAPI(configuration: store.configuration).chat(message: question, history: history))) }
            catch { turns.append(("assistant", error.localizedDescription)) }
            thinking = false
        }
    }
}

struct SettingsView: View {
    @EnvironmentObject private var model: AppModel
    @EnvironmentObject private var store: ConfigurationStore
    var body: some View {
        NavigationStack {
            Form {
                Section("LifeLog server") {
                    TextField("https://lifelog.example.com", text: $store.configuration.serverURL).textInputAutocapitalization(.never).keyboardType(.URL)
                    SecureField("Device API key", text: $store.configuration.deviceAPIKey)
                    SecureField("Account token for Assistant", text: $store.configuration.bearerToken)
                    Toggle("Upload on cellular", isOn: $store.configuration.uploadOnCellular)
                    Button("Test & sync") { Task { await model.syncEngine.syncNow(); await model.refreshSnapshot() } }
                }
                Section("Location detail") {
                    Toggle("Precise background trails", isOn: $store.configuration.preciseLocationMode)
                    Text("Off uses low-power visits and significant changes. On adds frequent GPS while iOS permits it and uses substantially more battery.").font(.caption).foregroundStyle(.secondary)
                }
                Section("Storage") {
                    LabeledContent("Signals", value: model.snapshot.totalSignalCount.formatted())
                    LabeledContent("Files", value: model.snapshot.totalArtifactCount.formatted())
                    LabeledContent("Waiting", value: model.snapshot.pendingCount.formatted())
                }
                Section { Button("Privacy & exclusions") { model.showingPrivacy = true }; Button("Upload queue") { model.showingQueue = true } }
            }.navigationTitle("You")
            .onChange(of: store.configuration.preciseLocationMode) { _, precise in
                model.location.start(precise: precise)
            }
        }
    }
}

struct DocumentScanner: UIViewControllerRepresentable {
    let completion: ([URL]) -> Void
    @Environment(\.dismiss) private var dismiss

    func makeCoordinator() -> Coordinator { Coordinator(parent: self) }
    func makeUIViewController(context: Context) -> VNDocumentCameraViewController {
        let controller = VNDocumentCameraViewController(); controller.delegate = context.coordinator; return controller
    }
    func updateUIViewController(_ uiViewController: VNDocumentCameraViewController, context: Context) {}

    @MainActor final class Coordinator: NSObject, @preconcurrency VNDocumentCameraViewControllerDelegate {
        let parent: DocumentScanner
        init(parent: DocumentScanner) { self.parent = parent }
        func documentCameraViewController(_ controller: VNDocumentCameraViewController, didFinishWith scan: VNDocumentCameraScan) {
            var urls: [URL] = []
            for page in 0..<scan.pageCount {
                guard let data = scan.imageOfPage(at: page).jpegData(compressionQuality: 0.92) else { continue }
                let url = FileManager.default.temporaryDirectory.appendingPathComponent("scan-\(UUID().uuidString).jpg")
                try? data.write(to: url, options: .atomic); urls.append(url)
            }
            parent.completion(urls); parent.dismiss()
        }
        func documentCameraViewControllerDidCancel(_ controller: VNDocumentCameraViewController) { parent.dismiss() }
    }
}

private extension SignalKind {
    var symbol: String {
        switch self {
        case .location, .visit: "location.fill"
        case .motion, .steps: "figure.walk.motion"
        case .health: "heart.fill"
        case .calendar: "calendar"
        case .reminder: "checklist"
        case .connectivity: "wifi"
        case .battery, .power: "battery.75percent"
        case .audio: "waveform"
        case .note: "note.text"
        case .photo, .photoLibrary: "photo"
        case .contact: "person.crop.circle"
        case .bluetooth: "antenna.radiowaves.left.and.right"
        case .file: "doc"
        }
    }
}

private extension QueueState {
    var label: String {
        switch self {
        case .locallyCommitted: "Safe locally"
        case .redacted: "Redacted locally"
        case .queued: "Waiting"
        case .uploading: "Uploading"
        case .serverVerified: "Verified"
        case .processing: "Processing"
        case .ready: "Searchable"
        case .retrying: "Will retry"
        case .excluded: "Excluded"
        case .failed: "Needs attention"
        }
    }
}

private extension TimeInterval {
    var formattedDuration: String {
        let total = Int(self)
        return String(format: "%02d:%02d:%02d", total / 3600, (total % 3600) / 60, total % 60)
    }
}
