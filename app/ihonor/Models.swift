import Foundation

struct SyncResult: Codable, Equatable {
    var ts: Double
    var ok: Bool
    var honor: Int?
    var icloud: Int?
    var pairs: Int?
    var created_honor: Int?
    var created_icloud: Int?
    var updated_honor: Int?
    var updated_icloud: Int?
    var conflicts: Int?
    var deleted_honor: Int?
    var deleted_icloud: Int?
    var errors: [String]
}

struct PairRow: Codable, Equatable, Identifiable {
    var honor_id: String
    var icloud_id: String
    var hash_honor: String
    var hash_icloud: String
    var id: String { honor_id + "|" + icloud_id }
}

struct PrecheckResult: Equatable {
    var honorWorkStationCDP: Bool
    var accessibility: Bool
    var notesApp: Bool
    var unmet: [String]
}
