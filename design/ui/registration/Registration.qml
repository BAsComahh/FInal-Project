import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: window
    width: 1140; height: 780
    minimumWidth: 820; minimumHeight: 600
    visible: true
    title: "Unit registration · Qt preview"
    color: "#edf2f5"
    font.family: "Segoe UI"
    font.pixelSize: 13
    property var draft: preview.state

    component Action: Button {
        id: control
        property bool primary: false
        implicitHeight: 36
        leftPadding: 15; rightPadding: 15
        background: Rectangle {
            radius: 7
            color: control.primary ? (control.hovered ? "#204f76" : "#29658f") : (control.hovered ? "#e7eef3" : "white")
            border.color: control.primary ? "#29658f" : "#cdd9e1"
            opacity: control.enabled ? 1 : 0.45
        }
        contentItem: Text {
            text: control.text
            color: control.primary ? "white" : "#294354"
            font: control.font
            horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
            opacity: control.enabled ? 1 : 0.45
        }
    }

    ColumnLayout {
        anchors.fill: parent; spacing: 0
        Rectangle {
            Layout.fillWidth: true; implicitHeight: 84; color: "white"
            RowLayout {
                anchors.fill: parent; anchors.margins: 22; spacing: 12
                Column {
                    spacing: 3
                    Text { text: "REGISTER UNITS"; color: "#5e7788"; font.pixelSize: 10; font.letterSpacing: 1.6; font.weight: Font.DemiBold }
                    Text { text: "Build the starting board"; color: "#193445"; font.pixelSize: 23; font.weight: Font.DemiBold }
                }
                Item { Layout.fillWidth: true }
                Action { text: "Undo"; enabled: draft.undo && !draft.locked; onClicked: preview.undo() }
                Action { text: "Reset draft"; onClicked: preview.reset() }
                Action { text: draft.locked ? "Preview finished" : "Finish preview"; primary: true; enabled: !draft.locked; onClicked: preview.finish() }
            }
        }

        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true
            Layout.margins: 20; spacing: 16
            ColumnLayout {
                Layout.fillWidth: true; Layout.fillHeight: true; spacing: 12
                RowLayout {
                    spacing: 7
                    Action { text: "Assign type"; primary: draft.mode === "Assign"; enabled: !draft.locked; onClicked: preview.setMode("Assign") }
                    Action { text: "Point prompts"; primary: draft.mode === "Points"; enabled: !draft.locked; onClicked: preview.setMode("Points") }
                    Item { Layout.fillWidth: true }
                    Text { text: "SAVED MASKS"; color: "#607888"; font.pixelSize: 10; font.letterSpacing: 1.1 }
                }
                Rectangle {
                    Layout.fillWidth: true; Layout.fillHeight: true
                    color: "#dae3e9"; radius: 10; clip: true
                    Image { id: board; anchors.fill: parent; source: "image://board/frame"; fillMode: Image.PreserveAspectFit; smooth: true }
                    Item {
                        id: imageArea
                        objectName: "boardSurface"
                        width: board.paintedWidth; height: board.paintedHeight; anchors.centerIn: parent
                        property real scaleX: width / draft.width
                        property real scaleY: height / draft.height
                        Repeater {
                            model: draft.objects
                            Rectangle {
                                required property var modelData
                                x: modelData.x * imageArea.scaleX - 3; y: modelData.y * imageArea.scaleY - 3
                                width: modelData.w * imageArea.scaleX + 6; height: modelData.h * imageArea.scaleY + 6
                                color: "transparent"; radius: 2
                                border.width: draft.selected === modelData.index ? 2 : 0; border.color: "white"
                                Rectangle {
                                    anchors.fill: parent; anchors.margins: -3; color: "transparent"; radius: 3
                                    visible: draft.selected === modelData.index; border.width: 2; border.color: "#2c739e"
                                }
                                Rectangle {
                                    x: -1; y: -23; width: label.implicitWidth + 12; height: 21; radius: 4
                                    color: draft.selected === modelData.index ? "#225c84" : "#cc243c4b"
                                    Text { id: label; anchors.centerIn: parent; text: modelData.label; color: "white"; font.pixelSize: 11; font.weight: Font.DemiBold }
                                }
                            }
                        }
                        Repeater {
                            model: draft.points
                            Rectangle {
                                required property var modelData
                                x: modelData.x * imageArea.scaleX - 8; y: modelData.y * imageArea.scaleY - 8
                                width: 16; height: 16; radius: 8
                                color: modelData.positive ? "#197b60" : "#b64252"; border.width: 2; border.color: "white"
                                Text { anchors.centerIn: parent; text: modelData.positive ? "+" : "−"; color: "white"; font.pixelSize: 12; font.bold: true }
                            }
                        }
                        MouseArea {
                            anchors.fill: parent; acceptedButtons: Qt.LeftButton | Qt.RightButton
                            enabled: !draft.locked
                            cursorShape: draft.mode === "Points" ? Qt.CrossCursor : Qt.PointingHandCursor
                            onClicked: mouse => preview.click(mouse.x / imageArea.scaleX, mouse.y / imageArea.scaleY, mouse.button === Qt.LeftButton)
                        }
                    }
                }
                Text { text: draft.note; color: "#405d70"; Layout.fillWidth: true; wrapMode: Text.WordWrap; Layout.minimumHeight: 36 }
            }

            Rectangle {
                Layout.preferredWidth: 300; Layout.fillHeight: true
                radius: 10; color: "white"; border.color: "#dbe4ea"
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 18; spacing: 12
                    Text { text: "Assign a type"; color: "#203d50"; font.pixelSize: 18; font.weight: Font.DemiBold }
                    Text { text: "Select a mask on the board,\nthen choose its type."; color: "#647b8b"; lineHeight: 1.25 }
                    RowLayout {
                        Layout.fillWidth: true; spacing: 10
                        Repeater {
                            model: ["A", "B"]
                            ColumnLayout {
                                required property string modelData
                                id: sideColumn
                                property string side: modelData
                                property color accent: side === "A" ? "#2d709e" : "#b65b65"
                                Layout.fillWidth: true; spacing: 8
                                RowLayout {
                                    Rectangle { width: 23; height: 23; radius: 6; color: sideColumn.accent
                                        Text { anchors.centerIn: parent; text: sideColumn.side; color: "white"; font.weight: Font.DemiBold } }
                                    Text { text: "Sample list"; color: "#78909e"; font.pixelSize: 10 }
                                }
                                Repeater {
                                    model: draft.types
                                    Button {
                                        id: typeButton
                                        objectName: "type" + sideColumn.side + index
                                        required property var modelData
                                        required property int index
                                        Layout.fillWidth: true; implicitHeight: 68
                                        enabled: !draft.locked && draft.selected >= 0
                                        onClicked: preview.assign(sideColumn.side, index)
                                        background: Rectangle {
                                            radius: 7; color: typeButton.hovered ? "#eaf3f9" : "#f4f7f9"
                                            border.color: typeButton.hovered ? sideColumn.accent : "#e2e9ee"
                                        }
                                        contentItem: Column {
                                            spacing: 6; leftPadding: 9; topPadding: 8
                                            Text { text: typeButton.modelData.name; color: "#294657"; font.pixelSize: 13; font.weight: Font.DemiBold }
                                            Text { text: typeButton.modelData.size; color: "#738895"; font.pixelSize: 10 }
                                        }
                                    }
                                }
                            }
                        }
                    }
                    Item { Layout.fillHeight: true }
                    Rectangle { Layout.fillWidth: true; height: 1; color: "#e5ebef" }
                    Text { text: draft.assigned + " / " + draft.total + " masks assigned"; color: "#456477"; font.weight: Font.DemiBold }
                }
            }
        }
        Rectangle {
            Layout.fillWidth: true; implicitHeight: 43; color: "#e4ecf1"
            RowLayout {
                anchors.fill: parent; anchors.leftMargin: 22; anchors.rightMargin: 22
                Text { text: "PREVIEW ONLY"; color: "#44667d"; font.pixelSize: 10; font.weight: Font.DemiBold; font.letterSpacing: 1 }
                Text { text: "Saved segmentation · sample types · no SAM inference or reference export"; color: "#607b8d"; font.pixelSize: 11 }
                Item { Layout.fillWidth: true }
                Text { text: "Qt Quick"; color: "#7b929f"; font.pixelSize: 11 }
            }
        }
    }
    Shortcut { sequence: StandardKey.Undo; onActivated: preview.undo() }
}
