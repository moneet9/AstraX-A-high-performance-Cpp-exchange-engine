// swift-tools-version: 6.0
import PackageDescription

let package = Package(name: "AstraXPersistence", platforms: [.iOS(.v17), .macOS(.v14)], products: [.library(name: "Persistence", targets: ["Persistence"])], dependencies: [
    .package(name: "Core", path: "../Core")
], targets: [.target(name: "Persistence", dependencies: [.product(name: "Core", package: "Core")])])
