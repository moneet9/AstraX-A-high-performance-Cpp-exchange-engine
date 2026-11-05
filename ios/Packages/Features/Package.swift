// swift-tools-version: 6.0
import PackageDescription

let package = Package(name: "AstraXFeatures", platforms: [.iOS(.v17)], products: [.library(name: "Features", targets: ["Features"])], dependencies: [
    .package(name: "Core", path: "../Core"), .package(name: "Networking", path: "../Networking"),
    .package(name: "MarketData", path: "../MarketData"), .package(name: "Persistence", path: "../Persistence"),
    .package(name: "Trading", path: "../Trading"), .package(name: "DesignSystem", path: "../DesignSystem")
], targets: [.target(name: "Features", dependencies: [
    .product(name: "Core", package: "Core"), .product(name: "Networking", package: "Networking"),
    .product(name: "MarketData", package: "MarketData"), .product(name: "Persistence", package: "Persistence"),
    .product(name: "Trading", package: "Trading"), .product(name: "DesignSystem", package: "DesignSystem")
])])
