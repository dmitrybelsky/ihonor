import XCTest
@testable import ihonor

final class PreconditionsTests: XCTestCase {
    func testAllMetGivesEmptyUnmet() {
        let r = Preconditions.evaluate(cdp: true, accessibility: true, notes: true)
        XCTAssertTrue(r.unmet.isEmpty)
    }

    func testMissingCDPListed() {
        let r = Preconditions.evaluate(cdp: false, accessibility: true, notes: true)
        XCTAssertEqual(r.unmet.count, 1)
        XCTAssertTrue(r.unmet[0].contains("HonorWorkStation"))
    }

    func testMissingAllListsThree() {
        let r = Preconditions.evaluate(cdp: false, accessibility: false, notes: false)
        XCTAssertEqual(r.unmet.count, 3)
    }
}
