"""Offline Markdown, JSON and basic LaTeX formatting for Qt rich text."""

import html
import json
import re
from html.parser import HTMLParser
from uuid import uuid4

from PySide6.QtGui import QTextDocument


# Preserve code before looking for math delimiters, even in an unfinished stream.
_CODE = re.compile(r"(?ms)^(?P<fence>`{3,}|~{3,})[ \t]*(?P<info>[^\n]*)\n"
                   r"(?P<code>.*?)(?=^(?P=fence)[ \t]*(?:\n|$)|\Z)"
                   r"(?:(?P=fence)[ \t]*(?=\n|$))?"
                   r"|(?P<ticks>`+)[^\n]*?(?P=ticks)")
_MATH = re.compile(r"(?s)(?<!\\)(?:\$\$(.+?)\$\$|\\\[(.+?)\\\]|"
                   r"\\\((.+?)\\\)|\$(?![\s$])([^\n$]+?)(?<!\s)\$(?![\d$]))")
_COMMAND = re.compile(r"\\([A-Za-z]+|.)")
_SYMBOLS = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
    "theta": "θ", "lambda": "λ", "mu": "μ", "pi": "π", "rho": "ρ",
    "sigma": "σ", "tau": "τ", "phi": "φ", "psi": "ψ", "omega": "ω",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Pi": "Π",
    "Sigma": "Σ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω", "infty": "∞",
    "times": "×", "cdot": "·", "pm": "±", "mp": "∓", "le": "≤", "leq": "≤",
    "ge": "≥", "geq": "≥", "neq": "≠", "approx": "≈", "equiv": "≡",
    "to": "→", "rightarrow": "→", "leftarrow": "←", "Rightarrow": "⇒",
    "sum": "∑", "prod": "∏", "int": "∫", "partial": "∂", "nabla": "∇",
    "in": "∈", "notin": "∉", "forall": "∀", "exists": "∃", "ldots": "…",
    "quad": "\u2003", "qquad": "\u2003\u2003", ",": "\u2009", "!": "",
    "left": "", "right": "", "{": "{", "}": "}", "%": "%", "$": "$", "_": "_",
}


def _latex(source):
    """Render common notation as selectable inline HTML, preserving unknown commands."""
    position = 0

    def argument(depth):
        nonlocal position
        while position < len(source) and source[position].isspace():
            position += 1
        return atom(depth + 1)

    def atom(depth):
        nonlocal position
        if position >= len(source):
            return ""
        if depth >= 24:
            raise ValueError("formula nesting too deep")
        char = source[position]
        position += 1
        if char == "{":
            parts = []
            while position < len(source) and source[position] != "}":
                parts.append(atom(depth + 1))
            if position < len(source):
                position += 1
            return "".join(parts)
        if char in "_^":
            tag = "sub" if char == "_" else "sup"
            return f"<{tag}>{argument(depth)}</{tag}>"
        if char == "\\" and (command := _COMMAND.match(source, position - 1)):
            name = command[1]
            position = command.end()
            if name in {"frac", "dfrac", "tfrac"}:
                return f"<sup>{argument(depth)}</sup>⁄<sub>{argument(depth)}</sub>"
            if name == "sqrt":
                return f"√({argument(depth)})"
            if name in {"text", "mathrm", "mathbf", "mathit"}:
                value = argument(depth)
                if name in {"mathbf", "mathit"}:
                    tag = "b" if name == "mathbf" else "i"
                    return f"<{tag}>{value}</{tag}>"
                return value
            return html.escape(_SYMBOLS.get(name, command[0]))
        return html.escape(char)

    try:
        parts = []
        while position < len(source):
            parts.append(atom(0))
        return "".join(parts)
    except ValueError:
        return html.escape(source)


def _pretty_json(text):
    try:
        return json.dumps(json.loads(text), ensure_ascii=False, indent=2)
    except (ValueError, RecursionError):
        return None


class _RichBody(HTMLParser):
    """Keep only Qt text markup, discarding links and external image resources."""

    _tags = frozenset(
        "p div span h1 h2 h3 h4 h5 h6 pre code blockquote br hr ul ol li table "
        "tr th td thead tbody b strong i em u s strike sub sup tt".split()
    )

    def __init__(self):
        super().__init__()
        self.parts = []
        self.body = False

    def handle_starttag(self, tag, attrs):
        if tag == "body":
            self.body = True
        if self.body and tag in self._tags:
            # Qt adds its own formatting styles. Drop resource-bearing styles.
            kept = "".join(
                f' {key}="{html.escape(value, quote=True)}"'
                for key, value in attrs
                if value and key in {"style", "align", "colspan", "rowspan"}
                and not re.search(r"url\s*\(|@import", value, re.IGNORECASE)
            )
            self.parts.append(f"<{tag}{kept}>")

    def handle_endtag(self, tag):
        if tag == "body":
            self.body = False
        if self.body and tag in self._tags and tag not in {"br", "hr"}:
            self.parts.append(f"</{tag}>")

    def handle_data(self, data):
        if self.body:
            self.parts.append(html.escape(data, quote=False))


class _LocalMarkdown(QTextDocument):
    def loadResource(self, resource_type, url):
        # Model output may contain images or file URLs. Rendering is text-only.
        return None


def format_message(text: str) -> str:
    """Return sanitized Qt RichText HTML. Call on the Qt GUI thread."""
    if not text:
        return ""
    cleaned = text.strip()
    if cleaned.startswith(("{", "[")) and (value := _pretty_json(cleaned)) is not None:
        code = html.escape(value)
        return f'<pre style="white-space:pre-wrap; font-family:monospace;">{code}</pre>'

    marker = f"FU{uuid4().hex}MATH"
    replacements = {}

    def replace_math(match):
        source = next(group for group in match.groups() if group is not None)
        token = f"{marker}{len(replacements)}X"
        replacements[token] = _latex(source)
        return token

    fragments = []
    cursor = 0
    for match in _CODE.finditer(text):
        fragments.append(_MATH.sub(replace_math, text[cursor:match.start()]))
        code = match[0]
        if match["info"] and match["info"].strip().lower() == "json":
            if (value := _pretty_json(match["code"])) is not None:
                fence = match["fence"]
                code = f"{fence}json\n{value}\n{fence}"
        fragments.append(code)
        cursor = match.end()
    fragments.append(_MATH.sub(replace_math, text[cursor:]))

    document = _LocalMarkdown()
    features = QTextDocument.MarkdownFeature
    document.setMarkdown("".join(fragments), features.MarkdownDialectGitHub | features.MarkdownNoHTML)
    body = _RichBody()
    body.feed(document.toHtml())
    rendered = "".join(body.parts)
    return re.sub(rf"{marker}\d+X", lambda found: replacements[found[0]], rendered)
