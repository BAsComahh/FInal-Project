import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts

ApplicationWindow {
    id: window
    width: 1180; height: 820
    minimumWidth: 820; minimumHeight: 640
    visible: true
    title: window.live ? "Match console · Live" : "Match console · Unit registration"
    color: "#edf2f5"; font.family: "Segoe UI"; font.pixelSize: 13
    property var s: ui.state
    readonly property bool table: s.stage === "table"
    readonly property bool live: s.stage === "playback" || s.stage === "recalibrate"
    readonly property bool modalOpen: resetDialog.visible || armyFile.visible || registrationFile.visible || workflowControls.formOpen
    onClosing: ui.close()

    ColumnLayout {
        anchors.fill: parent; spacing: 0
        Rectangle {
            Layout.fillWidth: true; implicitHeight: 84; color: "white"
            RowLayout {
                anchors.fill: parent; anchors.margins: 20; spacing: 10
                Column {
                    spacing: 3
                    Text {
                        text: window.table ? "TABLE SETUP" : window.live ? "LIVE BOARD" : "REGISTER UNITS"
                        color: "#5e7788"; font.pixelSize: 10; font.letterSpacing: 1.6; font.weight: Font.DemiBold
                    }
                    Text {
                        text: window.table ? "Frame the battlefield" : window.live ? "Match in progress" : "Build the starting board"
                        color: "#193445"; font.pixelSize: window.width < 1000 ? 18 : 23; font.weight: Font.DemiBold
                    }
                }
                Item { Layout.fillWidth: true }
                Rectangle {
                    visible: window.live; implicitWidth: 66; implicitHeight: 30; radius: 7; color: "#e8f1f5"
                    Text { anchors.centerIn: parent; text: "LIVE"; color: "#246b89"; font.family: "Consolas"; font.pixelSize: 11; font.letterSpacing: 1 }
                }
                ConsoleButton { objectName: "loadRegistration"; text: "Load registration"; visible: !window.live; enabled: !s.locked; onClicked: registrationFile.open() }
                ConsoleButton { text: "Undo"; visible: !window.live; enabled: window.table ? s.tableMode === "manual" && s.cornerCount > 0 : s.editable && s.undo; onClicked: ui.undo() }
                ConsoleButton { text: "Reset"; visible: !window.table; onClicked: resetDialog.open() }
                ConsoleButton { objectName: "saveRegistration"; text: s.locked ? "Saved" : "Save"; visible: !window.table && !window.live; enabled: s.editable && s.ready; onClicked: ui.finish() }
                ConsoleButton { objectName: "startPlayback"; text: s.pendingPlay ? "Starting…" : "Start video"; primary: true; visible: !window.table && !window.live; enabled: s.ready; onClicked: ui.start() }
            }
        }
        WorkflowControls { id: workflowControls; visible: window.live; Layout.leftMargin: 20; Layout.rightMargin: 20 }
        RowLayout {
            Layout.fillHeight: true; Layout.fillWidth: true; Layout.margins: 20; spacing: 16
            ColumnLayout {
                Layout.fillWidth: true; Layout.fillHeight: true; spacing: 10
                Flow {
                    Layout.fillWidth: true; spacing: 7
                    ConsoleButton { text: "Select"; visible: window.live; primary: s.console.tool === "select"; onClicked: ui.doneTool() }
                    ConsoleButton { text: "Points"; visible: !window.table && !window.live; primary: s.mode === "Points"; enabled: s.editable; onClicked: ui.setMode("Points") }
                    ConsoleButton { text: "Assign"; visible: !window.table && !window.live; primary: s.mode === "Assign"; enabled: s.editable; onClicked: ui.setMode("Assign") }
                    ConsoleButton { text: "New mask"; visible: !window.table && !window.live; enabled: s.editable && s.ready; onClicked: ui.newObject() }
                    ConsoleButton { text: "Front [F]"; visible: !window.table && !window.live; primary: s.mode === "Front"; enabled: s.canFront; onClicked: ui.setMode("Front") }
                    CheckBox { text: "Masks"; visible: !window.table; checked: s.masks; onToggled: ui.setOverlay("masks", checked) }
                    CheckBox { text: "Trays"; visible: !window.table; checked: s.trays; onToggled: ui.setOverlay("trays", checked) }
                }
                Rectangle {
                    Layout.fillWidth: true; Layout.fillHeight: true
                    color: "#dae3e9"; radius: 10; clip: true
                    Image {
                        id: board
                        objectName: "boardImage"
                        anchors.fill: parent
                        source: "image://match/" + s.imageRevision
                        fillMode: Image.PreserveAspectFit; smooth: true
                        asynchronous: false; cache: false
                    }
                    Item {
                        id: surface
                        objectName: "boardSurface"
                        width: board.paintedWidth; height: board.paintedHeight; anchors.centerIn: parent
                        readonly property real scaleX: width / s.imageWidth
                        readonly property real scaleY: height / s.imageHeight
                        function imageRevision() { return Number(board.source.toString().split("/").pop()) }
                        MouseArea {
                            anchors.fill: parent; acceptedButtons: Qt.LeftButton | Qt.RightButton
                            enabled: board.status === Image.Ready && (window.live || !s.locked || window.table)
                            cursorShape: window.live ? Qt.PointingHandCursor : window.table || s.mode !== "Assign" ? Qt.CrossCursor : Qt.PointingHandCursor
                            onClicked: mouse => ui.click(mouse.x / surface.scaleX, mouse.y / surface.scaleY,
                                                         mouse.button === Qt.LeftButton, surface.imageRevision())
                        }
                        DropArea {
                            anchors.fill: parent; keys: ["unit-recovery"]; enabled: flow.state.kind === "recovery"
                            onDropped: drop => {
                                flow.dropUnit(drop.source.unitId, drop.x / surface.scaleX, drop.y / surface.scaleY,
                                              surface.imageRevision(), drop.source.candidateGeneration)
                                drop.acceptProposedAction()
                            }
                        }
                        DropArea {
                            anchors.fill: parent; keys: ["unit-type"]; enabled: s.editable && board.status === Image.Ready
                            onDropped: drop => {
                                ui.dropType(drop.source.typeId, drop.x / surface.scaleX, drop.y / surface.scaleY, surface.imageRevision())
                                drop.acceptProposedAction()
                            }
                        }
                    }
                    UnitHud {
                        anchors.fill: parent; visible: window.live && flow.state.kind === "live" && s.console.selected; viewData: s.console; z: 2
                        imageRect: Qt.rect(surface.x, surface.y, surface.width, surface.height)
                    }
                    DistanceLabel {
                        anchors.fill: parent; visible: window.live && flow.state.kind === "live" && s.console.query.showDistance; query: s.console.query; z: 3
                        imageRect: Qt.rect(surface.x, surface.y, surface.width, surface.height)
                    }
                }
                ColumnLayout {
                    visible: window.table; Layout.fillWidth: true; spacing: 10
                    Text {
                        text: s.tableMode === "dimensions" ? "Confirm the table dimensions" : s.tableMode === "detecting" ? "Finding table corners…" : s.tableMode === "manual" ? "Mark four corners · " + s.cornerCount + " / 4" : "Are the table corners aligned?"
                        color: "#294354"; font.pixelSize: 18; font.weight: Font.DemiBold
                    }
                    RowLayout {
                        visible: s.tableMode !== "dimensions"; spacing: 10
                        ConsoleButton { objectName: "confirmCorners"; text: "Yes · Continue"; primary: true; enabled: s.canConfirmCorners; onClicked: ui.reviewDimensions() }
                        ConsoleButton { objectName: "manualCorners"; text: s.tableMode === "manual" ? "Clear" : "Manual correction"; onClicked: ui.manualCorners() }
                        ConsoleButton { text: "Auto detect"; enabled: s.tableMode !== "detecting"; onClicked: ui.detectCorners() }
                    }
                    RowLayout {
                        visible: s.tableMode === "dimensions"; spacing: 12
                        Column {
                            spacing: 5
                            Text { text: "Length · TL → TR (in)"; color: "#5e7788" }
                            TextField { id: tableWidth; objectName: "tableWidth"; width: 160; text: s.boardWidth; selectByMouse: true; onAccepted: ui.confirmTable(tableWidth.text, tableDepth.text) }
                        }
                        Column {
                            spacing: 5
                            Text { text: "Width · TL → BL (in)"; color: "#5e7788" }
                            TextField { id: tableDepth; objectName: "tableDepth"; width: 160; text: s.boardDepth; selectByMouse: true; onAccepted: ui.confirmTable(tableWidth.text, tableDepth.text) }
                        }
                        ConsoleButton { text: "Continue"; primary: true; onClicked: ui.confirmTable(tableWidth.text, tableDepth.text) }
                        ConsoleButton { text: "Back"; onClicked: ui.backToCorners() }
                    }
                }
                Text {
                    Layout.fillWidth: true; wrapMode: Text.WordWrap; color: "#607888"; font.pixelSize: 11
                    text: window.table ? "Keep the corner labels on the same physical corners. Dimensions are a manual input." : window.live ? "Click a unit · D distance / L LOS / V move · Esc cancels · source continues" : s.mode === "Front" ? "Click the front edge of the selected tray." : s.mode === "Assign" ? "Click a mask to select it, then choose its type." : "Left click adds a positive point. Right click excludes. Assign a type to continue with the next mask."
                }
            }
            CatalogPanel {
                visible: !window.table && !window.live
                Layout.preferredWidth: 300; Layout.fillHeight: true
                state: s; dragLayer: Overlay.overlay
                onImportRequested: side => { armyFile.side = side; armyFile.open() }
            }
            RecoveryPanel { visible: window.live && flow.state.kind === "recovery"; Layout.preferredWidth: 260; Layout.fillHeight: true }
            UncertaintyPanel {
                visible: window.live && flow.state.kind === "live" && ui.uncertainty.count > 0
                Layout.preferredWidth: window.width < 1000 ? 260 : 300; Layout.fillHeight: true
                viewData: ui.uncertainty; selectedUnit: s.console.unitId
                onInspectRequested: unitId => ui.inspectUnit(unitId)
            }
        }
        LiveConsole {
            visible: window.live && flow.state.kind === "live"; Layout.fillWidth: true
            viewData: s.console; drawerHeight: Math.min(220, window.height * .26)
        }
        Rectangle {
            Layout.fillWidth: true; implicitHeight: statusColumn.implicitHeight + 24; color: "#e4ecf1"
            ColumnLayout {
                id: statusColumn
                anchors.fill: parent; anchors.margins: 12; spacing: 6
                RowLayout {
                    Layout.fillWidth: true
                    Text { Layout.fillWidth: true; elide: Text.ElideRight; text: s.modelLabel; color: s.ready ? "#22765c" : "#44667d"; font.weight: Font.DemiBold }
                    ProgressBar { visible: s.loading; indeterminate: s.progress < 0; value: Math.max(0, s.progress); Layout.preferredWidth: 160 }
                    Text { Layout.maximumWidth: window.width * 0.6; elide: Text.ElideRight; text: "Source " + s.sourceTime + "s · Masks " + s.observationTime + "s · Geometry " + s.geometryTime + "s"; color: "#607b8d"; font.pixelSize: 11 }
                }
                Text { objectName: "statusNote"; Layout.fillWidth: true; text: s.note; color: "#405d70"; wrapMode: Text.WordWrap }
                Text { Layout.fillWidth: true; visible: s.historyWarning.length > 0; text: s.historyWarning; color: "#a23f42"; wrapMode: Text.WordWrap }
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
        anchors.centerIn: parent; modal: true; title: "Start a new registration?"
        standardButtons: Dialog.Yes | Dialog.No
        Label { text: "Current drafts will be cleared. Saved references are kept." }
        onAccepted: ui.reset()
    }
    Shortcut { sequences: [StandardKey.Undo]; enabled: !window.live && !window.modalOpen; onActivated: ui.undo() }
    Shortcut { sequence: "N"; enabled: s.editable && !window.modalOpen; onActivated: ui.newObject() }
    Shortcut { sequence: "F"; enabled: s.canFront && !window.modalOpen; onActivated: ui.setMode("Front") }
    Shortcut { sequence: "S"; enabled: s.editable && !window.modalOpen; onActivated: ui.finish() }
    Shortcut { sequence: "Space"; enabled: !window.table && !window.live && !window.modalOpen; onActivated: ui.start() }
    Shortcut { sequence: "Tab"; enabled: s.editable && !window.modalOpen; onActivated: ui.setMode(s.mode === "Assign" ? "Points" : "Assign") }
    Shortcut { sequence: "D"; enabled: window.live && flow.state.kind === "live" && s.console.canQuery && !window.modalOpen; onActivated: ui.liveTool("distance") }
    Shortcut { sequence: "L"; enabled: window.live && flow.state.kind === "live" && s.console.canQuery && !window.modalOpen; onActivated: ui.liveTool("los") }
    Shortcut { sequence: "V"; enabled: window.live && flow.state.kind === "live" && s.console.canQuery && !window.modalOpen; onActivated: ui.liveTool("move") }
    Shortcut { sequences: ["Left", "A"]; enabled: flow.state.kind === "replay" && !window.modalOpen; onActivated: flow.action("previous") }
    Shortcut { sequences: ["Right", "D"]; enabled: flow.state.kind === "replay" && !window.modalOpen; onActivated: flow.action("next") }
    Shortcut { sequence: "Escape"; enabled: window.live && !window.modalOpen; onActivated: ui.escapeLive() }
    Shortcut { sequences: ["Q", "Space"]; enabled: window.live && !window.modalOpen; onActivated: ui.clearSelection() }
}
