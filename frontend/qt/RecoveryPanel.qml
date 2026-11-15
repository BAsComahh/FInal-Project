import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: panel
    radius: 10; color: "white"
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 12
        Label { text: "Existing unit IDs · A / B"; font.bold: true }
        ScrollView {
            Layout.fillWidth: true; Layout.fillHeight: true; contentWidth: availableWidth
            Column {
                width: parent.width; spacing: 8
                Repeater {
                    model: flow.state.rows
                    Rectangle {
                        id: row
                        required property var modelData
                        width: parent.width; height: 42; radius: 5; color: "#eef3f7"
                        Label { anchors.centerIn: parent; text: row.modelData.side + " · " + row.modelData.id }
                        MouseArea {
                            id: pointer
                            anchors.fill: parent; enabled: !flow.state.busy
                            drag.target: ghost; drag.threshold: 8
                            onPressed: {
                                ghost.candidateGeneration = flow.state.candidateGeneration
                                const p = row.mapToItem(Overlay.overlay, mouseX, mouseY)
                                ghost.x = p.x - 10; ghost.y = p.y - 10
                            }
                            onClicked: flow.selectCandidate(row.modelData.id)
                            onReleased: ghost.Drag.drop()
                        }
                        Rectangle {
                            id: ghost
                            parent: Overlay.overlay
                            width: 120; height: 38; z: 100; radius: 5; color: "#ba5934"
                            visible: pointer.drag.active
                            property string unitId: row.modelData.id
                            property int candidateGeneration: 0
                            Drag.active: pointer.drag.active; Drag.keys: ["unit-recovery"]
                            Drag.hotSpot.x: 10; Drag.hotSpot.y: 10
                            Label { anchors.centerIn: parent; text: ghost.unitId; color: "white" }
                        }
                    }
                }
            }
        }
    }
}
