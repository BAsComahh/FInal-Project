import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Button {
    id: control
    property bool primary: false
    property string variant: primary ? "primary" : "default"
    property bool active: false
    property real cornerRadius: 8
    property string shortcut: ""
    property string tooltipText: ""
    readonly property Theme theme: Theme {}

    implicitHeight: 34
    leftPadding: 12
    rightPadding: 12
    scale: control.enabled && control.down ? 0.985 : 1.0
    Behavior on scale { NumberAnimation { duration: 70 } }

    ToolTip.visible: control.hovered && control.tooltipText.length > 0
    ToolTip.text: control.tooltipText
    ToolTip.delay: 450

    background: Rectangle {
        radius: control.cornerRadius
        color: {
            if (control.variant === "primary") {
                return control.hovered ? control.theme.accentHover : control.theme.accent
            }
            if (control.variant === "danger") {
                return control.hovered ? control.theme.dangerHover : control.theme.danger
            }
            if (control.variant === "dangerSubtle") {
                return control.hovered ? control.theme.dangerSoft : control.theme.bgSurface
            }
            if (control.variant === "subtle") {
                if (control.active) return control.theme.accentSoft
                return control.hovered ? "#e7eef4" : control.theme.bgSubtle
            }
            if (control.variant === "ghost") {
                if (control.active) return control.theme.accentSoft
                return control.hovered ? "#e9eff4" : "transparent"
            }
            if (control.active) return control.theme.accentSoft
            return control.hovered ? "#eef4f8" : control.theme.bgSurface
        }
        border.width: control.activeFocus ? 2 : 1
        border.color: {
            if (control.activeFocus) return control.theme.accent
            if (control.variant === "primary") return control.theme.accent
            if (control.variant === "danger") return control.theme.dangerHover
            if (control.variant === "dangerSubtle") return control.hovered ? control.theme.dangerBorder : control.theme.border
            if (control.variant === "ghost" && !control.active && !control.hovered) return "transparent"
            if (control.active) return control.theme.accentBorder
            return control.hovered ? control.theme.borderStrong : control.theme.border
        }
        opacity: control.enabled ? 1 : 0.44
    }

    contentItem: RowLayout {
        spacing: 7
        Text {
            text: control.text
            font: control.font
            color: {
                if (control.variant === "primary" || control.variant === "danger") return "white"
                if (control.variant === "dangerSubtle") return control.theme.danger
                if (control.active) return control.theme.accent
                return control.theme.ink
            }
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            Layout.fillWidth: true
            elide: Text.ElideRight
            opacity: control.enabled ? 1 : 0.44
        }
        Rectangle {
            visible: control.shortcut.length > 0
            implicitWidth: keyLabel.implicitWidth + 8
            implicitHeight: 17
            radius: 4
            color: (control.variant === "primary" || control.variant === "danger") ? "#30ffffff" : control.theme.bgTrack
            border.color: (control.variant === "primary" || control.variant === "danger") ? "transparent" : control.theme.borderSoft
            opacity: control.enabled ? 1 : 0.44
            Text {
                id: keyLabel
                anchors.centerIn: parent
                text: control.shortcut
                font.family: control.theme.fontMono
                font.pixelSize: 10
                color: (control.variant === "primary" || control.variant === "danger") ? "white" : control.theme.inkMuted
            }
        }
    }
}
