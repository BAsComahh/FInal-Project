import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: panel
    required property var viewData
    required property string selectedUnit
    signal inspectRequested(string unitId)
    readonly property Theme theme: Theme {}

    radius: theme.radiusLg
    color: theme.bgSurface
    border.color: theme.border

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 14
        spacing: 10

        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            Rectangle {
                width: 8; height: 8; radius: 4
                color: panel.theme.modeReplayDot
            }
            Text {
                text: "Needs attention"
                color: panel.theme.ink
                font.family: panel.theme.fontDisplay
                font.pixelSize: panel.theme.textLg
                font.weight: Font.DemiBold
                Layout.fillWidth: true
            }
            Rectangle {
                implicitWidth: countTxt.implicitWidth + 12
                implicitHeight: 22
                radius: height / 2
                color: panel.theme.warningSoft
                border.color: panel.theme.warningBorder
                Text {
                    id: countTxt
                    anchors.centerIn: parent
                    text: String(panel.viewData.count)
                    color: panel.theme.warning
                    font.family: panel.theme.fontMono
                    font.pixelSize: panel.theme.textXs
                    font.weight: Font.DemiBold
                }
            }
        }

        Text {
            text: (panel.viewData.showFacing ? "Mask / Facing" : "Mask") + " · Select a unit to inspect on board."
            color: panel.theme.inkMuted
            font.pixelSize: panel.theme.textXs
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 10

            Repeater {
                model: ["A", "B"]
                ColumnLayout {
                    id: sideColumn
                    required property string modelData
                    readonly property string side: modelData
                    readonly property bool isA: side === "A"
                    readonly property color sideColor: isA ? panel.theme.sideA : panel.theme.sideB
                    readonly property color sideSoft: isA ? panel.theme.sideASoft : panel.theme.sideBSoft
                    readonly property var sideRows: isA ? panel.viewData.rowsA : panel.viewData.rowsB

                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.preferredWidth: 1
                    Layout.minimumWidth: 0
                    spacing: 8

                    RowLayout {
                        spacing: 6
                        Rectangle {
                            width: 22; height: 22; radius: panel.theme.radiusSm
                            color: sideColumn.sideColor
                            Text {
                                anchors.centerIn: parent
                                text: sideColumn.side
                                color: "#ffffff"
                                font.pixelSize: panel.theme.textXs
                                font.weight: Font.DemiBold
                            }
                        }
                        Text {
                            text: "List " + sideColumn.side
                            color: panel.theme.inkSecondary
                            font.pixelSize: panel.theme.textSm
                            font.weight: Font.DemiBold
                        }
                    }

                    ScrollView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.minimumWidth: 0
                        clip: true
                        contentWidth: availableWidth
                        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                        Column {
                            width: parent.width
                            spacing: 7

                            Repeater {
                                model: sideColumn.sideRows
                                Button {
                                    id: unitButton
                                    required property var modelData
                                    objectName: "inspect_" + modelData.unitId
                                    width: parent.width
                                    implicitHeight: entry.implicitHeight + 18
                                    onClicked: panel.inspectRequested(modelData.unitId)
                                    ToolTip.visible: hovered
                                    ToolTip.text: modelData.name

                                    background: Rectangle {
                                        radius: panel.theme.radiusMd
                                        color: panel.selectedUnit === unitButton.modelData.unitId
                                               ? sideColumn.sideSoft
                                               : unitButton.hovered ? panel.theme.bgElevated : panel.theme.bgSubtle
                                        border.color: panel.selectedUnit === unitButton.modelData.unitId
                                                      ? sideColumn.sideColor
                                                      : unitButton.hovered ? panel.theme.borderStrong : panel.theme.border
                                        clip: true
                                        Rectangle {
                                            width: 3
                                            height: parent.height
                                            anchors.left: parent.left
                                            color: sideColumn.sideColor
                                        }
                                    }

                                    contentItem: Column {
                                        id: entry
                                        leftPadding: 6
                                        spacing: 3
                                        Text {
                                            text: unitButton.modelData.unitId
                                            color: panel.theme.ink
                                            font.pixelSize: panel.theme.textSm
                                            font.weight: Font.DemiBold
                                        }
                                        Text {
                                            width: parent.width - 6
                                            visible: (unitButton.modelData.name || "").length > 0
                                            text: unitButton.modelData.name || ""
                                            color: panel.theme.inkMuted
                                            font.pixelSize: panel.theme.textXs
                                            elide: Text.ElideRight
                                        }
                                        Text {
                                            width: parent.width - 6
                                            text: unitButton.modelData.details
                                            color: panel.theme.warning
                                            font.pixelSize: panel.theme.textXs
                                            wrapMode: Text.WordWrap
                                        }
                                    }
                                }
                            }

                            Text {
                                width: parent.width
                                visible: sideColumn.sideRows.length === 0
                                text: "No issues"
                                color: panel.theme.inkMuted
                                font.pixelSize: panel.theme.textXs
                            }
                        }
                    }
                }
            }
        }

        ConsoleButton {
            visible: typeof flow !== "undefined"
            text: "Open recovery"
            variant: "subtle"
            implicitHeight: 30
            Layout.fillWidth: true
            onClicked: flow.open("recover")
        }
    }
}
