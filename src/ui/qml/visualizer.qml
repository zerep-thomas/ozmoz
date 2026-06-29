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
        property bool isProcessing: typeof uiBridge !== "undefined" ? uiBridge.processing : false
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

        width: isError ? Math.max(76, errorLabel.implicitWidth + 24) : (isProcessing ? 90 : (isActive ? 76 : 56))
        height: (isActive || isProcessing || isError) ? 36 : 5
        radius: height / 2

        gradient: Gradient {
            GradientStop {
                position: 0.0
                color: (pill.isActive || pill.isProcessing || pill.isError)
                    ? Qt.rgba(0.25, 0.25, 0.28, 1.0)
                    : Qt.rgba(0.45, 0.45, 0.48, 1.0)
            }
            GradientStop {
                position: 1.0
                color: (pill.isActive || pill.isProcessing || pill.isError)
                    ? Qt.rgba(0.05, 0.05, 0.05, 1.0)
                    : Qt.rgba(0.25, 0.25, 0.27, 1.0)
            }
        }
        border.color: (pill.isActive || pill.isProcessing || pill.isError)
            ? Qt.rgba(1.0, 1.0, 1.0, 0.20)
            : Qt.rgba(1.0, 1.0, 1.0, 0.05)
        border.width: 1

        // clip évite que les barres dépassent visuellement de la pill pendant la fermeture
        clip: true

        Behavior on width  { NumberAnimation { duration: 400; easing.type: Easing.OutBack; easing.overshoot: 1.2 } }
        // OutCubic sur la hauteur : pas d'overshoot, fermeture propre.
        // L'effet "pop" à l'ouverture vient du width qui garde son OutBack.
        Behavior on height { NumberAnimation { duration: 400; easing.type: Easing.OutCubic } }

        Item {
            anchors.centerIn: parent
            width: pill.width
            height: 26

            // Normal voice recording bars
            Row {
                id: audioBars
                anchors.centerIn: parent
                spacing: 3
                height: 26
                opacity: (pill.isActive && !pill.isProcessing && !pill.isError) ? 1.0 : 0.0
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

            // AI generation wave — 9 bars driven by a single sine phase,
            // each bar offset by 2π/9 so the wave travels left → right.
            // Height and opacity pulse together for a "breathing" feel.
            Row {
                id: processingWave
                anchors.centerIn: parent
                spacing: 3
                height: 26
                opacity: (pill.isProcessing && !pill.isError) ? 1.0 : 0.0
                Behavior on opacity { NumberAnimation { duration: 200 } }

                // Single phase value that drives all 9 bars at once.
                // One full cycle = 1100 ms → smooth but visibly active.
                property real wavePhase: 0
                NumberAnimation on wavePhase {
                    from: 0
                    to: Math.PI * 2
                    duration: 1100
                    loops: Animation.Infinite
                    running: pill.isProcessing
                }

                Repeater {
                    model: 9
                    Item {
                        width: 3
                        height: 26

                        Rectangle {
                            // Each bar reads the shared phase + its own angular offset.
                            property real sinVal: Math.sin(
                                processingWave.wavePhase + index * (Math.PI * 2 / 9)
                            )

                            width: 3
                            // Height: 2 px (min) → 20 px (max), centred around 11 px
                            height: Math.max(2, 4 + 16 * (0.5 + 0.5 * sinVal))
                            anchors.verticalCenter: parent.verticalCenter
                            radius: 1.5
                            // Opacity: 0.35 (trough) → 1.0 (crest), synced with height
                            color: Qt.rgba(1.0, 1.0, 1.0, 0.35 + 0.65 * (0.5 + 0.5 * sinVal))
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
