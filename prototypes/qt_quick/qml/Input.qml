import QtQuick
import QtQuick.Controls

TextField {
    id: control
    property var theme
    implicitHeight: 38
    implicitWidth: 120
    leftPadding: 14; rightPadding: 14
    color: theme.ink; placeholderTextColor: theme.dim
    selectionColor: theme.accent; selectedTextColor: "white"
    font.family: "Segoe UI"; font.pixelSize: 13
    background: Rectangle {
        radius: height / 2; color: control.theme.surface
        border.color: control.activeFocus ? control.theme.accent : control.theme.lineBright
    }
}
