// swift-tools-version: 6.0
import PackageDescription

let package = Package(name: "AstraXMarketData", platforms: [.iOS(.v17)], products: [.library(name: "MarketData", targets: ["MarketData"])], dependencies: [
    .package(name: "Core", path: "../Core"), .package(name: "Networking", path: "../Networking")
], targets: [.target(name: "MarketData", dependencies: [
    .product(name: "Core", package: "Core"), .product(name: "Networking", package: "Networking")
])])
