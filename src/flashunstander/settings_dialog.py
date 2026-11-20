"""Application settings shown from the central launcher."""

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QMessageBox, QSpinBox,
)

DEFAULT_CONTEXT_TOKENS = 100_000
DEFAULT_CONTEXT_TURNS = 20
DEFAULT_OUTPUT_TOKENS = 16_384


class SettingsDialog(QDialog):
    def __init__(self, runtime):
        super().__init__()
        self.runtime = runtime
        config = runtime.config
        self.setWindowTitle("flashUnstander 设置")
        form = QFormLayout(self)
        self.provider = QComboBox()
        self.provider.addItems(["deepseek", "openai"])
        self.provider.setCurrentText(config["provider"])
        self.model = QLineEdit(config["model"])
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText("留空保留该服务商已保存的密钥")
        form.addRow("服务商", self.provider)
        form.addRow("模型", self.model)
        form.addRow("API Key", self.key)
        self.context = self._spin(form, "上下文输入 token", 1_000, 100_000, config["context_tokens"], 1_000)
        self.turns = self._spin(form, "历史问答轮数", 0, 200, config["context_turns"], 1)
        self.output = self._spin(form, "单次回答 max tokens", 256, 32_768, config["max_output_tokens"], 1_024)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    @staticmethod
    def _spin(form, label, minimum, maximum, value, step):
        field = QSpinBox()
        field.setRange(minimum, maximum)
        field.setSingleStep(step)
        field.setValue(value)
        form.addRow(label, field)
        return field

    def _save(self):
        try:
            self.runtime.save_settings(
                self.provider.currentText(), self.model.text(), self.key.text(),
                self.context.value(), self.turns.value(), self.output.value(),
            )
        except Exception as exc:
            QMessageBox.warning(self, "设置未保存", str(exc))
            return
        self.accept()
