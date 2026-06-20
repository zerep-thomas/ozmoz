import QtQuick
import QtQuick.Window

Window {
    id: visualizerWindow

    x: typeof WIN_X !== "undefined" ? WIN_X : Screen.width / 2 - width / 2
    y: typeof WIN_Y !== "undefined" ? WIN_Y : Screen.height - height - 50
    width: typeof WIN_W !== "undefined" ? WIN_W : 130
    height: typeof WIN_H !== "undefined" ? WIN_H : 48

    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowTransparentForInput
    color: "transparent"
    visible: true

    Rectangle {
        id: pill
        anchors.bottom: parent.bottom
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottomMargin: 8

        property bool isActive: typeof uiBridge !== "undefined" ? uiBridge.active : false
        property var barHeights: typeof uiBridge !== "undefined" ? uiBridge.levels : [2,2,2,2,2,2,2,2,2]
        property string errorText: ""
        property bool isError: false

        Connections {
            target: typeof uiBridge !== "undefined" ? uiBridge : null
            function onVisualizerErrorChanged(msg) {
                pill.errorText = msg
                pill.isError = true
                errorTimer.restart()
            }
        }

        Timer {
            id: errorTimer
            interval: 3000
            onTriggered: pill.isError = false
        }

        width: isError ? Math.max(76, errorLabel.implicitWidth + 24) : (isActive ? 76 : 56)
        height: (isActive || isError) ? 36 : 5
        radius: height / 2

        gradient: Gradient {
            GradientStop {
                position: 0.0
                color: (pill.isActive || pill.isError)
                    ? Qt.rgba(0.25, 0.25, 0.28, 1.0)
                    : Qt.rgba(0.45, 0.45, 0.48, 1.0)
            }
            GradientStop {
                position: 1.0
                color: (pill.isActive || pill.isError)
                    ? Qt.rgba(0.05, 0.05, 0.05, 1.0)
                    : Qt.rgba(0.25, 0.25, 0.27, 1.0)
            }
        }
        border.color: (pill.isActive || pill.isError)
            ? Qt.rgba(1.0, 1.0, 1.0, 0.20)
            : Qt.rgba(1.0, 1.0, 1.0, 0.05)
        border.width: 1

        Behavior on width  { NumberAnimation { duration: 400; easing.type: Easing.OutBack; easing.overshoot: 1.2 } }
        Behavior on height { NumberAnimation { duration: 400; easing.type: Easing.OutBack; easing.overshoot: 1.2 } }

        Item {
            anchors.centerIn: parent
            width: pill.width
            height: 26

            Row {
                anchors.centerIn: parent
                spacing: 3
                height: 26
                opacity: (pill.isActive && !pill.isError) ? 1.0 : 0.0
                Behavior on opacity { NumberAnimation { duration: 200 } }

                Repeater {
                    model: 9
                    Item {
                        width: 3
                        height: 26
                        Rectangle {
                            width: 3
                            height: pill.barHeights[index] !== undefined ? pill.barHeights[index] : 2
                            anchors.centerIn: parent
                            radius: 1.5
                            color: "white"
                            Behavior on height {
                                NumberAnimation { duration: 90; easing.type: Easing.OutCubic }
                            }
                        }
                    }
                }
            }

            Text {
                id: errorLabel
                anchors.centerIn: parent
                text: pill.errorText
                color: "white"
                font.pixelSize: 13
                font.bold: true
                opacity: pill.isError ? 1.0 : 0.0
                Behavior on opacity { NumberAnimation { duration: 200 } }
            }
        }
    }
}