import XCTest
@testable import ihonor

final class EngineBridgeTests: XCTestCase {
    func testDecodeSyncResult() throws {
        let json = """
        {"ts":1.0,"ok":true,"honor":9,"icloud":9,"pairs":9,
         "created_honor":1,"created_icloud":0,"updated_honor":0,"updated_icloud":0,
         "conflicts":0,"deleted_honor":0,"deleted_icloud":0,"errors":[]}
        """.data(using: .utf8)!
        let r = try EngineBridge.decodeResult(json)
        XCTAssertTrue(r.ok)
        XCTAssertEqual(r.honor, 9)
        XCTAssertEqual(r.created_honor, 1)
    }

    func testDecodePairs() throws {
        let json = """
        [{"honor_id":"h1","icloud_id":"i1","hash_honor":"a","hash_icloud":"b"}]
        """.data(using: .utf8)!
        let pairs = try EngineBridge.decodePairs(json)
        XCTAssertEqual(pairs.count, 1)
        XCTAssertEqual(pairs[0].honor_id, "h1")
    }

    func testDecodeErrorResult() throws {
        let json = """
        {"ts":1.0,"ok":false,"errors":["RuntimeError: boom"]}
        """.data(using: .utf8)!
        let r = try EngineBridge.decodeResult(json)
        XCTAssertFalse(r.ok)
        XCTAssertEqual(r.errors.first, "RuntimeError: boom")
    }
}
