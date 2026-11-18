import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: controls
    required property var uiState
    property bool replayDetailsOpen: false
    readonly property bool formOpen: editor.visible || undoTerrainDialog.visible
    readonly property Theme theme: Theme {}
    readonly property string kind: (flow.state && flow.state.kind) ? flow.state.kind : "live"
    readonly property var replayInfo: (flow.state && flow.state.replayInfo) ? flow.state.replayInfo : ({})
    Layout.fillWidth: true
    spacing: 8

    readonly property color modeAccent: {
        if (kind === "replay") return theme.modeReplay
        if (kind === "recovery") return theme.modeRecovery
        if (kind === "recalibrate") return theme.modeRecalibrate
        if (kind === "terrain") return theme.modeTerrain
        return theme.accent
    }
    readonly property color modeDot: {
        if (kind === "replay") return theme.modeReplayDot
        if (kind === "recovery") return theme.modeRecoveryDot
        if (kind === "recalibrate") return theme.modeRecalibrateDot
        if (kind === "terrain") return theme.modeTerrainDot
        return theme.accent
    }
    readonly property color modeSoft: {
        if (kind === "replay") return theme.modeReplaySoft
        if (kind === "recovery") return theme.modeRecoverySoft
        if (kind === "recalibrate") return theme.modeRecalibrateSoft
        if (kind === "terrain") return theme.modeTerrainSoft
        return theme.bgSurface
    }
    readonly property color modeBorder: {
        if (kind === "replay") return theme.modeReplayBorder
        if (kind === "recovery") return theme.modeRecoveryBorder
        if (kind === "recalibrate") return theme.modeRecalibrateBorder
        if (kind === "terrain") return theme.modeTerrainBorder
        return theme.border
    }

    // Inline layer toggle pill
    component LayerPill: Button {
        id: pill
        property bool checkedState: true
        property string badgeText: ""
        readonly property Theme t: controls.theme
        implicitHeight: 32
        leftPadding: 11
        rightPadding: 11
        background: Rectangle {
            radius: pill.t.radiusMd
            color: pill.checkedState ? (pill.hovered ? pill.t.bgElevated : pill.t.accentSoft)
                                     : (pill.hovered ? pill.t.bgElevated : pill.t.bgSubtle)
            border.color: pill.checkedState ? pill.t.accentBorder : pill.t.border
        }
        contentItem: RowLayout {
            spacing: 6
            Rectangle {
                width: 8; height: 8; radius: 4
                color: pill.checkedState ? pill.t.selection : pill.t.borderStrong
            }
            Text {
                text: pill.text
                font.family: pill.t.fontBody
                font.pixelSize: pill.t.textSm
                font.weight: pill.checkedState ? Font.DemiBold : Font.Normal
                color: pill.checkedState ? pill.t.ink : pill.t.inkSecondary
            }
            Rectangle {
                visible: pill.badgeText.length > 0
                implicitWidth: bTxt.implicitWidth + 8
                implicitHeight: 17
                radius: pill.t.radiusXs
                color: pill.t.bgTrack
                Text {
                    id: bTxt
                    anchors.centerIn: parent
                    text: pill.badgeText
                    font.family: pill.t.fontMono
                    font.pixelSize: pill.t.textXs
                    color: pill.checkedState ? pill.t.selection : pill.t.inkMuted
                }
            }
        }
    }

    // Styled dark numeric/text field
    component DarkField: TextField {
        id: df
        readonly property Theme t: controls.theme
        color: t.ink
        placeholderTextColor: t.inkMuted
        selectionColor: t.accentSoft
        selectedTextColor: t.ink
        font.family: t.fontBody
        font.pixelSize: t.textSm
        leftPadding: 10
        rightPadding: 10
        background: Rectangle {
            radius: df.t.radiusSm
            color: df.t.bgTrack
            border.width: df.activeFocus ? 1.5 : 1
            border.color: df.activeFocus ? df.t.selection : (df.hovered ? df.t.borderStrong : df.t.border)
        }
    }

    Rectangle {
        Layout.fillWidth: true
        implicitHeight: barContent.implicitHeight + 14
        radius: controls.theme.radiusLg
        color: controls.theme.bgSurface
        border.color: controls.kind === "live" ? controls.theme.border : controls.modeBorder
        clip: true

        Rectangle {
            visible: controls.kind !== "live"
            width: 3
            height: parent.height
            anchors.left: parent.left
            color: controls.modeDot
        }

        ColumnLayout {
            id: barContent
            anchors.fill: parent
            anchors.leftMargin: controls.kind !== "live" ? 15 : 12
            anchors.rightMargin: 12
            anchors.topMargin: 7
            anchors.bottomMargin: 7
            spacing: 7

            // Live unified toolbar
            RowLayout {
                visible: controls.kind === "live"
                Layout.fillWidth: true
                spacing: 8

                Flow {
                    Layout.fillWidth: true
                    spacing: 6

                    ConsoleButton {
                        text: "Select"
                        implicitHeight: 32
                        primary: controls.uiState.console.tool === "select"
                        onClicked: ui.doneTool()
                    }

                    Rectangle { width: 1; height: 22; color: controls.theme.borderSoft }

                    LayerPill {
                        text: "Masks"
                        checkedState: controls.uiState.masks
                        onClicked: ui.setOverlay("masks", !controls.uiState.masks)
                    }
                    LayerPill {
                        text: "Trays"
                        checkedState: controls.uiState.trays
                        onClicked: ui.setOverlay("trays", !controls.uiState.trays)
                    }

                    Rectangle { width: 1; height: 22; color: controls.theme.borderSoft }

                    ConsoleButton {
                        text: "Unit information"
                        implicitHeight: 32
                        variant: Boolean(flow.state && flow.state.profileOpen) ? "default" : "subtle"
                        primary: Boolean(flow.state && flow.state.profileOpen)
                        enabled: controls.uiState.console.selected
                        tooltipText: controls.uiState.console.selected
                                     ? ("View profile and edit rule attributes for " + controls.uiState.console.unitId)
                                     : "Select a unit on the board first"
                        onClicked: (flow.state && flow.state.profileOpen) ? flow.closeProfile() : flow.open("profile")
                    }
                    ConsoleButton {
                        text: "Recover units"
                        implicitHeight: 32
                        variant: "subtle"
                        onClicked: flow.open("recover")
                    }
                    ConsoleButton {
                        text: "Recalibrate"
                        implicitHeight: 32
                        variant: "subtle"
                        onClicked: flow.open("recalibrate")
                    }
                    ConsoleButton {
                        text: "Terrain"
                        implicitHeight: 32
                        variant: "subtle"
                        onClicked: flow.open("terrain")
                    }
                    ConsoleButton {
                        text: "Undo terrain"
                        implicitHeight: 32
                        variant: "dangerSubtle"
                        enabled: controls.uiState.terrainCount > 0
                        tooltipText: controls.uiState.terrainCount > 0
                                     ? "Remove the most recently saved terrain polygon"
                                     : "No saved terrain polygons to remove"
                        onClicked: undoTerrainDialog.open()
                    }
                    ConsoleButton {
                        text: "Debug"
                        implicitHeight: 32
                        variant: "subtle"
                        enabled: !controls.uiState.pendingPlay
                        onClicked: flow.open("debug")
                    }
                }
            }

            // Sub-workflow contextual bars (Recovery / Recalibrate / Terrain / Replay)
            RowLayout {
                visible: controls.kind !== "live"
                Layout.fillWidth: true
                spacing: 8

                Flow {
                    Layout.fillWidth: true
                    spacing: 8

                    ConsoleButton {
                        visible: controls.kind === "debug"
                        text: "Save snapshot"
                        primary: true
                        implicitHeight: 32
                        onClicked: flow.action("saveDebug")
                    }
                    LayerPill {
                        visible: controls.kind === "debug"
                        text: "Masks"
                        checkedState: controls.uiState.masks
                        onClicked: ui.setOverlay("masks", !controls.uiState.masks)
                    }
                    LayerPill {
                        visible: controls.kind === "debug"
                        text: "Trays"
                        checkedState: controls.uiState.trays
                        onClicked: ui.setOverlay("trays", !controls.uiState.trays)
                    }

                    // Replay header title & action delta (no button border)
                    RowLayout {
                        visible: controls.kind === "replay"
                        height: 32
                        spacing: 8

                        Text {
                            text: controls.replayInfo.stepText || "Replay"
                            color: controls.theme.ink
                            font.family: controls.theme.fontDisplay
                            font.pixelSize: controls.theme.textLg
                            font.weight: Font.DemiBold
                        }

                        Rectangle {
                            visible: (controls.replayInfo.stepLabel || "").length > 0
                            implicitWidth: stepKindTxt.implicitWidth + 14
                            implicitHeight: 22
                            radius: height / 2
                            color: controls.theme.modeReplaySoft
                            border.color: controls.theme.modeReplayBorder
                            Text {
                                id: stepKindTxt
                                anchors.centerIn: parent
                                text: controls.replayInfo.stepLabel || ""
                                color: controls.theme.modeReplay
                                font.pixelSize: controls.theme.textXs
                                font.weight: Font.DemiBold
                            }
                        }

                        Rectangle {
                            visible: (controls.replayInfo.stepUnit || "").length > 0
                            implicitWidth: stepUnitRow.implicitWidth + 14
                            implicitHeight: 22
                            radius: height / 2
                            color: controls.replayInfo.stepSide === "B" ? controls.theme.sideBSoft
                                   : controls.replayInfo.stepSide === "A" ? controls.theme.sideASoft
                                   : controls.theme.bgSubtle
                            border.color: controls.theme.selection
                            RowLayout {
                                id: stepUnitRow
                                anchors.centerIn: parent
                                spacing: 5
                                Rectangle {
                                    width: 7; height: 7; radius: 4
                                    color: controls.replayInfo.stepSide === "B" ? controls.theme.sideB
                                           : controls.replayInfo.stepSide === "A" ? controls.theme.sideA
                                           : controls.theme.selection
                                }
                                Text {
                                    text: controls.replayInfo.stepUnit || ""
                                    color: controls.theme.ink
                                    font.pixelSize: controls.theme.textXs
                                    font.weight: Font.DemiBold
                                }
                            }
                        }

                        Text {
                            visible: (controls.replayInfo.stepSummary || "").length > 0
                            text: controls.replayInfo.stepSummary || ""
                            color: controls.theme.selection
                            font.family: controls.theme.fontMono
                            font.pixelSize: controls.theme.textSm
                            font.weight: Font.DemiBold
                        }
                    }

                    ConsoleButton {
                        text: "Previous"
                        shortcut: "A"
                        implicitHeight: 32
                        visible: controls.kind === "replay"
                        enabled: flow.state.step > 0
                        onClicked: flow.action("previous")
                    }
                    ConsoleButton {
                        text: "Next"
                        shortcut: "D"
                        implicitHeight: 32
                        visible: controls.kind === "replay"
                        enabled: flow.state.step + 1 < flow.state.steps
                        onClicked: flow.action("next")
                    }
                    ConsoleButton {
                        text: "Refresh"
                        variant: "subtle"
                        implicitHeight: 32
                        visible: controls.kind === "replay"
                        onClicked: flow.action("refresh")
                    }

                    // Recovery controls
                    Rectangle {
                        visible: controls.kind === "recovery"
                        implicitWidth: recCandTxt.implicitWidth + 16
                        implicitHeight: 32
                        radius: controls.theme.radiusSm
                        color: controls.modeSoft
                        border.color: controls.modeBorder
                        Text {
                            id: recCandTxt
                            anchors.centerIn: parent
                            text: "Candidate · " + flow.state.candidateTime
                            color: controls.modeAccent
                            font.family: controls.theme.fontMono
                            font.pixelSize: controls.theme.textXs
                            font.weight: Font.DemiBold
                        }
                    }
                    ConsoleButton {
                        text: "Correct"
                        primary: true
                        implicitHeight: 32
                        visible: controls.kind === "recovery" && flow.state.review
                        enabled: !flow.state.busy
                        onClicked: flow.action("correct")
                    }
                    ConsoleButton {
                        text: "No / Search again"
                        implicitHeight: 32
                        visible: controls.kind === "recovery" && flow.state.review
                        enabled: !flow.state.busy
                        onClicked: flow.action("reject")
                    }
                    ConsoleButton {
                        text: "Clear / Retry"
                        variant: "subtle"
                        implicitHeight: 32
                        visible: controls.kind === "recovery"
                        enabled: !flow.state.busy
                        onClicked: flow.action("clear")
                    }

                    // Terrain controls
                    Rectangle {
                        visible: controls.kind === "terrain"
                        implicitWidth: terCntTxt.implicitWidth + 16
                        implicitHeight: 32
                        radius: controls.theme.radiusSm
                        color: controls.modeSoft
                        border.color: controls.modeBorder
                        Text {
                            id: terCntTxt
                            anchors.centerIn: parent
                            text: "Vertices · " + flow.state.pointCount
                            color: controls.modeAccent
                            font.family: controls.theme.fontMono
                            font.pixelSize: controls.theme.textXs
                            font.weight: Font.DemiBold
                        }
                    }
                    ConsoleButton {
                        text: "Save polygon"
                        primary: true
                        implicitHeight: 32
                        visible: controls.kind === "terrain"
                        enabled: flow.state.pointCount >= 3
                        onClicked: flow.finishTerrain()
                    }

                    // Recalibrate inline inputs
                    RowLayout {
                        visible: controls.kind === "recalibrate"
                        spacing: 8
                        onVisibleChanged: if (visible) { length.text = controls.uiState.boardWidth; depth.text = controls.uiState.boardDepth }

                        Rectangle {
                            implicitWidth: calCntTxt.implicitWidth + 14
                            implicitHeight: 32
                            radius: controls.theme.radiusSm
                            color: controls.modeSoft
                            border.color: controls.modeBorder
                            Text {
                                id: calCntTxt
                                anchors.centerIn: parent
                                text: "Corners " + flow.state.pointCount + " / 4"
                                color: controls.modeAccent
                                font.family: controls.theme.fontMono
                                font.pixelSize: controls.theme.textXs
                                font.weight: Font.DemiBold
                            }
                        }
                        Text { text: "L × W (in)"; color: controls.theme.inkSecondary; font.pixelSize: controls.theme.textSm }
                        DarkField {
                            id: length
                            text: controls.uiState.boardWidth
                            Layout.preferredWidth: 68
                            implicitHeight: 32
                            selectByMouse: true
                        }
                        Text { text: "×"; color: controls.theme.inkMuted }
                        DarkField {
                            id: depth
                            text: controls.uiState.boardDepth
                            Layout.preferredWidth: 68
                            implicitHeight: 32
                            selectByMouse: true
                        }
                        ConsoleButton {
                            text: "Apply"
                            primary: true
                            implicitHeight: 32
                            enabled: flow.state.pointCount === 4 && !flow.state.calibrationPending
                            onClicked: flow.applyCalibration(length.text, depth.text)
                        }
                    }
                }

                // Expandable technical telemetry toggle in Replay
                Button {
                    id: detailsToggle
                    visible: controls.kind === "replay"
                    implicitHeight: 32
                    leftPadding: 10
                    rightPadding: 10
                    onClicked: controls.replayDetailsOpen = !controls.replayDetailsOpen
                    ToolTip.visible: hovered
                    ToolTip.text: controls.replayDetailsOpen ? "Hide step timestamps and unavailable list"
                                                             : "Show step timestamps, calibration and unavailable units"
                    background: Rectangle {
                        radius: controls.theme.radiusMd
                        color: controls.replayDetailsOpen ? controls.theme.accentSoft
                               : (controls.replayInfo.unavailableCount || 0) > 0 ? controls.theme.warningSoft
                               : (detailsToggle.hovered ? controls.theme.bgElevated : controls.theme.bgSubtle)
                        border.color: controls.replayDetailsOpen ? controls.theme.accentBorder
                                      : (controls.replayInfo.unavailableCount || 0) > 0 ? controls.theme.warningBorder
                                      : controls.theme.border
                    }
                    contentItem: RowLayout {
                        spacing: 6
                        Rectangle {
                            visible: (controls.replayInfo.unavailableCount || 0) > 0
                            width: 7; height: 7; radius: 4
                            color: controls.theme.warning
                        }
                        Text {
                            text: (controls.replayInfo.unavailableCount || 0) > 0
                                  ? (controls.replayInfo.unavailableCount + " unavailable")
                                  : "Details"
                            color: (controls.replayInfo.unavailableCount || 0) > 0
                                   ? controls.theme.warning : controls.theme.inkSecondary
                            font.pixelSize: controls.theme.textXs
                            font.weight: Font.DemiBold
                        }
                        Text {
                            text: controls.replayDetailsOpen ? "▴" : "▾"
                            color: controls.theme.inkMuted
                            font.pixelSize: controls.theme.textXs
                        }
                    }
                }

                ConsoleButton {
                    text: controls.kind === "debug" ? "Resume Live" : "Back to Live"
                    shortcut: "Esc"
                    implicitHeight: 32
                    enabled: !flow.state.busy
                    onClicked: flow.action("cancel")
                }
            }

            // Secondary guidance (non-replay) or collapsible replay telemetry row
            RowLayout {
                visible: controls.kind !== "live" && (
                    controls.kind !== "replay"
                    || controls.replayDetailsOpen
                    || (controls.replayInfo.error || "").length > 0
                    || (controls.replayInfo.backgroundNote || "").length > 0
                )
                Layout.fillWidth: true
                spacing: 10

                Text {
                    visible: controls.kind !== "replay"
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                    color: controls.theme.inkSecondary
                    font.pixelSize: controls.theme.textXs
                    text: {
                        if (controls.kind === "terrain") return "Left click adds polygon vertices; right click removes the last vertex. Save once ≥ 3 points."
                        if (controls.kind === "recalibrate") return "Click four corners directly on the continuous raw video; right click undoes. Playback continues."
                        if (controls.kind === "recovery") return "Left click + / right click − points, then drag an existing ID onto the yellow candidate. " + (flow.state.note || "")
                        return flow.state.note || ""
                    }
                }

                Flow {
                    visible: controls.kind === "replay"
                    Layout.fillWidth: true
                    spacing: 12

                    Text {
                        visible: controls.replayDetailsOpen
                        text: "End " + (controls.replayInfo.endTime || "—")
                              + " · Obs " + (controls.replayInfo.observedTime || "—")
                              + " · Rec " + (controls.replayInfo.recordedTime || "—")
                              + " · Calib " + (controls.replayInfo.calibrationVersion || "—")
                              + (controls.replayInfo.boardDimensions ? " · " + controls.replayInfo.boardDimensions : "")
                        color: controls.theme.inkMuted
                        font.family: controls.theme.fontMono
                        font.pixelSize: controls.theme.textXs
                    }
                    Text {
                        visible: controls.replayDetailsOpen && (controls.replayInfo.unavailable || "").length > 0
                        text: "No position: " + (controls.replayInfo.unavailable || "")
                        color: controls.theme.warning
                        font.pixelSize: controls.theme.textXs
                    }
                    Text {
                        visible: (controls.replayInfo.backgroundNote || "").length > 0 || (controls.replayInfo.error || "").length > 0
                        text: (controls.replayInfo.error || controls.replayInfo.backgroundNote || "")
                        color: (controls.replayInfo.error || "").length > 0 ? controls.theme.modeRecovery : controls.theme.warning
                        font.pixelSize: controls.theme.textXs
                    }
                }
            }
        }
    }

    Dialog {
        id: undoTerrainDialog
        anchors.centerIn: Overlay.overlay
        modal: true
        title: "Remove last terrain?"
        standardButtons: Dialog.Yes | Dialog.No
        Overlay.modal: Rectangle { color: controls.theme.scrim }
        background: Rectangle {
            color: controls.theme.bgSurface
            radius: controls.theme.radiusLg
            border.color: controls.theme.borderStrong
        }
        header: Rectangle {
            implicitHeight: 44
            color: "transparent"
            Text {
                anchors.verticalCenter: parent.verticalCenter
                anchors.left: parent.left
                anchors.leftMargin: 18
                text: undoTerrainDialog.title
                color: controls.theme.ink
                font.family: controls.theme.fontDisplay
                font.pixelSize: controls.theme.textLg
                font.weight: Font.DemiBold
            }
        }
        Label {
            text: "Remove the most recently saved terrain polygon from the match scene?"
            color: controls.theme.inkSecondary
            font.pixelSize: controls.theme.textSm
        }
        onAccepted: flow.action("undoTerrain")
    }

    Dialog {
        id: editor
        property var rows: []
        property bool obstacle: false
        title: flow.formTitle
        modal: true
        anchors.centerIn: Overlay.overlay
        width: Math.min(540, Overlay.overlay.width - 40)
        height: Math.min(600, Overlay.overlay.height - 40)
        onClosed: flow.clearFormError()
        Overlay.modal: Rectangle { color: controls.theme.scrim }
        background: Rectangle {
            color: controls.theme.bgSurface
            radius: controls.theme.radiusLg
            border.color: controls.theme.borderStrong
        }
        header: Rectangle {
            implicitHeight: 46
            color: "transparent"
            Text {
                anchors.verticalCenter: parent.verticalCenter
                anchors.left: parent.left
                anchors.leftMargin: 18
                text: editor.title
                color: controls.theme.ink
                font.family: controls.theme.fontDisplay
                font.pixelSize: controls.theme.textLg
                font.weight: Font.DemiBold
            }
            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: 1
                color: controls.theme.borderSoft
            }
        }

        ColumnLayout {
            anchors.fill: parent
            spacing: 10

            ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                contentWidth: availableWidth
                clip: true

                ColumnLayout {
                    width: parent.width
                    spacing: 10

                    Repeater {
                        model: editor.rows
                        ColumnLayout {
                            required property var modelData
                            required property int index
                            readonly property bool fixedHeight: editor.obstacle && modelData.key === "height"
                            Layout.fillWidth: true
                            spacing: 4

                            Label {
                                visible: modelData.kind !== "bool"
                                text: fixedHeight ? "Rule height (fixed for Obstacle)" : modelData.label
                                color: controls.theme.inkSecondary
                                font.pixelSize: controls.theme.textSm
                                font.weight: Font.DemiBold
                            }

                            DarkField {
                                Layout.fillWidth: true
                                visible: modelData.kind === "text" || modelData.kind === "number" || modelData.kind === "rules"
                                text: fixedHeight ? "1" : String(modelData.value)
                                readOnly: fixedHeight
                                selectByMouse: true
                                onTextEdited: editor.rows[index].value = text
                            }

                            TextEdit {
                                Layout.fillWidth: true
                                visible: modelData.kind === "readonly"
                                text: modelData.value
                                textFormat: TextEdit.PlainText
                                readOnly: true
                                selectByMouse: true
                                wrapMode: TextEdit.Wrap
                                color: controls.theme.ink
                                font.family: controls.theme.fontBody
                                font.pixelSize: controls.theme.textSm
                            }

                            ComboBox {
                                id: combo
                                Layout.fillWidth: true
                                visible: modelData.kind === "choice"
                                model: modelData.optionLabels || modelData.options || []
                                currentIndex: {
                                    const opts = modelData.options || []
                                    const found = opts.indexOf(String(modelData.value))
                                    return found >= 0 ? found : 0
                                }
                                contentItem: Text {
                                    leftPadding: 10
                                    text: combo.displayText
                                    color: controls.theme.ink
                                    font.family: controls.theme.fontBody
                                    font.pixelSize: controls.theme.textSm
                                    verticalAlignment: Text.AlignVCenter
                                    elide: Text.ElideRight
                                }
                                background: Rectangle {
                                    implicitHeight: 34
                                    radius: controls.theme.radiusSm
                                    color: controls.theme.bgTrack
                                    border.color: combo.activeFocus ? controls.theme.selection : controls.theme.border
                                }
                                onActivated: idx => {
                                    const opts = modelData.options || []
                                    if (idx >= 0 && idx < opts.length) {
                                        editor.rows[index].value = opts[idx]
                                        if (modelData.key === "kind")
                                            editor.obstacle = opts[idx] === "obstacle"
                                    }
                                }
                            }

                            CheckBox {
                                id: chk
                                visible: modelData.kind === "bool"
                                text: modelData.label
                                checked: Boolean(modelData.value)
                                contentItem: Text {
                                    leftPadding: chk.indicator.width + chk.spacing
                                    text: chk.text
                                    color: controls.theme.ink
                                    font.pixelSize: controls.theme.textSm
                                    verticalAlignment: Text.AlignVCenter
                                }
                                onToggled: editor.rows[index].value = checked
                            }
                        }
                    }
                }
            }

            Rectangle {
                visible: flow.formError.length > 0
                Layout.fillWidth: true
                implicitHeight: errTxt.implicitHeight + 12
                radius: controls.theme.radiusSm
                color: controls.theme.dangerSoft
                border.color: controls.theme.dangerBorder
                Text {
                    id: errTxt
                    anchors.fill: parent
                    anchors.margins: 6
                    text: flow.formError
                    color: controls.theme.modeRecovery
                    wrapMode: Text.WordWrap
                    font.pixelSize: controls.theme.textSm
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                ConsoleButton { text: "Cancel"; variant: "subtle"; onClicked: editor.close() }
                ConsoleButton {
                    text: "Save"
                    primary: true
                    onClicked: {
                        const rows = editor.obstacle ? editor.rows.filter(row => row.key !== "height") : editor.rows
                        if (flow.saveForm(rows)) editor.close()
                    }
                }
            }
        }
    }

    Connections {
        target: flow
        function onFormRequested() {
            editor.obstacle = flow.fields.some(row => row.key === "kind" && row.value === "obstacle")
            editor.rows = flow.fields.map(row => ({
                key: row.key,
                label: row.label,
                kind: row.kind,
                value: row.value,
                options: row.options || [],
                optionLabels: row.optionLabels || []
            }))
            editor.open()
        }
    }
}
