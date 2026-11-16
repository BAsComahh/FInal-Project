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
        if (queryStatus === "blocked" || queryStatus === "unavailable") return theme.danger
        if (queryStatus === "uncertain") return theme.warning
        return theme.accent
    }
    readonly property color statusBg: {
        if (queryStatus === "ok" || queryStatus === "clear") return theme.successSoft
        if (queryStatus === "blocked" || queryStatus === "unavailable") return theme.dangerSoft
        if (queryStatus === "uncertain") return theme.warningSoft
        return theme.accentSoft
    }

    color: theme.bgSurface
    radius: 10
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
                        if (panel.viewData.tool !== "select") return panel.theme.accent
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
                    font.pixelSize: 12
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

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 3
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8
                            Text {
                                text: panel.viewData.query.title + " · " + panel.viewData.unitId
                                      + (panel.viewData.targetId ? " → " + panel.viewData.targetId : "")
                                color: panel.theme.ink
                                font.family: panel.theme.fontDisplay
                                font.pixelSize: 15
                                font.weight: Font.DemiBold
                                elide: Text.ElideRight
                            }
                            Rectangle {
                                implicitWidth: statusLabel.implicitWidth + 14
                                implicitHeight: 20
                                radius: 10
                                color: panel.statusBg
                                Text {
                                    id: statusLabel
                                    anchors.centerIn: parent
                                    text: panel.queryStatus.toUpperCase()
                                    color: panel.statusColor
                                    font.family: panel.theme.fontMono
                                    font.pixelSize: 10
                                    font.weight: Font.DemiBold
                                }
                            }
                            Text {
                                text: "Observed " + panel.viewData.query.observed
                                color: panel.theme.inkMuted
                                font.family: panel.theme.fontMono
                                font.pixelSize: 11
                            }
                            Item { Layout.fillWidth: true }
                        }
                    }

                    Text {
                        objectName: "queryMetric"
                        visible: panel.viewData.query.metric.length > 0
                        text: panel.viewData.query.metric
                        color: panel.theme.accent
                        font.family: panel.theme.fontDisplay
                        font.pixelSize: panel.width < 950 ? 17 : 21
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
                            cornerRadius: 6
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
                        font.pixelSize: 12
                        padding: 0
                        background: null
                    }
                }
            }
        }
    }
}
