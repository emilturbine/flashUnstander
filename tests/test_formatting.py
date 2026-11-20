import os
from html import unescape

import pytest
from PySide6.QtWidgets import QApplication

from flashunstander.formatting import format_message


@pytest.fixture(scope="module", autouse=True)
def qt_application():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])


def test_markdown_and_common_latex_without_loading_external_resources():
    rendered = format_message(
        "# Result\n\n**Value**: $x_1^2 + \\frac{\\alpha}{\\sqrt{4}}$.\n\n"
        "![external](https://example.test/tracker.png) [link](https://example.test)"
    )
    assert "<h1" in rendered
    assert "Value" in rendered
    assert "x<sub>1</sub><sup>2</sup>" in rendered
    assert "<sup>α</sup>⁄<sub>√(4)</sub>" in rendered
    assert "https://example.test" not in rendered
    assert "<img" not in rendered


def test_standalone_and_fenced_json_are_prettified_without_changing_code():
    assert '  "answer": 42' in unescape(format_message('{"answer":42}'))
    rendered = format_message(
        'Example:\n\n```json\n{"answer":42}\n```\n\n'
        'A literal `$x_1$` and prose $y_2$.'
    )
    assert '"answer": 42' in unescape(rendered)
    assert "$x_1$" in rendered
    assert "y<sub>2</sub>" in rendered


def test_formula_text_cannot_inject_markup():
    rendered = format_message(r"$\text{<img src=x>}$")
    assert "<img" not in rendered
    assert "&lt;img" in rendered
