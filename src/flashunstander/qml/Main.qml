import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs

ApplicationWindow {
    id: window
    width: 360
    height: 320
    minimumWidth: 320
    minimumHeight: 240
    title: "flashUnstander"
    flags: Qt.Window | Qt.FramelessWindowHint
    property bool lightTheme: false
    property color foreground: lightTheme ? "#182334" : "#edf1f8"
    property color surface: lightTheme ? "#ffffff" : "#222937"
    property color muted: lightTheme ? "#516078" : "#aebbd0"
    color: lightTheme ? "#e9edf4" : "#171b24"
    property string imagePath: ""
    signal newWindowRequested()
    onClosing: function(close) { close.accepted = false; window.hide() }

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
        onAccepted: bridge.saveSettings(providerBox.currentText, modelInput.text, keyInput.text)
        contentItem: ColumnLayout {
            Label { text: "服务商" }
            ComboBox { id: providerBox; model: ["deepseek", "openai"]; Layout.fillWidth: true }
            Label { text: "模型名称" }
            TextField { id: modelInput; Layout.fillWidth: true }
            Label { text: "API Key（留空保留已保存的密钥）" }
            TextField { id: keyInput; echoMode: TextInput.Password; Layout.fillWidth: true }
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
        anchors.margins: 10
        spacing: 6
        RowLayout {
            Label {
                text: "flashUnstander"
                color: window.foreground
                font.pixelSize: 16
                font.bold: true
                elide: Text.ElideRight
                Layout.fillWidth: true
                Layout.fillHeight: true
                verticalAlignment: Text.AlignVCenter
                MouseArea {
                    objectName: "windowDragRegion"
                    anchors.fill: parent
                    onPressed: window.startSystemMove()
                }
            }
            Button { text: "+"; onClicked: window.newWindowRequested() }
            Button { text: window.lightTheme ? "深色" : "浅色"; onClicked: window.lightTheme = !window.lightTheme }
            Button { text: "设置"; enabled: !bridge.busy; onClicked: { bridge.openSettings(); settingsDialog.open() } }
            Button { text: "─"; Accessible.name: "最小化"; onClicked: window.showMinimized() }
            Button { text: "×"; Accessible.name: "关闭"; onClicked: window.close() }
        }
        ScrollView {
            objectName: "answerScroll"
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            contentWidth: availableWidth
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            TextArea {
                text: bridge.answer
                textFormat: TextEdit.PlainText
                readOnly: true
                selectByMouse: true
                wrapMode: TextEdit.Wrap
                color: window.foreground
                background: Rectangle { color: window.surface; radius: 10 }
            }
        }
        Label { visible: window.imagePath !== ""; text: "已选择图片"; color: window.muted }
        ScrollView {
            objectName: "promptScroll"
            Layout.fillWidth: true
            Layout.preferredHeight: 34
            Layout.minimumHeight: 34
            Layout.maximumHeight: 34
            clip: true
            contentWidth: availableWidth
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            TextArea {
                id: prompt
                objectName: "prompt"
                placeholderText: "输入问题…"
                wrapMode: TextEdit.Wrap
                color: window.foreground
                placeholderTextColor: "#8290a5"
                background: Rectangle { color: window.surface; radius: 8 }
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

    // Only the inner five pixels handle resizing; the surrounding desktop keeps its clicks.
    Repeater {
        model: [
            [-1, -1, Qt.LeftEdge | Qt.TopEdge, Qt.SizeFDiagCursor],
            [0, -1, Qt.TopEdge, Qt.SizeVerCursor],
            [1, -1, Qt.RightEdge | Qt.TopEdge, Qt.SizeBDiagCursor],
            [-1, 0, Qt.LeftEdge, Qt.SizeHorCursor],
            [1, 0, Qt.RightEdge, Qt.SizeHorCursor],
            [-1, 1, Qt.LeftEdge | Qt.BottomEdge, Qt.SizeBDiagCursor],
            [0, 1, Qt.BottomEdge, Qt.SizeVerCursor],
            [1, 1, Qt.RightEdge | Qt.BottomEdge, Qt.SizeFDiagCursor]
        ]
        MouseArea {
            required property var modelData
            readonly property int rim: 5
            objectName: "windowResizeRegion"
            z: 10
            x: modelData[0] === 1 ? window.width - rim : modelData[0] === 0 ? rim : 0
            y: modelData[1] === 1 ? window.height - rim : modelData[1] === 0 ? rim : 0
            width: modelData[0] === 0 ? window.width - 2 * rim : rim
            height: modelData[1] === 0 ? window.height - 2 * rim : rim
            cursorShape: modelData[3]
            onPressed: window.startSystemResize(modelData[2])
        }
    }
}
