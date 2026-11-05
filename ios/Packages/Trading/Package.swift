// swift-tools-version: 6.0
import PackageDescription

let package = Package(name: "AstraXTrading", platforms: [.iOS(.v17), .macOS(.v14)], products: [.library(name: "Trading", targets: ["Trading"])], dependencies: [
    .package(name: "Core", path: "../Core"), .package(name: "Networking", path: "../Networking"),
    .package(name: "Persistence", path: "../Persistence")
], targets: [.target(name: "Trading", dependencies: [
    .product(name: "Core", package: "Core"), .product(name: "Networking", package: "Networking"),
    .product(name: "Persistence", package: "Persistence")
]), .testTarget(name: "TradingTests", dependencies: ["Trading", .product(name: "Core", package: "Core")])])
