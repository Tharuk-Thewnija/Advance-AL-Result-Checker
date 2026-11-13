import QtQuick
import QtQuick.Controls

CheckBox {
    id: control
    property var theme
    implicitHeight: Math.max(32, contentItem.implicitHeight + 10)
    leftPadding: 28; rightPadding: 6; topPadding: 5; bottomPadding: 5
    opacity: enabled ? 1 : 0.5
    contentItem: Text {
        text: control.text; color: control.theme.ink; wrapMode: Text.WordWrap
        font.family: "Segoe UI"; font.pixelSize: 12
        verticalAlignment: Text.AlignVCenter
    }
    indicator: Rectangle {
        x: 1; y: (control.height - height) / 2; width: 18; height: 18; radius: 5
        color: control.checked ? control.theme.accent : "transparent"
        border.width: 2
        border.color: control.checked || control.activeFocus ? control.theme.accent : control.theme.lineBright
        Text { anchors.centerIn: parent; text: "✓"; visible: control.checked; color: "white"; font.pixelSize: 13 }
    }
    background: Rectangle { radius: 6; color: control.hovered ? control.theme.buttonSurface : "transparent" }
}
