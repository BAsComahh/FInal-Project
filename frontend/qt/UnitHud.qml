import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: hud
    required property var viewData
    property rect imageRect: Qt.rect(0, 0, width, height)
    readonly property Theme theme: Theme {}
    visible: viewData.selected

    readonly property real menuWidth: 416
    readonly property real menuHeight: 266
    readonly property real arcCx: 236
    readonly property real arcCy: 133
    readonly property real arcRx: 108
    readonly property real arcRy: 124

    readonly property real topExtent: viewData.tool === "select" ? arcCy : brief.height / 2
    readonly property real bottomExtent: viewData.tool === "select" ? (menuHeight - arcCy) : brief.height / 2
    readonly property real anchorPixelX: imageRect.x + viewData.anchorX * imageRect.width
    readonly property real anchorPixelY: imageRect.y + viewData.anchorY * imageRect.height
    readonly property real baseScale: Math.max(0, Math.min(1, (width - 24) / menuWidth, (height - 24) / (topExtent + bottomExtent)))
    readonly property real baseX: Math.max(arcCx * baseScale + 12, Math.min(width - (menuWidth - arcCx) * baseScale - 12, anchorPixelX))
    readonly property bool leftEdge: anchorPixelX < baseX - 55 * baseScale
    readonly property bool rightEdge: anchorPixelX > baseX + 45 * baseScale
    readonly property real menuScale: Math.max(0, Math.min(baseScale, leftEdge ? (width - anchorPixelX - 24) / menuWidth : rightEdge ? (anchorPixelX - 24) / menuWidth : 1))
    readonly property real requestedX: leftEdge ? anchorPixelX + (arcCx + 20) * menuScale : rightEdge ? anchorPixelX - (menuWidth - arcCx + 20) * menuScale : anchorPixelX
    readonly property real cx: Math.max(arcCx * menuScale + 12, Math.min(width - (menuWidth - arcCx) * menuScale - 12, requestedX))
    readonly property real cy: Math.max(topExtent * menuScale + 12, Math.min(height - bottomExtent * menuScale - 12, anchorPixelY))

    readonly property string sideKey: viewData.side || ""
    readonly property color sideColor: sideKey === "A" ? theme.sideA : sideKey === "B" ? theme.sideB : theme.accent

    onViewDataChanged: leader.requestPaint()
    onWidthChanged: leader.requestPaint()
    onHeightChanged: leader.requestPaint()
    onImageRectChanged: leader.requestPaint()
    onVisibleChanged: leader.requestPaint()

    Canvas {
        id: leader
        anchors.fill: parent
        antialiasing: true
        onPaint: {
            const ctx = getContext("2d")
            ctx.clearRect(0, 0, width, height)
            if (!hud.visible) return

            if (hud.viewData.hasPosition) {
                const unitX = hud.imageRect.x + hud.viewData.centerX * hud.imageRect.width
                const unitY = hud.imageRect.y + hud.viewData.centerY * hud.imageRect.height
                const edgeX = unitX < menu.x ? menu.x - 4 * hud.menuScale : menu.x + (brief.width + 4) * hud.menuScale
                const edgeY = menu.y + (brief.y + brief.height * 0.48) * hud.menuScale

                ctx.save()
                ctx.lineCap = "round"
                ctx.beginPath()
                ctx.moveTo(edgeX, edgeY)
                ctx.lineTo(unitX, unitY)
                ctx.strokeStyle = "rgba(9, 14, 19, 0.88)"
                ctx.lineWidth = 4.0
                ctx.stroke()

                ctx.strokeStyle = "#4ce8ff"
                ctx.lineWidth = 1.8
                ctx.stroke()

                ctx.beginPath()
                ctx.arc(unitX, unitY, 4.5, 0, Math.PI * 2)
                ctx.fillStyle = "#4ce8ff"
                ctx.fill()
                ctx.lineWidth = 2.0
                ctx.strokeStyle = "#090e13"
                ctx.stroke()
                ctx.restore()
            }

            if (hud.viewData.tool === "select") {
                ctx.save()
                ctx.translate(hud.cx, hud.cy)
                ctx.scale(hud.menuScale, hud.menuScale * (hud.arcRy / hud.arcRx))
                ctx.lineCap = "round"

                // Primary query arc (-62 deg to +26 deg)
                ctx.beginPath()
                ctx.arc(0, 0, hud.arcRx, -62 * Math.PI / 180, 26 * Math.PI / 180)
                ctx.strokeStyle = "rgba(9, 14, 19, 0.72)"
                ctx.lineWidth = 3.8
                ctx.stroke()
                ctx.strokeStyle = "rgba(76, 232, 255, 0.72)"
                ctx.lineWidth = 1.6
                ctx.stroke()

                // Lower dashed branch (+30 deg to +60 deg) leading to Correct
                ctx.setLineDash([4, 4])
                ctx.beginPath()
                ctx.arc(0, 0, hud.arcRx, 30 * Math.PI / 180, 60 * Math.PI / 180)
                ctx.strokeStyle = "rgba(9, 14, 19, 0.65)"
                ctx.lineWidth = 3.0
                ctx.stroke()
                ctx.strokeStyle = "rgba(240, 106, 118, 0.78)"
                ctx.lineWidth = 1.5
                ctx.stroke()
                ctx.restore()
            }
        }
    }

    Item {
        id: menu
        x: hud.cx - hud.arcCx * hud.menuScale
        y: hud.cy - hud.arcCy * hud.menuScale
        width: hud.menuWidth
        height: hud.menuHeight
        scale: hud.menuScale
        transformOrigin: Item.TopLeft

        // Layered soft shadow under the dark glass unit card
        Rectangle {
            x: brief.x; y: brief.y + 5
            width: brief.width; height: brief.height
            radius: hud.theme.radiusLg + 1; color: hud.theme.bgShadow
        }

        Rectangle {
            id: brief
            objectName: "unitInformation"
            width: 176
            height: information.implicitHeight + 22
            x: 0
            y: hud.arcCy - height / 2
            radius: hud.theme.radiusLg
            color: hud.theme.bgGlass
            border.color: hud.theme.borderGlass
            clip: true

            MouseArea { anchors.fill: parent }

            Rectangle {
                x: 8; y: 11
                width: 3.5
                height: Math.max(0, parent.height - 22)
                radius: hud.theme.radiusXs
                color: hud.sideColor
            }

            ColumnLayout {
                id: information
                anchors.fill: parent
                anchors.leftMargin: 17
                anchors.rightMargin: 12
                anchors.topMargin: 11
                anchors.bottomMargin: 11
                spacing: 8

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 6
                    Text {
                        text: hud.viewData.unitId
                        color: hud.theme.ink
                        font.family: hud.theme.fontDisplay
                        font.pixelSize: hud.theme.textLg
                        font.weight: Font.DemiBold
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                    }
                    Button {
                        id: quickEdit
                        visible: typeof flow !== "undefined"
                        implicitWidth: editLabel.implicitWidth + 14
                        implicitHeight: 22
                        onClicked: flow.open("profile")
                        ToolTip.visible: hovered
                        ToolTip.text: "Edit unit rule attributes"
                        ToolTip.delay: 400
                        background: Rectangle {
                            radius: hud.theme.radiusSm
                            color: quickEdit.hovered ? hud.theme.accentSoft : hud.theme.bgSubtle
                            border.color: quickEdit.hovered ? hud.theme.selection : hud.theme.borderStrong
                        }
                        contentItem: Text {
                            id: editLabel
                            text: "Info"
                            font.family: hud.theme.fontBody
                            font.pixelSize: hud.theme.textXs
                            font.weight: Font.DemiBold
                            color: quickEdit.hovered ? hud.theme.selection : hud.theme.inkSecondary
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    height: 1
                    color: hud.theme.border
                }

                GridLayout {
                    columns: 2
                    Layout.fillWidth: true
                    columnSpacing: 12
                    rowSpacing: 5

                    Text { text: "Damage"; color: hud.theme.inkMuted; font.pixelSize: hud.theme.textSm }
                    Text {
                        objectName: "unitDamage"
                        text: hud.viewData.damage
                        color: hud.theme.ink
                        font.pixelSize: hud.theme.textMd
                        font.weight: Font.DemiBold
                        horizontalAlignment: Text.AlignRight
                        Layout.fillWidth: true
                    }
                    Text { text: "Speed"; color: hud.theme.inkMuted; font.pixelSize: hud.theme.textSm }
                    Text {
                        objectName: "unitSpeed"
                        text: hud.viewData.speed
                        color: hud.theme.ink
                        font.pixelSize: hud.theme.textMd
                        font.weight: Font.DemiBold
                        horizontalAlignment: Text.AlignRight
                        Layout.fillWidth: true
                    }
                }
            }
        }

        Repeater {
            model: [
                {tool: "distance", label: "Distance", key: "D", angle: -52},
                {tool: "los", label: "LOS", key: "L", angle: -17},
                {tool: "move", label: "Move", key: "V", angle: 17},
                {tool: "correct", label: "Correct", key: "", angle: 54}
            ]
            Item {
                id: slot
                required property var modelData
                required property int index
                readonly property real rad: modelData.angle * Math.PI / 180
                readonly property bool isCorrect: modelData.tool === "correct"
                visible: hud.viewData.tool === "select"
                width: 114
                height: 38
                x: hud.arcCx + hud.arcRx * Math.cos(rad) - width / 2
                y: hud.arcCy + hud.arcRy * Math.sin(rad) - height / 2

                Rectangle {
                    x: 0; y: 4
                    width: parent.width; height: parent.height
                    radius: height / 2
                    color: hud.theme.bgShadow
                }

                Button {
                    id: actionButton
                    objectName: "live_" + slot.modelData.tool
                    anchors.fill: parent
                    enabled: slot.isCorrect ? hud.viewData.selected : hud.viewData.canQuery
                    scale: enabled && down ? 0.97 : 1.0
                    Behavior on scale { NumberAnimation { duration: 70 } }
                    onClicked: slot.isCorrect ? flow.open("correct") : ui.liveTool(slot.modelData.tool)

                    ToolTip.visible: hovered && !slot.isCorrect && !enabled
                    ToolTip.text: hud.viewData.queryBlock || "Unavailable for geometry queries"
                    ToolTip.delay: 350

                    background: Rectangle {
                        radius: height / 2
                        color: {
                            if (slot.isCorrect) {
                                return actionButton.hovered ? hud.theme.dangerHover : hud.theme.danger
                            }
                            return actionButton.hovered ? hud.theme.bgGlassHover : hud.theme.bgGlass
                        }
                        border.width: 1
                        border.color: {
                            if (slot.isCorrect) return hud.theme.modeRecovery
                            return actionButton.hovered ? hud.theme.selection : hud.theme.borderGlass
                        }
                        opacity: actionButton.enabled ? 1 : 0.45
                    }

                    contentItem: RowLayout {
                        spacing: 6
                        Text {
                            text: slot.modelData.label
                            color: slot.isCorrect ? "#ffffff" : (actionButton.hovered ? hud.theme.selection : hud.theme.ink)
                            font.family: hud.theme.fontBody
                            font.pixelSize: hud.theme.textMd
                            font.weight: slot.isCorrect ? Font.DemiBold : Font.Medium
                            Layout.fillWidth: true
                            horizontalAlignment: slot.modelData.key ? Text.AlignLeft : Text.AlignHCenter
                            opacity: actionButton.enabled ? 1 : 0.45
                        }
                        Rectangle {
                            visible: slot.modelData.key.length > 0
                            implicitWidth: kbdText.implicitWidth + 8
                            implicitHeight: 18
                            radius: hud.theme.radiusXs
                            color: actionButton.hovered ? hud.theme.accentSoft : hud.theme.keycapBg
                            border.color: actionButton.hovered ? hud.theme.accentBorder : hud.theme.keycapBorder
                            opacity: actionButton.enabled ? 1 : 0.45
                            Text {
                                id: kbdText
                                anchors.centerIn: parent
                                text: slot.modelData.key
                                color: actionButton.hovered ? hud.theme.selection : hud.theme.inkMuted
                                font.family: hud.theme.fontMono
                                font.pixelSize: hud.theme.textXs
                                font.weight: Font.DemiBold
                            }
                        }
                    }
                }
            }
        }
    }
}
