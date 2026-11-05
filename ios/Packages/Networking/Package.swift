// swift-tools-version: 6.0
import PackageDescription

let package = Package(name: "AstraXNetworking", platforms: [.iOS(.v17), .macOS(.v14)], products: [.library(name: "Networking", targets: ["Networking"])], dependencies: [
    .package(name: "Core", path: "../Core")
], targets: [.target(name: "Networking", dependencies: [.product(name: "Core", package: "Core")])])
