import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: hud
    property var terrainData: ({})
    property real centerX: 0.5
    property real centerY: 0.5
    property real cardX: 0.35
    property real cardY: 0.5
    property bool infoOpen: false
    property rect imageRect: Qt.rect(0, 0, width, height)
    readonly property Theme theme: Theme {}
    readonly property color accentColor: (terrainData && terrainData.color) ? terrainData.color : theme.modeTerrain

    readonly property real targetCardX: Math.max(8, Math.min(Math.max(8, width - brief.width - 8),
        imageRect.x + cardX * imageRect.width - brief.width * 0.5))
    readonly property real targetCardY: Math.max(8, Math.min(Math.max(8, height - brief.height - 8),
        imageRect.y + cardY * imageRect.height - brief.height * 0.5))

    onTargetCardXChanged: if (!cardDrag.drag.active) brief.x = targetCardX
    onTargetCardYChanged: if (!cardDrag.drag.active) brief.y = targetCardY
    Component.onCompleted: {
        brief.x = targetCardX
        brief.y = targetCardY
    }
    onTerrainDataChanged: leader.requestPaint()
    onCenterXChanged: leader.requestPaint()
    onCenterYChanged: leader.requestPaint()
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
            const px = hud.imageRect.x + hud.centerX * hud.imageRect.width
            const py = hud.imageRect.y + hud.centerY * hud.imageRect.height
            const bx0 = brief.x
            const by0 = brief.y
            const bx1 = brief.x + brief.width
            const by1 = brief.y + brief.height
            const edgeX = Math.max(bx0, Math.min(bx1, px))
            const edgeY = Math.max(by0, Math.min(by1, py))

            ctx.save()
            ctx.lineCap = "round"
            ctx.beginPath()
            ctx.moveTo(edgeX, edgeY)
            ctx.lineTo(px, py)
            ctx.strokeStyle = "rgba(9, 14, 19, 0.88)"
            ctx.lineWidth = 4.0
            ctx.stroke()

            ctx.strokeStyle = "#4ce8ff"
            ctx.lineWidth = 1.8
            ctx.stroke()

            ctx.beginPath()
            ctx.arc(px, py, 4.5, 0, Math.PI * 2)
            ctx.fillStyle = "#4ce8ff"
            ctx.fill()
            ctx.lineWidth = 2.0
            ctx.strokeStyle = "#090e13"
            ctx.stroke()
            ctx.restore()
        }
    }

    // Drop shadow matching UnitHud
    Rectangle {
        x: brief.x
        y: brief.y + 5
        width: brief.width
        height: brief.height
        radius: hud.theme.radiusLg + 1
        color: hud.theme.bgShadow
    }

    Rectangle {
        id: brief
        objectName: "terrainHudCard"
        width: 232
        height: contentCol.implicitHeight + 20
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
            drag.maximumX: Math.max(8, hud.width - brief.width - 8)
            drag.minimumY: 8
            drag.maximumY: Math.max(8, hud.height - brief.height - 8)
            cursorShape: drag.active ? Qt.ClosedHandCursor : Qt.OpenHandCursor
            onReleased: {
                const cxNorm = ((brief.x + brief.width * 0.5) - hud.imageRect.x) / Math.max(1, hud.imageRect.width)
                const cyNorm = ((brief.y + brief.height * 0.5) - hud.imageRect.y) / Math.max(1, hud.imageRect.height)
                flow.moveTerrainCard(cxNorm, cyNorm)
            }
        }

        Rectangle {
            x: 8; y: 10
            width: 3.5
            height: Math.max(0, parent.height - 20)
            radius: hud.theme.radiusXs
            color: hud.accentColor
        }

        ColumnLayout {
            id: contentCol
            z: 1
            anchors.fill: parent
            anchors.leftMargin: 17
            anchors.rightMargin: 11
            anchors.topMargin: 10
            anchors.bottomMargin: 10
            spacing: 7

            RowLayout {
                Layout.fillWidth: true
                spacing: 6
                Text {
                    text: (hud.terrainData && hud.terrainData.label) ? hud.terrainData.label : "Terrain"
                    color: hud.theme.ink
                    font.family: hud.theme.fontDisplay
                    font.pixelSize: hud.theme.textLg
                    font.weight: Font.DemiBold
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }
                Rectangle {
                    visible: Boolean(hud.terrainData && hud.terrainData.id)
                    implicitWidth: idTxt.implicitWidth + 10
                    implicitHeight: 18
                    radius: height / 2
                    color: hud.theme.bgTrack
                    border.color: hud.theme.border
                    Text {
                        id: idTxt
                        anchors.centerIn: parent
                        text: (hud.terrainData && hud.terrainData.id) ? hud.terrainData.id : ""
                        color: hud.theme.inkSecondary
                        font.family: hud.theme.fontMono
                        font.pixelSize: 10
                    }
                }
                Button {
                    id: infoBtn
                    objectName: "terrainHudInfoButton"
                    implicitWidth: infoLbl.implicitWidth + 14
                    implicitHeight: 22
                    onClicked: flow.openTerrainInfo()
                    ToolTip.visible: hovered
                    ToolTip.text: "Configure or delete this terrain in the sidebar"
                    ToolTip.delay: 350
                    background: Rectangle {
                        radius: hud.theme.radiusSm
                        color: hud.infoOpen ? hud.theme.accentSoft
                               : (infoBtn.hovered ? hud.theme.accentSoft : hud.theme.bgSubtle)
                        border.color: (hud.infoOpen || infoBtn.hovered) ? hud.theme.selection : hud.theme.borderStrong
                    }
                    contentItem: Text {
                        id: infoLbl
                        text: "Info"
                        font.family: hud.theme.fontBody
                        font.pixelSize: hud.theme.textXs
                        font.weight: Font.DemiBold
                        color: (hud.infoOpen || infoBtn.hovered) ? hud.theme.selection : hud.theme.inkSecondary
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 6
                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: 36
                    radius: hud.theme.radiusSm
                    color: hud.theme.bgTrack
                    border.color: hud.theme.borderSoft
                    Column {
                        anchors.centerIn: parent
                        spacing: 1
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: "KIND"
                            color: hud.theme.inkMuted
                            font.family: hud.theme.fontMono
                            font.pixelSize: 9
                        }
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: (hud.terrainData && hud.terrainData.kindLabel) ? hud.terrainData.kindLabel : "—"
                            color: hud.theme.ink
                            font.pixelSize: hud.theme.textXs
                            font.weight: Font.DemiBold
                        }
                    }
                }
                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: 36
                    radius: hud.theme.radiusSm
                    color: hud.theme.bgTrack
                    border.color: hud.theme.borderSoft
                    Column {
                        anchors.centerIn: parent
                        spacing: 1
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: "HEIGHT"
                            color: hud.theme.inkMuted
                            font.family: hud.theme.fontMono
                            font.pixelSize: 9
                        }
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: (hud.terrainData && hud.terrainData.heightText) ? hud.terrainData.heightText : "—"
                            color: hud.theme.ink
                            font.pixelSize: hud.theme.textXs
                            font.weight: Font.DemiBold
                        }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 6
                Text {
                    text: (hud.terrainData && hud.terrainData.areaText) ? hud.terrainData.areaText : ""
                    color: hud.theme.inkMuted
                    font.family: hud.theme.fontMono
                    font.pixelSize: 10
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }
                Button {
                    id: dismissBtn
                    objectName: "terrainHudClose"
                    implicitWidth: 20
                    implicitHeight: 20
                    onClicked: flow.clearTerrainSelection()
                    ToolTip.visible: hovered
                    ToolTip.text: "Dismiss terrain card (Esc)"
                    ToolTip.delay: 350
                    background: Rectangle {
                        radius: hud.theme.radiusXs
                        color: dismissBtn.hovered ? hud.theme.bgHover : "transparent"
                    }
                    contentItem: Text {
                        text: "×"
                        color: dismissBtn.hovered ? hud.theme.ink : hud.theme.inkMuted
                        font.pixelSize: 13
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                }
            }
        }
    }
}
