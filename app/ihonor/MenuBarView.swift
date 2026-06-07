import SwiftUI

struct MenuBarView: View {
    @ObservedObject var ctrl: SyncController
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(ctrl.lastMessage).font(.callout)
            if let r = ctrl.lastResult {
                Text(detail(r)).font(.caption).foregroundStyle(.secondary)
            }
            Divider()
            Button(ctrl.status == .running ? "Синхронизация…" : "Sync now") {
                ctrl.syncNow()
            }.disabled(ctrl.status == .running)
            Toggle("Авто-синк каждые \(ctrl.intervalMinutes) мин", isOn: $ctrl.autoSync)
            if !ctrl.precheck.unmet.isEmpty {
                Divider()
                ForEach(ctrl.precheck.unmet, id: \.self) { u in
                    Label(u, systemImage: "exclamationmark.triangle")
                        .font(.caption).foregroundStyle(.orange)
                }
            }
            Divider()
            Button("Открыть окно…") {
                NSApp.activate(ignoringOtherApps: true)  // accessory-app: иначе окно не выходит на перед
                openWindow(id: "main")
            }
            Button("Выход") { NSApplication.shared.terminate(nil) }
        }
        .padding(10)
        .frame(width: 280)
        .onAppear { ctrl.refreshPrecheck() }
    }

    private func detail(_ r: SyncResult) -> String {
        "создано H\(r.created_honor ?? 0)/I\(r.created_icloud ?? 0) · "
        + "обновлено H\(r.updated_honor ?? 0)/I\(r.updated_icloud ?? 0) · "
        + "конфликты \(r.conflicts ?? 0)"
    }
}
