import QtQuick
import QtQuick.Layouts
import QtQuick.Controls.Basic
import Qt5Compat.GraphicalEffects

Item {
    id: pageRoot
    property string searchText: ""
    
    property real lastContentY: 0
    property bool showHeader: true

    property bool showInfoPanel: false
    property string infoDate: ""
    property string infoModel: ""
    
    property real infoAudioDuration: 0
    property real infoProcessingDuration: 0

    TapHandler {
        onTapped: {
            searchInput.focus = false
            pageRoot.forceActiveFocus()
        }
    }

    Rectangle {
        id: mainBackgroundCapture
        anchors.fill: parent
        color: "#494c4d" 

        ListView {
            id: root
            anchors.fill: parent
            topMargin: 65
            bottomMargin: 20
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            spacing: 12

            TapHandler {
                onTapped: {
                    searchInput.focus = false
                    pageRoot.forceActiveFocus()
                }
            }

            onContentYChanged: {
                var dy = contentY - pageRoot.lastContentY
                pageRoot.lastContentY = contentY

                if (contentY <= -topMargin) pageRoot.showHeader = true
                else if (dy > 3 && contentY > (-topMargin + 20)) pageRoot.showHeader = false
                else if (dy < -3) pageRoot.showHeader = true
            }

            model: ListModel { id: historyModel }

            Shortcut { sequence: "Ctrl+F"; onActivated: { searchInput.forceActiveFocus(); searchInput.selectAll() } }

            Connections { target: uiBridge; function onHistoryChanged() { root.updateModel() } }
            Component.onCompleted: root.updateModel()

            function updateModel() {
                historyModel.clear()
                if (typeof uiBridge === "undefined" || !uiBridge.historyListJson) return

                try {
                    var hist = JSON.parse(uiBridge.historyListJson)
                    var filterText = pageRoot.searchText.toLowerCase()

                    for (var i = 0; i < hist.length; i++) {
                        var item = hist[i]
                        var fText = item.fullText || ""

                        if (filterText === "" || fText.toLowerCase().indexOf(filterText) !== -1) {
                            historyModel.append({
                                "entryId": item.entryId || "",
                                "dateGroup": item.dateGroup || "Date inconnue",
                                "fullText": fText,
                                "shortText": item.shortText || "",
                                "detailsDate": item.detailsDate || "Unknown",
                                "method": item.method || "Whisper V3 Turbo",
                                "audioDuration": item.audioDuration !== undefined ? item.audioDuration : 0,
                                "transcriptionDuration": item.transcriptionDuration !== undefined ? item.transcriptionDuration : 0
                            })
                        }
                    }
                } catch(e) { console.log("[ERREUR] Impossible de parser l'historique:", e) }
            }

            section.property: "dateGroup"
            section.delegate: Item {
                width: root.width
                height: 38
                Text {
                    width: Math.min(620, root.width - 60)
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.bottom: parent.bottom
                    anchors.bottomMargin: 8
                    text: section
                    color: "#909090"
                    font.pixelSize: 12
                    font.bold: true
                }
            }

            delegate: Item {
                width: root.width
                height: recItem.implicitHeight

                RecordingItem {
                    id: recItem
                    anchors.horizontalCenter: parent.horizontalCenter
                    itemId: model.entryId
                    shortText: model.shortText
                    fullText: model.fullText
                    property string mDetailsDate: model.detailsDate
                    property string mMethod: model.method
                    property real mAudioDuration: model.audioDuration
                    property real mProcessingDuration: model.transcriptionDuration
                }
            }
        }

        Item {
            id: headerContainer
            width: parent.width
            height: 65
            z: 10 
            y: pageRoot.showHeader ? 0 : -height
            Behavior on y { NumberAnimation { duration: 350; easing.type: Easing.OutCubic } }

            Item {
                id: searchPill
                width: Math.min(620, parent.width - 60)
                height: 40
                anchors.centerIn: parent

                ShaderEffectSource { 
                    id: bgSource
                    sourceItem: root
                    sourceRect: Qt.rect(searchPill.x, headerContainer.y + searchPill.y, searchPill.width, searchPill.height)
                    visible: false 
                }
                FastBlur { 
                    id: bgBlur
                    anchors.fill: parent
                    source: bgSource
                    radius: 45
                    visible: false 
                }
                Rectangle { id: maskRect; anchors.fill: parent; radius: 20; visible: false }
                OpacityMask { anchors.fill: parent; source: bgBlur; maskSource: maskRect }

                Rectangle {
                    anchors.fill: parent
                    radius: 20
                    color: Qt.rgba(0.20, 0.22, 0.23, 0.50)
                    border.color: searchInput.activeFocus ? "#b0b4b5" : Qt.rgba(1, 1, 1, 0.15)
                    border.width: 1
                    Behavior on border.color { ColorAnimation { duration: 150 } }
                    HoverHandler { cursorShape: Qt.IBeamCursor }

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 16
                        anchors.rightMargin: 14
                        spacing: 0
                        
                        TextInput {
                            id: searchInput
                            Layout.fillWidth: true
                            font.pixelSize: 13
                            color: "white"
                            selectionColor: "#5a5e5f"
                            verticalAlignment: TextInput.AlignVCenter
                            onTextEdited: { pageRoot.searchText = text; root.updateModel() }
                            Text {
                                anchors.fill: parent
                                text: "Search recordings..."
                                color: Qt.rgba(1, 1, 1, 0.5)
                                font.pixelSize: parent.font.pixelSize
                                visible: parent.text.length === 0
                                verticalAlignment: Text.AlignVCenter
                            }
                        }
                        Text { text: "CTRL+F"; color: Qt.rgba(1, 1, 1, 0.4); font.pixelSize: 10; font.bold: true }
                    }
                }
            }
        }
    }

    component ActionButton: Rectangle {
        id: actionBtn
        property string iconSource: ""
        property color iconHoverColor: "#ffffff"
        property color iconDefaultColor: "#909597"
        property alias iconScale: iconContainer.scale
        signal clicked()

        implicitWidth: 28
        implicitHeight: 28
        radius: 6
        color: "transparent"

        Item {
            id: iconContainer
            width: 16
            height: 16
            anchors.centerIn: parent
            Image { id: btnIcon; source: actionBtn.iconSource; anchors.fill: parent; fillMode: Image.PreserveAspectFit; visible: false }
            ColorOverlay { 
                anchors.fill: btnIcon
                source: btnIcon
                color: btnArea.containsMouse ? actionBtn.iconHoverColor : actionBtn.iconDefaultColor
                Behavior on color { ColorAnimation { duration: 120 } } 
            }
        }
        MouseArea { id: btnArea; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: actionBtn.clicked() }
    }

    component RecordingItem: Rectangle {
        id: recItem
        property string itemId: ""
        property string shortText: ""
        property string fullText: ""
        property bool isExpanded: false

        width: isExpanded ? Math.min(625, parent.width - 40) : Math.min(620, parent.width - 60)
        implicitHeight: isExpanded ? expandedLayout.implicitHeight + 24 : 40
        radius: 20
        color: "#5a5e5f"
        clip: true
        transform: Translate { id: slideTransform }

        Behavior on width { NumberAnimation { duration: 250; easing.type: Easing.OutCubic } }
        Behavior on implicitHeight { NumberAnimation { duration: 250; easing.type: Easing.OutCubic } }

        SequentialAnimation {
            id: deleteAnim
            ParallelAnimation {
                NumberAnimation { target: slideTransform; property: "x"; to: 300; duration: 300; easing.type: Easing.InBack }
                NumberAnimation { target: recItem; property: "opacity"; to: 0; duration: 300 }
            }
            ScriptAction { script: { recItem.implicitHeight = 0 } }
            PauseAnimation { duration: 250 }
            onFinished: { uiBridge.deleteHistoryEntry(recItem.itemId) }
        }

        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: { searchInput.focus = false; recItem.isExpanded = !recItem.isExpanded } }

        ColumnLayout {
            id: expandedLayout
            anchors { left: parent.left; right: parent.right; top: parent.top; leftMargin: 16; rightMargin: 16; topMargin: 12 }
            spacing: 18

            Text {
                text: isExpanded ? recItem.fullText : recItem.shortText
                color: "white"
                font.pixelSize: 13
                font.bold: isExpanded
                Layout.fillWidth: true
                wrapMode: isExpanded ? Text.WordWrap : Text.NoWrap
                elide: isExpanded ? Text.ElideNone : Text.ElideRight
            }

            RowLayout {
                visible: isExpanded
                opacity: isExpanded ? 1 : 0
                Layout.fillWidth: true
                spacing: 2
                Behavior on opacity { NumberAnimation { duration: 200; easing.type: Easing.InOutQuad } }

                ActionButton {
                    id: copyBtn
                    property bool copied: false
                    iconSource: copied ? "icons/check.svg" : "icons/copy.svg"
                    iconDefaultColor: "#909597"
                    iconHoverColor: "#ffffff"
                    SequentialAnimation {
                        id: bounceAnim
                        NumberAnimation { target: copyBtn; property: "iconScale"; to: 1.3; duration: 120; easing.type: Easing.OutQuad }
                        NumberAnimation { target: copyBtn; property: "iconScale"; to: 1.0; duration: 250; easing.type: Easing.OutBounce }
                    }
                    onClicked: { if (copied) return; uiBridge.copyToClipboard(recItem.fullText); copied = true; copyReset.start() }
                    Timer { id: copyReset; interval: 700; onTriggered: { copyBtn.copied = false; bounceAnim.start(); } }
                }

                ActionButton {
                    iconSource: "icons/info.svg"
                    onClicked: {
                        pageRoot.infoDate = recItem.mDetailsDate
                        pageRoot.infoModel = recItem.mMethod
                        pageRoot.infoAudioDuration = recItem.mAudioDuration
                        pageRoot.infoProcessingDuration = recItem.mProcessingDuration
                        pageRoot.showInfoPanel = true
                    }
                }

                Item { Layout.fillWidth: true } 

                ActionButton {
                    iconSource: "icons/delete.svg"
                    iconHoverColor: "#e05555"
                    onClicked: { deleteAnim.start() }
                }
            }
        }
    }

    Item {
        id: lateralOverlay
        anchors.fill: parent
        z: 200
        visible: opacity > 0
        opacity: pageRoot.showInfoPanel ? 1.0 : 0.0

        Behavior on opacity { NumberAnimation { duration: 250; easing.type: Easing.OutCubic } }

        MouseArea {
            anchors.fill: parent
            onClicked: pageRoot.showInfoPanel = false
        }

        ShaderEffectSource {
            id: infoBlurSrc
            anchors.fill: parent
            sourceItem: mainBackgroundCapture
            visible: false
        }
        
        FastBlur {
            id: firstBlurPass
            anchors.fill: parent
            source: infoBlurSrc
            radius: 32
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
            radius: 32
            transparentBorder: false
        }
        
        Rectangle {
            anchors.fill: parent
            color: Qt.rgba(0.12, 0.13, 0.14, 0.70) 
        }

        Rectangle {
            id: drawer
            width: 280
            height: parent.height
            color: "#494c4d"
            
            x: pageRoot.showInfoPanel ? parent.width - width : parent.width
            border.color: "#66696a"
            border.width: 1

            Behavior on x { NumberAnimation { duration: 300; easing.type: Easing.OutCubic } }

            MouseArea { anchors.fill: parent }

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 20
                spacing: 20

                Text {
                    text: "Recording Details"
                    color: "white"
                    font.pixelSize: 16
                    font.bold: true
                    Layout.fillWidth: true
                    Layout.bottomMargin: 10
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 5
                    
                    Text { text: "Time"; color: "#909090"; font.pixelSize: 12; font.bold: true }
                    Text { text: pageRoot.infoDate; color: "white"; font.pixelSize: 14 }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 5
                    Text { text: "Audio Duration"; color: "#909090"; font.pixelSize: 12; font.bold: true }
                    Text { text: pageRoot.infoAudioDuration.toFixed(2) + " sec"; color: "white"; font.pixelSize: 14 }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 5
                    Text { text: "Compute Time"; color: "#909090"; font.pixelSize: 12; font.bold: true }
                    Text { text: pageRoot.infoProcessingDuration.toFixed(2) + " sec"; color: "white"; font.pixelSize: 14 }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 5
                    
                    Text { text: "Voice Model"; color: "#909090"; font.pixelSize: 12; font.bold: true }
                    
                    RowLayout {
                        spacing: 8
                        
                        Image { 
                            source: "icons/whisper_large.png"
                            sourceSize: Qt.size(20, 20)
                            width: 20
                            height: 20
                            fillMode: Image.PreserveAspectFit
                            mipmap: true 
                            Layout.alignment: Qt.AlignVCenter 
                        }
                        
                        Text { 
                            text: pageRoot.infoModel
                            color: "white"
                            font.pixelSize: 14 
                            Layout.alignment: Qt.AlignVCenter
                        }
                    }
                }

                Item { Layout.fillHeight: true }
            }
        }
    }
}