import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: panel
    property var rows: []
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
    onVisibleChanged: if (visible) loadFields()

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
                iconKind: "close"
                text: ""
                variant: "ghost"
                implicitWidth: 28
                implicitHeight: 26
                leftPadding: 0
                rightPadding: 0
                tooltipText: "Close (Esc)"
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

                        // Army-list stat strip matching the floating UnitHud card
                        StatStrip {
                            visible: fieldCol.modelData.kind === "stats"
                            Layout.fillWidth: true
                            stats: fieldCol.modelData.kind === "stats" ? (fieldCol.modelData.value || []) : []
                        }

                        TextField {
                            Layout.fillWidth: true
                            visible: fieldCol.modelData.kind === "text" || fieldCol.modelData.kind === "number"
                            text: (fieldCol.modelData.kind === "text" || fieldCol.modelData.kind === "number")
                                  ? String(fieldCol.modelData.value) : ""
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
                            onTextEdited: panel.rows[fieldCol.index].value = text
                        }

                        // Segmented A / B selector for side / army
                        Rectangle {
                            id: sidePicker
                            visible: fieldCol.modelData.kind === "side"
                            property string selectedSide: fieldCol.modelData.kind === "side"
                                                          ? String(fieldCol.modelData.value || "").trim().toUpperCase() : ""
                            Layout.fillWidth: true
                            implicitHeight: 34
                            radius: panel.theme.radiusSm
                            color: panel.theme.bgTrack
                            border.color: panel.theme.border

                            RowLayout {
                                anchors.fill: parent
                                anchors.margins: 3
                                spacing: 4

                                Repeater {
                                    model: [
                                        { id: "A", label: "Side A" },
                                        { id: "B", label: "Side B" }
                                    ]
                                    Button {
                                        id: sideBtn
                                        required property var modelData
                                        objectName: "unitSide_" + modelData.id
                                        readonly property bool isA: modelData.id === "A"
                                        readonly property bool isSelected: sidePicker.selectedSide === modelData.id
                                        readonly property color tone: isA ? panel.theme.sideA : panel.theme.sideB
                                        readonly property color toneSoft: isA ? panel.theme.sideASoft : panel.theme.sideBSoft
                                        readonly property color toneBorder: isA ? panel.theme.sideABorder : panel.theme.sideBBorder
                                        Layout.fillWidth: true
                                        Layout.fillHeight: true
                                        onClicked: {
                                            sidePicker.selectedSide = sideBtn.modelData.id
                                            panel.rows[fieldCol.index].value = sideBtn.modelData.id
                                        }
                                        background: Rectangle {
                                            radius: panel.theme.radiusXs
                                            color: sideBtn.isSelected ? sideBtn.toneSoft
                                                 : (sideBtn.hovered ? panel.theme.bgSubtle : "transparent")
                                            border.width: sideBtn.isSelected ? 1 : 0
                                            border.color: sideBtn.toneBorder
                                        }
                                        contentItem: RowLayout {
                                            spacing: 6
                                            Item { Layout.fillWidth: true }
                                            Rectangle {
                                                width: 7; height: 7; radius: 4
                                                color: sideBtn.tone
                                                opacity: sideBtn.isSelected ? 1.0 : 0.45
                                            }
                                            Text {
                                                text: sideBtn.modelData.label
                                                color: sideBtn.isSelected ? panel.theme.ink : panel.theme.inkSecondary
                                                font.family: panel.theme.fontBody
                                                font.pixelSize: panel.theme.textSm
                                                font.weight: sideBtn.isSelected ? Font.DemiBold : Font.Normal
                                            }
                                            Item { Layout.fillWidth: true }
                                        }
                                    }
                                }
                            }
                        }

                        // Multi-line auto-wrapping editor for Special rules (no single-line truncation)
                        TextArea {
                            id: rulesArea
                            objectName: fieldCol.modelData.kind === "rules" ? "unitSpecialRules" : ""
                            Layout.fillWidth: true
                            visible: fieldCol.modelData.kind === "rules"
                            implicitHeight: Math.max(58, contentHeight + topPadding + bottomPadding)
                            text: fieldCol.modelData.kind === "rules" ? String(fieldCol.modelData.value || "") : ""
                            wrapMode: TextEdit.Wrap
                            selectByMouse: true
                            color: panel.theme.ink
                            placeholderText: "e.g. Crushing Strength(1), Fly, Nimble"
                            placeholderTextColor: panel.theme.inkMuted
                            selectionColor: panel.theme.accentSoft
                            selectedTextColor: panel.theme.ink
                            font.family: panel.theme.fontBody
                            font.pixelSize: panel.theme.textSm
                            leftPadding: 10
                            rightPadding: 10
                            topPadding: 7
                            bottomPadding: 7
                            background: Rectangle {
                                radius: panel.theme.radiusSm
                                color: panel.theme.bgTrack
                                border.width: rulesArea.activeFocus ? 1.5 : 1
                                border.color: rulesArea.activeFocus ? panel.theme.selection : panel.theme.border
                            }
                            onTextChanged: {
                                if (fieldCol.modelData.kind === "rules" && fieldCol.index >= 0 && fieldCol.index < panel.rows.length) {
                                    panel.rows[fieldCol.index].value = text
                                }
                            }
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
                                text: fieldCol.modelData.kind === "readonly" ? String(fieldCol.modelData.value || "") : ""
                                textFormat: TextEdit.PlainText
                                readOnly: true
                                selectByMouse: true
                                wrapMode: TextEdit.Wrap
                                color: panel.theme.ink
                                font.family: panel.theme.fontBody
                                font.pixelSize: panel.theme.textXs
                            }
                        }

                        ConsoleComboBox {
                            id: infoCombo
                            Layout.fillWidth: true
                            visible: fieldCol.modelData.kind === "choice"
                            model: fieldCol.modelData.optionLabels || fieldCol.modelData.options || []
                            currentIndex: {
                                const opts = fieldCol.modelData.options || []
                                const found = opts.indexOf(String(fieldCol.modelData.value))
                                return found >= 0 ? found : 0
                            }
                            onActivated: idx => {
                                const opts = fieldCol.modelData.options || []
                                if (idx >= 0 && idx < opts.length) {
                                    panel.rows[fieldCol.index].value = opts[idx]
                                }
                            }
                        }

                        ConsoleCheckBox {
                            id: infoChk
                            visible: fieldCol.modelData.kind === "bool"
                            text: fieldCol.modelData.label
                            checked: Boolean(fieldCol.modelData.value)
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
                text: "Cancel"
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
