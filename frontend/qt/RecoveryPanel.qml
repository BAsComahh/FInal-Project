import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: panel
    readonly property Theme theme: Theme {}
    radius: 10
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
                color: panel.theme.modeRecoveryDot
            }
            Text {
                text: "Recover unit IDs"
                color: panel.theme.ink
                font.family: panel.theme.fontDisplay
                font.pixelSize: 17
                font.weight: Font.DemiBold
                Layout.fillWidth: true
            }
        }

        Text {
            text: "Click a unit to review its auto candidate, or drag an ID onto the yellow mask."
            color: panel.theme.inkMuted
            font.pixelSize: 11
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }

        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentWidth: availableWidth
            clip: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

            Column {
                width: parent.width
                spacing: 8

                Repeater {
                    model: flow.state.rows
                    Rectangle {
                        id: row
                        required property var modelData
                        readonly property bool isA: modelData.side === "A"
                        readonly property color sideColor: isA ? panel.theme.sideA : panel.theme.sideB
                        readonly property color sideSoft: isA ? panel.theme.sideASoft : panel.theme.sideBSoft
                        width: parent.width
                        height: 54
                        radius: 8
                        color: pointer.containsMouse ? sideSoft : panel.theme.bgSubtle
                        border.color: pointer.containsMouse ? sideColor : panel.theme.border
                        opacity: flow.state.busy ? 0.55 : 1.0
                        clip: true

                        Rectangle {
                            width: 3
                            height: parent.height
                            anchors.left: parent.left
                            color: row.sideColor
                        }

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 12
                            anchors.rightMargin: 10
                            spacing: 8

                            Rectangle {
                                width: 22; height: 22; radius: 6
                                color: row.sideColor
                                Text {
                                    anchors.centerIn: parent
                                    text: row.modelData.side
                                    color: "white"
                                    font.pixelSize: 11
                                    font.weight: Font.DemiBold
                                }
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 2
                                Text {
                                    text: row.modelData.id
                                    color: panel.theme.ink
                                    font.pixelSize: 13
                                    font.weight: Font.DemiBold
                                }
                                Text {
                                    text: row.modelData.name || ""
                                    color: panel.theme.inkMuted
                                    font.pixelSize: 11
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                            }

                            Rectangle {
                                visible: row.modelData.status === "review"
                                implicitWidth: badgeTxt.implicitWidth + 10
                                implicitHeight: 20
                                radius: 10
                                color: panel.theme.warningSoft
                                border.color: panel.theme.warningBorder
                                Text {
                                    id: badgeTxt
                                    anchors.centerIn: parent
                                    text: "Review"
                                    color: panel.theme.warning
                                    font.pixelSize: 10
                                    font.weight: Font.DemiBold
                                }
                            }
                        }

                        MouseArea {
                            id: pointer
                            anchors.fill: parent
                            hoverEnabled: true
                            enabled: !flow.state.busy
                            cursorShape: enabled ? Qt.OpenHandCursor : Qt.ArrowCursor
                            drag.target: ghost
                            drag.threshold: 8
                            onPressed: {
                                ghost.candidateGeneration = flow.state.candidateGeneration
                                const p = row.mapToItem(Overlay.overlay, mouseX, mouseY)
                                ghost.x = p.x - 10
                                ghost.y = p.y - 10
                            }
                            onClicked: flow.selectCandidate(row.modelData.id)
                            onReleased: ghost.Drag.drop()
                        }

                        Rectangle {
                            id: ghost
                            parent: Overlay.overlay
                            width: 148
                            height: 38
                            z: 100
                            radius: 8
                            color: row.sideColor
                            border.color: "white"
                            border.width: 1
                            visible: pointer.drag.active
                            property string unitId: row.modelData.id
                            property int candidateGeneration: 0
                            Drag.active: pointer.drag.active
                            Drag.keys: ["unit-recovery"]
                            Drag.hotSpot.x: 10
                            Drag.hotSpot.y: 10

                            Text {
                                anchors.centerIn: parent
                                text: "Confirm " + ghost.unitId
                                color: "white"
                                font.pixelSize: 12
                                font.weight: Font.DemiBold
                            }
                        }
                    }
                }

                Text {
                    width: parent.width
                    visible: flow.state.rows.length === 0
                    text: "No failed units listed. Select a unit on the board and use Correct to report a tracking error."
                    color: panel.theme.inkMuted
                    font.pixelSize: 11
                    wrapMode: Text.WordWrap
                }
            }
        }
    }
}
