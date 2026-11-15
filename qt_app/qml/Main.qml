import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: win
    objectName: "collectorWindow"
    width: 1180; height: 880; minimumWidth: 1020; minimumHeight: 750
    readonly property bool compactLayout: height < 820
    visible: true
    title: bridge.mockMode ? "A/L Results Collector — MOCK TEST" : (bridge.prototypeMode ? "A/L Results Collector — NONECAP PROTOTYPE" : "A/L Results Collector")
    onClosing: function(close) { close.accepted = bridge.requestClose() }
    Connections { target: bridge; function onReadyToClose() { win.close() } }
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
            Image {
                objectName: "appLogo"
                Layout.preferredWidth: 40; Layout.preferredHeight: 40
                source: Qt.resolvedUrl("../../packaging/app.ico")
                sourceSize.width: 40; sourceSize.height: 40
                fillMode: Image.PreserveAspectFit
            }
            ColumnLayout {
                Layout.fillWidth: true; spacing: 2
                Heading { text: "A/L Results Collector"; font.pixelSize: 21 }
                Hint { text: bridge.mockMode ? "Offline test · fictional students" : (bridge.prototypeMode ? "NONECAP PROTOTYPE · separate saved progress" : "Class lookup · manual or NoneCAP verification"); color: bridge.mockMode || bridge.prototypeMode ? t.warn : t.muted }
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
                                    Input { objectName: "workbookInput"; theme: t; Layout.fillWidth: true; text: bridge.filePath; placeholderText: "Choose an Excel file (.xlsx / .xls)"; enabled: !bridge.running && !bridge.mockMode; onTextEdited: bridge.filePath = text }
                                    ActionButton { theme: t; text: "Browse"; enabled: !bridge.running && !bridge.mockMode; onClicked: bridge.browse() }
                                }
                                Hint { text: "Uses the first worksheet with a column named NIC."; Layout.fillWidth: true }
                            }
                        }
                        Card {
                            id: captchaSettings
                            visible: !bridge.mockMode
                            property bool accountExpanded: true
                            property bool helpExpanded: false
                            theme: t; Layout.fillWidth: true
                            ColumnLayout {
                                width: parent.width; spacing: 10
                                RowLayout {
                                    Layout.fillWidth: true
                                    Heading { text: "CAPTCHA"; Layout.fillWidth: true }
                                    Selector {
                                        objectName: "captchaMode"; theme: t; model: ["Manual", "Automatic"]
                                        currentIndex: model.indexOf(bridge.captchaMode); enabled: !bridge.running
                                        onActivated: bridge.captchaMode = currentText
                                        Layout.preferredWidth: 145
                                    }
                                }
                                Hint { text: bridge.captchaMode === "Manual" ? "Complete CAPTCHA in Chrome for each student." : "NoneCAP handles verification. Leave CAPTCHA untouched while collecting."; Layout.fillWidth: true }
                                ColumnLayout {
                                    visible: bridge.captchaMode === "Automatic"; Layout.fillWidth: true; spacing: 8
                                    RowLayout {
                                        Layout.fillWidth: true
                                        Text { text: "Parallel browsers"; color: t.ink; Layout.fillWidth: true }
                                        Selector { objectName: "workerCount"; theme: t; model: bridge.workerOptions; currentIndex: model.indexOf(bridge.workerCount); enabled: !bridge.running; onActivated: bridge.workerCount = currentText; Layout.preferredWidth: 95 }
                                    }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        Text { text: "Account"; color: t.ink; font.bold: true; Layout.fillWidth: true }
                                        ActionButton { objectName: "accountToggle"; theme: t; text: captchaSettings.accountExpanded ? "Hide key & balance ▴" : "API key & balance ▾"; implicitHeight: 30; onClicked: captchaSettings.accountExpanded = !captchaSettings.accountExpanded }
                                    }
                                    ColumnLayout {
                                        objectName: "accountDetails"; visible: captchaSettings.accountExpanded; Layout.fillWidth: true; spacing: 6
                                        RowLayout {
                                            Layout.fillWidth: true; spacing: 8
                                            Input { objectName: "apiKeyInput"; theme: t; Layout.fillWidth: true; text: bridge.apiKey; placeholderText: "NoneCAP API key"; echoMode: TextInput.Password; enabled: !bridge.running; selectByMouse: true; onTextEdited: bridge.apiKey = text }
                                            ActionButton { theme: t; text: "Clear"; implicitWidth: 58; enabled: !bridge.running && bridge.apiKey.length > 0; onClicked: bridge.apiKey = "" }
                                        }
                                        RowLayout {
                                            Layout.fillWidth: true; spacing: 10
                                            ActionButton { objectName: "checkBalance"; theme: t; tone: "info"; text: "Check balance"; implicitHeight: 32; enabled: !bridge.running && bridge.apiKey.length > 0; onClicked: bridge.checkBalance() }
                                            Hint { text: bridge.balanceText; Layout.fillWidth: true }
                                        }
                                        Hint { text: "Your key stays in this window and is never saved."; Layout.fillWidth: true; font.pixelSize: 11 }
                                    }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        Text { text: "Session limits"; color: t.ink; font.bold: true; Layout.fillWidth: true }
                                        ActionButton { objectName: "limitsHelpToggle"; theme: t; text: captchaSettings.helpExpanded ? "Less ▴" : "How limits work ▾"; implicitHeight: 30; onClicked: captchaSettings.helpExpanded = !captchaSettings.helpExpanded }
                                    }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            Hint { text: "Solve attempts" }
                                            Input { objectName: "maxAttemptsInput"; theme: t; text: bridge.maxAttempts; onTextEdited: bridge.maxAttempts = text; enabled: !bridge.running; Layout.fillWidth: true; validator: IntValidator { bottom: 1; top: 1000 } }
                                        }
                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            Hint { text: "Pause at (credits)" }
                                            Input { objectName: "creditLimitInput"; theme: t; text: bridge.creditLimit; onTextEdited: bridge.creditLimit = text; enabled: !bridge.running; Layout.fillWidth: true; validator: IntValidator { bottom: 1; top: 100000 } }
                                        }
                                    }
                                    Hint { objectName: "sessionUsage"; text: bridge.usageText; color: t.accentInk; Layout.fillWidth: true }
                                    Hint { text: "Shared across all browsers and jobs in this window."; Layout.fillWidth: true; font.pixelSize: 11 }
                                    Hint { text: "At the credit amount, new solves pause. Active solves may finish above it."; color: t.warn; Layout.fillWidth: true }
                                    Hint { objectName: "limitsHelp"; visible: captchaSettings.helpExpanded; text: "One solve attempt is one request to NoneCAP, including free or failed attempts. It is not a CAPTCHA round. Stop, Resume and a new workbook keep the usage above. A provider-side key cap offers stronger spending control. An unconfirmed charge blocks automatic collection for this window."; Layout.fillWidth: true }
                                }
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
                                        Repeater { model: bridge.fields; delegate: SelectionBox { required property string modelData; objectName: "field-" + modelData; theme: t; text: modelData; checked: bridge.selectedFields.indexOf(modelData) >= 0; onClicked: bridge.selectField(modelData, checked); Layout.fillWidth: true; enabled: !bridge.running } }
                                    }
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Text { text: "Exam year"; color: t.ink; font.bold: true }
                                    Input { objectName: "examYearInput"; theme: t; text: bridge.examYear; onTextEdited: bridge.examYear = text; implicitWidth: 100; implicitHeight: 34; enabled: !bridge.running }
                                    Item { Layout.fillWidth: true }
                                    ActionButton { theme: t; text: advanced.visible ? "Advanced settings ▴" : "Advanced settings ▾"; implicitHeight: 32; enabled: !bridge.running; onClicked: advanced.visible = !advanced.visible }
                                }
                                Rectangle {
                                    id: advanced; visible: false; Layout.fillWidth: true; implicitHeight: advancedContent.implicitHeight + 28
                                    color: t.surface; border.color: t.line; radius: 14
                                    ColumnLayout {
                                        id: advancedContent; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 14; spacing: 8
                                        Hint { text: "Output folder" }
                                        RowLayout {
                                            Layout.fillWidth: true
                                            Input { theme: t; Layout.fillWidth: true; text: bridge.outputFolder; enabled: !bridge.running; onTextEdited: bridge.outputFolder = text; placeholderText: "Same folder as the student list" }
                                            ActionButton { theme: t; text: "Browse"; enabled: !bridge.running; onClicked: bridge.browseFolder() }
                                        }
                                        Hint { text: "CAPTCHA timeout (seconds)" }
                                        Input { theme: t; text: bridge.captchaTimeout; enabled: !bridge.running; onTextEdited: bridge.captchaTimeout = text; implicitWidth: 100 }
                                    }
                                }
                            }
                        }
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true; Layout.fillHeight: true; Layout.preferredWidth: 410; spacing: 12
                    Card {
                        theme: t; padding: win.compactLayout ? 14 : 18; Layout.fillWidth: true
                        ColumnLayout {
                            width: parent.width; spacing: win.compactLayout ? 7 : 10
                            RowLayout {
                                Layout.fillWidth: true
                                Caption { text: "LIVE TELEMETRY"; Layout.fillWidth: true }
                                Rectangle {
                                    implicitWidth: 100; implicitHeight: 26; radius: 12; color: t.accentSoft; border.color: t.line
                                    Text { anchors.centerIn: parent; text: bridge.mockMode ? "●  MOCK TEST" : (bridge.running ? "●  Working" : "●  Ready"); font.pixelSize: 11; color: bridge.mockMode ? t.warn : t.accentInk }
                                }
                            }
                            Heading { text: bridge.processed + " / " + bridge.total + " students"; font.pixelSize: win.compactLayout ? 24 : 28 }
                            Hint { text: bridge.status; Layout.fillWidth: true; maximumLineCount: win.compactLayout ? 3 : 5; elide: Text.ElideRight }
                            Hint { objectName: "performanceSummary"; text: bridge.performanceText; visible: bridge.processed > 0; Layout.fillWidth: true; color: t.accentInk; wrapMode: Text.NoWrap; elide: Text.ElideRight; font.pixelSize: 11 }
                            RowLayout {
                                Layout.fillWidth: true; spacing: 10
                                ProgressBar {
                                    id: progress; Layout.fillWidth: true; value: bridge.total ? bridge.processed / bridge.total : 0
                                    background: Rectangle { implicitHeight: 8; radius: 4; color: t.surface }
                                    contentItem: Item { implicitHeight: 8; Rectangle { width: progress.visualPosition * parent.width; height: parent.height; radius: 4; color: t.accent } }
                                }
                                Text { text: (bridge.total ? Math.round(bridge.processed / bridge.total * 100) : 0) + "%"; color: t.accentInk; font.bold: true }
                            }
                            RowLayout {
                                Layout.fillWidth: true; spacing: 6
                                Repeater {
                                    model: ["Completed", "Skipped", "Errors"]
                                    delegate: Rectangle {
                                        required property string modelData
                                        required property int index
                                        property color tone: index === 0 ? t.success : (index === 1 ? t.warn : t.danger)
                                        property int count: index === 0 ? bridge.completed : (index === 1 ? bridge.skipped : bridge.failed)
                                        Layout.fillWidth: true; implicitHeight: win.compactLayout ? 50 : 62; radius: 12; color: t.surface; border.color: t.line
                                        Column {
                                            anchors.left: parent.left; anchors.top: parent.top; anchors.margins: win.compactLayout ? 8 : 10; spacing: 4
                                            Text { text: "● " + parent.parent.modelData; color: parent.parent.tone; font.pixelSize: 11 }
                                            Text { text: parent.parent.count; color: t.ink; font.pixelSize: 18; font.bold: true }
                                        }
                                    }
                                }
                            }
                            Rectangle {
                                Layout.fillWidth: true; implicitHeight: 34; radius: 12; color: t.surface; border.color: t.line
                                Hint { anchors.fill: parent; anchors.margins: 10; text: bridge.currentStudent; elide: Text.ElideRight; wrapMode: Text.NoWrap }
                            }
                        }
                    }
                    Card {
                        theme: t; Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: win.compactLayout ? 90 : 130; implicitHeight: 200
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
                                    id: activityScroll; objectName: "activityScroll"
                                    anchors.fill: parent; anchors.margins: 10; contentWidth: availableWidth
                                    TextArea {
                                        text: bridge.logText; readOnly: true; wrapMode: TextEdit.WordWrap
                                        color: t.ink; font.pixelSize: 12; background: null
                                        onTextChanged: Qt.callLater(function() {
                                            activityScroll.contentItem.contentY = Math.max(0, activityScroll.contentHeight - activityScroll.availableHeight)
                                        })
                                    }
                                }
                            }
                        }
                    }
                    Card {
                        theme: t; padding: 16; Layout.fillWidth: true
                        ColumnLayout {
                            width: parent.width; spacing: 8
                            ActionButton { objectName: "startCollection"; theme: t; text: bridge.mockMode ? "Start mock collection" : (bridge.captchaMode === "Automatic" ? "Start collection · uses credits" : "Start collection · manual"); primary: true; implicitHeight: 42; Layout.fillWidth: true; enabled: !bridge.running; onClicked: bridge.startCollection() }
                            RowLayout {
                                Layout.fillWidth: true; spacing: 8
                                ActionButton { objectName: "stopCollection"; theme: t; tone: "stop"; text: "Stop & save"; Layout.fillWidth: true; enabled: bridge.collecting; onClicked: bridge.stopCollection() }
                                ActionButton { objectName: "skipCurrent"; theme: t; tone: "warning"; text: bridge.captchaMode === "Automatic" && Number(bridge.workerCount) > 1 ? "Skip worker " + bridge.skipWorker : "Skip current"; Layout.fillWidth: true; enabled: bridge.collecting; onClicked: bridge.skipCurrent() }
                                Selector { objectName: "skipWorker"; theme: t; model: bridge.skipOptions; currentIndex: model.indexOf(bridge.skipWorker); onActivated: bridge.skipWorker = currentText; visible: bridge.captchaMode === "Automatic" && Number(bridge.workerCount) > 1; Layout.preferredWidth: 55; enabled: bridge.collecting }
                            }
                            RowLayout {
                                Layout.fillWidth: true; spacing: 8
                                ActionButton { objectName: "exportResults"; theme: t; tone: "success"; text: "Export to Excel"; Layout.fillWidth: true; enabled: bridge.canExport; onClicked: bridge.exportResults() }
                                ActionButton { objectName: "openOutputFolder"; theme: t; tone: "info"; text: "Open folder"; Layout.fillWidth: true; enabled: bridge.lastOutput.length > 0; onClicked: bridge.openFolder() }
                            }
                            Hint { text: "Stop saves progress here. Export creates your Excel file."; Layout.fillWidth: true; font.pixelSize: 11 }
                        }
                    }
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Rectangle {
                implicitWidth: footerLabel.implicitWidth + 24; implicitHeight: 28; radius: 14; color: t.panel; border.color: t.line
                Hint { id: footerLabel; anchors.centerIn: parent; text: bridge.mockMode ? "●  MOCK TEST · fictional data only" : (bridge.prototypeMode ? "●  NONECAP PROTOTYPE · isolated storage" : "●  Progress saved locally"); color: bridge.mockMode || bridge.prototypeMode ? t.warn : t.muted; font.pixelSize: 11 }
            }
            Item { Layout.fillWidth: true }
            Hint { text: bridge.diagnostics || ("v" + Qt.application.version + " · doenets.lk"); Layout.fillWidth: true; horizontalAlignment: Text.AlignRight; elide: Text.ElideRight; wrapMode: Text.NoWrap; color: t.dim; font.pixelSize: 11 }
        }
    }
    Dialog {
        anchors.centerIn: parent
        width: Math.min(520, win.width - 80)
        visible: bridge.needsDecision
        modal: true
        closePolicy: Popup.NoAutoClose
        padding: 22
        background: Rectangle { color: t.panel; radius: 16; border.color: t.lineBright }
        contentItem: ColumnLayout {
            spacing: 16
            Heading { text: bridge.decisionMismatch ? "Different saved collection" : "Resume collection" }
            Hint { text: bridge.decisionText; Layout.fillWidth: true }
            RowLayout {
                Layout.fillWidth: true
                ActionButton { theme: t; text: "Resume"; primary: true; visible: !bridge.decisionMismatch; onClicked: bridge.decide("resume") }
                ActionButton { theme: t; text: "Start fresh"; onClicked: bridge.decide("restart") }
                Item { Layout.fillWidth: true }
                ActionButton { theme: t; text: "Cancel"; onClicked: bridge.decide("cancel") }
            }
        }
    }
}
