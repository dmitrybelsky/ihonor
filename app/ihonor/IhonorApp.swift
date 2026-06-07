import SwiftUI

@main
struct IhonorApp: App {
    @StateObject private var ctrl = SyncController()

    var body: some Scene {
        MenuBarExtra("ihonor", systemImage: "arrow.triangle.2.circlepath") {
            MenuBarView(ctrl: ctrl)
        }
        .menuBarExtraStyle(.window)

        Window("ihonor", id: "main") {
            MainWindowView(ctrl: ctrl)
                .onAppear { ctrl.requestNotificationAuth(); ctrl.refreshPrecheck() }
        }
    }
}
