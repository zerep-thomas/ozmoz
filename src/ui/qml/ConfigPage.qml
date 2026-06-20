import QtQuick
import QtQuick.Layouts
import QtQuick.Controls.Basic
import Qt5Compat.GraphicalEffects

Item {
    id: configRoot
    focus: true 

    TapHandler {
        onTapped: configRoot.forceActiveFocus()
    }

    property string updateStatus: "idle"
    property string updateMessage: "Check Now"
    property bool showClearHistoryModal: false
    property bool showModelsDropdown: false
    
    property string activeTooltip: ""
    property point tooltipAnchor: Qt.point(0, 0)

    Connections {
        target: uiBridge
        function onUpdateStatusChanged(status, message) {
            configRoot.updateStatus = status
            configRoot.updateMessage = message
        }
    }

    component InfoIcon: Item {
        id: self
        property string tip: ""
        width: 14; height: 14
        
        Image { 
            id: img; anchors.fill: parent; source: "icons/info.svg"
            fillMode: Image.PreserveAspectFit; smooth: true; layer.enabled: true 
        }
        ColorOverlay { anchors.fill: img; source: img; color: "white" }
        
        MouseArea {
            anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
            onEntered: { 
                if (self.tip !== "") { 
                    var pt = self.mapToItem(configRoot, self.width, self.height / 2)
                    configRoot.tooltipAnchor = Qt.point(pt.x, pt.y)
                    configRoot.activeTooltip = self.tip 
                } 
            }
            onExited: { configRoot.activeTooltip = "" }
        }
    }

    component ToggleSwitch: Rectangle {
        id: toggleRoot
        property bool checked: false
        signal toggled(bool checked)

        width: 44
        height: 24
        radius: height / 2
        color: checked ? "#34c759" : "#8e8e93"

        Behavior on color { ColorAnimation { duration: 150 } }

        Rectangle {
            width: 20
            height: 20
            radius: 10
            color: "white"
            anchors.verticalCenter: parent.verticalCenter
            x: checked ? parent.width - width - 2 : 2

            Behavior on x {
                NumberAnimation { duration: 150; easing.type: Easing.OutQuad }
            }
        }

        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: {
                toggleRoot.checked = !toggleRoot.checked
                toggleRoot.toggled(toggleRoot.checked)
            }
        }
    }

    component SettingRow: Item {
        id: rowRoot
        property alias text: label.text
        property alias control: controlSlot.sourceComponent
        property bool showSeparator: true

        height: 48
        Layout.fillWidth: true

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 16
            anchors.rightMargin: 16
            spacing: 6

            Text {
                id: label
                color: "white"
                font.pixelSize: 14
                font.weight: Font.Bold
                Layout.fillWidth: true
                verticalAlignment: Text.AlignVCenter
            }

            Loader {
                id: controlSlot
                Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
            }
        }

        Rectangle {
            visible: rowRoot.showSeparator
            anchors.bottom: parent.bottom
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.leftMargin: 16
            anchors.rightMargin: 16
            height: 1
            color: "#66696a"
        }
    }

    Rectangle { 
        id: backgroundCapture
        anchors.fill: parent
        color: "#494c4d"

        ScrollView {
            id: root
            anchors.fill: parent
            clip: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            ScrollBar.vertical.policy: ScrollBar.AsNeeded
            contentWidth: availableWidth
            
            Component.onCompleted: contentItem.boundsBehavior = Flickable.StopAtBounds

            Item {
                width: parent.width
                implicitHeight: mainColumn.implicitHeight + 40

                ColumnLayout {
                    id: mainColumn
                    width: Math.min(560, parent.width - 60)
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.top: parent.top
                    anchors.topMargin: 20
                    spacing: 24

                    // SECTION: API KEYS
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 10

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 6
                            Text { text: "API Keys"; color: "white"; font.pixelSize: 13; font.bold: true; Layout.leftMargin: 4 }
                            InfoIcon { tip: "Required for Cloud models (like Whisper V3 Turbo). Your key is encrypted securely with Windows and never stored in plain text." }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            color: "#55585a"
                            radius: 12
                            border.color: "#66696a"
                            border.width: 1
                            implicitHeight: apiColumn.implicitHeight + 2

                            ColumnLayout {
                                id: apiColumn
                                anchors.fill: parent
                                anchors.margins: 1
                                spacing: 0

                                SettingRow {
                                    text: "Groq API Key"
                                    showSeparator: false
                                    control: Rectangle {
                                        width: 350 
                                        height: 32
                                        radius: 8
                                        color: "#3e4243"
                                        border.color: groqKeyInput.activeFocus ? "#5a9ef8" : "#6e7273"
                                        border.width: 1

                                        property bool isSaved: true

                                        TextInput {
                                            id: groqKeyInput
                                            anchors.left: parent.left
                                            anchors.right: innerSaveBtn.left
                                            anchors.verticalCenter: parent.verticalCenter
                                            anchors.margins: 10
                                            color: "white"
                                            font.pixelSize: 13
                                            echoMode: TextInput.Password
                                            verticalAlignment: TextInput.AlignVCenter
                                            selectionColor: "#4a90d9"
                                            text: uiBridge.groqKey
                                            clip: true
                                            onTextEdited: parent.isSaved = false
                                        }

                                        Rectangle {
                                            id: innerSaveBtn
                                            width: 24
                                            height: 24
                                            radius: 6
                                            anchors.right: parent.right
                                            anchors.rightMargin: 4
                                            anchors.verticalCenter: parent.verticalCenter
                                            color: innerSaveBtnArea.containsMouse ? "#2c5fc4" : "#2452a3"
                                            
                                            opacity: !parent.isSaved ? 1.0 : 0.0
                                            visible: opacity > 0.0
                                            Behavior on opacity { NumberAnimation { duration: 250 } }

                                            Text {
                                                anchors.centerIn: parent
                                                text: "+"
                                                color: "white"
                                                font.pixelSize: 16
                                                font.bold: true
                                                anchors.verticalCenterOffset: -2
                                            }

                                            MouseArea {
                                                id: innerSaveBtnArea
                                                anchors.fill: parent
                                                hoverEnabled: true
                                                cursorShape: Qt.PointingHandCursor
                                                onClicked: {
                                                    uiBridge.saveGroqKey(groqKeyInput.text)
                                                    innerSaveBtn.parent.isSaved = true
                                                    groqKeyInput.focus = false
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }

                    // SECTION: SOUND
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 10

                        Text { text: "Sound"; color: "white"; font.pixelSize: 13; font.bold: true; Layout.leftMargin: 4 }

                        Rectangle {
                            Layout.fillWidth: true
                            color: "#55585a"
                            radius: 12
                            border.color: "#66696a"
                            border.width: 1
                            implicitHeight: soundColumn.implicitHeight + 2

                            ColumnLayout {
                                id: soundColumn
                                anchors.fill: parent
                                anchors.margins: 1
                                spacing: 0

                                SettingRow {
                                    text: "Play usage sounds"
                                    showSeparator: false
                                    control: ToggleSwitch {
                                        checked: uiBridge.playSounds
                                        onToggled: function(checked) { uiBridge.setPlaySounds(checked) }
                                    }
                                }
                            }
                        }
                    }

                    // SECTION: UPDATES
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 10

                        Text { text: "Updates"; color: "white"; font.pixelSize: 13; font.bold: true; Layout.leftMargin: 4 }

                        Rectangle {
                            Layout.fillWidth: true
                            color: "#55585a"
                            radius: 12
                            border.color: "#66696a"
                            border.width: 1
                            implicitHeight: updatesColumn.implicitHeight + 2

                            ColumnLayout {
                                id: updatesColumn
                                anchors.fill: parent
                                anchors.margins: 1
                                spacing: 0

                                SettingRow {
                                    text: "Check for updates"
                                    showSeparator: true
                                    control: Rectangle {
                                        height: 28
                                        implicitWidth: updateText.implicitWidth + 20
                                        radius: 6
                                        color: updateArea.containsMouse ? "#6a6e70" : "#64686a"
                                        border.color: "#7e8385"
                                        border.width: 1
                                        Behavior on color { ColorAnimation { duration: 120 } }

                                        Text {
                                            id: updateText
                                            anchors.centerIn: parent
                                            text: configRoot.updateMessage || ""
                                            color: configRoot.updateStatus === "available" ? "#b0b0b0" : "white"
                                            font.pixelSize: 12
                                            font.underline: configRoot.updateStatus === "available"
                                        }

                                        MouseArea {
                                            id: updateArea
                                            anchors.fill: parent
                                            hoverEnabled: true
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: {
                                                if (configRoot.updateStatus === "available") uiBridge.openUpdateUrl()
                                                else if (configRoot.updateStatus !== "checking") uiBridge.checkUpdatesNow()
                                            }
                                        }
                                    }
                                }

                                SettingRow {
                                    text: "Automatically check for updates"
                                    showSeparator: false
                                    control: ToggleSwitch {
                                        checked: uiBridge.autoCheckUpdates
                                        onToggled: function(checked) { uiBridge.setAutoCheckUpdates(checked) }
                                    }
                                }
                            }
                        }
                    }

                    // SECTION: HISTORY
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 10

                        Text { text: "History"; color: "white"; font.pixelSize: 13; font.bold: true; Layout.leftMargin: 4 }

                        Rectangle {
                            Layout.fillWidth: true
                            color: "#55585a"
                            radius: 12
                            border.color: "#66696a"
                            border.width: 1
                            implicitHeight: historyColumn.implicitHeight + 2

                            ColumnLayout {
                                id: historyColumn
                                anchors.fill: parent
                                anchors.margins: 1
                                spacing: 0

                                SettingRow {
                                    text: "Clear all history"
                                    showSeparator: false
                                    control: Rectangle {
                                        height: 28
                                        implicitWidth: clearBtnText.implicitWidth + 20
                                        radius: 6
                                        color: clearArea.containsMouse ? "#6a6e70" : "#64686a"
                                        border.color: "#7e8385"
                                        border.width: 1
                                        Behavior on color { ColorAnimation { duration: 120 } }

                                        Text {
                                            id: clearBtnText
                                            anchors.centerIn: parent
                                            text: "Clear" 
                                            color: "white"
                                            font.pixelSize: 12
                                        }

                                        MouseArea {
                                            id: clearArea
                                            anchors.fill: parent
                                            hoverEnabled: true
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: configRoot.showClearHistoryModal = true
                                        }
                                    }
                                }
                            }
                        }
                    }

                    // SECTION : Local models 
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 10

                        Text { text: "Local Models"; color: "white"; font.pixelSize: 13; font.bold: true; Layout.leftMargin: 4 }

                        Rectangle {
                            Layout.fillWidth: true
                            color: "#55585a"
                            radius: 12
                            border.color: "#66696a"
                            border.width: 1
                            implicitHeight: modelsColumn.implicitHeight + 2

                            ColumnLayout {
                                id: modelsColumn
                                anchors.fill: parent
                                anchors.margins: 1
                                spacing: 0

                                Rectangle {
                                    Layout.fillWidth: true
                                    height: 48
                                    color: "transparent"
                                    
                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.leftMargin: 16
                                        anchors.rightMargin: 16
                                        spacing: 6

                                        Text {
                                            text: "Manage Downloaded Models"
                                            color: "white"
                                            font.pixelSize: 14
                                            font.weight: Font.Bold
                                            Layout.fillWidth: true
                                            verticalAlignment: Text.AlignVCenter
                                        }

                                        Text {
                                            text: "‹"
                                            color: "#909090"
                                            font.pixelSize: 20
                                            font.weight: Font.Light
                                            rotation: configRoot.showModelsDropdown ? 90 : -90
                                            Behavior on rotation { NumberAnimation { duration: 200 } }
                                        }
                                    }

                                    MouseArea {
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: configRoot.showModelsDropdown = !configRoot.showModelsDropdown
                                    }
                                }

                                Rectangle {
                                    id: expandedContainer
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: height 
                                    color: "transparent"
                                    clip: true
                                    
                                    height: configRoot.showModelsDropdown ? expandedList.implicitHeight + 12 : 0
                                    opacity: configRoot.showModelsDropdown ? 1.0 : 0.0

                                    Behavior on height { NumberAnimation { duration: 250; easing.type: Easing.InOutQuad } }
                                    Behavior on opacity { NumberAnimation { duration: 180; easing.type: Easing.InOutQuad } }

                                    ColumnLayout {
                                        id: expandedList
                                        anchors.left: parent.left
                                        anchors.right: parent.right
                                        anchors.top: parent.top
                                        anchors.leftMargin: 16
                                        anchors.rightMargin: 16
                                        spacing: 8

                                        Repeater {
                                            model: JSON.parse(uiBridge.installedLocalModelsJson)
                                            delegate: Rectangle {
                                                Layout.fillWidth: true
                                                height: 36
                                                color: "#64686a"
                                                radius: 8
                                                border.color: "#7e8385"
                                                border.width: 1

                                                RowLayout {
                                                    anchors.fill: parent
                                                    anchors.leftMargin: 12
                                                    anchors.rightMargin: 8

                                                    Text {
                                                        text: modelData
                                                        color: "white"
                                                        font.pixelSize: 13
                                                        font.bold: true
                                                        Layout.fillWidth: true
                                                    }

                                                    Rectangle {
                                                        width: 28
                                                        height: 28
                                                        radius: 6
                                                        color: "transparent"
                                                        Image {
                                                            id: delIcon
                                                            source: "icons/delete.svg"
                                                            anchors.centerIn: parent
                                                            width: 16
                                                            height: 16
                                                            fillMode: Image.PreserveAspectFit
                                                            visible: false
                                                        }
                                                        ColorOverlay {
                                                            anchors.fill: delIcon
                                                            source: delIcon
                                                            color: delArea.containsMouse ? "#e05555" : "#909597"
                                                            Behavior on color { ColorAnimation { duration: 120 } }
                                                        }
                                                        MouseArea {
                                                            id: delArea
                                                            anchors.fill: parent
                                                            hoverEnabled: true
                                                            cursorShape: Qt.PointingHandCursor
                                                            onClicked: {
                                                                uiBridge.deleteLocalModel(modelData)
                                                            }
                                                        }
                                                    }
                                                }
                                            }
                                        }

                                        Text {
                                            visible: JSON.parse(uiBridge.installedLocalModelsJson).length === 0
                                            text: "No offline models downloaded yet."
                                            color: "#909090"
                                            font.pixelSize: 13
                                            Layout.alignment: Qt.AlignHCenter
                                            Layout.topMargin: 4
                                            Layout.bottomMargin: 4
                                        }
                                    }
                                }
                            }
                        }
                    }

                    Item { height: 10; Layout.fillWidth: true }
                }
            }
        }
    }

    // ── TOOLTIP OVERLAY  ──
    Item {
        anchors.fill: parent
        z: 250; enabled: false; visible: configRoot.activeTooltip !== ""

        Rectangle {
            transformOrigin: Item.TopLeft
            x: Math.max(6, Math.min(configRoot.tooltipAnchor.x + 10, configRoot.width - width - 6))
            y: Math.max(6, configRoot.tooltipAnchor.y - height / 2)
            width: Math.min(tipLabel.implicitWidth + 24, 260); height: tipLabel.implicitHeight + 14
            radius: 8; color: "#000000"

            scale: configRoot.activeTooltip !== "" ? 1.0 : 0.75
            Behavior on scale { NumberAnimation { duration: 160; easing.type: Easing.OutBack; easing.overshoot: 1.4 } }
            opacity: configRoot.activeTooltip !== "" ? 1.0 : 0.0
            Behavior on opacity { NumberAnimation { duration: 120 } }

            Text {
                id: tipLabel; anchors.centerIn: parent; width: parent.width - 24
                text: configRoot.activeTooltip; color: "#d4d6d8"; font.pixelSize: 12; wrapMode: Text.WordWrap
            }
        }
    }

