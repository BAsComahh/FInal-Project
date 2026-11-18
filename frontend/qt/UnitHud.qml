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

    readonly property real topExtent: arcCy
    readonly property real bottomExtent: menuHeight - arcCy
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

    readonly property real cardNormX: viewData.cardX !== undefined ? viewData.cardX : 0.35
    readonly property real cardNormY: viewData.cardY !== undefined ? viewData.cardY : 0.5
    readonly property real targetCardX: Math.max(8, Math.min(Math.max(8, width - brief.width * menuScale - 8),
        imageRect.x + cardNormX * imageRect.width - brief.width * menuScale * 0.5))
    readonly property real targetCardY: Math.max(8, Math.min(Math.max(8, height - brief.height * menuScale - 8),
        imageRect.y + cardNormY * imageRect.height - brief.height * menuScale * 0.5))

    readonly property string sideKey: viewData.side || ""
    readonly property color sideColor: sideKey === "A" ? theme.sideA : sideKey === "B" ? theme.sideB : theme.accent

    onTargetCardXChanged: if (!cardDrag.drag.active) brief.x = targetCardX
    onTargetCardYChanged: if (!cardDrag.drag.active) brief.y = targetCardY
    Component.onCompleted: {
        brief.x = targetCardX
        brief.y = targetCardY
    }

    onViewDataChanged: leader.requestPaint()
    onWidthChanged: leader.requestPaint()
    onHeightChanged: leader.requestPaint()
    onImageRectChanged: leader.requestPaint()
    onVisibleChanged: {
        if (visible && !cardDrag.drag.active) {
            brief.x = targetCardX
            brief.y = targetCardY
        }
        leader.requestPaint()
    }

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
                const bx0 = brief.x
                const by0 = brief.y
                const bx1 = brief.x + brief.width * hud.menuScale
                const by1 = brief.y + brief.height * hud.menuScale
                const edgeX = Math.max(bx0, Math.min(bx1, unitX))
                const edgeY = Math.max(by0, Math.min(by1, unitY))

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

    // Draggable left unit stat card (independent of the right semicircle buttons)
    Rectangle {
        x: brief.x
        y: brief.y + 5 * hud.menuScale
        width: brief.width
        height: brief.height
        scale: hud.menuScale
        transformOrigin: Item.TopLeft
        radius: hud.theme.radiusLg + 1
        color: hud.theme.bgShadow
    }

    Rectangle {
        id: brief
        objectName: "unitInformation"
        width: 224
        height: information.implicitHeight + 20
        scale: hud.menuScale
        transformOrigin: Item.TopLeft
        radius: hud.theme.radiusLg
        color: hud.theme.bgGlass
        border.color: cardDrag.drag.active ? hud.theme.selection : hud.theme.borderGlass
        clip: true
        onXChanged: leader.requestPaint()
        onYChanged: leader.requestPaint()
        onHeightChanged: leader.requestPaint()

        MouseArea {
            id: cardDrag
            anchors.fill: parent
            z: 0
            drag.target: brief
            drag.threshold: 4
            drag.minimumX: 8
            drag.maximumX: Math.max(8, hud.width - brief.width * hud.menuScale - 8)
            drag.minimumY: 8
            drag.maximumY: Math.max(8, hud.height - brief.height * hud.menuScale - 8)
            cursorShape: drag.active ? Qt.ClosedHandCursor : Qt.OpenHandCursor
            onReleased: {
                if (typeof ui !== "undefined" && ui.moveUnitCard) {
                    const cxNorm = ((brief.x + brief.width * hud.menuScale * 0.5) - hud.imageRect.x) / Math.max(1, hud.imageRect.width)
                    const cyNorm = ((brief.y + brief.height * hud.menuScale * 0.5) - hud.imageRect.y) / Math.max(1, hud.imageRect.height)
                    ui.moveUnitCard(cxNorm, cyNorm)
                }
            }
        }

        Rectangle {
            x: 8; y: 10
            width: 3.5
            height: Math.max(0, parent.height - 20)
            radius: hud.theme.radiusXs
            color: hud.sideColor
        }

        ColumnLayout {
            id: information
            z: 1
            anchors.fill: parent
            anchors.leftMargin: 17
            anchors.rightMargin: 11
            anchors.topMargin: 10
            anchors.bottomMargin: 10
            spacing: 6

            RowLayout {
                Layout.fillWidth: true
                spacing: 6
                Text {
                    text: hud.viewData.unitId
                    color: hud.theme.ink
                    font.family: hud.theme.fontDisplay
                    font.pixelSize: hud.theme.textLg
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }
                Rectangle {
                    visible: (hud.viewData.pointsText || "").length > 0
                    implicitWidth: ptsTxt.implicitWidth + 10
                    implicitHeight: 18
                    radius: height / 2
                    color: hud.theme.bgTrack
                    border.color: hud.theme.border
                    Text {
                        id: ptsTxt
                        anchors.centerIn: parent
                        text: hud.viewData.pointsText || ""
                        color: hud.theme.inkSecondary
                        font.family: hud.theme.fontMono
                        font.pixelSize: 10
                    }
                }
                Item { Layout.fillWidth: true }
                Button {
                    id: quickEdit
                    objectName: "hudInfoButton"
                    visible: typeof flow !== "undefined"
                    implicitWidth: editLabel.implicitWidth + 14
                    implicitHeight: 22
                    onClicked: flow.open("profile")
                    ToolTip.visible: hovered
                    ToolTip.text: "Open unit details and attribute editor in sidebar"
                    ToolTip.delay: 400
                    background: Rectangle {
                        radius: hud.theme.radiusSm
                        color: (typeof flow !== "undefined" && flow.state && flow.state.profileOpen)
                               ? hud.theme.accentSoft
                               : (quickEdit.hovered ? hud.theme.accentSoft : hud.theme.bgSubtle)
                        border.color: (typeof flow !== "undefined" && flow.state && flow.state.profileOpen)
                                      ? hud.theme.selection
                                      : (quickEdit.hovered ? hud.theme.selection : hud.theme.borderStrong)
                    }
                    contentItem: Text {
                        id: editLabel
                        text: "Info"
                        font.family: hud.theme.fontBody
                        font.pixelSize: hud.theme.textXs
                        font.weight: Font.DemiBold
                        color: ((typeof flow !== "undefined" && flow.state && flow.state.profileOpen) || quickEdit.hovered)
                               ? hud.theme.selection : hud.theme.inkSecondary
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                }
            }

            ColumnLayout {
                visible: (hud.viewData.name || "").length > 0 || (hud.viewData.classification || "").length > 0
                Layout.fillWidth: true
                spacing: 1
                Text {
                    visible: (hud.viewData.name || "").length > 0
                    text: hud.viewData.name || ""
                    color: hud.theme.ink
                    font.pixelSize: hud.theme.textSm
                    font.weight: Font.DemiBold
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }
                Text {
                    visible: (hud.viewData.classification || "").length > 0
                    text: hud.viewData.classification || ""
                    color: hud.theme.inkSecondary
                    font.pixelSize: 10
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }
            }

            Flow {
                visible: (hud.viewData.statusTags || []).length > 0
                Layout.fillWidth: true
                spacing: 4
                Repeater {
                    model: hud.viewData.statusTags || []
                    Rectangle {
                        required property string modelData
                        implicitWidth: stTxt.implicitWidth + 10
                        implicitHeight: 17
                        radius: height / 2
                        color: modelData === "Wavering" ? hud.theme.dangerSoft : hud.theme.warningSoft
                        border.color: modelData === "Wavering" ? hud.theme.dangerBorder : hud.theme.warningBorder
                        Text {
                            id: stTxt
                            anchors.centerIn: parent
                            text: modelData
                            color: modelData === "Wavering" ? hud.theme.modeRecovery : hud.theme.warning
                            font.pixelSize: 10
                            font.weight: Font.DemiBold
                        }
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                height: 1
                color: hud.theme.border
            }

            GridLayout {
                columns: 4
                Layout.fillWidth: true
                columnSpacing: 5
                rowSpacing: 5

                Repeater {
                    model: hud.viewData.stats || []
                    Rectangle {
                        id: statCell
                        required property var modelData
                        Layout.fillWidth: true
                        implicitHeight: 31
                        radius: hud.theme.radiusXs
                        color: hud.theme.bgTrack
                        border.color: hud.theme.borderSoft

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 4
                            anchors.rightMargin: 4
                            anchors.topMargin: 2
                            anchors.bottomMargin: 2
                            spacing: 0
                            Text {
                                text: statCell.modelData.label
                                color: hud.theme.inkMuted
                                font.pixelSize: 9
                                Layout.fillWidth: true
                            }
                            Text {
                                objectName: statCell.modelData.objectName || ""
                                text: statCell.modelData.value
                                color: statCell.modelData.value === "—" ? hud.theme.inkMuted : hud.theme.ink
                                font.family: hud.theme.fontMono
                                font.pixelSize: hud.theme.textSm
                                font.weight: Font.DemiBold
                                Layout.fillWidth: true
                                elide: Text.ElideRight
                            }
                        }
                    }
                }
            }

            Text {
                visible: (hud.viewData.rulesSummary || "").length > 0
                text: hud.viewData.rulesSummary || ""
                color: hud.theme.inkSecondary
                font.pixelSize: 10
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                maximumLineCount: 2
                elide: Text.ElideRight
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
