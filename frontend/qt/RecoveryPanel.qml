import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: panel
    readonly property Theme theme: Theme {}
    readonly property bool manualReady: Boolean(flow.state.hasCandidate) && !Boolean(flow.state.review)
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
                color: panel.theme.modeRecoveryDot
            }
            Text {
                text: "Recover unit IDs"
                color: panel.theme.ink
                font.family: panel.theme.fontDisplay
                font.pixelSize: panel.theme.textLg
                font.weight: Font.DemiBold
                Layout.fillWidth: true
            }
        }

        Text {
            text: panel.manualReady
                  ? "Candidate ready · click a unit ID or drag it onto the yellow mask to confirm."
                  : "Draw a candidate with Points, Rectangle, or Four corners, or click a Review unit."
            color: panel.manualReady ? panel.theme.selection : panel.theme.inkMuted
            font.pixelSize: panel.theme.textXs
            font.weight: panel.manualReady ? Font.DemiBold : Font.Normal
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
                    model: flow.recoveryRows
                    Rectangle {
                        id: row
                        required property var modelData
                        readonly property bool isA: modelData.side === "A"
                        readonly property bool isReviewing: flow.state.reviewUnitId === modelData.id
                        readonly property bool isTarget: flow.state.targetUnitId === modelData.id
                        readonly property color sideColor: isA ? panel.theme.sideA : panel.theme.sideB
                        readonly property color sideSoft: isA ? panel.theme.sideASoft : panel.theme.sideBSoft
                        width: parent.width
                        height: Math.max(54, textCol.implicitHeight + 16)
                        radius: panel.theme.radiusMd
                        color: (pointer.containsMouse || isReviewing || isTarget) ? sideSoft : panel.theme.bgSubtle
                        border.width: (isReviewing || isTarget) ? 1.5 : 1
                        border.color: isReviewing ? panel.theme.warning
                                    : (pointer.containsMouse || isTarget) ? sideColor : panel.theme.border
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
                                width: 22; height: 22; radius: panel.theme.radiusSm
                                color: row.sideColor
                                Text {
                                    anchors.centerIn: parent
                                    text: row.modelData.side
                                    color: "#ffffff"
                                    font.pixelSize: panel.theme.textXs
                                    font.weight: Font.DemiBold
                                }
                            }

                            ColumnLayout {
                                id: textCol
                                Layout.fillWidth: true
                                spacing: 2
                                Text {
                                    text: row.modelData.id
                                    color: panel.theme.ink
                                    font.pixelSize: panel.theme.textMd
                                    font.weight: Font.DemiBold
                                }
                                Text {
                                    text: row.modelData.name || ""
                                    color: panel.theme.inkSecondary
                                    font.pixelSize: panel.theme.textXs
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                                Text {
                                    visible: (row.modelData.subtitle || "").length > 0 && row.modelData.subtitle !== row.modelData.name
                                    text: row.modelData.subtitle || ""
                                    color: panel.theme.inkMuted
                                    font.pixelSize: 10
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                            }

                            Rectangle {
                                visible: row.modelData.status === "review" || row.isTarget || row.modelData.status === "failed"
                                implicitWidth: badgeTxt.implicitWidth + 12
                                implicitHeight: 20
                                radius: height / 2
                                color: row.modelData.status === "review" ? panel.theme.warningSoft
                                     : row.isTarget ? panel.theme.accentSoft
                                     : panel.theme.dangerSoft
                                border.color: row.modelData.status === "review" ? panel.theme.warningBorder
                                            : row.isTarget ? panel.theme.accentBorder
                                            : panel.theme.dangerBorder
                                Text {
                                    id: badgeTxt
                                    anchors.centerIn: parent
                                    text: row.modelData.status === "review" ? "Review"
                                        : row.isTarget ? (panel.manualReady ? "Confirm" : "Target")
                                        : "Missing"
                                    color: row.modelData.status === "review" ? panel.theme.warning
                                         : row.isTarget ? panel.theme.selection
                                         : panel.theme.modeRecovery
                                    font.pixelSize: panel.theme.textXs
                                    font.weight: Font.DemiBold
                                }
                            }
                        }

                        MouseArea {
                            id: pointer
                            property real grabX: 10
                            property real grabY: 10
                            anchors.fill: parent
                            hoverEnabled: true
                            preventStealing: true
                            enabled: !flow.state.busy
                            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                            drag.target: ghost
                            drag.threshold: 8
                            onPressed: {
                                grabX = mouseX
                                grabY = mouseY
                                ghost.candidateGeneration = flow.state.candidateGeneration
                                const p = row.mapToItem(Overlay.overlay, mouseX, mouseY)
                                ghost.x = p.x - grabX
                                ghost.y = p.y - grabY
                            }
                            onClicked: flow.selectCandidate(row.modelData.id)
                            onReleased: {
                                ghost.Drag.drop()
                                flow.clearRecoveryHover()
                            }
                            onCanceled: flow.clearRecoveryHover()
                        }

                        Rectangle {
                            id: ghost
                            parent: Overlay.overlay
                            width: 156
                            height: 38
                            z: 100
                            radius: panel.theme.radiusMd
                            color: row.sideColor
                            opacity: 0.88
                            border.color: "#ffffff"
                            border.width: 1
                            visible: pointer.drag.active
                            property string unitId: row.modelData.id
                            property int candidateGeneration: 0
                            Drag.active: pointer.drag.active
                            Drag.keys: ["unit-recovery"]
                            Drag.hotSpot.x: pointer.grabX
                            Drag.hotSpot.y: pointer.grabY

                            Text {
                                anchors.centerIn: parent
                                text: "Confirm " + ghost.unitId
                                color: "#ffffff"
                                font.pixelSize: panel.theme.textSm
                                font.weight: Font.DemiBold
                            }
                        }
                    }
                }

                Text {
                    width: parent.width
                    visible: flow.recoveryRows.length === 0
                    text: "No failed units listed. Select a unit on the board and use Correct to report a tracking error."
                    color: panel.theme.inkMuted
                    font.pixelSize: panel.theme.textXs
                    wrapMode: Text.WordWrap
                }
            }
        }
    }
}
