import QtQuick

QtObject {
    // Typography families & unified size scale
    readonly property string fontBody: "Segoe UI"
    readonly property string fontDisplay: "Bahnschrift"
    readonly property string fontMono: "Consolas"

    readonly property int textXs: 11
    readonly property int textSm: 12
    readonly property int textMd: 13
    readonly property int textLg: 16
    readonly property int textXl: 20

    // Unified corner radius scale
    readonly property real radiusXs: 4
    readonly property real radiusSm: 6
    readonly property real radiusMd: 8
    readonly property real radiusLg: 12

    // Dark tactical console surfaces
    readonly property color bgCanvas: "#0d141a"
    readonly property color bgHeader: "#121b23"
    readonly property color bgSurface: "#16212b"
    readonly property color bgSubtle: "#1c2a36"
    readonly property color bgElevated: "#223341"
    readonly property color bgHover: "#283c4c"
    readonly property color bgTrack: "#101820"
    readonly property color bgFooter: "#0f171e"
    readonly property color bgStage: "#090e13"
    readonly property color bgGlass: "#eb111b23"
    readonly property color bgGlassHover: "#f51a2936"
    readonly property color bgShadow: "#6604080c"
    readonly property color scrim: "#99060b10"

    // Borders
    readonly property color border: "#263847"
    readonly property color borderSoft: "#1d2c38"
    readonly property color borderStrong: "#3b5468"
    readonly property color borderGlass: "#4d7fa8c2"

    // Typography inks
    readonly property color ink: "#edf3f7"
    readonly property color inkSecondary: "#a7bdcd"
    readonly property color inkMuted: "#738c9e"
    readonly property color keycapBg: "#121c24"
    readonly property color keycapBorder: "#2d4152"

    // Primary accent & unified selection highlight (distinct from Replay amber)
    readonly property color accent: "#2d9dc4"
    readonly property color accentHover: "#39b1da"
    readonly property color accentSoft: "#183848"
    readonly property color accentBorder: "#347896"
    readonly property color selection: "#4ce8ff"

    // Side A (Blue) & Side B (Crimson)
    readonly property color sideA: "#4ca6e0"
    readonly property color sideASoft: "#173145"
    readonly property color sideABorder: "#336c94"

    readonly property color sideB: "#e0626f"
    readonly property color sideBSoft: "#3a1c22"
    readonly property color sideBBorder: "#8c3d47"

    // Semantic workflow mode tokens
    readonly property color modeLive: "#36d399"
    readonly property color modeLiveDot: "#18b87e"
    readonly property color modeLiveSoft: "#123026"
    readonly property color modeLiveBorder: "#24644d"

    readonly property color modeReplay: "#f0b44c"
    readonly property color modeReplayDot: "#e8a23a"
    readonly property color modeReplaySoft: "#2b2113"
    readonly property color modeReplayBorder: "#705124"

    readonly property color modeRecovery: "#f06a76"
    readonly property color modeRecoveryDot: "#e04856"
    readonly property color modeRecoverySoft: "#33181c"
    readonly property color modeRecoveryBorder: "#7a3038"

    readonly property color modeRecalibrate: "#7aa2f7"
    readonly property color modeRecalibrateDot: "#5a86eb"
    readonly property color modeRecalibrateSoft: "#17253e"
    readonly property color modeRecalibrateBorder: "#385694"

    readonly property color modeTerrain: "#45d49f"
    readonly property color modeTerrainDot: "#29b882"
    readonly property color modeTerrainSoft: "#132e24"
    readonly property color modeTerrainBorder: "#27694f"

    // Status tokens
    readonly property color success: "#36d399"
    readonly property color successSoft: "#123026"
    readonly property color successBorder: "#24644d"

    readonly property color warning: "#f0b44c"
    readonly property color warningSoft: "#2b2113"
    readonly property color warningBorder: "#705124"

    readonly property color danger: "#d94552"
    readonly property color dangerHover: "#c23542"
    readonly property color dangerSoft: "#33181c"
    readonly property color dangerBorder: "#7a3038"
}
