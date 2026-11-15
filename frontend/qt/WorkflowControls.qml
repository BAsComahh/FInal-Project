import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: controls
    readonly property bool formOpen: editor.visible
    Layout.fillWidth: true
    Flow {
        Layout.fillWidth: true; spacing: 6
        Repeater {
            model: [{id:"recover",label:"Recover units"},{id:"recalibrate",label:"Recalibrate"},
                    {id:"profile",label:"Unit information"},{id:"terrain",label:"Terrain"},{id:"replay",label:"Replay"}]
            ConsoleButton {
                required property var modelData
                text: modelData.label; enabled: flow.state.kind === "live"
                onClicked: flow.open(modelData.id)
            }
        }
        ConsoleButton { text: "Undo terrain"; enabled: flow.state.kind === "live"; onClicked: flow.action("undoTerrain") }
        ConsoleButton { text: "Cancel / Back to Live"; visible: flow.state.kind !== "live"; enabled: !flow.state.busy; onClicked: flow.action("cancel") }
        ConsoleButton { text: "Clear / Retry"; visible: flow.state.kind === "recovery"; enabled: !flow.state.busy; onClicked: flow.action("clear") }
        ConsoleButton { text: "Correct"; primary: true; visible: flow.state.kind === "recovery" && flow.state.review; enabled: !flow.state.busy; onClicked: flow.action("correct") }
        ConsoleButton { text: "No / Search again"; visible: flow.state.kind === "recovery" && flow.state.review; enabled: !flow.state.busy; onClicked: flow.action("reject") }
        ConsoleButton { text: "Save polygon"; visible: flow.state.kind === "terrain"; enabled: flow.state.pointCount >= 3; onClicked: flow.finishTerrain() }
        ConsoleButton { text: "Previous"; visible: flow.state.kind === "replay"; enabled: flow.state.step > 0; onClicked: flow.action("previous") }
        ConsoleButton { text: "Next"; visible: flow.state.kind === "replay"; enabled: flow.state.step + 1 < flow.state.steps; onClicked: flow.action("next") }
        ConsoleButton { text: "Refresh"; visible: flow.state.kind === "replay"; onClicked: flow.action("refresh") }
    }
    RowLayout {
        visible: flow.state.kind === "recalibrate"
        onVisibleChanged: if (visible) { length.text = ui.state.boardWidth; depth.text = ui.state.boardDepth }
        Label { text: "Raw video · corners " + flow.state.pointCount + "/4 · Length × Width (in)" }
        TextField { id: length; text: ui.state.boardWidth; Layout.preferredWidth: 80 }
        TextField { id: depth; text: ui.state.boardDepth; Layout.preferredWidth: 80 }
        ConsoleButton { text: "Apply"; enabled: flow.state.pointCount === 4 && !flow.state.calibrationPending; onClicked: flow.applyCalibration(length.text, depth.text) }
    }
    Label {
        Layout.fillWidth: true; wrapMode: Text.WordWrap
        visible: flow.state.kind !== "live"
        text: flow.state.kind === "terrain" ? "Click polygon vertices; right click removes the last point." :
              flow.state.kind === "recalibrate" ? "Click four raw-video corners; right click undoes. Source continues." :
              flow.state.kind === "recovery" ? "Candidate " + flow.state.candidateTime + " · positive / negative points, then drag an existing ID onto the yellow candidate. " + flow.state.note :
              flow.state.note
    }
    Dialog {
        id: editor
        property var rows: []
        title: flow.formTitle; modal: true; anchors.centerIn: Overlay.overlay
        width: Math.min(600, Overlay.overlay.width - 40); height: Math.min(620, Overlay.overlay.height - 40)
        ColumnLayout {
            anchors.fill: parent
            ScrollView {
                Layout.fillWidth: true; Layout.fillHeight: true; contentWidth: availableWidth
                ColumnLayout {
                    width: parent.width
                    Repeater {
                        model: editor.rows
                        ColumnLayout {
                            required property var modelData
                            required property int index
                            Layout.fillWidth: true
                            Label { text: modelData.label }
                            TextField { Layout.fillWidth: true; visible: modelData.kind !== "bool"; text: String(modelData.value); onTextEdited: editor.rows[index].value = text }
                            CheckBox { visible: modelData.kind === "bool"; checked: Boolean(modelData.value); onToggled: editor.rows[index].value = checked }
                        }
                    }
                }
            }
            Label { text: ui.state.note; wrapMode: Text.WordWrap; Layout.fillWidth: true; color: "#a92d37" }
            RowLayout {
                ConsoleButton { text: "Cancel"; onClicked: editor.close() }
                ConsoleButton { text: "Save"; primary: true; onClicked: { if (flow.saveForm(editor.rows)) editor.close() } }
            }
        }
    }
    Connections {
        target: flow
        function onFormRequested() {
            editor.rows = flow.fields.map(row => ({key:row.key,label:row.label,kind:row.kind,value:row.value}))
            editor.open()
        }
    }
}
