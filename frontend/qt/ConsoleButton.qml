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
    property string iconKind: ""
    readonly property Theme theme: Theme {}
    readonly property color labelColor: {
        if (control.variant === "primary") return control.theme.inkOnAccent
        if (control.variant === "danger") return "#ffffff"
        if (control.variant === "dangerSubtle") return control.theme.modeRecovery
        if (control.active) return control.theme.selection
        return control.theme.ink
    }

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
        spacing: control.text.length > 0 ? 6 : 0
        Canvas {
            id: btnIcon
            visible: control.iconKind.length > 0
            Layout.alignment: Qt.AlignVCenter | (control.text.length > 0 ? Qt.AlignLeft : Qt.AlignHCenter)
            Layout.preferredWidth: 14
            Layout.preferredHeight: 14
            antialiasing: true
            property string kind: control.iconKind
            property color ink: control.labelColor
            opacity: control.enabled ? 1 : 0.42
            onKindChanged: requestPaint()
            onInkChanged: requestPaint()
            onPaint: {
                const ctx = getContext("2d")
                ctx.clearRect(0, 0, width, height)
                ctx.strokeStyle = String(ink)
                ctx.fillStyle = String(ink)
                ctx.lineWidth = 1.5
                ctx.lineCap = "round"
                if (kind === "sun") {
                    ctx.beginPath()
                    ctx.arc(7, 7, 2.7, 0, Math.PI * 2)
                    ctx.stroke()
                    for (let i = 0; i < 8; i++) {
                        const a = i * Math.PI / 4
                        ctx.beginPath()
                        ctx.moveTo(7 + Math.cos(a) * 4.5, 7 + Math.sin(a) * 4.5)
                        ctx.lineTo(7 + Math.cos(a) * 6.0, 7 + Math.sin(a) * 6.0)
                        ctx.stroke()
                    }
                } else if (kind === "moon") {
                    ctx.beginPath()
                    ctx.arc(7.4, 7.2, 4.6, 0.35 * Math.PI, 1.68 * Math.PI, false)
                    ctx.arc(9.4, 5.4, 3.6, 1.48 * Math.PI, 0.55 * Math.PI, true)
                    ctx.closePath()
                    ctx.fill()
                } else if (kind === "more") {
                    for (let i = 0; i < 3; i++) {
                        ctx.beginPath()
                        ctx.arc(3 + i * 4, 7, 1.35, 0, Math.PI * 2)
                        ctx.fill()
                    }
                } else if (kind === "close") {
                    ctx.beginPath()
                    ctx.moveTo(3.5, 3.5); ctx.lineTo(10.5, 10.5)
                    ctx.moveTo(10.5, 3.5); ctx.lineTo(3.5, 10.5)
                    ctx.stroke()
                }
            }
        }
        Text {
            visible: control.text.length > 0
            text: control.text
            font.family: control.theme.fontBody
            font.pixelSize: control.theme.textSm
            font.weight: (control.variant === "primary" || control.variant === "danger" || control.active)
                         ? Font.DemiBold : Font.Medium
            color: control.labelColor
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
            color: control.variant === "primary" ? "#26000000"
                   : control.variant === "danger" ? "#28000000" : control.theme.keycapBg
            border.color: control.variant === "primary" ? "#40000000"
                          : control.variant === "danger" ? "#40ffffff" : control.theme.keycapBorder
            opacity: control.enabled ? 1 : 0.42
            Text {
                id: keyLabel
                anchors.centerIn: parent
                text: control.shortcut
                font.family: control.theme.fontMono
                font.pixelSize: control.theme.textXs
                color: control.variant === "primary" ? control.theme.inkOnAccent
                       : control.variant === "danger" ? "#ffffff" : control.theme.inkMuted
            }
        }
    }
}
