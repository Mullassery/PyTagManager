// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "PyTagManager",
    platforms: [.iOS(.v15), .macOS(.v12)],
    products: [
        .library(name: "PyTagManager", targets: ["PyTagManager"]),
    ],
    targets: [
        .target(name: "PyTagManager"),
        .executableTarget(
            name: "PyTagManagerChecks",
            dependencies: ["PyTagManager"],
            resources: [.copy("Fixtures")]
        ),
        .testTarget(
            name: "PyTagManagerTests",
            dependencies: ["PyTagManager"],
            resources: [.copy("Fixtures")]
        ),
    ]
)
