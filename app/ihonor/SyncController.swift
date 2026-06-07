import Foundation
import SwiftUI
import UserNotifications

@MainActor
final class SyncController: ObservableObject {
    enum Status: Equatable { case idle, running, ok, warning, error }

    @Published var status: Status = .idle
    @Published var lastResult: SyncResult?
    @Published var lastMessage: String = "Не синхронизировано"
    @Published var autoSync: Bool = false { didSet { rescheduleTimer() } }
    @Published var intervalMinutes: Int = 15 { didSet { rescheduleTimer() } }
    @Published var precheck: PrecheckResult = Preconditions.evaluate(cdp: false, accessibility: false, notes: false)

    private var timer: Timer?

    deinit { timer?.invalidate() }

    /// Precheck выполняется ВНЕ MainActor (checkCDP блокирует до ~2с), результат публикуем на main.
    func refreshPrecheck() {
        Task.detached { [weak self] in
            let pre = Preconditions.current()
            await MainActor.run { self?.precheck = pre }
        }
    }

    func syncNow() {
        guard status != .running else { return }
        status = .running
        lastMessage = "Синхронизация…"
        Task.detached { [weak self] in
            // precheck off-main (блокирующий сетевой probe), публикуем на main
            var pre = Preconditions.current()
            await MainActor.run { self?.precheck = pre }
            if pre.unmet.contains(where: { $0.contains("HonorWorkStation") }) {
                Preconditions.launchHonorWorkStation()
                try? await Task.sleep(nanoseconds: 6_000_000_000)
                pre = Preconditions.current()
                await MainActor.run { self?.precheck = pre }
            }
            do {
                let r = try EngineBridge.sync()
                await MainActor.run { self?.apply(r) }
            } catch {
                await MainActor.run { self?.fail("\(error)") }
            }
        }
    }

    private func apply(_ r: SyncResult) {
        lastResult = r
        if !r.ok || !r.errors.isEmpty {
            status = .error
            lastMessage = "Ошибка: " + (r.errors.first ?? "неизвестно")
            notify("Синк: ошибка", lastMessage)
        } else {
            let conflicts = r.conflicts ?? 0
            status = conflicts > 0 ? .warning : .ok
            lastMessage = "OK · honor \(r.honor ?? 0) · icloud \(r.icloud ?? 0) · пары \(r.pairs ?? 0)"
            if conflicts > 0 { notify("Синк: конфликты", "Создано конфликт-копий: \(conflicts)") }
        }
    }

    private func fail(_ msg: String) {
        status = .error
        lastMessage = "Сбой: \(msg)"
        notify("Синк: сбой", msg)
    }

    private func rescheduleTimer() {
        timer?.invalidate(); timer = nil
        guard autoSync else { return }
        let interval = TimeInterval(max(1, intervalMinutes) * 60)
        timer = Timer.scheduledTimer(withTimeInterval: interval, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.syncNow() }
        }
    }

    private func notify(_ title: String, _ body: String) {
        let c = UNMutableNotificationContent(); c.title = title; c.body = body
        let req = UNNotificationRequest(identifier: UUID().uuidString, content: c, trigger: nil)
        UNUserNotificationCenter.current().add(req)
    }

    func requestNotificationAuth() {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { granted, error in
            if let error { NSLog("ihonor: notif auth error: \(error)") }
            else if !granted { NSLog("ihonor: notifications denied by user") }
        }
    }
}
