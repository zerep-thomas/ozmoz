import QtQuick
import QtQuick.Layouts
import QtQuick.Controls.Basic
import Qt5Compat.GraphicalEffects

ScrollView {
    id: root
    clip: true
    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
    ScrollBar.vertical.policy: ScrollBar.AsNeeded
    contentWidth: availableWidth
    
    Component.onCompleted: contentItem.boundsBehavior = Flickable.StopAtBounds

    Theme { id: theme }

    component StatItem: ColumnLayout {
        property string value: "0"
        property string label: "label"
        Layout.fillWidth: true
        spacing: 2
        Text {
            text: value
            color: theme.textPrimary
            font.pixelSize: 17
            font.bold: true
            Layout.fillWidth: true
            horizontalAlignment: Text.AlignHCenter
        }
        Text {
            text: label
            color: theme.textSecondary
            font.pixelSize: 11
            Layout.fillWidth: true
            horizontalAlignment: Text.AlignHCenter
        }
    }

    component GetStartedItem: RowLayout {
        property string iconSource: ""
        property string title: "Title"
        property string subtitle: "Subtitle"
        property string shortcutKey1: ""
        property string shortcutKey2: ""

        Layout.fillWidth: true
        spacing: 14

        Item {
            width: 15; height: 15
            Layout.preferredWidth: 22
            Layout.alignment: Qt.AlignVCenter
            Image {
                id: gsIcon
                source: iconSource
                anchors.fill: parent
                fillMode: Image.PreserveAspectFit
                visible: false
            }
            ColorOverlay { anchors.fill: gsIcon; source: gsIcon; color: theme.textMuted }
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            Text {
                text: title
                color: theme.textPrimary
                font.pixelSize: 13
                font.bold: true
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
            }
            Text {
                text: subtitle
                color: theme.textMuted
                font.pixelSize: 12
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
            }
        }

        Row {
            spacing: 4
            visible: shortcutKey1 !== ""
            Layout.alignment: Qt.AlignVCenter
            Repeater {
                model: shortcutKey1 !== "" && shortcutKey2 !== "" ? [shortcutKey1, shortcutKey2] : [shortcutKey1]
                Rectangle {
                    width: badgeLabel.implicitWidth + 14
                    height: 22
                    radius: 5
                    color: "#4a4e50"
                    border.color: "#6e7273"
                    border.width: 1
                    Text {
                        id: badgeLabel
                        anchors.centerIn: parent
                        text: modelData
                        color: "#d0d0d0"
                        font.pixelSize: 11
                        font.bold: true
                    }
                }
            }
        }
    }

    component ChangelogItem: RowLayout {
        property string date: ""
        property string title: ""
        property string description: ""

        Layout.fillWidth: true
        spacing: 16
        Layout.topMargin: 12
        Layout.bottomMargin: 12

        Text {
            text: date
            color: theme.textSecondary
            font.pixelSize: 11
            Layout.preferredWidth: 60
            Layout.alignment: Qt.AlignTop
            topPadding: 1
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 4
            Text {
                text: title
                color: theme.textPrimary
                font.pixelSize: 13
                font.bold: true
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
            }
            Text {
                text: description
                color: theme.textSecondary
                font.pixelSize: 12
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
            }
        }
    }

    Item {
        width: root.availableWidth
        implicitHeight: mainColumn.implicitHeight + 32

        ColumnLayout {
            id: mainColumn
            width: Math.min(520, root.availableWidth - 60)
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: parent.top
            anchors.topMargin: 15
            spacing: 20

            // --- STATISTICS ---
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: 80
                color: theme.backgroundTertiary
                radius: 12
                border.color: theme.borderSubtle
                border.width: 1

                RowLayout {
                    anchors.fill: parent
                    spacing: 0
                    StatItem { value: uiBridge.statAvgSpeed; label: "Average speed" }
                    Rectangle { width: 1; height: 30; color: theme.borderSubtle; Layout.alignment: Qt.AlignVCenter }
                    StatItem { value: uiBridge.statWordsThisWeek; label: "Words this week" }
                    Rectangle { width: 1; height: 30; color: theme.borderSubtle; Layout.alignment: Qt.AlignVCenter }
                    StatItem { value: uiBridge.statTimeSaved; label: "Saved this week" }
                }
            }

            // --- GET STARTED ---
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 0

                Text {
                    text: "Get started"
                    color: theme.textPrimary
                    font.pixelSize: 14
                    font.bold: true
                    Layout.bottomMargin: 10
                }

                GetStartedItem {
                    iconSource: "icons/record.svg"
                    title: "Start recording"
                    subtitle: "Transform your voice into text by holding down the keys"
                    shortcutKey1: uiBridge.recordShortcut1
                    shortcutKey2: uiBridge.recordShortcut2
                }
                Rectangle { Layout.fillWidth: true; height: 1; color: "#5e6263"; Layout.topMargin: 8; Layout.bottomMargin: 8 }

                GetStartedItem {
                    iconSource: "icons/mode.svg"
                    title: "Create a mode"
                    subtitle: "Build the perfect mode for your workflow."
                }
                Rectangle { Layout.fillWidth: true; height: 1; color: "#5e6263"; Layout.topMargin: 8; Layout.bottomMargin: 8 }

                GetStartedItem {
                    iconSource: "icons/vocabulary.svg"
                    title: "Add vocabulary"
                    subtitle: "Teach custom words, names, or industry terms."
                }
            }

            // --- WHAT'S NEW ---
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 10

                RowLayout {
                    Layout.fillWidth: true
                    Text {
                        text: "What's new?"
                        color: theme.textPrimary
                        font.pixelSize: 14
                        font.bold: true
                        Layout.fillWidth: true
                    }
                    Text {
                        text: "View all changes"
                        color: viewAllArea.containsMouse ? theme.textPrimary : theme.textMuted
                        font.pixelSize: 12
                        font.underline: viewAllArea.containsMouse
                        Behavior on color { ColorAnimation { duration: 120 } }
                        MouseArea {
                            id: viewAllArea
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: Qt.openUrlExternally("https://github.com/zerep-thomas/ozmoz/releases")
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    color: theme.backgroundTertiary
                    radius: 12
                    border.color: theme.borderSubtle
                    border.width: 1
                    implicitHeight: changelogLayout.implicitHeight

                    ColumnLayout {
                        id: changelogLayout
                        anchors { left: parent.left; right: parent.right; leftMargin: 16; rightMargin: 16 }
                        spacing: 0

                        Repeater {
                            model: uiBridge.changelogList
                            ChangelogItem {
                                date: modelData.date
                                title: modelData.title
                                description: modelData.description
                            }
                        }
                    }
                }
            }
        }
    }
}