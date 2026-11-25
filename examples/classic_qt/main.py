"""Run the classic Qt interface on the current conversation backend."""
from pathlib import Path

from flashunstander.app import main

from control_ball import ControlBall


if __name__ == "__main__":
    raise SystemExit(main(
        launcher_class=ControlBall,
        qml_path=Path(__file__).with_name("Main.qml"),
        data_name="flashUnstander-classic-example",
    ))
