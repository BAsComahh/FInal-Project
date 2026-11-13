import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: panel
    objectName: "liveConsole"
    required property var viewData
    property real drawerHeight: 220
    readonly property bool drawerOpen: viewData.tool === "los" || viewData.tool === "move"
    color: "white"
    implicitHeight: bar.implicitHeight + (drawerOpen ? drawerHeight : 0)
    ColumnLayout {
        anchors.fill: parent; spacing: 0
        Rectangle {
            id: bar
            Layout.fillWidth: true; implicitHeight: Math.max(48, caption.implicitHeight + 20); color: "#f7f9fa"
            RowLayout {
                anchors.fill: parent; anchors.leftMargin: 20; anchors.rightMargin: 20; spacing: 12
                Text {
                    id: caption
                    text: panel.viewData.caption + (panel.viewData.tool === "distance" && panel.viewData.query.reason ? " · " + panel.viewData.query.reason : panel.viewData.selected && !panel.viewData.canQuery ? " · " + panel.viewData.queryBlock : "")
                    color: "#627985"; font.pixelSize: 12; wrapMode: Text.WordWrap; Layout.fillWidth: true
                }
                ConsoleButton { objectName: "doneDistance"; text: "Done"; visible: panel.viewData.tool === "distance"; onClicked: ui.doneTool() }
                ConsoleButton { objectName: "clearSelection"; text: "Clear selection"; visible: panel.viewData.selected; onClicked: ui.clearSelection() }
            }
        }
        Rectangle {
            visible: panel.drawerOpen; Layout.fillWidth: true; Layout.preferredHeight: panel.drawerHeight
            color: "white"
            Rectangle { width: parent.width; height: 1; color: "#d9e3e8" }
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 16; spacing: 7
                RowLayout {
                    Layout.fillWidth: true; spacing: 12
                    ColumnLayout {
                        Layout.fillWidth: true; spacing: 3
                        Text {
                            text: panel.viewData.query.title + " · " + panel.viewData.unitId + (panel.viewData.targetId ? " → " + panel.viewData.targetId : "")
                            color: "#233b49"; font.family: "Bahnschrift"; font.pixelSize: 15; font.weight: Font.DemiBold
                            Layout.fillWidth: true; elide: Text.ElideRight
                        }
                        Text { text: panel.viewData.query.status + " · Observed " + panel.viewData.query.observed; color: "#627985"; font.pixelSize: 11 }
                    }
                    Text { objectName: "queryMetric"; text: panel.viewData.query.metric; color: "#246b89"; font.pixelSize: panel.width < 950 ? 17 : 23 }
                    ConsoleButton { objectName: "doneTool"; text: "Done"; onClicked: ui.doneTool() }
                }
                Flow {
                    visible: panel.viewData.tool === "move"
                    Layout.fillWidth: true; spacing: 6
                    Repeater {
                        model: ui.moveOrders
                        ConsoleButton {
                            required property var modelData
                            objectName: "order_" + modelData.id
                            text: modelData.label; implicitHeight: 30
                            primary: panel.viewData.order === modelData.id
                            onClicked: ui.moveOrder(modelData.id)
                        }
                    }
                }
                ScrollView {
                    Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                    TextArea {
                        objectName: "queryExplanation"
                        text: panel.viewData.query.reason + (panel.viewData.query.warnings.length ? "\n" + panel.viewData.query.warnings.join("\n") : "")
                        readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap
                        color: "#627985"; font.pixelSize: 12; background: null
                    }
                }
            }
        }
    }
}
