import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: panel
    required property var state
    required property Item dragLayer
    signal importRequested(string side)
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
            Text {
                text: "Assign a type"
                color: panel.theme.ink
                font.family: panel.theme.fontDisplay
                font.pixelSize: 17
                font.weight: Font.DemiBold
                Layout.fillWidth: true
            }
            Rectangle {
                implicitWidth: countBadge.implicitWidth + 14
                implicitHeight: 22
                radius: 11
                color: panel.state.assigned > 0 && panel.state.assigned === panel.state.total
                       ? panel.theme.successSoft : panel.theme.bgTrack
                Text {
                    id: countBadge
                    anchors.centerIn: parent
                    text: panel.state.assigned + " / " + panel.state.total
                    color: panel.state.assigned > 0 && panel.state.assigned === panel.state.total
                           ? panel.theme.success : panel.theme.inkSecondary
                    font.family: panel.theme.fontMono
                    font.pixelSize: 11
                    font.weight: Font.DemiBold
                }
            }
        }

        Text {
            text: "Select a mask, then click or drag a type onto it."
            color: panel.theme.inkMuted
            font.pixelSize: 11
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
                    readonly property color sideBorder: isA ? panel.theme.sideABorder : panel.theme.sideBBorder
                    readonly property var listModel: {
                        if (typeof ui !== "undefined" && ui.catalogA !== undefined) {
                            return isA ? ui.catalogA : ui.catalogB
                        }
                        return isA ? panel.state.typesA : panel.state.typesB
                    }

                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.preferredWidth: 1
                    Layout.minimumWidth: 0
                    spacing: 8

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 6
                        Rectangle {
                            width: 22; height: 22; radius: 6
                            color: sideColumn.sideColor
                            Text {
                                anchors.centerIn: parent
                                text: sideColumn.side
                                color: "white"
                                font.pixelSize: 11
                                font.weight: Font.DemiBold
                            }
                        }
                        Text {
                            text: "List " + sideColumn.side
                            color: panel.theme.inkSecondary
                            font.pixelSize: 12
                            font.weight: Font.DemiBold
                            Layout.fillWidth: true
                        }
                    }

                    ConsoleButton {
                        objectName: "import" + sideColumn.side
                        text: "Import " + sideColumn.side
                        variant: "subtle"
                        implicitHeight: 30
                        Layout.fillWidth: true
                        enabled: panel.state.editable
                        onClicked: panel.importRequested(sideColumn.side)
                    }

                    ScrollView {
                        Layout.fillHeight: true
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        contentWidth: availableWidth
                        clip: true
                        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                        Column {
                            width: parent.width
                            spacing: 6

                            Repeater {
                                model: panel.visible ? sideColumn.listModel : 0
                                delegate: Rectangle {
                                    id: card
                                    required property var modelData
                                    width: parent.width
                                    height: 48
                                    radius: 6
                                    color: pointer.containsMouse ? sideColumn.sideSoft : panel.theme.bgSubtle
                                    border.color: pointer.containsMouse ? sideColumn.sideColor : panel.theme.border
                                    opacity: panel.state.ready && panel.state.editable ? 1 : 0.52
                                    clip: true

                                    Rectangle {
                                        width: 3
                                        height: parent.height
                                        anchors.left: parent.left
                                        color: sideColumn.sideColor
                                    }

                                    Text {
                                        anchors.fill: parent
                                        anchors.leftMargin: 10
                                        anchors.rightMargin: 8
                                        anchors.topMargin: 6
                                        anchors.bottomMargin: 6
                                        text: card.modelData.title
                                        color: panel.theme.ink
                                        font.pixelSize: 11
                                        wrapMode: Text.WordWrap
                                        maximumLineCount: 2
                                        verticalAlignment: Text.AlignVCenter
                                        elide: Text.ElideRight
                                    }

                                    MouseArea {
                                        id: pointer
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        enabled: panel.state.ready && panel.state.editable
                                        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                                        drag.target: ghost
                                        drag.threshold: 8
                                        onPressed: {
                                            const p = card.mapToItem(panel.dragLayer, mouseX, mouseY)
                                            ghost.x = p.x - 10
                                            ghost.y = p.y - 10
                                        }
                                        onReleased: ghost.Drag.drop()
                                        onClicked: ui.assign(card.modelData.id)
                                    }

                                    Rectangle {
                                        id: ghost
                                        parent: panel.dragLayer
                                        width: card.width
                                        height: 48
                                        radius: 6
                                        z: 100
                                        visible: pointer.drag.active
                                        color: sideColumn.sideColor
                                        opacity: 0.94
                                        border.color: "white"
                                        border.width: 1
                                        property string typeId: card.modelData.id
                                        Drag.active: pointer.drag.active
                                        Drag.keys: ["unit-type"]
                                        Drag.hotSpot.x: 10
                                        Drag.hotSpot.y: 10

                                        Text {
                                            anchors.fill: parent
                                            anchors.margins: 9
                                            text: card.modelData.title
                                            color: "white"
                                            font.pixelSize: 11
                                            font.weight: Font.DemiBold
                                            wrapMode: Text.WordWrap
                                            maximumLineCount: 2
                                            verticalAlignment: Text.AlignVCenter
                                            elide: Text.ElideRight
                                        }
                                    }
                                }
                            }

                            Text {
                                width: parent.width
                                visible: sideColumn.listModel.length === 0
                                text: "Import a PDF or JSON list."
                                color: panel.theme.inkMuted
                                wrapMode: Text.WordWrap
                                font.pixelSize: 11
                            }
                        }
                    }
                }
            }
        }

        Rectangle { Layout.fillWidth: true; height: 1; color: panel.theme.borderSoft }

        // Progress bar for assigned masks
        Rectangle {
            Layout.fillWidth: true
            height: 5
            radius: 3
            color: panel.theme.bgTrack
            Rectangle {
                height: parent.height
                radius: 3
                width: panel.state.total > 0 ? parent.width * Math.min(1, panel.state.assigned / panel.state.total) : 0
                color: panel.state.assigned > 0 && panel.state.assigned === panel.state.total
                       ? panel.theme.success : panel.theme.accent
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            Rectangle {
                implicitWidth: selText.implicitWidth + 16
                implicitHeight: 28
                radius: 7
                color: panel.state.hasSelection ? panel.theme.accentSoft : panel.theme.bgSubtle
                border.color: panel.state.hasSelection ? panel.theme.accentBorder : panel.theme.borderSoft
                Layout.fillWidth: true
                Text {
                    id: selText
                    anchors.centerIn: parent
                    width: parent.width - 14
                    elide: Text.ElideRight
                    horizontalAlignment: Text.AlignHCenter
                    text: panel.state.selectedLabel
                    color: panel.state.hasSelection ? panel.theme.accent : panel.theme.inkMuted
                    font.pixelSize: 12
                    font.weight: Font.DemiBold
                }
            }
            ConsoleButton {
                text: "Unbind"
                variant: "dangerSubtle"
                implicitHeight: 28
                enabled: panel.state.editable && panel.state.hasSelection
                onClicked: ui.unbind()
            }
        }
    }
}
