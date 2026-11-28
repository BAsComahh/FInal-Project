import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts

ApplicationWindow {
    id: window
    width: 1180
    height: 820
    minimumWidth: 820
    minimumHeight: 640
    visible: true

    readonly property Theme theme: Theme {}
    property var s: ui.state
    readonly property bool table: s.stage === "table"
    readonly property bool live: s.stage === "playback" || s.stage === "recalibrate"
    readonly property string flowKind: flow.state.kind || "live"
    readonly property bool terrainMode: !window.table && !window.live && flowKind === "terrain"
    readonly property bool recoveryRectMode: window.live && flowKind === "recovery" && flow.state.tool === "Rectangle" && !flow.state.busy
    readonly property bool recoveryQuadMode: window.live && flowKind === "recovery" && flow.state.tool === "Quad" && !flow.state.busy
    readonly property bool modalOpen: resetDialog.visible || armyFile.visible || registrationFile.visible || terrainDialogs.formOpen
    readonly property bool textInputActive: activeFocusItem instanceof TextInput || activeFocusItem instanceof TextEdit
    readonly property bool tableDimensions: window.table && s.tableMode === "dimensions"
    property var tableWidthDraft: null
    property var tableDepthDraft: null
    onTableDimensionsChanged: {
        if (!tableDimensions) {
            tableWidthDraft = null
            tableDepthDraft = null
        }
    }

    readonly property string badgeText: {
        if (window.table) return "TABLE SETUP"
        if (window.terrainMode) return "TERRAIN"
        if (!window.live) return "REGISTER"
        if (flowKind === "replay") return "REPLAY"
        if (flowKind === "recovery") return "RECOVERY"
        if (flowKind === "recalibrate") return "RECALIBRATE"
        if (flowKind === "debug") return "DEBUG"
        return "LIVE"
    }
    readonly property color badgeColor: {
        if (window.table) return theme.inkSecondary
        if (window.terrainMode) return theme.modeTerrain
        if (!window.live) return theme.selection
        if (flowKind === "replay") return theme.modeReplay
        if (flowKind === "recovery") return theme.modeRecovery
        if (flowKind === "recalibrate") return theme.modeRecalibrate
        return theme.modeLive
    }
    readonly property color badgeDot: {
        if (window.table) return theme.selection
        if (window.terrainMode) return theme.modeTerrainDot
        if (!window.live) return theme.accentHover
        if (flowKind === "replay") return theme.modeReplayDot
        if (flowKind === "recovery") return theme.modeRecoveryDot
        if (flowKind === "recalibrate") return theme.modeRecalibrateDot
        return theme.modeLiveDot
    }
    readonly property color badgeSoft: {
        if (window.table) return theme.bgTrack
        if (window.terrainMode) return theme.modeTerrainSoft
        if (!window.live) return theme.accentSoft
        if (flowKind === "replay") return theme.modeReplaySoft
        if (flowKind === "recovery") return theme.modeRecoverySoft
        if (flowKind === "recalibrate") return theme.modeRecalibrateSoft
        return theme.modeLiveSoft
    }
    readonly property color badgeBorder: {
        if (window.table) return theme.borderStrong
        if (window.terrainMode) return theme.modeTerrainBorder
        if (!window.live) return theme.accentBorder
        if (flowKind === "replay") return theme.modeReplayBorder
        if (flowKind === "recovery") return theme.modeRecoveryBorder
        if (flowKind === "recalibrate") return theme.modeRecalibrateBorder
        return theme.modeLiveBorder
    }

    title: {
        if (window.table) return "Match console · Table setup"
        if (window.terrainMode) return "Match console · Terrain"
        if (!window.live) return "Match console · Unit registration"
        if (flowKind === "replay") return "Match console · Replay"
        if (flowKind === "recovery") return "Match console · Recovery"
        if (flowKind === "recalibrate") return "Match console · Recalibrate"
        return "Match console · Live"
    }
    color: theme.bgCanvas
    font.family: theme.fontBody
    font.pixelSize: theme.textMd
    onClosing: ui.close()

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // Compact 52px top header bar with subtle 2px mode accent stripe
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 52
            color: theme.bgHeader

            Rectangle {
                anchors.top: parent.top
                width: parent.width
                height: 2
                color: window.badgeDot
            }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 16
                anchors.rightMargin: 16
                anchors.topMargin: 2
                spacing: 10

                Rectangle {
                    implicitWidth: badgeRow.implicitWidth + 16
                    implicitHeight: 26
                    radius: height / 2
                    color: window.badgeSoft
                    border.color: window.badgeBorder
                    RowLayout {
                        id: badgeRow
                        anchors.centerIn: parent
                        spacing: 6
                        Rectangle {
                            width: 7; height: 7; radius: 4
                            color: window.badgeDot
                        }
                        Text {
                            text: window.badgeText
                            color: window.badgeColor
                            font.family: theme.fontMono
                            font.pixelSize: theme.textXs
                            font.weight: Font.DemiBold
                            font.letterSpacing: 0.8
                        }
                    }
                }

                Text {
                    text: {
                        if (window.table) return "Frame the battlefield"
                        if (window.terrainMode) return "Terrain polygon editor"
                        if (!window.live) return "Build the starting board"
                        if (flowKind === "replay") return "Historical board"
                        if (flowKind === "recovery") return "Scoped unit recovery"
                        if (flowKind === "recalibrate") return "Board corner alignment"
                        if (flowKind === "debug") return "Paused snapshot"
                        return "Match console"
                    }
                    color: theme.ink
                    font.family: theme.fontDisplay
                    font.pixelSize: window.width < 980 ? theme.textLg : theme.textXl
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }

                Item { Layout.fillWidth: true }

                // Live / Replay segmented mode switcher
                Rectangle {
                    visible: window.live
                    implicitWidth: segRow.implicitWidth + 6
                    implicitHeight: 34
                    radius: theme.radiusMd
                    color: theme.bgTrack
                    border.color: theme.border

                    RowLayout {
                        id: segRow
                        anchors.centerIn: parent
                        spacing: 3

                        Button {
                            id: liveSeg
                            implicitHeight: 28
                            leftPadding: 12; rightPadding: 12
                            enabled: !flow.state.busy
                            onClicked: if (window.flowKind !== "live") flow.action("cancel")
                            background: Rectangle {
                                radius: theme.radiusSm
                                color: window.flowKind === "live" ? theme.bgElevated : (liveSeg.hovered ? theme.bgSubtle : "transparent")
                                border.color: window.flowKind === "live" ? theme.modeLiveBorder : "transparent"
                            }
                            contentItem: Text {
                                text: "Live"
                                font.family: theme.fontBody
                                font.pixelSize: theme.textSm
                                font.weight: window.flowKind === "live" ? Font.DemiBold : Font.Normal
                                color: window.flowKind === "live" ? theme.modeLive : theme.inkSecondary
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                            }
                        }

                        Button {
                            id: replaySeg
                            implicitHeight: 28
                            leftPadding: 12; rightPadding: 12
                            enabled: !flow.state.busy && window.flowKind !== "debug"
                            onClicked: if (window.flowKind !== "replay") flow.open("replay")
                            background: Rectangle {
                                radius: theme.radiusSm
                                color: window.flowKind === "replay" ? theme.bgElevated : (replaySeg.hovered ? theme.bgSubtle : "transparent")
                                border.color: window.flowKind === "replay" ? theme.modeReplayBorder : "transparent"
                            }
                            contentItem: Text {
                                text: "Replay"
                                font.family: theme.fontBody
                                font.pixelSize: theme.textSm
                                font.weight: window.flowKind === "replay" ? Font.DemiBold : Font.Normal
                                color: window.flowKind === "replay" ? theme.modeReplay : theme.inkSecondary
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                            }
                        }
                    }
                }

                ConsoleButton {
                    objectName: "loadRegistration"
                    text: "Load registration"
                    variant: "subtle"
                    visible: !window.live
                    enabled: !s.locked
                    onClicked: registrationFile.open()
                }
                ConsoleButton {
                    text: "Undo"
                    variant: "subtle"
                    visible: !window.live
                    enabled: window.table ? s.tableMode === "manual" && s.cornerCount > 0 : s.editable && s.undo
                    onClicked: ui.undo()
                }
                ConsoleButton {
                    text: "Reset"
                    variant: "subtle"
                    visible: !window.table
                    onClicked: resetDialog.open()
                }
                ConsoleButton {
                    objectName: "saveRegistration"
                    text: s.locked ? "Saved" : "Save"
                    shortcut: s.locked ? "" : "S"
                    visible: !window.table && !window.live
                    enabled: s.editable && s.ready
                    onClicked: ui.finish()
                }
                ConsoleButton {
                    objectName: "startPlayback"
                    text: s.pendingPlay ? "Starting…" : "Start video"
                    primary: true
                    visible: !window.table && !window.live
                    enabled: s.ready
                    onClicked: ui.start()
                }
            }

            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: 1
                color: theme.border
            }
        }

        // Workspace body
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.margins: 10
            spacing: 8

            // Registration toolbar (single compact dark card)
            Rectangle {
                visible: !window.table && !window.live && !window.terrainMode
                Layout.fillWidth: true
                implicitHeight: regFlow.implicitHeight + 14
                radius: theme.radiusLg
                color: theme.bgSurface
                border.color: theme.border

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 12
                    anchors.rightMargin: 12
                    anchors.topMargin: 7
                    anchors.bottomMargin: 7
                    spacing: 8

                    Flow {
                        id: regFlow
                        Layout.fillWidth: true
                        spacing: 7

                        // Segmented Points | Assign mode switcher
                        Rectangle {
                            implicitWidth: regModeSeg.implicitWidth + 6
                            implicitHeight: 32
                            radius: theme.radiusMd
                            color: theme.bgTrack
                            border.color: theme.border

                            RowLayout {
                                id: regModeSeg
                                anchors.centerIn: parent
                                spacing: 3

                                Button {
                                    id: pointsSeg
                                    implicitHeight: 26
                                    leftPadding: 11; rightPadding: 11
                                    enabled: s.editable
                                    onClicked: ui.setMode("Points")
                                    background: Rectangle {
                                        radius: theme.radiusSm
                                        color: s.mode === "Points" ? theme.accent : (pointsSeg.hovered ? theme.bgSubtle : "transparent")
                                    }
                                    contentItem: Text {
                                        text: "Points"
                                        font.family: theme.fontBody
                                        font.pixelSize: theme.textSm
                                        font.weight: s.mode === "Points" ? Font.DemiBold : Font.Normal
                                        color: s.mode === "Points" ? "#ffffff" : theme.inkSecondary
                                        horizontalAlignment: Text.AlignHCenter
                                        verticalAlignment: Text.AlignVCenter
                                        opacity: pointsSeg.enabled ? 1 : 0.42
                                    }
                                }
                                Button {
                                    id: assignSeg
                                    implicitHeight: 26
                                    leftPadding: 11; rightPadding: 11
                                    enabled: s.editable
                                    onClicked: ui.setMode("Assign")
                                    background: Rectangle {
                                        radius: theme.radiusSm
                                        color: s.mode === "Assign" ? theme.accent : (assignSeg.hovered ? theme.bgSubtle : "transparent")
                                    }
                                    contentItem: Text {
                                        text: "Assign"
                                        font.family: theme.fontBody
                                        font.pixelSize: theme.textSm
                                        font.weight: s.mode === "Assign" ? Font.DemiBold : Font.Normal
                                        color: s.mode === "Assign" ? "#ffffff" : theme.inkSecondary
                                        horizontalAlignment: Text.AlignHCenter
                                        verticalAlignment: Text.AlignVCenter
                                        opacity: assignSeg.enabled ? 1 : 0.42
                                    }
                                }
                            }
                        }

                        ConsoleButton {
                            text: "New mask"
                            shortcut: "N"
                            implicitHeight: 32
                            variant: "subtle"
                            enabled: s.editable && s.ready
                            onClicked: ui.newObject()
                        }
                        ConsoleButton {
                            text: "Rectangle"
                            implicitHeight: 32
                            active: s.mode === "Rectangle"
                            enabled: s.editable && s.ready
                            tooltipText: "Drag with the left mouse button to draw a mask."
                            onClicked: ui.setMode("Rectangle")
                        }
                        ConsoleButton {
                            text: "Four corners"
                            implicitHeight: 32
                            active: s.mode === "Quad"
                            enabled: s.editable && s.ready
                            tooltipText: "Click four corners to draw a mask."
                            onClicked: ui.setMode("Quad")
                        }
                        ConsoleButton {
                            text: "Front"
                            shortcut: "F"
                            implicitHeight: 32
                            active: s.mode === "Front"
                            enabled: s.canFront
                            onClicked: ui.setMode("Front")
                        }

                        Rectangle { width: 1; height: 22; color: theme.borderSoft }

                        ConsoleButton {
                            objectName: "openTerrain"
                            text: s.terrainCount > 0 ? ("Terrain (" + s.terrainCount + ")") : "Terrain"
                            implicitHeight: 32
                            variant: "subtle"
                            enabled: s.editable
                            tooltipText: "Draw terrain polygons before starting playback."
                            onClicked: flow.open("terrain")
                        }
                        ConsoleButton {
                            objectName: "undoTerrain"
                            text: "Undo terrain"
                            implicitHeight: 32
                            variant: "dangerSubtle"
                            enabled: s.editable && s.terrainCount > 0
                            tooltipText: s.terrainCount > 0
                                         ? "Remove the most recently saved terrain polygon"
                                         : "No saved terrain polygons to remove"
                            onClicked: terrainDialogs.openUndoConfirm()
                        }

                        Rectangle { width: 1; height: 22; color: theme.borderSoft }

                        OverlayToggles {
                            uiState: s
                            prefix: "reg"
                        }
                    }

                    Text {
                        visible: window.width >= 1040
                        color: (s.replacingBound && (s.mode === "Rectangle" || s.mode === "Quad" || s.mode === "Points"))
                               ? theme.warning : theme.inkMuted
                        font.pixelSize: theme.textXs
                        font.weight: (s.replacingBound && (s.mode === "Rectangle" || s.mode === "Quad" || s.mode === "Points"))
                                     ? Font.DemiBold : Font.Normal
                        text: s.mode === "Front" ? "Click the front edge of the selected tray."
                              : s.mode === "Assign" ? "Click a mask to assign type, or click a terrain for Info."
                              : s.mode === "Rectangle" ? (s.replacingBound
                                    ? "Replacing " + s.selectedLabel + " · Drag to redraw · N for new mask."
                                    : "Drag to draw Mask " + s.selected + " · Ctrl+Z to undo.")
                              : s.mode === "Quad" ? (s.replacingBound
                                    ? "Replacing " + s.selectedLabel + " · " + s.manualVertices.length + "/4 corners · N for new mask."
                                    : "Mask " + s.selected + " · " + s.manualVertices.length + "/4 corners · Right-click removes vertex.")
                              : s.replacingBound ? "Editing " + s.selectedLabel + " · N starts a new unit."
                              : "Left: + point · Right: − point · Assign type to advance."
                    }
                }
            }

            // Registration terrain polygon toolbar
            Rectangle {
                visible: window.terrainMode
                Layout.fillWidth: true
                implicitHeight: regTerrainCol.implicitHeight + 14
                radius: theme.radiusLg
                color: theme.bgSurface
                border.color: theme.modeTerrainBorder
                clip: true

                Rectangle {
                    width: 3
                    height: parent.height
                    anchors.left: parent.left
                    color: theme.modeTerrainDot
                }

                ColumnLayout {
                    id: regTerrainCol
                    anchors.fill: parent
                    anchors.leftMargin: 15
                    anchors.rightMargin: 12
                    anchors.topMargin: 7
                    anchors.bottomMargin: 7
                    spacing: 7

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        Flow {
                            Layout.fillWidth: true
                            spacing: 8

                            Rectangle {
                                implicitWidth: regTerCntTxt.implicitWidth + 16
                                implicitHeight: 32
                                radius: theme.radiusSm
                                color: theme.modeTerrainSoft
                                border.color: theme.modeTerrainBorder
                                Text {
                                    id: regTerCntTxt
                                    anchors.centerIn: parent
                                    text: "Vertices · " + flow.state.pointCount
                                    color: theme.modeTerrain
                                    font.family: theme.fontMono
                                    font.pixelSize: theme.textXs
                                    font.weight: Font.DemiBold
                                }
                            }
                            ConsoleButton {
                                objectName: "saveTerrainPolygon"
                                text: "Save polygon"
                                primary: true
                                implicitHeight: 32
                                enabled: flow.state.pointCount >= 3
                                onClicked: flow.finishTerrain()
                            }
                            ConsoleButton {
                                text: s.terrainCount > 0 ? ("Undo terrain (" + s.terrainCount + ")") : "Undo terrain"
                                implicitHeight: 32
                                variant: "dangerSubtle"
                                enabled: s.editable && s.terrainCount > 0
                                tooltipText: s.terrainCount > 0
                                             ? "Remove the most recently saved terrain polygon"
                                             : "No saved terrain polygons to remove"
                                onClicked: terrainDialogs.openUndoConfirm()
                            }

                            Rectangle { width: 1; height: 22; color: theme.borderSoft }

                            OverlayToggles {
                                uiState: s
                                prefix: "ter"
                            }
                        }

                        ConsoleButton {
                            objectName: "exitTerrain"
                            text: "Done"
                            shortcut: "Esc"
                            implicitHeight: 32
                            onClicked: flow.action("cancel")
                        }
                    }

                    Text {
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                        color: theme.inkSecondary
                        font.pixelSize: theme.textXs
                        text: "Left click adds vertices (right click removes last). Save once ≥ 3 points, or select any saved terrain on the right to edit or delete."
                    }
                }
            }

            // Live / Auxiliary workflow controls
            WorkflowControls {
                id: workflowControls
                visible: window.live
                uiState: s
            }

            // Main stage + right panel
            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 10

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    spacing: 8

                    // Deep matte video/board stage
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        color: theme.bgStage
                        radius: theme.radiusLg
                        border.width: 1
                        border.color: (window.terrainMode || (window.live && window.flowKind !== "live")) ? window.badgeBorder : theme.border
                        clip: true

                        Image {
                            id: board
                            objectName: "boardImage"
                            anchors.fill: parent
                            anchors.margins: 1
                            source: "image://match/" + s.imageRevision
                            fillMode: Image.PreserveAspectFit
                            smooth: true
                            asynchronous: false
                            cache: false
                        }

                        Image {
                            id: boardOverlay
                            objectName: "boardOverlay"
                            anchors.fill: board
                            visible: Boolean(s.anyOverlay) && Boolean(s.hasOverlay) && (!window.live || window.flowKind === "live" || window.flowKind === "recovery" || window.flowKind === "debug")
                            source: "image://match/overlay/" + (s.overlayRevision || 0)
                            fillMode: Image.PreserveAspectFit
                            smooth: true
                            asynchronous: false
                            cache: false
                        }

                        Image {
                            id: boardInteractive
                            anchors.fill: board
                            visible: Boolean(s.hasInteractive) && (!window.live || window.flowKind !== "replay")
                            source: "image://match/interactive/" + (s.interactiveRevision || 0)
                            fillMode: Image.PreserveAspectFit
                            smooth: true
                            asynchronous: false
                            cache: false
                        }

                        Item {
                            id: surface
                            objectName: "boardSurface"
                            width: board.paintedWidth
                            height: board.paintedHeight
                            anchors.centerIn: parent
                            readonly property real scaleX: width / s.imageWidth
                            readonly property real scaleY: height / s.imageHeight
                            function imageRevision() { return Number(board.source.toString().split("/").pop()) }
                            onWidthChanged: if (width > 0 && height > 0) ui.setViewportSize(width, height)
                            onHeightChanged: if (width > 0 && height > 0) ui.setViewportSize(width, height)
                            Component.onCompleted: if (width > 0 && height > 0) ui.setViewportSize(width, height)

                            MouseArea {
                                id: boardPointer
                                objectName: "boardPointer"
                                property bool rectGesture: false
                                property bool rectForRecovery: false
                                property bool skipNextClick: false
                                property real startX: 0
                                property real startY: 0
                                property int startRevision: 0
                                readonly property real dragX: Math.max(0, Math.min(width, mouseX))
                                readonly property real dragY: Math.max(0, Math.min(height, mouseY))
                                anchors.fill: parent
                                acceptedButtons: Qt.LeftButton | Qt.RightButton
                                enabled: board.status === Image.Ready && window.flowKind !== "debug"
                                         && (window.live || !s.locked || window.table)
                                cursorShape: (window.live && window.flowKind === "recovery") ? Qt.CrossCursor
                                             : window.live ? Qt.PointingHandCursor
                                             : (window.table || window.terrainMode || s.mode !== "Assign") ? Qt.CrossCursor : Qt.PointingHandCursor
                                onPressed: mouse => {
                                    surface.forceActiveFocus()
                                    const regRect = s.editable && !window.terrainMode && s.mode === "Rectangle"
                                    rectForRecovery = window.recoveryRectMode
                                    rectGesture = (regRect || rectForRecovery) && mouse.button === Qt.LeftButton
                                    skipNextClick = false
                                    startX = mouse.x
                                    startY = mouse.y
                                    startRevision = surface.imageRevision()
                                }
                                onReleased: mouse => {
                                    if (rectGesture && mouse.button === Qt.LeftButton) {
                                        const forRec = rectForRecovery
                                        rectGesture = false
                                        rectForRecovery = false
                                        skipNextClick = true
                                        if (Math.abs(dragX - startX) >= 3 && Math.abs(dragY - startY) >= 3) {
                                            if (forRec) {
                                                flow.drawRecoveryRectangle(startX / surface.scaleX, startY / surface.scaleY,
                                                                           dragX / surface.scaleX, dragY / surface.scaleY)
                                            } else {
                                                ui.drawMaskRectangle(startX / surface.scaleX, startY / surface.scaleY,
                                                                     dragX / surface.scaleX, dragY / surface.scaleY, startRevision)
                                            }
                                        }
                                    }
                                }
                                onCanceled: {
                                    rectGesture = false
                                    rectForRecovery = false
                                    skipNextClick = false
                                }
                                onClicked: mouse => {
                                    if (skipNextClick && mouse.button === Qt.LeftButton) {
                                        skipNextClick = false
                                        return
                                    }
                                    skipNextClick = false
                                    ui.click(mouse.x / surface.scaleX, mouse.y / surface.scaleY,
                                             mouse.button === Qt.LeftButton, surface.imageRevision())
                                }

                                Rectangle {
                                    objectName: "manualRectPreview"
                                    visible: ((s.editable && !window.terrainMode && s.mode === "Rectangle") || window.recoveryRectMode)
                                             && boardPointer.rectGesture && (boardPointer.pressedButtons & Qt.LeftButton) !== 0
                                    x: Math.min(boardPointer.startX, boardPointer.dragX)
                                    y: Math.min(boardPointer.startY, boardPointer.dragY)
                                    width: Math.abs(boardPointer.startX - boardPointer.dragX)
                                    height: Math.abs(boardPointer.startY - boardPointer.dragY)
                                    color: boardPointer.rectForRecovery
                                           ? Qt.rgba(theme.warning.r, theme.warning.g, theme.warning.b, 0.18)
                                           : Qt.rgba(theme.selection.r, theme.selection.g, theme.selection.b, 0.16)
                                    border.color: boardPointer.rectForRecovery ? theme.warning : theme.selection
                                    border.width: 2
                                    z: 2
                                }
                            }

                            Repeater {
                                model: (s.editable && !window.terrainMode && s.mode === "Quad") ? s.manualVertices
                                     : window.recoveryQuadMode ? (flow.state.quadVertices || [])
                                     : []
                                Rectangle {
                                    required property var modelData
                                    x: modelData[0] * surface.scaleX - width / 2
                                    y: modelData[1] * surface.scaleY - height / 2
                                    width: 9
                                    height: 9
                                    radius: width / 2
                                    color: window.recoveryQuadMode ? theme.warning : theme.selection
                                    border.color: theme.bgTrack
                                    z: 2
                                }
                            }

                            DropArea {
                                anchors.fill: parent
                                keys: ["unit-recovery"]
                                enabled: flow.state.kind === "recovery"
                                onEntered: drag => flow.hoverRecovery(drag.x / surface.scaleX, drag.y / surface.scaleY)
                                onPositionChanged: drag => flow.hoverRecovery(drag.x / surface.scaleX, drag.y / surface.scaleY)
                                onExited: flow.clearRecoveryHover()
                                onDropped: drop => {
                                    flow.dropUnit(drop.source.unitId, drop.x / surface.scaleX, drop.y / surface.scaleY,
                                                  surface.imageRevision(), drop.source.candidateGeneration)
                                    drop.acceptProposedAction()
                                }
                            }

                            DropArea {
                                anchors.fill: parent
                                keys: ["unit-type"]
                                enabled: s.editable && !window.terrainMode && board.status === Image.Ready
                                onEntered: drag => ui.hoverType(drag.x / surface.scaleX, drag.y / surface.scaleY, surface.imageRevision())
                                onPositionChanged: drag => ui.hoverType(drag.x / surface.scaleX, drag.y / surface.scaleY, surface.imageRevision())
                                onExited: ui.clearHover()
                                onDropped: drop => {
                                    ui.dropType(drop.source.typeId, drop.x / surface.scaleX, drop.y / surface.scaleY, surface.imageRevision())
                                    drop.acceptProposedAction()
                                }
                            }

                            // Crisp vector rounded-pill unit & terrain badges (never intercept clicks)
                            BoardBadges {
                                objectName: "boardBadges"
                                anchors.fill: parent
                                z: 1
                                visible: Boolean(s.labels) && !window.table && (!window.live || window.flowKind === "live" || window.flowKind === "recovery" || window.flowKind === "debug" || window.flowKind === "replay")
                                badges: ui.badges
                                hoverObjectId: s.editable ? (s.hoverObjectId || -1) : -1
                                selectedUnitId: window.live && window.flowKind === "live" ? (s.console.unitId || "") : ""
                                targetUnitId: window.live && window.flowKind === "live" ? (s.console.targetId || "") : ""
                                selectedTerrainId: (!window.table && !window.live) ? (flow.state.selectedTerrainId || "") : ""
                            }
                        }

                        TerrainHud {
                            id: terrainHud
                            objectName: "terrainHud"
                            anchors.fill: parent
                            visible: s.terrain && !window.table && !window.live && !window.terrainMode && Boolean(flow.state.selectedTerrainId)
                            terrainData: flow.state.selectedTerrain || ({})
                            centerX: flow.state.terrainCenterX !== undefined ? flow.state.terrainCenterX : 0.5
                            centerY: flow.state.terrainCenterY !== undefined ? flow.state.terrainCenterY : 0.5
                            cardX: flow.state.terrainCardX !== undefined ? flow.state.terrainCardX : 0.35
                            cardY: flow.state.terrainCardY !== undefined ? flow.state.terrainCardY : 0.5
                            infoOpen: Boolean(flow.state.terrainInfoOpen)
                            z: 2
                            imageRect: Qt.rect(surface.x, surface.y, surface.width, surface.height)
                        }

                        UnitHud {
                            anchors.fill: parent
                            visible: window.live && window.flowKind === "live" && ui.console.selected
                            viewData: ui.console
                            z: 2
                            imageRect: Qt.rect(surface.x, surface.y, surface.width, surface.height)
                        }

                        DistanceLabel {
                            anchors.fill: parent
                            visible: window.live && window.flowKind === "live" && s.console.query.showDistance
                            query: s.console.query
                            z: 3
                            imageRect: Qt.rect(surface.x, surface.y, surface.width, surface.height)
                        }
                    }

                    // Table setup card
                    Rectangle {
                        visible: window.table
                        Layout.fillWidth: true
                        implicitHeight: tableCardCol.implicitHeight + 24
                        radius: theme.radiusLg
                        color: theme.bgSurface
                        border.color: theme.border

                        ColumnLayout {
                            id: tableCardCol
                            anchors.fill: parent
                            anchors.margins: 12
                            spacing: 10

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 10
                                Rectangle {
                                    implicitWidth: stepChip.implicitWidth + 14
                                    implicitHeight: 22
                                    radius: height / 2
                                    color: theme.accentSoft
                                    border.color: theme.accentBorder
                                    Text {
                                        id: stepChip
                                        anchors.centerIn: parent
                                        text: s.tableMode === "dimensions" ? "STEP 2 / 2" : "STEP 1 / 2"
                                        color: theme.selection
                                        font.family: theme.fontMono
                                        font.pixelSize: theme.textXs
                                        font.weight: Font.DemiBold
                                    }
                                }
                                Text {
                                    text: s.tableMode === "dimensions" ? "Confirm physical table dimensions"
                                          : s.tableMode === "detecting" ? "Finding table corners…"
                                          : s.tableMode === "manual" ? "Mark four table corners · " + s.cornerCount + " / 4"
                                          : "Are the table corners aligned?"
                                    color: theme.ink
                                    font.family: theme.fontDisplay
                                    font.pixelSize: theme.textLg
                                    font.weight: Font.DemiBold
                                    Layout.fillWidth: true
                                }
                                Text {
                                    visible: window.width >= 940
                                    text: s.tableMode === "dimensions" ? "Entered dimensions scale millimetre measurements."
                                          : "Keep TL / TR / BR / BL on the physical table corners."
                                    color: theme.inkMuted
                                    font.pixelSize: theme.textXs
                                }
                            }

                            RowLayout {
                                visible: s.tableMode !== "dimensions"
                                spacing: 8
                                ConsoleButton {
                                    objectName: "confirmCorners"
                                    text: "Yes · Continue"
                                    primary: true
                                    enabled: s.canConfirmCorners
                                    onClicked: ui.reviewDimensions()
                                }
                                ConsoleButton {
                                    objectName: "manualCorners"
                                    text: s.tableMode === "manual" ? "Clear" : "Manual correction"
                                    onClicked: ui.manualCorners()
                                }
                                ConsoleButton {
                                    text: "Auto detect"
                                    variant: "subtle"
                                    enabled: s.tableMode !== "detecting"
                                    onClicked: ui.detectCorners()
                                }
                            }

                            RowLayout {
                                visible: s.tableMode === "dimensions"
                                spacing: 10
                                Column {
                                    spacing: 4
                                    Text { text: "Length · TL → TR (in)"; color: theme.inkSecondary; font.pixelSize: theme.textXs; font.weight: Font.DemiBold }
                                    TextField {
                                        id: tableWidth
                                        objectName: "tableWidth"
                                        width: 150
                                        height: 34
                                        text: window.tableWidthDraft === null ? s.boardWidth : window.tableWidthDraft
                                        onTextEdited: window.tableWidthDraft = text
                                        selectByMouse: true
                                        color: theme.ink
                                        selectionColor: theme.accentSoft
                                        selectedTextColor: theme.ink
                                        font.family: theme.fontBody
                                        font.pixelSize: theme.textSm
                                        leftPadding: 10
                                        rightPadding: 10
                                        background: Rectangle {
                                            radius: theme.radiusSm
                                            color: theme.bgTrack
                                            border.width: tableWidth.activeFocus ? 1.5 : 1
                                            border.color: tableWidth.activeFocus ? theme.selection : theme.borderStrong
                                        }
                                        onAccepted: ui.confirmTable(tableWidth.text, tableDepth.text)
                                    }
                                }
                                Column {
                                    spacing: 4
                                    Text { text: "Width · TL → BL (in)"; color: theme.inkSecondary; font.pixelSize: theme.textXs; font.weight: Font.DemiBold }
                                    TextField {
                                        id: tableDepth
                                        objectName: "tableDepth"
                                        width: 150
                                        height: 34
                                        text: window.tableDepthDraft === null ? s.boardDepth : window.tableDepthDraft
                                        onTextEdited: window.tableDepthDraft = text
                                        selectByMouse: true
                                        color: theme.ink
                                        selectionColor: theme.accentSoft
                                        selectedTextColor: theme.ink
                                        font.family: theme.fontBody
                                        font.pixelSize: theme.textSm
                                        leftPadding: 10
                                        rightPadding: 10
                                        background: Rectangle {
                                            radius: theme.radiusSm
                                            color: theme.bgTrack
                                            border.width: tableDepth.activeFocus ? 1.5 : 1
                                            border.color: tableDepth.activeFocus ? theme.selection : theme.borderStrong
                                        }
                                        onAccepted: ui.confirmTable(tableWidth.text, tableDepth.text)
                                    }
                                }
                                ConsoleButton {
                                    text: "Continue"
                                    primary: true
                                    Layout.alignment: Qt.AlignBottom
                                    onClicked: ui.confirmTable(tableWidth.text, tableDepth.text)
                                }
                                ConsoleButton {
                                    text: "Back"
                                    variant: "subtle"
                                    Layout.alignment: Qt.AlignBottom
                                    onClicked: ui.backToCorners()
                                }
                            }
                        }
                    }
                }

                CatalogPanel {
                    visible: !window.table && !window.live && !window.terrainMode && !Boolean(flow.state.terrainInfoOpen)
                    Layout.preferredWidth: 300
                    Layout.fillHeight: true
                    state: s
                    dragLayer: Overlay.overlay
                    onImportRequested: side => { armyFile.side = side; armyFile.open() }
                }

                TerrainPanel {
                    id: terrainPanel
                    objectName: "terrainPanel"
                    visible: !window.table && !window.live && (window.terrainMode || Boolean(flow.state.terrainInfoOpen))
                    drawMode: window.terrainMode
                    Layout.preferredWidth: 300
                    Layout.fillHeight: true
                }

                RecoveryPanel {
                    visible: window.live && window.flowKind === "recovery"
                    Layout.preferredWidth: 270
                    Layout.fillHeight: true
                }

                UnitInfoPanel {
                    id: unitInfoPanel
                    visible: window.live && window.flowKind === "live" && Boolean(flow.state.profileOpen)
                    Layout.preferredWidth: window.width < 1000 ? 280 : 320
                    Layout.fillHeight: true
                }

                UncertaintyPanel {
                    visible: window.live && window.flowKind === "live" && !flow.state.profileOpen && ui.uncertainty.count > 0
                    Layout.preferredWidth: window.width < 1000 ? 260 : 300
                    Layout.fillHeight: true
                    viewData: ui.uncertainty
                    selectedUnit: s.console.unitId
                    onInspectRequested: unitId => ui.inspectUnit(unitId)
                }
            }

            LiveConsole {
                visible: window.live && window.flowKind === "live"
                Layout.fillWidth: true
                viewData: ui.console
                drawerHeight: Math.min(186, Math.max(150, window.height * 0.22))
            }
        }

        // Slim bottom telemetry footer
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: statusColumn.implicitHeight + 12
            color: theme.bgFooter

            Rectangle {
                anchors.top: parent.top
                width: parent.width
                height: 1
                color: theme.border
            }

            ColumnLayout {
                id: statusColumn
                anchors.fill: parent
                anchors.leftMargin: 16
                anchors.rightMargin: 16
                anchors.topMargin: 6
                anchors.bottomMargin: 6
                spacing: 4

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    Rectangle {
                        width: 7; height: 7; radius: 4
                        color: s.ready ? theme.success : s.loading ? theme.selection : theme.modeRecovery
                    }
                    Text {
                        text: s.modelLabel
                        color: s.ready ? theme.success : s.loading ? theme.selection : theme.modeRecovery
                        font.pixelSize: theme.textSm
                        font.weight: Font.DemiBold
                    }
                    ProgressBar {
                        visible: s.loading
                        indeterminate: s.progress < 0
                        value: Math.max(0, s.progress)
                        Layout.preferredWidth: 120
                    }
                    Text {
                        visible: (s.note || "").length > 0
                        text: "·"
                        color: theme.inkMuted
                        font.pixelSize: theme.textXs
                    }
                    Text {
                        objectName: "statusNote"
                        visible: (s.note || "").length > 0
                        text: s.note
                        color: s.noticeError ? theme.warning : theme.inkSecondary
                        font.pixelSize: theme.textXs
                        font.weight: s.noticeError ? Font.DemiBold : Font.Normal
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                        ToolTip.visible: noteHover.containsMouse && truncated
                        ToolTip.text: s.note
                        MouseArea { id: noteHover; anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.NoButton }
                    }
                    Item {
                        visible: (s.note || "").length === 0
                        Layout.fillWidth: true
                    }
                    Text {
                        text: "Src " + s.sourceTime + "s · Mask " + s.observationTime + "s · Geom " + s.geometryTime + "s"
                        color: theme.inkMuted
                        font.family: theme.fontMono
                        font.pixelSize: theme.textXs
                    }
                }

                Text {
                    Layout.fillWidth: true
                    visible: s.historyWarning.length > 0
                    text: s.historyWarning
                    color: theme.modeRecovery
                    font.pixelSize: theme.textXs
                    font.weight: Font.DemiBold
                    wrapMode: Text.WordWrap
                }
            }
        }
    }

    FileDialog {
        id: registrationFile
        title: "Load registration · select prompts.json"
        currentFolder: s.archivesFolder
        nameFilters: ["Registration (prompts.json)"]
        onAccepted: ui.loadArchive(selectedFile)
    }
    FileDialog {
        id: armyFile
        property string side: "A"
        title: "Import list " + side
        currentFolder: s.inputsFolder
        nameFilters: ["Army lists (*.pdf *.json)", "PDF (*.pdf)", "JSON (*.json)"]
        onAccepted: ui.importList(selectedFile, side)
    }
    Dialog {
        id: resetDialog
        anchors.centerIn: parent
        modal: true
        title: "Start a new registration?"
        standardButtons: Dialog.Yes | Dialog.No
        Overlay.modal: Rectangle { color: theme.scrim }
        background: Rectangle {
            color: theme.bgSurface
            radius: theme.radiusLg
            border.color: theme.borderStrong
        }
        header: Rectangle {
            implicitHeight: 44
            color: "transparent"
            Text {
                anchors.verticalCenter: parent.verticalCenter
                anchors.left: parent.left
                anchors.leftMargin: 18
                text: resetDialog.title
                color: theme.ink
                font.family: theme.fontDisplay
                font.pixelSize: theme.textLg
                font.weight: Font.DemiBold
            }
        }
        Label {
            text: "Current drafts will be cleared. Saved references are kept."
            color: theme.inkSecondary
            font.pixelSize: theme.textSm
        }
        onAccepted: ui.reset()
    }
    TerrainDialogs {
        id: terrainDialogs
    }
    Shortcut { sequences: [StandardKey.Undo]; enabled: !window.live && !window.modalOpen && !window.textInputActive; onActivated: ui.undo() }
    Shortcut { sequence: "N"; enabled: s.editable && !window.terrainMode && !window.modalOpen && !window.textInputActive; onActivated: ui.newObject() }
    Shortcut { sequence: "F"; enabled: s.canFront && !window.terrainMode && !window.modalOpen && !window.textInputActive; onActivated: ui.setMode("Front") }
    Shortcut { sequence: "S"; enabled: s.editable && s.ready && !window.terrainMode && !window.modalOpen && !window.textInputActive; onActivated: ui.finish() }
    Shortcut { sequence: "Space"; enabled: s.ready && !window.table && !window.live && !window.terrainMode && !window.modalOpen && !window.textInputActive; onActivated: ui.start() }
    Shortcut { sequence: "Tab"; enabled: s.editable && !window.terrainMode && !window.modalOpen
                 && (!window.activeFocusItem || window.activeFocusItem === window.contentItem || window.activeFocusItem === surface); onActivated: ui.setMode(s.mode === "Assign" ? "Points" : "Assign") }
    Shortcut { sequence: "O"; enabled: !window.table && !window.modalOpen && !window.textInputActive; onActivated: ui.toggleAllOverlays() }
    Shortcut { sequence: "Escape"; enabled: window.terrainMode && !window.modalOpen && !window.textInputActive; onActivated: flow.action("cancel") }
    Shortcut {
        sequence: "Escape"
        enabled: !window.table && !window.live && !window.terrainMode && !window.modalOpen && !window.textInputActive
                 && (Boolean(flow.state.terrainInfoOpen) || Boolean(flow.state.selectedTerrainId))
        onActivated: flow.state.terrainInfoOpen ? flow.closeTerrainInfo() : flow.clearTerrainSelection()
    }
    Shortcut { sequence: "D"; enabled: window.live && window.flowKind === "live" && s.console.canQuery && !window.modalOpen && !window.textInputActive; onActivated: ui.liveTool("distance") }
    Shortcut { sequence: "L"; enabled: window.live && window.flowKind === "live" && s.console.canQuery && !window.modalOpen && !window.textInputActive; onActivated: ui.liveTool("los") }
    Shortcut { sequence: "V"; enabled: window.live && window.flowKind === "live" && s.console.canQuery && !window.modalOpen && !window.textInputActive; onActivated: ui.liveTool("move") }
    Shortcut { sequences: ["Left", "A"]; enabled: window.flowKind === "replay" && !window.modalOpen && !window.textInputActive; onActivated: flow.action("previous") }
    Shortcut { sequences: ["Right", "D"]; enabled: window.flowKind === "replay" && !window.modalOpen && !window.textInputActive; onActivated: flow.action("next") }
    Shortcut { sequences: [StandardKey.Undo]; enabled: window.recoveryQuadMode && !window.modalOpen && !window.textInputActive; onActivated: flow.undoRecoveryVertex() }
    Shortcut { sequence: "Escape"; enabled: window.live && !window.modalOpen && !window.textInputActive; onActivated: flow.state.profileOpen ? flow.closeProfile() : ui.escapeLive() }
    Shortcut { sequences: ["Q", "Space"]; enabled: window.live && window.flowKind === "live" && !window.modalOpen && !window.textInputActive; onActivated: ui.clearSelection() }
}
