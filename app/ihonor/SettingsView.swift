import SwiftUI

struct MainWindowView: View {
    @ObservedObject var ctrl: SyncController
    var body: some View {
        TabView {
            SettingsTab(ctrl: ctrl).tabItem { Label("Настройки", systemImage: "gear") }
            LogsTab().tabItem { Label("Логи", systemImage: "doc.plaintext") }
            PairsTab().tabItem { Label("Пары", systemImage: "link") }
        }
        .frame(width: 560, height: 420)
        .padding()
    }
}

struct SettingsTab: View {
    @ObservedObject var ctrl: SyncController
    var body: some View {
        Form {
            Toggle("Авто-синк", isOn: $ctrl.autoSync)
            Stepper("Интервал: \(ctrl.intervalMinutes) мин",
                    value: $ctrl.intervalMinutes, in: 1...240)
            Divider()
            ForEach(ctrl.precheck.unmet, id: \.self) { u in
                Label(u, systemImage: "exclamationmark.triangle").foregroundStyle(.orange)
            }
            if ctrl.precheck.unmet.isEmpty {
                Label("Все предусловия выполнены", systemImage: "checkmark.seal")
                    .foregroundStyle(.green)
            }
            Button("Проверить предусловия") { ctrl.refreshPrecheck() }
        }
    }
}

struct LogsTab: View {
    @State private var text: String = ""
    private let logPath = NSString(string: "~/.ihonor/ihonor.log").expandingTildeInPath
    var body: some View {
        ScrollView {
            Text(text.isEmpty ? "Лог пуст" : text)
                .font(.system(.caption, design: .monospaced))
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .onAppear(perform: reload)
        .toolbar { Button("Обновить", action: reload) }
    }
    private func reload() {
        text = (try? String(contentsOfFile: logPath, encoding: .utf8)) ?? ""
    }
}

struct PairsTab: View {
    @State private var pairs: [PairRow] = []
    @State private var err: String?
    var body: some View {
        VStack {
            if let err { Text(err).foregroundStyle(.red) }
            Table(pairs) {
                TableColumn("honor_id", value: \.honor_id)
                TableColumn("icloud_id", value: \.icloud_id)
                TableColumn("hash_h") { Text($0.hash_honor.prefix(8)) }
                TableColumn("hash_i") { Text($0.hash_icloud.prefix(8)) }
            }
        }
        .onAppear(perform: reload)
        .toolbar { Button("Обновить", action: reload) }
    }
    private func reload() {
        do { pairs = try EngineBridge.pairs(); err = nil }
        catch { err = "\(error)" }
    }
}
