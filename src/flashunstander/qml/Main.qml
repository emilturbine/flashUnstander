import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs

ApplicationWindow {
    id: window
    width: 420
    height: 500
    minimumWidth: 320
    minimumHeight: 240
    title: "flashUnstander"
    flags: Qt.Window | Qt.FramelessWindowHint
    property bool lightTheme: false
    property color foreground: lightTheme ? "#182334" : "#edf1f8"
    property color surface: lightTheme ? "#ffffff" : "#171b24"
    property color muted: lightTheme ? "#516078" : "#aebbd0"
    color: lightTheme ? "#e9edf4" : "#0d0f14"
    property string imagePath: ""
    signal newWindowRequested()
    onClosing: function(close) { close.accepted = false; window.hide() }

    ListModel { id: messageModel }

    function syncMessages() {
        const rows = bridge.messages
        const followBottom = answers.contentItem.atYEnd
            || answers.contentItem.contentHeight - answers.contentItem.height - answers.contentItem.contentY <= 24
        answers.followBottomOnChange = followBottom
        if (messageModel.count > rows.length)
            messageModel.remove(rows.length, messageModel.count - rows.length)
        for (let i = 0; i < rows.length; ++i) {
            const row = {
                senderRole: rows[i].role || "",
                body: rows[i].text || "",
                richBody: rows[i].formatted || "",
                trace: rows[i].process || "",
                messageStatus: rows[i].status || ""
            }
            if (i === messageModel.count) {
                messageModel.append(row)
            } else {
                const previous = messageModel.get(i)
                for (const key of Object.keys(row))
                    if (previous[key] !== row[key])
                        messageModel.setProperty(i, key, row[key])
            }
        }
        if (followBottom)
            Qt.callLater(answers.scrollToBottom)
    }

    Component.onCompleted: syncMessages()
    Connections {
        target: bridge
        function onMessagesChanged() { window.syncMessages() }
    }

    function submitPrompt() {
        if (bridge.send(prompt.text, window.imagePath)) {
            prompt.clear()
            window.imagePath = ""
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
            Layout.fillWidth: true
            Layout.fillHeight: false
            Label {
                text: "flashUnstander"
                color: window.foreground
                font.pixelSize: 16
                font.bold: true
                elide: Text.ElideRight
                Layout.fillWidth: true
                verticalAlignment: Text.AlignVCenter
                MouseArea {
                    objectName: "windowDragRegion"
                    anchors.fill: parent
                    onPressed: window.startSystemMove()
                }
            }
            Button { text: "+"; visible: false; onClicked: window.newWindowRequested() }
            Button { text: window.lightTheme ? "深色" : "浅色"; onClicked: window.lightTheme = !window.lightTheme }
            Button { text: "─"; Accessible.name: "最小化"; onClicked: window.showMinimized() }
            Button { text: "×"; Accessible.name: "关闭"; onClicked: window.close() }
        }
        ScrollView {
            id: answers
            objectName: "answerScroll"
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            contentWidth: availableWidth
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            property bool followBottomOnChange: true

            function scrollToBottom() {
                contentItem.contentY = Math.max(0, contentItem.contentHeight - contentItem.height)
            }

            Column {
                width: answers.availableWidth
                spacing: 7
                onImplicitHeightChanged: {
                    if (answers.followBottomOnChange)
                        Qt.callLater(answers.scrollToBottom)
                }
                Repeater {
                    model: messageModel
                    delegate: Item {
                        id: message
                        required property string senderRole
                        required property string body
                        required property string richBody
                        required property string trace
                        required property string messageStatus
                        property bool expanded: false
                        readonly property bool fromUser: senderRole === "user"
                        width: answers.availableWidth
                        height: bubble.height

                        Rectangle {
                            id: bubble
                            anchors.right: message.fromUser ? parent.right : undefined
                            anchors.left: message.fromUser ? undefined : parent.left
                            width: parent.width * 0.85
                            height: bubbleContent.implicitHeight + 14
                            color: message.fromUser ? (window.lightTheme ? "#dce9ff" : "#333029") : window.surface
                            radius: 8

                            ColumnLayout {
                                id: bubbleContent
                                x: 8
                                y: 7
                                width: bubble.width - 16
                                spacing: 3
                                Label {
                                    text: message.fromUser ? "你" : "助手"
                                    color: window.muted
                                    font.pixelSize: 11
                                }
                                ToolButton {
                                    visible: !message.fromUser && message.trace !== ""
                                    text: message.expanded ? "▾ 思考和搜索过程" : "▸ 思考和搜索过程"
                                    onClicked: {
                                        answers.followBottomOnChange = false
                                        message.expanded = !message.expanded
                                    }
                                }
                                TextArea {
                                    objectName: "processDetails"
                                    visible: !message.fromUser && message.expanded && message.trace !== ""
                                    Layout.fillWidth: true
                                    text: message.trace
                                    textFormat: TextEdit.PlainText
                                    readOnly: true
                                    selectByMouse: true
                                    wrapMode: TextEdit.Wrap
                                    color: window.muted
                                    padding: 0
                                    background: null
                                }
                                TextArea {
                                    visible: text !== ""
                                    Layout.fillWidth: true
                                    text: !message.fromUser && message.richBody ? message.richBody : message.body
                                    textFormat: !message.fromUser && message.richBody ? TextEdit.RichText : TextEdit.PlainText
                                    readOnly: true
                                    selectByMouse: true
                                    wrapMode: TextEdit.Wrap
                                    color: window.foreground
                                    padding: 0
                                    background: null
                                }
                                Label {
                                    visible: text !== ""
                                    text: ({
                                        queued: "排队中",
                                        streaming: "生成中",
                                        truncated: "已达输出上限",
                                        failed: "请求失败",
                                        cancelled: "已停止"
                                    })[message.messageStatus] || ""
                                    color: window.muted
                                    font.pixelSize: 11
                                }
                            }
                        }
                    }
                }
            }
        }
        Label { visible: window.imagePath !== ""; text: "已选择图片"; color: window.muted }
        ScrollView {
            id: promptScroll
            objectName: "promptScroll"
            Layout.fillWidth: true
            Layout.preferredHeight: 34
            Layout.minimumHeight: 34
            Layout.maximumHeight: 34
            clip: true
            contentWidth: availableWidth
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            function showCaret() {
                const view = contentItem
                const caret = prompt.cursorRectangle
                const bottom = caret.y + caret.height + 2
                const target = caret.y < view.contentY ? caret.y
                    : bottom > view.contentY + view.height ? bottom - view.height : view.contentY
                view.contentY = Math.max(0, Math.min(target, view.contentHeight - view.height))
            }
            TextArea {
                id: prompt
                objectName: "prompt"
                placeholderText: "输入问题…"
                wrapMode: TextEdit.Wrap
                color: window.foreground
                placeholderTextColor: "#8290a5"
                background: Rectangle { color: window.surface; radius: 8 }
                onCursorRectangleChanged: Qt.callLater(promptScroll.showCaret)
                Keys.onReturnPressed: function(event) {
                    if (!event.isAutoRepeat && !prompt.inputMethodComposing && !(event.modifiers & Qt.ShiftModifier) && !bridge.busy && (prompt.text.trim() !== "" || window.imagePath !== "")) {
                        window.submitPrompt()
                        event.accepted = true
                    }
                }
            }
        }
        RowLayout {
            ToolButton {
                text: window.imagePath === "" ? "图片" : "移除图片"
                enabled: !bridge.busy
                onClicked: {
                    if (window.imagePath === "")
                        imageDialog.open()
                    else
                        window.imagePath = ""
                }
            }
            ToolButton {
                text: "思考"
                checkable: true
                checked: bridge.thinkingEnabled
                enabled: bridge.thinkingAvailable && !bridge.busy
                onClicked: bridge.setThinking(checked)
            }
            ToolButton {
                text: "搜索"
                checkable: true
                checked: bridge.searchEnabled
                enabled: bridge.searchAvailable && !bridge.busy
                onClicked: bridge.setSearch(checked)
            }
            Item { Layout.fillWidth: true }
            Button { text: "停止"; visible: bridge.busy; onClicked: bridge.stop() }
            Button { text: "发送"; enabled: !bridge.busy && (prompt.text.trim() !== "" || window.imagePath !== ""); onClicked: window.submitPrompt() }
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
