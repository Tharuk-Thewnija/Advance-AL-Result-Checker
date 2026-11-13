import QtQuick
import QtQuick.Controls

Button {
    id: control
    property var theme
    property bool primary: false
    implicitHeight: 38
    implicitWidth: Math.max(72, contentItem.implicitWidth + 32)
    opacity: enabled ? 1 : 0.45
    padding: 8
    contentItem: Text {
        text: control.text
        color: control.primary ? "white" : control.theme.ink
        font.family: "Segoe UI"; font.pixelSize: 13; font.bold: control.primary
        horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    background: Rectangle {
        radius: height / 2
        color: control.primary ? (control.hovered ? control.theme.hover : control.theme.accent)
                               : (control.hovered ? control.theme.buttonHover : control.theme.buttonSurface)
        border.width: control.primary ? 0 : 1
        border.color: control.activeFocus ? control.theme.accent : control.theme.lineBright
    }
}
