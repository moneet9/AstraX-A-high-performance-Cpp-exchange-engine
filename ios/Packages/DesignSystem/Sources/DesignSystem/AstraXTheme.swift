import SwiftUI

public enum AstraXTheme {
    public static let background = Color(red: 0.035, green: 0.055, blue: 0.09)
    public static let surface = Color(red: 0.075, green: 0.105, blue: 0.15)
    public static let raised = Color(red: 0.11, green: 0.15, blue: 0.21)
    public static let text = Color(red: 0.93, green: 0.95, blue: 0.98)
    public static let secondaryText = Color(red: 0.60, green: 0.66, blue: 0.73)
    public static let buy = Color(red: 0.25, green: 0.70, blue: 0.95)
    public static let sell = Color(red: 1.0, green: 0.59, blue: 0.36)
    public static let positive = Color(red: 0.42, green: 0.82, blue: 0.64)
    public static let negative = Color(red: 1.0, green: 0.50, blue: 0.51)
    public static let border = Color.white.opacity(0.09)
}

public struct CardSurface<Content: View>: View {
    private let content: Content

    public init(@ViewBuilder content: () -> Content) {
        self.content = content()
    }

    public var body: some View {
        content
            .padding(16)
            .background(AstraXTheme.surface, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 16).stroke(AstraXTheme.border, lineWidth: 1))
    }
}

public enum PriceFormatting {
    @MainActor
    public static func string(ticks: Int64, scale: Int64 = 10_000, currency: String = "USD") -> String {
        let formatter = NumberFormatter()
        formatter.numberStyle = .currency
        formatter.currencyCode = currency
        formatter.maximumFractionDigits = 4
        formatter.minimumFractionDigits = 2
        return formatter.string(from: NSDecimalNumber(decimal: Decimal(ticks) / Decimal(max(scale, 1)))) ?? "—"
    }
}
