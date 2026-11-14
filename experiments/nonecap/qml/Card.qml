import QtQuick

Rectangle {
    id: card
    property var theme
    property int padding: 18
    default property alias contents: body.data
    implicitHeight: body.childrenRect.height + padding * 2
    color: theme.panel
    radius: 16
    border.color: theme.line
    Item { id: body; anchors.fill: parent; anchors.margins: card.padding }
}
