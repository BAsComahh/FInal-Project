import QtQuick
import QtQuick.Layouts

Item {
    id: overlay
    required property var query
    property rect imageRect: Qt.rect(0, 0, width, height)
    readonly property Theme theme: Theme {}
    visible: query.showDistance

    Rectangle {
        x: pill.x; y: pill.y + 3
        width: pill.width; height: pill.height
        radius: pill.radius; color: "#26131d24"
    }

    Rectangle {
        id: pill
        objectName: "distanceLabel"
        width: Math.min(contentCol.implicitWidth + 24, Math.max(0, overlay.width - 12))
        height: contentCol.implicitHeight + 12
        x: Math.max(6, Math.min(overlay.width - width - 6, overlay.imageRect.x + overlay.query.labelX * overlay.imageRect.width - width / 2))
        y: Math.max(6, Math.min(overlay.height - height - 6, overlay.imageRect.y + overlay.query.labelY * overlay.imageRect.height - height / 2))
        radius: 10
        color: "#fcffffff"
        border.color: overlay.theme.accentBorder
        border.width: 1

        Column {
            id: contentCol
            anchors.centerIn: parent
            spacing: 2
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: overlay.query.metric
                color: overlay.theme.accent
                font.family: overlay.theme.fontBody
                font.pixelSize: 13
                font.weight: Font.DemiBold
            }
            Text {
                visible: overlay.query.fixed
                anchors.horizontalCenter: parent.horizontalCenter
                text: "Snapshot · " + overlay.query.observed
                color: overlay.theme.inkMuted
                font.family: overlay.theme.fontMono
                font.pixelSize: 10
            }
        }
    }
}
