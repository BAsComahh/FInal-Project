import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: panel
    property var rows: []
    property int focusedInputs: 0
    readonly property bool editingFocus: focusedInputs > 0
    readonly property Theme theme: Theme {}

    radius: theme.radiusLg
    color: theme.bgSurface
    border.color: theme.border

    function loadFields() {
        rows = (flow.fields || []).map(row => ({
            key: row.key,
            label: row.label,
            kind: row.kind,
            value: row.value,
            options: row.options || [],
            optionLabels: row.optionLabels || []
        }))
    }

    Component.onCompleted: loadFields()
    onVisibleChanged: {
        if (!visible) focusedInputs = 0
        else loadFields()
    }

    Connections {
        target: flow
        function onProfileLoaded() { panel.loadFields() }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 14
        spacing: 10

        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            Rectangle {
                width: 8; height: 8; radius: 4
                color: panel.theme.selection
            }
            Text {
                text: flow.formTitle || "Unit information"
                color: panel.theme.ink
                font.family: panel.theme.fontDisplay
                font.pixelSize: panel.theme.textLg
                font.weight: Font.DemiBold
                Layout.fillWidth: true
                elide: Text.ElideRight
            }
            ConsoleButton {
                objectName: "closeUnitInfo"
                text: "Close"
                variant: "subtle"
                implicitHeight: 26
                onClicked: flow.closeProfile()
            }
        }

        Rectangle { Layout.fillWidth: true; height: 1; color: panel.theme.borderSoft }

        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentWidth: availableWidth
            clip: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

            ColumnLayout {
                width: parent.width
                spacing: 10

                Repeater {
                    model: panel.rows
                    ColumnLayout {
                        id: fieldCol
                        required property var modelData
                        required property int index
                        Layout.fillWidth: true
                        spacing: 4

                        Text {
                            visible: fieldCol.modelData.kind !== "bool"
                            text: fieldCol.modelData.label
                            color: panel.theme.inkSecondary
                            font.pixelSize: panel.theme.textXs
                            font.weight: Font.DemiBold
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                        }

                        TextField {
                            Layout.fillWidth: true
                            visible: fieldCol.modelData.kind === "text" || fieldCol.modelData.kind === "number" || fieldCol.modelData.kind === "rules"
                            text: String(fieldCol.modelData.value)
                            selectByMouse: true
                            color: panel.theme.ink
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
                                border.width: parent.activeFocus ? 1.5 : 1
                                border.color: parent.activeFocus ? panel.theme.selection : panel.theme.border
                            }
                            onActiveFocusChanged: {
                                if (activeFocus) panel.focusedInputs += 1
                                else panel.focusedInputs = Math.max(0, panel.focusedInputs - 1)
                            }
                            onTextEdited: panel.rows[fieldCol.index].value = text
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            visible: fieldCol.modelData.kind === "readonly"
                            implicitHeight: refText.implicitHeight + 12
                            radius: panel.theme.radiusSm
                            color: panel.theme.bgSubtle
                            border.color: panel.theme.borderSoft

                            TextEdit {
                                id: refText
                                anchors.fill: parent
                                anchors.margins: 6
                                text: String(fieldCol.modelData.value || "")
                                textFormat: TextEdit.PlainText
                                readOnly: true
                                selectByMouse: true
                                wrapMode: TextEdit.Wrap
                                color: panel.theme.ink
                                font.family: panel.theme.fontBody
                                font.pixelSize: panel.theme.textXs
                            }
                        }

                        ComboBox {
                            id: infoCombo
                            Layout.fillWidth: true
                            visible: fieldCol.modelData.kind === "choice"
                            model: fieldCol.modelData.optionLabels || fieldCol.modelData.options || []
                            currentIndex: {
                                const opts = fieldCol.modelData.options || []
                                const found = opts.indexOf(String(fieldCol.modelData.value))
                                return found >= 0 ? found : 0
                            }
                            contentItem: Text {
                                leftPadding: 10
                                text: infoCombo.displayText
                                color: panel.theme.ink
                                font.family: panel.theme.fontBody
                                font.pixelSize: panel.theme.textSm
                                verticalAlignment: Text.AlignVCenter
                                elide: Text.ElideRight
                            }
                            background: Rectangle {
                                implicitHeight: 32
                                radius: panel.theme.radiusSm
                                color: panel.theme.bgTrack
                                border.color: infoCombo.activeFocus ? panel.theme.selection : panel.theme.border
                            }
                            onActivated: idx => {
                                const opts = fieldCol.modelData.options || []
                                if (idx >= 0 && idx < opts.length) {
                                    panel.rows[fieldCol.index].value = opts[idx]
                                }
                            }
                        }

                        CheckBox {
                            id: infoChk
                            visible: fieldCol.modelData.kind === "bool"
                            text: fieldCol.modelData.label
                            checked: Boolean(fieldCol.modelData.value)
                            contentItem: Text {
                                leftPadding: infoChk.indicator.width + infoChk.spacing
                                text: infoChk.text
                                color: panel.theme.ink
                                font.pixelSize: panel.theme.textSm
                                verticalAlignment: Text.AlignVCenter
                            }
                            onToggled: panel.rows[fieldCol.index].value = checked
                        }
                    }
                }
            }
        }

        Rectangle {
            visible: flow.formError.length > 0
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

        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            ConsoleButton {
                text: "Close"
                variant: "subtle"
                Layout.fillWidth: true
                onClicked: flow.closeProfile()
            }
            ConsoleButton {
                objectName: "saveUnitInfo"
                text: "Save"
                primary: true
                Layout.fillWidth: true
                onClicked: flow.saveForm(panel.rows)
            }
        }
    }
}
