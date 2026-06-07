import Foundation

enum EngineError: Error { case nonZero(Int32, String), notFound }

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
        try proc.run()
        let data = out.fileHandleForReading.readDataToEndOfFile()
        let errData = err.fileHandleForReading.readDataToEndOfFile()
        proc.waitUntilExit()
        if proc.terminationStatus != 0 && data.isEmpty {
            let msg = String(data: errData, encoding: .utf8) ?? ""
            throw EngineError.nonZero(proc.terminationStatus, msg)
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
