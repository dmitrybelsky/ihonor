import SwiftUI
import AppKit
import UniformTypeIdentifiers

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
        .onDisappear { NSApp.setActivationPolicy(.accessory) }  // вернуть agent-режим
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
        .toolbar {
            Button("Обновить", action: reload)
            Button("Экспорт…", action: exportLog)
            Button("Показать в Finder", action: revealInFinder)
        }
    }
    private func reload() {
        // Отличаем «лога нет» (норм) от ошибки чтения (показываем).
        if !FileManager.default.fileExists(atPath: logPath) { text = ""; return }
        do { text = try String(contentsOfFile: logPath, encoding: .utf8) }
        catch { text = "Не удалось прочитать лог: \(error.localizedDescription)" }
    }
    private func exportLog() {
        let panel = NSSavePanel()
        panel.nameFieldStringValue = "ihonor-log.txt"
        panel.allowedContentTypes = [.plainText]
        panel.canCreateDirectories = true
        NSApp.activate(ignoringOtherApps: true)  // окно уже .regular (open), panel выйдет на перед
        guard panel.runModal() == .OK, let url = panel.url else { return }
        do {
            let content = (try? String(contentsOfFile: logPath, encoding: .utf8)) ?? text
            try content.write(to: url, atomically: true, encoding: .utf8)
        } catch {
            NSAlert(error: error).runModal()         // показываем сбой записи
        }
    }
    private func revealInFinder() {
        NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: logPath)])
    }
}

struct PairsTab: View {
    @State private var pairs: [PairRow] = []
    @State private var err: String?
    @State private var loading = false
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
        guard !loading else { return }  // не плодим параллельные subprocess при частых тапах
        loading = true
        // EngineBridge.pairs() запускает python-subprocess — не на MainActor (иначе фриз UI).
        Task {
            let result = await Task.detached { () -> Result<[PairRow], Error> in
                do { return .success(try EngineBridge.pairs()) }
                catch { return .failure(error) }
            }.value
            loading = false
            switch result {
            case .success(let p): pairs = p; err = nil
            case .failure(let e): err = "Ошибка загрузки пар: \(String("\(e)".prefix(200)))"
            }
        }
    }
}
