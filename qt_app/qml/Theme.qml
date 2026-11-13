import QtQuick

QtObject {
    property bool dark: true
    readonly property color bg: dark ? "#0B0B10" : "#EDF1F7"
    readonly property color shell: dark ? "#121219" : "#F6F8FC"
    readonly property color panel: dark ? "#181822" : "#FFFFFF"
    readonly property color surface: dark ? "#111118" : "#F0F3F9"
    readonly property color ink: dark ? "#F3F4F8" : "#111827"
    readonly property color muted: dark ? "#8B8E9F" : "#5E6B80"
    readonly property color dim: dark ? "#5B5E70" : "#8D99AD"
    readonly property color line: dark ? "#262634" : "#DCE3EE"
    readonly property color lineBright: dark ? "#343448" : "#C5D0E2"
    readonly property color accent: dark ? "#6147E5" : "#5941D6"
    readonly property color hover: dark ? "#7259F0" : "#4832BE"
    readonly property color accentSoft: dark ? "#231D42" : "#EAE6FD"
    readonly property color accentInk: dark ? "#A799FF" : "#4A35B8"
    readonly property color buttonSurface: dark ? "#1E1E2B" : "#E9EEF6"
    readonly property color buttonHover: dark ? "#29293A" : "#DCE4F0"
    readonly property color success: dark ? "#34D399" : "#059669"
    readonly property color warn: dark ? "#FBBF24" : "#D97706"
    readonly property color danger: dark ? "#F87171" : "#DC2626"
}
