import QtQuick
import QtQuick.Layouts
import QtQuick.Controls.Basic
import Qt5Compat.GraphicalEffects

Item {
    id: pageRoot
    property int selectedIndex: -1

    TapHandler {
        onTapped: {
            inputField.focus = false
            pageRoot.selectedIndex = -1
            pageRoot.forceActiveFocus()
        }
    }

    ListModel { id: wordModel }

    Connections {
        target: uiBridge
        function onVocabularyChanged() {
            loadVocabularyFromBackend()
        }
    }

    Component.onCompleted: loadVocabularyFromBackend()

    function loadVocabularyFromBackend() {
        wordModel.clear()
        var jsonStr = uiBridge.vocabularyListJson
        if (!jsonStr) return
        try {
            var words = JSON.parse(jsonStr)
            for (var i = 0; i < words.length; i++) {
                wordModel.append({ "word": words[i] })
            }
        } catch(e) {}
    }

    function addWord() {
        var text = inputField.text.trim()
        if (text.length === 0) {
            inputField.focus = false
            pageRoot.forceActiveFocus()
            return
        }
        uiBridge.addVocabularyWord(text)
        inputField.text = ""
        inputField.focus = false
        pageRoot.forceActiveFocus()
    }

    ListView {
        id: rootList
        anchors.fill: parent
        topMargin: 70
        bottomMargin: 20
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        spacing: 12

        TapHandler {
            onTapped: {
                inputField.focus = false
                pageRoot.selectedIndex = -1
                pageRoot.forceActiveFocus()
            }
        }

        model: wordModel

        delegate: Item {
            id: delegateItem
            width: rootList.width
            height: deleting ? 0 : 40

            property bool deleting: false

            transform: Translate { id: slideTransform; x: 0 }
            Behavior on height { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }

            Rectangle {
                id: cardRect
                width: Math.min(620, parent.width - 60)
                height: 40
                anchors.horizontalCenter: parent.horizontalCenter
                radius: 20
                color: "#5a5e5f"
                border.color: (pageRoot.selectedIndex === index && editInput.activeFocus) ? "#b0b4b5" : "transparent"
                border.width: 1
                clip: true

                Behavior on border.color { ColorAnimation { duration: 150 } }

                HoverHandler { id: hoverHandler; enabled: !deleting }
                
                Rectangle {
                    anchors.fill: parent
                    radius: 20
                    color: hoverHandler.hovered && pageRoot.selectedIndex !== index ? "#10ffffff" : "transparent"
                    Behavior on color { ColorAnimation { duration: 120 } }
                }

                TapHandler {
                    gesturePolicy: TapHandler.WithinBounds
                    enabled: !deleting
                    onTapped: {
                        inputField.focus = false
                        if (pageRoot.selectedIndex !== index) {
                            pageRoot.selectedIndex = index
                            editInput.text = model.word
                            editInput.forceActiveFocus()
                            editInput.selectAll()
                        }
                    }
                }

                Item {
                    anchors.fill: parent
                    visible: pageRoot.selectedIndex !== index && !deleting
                    opacity: visible ? 1 : 0
                    Behavior on opacity { NumberAnimation { duration: 120 } }

                    Text {
                        text: model.word
                        color: "white"
                        font.pixelSize: 13
                        font.bold: true
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.left: parent.left
                        anchors.leftMargin: 16
                    }

                    Rectangle {
                        anchors.right: parent.right
                        anchors.rightMargin: 8
                        anchors.verticalCenter: parent.verticalCenter
                        width: 28
                        height: 28
                        radius: 6
                        color: "transparent"
                        opacity: hoverHandler.hovered ? 1 : 0
                        Behavior on opacity { NumberAnimation { duration: 150 } }

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
                            color: normalCrossHover.hovered ? "#e05555" : "#909597"
                            Behavior on color { ColorAnimation { duration: 120 } }
                        }

                        HoverHandler { id: normalCrossHover; enabled: !deleting }
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: deleteAnimation.start()
                        }
                    }
                }

                Item {
                    anchors.fill: parent
                    visible: pageRoot.selectedIndex === index && !deleting
                    opacity: visible ? 1 : 0
                    Behavior on opacity { NumberAnimation { duration: 150 } }

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 16
                        anchors.rightMargin: 8
                        spacing: 8

                        TextInput {
                            id: editInput
                            Layout.fillWidth: true
                            color: "white"
                            font.pixelSize: 13
                            font.bold: true
                            verticalAlignment: TextInput.AlignVCenter
                            selectionColor: "#4a90d9"

                            onAccepted: {
                                var t = text.trim()
                                if (t.length === 0) {
                                    editInput.focus = false
                                    pageRoot.selectedIndex = -1
                                    pageRoot.forceActiveFocus()
                                    return
                                }
                                uiBridge.removeVocabularyWord(index)
                                uiBridge.addVocabularyWord(t)
                                editInput.focus = false
                                pageRoot.selectedIndex = -1
                                pageRoot.forceActiveFocus()
                            }

                            Keys.onEscapePressed: {
                                editInput.focus = false
                                pageRoot.selectedIndex = -1
                                pageRoot.forceActiveFocus()
                            }
                            
                            onActiveFocusChanged: {
                                if (!activeFocus && pageRoot.selectedIndex === index) {
                                    var t = text.trim()
                                    if (t.length > 0) {
                                        uiBridge.removeVocabularyWord(index)
                                        uiBridge.addVocabularyWord(t)
                                    }
                                    pageRoot.selectedIndex = -1
                                }
                            }
                        }
                    }
                }
            }

            SequentialAnimation {
                id: deleteAnimation
                ParallelAnimation {
                    NumberAnimation { target: slideTransform; property: "x"; to: 300; duration: 300; easing.type: Easing.InBack }
                    NumberAnimation { target: delegateItem; property: "opacity"; to: 0; duration: 300 }
                }
                ScriptAction { script: delegateItem.deleting = true }
                PauseAnimation { duration: 250 }
                ScriptAction {
                    script: {
                        uiBridge.removeVocabularyWord(index)
                        pageRoot.selectedIndex = -1
                    }
                }
            }
        }
    }

    Item {
        id: headerContainer
        width: parent.width
        height: 65
        z: 10 
        y: 0

        Item {
            id: searchPill
            width: Math.min(620, parent.width - 60)
            height: 40
            anchors.centerIn: parent

            ShaderEffectSource {
                id: bgSource
                sourceItem: rootList
                sourceRect: Qt.rect(searchPill.x, searchPill.y, searchPill.width, searchPill.height)
                visible: false
            }
            FastBlur {
                id: bgBlur
                anchors.fill: parent
                source: bgSource
                radius: 45
                visible: false
            }
            Rectangle {
                id: maskRect
                anchors.fill: parent
                radius: 20
                visible: false
            }
            OpacityMask {
                anchors.fill: parent
                source: bgBlur
                maskSource: maskRect
            }

            Rectangle {
                anchors.fill: parent
                radius: 20
                color: Qt.rgba(0.20, 0.22, 0.23, 0.50)
                border.color: inputField.activeFocus ? "#b0b4b5" : Qt.rgba(1, 1, 1, 0.15)
                border.width: 1
                Behavior on border.color { ColorAnimation { duration: 150 } }

                HoverHandler { cursorShape: Qt.IBeamCursor }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 16
                    anchors.rightMargin: 6
                    spacing: 8

                    TextInput {
                        id: inputField
                        Layout.fillWidth: true
                        font.pixelSize: 13
                        color: "white"
                        selectionColor: "#5a5e5f"
                        verticalAlignment: TextInput.AlignVCenter

                        onAccepted: {
                            var t = text.trim()
                            if (t.length === 0) {
                                inputField.focus = false
                                pageRoot.forceActiveFocus()
                                return
                            }
                            pageRoot.addWord()
                        }

                        Text {
                            anchors.fill: parent
                            text: "Add custom vocabulary..."
                            color: Qt.rgba(1, 1, 1, 0.5)
                            font.pixelSize: parent.font.pixelSize
                            visible: parent.text.length === 0
                            verticalAlignment: Text.AlignVCenter
                        }
                    }

                    Rectangle {
                        height: 28
                        implicitWidth: addWordRow.implicitWidth + 16
                        radius: 14
                        color: addWordArea.containsMouse ? "#6a6e70" : "#4a4e50"
                        border.color: "#6e7273"
                        border.width: 1
                        opacity: inputField.activeFocus ? 1 : 0
                        Behavior on opacity { NumberAnimation { duration: 150 } }
                        Behavior on color { ColorAnimation { duration: 100 } }

                        Row {
                            id: addWordRow
                            anchors.centerIn: parent
                            spacing: 6
                            Text { text: "Add"; color: "#d0d0d0"; font.pixelSize: 12; font.bold: true; anchors.verticalCenter: parent.verticalCenter }
                        }
                        MouseArea {
                            id: addWordArea
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: pageRoot.addWord()
                        }
                    }
                }
            }
        }
    }
}