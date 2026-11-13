import QtQuick
import QtQuick.Controls

Button {
    id: control
    property bool primary: false
    property real cornerRadius: 7
    implicitHeight: 36
    leftPadding: 12; rightPadding: 12
    background: Rectangle {
        radius: control.cornerRadius
        color: control.primary ? (control.hovered ? "#204f76" : "#29658f") : (control.hovered ? "#e7eef3" : "white")
        border.color: control.primary ? "#29658f" : "#cdd9e1"
        opacity: control.enabled ? 1 : 0.45
    }
    contentItem: Text {
        text: control.text; font: control.font
        color: control.primary ? "white" : "#294354"
        horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
        opacity: control.enabled ? 1 : 0.45
    }
}
