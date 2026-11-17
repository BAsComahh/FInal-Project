import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: panel
    objectName: "liveConsole"
    required property var viewData
    property real drawerHeight: 176
    readonly property bool drawerOpen: viewData.tool === "los" || viewData.tool === "move"
    readonly property Theme theme: Theme {}

    readonly property string queryStatus: viewData.query.status || "waiting"
    readonly property color statusColor: {
        if (queryStatus === "ok" || queryStatus === "clear") return theme.success
        if (queryStatus === "blocked" || queryStatus === "unavailable") return theme.modeRecovery
        if (queryStatus === "uncertain") return theme.warning
        return theme.selection
    }
    readonly property color statusBg: {
        if (queryStatus === "ok" || queryStatus === "clear") return theme.successSoft
        if (queryStatus === "blocked" || queryStatus === "unavailable") return theme.dangerSoft
        if (queryStatus === "uncertain") return theme.warningSoft
        return theme.accentSoft
    }
    readonly property color statusBorder: {
        if (queryStatus === "ok" || queryStatus === "clear") return theme.successBorder
        if (queryStatus === "blocked" || queryStatus === "unavailable") return theme.dangerBorder
        if (queryStatus === "uncertain") return theme.warningBorder
        return theme.accentBorder
    }

    color: theme.bgSurface
    radius: theme.radiusLg
    border.color: theme.border
    clip: true
    implicitHeight: bar.implicitHeight + (drawerOpen ? drawerHeight : 0)

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            id: bar
            Layout.fillWidth: true
            implicitHeight: Math.max(40, captionRow.implicitHeight + 14)
            color: theme.bgSubtle

            RowLayout {
                id: captionRow
                anchors.fill: parent
                anchors.leftMargin: 14
                anchors.rightMargin: 12
                spacing: 10

                Rectangle {
                    width: 8; height: 8; radius: 4
                    color: {
                        if (panel.viewData.selected && !panel.viewData.canQuery) return panel.theme.warning
                        if (panel.viewData.tool !== "select") return panel.theme.selection
                        if (panel.viewData.selected) return panel.theme.modeLiveDot
                        return panel.theme.borderStrong
                    }
                }

                Text {
                    id: caption
                    text: panel.viewData.caption
                          + (panel.viewData.tool === "distance" && panel.viewData.query.reason ? " · " + panel.viewData.query.reason
                             : panel.viewData.selected && !panel.viewData.canQuery ? " · " + panel.viewData.queryBlock : "")
                    color: panel.viewData.selected && !panel.viewData.canQuery ? panel.theme.warning : panel.theme.inkSecondary
                    font.pixelSize: panel.theme.textSm
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }

                ConsoleButton {
                    objectName: "doneDistance"
                    text: "Done"
                    implicitHeight: 28
                    visible: panel.viewData.tool === "distance"
                    onClicked: ui.doneTool()
                }
                ConsoleButton {
                    objectName: "clearSelection"
                    text: "Clear selection"
                    variant: "subtle"
                    implicitHeight: 28
                    visible: panel.viewData.selected
                    onClicked: ui.clearSelection()
                }
            }
        }

        Rectangle {
            visible: panel.drawerOpen
            Layout.fillWidth: true
            Layout.preferredHeight: panel.drawerHeight
            color: panel.theme.bgSurface

            Rectangle { width: parent.width; height: 1; color: panel.theme.border }
            Rectangle { width: 4; height: parent.height; color: panel.statusColor }

            ColumnLayout {
                anchors.fill: parent
                anchors.leftMargin: 16
                anchors.rightMargin: 14
                anchors.topMargin: 12
                anchors.bottomMargin: 12
                spacing: 8

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Text {
                            text: panel.viewData.query.title + " · " + panel.viewData.unitId
                                  + (panel.viewData.targetId ? " → " + panel.viewData.targetId : "")
                            color: panel.theme.ink
                            font.family: panel.theme.fontDisplay
                            font.pixelSize: panel.theme.textLg
                            font.weight: Font.DemiBold
                            elide: Text.ElideRight
                        }
                        Rectangle {
                            implicitWidth: statusLabel.implicitWidth + 14
                            implicitHeight: 22
                            radius: height / 2
                            color: panel.statusBg
                            border.color: panel.statusBorder
                            Text {
                                id: statusLabel
                                anchors.centerIn: parent
                                text: panel.queryStatus.toUpperCase()
                                color: panel.statusColor
                                font.family: panel.theme.fontMono
                                font.pixelSize: panel.theme.textXs
                                font.weight: Font.DemiBold
                            }
                        }
                        Text {
                            text: "Observed " + panel.viewData.query.observed
                            color: panel.theme.inkMuted
                            font.family: panel.theme.fontMono
                            font.pixelSize: panel.theme.textXs
                        }
                        Item { Layout.fillWidth: true }
                    }

                    Text {
                        objectName: "queryMetric"
                        visible: panel.viewData.query.metric.length > 0
                        text: panel.viewData.query.metric
                        color: panel.theme.selection
                        font.family: panel.theme.fontDisplay
                        font.pixelSize: panel.width < 950 ? panel.theme.textLg : panel.theme.textXl
                        font.weight: Font.DemiBold
                    }

                    ConsoleButton {
                        objectName: "doneTool"
                        text: "Done"
                        implicitHeight: 30
                        onClicked: ui.doneTool()
                    }
                }

                Flow {
                    visible: panel.viewData.tool === "move"
                    Layout.fillWidth: true
                    spacing: 6
                    Repeater {
                        model: ui.moveOrders
                        ConsoleButton {
                            required property var modelData
                            objectName: "order_" + modelData.id
                            text: modelData.label
                            implicitHeight: 28
                            cornerRadius: panel.theme.radiusSm
                            primary: panel.viewData.order === modelData.id
                            onClicked: ui.moveOrder(modelData.id)
                        }
                    }
                }

                ScrollView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                    TextArea {
                        objectName: "queryExplanation"
                        text: panel.viewData.query.reason
                              + (panel.viewData.query.warnings.length ? "\n" + panel.viewData.query.warnings.join("\n") : "")
                        readOnly: true
                        selectByMouse: true
                        wrapMode: TextEdit.Wrap
                        color: panel.theme.inkSecondary
                        font.family: panel.theme.fontBody
                        font.pixelSize: panel.theme.textSm
                        padding: 0
                        background: null
                    }
                }
            }
        }
    }
}
