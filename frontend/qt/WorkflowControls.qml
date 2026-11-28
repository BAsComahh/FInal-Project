import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: controls
    required property var uiState
    property bool replayDetailsOpen: false
    readonly property Theme theme: Theme {}
    readonly property string kind: (flow.state && flow.state.kind) ? flow.state.kind : "live"
    readonly property var replayInfo: (flow.state && flow.state.replayInfo) ? flow.state.replayInfo : ({})
    Layout.fillWidth: true
    spacing: 8

    readonly property color modeAccent: {
        if (kind === "replay") return theme.modeReplay
        if (kind === "recovery") return theme.modeRecovery
        if (kind === "recalibrate") return theme.modeRecalibrate
        return theme.accent
    }
    readonly property color modeDot: {
        if (kind === "replay") return theme.modeReplayDot
        if (kind === "recovery") return theme.modeRecoveryDot
        if (kind === "recalibrate") return theme.modeRecalibrateDot
        return theme.accent
    }
    readonly property color modeSoft: {
        if (kind === "replay") return theme.modeReplaySoft
        if (kind === "recovery") return theme.modeRecoverySoft
        if (kind === "recalibrate") return theme.modeRecalibrateSoft
        return theme.bgSurface
    }
    readonly property color modeBorder: {
        if (kind === "replay") return theme.modeReplayBorder
        if (kind === "recovery") return theme.modeRecoveryBorder
        if (kind === "recalibrate") return theme.modeRecalibrateBorder
        return theme.border
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

            // Live unified toolbar (display layers on the left, match actions on the right)
            RowLayout {
                visible: controls.kind === "live"
                Layout.fillWidth: true
                spacing: 8

                ConsoleButton {
                    text: "Select"
                    implicitHeight: 32
                    primary: controls.uiState.console.tool === "select"
                    onClicked: ui.doneTool()
                }

                Rectangle {
                    Layout.preferredWidth: 1
                    Layout.preferredHeight: 20
                    color: controls.theme.border
                }

                OverlayToggles {
                    uiState: controls.uiState
                    prefix: "live"
                }

                Item { Layout.fillWidth: true }

                Rectangle {
                    visible: controls.width < 920
                    Layout.preferredWidth: 1
                    Layout.preferredHeight: 20
                    color: controls.theme.border
                }

                RowLayout {
                    spacing: 6

                    ConsoleButton {
                        text: controls.width < 940 ? "Unit info" : "Unit information"
                        implicitHeight: 32
                        variant: Boolean(flow.state && flow.state.profileOpen) ? "default" : "subtle"
                        active: Boolean(flow.state && flow.state.profileOpen)
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
                        id: moreButton
                        objectName: "liveMoreMenu"
                        iconKind: "more"
                        text: ""
                        implicitWidth: 34
                        implicitHeight: 32
                        leftPadding: 0
                        rightPadding: 0
                        variant: "subtle"
                        active: moreMenu.visible
                        tooltipText: "More tools"
                        onClicked: moreMenu.popup(moreButton, moreButton.width - moreMenu.width, moreButton.height + 4)

                        Menu {
                            id: moreMenu
                            width: 172
                            padding: 4
                            background: Rectangle {
                                radius: controls.theme.radiusSm
                                color: controls.theme.bgElevated
                                border.color: controls.theme.borderStrong
                                border.width: 1
                            }
                            delegate: MenuItem {
                                id: mItem
                                implicitHeight: 32
                                contentItem: Text {
                                    leftPadding: 8
                                    rightPadding: 8
                                    text: mItem.text
                                    color: mItem.enabled
                                           ? (mItem.highlighted ? controls.theme.selection : controls.theme.ink)
                                           : controls.theme.inkMuted
                                    font.family: controls.theme.fontBody
                                    font.pixelSize: controls.theme.textSm
                                    verticalAlignment: Text.AlignVCenter
                                }
                                background: Rectangle {
                                    radius: controls.theme.radiusXs
                                    color: mItem.highlighted ? controls.theme.accentSoft : "transparent"
                                }
                            }
                            Action {
                                objectName: "liveDebugAction"
                                text: "Debug snapshot"
                                enabled: !controls.uiState.pendingPlay
                                onTriggered: flow.open("debug")
                            }
                        }
                    }
                }
            }

            // Sub-workflow contextual bars (Recovery / Recalibrate / Replay / Debug)
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
                    OverlayToggles {
                        visible: controls.kind === "debug"
                        uiState: controls.uiState
                        prefix: "debug"
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
                    OverlayToggles {
                        visible: controls.kind === "replay"
                        uiState: controls.uiState
                        prefix: "replay"
                        showMasksPill: false
                        showTerrainPill: false
                    }

                    // Recovery controls (aligned with Registration tools)
                    ConsoleButton {
                        objectName: "recoveryPoints"
                        text: "Points"
                        implicitHeight: 32
                        visible: controls.kind === "recovery"
                        active: flow.state.tool === "Points"
                        enabled: !flow.state.busy
                        tooltipText: "Left click + / right click − points to segment the candidate."
                        onClicked: flow.setRecoveryTool("Points")
                    }
                    ConsoleButton {
                        objectName: "recoveryRectangle"
                        text: "Rectangle"
                        implicitHeight: 32
                        visible: controls.kind === "recovery"
                        active: flow.state.tool === "Rectangle"
                        enabled: !flow.state.busy
                        tooltipText: "Drag with the left mouse button to draw the recovery candidate."
                        onClicked: flow.setRecoveryTool("Rectangle")
                    }
                    ConsoleButton {
                        objectName: "recoveryQuad"
                        text: "Four corners"
                        implicitHeight: 32
                        visible: controls.kind === "recovery"
                        active: flow.state.tool === "Quad"
                        enabled: !flow.state.busy
                        tooltipText: "Click four corners to draw the recovery candidate."
                        onClicked: flow.setRecoveryTool("Quad")
                    }
                    ConsoleButton {
                        objectName: "confirmRecoveryTarget"
                        text: "Confirm " + (flow.state.targetUnitId || "")
                        primary: true
                        implicitHeight: 32
                        visible: controls.kind === "recovery" && Boolean(flow.state.canConfirmTarget)
                        enabled: !flow.state.busy
                        onClicked: flow.confirmTarget()
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
                    OverlayToggles {
                        visible: controls.kind === "recovery"
                        uiState: controls.uiState
                        prefix: "recovery"
                    }
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

            // Replay discrete step timeline slider (P02)
            RowLayout {
                id: replayTimelineRow
                visible: controls.kind === "replay" && flow.state.steps > 0
                Layout.fillWidth: true
                spacing: 10

                readonly property int stepCount: flow.state.steps || 0
                readonly property int maxStep: Math.max(0, stepCount - 1)
                readonly property var timelineList: flow.replaySteps || []
                property int previewStep: flow.state.step || 0

                function formatStepTip(idx) {
                    if (idx < 0 || idx >= timelineList.length) return "Step " + idx
                    const s = timelineList[idx]
                    const who = s.unit ? (s.unit + " ") : ""
                    const detail = s.summary ? (" · " + s.summary) : ""
                    return "Step " + s.index + " · " + who + s.label + detail + " · " + s.time
                }

                Text {
                    text: "0 · " + (controls.replayInfo.firstTime || "0.0s")
                    color: controls.theme.inkMuted
                    font.family: controls.theme.fontMono
                    font.pixelSize: controls.theme.textXs
                }

                Item {
                    Layout.fillWidth: true
                    implicitHeight: 28

                    Slider {
                        id: replaySlider
                        objectName: "replaySlider"
                        anchors.fill: parent
                        from: 0
                        to: Math.max(1, replayTimelineRow.maxStep)
                        stepSize: 1
                        snapMode: Slider.SnapAlways
                        enabled: replayTimelineRow.stepCount > 1
                        live: true

                        Binding {
                            target: replaySlider
                            property: "value"
                            value: replayTimelineRow.stepCount > 1 ? (flow.state.step || 0) : 0
                            when: !replaySlider.pressed
                        }

                        onMoved: {
                            const nextStep = Math.round(value)
                            replayTimelineRow.previewStep = nextStep
                            if (nextStep !== flow.state.step) {
                                flow.selectReplayStep(nextStep)
                            }
                        }

                        HoverHandler {
                            id: sliderHover
                            onPointChanged: {
                                if (!replaySlider.pressed && replayTimelineRow.maxStep > 0 && replaySlider.availableWidth > 0) {
                                    const frac = Math.max(0, Math.min(1, (point.position.x - replaySlider.leftPadding) / replaySlider.availableWidth))
                                    replayTimelineRow.previewStep = Math.round(frac * replayTimelineRow.maxStep)
                                }
                            }
                        }

                        background: Item {
                            x: replaySlider.leftPadding
                            y: replaySlider.topPadding + replaySlider.availableHeight / 2 - 4
                            width: replaySlider.availableWidth
                            height: 8

                            Rectangle {
                                anchors.verticalCenter: parent.verticalCenter
                                width: parent.width
                                height: 6
                                radius: 3
                                color: controls.theme.bgTrack
                                border.color: controls.theme.borderSoft
                            }

                            Rectangle {
                                anchors.verticalCenter: parent.verticalCenter
                                width: replayTimelineRow.stepCount > 1 ? (replaySlider.visualPosition * parent.width) : 0
                                height: 6
                                radius: 3
                                color: controls.theme.modeReplayDot
                            }

                            // Discrete step markers along the track
                            Repeater {
                                model: (replayTimelineRow.stepCount > 1 && replayTimelineRow.stepCount <= 80)
                                       ? replayTimelineRow.timelineList : []
                                delegate: Rectangle {
                                    required property var modelData
                                    readonly property real pos: replayTimelineRow.maxStep > 0 ? (modelData.index / replayTimelineRow.maxStep) : 0
                                    x: Math.round(pos * parent.width - width / 2)
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: modelData.index === flow.state.step ? 6 : 4
                                    height: modelData.index === flow.state.step ? 12 : 8
                                    radius: 2
                                    color: modelData.index === 0 ? controls.theme.inkSecondary
                                           : modelData.side === "A" ? controls.theme.sideA
                                           : modelData.side === "B" ? controls.theme.sideB
                                           : controls.theme.modeReplay
                                    opacity: modelData.index <= flow.state.step ? 0.95 : 0.45
                                }
                            }
                        }

                        handle: Rectangle {
                            x: replaySlider.leftPadding + (replayTimelineRow.stepCount > 1 ? replaySlider.visualPosition * (replaySlider.availableWidth - width) : 0)
                            y: replaySlider.topPadding + replaySlider.availableHeight / 2 - height / 2
                            width: replaySlider.pressed ? 18 : 16
                            height: replaySlider.pressed ? 18 : 16
                            radius: width / 2
                            color: replaySlider.enabled
                                   ? (replaySlider.pressed ? controls.theme.selection : controls.theme.modeReplay)
                                   : controls.theme.borderStrong
                            border.width: 2
                            border.color: controls.theme.bgHeader

                            Rectangle {
                                anchors.centerIn: parent
                                width: 5; height: 5; radius: 2.5
                                color: controls.theme.bgHeader
                            }
                        }

                        ToolTip {
                            visible: (sliderHover.hovered || replaySlider.pressed) && replayTimelineRow.stepCount > 0
                            text: replayTimelineRow.formatStepTip(replaySlider.pressed ? Math.round(replaySlider.value) : replayTimelineRow.previewStep)
                            y: -height - 8
                        }
                    }
                }

                Text {
                    text: replayTimelineRow.stepCount > 1
                          ? (replayTimelineRow.maxStep + " · " + (controls.replayInfo.lastTime || "—"))
                          : "Initial snapshot only"
                    color: controls.theme.inkMuted
                    font.family: controls.theme.fontMono
                    font.pixelSize: controls.theme.textXs
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
                        if (controls.kind === "recalibrate") return "Click four corners directly on the continuous raw video; right click undoes. Playback continues."
                        if (controls.kind === "recovery") {
                            const hint = flow.state.tool === "Rectangle"
                                         ? "Drag a rectangle over the unit, then click or drag its ID."
                                         : flow.state.tool === "Quad"
                                         ? ("Click 4 corners (" + ((flow.state.quadVertices || []).length) + "/4 · Right-click removes vertex), then click or drag its ID.")
                                         : "Left: + point · Right: − point, then click or drag an ID."
                            return hint + (flow.state.note ? (" · " + flow.state.note) : "")
                        }
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
}
