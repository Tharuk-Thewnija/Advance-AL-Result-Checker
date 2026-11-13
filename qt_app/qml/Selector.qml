import QtQuick
import QtQuick.Controls

ComboBox {
    id: control
    property var theme
    implicitHeight: 32; implicitWidth: 110
    leftPadding: 12; rightPadding: 28
    contentItem: Text { text: control.displayText; color: control.theme.ink; verticalAlignment: Text.AlignVCenter; font.pixelSize: 12 }
    indicator: Text { text: "⌄"; color: control.theme.muted; x: control.width - 22; y: (control.height - height) / 2 }
    background: Rectangle { color: control.theme.surface; radius: height / 2; border.color: control.activeFocus ? control.theme.accent : control.theme.line }
    delegate: ItemDelegate {
        required property string modelData
        width: control.width
        contentItem: Text { text: parent.modelData; color: control.theme.ink; font.pixelSize: 12 }
        background: Rectangle { color: parent.highlighted ? control.theme.buttonHover : control.theme.panel; radius: 6 }
    }
    popup: Popup {
        y: control.height + 4; width: control.width; padding: 6
        implicitHeight: contentItem.implicitHeight + 12
        contentItem: ListView { implicitHeight: contentHeight; model: control.popup.visible ? control.delegateModel : null; clip: true }
        background: Rectangle { color: control.theme.panel; radius: 12; border.color: control.theme.line }
    }
}
