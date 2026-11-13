import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: win
    objectName: "prototypeWindow"
    width: 1180; height: 880; minimumWidth: 1020; minimumHeight: 750
    visible: true
    title: "A/L Results Collector — Qt Quick prototype"
    color: t.bg
    font.family: "Segoe UI"; font.pixelSize: 13
    Theme { id: t; dark: bridge.theme === "Dark" || (bridge.theme === "System" && bridge.systemDark) }
    component Caption: Text { color: t.accentInk; font.pixelSize: 11; font.bold: true }
    component Heading: Text { color: t.ink; font.pixelSize: 16; font.bold: true }
    component Hint: Text { color: t.muted; font.pixelSize: 12; wrapMode: Text.WordWrap }

    ColumnLayout {
        anchors.fill: parent; anchors.margins: 28; spacing: 14
        RowLayout {
            Layout.fillWidth: true; spacing: 14
            Rectangle {
                width: 40; height: 40; radius: 12; color: t.accentSoft; border.color: t.accent
                Text { anchors.centerIn: parent; text: "✦"; color: t.accentInk; font.pixelSize: 18 }
            }
            ColumnLayout {
                Layout.fillWidth: true; spacing: 2
                Heading { text: "A/L Results Collector"; font.pixelSize: 21 }
                Hint { text: "Class lookup  ·  doenets.lk" }
            }
            Rectangle {
                implicitWidth: stages.implicitWidth + 8; implicitHeight: 40
                color: t.panel; radius: 20; border.color: t.line
                RowLayout {
                    id: stages; anchors.centerIn: parent; spacing: 4
                    Repeater {
                        model: [{key:"configure", title:"01  Configure"}, {key:"collect", title:"02  Collect"}, {key:"export", title:"03  Export"}]
                        delegate: Rectangle {
                            required property var modelData
                            property bool active: bridge.stage === modelData.key
                            implicitWidth: pillText.implicitWidth + 24; implicitHeight: 30; radius: 15
                            color: active ? t.accentSoft : "transparent"
                            border.width: active ? 1 : 0; border.color: t.accent
                            Text { id: pillText; anchors.centerIn: parent; text: parent.modelData.title; color: parent.active ? t.accentInk : t.muted; font.bold: true; font.pixelSize: 12 }
                        }
                    }
                }
            }
            Rectangle {
                implicitWidth: 162; implicitHeight: 40; radius: 20; color: t.panel; border.color: t.line
                RowLayout {
                    anchors.fill: parent; anchors.margins: 5; spacing: 8
                    Hint { text: "Theme"; Layout.leftMargin: 8 }
                    Selector { theme: t; model: ["System", "Light", "Dark"]; currentIndex: model.indexOf(bridge.theme); onActivated: bridge.theme = currentText; Layout.fillWidth: true }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true; Layout.fillHeight: true
            color: t.shell; border.color: t.line; radius: 22
            RowLayout {
                anchors.fill: parent; anchors.margins: 14; spacing: 16
                ScrollView {
                    id: setupScroll
                    Layout.fillWidth: true; Layout.fillHeight: true; Layout.preferredWidth: 530
                    clip: true; contentWidth: availableWidth
                    ColumnLayout {
                        width: setupScroll.availableWidth; spacing: 12
                        Card {
                            theme: t; Layout.fillWidth: true
                            ColumnLayout {
                                width: parent.width; spacing: 10
                                Caption { text: "01  ·  STUDENT LIST" }
                                Heading { text: "Source workbook" }
                                RowLayout {
                                    Layout.fillWidth: true; spacing: 8
                                    Input { theme: t; Layout.fillWidth: true; text: bridge.filePath; placeholderText: "Choose an Excel file (.xlsx / .xls)"; enabled: !bridge.running; onTextEdited: bridge.filePath = text }
                                    ActionButton { theme: t; text: "Browse"; enabled: !bridge.running; onClicked: bridge.browse() }
                                }
                                Hint { text: "Uses the first worksheet with a column named NIC."; Layout.fillWidth: true }
                            }
                        }
                        Card {
                            theme: t; Layout.fillWidth: true
                            ColumnLayout {
                                width: parent.width; spacing: 10
                                RowLayout {
                                    Layout.fillWidth: true
                                    ColumnLayout {
                                        Layout.fillWidth: true; spacing: 3
                                        Caption { text: "02  ·  SUBJECTS" }
                                        Heading { text: "Filter target subjects" }
                                    }
                                    Rectangle {
                                        implicitWidth: selectedLabel.implicitWidth + 20; implicitHeight: 27; radius: 12
                                        color: t.accentSoft; border.color: t.line
                                        Text { id: selectedLabel; anchors.centerIn: parent; text: bridge.selectedCount + " selected"; color: t.accentInk; font.pixelSize: 11; font.bold: true }
                                    }
                                    ActionButton { theme: t; text: "Clear"; implicitHeight: 30; implicitWidth: 64; enabled: !bridge.running; onClicked: bridge.clearSubjects() }
                                }
                                Hint { text: "Search by subject name or code" }
                                Input { id: searchField; objectName: "subjectSearch"; theme: t; Layout.fillWidth: true; implicitHeight: 36; enabled: !bridge.running; onTextChanged: bridge.search(text) }
                                Rectangle {
                                    Layout.fillWidth: true; implicitHeight: 210; radius: 14; color: t.surface; border.color: t.line
                                    ListView {
                                        id: subjectList; objectName: "subjectList"
                                        anchors.fill: parent; anchors.margins: 10; clip: true
                                        model: bridge.subjects; reuseItems: true; spacing: 4
                                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                                        delegate: SelectionBox {
                                            required property string subjectId
                                            required property string subjectCode
                                            required property string displayName
                                            required property bool subjectSelected
                                            theme: t; width: subjectList.width - 12
                                            text: subjectCode + "  " + displayName
                                            checked: subjectSelected; enabled: !bridge.running
                                            onClicked: bridge.selectSubject(subjectId, checked)
                                        }
                                        Hint { anchors.centerIn: parent; text: "No matching subjects."; visible: subjectList.count === 0 }
                                    }
                                }
                            }
                        }
                        Card {
                            theme: t; Layout.fillWidth: true
                            ColumnLayout {
                                width: parent.width; spacing: 10
                                Caption { text: "03  ·  OPTIONS" }
                                Heading { text: "Extra fields & exam settings" }
                                Rectangle {
                                    Layout.fillWidth: true; implicitHeight: fieldGrid.implicitHeight + 20
                                    color: t.surface; radius: 14; border.color: t.line
                                    GridLayout {
                                        id: fieldGrid; anchors.fill: parent; anchors.margins: 10; columns: 2; columnSpacing: 14; rowSpacing: 4
                                        Repeater { model: bridge.fields; delegate: SelectionBox { required property string modelData; theme: t; text: modelData; Layout.fillWidth: true; enabled: !bridge.running } }
                                    }
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Text { text: "Exam year"; color: t.ink; font.bold: true }
                                    Input { theme: t; text: "2025"; implicitWidth: 100; implicitHeight: 34; enabled: !bridge.running }
                                    Item { Layout.fillWidth: true }
                                    ActionButton { theme: t; text: advanced.visible ? "Advanced settings ▴" : "Advanced settings ▾"; implicitHeight: 32; enabled: !bridge.running; onClicked: advanced.visible = !advanced.visible }
                                }
                                Rectangle {
                                    id: advanced; visible: false; Layout.fillWidth: true; implicitHeight: advancedContent.implicitHeight + 28
                                    color: t.surface; border.color: t.line; radius: 14
                                    ColumnLayout {
                                        id: advancedContent; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 14; spacing: 8
                                        Hint { text: "Output folder (preview only)" }
                                        Input { theme: t; Layout.fillWidth: true; placeholderText: "Same folder as the student list" }
                                        Hint { text: "CAPTCHA timeout (seconds)" }
                                        Input { theme: t; text: "180"; implicitWidth: 100 }
                                    }
                                }
                            }
                        }
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true; Layout.fillHeight: true; Layout.preferredWidth: 410; spacing: 12
                    Card {
                        theme: t; Layout.fillWidth: true
                        ColumnLayout {
                            width: parent.width; spacing: 10
                            RowLayout {
                                Layout.fillWidth: true
                                Caption { text: "LIVE TELEMETRY"; Layout.fillWidth: true }
                                Rectangle {
                                    implicitWidth: 100; implicitHeight: 26; radius: 12; color: t.accentSoft; border.color: t.line
                                    Text { anchors.centerIn: parent; text: bridge.running ? "●  Demo running" : "●  Prototype"; font.pixelSize: 11; color: t.accentInk }
                                }
                            }
                            Heading { text: bridge.processed + " / " + (bridge.processed || bridge.running ? bridge.total : 0) + " students"; font.pixelSize: 28 }
                            Hint { text: bridge.status; Layout.fillWidth: true }
                            RowLayout {
                                Layout.fillWidth: true; spacing: 10
                                ProgressBar {
                                    id: progress; Layout.fillWidth: true; value: bridge.processed / bridge.total
                                    background: Rectangle { implicitHeight: 8; radius: 4; color: t.surface }
                                    contentItem: Item { implicitHeight: 8; Rectangle { width: progress.visualPosition * parent.width; height: parent.height; radius: 4; color: t.accent } }
                                }
                                Text { text: Math.round(bridge.processed / bridge.total * 100) + "%"; color: t.accentInk; font.bold: true }
                            }
                            RowLayout {
                                Layout.fillWidth: true; spacing: 6
                                Repeater {
                                    model: ["Completed", "Skipped", "Errors"]
                                    delegate: Rectangle {
                                        required property string modelData
                                        required property int index
                                        property color tone: index === 0 ? t.success : (index === 1 ? t.warn : t.danger)
                                        property int count: index === 0 ? bridge.completed : (index === 1 ? bridge.skipped : 0)
                                        Layout.fillWidth: true; implicitHeight: 62; radius: 12; color: t.surface; border.color: t.line
                                        Column {
                                            anchors.left: parent.left; anchors.top: parent.top; anchors.margins: 10; spacing: 4
                                            Text { text: "● " + parent.parent.modelData; color: parent.parent.tone; font.pixelSize: 11 }
                                            Text { text: parent.parent.count; color: t.ink; font.pixelSize: 18; font.bold: true }
                                        }
                                    }
                                }
                            }
                            Rectangle {
                                Layout.fillWidth: true; implicitHeight: 34; radius: 12; color: t.surface; border.color: t.line
                                Hint { anchors.fill: parent; anchors.margins: 10; text: bridge.running ? "Synthetic student " + bridge.processed : "No student in progress" }
                            }
                            Hint { text: "UI demo only. Real CAPTCHA and scraping remain in the original app."; color: t.dim; Layout.fillWidth: true; font.pixelSize: 11 }
                        }
                    }
                    Card {
                        theme: t; Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 130; implicitHeight: 200
                        ColumnLayout {
                            anchors.fill: parent; spacing: 10
                            RowLayout {
                                Layout.fillWidth: true
                                Heading { text: "Activity feed"; font.pixelSize: 14; Layout.fillWidth: true }
                                Hint { text: "SESSION LOG"; font.pixelSize: 10; color: t.dim }
                            }
                            Rectangle {
                                Layout.fillWidth: true; Layout.fillHeight: true; radius: 12; color: t.surface; border.color: t.line; clip: true
                                ScrollView {
                                    anchors.fill: parent; anchors.margins: 10; contentWidth: availableWidth
                                    TextArea { text: bridge.logText; readOnly: true; wrapMode: TextEdit.WordWrap; color: t.ink; font.pixelSize: 12; background: null }
                                }
                            }
                        }
                    }
                    Card {
                        theme: t; padding: 16; Layout.fillWidth: true
                        ColumnLayout {
                            width: parent.width; spacing: 8
                            ActionButton { objectName: "startDemo"; theme: t; text: "Start demo collection"; primary: true; implicitHeight: 42; Layout.fillWidth: true; enabled: !bridge.running; onClicked: bridge.startDemo() }
                            RowLayout {
                                Layout.fillWidth: true; spacing: 8
                                ActionButton { theme: t; text: "Stop & save"; Layout.fillWidth: true; enabled: bridge.running; onClicked: bridge.stopDemo() }
                                ActionButton { theme: t; text: "Skip current"; Layout.fillWidth: true; enabled: bridge.running; onClicked: bridge.skipDemo() }
                            }
                            RowLayout {
                                Layout.fillWidth: true; spacing: 8
                                ActionButton { theme: t; text: "Export to Excel"; Layout.fillWidth: true; enabled: bridge.processed > 0 && !bridge.running; onClicked: bridge.exportDemo() }
                                ActionButton { theme: t; text: "Open folder"; Layout.fillWidth: true; enabled: false }
                            }
                        }
                    }
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Rectangle {
                implicitWidth: footerLabel.implicitWidth + 24; implicitHeight: 28; radius: 14; color: t.panel; border.color: t.line
                Hint { id: footerLabel; anchors.centerIn: parent; text: "●  UI prototype · no student lookups or result files"; font.pixelSize: 11 }
            }
            Item { Layout.fillWidth: true }
            Hint { text: "PySide6 + Qt Quick · performance comparison"; color: t.dim; font.pixelSize: 11 }
        }
    }
}
