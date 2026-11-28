import QtQuick
import QtQuick.Controls

ComboBox {
    id: control
    readonly property Theme theme: Theme {}
    implicitHeight: 32

    delegate: ItemDelegate {
        id: itemDel
        required property var modelData
        required property int index
        width: ListView.view ? ListView.view.width : control.width
        implicitHeight: 30
        highlighted: control.highlightedIndex === index
        contentItem: Text {
            leftPadding: 10
            rightPadding: 10
            text: itemDel.modelData !== undefined ? String(itemDel.modelData) : ""
            color: itemDel.highlighted ? control.theme.selection : control.theme.ink
            font.family: control.theme.fontBody
            font.pixelSize: control.theme.textSm
            font.weight: control.currentIndex === itemDel.index ? Font.DemiBold : Font.Normal
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        background: Rectangle {
            radius: control.theme.radiusXs
            color: itemDel.highlighted ? control.theme.accentSoft
                 : itemDel.hovered ? control.theme.bgHover : "transparent"
        }
    }

    indicator: Canvas {
        id: chevron
        x: control.width - width - 10
        y: (control.availableHeight - height) / 2
        width: 10
        height: 6
        antialiasing: true
        property color strokeColor: (control.pressed || control.popup.visible || control.hovered)
                                    ? control.theme.selection : control.theme.inkSecondary
        property bool flipped: control.popup.visible
        onStrokeColorChanged: requestPaint()
        onFlippedChanged: requestPaint()
        onPaint: {
            const ctx = getContext("2d")
            ctx.clearRect(0, 0, width, height)
            ctx.strokeStyle = String(strokeColor)
            ctx.lineWidth = 1.6
            ctx.lineCap = "round"
            ctx.lineJoin = "round"
            ctx.beginPath()
            if (flipped) {
                ctx.moveTo(1.5, height - 1.5)
                ctx.lineTo(width / 2, 1.5)
                ctx.lineTo(width - 1.5, height - 1.5)
            } else {
                ctx.moveTo(1.5, 1.5)
                ctx.lineTo(width / 2, height - 1.5)
                ctx.lineTo(width - 1.5, 1.5)
            }
            ctx.stroke()
        }
    }

    contentItem: Text {
        leftPadding: 10
        rightPadding: 28
        text: control.displayText
        color: control.enabled ? control.theme.ink : control.theme.inkMuted
        font.family: control.theme.fontBody
        font.pixelSize: control.theme.textSm
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    background: Rectangle {
        implicitHeight: 32
        radius: control.theme.radiusSm
        color: control.theme.bgTrack
        border.width: (control.activeFocus || control.popup.visible) ? 1.5 : 1
        border.color: (control.activeFocus || control.popup.visible) ? control.theme.selection
                    : (control.hovered ? control.theme.borderStrong : control.theme.border)
    }

    popup: Popup {
        y: control.height + 3
        width: control.width
        implicitHeight: Math.min(220, contentItem.implicitHeight + 8)
        padding: 4

        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: control.popup.visible ? control.delegateModel : null
            currentIndex: control.highlightedIndex
            ScrollIndicator.vertical: ScrollIndicator {}
        }

        background: Rectangle {
            radius: control.theme.radiusSm
            color: control.theme.bgElevated
            border.color: control.theme.borderStrong
            border.width: 1
        }
    }
}
