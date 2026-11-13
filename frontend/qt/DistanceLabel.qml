import QtQuick

Item {
    id: overlay
    required property var query
    property rect imageRect: Qt.rect(0, 0, width, height)
    visible: query.showDistance
    Rectangle {
        objectName: "distanceLabel"
        width: Math.min(label.implicitWidth + 20, Math.max(0, overlay.width - 12))
        height: label.implicitHeight + 12
        x: Math.max(6, Math.min(overlay.width - width - 6, overlay.imageRect.x + overlay.query.labelX * overlay.imageRect.width - width / 2))
        y: Math.max(6, Math.min(overlay.height - height - 6, overlay.imageRect.y + overlay.query.labelY * overlay.imageRect.height - height / 2))
        radius: 8; color: "#fcffffff"; border.color: "#9cc1d1"
        Text {
            id: label
            anchors.centerIn: parent
            text: overlay.query.metric; color: "#246b89"
            font.family: "Segoe UI"; font.pixelSize: 13; font.weight: Font.DemiBold
        }
    }
}
