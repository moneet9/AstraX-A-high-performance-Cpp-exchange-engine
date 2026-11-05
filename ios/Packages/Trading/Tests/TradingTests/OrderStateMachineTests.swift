import XCTest
import Core
@testable import Trading

final class OrderStateMachineTests: XCTestCase {
    func testOrderSubmitsAndFillsThroughValidTransitions() throws {
        var machine = OrderStateMachine()
        try machine.transition(to: .submitting)
        try machine.transition(to: .partiallyFilled)
        try machine.transition(to: .filled)
        XCTAssertEqual(machine.state, .filled)
    }

    func testRejectsInvalidTransitionFromTerminalState() throws {
        var machine = OrderStateMachine(state: .cancelled)
        XCTAssertThrowsError(try machine.transition(to: .submitting))
    }

    func testLimitRequiresPositiveTickAlignedIntegerPrice() throws {
        let request = OrderRequestDTO(symbol: "ASTR", side: .buy, type: .limit,
                                      quantity: 5, priceTicks: 1_000_050)
        XCTAssertThrowsError(try OrderManager.validate(request, tickSize: 100))
    }

    func testIcebergVisibleQuantityMustBeSmallerThanTotal() throws {
        let request = OrderRequestDTO(symbol: "ASTR", side: .buy, type: .iceberg,
                                      quantity: 10, priceTicks: 1_000_000, visibleQuantity: 10)
        XCTAssertThrowsError(try OrderManager.validate(request, tickSize: 100))
    }
}
