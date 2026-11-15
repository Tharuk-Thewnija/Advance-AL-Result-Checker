import QtQuick
import QtQuick.Controls

Button {
    id: control
    property var theme
    property bool primary: false
    property string tone: "neutral"
    readonly property color baseColor: primary ? theme.accent : tone === "success" ? theme.exportFill : tone === "stop" ? theme.stopFill : tone === "warning" ? theme.skipFill : tone === "info" ? theme.infoFill : theme.buttonSurface
    readonly property color inkColor: primary || tone === "success" ? "white" : tone === "stop" ? theme.stopInk : tone === "warning" ? theme.skipInk : tone === "info" ? theme.infoInk : theme.ink
    readonly property color edgeColor: tone === "stop" ? theme.stopBorder : tone === "warning" ? theme.skipBorder : tone === "info" ? theme.infoBorder : theme.lineBright
    implicitHeight: 38
    implicitWidth: Math.max(72, contentItem.implicitWidth + 32)
    opacity: enabled ? 1 : 0.45
    padding: 8
    contentItem: Text {
        text: control.text
        color: control.inkColor
        font.family: "Segoe UI"; font.pixelSize: 13; font.bold: control.primary || control.tone !== "neutral"
        horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    background: Rectangle {
        radius: height / 2
        color: control.down ? Qt.darker(control.baseColor, 1.12) : control.hovered ? (control.theme.dark ? Qt.lighter(control.baseColor, 1.12) : Qt.darker(control.baseColor, 1.04)) : control.baseColor
        border.width: control.activeFocus ? 2 : (control.primary || control.tone === "success" ? 0 : 1)
        border.color: control.activeFocus ? control.theme.accentInk : control.edgeColor
    }
}
