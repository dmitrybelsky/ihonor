import Foundation

enum EngineError: Error { case nonZero(Int32, String), notFound, launchFailed(String) }

struct EngineBridge {
    /// Путь к забандленному python внутри .app (bundle-задача кладёт сюда).
    static func pythonPath() -> String? {
        if let res = Bundle.main.resourcePath {
            let p = res + "/pyengine/bin/python3"
            if FileManager.default.isExecutableFile(atPath: p) { return p }
        }
        if let dev = ProcessInfo.processInfo.environment["IHONOR_DEV_PYTHON"] { return dev }
        return nil
    }

    static func decodeResult(_ data: Data) throws -> SyncResult {
        try JSONDecoder().decode(SyncResult.self, from: data)
    }

    static func decodePairs(_ data: Data) throws -> [PairRow] {
        try JSONDecoder().decode([PairRow].self, from: data)
    }

    static func run(module: String, args: [String] = []) throws -> Data {
        guard let py = pythonPath() else { throw EngineError.notFound }
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: py)
        proc.arguments = ["-m", module] + args
        let out = Pipe(); let err = Pipe()
        proc.standardOutput = out; proc.standardError = err
        do { try proc.run() } catch { throw EngineError.launchFailed("\(error)") }
        // Watchdog: зависший движок (стак CDP-сокет / Accessibility-промпт / залипший
        // AppleScript) иначе клинит синк навсегда (status застрянет .running). Убиваем по дедлайну.
        let watchdog = DispatchWorkItem {
            guard proc.isRunning else { return }
            proc.terminate()  // SIGTERM
            // эскалация: процесс, игнорящий SIGTERM, добиваем SIGKILL через 5с
            DispatchQueue.global().asyncAfter(deadline: .now() + 5) {
                if proc.isRunning { kill(proc.processIdentifier, SIGKILL) }
            }
        }
        DispatchQueue.global().asyncAfter(deadline: .now() + 240, execute: watchdog)
        defer { watchdog.cancel() }
        // Читаем stderr в фоне, чтобы не словить deadlock на полном pipe-буфере,
        // пока блокируемся на чтении stdout (traceback/log может превысить 64KB).
        var errData = Data()
        let g = DispatchGroup(); g.enter()
        DispatchQueue.global().async {
            errData = err.fileHandleForReading.readDataToEndOfFile(); g.leave()
        }
        let data = out.fileHandleForReading.readDataToEndOfFile()
        g.wait()
        proc.waitUntilExit()
        // runner на ошибке пишет валидный error-JSON и exit(1) — это легитимно (декодится в ok:false).
        // Но ненулевой exit с НЕ-JSON stdout (traceback/print до краха) = реальный сбой:
        // бросаем со stderr, не отдаём мусор в JSONDecoder.
        if proc.terminationStatus != 0 {
            // runner на ошибке пишет ПОЛНЫЙ валидный error-JSON и exit(1) — легитимно.
            // Валидируем именно парсингом (не первым символом): обрезанный JSON от
            // watchdog-kill/краха не пройдёт → отдаём stderr, а не мусор в декодер.
            let valid = (try? JSONSerialization.jsonObject(with: data)) != nil
            if !valid {
                throw EngineError.nonZero(proc.terminationStatus,
                                          String(data: errData, encoding: .utf8) ?? "")
            }
        }
        return data
    }

    static func sync() throws -> SyncResult {
        try decodeResult(try run(module: "ihonor.runner", args: ["--json"]))
    }

    static func pairs() throws -> [PairRow] {
        try decodePairs(try run(module: "ihonor.statedump"))
    }
}
