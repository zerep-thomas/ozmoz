import QtQuick
import QtQuick.Layouts
import QtQuick.Controls.Basic
import Qt5Compat.GraphicalEffects

Item {
    id: modePageRoot

    property string selectedPreset:     uiBridge.defaultModePreset
    property string selectedLanguage:   uiBridge.defaultModeLanguage
    property string selectedVoiceModel: uiBridge.defaultModeVoiceModel
    
    property bool   showDetail:          false
    property bool   showCreateModeModal: false
    property bool   showDeleteModeModal: false
    property int    editingModeIndex:    -1 
    property int    activeModeIndex:     -1 

    property string newModeName: ""
    property string newModePreset: presets[0].name
    property string newModeLanguage: "English"
    property string newModeVoiceModel: voiceModels[1].name 

    property string openDropdown: ""
    property string pendingModelSelectionContext: ""
    property rect   dropdownRect: Qt.rect(0, 0, 0, 0)

    property string activeTooltip: ""
    property point  tooltipAnchor: Qt.point(0, 0)
    
    property string presetTip: ""
    property point  presetTipAnchor: Qt.point(0, 0)
    readonly property int presetTipWidth: 200

    property string voiceModelTip: ""
    property point  voiceModelTipAnchor: Qt.point(0, 0)
    readonly property int voiceModelTipWidth: 200

    property bool showDownloadModal: false
    property string modelToDownload: ""
    property string downloadStatus: "idle" 
    property real downloadProgress: 0.0
    
    property bool showApiKeyModal: false
    
    property bool showEquationKeyModal: false

    Connections {
        target: uiBridge
        function onDownloadLocalModelStatusChanged(status) {
            modePageRoot.downloadStatus = status
            if (status === "done") {
                if (modePageRoot.pendingModelSelectionContext === "modal_voicemodel") {
                    modePageRoot.newModeVoiceModel = modePageRoot.modelToDownload
                } else if (modePageRoot.editingModeIndex === -1) {
                    uiBridge.setDefaultModeVoiceModel(modePageRoot.modelToDownload)
                } else {
                    var mIdDl = customModesList.get(modePageRoot.editingModeIndex).id
                    uiBridge.updateCustomMode(mIdDl, "voice_model", modePageRoot.modelToDownload)
                }
                modePageRoot.pendingModelSelectionContext = ""
                modePageRoot.showDownloadModal = false
                modePageRoot.downloadStatus = "idle"
                modePageRoot.downloadProgress = 0.0
                syncActiveModeToBackend()
            }
        }
        function onDownloadProgressChanged(progress) {
            modePageRoot.downloadProgress = progress
        }
    }

    function openDefaultMode() {
        modePageRoot.editingModeIndex = -1;
        modePageRoot.activeModeIndex = -1; 
        modePageRoot.showDetail = true;
        
        uiBridge.setDefaultModeVoiceModel("Select a model...");
        syncActiveModeToBackend();
    }

    function syncActiveModeToBackend() {
        var p = "Voice to text"
        var l = "English"
        var m = "Whisper V3 Turbo"
        
        if (activeModeIndex === -1) {
            p = selectedPreset || "Voice to text"
            l = selectedLanguage || "English"
            m = selectedVoiceModel || "Whisper V3 Turbo"
        } else if (activeModeIndex >= 0 && activeModeIndex < customModesList.count) {
            var cust = customModesList.get(activeModeIndex)
            if (cust) {
                p = cust.modePreset || "Voice to text"
                l = cust.modeLanguage || "English"
                m = cust.modeVoiceModel || "Whisper V3 Turbo"
            }
        }
        
        if (p !== undefined && l !== undefined && m !== undefined && p !== null && l !== null && m !== null) {
            uiBridge.applyActiveModeSettings(p, l, m)
        }
    }

    onActiveModeIndexChanged: syncActiveModeToBackend()
    onSelectedPresetChanged: syncActiveModeToBackend()
    onSelectedLanguageChanged: syncActiveModeToBackend()
    onSelectedVoiceModelChanged: syncActiveModeToBackend()
    
    Connections {
        target: uiBridge
        function onModeChanged() {
            loadCustomModes()
        }
    }

    Component.onCompleted: {
        loadCustomModes()
        syncActiveModeToBackend()
    }

    function loadCustomModes() {
        var jsonStr = uiBridge.customModesJson
        if (!jsonStr) return
        var modes = JSON.parse(jsonStr)
        var newActiveIndex = -1
        var currentActiveId = uiBridge.activeModeId
        
        customModesList.clear()
        for (var i = 0; i < modes.length; i++) {
            customModesList.append(modes[i])
            if (modes[i].id === currentActiveId) {
                newActiveIndex = i
            }
        }
        
        if (currentActiveId === "default") {
            activeModeIndex = -1
        } else {
            activeModeIndex = newActiveIndex
        }
    }

    ListModel { id: customModesList }


    readonly property var presets: [
        { name: "Voice to text", icon: "icons/voice2text.svg", tag: "", tip: "Simply to transcribe what you say into text", requireKey: false },
        { name: "Email Draft", icon: "icons/email.svg", tag: "", tip: "Automatically format your speech into a ready-to-send email", requireKey: false },
        { name: "Equation", icon: "icons/equation.svg", tag: "LaTeX", tip: "Convert your voice into LaTeX equations. Requires Groq API Key.", requireKey: true }
    ]

    readonly property var languages: [
        "Afrikaans", "Albanian", "Amharic", "Arabic", "Armenian", "Assamese", "Azerbaijani",
        "Bashkir", "Basque", "Belarusian", "Bengali", "Bosnian", "Breton", "Bulgarian",
        "Burmese", "Catalan", "Chinese", "Croatian", "Czech", "Danish", "Dutch",
        "English", "Estonian", "Faroese", "Finnish", "French", "Galician", "Georgian",
        "German", "Greek", "Gujarati", "Haitian Creole", "Hausa", "Hawaiian", "Hebrew",
        "Hindi", "Hungarian", "Icelandic", "Indonesian", "Italian", "Japanese", "Javanese",
        "Kannada", "Kazakh", "Khmer", "Korean", "Lao", "Latin", "Latvian", "Lingala",
        "Lithuanian", "Luxembourgish", "Macedonian", "Malagasy", "Malay", "Malayalam",
        "Maltese", "Maori", "Marathi", "Mongolian", "Nepali", "Norwegian", "Nynorsk",
        "Occitan", "Pashto", "Persian", "Polish", "Portuguese", "Punjabi", "Romanian",
        "Russian", "Sanskrit", "Serbian", "Shona", "Sindhi", "Sinhala", "Slovak",
        "Slovenian", "Somali", "Spanish", "Sundanese", "Swahili", "Swedish", "Tagalog",
        "Tajik", "Tamil", "Tatar", "Telugu", "Thai", "Tibetan", "Turkish", "Turkmen",
        "Ukrainian", "Urdu", "Uzbek", "Vietnamese", "Welsh", "Yiddish", "Yoruba"
    ]
    
    readonly property var englishOnly: ["English"]

    readonly property var voiceModels: [
        { name: "Whisper V3", tag: "", cloud: true, icon: "icons/whisper.png", tip: "Whisper Large v3 is OpenAI's most advanced speech recognition model, offering cutting-edge accuracy even in challenging audio conditions." },
        { name: "Whisper V3 Turbo", tag: "", cloud: true, icon: "icons/whisper_large.png", tip: "Whisper Large v3 Turbo is OpenAI's fastest speech recognition model, designed to combine speed, good accuracy and multilingual support." },
        { name: "Local Whisper Base", tag: "Fast", cloud: false, icon: "icons/whisper_local.png", tip: "Runs completely offline on your device. High speed and total privacy." },
        { name: "Local Whisper Small", tag: "Accurate", cloud: false, icon: "icons/whisper_local.png", tip: "Runs completely offline. Better accuracy, requires slightly more memory." },
        { name: "Local Whisper Turbo", tag: "Best", cloud: false, icon: "icons/whisper_local.png", tip: "The ultimate offline experience. Multilingual, high accuracy, and fast." },
        { name: "Local Distil-Whisper (EN)", tag: "Ultra Fast", cloud: false, icon: "icons/whisper_local.png", tip: "6x faster than normal models. WARNING: English language only." }
    ]

    component ToggleSwitch: Item {
        id: toggleRoot
        property bool checked: false
        signal clicked()

        property bool _isInit: false
        Component.onCompleted: Qt.callLater(function() { _isInit = true })

        width: 36
        height: 20

        Rectangle {
            anchors.fill: parent
            radius: height / 2
            color: toggleRoot.checked ? "#34c759" : "#8e8e93"
            Behavior on color { ColorAnimation { duration: toggleRoot._isInit ? 150 : 0 } }
        }

        Rectangle {
            width: 16
            height: 16
            radius: 8
            color: "white"
            anchors.verticalCenter: parent.verticalCenter
            x: toggleRoot.checked ? toggleRoot.width - width - 2 : 2

            Behavior on x {
                NumberAnimation { duration: toggleRoot._isInit ? 150 : 0; easing.type: Easing.OutQuad }
            }
        }

        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: {
                toggleRoot.clicked()
                syncActiveModeToBackend() 
            }
        }
    }

    function getVoiceModelIcon(mName) {
        if (mName === "Select a model...") return "icons/info.svg";
        for (var i = 0; i < voiceModels.length; i++) {
            if (voiceModels[i].name === mName) return voiceModels[i].icon;
        }
        return voiceModels[0].icon;
    }

    function getPresetIcon(pName) {
        for (var i = 0; i < presets.length; i++) {
            if (presets[i].name === pName) return presets[i].icon;
        }
        return presets[0].icon;
    }

    function getHeaderTitle() {
        if (!showDetail) return "Modes";
        if (editingModeIndex === -1) return "Default Settings";
        if (editingModeIndex >= 0 && editingModeIndex < customModesList.count) {
            return customModesList.get(editingModeIndex).modeName + " Settings";
        }
        return "Settings";
    }

    function getActive(prop) {
        if (editingModeIndex === -1) {
            if (prop === "preset") return selectedPreset;
            if (prop === "language") return selectedLanguage;
            if (prop === "model") return selectedVoiceModel;
        } else if (editingModeIndex >= 0 && editingModeIndex < customModesList.count) {
            var m = customModesList.get(editingModeIndex);
            if (prop === "preset") return m.modePreset;
            if (prop === "language") return m.modeLanguage;
            if (prop === "model") return m.modeVoiceModel;
        }
        return "";
    }

    function dropWidth(id) {
        var baseId = id.replace("modal_", "")
        if (baseId === "preset")     return 240
        if (baseId === "language")   return 220
        if (baseId === "voicemodel") return 260
        return 220
    }

    function openDrop(id, btn, dropH) {
        var btnGlobal = btn.mapToItem(modePageRoot, 0, 0)
        var spaceBelow = modePageRoot.height - (btnGlobal.y + btn.height) - 10
        var spaceAbove = btnGlobal.y - 10
        var xPos = btnGlobal.x + btn.width - dropWidth(id)
        var yPos = 0
        var finalH = dropH
        
        if (spaceBelow >= dropH) {
            yPos = btnGlobal.y + btn.height + 6
        } else if (spaceAbove >= dropH) {
            yPos = btnGlobal.y - dropH - 6
        } else {
            if (spaceBelow >= spaceAbove) {
                yPos = btnGlobal.y + btn.height + 6
                finalH = Math.max(100, spaceBelow - 6)
            } else {
                finalH = Math.max(100, spaceAbove - 6)
                yPos = btnGlobal.y - finalH - 6
            }
        }
        
        openDropdown = id
        dropdownRect = Qt.rect(xPos, yPos, dropWidth(id), finalH)
    }

    function getAvailableLanguages() {
        var activeVM = openDropdown === "modal_language" ? newModeVoiceModel : getActive("model");
        if (activeVM === "Local Distil-Whisper (EN)") return englishOnly;
        return languages;
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
                    var pt = self.mapToItem(modePageRoot, self.width, self.height / 2)
                    tooltipAnchor = Qt.point(pt.x, pt.y)
                    activeTooltip = self.tip 
                } 
            }
            onExited: { activeTooltip = "" }
        }
    }

    Rectangle {
        id: backgroundCapture
        anchors.fill: parent
        color: "#494c4d" 

        ScrollView {
            id: scrollView
            anchors.fill: parent
            clip: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            ScrollBar.vertical.policy: ScrollBar.AsNeeded
            Component.onCompleted: contentItem.boundsBehavior = Flickable.StopAtBounds

            Item {
                width: scrollView.availableWidth
                implicitHeight: mainColumn.implicitHeight + 40

                ColumnLayout {
                    id: mainColumn
                    width: Math.min(520, scrollView.availableWidth - 60)
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.top: parent.top
                    anchors.topMargin: 20
                    spacing: 20

                    // ── HEADER ──
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 6

                        Rectangle {
                            visible: showDetail
                            width: 26; height: 26; radius: 6
                            color: backHover.containsMouse ? "#6a6e70" : "#006a6e70"
                            Layout.alignment: Qt.AlignVCenter 
                            Behavior on color { ColorAnimation { duration: 100 } }
                            
                            Text { 
                                anchors.centerIn: parent; anchors.verticalCenterOffset: -2
                                text: "‹"; color: "white"; font.pixelSize: 22; font.weight: Font.Light 
                            }
                            MouseArea { 
                                id: backHover; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                onClicked: { 
                                    openDropdown = ""
                                    showDetail = false 
                                    editingModeIndex = -1
                                } 
                            }
                        }

                        Text { 
                            text: getHeaderTitle()
                            color: "white"; font.pixelSize: 14; font.bold: true
                            Layout.alignment: Qt.AlignVCenter 
                        }

                        InfoIcon { 
                            visible: !showDetail
                            tip: "Create custom modes so that Ozmoz perfectly matches your use case."
                            Layout.alignment: Qt.AlignVCenter 
                        }

                        Item { Layout.fillWidth: true; Layout.alignment: Qt.AlignVCenter } 

                        Rectangle {
                            visible: !showDetail
                            height: 28; implicitWidth: createLbl.implicitWidth + 20; radius: 6
                            color: createHover.containsMouse ? "#6a6e70" : "#55585a"
                            border.color: "#7e8385"; border.width: 1
                            Layout.alignment: Qt.AlignVCenter 
                            Layout.topMargin: 3 
                            Behavior on color { ColorAnimation { duration: 120 } }
                            
                            Text { 
                                id: createLbl; anchors.centerIn: parent
                                text: "+ Create mode"; color: "white"; font.pixelSize: 12 
                            }
                            MouseArea {
                                id: createHover; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    newModeName = ""
                                    showCreateModeModal = true
                                }
                            }
                        }
                    }

                    // ── DEFAULT MODE CARD ──
                    Rectangle {
                        visible: !showDetail
                        Layout.fillWidth: true; height: 52; color: "#55585a"; radius: 12; border.color: "#66696a"; border.width: 1

                        Rectangle { 
                            anchors.fill: parent; radius: parent.radius
                            color: cardHover.containsMouse ? "#10ffffff" : "transparent"
                            Behavior on color { ColorAnimation { duration: 110 } } 
                        }

                        MouseArea { 
                            id: cardHover; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                editingModeIndex = -1
                                showDetail = true 
                            }
                        }

                        RowLayout {
                            anchors.fill: parent; anchors.leftMargin: 14; anchors.rightMargin: 14; spacing: 10
                            
                            Item { 
                                width: 15; height: 15
                                Layout.alignment: Qt.AlignVCenter
                                Image { id: recImg; anchors.fill: parent; source: "icons/rec.svg"; fillMode: Image.PreserveAspectFit; smooth: true; layer.enabled: true }
                                ColorOverlay { anchors.fill: recImg; source: recImg; color: "white" } 
                            }
                            
                            Text { 
                                text: "Default"
                                color: "white"; font.pixelSize: 14; font.bold: true 
                                Layout.alignment: Qt.AlignVCenter
                            }

                            Rectangle {
                                width: 6; height: 6; radius: 3
                                color: "#34c759"
                                visible: activeModeIndex === -1
                                Layout.alignment: Qt.AlignVCenter
                                Layout.topMargin: 2
                            }
                            
                            Item { Layout.fillWidth: true } 

                            Rectangle {
                                width: 32; height: 28; radius: 6; color: "transparent"
                                Layout.alignment: Qt.AlignVCenter
                                Image { 
                                    id: defaultModeIcon
                                    anchors.centerIn: parent
                                    width: 20; height: 20
                                    sourceSize: Qt.size(40, 40)
                                    source: getVoiceModelIcon(selectedVoiceModel)
                                    fillMode: Image.PreserveAspectFit
                                    smooth: true; mipmap: true 
                                }
                                ColorOverlay {
                                    anchors.fill: defaultModeIcon
                                    source: defaultModeIcon
                                    color: "#909090"
                                    visible: selectedVoiceModel === "Select a model..."
                                }
                            }
                        }
                    }

                    // ── CUSTOM MODES LIST ──
                    ColumnLayout {
                        visible: !showDetail && customModesList.count > 0
                        Layout.fillWidth: true; spacing: 12; Layout.topMargin: 10

                        Text { text: "Your Modes"; color: "#909090"; font.pixelSize: 12; font.bold: true; Layout.leftMargin: 4 }

                        Repeater {
                            model: customModesList
                            delegate: Rectangle {
                                Layout.fillWidth: true; height: 52; color: "#55585a"; radius: 12; border.color: "#66696a"; border.width: 1

                                Rectangle { 
                                    anchors.fill: parent; radius: parent.radius
                                    color: cCardHover.containsMouse ? "#10ffffff" : "transparent"
                                    Behavior on color { ColorAnimation { duration: 110 } } 
                                }

                                MouseArea { 
                                    id: cCardHover; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        editingModeIndex = index
                                        showDetail = true 
                                    }
                                }

                                RowLayout {
                                    anchors.fill: parent; anchors.leftMargin: 14; anchors.rightMargin: 14; spacing: 10
                                    
                                    Item { 
                                        width: 15; height: 15
                                        Layout.alignment: Qt.AlignVCenter
                                        Image { id: cRecImg; anchors.fill: parent; source: "icons/rec.svg"; fillMode: Image.PreserveAspectFit; smooth: true; layer.enabled: true }
                                        ColorOverlay { anchors.fill: cRecImg; source: cRecImg; color: "white" } 
                                    }
                                    
                                    Text { 
                                        text: modeName
                                        color: "white"; font.pixelSize: 14; font.bold: true 
                                        Layout.alignment: Qt.AlignVCenter
                                    }

                                    Rectangle {
                                        width: 6; height: 6; radius: 3
                                        color: "#34c759"
                                        visible: activeModeIndex === index
                                        Layout.alignment: Qt.AlignVCenter
                                        Layout.topMargin: 2
                                    }
                                    
                                    Item { Layout.fillWidth: true } 

                                    Rectangle {
                                        width: 32; height: 28; radius: 6; color: "transparent"
                                        Layout.alignment: Qt.AlignVCenter
                                        Image { 
                                            anchors.centerIn: parent
                                            width: 20; height: 20
                                            sourceSize: Qt.size(40, 40)
                                            source: getVoiceModelIcon(modeVoiceModel)
                                            fillMode: Image.PreserveAspectFit
                                            smooth: true; mipmap: true 
                                        }
                                    }
                                }
                            }
                        }
                    }

                    // ── DETAIL VIEW ──
                    Rectangle {
                        visible: showDetail
                        Layout.fillWidth: true; color: "#55585a"; radius: 12; border.color: "#66696a"; border.width: 1
                        implicitHeight: detailCol.implicitHeight + 2

                        ColumnLayout {
                            id: detailCol; anchors.fill: parent; anchors.margins: 1; spacing: 0

                            Item {
                                height: 52
                                Layout.fillWidth: true
                                
                                RowLayout {
                                    anchors.fill: parent; anchors.leftMargin: 16; anchors.rightMargin: 16; spacing: 6
                                    Text { text: "Active Mode"; color: "white"; font.pixelSize: 14; font.bold: true }
                                    InfoIcon { tip: "Activate this mode to make it your current layout." }
                                    Item { Layout.fillWidth: true }
                                    
                                    ToggleSwitch {
                                        checked: editingModeIndex === -1 ? (activeModeIndex === -1) : (activeModeIndex === editingModeIndex)
                                        Layout.alignment: Qt.AlignVCenter
                                        onClicked: {
                                            if (editingModeIndex === -1) {
                                                if (!checked) {
                                                    activeModeIndex = -1
                                                    uiBridge.setActiveModeId("default")
                                                }
                                            } else {
                                                if (checked) {
                                                    activeModeIndex = -1
                                                    uiBridge.setActiveModeId("default")
                                                } else {
                                                    activeModeIndex = editingModeIndex
                                                    var mId = customModesList.get(editingModeIndex).id
                                                    uiBridge.setActiveModeId(mId)
                                                }
                                            }
                                        }
                                    }
                                }
                                Rectangle { anchors.bottom: parent.bottom; anchors.left: parent.left; anchors.right: parent.right; anchors.leftMargin: 16; anchors.rightMargin: 16; height: 1; color: "#66696a" }
                            }

                            Item {
                                height: 52; Layout.fillWidth: true
                                RowLayout {
                                    anchors.fill: parent; anchors.leftMargin: 16; anchors.rightMargin: 16; spacing: 6
                                    Text { text: "Preset"; color: "white"; font.pixelSize: 14; font.bold: true }
                                    InfoIcon { tip: "Select the type of task for which you want to use this mode" }
                                    Item { Layout.fillWidth: true }
                                    
                                    Rectangle {
                                        id: presetBtn
                                        height: 34; implicitWidth: 190; radius: 8
                                        color: presetHover.containsMouse || openDropdown === "preset" ? "#6a6e70" : "#64686a"
                                        border.color: openDropdown === "preset" ? "#5a9ef8" : "#7e8385"; border.width: 1
                                        
                                        RowLayout {
                                            anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 10; spacing: 8
                                            
                                            Item { 
                                                width: 18; height: 18; Layout.alignment: Qt.AlignVCenter
                                                Image { 
                                                    id: currentPresetIcon
                                                    width: 18; height: 18; anchors.centerIn: parent
                                                    source: getPresetIcon(getActive("preset"))
                                                    fillMode: Image.PreserveAspectFit; smooth: true; mipmap: true; layer.enabled: true 
                                                }
                                                ColorOverlay { anchors.fill: currentPresetIcon; source: currentPresetIcon; color: "white" } 
                                            }
                                            
                                            Text { text: getActive("preset"); color: "white"; font.pixelSize: 13; font.bold: true; Layout.fillWidth: true; elide: Text.ElideRight }
                                            Text { text: "\u25BE"; color: "#ccc"; font.pixelSize: 14; font.bold: true }
                                        }
                                        
                                        MouseArea {
                                            id: presetHover; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                            onClicked: openDropdown === "preset" ? openDropdown = "" : openDrop("preset", presetBtn, presets.length * 30 + 12) 
                                        }
                                    }
                                }
                                Rectangle { anchors.bottom: parent.bottom; anchors.left: parent.left; anchors.right: parent.right; anchors.leftMargin: 16; anchors.rightMargin: 16; height: 1; color: "#66696a" }
                            }

                            Item {
                                height: 52; Layout.fillWidth: true
                                RowLayout {
                                    anchors.fill: parent; anchors.leftMargin: 16; anchors.rightMargin: 16; spacing: 6
                                    Text { text: "Language"; color: "white"; font.pixelSize: 14; font.bold: true }
                                    Item { Layout.fillWidth: true }
                                    Rectangle {
                                        id: langBtn
                                        height: 34; implicitWidth: 190; radius: 8
                                        color: langHover.containsMouse || openDropdown === "language" ? "#6a6e70" : "#64686a"
                                        border.color: openDropdown === "language" ? "#5a9ef8" : "#7e8385"; border.width: 1
                                        RowLayout {
                                            anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 10
                                            Text { text: getActive("language"); color: "white"; font.pixelSize: 13; font.bold: true; Layout.fillWidth: true }
                                            Text { text: "\u25BE"; color: "#ccc"; font.pixelSize: 14; font.bold: true }
                                        }
                                        MouseArea {
                                            id: langHover; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                            onClicked: openDropdown === "language" ? openDropdown = "" : openDrop("language", langBtn, Math.min(getAvailableLanguages().length * 30 + 12, 350)) 
                                        }
                                    }
                                }
                                Rectangle { anchors.bottom: parent.bottom; anchors.left: parent.left; anchors.right: parent.right; anchors.leftMargin: 16; anchors.rightMargin: 16; height: 1; color: "#66696a" }
                            }

                            Item {
                                height: 52; Layout.fillWidth: true
                                RowLayout {
                                    anchors.fill: parent; anchors.leftMargin: 16; anchors.rightMargin: 16; spacing: 6
                                    Text { text: "Voice Model"; color: "white"; font.pixelSize: 14; font.bold: true }
                                    InfoIcon { tip: "Select the speech recognition model" }
                                    Item { Layout.fillWidth: true }
                                    Rectangle {
                                        id: voiceBtn
                                        height: 34; implicitWidth: 190; radius: 8
                                        color: voiceHover.containsMouse || openDropdown === "voicemodel" ? "#6a6e70" : "#64686a"
                                        border.color: openDropdown === "voicemodel" ? "#5a9ef8" : "#7e8385"; border.width: 1
                                        RowLayout {
                                            anchors.fill: parent; anchors.leftMargin: 8; anchors.rightMargin: 10; spacing: 6
                                            Item { 
                                                width: 16; height: 16
                                                Image { 
                                                    id: voiceModelSelectedIcon
                                                    anchors.centerIn: parent; width: 16; height: 16
                                                    sourceSize: Qt.size(40, 40)
                                                    source: getVoiceModelIcon(getActive("model"))
                                                    fillMode: Image.PreserveAspectFit; smooth: true; mipmap: true 
                                                }
                                                ColorOverlay {
                                                    anchors.fill: voiceModelSelectedIcon
                                                    source: voiceModelSelectedIcon
                                                    color: "white"
                                                    visible: getActive("model") === "Select a model..."
                                                }
                                            }
                                            Text { text: getActive("model"); color: "white"; font.pixelSize: 13; font.bold: true; Layout.fillWidth: true; elide: Text.ElideRight }
                                            Text { text: "\u25BE"; color: "#ccc"; font.pixelSize: 14; font.bold: true }
                                        }
                                        MouseArea {
                                            id: voiceHover; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                            onClicked: openDropdown === "voicemodel" ? openDropdown = "" : openDrop("voicemodel", voiceBtn, voiceModels.length * 30 + 12) 
                                        }
                                    }
                                }
                                Rectangle { visible: editingModeIndex !== -1; anchors.bottom: parent.bottom; anchors.left: parent.left; anchors.right: parent.right; anchors.leftMargin: 16; anchors.rightMargin: 16; height: 1; color: "#66696a" }
                            }

                            // ── DELETE ROW ──
                            Item {
                                visible: editingModeIndex !== -1
                                height: visible ? 52 : 0
                                Layout.fillWidth: true
                                RowLayout {
                                    anchors.fill: parent; anchors.leftMargin: 16; anchors.rightMargin: 16; spacing: 6
                                    Text { text: "Delete mode"; color: "white"; font.pixelSize: 14; font.bold: true }
                                    Item { Layout.fillWidth: true }
                                    Rectangle {
                                        height: 28; implicitWidth: 70; radius: 6
                                        color: delRowHover.containsMouse ? "#6a6e70" : "#64686a"
                                        border.color: "#7e8385"; border.width: 1
                                        Behavior on color { ColorAnimation { duration: 120 } }
                                        Text { anchors.centerIn: parent; text: "Delete"; color: "white"; font.pixelSize: 12 }
                                        MouseArea {
                                            id: delRowHover; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                            onClicked: showDeleteModeModal = true
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

    // ── CREATE MODE MODAL ──
    Item {
        id: createModeOverlay
        anchors.fill: parent; z: 150
        visible: opacity > 0; opacity: showCreateModeModal ? 1.0 : 0.0
        Behavior on opacity { NumberAnimation { duration: 250; easing.type: Easing.OutCubic } }
        TapHandler { onTapped: { showCreateModeModal = false; openDropdown = "" } }

        ShaderEffectSource { id: cmBlurSrc; anchors.fill: parent; sourceItem: backgroundCapture; visible: false }
        FastBlur { id: cmFirstBlur; anchors.fill: parent; source: cmBlurSrc; radius: 32 }
        ShaderEffectSource { id: cmMidCap; sourceItem: cmFirstBlur; hideSource: true; visible: false }
        FastBlur { anchors.fill: parent; source: cmMidCap; radius: 32; transparentBorder: false }
        Rectangle { anchors.fill: parent; color: Qt.rgba(0.12, 0.13, 0.14, 0.70) }

        Rectangle {
            anchors.centerIn: parent; width: 400; implicitHeight: modalCol.implicitHeight + 40
            radius: 12; color: "#494c4d"; border.color: "#66696a"; border.width: 1
            scale: showCreateModeModal ? 1.0 : 0.8
            Behavior on scale { NumberAnimation { duration: 250; easing.type: Easing.OutBack; easing.overshoot: 1.2 } }
            MouseArea { anchors.fill: parent; onClicked: openDropdown = "" }

            ColumnLayout {
                id: modalCol; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 20; spacing: 12
                Text { text: "Create New Mode"; color: "white"; font.pixelSize: 16; font.bold: true; Layout.alignment: Qt.AlignHCenter }

                ColumnLayout {
                    Layout.fillWidth: true; spacing: 5
                    Text { text: "Mode Name"; color: "#909090"; font.pixelSize: 12; font.bold: true }
                    Rectangle {
                        Layout.fillWidth: true; height: 36; radius: 6; color: "#3e4243"
                        border.color: modeNameInput.activeFocus ? "#5a9ef8" : "#6e7273"; border.width: 1
                        Behavior on border.color { ColorAnimation { duration: 150 } }
                        TextInput { 
                            id: modeNameInput; anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 10
                            color: "white"; font.pixelSize: 13; verticalAlignment: TextInput.AlignVCenter; selectionColor: "#4a90d9" 
                            text: newModeName
                            onTextEdited: newModeName = text
                        }
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true; spacing: 10
                    Layout.topMargin: 4 
                    
                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "Preset"; color: "white"; font.pixelSize: 13; font.bold: true }
                        Item { Layout.fillWidth: true }
                        Rectangle {
                            id: modalPresetBtn; width: 170; height: 32; radius: 6
                            color: mPresetHover.containsMouse || openDropdown === "modal_preset" ? "#6a6e70" : "#64686a"
                            border.color: openDropdown === "modal_preset" ? "#5a9ef8" : "#7e8385"; border.width: 1
                            RowLayout {
                                anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 10
                                Text { text: newModePreset; color: "white"; font.pixelSize: 12; font.bold: true; Layout.fillWidth: true }
                                Text { text: "\u25BE"; color: "#ccc"; font.pixelSize: 14; font.bold: true }
                            }
                            MouseArea {
                                id: mPresetHover; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                onClicked: openDropdown === "modal_preset" ? openDropdown = "" : openDrop("modal_preset", modalPresetBtn, presets.length * 30 + 12)
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "Language"; color: "white"; font.pixelSize: 13; font.bold: true }
                        Item { Layout.fillWidth: true }
                        Rectangle {
                            id: modalLangBtn; width: 170; height: 32; radius: 6
                            color: mLangHover.containsMouse || openDropdown === "modal_language" ? "#6a6e70" : "#64686a"
                            border.color: openDropdown === "modal_language" ? "#5a9ef8" : "#7e8385"; border.width: 1
                            RowLayout {
                                anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 10
                                Text { text: newModeLanguage; color: "white"; font.pixelSize: 12; font.bold: true; Layout.fillWidth: true; elide: Text.ElideRight }
                                Text { text: "\u25BE"; color: "#ccc"; font.pixelSize: 14; font.bold: true }
                            }
                            MouseArea {
                                id: mLangHover; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                onClicked: openDropdown === "modal_language" ? openDropdown = "" : openDrop("modal_language", modalLangBtn, Math.min(getAvailableLanguages().length * 30 + 12, 350))
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "Voice Model"; color: "white"; font.pixelSize: 13; font.bold: true }
                        Item { Layout.fillWidth: true }
                        Rectangle {
                            id: modalVoiceBtn; width: 170; height: 32; radius: 6
                            color: mVoiceHover.containsMouse || openDropdown === "modal_voicemodel" ? "#6a6e70" : "#64686a"
                            border.color: openDropdown === "modal_voicemodel" ? "#5a9ef8" : "#7e8385"; border.width: 1
                            RowLayout {
                                anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 10
                                Text { text: newModeVoiceModel; color: "white"; font.pixelSize: 12; font.bold: true; Layout.fillWidth: true; elide: Text.ElideRight }
                                Text { text: "\u25BE"; color: "#ccc"; font.pixelSize: 14; font.bold: true }
                            }
                            MouseArea {
                                id: mVoiceHover; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                onClicked: openDropdown === "modal_voicemodel" ? openDropdown = "" : openDrop("modal_voicemodel", modalVoiceBtn, voiceModels.length * 30 + 12)
                            }
                        }
                    }
                }

                Item { Layout.fillWidth: true; height: 4 } 

                RowLayout {
                    Layout.fillWidth: true; spacing: 12
                    Rectangle {
                        Layout.fillWidth: true; height: 36; radius: 8
                        color: cmCancelHover.containsMouse ? "#6a6e70" : "#55585a"; border.color: "#7e8385"; border.width: 1
                        Text { anchors.centerIn: parent; text: "Cancel"; color: "white"; font.pixelSize: 13; font.bold: true }
                        MouseArea { 
                            id: cmCancelHover; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                            onClicked: { showCreateModeModal = false; openDropdown = "" }
                        }
                    }
                    Rectangle {
                        Layout.fillWidth: true; height: 36; radius: 8
                        color: cmSaveHover.containsMouse ? "#2c5fc4" : "#2452a3"; border.color: "#3a73e6"; border.width: 1
                        opacity: newModeName.trim() === "" ? 0.5 : 1.0 
                        Text { anchors.centerIn: parent; text: "Create Mode"; color: "white"; font.pixelSize: 13; font.bold: true }
                        MouseArea { 
                            id: cmSaveHover; anchors.fill: parent; hoverEnabled: newModeName.trim() !== ""; cursorShape: hoverEnabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                            onClicked: {
                                if (newModeName.trim() === "") return;
                                var modeIdNew = "mode_" + new Date().getTime();
                                uiBridge.addCustomMode(modeIdNew, newModeName.trim(), newModePreset, newModeLanguage, newModeVoiceModel);
                                
                                showCreateModeModal = false
                                openDropdown = ""
                            }
                        }
                    }
                }
            }
        }
    }

    // ── DELETE MODE MODAL ──
    Item {
        id: deleteModeOverlay
        anchors.fill: parent; z: 160
        visible: opacity > 0; opacity: showDeleteModeModal ? 1.0 : 0.0
        Behavior on opacity { NumberAnimation { duration: 250; easing.type: Easing.OutCubic } }
        TapHandler { onTapped: showDeleteModeModal = false }

        ShaderEffectSource { id: delBlurSrc; anchors.fill: parent; sourceItem: backgroundCapture; visible: false }
        FastBlur { id: delFirstBlur; anchors.fill: parent; source: delBlurSrc; radius: 32 }
        ShaderEffectSource { id: delMidCap; sourceItem: delFirstBlur; hideSource: true; visible: false }
        FastBlur { anchors.fill: parent; source: delMidCap; radius: 32; transparentBorder: false }
        Rectangle { anchors.fill: parent; color: Qt.rgba(0.12, 0.13, 0.14, 0.65) }

        Rectangle {
            anchors.centerIn: parent
            width: 380
            height: 180
            radius: 12; color: "#494c4d"; border.color: "#66696a"; border.width: 1
            scale: showDeleteModeModal ? 1.0 : 0.8
            Behavior on scale { NumberAnimation { duration: 250; easing.type: Easing.OutBack; easing.overshoot: 1.2 } }
            MouseArea { anchors.fill: parent } 

            ColumnLayout {
                anchors.fill: parent; anchors.margins: 20; spacing: 10
                Text { text: "Delete Mode"; color: "white"; font.pixelSize: 16; font.bold: true; Layout.alignment: Qt.AlignHCenter }
                Text {
                    text: "Are you sure you want to delete this mode? This action cannot be undone."
                    color: "#b0b0b0"; font.pixelSize: 13; wrapMode: Text.WordWrap; horizontalAlignment: Text.AlignHCenter
                    Layout.fillWidth: true; Layout.topMargin: 10
                }
                Item { Layout.fillHeight: true }
                RowLayout {
                    Layout.fillWidth: true; Layout.alignment: Qt.AlignHCenter; spacing: 12
                    Rectangle {
                        implicitWidth: 100; height: 32; radius: 8
                        color: delCancelHover.containsMouse ? "#6a6e70" : "#55585a"; border.color: "#7e8385"; border.width: 1
                        Text { anchors.centerIn: parent; text: "Cancel"; color: "white"; font.pixelSize: 13; font.bold: true }
                        MouseArea { 
                            id: delCancelHover; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                            onClicked: showDeleteModeModal = false
                        }
                    }
                    Rectangle {
                        implicitWidth: 100; height: 32; radius: 8
                        color: delConfirmHover.containsMouse ? "#c93c3c" : "#a83232"; border.color: "#d64545"; border.width: 1
                        Text { anchors.centerIn: parent; text: "Delete"; color: "white"; font.pixelSize: 13; font.bold: true }
                       MouseArea { 
                            id: delConfirmHover; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                var modeIdDel = customModesList.get(editingModeIndex).id
                                uiBridge.removeCustomMode(modeIdDel)
                                
                                if (activeModeIndex === editingModeIndex) {
                                    activeModeIndex = -1; 
                                    uiBridge.setActiveModeId("default")
                                } else if (activeModeIndex > editingModeIndex) {
                                    activeModeIndex--; 
                                }
                                editingModeIndex = -1;
                                showDetail = false;
                                showDeleteModeModal = false;
                            }
                        }
                    }
                }
            }
        }
    }

    // ── DROPDOWN OVERLAY ──
    Item {
        id: overlay
        anchors.fill: parent; z: 200 
        visible: openDropdown !== ""
        MouseArea { anchors.fill: parent; onClicked: openDropdown = "" }

        Item {
            id: dropPanel
            x: dropdownRect.x; y: dropdownRect.y
            width: dropdownRect.width; height: dropdownRect.height
            layer.enabled: true; layer.effect: OpacityMask { maskSource: dropPanelMask }
            
            Rectangle { id: dropPanelMask; anchors.fill: parent; radius: 10; visible: false }
            
            ShaderEffectSource { 
                id: dropBlurSrc; anchors.fill: parent
                sourceItem: showCreateModeModal ? createModeOverlay : backgroundCapture
                sourceRect: Qt.rect(dropPanel.x, dropPanel.y, dropPanel.width, dropPanel.height); visible: false 
            }
            FastBlur { anchors.fill: parent; source: dropBlurSrc; radius: 64 }
            Rectangle { anchors.fill: parent; radius: 10; color: "#0A000000"; border.color: "#30FFFFFF"; border.width: 1 }

            ScrollView {
                anchors.fill: parent; clip: true
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                ScrollBar.vertical.policy: ScrollBar.AsNeeded
                Component.onCompleted: contentItem.boundsBehavior = Flickable.StopAtBounds

                ColumnLayout {
                    width: dropPanel.width; spacing: 0
                    
                    Item { height: 6; width: 1 }
                    
                    Repeater {
                        model: openDropdown.indexOf("preset") !== -1 ? presets : []
                        delegate: Item {
                            id: presetItem
                            width: dropPanel.width; height: 30 
                            property bool isAvailable: !modelData.requireKey || uiBridge.hasGroqKeyProp

                            Rectangle {
                                anchors.fill: parent
                                anchors.leftMargin: 8; anchors.rightMargin: 8; anchors.topMargin: 2; anchors.bottomMargin: 2
                                radius: 6 
                                color: {
                                    var activeVal = openDropdown === "modal_preset" ? newModePreset : getActive("preset");
                                    return activeVal === modelData.name ? "#2c5fc4" : (pHover.containsMouse ? (isAvailable ? "#20ffffff" : "#10ffffff") : "transparent");
                                }
                            }
                            RowLayout {
                                anchors.fill: parent; anchors.leftMargin: 18; anchors.rightMargin: 18; spacing: 10
                                Item { 
                                    width: 18; height: 18; Layout.alignment: Qt.AlignVCenter
                                    Image { 
                                        id: presetIcon
                                        width: 18; height: 18; anchors.centerIn: parent
                                        source: modelData.icon; fillMode: Image.PreserveAspectFit; smooth: true; mipmap: true; layer.enabled: true 
                                    }
                                    ColorOverlay { anchors.fill: presetIcon; source: presetIcon; color: "white"; opacity: isAvailable ? 1.0 : 0.5 } 
                                }
                                Text { 
                                    text: modelData.name; 
                                    color: isAvailable ? "white" : "#909090"; 
                                    font.pixelSize: 13; font.bold: true; Layout.fillWidth: true; Layout.alignment: Qt.AlignVCenter 
                                }
                            }
                            MouseArea { 
                                id: pHover; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                onEntered: {
                                    if (openDropdown === "preset") { 
                                        var pt = presetItem.mapToItem(overlay, 0, presetItem.height / 2)
                                        presetTipAnchor = Qt.point(pt.x, pt.y)
                                        presetTip = modelData.tip
                                    }
                                }
                                onExited: { if (presetTip === modelData.tip) presetTip = "" }
                                onClicked: { 
                                    if (!isAvailable) {
                                        modePageRoot.showEquationKeyModal = true
                                        openDropdown = ""
                                        return
                                    }
                                    if (openDropdown === "modal_preset") {
                                        newModePreset = modelData.name
                                    } else {
                                        if (editingModeIndex === -1) {
                                            uiBridge.setDefaultModePreset(modelData.name)
                                        } else {
                                            var modeIdP = customModesList.get(editingModeIndex).id
                                            uiBridge.updateCustomMode(modeIdP, "preset", modelData.name)
                                        }
                                        syncActiveModeToBackend() 
                                    }
                                    openDropdown = "" 
                                }
                            }
                        }
                    }
                    
                    Repeater {
                        model: openDropdown.indexOf("language") !== -1 ? getAvailableLanguages() : []
                        delegate: Item {
                            width: dropPanel.width; height: 30 
                            Rectangle {
                                anchors.fill: parent
                                anchors.leftMargin: 8; anchors.rightMargin: 8; anchors.topMargin: 2; anchors.bottomMargin: 2
                                radius: 6
                                color: {
                                    var activeVal = openDropdown === "modal_language" ? newModeLanguage : getActive("language");
                                    return activeVal === modelData ? "#2c5fc4" : lHover.containsMouse ? "#20ffffff" : "transparent";
                                }
                            }
                            Text { 
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.left: parent.left; anchors.leftMargin: 18 
                                text: modelData; color: "white"; font.pixelSize: 13; font.bold: true 
                            }
                            MouseArea { 
                                id: lHover; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                onClicked: { 
                                    if (openDropdown === "modal_language") {
                                        newModeLanguage = modelData
                                    } else {
                                        if (editingModeIndex === -1) {
                                            uiBridge.setDefaultModeLanguage(selectedLanguage = modelData)
                                        } else {
                                            var modeIdL = customModesList.get(editingModeIndex).id
                                            uiBridge.updateCustomMode(modeIdL, "language", modelData)
                                        }
                                        syncActiveModeToBackend()
                                    }
                                    openDropdown = "" 
                                } 
                            }
                        }
                    }
                    
                    Repeater {
                        model: openDropdown.indexOf("voicemodel") !== -1 ? voiceModels : []
                        delegate: Item {
                            id: voiceModelItem
                            width: dropPanel.width; height: 30 
                            property bool isAvailable: modelData.cloud ? uiBridge.hasGroqKeyProp : uiBridge.isLocalModelInstalled(modelData.name)
                            
                            Rectangle {
                                anchors.fill: parent
                                anchors.leftMargin: 8; anchors.rightMargin: 8; anchors.topMargin: 2; anchors.bottomMargin: 2
                                radius: 6
                                color: {
                                    var activeVal = openDropdown === "modal_voicemodel" ? newModeVoiceModel : getActive("model");
                                    return activeVal === modelData.name ? "#2c5fc4" : (vmHover.containsMouse ? (isAvailable ? "#20ffffff" : "#10ffffff") : "transparent");
                                }
                            }
                            RowLayout {
                                anchors.fill: parent; anchors.leftMargin: 16; anchors.rightMargin: 16; spacing: 10
                                Item { 
                                    width: 18; height: 18; Layout.alignment: Qt.AlignVCenter; 
                                    Image { width: 18; height: 18; anchors.centerIn: parent; source: modelData.icon; fillMode: Image.PreserveAspectFit; smooth: true; mipmap: true; opacity: isAvailable ? 1.0 : 0.5 } 
                                }
                                Text { 
                                    text: isAvailable ? modelData.name : (vmHover.containsMouse ? (modelData.cloud ? "Enter API Key \u2192" : "Download \u2193") : modelData.name)
                                    color: isAvailable ? "white" : (vmHover.containsMouse ? "#5a9ef8" : "#909090")
                                    font.pixelSize: 13; font.bold: true; Layout.fillWidth: true; Layout.alignment: Qt.AlignVCenter; elide: Text.ElideRight 
                                }
                            }
                            MouseArea { 
                                id: vmHover; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                onEntered: {
                                    if (openDropdown === "voicemodel") { 
                                        var pt = voiceModelItem.mapToItem(overlay, 0, voiceModelItem.height / 2)
                                        voiceModelTipAnchor = Qt.point(pt.x, pt.y)
                                        voiceModelTip = modelData.tip
                                    }
                                }
                                onExited: { if (voiceModelTip === modelData.tip) voiceModelTip = "" }
                                onClicked: { 
                                    if (!isAvailable) {
                                        modePageRoot.pendingModelSelectionContext = openDropdown
                                        if (modelData.cloud) {
                                            modePageRoot.showApiKeyModal = true
                                        } else {
                                            modelToDownload = modelData.name
                                            downloadStatus = "idle"
                                            modePageRoot.showDownloadModal = true
                                        }
                                        openDropdown = "" 
                                        return
                                    }

                                    if (modelData.name === "Local Distil-Whisper (EN)") {
                                        if (openDropdown === "modal_voicemodel") {
                                            newModeLanguage = "English"
                                        } else {
                                            if (editingModeIndex === -1) {
                                                uiBridge.setDefaultModeLanguage("English")
                                                selectedLanguage = "English"
                                            } else {
                                                customModesList.setProperty(editingModeIndex, "modeLanguage", "English")
                                            }
                                        }
                                    }

                                    if (openDropdown === "modal_voicemodel") {
                                        newModeVoiceModel = modelData.name
                                    } else {
                                        if (editingModeIndex === -1) {
                                            uiBridge.setDefaultModeVoiceModel(modelData.name)
                                        } else {
                                            var modeIdV = customModesList.get(editingModeIndex).id
                                            uiBridge.updateCustomMode(modeIdV, "voice_model", modelData.name)
                                        }
                                        syncActiveModeToBackend()
                                    }
                                    openDropdown = "" 
                                } 
                            }
                        }
                    }
                    
                    Item { height: 6; width: 1 } 
                }
            }
        } 

        // ── TOOLTIP (Preset Info) ──
        Item {
            id: presetTipBox
            visible: presetTip !== "" && openDropdown === "preset"
            x: Math.max(6, dropPanel.x - width - 8); y: Math.max(6, dropPanel.y)
            width: presetTipWidth + 24; height: Math.max(presetTipLabel.implicitHeight + 16, 60)
            layer.enabled: true; layer.effect: OpacityMask { maskSource: presetTipMask }
            Rectangle { id: presetTipMask; anchors.fill: parent; radius: 8; visible: false }
            ShaderEffectSource { 
                id: tipBlurSrc; anchors.fill: parent
                sourceItem: backgroundCapture
                sourceRect: Qt.rect(presetTipBox.x, presetTipBox.y, presetTipBox.width, presetTipBox.height); visible: false 
            }
            FastBlur { anchors.fill: parent; source: tipBlurSrc; radius: 70 }
            Rectangle { anchors.fill: parent; radius: 8; color: "#0A000000"; border.color: "#20FFFFFF"; border.width: 1 }
            
            scale: presetTip !== "" ? 1.0 : 0.85
            Behavior on scale { NumberAnimation { duration: 140; easing.type: Easing.OutBack; easing.overshoot: 1.3 } }
            opacity: presetTip !== "" ? 1.0 : 0.0
            Behavior on opacity { NumberAnimation { duration: 100 } }

            Text {
                id: presetTipLabel; anchors.fill: parent; anchors.margins: 10
                text: presetTip; color: "#ffffff"; font.pixelSize: 12; font.bold: true
                wrapMode: Text.WordWrap; horizontalAlignment: Text.AlignLeft; verticalAlignment: Text.AlignVCenter
            }
        } 

        // ── TOOLTIP (Voice Model Info) ──
        Item {
            id: voiceModelTipBox
            visible: voiceModelTip !== "" && openDropdown === "voicemodel"
            x: Math.max(6, dropPanel.x - width - 8); y: Math.max(6, dropPanel.y)
            width: voiceModelTipWidth + 24; implicitHeight: voiceModelTipLabel.implicitHeight + 24; height: Math.max(implicitHeight, 60)
            layer.enabled: true; layer.effect: OpacityMask { maskSource: voiceModelTipMask }
            Rectangle { id: voiceModelTipMask; anchors.fill: parent; radius: 8; visible: false }
            ShaderEffectSource { 
                id: vmTipBlurSrc; anchors.fill: parent
                sourceItem: showCreateModeModal ? createModeOverlay : backgroundCapture
                sourceRect: Qt.rect(voiceModelTipBox.x, voiceModelTipBox.y, voiceModelTipBox.width, voiceModelTipBox.height); visible: false 
            }
            FastBlur { anchors.fill: parent; source: vmTipBlurSrc; radius: 70 }
            Rectangle { anchors.fill: parent; radius: 8; color: "#0A000000"; border.color: "#20FFFFFF"; border.width: 1 }
            
            scale: voiceModelTip !== "" ? 1.0 : 0.85
            Behavior on scale { NumberAnimation { duration: 140; easing.type: Easing.OutBack; easing.overshoot: 1.3 } }
            opacity: voiceModelTip !== "" ? 1.0 : 0.0
            Behavior on opacity { NumberAnimation { duration: 100 } }

            Text {
                id: voiceModelTipLabel
                anchors { left: parent.left; leftMargin: 12; right: parent.right; rightMargin: 12; top: parent.top; topMargin: 12 }
                text: voiceModelTip; color: "#ffffff"; font.pixelSize: 12; font.bold: true
                wrapMode: Text.WordWrap; horizontalAlignment: Text.AlignLeft
            }
        } 
    } 

    // ── TOOLTIP OVERLAY ──
    Item {
        anchors.fill: parent
        z: 250; enabled: false; visible: activeTooltip !== ""

        Rectangle {
            id: tooltipRect
            transformOrigin: Item.TopLeft
            x: Math.max(6, Math.min(tooltipAnchor.x + 10, modePageRoot.width - width - 6))
            y: Math.max(6, tooltipAnchor.y - height / 2)
            width: Math.min(tipLabel.implicitWidth + 24, 260); height: tipLabel.implicitHeight + 14
            radius: 8; color: "#000000"

            scale: activeTooltip !== "" ? 1.0 : 0.75
            Behavior on scale { NumberAnimation { duration: 160; easing.type: Easing.OutBack; easing.overshoot: 1.4 } }
            opacity: activeTooltip !== "" ? 1.0 : 0.0
            Behavior on opacity { NumberAnimation { duration: 120 } }

            Text {
                id: tipLabel; anchors.centerIn: parent; width: parent.width - 24
                text: activeTooltip; color: "#d4d6d8"; font.pixelSize: 12; wrapMode: Text.WordWrap
            }
        }
    }

    // ── API KEY REQUIRED MODAL ──
    Item {
        id: apiKeyModalOverlay
        anchors.fill: parent; z: 300
        visible: opacity > 0; opacity: modePageRoot.showApiKeyModal ? 1.0 : 0.0
        Behavior on opacity { NumberAnimation { duration: 250; easing.type: Easing.OutCubic } }

        ShaderEffectSource { id: keyBlurSrc; anchors.fill: parent; sourceItem: backgroundCapture; visible: false }
        FastBlur { id: keyFirstBlur; anchors.fill: parent; source: keyBlurSrc; radius: 32 }
        ShaderEffectSource { id: keyMidCap; sourceItem: keyFirstBlur; hideSource: true; visible: false }
        FastBlur { anchors.fill: parent; source: keyMidCap; radius: 32; transparentBorder: false }
        Rectangle { anchors.fill: parent; color: Qt.rgba(0.12, 0.13, 0.14, 0.65) }

        Rectangle {
            anchors.centerIn: parent
            width: 380
            height: 180
            radius: 12; color: "#494c4d"; border.color: "#66696a"; border.width: 1
            scale: modePageRoot.showApiKeyModal ? 1.0 : 0.8
            Behavior on scale { NumberAnimation { duration: 250; easing.type: Easing.OutBack; easing.overshoot: 1.2 } }
            MouseArea { anchors.fill: parent } 

            ColumnLayout {
                anchors.fill: parent; anchors.margins: 20; spacing: 10
                Text { text: "API Key Required"; color: "white"; font.pixelSize: 16; font.bold: true; Layout.alignment: Qt.AlignHCenter }
                
                Text {
                    text: "To use cloud models like Whisper V3 Turbo, you need to provide a Groq API key in the settings."
                    color: "#b0b0b0"; font.pixelSize: 13; wrapMode: Text.WordWrap; horizontalAlignment: Text.AlignHCenter
                    Layout.fillWidth: true; Layout.topMargin: 10
                }

                Item { Layout.fillHeight: true }
                
                RowLayout {
                    Layout.fillWidth: true; Layout.alignment: Qt.AlignHCenter; spacing: 12
                    
                    Rectangle {
                        implicitWidth: 100; height: 32; radius: 8
                        color: keyCancelHover.containsMouse ? "#6a6e70" : "#55585a"; border.color: "#7e8385"; border.width: 1
                        Text { anchors.centerIn: parent; text: "Cancel"; color: "white"; font.pixelSize: 13; font.bold: true }
                        MouseArea { 
                            id: keyCancelHover; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                modePageRoot.showApiKeyModal = false
                                modePageRoot.pendingModelSelectionContext = ""
                            }
                        }
                    }

                    Rectangle {
                        implicitWidth: 120; height: 32; radius: 8
                        color: keyConfirmHover.containsMouse ? "#2c5fc4" : "#2452a3"; border.color: "#3a73e6"; border.width: 1
                        Text { anchors.centerIn: parent; text: "Enter API Key"; color: "white"; font.pixelSize: 13; font.bold: true }
                        MouseArea { 
                            id: keyConfirmHover; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                modePageRoot.showApiKeyModal = false
                                modePageRoot.pendingModelSelectionContext = ""
                                uiBridge.requestNavigateToConfig() 
                            }
                        }
                    }
                }
            }
        }
    }

    // ── DOWNLOAD MODEL MODAL ──
    Item {
        id: downloadModelOverlay
        anchors.fill: parent; z: 300
        visible: opacity > 0; opacity: modePageRoot.showDownloadModal ? 1.0 : 0.0
        Behavior on opacity { NumberAnimation { duration: 250; easing.type: Easing.OutCubic } }

        ShaderEffectSource { id: dlBlurSrc; anchors.fill: parent; sourceItem: backgroundCapture; visible: false }
        FastBlur { id: dlFirstBlur; anchors.fill: parent; source: dlBlurSrc; radius: 32 }
        ShaderEffectSource { id: dlMidCap; sourceItem: dlFirstBlur; hideSource: true; visible: false }
        FastBlur { anchors.fill: parent; source: dlMidCap; radius: 32; transparentBorder: false }
        Rectangle { anchors.fill: parent; color: Qt.rgba(0.12, 0.13, 0.14, 0.65) }

        Rectangle {
            anchors.centerIn: parent
            width: 380
            height: downloadStatus === "downloading" ? 190 : 180
            radius: 12; color: "#494c4d"; border.color: "#66696a"; border.width: 1
            scale: modePageRoot.showDownloadModal ? 1.0 : 0.8
            Behavior on scale { NumberAnimation { duration: 250; easing.type: Easing.OutBack; easing.overshoot: 1.2 } }
            Behavior on height { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
            MouseArea { anchors.fill: parent } 

            ColumnLayout {
                anchors.fill: parent; anchors.margins: 20; spacing: 10
                Text { text: "Download Required"; color: "white"; font.pixelSize: 16; font.bold: true; Layout.alignment: Qt.AlignHCenter }
                
                Text {
                    text: downloadStatus === "downloading" ? "Downloading " + modelToDownload + "...\nThis may take a few minutes." : "To use " + modelToDownload + " completely offline, you need to download it first. This is a one-time process."
                    color: "#b0b0b0"; font.pixelSize: 13; wrapMode: Text.WordWrap; horizontalAlignment: Text.AlignHCenter
                    Layout.fillWidth: true; Layout.topMargin: 10
                }

                Text {
                    visible: downloadStatus === "error"
                    text: "An error occurred. Check your connection."
                    color: "#ff4d4d"; font.pixelSize: 12; horizontalAlignment: Text.AlignHCenter
                    Layout.fillWidth: true
                }

                Rectangle {
                    visible: downloadStatus === "downloading"
                    Layout.fillWidth: true
                    height: 6
                    radius: 3
                    color: "#3e4243"
                    Layout.topMargin: 14 

                    Rectangle {
                        width: parent.width * downloadProgress
                        height: parent.height
                        radius: 3
                        color: "#5a9ef8"
                        Behavior on width { NumberAnimation { duration: 250; easing.type: Easing.OutCubic } }
                    }
                }
                
                Text {
                    visible: downloadStatus === "downloading"
                    text: Math.round(downloadProgress * 100) + "%"
                    color: "#5a9ef8"
                    font.pixelSize: 11
                    font.bold: true
                    Layout.alignment: Qt.AlignHCenter 
                    Layout.topMargin: 4 
                }

                Item { Layout.fillHeight: true }
                
                RowLayout {
                    Layout.fillWidth: true; Layout.alignment: Qt.AlignHCenter; spacing: 12
                    
                    Rectangle {
                        visible: downloadStatus !== "downloading"
                        implicitWidth: 100; height: 32; radius: 8
                        color: dlCancelHover.containsMouse ? "#6a6e70" : "#55585a"; border.color: "#7e8385"; border.width: 1
                        Text { anchors.centerIn: parent; text: "Cancel"; color: "white"; font.pixelSize: 13; font.bold: true }
                        MouseArea { 
                            id: dlCancelHover; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                modePageRoot.showDownloadModal = false
                                modePageRoot.pendingModelSelectionContext = ""
                            }
                        }
                    }

                    Rectangle {
                        visible: downloadStatus !== "downloading"
                        implicitWidth: 100; height: 32; radius: 8
                        color: dlConfirmHover.containsMouse ? "#2c5fc4" : "#2452a3"; border.color: "#3a73e6"; border.width: 1
                        Text { anchors.centerIn: parent; text: "Download"; color: "white"; font.pixelSize: 13; font.bold: true }
                        MouseArea { 
                            id: dlConfirmHover; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                            onClicked: uiBridge.downloadLocalModel(modelToDownload)
                        }
                    }
                }
            }
        }
    }
    // ── EQUATION API KEY REQUIRED MODAL ──
    Item {
        id: equationKeyModalOverlay
        anchors.fill: parent; z: 300
        visible: opacity > 0; opacity: modePageRoot.showEquationKeyModal ? 1.0 : 0.0
        Behavior on opacity { NumberAnimation { duration: 250; easing.type: Easing.OutCubic } }

        ShaderEffectSource { id: eqKeyBlurSrc; anchors.fill: parent; sourceItem: backgroundCapture; visible: false }
        FastBlur { id: eqKeyFirstBlur; anchors.fill: parent; source: eqKeyBlurSrc; radius: 32 }
        ShaderEffectSource { id: eqKeyMidCap; sourceItem: eqKeyFirstBlur; hideSource: true; visible: false }
        FastBlur { anchors.fill: parent; source: eqKeyMidCap; radius: 32; transparentBorder: false }
        Rectangle { anchors.fill: parent; color: Qt.rgba(0.12, 0.13, 0.14, 0.65) }

        Rectangle {
            anchors.centerIn: parent
            width: 380
            height: 180
            radius: 12; color: "#494c4d"; border.color: "#66696a"; border.width: 1
            scale: modePageRoot.showEquationKeyModal ? 1.0 : 0.8
            Behavior on scale { NumberAnimation { duration: 250; easing.type: Easing.OutBack; easing.overshoot: 1.2 } }
            MouseArea { anchors.fill: parent } 

            ColumnLayout {
                anchors.fill: parent; anchors.margins: 20; spacing: 10
                Text { text: "API Key Required"; color: "white"; font.pixelSize: 16; font.bold: true; Layout.alignment: Qt.AlignHCenter }
                
                Text {
                    text: "To use the Equation mode (LaTeX generation), you need to provide a Groq API key in the settings."
                    color: "#b0b0b0"; font.pixelSize: 13; wrapMode: Text.WordWrap; horizontalAlignment: Text.AlignHCenter
                    Layout.fillWidth: true; Layout.topMargin: 10
                }

                Item { Layout.fillHeight: true }
                
                RowLayout {
                    Layout.fillWidth: true; Layout.alignment: Qt.AlignHCenter; spacing: 12
                    
                    Rectangle {
                        implicitWidth: 100; height: 32; radius: 8
                        color: eqKeyCancelHover.containsMouse ? "#6a6e70" : "#55585a"; border.color: "#7e8385"; border.width: 1
                        Text { anchors.centerIn: parent; text: "Cancel"; color: "white"; font.pixelSize: 13; font.bold: true }
                        MouseArea { 
                            id: eqKeyCancelHover; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                modePageRoot.showEquationKeyModal = false
                            }
                        }
                    }

                    Rectangle {
                        implicitWidth: 120; height: 32; radius: 8
                        color: eqKeyConfirmHover.containsMouse ? "#2c5fc4" : "#2452a3"; border.color: "#3a73e6"; border.width: 1
                        Text { anchors.centerIn: parent; text: "Go to Settings"; color: "white"; font.pixelSize: 13; font.bold: true }
                        MouseArea { 
                            id: eqKeyConfirmHover; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                modePageRoot.showEquationKeyModal = false
                                uiBridge.requestNavigateToConfig() 
                            }
                        }
                    }
                }
            }
        }
    }
}