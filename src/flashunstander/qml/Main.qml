import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs

ApplicationWindow {
    id: window
    visible: true
    width: 520
    height: 640
    minimumWidth: 360
    minimumHeight: 420
    title: "flashUnstander"
    flags: Qt.Window | Qt.WindowStaysOnTopHint
    property bool lightTheme: false
    property color foreground: lightTheme ? "#182334" : "#edf1f8"
    property color surface: lightTheme ? "#ffffff" : "#222937"
    property color muted: lightTheme ? "#516078" : "#aebbd0"
    color: lightTheme ? "#e9edf4" : "#171b24"
    property string imagePath: ""
    signal newWindowRequested()
    onClosing: function(close) { close.accepted = false; window.hide() }
    Shortcut { sequence: "Ctrl+N"; onActivated: window.newWindowRequested() }
    Shortcut { sequence: "Escape"; onActivated: window.hide() }

    Dialog {
        id: settingsDialog
        title: "模型设置"
        modal: true
        anchors.centerIn: parent
        standardButtons: Dialog.Save | Dialog.Cancel
        onOpened: {
            providerBox.currentIndex = bridge.provider === "openai" ? 1 : 0
            modelInput.text = bridge.model
            keyInput.text = ""
        }
        onAccepted: { bridge.saveSettings(providerBox.currentText, modelInput.text, keyInput.text); bridge.changeHotkey(hotkeyBox.currentText) }
        contentItem: ColumnLayout {
            Label { text: "服务商" }
            ComboBox { id: providerBox; model: ["deepseek", "openai"]; Layout.fillWidth: true }
            Label { text: "模型名称" }
            TextField { id: modelInput; Layout.fillWidth: true }
            Label { text: "API Key（留空保留已保存的密钥）" }
            TextField { id: keyInput; echoMode: TextInput.Password; Layout.fillWidth: true }
            Label { text: "全局快捷键" }
            ComboBox { id: hotkeyBox; model: ["Alt+Space", "Ctrl+Alt+Space", "Ctrl+Shift+Space"]; currentIndex: Math.max(0, model.indexOf(bridge.hotkey)); Layout.fillWidth: true }
        }
    }

    FileDialog {
        id: imageDialog
        title: "选择图片"
        nameFilters: ["图片 (*.png *.jpg *.jpeg *.webp *.gif)"]
        onAccepted: window.imagePath = selectedFile.toString()
    }
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 16
        spacing: 10
        RowLayout {
            Label { text: "flashUnstander"; color: window.foreground; font.pixelSize: 19; font.bold: true; Layout.fillWidth: true }
            Button { text: "+"; onClicked: window.newWindowRequested() }
            Button { text: window.lightTheme ? "深色" : "浅色"; onClicked: window.lightTheme = !window.lightTheme }
            Button { text: "设置"; enabled: !bridge.busy; onClicked: { bridge.openSettings(); settingsDialog.open() } }
        }
        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            TextArea {
                text: bridge.answer
                readOnly: true
                selectByMouse: true
                wrapMode: TextEdit.Wrap
                color: window.foreground
                background: Rectangle { color: window.surface; radius: 10 }
            }
        }
        Label { visible: window.imagePath !== ""; text: "已选择图片"; color: window.muted }
        TextArea {
            id: prompt
            Layout.fillWidth: true
            Layout.preferredHeight: 100
            placeholderText: "输入问题…"
            wrapMode: TextEdit.Wrap
            color: window.foreground
            placeholderTextColor: "#8290a5"
            background: Rectangle { color: window.surface; radius: 10 }
            Keys.onReturnPressed: function(event) {
                if (!event.isAutoRepeat && !prompt.inputMethodComposing && !(event.modifiers & Qt.ShiftModifier) && !bridge.busy && (prompt.text.trim() !== "" || window.imagePath !== "")) {
                    if (bridge.send(prompt.text, window.imagePath)) {
                        prompt.clear()
                        window.imagePath = ""
                    }
                    event.accepted = true
                }
            }
        }
        RowLayout {
            Button { text: "添加图片"; enabled: !bridge.busy; onClicked: imageDialog.open() }
            Button { text: "移除图片"; visible: window.imagePath !== ""; onClicked: window.imagePath = "" }
            Item { Layout.fillWidth: true }
            Button { text: "停止"; visible: bridge.busy; onClicked: bridge.stop() }
            Button { text: "发送"; enabled: !bridge.busy && (prompt.text.trim() !== "" || window.imagePath !== ""); onClicked: { if (bridge.send(prompt.text, window.imagePath)) { prompt.clear(); window.imagePath = "" } } }
        }
        Label { text: bridge.status + (bridge.metrics ? "  ·  " + bridge.metrics : ""); color: window.muted; Layout.fillWidth: true; elide: Text.ElideRight }
    }
}
