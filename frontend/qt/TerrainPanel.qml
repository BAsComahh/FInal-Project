import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: panel
    property bool drawMode: false
    property int focusedInputs: 0
    readonly property bool editingFocus: focusedInputs > 0
    readonly property Theme theme: Theme {}
    readonly property string selectedId: (flow.state && flow.state.selectedTerrainId) ? flow.state.selectedTerrainId : ""
    readonly property var selectedRow: (flow.state && flow.state.selectedTerrain) ? flow.state.selectedTerrain : ({})
    readonly property var kindOptions: [
        { value: "blocking", label: "Blocking" },
        { value: "difficult", label: "Difficult" },
        { value: "obstacle", label: "Obstacle" },
        { value: "hill", label: "Hill" },
        { value: "decorative", label: "Decorative" }
    ]

    property string editLabel: ""
    property string editKind: "blocking"
    property string editHeight: ""
    property bool confirmDelete: false
    readonly property bool isObstacle: editKind === "obstacle"

    radius: theme.radiusLg
    color: theme.bgSurface
    border.color: drawMode ? theme.modeTerrainBorder : theme.border

    function loadSelected() {
        confirmDelete = false
        if (!selectedId || !selectedRow || !selectedRow.id) {
            editLabel = ""
            editKind = "blocking"
            editHeight = ""
            return
        }
        editLabel = String(selectedRow.label || "")
        editKind = String(selectedRow.kind || "blocking")
        editHeight = String(selectedRow.heightRaw || "")
    }

    onSelectedIdChanged: loadSelected()
    onVisibleChanged: {
        if (!visible) {
            focusedInputs = 0
            confirmDelete = false
        } else {
            loadSelected()
        }
    }

    Connections {
        target: flow
        function onTerrainLoaded() { panel.loadSelected() }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 14
        spacing: 10

        // Header
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            Rectangle {
                width: 8; height: 8; radius: 4
                color: panel.theme.modeTerrainDot
            }
            Text {
                text: panel.drawMode ? "Saved terrain" : "Terrain information"
                color: panel.theme.ink
                font.family: panel.theme.fontDisplay
                font.pixelSize: panel.theme.textLg
                font.weight: Font.DemiBold
                Layout.fillWidth: true
                elide: Text.ElideRight
            }
            Rectangle {
                implicitWidth: countTxt.implicitWidth + 12
                implicitHeight: 20
                radius: height / 2
                color: panel.theme.modeTerrainSoft
                border.color: panel.theme.modeTerrainBorder
                Text {
                    id: countTxt
                    anchors.centerIn: parent
                    text: String((flow.terrainRows || []).length)
                    color: panel.theme.modeTerrain
                    font.family: panel.theme.fontMono
                    font.pixelSize: panel.theme.textXs
                    font.weight: Font.DemiBold
                }
            }
            ConsoleButton {
                objectName: "closeTerrainPanel"
                visible: !panel.drawMode || panel.selectedId.length > 0
                text: "Close"
                variant: "subtle"
                implicitHeight: 26
                onClicked: flow.closeTerrainInfo()
            }
        }

        Text {
            visible: panel.drawMode
            text: "Click a saved terrain below to edit attributes or delete it, or click the board to draw a new polygon."
            color: panel.theme.inkMuted
            font.pixelSize: panel.theme.textXs
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }

        Rectangle { Layout.fillWidth: true; height: 1; color: panel.theme.borderSoft }

        // Saved terrain list
        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: panel.selectedId.length === 0
            Layout.preferredHeight: panel.selectedId.length > 0 ? Math.min(185, Math.max(66, listCol.implicitHeight + 6)) : -1
            contentWidth: availableWidth
            clip: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

            Column {
                id: listCol
                width: parent.width
                spacing: 6

                Repeater {
                    model: flow.terrainRows
                    delegate: Rectangle {
                        id: tCard
                        required property var modelData
                        readonly property bool isSel: modelData.id === panel.selectedId
                        objectName: "terrainRow_" + modelData.id
                        width: parent.width
                        height: cardBody.implicitHeight + 14
                        radius: panel.theme.radiusSm
                        color: isSel ? panel.theme.accentSoft : (rowMouse.containsMouse ? panel.theme.bgElevated : panel.theme.bgSubtle)
                        border.width: isSel ? 1.5 : 1
                        border.color: isSel ? panel.theme.selection : (rowMouse.containsMouse ? panel.theme.borderStrong : panel.theme.border)
                        clip: true

                        Rectangle {
                            width: 3.5
                            height: parent.height
                            anchors.left: parent.left
                            color: tCard.modelData.color || panel.theme.modeTerrainDot
                        }

                        ColumnLayout {
                            id: cardBody
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.leftMargin: 11
                            anchors.rightMargin: 9
                            spacing: 2

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 6
                                Text {
                                    text: tCard.modelData.label
                                    color: panel.theme.ink
                                    font.pixelSize: panel.theme.textSm
                                    font.weight: Font.DemiBold
                                    Layout.fillWidth: true
                                    elide: Text.ElideRight
                                }
                                Text {
                                    text: tCard.modelData.id
                                    color: tCard.isSel ? panel.theme.selection : panel.theme.inkMuted
                                    font.family: panel.theme.fontMono
                                    font.pixelSize: 10
                                }
                            }

                            Text {
                                text: tCard.modelData.kindLabel + " · H " + tCard.modelData.heightText + " · " + tCard.modelData.areaText
                                color: panel.theme.inkSecondary
                                font.pixelSize: panel.theme.textXs
                                Layout.fillWidth: true
                                elide: Text.ElideRight
                            }
                        }

                        MouseArea {
                            id: rowMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: flow.selectTerrain(tCard.modelData.id, true)
                        }
                    }
                }

                Text {
                    visible: (flow.terrainRows || []).length === 0
                    width: parent.width
                    text: "No terrain saved yet. Click ≥ 3 vertices on the board, then click Save polygon."
                    color: panel.theme.inkMuted
                    font.pixelSize: panel.theme.textXs
                    wrapMode: Text.WordWrap
                }
            }
        }

        // Selected terrain editor (modeled after UnitInfoPanel)
        Rectangle {
            visible: panel.selectedId.length > 0
            Layout.fillWidth: true
            height: 1
            color: panel.theme.borderSoft
        }

        ScrollView {
            visible: panel.selectedId.length > 0
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentWidth: availableWidth
            clip: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

            ColumnLayout {
                width: parent.width
                spacing: 10

                // Metadata strip
                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: metaRow.implicitHeight + 12
                    radius: panel.theme.radiusSm
                    color: panel.theme.bgSubtle
                    border.color: panel.theme.borderSoft
                    RowLayout {
                        id: metaRow
                        anchors.fill: parent
                        anchors.margins: 6
                        spacing: 6
                        Rectangle {
                            width: 8; height: 8; radius: 4
                            color: (panel.selectedRow && panel.selectedRow.color) ? panel.selectedRow.color : panel.theme.modeTerrainDot
                        }
                        Text {
                            text: panel.selectedId + " · " + ((panel.selectedRow && panel.selectedRow.areaText) ? panel.selectedRow.areaText : "")
                            color: panel.theme.inkSecondary
                            font.family: panel.theme.fontMono
                            font.pixelSize: panel.theme.textXs
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                        }
                    }
                }

                // Label input
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 4
                    Text {
                        text: "Label"
                        color: panel.theme.inkSecondary
                        font.pixelSize: panel.theme.textXs
                        font.weight: Font.DemiBold
                    }
                    TextField {
                        id: labelField
                        objectName: "terrainEditLabel"
                        Layout.fillWidth: true
                        text: panel.editLabel
                        selectByMouse: true
                        color: panel.theme.ink
                        placeholderText: "e.g. Forest, Ruin, Hill"
                        placeholderTextColor: panel.theme.inkMuted
                        selectionColor: panel.theme.accentSoft
                        selectedTextColor: panel.theme.ink
                        font.family: panel.theme.fontBody
                        font.pixelSize: panel.theme.textSm
                        leftPadding: 10
                        rightPadding: 10
                        background: Rectangle {
                            radius: panel.theme.radiusSm
                            color: panel.theme.bgTrack
                            border.width: labelField.activeFocus ? 1.5 : 1
                            border.color: labelField.activeFocus ? panel.theme.selection : panel.theme.border
                        }
                        onActiveFocusChanged: {
                            if (activeFocus) panel.focusedInputs += 1
                            else panel.focusedInputs = Math.max(0, panel.focusedInputs - 1)
                        }
                        onTextEdited: panel.editLabel = text
                    }
                }

                // Kind selector
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 4
                    Text {
                        text: "Terrain kind"
                        color: panel.theme.inkSecondary
                        font.pixelSize: panel.theme.textXs
                        font.weight: Font.DemiBold
                    }
                    ConsoleComboBox {
                        id: kindCombo
                        objectName: "terrainEditKind"
                        Layout.fillWidth: true
                        model: panel.kindOptions.map(opt => opt.label)
                        currentIndex: {
                            for (let i = 0; i < panel.kindOptions.length; i++) {
                                if (panel.kindOptions[i].value === panel.editKind) return i
                            }
                            return 0
                        }
                        onActivated: idx => {
                            if (idx >= 0 && idx < panel.kindOptions.length) {
                                const nextKind = panel.kindOptions[idx].value
                                const wasObstacle = panel.editKind === "obstacle"
                                panel.editKind = nextKind
                                if (nextKind === "obstacle") panel.editHeight = "1"
                                else if (wasObstacle && panel.editHeight === "1") panel.editHeight = ""
                            }
                        }
                    }
                }

                // Height input
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 4
                    Text {
                        text: panel.isObstacle ? "Rule height (fixed for Obstacle)" : "Rule height (optional)"
                        color: panel.theme.inkSecondary
                        font.pixelSize: panel.theme.textXs
                        font.weight: Font.DemiBold
                    }
                    TextField {
                        id: heightField
                        objectName: "terrainEditHeight"
                        Layout.fillWidth: true
                        text: panel.isObstacle ? "1" : panel.editHeight
                        readOnly: panel.isObstacle
                        selectByMouse: true
                        color: panel.isObstacle ? panel.theme.inkMuted : panel.theme.ink
                        placeholderText: "Leave empty if unknown"
                        placeholderTextColor: panel.theme.inkMuted
                        selectionColor: panel.theme.accentSoft
                        selectedTextColor: panel.theme.ink
                        font.family: panel.theme.fontBody
                        font.pixelSize: panel.theme.textSm
                        leftPadding: 10
                        rightPadding: 10
                        background: Rectangle {
                            radius: panel.theme.radiusSm
                            color: panel.isObstacle ? panel.theme.bgSubtle : panel.theme.bgTrack
                            border.width: (!panel.isObstacle && heightField.activeFocus) ? 1.5 : 1
                            border.color: (!panel.isObstacle && heightField.activeFocus) ? panel.theme.selection : panel.theme.border
                        }
                        onActiveFocusChanged: {
                            if (activeFocus) panel.focusedInputs += 1
                            else panel.focusedInputs = Math.max(0, panel.focusedInputs - 1)
                        }
                        onTextEdited: if (!panel.isObstacle) panel.editHeight = text
                    }
                }
            }
        }

        // Validation error banner
        Rectangle {
            visible: panel.selectedId.length > 0 && flow.formError.length > 0
            Layout.fillWidth: true
            implicitHeight: errTxt.implicitHeight + 12
            radius: panel.theme.radiusSm
            color: panel.theme.dangerSoft
            border.color: panel.theme.dangerBorder
            Text {
                id: errTxt
                anchors.fill: parent
                anchors.margins: 6
                text: flow.formError
                color: panel.theme.modeRecovery
                wrapMode: Text.WordWrap
                font.pixelSize: panel.theme.textXs
            }
        }

        // Inline two-step delete confirmation banner
        Rectangle {
            visible: panel.selectedId.length > 0 && panel.confirmDelete
            Layout.fillWidth: true
            implicitHeight: delConfirmCol.implicitHeight + 14
            radius: panel.theme.radiusSm
            color: panel.theme.dangerSoft
            border.color: panel.theme.dangerBorder
            ColumnLayout {
                id: delConfirmCol
                anchors.fill: parent
                anchors.margins: 7
                spacing: 6
                Text {
                    text: "Delete " + panel.selectedId + " (" + ((panel.selectedRow && panel.selectedRow.label) ? panel.selectedRow.label : "terrain") + ")?"
                    color: panel.theme.ink
                    font.pixelSize: panel.theme.textXs
                    font.weight: Font.DemiBold
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 6
                    ConsoleButton {
                        objectName: "cancelDeleteTerrain"
                        text: "Cancel"
                        variant: "subtle"
                        implicitHeight: 28
                        Layout.fillWidth: true
                        onClicked: panel.confirmDelete = false
                    }
                    ConsoleButton {
                        objectName: "confirmDeleteTerrain"
                        text: "Confirm delete"
                        variant: "danger"
                        implicitHeight: 28
                        Layout.fillWidth: true
                        onClicked: {
                            const tid = panel.selectedId
                            panel.confirmDelete = false
                            flow.deleteTerrain(tid)
                        }
                    }
                }
            }
        }

        // Primary footer buttons
        RowLayout {
            visible: panel.selectedId.length > 0 && !panel.confirmDelete
            Layout.fillWidth: true
            spacing: 8
            ConsoleButton {
                objectName: "deleteTerrainButton"
                text: "Delete"
                variant: "dangerSubtle"
                Layout.fillWidth: true
                onClicked: panel.confirmDelete = true
            }
            ConsoleButton {
                objectName: "saveTerrainEditButton"
                text: "Save"
                primary: true
                Layout.fillWidth: true
                onClicked: flow.saveTerrainEdit(panel.selectedId, panel.editLabel, panel.editKind, panel.editHeight)
            }
        }
    }
}
