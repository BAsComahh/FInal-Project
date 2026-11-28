import QtQuick
import QtQuick.Controls

CheckBox {
    id: control
    readonly property Theme theme: Theme {}
    spacing: 8
    padding: 2

    indicator: Rectangle {
        implicitWidth: 18
        implicitHeight: 18
        x: control.leftPadding
        y: parent.height / 2 - height / 2
        radius: control.theme.radiusXs
        color: control.checked ? control.theme.accent
             : (control.hovered ? control.theme.bgSubtle : control.theme.bgTrack)
        border.width: (control.checked || control.visualFocus) ? 1.5 : 1
        border.color: control.visualFocus ? control.theme.selection
                    : control.checked ? control.theme.accentBorder
                    : (control.hovered ? control.theme.borderStrong : control.theme.borderStrong)

        Canvas {
            id: mark
            anchors.fill: parent
            visible: control.checked
            antialiasing: true
            property color strokeColor: control.theme.inkOnAccent
            onStrokeColorChanged: requestPaint()
            onVisibleChanged: if (visible) requestPaint()
            onPaint: {
                const ctx = getContext("2d")
                ctx.clearRect(0, 0, width, height)
                ctx.strokeStyle = String(strokeColor)
                ctx.lineWidth = 2.1
                ctx.lineCap = "round"
                ctx.lineJoin = "round"
                ctx.beginPath()
                ctx.moveTo(4.5, 9.2)
                ctx.lineTo(7.8, 12.6)
                ctx.lineTo(13.6, 5.6)
                ctx.stroke()
            }
        }
    }

    contentItem: Text {
        leftPadding: control.indicator.width + control.spacing
        text: control.text
        color: control.enabled ? control.theme.ink : control.theme.inkMuted
        font.family: control.theme.fontBody
        font.pixelSize: control.theme.textSm
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
}
