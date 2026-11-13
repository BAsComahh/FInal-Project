import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: panel
    required property var viewData
    required property string selectedUnit
    signal inspectRequested(string unitId)
    radius: 10; color: "white"; border.color: "#dbe4ea"
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 16; spacing: 12
        Text { text: "Needs attention"; color: "#203d50"; font.pixelSize: 18; font.weight: Font.DemiBold }
        Text { text: "Mask / Facing · " + panel.viewData.count + " units\nSelect a unit to inspect."; color: "#647b8b"; font.pixelSize: 12 }
        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: 10
            Repeater {
                model: ["A", "B"]
                ColumnLayout {
                    id: sideColumn
                    required property string modelData
                    property string side: modelData
                    Layout.fillWidth: true; Layout.fillHeight: true; Layout.preferredWidth: 1; Layout.minimumWidth: 0; spacing: 10
                    RowLayout {
                        Rectangle {
                            width: 23; height: 23; radius: 6
                            color: sideColumn.side === "A" ? "#2d709e" : "#b65b65"
                            Text { anchors.centerIn: parent; text: sideColumn.side; color: "white"; font.weight: Font.DemiBold }
                        }
                        Text { text: "List " + sideColumn.side; color: "#647b8b"; font.pixelSize: 11 }
                    }
                    ScrollView {
                        Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumWidth: 0; clip: true
                        contentWidth: availableWidth
                        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                        Column {
                            width: parent.width; spacing: 8
                            Repeater {
                                model: sideColumn.side === "A" ? panel.viewData.rowsA : panel.viewData.rowsB
                                Button {
                                    id: unitButton
                                    required property var modelData
                                    objectName: "inspect_" + modelData.unitId
                                    width: parent.width; implicitHeight: entry.implicitHeight + 22
                                    onClicked: panel.inspectRequested(modelData.unitId)
                                    background: Rectangle {
                                        radius: 7
                                        color: panel.selectedUnit === unitButton.modelData.unitId ? "#e8f2f8" : unitButton.hovered ? "#edf4f8" : "#f4f7f9"
                                        border.color: panel.selectedUnit === unitButton.modelData.unitId ? "#76a4c3" : "#e2e9ee"
                                    }
                                    contentItem: Column {
                                        id: entry
                                        spacing: 6
                                        Text { text: unitButton.modelData.unitId; color: "#294657"; font.weight: Font.DemiBold }
                                        Text { width: parent.width; text: unitButton.modelData.details; color: "#8e6718"; font.pixelSize: 11; wrapMode: Text.WordWrap }
                                    }
                                    ToolTip.visible: hovered
                                    ToolTip.text: modelData.name
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
