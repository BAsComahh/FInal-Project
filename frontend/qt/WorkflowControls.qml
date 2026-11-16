import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: controls
    required property var uiState
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
        leftPadding: 10
        rightPadding: 10
        background: Rectangle {
            radius: 8
            color: pill.checkedState ? (pill.hovered ? "#dcecf5" : pill.t.accentSoft) : (pill.hovered ? "#eef3f7" : pill.t.bgSubtle)
            border.color: pill.checkedState ? pill.t.accentBorder : pill.t.border
        }
        contentItem: RowLayout {
            spacing: 6
            Rectangle {
                width: 8; height: 8; radius: 4
                color: pill.checkedState ? pill.t.accent : pill.t.borderStrong
            }
            Text {
                text: pill.text
                font.family: pill.t.fontBody
                font.pixelSize: 12
                font.weight: pill.checkedState ? Font.DemiBold : Font.Normal
                color: pill.checkedState ? pill.t.accent : pill.t.inkSecondary
            }
            Rectangle {
                visible: pill.badgeText.length > 0
                implicitWidth: bTxt.implicitWidth + 8
                implicitHeight: 17
                radius: 5
                color: pill.checkedState ? "#ffffff" : pill.t.bgTrack
                Text {
                    id: bTxt
                    anchors.centerIn: parent
                    text: pill.badgeText
                    font.family: pill.t.fontMono
                    font.pixelSize: 9
                    color: pill.checkedState ? pill.t.accent : pill.t.inkMuted
                }
            }
        }
    }

    Rectangle {
        Layout.fillWidth: true
        implicitHeight: barContent.implicitHeight + 14
        radius: 10
        color: controls.kind === "live" ? controls.theme.bgSurface : controls.modeSoft
        border.color: controls.modeBorder

        ColumnLayout {
            id: barContent
            anchors.fill: parent
            anchors.leftMargin: 12
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
                        variant: "subtle"
                        enabled: controls.uiState.console.selected
                        tooltipText: controls.uiState.console.selected
                                     ? ("Edit rule attributes for " + controls.uiState.console.unitId)
                                     : "Select a unit on the board first"
                        onClicked: flow.open("profile")
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

                    // Replay controls
                    Rectangle {
                        visible: controls.kind === "replay"
                        implicitWidth: replayStepTxt.implicitWidth + 16
                        implicitHeight: 32
                        radius: 7
                        color: controls.theme.bgSurface
                        border.color: controls.theme.modeReplayBorder
                        Text {
                            id: replayStepTxt
                            anchors.centerIn: parent
                            text: (controls.replayInfo.stepText || "Replay")
                                  + (controls.replayInfo.stepLabel ? " · " + controls.replayInfo.stepLabel : "")
                                  + (controls.replayInfo.stepUnit ? " · " + controls.replayInfo.stepUnit : "")
                            color: controls.theme.ink
                            font.pixelSize: 12
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
                        implicitHeight: 32
                        visible: controls.kind === "replay"
                        onClicked: flow.action("refresh")
                    }

                    // Recovery controls
                    Rectangle {
                        visible: controls.kind === "recovery"
                        implicitWidth: recCandTxt.implicitWidth + 16
                        implicitHeight: 32
                        radius: 7
                        color: controls.theme.bgSurface
                        border.color: controls.theme.modeRecoveryBorder
                        Text {
                            id: recCandTxt
                            anchors.centerIn: parent
                            text: "Candidate · " + flow.state.candidateTime
                            color: controls.theme.modeRecovery
                            font.family: controls.theme.fontMono
                            font.pixelSize: 11
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
                        radius: 7
                        color: controls.theme.bgSurface
                        border.color: controls.theme.modeTerrainBorder
                        Text {
                            id: terCntTxt
                            anchors.centerIn: parent
                            text: "Vertices · " + flow.state.pointCount
                            color: controls.theme.modeTerrain
                            font.family: controls.theme.fontMono
                            font.pixelSize: 11
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
                            radius: 7
                            color: controls.theme.bgSurface
                            border.color: controls.theme.modeRecalibrateBorder
                            Text {
                                id: calCntTxt
                                anchors.centerIn: parent
                                text: "Corners " + flow.state.pointCount + " / 4"
                                color: controls.theme.modeRecalibrate
                                font.family: controls.theme.fontMono
                                font.pixelSize: 11
                                font.weight: Font.DemiBold
                            }
                        }
                        Text { text: "L × W (in)"; color: controls.theme.inkSecondary; font.pixelSize: 12 }
                        TextField {
                            id: length
                            text: controls.uiState.boardWidth
                            Layout.preferredWidth: 68
                            implicitHeight: 32
                            selectByMouse: true
                        }
                        Text { text: "×"; color: controls.theme.inkMuted }
                        TextField {
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

                ConsoleButton {
                    text: "Back to Live"
                    shortcut: "Esc"
                    implicitHeight: 32
                    enabled: !flow.state.busy
                    onClicked: flow.action("cancel")
                }
            }

            // Secondary guidance / replay telemetry line
            RowLayout {
                visible: controls.kind !== "live"
                Layout.fillWidth: true
                spacing: 10

                Text {
                    visible: controls.kind !== "replay"
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                    color: controls.modeAccent
                    font.pixelSize: 11
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
                        text: "End " + (controls.replayInfo.endTime || "—")
                              + " · Obs " + (controls.replayInfo.observedTime || "—")
                              + " · Rec " + (controls.replayInfo.recordedTime || "—")
                              + " · Calib " + (controls.replayInfo.calibrationVersion || "—")
                              + (controls.replayInfo.boardDimensions ? " · " + controls.replayInfo.boardDimensions : "")
                        color: controls.theme.inkSecondary
                        font.family: controls.theme.fontMono
                        font.pixelSize: 11
                    }
                    Text {
                        visible: (controls.replayInfo.unavailable || "").length > 0
                        text: "No position: " + (controls.replayInfo.unavailable || "")
                        color: controls.theme.warning
                        font.pixelSize: 11
                    }
                    Text {
                        visible: (controls.replayInfo.backgroundNote || "").length > 0 || (controls.replayInfo.error || "").length > 0
                        text: (controls.replayInfo.error || controls.replayInfo.backgroundNote || "")
                        color: (controls.replayInfo.error || "").length > 0 ? controls.theme.danger : controls.theme.warning
                        font.pixelSize: 11
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
        Label {
            text: "Remove the most recently saved terrain polygon from the match scene?"
            color: controls.theme.inkSecondary
        }
        onAccepted: flow.action("undoTerrain")
    }

    Dialog {
        id: editor
        property var rows: []
        title: flow.formTitle
        modal: true
        anchors.centerIn: Overlay.overlay
        width: Math.min(540, Overlay.overlay.width - 40)
        height: Math.min(600, Overlay.overlay.height - 40)
        onClosed: flow.clearFormError()

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
                            Layout.fillWidth: true
                            spacing: 4

                            Label {
                                visible: modelData.kind !== "bool"
                                text: modelData.label
                                color: controls.theme.inkSecondary
                                font.pixelSize: 12
                                font.weight: Font.DemiBold
                            }

                            TextField {
                                Layout.fillWidth: true
                                visible: modelData.kind !== "bool" && modelData.kind !== "choice"
                                text: String(modelData.value)
                                selectByMouse: true
                                onTextEdited: editor.rows[index].value = text
                            }

                            ComboBox {
                                Layout.fillWidth: true
                                visible: modelData.kind === "choice"
                                model: modelData.optionLabels || modelData.options || []
                                currentIndex: {
                                    const opts = modelData.options || []
                                    const found = opts.indexOf(String(modelData.value))
                                    return found >= 0 ? found : 0
                                }
                                onActivated: idx => {
                                    const opts = modelData.options || []
                                    if (idx >= 0 && idx < opts.length) {
                                        editor.rows[index].value = opts[idx]
                                    }
                                }
                            }

                            CheckBox {
                                visible: modelData.kind === "bool"
                                text: modelData.label
                                checked: Boolean(modelData.value)
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
                radius: 7
                color: controls.theme.dangerSoft
                border.color: controls.theme.dangerBorder
                Text {
                    id: errTxt
                    anchors.fill: parent
                    anchors.margins: 6
                    text: flow.formError
                    color: controls.theme.danger
                    wrapMode: Text.WordWrap
                    font.pixelSize: 12
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                ConsoleButton { text: "Cancel"; onClicked: editor.close() }
                ConsoleButton {
                    text: "Save"
                    primary: true
                    onClicked: {
                        if (flow.saveForm(editor.rows)) editor.close()
                    }
                }
            }
        }
    }

    Connections {
        target: flow
        function onFormRequested() {
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
