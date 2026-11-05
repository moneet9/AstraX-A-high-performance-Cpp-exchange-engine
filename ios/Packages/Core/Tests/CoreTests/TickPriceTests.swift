import XCTest
@testable import Core

final class TickPriceTests: XCTestCase {
    func testTickPriceKeepsIntegerStorageAndFormatsAsDecimal() {
        let price = TickPrice(rawValue: 1_234_500)
        XCTAssertEqual(price.rawValue, 1_234_500)
        XCTAssertEqual(price.decimalValue, Decimal(12_345) / Decimal(100))
    }

    func testMidpointUsesIntegerTicks() {
        let book = MarketBook(symbol: "ASTR", sequence: 1,
            bids: [BookLevel(priceTicks: 1_000_000, quantity: 3)],
            asks: [BookLevel(priceTicks: 1_000_100, quantity: 4)], receivedAtNanoseconds: 1)
        XCTAssertEqual(book.midpointTicks, 1_000_050)
    }
}
