// swift-tools-version: 6.0
import PackageDescription

let package = Package(name: "AstraXDesignSystem", platforms: [.iOS(.v17)], products: [.library(name: "DesignSystem", targets: ["DesignSystem"])], dependencies: [
    .package(name: "Core", path: "../Core")
], targets: [.target(name: "DesignSystem", dependencies: [.product(name: "Core", package: "Core")])])
