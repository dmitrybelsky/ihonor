import Foundation
import AppKit
import ApplicationServices

struct Preconditions {
    static func evaluate(cdp: Bool, accessibility: Bool, notes: Bool) -> PrecheckResult {
        var unmet: [String] = []
        if !cdp { unmet.append("HonorWorkStation не запущен с CDP (порт 9222)") }
        if !accessibility { unmet.append("Нет разрешения Accessibility (нужно для delete)") }
        if !notes { unmet.append("Apple Notes.app не найден") }
        return PrecheckResult(honorWorkStationCDP: cdp, accessibility: accessibility,
                              notesApp: notes, unmet: unmet)
    }

    static func checkCDP(port: Int = 9222) -> Bool {
        guard let url = URL(string: "http://localhost:\(port)/json") else { return false }
        let sem = DispatchSemaphore(value: 0)
        var ok = false
        var req = URLRequest(url: url); req.timeoutInterval = 2
        URLSession.shared.dataTask(with: req) { _, resp, _ in
            if let h = resp as? HTTPURLResponse, h.statusCode == 200 { ok = true }
            sem.signal()
        }.resume()
        _ = sem.wait(timeout: .now() + 3)
        return ok
    }

    static func checkAccessibility(prompt: Bool = false) -> Bool {
        let opts = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: prompt]
        return AXIsProcessTrustedWithOptions(opts as CFDictionary)
    }

    static func checkNotesApp() -> Bool {
        FileManager.default.fileExists(atPath: "/System/Applications/Notes.app")
            || FileManager.default.fileExists(atPath: "/Applications/Notes.app")
    }

    static func launchHonorWorkStation(port: Int = 9222) {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/open")
        p.arguments = ["-a", "HonorWorkStation", "--args", "--remote-debugging-port=\(port)"]
        do { try p.run() } catch { NSLog("ihonor: launch HonorWorkStation failed: \(error)") }
    }

    static func current() -> PrecheckResult {
        evaluate(cdp: checkCDP(), accessibility: checkAccessibility(), notes: checkNotesApp())
    }
}
