import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Button {
    id: control
    property bool primary: false
    property string variant: primary ? "primary" : "default"
    property bool active: false
    property real cornerRadius: theme.radiusMd
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
                return control.hovered ? control.theme.dangerSoft : control.theme.bgSubtle
            }
            if (control.variant === "subtle") {
                if (control.active) return control.theme.accentSoft
                return control.hovered ? control.theme.bgHover : control.theme.bgSubtle
            }
            if (control.variant === "ghost") {
                if (control.active) return control.theme.accentSoft
                return control.hovered ? control.theme.bgElevated : "transparent"
            }
            if (control.active) return control.theme.accentSoft
            return control.hovered ? control.theme.bgElevated : control.theme.bgSubtle
        }
        border.width: control.visualFocus ? 2 : 1
        border.color: {
            if (control.visualFocus) return control.theme.selection
            if (control.variant === "primary") return control.hovered ? control.theme.accentHover : control.theme.accentBorder
            if (control.variant === "danger") return control.theme.dangerHover
            if (control.variant === "dangerSubtle") return control.hovered ? control.theme.danger : control.theme.dangerBorder
            if (control.variant === "ghost" && !control.active && !control.hovered) return "transparent"
            if (control.active) return control.theme.accentBorder
            return control.hovered ? control.theme.borderStrong : control.theme.border
        }
        opacity: control.enabled ? 1 : 0.42
    }

    contentItem: RowLayout {
        spacing: 7
        Text {
            text: control.text
            font.family: control.theme.fontBody
            font.pixelSize: control.theme.textSm
            font.weight: (control.variant === "primary" || control.variant === "danger" || control.active)
                         ? Font.DemiBold : Font.Medium
            color: {
                if (control.variant === "primary" || control.variant === "danger") return "#ffffff"
                if (control.variant === "dangerSubtle") return control.theme.modeRecovery
                if (control.active) return control.theme.selection
                return control.theme.ink
            }
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            Layout.fillWidth: true
            elide: Text.ElideRight
            opacity: control.enabled ? 1 : 0.42
        }
        Rectangle {
            visible: control.shortcut.length > 0
            implicitWidth: keyLabel.implicitWidth + 10
            implicitHeight: 18
            radius: control.theme.radiusXs
            color: (control.variant === "primary" || control.variant === "danger")
                   ? "#28000000" : control.theme.keycapBg
            border.color: (control.variant === "primary" || control.variant === "danger")
                          ? "#40ffffff" : control.theme.keycapBorder
            opacity: control.enabled ? 1 : 0.42
            Text {
                id: keyLabel
                anchors.centerIn: parent
                text: control.shortcut
                font.family: control.theme.fontMono
                font.pixelSize: control.theme.textXs
                color: (control.variant === "primary" || control.variant === "danger")
                       ? "#ffffff" : control.theme.inkMuted
            }
        }
    }
}
