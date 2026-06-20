import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Window
import Qt5Compat.GraphicalEffects

Window {
    id: settingsWindow
    width: 750
    height: 500
    title: "Ozmoz"

    flags: Qt.Window
    color: "#494c4d"

    Theme { id: theme }

    property bool showUpdateModal: false
    property string updateVersion: ""
    property string updateUrl: ""

    Connections {
        target: uiBridge
        function onShowSettingsWindow() {
            settingsWindow.show()
            settingsWindow.raise()
            settingsWindow.requestActivate()
        }
        function onShowUpdateModalRequested(version, url) {
            settingsWindow.show()
            settingsWindow.raise()
            settingsWindow.requestActivate()
            settingsWindow.updateVersion = version
            settingsWindow.updateUrl = url
            settingsWindow.showUpdateModal = true
        }
        function onNavigateToConfig() {
            for (var i = 0; i < navModel.count; ++i) {
                navModel.setProperty(i, "isActive", i === 1)
            }
            pageStack.currentIndex = 1
        }
        function onNavigateToDefaultMode() {
            for (var i = 0; i < navModel.count; ++i) {
                navModel.setProperty(i, "isActive", i === 4)
            }
            pageStack.currentIndex = 4
            if (pageStack.children[4] && typeof pageStack.children[4].openDefaultMode === "function") {
                pageStack.children[4].openDefaultMode()
            }
        }
    }

    Rectangle {
        id: backgroundCapture
        anchors.fill: parent
        color: "#494c4d"

        Row {
            anchors.fill: parent

            // --- SIDEBAR ---
            Rectangle {
                width: 170
                height: parent.height
                color: "transparent"

                Rectangle {
                    width: 0.5
                    height: parent.height
                    anchors.right: parent.right
                    color: "#6a6a6a"
                }

                ListModel {
                    id: navModel
                    ListElement { name: "Home"; iconSource: "icons/home.png"; isActive: true }
                    ListElement { name: "Settings"; iconSource: "icons/config.png"; isActive: false }
                    ListElement { name: "History"; iconSource: "icons/history.png"; isActive: false }
                    ListElement { name: "Vocabulary"; iconSource: "icons/vocabulary.png"; isActive: false }
                    ListElement { name: "Mode"; iconSource: "icons/mode.png"; isActive: false }
                }

                Column {
                    anchors.top: parent.top
                    anchors.topMargin: 15
                    anchors.left: parent.left
                    anchors.right: parent.right
                    spacing: 2

                    Repeater {
                        model: navModel

                        Rectangle {
                            width: 150
                            height: 38
                            anchors.horizontalCenter: parent.horizontalCenter
                            radius: 8
                            color: model.isActive ? theme.backgroundTertiary : "transparent"

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    for (var i = 0; i < navModel.count; ++i) {
                                        navModel.setProperty(i, "isActive", false)
                                    }
                                    navModel.setProperty(index, "isActive", true)
                                    pageStack.currentIndex = index
                                }
                            }

                            Row {
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.left: parent.left
                                anchors.leftMargin: 10
                                spacing: 7

                                Item {
                                    width: 21; height: 21
                                    anchors.verticalCenter: parent.verticalCenter
                                    Image {
                                        source: model.iconSource
                                        anchors.fill: parent
                                        fillMode: Image.PreserveAspectFit
                                    }
                                }

                                Text {
                                    text: model.name
                                    color: theme.textPrimary
                                    font.pixelSize: 13
                                    font.bold: true
                                    anchors.verticalCenter: parent.verticalCenter
                                }
                            }
                        }
                    }
                }
            }

            // --- MAIN CONTENT ---
            StackLayout {
                id: pageStack
                width: parent.width - 170
                height: parent.height

                HomePage {}
                ConfigPage {}
                HistoryPage {}
                VocabularyPage {}
                ModePage {}
            }
        }
    }

    // ─── MODAL NOTIFICATION UPDATE ───
    Item {
        id: updateModalOverlay
        anchors.fill: parent
        z: 1000
        visible: opacity > 0
        opacity: settingsWindow.showUpdateModal ? 1.0 : 0.0

        Behavior on opacity { NumberAnimation { duration: 250; easing.type: Easing.OutCubic } }

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
            MouseArea { anchors.fill: parent } 
        }

        Rectangle {
            anchors.centerIn: parent
            width: 380
            height: 180
            radius: 12
            color: "#494c4d"
            border.color: "#66696a"
            border.width: 1

            scale: settingsWindow.showUpdateModal ? 1.0 : 0.8
            Behavior on scale { NumberAnimation { duration: 250; easing.type: Easing.OutBack; easing.overshoot: 1.2 } }

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 20
                spacing: 10

                Text {
                    text: "Update Available"
                    color: "white"
                    font.pixelSize: 16
                    font.bold: true
                    Layout.alignment: Qt.AlignHCenter
                }

                Text {
                    text: "A new version (" + settingsWindow.updateVersion + ") of Ozmoz is available. Would you like to view the release and download it on GitHub?"
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
                        color: updateCancelHover.containsMouse ? "#6a6e70" : "#55585a"
                        border.color: "#7e8385"
                        border.width: 1
                        Behavior on color { ColorAnimation { duration: 120 } }

                        Text { anchors.centerIn: parent; text: "Cancel"; color: "white"; font.pixelSize: 13; font.bold: true }
                        MouseArea {
                            id: updateCancelHover
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: settingsWindow.showUpdateModal = false
                        }
                    }

                    Rectangle {
                        implicitWidth: 120
                        height: 32; radius: 8
                        color: updateConfirmHover.containsMouse ? "#2c5fc4" : "#2452a3"
                        border.color: "#3a73e6"
                        border.width: 1
                        Behavior on color { ColorAnimation { duration: 120 } }

                        Text { anchors.centerIn: parent; text: "Go to GitHub"; color: "white"; font.pixelSize: 13; font.bold: true }
                        MouseArea {
                            id: updateConfirmHover
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                Qt.openUrlExternally(settingsWindow.updateUrl)
                                settingsWindow.showUpdateModal = false
                            }
                        }
                    }
                }
            }
        }
    }
}