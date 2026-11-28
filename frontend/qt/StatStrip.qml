import QtQuick
import QtQuick.Layouts

Rectangle {
    id: strip
    property var stats: []
    property bool compact: false
    readonly property Theme theme: Theme {}
    readonly property int headerHeight: compact ? 20 : 22
    readonly property int valueHeight: compact ? 24 : 26

    implicitHeight: headerHeight + 1 + valueHeight
    Layout.preferredHeight: implicitHeight
    Layout.minimumHeight: implicitHeight
    radius: theme.radiusSm
    color: theme.bgTrack
    border.color: theme.borderSoft
    clip: true

    Column {
        anchors.fill: parent
        spacing: 0

        // Army-list stat header row (Sp Me Sh De US Att Ne Ht)
        RowLayout {
            width: parent.width
            height: strip.headerHeight
            spacing: 0

            Repeater {
                model: strip.stats || []
                Item {
                    id: headerCell
                    required property var modelData
                    required property int index
                    Layout.fillWidth: true
                    Layout.fillHeight: true

                    Rectangle {
                        visible: headerCell.index > 0
                        anchors.left: parent.left
                        anchors.top: parent.top
                        anchors.bottom: parent.bottom
                        anchors.topMargin: 3
                        anchors.bottomMargin: 2
                        width: 1
                        color: strip.theme.borderSoft
                        opacity: 0.65
                    }

                    Text {
                        anchors.centerIn: parent
                        text: headerCell.modelData.label || ""
                        color: strip.theme.inkSecondary
                        font.family: strip.theme.fontBody
                        font.pixelSize: strip.theme.textXs
                        font.weight: Font.DemiBold
                    }
                }
            }
        }

        Rectangle {
            width: parent.width
            height: 1
            color: strip.theme.border
        }

        // Tabular stat values row
        RowLayout {
            width: parent.width
            height: strip.valueHeight
            spacing: 0

            Repeater {
                model: strip.stats || []
                Item {
                    id: valueCell
                    required property var modelData
                    required property int index
                    Layout.fillWidth: true
                    Layout.fillHeight: true

                    Rectangle {
                        visible: valueCell.index > 0
                        anchors.left: parent.left
                        anchors.top: parent.top
                        anchors.bottom: parent.bottom
                        anchors.topMargin: 2
                        anchors.bottomMargin: 3
                        width: 1
                        color: strip.theme.borderSoft
                        opacity: 0.65
                    }

                    Text {
                        objectName: valueCell.modelData.objectName || ""
                        anchors.centerIn: parent
                        text: valueCell.modelData.value || "—"
                        color: (valueCell.modelData.value || "—") === "—"
                               ? strip.theme.inkMuted : strip.theme.ink
                        font.family: strip.theme.fontMono
                        font.pixelSize: strip.compact ? strip.theme.textSm : strip.theme.textMd
                        font.weight: Font.DemiBold
                    }
                }
            }
        }
    }
}
