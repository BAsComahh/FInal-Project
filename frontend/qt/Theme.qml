import QtQuick

QtObject {
    // Shared light/dark switch owned by window.py (`appearance` context property, not persisted).
    readonly property bool dark: typeof appearance === "undefined" || appearance === null ? true : appearance.dark

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

    // Surfaces (dark tactical console / light field sheet)
    readonly property color bgCanvas: dark ? "#0d141a" : "#e9edf1"
    readonly property color bgHeader: dark ? "#121b23" : "#fbfcfd"
    readonly property color bgSurface: dark ? "#16212b" : "#ffffff"
    readonly property color bgSubtle: dark ? "#1c2a36" : "#f1f4f7"
    readonly property color bgElevated: dark ? "#223341" : "#e6ebf0"
    readonly property color bgHover: dark ? "#283c4c" : "#dde4ea"
    readonly property color bgTrack: dark ? "#101820" : "#f4f6f8"
    readonly property color bgFooter: dark ? "#0f171e" : "#f6f8fa"
    readonly property color bgStage: dark ? "#090e13" : "#d5dce3"
    readonly property color bgGlass: dark ? "#eb111b23" : "#f2ffffff"
    readonly property color bgGlassHover: dark ? "#f51a2936" : "#fff6f8fa"
    readonly property color bgShadow: dark ? "#6604080c" : "#2e1b2a38"
    readonly property color scrim: dark ? "#99060b10" : "#661b2633"

    // Borders
    readonly property color border: dark ? "#263847" : "#d2dae2"
    readonly property color borderSoft: dark ? "#1d2c38" : "#e3e8ed"
    readonly property color borderStrong: dark ? "#3b5468" : "#aebccb"
    readonly property color borderGlass: dark ? "#4d7fa8c2" : "#80a3b3c2"

    // Typography inks
    readonly property color ink: dark ? "#edf3f7" : "#17212b"
    readonly property color inkSecondary: dark ? "#a7bdcd" : "#475a6b"
    readonly property color inkMuted: dark ? "#738c9e" : "#6b7d8e"
    readonly property color keycapBg: dark ? "#121c24" : "#f1f4f7"
    readonly property color keycapBorder: dark ? "#2d4152" : "#c6d0da"

    // Primary accent & unified selection highlight: amber, kept apart from side A blue / side B red.
    readonly property color accent: dark ? "#f0b03c" : "#e9a426"
    readonly property color accentHover: dark ? "#f6c360" : "#d89314"
    readonly property color accentSoft: dark ? "#2e2412" : "#fbf0d9"
    readonly property color accentBorder: dark ? "#7a5a22" : "#e2b45e"
    readonly property color inkOnAccent: "#1d1405"
    readonly property color selection: dark ? "#ffc94d" : "#b47206"

    // Side A (Blue) & Side B (Crimson)
    readonly property color sideA: dark ? "#4ca6e0" : "#2a7fbd"
    readonly property color sideASoft: dark ? "#173145" : "#e2eff9"
    readonly property color sideABorder: dark ? "#336c94" : "#9cc5e5"

    readonly property color sideB: dark ? "#e0626f" : "#c93a4b"
    readonly property color sideBSoft: dark ? "#3a1c22" : "#fbe6e9"
    readonly property color sideBBorder: dark ? "#8c3d47" : "#eaa3ac"

    // On-video unit badges stay dark in both themes for contrast over the bright table.
    readonly property color badgeInk: "#edf3f7"
    readonly property color badgeFill: "#e6101922"
    readonly property color badgeTerrainFill: "#cc101922"
    readonly property color badgeSelectedFill: "#f2241c0c"
    readonly property color badgeDropFill: "#f2133024"
    readonly property color badgeNeedsWorkFill: "#ea2a1a10"
    readonly property color badgeBorder: "#6692aec4"
    readonly property color overlaySelection: "#ffc94d"
    readonly property color overlayHalo: "#e0090e13"

    // Semantic workflow mode tokens
    readonly property color modeLive: dark ? "#36d399" : "#12875b"
    readonly property color modeLiveDot: "#18b87e"
    readonly property color modeLiveSoft: dark ? "#123026" : "#e0f4eb"
    readonly property color modeLiveBorder: dark ? "#24644d" : "#97d5ba"

    // Replay moved from amber to violet so it no longer collides with the amber selection accent.
    readonly property color modeReplay: dark ? "#c49bff" : "#7444d0"
    readonly property color modeReplayDot: dark ? "#a979f2" : "#8656e0"
    readonly property color modeReplaySoft: dark ? "#251b38" : "#efe8fd"
    readonly property color modeReplayBorder: dark ? "#5c4590" : "#c5b1f2"

    readonly property color modeRecovery: dark ? "#f06a76" : "#c6303e"
    readonly property color modeRecoveryDot: "#e04856"
    readonly property color modeRecoverySoft: dark ? "#33181c" : "#fbe7e9"
    readonly property color modeRecoveryBorder: dark ? "#7a3038" : "#eaa0a7"

    readonly property color modeRecalibrate: dark ? "#7aa2f7" : "#3a62c8"
    readonly property color modeRecalibrateDot: "#5a86eb"
    readonly property color modeRecalibrateSoft: dark ? "#17253e" : "#e5ecfb"
    readonly property color modeRecalibrateBorder: dark ? "#385694" : "#a8bcee"

    readonly property color modeTerrain: dark ? "#45d49f" : "#11835a"
    readonly property color modeTerrainDot: "#29b882"
    readonly property color modeTerrainSoft: dark ? "#132e24" : "#dff3ea"
    readonly property color modeTerrainBorder: dark ? "#27694f" : "#96d4ba"

    // Status tokens (warning is orange so it stays distinct from the amber selection)
    readonly property color success: dark ? "#36d399" : "#12875b"
    readonly property color successSoft: dark ? "#123026" : "#e0f4eb"
    readonly property color successBorder: dark ? "#24644d" : "#97d5ba"

    readonly property color warning: dark ? "#ff9150" : "#c4560f"
    readonly property color warningSoft: dark ? "#341f12" : "#fdeee3"
    readonly property color warningBorder: dark ? "#7c4626" : "#efb88f"

    readonly property color danger: dark ? "#d94552" : "#cf3a47"
    readonly property color dangerHover: dark ? "#c23542" : "#b52f3b"
    readonly property color dangerSoft: dark ? "#33181c" : "#fbe7e9"
    readonly property color dangerBorder: dark ? "#7a3038" : "#eaa0a7"
}
