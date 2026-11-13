import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: panel
    required property var state
    required property Item dragLayer
    signal importRequested(string side)
    radius: 10; color: "white"; border.color: "#dbe4ea"

    ColumnLayout {
        anchors.fill: parent; anchors.margins: 16; spacing: 12
        Text { text: "Assign a type"; color: "#203d50"; font.pixelSize: 18; font.weight: Font.DemiBold }
        Text {
            text: "Select a mask, then a type.\nOr drag a type onto a mask."
            color: "#647b8b"; lineHeight: 1.25
        }
        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: 10
            Repeater {
                model: ["A", "B"]
                ColumnLayout {
                    id: sideColumn
                    required property string modelData
                    property string side: modelData
                    Layout.fillWidth: true; Layout.fillHeight: true; Layout.preferredWidth: 1; spacing: 8
                    ConsoleButton {
                        objectName: "import" + sideColumn.side
                        text: "Import " + sideColumn.side; Layout.fillWidth: true
                        enabled: panel.state.editable
                        onClicked: panel.importRequested(sideColumn.side)
                    }
                    ScrollView {
                        Layout.fillHeight: true; Layout.fillWidth: true
                        contentWidth: availableWidth
                        clip: true
                        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                        Column {
                            width: parent.width; spacing: 6
                            Repeater {
                                model: panel.visible ? (sideColumn.side === "A" ? panel.state.typesA : panel.state.typesB) : 0
                                delegate: Rectangle {
                                    id: card
                                    required property var modelData
                                    width: parent.width; height: 48; radius: 5
                                    color: pointer.containsMouse ? "#eaf3f9" : "#f4f7f9"
                                    border.color: pointer.containsMouse ? "#76a4c3" : "#e2e9ee"
                                    opacity: panel.state.ready && panel.state.editable ? 1 : 0.55
                                    Text {
                                        anchors.fill: parent; anchors.margins: 9
                                        text: card.modelData.title; color: "#294657"; font.pixelSize: 11
                                        wrapMode: Text.WordWrap; maximumLineCount: 2
                                        verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight
                                    }
                                    MouseArea {
                                        id: pointer
                                        anchors.fill: parent; hoverEnabled: true
                                        enabled: panel.state.ready && panel.state.editable
                                        drag.target: ghost; drag.threshold: 8
                                        onPressed: {
                                            const p = card.mapToItem(panel.dragLayer, mouseX, mouseY)
                                            ghost.x = p.x - 10; ghost.y = p.y - 10
                                        }
                                        onReleased: ghost.Drag.drop()
                                        onClicked: ui.assign(card.modelData.id)
                                    }
                                    Rectangle {
                                        id: ghost
                                        parent: panel.dragLayer
                                        width: card.width; height: card.height; radius: 5; z: 100
                                        visible: pointer.drag.active; color: "#29658f"; opacity: 0.9
                                        property string typeId: card.modelData.id
                                        Drag.active: pointer.drag.active
                                        Drag.keys: ["unit-type"]
                                        Drag.hotSpot.x: 10; Drag.hotSpot.y: 10
                                        Text {
                                            anchors.fill: parent; anchors.margins: 9
                                            text: card.modelData.title; color: "white"; font.pixelSize: 11
                                            wrapMode: Text.WordWrap; maximumLineCount: 2
                                            verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight
                                        }
                                    }
                                }
                            }
                            Text {
                                width: parent.width; visible: (sideColumn.side === "A" ? panel.state.typesA : panel.state.typesB).length === 0
                                text: "Import a PDF or JSON list."; color: "#78909e"
                                wrapMode: Text.WordWrap; font.pixelSize: 11
                            }
                        }
                    }
                }
            }
        }
        Rectangle { Layout.fillWidth: true; height: 1; color: "#e5ebef" }
        Text { text: panel.state.assigned + " / " + panel.state.total + " masks assigned"; color: "#456477"; font.weight: Font.DemiBold }
        Text { text: panel.state.selectedLabel; color: "#647b8b" }
        ConsoleButton { text: "Unbind"; enabled: panel.state.editable && panel.state.hasSelection; onClicked: ui.unbind() }
    }
}