// ─── MODAL CONFIRMATION CLEAR HISTORY ───
    Item {
        id: clearModalOverlay
        anchors.fill: parent
        z: 100
        visible: opacity > 0
        opacity: configRoot.showClearHistoryModal ? 1.0 : 0.0

        Behavior on opacity { NumberAnimation { duration: 250; easing.type: Easing.OutCubic } }

        MouseArea {
            anchors.fill: parent
            onClicked: configRoot.showClearHistoryModal = false
        }

        ShaderEffectSource {
            id: blurSrc
            anchors.fill: parent
            sourceItem: backgroundCapture
            visible: false
        }
        
        FastBlur {
            id: firstBlurPass
            anchors.fill: parent
            source: blurSrc
            radius: 5
        }

        ShaderEffectSource {
            id: intermediateCapture
            sourceItem: firstBlurPass
            hideSource: true 
            visible: false
        }

        FastBlur {
            id: secondBlurPass
            anchors.fill: parent
            source: intermediateCapture
            radius: 64
            transparentBorder: false
        }
        
        Rectangle {
            anchors.fill: parent
            color: Qt.rgba(0.12, 0.13, 0.14, 0.65)
        }

        Rectangle {
            anchors.centerIn: parent
            width: 380
            height: 180
            radius: 12
            color: "#494c4d"
            border.color: "#66696a"
            border.width: 1

            scale: configRoot.showClearHistoryModal ? 1.0 : 0.8
            Behavior on scale { NumberAnimation { duration: 250; easing.type: Easing.OutBack; easing.overshoot: 1.2 } }

            MouseArea { anchors.fill: parent } 

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 20
                spacing: 10

                Text {
                    text: "Clear History"
                    color: "white"
                    font.pixelSize: 16
                    font.bold: true
                    Layout.alignment: Qt.AlignHCenter
                }

                Text {
                    text: "Are you sure you want to delete all history? This action cannot be undone."
                    color: "#b0b0b0"
                    font.pixelSize: 13
                    wrapMode: Text.WordWrap
                    horizontalAlignment: Text.AlignHCenter
                    Layout.fillWidth: true
                    Layout.topMargin: 10
                }

                Item { Layout.fillHeight: true }

                RowLayout {
                    Layout.fillWidth: true; Layout.alignment: Qt.AlignHCenter; spacing: 12

                    Rectangle {
                        implicitWidth: 100
                        height: 32
                        radius: 8
                        color: cancelHover.containsMouse ? "#6a6e70" : "#55585a"
                        border.color: "#7e8385"
                        border.width: 1
                        Behavior on color { ColorAnimation { duration: 120 } }

                        Text { anchors.centerIn: parent; text: "Cancel"; color: "white"; font.pixelSize: 13; font.bold: true }
                        MouseArea {
                            id: cancelHover
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: configRoot.showClearHistoryModal = false
                        }
                    }

                    Rectangle {
                        implicitWidth: 100
                        height: 32; radius: 8
                        color: confirmHover.containsMouse ? "#c93c3c" : "#a83232"
                        border.color: "#d64545"
                        border.width: 1
                        Behavior on color { ColorAnimation { duration: 120 } }

                        Text { anchors.centerIn: parent; text: "Delete"; color: "white"; font.pixelSize: 13; font.bold: true }
                        MouseArea {
                            id: confirmHover
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                uiBridge.clearAllHistory()
                                configRoot.showClearHistoryModal = false
                            }
                        }
                    }
                }
            }
        }
    }
}
