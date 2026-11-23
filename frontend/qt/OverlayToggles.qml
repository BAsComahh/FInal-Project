import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Row {
    id: root
    required property var uiState
    property string prefix: ""
    property bool showMasksPill: true
    property bool showTraysPill: true
    property bool showLabelsPill: true
    property bool showTerrainPill: true
    readonly property Theme theme: Theme {}
    readonly property bool anyOverlay: Boolean(uiState && uiState.anyOverlay)
    readonly property bool masksOn: Boolean(uiState && uiState.masks)
    readonly property bool traysOn: Boolean(uiState && uiState.trays)
    readonly property bool labelsOn: Boolean(uiState && uiState.labels)
    readonly property bool terrainOn: Boolean(uiState && uiState.terrain)

    spacing: 5

    component PillButton: Button {
        id: pill
        property bool checkedState: true
        property bool master: false
        property string keyHint: ""
        property string tooltipText: ""
        readonly property Theme t: root.theme
        implicitHeight: 32
        leftPadding: master ? 10 : 9
        rightPadding: master ? 10 : 9
        ToolTip.visible: hovered && tooltipText.length > 0
        ToolTip.text: tooltipText
        ToolTip.delay: 420
        background: Rectangle {
            radius: pill.t.radiusMd
            color: pill.master
                   ? (pill.checkedState ? (pill.hovered ? pill.t.bgElevated : pill.t.bgElevated)
                                        : (pill.hovered ? pill.t.bgElevated : pill.t.bgTrack))
                   : (pill.checkedState ? (pill.hovered ? pill.t.bgElevated : pill.t.accentSoft)
                                        : (pill.hovered ? pill.t.bgElevated : pill.t.bgSubtle))
            border.color: pill.master
                          ? (pill.checkedState ? pill.t.selection : pill.t.borderStrong)
                          : (pill.checkedState ? pill.t.accentBorder : pill.t.border)
        }
        contentItem: RowLayout {
            spacing: 5
            Rectangle {
                width: 7; height: 7; radius: 4
                color: pill.checkedState
                       ? (pill.master ? pill.t.modeLiveDot : pill.t.selection)
                       : pill.t.borderStrong
            }
            Text {
                text: pill.text
                font.family: pill.t.fontBody
                font.pixelSize: pill.t.textSm
                font.weight: pill.checkedState ? Font.DemiBold : Font.Normal
                color: pill.checkedState ? pill.t.ink : pill.t.inkSecondary
            }
            Rectangle {
                visible: pill.keyHint.length > 0
                implicitWidth: keyTxt.implicitWidth + 8
                implicitHeight: 16
                radius: pill.t.radiusXs
                color: pill.t.keycapBg
                border.color: pill.t.keycapBorder
                Text {
                    id: keyTxt
                    anchors.centerIn: parent
                    text: pill.keyHint
                    font.family: pill.t.fontMono
                    font.pixelSize: 10
                    color: pill.t.inkMuted
                }
            }
        }
    }

    PillButton {
        objectName: root.prefix + "OverlayAll"
        text: "Overlays"
        master: true
        keyHint: "O"
        checkedState: root.anyOverlay
        tooltipText: root.anyOverlay ? "Hide all overlays (O)" : "Restore overlays (O)"
        onClicked: ui.toggleAllOverlays()
    }
    PillButton {
        objectName: root.prefix + "OverlayMasks"
        visible: root.showMasksPill
        text: "Masks"
        checkedState: root.masksOn
        tooltipText: "Show or hide unit segmentation masks"
        onClicked: ui.setOverlay("masks", !root.masksOn)
    }
    PillButton {
        objectName: root.prefix + "OverlayTrays"
        visible: root.showTraysPill
        text: "Trays"
        checkedState: root.traysOn
        tooltipText: "Show or hide fitted unit trays"
        onClicked: ui.setOverlay("trays", !root.traysOn)
    }
    PillButton {
        objectName: root.prefix + "OverlayLabels"
        visible: root.showLabelsPill
        text: "Labels"
        checkedState: root.labelsOn
        tooltipText: "Show or hide unit and terrain name badges"
        onClicked: ui.setOverlay("labels", !root.labelsOn)
    }
    PillButton {
        objectName: root.prefix + "OverlayTerrain"
        visible: root.showTerrainPill
        text: "Terrain"
        checkedState: root.terrainOn
        tooltipText: "Show or hide saved terrain polygons and labels"
        onClicked: ui.setOverlay("terrain", !root.terrainOn)
    }
}
