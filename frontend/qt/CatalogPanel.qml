import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: panel
    required property var state
    required property Item dragLayer
    signal importRequested(string side)
    readonly property Theme theme: Theme {}
    readonly property var unassignedList: state.unassigned || []
    readonly property var unconfirmedList: state.unconfirmed || []
    readonly property bool allReady: state.total > 0 && state.assigned === state.total && unconfirmedList.length === 0

    radius: theme.radiusLg
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
                font.pixelSize: panel.theme.textLg
                font.weight: Font.DemiBold
                Layout.fillWidth: true
            }
            Rectangle {
                implicitWidth: countBadge.implicitWidth + 14
                implicitHeight: 22
                radius: height / 2
                color: panel.allReady ? panel.theme.successSoft : panel.theme.bgTrack
                border.color: panel.allReady ? panel.theme.successBorder
                              : (panel.unconfirmedList.length > 0 ? panel.theme.warning : panel.theme.borderSoft)
                Text {
                    id: countBadge
                    anchors.centerIn: parent
                    text: panel.state.assigned + " / " + panel.state.total
                    color: panel.allReady ? panel.theme.success
                           : (panel.unconfirmedList.length > 0 ? panel.theme.warning : panel.theme.inkSecondary)
                    font.family: panel.theme.fontMono
                    font.pixelSize: panel.theme.textXs
                    font.weight: Font.DemiBold
                }
            }
        }

        Text {
            text: "Select a mask, then click or drag a type onto it."
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
                                    height: Math.max(48, cardTextCol.implicitHeight + 12)
                                    radius: panel.theme.radiusSm
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

                                    Column {
                                        id: cardTextCol
                                        anchors.verticalCenter: parent.verticalCenter
                                        anchors.left: parent.left
                                        anchors.right: parent.right
                                        anchors.leftMargin: 10
                                        anchors.rightMargin: 8
                                        spacing: 2

                                        Text {
                                            width: parent.width
                                            text: card.modelData.title
                                            color: panel.theme.ink
                                            font.pixelSize: panel.theme.textXs
                                            font.weight: Font.DemiBold
                                            wrapMode: Text.WordWrap
                                            maximumLineCount: 2
                                            elide: Text.ElideRight
                                        }

                                        Text {
                                            width: parent.width
                                            visible: (card.modelData.subtitle || "").length > 0
                                            text: card.modelData.subtitle || ""
                                            color: panel.theme.inkSecondary
                                            font.pixelSize: 10
                                            wrapMode: Text.WordWrap
                                            maximumLineCount: 2
                                            elide: Text.ElideRight
                                        }
                                    }

                                    MouseArea {
                                        id: pointer
                                        property real grabX: 10
                                        property real grabY: 10
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        preventStealing: true
                                        enabled: panel.state.ready && panel.state.editable
                                        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                                        drag.target: ghost
                                        drag.threshold: 8
                                        onPressed: {
                                            grabX = mouseX
                                            grabY = mouseY
                                            const p = card.mapToItem(panel.dragLayer, mouseX, mouseY)
                                            ghost.x = p.x - grabX
                                            ghost.y = p.y - grabY
                                        }
                                        onReleased: {
                                            ghost.Drag.drop()
                                            ui.clearHover()
                                        }
                                        onCanceled: ui.clearHover()
                                        onClicked: ui.assign(card.modelData.id)
                                    }

                                    Rectangle {
                                        id: ghost
                                        parent: panel.dragLayer
                                        width: card.width
                                        height: card.height
                                        radius: panel.theme.radiusSm
                                        z: 100
                                        visible: pointer.drag.active
                                        color: sideColumn.sideColor
                                        opacity: 0.84
                                        border.color: "#ffffff"
                                        border.width: 1
                                        property string typeId: card.modelData.id
                                        Drag.active: pointer.drag.active
                                        Drag.keys: ["unit-type"]
                                        Drag.hotSpot.x: pointer.grabX
                                        Drag.hotSpot.y: pointer.grabY

                                        Column {
                                            anchors.verticalCenter: parent.verticalCenter
                                            anchors.left: parent.left
                                            anchors.right: parent.right
                                            anchors.margins: 9
                                            spacing: 2

                                            Text {
                                                width: parent.width
                                                text: card.modelData.title
                                                color: "#ffffff"
                                                font.pixelSize: panel.theme.textXs
                                                font.weight: Font.DemiBold
                                                wrapMode: Text.WordWrap
                                                maximumLineCount: 2
                                                elide: Text.ElideRight
                                            }

                                            Text {
                                                width: parent.width
                                                visible: (card.modelData.subtitle || "").length > 0
                                                text: card.modelData.subtitle || ""
                                                color: "#dce8f2"
                                                font.pixelSize: 10
                                                wrapMode: Text.WordWrap
                                                maximumLineCount: 2
                                                elide: Text.ElideRight
                                            }
                                        }

                                        Rectangle {
                                            x: pointer.grabX - 4
                                            y: pointer.grabY - 4
                                            width: 8
                                            height: 8
                                            radius: 4
                                            color: panel.theme.selection
                                            border.color: "#101922"
                                            border.width: 1
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
                                font.pixelSize: panel.theme.textXs
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
            radius: panel.theme.radiusXs
            color: panel.theme.bgTrack
            Rectangle {
                height: parent.height
                radius: panel.theme.radiusXs
                width: panel.state.total > 0 ? parent.width * Math.min(1, panel.state.assigned / panel.state.total) : 0
                color: panel.allReady ? panel.theme.success
                       : (panel.unconfirmedList.length > 0 ? panel.theme.warning : panel.theme.accent)
            }
        }

        // Unassigned or edited unconfirmed masks: click a chip to highlight & select that mask.
        Flickable {
            Layout.fillWidth: true
            Layout.preferredHeight: Math.min(82, pendingFlow.implicitHeight)
            visible: panel.unassignedList.length > 0 || panel.unconfirmedList.length > 0
            contentWidth: width
            contentHeight: pendingFlow.implicitHeight
            clip: true
            boundsBehavior: Flickable.StopAtBounds

            Flow {
                id: pendingFlow
                width: parent.width
                spacing: 6

                Text {
                    visible: panel.unassignedList.length > 0
                    text: "Unassigned:"
                    color: panel.theme.warning
                    font.pixelSize: panel.theme.textXs
                    font.weight: Font.DemiBold
                    height: 24
                    verticalAlignment: Text.AlignVCenter
                }
                Repeater {
                    model: panel.unassignedList
                    delegate: Rectangle {
                        required property var modelData
                        width: chipText.implicitWidth + 14
                        height: 24
                        radius: panel.theme.radiusSm
                        color: modelData.id === panel.state.selected ? panel.theme.accentSoft : panel.theme.bgSubtle
                        border.color: modelData.id === panel.state.selected ? panel.theme.accentBorder : panel.theme.warning
                        Text {
                            id: chipText
                            anchors.centerIn: parent
                            text: modelData.label
                            color: panel.theme.ink
                            font.family: panel.theme.fontMono
                            font.pixelSize: panel.theme.textXs
                        }
                        MouseArea {
                            anchors.fill: parent
                            enabled: panel.state.editable
                            cursorShape: Qt.PointingHandCursor
                            onClicked: ui.selectMask(modelData.id)
                        }
                    }
                }

                Text {
                    visible: panel.unconfirmedList.length > 0
                    text: "Re-confirm:"
                    color: panel.theme.warning
                    font.pixelSize: panel.theme.textXs
                    font.weight: Font.DemiBold
                    height: 24
                    verticalAlignment: Text.AlignVCenter
                }
                Repeater {
                    model: panel.unconfirmedList
                    delegate: Rectangle {
                        required property var modelData
                        width: confText.implicitWidth + 14
                        height: 24
                        radius: panel.theme.radiusSm
                        color: modelData.id === panel.state.selected ? panel.theme.accentSoft : panel.theme.bgSubtle
                        border.color: modelData.id === panel.state.selected ? panel.theme.accentBorder : panel.theme.warning
                        Text {
                            id: confText
                            anchors.centerIn: parent
                            text: modelData.label
                            color: panel.theme.ink
                            font.family: panel.theme.fontMono
                            font.pixelSize: panel.theme.textXs
                        }
                        MouseArea {
                            anchors.fill: parent
                            enabled: panel.state.editable
                            cursorShape: Qt.PointingHandCursor
                            onClicked: ui.selectMask(modelData.id)
                        }
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            Rectangle {
                implicitWidth: selText.implicitWidth + 16
                implicitHeight: 28
                radius: panel.theme.radiusSm
                color: panel.state.hasSelection ? panel.theme.accentSoft : panel.theme.bgSubtle
                border.color: panel.state.hasSelection ? panel.theme.accentBorder : panel.theme.border
                Layout.fillWidth: true
                Text {
                    id: selText
                    anchors.centerIn: parent
                    width: parent.width - 14
                    elide: Text.ElideRight
                    horizontalAlignment: Text.AlignHCenter
                    text: panel.state.selectedLabel
                    color: panel.state.hasSelection ? panel.theme.selection : panel.theme.inkMuted
                    font.pixelSize: panel.theme.textSm
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
