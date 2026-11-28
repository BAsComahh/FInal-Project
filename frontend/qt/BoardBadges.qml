import QtQuick
import QtQuick.Layouts

Item {
    id: badgeLayer
    property var badges: []
    property string selectedUnitId: ""
    property string targetUnitId: ""
    property string selectedTerrainId: ""
    property int hoverObjectId: -1
    readonly property Theme theme: Theme {}

    Repeater {
        model: badgeLayer.badges
        Rectangle {
            id: pill
            required property var modelData
            readonly property bool isTerrain: modelData.kind === "terrain"
            readonly property bool isDropHover: !isTerrain && badgeLayer.hoverObjectId > 0 && modelData.objectId === badgeLayer.hoverObjectId
            readonly property bool isSelected: isTerrain
                ? (Boolean(modelData.active) || (badgeLayer.selectedTerrainId.length > 0 && modelData.unitId === badgeLayer.selectedTerrainId))
                : (Boolean(modelData.active) || (badgeLayer.selectedUnitId.length > 0 && modelData.unitId === badgeLayer.selectedUnitId))
            readonly property bool isTarget: !isTerrain && badgeLayer.targetUnitId.length > 0 && modelData.unitId === badgeLayer.targetUnitId
            readonly property bool isNeedsWork: !isTerrain && ((modelData.unitId || "").length === 0 || Boolean(modelData.unconfirmed))
            readonly property real targetH: Math.max(18, Math.round(modelData.h * badgeLayer.height))
            readonly property real targetW: Math.max(row.implicitWidth + 14, Math.round(modelData.w * badgeLayer.width))

            width: targetW
            height: targetH
            x: Math.max(2, Math.min(badgeLayer.width - width - 2,
               (modelData.x + modelData.w * 0.5) * badgeLayer.width - width * 0.5))
            y: Math.max(2, Math.min(badgeLayer.height - height - 2,
               (modelData.y + modelData.h * 0.5) * badgeLayer.height - height * 0.5))
            radius: height / 2
            color: isDropHover ? badgeLayer.theme.badgeDropFill
                 : isSelected ? badgeLayer.theme.badgeSelectedFill
                 : isNeedsWork ? badgeLayer.theme.badgeNeedsWorkFill
                 : (isTerrain ? badgeLayer.theme.badgeTerrainFill : badgeLayer.theme.badgeFill)
            border.width: isDropHover ? 2 : (isSelected || isTarget || isNeedsWork) ? 1.5 : 1
            border.color: isDropHover ? "#36d399"
                        : isSelected ? badgeLayer.theme.overlaySelection
                        : isTarget ? "#36d399"
                        : isNeedsWork ? "#ff9150"
                        : isTerrain ? modelData.border
                        : badgeLayer.theme.badgeBorder

            RowLayout {
                id: row
                anchors.centerIn: parent
                spacing: 5

                Rectangle {
                    visible: (pill.modelData.dot || "").length > 0 || pill.isNeedsWork
                    width: Math.max(6, Math.round(pill.height * 0.34))
                    height: width
                    radius: width / 2
                    color: (pill.modelData.dot || "").length > 0 ? pill.modelData.dot : "#ff9150"
                }

                Text {
                    text: pill.modelData.text
                    color: pill.isSelected ? badgeLayer.theme.overlaySelection : badgeLayer.theme.badgeInk
                    font.family: badgeLayer.theme.fontBody
                    font.pixelSize: Math.max(10, Math.min(12, Math.round(pill.height * 0.55)))
                    font.weight: Font.DemiBold
                }
            }
        }
    }
}
