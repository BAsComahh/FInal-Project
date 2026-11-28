import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: dialogs
    readonly property Theme theme: Theme {}
    readonly property bool formOpen: editor.visible || undoTerrainDialog.visible

    function openUndoConfirm() {
        undoTerrainDialog.open()
    }

    component DarkField: TextField {
        id: df
        readonly property Theme t: dialogs.theme
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

    Dialog {
        id: undoTerrainDialog
        anchors.centerIn: Overlay.overlay
        modal: true
        title: "Remove last terrain?"
        standardButtons: Dialog.Yes | Dialog.No
        Overlay.modal: Rectangle { color: dialogs.theme.scrim }
        background: Rectangle {
            color: dialogs.theme.bgSurface
            radius: dialogs.theme.radiusLg
            border.color: dialogs.theme.borderStrong
        }
        header: Rectangle {
            implicitHeight: 44
            color: "transparent"
            Text {
                anchors.verticalCenter: parent.verticalCenter
                anchors.left: parent.left
                anchors.leftMargin: 18
                text: undoTerrainDialog.title
                color: dialogs.theme.ink
                font.family: dialogs.theme.fontDisplay
                font.pixelSize: dialogs.theme.textLg
                font.weight: Font.DemiBold
            }
        }
        Label {
            text: "Remove the most recently saved terrain polygon from the match scene?"
            color: dialogs.theme.inkSecondary
            font.pixelSize: dialogs.theme.textSm
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
        height: Math.min(540, Overlay.overlay.height - 40)
        onClosed: flow.clearFormError()
        Overlay.modal: Rectangle { color: dialogs.theme.scrim }
        background: Rectangle {
            color: dialogs.theme.bgSurface
            radius: dialogs.theme.radiusLg
            border.color: dialogs.theme.borderStrong
        }
        header: Rectangle {
            implicitHeight: 46
            color: "transparent"
            Text {
                anchors.verticalCenter: parent.verticalCenter
                anchors.left: parent.left
                anchors.leftMargin: 18
                text: editor.title
                color: dialogs.theme.ink
                font.family: dialogs.theme.fontDisplay
                font.pixelSize: dialogs.theme.textLg
                font.weight: Font.DemiBold
            }
            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: 1
                color: dialogs.theme.borderSoft
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
                                color: dialogs.theme.inkSecondary
                                font.pixelSize: dialogs.theme.textSm
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

                            ConsoleComboBox {
                                id: combo
                                Layout.fillWidth: true
                                implicitHeight: 34
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
                                        if (modelData.key === "kind")
                                            editor.obstacle = opts[idx] === "obstacle"
                                    }
                                }
                            }
                        }
                    }
                }
            }

            Rectangle {
                visible: flow.formError.length > 0
                Layout.fillWidth: true
                implicitHeight: errTxt.implicitHeight + 12
                radius: dialogs.theme.radiusSm
                color: dialogs.theme.dangerSoft
                border.color: dialogs.theme.dangerBorder
                Text {
                    id: errTxt
                    anchors.fill: parent
                    anchors.margins: 6
                    text: flow.formError
                    color: dialogs.theme.modeRecovery
                    wrapMode: Text.WordWrap
                    font.pixelSize: dialogs.theme.textSm
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                ConsoleButton { text: "Cancel"; variant: "subtle"; onClicked: editor.close() }
                ConsoleButton {
                    objectName: "saveTerrainForm"
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
