"""Verify the normal desktop exit releases the instance lock and history file."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PySide6.QtCore import QLockFile, QTimer
from PySide6.QtWidgets import QApplication

from flashunstander import app


def main():
    with TemporaryDirectory() as temp:
        directory = Path(temp) / "flashUnstander"
        lock_path = directory / "application.lock"
        original_exec = QApplication.exec

        def quit_normally(application):
            contender = QLockFile(str(lock_path))
            assert not contender.tryLock(0), "A second instance must be blocked while running"
            QTimer.singleShot(0, application.quit)
            return original_exec()

        with (
            patch.dict("os.environ", LOCALAPPDATA=temp),
            patch.object(QApplication, "exec", quit_normally),
            patch.object(app.DesktopIntegration, "register_hotkey", return_value=False),
        ):
            assert app.main() == 0

        assert not lock_path.exists(), "Normal exit must remove the instance lock"
        contender = QLockFile(str(lock_path))
        assert contender.tryLock(0), "A new instance must acquire the lock after exit"
        contender.unlock()
        # Windows refuses to remove an SQLite file with an open database handle.
        (directory / "history.db").unlink()
    print("Normal exit released the instance lock and SQLite handles.")


if __name__ == "__main__":
    main()
