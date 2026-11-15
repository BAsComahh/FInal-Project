import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: hud
    required property var viewData
    visible: viewData.selected
    property rect imageRect: Qt.rect(0, 0, width, height)
    readonly property real topExtent: viewData.tool === "select" ? 132 : 51
    readonly property real bottomExtent: viewData.tool === "select" ? 132 : Math.max(64, brief.height - 51)
    readonly property real anchorPixelX: imageRect.x + viewData.anchorX * imageRect.width
    readonly property real baseScale: Math.max(0, Math.min(1, (width - 24) / 426, (height - 24) / (topExtent + bottomExtent)))
    readonly property real baseX: Math.max(245 * baseScale + 12, Math.min(width - 169 * baseScale - 12, anchorPixelX))
    readonly property bool leftEdge: anchorPixelX < baseX - 63 * baseScale
    readonly property bool rightEdge: anchorPixelX > baseX + 43 * baseScale
    readonly property real menuScale: Math.max(0, Math.min(baseScale, leftEdge ? (width - anchorPixelX - 24) / 426 : rightEdge ? (anchorPixelX - 24) / 426 : 1))
    readonly property real requestedX: leftEdge ? anchorPixelX + 265 * menuScale : rightEdge ? anchorPixelX - 189 * menuScale : anchorPixelX
    readonly property real cx: Math.max(245 * menuScale + 12, Math.min(width - 169 * menuScale - 12, requestedX))
    readonly property real cy: Math.max(topExtent * menuScale + 12, Math.min(height - bottomExtent * menuScale - 12, imageRect.y + viewData.anchorY * imageRect.height))
    onViewDataChanged: leader.requestPaint()
    onWidthChanged: leader.requestPaint()
    onHeightChanged: leader.requestPaint()
    onImageRectChanged: leader.requestPaint()

    Canvas {
        id: leader
        anchors.fill: parent
        onPaint: {
            const ctx = getContext("2d")
            ctx.clearRect(0, 0, width, height)
            if (!hud.visible) return
            ctx.strokeStyle = "#6e9bb1"; ctx.lineWidth = 1
            if (hud.viewData.hasPosition) {
                const unitX = hud.imageRect.x + hud.viewData.centerX * hud.imageRect.width
                const unitY = hud.imageRect.y + hud.viewData.centerY * hud.imageRect.height
                const edgeX = unitX < menu.x ? menu.x - 4 * hud.menuScale : menu.x + (brief.width + 4) * hud.menuScale
                ctx.beginPath(); ctx.moveTo(edgeX, menu.y + (brief.y + 44) * hud.menuScale)
                ctx.lineTo(unitX, unitY)
                ctx.stroke()
            }
            if (hud.viewData.tool === "select") {
                ctx.save(); ctx.translate(hud.cx, hud.cy); ctx.scale(hud.menuScale, hud.menuScale * 1.2)
                ctx.beginPath()
                ctx.arc(0, 0, 110, -Math.PI / 2, Math.PI / 2)
                ctx.stroke(); ctx.restore()
            }
        }
    }
    Item {
        id: menu
        x: hud.cx - 245 * hud.menuScale; y: hud.cy - 132 * hud.menuScale
        width: 426; height: 264; scale: hud.menuScale; transformOrigin: Item.TopLeft
        Rectangle {
            id: brief
            objectName: "unitInformation"
            width: 170
            height: information.implicitHeight + 24
            x: 0; y: 81
            radius: 13; color: "#fcffffff"; border.color: "#d9e3e8"
            MouseArea { anchors.fill: parent }
            ColumnLayout {
                id: information
                anchors.fill: parent; anchors.margins: 12; spacing: 6
                Text { text: hud.viewData.unitId; color: "#233b49"; font.family: "Bahnschrift"; font.pixelSize: 15; font.weight: Font.DemiBold }
                GridLayout {
                    columns: 2; Layout.fillWidth: true; columnSpacing: 14; rowSpacing: 6
                    Text { text: "Damage"; color: "#627985"; font.pixelSize: 12 }
                    Text { objectName: "unitDamage"; text: hud.viewData.damage; color: "#233b49"; Layout.fillWidth: true }
                    Text { text: "Speed"; color: "#627985"; font.pixelSize: 12 }
                    Text { objectName: "unitSpeed"; text: hud.viewData.speed; color: "#233b49"; Layout.fillWidth: true }
                }
            }
        }
        Repeater {
            model: [{tool: "distance", label: "Distance", key: "D"}, {tool: "los", label: "LOS", key: "L"}, {tool: "move", label: "Move", key: "V"}, {tool: "correct", label: "Correct", key: ""}]
            ConsoleButton {
                id: actionButton
                required property var modelData
                required property int index
                objectName: "live_" + modelData.tool
                visible: hud.viewData.tool === "select"
                enabled: modelData.tool === "correct" ? hud.viewData.selected : hud.viewData.canQuery
                width: 114
                height: 39; cornerRadius: 24
                x: 245 + (index === 1 || index === 2 ? 105 : 60) - 57
                y: 13 + index * 66
                text: modelData.label
                background: Rectangle {
                    radius: 24
                    color: actionButton.modelData.tool === "correct" ? (actionButton.hovered ? "#a92d37" : "#c63d49") : "white"
                    border.color: actionButton.modelData.tool === "correct" ? "#a92d37" : "#cdd9e1"
                    opacity: actionButton.enabled ? 1 : .45
                }
                contentItem: RowLayout {
                    spacing: 8
                    Text { text: actionButton.modelData.label; color: actionButton.modelData.tool === "correct" ? "white" : "#233b49"; Layout.fillWidth: true; font.pixelSize: 13 }
                    Text { text: actionButton.modelData.key; color: "#627985"; font.family: "Consolas"; font.pixelSize: 10 }
                }
                onClicked: modelData.tool === "correct" ? flow.open("correct") : ui.liveTool(modelData.tool)
            }
        }
    }
}
