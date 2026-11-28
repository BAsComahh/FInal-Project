import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
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

    implicitWidth: stripRow.implicitWidth + 6
    implicitHeight: 32
    radius: theme.radiusMd
    color: theme.bgTrack
    border.color: theme.border

    component LayerChip: Button {
        id: pill
        property bool checkedState: true
        property bool master: false
        property string tooltipText: ""
        readonly property Theme t: root.theme
        implicitHeight: 26
        leftPadding: master ? 9 : 8
        rightPadding: master ? 9 : 8
        ToolTip.visible: hovered && tooltipText.length > 0
        ToolTip.text: tooltipText
        ToolTip.delay: 420
        background: Rectangle {
            radius: pill.t.radiusSm
            color: pill.checkedState
                   ? (pill.hovered ? pill.t.bgHover : pill.t.bgElevated)
                   : (pill.hovered ? pill.t.bgSubtle : "transparent")
            border.width: pill.checkedState ? 1 : 0
            border.color: pill.master
                          ? (pill.checkedState ? pill.t.modeLiveBorder : "transparent")
                          : (pill.checkedState ? pill.t.borderStrong : "transparent")
        }
        contentItem: RowLayout {
            spacing: 5
            Rectangle {
                width: 6; height: 6; radius: 3
                color: pill.checkedState
                       ? (pill.master ? pill.t.modeLiveDot : pill.t.selection)
                       : pill.t.borderStrong
                opacity: pill.checkedState ? 1.0 : 0.65
            }
            Text {
                text: pill.text
                font.family: pill.t.fontBody
                font.pixelSize: pill.t.textSm
                font.weight: pill.checkedState ? Font.DemiBold : Font.Normal
                color: pill.checkedState ? pill.t.ink : pill.t.inkMuted
            }
        }
    }

    Row {
        id: stripRow
        anchors.centerIn: parent
        spacing: 2

        LayerChip {
            objectName: root.prefix + "OverlayAll"
            text: "Overlays"
            master: true
            checkedState: root.anyOverlay
            tooltipText: root.anyOverlay ? "Hide all overlays (O)" : "Restore overlays (O)"
            onClicked: ui.toggleAllOverlays()
        }

        Rectangle {
            width: 1
            height: 16
            anchors.verticalCenter: parent.verticalCenter
            color: root.theme.border
        }

        LayerChip {
            objectName: root.prefix + "OverlayMasks"
            visible: root.showMasksPill
            text: "Masks"
            checkedState: root.masksOn
            tooltipText: "Show or hide unit segmentation masks"
            onClicked: ui.setOverlay("masks", !root.masksOn)
        }
        LayerChip {
            objectName: root.prefix + "OverlayTrays"
            visible: root.showTraysPill
            text: "Trays"
            checkedState: root.traysOn
            tooltipText: "Show or hide fitted unit trays"
            onClicked: ui.setOverlay("trays", !root.traysOn)
        }
        LayerChip {
            objectName: root.prefix + "OverlayLabels"
            visible: root.showLabelsPill
            text: "Labels"
            checkedState: root.labelsOn
            tooltipText: "Show or hide unit and terrain name badges"
            onClicked: ui.setOverlay("labels", !root.labelsOn)
        }
        LayerChip {
            objectName: root.prefix + "OverlayTerrain"
            visible: root.showTerrainPill
            text: "Terrain"
            checkedState: root.terrainOn
            tooltipText: "Show or hide saved terrain polygons and labels"
            onClicked: ui.setOverlay("terrain", !root.terrainOn)
        }
    }
}
