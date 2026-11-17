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
    readonly property bool modalOpen: resetDialog.visible || armyFile.visible || registrationFile.visible || workflowControls.formOpen

    readonly property string badgeText: {
        if (window.table) return "TABLE SETUP"
        if (!window.live) return "REGISTER"
        if (flowKind === "replay") return "REPLAY"
        if (flowKind === "recovery") return "RECOVERY"
        if (flowKind === "recalibrate") return "RECALIBRATE"
        if (flowKind === "terrain") return "TERRAIN"
        return "LIVE"
    }
    readonly property color badgeColor: {
        if (window.table) return theme.inkSecondary
        if (!window.live) return theme.selection
        if (flowKind === "replay") return theme.modeReplay
        if (flowKind === "recovery") return theme.modeRecovery
        if (flowKind === "recalibrate") return theme.modeRecalibrate
        if (flowKind === "terrain") return theme.modeTerrain
        return theme.modeLive
    }
    readonly property color badgeDot: {
        if (window.table) return theme.selection
        if (!window.live) return theme.accentHover
        if (flowKind === "replay") return theme.modeReplayDot
        if (flowKind === "recovery") return theme.modeRecoveryDot
        if (flowKind === "recalibrate") return theme.modeRecalibrateDot
        if (flowKind === "terrain") return theme.modeTerrainDot
        return theme.modeLiveDot
    }
    readonly property color badgeSoft: {
        if (window.table) return theme.bgTrack
        if (!window.live) return theme.accentSoft
        if (flowKind === "replay") return theme.modeReplaySoft
        if (flowKind === "recovery") return theme.modeRecoverySoft
        if (flowKind === "recalibrate") return theme.modeRecalibrateSoft
        if (flowKind === "terrain") return theme.modeTerrainSoft
        return theme.modeLiveSoft
    }
    readonly property color badgeBorder: {
        if (window.table) return theme.borderStrong
        if (!window.live) return theme.accentBorder
        if (flowKind === "replay") return theme.modeReplayBorder
        if (flowKind === "recovery") return theme.modeRecoveryBorder
        if (flowKind === "recalibrate") return theme.modeRecalibrateBorder
        if (flowKind === "terrain") return theme.modeTerrainBorder
        return theme.modeLiveBorder
    }

    title: {
        if (window.table) return "Match console · Table setup"
        if (!window.live) return "Match console · Unit registration"
        if (flowKind === "replay") return "Match console · Replay"
        if (flowKind === "recovery") return "Match console · Recovery"
        if (flowKind === "recalibrate") return "Match console · Recalibrate"
        if (flowKind === "terrain") return "Match console · Terrain"
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
                        if (!window.live) return "Build the starting board"
                        if (flowKind === "replay") return "Historical board"
                        if (flowKind === "recovery") return "Scoped unit recovery"
                        if (flowKind === "recalibrate") return "Board corner alignment"
                        if (flowKind === "terrain") return "Terrain polygon editor"
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
                            enabled: !flow.state.busy
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
                visible: !window.table && !window.live
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
                            text: "Front"
                            shortcut: "F"
                            implicitHeight: 32
                            active: s.mode === "Front"
                            enabled: s.canFront
                            onClicked: ui.setMode("Front")
                        }

                        Rectangle { width: 1; height: 22; color: theme.borderSoft }

                        Button {
                            id: regMaskPill
                            implicitHeight: 32
                            leftPadding: 11; rightPadding: 11
                            onClicked: ui.setOverlay("masks", !s.masks)
                            background: Rectangle {
                                radius: theme.radiusMd
                                color: s.masks ? (regMaskPill.hovered ? theme.bgElevated : theme.accentSoft)
                                               : (regMaskPill.hovered ? theme.bgElevated : theme.bgSubtle)
                                border.color: s.masks ? theme.accentBorder : theme.border
                            }
                            contentItem: RowLayout {
                                spacing: 6
                                Rectangle { width: 8; height: 8; radius: 4; color: s.masks ? theme.selection : theme.borderStrong }
                                Text {
                                    text: "Masks"
                                    font.pixelSize: theme.textSm
                                    font.weight: s.masks ? Font.DemiBold : Font.Normal
                                    color: s.masks ? theme.ink : theme.inkSecondary
                                }
                            }
                        }

                        Button {
                            id: regTrayPill
                            implicitHeight: 32
                            leftPadding: 11; rightPadding: 11
                            onClicked: ui.setOverlay("trays", !s.trays)
                            background: Rectangle {
                                radius: theme.radiusMd
                                color: s.trays ? (regTrayPill.hovered ? theme.bgElevated : theme.accentSoft)
                                               : (regTrayPill.hovered ? theme.bgElevated : theme.bgSubtle)
                                border.color: s.trays ? theme.accentBorder : theme.border
                            }
                            contentItem: RowLayout {
                                spacing: 6
                                Rectangle { width: 8; height: 8; radius: 4; color: s.trays ? theme.selection : theme.borderStrong }
                                Text {
                                    text: "Trays"
                                    font.pixelSize: theme.textSm
                                    font.weight: s.trays ? Font.DemiBold : Font.Normal
                                    color: s.trays ? theme.ink : theme.inkSecondary
                                }
                            }
                        }
                    }

                    Text {
                        visible: window.width >= 1040
                        color: theme.inkMuted
                        font.pixelSize: theme.textXs
                        text: s.mode === "Front" ? "Click the front edge of the selected tray."
                              : s.mode === "Assign" ? "Click a mask, then choose its type."
                              : "Left: + point · Right: − point · Assign type to advance."
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
                        border.color: (window.live && window.flowKind !== "live") ? window.badgeBorder : theme.border
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
                            anchors.fill: board
                            visible: Boolean(s.hasOverlay) && (!window.live || window.flowKind === "live" || window.flowKind === "recovery")
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

                            MouseArea {
                                anchors.fill: parent
                                acceptedButtons: Qt.LeftButton | Qt.RightButton
                                enabled: board.status === Image.Ready && (window.live || !s.locked || window.table)
                                cursorShape: window.live ? Qt.PointingHandCursor
                                             : (window.table || s.mode !== "Assign") ? Qt.CrossCursor : Qt.PointingHandCursor
                                onClicked: mouse => ui.click(mouse.x / surface.scaleX, mouse.y / surface.scaleY,
                                                             mouse.button === Qt.LeftButton, surface.imageRevision())
                            }

                            DropArea {
                                anchors.fill: parent
                                keys: ["unit-recovery"]
                                enabled: flow.state.kind === "recovery"
                                onDropped: drop => {
                                    flow.dropUnit(drop.source.unitId, drop.x / surface.scaleX, drop.y / surface.scaleY,
                                                  surface.imageRevision(), drop.source.candidateGeneration)
                                    drop.acceptProposedAction()
                                }
                            }

                            DropArea {
                                anchors.fill: parent
                                keys: ["unit-type"]
                                enabled: s.editable && board.status === Image.Ready
                                onDropped: drop => {
                                    ui.dropType(drop.source.typeId, drop.x / surface.scaleX, drop.y / surface.scaleY, surface.imageRevision())
                                    drop.acceptProposedAction()
                                }
                            }

                            // Crisp vector rounded-pill unit & terrain badges (never intercept clicks)
                            BoardBadges {
                                anchors.fill: parent
                                z: 1
                                visible: !window.table && (!window.live || window.flowKind === "live" || window.flowKind === "recovery" || window.flowKind === "replay")
                                badges: ui.badges
                                selectedUnitId: window.live && window.flowKind === "live" ? (s.console.unitId || "") : ""
                                targetUnitId: window.live && window.flowKind === "live" ? (s.console.targetId || "") : ""
                            }
                        }

                        UnitHud {
                            anchors.fill: parent
                            visible: window.live && window.flowKind === "live" && s.console.selected
                            viewData: s.console
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
                                        text: s.boardWidth
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
                                        text: s.boardDepth
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
                    visible: !window.table && !window.live
                    Layout.preferredWidth: 300
                    Layout.fillHeight: true
                    state: s
                    dragLayer: Overlay.overlay
                    onImportRequested: side => { armyFile.side = side; armyFile.open() }
                }

                RecoveryPanel {
                    visible: window.live && window.flowKind === "recovery"
                    Layout.preferredWidth: 270
                    Layout.fillHeight: true
                }

                UncertaintyPanel {
                    visible: window.live && window.flowKind === "live" && ui.uncertainty.count > 0
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
                viewData: s.console
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
                        color: theme.inkSecondary
                        font.pixelSize: theme.textXs
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
    Shortcut { sequences: [StandardKey.Undo]; enabled: !window.live && !window.modalOpen; onActivated: ui.undo() }
    Shortcut { sequence: "N"; enabled: s.editable && !window.modalOpen; onActivated: ui.newObject() }
    Shortcut { sequence: "F"; enabled: s.canFront && !window.modalOpen; onActivated: ui.setMode("Front") }
    Shortcut { sequence: "S"; enabled: s.editable && !window.modalOpen; onActivated: ui.finish() }
    Shortcut { sequence: "Space"; enabled: !window.table && !window.live && !window.modalOpen; onActivated: ui.start() }
    Shortcut { sequence: "Tab"; enabled: s.editable && !window.modalOpen; onActivated: ui.setMode(s.mode === "Assign" ? "Points" : "Assign") }
    Shortcut { sequence: "D"; enabled: window.live && window.flowKind === "live" && s.console.canQuery && !window.modalOpen; onActivated: ui.liveTool("distance") }
    Shortcut { sequence: "L"; enabled: window.live && window.flowKind === "live" && s.console.canQuery && !window.modalOpen; onActivated: ui.liveTool("los") }
    Shortcut { sequence: "V"; enabled: window.live && window.flowKind === "live" && s.console.canQuery && !window.modalOpen; onActivated: ui.liveTool("move") }
    Shortcut { sequences: ["Left", "A"]; enabled: window.flowKind === "replay" && !window.modalOpen; onActivated: flow.action("previous") }
    Shortcut { sequences: ["Right", "D"]; enabled: window.flowKind === "replay" && !window.modalOpen; onActivated: flow.action("next") }
    Shortcut { sequence: "Escape"; enabled: window.live && !window.modalOpen; onActivated: ui.escapeLive() }
    Shortcut { sequences: ["Q", "Space"]; enabled: window.live && !window.modalOpen; onActivated: ui.clearSelection() }
}
